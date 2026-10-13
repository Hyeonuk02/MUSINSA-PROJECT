"""Phase 3.4 — Normalization v1.

Evidence 레코드 한 건을 판정용 정규형으로 바꾼다. 원문(Evidence)은 그대로 두고, 판정에 쓰는 형태만 만든다
("기록은 최대 해상도, 판정은 선언된 해상도"). 이 규칙은 엔진에만 있고 앱에는 없다.

축은 두 층이다(D18 확장, phase3-plan 3.4 구현 시 확정):
  기능 계약 축  response.status, response.body(+content-type), writeSet, externalCalls(method·path·status·requestBodyHash),
               events(발행)·event(소비), transactions outcome 순서열, error, consumeOutcome, hop 집합
  실행 특성 축  readCount·readFingerprints, callTree, transactions name, externalCalls.responseBodyHash

제외: timing, capturedAt, runId, version, request(요청 동일성은 verify_sameness가 확인),
      response.body·event payload의 "id" 키(DB auto id, 모든 깊이 — Phase 2 diff_v0와 동일)
"""
import json
import re

ALIAS = re.compile(r"\b[a-z]+\d+_\d+\b")
WHITESPACE = re.compile(r"\s+")
WRITE_TYPES = ("insert", "update", "delete")


def canonical(value) -> str:
    """키 정렬·공백 제거 JSON. 배열 순서는 유지."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


AUTO_ID_KEY = "id"


def strip_ids(value):
    """키 이름이 정확히 "id"인 필드를 모든 깊이에서 제거(DB auto id — Phase 2 diff_v0와 같은 유일한 제외 필드)."""
    if isinstance(value, dict):
        return {k: strip_ids(v) for k, v in value.items() if k != AUTO_ID_KEY}
    if isinstance(value, list):
        return [strip_ids(v) for v in value]
    return value


def parse_json(text):
    """JSON이면 파싱 결과, 아니면 None."""
    if text is None:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


# ---------------------------------------------------------------- SQL
def sql_fingerprint(sql: str) -> str:
    """소문자·공백 축약·Hibernate alias(o1_0류) → t. 바인딩 자리(?)는 그대로."""
    return ALIAS.sub("t", WHITESPACE.sub(" ", sql.lower()).strip())


def sql_type(fingerprint: str) -> str:
    return fingerprint.split(" ", 1)[0] if fingerprint else ""


def sql_tables(fingerprint: str) -> list[str]:
    kind = sql_type(fingerprint)
    if kind == "insert":
        names = re.findall(r"\binsert into (\w+)", fingerprint)
    elif kind == "update":
        names = re.findall(r"^update (\w+)", fingerprint)
    elif kind == "delete":
        names = re.findall(r"\bdelete from (\w+)", fingerprint)
    else:
        names = re.findall(r"\b(?:from|join) (\w+)", fingerprint)
    return sorted(set(names))


def statement(sql: str) -> dict:
    fp = sql_fingerprint(sql)
    return {"type": sql_type(fp), "tables": sql_tables(fp), "fingerprint": fp}


# ---------------------------------------------------------------- callTree
def clean_class(cls: str) -> str:
    """프록시·Kotlin·람다 흔적 제거. 같은 FQCN이면 Java·Kotlin이 같은 이름이 된다."""
    cls = cls.split("$$")[0]                  # $$SpringCGLIB$$0, $$Lambda...
    cls = re.sub(r"\$lambda.*$", "", cls)
    cls = cls.replace("$DefaultImpls", "")
    pkg, _, simple = cls.rpartition(".")
    if simple.endswith("Kt") and len(simple) > 2:
        simple = simple[:-2]
    return f"{pkg}.{simple}" if pkg else simple


def call_tree_roots(nodes: list[dict]) -> list[list[str]]:
    """depth 0마다 새 루트. 각 루트는 class.method 시퀀스(pre-order). 합성 메서드(access$·lambda$)는 뺀다."""
    roots: list[list[str]] = []
    for node in nodes:
        method = node["method"]
        if method.startswith("access$") or method.startswith("lambda$"):
            continue
        if node["depth"] == 0 or not roots:
            roots.append([])
        roots[-1].append(f"{clean_class(node['class'])}.{method}")
    return roots


# ---------------------------------------------------------------- 엔드포인트
class Endpoints:
    def __init__(self, table: list[dict]):
        self.http = [(e["id"], e["method"], re.compile(e["path"])) for e in table if "path" in e]
        self.topics = {e["topic"]: e["id"] for e in table if "topic" in e}

    def of(self, rec: dict) -> str:
        if rec.get("origin") == "kafka":
            return self.topics.get((rec.get("event") or {}).get("topic"), "unknown")
        req = rec.get("request") or {}
        for eid, method, pattern in self.http:
            if req.get("method") == method and pattern.match(req.get("path", "")):
                return eid
        return "unknown"


# ---------------------------------------------------------------- 레코드
def normalize(rec: dict, endpoints: Endpoints) -> dict:
    """판정용 정규형. 키는 축 이름."""
    stmts = [statement(s["sql"]) for s in rec["dbAccess"]["statements"]]
    writes = sorted([s["type"], t] for s in stmts if s["type"] in WRITE_TYPES for t in s["tables"])
    reads = [s["fingerprint"] for s in stmts if s["type"] == "select"]
    kafka = rec.get("origin") == "kafka"
    response = rec.get("response") or {}
    body_json = parse_json(response.get("body")) if not kafka else None

    n = {
        "endpoint": endpoints.of(rec),
        "origin": rec.get("origin", "http"),
        # 기능 계약 축
        "response.status": None if kafka else response.get("status"),
        "response.contentType": None if kafka else (response.get("headers") or {}).get("content-type"),
        "response.body": None if kafka else (strip_ids(body_json) if body_json is not None
                                              else {"$hash": response.get("bodyHash")}),
        "writeSet": writes,
        "externalCalls": [{k: c[k] for k in ("method", "host", "path", "status", "requestBodyHash")}
                          for c in rec.get("externalCalls", [])],
        "events": [{"topic": p["topic"], "key": p["key"],
                    "payload": _payload(p.get("payload"), p["payloadHash"]), "ack": p["ack"]}
                   for p in rec.get("events", {}).get("published", [])],
        "event": None if not kafka else {"topic": rec["event"]["topic"], "key": rec["event"]["key"],
                                          "payload": _payload(rec["event"].get("payload"), rec["event"]["payloadHash"])},
        "transactions.outcomes": [[t["phase"], t["outcome"]] for t in rec.get("transactions", [])],
        "error": rec.get("error"),
        "consumeOutcome": rec.get("consumeOutcome"),
        # 실행 특성 축
        "dbRead.count": len(reads),
        "dbRead.fingerprints": reads,
        "callTree": call_tree_roots(rec.get("callTree", {}).get("nodes", [])),
        "transactions.names": [t["name"] for t in rec.get("transactions", [])],
        "externalCalls.responseHash": [c["responseBodyHash"] for c in rec.get("externalCalls", [])],
        # 검사용 원자료(축 아님)
        "_publishSeqs": [p["seq"] for p in rec.get("events", {}).get("published", [])],
        "_commitBeginSeqs": [t["seq"] for t in rec.get("transactions", []) if t["phase"] == "COMMIT_BEGIN"],
        "_idempotencyKey": ((rec.get("request") or {}).get("headers") or {}).get("idempotency-key"),
        "_rawExternalCalls": rec.get("externalCalls", []),
        "_rawPublished": rec.get("events", {}).get("published", []),
        "_statements": stmts,
    }
    return n


def _payload(text, payload_hash):
    parsed = parse_json(text)
    return strip_ids(parsed) if parsed is not None else {"$hash": payload_hash}


FUNCTIONAL_AXES = ("response.status", "response.contentType", "response.body", "writeSet", "externalCalls",
                   "events", "event", "transactions.outcomes", "error", "consumeOutcome")
EXECUTION_AXES = ("dbRead.count", "dbRead.fingerprints", "callTree", "transactions.names", "externalCalls.responseHash")


# ---------------------------------------------------------------- JSON diff
def flatten(value, prefix="") -> dict:
    """리프 경로 → 값. 경로는 a.b[0].c. 빈 객체·배열도 리프로 남긴다."""
    out = {}
    if isinstance(value, dict) and value:
        for k in sorted(value):
            out.update(flatten(value[k], f"{prefix}.{k}" if prefix else k))
    elif isinstance(value, list) and value:
        for i, v in enumerate(value):
            out.update(flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix or "$"] = value
    return out


def json_diff(legacy, new) -> dict:
    """{added: [path], removed: [path], changed: [{path, from, to}]} — 리프 단위."""
    a, b = flatten(legacy), flatten(new)
    return {
        "added": sorted(set(b) - set(a)),
        "removed": sorted(set(a) - set(b)),
        "changed": [{"path": p, "from": a[p], "to": b[p]} for p in sorted(set(a) & set(b)) if a[p] != b[p]],
    }
