"""Tag·run 대조(4.4): 합성 입력으로 태그·순서·비교 규칙을 고정한다."""
import run_check
import tag


def pair(rid, session, verdict="SAME", hop="0"):
    return {"replayRequestId": rid, "hopPath": hop, "sessionId": session, "endpoint": "e", "verdict": verdict}


VERDICT = {"pairs": [pair("R1", "S1"), pair("R2", "S1", "CONTRACT_VIOLATION"), pair("R3", "S2", "UNCERTAIN"), pair("R000047", "S2", "CONTRACT_VIOLATION")]}
IMPACT = {"selectedSessions": ["S1"], "impactedRequests": {"R1": ["observed:C"]}}


def test_in_scope_is_session_grain_and_impacted_request_is_separate():
    rows, _ = tag.build_tags(VERDICT, IMPACT)
    by = {r["pair"]: r for r in rows}
    assert by["R2/0"]["inScope"] and not by["R2/0"]["impactedRequest"]
    assert by["R1/0"]["inScope"] and by["R1/0"]["impactedRequest"]
    assert not by["R3/0"]["inScope"]


def test_review_order_three_tiers():
    rows, order = tag.build_tags(VERDICT, IMPACT)
    assert [r["tier"] for r in rows] == [1, 2, 3, 3]
    assert order[:2] == ["R1/0", "R2/0"]


def test_summary_excludes_f0_and_reports_request_grain_as_auxiliary():
    rows, _ = tag.build_tags(VERDICT, IMPACT)
    s = tag.summarize(rows)
    assert s["session"]["diffs"] == 2 and s["session"]["rate"] == 0.5 and s["requestAuxiliary"]["rate"] == 0.0
    assert s["f0"] is False


def test_compare_pairs_restricts_full_replay_to_sessions():
    full = {"pairs": [pair("R1", "S1"), pair("R2", "S2", "CONTRACT_VIOLATION")]}
    assert run_check.compare_pairs({"pairs": [pair("R1", "S1")]}, full, {"S1"}) == []
    assert run_check.compare_pairs({"pairs": [pair("R1", "S1", "UNCERTAIN")]}, full, {"S1"})
    assert run_check.compare_pairs({"pairs": [pair("R1", "S1")]}, full, None)


def test_session_violations_filtered_by_session():
    v = {"summary": {"sessionViolations": [{"session": "S1", "key": "a"}, {"session": "S2", "key": "b"}]}}
    assert len(run_check.session_violations(v, {"S1"})) == 1 and len(run_check.session_violations(v, None)) == 2
