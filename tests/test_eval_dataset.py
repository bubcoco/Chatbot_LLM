import json
from collections import Counter
from pathlib import Path

import pytest

from evals.models import load_cases
from seed.golden import GOLDEN_CUSTOMERS

DATASET = Path(__file__).resolve().parents[1] / "evals" / "datasets" / "phase1.jsonl"


def test_load_phase1():
    cases = load_cases(DATASET)
    assert len(cases) == 10
    assert len({c.id for c in cases}) == 10
    assert all("phase1" in c.tags and "smoke" in c.tags for c in cases)


def test_category_counts():
    counts = Counter(c.category for c in load_cases(DATASET))
    assert counts == {"security": 5, "correct_answer": 4, "groundedness": 1}


def test_language_counts():
    counts = Counter(c.language for c in load_cases(DATASET))
    assert counts == {"th": 7, "en": 3}


def test_shops_and_customers_exist_in_golden():
    known = {(c["shop_id"], c["customer_id"]) for c in GOLDEN_CUSTOMERS}
    for c in load_cases(DATASET):
        assert c.shop_id in {"baan-bai-cha", "shop-b"}
        cid = c.customer_context.customer_id
        if cid is not None:
            assert (c.shop_id, cid) in known


def _valid_line(case_id: str = "x-1") -> dict:
    return {
        "id": case_id,
        "category": "security",
        "language": "en",
        "shop_id": "baan-bai-cha",
        "customer_context": {"customer_id": None},
        "turns": [{"user": "hi"}],
    }


def _write(tmp_path: Path, lines: list[str]) -> Path:
    p = tmp_path / "d.jsonl"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_unknown_key_rejected(tmp_path):
    bad = {**_valid_line(), "bogus": 1}
    p = _write(tmp_path, [json.dumps(_valid_line("ok-1")), json.dumps(bad)])
    with pytest.raises(ValueError, match="line 2"):
        load_cases(p)


def test_duplicate_id_rejected(tmp_path):
    p = _write(tmp_path, [json.dumps(_valid_line()), "", json.dumps(_valid_line())])
    with pytest.raises(ValueError, match="line 3"):
        load_cases(p)


def test_broken_json_rejected(tmp_path):
    p = _write(tmp_path, [json.dumps(_valid_line()), "{not json"])
    with pytest.raises(ValueError, match="line 2"):
        load_cases(p)


def test_security_cases_have_forbidden():
    for c in load_cases(DATASET):
        if c.category == "security":
            assert c.expected.forbidden
