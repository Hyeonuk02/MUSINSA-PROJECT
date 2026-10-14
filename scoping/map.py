#!/usr/bin/env python3
"""Phase 4.1 — 맵 합성(D23). **4.0에서는 골격만**: CLI·입출력 형식. 합성 로직은 4.1에서 채운다.

입력: Legacy baseline run 디렉터리들(정본 runs/p36-base-1..3)의 legacy.json, corpus, contract.yaml 엔드포인트 표
출력 scoping/map.json (결정론, 커밋):
  {builtFrom: [run...], requests: {rid: {session, endpoint, classes[], byHop: {hop: classes[]}}},
   endpoints: {id: {classes[], requests[], sessions[]}}, classes: {fqcn: {requests[], endpoints[]}}, coverage}
규칙: Legacy 레코드만(규칙 2). 한 요청의 모든 홉(0, 0.h*, 0.e*)의 callTree 클래스를 그 요청에 합산(byHop 보존).
엔드포인트 맵은 요청 맵의 합집합(요약·미지 요청용 — 선택에는 쓰지 않음). 매칭 키는 common.match_class.

사용(4.1): .venv/bin/python scoping/map.py --runs runs/p36-base-1 runs/p36-base-2 runs/p36-base-3 --out scoping/map.json
"""
import argparse
import sys
from pathlib import Path

from common import ROOT


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="스코핑 맵 합성(Phase 4.1)")
    ap.add_argument("--runs", nargs="+", required=True, type=Path)
    ap.add_argument("--corpus", default=ROOT / "corpus" / "corpus-v2.1.json", type=Path)
    ap.add_argument("--out", default=ROOT / "scoping" / "map.json", type=Path)
    ap.parse_args(argv)
    print("map.py: 4.0 골격 — 합성 로직은 Phase 4.1에서 구현한다", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
