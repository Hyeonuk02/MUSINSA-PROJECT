"""Phase 4 스코핑 공용 — run·corpus·git 읽기, 클래스 이름 정리, 엔드포인트 식별, 파일 분류.

스코핑 도구는 엔진(engine/)을 import하지 않는다(phase4-plan 2절). 읽는 것은 runs/*/legacy.json·verdict*.json,
corpus, engine/rules/contract.yaml의 엔드포인트 표(데이터), git뿐이다.
클래스 이름 정리는 엔진 Normalization v1(normalize.clean_class)과 같은 규칙을 여기서 다시 구현한다 — 같음은 tests가 확인.
"""
import json
import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "engine" / "rules" / "contract.yaml"
ENTRY_HOP = "0"


# ---------------------------------------------------------------- 클래스 이름
def clean_class(cls: str) -> str:
    """프록시·Kotlin·람다 흔적 제거(엔진 normalize.clean_class와 같은 규칙).
    `$$SpringCGLIB$$0`·`$$Lambda…` → 앞부분, `$lambda…` 제거, `$DefaultImpls` 제거, 단순 이름 끝 `Kt` 제거."""
    cls = cls.split("$$")[0]
    cls = re.sub(r"\$lambda.*$", "", cls)
    cls = cls.replace("$DefaultImpls", "")
    pkg, _, simple = cls.rpartition(".")
    if simple.endswith("Kt") and len(simple) > 2:
        simple = simple[:-2]
    return f"{pkg}.{simple}" if pkg else simple


def outer_class(fqcn: str) -> str:
    """중첩 클래스는 바깥 클래스로(`poc.order.OrderService$Outcome` → `poc.order.OrderService`) — 클래스 단위 매칭(D23)."""
    return fqcn.split("$")[0]


def match_class(cls: str) -> str:
    """맵·영향 산출에서 쓰는 매칭 키: 정리 후 바깥 클래스."""
    return outer_class(clean_class(cls))


# ---------------------------------------------------------------- run·corpus
def hop_of(rec: dict) -> str:
    return rec.get("hopPath", ENTRY_HOP)


def load_records(run_dir: Path, stack: str = "legacy") -> list[dict]:
    return json.loads((run_dir / f"{stack}.json").read_text(encoding="utf-8"))


def load_verdict(run_dir: Path, name: str = "verdict.json") -> dict:
    return json.loads((run_dir / name).read_text(encoding="utf-8"))


def load_corpus(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def corpus_index(corpus: dict) -> dict:
    """요청 id → {session, split, method, path, order}."""
    out = {}
    for s in corpus["sessions"]:
        for i, r in enumerate(s["requests"]):
            out[r["id"]] = {"session": s["id"], "split": s["split"], "method": r["method"], "path": r["path"], "order": i}
    return out


def callTree_classes(rec: dict) -> list[str]:
    """한 홉 레코드의 callTree 클래스(매칭 키) — 정렬·중복 제거."""
    return sorted({match_class(n["class"]) for n in (rec.get("callTree") or {}).get("nodes", [])})


# ---------------------------------------------------------------- 엔드포인트
class Endpoints:
    """contract.yaml endpoints 표(데이터)로 레코드의 엔드포인트 id를 식별 — 엔진과 같은 표를 읽지만 엔진 코드는 쓰지 않는다."""

    def __init__(self, contract: Path = CONTRACT):
        table = yaml.safe_load(contract.read_text(encoding="utf-8"))["endpoints"]
        self.http = [(e["id"], e["method"], re.compile(e["path"])) for e in table if "path" in e]
        self.topics = {e["topic"]: e["id"] for e in table if "topic" in e}

    def of(self, rec: dict) -> str:
        if rec.get("origin") == "kafka":
            return self.topics.get((rec.get("event") or {}).get("topic"), "unknown")
        req = rec.get("request") or {}
        return self.of_request(req.get("method", ""), req.get("path", ""))

    def of_request(self, method: str, path: str) -> str:
        for eid, m, pattern in self.http:
            if method == m and pattern.match(path):
                return eid
        return "unknown"


# ---------------------------------------------------------------- git·파일 분류 (D24)
KINDS = ("class", "test", "resource", "build", "deploy", "verify", "docs")
VERIFY_PREFIXES = ("services/evidence-collector/", "engine/", "corpus/", "k6/", "evidence-store/", "scoping/")


def classify_path(path: str) -> str:
    """파일 분류(phase4-plan 3절 D24). 순서가 중요하다 — verify·deploy·docs를 먼저 본다."""
    if path.startswith(VERIFY_PREFIXES):
        return "verify"
    if path.startswith("deploy/"):
        return "deploy"
    if path.startswith("docs/") or path.endswith(".md"):
        return "docs"
    if "/src/test/" in path:
        return "test"
    if re.search(r"/src/main/(java|kotlin)/.+\.(java|kt)$", path):
        return "class"
    if "/src/main/resources/" in path:
        return "resource"
    if path.endswith(("pom.xml", "Dockerfile", ".gradle", ".gradle.kts")):
        return "build"
    return "build"   # 분류 밖(루트 설정 파일 등)은 fail-closed — 빌드·배포 영향으로 본다(전역)


def git(*args: str, repo: Path = ROOT) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout


def name_status(base: str, head: str, repo: Path = ROOT, paths: list[str] | None = None) -> list[dict]:
    """`git diff -M --name-status base..head [-- paths]` → [{status, path, oldPath?}] (rename은 R, 새 경로 기준).
    Java → Kotlin 전환처럼 내용이 크게 바뀐 이동은 git이 R로 못 잡고 D + A로 낸다 — FQCN 기준 처리는 impact.py(4.2)의 몫."""
    out = []
    args = ["diff", "-M", "--name-status", f"{base}..{head}"] + (["--", *paths] if paths else [])
    for line in git(*args, repo=repo).splitlines():
        parts = line.split("\t")
        st = parts[0]
        if st.startswith("R") or st.startswith("C"):
            out.append({"status": st[0], "path": parts[2], "oldPath": parts[1]})
        else:
            out.append({"status": st, "path": parts[1]})
    return out


def dumps(value) -> str:
    """결정론 JSON(키 정렬, 들여쓰기 2, 끝 개행)."""
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
