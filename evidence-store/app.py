"""Evidence Store v0 — Phase 2.3

Evidence JSON을 받아 runId별 JSON Lines 파일에 저장하고, k6 완료 폴링·flush barrier·export에 응답한다.

- 본문은 해석하지 않는다. 키 (runId, replayRequestId, stack, hopPath) 네 필드와 필터용 service·origin만 읽고,
  받은 바이트를 그대로 저장·반환한다. (v1, Phase 3.2: 키에 hopPath — 한 요청이 여러 홉·서비스의 Evidence를 남긴다, D15)
  Evidence 형식의 소유자는 docs/evidence-schema-v0.json이다 (Store는 스키마를 검증하지 않는다).
- 같은 키를 다시 받으면 덮어쓴다(멱등). 파일은 append-only이고 읽을 때 last-wins.
  count는 중복 제거된 키 수, export는 키당 마지막 1건.
- 저장소: $EVIDENCE_DATA_DIR/<runId>/evidence.jsonl (Phase 2는 emptyDir)
  한 줄 = {"runId", "replayRequestId", "stack", "hopPath", "service", "origin", "raw": "<받은 본문 문자열 그대로>"}

엔드포인트
  POST   /evidence                              200 {"stored": true, "replaced": bool} / 400
  GET    /exists?runId=&requestId=&stack=&hopPath=   200 / 404 (hopPath 필수, 기본값 없음)
  GET    /count?runId=[&stack=][&service=][&origin=]   200 {"count": n}
  GET    /export?runId=[&stack=]                200 JSON 배열 (replayRequestId, hopPath, stack 순)
  DELETE /runs/{runId}                          200 {"deleted": n}
"""
import json
import os
import re
import shutil
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

DATA_DIR = Path(os.environ.get("EVIDENCE_DATA_DIR", "/data"))
RUN_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
KEY_FIELDS = ("runId", "replayRequestId", "stack", "hopPath")
FILE_NAME = "evidence.jsonl"

_lock = threading.Lock()
# runId -> {(replayRequestId, hopPath, stack): (raw, service, origin)}. 디스크 파일의 last-wins 뷰.
_index: dict[str, dict[tuple[str, str], str]] = {}


def _check_run_id(run_id: str) -> str:
    if not RUN_ID.match(run_id) or run_id in (".", ".."):
        raise HTTPException(400, f"invalid runId: {run_id!r}")
    return run_id


def _load_existing() -> None:
    """컨테이너 재시작 시 emptyDir에 남은 파일로 인덱스를 복원한다."""
    if not DATA_DIR.exists():
        return
    for path in DATA_DIR.glob(f"*/{FILE_NAME}"):
        records = _index.setdefault(path.parent.name, {})
        with path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    row = json.loads(line)
                    records[(row["replayRequestId"], row["hopPath"], row["stack"])] = (row["raw"], row.get("service"), row.get("origin"))


@asynccontextmanager
async def _lifespan(_app):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _lock:
        _load_existing()
    yield


app = FastAPI(title="evidence-store", version="v0", lifespan=_lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)


@app.exception_handler(RequestValidationError)
async def _bad_request(_request, exc):
    # 쿼리 파라미터 누락도 POST 키 누락과 같은 400으로 (FastAPI 기본은 422)
    return JSONResponse({"detail": exc.errors()}, status_code=400)


@app.post("/evidence")
async def post_evidence(request: Request):
    raw = (await request.body()).decode("utf-8", errors="strict")
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"body is not JSON: {e.msg}")
    if not isinstance(doc, dict):
        raise HTTPException(400, "body must be a JSON object")
    missing = [k for k in KEY_FIELDS if not isinstance(doc.get(k), str) or not doc.get(k)]
    if missing:
        raise HTTPException(400, f"missing key fields: {missing}")

    run_id = _check_run_id(doc["runId"])
    key = (doc["replayRequestId"], doc["hopPath"], doc["stack"])
    service, origin = doc.get("service"), doc.get("origin")
    line = json.dumps({"runId": run_id, "replayRequestId": key[0], "stack": key[2], "hopPath": key[1],
                       "service": service, "origin": origin, "raw": raw},
                      ensure_ascii=False) + "\n"
    with _lock:
        run_dir = DATA_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        with (run_dir / FILE_NAME).open("a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        records = _index.setdefault(run_id, {})
        replaced = key in records
        records[key] = (raw, service, origin)
    return {"stored": True, "replaced": replaced}


@app.get("/exists")
def exists(runId: str = Query(...), requestId: str = Query(...), stack: str = Query(...), hopPath: str = Query(...)):
    with _lock:
        found = (requestId, hopPath, stack) in _index.get(_check_run_id(runId), {})
    if not found:
        raise HTTPException(404, "not found")
    return {"exists": True}


@app.get("/count")
def count(runId: str = Query(...), stack: str | None = Query(None), service: str | None = Query(None),
          origin: str | None = Query(None)):
    with _lock:
        items = _index.get(_check_run_id(runId), {}).items()
        n = sum(1 for (_, _, s), (_, svc, org) in items
                if (stack is None or s == stack) and (service is None or svc == service)
                and (origin is None or org == origin))
    return {"count": n}


@app.get("/export")
def export(runId: str = Query(...), stack: str | None = Query(None)):
    with _lock:
        records = _index.get(_check_run_id(runId), {})
        raws = [records[k][0] for k in sorted(records) if stack is None or k[2] == stack]
    # 받은 본문을 그대로 이어 붙여 배열로 만든다 (재직렬화하지 않음)
    return Response("[" + ",".join(raws) + "]", media_type="application/json")


@app.delete("/runs/{runId}")
def delete_run(runId: str):
    with _lock:
        n = len(_index.pop(_check_run_id(runId), {}))
        shutil.rmtree(DATA_DIR / runId, ignore_errors=True)
    return {"deleted": n}
