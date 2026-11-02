#!/usr/bin/env python3
"""Phase 4.3 — 오프라인 평가(D25). 전체 재생 판정을 선택 세션으로 제한해 잰다. 판정 파일은 읽기만 한다.

입력: scoping/impacts/<변형>.json(aux의 impact-v1.0 포함), runs/ 전체 재생 verdict.json(C, 규칙 후), docs/fault-expectations.json
출력 docs/phase4-metrics.json (결정론):
  변형별 감소율(요청·세션), Observed-diff Recall(F0 `R000047/0` 제외 주·포함 보조, 분모 0 → N/A),
  결함 탐지 유지(행동 차이 없는 변형 N/A), Filter Precision, 세션 검사 재계산, run 범위 항목 = "not evaluated offline",
  B2-S 전체 조합(C(11,k) 열거 + 요청 예산 보조), ablation 2종(엔드포인트 합집합 맵 / 홉 합산 없는 맵), Tag 순위 품질
  Tag는 두 입도로 낸다: session(계획 정의, = Recall), request(영향 요청에 든 pair — 요청 단위 차이가 드러나는 쪽).

사용: .venv/bin/python scoping/evaluate.py --impacts scoping/impacts --runs runs \
        --expectations docs/fault-expectations.json --out docs/phase4-metrics.json
Recall < 1.0인 결함 변형이 있으면 exit 1(규칙 6 위반 — 멈추고 보고).
"""
import argparse
import itertools
import json
import sys
from pathlib import Path

import impact
from common import ENTRY_HOP, ROOT, corpus_index, dumps, load_corpus, load_verdict

F0_PAIR = "R000047/0"
NOT_OFFLINE = "not evaluated offline"
OFFLINE_GAPS = ("dbstate_equal", "undelivered", "degraded", "settleTimeouts", "replayTime", "sessionIndependence")
LADDER = ("v1.1", "v1.2", "v1.3", "v1.4")
FAULTS = tuple(f"F{i}" for i in range(1, 10))
DUAL = ("v1.2", "F2")     # impact-v1.0과 나란히 싣는 변형(D-4.2a)


def run_ids(variant: str) -> list[str]:
    prefix = "p35" if variant.startswith("v") else "p36"
    return [f"{prefix}-{variant}-{i}" for i in (1, 2, 3)]


def pair_verdicts(verdict: dict) -> dict[str, dict]:
    return {f"{p['replayRequestId']}/{p['hopPath']}": {"session": p["sessionId"], "rid": p["replayRequestId"], "verdict": p["verdict"]}
            for p in verdict["pairs"]}


def ratio(n: int, d: int):
    return None if d == 0 else round(n / d, 4)


def recall(pairs: dict, sessions: set, exclude_f0: bool = True):
    """비-SAME pair 중 선택 세션에 든 비율. 분모 0이면 None(N/A)."""
    diffs = [k for k, p in pairs.items() if p["verdict"] != "SAME" and not (exclude_f0 and k == F0_PAIR)]
    return ratio(sum(pairs[k]["session"] in sessions for k in diffs), len(diffs))


def precision(pairs: dict, sessions: set):
    selected = [p for p in pairs.values() if p["session"] in sessions]
    return ratio(sum(p["verdict"] != "SAME" for p in selected), len(selected))


def detection(targets: dict | None, pairs: dict, sessions: set, sizes_session: dict):
    """target pair 중 선택 세션에 든 비율. 행동 차이 없는 변형(target 없음)은 None(N/A)."""
    if not targets:
        return None
    inside = sum(sizes_session[k.split("/")[0]] in sessions for k in targets)
    return {"selected": inside, "total": len(targets), "ratio": ratio(inside, len(targets))}


def session_checks(verdict: dict, sessions: set) -> dict:
    found = verdict["summary"]["sessionViolations"]
    return {"full": len(found), "inSelected": sum(v["session"] in sessions for v in found)}


def tag_quality(pairs: dict, sessions: set, impacted: set) -> dict:
    def grain(in_scope):
        total = [k for k in pairs if in_scope(k)]
        diffs = [k for k, p in pairs.items() if p["verdict"] != "SAME" and k != F0_PAIR]
        return {"inScopePairs": len(total), "budget": ratio(len(total), len(pairs)),
                "diffsInScope": sum(in_scope(k) for k in diffs), "diffs": len(diffs), "rate": ratio(sum(in_scope(k) for k in diffs), len(diffs))}
    return {"session": grain(lambda k: pairs[k]["session"] in sessions), "request": grain(lambda k: pairs[k]["rid"] in impacted)}


def b2s(pairs: dict, selected: list[str], request_budget: int, sizes: dict[str, int]) -> dict:
    """같은 세션 수의 모든 부분집합 + 요청 수 ≤ 예산인 모든 부분집합의 Recall(F0 제외). 분모 0이면 None."""
    weights: dict[str, int] = {}
    for k, p in pairs.items():
        if p["verdict"] != "SAME" and k != F0_PAIR:
            weights[p["session"]] = weights.get(p["session"], 0) + 1
    total = sum(weights.values())
    if total == 0:
        return None
    names = sorted(sizes)

    def summary(subsets) -> dict:
        values = [sum(weights.get(s, 0) for s in c) / total for c in subsets]
        return {"subsets": len(values), "mean": round(sum(values) / len(values), 4), "min": round(min(values), 4),
                "fullRecallRate": round(sum(v == 1 for v in values) / len(values), 4)}

    same_k = list(itertools.combinations(names, len(selected)))
    every = [c for k in range(len(names) + 1) for c in itertools.combinations(names, k)]
    budget = [c for c in every if sum(sizes[s] for s in c) <= request_budget]
    return {"k": len(selected), "sameSessionCount": summary(same_k), "requestBudget": {"budget": request_budget, **summary(budget)}}


# ---------------------------------------------------------------- ablation 맵
def endpoint_union_map(m: dict) -> dict:
    """(a) 엔드포인트 합집합으로 선택: 클래스가 그 엔드포인트의 모든 요청에서 실행됐다고 본다."""
    classes = {}
    for c, e in m["classes"].items():
        rids = {r for eid in e["endpoints"] for r in m["endpoints"][eid]["requests"] + m["endpoints"][eid]["hopRequests"]}
        classes[c] = {"requests": sorted(rids), "endpoints": e["endpoints"]}
    return {**m, "classes": classes}


def no_hop_merge_map(m: dict) -> dict:
    """(b) 자식 홉 합산 없는 요청 단위 맵: 진입 홉 callTree만."""
    classes: dict[str, dict] = {}
    for rid, q in m["requests"].items():
        for c in q["byHop"][ENTRY_HOP]:
            classes.setdefault(c, {"requests": [], "endpoints": []})["requests"].append(rid)
    return {**m, "classes": {c: {"requests": sorted(e["requests"]), "endpoints": []} for c, e in classes.items()}}


def evaluate_selection(imp: dict, pairs: dict, verdict: dict, targets: dict | None, index: dict, sizes: dict) -> dict:
    sessions = set(imp["selectedSessions"])
    rid_session = {r: q["session"] for r, q in index.items()}
    return {
        "toolVersion": imp.get("toolVersion", "impact-v1.0"),
        "global": imp["globalTriggered"],
        "selectedSessions": len(sessions), "selectedRequests": len(imp["selectedRequests"]), "impactedRequests": len(imp["impactedRequests"]),
        "reductionRequests": imp["reductionRequests"], "reductionSessions": imp["reductionSessions"],
        "recall": recall(pairs, sessions), "recallWithF0": recall(pairs, sessions, exclude_f0=False),
        "detection": detection(targets, pairs, sessions, rid_session),
        "precision": precision(pairs, sessions),
        "sessionChecks": session_checks(verdict, sessions),
        "tag": tag_quality(pairs, sessions, set(imp["impactedRequests"])),
        "b2s": b2s(pairs, imp["selectedSessions"], len(imp["selectedRequests"]), sizes),
    }


def ablation_row(variant_map: dict, imp: dict, pairs: dict, corpus: dict) -> dict:
    other = impact.compute(variant_map, corpus, imp["base"], imp["head"], ROOT, imp["pathFilter"])
    sessions = set(other["selectedSessions"])
    return {"global": other["globalTriggered"], "selectedSessions": len(sessions), "selectedRequests": len(other["selectedRequests"]),
            "impactedRequests": len(other["impactedRequests"]), "reductionRequests": other["reductionRequests"],
            "recall": recall(pairs, sessions), "tag": tag_quality(pairs, sessions, set(other["impactedRequests"]))}


def fmt(v) -> str:
    return "N/A" if v is None else f"{v:.4g}"


def table(metrics: dict) -> str:
    out = ["## 결함 변형", "", "| 변형 | 도구 | 세션 | 요청 | 감소(요청) | 감소(세션) | Recall | Recall+F0 | 탐지 유지 | Precision | 세션검사 | 전체 조합 k개 평균·최소·1.0 비율 | 예산 평균·1.0 비율 |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    def row(name, r):
        d = r["detection"]
        b = r["b2s"]
        bs = f"{b['sameSessionCount']['mean']:.3f}·{b['sameSessionCount']['min']:.3f}·{b['sameSessionCount']['fullRecallRate']:.4f} ({b['sameSessionCount']['subsets']})" if b else "N/A"
        bb = f"{b['requestBudget']['mean']:.3f}·{b['requestBudget']['fullRecallRate']:.4f} ({b['requestBudget']['subsets']})" if b else "N/A"
        return (f"| {name} | {r['toolVersion'].removeprefix('impact-')} | {r['selectedSessions']}/11 | {r['selectedRequests']}/48 | {r['reductionRequests']:.1%} | {r['reductionSessions']:.1%} "
                f"| {fmt(r['recall'])} | {fmt(r['recallWithF0'])} | {f'{d['selected']}/{d['total']}' if d else 'N/A'} | {fmt(r['precision'])} | {r['sessionChecks']['inSelected']}/{r['sessionChecks']['full']} | {bs} | {bb} |")
    for v in FAULTS:
        if f"{v}@impact-v1.0" in metrics["variants"]:
            out.append(row(v, metrics["variants"][f"{v}@impact-v1.0"]))
        out.append(row(v, metrics["variants"][v]))
    out += ["", "## 행동 차이 없는 변형", "", "| 변형 | 도구 | 세션 | 요청 | 감소(요청) | 감소(세션) | Recall | Recall+F0 | 탐지 유지 | Precision | 세션검사 | 전체 조합 | 예산 |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for v in LADDER:
        if f"{v}@impact-v1.0" in metrics["variants"]:
            out.append(row(v, metrics["variants"][f"{v}@impact-v1.0"]))
        out.append(row(v, metrics["variants"][v]))
    out += ["", "## ablation (impact-v1.1)", "", "| 변형 | 맵 | 전역 | 세션 | 요청 | 영향 요청 | 감소(요청) | Recall | Tag 세션 입도(예산·포함) | Tag 요청 입도(예산·포함) |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for v in FAULTS + LADDER:
        r = metrics["variants"][v]
        rows = [("정본", {**r, "tag": r["tag"]}), ("(a) 엔드포인트", r["ablation"]["endpointUnion"]), ("(b) 합산 없음(보조: Tag)", r["ablation"]["noHopMerge"])]
        for label, x in rows:
            t = x["tag"]
            out.append(f"| {v} | {label} | {'전역' if x['global'] else '-'} | {x['selectedSessions']} | {x['selectedRequests']} | {x['impactedRequests']} | {x['reductionRequests']:.1%} "
                       f"| {fmt(x['recall'])} | {fmt(t['session']['budget'])}·{fmt(t['session']['rate'])} | {fmt(t['request']['budget'])}·{fmt(t['request']['rate'])} |")
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="스코핑 오프라인 평가(Phase 4.3)")
    ap.add_argument("--impacts", default=ROOT / "scoping" / "impacts", type=Path)
    ap.add_argument("--runs", default=ROOT / "runs", type=Path)
    ap.add_argument("--expectations", default=ROOT / "docs" / "fault-expectations.json", type=Path)
    ap.add_argument("--out", default=ROOT / "docs" / "phase4-metrics.json", type=Path)
    ap.add_argument("--map", default=ROOT / "scoping" / "map.json", type=Path)
    ap.add_argument("--corpus", default=ROOT / "corpus" / "corpus-v2.1.json", type=Path)
    args = ap.parse_args(argv)

    m = json.loads(args.map.read_text(encoding="utf-8"))
    corpus = load_corpus(args.corpus)
    index = corpus_index(corpus)
    sizes = {s["id"]: len(s["requests"]) for s in corpus["sessions"]}
    expectations = json.loads(args.expectations.read_text(encoding="utf-8"))
    union_map, no_hop_map = endpoint_union_map(m), no_hop_merge_map(m)

    variants, determinism = {}, {}
    for v in FAULTS + LADDER:
        verdicts = [load_verdict(args.runs / r) for r in run_ids(v)]
        per_run = [pair_verdicts(x) for x in verdicts]
        determinism[v] = all(p == per_run[0] for p in per_run)
        pairs, verdict = per_run[0], verdicts[0]
        targets = expectations.get(v, {}).get("targets")
        imp = json.loads((args.impacts / f"{v}.json").read_text(encoding="utf-8"))
        row = evaluate_selection(imp, pairs, verdict, targets, index, sizes)
        row["recallPerRun"] = [recall(p, set(imp["selectedSessions"])) for p in per_run]
        row["ablation"] = {"endpointUnion": ablation_row(union_map, imp, pairs, corpus), "noHopMerge": ablation_row(no_hop_map, imp, pairs, corpus)}
        variants[v] = row
        if v in DUAL:
            old = json.loads((args.impacts / "aux" / f"{v}.impact-v1.0.json").read_text(encoding="utf-8"))
            variants[f"{v}@impact-v1.0"] = evaluate_selection(old, pairs, verdict, targets, index, sizes)

    fn = [v for v in FAULTS if variants[v]["recall"] != 1.0]
    metrics = {"tool": impact.IMPACT_VERSION, "mapBodySha256": m["bodySha256"], "f0Pair": F0_PAIR,
               "notEvaluatedOffline": {k: NOT_OFFLINE for k in OFFLINE_GAPS}, "verdictSameAcrossRuns": determinism,
               "variants": variants, "recallBelowOne": fn}
    args.out.write_text(dumps(metrics), encoding="utf-8")
    print(table(metrics))
    print(f"3 run 판정 동일: {sum(determinism.values())}/{len(determinism)}, Recall < 1 결함 변형: {fn or '없음'}")
    return 1 if fn else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
