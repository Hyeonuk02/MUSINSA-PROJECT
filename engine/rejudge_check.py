#!/usr/bin/env python3
"""엔진 버전을 올린 뒤 기존 run을 메모리에서 다시 판정해 디스크의 판정 파일과 pair 판정·집계를 비교한다(평가 도구).
판정 파일은 덮어쓰지 않는다(Phase 4 고정 — Phase 3 run 판정 파일 덮어쓰기 금지). 클러스터 접근 없음.

비교 대상(run마다 있는 것만):
  verdict.json            arm C, 현재 규칙 세트          (F1~F4·F7·F9·사다리·base는 규칙 적용 0이라 규칙 전후 동일)
  verdict-B0.json/B1.json arm B0 / B1
  verdict-prelabel.json   arm C, 규칙 없음(contract.yaml만) — F5 라벨 전
  verdict-maxselects.json arm C, contract-maxselects.yaml — F8
집계 비교는 summary에서 엔진 버전과 무관한 키(verdicts·bySplit·byEndpoint·undelivered·degraded·sessionViolations)와 runChecks.

사용: .venv/bin/python engine/rejudge_check.py [--runs p33 p35-base ...]   (기본: p33, p35-*, p36-* 각 1..3)
종료 코드: 0 = 변화 없음, 1 = 변화 있음
"""
import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from common import ROOT
from verdict import ENGINE_VERSION, judge_run

RUNS = ROOT / "runs"
RULES = ROOT / "engine" / "rules"
DEFAULT = ["p33", "p35-base", "p35-v1.1", "p35-v1.2", "p35-v1.3", "p35-v1.4", "p36-base"] + [f"p36-F{n}" for n in range(1, 10)]
SUMMARY_KEYS = ("verdicts", "bySplit", "byEndpoint", "undelivered", "degraded", "sessionViolations")


def pairs(v: dict) -> dict:
    return {f"{p['replayRequestId']}/{p['hopPath']}": p["verdict"] for p in v["pairs"]}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="*", default=DEFAULT)
    args = ap.parse_args(argv)
    tmp = Path(tempfile.mkdtemp())
    none = tmp / "rules-none"
    (none / "learned").mkdir(parents=True)
    shutil.copy(RULES / "contract.yaml", none / "contract.yaml")
    (none / "improvement.yaml").write_text("rules: []\n", encoding="utf-8")
    changed_total = 0
    print(f"엔진 {ENGINE_VERSION}")
    try:
        for base in args.runs:
            for i in (1, 2, 3):
                d = RUNS / f"{base}-{i}"
                plans = {"verdict.json": (RULES, "C", None), "verdict-B0.json": (RULES, "B0", None),
                         "verdict-B1.json": (RULES, "B1", None), "verdict-prelabel.json": (none, "C", None),
                         "verdict-maxselects.json": (RULES, "C", RULES / "contract-maxselects.yaml")}
                for fn, (rd, arm, contract) in plans.items():
                    if not (d / fn).exists():
                        continue
                    old = json.loads((d / fn).read_text(encoding="utf-8"))
                    new = judge_run(d, rd, arm, contract)
                    op, np_ = pairs(old), pairs(new)
                    diff = {k: (op.get(k), np_.get(k)) for k in sorted(set(op) | set(np_)) if op.get(k) != np_.get(k)}
                    sdiff = [k for k in SUMMARY_KEYS if old["summary"].get(k) != new["summary"].get(k)]
                    rc = old["runChecks"] != new["runChecks"]
                    changed_total += bool(diff or sdiff or rc)
                    print(f"{d.name:12} {fn:24} {old['engine']['version'][:11]} → {new['engine']['version'][:11]}  pairs {len(np_)}  "
                          f"판정 변경 {diff or 0}  집계 변경 {sdiff or 0}  runChecks 변경 {rc}")
    finally:
        shutil.rmtree(tmp)
    print(f"변화 있는 판정 파일: {changed_total}")
    return 1 if changed_total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
