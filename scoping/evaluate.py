#!/usr/bin/env python3
"""Phase 4.3 — 오프라인 평가(D25). **4.0에서는 골격만**: CLI·입출력 형식. 계산은 4.3에서 채운다.

입력: scoping/impacts/<변형>.json, runs/ 전체 재생 판정(verdict*.json — 덮어쓰지 않는다), docs/fault-expectations.json
출력 docs/phase4-metrics.json (결정론):
  변형별 감소율(요청·세션), Observed-diff Recall(F0 `R000047/0` 제외 주·포함 보조, 분모 0 → N/A),
  결함 탐지 유지(행동 차이 없는 변형 N/A), Filter Precision, 세션 검사 재계산, run 범위 dbstate = "not evaluated offline",
  B2-S 전체 조합(C(11,k) 열거 + 요청 예산 보조), ablation 2종(엔드포인트 합집합 맵 / 홉 합산 없는 맵), Tag 순위 품질

사용(4.3): .venv/bin/python scoping/evaluate.py --impacts scoping/impacts --runs runs \
            --expectations docs/fault-expectations.json --out docs/phase4-metrics.json
"""
import argparse
import sys
from pathlib import Path

from common import ROOT


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="스코핑 오프라인 평가(Phase 4.3)")
    ap.add_argument("--impacts", default=ROOT / "scoping" / "impacts", type=Path)
    ap.add_argument("--runs", default=ROOT / "runs", type=Path)
    ap.add_argument("--expectations", default=ROOT / "docs" / "fault-expectations.json", type=Path)
    ap.add_argument("--out", default=ROOT / "docs" / "phase4-metrics.json", type=Path)
    ap.parse_args(argv)
    print("evaluate.py: 4.0 골격 — 오프라인 평가는 Phase 4.3에서 구현한다", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
