#!/usr/bin/env python3
"""Phase 4.2 — docs/scope-expectations.json의 변형을 impact로 돌려 scoping/impacts/에 쓰고 사전 등록과 대조한다.
불일치는 출력만 한다(기대·도구를 고치지 않는다, exit 1). status가 있는 변형(C1·C2)은 head 브랜치가 생기면 실행한다(4.5).

사용: .venv/bin/python scoping/check_scope.py [--explain]
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import impact
from common import ROOT, dumps, load_corpus

EXPECT = ROOT / "docs" / "scope-expectations.json"
FAULTS = ROOT / "docs" / "fault-expectations.json"
OUT = ROOT / "scoping" / "impacts"


def ref_exists(ref: str) -> bool:
    return subprocess.run(["git", "rev-parse", "--verify", "--quiet", ref], cwd=ROOT, capture_output=True).returncode == 0


def compare(exp: dict, got: dict, sets: dict, sessions: dict) -> list[str]:
    bad = []
    def check(name, want, have):
        if want != have:
            bad.append(f"{name}: 기대 {want} / 결과 {have}")
    for key, field in (("changedClasses", "changedClasses"), ("observed", "observed")):
        if key in exp:
            check(key, exp[key], got[field])
    if "unobserved" in exp:
        check("unobserved", exp["unobserved"], {u["fqcn"]: {"reachedClasses": u["reachedClasses"], "unresolved": u["unresolved"]}
                                                for u in got["unobserved"]})
    check("global", exp["global"], got["globalTriggered"])
    missing = set(exp.get("globalReasonsInclude", [])) - set(got["globalReasons"])
    if missing:
        bad.append(f"globalReasons 누락: {sorted(missing)} / 결과 {got['globalReasons']}")
    check("impactedRequests", sets[exp["impactedRequestSet"]], sorted(got["impactedRequests"]))
    check("selectedSessions", sessions[exp["selectedSessionSet"]], got["selectedSessions"])
    check("selectedRequests", exp["selectedRequests"], len(got["selectedRequests"]))
    for key in ("reductionRequests", "reductionSessions"):
        if key in exp:
            check(key, exp[key], got[key])
    return bad


def verdict_cell(name: str, got: dict, bad: list) -> str:
    """사전 등록 대조 결과. 이전 버전 결과가 보존된 변형은 전후를 남긴다 — 결과를 본 뒤의 변경이라 독립 검증이 아니다."""
    previous = OUT / "aux" / f"{name}.impact-v1.0.json"
    if not previous.exists():
        return "일치" if not bad else "**불일치**"
    old = json.loads(previous.read_text(encoding="utf-8"))
    return (f"{'회귀 확인 일치' if not bad else '**불일치**'} — impact-v1.0 {len(old['selectedSessions'])}세션 → "
            f"{got['toolVersion'].removeprefix('impact-')} {len(got['selectedSessions'])}세션(사전 등록 아님)")


def target_coverage(variant: str, got: dict, faults: dict, m: dict) -> str:
    targets = faults.get(variant, {}).get("targets")
    if not targets:
        return "-"
    rids = {p.split("/")[0] for p in targets}
    inside = sum(m["requests"][r]["session"] in got["selectedSessions"] for r in rids)
    return f"{inside}/{len(rids)}"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="영향 기대 대조(Phase 4.2)")
    ap.add_argument("--explain", action="store_true")
    args = ap.parse_args(argv)
    spec = json.loads(EXPECT.read_text(encoding="utf-8"))
    m = json.loads((ROOT / "scoping" / "map.json").read_text(encoding="utf-8"))
    faults = json.loads(FAULTS.read_text(encoding="utf-8"))
    corpus = load_corpus(ROOT / "corpus" / "corpus-v2.1.json")
    if spec["mapBodySha256"] != m["bodySha256"]:
        print("기대 등록 시점의 맵과 다르다", file=sys.stderr)
        return 1
    sets, sessions = spec["requestSets"], spec["sessionSets"]
    (OUT / "aux").mkdir(parents=True, exist_ok=True)
    failures = 0

    print(f"도구 {impact.IMPACT_VERSION}. 사전 등록에 대한 독립 대조는 impact-v1.0의 11/13이다(phase4.2 보고서). 이 표의 일치는 기존 기대에 대한 회귀 확인이다.\n")
    print("| 변형 | 범위 | 변경 | 관측 | 미관측 | 전역 | 영향 요청 | 세션 | 재생 | 감소(요청) | target 세션 포함 | 사전 등록 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for name, exp in spec["variants"].items():
        if "status" in exp and not ref_exists(exp["head"]):
            print(f"| {name} | `{exp['base']}..{exp['head']}` | {exp['status']} | | | | | | | | | 대기 |")
            continue
        got = impact.compute(m, corpus, exp["base"], exp["head"], ROOT, exp["pathFilter"])
        (OUT / f"{name}.json").write_text(dumps(got), encoding="utf-8")
        bad = compare(exp, got, sets, sessions)
        failures += bool(bad)
        print(f"| {name} | `{exp['base']}..{exp['head']}` | {len(got['changedClasses'])} | {len(got['observed'])} | {len(got['unobserved'])} "
              f"| {'전역' if got['globalTriggered'] else '-'} | {len(got['impactedRequests'])} | {len(got['selectedSessions'])}/11 "
              f"| {len(got['selectedRequests'])}/48 | {got['reductionRequests']:.1%} | {target_coverage(name, got, faults, m)} | {verdict_cell(name, got, bad)} |")
        for b in bad:
            print(f"<!-- {name} {b} -->")
        if args.explain:
            print("\n".join(f"<!-- {l} -->" for l in impact.explain(got).splitlines()))

    print("\n| 보조 | 조건 | 전역 | 영향 요청 | 세션 | 재생 | 사전 등록 |\n|---|---|---|---|---|---|---|")
    for name, exp in spec["aux"].items():
        base = exp.get("base") or spec["variants"][exp["of"]]["base"]
        head = exp.get("head") or spec["variants"][exp["of"]]["head"]
        pf = spec["variants"][exp["of"]]["pathFilter"] if exp["of"] in spec["variants"] else None
        got = impact.compute(m, corpus, base, head, ROOT, pf, exp.get("ignoreKind", ()),
                             exp.get("nameResolution") == "literal", exp.get("assumeChanged", ()))
        (OUT / "aux" / f"{name}.json").write_text(dumps(got), encoding="utf-8")
        bad = compare(exp, got, sets, sessions)
        failures += bool(bad)
        cond = exp.get("nameResolution") or ",".join(exp.get("ignoreKind", []))
        print(f"| {name} | {cond} | {'전역' if got['globalTriggered'] else '-'} | {len(got['impactedRequests'])} | {len(got['selectedSessions'])}/11 "
              f"| {len(got['selectedRequests'])}/48 | {verdict_cell(name, got, bad)} |")
        for b in bad:
            print(f"<!-- {name} {b} -->")
        if args.explain:
            print("\n".join(f"<!-- {l} -->" for l in impact.explain(got).splitlines()))
    print("\n| 경계 사례 | 변경 | 관측 | 미관측 | 전역 | 영향 요청 | 세션 | 재생 | 경고 | 사전 등록 |\n|---|---|---|---|---|---|---|---|---|---|")
    (OUT / "boundary").mkdir(exist_ok=True)
    empty = ({**sets, "none": []}, {**sessions, "none": []})
    for name, exp in spec.get("boundaryCases", {}).items():
        if not ref_exists(exp["head"]):
            print(f"| {name} | {exp['change']} | | | | | | | | 대기 |")
            continue
        got = impact.compute(m, corpus, exp["base"], exp["head"], ROOT, exp["pathFilter"])
        (OUT / "boundary" / f"{name}.json").write_text(dumps(got), encoding="utf-8")
        bad = compare(exp, got, *empty)
        if got["warnings"] != exp["warnings"]:
            bad.append(f"warnings: 기대 {exp['warnings']} / 결과 {got['warnings']}")
        failures += bool(bad)
        print(f"| {name} | {exp['change']} | {len(got['observed'])} | {len(got['unobserved'])} | {'전역' if got['globalTriggered'] else '-'} | {len(got['impactedRequests'])} "
              f"| {len(got['selectedSessions'])}/11 | {len(got['selectedRequests'])}/48 | {'A/A' if got['warnings'] else '-'} | {'일치' if not bad else '**불일치**'} |")
        for b in bad:
            print(f"<!-- {name} {b} -->")
        if args.explain:
            print("\n".join(f"<!-- {l} -->" for l in impact.explain(got).splitlines()))
    print(f"\n불일치 {failures}건")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
