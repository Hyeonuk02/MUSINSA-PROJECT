"""Phase 4.0 스코핑 공용 테스트 — fixture p36-base-1-mini(runs/p36-base-1 축약). 클러스터·엔진 import 없음."""
import json
from collections import Counter
from pathlib import Path

import pytest

import common

FIX = Path(__file__).resolve().parent / "fixtures" / "p36-base-1-mini"


@pytest.mark.parametrize("raw, want", [
    ("poc.order.OrderService$$SpringCGLIB$$0", "poc.order.OrderService"),
    ("poc.order.OrderApplicationKt", "poc.order.OrderApplication"),
    ("poc.order.OrderService$lambda$1", "poc.order.OrderService"),
    ("poc.order.Repo$DefaultImpls", "poc.order.Repo"),
    ("poc.order.Kt", "poc.order.Kt"),
    ("poc.order.OrderController", "poc.order.OrderController"),
])
def test_clean_class_same_rules_as_engine(raw, want):
    """엔진 normalize.clean_class와 같은 규칙(엔진 테스트 test_proxy_and_kotlin_names_normalized와 같은 접미)."""
    assert common.clean_class(raw) == want


def test_match_class_uses_outer_class():
    assert common.match_class("poc.order.OrderService$Outcome") == "poc.order.OrderService"
    assert common.match_class("poc.order.CouponClient$CouponFailure$$SpringCGLIB$$0") == "poc.order.CouponClient"


def test_fixture_shape():
    recs = common.load_records(FIX)
    hops = Counter(common.hop_of(r) for r in recs)
    assert len(recs) == 60 and hops["0"] == 48 and hops["0.h1"] == 5 and hops["0.e1"] == 7


def test_endpoints_match_engine_recorded_endpoints():
    """같은 contract.yaml 표로 식별한 엔드포인트가 엔진 판정 파일의 endpoint와 모두 같다(엔진 코드 없이)."""
    eps = common.Endpoints()
    by_key = {(r["replayRequestId"], common.hop_of(r)): eps.of(r) for r in common.load_records(FIX)}
    pairs = json.loads((FIX / "verdict.json").read_text(encoding="utf-8"))["pairs"]
    assert all(by_key[(p["replayRequestId"], p["hopPath"])] == p["endpoint"] for p in pairs)
    assert len({p["endpoint"] for p in pairs}) == 8


def test_corpus_index_covers_fixture_requests():
    idx = common.corpus_index(common.load_corpus(common.ROOT / "corpus" / "corpus-v2.1.json"))
    rids = {r["replayRequestId"] for r in common.load_records(FIX)}
    assert rids <= set(idx) and len(idx) == 48 and len({v["session"] for v in idx.values()}) == 11


def test_callTree_classes_sorted_unique():
    rec = next(r for r in common.load_records(FIX) if r["replayRequestId"] == "R000003" and common.hop_of(r) == "0")
    got = common.callTree_classes(rec)
    assert got == sorted(set(got)) and "poc.order.OrderService" in got and "poc.order.PaymentGatewayClient" in got


@pytest.mark.parametrize("path, kind", [
    ("services/order/src/main/kotlin/poc/order/OrderService.kt", "class"),
    ("services/coupon/src/main/java/poc/coupon/OrderPaidListener.java", "class"),
    ("services/order/src/main/resources/application.yml", "resource"),
    ("services/order/pom.xml", "build"),
    ("services/order/Dockerfile", "build"),
    ("deploy/k8s/base/order.yaml", "deploy"),
    ("services/evidence-collector/src/main/java/poc/evidence/EvidenceFilter.java", "verify"),
    ("engine/verdict.py", "verify"),
    ("corpus/corpus-v2.1.json", "verify"),
    ("scoping/map.py", "verify"),
    ("docs/phase4-plan.md", "docs"),
    ("README.md", "docs"),
    ("services/order/src/test/kotlin/poc/order/FooTest.kt", "test"),
    (".gitignore", "build"),
])
def test_classify_path(path, kind):
    assert common.classify_path(path) == kind


def test_name_status_ladder_and_fault_shapes():
    """사다리 커밋은 Java → Kotlin이 D + A(같은 FQCN)로 나오고 new overlay 이미지 태그(deploy)도 함께 바뀐다.
    결함 브랜치는 기준선 위 1커밋으로 서비스 코드만 — 4.0 입력 점검의 근거."""
    v12 = common.name_status("fd839d6~1", "fd839d6")
    assert {(r["status"], common.classify_path(r["path"])) for r in v12} == {
        ("M", "deploy"), ("M", "build"), ("D", "class"), ("A", "class")}
    only_services = common.name_status("fd839d6~1", "fd839d6", paths=["services/"])
    assert all(r["path"].startswith("services/") for r in only_services) and len(only_services) == 3
    f1 = common.name_status("phase3.5-v1.4", "fault/F1")
    assert f1 == [{"status": "M", "path": "services/order/src/main/kotlin/poc/order/OrderService.kt"}]


def test_skeleton_clis_exit_2():
    import impact, map as mapmod, evaluate
    assert mapmod.main(["--runs", str(FIX)]) == 2
    assert impact.main(["--base", "a", "--head", "b", "--out", "/dev/null"]) == 2
    assert evaluate.main([]) == 2
