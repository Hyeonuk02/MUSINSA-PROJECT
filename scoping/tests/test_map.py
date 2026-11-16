"""맵 합성(4.1): fixture는 runs/p36-base-1 축약본이라 정본 맵과 본문이 같아야 한다."""
import json
import random
from pathlib import Path

import pytest

import map as mapmod
from common import ROOT, dumps, load_corpus

FIX = Path(__file__).resolve().parent / "fixtures" / "p36-base-1-mini"
CORPUS = load_corpus(ROOT / "corpus" / "corpus-v2.1.json")
CS = "poc.coupon.CouponService"
OPL = "poc.coupon.OrderPaidListener"


@pytest.fixture(scope="module")
def records():
    return json.loads((FIX / "legacy.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def body(records):
    return mapmod.build_map(records, CORPUS)


def test_body_equals_committed_map(body):
    committed = json.loads((ROOT / "scoping" / "map.json").read_text(encoding="utf-8"))
    assert mapmod.body_sha(body) == committed["bodySha256"]
    assert {k: committed[k] for k in body} == body


def test_record_order_does_not_change_map(records, body):
    shuffled = list(records)
    random.Random(1).shuffle(shuffled)
    assert dumps(mapmod.build_map(shuffled, CORPUS)) == dumps(body)


def test_child_hops_are_merged_and_kept_in_byHop(body):
    created = body["requests"]["R000027"]                 # 쿠폰 주문 생성 — HTTP 홉
    assert CS in created["classes"] and CS in created["byHop"]["0.h1"] and CS not in created["byHop"]["0"]
    paid = body["requests"]["R000003"]                    # 쿠폰 없는 결제 — Kafka 홉(no-op 소비)
    assert paid["byHop"]["0.e1"] == [OPL] and OPL in paid["classes"] and CS not in paid["classes"]


def test_endpoint_summary_is_union_and_hop_only_endpoint_has_no_entry_requests(body):
    assert len(body["endpoints"]) == 8
    consume = body["endpoints"]["consume.order.paid"]
    assert consume["requests"] == [] and len(consume["hopRequests"]) == 7
    assert set(consume["classes"]) == {OPL, CS, "poc.coupon.CouponRepository"}
    assert CS in body["endpoints"]["order.create"]["classes"]    # 합집합이 요청 단위보다 넓다 — 쿠폰 없는 주문도 포함
    assert CS not in body["requests"]["R000001"]["classes"]


def test_class_index_inverts_requests(body):
    for c, e in body["classes"].items():
        assert e["requests"] == sorted(r for r, q in body["requests"].items() if c in q["classes"])


def test_corpus_mismatch_is_rejected(records):
    with pytest.raises(ValueError, match="요청 집합"):
        mapmod.build_map([r for r in records if r["replayRequestId"] != "R000001"], CORPUS)


def test_truncated_callTree_is_rejected(records):
    bad = [dict(records[0], callTree={"nodes": [], "truncated": True})] + records[1:]
    with pytest.raises(ValueError, match="잘림"):
        mapmod.build_map(bad, CORPUS)


def test_request_diff_groups_by_session(body):
    other = {"requests": {r: q for r, q in body["requests"].items() if q["session"] != "S011"}}
    assert mapmod.request_diff(body, other) == {"S011": ["R000047", "R000048"]}


def test_declared_classes_java_and_kotlin():
    java = """package poc.x;
// @Service 주석은 세지 않는다
/** @Component */
@Service
public class A {
    record Inner(String v) {}
}
"""
    assert [(c["fqcn"], c["beanKinds"]) for c in mapmod.declared_classes("A.java", java)] == [("poc.x.A", ["Service"])]
    kotlin = """package poc.x

@Component
class F(@Value("\\${a.b}") names: List<String>) : OncePerRequestFilter() {
}

data class Dto(val a: Int)

interface R : JpaRepository<Dto, Long> {
}
"""
    got = {c["fqcn"]: c for c in mapmod.declared_classes("F.kt", kotlin)}
    assert got["poc.x.F"]["filter"] and got["poc.x.F"]["beanKinds"] == ["Component"]
    assert got["poc.x.Dto"]["beanKinds"] == [] and not got["poc.x.Dto"]["filter"]
    assert got["poc.x.R"]["beanKinds"] == ["repository-interface"]


@pytest.mark.parametrize("ref", mapmod.SOURCE_REFS)
def test_source_beans_at_both_refs(ref):
    beans = {c["fqcn"] for c in mapmod.source_classes(ref) if c["beanKinds"]}
    assert len(beans) == 11 and "poc.coupon.OrderPaidListener" in beans and "poc.order.requestlog.RequestLogFilter" in beans
