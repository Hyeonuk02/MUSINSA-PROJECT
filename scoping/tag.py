#!/usr/bin/env python3
"""Phase 4.4 — Tag 모드: 판정 뒤 pair에 영향 범위를 붙이고 리뷰 순서를 만든다. 판정·재생 수는 바꾸지 않는다.

입력: runs/<runId>/verdict.json, impact.json. 출력 runs/<runId>/tags.json (결정론):
  {runId, impact{path, sha256, toolVersion}, pairs[{pair, session, endpoint, verdict, inScope, impactedRequest, tier, reasons[]}],
   reviewOrder[pair...], summary}
inScope = 선택 세션의 pair(세션 입도, D-4.3a). impactedRequest = 영향 요청의 pair(보조).
리뷰 순서 tier 1 영향 요청 → 2 같은 세션의 나머지 → 3 범위 밖. 같은 tier 안은 corpus 순서(run의 요청 id·hop).
Tag의 효과는 비-SAME pair가 앞쪽에 모이는가뿐이다 — 검토량 감소가 아니다.

사용: .venv/bin/python scoping/tag.py --run runs/<runId> --impact scoping/impacts/<변형>.json
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

from common import dumps, load_verdict

F0_PAIR = "R000047/0"


def build_tags(verdict: dict, impact: dict) -> tuple[list[dict], list[str]]:
    sessions, impacted = set(impact["selectedSessions"]), impact["impactedRequests"]
    rows = []
    for p in verdict["pairs"]:
        rid = p["replayRequestId"]
        in_scope = p["sessionId"] in sessions
        hit = rid in impacted
        rows.append({"pair": f"{rid}/{p['hopPath']}", "session": p["sessionId"], "endpoint": p["endpoint"], "verdict": p["verdict"],
                     "inScope": in_scope, "impactedRequest": hit, "tier": 1 if hit else 2 if in_scope else 3,
                     "reasons": impacted.get(rid, [])})
    rows.sort(key=lambda r: (r["tier"], r["pair"].split("/")[0], r["pair"]))
    return rows, [r["pair"] for r in rows]


def summarize(rows: list[dict]) -> dict:
    diffs = [r for r in rows if r["verdict"] != "SAME" and r["pair"] != F0_PAIR]
    def grain(key):
        inside = sum(r[key] for r in rows)
        hit = sum(r[key] for r in diffs)
        return {"pairs": inside, "budget": round(inside / len(rows), 4), "diffsInside": hit, "diffs": len(diffs),
                "rate": round(hit / len(diffs), 4) if diffs else None}
    tiers = {str(t): sum(r["tier"] == t for r in rows) for t in (1, 2, 3)}
    return {"pairs": len(rows), "session": grain("inScope"), "requestAuxiliary": grain("impactedRequest"), "tiers": tiers,
            "f0": next((r["inScope"] for r in rows if r["pair"] == F0_PAIR), None)}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Tag 모드 태그·리뷰 순서(Phase 4.4)")
    ap.add_argument("--run", required=True, type=Path)
    ap.add_argument("--impact", required=True, type=Path)
    args = ap.parse_args(argv)
    raw = args.impact.read_bytes()
    impact = json.loads(raw)
    rows, order = build_tags(load_verdict(args.run), impact)
    out = {"runId": args.run.name, "impact": {"path": str(args.impact), "sha256": hashlib.sha256(raw).hexdigest(), "toolVersion": impact.get("toolVersion")},
           "pairs": rows, "reviewOrder": order, "summary": summarize(rows)}
    (args.run / "tags.json").write_text(dumps(out), encoding="utf-8")
    print(json.dumps(out["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
