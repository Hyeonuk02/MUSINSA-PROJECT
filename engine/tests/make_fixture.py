#!/usr/bin/env python3
"""Phase 3.4 — 테스트 fixture p33-mini를 runs/p33-1에서 만든다(한 번 만들어 커밋, 테스트는 클러스터 없이 이것만 읽는다).

세션: S001·S006·S008(learn) + S007(eval — "learn 라벨이 eval Uncertain을 지움" 테스트용).
입력 계약(runId == 디렉터리 이름)을 지키려고 runId·x-run-id를 p33-mini로 바꾼다. 그 외 Evidence 원문은 그대로.
corpus.json은 해당 세션만 담은 사본(verdict.py는 run 디렉터리의 corpus.json을 run-meta 경로보다 먼저 쓴다).
dbstate-*.json은 run 전체 값 그대로(세션별로 자를 수 없다 — 양쪽 동일성만 검사하므로 충분).

사용: .venv/bin/python engine/tests/make_fixture.py [--src runs/p33-1]
"""
import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEST = Path(__file__).resolve().parent / "fixtures" / "p33-mini"
SESSIONS = ("S001", "S006", "S007", "S008")
RUN_ID = "p33-mini"


def dump(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=ROOT / "runs" / "p33-1", type=Path)
    src = ap.parse_args().src
    if DEST.exists():
        shutil.rmtree(DEST)
    DEST.mkdir(parents=True)

    meta = json.loads((src / "run-meta.json").read_text(encoding="utf-8"))
    corpus = json.loads((ROOT / meta["corpus"]["path"]).read_text(encoding="utf-8"))
    corpus["sessions"] = [s for s in corpus["sessions"] if s["id"] in SESSIONS]
    rids = {r["id"] for s in corpus["sessions"] for r in s["requests"]}
    dump(DEST / "corpus.json", corpus)

    for stack in ("legacy", "new"):
        recs = [r for r in json.loads((src / f"{stack}.json").read_text(encoding="utf-8")) if r["sessionId"] in SESSIONS]
        for r in recs:
            r["runId"] = RUN_ID
            if r.get("request") and "x-run-id" in r["request"]["headers"]:
                r["request"]["headers"]["x-run-id"] = RUN_ID
        dump(DEST / f"{stack}.json", recs)
        shutil.copy(src / f"dbstate-{stack}.json", DEST / f"dbstate-{stack}.json")

    summary = json.loads((src / "k6-summary.json").read_text(encoding="utf-8"))
    dump(DEST / "k6-summary.json", {
        "runId": RUN_ID, "corpusVersion": summary["corpusVersion"], "vus": summary["vus"],
        "sent": [r for r in summary["sent"] if r in rids],
        "degraded": [d for d in summary["degraded"] if d["session"] in SESSIONS],
        "status": {k: v for k, v in summary["status"].items() if k in rids},
    })
    dump(DEST / "run-meta.json", {"runId": RUN_ID, "source": src.name, "sessions": list(SESSIONS),
                                  "corpus": {"version": corpus["version"], "path": "corpus.json (fixture 사본)"}})
    print(f"{DEST}: sessions {SESSIONS}, requests {len(rids)}")


if __name__ == "__main__":
    main()
