#!/usr/bin/env python3
"""Prince Mart 결함 판정 대조와 지표 (6단계). 판정 엔진이 아니다 — runs/<run>/verdict*.json, legacy/new.json과 사전 등록만 읽는다.

사용: .venv/bin/python tracks/prince-mart/tools/fault_metrics.py [--json out.json] [PF1 PF2 ...]

집계(사전 등록 tools/faults/fault-expectations.json의 _definitions.count)
  match         엔진 판정 == 정답
  misjudged     엔진이 정답과 다른 확정 판정(SAME, IMPROVEMENT, CONTRACT_VIOLATION). 대상 밖 pair(정답 SAME)가 SAME이 아니면 여기에 센다
  review        정답이 확정인데 엔진이 UNCERTAIN(검토)
  notComparable 정답이 MISALIGNED(비교 불성립)
예상 대비: 실제 엔진 판정 == expectedEngine(변형별 키)인 pair 수.
변형: default(verdict.json, expectedEngine), learn(verdict-learn.json, expectedEngineAfterLearn),
      approved(verdict-approved.json, expectedEngineApproved), maxSelects(verdict-maxselects.json, expectedEngineMaxSelects).
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXP = ROOT / "tracks/prince-mart/tools/faults/fault-expectations.json"
VARIANTS = [("default", "verdict.json", "expectedEngine"), ("learn", "verdict-learn.json", "expectedEngineAfterLearn"),
            ("approved", "verdict-approved.json", "expectedEngineApproved"), ("maxSelects", "verdict-maxselects.json", "expectedEngineMaxSelects")]
MIS, UNC, SAME = "MISALIGNED", "UNCERTAIN", "SAME"


def keys(run: Path, stack: str) -> set[str]:
    return {f"{e['replayRequestId']}/{e['hopPath']}" for e in json.loads((run / f"{stack}.json").read_text(encoding="utf-8"))}


def classify(truth: str, got: str | None) -> str:
    if truth == MIS:
        return "notComparable"
    if got == truth:
        return "match"
    if got == UNC:
        return "review"
    return "misjudged"


def one(pf: str, exp: dict, base_dir: str) -> dict:
    out = {}
    run_base = pf.lower()
    for name, file, exp_key in VARIANTS:
        if name != "default" and exp_key not in exp:
            continue
        runs = []
        for i in (1, 2, 3):
            run = ROOT / "runs" / f"{run_base}-{i}"
            vf = run / file
            if not vf.exists():
                continue
            v = json.loads(vf.read_text(encoding="utf-8"))
            got = {f"{p['replayRequestId']}/{p['hopPath']}": p["verdict"] for p in v["pairs"]}
            base = {f"{p['replayRequestId']}/{p['hopPath']}": p["verdict"]
                    for p in json.loads((ROOT / "runs" / f"{base_dir}-{i}" / "verdict.json").read_text(encoding="utf-8"))["pairs"]}
            truth = exp["targets"]
            engine_exp = {**exp["expectedEngine"], **exp.get(exp_key, {})}
            counts = Counter()
            detail = {}
            for pair, t in truth.items():
                g = got.get(pair)
                c = classify(t, g)
                counts[c] += 1
                detail[pair] = {"truth": t, "engine": g, "expected": engine_exp.get(pair), "class": c}
            outside = {pair: g for pair, g in got.items() if pair not in truth and g != SAME}
            counts["misjudged"] += len(outside)
            agree = sum(1 for pair in truth if got.get(pair) == engine_exp.get(pair))
            agree_outside = sum(1 for pair in got if pair not in truth and got[pair] == SAME)
            lk, nk = keys(run, "legacy"), keys(run, "new")
            rc = {r["check"]: r["ok"] for r in v["runChecks"]}
            runs.append({
                "run": f"{run_base}-{i}", "verdicts": v["summary"]["verdicts"], "counts": dict(counts),
                "agreeExpected": agree, "targets": len(truth), "outsideTargetsNonSame": outside,
                "outsideTargetsSame": agree_outside,
                "legacyOnly": sorted(lk - nk), "newOnly": sorted(nk - lk),
                "legacyOnlyExpected": sorted(exp.get("legacyOnlyHops", {})), "newOnlyExpected": sorted(exp.get("newOnlyHops", {})),
                "runCheck": rc, "runCheckExpected": exp.get("runCheck", {}),
                "undelivered": sum(len(x) for x in v["summary"]["undelivered"].values()), "degraded": len(v["summary"]["degraded"]),
                "baselineMissing": sorted(set(base) - set(got)), "detail": detail,
                "signature": json.dumps(got, sort_keys=True),
            })
        if runs:
            out[name] = {"runs": runs, "sameAcrossRuns": len({r["signature"] for r in runs}) == 1}
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("faults", nargs="*")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--base", default="p4-aa")
    args = ap.parse_args(argv)
    exp_all = json.loads(EXP.read_text(encoding="utf-8"))
    faults = args.faults or [k for k in exp_all if k.startswith("PF")]
    result = {pf: one(pf, exp_all[pf], args.base) for pf in faults}
    print("| PF | 변형 | targets | 일치 | 오판정 | 검토 | 비교 불성립 | 오판정+비교 불성립 | 예상 엔진 판정과 같음 | 대상 밖 비-SAME | runCheck(기대) | 한쪽에만 있는 홉(등록과 같음) | 세 run 동일 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for pf, variants in result.items():
        for name, r in variants.items():
            x = r["runs"][0]
            c = x["counts"]
            hop_ok = x["legacyOnly"] == x["legacyOnlyExpected"] and x["newOnly"] == x["newOnlyExpected"]
            print(f"| {pf} | {name} | {x['targets']} | {c.get('match', 0)} | {c.get('misjudged', 0)} | {c.get('review', 0)} | "
                  f"{c.get('notComparable', 0)} | {c.get('misjudged', 0) + c.get('notComparable', 0)} | {x['agreeExpected']}/{x['targets']} | "
                  f"{len(x['outsideTargetsNonSame'])} | {x['runCheck']}({x['runCheckExpected']}) | "
                  f"legacy {len(x['legacyOnly'])}, new {len(x['newOnly'])} ({'예' if hop_ok else '아니오'}) | {'예' if r['sameAcrossRuns'] else '아니오'} |")
    if args.json:
        for variants in result.values():
            for r in variants.values():
                for x in r["runs"]:
                    x.pop("signature", None)
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
