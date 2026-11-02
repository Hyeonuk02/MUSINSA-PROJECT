#!/usr/bin/env python3
"""Phase 4.3 — 오프라인 평가(D25). 전체 재생 판정을 선택 세션으로 제한해 잰다. 판정 파일은 읽기만 한다.

입력: scoping/impacts/<변형>.json(aux의 impact-v1.0 포함), runs/ 전체 재생 verdict.json(C, 규칙 후), docs/fault-expectations.json
출력 docs/phase4-metrics.json, docs/phase4-metrics.md (결정론, md는 손으로 고치지 않는다):
  변형별 감소율(요청·세션), Observed-diff Recall(F0 `R000047/0` 제외 주·포함 보조, 분모 0 → N/A),
  결함 탐지 유지(행동 차이 없는 변형 N/A), Filter Precision, 세션 검사 재계산, run 범위 항목 = "not evaluated offline",
  B2-S 전체 조합(C(11,k) 열거 + 요청 예산 보조), ablation 2종(엔드포인트 합집합 맵 / 홉 합산 없는 맵), Tag 순위 품질
  Tag는 두 입도로 낸다: session(계획 정의, = Recall), request(영향 요청에 든 pair — 요청 단위 차이가 드러나는 쪽).
  관측된 차이 pair = verdict != SAME 또는 appliedRules가 있는 pair(= 규칙 적용 전 비-SAME, D26). 사람 검토 감소는 규칙 적용 후 verdict로 잰다.

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
import run_check
from check_scope import compare
from common import ENTRY_HOP, ROOT, corpus_index, dumps, load_corpus, load_verdict
from metrics_report import recall_kind, render

F0_PAIR = "R000047/0"
NOT_OFFLINE = "not evaluated offline"
OFFLINE_GAPS = ("dbstate_equal", "undelivered", "degraded", "settleTimeouts", "replayTime", "sessionIndependence")
LADDER = ("v1.1", "v1.2", "v1.3", "v1.4")
FAULTS = tuple(f"F{i}" for i in range(1, 10))
DUAL = ("v1.2", "F2")     # impact-v1.0과 나란히 싣는 변형(D-4.2a)
CHANGES = ("C1", "C2")    # 서비스 간 변경(4.5)
REGRESSION_BOUNDARY = ("E5",)   # 등록 전에 값을 이미 봤다(4.2 whatif)


def run_ids(variant: str) -> list[str]:
    prefix = {"v": "p35", "F": "p36", "C": "p45"}[variant[0]]
    return [f"{prefix}-{variant}-{i}" for i in (1, 2, 3)]


def pair_verdicts(verdict: dict) -> dict[str, dict]:
    return {f"{p['replayRequestId']}/{p['hopPath']}": {"session": p["sessionId"], "rid": p["replayRequestId"], "verdict": p["verdict"],
                                                        "split": p.get("split"), "diff": p["verdict"] != "SAME" or bool(p.get("appliedRules"))}
            for p in verdict["pairs"]}


def ratio(n: int, d: int):
    return None if d == 0 else round(n / d, 4)


def recall(pairs: dict, sessions: set, exclude_f0: bool = True):
    """관측된 차이 pair 중 선택 세션에 든 비율. 분모 0이면 None(N/A)."""
    diffs = [k for k, p in pairs.items() if p["diff"] and not (exclude_f0 and k == F0_PAIR)]
    return ratio(sum(pairs[k]["session"] in sessions for k in diffs), len(diffs))


def precision(pairs: dict, sessions: set):
    selected = [p for p in pairs.values() if p["session"] in sessions]
    return ratio(sum(p["diff"] for p in selected), len(selected))


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
        diffs = [k for k, p in pairs.items() if p["diff"] and k != F0_PAIR]
        return {"inScopePairs": len(total), "budget": ratio(len(total), len(pairs)),
                "diffsInScope": sum(in_scope(k) for k in diffs), "diffs": len(diffs), "rate": ratio(sum(in_scope(k) for k in diffs), len(diffs))}
    return {"session": grain(lambda k: pairs[k]["session"] in sessions), "request": grain(lambda k: pairs[k]["rid"] in impacted)}


def b2s(pairs: dict, selected: list[str], request_budget: int, sizes: dict[str, int]) -> dict:
    """같은 세션 수의 모든 부분집합 + 요청 수 ≤ 예산인 모든 부분집합의 Recall(F0 제외). 분모 0이면 None."""
    weights: dict[str, int] = {}
    for k, p in pairs.items():
        if p["diff"] and k != F0_PAIR:
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


def review_effect(before: dict, after: dict) -> dict:
    """사람 검토 감소: 규칙 적용 전(라벨 전)과 후의 Uncertain — 규칙 적용 후 verdict 기준(D26)."""
    def count(v, split):
        return sum(p["verdict"] == "UNCERTAIN" and p["split"] == split for p in v["pairs"])
    kinds = sorted({u["diffKind"] for p in before["pairs"] if p["verdict"] == "UNCERTAIN" for u in p["uncertain"]})
    return {"evalUncertainBefore": count(before, "eval"), "evalUncertainAfter": count(after, "eval"),
            "learnUncertainBefore": count(before, "learn"), "learnUncertainAfter": count(after, "learn"),
            "uncertainDiffKinds": kinds, "sameWithRules": sum(p["verdict"] == "SAME" and bool(p["appliedRules"]) for p in after["pairs"])}


def registration(spec: dict, m: dict, corpus_sets, impacts: Path) -> dict:
    """사전 등록 대조 표. 맹검 = 결과를 보기 전의 대조, 회귀 확인 = 결과를 이미 본 뒤의 일치(독립 검증 아님)."""
    sets, sessions = corpus_sets
    out = {}
    def load(path):
        return json.loads(path.read_text(encoding="utf-8"))
    for name, exp in spec["variants"].items():
        if name in DUAL:
            old = load(impacts / "aux" / f"{name}.impact-v1.0.json")
            out[name] = {"case": name, "kind": "blind", "tool": "impact-v1.0", "match": not compare(exp, old, sets, sessions),
                         "note": "폐포가 JpaRepository로 Coupon까지 번짐(O18)"}
            out[f"{name}@impact-v1.1"] = {"case": name, "kind": "regression", "tool": impact.IMPACT_VERSION, "match": not compare(exp, load(impacts / f"{name}.json"), sets, sessions),
                                          "note": "결과를 본 뒤 도구 변경, 사전 등록 아님(D24 보완 3)"}
            continue
        got = load(impacts / f"{name}.json")
        tool = impact.IMPACT_VERSION if name in CHANGES else "impact-v1.0"   # 13 변형의 대조는 v1.0에서 했고 v1.1 결과도 같다
        out[name] = {"case": name, "kind": "blind", "tool": tool, "match": not compare(exp, got, sets, sessions)}
    for name, exp in spec["boundaryCases"].items():
        got = load(impacts / "boundary" / f"{name}.json")
        ok = not compare(exp, got, {**sets, "none": []}, {**sessions, "none": []}) and got["warnings"] == exp["warnings"]
        kind = "regression" if name in REGRESSION_BOUNDARY else "blind"
        out[name] = {"case": name, "kind": kind, "tool": got["toolVersion"], "match": ok}
        if kind == "regression":
            out[name]["note"] = "4.2 whatif에서 본 값"
    return out


def fail_closed(spec: dict, impacts: Path) -> list[dict]:
    rows = []
    for name, path, change in (("E1", impacts / "boundary" / "E1.json", spec["boundaryCases"]["E1"]["change"]),
                               ("E2", impacts / "boundary" / "E2.json", spec["boundaryCases"]["E2"]["change"]),
                               ("E6", impacts / "boundary" / "E6.json", spec["boundaryCases"]["E6"]["change"]),
                               ("v1.1", impacts / "v1.1.json", "PaymentGatewayClient Kotlin 전환 + pom"),
                               ("v1.4", impacts / "v1.4.json", "Controller·DTO·설정·필터·메인 Kotlin 전환")):
        got = json.loads(path.read_text(encoding="utf-8"))
        rows.append({"case": name, "change": change, "reasons": got["globalReasons"], "sessions": len(got["selectedSessions"]), "reduction": got["reductionRequests"]})
    return rows


def boundary_rows(spec: dict, impacts: Path) -> list[dict]:
    rows = []
    for name, exp in spec["boundaryCases"].items():
        got = json.loads((impacts / "boundary" / f"{name}.json").read_text(encoding="utf-8"))
        rows.append({"case": name, "change": exp["change"], "label": "회귀 확인(4.2 whatif에서 본 값)" if name in REGRESSION_BOUNDARY else "맹검 일치",
                     "global": got["globalTriggered"], "impacted": len(got["impactedRequests"]), "sessions": len(got["selectedSessions"]),
                     "requests": len(got["selectedRequests"]), "warning": bool(got["warnings"])})
    return rows


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="스코핑 오프라인 평가(Phase 4.3)")
    ap.add_argument("--impacts", default=ROOT / "scoping" / "impacts", type=Path)
    ap.add_argument("--runs", default=ROOT / "runs", type=Path)
    ap.add_argument("--expectations", default=ROOT / "docs" / "fault-expectations.json", type=Path)
    ap.add_argument("--out", default=ROOT / "docs" / "phase4-metrics.json", type=Path)
    ap.add_argument("--md", default=ROOT / "docs" / "phase4-metrics.md", type=Path)
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
    changes = tuple(c for c in CHANGES if (args.impacts / f"{c}.json").exists())
    for v in FAULTS + LADDER + changes:
        verdicts = [load_verdict(args.runs / r) for r in run_ids(v)]
        per_run = [pair_verdicts(x) for x in verdicts]
        determinism[v] = all(p == per_run[0] for p in per_run)
        pairs, verdict = per_run[0], verdicts[0]
        targets = expectations.get(v, {}).get("targets")
        imp = json.loads((args.impacts / f"{v}.json").read_text(encoding="utf-8"))
        row = evaluate_selection(imp, pairs, verdict, targets, index, sizes)
        row["recallPerRun"] = [recall(p, set(imp["selectedSessions"])) for p in per_run]
        row["ablation"] = {"endpointUnion": ablation_row(union_map, imp, pairs, corpus), "noHopMerge": ablation_row(no_hop_map, imp, pairs, corpus)}
        row["recallKind"] = recall_kind(row)
        for x in row["ablation"].values():
            x["recallKind"] = recall_kind(x)
        prelabel = args.runs / run_ids(v)[0] / "verdict-prelabel.json"
        if v in CHANGES and prelabel.exists():
            row["review"] = review_effect(load_verdict(args.runs / run_ids(v)[0], "verdict-prelabel.json"), verdict)
        variants[v] = row
        if v in DUAL:
            old = json.loads((args.impacts / "aux" / f"{v}.impact-v1.0.json").read_text(encoding="utf-8"))
            variants[f"{v}@impact-v1.0"] = evaluate_selection(old, pairs, verdict, targets, index, sizes)
            variants[f"{v}@impact-v1.0"]["recallKind"] = recall_kind(variants[f"{v}@impact-v1.0"])

    fn = [v for v in FAULTS + changes if variants[v]["recall"] != 1.0]
    spec = json.loads((ROOT / "docs" / "scope-expectations.json").read_text(encoding="utf-8"))
    metrics = {"tool": impact.IMPACT_VERSION, "mapBodySha256": m["bodySha256"], "f0Pair": F0_PAIR,
               "notEvaluatedOffline": {k: NOT_OFFLINE for k in OFFLINE_GAPS}, "verdictSameAcrossRuns": determinism,
               "variants": variants, "recallBelowOne": fn,
               "registration": registration(spec, m, (spec["requestSets"], spec["sessionSets"]), args.impacts),
               "failClosed": fail_closed(spec, args.impacts), "boundary": boundary_rows(spec, args.impacts),
               "runs": run_check.summarize()}
    args.out.write_text(dumps(metrics), encoding="utf-8")
    args.md.write_text(render(metrics), encoding="utf-8")
    print(render(metrics))
    return 1 if fn else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
