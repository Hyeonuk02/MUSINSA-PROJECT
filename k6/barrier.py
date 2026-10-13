#!/usr/bin/env python3
"""Phase 3.2 - flush barrier v2 (D19). run.sh가 k6·spill 회수 뒤에 호출한다.

스택별 기대 집합을 corpus에서 결정론적으로 계산하고, 도착한 Evidence가 선언한 자식 홉까지 넓혀 기다린다.
안정화 대기(“N초간 변화 없음”) 휴리스틱은 쓰지 않는다.

  1단계  기대 = k6-summary.json의 sent 각각의 진입 홉 "0"
         + corpus settle 홉 중 **그 스택의 부모 Evidence가 childHopPath로 실제 선언한 것**(v2.1, Phase 3.6 — D19 보완)
         → 스택별로 도착할 때까지 최대 30초
         settle은 k6가 폴링할 힌트일 뿐 기대 집합의 근거가 아니다. 부모가 선언하지 않은 settle 홉(예: F7에서 New 결제가
         실패해 발행이 없음)은 미달이 아니라 행동 차이 — barrier.json의 settleUndeclared에 남기고 엔진(hop_set_equal)으로 넘긴다
  2단계  폐포 = 도착한 Evidence의 externalCalls[].childHopPath(host가 관측 서비스일 때만)
         + events.published[].childHopPath(topic이 관측 토픽일 때만 — order.paid.dlq처럼 소비자가 없는 토픽은 Evidence가 없다)
         → 새로 늘어난 기대가 도착할 때까지 최대 10초. 새로 도착한 Evidence가 또 자식을 선언하면 반복
         settle에 없는 추가 호출(F9의 0.h2처럼 한쪽에만 생긴 호출)의 Evidence도 export 전에 들어오게 하기 위함
  WireMock 같은 외부 대상(host가 관측 서비스가 아님)은 Evidence를 남기지 않으므로 폐포에 넣지 않는다.

미달이면 누락 (requestId, hopPath)를 스택별로 출력하고 exit 1 (run.sh는 export만 하고 중단).
결과는 <run 디렉터리>/barrier.json (스택별 기대 집합·도착 수).

사용: barrier.py --run-dir runs/<runId> --corpus corpus/corpus-v2.json --evidence-url http://localhost/_evidence
             --observed-hosts order,coupon --observed-topics order.paid
"""
import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

STACKS = ("legacy", "new")
ENTRY_TIMEOUT_S = 30
CLOSURE_TIMEOUT_S = 10
POLL_S = 1


def export(evidence_url: str, run_id: str, stack: str) -> list[dict]:
    with urllib.request.urlopen(f"{evidence_url}/export?runId={run_id}&stack={stack}", timeout=30) as r:
        return json.load(r)


def keys_and_children(records: list[dict], observed: set[str], topics: set[str]) -> tuple[set, set]:
    present, children = set(), set()
    for rec in records:
        rid = rec["replayRequestId"]
        present.add((rid, rec.get("hopPath", "0")))
        for call in rec.get("externalCalls", []):
            if call["host"] in observed:
                children.add((rid, call["childHopPath"]))
        for pub in rec.get("events", {}).get("published", []):
            if pub["topic"] in topics:
                children.add((rid, pub["childHopPath"]))
    return present, children


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--evidence-url", required=True)
    ap.add_argument("--observed-hosts", required=True)
    ap.add_argument("--observed-topics", required=True)
    args = ap.parse_args(argv)
    run_id = args.run_dir.name
    observed = {h.strip() for h in args.observed_hosts.split(",") if h.strip()}
    topics = {t.strip() for t in args.observed_topics.split(",") if t.strip()}

    sent = json.loads((args.run_dir / "k6-summary.json").read_text(encoding="utf-8"))["sent"]
    settle = {r["id"]: [s["hop"] for s in r.get("settle", [])]
              for s in json.loads(args.corpus.read_text(encoding="utf-8"))["sessions"] for r in s["requests"]}
    entries = {(rid, "0") for rid in sent}
    settle_all = {(rid, hop) for rid in sent for hop in settle.get(rid, [])}
    expected = {stack: set(entries) for stack in STACKS}
    kinds = {}
    for s in json.loads(args.corpus.read_text(encoding="utf-8"))["sessions"]:
        for r in s["requests"]:
            if r["id"] in sent:
                for x in r.get("settle", []):
                    kinds[x["origin"]] = kinds.get(x["origin"], 0) + 1
    print(f"  1단계 기대: 스택당 진입 {len(sent)} + corpus settle {len(settle_all)} {kinds} 중 부모가 선언한 것")

    def wait(deadline_s: float, phase: str, with_settle: bool = False) -> dict[str, set]:
        """기대가 모두 도착하거나 deadline까지. 반환: 스택별 (present, children).
        with_settle이면 매 폴링마다 '부모가 선언한 settle 홉'을 기대에 더한다(1단계)."""
        end = time.monotonic() + deadline_s
        while True:
            state = {stack: keys_and_children(export(args.evidence_url, run_id, stack), observed, topics) for stack in STACKS}
            if with_settle:
                for stack in STACKS:
                    expected[stack] |= settle_all & state[stack][1]
            missing = {stack: expected[stack] - state[stack][0] for stack in STACKS}
            if not any(missing.values()) or time.monotonic() >= end:
                return state, missing
            time.sleep(POLL_S)

    state, missing = wait(ENTRY_TIMEOUT_S, "1단계", with_settle=True)
    settle_undeclared = {stack: sorted(f"{r}/{h}" for r, h in settle_all - state[stack][1]) for stack in STACKS}
    for stack in STACKS:
        print(f"  1단계 {stack}: 기대 {len(expected[stack])} (진입 {len(entries)} + 선언된 settle {len(expected[stack]) - len(entries)})"
              + (f", 부모가 선언하지 않은 settle {len(settle_undeclared[stack])}: {' '.join(settle_undeclared[stack])} → 엔진(hop 집합)"
                 if settle_undeclared[stack] else ""))
    rounds = 0
    while not any(missing.values()):
        grown = False
        for stack in STACKS:
            new_children = state[stack][1] - expected[stack]
            if new_children:
                expected[stack] |= new_children
                grown = True
        if not grown:
            break
        rounds += 1
        print(f"  2단계 폐포 라운드 {rounds}: 기대 legacy {len(expected['legacy'])}, new {len(expected['new'])}")
        state, missing = wait(CLOSURE_TIMEOUT_S, "2단계")

    result = {
        "runId": run_id,
        "observedHosts": sorted(observed),
        "observedTopics": sorted(topics),
        "closureRounds": rounds,
        "stacks": {stack: {
            "expected": len(expected[stack]),
            "present": len(state[stack][0]),
            "unexpected": sorted(f"{r}/{h}" for r, h in state[stack][0] - expected[stack]),
            "missing": sorted(f"{r}/{h}" for r, h in missing[stack]),
            "settleUndeclared": settle_undeclared[stack],
            "hops": sorted({h for _, h in expected[stack]}),
        } for stack in STACKS},
    }
    (args.run_dir / "barrier.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for stack in STACKS:
        st = result["stacks"][stack]
        print(f"  {stack}: 기대 {st['expected']}, 도착 {st['present']}, 누락 {len(st['missing'])}"
              + (f" {' '.join(st['missing'])}" if st["missing"] else "")
              + (f", 기대 밖 {len(st['unexpected'])} {' '.join(st['unexpected'])}" if st["unexpected"] else ""))
    return 1 if any(missing.values()) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
