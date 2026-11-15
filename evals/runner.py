"""Eval runner: executes cases in-process through run_turn against seeded Postgres."""

import json
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import psycopg
import yaml
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel

import supportkit.aio
from evals.checks import check_forbidden, check_turn, extract_tool_calls
from evals.models import EvalCase, load_cases
from supportkit.bootstrap import open_runtime
from supportkit.core.graph.state import SupportContext, thread_id_for
from supportkit.core.graph.turn import run_turn
from supportkit.settings import get_settings

EVAL_NOW = "2026-11-15T12:00:00+07:00"  # = seed ANCHOR, so runs are reproducible
THRESHOLDS_PATH = Path(__file__).parent / "thresholds.yaml"


class TurnReport(BaseModel):
    user: str
    reply: str | None
    tool_calls: list[dict]
    failures: list[str]


class CaseReport(BaseModel):
    id: str
    category: str
    passed: bool
    error: str | None
    turns: list[TurnReport]
    latency_ms: int


class RunReport(BaseModel):
    run_id: str
    model: str
    dataset: str
    started_at: str
    total: int
    passed: int
    pass_rate: float
    by_category: dict[str, dict[str, float | int]]
    thresholds_met: bool
    threshold_failures: list[str]
    cases: list[CaseReport]


async def _run_case(
    case: EvalCase, *, database_url: str, model_spec: str, run_id: str, model: BaseChatModel | None
) -> CaseReport:
    ctx = SupportContext(
        shop_id=case.shop_id,
        channel=case.customer_context.channel,
        channel_user_id=f"eval-{run_id}-{case.id}",
        customer_id=case.customer_context.customer_id,
        now=EVAL_NOW,
    )
    start = time.perf_counter()
    turns: list[TurnReport] = []
    error: str | None = None
    runtime_cm = None
    runtime = None
    try:
        runtime_cm = open_runtime(database_url, model_spec, model=model)
        runtime = await runtime_cm.__aenter__()
        for turn in case.turns:
            if turn.restart_before:
                old_cm, runtime_cm, runtime = runtime_cm, None, None
                await old_cm.__aexit__(None, None, None)
                runtime_cm = open_runtime(database_url, model_spec, model=model)
                runtime = await runtime_cm.__aenter__()
            result = await run_turn(runtime.graph, ctx, turn.user)
            failures = check_turn(turn.expected, result.reply, result.messages)
            failures += check_forbidden(case.expected.forbidden, result.reply, result.messages)
            turns.append(
                TurnReport(
                    user=turn.user,
                    reply=result.reply,
                    tool_calls=extract_tool_calls(result.messages),
                    failures=failures,
                )
            )
    except Exception as e:  # noqa: BLE001 - a failing case must not stop the run
        error = f"{type(e).__name__}: {e}"
    finally:
        try:
            if runtime is not None:
                await runtime.checkpointer.adelete_thread(thread_id_for(ctx))
        finally:
            if runtime_cm is not None:
                await runtime_cm.__aexit__(None, None, None)
    passed = error is None and all(not t.failures for t in turns)
    return CaseReport(
        id=case.id,
        category=case.category,
        passed=passed,
        error=error,
        turns=turns,
        latency_ms=int((time.perf_counter() - start) * 1000),
    )


async def run_cases(
    cases: list[EvalCase],
    *,
    database_url: str,
    model_spec: str,
    run_id: str,
    model: BaseChatModel | None = None,
) -> list[CaseReport]:
    reports: list[CaseReport] = []
    for case in cases:
        reports.append(
            await _run_case(
                case, database_url=database_url, model_spec=model_spec, run_id=run_id, model=model
            )
        )
    return reports


def _db_ready(database_url: str) -> bool:
    try:
        with psycopg.connect(database_url, connect_timeout=3) as conn:
            row = conn.execute(
                "SELECT 1 FROM orders WHERE shop_id='baan-bai-cha' AND order_no='BC-1042'"
            ).fetchone()
    except psycopg.Error:
        return False
    return row is not None


def _first_failure(report: CaseReport) -> str:
    if report.error:
        return report.error
    for t in report.turns:
        if t.failures:
            return t.failures[0]
    return ""


def run_cli(
    *,
    dataset: Path,
    model: str | None,
    tag: str | None,
    case: str | None,
    report_dir: Path,
    require_all: bool,
) -> int:
    settings = get_settings()
    model_spec = model or settings.supportkit_model
    run_id = uuid4().hex[:12]

    cases = load_cases(dataset)
    cases = [c for c in cases if (tag is None or tag in c.tags) and (case is None or c.id == case)]
    if not cases:
        print("Error: no cases selected (check --tag / --case).")
        return 2

    if not _db_ready(settings.database_url):
        print("Database not ready: run `supportkit migrate` and `supportkit seed`.")
        return 2

    started_at = datetime.now(ZoneInfo("Asia/Bangkok")).isoformat(timespec="seconds")
    reports = supportkit.aio.run(
        run_cases(cases, database_url=settings.database_url, model_spec=model_spec, run_id=run_id)
    )

    thresholds = yaml.safe_load(THRESHOLDS_PATH.read_text(encoding="utf-8")) or {}
    total = len(reports)
    passed = sum(r.passed for r in reports)
    pass_rate = passed / total
    by_category: dict[str, dict[str, float | int]] = {}
    for r in reports:
        c = by_category.setdefault(r.category, {"total": 0, "passed": 0, "pass_rate": 0.0})
        c["total"] += 1
        c["passed"] += int(r.passed)
    for c in by_category.values():
        c["pass_rate"] = c["passed"] / c["total"]

    failures: list[str] = []
    overall_min = thresholds.get("overall_min", 0.0)
    if pass_rate < overall_min:
        failures.append(f"overall pass_rate {pass_rate:.2f} < {overall_min}")
    for cat, minimum in (thresholds.get("category_min") or {}).items():
        if cat in by_category and by_category[cat]["pass_rate"] < minimum:
            failures.append(f"{cat} pass_rate {by_category[cat]['pass_rate']:.2f} < {minimum}")
    if require_all and passed != total:
        failures.append(f"require_all: {total - passed} case(s) failed")

    for r in reports:
        if r.passed:
            print(f"PASS {r.id} {r.category} {r.latency_ms}ms")
        else:
            print(f"FAIL {r.id} {r.category}  {_first_failure(r)}")
            for t in r.turns:
                print(f"     reply: {t.reply!r}")
    print(f"model: {model_spec}")
    print(f"{passed}/{total} passed")
    for cat, c in sorted(by_category.items()):
        print(f"  {cat}: {c['passed']}/{c['total']} ({c['pass_rate']:.2f})")
    for f in failures:
        print(f"THRESHOLD FAILURE: {f}")

    report = RunReport(
        run_id=run_id,
        model=model_spec,
        dataset=str(dataset),
        started_at=started_at,
        total=total,
        passed=passed,
        pass_rate=pass_rate,
        by_category=by_category,
        thresholds_met=not failures,
        threshold_failures=failures,
        cases=reports,
    )
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / f"{run_id}.json").write_text(
        json.dumps(report.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0 if not failures else 1
