#!/usr/bin/env python3
"""Phase 4.0 — 스코핑 테스트 fixture `p36-base-1-mini`를 runs/p36-base-1에서 만든다(한 번 만들어 커밋).

축약: legacy.json은 맵 합성에 필요한 필드만(replayRequestId, hopPath, sessionId, service, origin, request.method·path,
event.topic, callTree.nodes[class·method·depth]). verdict.json은 pair 판정만(replayRequestId, hopPath, sessionId, split,
endpoint, verdict). 원본 Evidence·판정 파일은 건드리지 않는다.

사용: .venv/bin/python scoping/tests/make_fixture.py [--src runs/p36-base-1]
"""
import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEST = Path(__file__).resolve().parent / "fixtures" / "p36-base-1-mini"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=ROOT / "runs" / "p36-base-1", type=Path)
    src = ap.parse_args().src
    if DEST.exists():
        shutil.rmtree(DEST)
    DEST.mkdir(parents=True)
    legacy = json.loads((src / "legacy.json").read_text(encoding="utf-8"))
    mini = [{
        "replayRequestId": r["replayRequestId"], "hopPath": r.get("hopPath", "0"), "sessionId": r["sessionId"],
        "service": r["service"], "origin": r.get("origin", "http"),
        "request": None if not r.get("request") else {"method": r["request"]["method"], "path": r["request"]["path"]},
        "event": None if not r.get("event") else {"topic": r["event"]["topic"]},
        "callTree": {"nodes": [{"class": n["class"], "method": n["method"], "depth": n["depth"]} for n in r["callTree"]["nodes"]]},
    } for r in legacy]
    (DEST / "legacy.json").write_text(json.dumps(mini, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    verdict = json.loads((src / "verdict.json").read_text(encoding="utf-8"))
    pairs = [{k: p[k] for k in ("replayRequestId", "hopPath", "sessionId", "split", "endpoint", "verdict")} for p in verdict["pairs"]]
    (DEST / "verdict.json").write_text(json.dumps({"source": src.name, "engine": verdict["engine"]["version"], "pairs": pairs},
                                                  ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{DEST}: legacy {len(mini)} records, pairs {len(pairs)}")


if __name__ == "__main__":
    main()
