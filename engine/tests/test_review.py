"""Phase 3.4 review.py 테스트 — learn 라벨 → learned 규칙 → 재판정. eval 세션은 보이지도, 라벨되지도 않는다."""
import yaml

import review
from test_engine import IMP, SAME, UNC, body, judge_run, others_same, pair, run, rules, tamper  # noqa: F401 (fixture)


def test_response_field_added_uncertain_then_label_improvement(run, rules):
    tamper(run, "R000028", "0", lambda r, _: body(r, note="hello"))
    r = judge_run(run, rules, "C")
    p = pair(r, "R000028")
    assert p["verdict"] == UNC and p["uncertain"][0]["diffKind"] == "response.addedFields"
    uid = p["uncertain"][0]["uid"]
    assert review.main(["label", "--run", str(run), "--rules", str(rules), "--uid", uid,
                        "--as", "improvement", "--reason", "응답에 note 필드 추가(하위 호환)"]) == 0
    learned = yaml.safe_load((rules / "learned" / f"{uid}.yaml").read_text(encoding="utf-8"))
    assert learned["provenance"]["split"] == "learn" and learned["provenance"]["sessions"] == ["S006"]
    r = judge_run(run, rules, "C")
    p = pair(r, "R000028")
    assert p["verdict"] == IMP and p["appliedRules"][0]["rule"] == f"learned-{uid}"
    others_same(r, ("R000028", "0"))

def test_learn_label_clears_eval_uncertain(run, rules):
    note = lambda r, _: body(r, note="hello")
    tamper(run, "R000028", "0", note)       # S006 learn
    tamper(run, "R000034", "0", note)       # S007 eval, 같은 endpoint·같은 diff
    r = judge_run(run, rules, "C")
    learn, ev = pair(r, "R000028"), pair(r, "R000034")
    assert learn["verdict"] == UNC and ev["verdict"] == UNC
    assert learn["uncertain"][0]["uid"] == ev["uncertain"][0]["uid"]
    uid = learn["uncertain"][0]["uid"]
    assert review.main(["label", "--run", str(run), "--rules", str(rules), "--uid", uid,
                        "--as", "same", "--reason", "note는 표시용"]) == 0
    r = judge_run(run, rules, "C")
    assert pair(r, "R000028")["verdict"] == SAME and pair(r, "R000034")["verdict"] == SAME
    assert pair(r, "R000034")["appliedRules"][0]["rule"] == f"learned-{uid}"

def test_eval_only_uid_cannot_be_labeled(run, rules, capsys):
    tamper(run, "R000034", "0", lambda r, _: body(r, note="hello"))
    uid = pair(judge_run(run, rules, "C"), "R000034")["uncertain"][0]["uid"]
    assert review.main(["list", "--run", str(run), "--rules", str(rules), "--split", "learn"]) == 0
    assert uid not in capsys.readouterr().out
    assert review.main(["label", "--run", str(run), "--rules", str(rules), "--uid", uid,
                        "--as", "same", "--reason", "x"]) == 2
    assert not list((rules / "learned").glob("*.yaml"))


def test_label_response_hash_changed(run, rules):
    """engine-v1.3: responseHashChanged도 learn에서 라벨 가능(제안 matcher host·path)."""
    tamper(run, "R000027", "0", lambda r, _: r["externalCalls"][0].update(responseBodyHash="sha256:" + "0" * 64))
    p = pair(judge_run(run, rules, "C"), "R000027")
    uid = next(u["uid"] for u in p["uncertain"] if u["diffKind"] == "externalCalls.responseHashChanged")
    assert review.main(["label", "--run", str(run), "--rules", str(rules), "--uid", uid,
                        "--as", "same", "--reason", "Coupon 응답 표현 변경(내용 동일)"]) == 0
    m = yaml.safe_load((rules / "learned" / f"{uid}.yaml").read_text(encoding="utf-8"))["match"]
    assert m["host"] == "coupon" and m["path"] == r"/api/coupons/ck\-R000026/use"
    assert pair(judge_run(run, rules, "C"), "R000027")["verdict"] == SAME
