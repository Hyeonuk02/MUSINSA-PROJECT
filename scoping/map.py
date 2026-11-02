#!/usr/bin/env python3
"""Phase 4.1 — 맵 합성(D23).

입력: Legacy baseline run 디렉터리들(정본 runs/p36-base-1..3)의 legacy.json, corpus, contract.yaml 엔드포인트 표
출력 scoping/map.json (결정론, 커밋):
  {builtFrom: [run...], corpus: {version, sha256}, bodySha256,
   requests: {rid: {session, endpoint, classes[], byHop: {hop: classes[]}}},
   endpoints: {id: {classes[], requests[], hopRequests[], sessions[]}}, classes: {fqcn: {requests[], endpoints[]}}, coverage}
규칙: Legacy 레코드만(규칙 2). 한 요청의 모든 홉(0, 0.h*, 0.e*)의 callTree 클래스를 그 요청에 합산(byHop 보존).
엔드포인트 맵은 요청 맵의 합집합(요약·미지 요청용 — 선택에는 쓰지 않음). 매칭 키는 common.match_class.
endpoints[id].requests는 진입 홉이 그 엔드포인트인 요청, hopRequests는 자식 홉으로 닿은 요청(consume.order.paid는 진입 요청이 없다).

사용: .venv/bin/python scoping/map.py --runs runs/p36-base-1 runs/p36-base-2 runs/p36-base-3 --out scoping/map.json \
        [--compare runs/p33-1 ... runs/p35-base-3]
--runs의 맵이 서로 다르면 exit 1, --compare에서 S011 밖 차이가 있으면 exit 1.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from common import (ENTRY_HOP, ROOT, Endpoints, callTree_classes, corpus_index, dumps, git, hop_of, load_corpus,
                    load_records)

SOURCE_REFS = ("phase3.3-base", "phase3.5-v1.4")   # Legacy 소스(레코드를 만든 코드), New 사다리 끝(변형의 head 쪽)
SOURCE_ROOTS = ("services/order/src/main", "services/coupon/src/main")
EXPECTED_SESSION_DIFF = {"S011"}                   # corpus v2 → v2.1 차이(phase4-plan 4.1)


# ---------------------------------------------------------------- 맵
def build_map(records: list[dict], corpus: dict, endpoints: Endpoints | None = None) -> dict:
    """Legacy 레코드 → {requests, endpoints, classes}. corpus와 어긋나거나 잘린 callTree가 있으면 ValueError."""
    endpoints = endpoints or Endpoints()
    index = corpus_index(corpus)
    hops: dict[str, dict[str, dict]] = {}
    for r in records:
        if (r.get("callTree") or {}).get("truncated"):
            raise ValueError(f"callTree 잘림: {r['replayRequestId']}/{hop_of(r)}")
        hops.setdefault(r["replayRequestId"], {})[hop_of(r)] = r
    if set(hops) != set(index):
        raise ValueError(f"corpus와 요청 집합이 다르다: {sorted(set(hops) ^ set(index))}")

    requests = {}
    for rid, by_hop in hops.items():
        if ENTRY_HOP not in by_hop:
            raise ValueError(f"진입 홉 없음: {rid}")
        hop_classes = {hop: callTree_classes(rec) for hop, rec in by_hop.items()}
        requests[rid] = {
            "session": index[rid]["session"],
            "endpoint": endpoints.of(by_hop[ENTRY_HOP]),
            "classes": sorted({c for cs in hop_classes.values() for c in cs}),
            "byHop": hop_classes,
        }

    ep_map: dict[str, dict[str, set]] = {}
    def entry(eid: str) -> dict[str, set]:
        return ep_map.setdefault(eid, {"classes": set(), "requests": set(), "hopRequests": set(), "sessions": set()})
    for rid, req in requests.items():
        e = entry(req["endpoint"])
        e["requests"].add(rid)
        e["classes"].update(req["classes"])
        e["sessions"].add(req["session"])
        for hop, rec in hops[rid].items():
            if hop != ENTRY_HOP:
                child = entry(endpoints.of(rec))
                child["hopRequests"].add(rid)
                child["classes"].update(req["byHop"][hop])
                child["sessions"].add(req["session"])

    class_map: dict[str, dict[str, set]] = {}
    for rid, req in requests.items():
        for c in req["classes"]:
            class_map.setdefault(c, {"requests": set(), "endpoints": set()})["requests"].add(rid)
    for eid, e in ep_map.items():
        for c in e["classes"]:
            class_map[c]["endpoints"].add(eid)

    return {
        "requests": requests,
        "endpoints": {eid: {k: sorted(v) for k, v in e.items()} for eid, e in ep_map.items()},
        "classes": {c: {k: sorted(v) for k, v in e.items()} for c, e in class_map.items()},
    }


def body_sha(body: dict) -> str:
    return "sha256:" + hashlib.sha256(dumps(body).encode()).hexdigest()


def run_corpus(run_dir: Path) -> dict:
    """그 run이 재생한 corpus(run-meta 기록) — sha256까지 맞아야 한다."""
    meta = json.loads((run_dir / "run-meta.json").read_text(encoding="utf-8"))["corpus"]
    path = ROOT / meta["path"]
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if sha != meta["sha256"]:
        raise ValueError(f"{run_dir.name}: corpus sha256 불일치 {meta['path']}")
    return {"version": meta["version"], "sha256": sha, "corpus": load_corpus(path)}


def request_diff(a: dict, b: dict) -> dict:
    """두 맵의 요청 단위 차이 → {세션: [rid...]}. 한쪽에만 있는 요청과 내용이 다른 요청 모두."""
    out: dict[str, set] = {}
    for rid in set(a["requests"]) | set(b["requests"]):
        x, y = a["requests"].get(rid), b["requests"].get(rid)
        if x != y:
            out.setdefault((x or y)["session"], set()).add(rid)
    return {s: sorted(r) for s, r in sorted(out.items())}


# ---------------------------------------------------------------- 커버리지 (소스의 빈 클래스 대비)
DECL = re.compile(r"^(?:(?:public|protected|private|internal|abstract|final|open|sealed|static|data|annotation)\s+)*"
                  r"(?:enum\s+class|class|interface|object|record|enum|@interface)\s+(\w+)", re.M)
BEAN_ANNOTATION = re.compile(r"^@(RestController|Controller|Service|Repository|Component)\b", re.M)
OTHER_ANNOTATION = re.compile(r"^@(Configuration|SpringBootApplication|Entity)\b", re.M)
OTHER_KIND = {"Configuration": "config", "SpringBootApplication": "main", "Entity": "entity"}


def strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def declared_classes(path: str, src: str) -> list[dict]:
    """소스 한 파일의 최상위 선언(중첩은 바깥 클래스로 — D24) → [{fqcn, beanKinds[], otherKind, filter}]."""
    src = strip_comments(src)
    pkg = re.search(r"^package\s+([\w.]+)", src, re.M).group(1)
    decls = list(DECL.finditer(src))
    out = []
    for i, d in enumerate(decls):
        end = decls[i + 1].start() if i + 1 < len(decls) else len(src)
        body = src[d.start():end]
        header = body.replace("${", "").split("{")[0]   # Kotlin 생성자의 "\${…}"에서 끊기지 않게
        prev = decls[i - 1].end() if i else 0
        above = src[prev:d.start()]
        kinds = set(BEAN_ANNOTATION.findall(above))
        if "JpaRepository" in header:
            kinds.add("repository-interface")
        if "@KafkaListener" in body:
            kinds.add("KafkaListener")
        if d.group(1).endswith("Client"):
            kinds.add("client")
        other = OTHER_ANNOTATION.findall(above)
        out.append({"fqcn": f"{pkg}.{d.group(1)}", "beanKinds": sorted(kinds),
                    "otherKind": OTHER_KIND[other[0]] if other else "plain",
                    "filter": bool(re.search(r"\bOncePerRequestFilter\b|\bFilter\b", header))})
    return out


def source_classes(ref: str, repo: Path = ROOT) -> list[dict]:
    files = git("ls-tree", "-r", "--name-only", ref, "--", *SOURCE_ROOTS, repo=repo).splitlines()
    out = []
    for f in sorted(files):
        if f.endswith((".java", ".kt")):
            out.extend(declared_classes(f, git("show", f"{ref}:{f}", repo=repo)))
    return sorted(out, key=lambda c: c["fqcn"])


def unobserved_reason(c: dict) -> str:
    if c["filter"]:
        return "AOP 포인트컷 제외 — !within(jakarta.servlet.Filter+) (EvidenceAutoConfiguration.callTreeExpression)"
    return "원인 미상 — corpus 미실행 여부 확인 필요"


def coverage(body: dict, contract_endpoints: Endpoints, refs=SOURCE_REFS, repo: Path = ROOT) -> dict:
    ids = sorted({e[0] for e in contract_endpoints.http} | set(contract_endpoints.topics.values()))
    seen = body["classes"]
    sources = {}
    for ref in refs:
        classes = source_classes(ref, repo)
        beans = [c for c in classes if c["beanKinds"]]
        sources[ref] = {
            "beans": len(beans),
            "beansObserved": sum(c["fqcn"] in seen for c in beans),
            "unobservedBeans": [{"fqcn": c["fqcn"], "beanKinds": c["beanKinds"], "reason": unobserved_reason(c)}
                                for c in beans if c["fqcn"] not in seen],
            "nonBeans": [{"fqcn": c["fqcn"], "kind": c["otherKind"]} for c in classes if not c["beanKinds"]],
            "observedNotInSource": sorted(set(seen) - {c["fqcn"] for c in classes}),
        }
    return {"endpoints": {"total": len(ids), "observed": sorted(set(ids) & set(body["endpoints"])),
                          "missing": sorted(set(ids) - set(body["endpoints"]))},
            "sources": sources}


# ---------------------------------------------------------------- CLI
def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="스코핑 맵 합성(Phase 4.1)")
    ap.add_argument("--runs", nargs="+", required=True, type=Path)
    ap.add_argument("--corpus", default=ROOT / "corpus" / "corpus-v2.1.json", type=Path)
    ap.add_argument("--out", default=ROOT / "scoping" / "map.json", type=Path)
    ap.add_argument("--compare", nargs="*", default=[], type=Path, help="안정성 확인용 run — 정본과 요청 단위 비교")
    args = ap.parse_args(argv)

    endpoints = Endpoints()
    corpus_sha = hashlib.sha256(args.corpus.read_bytes()).hexdigest()
    bodies = {}
    for run in args.runs:
        rc = run_corpus(run)
        if rc["sha256"] != corpus_sha:
            print(f"map.py: {run.name}의 corpus가 --corpus와 다르다 ({rc['version']})", file=sys.stderr)
            return 1
        bodies[run.name] = build_map(load_records(run), rc["corpus"], endpoints)
    shas = {name: body_sha(b) for name, b in bodies.items()}
    for name, sha in shas.items():
        print(f"{name}  {sha}")
    if len(set(shas.values())) != 1:
        print("map.py: run마다 맵이 다르다 — 결정론 실패", file=sys.stderr)
        return 1

    body = next(iter(bodies.values()))
    result = dict(body)
    result["builtFrom"] = sorted(bodies)
    result["corpus"] = {"version": load_corpus(args.corpus)["version"], "sha256": corpus_sha}
    result["bodySha256"] = next(iter(shas.values()))
    result["coverage"] = coverage(body, endpoints)
    args.out.write_text(dumps(result), encoding="utf-8")
    print(f"{args.out}: requests {len(body['requests'])}, endpoints {len(body['endpoints'])}, classes {len(body['classes'])}")

    status = 0
    for run in args.compare:
        rc = run_corpus(run)
        other = build_map(load_records(run), rc["corpus"], endpoints)
        diff = request_diff(body, other)
        outside = set(diff) - EXPECTED_SESSION_DIFF
        print(f"compare {run.name} ({rc['version']}): 차이 세션 {diff or '없음'}" + (" ← S011 밖 차이" if outside else ""))
        status = status or (1 if outside else 0)
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
