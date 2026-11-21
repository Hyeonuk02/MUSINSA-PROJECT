#!/usr/bin/env python3
"""Prince Mart corpus 검증 — schema-v2.json(구조) + 구조로 표현하기 어려운 규칙. 팀원 corpus/validate.py v2와 같은 방식.

사용: .venv/bin/python tracks/prince-mart/corpus/validate.py [tracks/prince-mart/corpus/corpus-v2.json]
      .venv/bin/python tracks/prince-mart/corpus/validate.py --self-test
의존: 루트 requirements.txt (jsonschema)

규칙 (위반 메시지 앞의 [태그])
  [schema]   schema-v2.json 통과
  [unique]   세션 id, 요청 id 전역 유일
  [endpoint] path가 Prince Mart API 중 하나이고 method와 맞는다. body는 주문 생성과 쿠폰 검증에만, 그 둘에는 필수
  [user]     X-User-Id = 세션 userId. 예외는 asOtherUser: true(그때는 달라야 함). 세션마다 다른 사용자(세션 독립)
  [capture]  ${변수}는 같은 세션의 앞선 요청이 capture한 것만. 같은 세션에서 변수를 다시 정의하지 않는다. 세션 밖 값 참조 금지
  [settle]   결제 확정(/payments/verify)은 settle = [{hop 0.e1, service order, origin kafka}](결제 이벤트의 Order 소비 홉).
             그 외 요청에는 settle 금지(HTTP 하위 홉은 부모 응답 전에 끝나고 barrier가 관측 host 폐포로 기다린다)
  [coupon]   쿠폰 코드(주문 body, 쿠폰 검증 body, /coupons/use 쿼리)는 S0 시드(k8s/base/coupon-mysql-initdb/02-seed.sql)에 있고,
             한 코드는 한 세션만 쓴다(세션 독립 — B1 재사용이 다른 세션 결과에 섞이지 않게)
  [split]    흐름 유형(flow)마다 learn, eval 세션이 각각 1개 이상
  [expect]   결제 확정은 expect.evidence >= 2(진입 + 소비 홉)
  [runtime]  실행 시점 값 없음(ISO 시각, UUID). 치환자는 ${이름} 형식만
종료 코드: 0 = 통과, 1 = 위반, 2 = 사용법/파일 오류
--self-test: corpus-v2.json은 통과해야 하고, tests/invalid/<태그>-<케이스>.json은 모두 위반이고 위반 목록에 [<태그>]가 있어야 한다.
"""
import json
import re
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

HERE = Path(__file__).resolve().parent
SEED = HERE.parent / "k8s" / "base" / "coupon-mysql-initdb" / "02-seed.sql"
DEFAULT = HERE / "corpus-v2.json"

VAR = r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}"
ID_OR_VAR = rf"(?:[0-9]+|{VAR})"
# (이름, method, path 정규식, body 종류 또는 None)
ENDPOINTS = [
    ("order.place", "POST", r"^/orders/place$", "place"),
    ("order.get", "GET", rf"^/orders/order/{ID_OR_VAR}$", None),
    ("order.mine", "GET", r"^/orders/my-orders$", None),
    ("order.history", "GET", r"^/orders/history$", None),
    ("order.cancel", "PUT", rf"^/orders/{ID_OR_VAR}/cancel$", None),
    ("payment.verify", "POST", rf"^/payments/verify\?orderId=(?:order_[0-9]+|{VAR})&paymentId=pay-S[0-9]{{2}}$", None),
    ("coupon.use", "POST", rf"^/coupons/use\?orderId={ID_OR_VAR}&code=(S[0-9]{{2}}-[A-Z0-9]+)$", None),
    ("coupon.validate", "POST", r"^/coupons/validate$", "validate"),
    ("coupon.all", "GET", r"^/coupons/all$", None),
]
VERIFY_SETTLE = [{"hop": "0.e1", "service": "order", "origin": "kafka"}]
ISO_TIME = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
OTHER_PLACEHOLDER = re.compile(r"\{\{|\$\(|\$[A-Za-z_]|\$\{(?![A-Za-z_][A-Za-z0-9_]*\})")


def seed_codes() -> set[str]:
    return set(re.findall(r"\('(S[0-9]{2}-[A-Z0-9]+)'", SEED.read_text(encoding="utf-8")))


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)


def endpoint_of(req):
    for name, method, pattern, body in ENDPOINTS:
        m = re.match(pattern, req["path"])
        if m and req["method"] == method:
            return name, body, m
    return None, None, None


def validate(corpus: dict, schema: dict) -> list[str]:
    errors = []
    for e in sorted(Draft202012Validator(schema).iter_errors(corpus), key=lambda e: list(e.absolute_path)):
        loc = "/".join(str(p) for p in e.absolute_path) or "(root)"
        errors.append(f"[schema] {loc}: {e.message}")
    if errors:
        return errors  # 구조가 틀리면 아래 규칙은 의미가 없다

    seen_sessions, seen_requests, users = set(), set(), {}
    code_owner: dict[str, str] = {}
    codes = seed_codes()
    flows: dict[str, set[str]] = {}
    for s in corpus["sessions"]:
        sid = s["id"]
        if sid in seen_sessions:
            errors.append(f"[unique] 세션 id 중복: {sid}")
        seen_sessions.add(sid)
        flows.setdefault(s["flow"], set()).add(s["split"])
        if s["userId"] in users:
            errors.append(f"[user] {sid}: userId {s['userId']}를 {users[s['userId']]}도 쓴다(세션 독립)")
        users.setdefault(s["userId"], sid)
        captured: set[str] = set()
        for r in s["requests"]:
            rid = r["id"]
            where = f"{sid}/{rid}"
            if rid in seen_requests:
                errors.append(f"[unique] 요청 id 중복: {rid}")
            seen_requests.add(rid)

            name, body_kind, match = endpoint_of(r)
            if name is None:
                errors.append(f"[endpoint] {where}: 알 수 없는 경로 또는 method: {r['method']} {r['path']}")
            else:
                if body_kind is None and "body" in r:
                    errors.append(f"[endpoint] {where}: {name}에는 body가 없어야 한다")
                if body_kind is not None and "body" not in r:
                    errors.append(f"[endpoint] {where}: {name}에는 body가 필요하다")
                if body_kind == "place" and "body" in r and "code" in r["body"]:
                    errors.append(f"[endpoint] {where}: 주문 body가 아니다")
                if body_kind == "validate" and "body" in r and "currency" in r["body"]:
                    errors.append(f"[endpoint] {where}: 쿠폰 검증 body가 아니다")

            header_user = r["headers"]["X-User-Id"]
            if r.get("asOtherUser"):
                if header_user == str(s["userId"]):
                    errors.append(f"[user] {where}: asOtherUser인데 X-User-Id가 세션 사용자와 같다")
            elif header_user != str(s["userId"]):
                errors.append(f"[user] {where}: X-User-Id {header_user} != 세션 userId {s['userId']}")

            for text in [r["path"], *strings(r.get("body"))]:
                for var in re.findall(VAR, text):
                    if var not in captured:
                        errors.append(f"[capture] {where}: ${{{var}}}는 이 세션의 앞선 요청이 capture하지 않았다")
            for var in (r.get("capture") or {}):
                if var in captured:
                    errors.append(f"[capture] {where}: 변수 {var}를 다시 정의한다")
                captured.add(var)

            if name == "payment.verify":
                if r.get("settle") != VERIFY_SETTLE:
                    errors.append(f"[settle] {where}: 결제 확정은 settle {VERIFY_SETTLE}이어야 한다")
                if r["expect"]["evidence"] < 2:
                    errors.append(f"[expect] {where}: 결제 확정은 expect.evidence >= 2(진입 + 소비 홉)")
            elif "settle" in r:
                errors.append(f"[settle] {where}: 결제 확정 외 요청에는 settle을 두지 않는다")

            used = []
            if "body" in r:
                used += [r["body"][k] for k in ("couponCode", "code") if k in r["body"]]
            if name == "coupon.use" and match:
                used.append(match.group(match.lastindex))
            for code in used:
                if code not in codes:
                    errors.append(f"[coupon] {where}: 쿠폰 {code}가 S0 시드에 없다")
                owner = code_owner.setdefault(code, sid)
                if owner != sid:
                    errors.append(f"[coupon] {where}: 쿠폰 {code}를 {owner}도 쓴다(세션 독립)")

            for text in [r["path"], *strings(r.get("body")), *r["headers"].values()]:
                if ISO_TIME.search(text) or UUID.search(text):
                    errors.append(f"[runtime] {where}: 실행 시점 값으로 보이는 문자열: {text}")
                if OTHER_PLACEHOLDER.search(text):
                    errors.append(f"[runtime] {where}: ${{이름}} 외의 치환자: {text}")
    for flow, splits in sorted(flows.items()):
        missing = {"learn", "eval"} - splits
        if missing:
            errors.append(f"[split] flow {flow}: {', '.join(sorted(missing))} 세션이 없다")
    return errors


def load_schema() -> dict:
    return json.loads((HERE / "schema-v2.json").read_text(encoding="utf-8"))


def self_test() -> int:
    schema = load_schema()
    failed = 0
    errs = validate(json.loads(DEFAULT.read_text(encoding="utf-8")), schema)
    print(f"{'PASS' if not errs else 'FAIL'} {DEFAULT.name} (통과해야 함)")
    for e in errs:
        print("   ", e)
    failed += bool(errs)
    cases = sorted((HERE / "tests" / "invalid").glob("*.json"))
    for f in cases:
        tag = f.stem.split("-", 1)[0]
        errs = validate(json.loads(f.read_text(encoding="utf-8")), schema)
        ok = any(e.startswith(f"[{tag}]") for e in errs)
        print(f"{'PASS' if ok else 'FAIL'} tests/invalid/{f.name} (위반 [{tag}]이어야 함){'' if ok else ': ' + '; '.join(errs) or ' 위반 없음'}")
        failed += not ok
    print(f"self-test: {len(cases) + 1 - failed}/{len(cases) + 1} 통과")
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    if argv == ["--self-test"]:
        return self_test()
    if len(argv) > 1:
        print(__doc__, file=sys.stderr)
        return 2
    path = Path(argv[0]) if argv else DEFAULT
    try:
        corpus = json.loads(path.read_text(encoding="utf-8"))
        schema = load_schema()
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    errors = validate(corpus, schema)
    if errors:
        print(f"FAIL {path}: 위반 {len(errors)}건")
        for e in errors:
            print("  ", e)
        return 1
    n = sum(len(s["requests"]) for s in corpus["sessions"])
    print(f"PASS {path}: 세션 {len(corpus['sessions'])}, 요청 {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
