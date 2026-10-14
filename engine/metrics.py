#!/usr/bin/env python3
"""Phase 3.7 — 평가 지표 집계(평가 도구, 판정 엔진 아님 — fault_check.py와 같은 위치). 클러스터 접근 없음, 재실행 없음.

입력: runs/ 아래 기존 run 산출물(Evidence·k6-summary·dbstate·run-meta)과 판정 파일(verdict*.json),
      docs/fault-expectations.json(3.6 사전 등록), engine/rules/.
같은 Evidence를 현재 엔진으로 메모리 안에서 여러 "보기"로 판정한다(파일은 쓰지 않는다):
  B0, B1          arm B0·B1
  C_norules       arm C, 규칙 없음(contract.yaml만 — improvement·learned 비움) = "규칙 전"
  C_rules         arm C, 현재 규칙 세트(learned 3 + 사전 승인 1) = "규칙 후"
  C_maxsel        arm C, contract-maxselects.yaml + 현재 규칙(F8만)
디스크의 판정 파일이 어느 보기와 같은지도 확인해 기록한다(integrity).

출력: docs/phase3-metrics.json(결정론 — 시각 없음, 키 정렬), docs/phase3-metrics.md(표)
사용: .venv/bin/python engine/metrics.py
"""
import json
import re
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

from common import ROOT, STACKS
from verdict import ENGINE_VERSION, judge_run

RUNS = ROOT / "runs"
RULES = ROOT / "engine" / "rules"
LADDER = [("base", "p35-base"), ("v1.1", "p35-v1.1"), ("v1.2", "p35-v1.2"), ("v1.3", "p35-v1.3"), ("v1.4", "p35-v1.4")]
FAULTS = [("F0", "p36-base")] + [(f"F{n}", f"p36-F{n}") for n in range(1, 10)]
REAL = ["F1", "F2", "F3", "F4", "F7", "F9"]          # 진짜 결함
PERF = ["F8"]                                         # 성능 계약
CLASSIFY = ["F5", "F6"]                               # 분류 대상(정상 리팩터링·승인된 개선)
FILTERED = ["p35-v1.1-oom-1", "p35-v1.1-stale-1"]     # 판정 전에 걸러진 run(3.5)
# 계획 3.7의 사전 선언 관측 매트릭스(B1 기준). "C만" = B1이 못 잡는다(B0은 원문 DIFF까지, 분류 불가)
DECLARED = {"F1": "C만", "F2": "B1·C", "F3": "C만", "F4": "C만", "F5": "분류(B1 DIFF, C 분류)",
            "F6": "분류(B1 DIFF, C 분류)", "F7": "분류(B1 DIFF, C 분류)", "F8": "B1에서도", "F9": "C만"}


def pairmap(result: dict) -> dict:
    return {f"{p['replayRequestId']}/{p['hopPath']}": p for p in result["pairs"]}


def norules_dir(tmp: Path) -> Path:
    d = tmp / "rules-none"
    (d / "learned").mkdir(parents=True)
    shutil.copy(RULES / "contract.yaml", d / "contract.yaml")
    (d / "improvement.yaml").write_text("rules: []\n", encoding="utf-8")
    return d


def views(run: str, none_dir: Path, maxsel: bool) -> dict:
    d = RUNS / run
    out = {"B0": judge_run(d, RULES, "B0"), "B1": judge_run(d, RULES, "B1"),
           "C_norules": judge_run(d, none_dir, "C"), "C_rules": judge_run(d, RULES, "C")}
    if maxsel:
        out["C_maxsel"] = judge_run(d, RULES, "C", RULES / "contract-maxselects.yaml")
    return out


def verdicts(result: dict) -> dict:
    return {k: p["verdict"] for k, p in pairmap(result).items()}


def disk_integrity(run: str, v: dict) -> dict:
    """디스크 판정 파일이 어느 보기와 pair 판정이 같은지."""
    out = {}
    d = RUNS / run
    for f in sorted(d.glob("verdict*.json")):
        disk = verdicts(json.loads(f.read_text(encoding="utf-8")))
        cands = {"verdict-B0.json": ["B0"], "verdict-B1.json": ["B1"]}.get(f.name, [k for k in v if k.startswith("C_")])
        same = sorted(name for name in cands if name in v and verdicts(v[name]) == disk)
        out[f.name] = same or ["(없음 — 다른 엔진 버전의 기록)"]
    return out


def main() -> int:
    exp = json.loads((ROOT / "docs" / "fault-expectations.json").read_text(encoding="utf-8"))
    tmp = Path(tempfile.mkdtemp())
    try:
        none_dir = norules_dir(tmp)
        V, integ = {}, {}
        for _, base in LADDER + FAULTS + [("p33", "p33")]:
            for i in (1, 2, 3):
                run = f"{base}-{i}"
                V[run] = views(run, none_dir, base == "p36-F8")
                integ[run] = disk_integrity(run, V[run])
        rules_sha = {"C_rules": V["p36-F1-1"]["C_rules"]["engine"]["rules"],
                     "C_norules": V["p36-F1-1"]["C_norules"]["engine"]["rules"],
                     "C_maxsel": V["p36-F8-1"]["C_maxsel"]["engine"]["rules"]}
    finally:
        shutil.rmtree(tmp)

    M = {"engine": {"version": ENGINE_VERSION, "rules": rules_sha},
         "inputs": {"ladder": {k: [f"{b}-{i}" for i in (1, 2, 3)] for k, b in LADDER},
                    "faults": {k: [f"{b}-{i}" for i in (1, 2, 3)] for k, b in FAULTS},
                    "aa": ["p33-1", "p33-2", "p33-3"], "expectations": "docs/fault-expectations.json"},
         "integrity": integ}

    # ---------------------------------------------------------------- 1. 결함 탐지율
    def check(F, view, key):
        targets = exp[F][key]
        per_pair = {k: all(pairmap(V[f"{dict(FAULTS)[F]}-{i}"][view])[k]["verdict"] == want
                           if k in pairmap(V[f"{dict(FAULTS)[F]}-{i}"][view]) else False for i in (1, 2, 3))
                    for k, want in targets.items()}
        return per_pair

    def false_pos(F, view="C_rules"):
        fps = []
        for i in (1, 2, 3):
            base = verdicts(V[f"p36-base-{i}"]["C_rules"])
            got = verdicts(V[f"{dict(FAULTS)[F]}-{i}"][view])
            targets = set(exp[F]["targets"])
            fps.append(sorted(k for k, v in got.items() if k not in targets and k in base and v != base[k]))
        return fps

    det = {}
    for F, base in FAULTS:
        if F == "F0":
            parts = {"C_rules": check(F, "C_rules", "targets")}
        elif F == "F5":
            parts = {"pre(C_norules)": check(F, "C_norules", "targets"), "post(C_rules)": check(F, "C_rules", "afterLearnLabels")}
        elif F == "F8":
            parts = {"C_rules": check(F, "C_rules", "targets"), "C_maxsel": check(F, "C_maxsel", "targetsMaxSelects")}
        else:
            parts = {"C_rules": check(F, "C_rules", "targets")}
        rc_ok = True
        for want_check, want in exp[F].get("runCheck", {}).items():
            for i in (1, 2, 3):
                got = {r["check"]: r["ok"] for r in V[f"{base}-{i}"]["C_rules"]["runChecks"]}
                rc_ok &= got.get(want_check) == want
        fps = false_pos(F)
        pairs_ok = {name: sum(p.values()) for name, p in parts.items()}
        pairs_n = {name: len(p) for name, p in parts.items()}
        # pair 단위: F5는 전·후 둘 다 맞아야 1, F8은 기본(C_rules)만 92에 넣고 maxSelects는 따로
        if F == "F5":
            both = [k for k in exp[F]["targets"] if parts["pre(C_norules)"][k] and parts["post(C_rules)"][k]]
            main_ok, main_n = len(both), len(exp[F]["targets"])
        else:
            first = next(iter(parts))
            main_ok, main_n = pairs_ok[first], pairs_n[first]
        det[F] = {"category": "real" if F in REAL else "perf" if F in PERF else "classify" if F in CLASSIFY else "baseline",
                  "views": {n: {"ok": pairs_ok[n], "n": pairs_n[n]} for n in parts},
                  "pairsOk": main_ok, "pairsN": main_n,
                  "maxSelOk": pairs_ok.get("C_maxsel"), "maxSelN": pairs_n.get("C_maxsel"),
                  "runCheckOk": rc_ok, "falsePositives": fps[0] if fps[0] == fps[1] == fps[2] else fps,
                  "detected": all(v == pairs_n[n] for n, v in pairs_ok.items()) and rc_ok}
    v11 = []
    for i in (1, 2, 3):
        old = verdicts(json.loads((RUNS / f"p36-F1-{i}" / "verdict-engine-v1.1.json").read_text(encoding="utf-8")))
        base = verdicts(V[f"p36-base-{i}"]["C_rules"])
        v11.append(sorted(k for k, v in old.items() if k not in exp["F1"]["targets"] and k in base and v != base[k]))
    det["F1"]["falsePositivesEngineV11"] = v11[0]

    def rate(cat):
        fs = [F for F, d in det.items() if d["category"] == cat]
        return {"faults": fs, "detected": sum(det[F]["detected"] for F in fs), "n": len(fs)}
    detection = {"real": rate("real"), "perf": rate("perf"), "classify": rate("classify")}
    detection["all"] = {"detected": sum(x["detected"] for x in detection.values()),
                        "n": sum(x["n"] for x in detection.values())}
    detection["pairs"] = {"ok": sum(det[F]["pairsOk"] for F in det if F != "F0"),
                          "n": sum(det[F]["pairsN"] for F in det if F != "F0"),
                          "maxSelOk": det["F8"]["maxSelOk"], "maxSelN": det["F8"]["maxSelN"]}
    M["detection"] = {"perFault": det, "summary": detection}

    # ---------------------------------------------------------------- 2. 수동 검토 감소율 (eval 기준)
    def unc(result, split):
        return sum(1 for p in result["pairs"] if p["verdict"] == "UNCERTAIN" and p["split"] == split)

    def npairs(result, split):
        return sum(1 for p in result["pairs"] if p["split"] == split)

    def rule_split(result):
        c = Counter()
        for p in result["pairs"]:
            for a in p["appliedRules"]:
                c["learned" if a["rule"].startswith("learned-") else "approved"] += 1
        return c

    review = {}
    for F, base in FAULTS[1:]:
        rows = []
        for i in (1, 2, 3):
            pre, post = V[f"{base}-{i}"]["C_norules"], V[f"{base}-{i}"]["C_rules"]
            # 규칙으로 UNC가 빠진 pair를 규칙 출처별로
            pm, qm = pairmap(pre), pairmap(post)
            by = Counter()
            for k, p in qm.items():
                if pm[k]["verdict"] == "UNCERTAIN" and p["verdict"] != "UNCERTAIN" and p["split"] == "eval":
                    src = {"learned" if a["rule"].startswith("learned-") else "approved" for a in p["appliedRules"]}
                    by["+".join(sorted(src))] += 1
            rows.append({"evalPairs": npairs(post, "eval"), "evalUncBefore": unc(pre, "eval"), "evalUncAfter": unc(post, "eval"),
                         "learnPairs": npairs(post, "learn"), "learnUncBefore": unc(pre, "learn"), "learnUncAfter": unc(post, "learn"),
                         "evalClearedBy": dict(sorted(by.items()))})
        review[F] = {"perRun": rows[0], "sameAcrossRuns": rows[0] == rows[1] == rows[2]}

    def total(keys):
        t = Counter()
        for F in keys:
            for k in ("evalPairs", "evalUncBefore", "evalUncAfter", "learnPairs", "learnUncBefore", "learnUncAfter"):
                t[k] += review[F]["perRun"][k]
        t = dict(t)
        t["reduction"] = round((t["evalUncBefore"] - t["evalUncAfter"]) / t["evalUncBefore"], 4) if t["evalUncBefore"] else None
        return t
    fs = [F for F, _ in FAULTS[1:]]
    M["review"] = {"perFault": review, "total": total(fs), "totalExclF8": total([F for F in fs if F != "F8"]),
                   "note": "run당 값(세 run 동일). 3 run 합계는 ×3. F8의 eval Uncertain 6은 maxSelects 미선언 시 의도된 결과"}

    # ---------------------------------------------------------------- 3. 오판정률
    hidden, real_n = [], 0
    for F in REAL:
        base = dict(FAULTS)[F]
        for k in exp[F]["targets"]:
            real_n += 1
            for i in (1, 2, 3):
                pre = pairmap(V[f"{base}-{i}"]["C_norules"])[k]["verdict"]
                post = pairmap(V[f"{base}-{i}"]["C_rules"])[k]["verdict"]
                if pre != post and post in ("SAME", "IMPROVEMENT"):
                    hidden.append(f"{F} {k} run{i}: {pre}→{post}")
    applications = {}
    for name, base in LADDER + FAULTS:
        c = rule_split(V[f"{base}-1"]["C_rules"])
        same = all(rule_split(V[f"{base}-{i}"]["C_rules"]) == c for i in (2, 3))
        applications[name] = {"learned": c["learned"], "approved": c["approved"], "sameAcrossRuns": same}
    M["misjudgment"] = {"realTargetPairs": real_n, "realTargetPairRuns": real_n * 3, "hidden": hidden,
                        "rate": len(hidden) / (real_n * 3), "ruleApplicationsRun1": applications}

    # ---------------------------------------------------------------- 4. Rule 재사용 효과 (learned 3)
    def learned_cleared(result_pre, result_post):
        pm, qm = pairmap(result_pre), pairmap(result_post)
        out = Counter()
        for k, p in qm.items():
            if any(a["rule"].startswith("learned-") for a in p["appliedRules"]) and pm[k]["verdict"] == "UNCERTAIN":
                out[p["split"]] += 1
        return dict(out)
    reuse = {}
    for name, base in LADDER + FAULTS:
        r = learned_cleared(V[f"{base}-1"]["C_norules"], V[f"{base}-1"]["C_rules"])
        reuse[name] = {"learn": r.get("learn", 0), "eval": r.get("eval", 0)}
    M["ruleReuse"] = {"perVariantRun1": reuse,
                      "a_F5_eval": reuse["F5"]["eval"],
                      "b_otherVariants": sum(v["learn"] + v["eval"] for k, v in reuse.items() if k.startswith("F") and k != "F5"),
                      "c_ladder_v13_v14": sum(reuse[k]["learn"] + reuse[k]["eval"] for k in ("v1.3", "v1.4")),
                      "ladder_all": sum(reuse[k]["learn"] + reuse[k]["eval"] for k, _ in LADDER)}

    # ---------------------------------------------------------------- 5. 운영 지표
    ops = {"runs": [], "filtered": FILTERED}
    for d in sorted(p for p in RUNS.iterdir() if re.match(r"^p3\d", p.name)):
        if not (d / "k6-summary.json").exists():
            continue
        s = json.loads((d / "k6-summary.json").read_text(encoding="utf-8"))
        und = None
        if all((d / f"{st}.json").exists() for st in STACKS):
            hop0 = {st: {r["replayRequestId"] for r in json.loads((d / f"{st}.json").read_text(encoding="utf-8"))
                         if r.get("hopPath", "0") == "0"} for st in STACKS}
            und = sum(1 for st in STACKS for rid in s["sent"] if rid not in hop0[st])
        ops["runs"].append({"run": d.name, "sent": len(s["sent"]), "undelivered": und, "degraded": len(s.get("degraded", [])),
                            "settleTimeouts": len(s.get("settleTimeouts", [])), "filtered": d.name in FILTERED})
    counted = [r for r in ops["runs"] if not r["filtered"]]
    ops["totals"] = {"runs": len(ops["runs"]), "judgedOrGateRuns": len(counted), "filteredRuns": len(FILTERED),
                     "undelivered": sum(r["undelivered"] or 0 for r in counted),
                     "degraded": sum(r["degraded"] for r in counted),
                     "settleTimeouts": sum(r["settleTimeouts"] for r in counted)}
    agree = {}
    for name, base in LADDER + FAULTS + [("A/A p33", "p33")]:
        agree[name] = all(verdicts(V[f"{base}-{i}"]["C_rules"]) == verdicts(V[f"{base}-1"]["C_rules"]) for i in (2, 3))
    ops["threeRunAgreement"] = {"groups": agree, "agreed": sum(agree.values()), "n": len(agree)}
    sv = [dict(x, run=run) for run, v in sorted(V.items()) for x in v["C_rules"]["summary"]["sessionViolations"]]
    ops["sessionViolations"] = {"total": len(sv), "bothStacks": sum(1 for x in sv if x["bothStacks"]),
                                "attributed": sum(1 for x in sv if x["attributedPairs"]), "items": sv}
    M["ops"] = ops

    # ---------------------------------------------------------------- arm 비교
    arms = {}
    for name, base in LADDER + FAULTS:
        r1 = V[f"{base}-1"]
        targets = exp.get(name, {}).get("targets", {}) if name.startswith("F") else {}
        row = {"pairs": r1["C_rules"]["summary"]["pairs"],
               "B0_DIFF": r1["B0"]["summary"]["verdicts"].get("DIFF", 0), "B1_DIFF": r1["B1"]["summary"]["verdicts"].get("DIFF", 0),
               "C": r1["C_rules"]["summary"]["verdicts"], "C_norules": r1["C_norules"]["summary"]["verdicts"],
               "sameAcrossRuns": all(r1[a]["summary"]["verdicts"] == V[f"{base}-{i}"][a]["summary"]["verdicts"]
                                     for a in ("B0", "B1", "C_rules") for i in (2, 3))}
        if "C_maxsel" in r1:
            row["C_maxsel"] = r1["C_maxsel"]["summary"]["verdicts"]
        if targets and name != "F0":
            seen = {a: [k for k in targets if all(pairmap(V[f"{base}-{i}"][a]).get(k, {}).get("verdict") == "DIFF" for i in (1, 2, 3))]
                    for a in ("B0", "B1")}
            row["targets"] = len(targets)
            row["B0_targetsDIFF"] = len(seen["B0"])
            row["B1_targetsDIFF"] = len(seen["B1"])
            row["B1_missed"] = sorted(set(targets) - set(seen["B1"]))
            row["C_caught"] = det[name]["detected"]
            b1 = len(seen["B1"]) / len(targets)
            actual = "B1 미탐(C만)" if b1 == 0 else "B1 가시" if b1 == 1 else f"B1 일부({len(seen['B1'])}/{len(targets)})"
            decl = DECLARED[name]
            match = ("일치" if (decl == "C만" and b1 == 0) or (decl != "C만" and b1 == 1)
                     else "반 칸(결함 요청 B1 미탐, 후속 조회 가시)" if decl == "C만" and 0 < b1 < 1 else "불일치")
            row["matrix"] = {"declared": decl, "actual": actual, "match": match}
        arms[name] = row
    M["arms"] = arms

    out_json = ROOT / "docs" / "phase3-metrics.json"
    out_json.write_text(json.dumps(M, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (ROOT / "docs" / "phase3-metrics.md").write_text(render(M), encoding="utf-8")
    print(render(M))
    return 0


def pct(a, b):
    return f"{a}/{b} ({a / b * 100:.1f}%)" if b else f"{a}/{b}"


def render(M) -> str:
    L = ["# Phase 3 지표 (engine/metrics.py 생성 — 손으로 고치지 않는다)", "",
         f"엔진 `{M['engine']['version']}`. 규칙 세트 sha256은 `docs/phase3-metrics.json` `engine.rules`. 입력 run은 `inputs`.", ""]
    d = M["detection"]
    L += ["## 1. 결함 탐지율", "",
          "| 결함 | 분류 | target pair (보기별 ok/n, 3 run 모두) | runCheck | 정상 경로 오탐 | 탐지 |", "|---|---|---|---|---|---|"]
    for F, x in d["perFault"].items():
        vs = ", ".join(f"{n} {v['ok']}/{v['n']}" for n, v in x["views"].items())
        fp = x["falsePositives"]
        fp_s = (str(len(fp)) if isinstance(fp[0] if fp else "", str) or not fp else str(fp))
        if F == "F1":
            fp_s += f" (engine-v1.1 기준 {len(x['falsePositivesEngineV11'])}: {', '.join(x['falsePositivesEngineV11'])})"
        L.append(f"| {F} | {x['category']} | {vs} | {'OK' if x['runCheckOk'] else '불일치'} | {fp_s} | {'✔' if x['detected'] else '✘'} |")
    s = d["summary"]
    L += ["", f"- 결함 단위: 진짜 결함 {pct(s['real']['detected'], s['real']['n'])}, 성능 계약 {pct(s['perf']['detected'], s['perf']['n'])}, "
          f"분류 대상 {pct(s['classify']['detected'], s['classify']['n'])}, 합계 {pct(s['all']['detected'], s['all']['n'])}",
          f"- pair 단위: {pct(s['pairs']['ok'], s['pairs']['n'])} (F5는 규칙 전 UNC·후 IMP 둘 다 맞아야 1) + F8 maxSelects {pct(s['pairs']['maxSelOk'], s['pairs']['maxSelN'])}", ""]
    r = M["review"]
    L += ["## 2. 수동 검토 감소율 (eval 세션 기준, run당 — 세 run 동일)", "",
          "| 변형 | eval pair | eval UNC 규칙 전 → 후 | 감소 출처 | learn UNC 전 → 후 (참고) |", "|---|---|---|---|---|"]
    for F, x in r["perFault"].items():
        p = x["perRun"]
        L.append(f"| {F} | {p['evalPairs']} | {p['evalUncBefore']} → {p['evalUncAfter']} | {p['evalClearedBy'] or '-'} | {p['learnUncBefore']} → {p['learnUncAfter']} |")
    for label, t in (("합계(F1~F9)", r["total"]), ("합계(F8 제외)", r["totalExclF8"])):
        red = f"{t['reduction'] * 100:.1f}%" if t["reduction"] is not None else "-"
        L.append(f"| **{label}** | {t['evalPairs']} | **{t['evalUncBefore']} → {t['evalUncAfter']}** (감소율 {red}) | | {t['learnUncBefore']} → {t['learnUncAfter']} |")
    m = M["misjudgment"]
    L += ["", "## 3. 오판정률", "",
          f"진짜 결함(F1·F2·F3·F4·F7·F9) target pair {m['realTargetPairs']}개 × 3 run = {m['realTargetPairRuns']} 판정 중 규칙(learned 3 + 사전 1)에 의해 SAME·IMPROVEMENT로 바뀐 것: "
          f"**{len(m['hidden'])} / {m['realTargetPairRuns']}** ({m['rate'] * 100:.1f}%)", "",
          "| 변형 | learned 규칙 적용(run1, pair-규칙 수) | 사전 승인 규칙 적용 | 세 run 동일 |", "|---|---|---|---|"]
    for k, v in m["ruleApplicationsRun1"].items():
        L.append(f"| {k} | {v['learned']} | {v['approved']} | {'✔' if v['sameAcrossRuns'] else '✘'} |")
    u = M["ruleReuse"]
    L += ["", "## 4. Rule 재사용 효과 (F5 learn 5 pair → learned 규칙 3)", "",
          f"- (a) F5 eval: Uncertain → Improvement **{u['a_F5_eval']}** pair",
          f"- (b) 다른 변형(F0~F4, F6~F9): **{u['b_otherVariants']}**",
          f"- (c) 사다리 v1.3·v1.4: **{u['c_ladder_v13_v14']}** (사다리 전체 {u['ladder_all']})", "",
          "| 변형 | learn | eval |", "|---|---|---|"]
    for k, v in u["perVariantRun1"].items():
        L.append(f"| {k} | {v['learn']} | {v['eval']} |")
    o = M["ops"]
    t = o["totals"]
    L += ["", "## 5. 운영 지표 (참고)", "",
          f"- Phase 3 run 디렉터리(p31~p36): {t['runs']} (판정·게이트 대상 {t['judgedOrGateRuns']}, 걸러진 run {t['filteredRuns']}: {', '.join(o['filtered'])})",
          f"- 판정·게이트 대상 run 합계: Undelivered(진입 홉) {t['undelivered']}, degraded {t['degraded']}, settleTimeouts {t['settleTimeouts']}",
          f"- 3 run 판정 일치(C, pair 단위 완전 일치): {o['threeRunAgreement']['agreed']}/{o['threeRunAgreement']['n']} 그룹",
          f"- sessionViolations(C, 판정한 run 전체): {o['sessionViolations']['total']}건 — pair 귀속 {o['sessionViolations']['attributed']}, bothStacks {o['sessionViolations']['bothStacks']}"
          + "".join(f"; {x['run']} {x['check']}[{x['key']}] legacy {x['legacy']} / new {x['new']} → {x['attributedPairs']}" for x in o['sessionViolations']['items']), "",
          "| run | sent | Undelivered | degraded | settleTimeouts | 걸러짐 |", "|---|---|---|---|---|---|"]
    for x in o["runs"]:
        L.append(f"| {x['run']} | {x['sent']} | {x['undelivered'] if x['undelivered'] is not None else '-'} | {x['degraded']} | {x['settleTimeouts']} | {'✔' if x['filtered'] else ''} |")
    L += ["", "## arm 비교 B0 / B1 / C (run1 — 세 run 동일 여부 열)", "",
          "| 변형 | pairs | B0 DIFF | B1 DIFF | C (규칙 후) | C 규칙 전 | target | B0 target DIFF | B1 target DIFF | C 기대 일치 | 사전 선언 매트릭스 | 실제 | 일치 | 세 run 동일 |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, a in M["arms"].items():
        c = a["C"] if "C_maxsel" not in a else f"{a['C']} / maxSel {a['C_maxsel']}"
        mx = a.get("matrix", {})
        L.append(f"| {k} | {a['pairs']} | {a['B0_DIFF']} | {a['B1_DIFF']} | {c} | {a['C_norules']} | {a.get('targets', '-')} | "
                 f"{a.get('B0_targetsDIFF', '-')} | {a.get('B1_targetsDIFF', '-')} | {('✔' if a['C_caught'] else '✘') if 'C_caught' in a else '-'} | "
                 f"{mx.get('declared', '-')} | {mx.get('actual', '-')} | {mx.get('match', '-')} | {'✔' if a['sameAcrossRuns'] else '✘'} |")
    miss = {k: a["B1_missed"] for k, a in M["arms"].items() if a.get("B1_missed")}
    L += ["", "B1 미탐(target pair가 B1에서 SAME): " + "; ".join(f"{k} {len(v)}건 ({', '.join(v)})" for k, v in miss.items()), "",
          "각주: 사전 선언의 \"C만 잡는다\"는 \"B1이 못 잡는다(B0은 원문 비교라 DIFF까지는 보지만 분류는 못 함)\"로 읽는다. "
          "세션 검사 위반의 pair 귀속은 engine-v1.2 규칙(D-6/D20), bothStacks 플래그는 오탐·탐지율에 세지 않고 별도 보고(5절 sessionViolations).", "",
          "## 판정 파일 무결성", "",
          "디스크의 verdict*.json이 같은 pair 판정을 내는 메모리 보기(B0·B1·C_norules·C_rules·C_maxsel). `docs/phase3-metrics.json` `integrity`에 run별 전체.", ""]
    for run, files in M["integrity"].items():
        if run.endswith("-1"):
            L.append(f"- {run}: " + "; ".join(f"{f} = {', '.join(v)}" for f, v in files.items()))
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
