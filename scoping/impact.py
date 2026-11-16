#!/usr/bin/env python3
"""Phase 4.2 — 영향 산출(D24 + 보완 3건). impact-v1.1: 상위 타입 확장은 프로젝트 소스에 선언된 타입만(D24 보완 3).

입력: scoping/map.json, git base·head, head의 src/main 소스(정적 참조 폐포, git에서 읽음), corpus
출력 impact.json (결정론):
  {toolVersion, base, head, baseCommit, headCommit, pathFilter, nameResolution, ignoreKind, assumedChanged,
   changedFiles[{path, status, kind, fqcns}], changedClasses, observed[],
   unobserved[{fqcn, closurePaths[], reachedClasses[], unresolved}], globalTriggered, globalReasons[], warnings[],
   impactedRequests{rid: reasons[]}, impactedEndpoints, selectedSessions, selectedRequests,
   reductionRequests, reductionSessions, mapRef}
규칙(call-graph.md 4절 + D24): 관측 → 그 클래스가 실행된 요청 / 미관측 → 정적 참조 폐포(깊이 ≤3, 합집합, 미해결 → 전역) /
resource·build·deploy·삭제 → 전역 / verify·docs·test만 → 영향 없음(verify면 A/A 게이트 경고) / 전역 하나라도 → 전역.
선택 단위는 세션. 같은 diff 안 같은 클래스의 삭제 + 추가는 수정(Java → Kotlin, O14). 스코핑은 보수적 휴리스틱이다.

사용: .venv/bin/python scoping/impact.py --map scoping/map.json --base <ref> --head <ref> --repo . \
        --corpus corpus/corpus-v2.1.json --out impact.json [--path-filter services/] [--explain] [--ignore-kind build] \
        [--name-resolution literal] [--assume-changed <fqcn>]
"""
import argparse
import json
import re
import sys
from pathlib import Path

from common import ROOT, KINDS, classify_path, corpus_index, dumps, git, load_corpus, match_class, name_status
from map import DECL, SOURCE_ROOTS, declared_classes

IMPACT_VERSION = "impact-v1.1"
MAX_DEPTH = 3
NOISE = re.compile(r'"""[\s\S]*?"""|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])\'|//[^\n]*|/\*[\s\S]*?\*/')
TYPE_DECL = re.compile(r"\b(?:class|interface|record|enum|object)\s+([A-Z]\w*)")
REFLECTION = re.compile(r"Class\.forName|getBean\(")
A_A_WARNING = "검증 레이어 변경 — A/A 게이트 필요"


def clean_source(src: str) -> str:
    """주석·문자열 제거(문자열 안의 // 와 주석 안의 따옴표를 함께 처리하려고 한 번에 스캔)."""
    return NOISE.sub(lambda m: '""' if m.group().startswith(('"', "'")) else " ", src)


def supertypes(header: str, name: str) -> list[str]:
    """선언 헤더(첫 `{` 앞)에서 상위 타입의 단순 이름. 생성자 인자·제네릭은 지운다."""
    rest = header.split(name, 1)[1]
    for pattern in (r"\([^()]*\)", r"<[^<>]*>"):
        while re.search(pattern, rest):
            rest = re.sub(pattern, "", rest)
    return sorted({n.rsplit(".", 1)[-1] for n in re.findall(r"\b[\w.]*[A-Z]\w*\b", rest)})


def declared_types(texts) -> set:
    """소스에 선언된 타입의 단순 이름(중첩 포함)."""
    return {name for t in texts for name in TYPE_DECL.findall(t)}


class Sources:
    """head의 소스 → 클래스·참조. files = {경로: 원문}."""

    def __init__(self, files: dict[str, str], literal: bool = False, project_types: set | None = None):
        self.literal = literal
        self.raw = files
        self.text = {f: clean_source(s) for f, s in files.items()}
        self.classes: dict[str, dict] = {}     # fqcn → {file, simple, kind, supers}
        self.by_file: dict[str, list[str]] = {}
        for f, s in self.text.items():
            for c in declared_classes(f, s):
                simple = c["fqcn"].rsplit(".", 1)[1]
                decl = next(d for d in DECL.finditer(s) if d.group(1) == simple)
                header = s[decl.start():].replace("${", "").split("{")[0]
                self.classes[c["fqcn"]] = {"file": f, "simple": simple, "interface": "interface" in decl.group(0),
                                           "supers": supertypes(header, simple)}
                self.by_file.setdefault(f, []).append(c["fqcn"])
        project = project_types if project_types is not None else declared_types(self.text.values())
        for info in self.classes.values():
            info["supers"] = [s for s in info["supers"] if s in project]   # D24 보완 3 — 프레임워크 타입 공유는 관계가 아니다

    @classmethod
    def at(cls, head: str, repo: Path = ROOT, literal: bool = False) -> "Sources":
        tree = [f for f in git("ls-tree", "-r", "--name-only", head, "--", "services/", repo=repo).splitlines()
                if "/src/main/" in f and f.endswith((".java", ".kt"))]
        files = {f: git("show", f"{head}:{f}", repo=repo) for f in tree}
        scanned = {f: t for f, t in files.items() if f.startswith(SOURCE_ROOTS)}
        return cls(scanned, literal, declared_types(clean_source(t) for t in files.values()))

    def _shadowed(self, text: str, name: str, target: str) -> bool:
        """D24 보완 2: 이 파일에서 name이 target이 아닌 타입으로 해석되는가."""
        for imported in re.findall(rf"^import\s+([\w.]+\.{name})\s*;?\s*$", text, re.M):
            if imported != target:
                return True
        return bool(re.search(rf"\b(?:class|interface|record|enum|object)\s+{name}\b", text))

    def referrers(self, target: str) -> list[str]:
        """target(또는 그 상위 타입)을 이름으로 참조하는 클래스. 자기 파일 제외."""
        info = self.classes.get(target)
        simple = info["simple"] if info else target.rsplit(".", 1)[1]
        supers = info["supers"] if info else []
        out = set()
        for f, text in self.text.items():
            if info and f == info["file"]:
                continue
            by_name = re.search(rf"\b{simple}\b", text) and (self.literal or not self._shadowed(text, simple, target))
            declared = {self.classes[c]["simple"] for c in self.by_file.get(f, [])}
            if by_name or any(s not in declared and re.search(rf"\b{s}\b", text) for s in supers):
                out.update(self.by_file.get(f, []))
        return sorted(out)

    def ambiguous(self, target: str) -> bool:
        """타입 모호: 구현체가 여럿인 인터페이스, 리플렉션·문자열 빈 조회가 그 이름을 언급."""
        info = self.classes.get(target)
        if not info:
            return False
        impls = [c for c, i in self.classes.items() if info["simple"] in i["supers"]]
        if info["interface"] and len(impls) > 1:
            return True
        return any(REFLECTION.search(s) and re.search(rf"\b{info['simple']}\b", s) for s in self.raw.values())


def closure(target: str, sources: Sources, observed: set) -> dict:
    """미관측 클래스의 참조 폐포(깊이 ≤3). 관측 클래스를 지나서도 계속하고 도달한 관측 클래스를 모두 모은다."""
    depth = {target: 0}
    edges: dict[str, list[str]] = {}
    frontier = [target]
    for d in range(1, MAX_DEPTH + 1):
        following = []
        for node in frontier:
            edges[node] = sources.referrers(node)
            for r in edges[node]:
                if r not in depth:
                    depth[r] = d
                    following.append(r)
        frontier = following

    resolved = {n for n in depth if n in observed}
    changed = True
    while changed:
        changed = False
        for n, refs in edges.items():
            if n not in resolved and resolved & set(refs):
                resolved.add(n)
                changed = True

    paths: list[str] = []
    def walk(path: list[str]) -> None:
        nexts = [r for r in edges.get(path[-1], []) if r not in path] if len(path) <= MAX_DEPTH else []
        if not nexts and len(path) > 1:
            paths.append(" <- ".join(path))
        for r in nexts:
            walk(path + [r])
    walk([target])

    return {"fqcn": target, "closurePaths": sorted(paths), "reachedClasses": sorted(n for n in depth if n in observed),
            "unresolved": bool(set(depth) - resolved), "unresolvedClasses": sorted(set(depth) - resolved)}


def file_fqcns(path: str, text: str) -> list[str]:
    """class 파일 → 매칭 키. 최상위 선언 전부, 최상위 함수만이면 <파일>Kt(match_class가 정리)."""
    classes = [c["fqcn"] for c in declared_classes(path, clean_source(text))]
    if not classes:
        pkg = re.search(r"^package\s+([\w.]+)", text, re.M).group(1)
        classes = [f"{pkg}.{Path(path).stem}Kt"]
    return sorted({match_class(c) for c in classes})


def changed_files(base: str, head: str, repo: Path, path_filter: str | None) -> tuple[list[dict], set]:
    """변경 파일과 삭제된 클래스(같은 diff에서 다시 나타나지 않는 것)."""
    out, gone, present = [], set(), set()
    for e in name_status(base, head, repo, [path_filter] if path_filter else None):
        kind, fqcns = classify_path(e["path"]), []
        if kind == "class":
            if e["status"] == "D":
                before = file_fqcns(e["path"], git("show", f"{base}:{e['path']}", repo=repo))
                gone.update(before)
                fqcns = before
            else:
                after = file_fqcns(e["path"], git("show", f"{head}:{e['path']}", repo=repo))
                present.update(after)
                fqcns = after
                if e["status"] in ("M", "R"):
                    old_path = e.get("oldPath", e["path"])
                    before = file_fqcns(old_path, git("show", f"{base}:{old_path}", repo=repo))
                    if e["status"] == "M":
                        gone.update(set(before) - set(after))
                    fqcns = sorted(set(after) | set(before))
        out.append({**e, "kind": kind, "fqcns": fqcns})
    return out, gone - present


def compute(m: dict, corpus: dict, base: str, head: str, repo: Path = ROOT, path_filter: str | None = None,
            ignore_kinds=(), literal: bool = False, assume_changed=()) -> dict:
    files, deleted = changed_files(base, head, repo, path_filter)
    classes = set(assume_changed)
    reasons_global, warnings = [], []
    for f in files:
        if f["kind"] in ignore_kinds:
            continue
        if f["kind"] == "class":
            classes.update(f["fqcns"])
        elif f["kind"] in ("resource", "build", "deploy"):
            reasons_global.append(f"{f['kind']}:{f['path']}")
        elif f["kind"] == "verify" and A_A_WARNING not in warnings:
            warnings.append(A_A_WARNING)
    reasons_global.extend(f"deleted:{c}" for c in sorted(deleted))

    known = m["classes"]
    observed = sorted(classes & set(known))
    impacted: dict[str, set] = {}
    for c in observed:
        for rid in known[c]["requests"]:
            impacted.setdefault(rid, set()).add(f"observed:{c}")

    unobserved = []
    if classes - set(known):
        sources = Sources.at(head, repo, literal)
        for c in sorted(classes - set(known)):
            result = closure(c, sources, set(known))
            unobserved.append(result)
            if sources.ambiguous(c):
                reasons_global.append(f"ambiguous:{c}")
            if result["unresolved"] or not result["reachedClasses"]:
                reasons_global.append(f"unresolved:{c}")
            for reached in result["reachedClasses"]:
                for rid in known[reached]["requests"]:
                    impacted.setdefault(rid, set()).add(f"closure:{c}->{reached}")

    index = corpus_index(corpus)
    if reasons_global:
        for rid in index:
            impacted.setdefault(rid, set()).add("global")
    sessions = sorted({index[r]["session"] for r in impacted})
    selected = [rid for rid, q in index.items() if q["session"] in sessions]
    return {
        "toolVersion": IMPACT_VERSION, "base": base, "head": head, "pathFilter": path_filter,
        "baseCommit": git("rev-parse", base, repo=repo).strip(), "headCommit": git("rev-parse", head, repo=repo).strip(),
        "nameResolution": "literal" if literal else "language", "ignoreKind": sorted(ignore_kinds),
        "assumedChanged": sorted(assume_changed),
        "changedFiles": files, "changedClasses": sorted(classes), "observed": observed, "unobserved": unobserved,
        "globalTriggered": bool(reasons_global), "globalReasons": sorted(reasons_global), "warnings": warnings,
        "impactedRequests": {r: sorted(v) for r, v in sorted(impacted.items())},
        "impactedEndpoints": sorted({m["requests"][r]["endpoint"] for r in impacted}),
        "selectedSessions": sessions, "selectedRequests": sorted(selected),
        "reductionRequests": round(1 - len(selected) / len(index), 4),
        "reductionSessions": round(1 - len(sessions) / len(corpus["sessions"]), 4),
        "mapRef": {"path": "scoping/map.json", "bodySha256": m["bodySha256"]},
    }


def explain(r: dict) -> str:
    lines = [f"{r['base']}..{r['head']} 변경 클래스 {len(r['changedClasses'])}, 관측 {r['observed']}"]
    for u in r["unobserved"]:
        lines.append(f"  미관측 {u['fqcn']}: 도달 {u['reachedClasses']}, 미해결 {u['unresolvedClasses']}")
        lines.extend(f"    {p}" for p in u["closurePaths"])
    lines.append(f"  전역 {r['globalTriggered']} {r['globalReasons']}")
    lines.append(f"  영향 요청 {len(r['impactedRequests'])}, 선택 {len(r['selectedSessions'])}세션·{len(r['selectedRequests'])}요청")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="영향 산출(Phase 4.2)")
    ap.add_argument("--map", default=ROOT / "scoping" / "map.json", type=Path)
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--repo", default=ROOT, type=Path)
    ap.add_argument("--corpus", default=ROOT / "corpus" / "corpus-v2.1.json", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--path-filter")
    ap.add_argument("--explain", action="store_true")
    ap.add_argument("--ignore-kind", action="append", choices=KINDS, default=[])
    ap.add_argument("--name-resolution", choices=("language", "literal"), default="language",
                    help="literal = D24 원래 문구(이름 해석 없이 토큰만) — 오탐 사례 재현용")
    ap.add_argument("--assume-changed", action="append", default=[], help="diff 없이 이 클래스가 바뀌었다고 본다(경계 사례 재현용)")
    args = ap.parse_args(argv)
    m = json.loads(Path(args.map).read_text(encoding="utf-8"))
    result = compute(m, load_corpus(Path(args.corpus)), args.base, args.head, args.repo, args.path_filter,
                     args.ignore_kind, args.name_resolution == "literal", args.assume_changed)
    Path(args.out).write_text(dumps(result), encoding="utf-8")
    if args.explain:
        print(explain(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
