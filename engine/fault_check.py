#!/usr/bin/env python3
"""Phase 3.6 — 결함 run의 기대 판정 대조(평가 도구, 판정 엔진 아님). 클러스터 접근 없음.

입력: runs/<F run>-1..3의 verdict*.json, baseline runs/<base>-1..3의 verdict.json, docs/fault-expectations.json(사전 등록).
pair 단위로:
  - targets: 결함이 겨냥한 pair의 실제 판정 == 기대 판정
  - 정상 경로: targets 밖의 pair는 baseline 판정과 같아야 한다(오탐 = baseline과 다른 non-target pair)
  - pair 집합: baseline에 있는데 F run에 없는 pair, 그 반대(한쪽 스택에만 생긴 홉은 pair가 아니다)
세 run의 판정이 서로 같은지도 본다.

사용: .venv/bin/python engine/fault_check.py --fault F1 --run-base p36-F1 [--base p36-base] [--verdict verdict.json]
      [--expect-key targets]   (F5 라벨 후: afterLearnLabels, F8 maxSelects: targetsMaxSelects)
종료 코드: 0 = 기대와 일치, 1 = 불일치
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(run_dir: Path, name: str) -> dict:
    v = json.loads((run_dir / name).read_text(encoding="utf-8"))
    return {f"{p['replayRequestId']}/{p['hopPath']}": p for p in v["pairs"]}, v


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fault", required=True)
    ap.add_argument("--run-base", required=True)
    ap.add_argument("--base", default="p36-base")
    ap.add_argument("--verdict", default="verdict.json")
    ap.add_argument("--expect-key", default="targets")
    args = ap.parse_args(argv)
    exp = json.loads((ROOT / "docs" / "fault-expectations.json").read_text(encoding="utf-8"))[args.fault]
    targets = exp[args.expect_key]

    ok = True
    signatures = []
    for i in (1, 2, 3):
        base, _ = load(ROOT / "runs" / f"{args.base}-{i}", "verdict.json")
        got, whole = load(ROOT / "runs" / f"{args.run_base}-{i}", args.verdict)
        miss_t = {k: (v, got.get(k, {}).get("verdict")) for k, v in targets.items() if got.get(k, {}).get("verdict") != v}
        fp = {k: (base[k]["verdict"], p["verdict"]) for k, p in got.items()
              if k not in targets and k in base and p["verdict"] != base[k]["verdict"]}
        only_base = sorted(set(base) - set(got))
        only_f = sorted(set(got) - set(base))
        run_checks = {rc["check"]: rc["ok"] for rc in whole["runChecks"]}
        rc_bad = {c: run_checks.get(c) for c, want in exp.get("runCheck", {}).items()
                  if args.expect_key == "targets" and run_checks.get(c) != want}
        detected = sum(1 for k in targets if got.get(k, {}).get("verdict") == targets[k])
        print(f"== {args.run_base}-{i} ({args.verdict}, 기대 {args.expect_key}) verdicts {whole['summary']['verdicts']}")
        print(f"   targets 일치 {detected}/{len(targets)}" + (f"  불일치 {miss_t}" if miss_t else ""))
        print(f"   정상 경로 오탐(baseline과 다른 non-target) {len(fp)}" + (f" {fp}" if fp else ""))
        print(f"   pair 집합: baseline에만 {only_base or 0}, F run에만 {only_f or 0}")
        if exp.get("runCheck"):
            print(f"   runChecks {run_checks}" + (f"  기대와 다름 {rc_bad}" if rc_bad else ""))
        print(f"   Undelivered {sum(len(v) for v in whole['summary']['undelivered'].values())}, degraded {len(whole['summary']['degraded'])}")
        ok &= not miss_t and not fp and not rc_bad and not whole["summary"]["degraded"] \
            and not any(whole["summary"]["undelivered"].values())
        signatures.append(json.dumps({k: p["verdict"] for k, p in sorted(got.items())}, sort_keys=True))
    same = len(set(signatures)) == 1
    print(f"세 run 판정 동일: {same}")
    print("결과:", "기대와 일치" if ok and same else "기대와 다름")
    return 0 if ok and same else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
