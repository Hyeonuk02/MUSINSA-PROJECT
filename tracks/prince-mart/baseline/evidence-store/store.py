#!/usr/bin/env python3
"""Evidence Store v0 — Prince Mart 베이스라인 트랙 (architecture v10.1 §5)

앱(Evidence 필터·Kafka 인터셉터)과 수집 도구(WireMock journal, Kafka 기록 consumer)가 보낸 Evidence를 받아 저장하고,
k6(완료 대기)·run script(flush barrier)·비교 엔진(export)에 돌려준다.

API는 hyeonuk-dev Phase 2 계획(2.3)의 계약과 호환되게 맞췄다(exists 200/404, count&stack, export 배열·&stack, DELETE /runs).
이 트랙에 필요한 것은 확장으로 둔다: 한 키 안의 여러 건(service·kind·seq), count/exists의 requestId·kind·service 필터, run 정보.
저장은 SQLite 파일 하나다. v10.1 §11-2(Store 저장소: 파일 vs 경량 DB)가 미결이라 임시로 고른 것이다(legacy-decision-log L10).
표준 라이브러리만 쓴다.

키: (runId, replayRequestId, stack). 한 요청이 여러 서비스를 거치므로 같은 키 안에 service·kind·seq가 다른 여러 건이 있다.
(runId, replayRequestId, stack, service, kind, seq)가 같은 Evidence를 다시 받으면 덮어쓴다(멱등).

  POST   /evidence                      Evidence 1건(JSON 객체) 또는 여러 건(JSON 배열)
  GET    /exists?runId=&requestId=&stack=[&kind=][&service=]   있으면 200, 없으면 404 (본문 {exists, count})
  GET    /count?runId=[&stack=][&requestId=][&kind=][&service=] {count}
  GET    /export?runId=[&stack=]        Evidence 배열(정렬: stack, replayRequestId, service, kind, seq)
  POST   /runs                          run 정보(runId 필수) 저장
  GET    /runs/{runId}                  run 정보
  DELETE /runs/{runId}                  run의 Evidence와 정보 삭제
  GET    /health
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
FILTERS = {"runId": "run_id", "requestId": "request_id", "stack": "stack", "kind": "kind", "service": "service"}

_lock = threading.Lock()
_db = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
_db.execute("PRAGMA journal_mode=WAL")
_db.execute("""CREATE TABLE IF NOT EXISTS evidence (
    run_id TEXT NOT NULL, request_id TEXT NOT NULL, stack TEXT NOT NULL,
    service TEXT NOT NULL, kind TEXT NOT NULL, seq INTEGER NOT NULL,
    internal INTEGER NOT NULL,           -- X-Evidence-Internal: true 로 들어왔는지(앱 전송은 1이어야 한다)
    body TEXT NOT NULL,
    PRIMARY KEY (run_id, request_id, stack, service, kind, seq))""")
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

    def _route(self):
        u = urlparse(self.path)
        return u.path.rstrip("/") or "/", {k: v[0] for k, v in parse_qs(u.query).items()}

    @staticmethod
    def _where(q, require):
        missing = [r for r in require if not q.get(r)]
        if missing:
            raise ValueError(f"{', '.join(missing)} required")
        conds, args = [], []
        for k, col in FILTERS.items():
            if q.get(k):
                conds.append(f"{col} = ?")
                args.append(q[k])
        return (" WHERE " + " AND ".join(conds)) if conds else "", args

    def do_POST(self):
        path, _ = self._route()
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
                             int(e.get("seq") or 0), internal, json.dumps(e, ensure_ascii=False)))
            with _lock:
                _db.executemany("INSERT OR REPLACE INTO evidence"
                                "(run_id, request_id, stack, service, kind, seq, internal, body) VALUES (?,?,?,?,?,?,?,?)",
                                rows)
            return self._send(201, {"stored": len(rows)})
        if path == "/runs":
            if not isinstance(payload, dict) or not payload.get("runId"):
                return self._send(400, {"error": "runId required"})
            with _lock:
                _db.execute("INSERT OR REPLACE INTO runs(run_id, body) VALUES (?,?)",
                            (payload["runId"], json.dumps(payload, ensure_ascii=False)))
            return self._send(201, {"runId": payload["runId"]})
        return self._send(404, {"error": "not found"})

    def do_GET(self):
        path, q = self._route()
        try:
            if path == "/health":
                return self._send(200, {"status": "ok"})
            if path == "/count":
                where, args = self._where(q, ["runId"])
                return self._send(200, {"count": _db.execute(f"SELECT count(*) FROM evidence{where}", args).fetchone()[0]})
            if path == "/exists":
                where, args = self._where(q, ["runId", "requestId", "stack"])
                n = _db.execute(f"SELECT count(*) FROM evidence{where}", args).fetchone()[0]
                return self._send(200 if n else 404, {"exists": n > 0, "count": n})
            if path == "/export":
                where, args = self._where(q, ["runId"])
                rows = _db.execute(f"SELECT body FROM evidence{where} ORDER BY stack, request_id, service, kind, seq",
                                   args).fetchall()
                return self._send(200, [json.loads(r[0]) for r in rows])
            if path.startswith("/runs/"):
                row = _db.execute("SELECT body FROM runs WHERE run_id = ?", (path[len("/runs/"):],)).fetchone()
                return self._send(200, json.loads(row[0])) if row else self._send(404, {"error": "no such run"})
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        return self._send(404, {"error": "not found"})

    def do_DELETE(self):
        path, _ = self._route()
        if path.startswith("/runs/"):
            run_id = path[len("/runs/"):]
            with _lock:
                n = _db.execute("DELETE FROM evidence WHERE run_id = ?", (run_id,)).rowcount
                _db.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
            return self._send(200, {"deleted": n})
        return self._send(404, {"error": "not found"})


if __name__ == "__main__":
    print(f"evidence-store v0 listening on :{PORT}, db={DB_PATH}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
