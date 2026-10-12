#!/usr/bin/env python3
"""Evidence Store v0 (architecture v10.1 §5, Phase 2.3)

앱(Evidence 필터·Kafka 인터셉터)과 수집 도구(WireMock journal, Kafka 기록 consumer)가 보낸 Evidence를 받아 저장하고,
k6(완료 대기)·run script(flush barrier)·비교 엔진(export)에 돌려준다.

저장소는 SQLite 파일 하나다. v10.1 §11-2(Store 저장소: 파일 vs 경량 DB)가 미결이라 임시로 고른 것이다
(docs/legacy-decision-log.md L10). 표준 라이브러리만 쓴다.

키: (runId, replayRequestId, stack). 한 요청이 여러 서비스를 거치므로 같은 키 안에 service·kind·seq가 다른 여러 건이 있다.

  POST /evidence                         Evidence 1건(JSON 객체) 또는 여러 건(JSON 배열) 저장
  POST /runs                             run 단위 정보(runContext: iteration, vu, arm, corpusVersion, s0Version, imageDigest …)
  GET  /count?runId=[&requestId=][&stack=][&kind=]   건수
  GET  /exists?requestId=&stack=[&runId=][&kind=]    존재 여부
  GET  /export?runId=                    run 정보 + Evidence 전체(정렬: stack, replayRequestId, service, kind, seq)
  GET  /health
"""
import json
import os
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

DB_PATH = os.environ.get("STORE_DB", "/data/evidence.db")
PORT = int(os.environ.get("STORE_PORT", "8080"))
REQUIRED = ("runId", "replayRequestId", "stack", "service", "kind")

_lock = threading.Lock()
_db = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
_db.execute("PRAGMA journal_mode=WAL")
_db.execute("""CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL, request_id TEXT NOT NULL, stack TEXT NOT NULL,
    service TEXT NOT NULL, kind TEXT NOT NULL, seq INTEGER,
    internal INTEGER NOT NULL,           -- X-Evidence-Internal: true 로 들어왔는지(앱 전송은 1이어야 한다)
    body TEXT NOT NULL)""")
_db.execute("CREATE INDEX IF NOT EXISTS ix_key ON evidence(run_id, request_id, stack)")
_db.execute("CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, body TEXT NOT NULL)")


class Handler(BaseHTTPRequestHandler):
    server_version = "evidence-store/0"

    def log_message(self, fmt, *args):  # 요청마다 로그를 남기지 않는다(양이 많다)
        pass

    def _send(self, status, obj):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _query(self):
        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"null")
        except json.JSONDecodeError as e:
            return self._send(400, {"error": f"invalid json: {e}"})
        if path == "/evidence":
            items = payload if isinstance(payload, list) else [payload]
            internal = 1 if self.headers.get("X-Evidence-Internal", "").lower() == "true" else 0
            rows = []
            for e in items:
                missing = [k for k in REQUIRED if not e.get(k)]
                if missing:
                    return self._send(400, {"error": f"missing {missing}"})
                rows.append((e["runId"], e["replayRequestId"], e["stack"], e["service"], e["kind"],
                             e.get("seq"), internal, json.dumps(e, ensure_ascii=False)))
            with _lock:
                _db.executemany("INSERT INTO evidence(run_id, request_id, stack, service, kind, seq, internal, body) "
                                "VALUES (?,?,?,?,?,?,?,?)", rows)
            return self._send(201, {"stored": len(rows)})
        if path == "/runs":
            if not isinstance(payload, dict) or not payload.get("runId"):
                return self._send(400, {"error": "runId required"})
            with _lock:
                _db.execute("INSERT OR REPLACE INTO runs(run_id, body) VALUES (?,?)",
                            (payload["runId"], json.dumps(payload, ensure_ascii=False)))
            return self._send(201, {"runId": payload["runId"]})
        return self._send(404, {"error": "not found"})

    def _where(self, q, require):
        cols = {"runId": "run_id", "requestId": "request_id", "stack": "stack", "kind": "kind", "service": "service"}
        for r in require:
            if not q.get(r):
                raise ValueError(f"{r} required")
        conds, args = [], []
        for k, col in cols.items():
            if q.get(k):
                conds.append(f"{col} = ?")
                args.append(q[k])
        return (" WHERE " + " AND ".join(conds)) if conds else "", args

    def do_GET(self):
        path, q = urlparse(self.path).path, self._query()
        try:
            if path == "/health":
                return self._send(200, {"status": "ok"})
            if path == "/count":
                where, args = self._where(q, ["runId"])
                n = _db.execute(f"SELECT count(*) FROM evidence{where}", args).fetchone()[0]
                return self._send(200, {"count": n})
            if path == "/exists":
                where, args = self._where(q, ["requestId", "stack"])
                n = _db.execute(f"SELECT count(*) FROM evidence{where}", args).fetchone()[0]
                return self._send(200, {"exists": n > 0, "count": n})
            if path == "/export":
                where, args = self._where(q, ["runId"])
                rows = _db.execute(f"SELECT body FROM evidence{where} "
                                   "ORDER BY stack, request_id, service, kind, seq, id", args).fetchall()
                run = _db.execute("SELECT body FROM runs WHERE run_id = ?", (q["runId"],)).fetchone()
                not_internal = _db.execute(f"SELECT count(*) FROM evidence{where} AND internal = 0 AND kind IN ('http','consume')",
                                           args).fetchone()[0]
                return self._send(200, {"schema": "evidence-export/v0", "runId": q["runId"],
                                        "run": json.loads(run[0]) if run else None,
                                        "appEvidenceWithoutInternalHeader": not_internal,
                                        "evidence": [json.loads(r[0]) for r in rows]})
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        return self._send(404, {"error": "not found"})


if __name__ == "__main__":
    print(f"evidence-store v0 listening on :{PORT}, db={DB_PATH}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
