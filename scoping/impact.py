#!/usr/bin/env python3
"""Phase 4.2 — 영향 산출(D24). **4.0에서는 골격만**: CLI·입출력 형식. 규칙 1~6 적용은 4.2에서 채운다.

입력: scoping/map.json, git base·head, head 체크아웃 소스(정적 참조 폐포), corpus
출력 impact.json (결정론):
  {base, head, changedFiles[{path, status, kind, fqcns}], changedClasses, observed[],
   unobserved[{fqcn, closurePaths[], reachedClasses[], unresolved}], globalTriggered, globalReasons[],
   impactedRequests{rid: reasons[]}, impactedEndpoints, selectedSessions, selectedRequests,
   reductionRequests, reductionSessions, mapRef}
규칙(call-graph.md 4절 + D24): 관측 → 그 클래스가 실행된 요청 / 미관측 → 정적 참조 폐포(깊이 ≤3, 합집합, 미해결 → 전역) /
resource·build·deploy·삭제 → 전역 / verify·docs·test만 → 영향 없음(verify면 A/A 게이트 경고) / 전역 하나라도 → 전역.
선택 단위는 세션. 파일 분류는 common.classify_path, 변경 목록은 common.name_status(`git diff -M`).

사용(4.2): .venv/bin/python scoping/impact.py --map scoping/map.json --base <ref> --head <ref> --repo . \
            --corpus corpus/corpus-v2.1.json --out impact.json [--explain] [--ignore-kind build]
"""
import argparse
import sys
from pathlib import Path

from common import KINDS, ROOT


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="영향 산출(Phase 4.2)")
    ap.add_argument("--map", default=ROOT / "scoping" / "map.json", type=Path)
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--repo", default=ROOT, type=Path)
    ap.add_argument("--corpus", default=ROOT / "corpus" / "corpus-v2.1.json", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--explain", action="store_true")
    ap.add_argument("--ignore-kind", action="append", choices=KINDS, default=[])
    ap.parse_args(argv)
    print("impact.py: 4.0 골격 — 영향 산출은 Phase 4.2에서 구현한다", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
