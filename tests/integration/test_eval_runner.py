import uuid
from pathlib import Path

import psycopg
import pytest

from evals.models import (
    CaseExpectation,
    CustomerContext,
    EvalCase,
    Turn,
    TurnExpectation,
    load_cases,
)
from evals.runner import RunReport, run_cases, run_cli
from supportkit.core.llm.fake import RuleBasedFakeModel, ScriptedChatModel

DATASET = Path(__file__).resolve().parents[2] / "evals" / "datasets" / "phase1.jsonl"


@pytest.fixture(scope="module")
def seeded(database_url):
    with psycopg.connect(database_url) as conn:
        row = conn.execute(
            "SELECT 1 FROM orders WHERE shop_id='baan-bai-cha' AND order_no='BC-1042'"
        ).fetchone()
    if row is None:
        pytest.skip("seed data missing")
    return database_url


def _count_threads(url: str, run_id: str) -> int:
    with psycopg.connect(url) as conn:
        return conn.execute(
            "SELECT count(*) FROM checkpoints WHERE thread_id LIKE %s", (f"%eval-{run_id}-%",)
        ).fetchone()[0]


def _synthetic(case_id: str, forbidden: list[str]) -> EvalCase:
    return EvalCase(
        id=case_id,
        category="security",
        language="th",
        shop_id="baan-bai-cha",
        customer_context=CustomerContext(customer_id="C-0001"),
        turns=[Turn(user="ออเดอร์ BC-1042 ถึงไหนแล้วคะ", expected=TurnExpectation())],
        expected=CaseExpectation(forbidden=forbidden),
    )


async def test_full_dataset_with_fake_model_and_cleanup(seeded):
    run_id = uuid.uuid4().hex[:12]
    reports = await run_cases(
        load_cases(DATASET),
        database_url=seeded,
        model_spec="fake:rules",
        run_id=run_id,
        model=RuleBasedFakeModel(),
    )
    assert len(reports) == 10
    assert all(r.passed for r in reports), [r for r in reports if not r.passed]
    assert all(r.error is None for r in reports)
    assert _count_threads(seeded, run_id) == 0


async def test_leak_detector_fires(seeded):
    run_id = uuid.uuid4().hex[:12]
    [report] = await run_cases(
        [_synthetic("syn-leak", ["KEX26111042TH"])],
        database_url=seeded,
        model_spec="fake:rules",
        run_id=run_id,
        model=RuleBasedFakeModel(),
    )
    assert report.passed is False
    assert any("forbidden" in f for t in report.turns for f in t.failures)
    assert _count_threads(seeded, run_id) == 0


async def test_model_exception_is_contained(seeded):
    run_id = uuid.uuid4().hex[:12]
    [report] = await run_cases(
        [_synthetic("syn-boom", [])],
        database_url=seeded,
        model_spec="fake:rules",
        run_id=run_id,
        model=ScriptedChatModel(responses=[]),
    )
    assert report.passed is False
    assert report.error is not None and report.error.startswith("IndexError")
    assert _count_threads(seeded, run_id) == 0


def test_run_cli_writes_report(seeded, tmp_path):
    code = run_cli(
        dataset=DATASET,
        model="fake:rules",
        tag=None,
        case=None,
        report_dir=tmp_path,
        require_all=True,
    )
    assert code == 0
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    report = RunReport.model_validate_json(files[0].read_text(encoding="utf-8"))
    assert report.passed == 10


def test_run_cli_unknown_case(seeded, tmp_path):
    code = run_cli(
        dataset=DATASET,
        model="fake:rules",
        tag=None,
        case="does-not-exist",
        report_dir=tmp_path,
        require_all=False,
    )
    assert code == 2
