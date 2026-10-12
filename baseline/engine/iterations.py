#!/usr/bin/env python3
"""반복 run 비교 (Step 8-1, 8-2). 각 run의 compare.json과 export만 입력으로 받는다.

  python3 baseline/engine/iterations.py baseline/runs/aa-001-1 baseline/runs/aa-001-2 baseline/runs/aa-001-3

확인
  - 비교 유효 조건 해시가 run마다 같은지(같은 조건에서 돌았는지)
  - B0 범주·diff 집합, B1 diff 집합이 run마다 같은지(v10.1 §4.2: 반복 간 diff 집합이 같아야 판정으로 인정)
  - 누락(barrier)·Undelivered·degraded가 0인지
  - 환경 drift: 첫 run의 Legacy Evidence(정규화 후, runId 치환)와 DB가 다음 run과 같은지
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from compare import diff_paths, normalize  # noqa: E402


def legacy_normalized(run, rules, run_id):
    ev = json.loads((run / "legacy.json").read_text())
    out = {}
    for e in ev:
        k = (e["replayRequestId"], e["service"], e["kind"], int(e.get("seq") or 0))
        out[k] = json.loads(json.dumps(normalize(e, rules)).replace(run_id, "<RUN>"))
    return out


def main():
    runs = [pathlib.Path(p) for p in sys.argv[1:]]
    rules = json.loads(pathlib.Path(__file__).with_name("normalization.json").read_text())
    reports = [json.loads((r / "compare.json").read_text()) for r in runs]
    metas = [json.loads((r / "run-meta.json").read_text()) for r in runs]

    base = reports[0]
    same_validity = len({r["validityHash"] for r in reports}) == 1
    same_b0_cats = all({c: v["diffs"] for c, v in r["b0"]["byCategory"].items()} ==
                       {c: v["diffs"] for c, v in base["b0"]["byCategory"].items()} for r in reports)
    same_b0_set = all(r["diffSets"]["b0"] == base["diffSets"]["b0"] for r in reports)
    same_b1_set = all(r["diffSets"]["b1"] == base["diffSets"]["b1"] for r in reports)
    # 시각·소요 시간은 양쪽 값이 같은 ms로 찍히면 우연히 diff에서 빠져 건수가 흔들린다. 그 밖의 B0 diff 집합은 같아야 한다.
    timing_like = ("timing", "capturedAt", "durationMs")
    non_timing = [{d for d in r["diffSets"]["b0"] if not any(t in d.split("::")[1] for t in timing_like)} for r in reports]
    same_b0_non_timing = all(x == non_timing[0] for x in non_timing)

    drift = []
    ref = legacy_normalized(runs[0], rules, metas[0]["runId"])
    ref_db = json.loads((runs[0] / "db-legacy.json").read_text())
    for run, meta in zip(runs[1:], metas[1:]):
        cur = legacy_normalized(run, rules, meta["runId"])
        diffs = [(k, p) for k in sorted(set(ref) | set(cur)) for p in diff_paths(ref.get(k), cur.get(k))]
        db_same = json.loads((run / "db-legacy.json").read_text()) == ref_db
        drift.append({"run": meta["runId"], "vs": metas[0]["runId"], "evidenceDiffs": len(diffs),
                      "examples": [f"{'|'.join(map(str, k))}::{p}" for k, p in diffs[:5]], "dbSame": db_same})

    out = {
        "runs": [r["runId"] for r in reports],
        "validityHash": {"same": same_validity, "value": base["validityHash"]},
        "perRun": [{"runId": r["runId"], "sent": r["requestsSent"], "degraded": r["degradedSessions"],
                    "barrierOk": m["barrier"]["ok"], "missing": len(m["barrier"]["missing"]),
                    "undelivered": len(r["undelivered"]), "paired": r["paired"],
                    "pairingFail": sum(v["fail"] for v in r["pairing"].values()),
                    "b0": r["b0"]["diffs"], "b0ByCategory": {c: v["diffs"] for c, v in r["b0"]["byCategory"].items()},
                    "b1": r["b1"]["diffs"],
                    "tablesMismatch": [t for t, v in r["tables"].items() if not all(v["same"].values())],
                    "orderSame": all(v["same"] for v in r["order"].values())}
                   for r, m in zip(reports, metas)],
        "acrossRuns": {"b0CategoryCountsSame": same_b0_cats, "b0DiffSetSame": same_b0_set,
                       "b0DiffSetSameExcludingTiming": same_b0_non_timing, "b1DiffSetSame": same_b1_set},
        "drift": drift,
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))
    ok = (same_validity and same_b1_set and same_b0_non_timing and all(p["b1"] == 0 and p["undelivered"] == 0 and p["missing"] == 0
                                                 and not p["degraded"] and p["barrierOk"] for p in out["perRun"])
          and all(d["evidenceDiffs"] == 0 and d["dbSame"] for d in drift))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
