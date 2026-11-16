#!/usr/bin/env python3
"""Prince Mart 베이스라인 run script (Step 7-4, v10.1 §4.3)

  python3 baseline/k6/run.py --run-id base-001 [--iterations 3] [--vus 1] [--corpus baseline/corpus/corpus-v1.json]

iteration마다:
  1. reset      deploy/compose/reset.sh (두 스택 S0)
  2. run 정보    비교 유효 조건 해시 = hash(corpus, S0 init SQL, WireMock 매핑, 고정 시각, 이미지 digest, Normalization 규칙)
                → Store POST /runs, run-meta.json
  3. k6         baseline/k6/run.js (VU=1, 세션 순서대로, 요청마다 양쪽 Evidence 도착 대기)
  4. barrier    보낸 요청마다 두 스택이 완료(closure: 진입 Evidence + 선언된 하위 처리만큼 도착) + 두 스택 consumer lag 0.
                타임아웃이면 완료되지 않은 요청·스택을 보고. legacy 건수가 corpus expect.evidence와 다르면 따로 보고
  5. collect    WireMock journal(kind=external), Kafka 토픽(kind=event)을 Store에 넣는다
  6. export     runs/<runId>/legacy.json, new.json (Evidence 배열), k6-summary.json, k6-results.jsonl, run-meta.json
  7. db         runs/<runId>/db-legacy.json, db-new.json (테이블별 전체 행, Step 8의 테이블 비교용)

결과 배치는 hyeonuk-dev Phase 2 계획(2.6)과 같다. 위치만 baseline/runs/(gitignore).
"""
import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "deploy" / "compose"
BASELINE = ROOT / "baseline"
CORPUS = BASELINE / "corpus" / "corpus-v1.1.json"   # --corpus로 바꿀 수 있다(v1 결과 재현)
NORMALIZATION = BASELINE / "engine" / "normalization.json"   # Step 8에서 생긴다. 없으면 "none"
STORE = "http://localhost:8099"
K6_IMAGE = "grafana/k6@sha256:e66db15b860113878fa74670e31f5e274830b7b6e42c8bff28b2f2d86a257603"  # k6 v2.3.0
NETWORK = "prince-mart_legacy"   # k6는 외부 클라이언트처럼 legacy 네트워크에서 nginx로 보낸다
STACKS = ["legacy", "new"]
TABLES = {"order": ["orders", "order_items", "order_status_history"],
          "coupon": ["coupons", "coupon_usage"],
          "payment": ["payments", "refunds"]}


def log(msg):
    print(f"[run] {msg}", flush=True)


def sh(cmd, cwd=COMPOSE, check=True):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check).stdout


def http(method, path, body=None):
    req = urllib.request.Request(STORE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def sha256_files(paths):
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(str(p.relative_to(ROOT)).encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def run_meta(run_id, base, iteration, vus):
    fixed_clock = next(l.split(":", 1)[1].strip().strip('"') for l in (COMPOSE / "docker-compose.yml").read_text().splitlines()
                       if l.strip().startswith("APP_FIXED_CLOCK:"))
    # 실제로 떠 있는 컨테이너의 이미지를 스택별로 읽는다(결함 실험에서는 new만 PF<n> 이미지, baseline/faults/deploy.sh).
    # 유효성 해시(images)는 legacy 스택만 덮는다 — 조건은 같고 arm(new 버전)만 다른 run끼리 비교할 수 있게.
    running = {st: {svc: sh(["docker", "inspect", f"prince-mart-{svc}-{st}-1", "--format", "{{.Image}}"]).strip()
                    for svc in ["order", "coupon", "payment"]} for st in STACKS}
    images = running["legacy"]
    new_version = next(e.split("=", 1)[1] for e in json.loads(sh(["docker", "inspect", "prince-mart-order-new-1",
                       "--format", "{{json .Config.Env}}"])) if e.startswith("EVIDENCE_VERSION="))
    parts = {
        "corpus": sha256_files([CORPUS]),
        "s0": sha256_files(list((COMPOSE / "mysql-initdb").rglob("*.sql")) + [COMPOSE / "kafka" / "init-topics.sh"]),
        "wiremock": sha256_files(list((COMPOSE / "wiremock" / "mappings").glob("*.json"))),
        "fixedClock": hashlib.sha256(fixed_clock.encode()).hexdigest(),
        "images": hashlib.sha256(json.dumps(images, sort_keys=True).encode()).hexdigest(),
        "normalization": sha256_files([NORMALIZATION]) if NORMALIZATION.exists() else "none",
    }
    validity = hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()
    corpus = json.loads(CORPUS.read_text())
    return {"runId": run_id, "baseRunId": base, "iteration": iteration, "vus": vus,
            "arm": "A/A (legacy image on both stacks)" if running["new"] == running["legacy"] else f"fault {new_version}",
            "newVersion": new_version, "corpusVersion": corpus["version"],
            "fixedClock": fixed_clock, "imageDigests": images, "stackImages": running,
            "conditionHashes": parts, "validityHash": validity,
            "startedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def consumer_lag(stack):
    out = sh(["docker", "compose", "exec", "-T", f"kafka-{stack}", "/opt/kafka/bin/kafka-consumer-groups.sh",
              "--bootstrap-server", "localhost:9092", "--describe", "--group", "order-service"])
    rows = [l.split() for l in out.splitlines() if l.startswith("order-service")]
    # GROUP TOPIC PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG ...
    return sum(0 if r[5] == "-" and r[4] == "0" else (int(r[5]) if r[5].isdigit() else 10**9) for r in rows)


INTERNAL = {"ORDER-SERVICE": "order", "COUPON-SERVICE": "coupon", "PAYMENT-SERVICE": "payment"}


def closure(evs, request_id):
    """스택 하나의 완료 여부(k6 run.js의 closure()와 같은 규칙, legacy-decision-log L17)."""
    app = [e for e in evs if e["kind"] in ("http", "consume")]
    is_entry = lambda e: e["kind"] == "http" and (e["request"].get("headers") or {}).get("x-replay-request-id") == request_id
    declared = {"order": 0, "coupon": 0, "payment": 0, "consume": 0}
    present = dict(declared)
    for e in app:
        for o in e.get("outbound") or []:
            svc = INTERNAL.get((o.get("url") or "").split("/")[2] if "//" in (o.get("url") or "") else "")
            if svc and o.get("status") is not None:
                declared[svc] += 1
        declared["consume"] += len(e.get("events") or [])
        if e["kind"] == "consume":
            present["consume"] += 1
        elif not is_entry(e):
            present[e["service"]] += 1
    settled = any(is_entry(e) for e in app) and all(present[k] >= declared[k] for k in declared)
    return settled, len(app)


def barrier(run_id, results, timeout=60):
    deadline = time.time() + timeout
    while True:
        status, counts = [], {st: 0 for st in STACKS}
        for r in results:
            for st in STACKS:
                ok, n = closure(http("GET", f"/export?runId={run_id}&requestId={r['requestId']}&stack={st}"), r["requestId"])
                counts[st] += n
                status.append({"requestId": r["requestId"], "stack": st, "settled": ok, "got": n,
                               "expected": r["expectedEvidence"] if st == "legacy" else None})
        lags = {st: consumer_lag(st) for st in STACKS}
        unsettled = [x for x in status if not x["settled"]]
        if (not unsettled and all(v == 0 for v in lags.values())) or time.time() > deadline:
            legacy_mismatch = [x for x in status if x["stack"] == "legacy" and x["got"] != x["expected"]]
            return {"ok": not unsettled and all(v == 0 for v in lags.values()),
                    "expectedLegacy": sum(r["expectedEvidence"] for r in results), "counts": counts,
                    "consumerLag": lags, "missing": unsettled, "legacyCountMismatch": legacy_mismatch}
        time.sleep(0.5)


def dump_db(stack):
    out = {}
    for svc, tables in TABLES.items():
        for t in tables:
            raw = sh(["docker", "compose", "exec", "-T", f"mysql-{svc}-{stack}", "sh", "-c",
                      f'mysql -B -u root -p"$MYSQL_ROOT_PASSWORD" {svc}_db -e "SELECT * FROM {t} ORDER BY 1" 2>/dev/null'])
            lines = raw.splitlines()
            cols = lines[0].split("\t") if lines else []
            out[f"{svc}.{t}"] = {"columns": cols, "rows": [l.split("\t") for l in lines[1:]]}
    return out


def one_run(run_id, base, iteration, vus):
    out = BASELINE / "runs" / run_id
    out.mkdir(parents=True, exist_ok=True)

    log(f"{run_id}: reset")
    t = time.time()
    subprocess.run(["./reset.sh"], cwd=COMPOSE, check=True, capture_output=True)
    reset_s = round(time.time() - t, 1)

    meta = run_meta(run_id, base, iteration, vus)
    meta["resetSeconds"] = reset_s
    http("DELETE", f"/runs/{run_id}")          # 같은 runId로 다시 돌릴 때 이전 Evidence를 지운다
    http("POST", "/runs", meta)

    log(f"{run_id}: k6 (VUS={vus})")
    t = time.time()
    k6 = subprocess.run(["docker", "run", "--rm", "--network", NETWORK,
                         "-v", f"{BASELINE / 'k6'}:/k6:ro", "-v", f"{BASELINE / 'corpus'}:/corpus:ro", "-v", f"{out}:/out",
                         "-e", f"RUN_ID={run_id}", "-e", f"VUS={vus}", "-e", f"CORPUS=/corpus/{CORPUS.name}",
                         K6_IMAGE, "run", "--quiet", "--log-format", "raw", "/k6/run.js"],
                        capture_output=True, text=True)
    k6_s = round(time.time() - t, 1)
    lines = [l for l in (k6.stdout + k6.stderr).splitlines() if l.startswith("{")]
    results = [json.loads(l) for l in lines if '"type":"result"' in l]
    sessions = [json.loads(l) for l in lines if '"type":"session"' in l]
    (out / "k6-results.jsonl").write_text("\n".join(lines) + "\n")
    if k6.returncode != 0 and not results:
        sys.exit(f"k6 failed:\n{k6.stdout}\n{k6.stderr}")

    log(f"{run_id}: flush barrier")
    b = barrier(run_id, results)

    log(f"{run_id}: collect external calls / events")
    collected = json.loads(subprocess.run([sys.executable, str(COMPOSE / "tools" / "collect.py"), "--run-id", run_id],
                                          capture_output=True, text=True, check=True).stdout)

    log(f"{run_id}: export")
    for st in STACKS:
        (out / f"{st}.json").write_text(json.dumps(http("GET", f"/export?runId={run_id}&stack={st}"),
                                                    ensure_ascii=False, indent=1))
        (out / f"db-{st}.json").write_text(json.dumps(dump_db(st), ensure_ascii=False, indent=1))

    meta.update({"finishedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "k6Seconds": k6_s,
                 "requestsSent": len(results),
                 "requestsInCorpus": sum(len(s["requests"]) for s in json.loads(CORPUS.read_text())["sessions"]),
                 "statusMismatches": [r["requestId"] for r in results if not r["statusOk"]],
                 "degradedSessions": [s["sessionId"] for s in sessions if s["degraded"]],
                 "settleWaitMs": {"max": max((r["waitedMs"] for r in results), default=0),
                                  "sum": sum(r["waitedMs"] for r in results)},
                 "barrier": b, "collected": collected["stacks"]})
    (out / "run-meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    http("POST", "/runs", meta)
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True, help="기본 runId. iteration이 2 이상이면 <run-id>-<i>")
    ap.add_argument("--iterations", type=int, default=1)
    ap.add_argument("--vus", type=int, default=1)
    ap.add_argument("--corpus", help="corpus 파일(기본 corpus-v1.1.json)")
    args = ap.parse_args()
    global CORPUS
    if args.corpus:
        CORPUS = pathlib.Path(args.corpus).resolve()

    v = subprocess.run([sys.executable, str(BASELINE / "corpus" / "validate.py"), str(CORPUS)], capture_output=True, text=True)
    if v.returncode != 0:
        sys.exit(f"corpus validation failed:\n{v.stdout}")

    summary = []
    for i in range(1, args.iterations + 1):
        run_id = args.run_id if args.iterations == 1 else f"{args.run_id}-{i}"
        m = one_run(run_id, args.run_id, i, args.vus)
        summary.append({k: m[k] for k in ["runId", "validityHash", "requestsSent", "requestsInCorpus", "statusMismatches",
                                         "degradedSessions", "resetSeconds", "k6Seconds", "settleWaitMs"]}
                       | {"barrierOk": m["barrier"]["ok"], "evidencePerStack": m["barrier"]["counts"],
                          "missing": m["barrier"]["missing"], "collected": m["collected"]})
        log(f"{run_id}: done barrier_ok={m['barrier']['ok']} sent={m['requestsSent']}/{m['requestsInCorpus']} "
            f"degraded={m['degradedSessions']} status_mismatch={m['statusMismatches']}")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    sys.exit(0 if all(s["barrierOk"] and not s["degradedSessions"] for s in summary) else 1)


if __name__ == "__main__":
    main()
