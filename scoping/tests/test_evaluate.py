"""오프라인 평가(4.3): 지표 정의를 합성 입력으로 고정한다."""
import json
from math import comb
from pathlib import Path

import evaluate as ev

FIX = Path(__file__).resolve().parent / "fixtures" / "p36-base-1-mini"


def pair(session, verdict="SAME", rid=None):
    return {"session": session, "rid": rid or session, "verdict": verdict}


PAIRS = {"a/0": pair("S1", "CONTRACT_VIOLATION", "a"), "b/0": pair("S2", "UNCERTAIN", "b"), "c/0": pair("S3", rid="c"),
         ev.F0_PAIR: pair("S4", "CONTRACT_VIOLATION", "R000047")}


def test_recall_excludes_f0_by_default_and_counts_improvement_as_diff():
    assert ev.recall(PAIRS, {"S1"}) == 0.5
    assert ev.recall(PAIRS, {"S1"}, exclude_f0=False) == round(1 / 3, 4)
    assert ev.recall({"x/0": pair("S1", "IMPROVEMENT")}, {"S1"}) == 1.0


def test_recall_zero_denominator_is_na_not_one():
    assert ev.recall({"c/0": pair("S3")}, {"S3"}) is None
    assert ev.recall({ev.F0_PAIR: pair("S4", "CONTRACT_VIOLATION")}, {"S4"}) is None
    assert ev.recall({ev.F0_PAIR: pair("S4", "CONTRACT_VIOLATION")}, {"S4"}, exclude_f0=False) == 1.0


def test_precision_and_detection():
    assert ev.precision(PAIRS, {"S1", "S3"}) == 0.5
    assert ev.detection(None, PAIRS, {"S1"}, {}) is None
    assert ev.detection({"a/0": "CV", "b/0": "CV"}, PAIRS, {"S1"}, {"a": "S1", "b": "S2"}) == {"selected": 1, "total": 2, "ratio": 0.5}


def test_session_checks_recomputed_on_selection():
    verdict = {"summary": {"sessionViolations": [{"session": "S1"}, {"session": "S2"}]}}
    assert ev.session_checks(verdict, {"S1"}) == {"full": 2, "inSelected": 1}


def test_tag_request_grain_can_be_narrower_than_session():
    pairs = {"r1/0": pair("S1", "CONTRACT_VIOLATION", "r1"), "r2/0": pair("S1", "SAME", "r2"), "r3/0": pair("S2", "SAME", "r3")}
    t = ev.tag_quality(pairs, {"S1"}, {"r2"})
    assert t["session"]["rate"] == 1.0 and t["session"]["budget"] == round(2 / 3, 4)
    assert t["request"]["rate"] == 0.0 and t["request"]["budget"] == round(1 / 3, 4)


def test_b2s_enumerates_all_subsets():
    sizes = {f"S{i}": 1 for i in range(1, 12)}
    pairs = {"a/0": pair("S1", "CONTRACT_VIOLATION", "a")}
    r = ev.b2s(pairs, [f"S{i}" for i in range(1, 8)], 7, sizes)
    same = r["sameSessionCount"]
    assert same["subsets"] == comb(11, 7) == 330
    assert same["fullRecallRate"] == round(7 / 11, 4) and same["mean"] == round(7 / 11, 4) and same["min"] == 0
    assert r["requestBudget"]["subsets"] == sum(comb(11, k) for k in range(8))


def test_b2s_na_without_diffs():
    assert ev.b2s({"c/0": pair("S3")}, ["S3"], 1, {"S3": 1}) is None


MAP = {"classes": {"C": {"requests": ["R1"], "endpoints": ["e"]}, "H": {"requests": ["R1"], "endpoints": ["e"]}},
       "endpoints": {"e": {"requests": ["R1", "R2"], "hopRequests": [], "classes": ["C", "H"], "sessions": []}},
       "requests": {"R1": {"session": "S1", "endpoint": "e", "classes": ["C", "H"], "byHop": {"0": ["C"], "0.h1": ["H"]}},
                    "R2": {"session": "S2", "endpoint": "e", "classes": ["C"], "byHop": {"0": ["C"]}}}}


def test_endpoint_union_map_widens_to_all_requests_of_endpoint():
    assert ev.endpoint_union_map(MAP)["classes"]["H"]["requests"] == ["R1", "R2"]


def test_no_hop_merge_map_drops_hop_only_classes():
    assert set(ev.no_hop_merge_map(MAP)["classes"]) == {"C"}


def test_pair_verdicts_reads_fixture():
    pairs = ev.pair_verdicts(json.loads((FIX / "verdict.json").read_text(encoding="utf-8")))
    assert len(pairs) == 60 and pairs[ev.F0_PAIR]["verdict"] == "CONTRACT_VIOLATION"
