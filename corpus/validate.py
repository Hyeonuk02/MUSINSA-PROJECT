#!/usr/bin/env python3
"""corpus 검증 — schema.json(구조) + 구조로 표현하기 어려운 규칙.

사용: .venv/bin/python corpus/validate.py [corpus/corpus-v2.json]   (version으로 v1/v2 규칙을 고른다)
      .venv/bin/python corpus/validate.py --self-test
의존: 루트 requirements.txt (jsonschema) — .venv/bin/pip install -r requirements.txt

검사 규칙
  1. schema.json 통과 (필수 필드, 형식)
  2. 세션 id·요청 id 전역 유일
  3. 생성 요청(POST /api/orders)만 body를 갖고, orderKey = ok-<자기 요청 id>
  4. path는 Order API 형태 중 하나이고 method와 맞는다
  5. 결제 요청은 Idempotency-Key = idem-<자기 요청 id>, 그 외 요청은 headers 없음
  6. path가 참조하는 orderKey는 같은 세션에서 앞서 생성된 것만.
     예외: expectMissing: true — 그 세션에서 만들지 않은 키 참조 허용.
     단 그 키는 corpus 어디서도 생성되지 않아야 한다(다른 세션 키를 "없는 키"로 쓰면 세션 독립이 깨짐)
  7. 문자열에 실행 시점 값으로 보이는 것(시각, UUID, 템플릿 치환자) 없음

v2 (corpus-v2, Phase 3.2) — schema-v2.json + 아래 규칙
  1. 세션 id·요청 id 전역 유일
  2. 경로: Order(create·get·pay·cancel)·Coupon(issue·get·use) 중 하나, method와 맞음. body는 create·issue·use에만
  3. 생성 키: 주문 orderKey = ok-<자기 id>, 쿠폰 couponKey = ck-<자기 id>
  4. 참조 키(path의 orderKey·couponKey, 주문 body의 couponKey, use body의 orderKey)는 같은 세션에서 앞서 생성된 것만.
     예외: expectMissing(그 키는 corpus 어디서도 생성되지 않아야 함), use body의 외부 주문 키 ok-ext-<자기 id>
  5. 결제 Idempotency-Key = idem-<id> 또는 idem-slow-<id>(F7 지연 세션 예약). <id>는 같은 세션의 결제 요청 id(자기 자신 또는 앞선 결제 — 멱등 재결제)
  6. settle: 쿠폰 주문 생성은 settle에 {hop 0.h1, service coupon, origin http}가 있어야 한다.
     결제(Phase 3.3): 같은 세션에서 그 주문의 첫 /pay는 settle에 {hop 0.e1, service coupon, origin kafka}가 있어야 하고(처음 PAID → order.paid 소비),
     두 번째 이후 /pay에는 0.e1 금지(재결제는 발행 없음). 그 외 요청에 settle 금지
  7. 흐름 유형(flow)마다 learn·eval 세션이 각각 1개 이상
  8. 실행 시점 값 없음

expectMissing의 의미는 이 스크립트에만 있다. k6와 engine은 무시한다.
종료 코드: 0 = 통과, 1 = 위반, 2 = 사용법/파일 오류

--self-test: 회귀 방지. corpus-v1·v2는 통과해야 하고, tests/invalid/·tests/invalid-v2/<태그>-<케이스>.json은
  모두 위반이어야 하며 위반 목록에 [<태그>] 규칙이 있어야 한다(엉뚱한 규칙에 걸려 통과한 척 하는 것 방지).
"""
import json
import re
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

HERE = Path(__file__).resolve().parent

ROUTES = [
    ("POST", re.compile(r"^/api/orders$"), "create"),
    ("GET", re.compile(r"^/api/orders/by-key/(?P<key>[^/]+)$"), "get"),
    ("POST", re.compile(r"^/api/orders/(?P<key>[^/]+)/pay$"), "pay"),
    ("POST", re.compile(r"^/api/orders/(?P<key>[^/]+)/cancel$"), "cancel"),
]

RUNTIME_VALUE_PATTERNS = [
    ("ISO 시각", re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")),
    ("UUID", re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")),
    ("템플릿 치환자", re.compile(r"\{\{|\$\{|__ENV|Date\.now|random", re.IGNORECASE)),
]


def route_of(method, path):
    for m, pattern, kind in ROUTES:
        match = pattern.match(path)
        if match and m == method:
            return kind, match.groupdict().get("key")
    return None, None


def strings_in(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from strings_in(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings_in(v)


def validate(corpus, schema):
    errors = []

    for e in sorted(Draft202012Validator(schema).iter_errors(corpus), key=lambda e: list(e.absolute_path)):
        loc = "/".join(str(p) for p in e.absolute_path) or "(root)"
        errors.append(f"[schema] {loc}: {e.message}")
    if errors:
        return errors, None  # 구조가 틀리면 아래 규칙 검사는 의미가 없다

    sessions = corpus["sessions"]
    created_anywhere = {}  # orderKey -> sessionId
    for s in sessions:
        for r in s["requests"]:
            if r["method"] == "POST" and r["path"] == "/api/orders":
                created_anywhere.setdefault(r["body"]["orderKey"], s["id"])

    seen_sessions, seen_requests = set(), set()
    stats = {"sessions": len(sessions), "requests": 0, "expectMissing": 0}

    for s in sessions:
        sid = s["id"]
        if sid in seen_sessions:
            errors.append(f"[id] 세션 id 중복: {sid}")
        seen_sessions.add(sid)
        created_here = set()

        for r in s["requests"]:
            rid = r["id"]
            where = f"{sid}/{rid}"
            stats["requests"] += 1
            if rid in seen_requests:
                errors.append(f"[id] 요청 id 중복: {rid}")
            seen_requests.add(rid)

            kind, key = route_of(r["method"], r["path"])
            if kind is None:
                errors.append(f"[path] {where}: 알 수 없는 method/path {r['method']} {r['path']}")
                continue

            if kind == "create":
                if "body" not in r:
                    errors.append(f"[body] {where}: 생성 요청에 body 없음")
                    continue
                key = r["body"]["orderKey"]
                if key != f"ok-{rid}":
                    errors.append(f"[orderKey] {where}: 생성 키는 ok-{rid} 이어야 함 (실제 {key})")
                if key in created_here or created_anywhere.get(key) != sid:
                    errors.append(f"[orderKey] {where}: {key} 중복 생성")
                created_here.add(key)
            elif "body" in r:
                errors.append(f"[body] {where}: 생성 요청이 아닌데 body 있음")

            headers = r.get("headers", {})
            if kind == "pay":
                if headers.get("Idempotency-Key") != f"idem-{rid}":
                    errors.append(f"[header] {where}: Idempotency-Key는 idem-{rid} 이어야 함 (실제 {headers.get('Idempotency-Key')})")
            elif headers:
                errors.append(f"[header] {where}: 결제 요청이 아닌데 headers 있음 {sorted(headers)}")

            if kind != "create":
                missing = r.get("expectMissing", False)
                if missing:
                    stats["expectMissing"] += 1
                    if key in created_here:
                        errors.append(f"[orderKey] {where}: expectMissing인데 {key}는 이 세션에서 생성됨")
                    elif key in created_anywhere:
                        errors.append(f"[orderKey] {where}: expectMissing 키 {key}가 다른 세션({created_anywhere[key]})에서 생성됨 — 세션 간 공유 상태")
                elif key not in created_here:
                    owner = created_anywhere.get(key)
                    if owner == sid:
                        why = "이 세션에서 아직 생성 전인 키(순서 오류)"
                    elif owner:
                        why = f"다른 세션({owner})의 키"
                    else:
                        why = "이 세션에서 앞서 생성되지 않은 키"
                    errors.append(f"[orderKey] {where}: {key}는 {why} (없는 키 조회라면 expectMissing: true)")
            elif r.get("expectMissing"):
                errors.append(f"[orderKey] {where}: 생성 요청에는 expectMissing을 둘 수 없음")

            for text in strings_in(r):
                for label, pattern in RUNTIME_VALUE_PATTERNS:
                    if pattern.search(text):
                        errors.append(f"[runtime] {where}: 실행 시점 값으로 보이는 문자열({label}): {text!r}")

    return errors, stats


V2_ROUTES = [
    ("POST", re.compile(r"^/api/orders$"), "order.create"),
    ("GET", re.compile(r"^/api/orders/by-key/(?P<key>[^/]+)$"), "order.get"),
    ("POST", re.compile(r"^/api/orders/(?P<key>[^/]+)/pay$"), "order.pay"),
    ("POST", re.compile(r"^/api/orders/(?P<key>[^/]+)/cancel$"), "order.cancel"),
    ("POST", re.compile(r"^/api/coupons$"), "coupon.issue"),
    ("GET", re.compile(r"^/api/coupons/by-key/(?P<key>[^/]+)$"), "coupon.get"),
    ("POST", re.compile(r"^/api/coupons/(?P<key>[^/]+)/use$"), "coupon.use"),
]
BODY_KINDS = {"order.create", "coupon.issue", "coupon.use"}
COUPON_SETTLE = {"hop": "0.h1", "service": "coupon", "origin": "http"}
PAID_SETTLE = {"hop": "0.e1", "service": "coupon", "origin": "kafka"}


def validate_v2(corpus, schema):
    errors = []
    for e in sorted(Draft202012Validator(schema).iter_errors(corpus), key=lambda e: list(e.absolute_path)):
        loc = "/".join(str(p) for p in e.absolute_path) or "(root)"
        errors.append(f"[schema] {loc}: {e.message}")
    if errors:
        return errors, None

    sessions = corpus["sessions"]
    created = {}  # key -> sessionId (주문·쿠폰 키 모두)
    for s in sessions:
        for r in s["requests"]:
            body = r.get("body") or {}
            if r["method"] == "POST" and r["path"] in ("/api/orders", "/api/coupons"):
                key = body.get("orderKey") if r["path"] == "/api/orders" else body.get("couponKey")
                if key in created and created[key] != s["id"]:
                    errors.append(f"[orderKey] {s['id']}/{r['id']}: 키 {key}가 여러 세션에서 생성됨")
                created.setdefault(key, s["id"])

    seen_s, seen_r = set(), set()
    stats = {"sessions": len(sessions), "requests": 0, "expectMissing": 0, "settle": 0}
    splits = {}
    for s in sessions:
        sid = s["id"]
        if sid in seen_s:
            errors.append(f"[id] 세션 id 중복: {sid}")
        seen_s.add(sid)
        splits.setdefault(s["flow"], set()).add(s["split"])
        made, pays, paid_keys = set(), set(), set()
        for r in s["requests"]:
            rid, where = r["id"], f"{sid}/{r['id']}"
            stats["requests"] += 1
            if rid in seen_r:
                errors.append(f"[id] 요청 id 중복: {rid}")
            seen_r.add(rid)
            kind, key = None, None
            for m, pattern, k in V2_ROUTES:
                match = pattern.match(r["path"])
                if match and m == r["method"]:
                    kind, key = k, match.groupdict().get("key")
                    break
            if kind is None:
                errors.append(f"[path] {where}: 알 수 없는 method/path {r['method']} {r['path']}")
                continue
            body = r.get("body")
            if (kind in BODY_KINDS) != (body is not None):
                errors.append(f"[body] {where}: {kind}에 body {'없음' if body is None else '있으면 안 됨'}")
                continue
            refs = []  # (참조 키, expectMissing 허용 여부)
            if kind == "order.create":
                if set(body) - {"orderKey", "items", "couponKey"} or "discountAmount" in body:
                    errors.append(f"[body] {where}: 주문 생성 body 형식이 아님")
                if body.get("orderKey") != f"ok-{rid}":
                    errors.append(f"[orderKey] {where}: 생성 키는 ok-{rid} 이어야 함 (실제 {body.get('orderKey')})")
                if "couponKey" in body:
                    refs.append(body["couponKey"])
                    if COUPON_SETTLE not in r.get("settle", []):
                        errors.append(f"[settle] {where}: 쿠폰 주문 생성은 settle에 {COUPON_SETTLE}가 필요")
            elif kind == "coupon.issue":
                if body.get("couponKey") != f"ck-{rid}":
                    errors.append(f"[orderKey] {where}: 쿠폰 키는 ck-{rid} 이어야 함 (실제 {body.get('couponKey')})")
            elif kind == "coupon.use":
                refs.append(key)
                order_key = body.get("orderKey")
                if order_key != f"ok-ext-{rid}" and not order_key.startswith("ok-ext-"):
                    refs.append(order_key)
                elif order_key.startswith("ok-ext-") and order_key not in {f"ok-ext-{x['id']}" for x in s["requests"]}:
                    errors.append(f"[orderKey] {where}: 외부 주문 키 {order_key}는 같은 세션의 요청 id에서 나와야 함")
            else:
                refs.append(key)
            if kind == "order.pay":
                has_paid_settle = PAID_SETTLE in r.get("settle", [])
                if key not in paid_keys and not has_paid_settle:
                    errors.append(f"[settle] {where}: 주문 {key}의 첫 /pay는 settle에 {PAID_SETTLE}가 필요")
                if key in paid_keys and has_paid_settle:
                    errors.append(f"[settle] {where}: 주문 {key}의 두 번째 이후 /pay에는 settle 0.e1 금지(재결제는 발행 없음)")
                paid_keys.add(key)
                if any(x != PAID_SETTLE for x in r.get("settle", [])):
                    errors.append(f"[settle] {where}: 결제 settle은 {PAID_SETTLE}만")
            elif r.get("settle") and not (kind == "order.create" and "couponKey" in (body or {})):
                errors.append(f"[settle] {where}: settle은 쿠폰 주문 생성과 첫 결제에만")
            if r.get("settle"):
                stats["settle"] += len(r["settle"])
            if kind == "order.pay":
                pays.add(rid)
                idem = (r.get("headers") or {}).get("Idempotency-Key", "")
                target = idem.removeprefix("idem-").removeprefix("slow-")
                if not idem.startswith("idem-") or target not in pays:
                    errors.append(f"[header] {where}: Idempotency-Key는 idem[-slow]-<이 세션의 결제 요청 id> (실제 {idem})")
            elif r.get("headers"):
                errors.append(f"[header] {where}: 결제 요청이 아닌데 headers 있음")
            missing_flag = r.get("expectMissing", False)
            if missing_flag:
                stats["expectMissing"] += 1
            for ref in refs:
                if ref in made:
                    if missing_flag:
                        errors.append(f"[orderKey] {where}: expectMissing인데 {ref}는 이 세션에서 생성됨")
                elif missing_flag:
                    if ref in created:
                        errors.append(f"[orderKey] {where}: expectMissing 키 {ref}가 다른 세션({created[ref]})에서 생성됨")
                else:
                    owner = created.get(ref)
                    why = ("이 세션에서 아직 생성 전인 키(순서 오류)" if owner == sid else
                           f"다른 세션({owner})의 키" if owner else "이 세션에서 앞서 생성되지 않은 키")
                    errors.append(f"[orderKey] {where}: {ref}는 {why} (없는 키 조회라면 expectMissing: true)")
            if kind == "order.create":
                made.add(body["orderKey"])
            elif kind == "coupon.issue":
                made.add(body["couponKey"])
            for text in strings_in(r):
                for label, pattern in RUNTIME_VALUE_PATTERNS:
                    if pattern.search(text):
                        errors.append(f"[runtime] {where}: 실행 시점 값으로 보이는 문자열({label}): {text!r}")
    for flow, got in sorted(splits.items()):
        if got != {"learn", "eval"}:
            errors.append(f"[split] flow={flow}: learn·eval 세션이 모두 있어야 함 (있음: {sorted(got)})")
    stats["flows"] = {f: sorted(v) for f, v in sorted(splits.items())}
    return errors, stats


def run_validate(corpus):
    """corpus version으로 스키마·규칙을 고른다."""
    if corpus.get("version") == "corpus-v2":
        return validate_v2(corpus, json.loads((HERE / "schema-v2.json").read_text(encoding="utf-8")))
    return validate(corpus, json.loads((HERE / "schema.json").read_text(encoding="utf-8")))


def self_test():
    results = []
    for valid in (HERE / "corpus-v1.json", HERE / "corpus-v2.json"):
        errors, _ = run_validate(json.loads(valid.read_text(encoding="utf-8")))
        results.append((valid.name, "PASS 기대", not errors, errors[:1]))

    fixtures = sorted((HERE / "tests" / "invalid").glob("*.json")) + sorted((HERE / "tests" / "invalid-v2").glob("*.json"))
    for path in fixtures:
        tag = path.stem.split("-", 1)[0]
        errors, _ = run_validate(json.loads(path.read_text(encoding="utf-8")))
        ok = any(e.startswith(f"[{tag}]") for e in errors)
        results.append((f"{path.parent.name}/{path.name}", f"[{tag}] 위반 기대", ok, errors[:1]))

    for name, expect, ok, first in results:
        print(f"  {'ok  ' if ok else 'FAIL'} {name:58} {expect}" + (f"  -> {first[0]}" if first else ""))
    failed = [r for r in results if not r[2]]
    print(f"self-test: {len(results) - len(failed)}/{len(results)} ok ({len(fixtures)} invalid fixtures)")
    if not fixtures:
        print("FAIL: tests/invalid에 fixture 없음")
        return 1
    return 1 if failed else 0


def main(argv):
    if argv[1:] == ["--self-test"]:
        return self_test()
    corpus_path = Path(argv[1]) if len(argv) > 1 else HERE / "corpus-v2.json"
    try:
        corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    errors, stats = run_validate(corpus)
    print(f"corpus: {corpus_path} (version={corpus.get('version')})")
    if errors:
        for e in errors:
            print(f"  FAIL {e}")
        print(f"FAIL ({len(errors)} violations)")
        return 1
    print("  " + " ".join(f"{k}={v}" for k, v in stats.items()))
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
