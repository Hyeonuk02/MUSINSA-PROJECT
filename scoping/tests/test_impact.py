"""영향 산출(4.2): 합성 소스·임시 git 레포만 쓴다 — 실제 변형의 결과는 check_scope.py가 사전 등록과 대조한다."""
import subprocess
from pathlib import Path

import pytest

import impact
from impact import Sources, clean_source, closure, supertypes

J = "services/order/src/main/java/poc/order/"
K = "services/order/src/main/kotlin/poc/order/"


def src(**files):
    return {J + n.replace("_", "/") + ".java": t for n, t in files.items()}


def test_clean_source_drops_comments_and_strings_keeps_annotations():
    text = clean_source('/* Order */ // Order\n@Order(1)\nString s = "Order // x"; // it\'s Order\nchar c = \'"\';\nOrder o;\n')
    assert text.count("Order") == 2


@pytest.mark.parametrize("header,name,want", [
    ('class F(val a: List<String>, b: Int) : OncePerRequestFilter()', "F", ["OncePerRequestFilter"]),
    ("public class A extends B<C> implements D, e.f.G ", "A", ["B", "D", "G"]),
    ("class Order protected constructor() ", "Order", []),
])
def test_supertypes(header, name, want):
    assert supertypes(header, name) == want


TARGET = "package poc.order;\npublic class Order {}\n"


def refs(body: str, literal=False, name="Filter"):
    files = {J + "Order.java": TARGET, f"services/order/src/main/java/poc/order/x/{name}.java": f"package poc.order.x;\n{body}\n"}
    return Sources(files, literal).referrers("poc.order.Order")


def test_other_package_single_import_shadows_name():
    body = "import org.springframework.core.annotation.Order;\n@Order(1)\npublic class Filter {}"
    assert refs(body) == []
    assert refs(body, literal=True) == ["poc.order.x.Filter"]


def test_target_import_counts():
    assert refs("import poc.order.Order;\npublic class Filter { Order o; }") == ["poc.order.x.Filter"]


def test_nested_declaration_of_same_name_shadows():
    assert refs("public class Filter { record Order(String v) {} Order o; }") == []


def test_wildcard_import_does_not_shadow():
    assert refs("import org.other.*;\npublic class Filter { Order o; }") == ["poc.order.x.Filter"]


def test_kotlin_alias_import_does_not_shadow():
    assert refs("import org.other.Order as Other\nclass Filter { val a: Order? = null }") == ["poc.order.x.Filter"]


def test_top_level_same_name_in_other_service_is_not_a_reference():
    files = {K + "ClockConfig.kt": "package poc.order\nclass ClockConfig\n",
             "services/coupon/src/main/java/poc/coupon/ClockConfig.java": "package poc.coupon;\npublic class ClockConfig {}\n"}
    assert Sources(files).referrers("poc.order.ClockConfig") == []


def test_referrers_via_supertype_name():
    files = src(Base="package poc.order;\npublic interface Base {}",
                Impl="package poc.order;\npublic class Impl implements Base {}",
                User="package poc.order;\npublic class User { Base b; }")
    assert Sources(files).referrers("poc.order.Impl") == ["poc.order.User"]


def graph(**edges):
    """edges: 클래스 → 그 클래스가 참조하는 클래스들."""
    return Sources({J + n + ".java": f"package poc.order;\npublic class {n} {{ {' '.join(t + ' a' + str(i) + ';' for i, t in enumerate(ts))} }}"
                    for n, ts in edges.items()})


def test_closure_passes_through_observed_and_unions():
    s = graph(Entity=[], Repo=["Entity"], Svc=["Repo"], Ctrl=["Svc"])
    r = closure("poc.order.Entity", s, {"poc.order.Repo", "poc.order.Svc", "poc.order.Ctrl"})
    assert r["reachedClasses"] == ["poc.order.Ctrl", "poc.order.Repo", "poc.order.Svc"] and not r["unresolved"]
    assert r["closurePaths"] == ["poc.order.Entity <- poc.order.Repo <- poc.order.Svc <- poc.order.Ctrl"]


def test_closure_no_referrers_is_unresolved():
    r = closure("poc.order.Config", graph(Config=[], Svc=[]), {"poc.order.Svc"})
    assert r["unresolved"] and r["reachedClasses"] == [] and r["closurePaths"] == []


def test_closure_one_dead_branch_is_unresolved_even_if_other_reaches():
    s = graph(Dto=[], Svc=["Dto"], Filter=["Dto"])
    r = closure("poc.order.Dto", s, {"poc.order.Svc"})
    assert r["unresolved"] and r["reachedClasses"] == ["poc.order.Svc"] and r["unresolvedClasses"] == ["poc.order.Filter"]


def test_closure_cycle_is_not_unresolved():
    s = graph(Parent=["Child"], Child=["Parent"], Repo=["Parent"])
    r = closure("poc.order.Child", s, {"poc.order.Repo"})
    assert not r["unresolved"] and r["reachedClasses"] == ["poc.order.Repo"]


def test_closure_beyond_depth_3_is_unresolved():
    s = graph(A=[], B=["A"], C=["B"], D=["C"], Svc=["D"])
    r = closure("poc.order.A", s, {"poc.order.Svc"})
    assert r["unresolved"] and r["reachedClasses"] == []


def test_ambiguous_interface_with_many_impls():
    s = Sources(src(Base="package poc.order;\npublic interface Base {}",
                    A="package poc.order;\npublic class A implements Base {}",
                    B="package poc.order;\npublic class B implements Base {}"))
    assert s.ambiguous("poc.order.Base") and not s.ambiguous("poc.order.A")


# ---------------------------------------------------------------- 임시 레포
MAP = {"bodySha256": "x",
       "requests": {"R1": {"session": "S1", "endpoint": "a"}, "R2": {"session": "S1", "endpoint": "a"}, "R3": {"session": "S2", "endpoint": "b"}},
       "classes": {"poc.order.Svc": {"requests": ["R1"], "endpoints": ["a"]}, "poc.order.Other": {"requests": ["R3"], "endpoints": ["b"]}}}
CORPUS = {"sessions": [{"id": "S1", "split": "learn", "requests": [{"id": "R1", "method": "GET", "path": "/"}, {"id": "R2", "method": "GET", "path": "/"}]},
                       {"id": "S2", "split": "eval", "requests": [{"id": "R3", "method": "GET", "path": "/"}]}]}
SVC = "package poc.order;\npublic class Svc { Dto d; }\n"
DTO = "package poc.order;\npublic class Dto {}\n"
OTHER = "package poc.order;\npublic class Other {}\n"


class Repo:
    def __init__(self, path: Path):
        self.path = path
        self.run("init", "-q")
        self.run("config", "user.email", "t@t")
        self.run("config", "user.name", "t")
        self.write(J + "Svc.java", SVC)
        self.write(J + "Dto.java", DTO)
        self.write(J + "Other.java", OTHER)
        self.commit("base")
        self.run("tag", "base")

    def run(self, *args):
        subprocess.run(["git", *args], cwd=self.path, check=True, capture_output=True)

    def write(self, rel, text):
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def commit(self, msg):
        self.run("add", "-A")
        self.run("commit", "-q", "-m", msg)

    def compute(self, **kw):
        return impact.compute(MAP, CORPUS, "base", "HEAD", self.path, **kw)


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path)


def test_observed_change_selects_whole_session(repo):
    repo.write(J + "Svc.java", SVC + "// x\n")
    repo.commit("c")
    r = repo.compute()
    assert r["observed"] == ["poc.order.Svc"] and list(r["impactedRequests"]) == ["R1"]
    assert r["selectedSessions"] == ["S1"] and r["selectedRequests"] == ["R1", "R2"]
    assert r["reductionRequests"] == round(1 - 2 / 3, 4) and r["reductionSessions"] == 0.5 and not r["globalTriggered"]


def test_unobserved_change_goes_through_closure(repo):
    repo.write(J + "Dto.java", DTO + "// x\n")
    repo.commit("c")
    r = repo.compute()
    assert r["unobserved"][0]["reachedClasses"] == ["poc.order.Svc"]
    assert r["impactedRequests"] == {"R1": ["closure:poc.order.Dto->poc.order.Svc"]}


def test_java_to_kotlin_move_is_modification_not_deletion(repo):
    (repo.path / J / "Svc.java").unlink()
    repo.write(K + "Svc.kt", "package poc.order\n\nclass Svc\n")
    repo.commit("c")
    r = repo.compute()
    assert r["changedClasses"] == ["poc.order.Svc"] and not r["globalTriggered"]


def test_deleted_class_is_global(repo):
    (repo.path / J / "Other.java").unlink()
    repo.commit("c")
    r = repo.compute()
    assert r["globalTriggered"] and r["globalReasons"] == ["deleted:poc.order.Other"] and len(r["selectedRequests"]) == 3


@pytest.mark.parametrize("path,kind", [
    ("services/order/src/main/resources/application.yml", "resource"),
    ("services/order/pom.xml", "build"),
    ("deploy/k8s/x.yaml", "deploy"),
])
def test_non_class_changes_are_global_and_one_global_wins(repo, path, kind):
    repo.write(J + "Svc.java", SVC + "// x\n")
    repo.write(path, "x")
    repo.commit("c")
    r = repo.compute()
    assert r["globalReasons"] == [f"{kind}:{path}"] and r["selectedSessions"] == ["S1", "S2"]


def test_ignore_kind_drops_only_that_global(repo):
    repo.write(J + "Svc.java", SVC + "// x\n")
    repo.write("services/order/pom.xml", "x")
    repo.commit("c")
    r = repo.compute(ignore_kinds=("build",))
    assert not r["globalTriggered"] and r["selectedSessions"] == ["S1"]


def test_path_filter_excludes_outside(repo):
    repo.write("deploy/k8s/x.yaml", "x")
    repo.commit("c")
    assert repo.compute()["globalTriggered"]
    assert not repo.compute(path_filter="services/")["globalTriggered"]


def test_docs_test_verify_have_no_impact_verify_warns(repo):
    repo.write("docs/a.md", "x")
    repo.write("services/order/src/test/java/T.java", "x")
    repo.commit("c")
    r = repo.compute()
    assert r["selectedSessions"] == [] and r["warnings"] == [] and r["reductionRequests"] == 1.0
    repo.write("engine/x.py", "x")
    repo.commit("c2")
    assert repo.compute()["warnings"] == [impact.A_A_WARNING]


def test_output_is_deterministic(repo):
    repo.write(J + "Dto.java", DTO + "// x\n")
    repo.commit("c")
    assert repo.compute() == repo.compute()
