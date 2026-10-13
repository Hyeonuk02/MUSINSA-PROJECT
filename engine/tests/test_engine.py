"""Phase 3.4 엔진 테스트(review.py 라벨 흐름은 test_review.py) — fixture p33-mini(runs/p33-1의 S001·S006·S007·S008)의 사본에서 new만 변조한다.
클러스터 접근 없음. 규칙 디렉터리도 tmp 사본을 써서 engine/rules/를 건드리지 않는다."""
import json
import shutil
from pathlib import Path

import pytest
import yaml

from ruleset import RuleError, RuleSet
from verdict import dumps, judge_run

ENGINE = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "p33-mini"
CV, UNC, IMP, SAME = "CONTRACT_VIOLATION", "UNCERTAIN", "IMPROVEMENT", "SAME"


@pytest.fixture
def run(tmp_path):
    dest = tmp_path / "p33-mini"            # 입력 계약: 디렉터리 이름 == runId
    shutil.copytree(FIXTURE, dest)
    return dest


@pytest.fixture
def rules(tmp_path):
    dest = tmp_path / "rules"
    shutil.copytree(ENGINE / "rules", dest, ignore=shutil.ignore_patterns("*.pyc"))
    for f in (dest / "learned").glob("*.yaml"):
        f.unlink()
    return dest


def tamper(run_dir: Path, rid: str, hop: str, fn) -> None:
    path = run_dir / "new.json"
    recs = json.loads(path.read_text(encoding="utf-8"))
    hit = [r for r in recs if r["replayRequestId"] == rid and r["hopPath"] == hop]
    assert len(hit) == 1
    fn(hit[0], recs)
    path.write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")


def next_seq(rec: dict) -> int:
    seqs = ([s["seq"] for s in rec["dbAccess"]["statements"]] + [c["seq"] for c in rec["externalCalls"]]
            + [p["seq"] for p in rec["events"]["published"]] + [t["seq"] for t in rec["transactions"]])
    return max(seqs, default=0) + 1


def body(rec: dict, **changes) -> None:
    b = json.loads(rec["response"]["body"])
    b.update(changes)
    rec["response"]["body"] = json.dumps(b, ensure_ascii=False, separators=(",", ":"))


def pair(result: dict, rid: str, hop: str = "0") -> dict:
    return next(p for p in result["pairs"] if p["replayRequestId"] == rid and p["hopPath"] == hop)


def others_same(result: dict, *keys) -> None:
    """변조한 pair 외에는 모두 SAME — 변조가 다른 pair로 새지 않았는지."""
    bad = [(p["replayRequestId"], p["hopPath"], p["verdict"]) for p in result["pairs"]
           if (p["replayRequestId"], p["hopPath"]) not in keys and p["verdict"] != SAME]
    assert bad == []


def has(violations: list[str], prefix: str) -> bool:
    return any(v.startswith(prefix) for v in violations)


# ---------------------------------------------------------------- 기준선
def test_fixture_all_same_all_arms(run, rules):
    for arm in ("B0", "B1", "C"):
        r = judge_run(run, rules, arm)
        assert r["summary"]["verdicts"] == {SAME: 25}, arm
    r = judge_run(run, rules, "C")
    assert r["runChecks"][0]["ok"] is True


@pytest.mark.parametrize("name", ["p33-1", "p33-2", "p33-3"])
def test_real_runs_all_same(name, rules):
    """runs/는 gitignore — 있으면 실제 A/A run 전체로 B0·B1·C 확인, 없으면 건너뜀."""
    run_dir = ENGINE.parent / "runs" / name
    if not (run_dir / "new.json").exists():
        pytest.skip(f"{run_dir} 없음")
    for arm in ("B0", "B1", "C"):
        r = judge_run(run_dir, rules, arm)
        assert set(r["summary"]["verdicts"]) == {SAME}, arm


def test_output_deterministic(run, rules):
    a = dumps(judge_run(run, rules, "C"))
    b = dumps(judge_run(run, rules, "C"))
    assert a == b
    head = json.loads(a)["engine"]
    assert head["version"].startswith("engine-v1.1") and set(head["rules"]) >= {"contract.yaml", "improvement.yaml"}


# ---------------------------------------------------------------- 계획 7건
def test_response_field_added_is_uncertain(run, rules):
    tamper(run, "R000028", "0", lambda r, _: body(r, note="hello"))
    r = judge_run(run, rules, "C")
    p = pair(r, "R000028")
    assert p["verdict"] == UNC and [u["diffKind"] for u in p["uncertain"]] == ["response.addedFields"]
    others_same(r, ("R000028", "0"))


def test_amount_change_is_cv(run, rules):
    tamper(run, "R000029", "0", lambda r, _: body(r, amount=1))
    r = judge_run(run, rules, "C")
    p = pair(r, "R000029")
    assert p["verdict"] == CV and has(p["violations"], "response_body_compatible")
    others_same(r, ("R000029", "0"))


def test_insert_removed_is_cv_write_set(run, rules):
    def drop(rec, _):
        st = rec["dbAccess"]["statements"]
        idx = next(i for i, s in enumerate(st) if s["sql"].lower().startswith("insert into order_items"))
        del st[idx]
    tamper(run, "R000027", "0", drop)
    r = judge_run(run, rules, "C")
    p = pair(r, "R000027")
    assert p["verdict"] == CV and has(p["violations"], "writeSet")
    others_same(r, ("R000027", "0"))



def test_gateway_charged_twice_is_cv_session_rule(run, rules):
    def dup(rec, _):
        call = dict(rec["externalCalls"][0], seq=next_seq(rec), childHopPath="0.h2")
        rec["externalCalls"].append(call)
    tamper(run, "R000029", "0", dup)
    r = judge_run(run, rules, "C")
    p = pair(r, "R000029")
    assert p["verdict"] == CV and has(p["violations"], "gateway_calls_per_idem_key_le_1[idem-R000029]: legacy 1 / new 2")


def test_publish_before_commit_begin_is_cv(run, rules):
    def swap(rec, _):
        pub, begin = rec["events"]["published"][0], rec["transactions"][0]
        assert begin["phase"] == "COMMIT_BEGIN" and pub["seq"] > begin["seq"]
        pub["seq"], begin["seq"] = begin["seq"], pub["seq"]
    tamper(run, "R000029", "0", swap)
    r = judge_run(run, rules, "C")
    p = pair(r, "R000029")
    assert p["verdict"] == CV and has(p["violations"], "publish_after_commit_begin")
    others_same(r, ("R000029", "0"))


def test_duplicate_child_hop_is_cv_hop_set(run, rules):
    def dup(rec, recs):
        rec["externalCalls"].append(dict(rec["externalCalls"][0], seq=next_seq(rec), childHopPath="0.h2"))
        child = json.loads(json.dumps(next(x for x in recs if x["replayRequestId"] == "R000027" and x["hopPath"] == "0.h1")))
        child["hopPath"] = "0.h2"
        child["request"]["headers"]["x-replay-hop-path"] = "0.h2"
        recs.append(child)
    tamper(run, "R000027", "0", dup)
    r = judge_run(run, rules, "C")
    p = pair(r, "R000027")
    assert p["verdict"] == CV and has(p["violations"], "hop_set: legacy만 [] / new만 ['0.h2']")
    assert all(x["hopPath"] != "0.h2" for x in r["pairs"])       # 한쪽에만 있는 홉은 pair가 아니다


def add_select(rec, _):
    rec["dbAccess"]["statements"].append({"seq": next_seq(rec), "sql": "select o1_0.id from orders o1_0 where o1_0.id=?"})


def test_select_added_uncertain_when_undeclared(run, rules):
    tamper(run, "R000028", "0", add_select)
    r = judge_run(run, rules, "C")
    p = pair(r, "R000028")
    assert p["verdict"] == UNC and [u["diffKind"] for u in p["uncertain"]] == ["dbRead.countDelta"]
    others_same(r, ("R000028", "0"))


def test_select_added_cv_when_max_selects_declared(run, rules):
    contract = yaml.safe_load((rules / "contract.yaml").read_text(encoding="utf-8"))
    legacy = json.loads((run / "legacy.json").read_text(encoding="utf-8"))
    base = next(r for r in legacy if r["replayRequestId"] == "R000028")
    reads = sum(1 for s in base["dbAccess"]["statements"] if s["sql"].lower().startswith("select"))
    contract["checks"]["max_selects"]["endpoints"] = {"order.get": reads}
    (rules / "contract.yaml").write_text(yaml.safe_dump(contract, allow_unicode=True), encoding="utf-8")
    tamper(run, "R000028", "0", add_select)
    r = judge_run(run, rules, "C")
    p = pair(r, "R000028")
    assert p["verdict"] == CV and has(p["violations"], f"max_selects[order.get]: new readCount {reads + 1} > {reads}")
    others_same(r, ("R000028", "0"))


# ---------------------------------------------------------------- 추가
def test_ack_failed_is_cv(run, rules):
    tamper(run, "R000029", "0", lambda r, _: r["events"]["published"][0].update(ack="failed"))
    p = pair(judge_run(run, rules, "C"), "R000029")
    assert p["verdict"] == CV and has(p["violations"], "events.published[0].ack")


def test_consume_outcome_failed_is_cv(run, rules):
    tamper(run, "R000029", "0.e1", lambda r, _: r.update(consumeOutcome="failed"))
    r = judge_run(run, rules, "C")
    p = pair(r, "R000029", "0.e1")
    assert p["endpoint"] == "consume.order.paid"
    assert p["verdict"] == CV and has(p["violations"], "consumeOutcome")
    others_same(r, ("R000029", "0.e1"))


def test_call_tree_only_is_uncertain(run, rules):
    tamper(run, "R000028", "0", lambda r, _: r["callTree"]["nodes"][-1].update(method="findByOrderKeyV2"))
    p = pair(judge_run(run, rules, "C"), "R000028")
    assert p["verdict"] == UNC and [u["diffKind"] for u in p["uncertain"]] == ["callTree.sequenceReplaced"]


def test_transaction_name_only_is_uncertain(run, rules):
    def rename(rec, _):
        for t in rec["transactions"]:
            t["name"] = t["name"].replace("OrderService", "PaymentService")
    tamper(run, "R000029", "0", rename)
    p = pair(judge_run(run, rules, "C"), "R000029")
    assert p["verdict"] == UNC and [u["diffKind"] for u in p["uncertain"]] == ["transactions.nameChanged"]


def test_proxy_and_kotlin_names_normalized(run, rules):
    """CGLIB·Kotlin 접미사만 다른 callTree는 SAME(Normalization v1)."""
    def kt(rec, _):
        for n in rec["callTree"]["nodes"]:
            n["class"] = n["class"] + "Kt$$SpringCGLIB$$0"
    tamper(run, "R000028", "0", kt)
    assert pair(judge_run(run, rules, "C"), "R000028")["verdict"] == SAME


@pytest.mark.parametrize("key", ["sessionId", "replayRequestId", "runId"])
def test_rule_with_instance_key_rejected(rules, key):
    rule = {"id": "bad", "scope": "request", "verdict": "same", "reason": "x",
            "provenance": {"author": "t", "date": "2026-10-13", "runId": "p33-mini", "split": "learn", "sessions": ["S006"]},
            "match": {"endpoint": "order.get", "diffKind": "response.addedFields", "fields": ["note"], key: "S006"}}
    (rules / "learned" / "bad.yaml").write_text(yaml.safe_dump(rule), encoding="utf-8")
    with pytest.raises(RuleError, match=key):
        RuleSet(rules)




def test_status_mismatch_never_explained_by_rule(run, rules):
    tamper(run, "R000028", "0", lambda r, _: r["response"].update(status=500))
    p = pair(judge_run(run, rules, "C"), "R000028")
    assert p["verdict"] == CV and has(p["violations"], "response.status")


def test_settle_without_use_is_cv_session_rule(run, rules):
    """같은 couponKey의 use(200)가 앞서지 않은 settle 소비 → coupon_transition_order 위반."""
    tamper(run, "R000027", "0.h1", lambda r, _: r["response"].update(status=409))
    r = judge_run(run, rules, "C")
    assert pair(r, "R000027", "0.h1")["verdict"] == CV
    p = pair(r, "R000029", "0.e1")
    assert p["verdict"] == CV and has(p["violations"], "coupon_transition_order[ck-R000026]: new에서 use 없이 SETTLED")


def test_id_value_masked_but_key_compared(run, rules):
    """DB auto id는 값만 가린다 — 값이 달라도 SAME, 키가 빠지면 CV(response_body_compatible)."""
    tamper(run, "R000028", "0", lambda r, _: body(r, id=999))
    assert pair(judge_run(run, rules, "C"), "R000028")["verdict"] == SAME

    def drop_id(rec, _):
        b = json.loads(rec["response"]["body"])
        del b["id"]
        rec["response"]["body"] = json.dumps(b, separators=(",", ":"))
    tamper(run, "R000028", "0", drop_id)
    p = pair(judge_run(run, rules, "C"), "R000028")
    assert p["verdict"] == CV and has(p["violations"], 'response_body_compatible: response.removedFields {"fields":["id"]}')
    for arm in ("B0", "B1"):
        assert pair(judge_run(run, rules, arm), "R000028")["verdict"] == "DIFF"


def test_contract_file_option(run, rules):
    """--contract로 같은 run을 다른 계약 선언(maxSelects)으로 판정 — 어떤 계약 파일을 썼는지 sha와 함께 기록."""
    tamper(run, "R000028", "0", add_select)
    base = judge_run(run, rules, "C")
    alt = judge_run(run, rules, "C", rules / "contract-maxselects.yaml")
    assert pair(base, "R000028")["verdict"] == UNC and base["engine"]["contract"] == "contract.yaml"
    assert pair(alt, "R000028")["verdict"] == CV and alt["engine"]["contract"] == "contract-maxselects.yaml"
    assert "contract-maxselects.yaml" in alt["engine"]["rules"] and "contract.yaml" not in alt["engine"]["rules"]
