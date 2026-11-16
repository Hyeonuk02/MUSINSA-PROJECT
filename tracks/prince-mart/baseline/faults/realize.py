#!/usr/bin/env python3
"""결함 실현 확인(E2, 평가 도구 — 판정 엔진 아님). 결함이 기대한 pair에만 드러났는지 B1 차이로 본다.

입력: runs/<run-base>-1..3/compare.json(없으면 engine/compare.py를 먼저 돌린다), runs/<base>-1..3/compare.json(A/A),
      faults/fault-expectations.json(사전 등록), faults/fault-expectations-amendments.json(run 뒤 발견한 기대 누락, L20).
pair 단위로:
  - targets: 기대 대상 pair에 B1 차이가 있는가(판정이 SAME 아닌 것으로 기대했으므로 차이가 있어야 한다)
  - 대상 밖: targets·legacyOnly·newOnly 밖의 pair에 B1 차이가 없는가(있으면 결함이 기대보다 넓게 퍼짐)
  - 한쪽에만: Undelivered/Unexpected가 legacyOnly/newOnly와 같은가
  - dbstate: 테이블 비교 결과가 runCheck.dbstate_equal과 같은가(등록이 없으면 같아야 한다)
A/A 기준선은 B1 0이어야 하고, 세 run의 차이 집합이 서로 같은지도 본다.
판정은 원래 기대로 하고, 보정(amendments)이 있으면 보정을 더한 기대로 본 대상 밖 차이도 함께 보고한다.

  python3 baseline/faults/realize.py --fault PF1 --run-base pf1 [--base aa-004]
종료 코드: 0 = 기대한 곳에만 실현, 1 = 다름
"""
import argparse
import json
import pathlib
import subprocess
import sys

BASELINE = pathlib.Path(__file__).resolve().parent.parent


def pair_key(k):
    """R000001|order|http|1 -> R000001/order.http.1 (fault-expectations.json 형식)"""
    rid, svc, kind, n = k
    return f"{rid}/{svc}.{kind}.{n}"


def load(run):
    p = BASELINE / "runs" / run / "compare.json"
    if not p.exists():
        # 결함 run은 차이가 있으므로 compare.py가 1(FAIL)로 끝난다. compare.json만 쓰면 된다
        subprocess.run([sys.executable, str(BASELINE / "engine" / "compare.py"), str(p.parent)], capture_output=True)
    c = json.loads(p.read_text())
    diffs = {}
    for d in c["diffSets"]["b1"]:
        k, path = d.split("::", 1)
        diffs.setdefault(pair_key(k.split("|")), []).append(path)
    return {"diffs": diffs, "legacyOnly": {pair_key(k) for k in c["undelivered"]},
            "newOnly": {pair_key(k) for k in c["unexpected"]},
            "tablesEqual": not [t for t, v in c["tables"].items() if not v["rawEqual"]],
            "tablesMismatched": [t for t, v in c["tables"].items() if not v["rawEqual"]]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fault", required=True)
    ap.add_argument("--run-base", required=True)
    ap.add_argument("--base", default="aa-004")
    ap.add_argument("--iterations", type=int, default=3)
    args = ap.parse_args()
    exp = json.loads((BASELINE / "faults" / "fault-expectations.json").read_text())[args.fault]
    targets = set(exp["targets"])
    legacy_only, new_only = set(exp.get("legacyOnly", [])), set(exp.get("newOnly", []))
    db_equal = exp.get("runCheck", {}).get("dbstate_equal", True)
    amends = json.loads((BASELINE / "faults" / "fault-expectations-amendments.json").read_text()).get(args.fault, [])
    amended = targets | {a["pair"] for a in amends}

    ok, signatures = True, []
    for i in range(1, args.iterations + 1):
        base, got = load(f"{args.base}-{i}"), load(f"{args.run_base}-{i}")
        hit = targets & set(got["diffs"])
        missed = sorted(targets - set(got["diffs"]))
        spread = sorted(set(got["diffs"]) - targets - legacy_only - new_only)
        lo_bad = (got["legacyOnly"] ^ legacy_only)
        no_bad = (got["newOnly"] ^ new_only)
        base_bad = bool(base["diffs"] or base["legacyOnly"] or base["newOnly"])
        db_ok = got["tablesEqual"] == db_equal
        print(f"== {args.run_base}-{i} (기준선 {args.base}-{i}: B1 {'0' if not base_bad else '차이 있음'})")
        print(f"   targets 실현 {len(hit)}/{len(targets)}" + (f"  미실현 {missed}" if missed else ""))
        print(f"   대상 밖 차이 {len(spread)}" + (f" {spread}" if spread else ""))
        if amends:
            spread_a = sorted(set(got["diffs"]) - amended - legacy_only - new_only)
            print(f"   └ 보정 기대(amendments {len(amends)}) 기준 대상 밖 차이 {len(spread_a)}" + (f" {spread_a}" if spread_a else ""))
        print(f"   legacy에만 {len(got['legacyOnly'])}/{len(legacy_only)} new에만 {len(got['newOnly'])}/{len(new_only)}"
              + (f"  기대와 다름 {sorted(lo_bad | no_bad)}" if lo_bad or no_bad else ""))
        print(f"   dbstate 같음={got['tablesEqual']} (기대 {db_equal})" + (f" 다른 테이블 {got['tablesMismatched']}" if got["tablesMismatched"] else ""))
        ok &= not (missed or spread or lo_bad or no_bad or base_bad) and db_ok
        signatures.append(json.dumps({"diffs": {k: sorted(v) for k, v in sorted(got["diffs"].items())},
                                      "lo": sorted(got["legacyOnly"]), "no": sorted(got["newOnly"]),
                                      "tables": got["tablesMismatched"]}, sort_keys=True))
    same = len(set(signatures)) == 1
    print(f"세 run 차이 집합 동일: {same}")
    print("결과:", "기대한 곳에만 실현" if ok and same else "기대와 다름")
    return 0 if ok and same else 1


if __name__ == "__main__":
    sys.exit(main())
