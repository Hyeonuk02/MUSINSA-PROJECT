"""Phase 4 완료 뒤 추가 검증(2026-11-13) — 판정 우선순위와 승인 규칙의 적용 범위.

test_engine.py의 rules fixture는 learned 규칙을 지운다. 여기서는 engine/rules/ 전체(사전 승인 1 + learned 5)를
tmp에 그대로 복사해 실제 judge_run()·RuleSet으로 판정한다. 합성 Evidence는 p33-mini 사본의 레코드를 고쳐 만들고
입력 계약(스키마·seq 불변식)을 그대로 통과해야 한다(judge_run이 위반이면 ValueError).
클러스터 run이 아니다 — Phase 3·4 실험 당시의 검증이 아니라 그 뒤에 더한 단위 검증이다.
"""
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from ruleset import RuleSet
from verdict import judge_run

ENGINE = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "p33-mini"
CV, UNC, IMP, SAME = "CONTRACT_VIOLATION", "UNCERTAIN", "IMPROVEMENT", "SAME"

ITEM_COUNT = "order-view-item-count"
F5_COUNT = "learned-5da05fdb147f"          # order.get dbRead.countDelta 2 → 1
F5_TREE = "learned-989c110b103e"           # order.get callTree.sequenceReplaced findByOrderKey → findWithItemsByOrderKey
F5_FP = "learned-9a82df6b99b4"             # order.get dbRead.fingerprintReplaced orders → orders join order_items
C2_COUNT = "learned-aa06c259e967"          # coupon.use dbRead.countDelta 1 → 2 (same)
C2_TREE = "learned-cfb6811c9f5c"           # coupon.use callTree.sequenceReplaced (same)

# runs/p36-F5-1 new.json의 order.get SQL 원문(F5 = fault/F5 1597c73, JOIN FETCH)
F5_JOIN_SQL = ("select o1_0.id,o1_0.amount,o1_0.coupon_key,o1_0.created_at,o1_0.discount_amount,o1_0.idempotency_key,"
               "i1_0.order_id,i1_0.id,i1_0.line_no,i1_0.price,i1_0.qty,i1_0.sku,o1_0.order_key,o1_0.status,o1_0.transaction_id "
               "from orders o1_0 join order_items i1_0 on o1_0.id=i1_0.order_id where o1_0.order_key=? order by i1_0.line_no")


@pytest.fixture
def run(tmp_path):
    dest = tmp_path / "p33-mini"            # 입력 계약: 디렉터리 이름 == runId
    shutil.copytree(FIXTURE, dest)
    return dest


@pytest.fixture
def all_rules(tmp_path):
    """engine/rules/ 전체 사본(learned 포함). 원본은 읽기만 한다."""
    dest = tmp_path / "rules"
    shutil.copytree(ENGINE / "rules", dest, ignore=shutil.ignore_patterns("*.pyc"))
    return dest


# ---------------------------------------------------------------- 합성 도우미
def edit(run_dir: Path, stack: str, rid: str, fn, hop: str = "0") -> None:
    path = run_dir / f"{stack}.json"
    recs = json.loads(path.read_text(encoding="utf-8"))
    hit = [r for r in recs if r["replayRequestId"] == rid and r["hopPath"] == hop]
    assert len(hit) == 1
    fn(hit[0])
    path.write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")


def set_body(rec: dict, b: dict) -> None:
    text = json.dumps(b, ensure_ascii=False, separators=(",", ":"))
    rec["response"]["body"] = text
    rec["response"]["bodyHash"] = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def body_update(**changes):
    def fn(rec):
        set_body(rec, json.loads(rec["response"]["body"]) | changes)
    return fn


def renumber(rec: dict) -> None:
    """타임라인 seq를 statements → externalCalls → transactions 순서로 1부터 다시 매긴다(배열 간 겹침 없음)."""
    seq = 1
    for arr in (rec["dbAccess"]["statements"], rec["externalCalls"], rec["transactions"]):
        for x in arr:
            x["seq"] = seq
            seq += 1


def f5(rec: dict) -> None:
    """F5 New: 주문·항목 SELECT 두 건(또는 주문 SELECT 한 건)을 JOIN FETCH 한 건으로, Repository 메서드 교체."""
    rec["dbAccess"]["statements"] = [{"seq": 0, "sql": F5_JOIN_SQL}]
    rec["callTree"]["nodes"][2]["method"] = "findWithItemsByOrderKey"
    renumber(rec)


def add_call(rec: dict, n: int) -> None:
    """order.get 홉에 외부 호출 n건(관측 밖 호스트 wiremock — 자식 홉 Evidence 없음). 필드는 evidence-schema-v1 externalCalls 그대로."""
    call = {"method": "GET", "host": "wiremock", "path": "/gateway/status", "status": 200,
            "requestBodyHash": "sha256:" + "0" * 64, "responseBodyHash": "sha256:" + "1" * 64}
    rec["externalCalls"] = [call | {"seq": 0, "childHopPath": f"0.h{i + 1}"} for i in range(n)]
    renumber(rec)


def pair(result: dict, rid: str, hop: str = "0") -> dict:
    return next(p for p in result["pairs"] if p["replayRequestId"] == rid and p["hopPath"] == hop)


def others_same(result: dict, *keys) -> None:
    bad = [(p["replayRequestId"], p["hopPath"], p["verdict"]) for p in result["pairs"]
           if (p["replayRequestId"], p["hopPath"]) not in keys and p["verdict"] != SAME]
    assert bad == []
    assert result["summary"]["sessionViolations"] == []
    assert result["runChecks"][0]["ok"] is True


def applied(p: dict) -> list[tuple[str, str]]:
    return [(a["rule"], a["verdict"]) for a in p["appliedRules"]]


def uncertain_kinds(p: dict) -> list[str]:
    return [u["diffKind"] for u in p["uncertain"]]


# ---------------------------------------------------------------- 규칙 로딩
def test_all_rules_loaded(all_rules):
    rs = RuleSet(all_rules)
    assert [r.id for r in rs.improvement] == [ITEM_COUNT]
    assert sorted(r.id for r in rs.learned) == sorted([F5_COUNT, F5_TREE, F5_FP, C2_COUNT, C2_TREE])
    assert len(rs.rules) == 6
    by_verdict = {r.id: r.verdict for r in rs.rules}
    assert [i for i, v in by_verdict.items() if v == "improvement"] == [ITEM_COUNT, F5_COUNT, F5_TREE, F5_FP]
    assert sorted(i for i, v in by_verdict.items() if v == "same") == sorted([C2_COUNT, C2_TREE])
    # 사본이 원본과 같다(원본은 고치지 않는다)
    for src in sorted((ENGINE / "rules").rglob("*.yaml")):
        assert (all_rules / src.relative_to(ENGINE / "rules")).read_bytes() == src.read_bytes()


def test_fixture_all_same_with_all_rules(run, all_rules):
    r = judge_run(run, all_rules, "C")
    assert r["summary"]["verdicts"] == {SAME: 25}
    assert all(p["appliedRules"] == [] for p in r["pairs"])


# ---------------------------------------------------------------- (a) 승인된 F5 변경
def test_a1_f5_count_and_tree_is_improvement(run, all_rules):
    edit(run, "new", "R000002", f5)
    r = judge_run(run, all_rules, "C")
    p = pair(r, "R000002")
    assert p["verdict"] == IMP
    assert applied(p) == [(F5_COUNT, "improvement"), (F5_TREE, "improvement")]
    assert p["violations"] == [] and p["uncertain"] == []
    others_same(r, ("R000002", "0"))


def test_a2_f5_fingerprint_and_tree_is_improvement(run, all_rules):
    """SELECT 수가 같은 경우(R000038 404: 주문 SELECT 1 → JOIN 1) — fingerprintReplaced. countDelta와는 한 pair에서 배타적."""
    edit(run, "new", "R000038", f5)
    r = judge_run(run, all_rules, "C")
    p = pair(r, "R000038")
    assert p["verdict"] == IMP
    assert applied(p) == [(F5_FP, "improvement"), (F5_TREE, "improvement")]
    assert p["violations"] == [] and p["uncertain"] == []
    others_same(r, ("R000038", "0"))


# ---------------------------------------------------------------- (b)~(d) 승인된 개선이 다른 차이를 덮지 못함
def test_b_f5_plus_amount_change_is_cv(run, all_rules):
    def fn(rec):
        f5(rec)
        body_update(amount=1)(rec)
    edit(run, "new", "R000002", fn)
    r = judge_run(run, all_rules, "C")
    p = pair(r, "R000002")
    assert p["verdict"] == CV
    assert applied(p) == [(F5_COUNT, "improvement"), (F5_TREE, "improvement")]
    assert p["violations"] == ['response_body_compatible: response.valueChanged {"from":10000,"path":"amount","to":1}']
    assert p["uncertain"] == []
    others_same(r, ("R000002", "0"))


def test_c_f5_plus_external_call_added_is_cv(run, all_rules):
    edit(run, "legacy", "R000002", lambda rec: add_call(rec, 1))
    def fn(rec):
        f5(rec)
        add_call(rec, 2)
    edit(run, "new", "R000002", fn)
    r = judge_run(run, all_rules, "C")
    p = pair(r, "R000002")
    assert p["verdict"] == CV
    assert applied(p) == [(F5_COUNT, "improvement"), (F5_TREE, "improvement")]
    assert len(p["violations"]) == 1 and p["violations"][0].startswith("externalCalls: ")
    # 호출 수가 다르면 응답 hash 목록도 달라진다 — 규칙이 없으므로 Uncertain 후보로 남는다(판정은 CV가 우선)
    assert uncertain_kinds(p) == ["externalCalls.responseHashChanged"]
    others_same(r, ("R000002", "0"))


def test_c_baseline_same_external_call_both_sides(run, all_rules):
    """(c)의 대조 — 양쪽에 같은 외부 호출 1건만 더하면 SAME(합성 호출 자체는 차이를 만들지 않는다)."""
    for stack in ("legacy", "new"):
        edit(run, stack, "R000002", lambda rec: add_call(rec, 1))
    r = judge_run(run, all_rules, "C")
    assert r["summary"]["verdicts"] == {SAME: 25}


def test_d_f5_plus_unapproved_field_is_uncertain(run, all_rules):
    def fn(rec):
        f5(rec)
        body_update(note="hello")(rec)
    edit(run, "new", "R000002", fn)
    r = judge_run(run, all_rules, "C")
    p = pair(r, "R000002")
    assert p["verdict"] == UNC
    assert applied(p) == [(F5_COUNT, "improvement"), (F5_TREE, "improvement")]
    assert p["violations"] == []
    assert [(u["diffKind"], u["detail"]) for u in p["uncertain"]] == [("response.addedFields", {"fields": ["note"]})]
    others_same(r, ("R000002", "0"))


# ---------------------------------------------------------------- (e)(f) 현재 규칙의 한계 고정
def test_e_known_limitation_wrong_item_count_is_improvement(run, all_rules):
    """현재 버전의 탐지 한계를 기록하는 테스트다. 향후 itemCount와 items.size() 사이의 의미 검증 계약을 도입하면
    기대 판정을 의도적으로 변경해야 한다.
    정상이라는 뜻이 아니다 — order-view-item-count는 추가된 필드 이름만 보므로 items 2개에 itemCount 0도 승인한다."""
    two = {"items": [{"sku": "A-1", "qty": 1, "price": 10000}, {"sku": "A-2", "qty": 1, "price": 5000}], "amount": 15000}
    edit(run, "legacy", "R000002", body_update(**two))
    edit(run, "new", "R000002", body_update(**two, itemCount=0))
    r = judge_run(run, all_rules, "C")
    p = pair(r, "R000002")
    new_body = json.loads(next(x for x in json.loads((run / "new.json").read_text(encoding="utf-8"))
                               if x["replayRequestId"] == "R000002")["response"]["body"])
    assert len(new_body["items"]) == 2 and new_body["itemCount"] == 0
    assert p["verdict"] == IMP          # 한계: 잘못된 값도 승인된다
    assert applied(p) == [(ITEM_COUNT, "improvement")]
    assert p["violations"] == [] and p["uncertain"] == []
    others_same(r, ("R000002", "0"))


def test_f_known_limitation_item_count_rule_applies_to_coupon_get(run, all_rules):
    """endpoint "*"의 실제 적용 범위 — 매처는 응답 타입을 보지 않아 OrderView가 아닌 coupon.get 응답에도 적용된다.
    "*" 자체가 결함이라는 주장이 아니라 현재 승인 범위(잠재적 과적용)를 고정하는 테스트다."""
    edit(run, "new", "R000039", body_update(itemCount=0))
    r = judge_run(run, all_rules, "C")
    p = pair(r, "R000039")
    assert p["endpoint"] == "coupon.get"
    assert p["verdict"] == IMP
    assert applied(p) == [(ITEM_COUNT, "improvement")]
    assert p["violations"] == [] and p["uncertain"] == []
    others_same(r, ("R000039", "0"))
