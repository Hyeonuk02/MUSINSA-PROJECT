#!/usr/bin/env python3
"""외부 호출(WireMock journal)과 이벤트(Kafka 기록 consumer)를 Evidence로 만들어 Store에 넣는다 (Step 6, v10.1 §5.1).

앱 Evidence(kind=http/consume)는 앱이 직접 보낸다. 앱 밖에서 관측하는 두 가지는 run이 끝난 뒤 이 도구가 모은다.
  - kind=external: 스택별 WireMock journal을 요청의 baggage(replayRequestId)로 묶는다. 요청 1개당 1건(도착 순서 목록).
  - kind=event:    스택별 Kafka 토픽을 처음부터 읽는다. 레코드 1개당 1건. replayRequestId는 레코드 헤더의 baggage.
키는 앱 Evidence와 같다(runId, replayRequestId, stack). baggage가 없는 호출은 제외하고 개수만 보고한다.

  python3 deploy/compose/tools/collect.py --run-id RUN [--stacks legacy new] [--dry-run]

Compose 전용 수집 경로(docker compose exec)다. k8s로 합칠 때는 kubectl exec/port-forward로 바뀐다.
"""
import argparse
import json
import pathlib
import subprocess
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent.parent  # deploy/compose
STORE = "http://localhost:8099"
TOPICS = ["payment-events"]


def sh(*cmd):
    return subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, check=True).stdout


def baggage(header):
    out = {}
    for member in (header or "").split(","):
        kv = member.split(";", 1)[0].strip()
        if "=" in kv:
            k, v = kv.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def journal(stack):
    raw = sh("docker", "compose", "exec", "-T", f"wiremock-{stack}", "curl", "-s", "http://127.0.0.1:8080/__admin/requests")
    # WireMock은 최신순으로 준다. 도착 순서로 뒤집는다.
    return list(reversed(json.loads(raw)["requests"]))


def kafka_records(stack, topic):
    out = sh("docker", "compose", "exec", "-T", f"kafka-{stack}", "/opt/kafka/bin/kafka-console-consumer.sh",
             "--bootstrap-server", "localhost:9092", "--topic", topic, "--from-beginning", "--timeout-ms", "4000",
             "--formatter-property", "print.headers=true", "--formatter-property", "print.key=true",
             "--formatter-property", "print.offset=true", "--formatter-property", "print.partition=true",
             "--formatter-property", "headers.separator=|~|", "--formatter-property", "key.separator=\t")
    recs = []
    for line in out.splitlines():
        parts = line.split("\t", 4)
        if len(parts) != 5 or not parts[0].startswith("Partition:"):
            continue
        headers = {}
        if parts[2] != "NO_HEADERS":
            for h in parts[2].split("|~|"):
                k, _, v = h.partition(":")
                headers[k] = v
        recs.append({"topic": topic, "partition": int(parts[0].split(":")[1]), "offset": int(parts[1].split(":")[1]),
                     "key": parts[3], "value": parts[4], "headers": headers})
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--stacks", nargs="+", default=["legacy", "new"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    evidence, report = [], {}
    for st in args.stacks:
        by_req, sessions, untagged = {}, {}, 0
        for x in journal(st):
            r = x["request"]
            b = baggage(r.get("headers", {}).get("baggage"))
            rid = b.get("replayRequestId")
            if not rid or b.get("runId") != args.run_id:
                untagged += 1
                continue
            sessions[rid] = b.get("sessionId")
            by_req.setdefault(rid, []).append({
                "order": len(by_req.get(rid, [])) + 1,
                "method": r["method"], "url": r["url"], "body": r.get("body", ""),
                "status": x["responseDefinition"]["status"],
                "headers": {k: r["headers"][k] for k in sorted(r.get("headers", {}))},
            })
        for rid, calls in by_req.items():
            evidence.append({"schemaVersion": "v0", "runId": args.run_id, "replayRequestId": rid, "sessionId": sessions.get(rid),
                             "stack": st, "service": "wiremock", "kind": "external", "seq": 1, "calls": calls})

        events, untagged_ev = 0, 0
        for topic in TOPICS:
            for rec in kafka_records(st, topic):
                b = baggage(rec["headers"].get("baggage"))
                if not b.get("replayRequestId") or b.get("runId") != args.run_id:
                    untagged_ev += 1
                    continue
                evidence.append({"schemaVersion": "v0", "runId": args.run_id, "replayRequestId": b["replayRequestId"],
                                 "sessionId": b.get("sessionId"), "stack": st, "service": "kafka", "kind": "event",
                                 "seq": rec["offset"] + 1, "message": rec})
                events += 1
        report[st] = {"externalRequests": len(by_req), "externalCalls": sum(len(c) for c in by_req.values()),
                      "externalUntagged": untagged, "events": events, "eventsUntagged": untagged_ev}

    if not args.dry_run and evidence:
        req = urllib.request.Request(f"{STORE}/evidence", data=json.dumps(evidence).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as r:
            stored = json.load(r)["stored"]
    else:
        stored = 0
    print(json.dumps({"runId": args.run_id, "stored": stored, "stacks": report}, ensure_ascii=False))


if __name__ == "__main__":
    main()
