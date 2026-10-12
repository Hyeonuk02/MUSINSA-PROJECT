#!/usr/bin/env python3
"""corpus 검증 — schema.json(구조) + 구조로 표현하기 어려운 규칙.

사용: .venv/bin/python corpus/validate.py [corpus/corpus-v1.json]
      .venv/bin/python corpus/validate.py --self-test
의존: corpus/requirements.txt (jsonschema)

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

expectMissing의 의미는 이 스크립트에만 있다. k6와 engine은 무시한다.
종료 코드: 0 = 통과, 1 = 위반, 2 = 사용법/파일 오류

--self-test: 회귀 방지. corpus-v1.json은 통과해야 하고, tests/invalid/<태그>-<케이스>.json은
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


def self_test(schema):
    results = []
    valid = HERE / "corpus-v1.json"
    errors, _ = validate(json.loads(valid.read_text(encoding="utf-8")), schema)
    results.append((valid.name, "PASS 기대", not errors, errors[:1]))

    fixtures = sorted((HERE / "tests" / "invalid").glob("*.json"))
    for path in fixtures:
        tag = path.stem.split("-", 1)[0]
        errors, _ = validate(json.loads(path.read_text(encoding="utf-8")), schema)
        ok = any(e.startswith(f"[{tag}]") for e in errors)
        results.append((f"invalid/{path.name}", f"[{tag}] 위반 기대", ok, errors[:1]))

    for name, expect, ok, first in results:
        print(f"  {'ok  ' if ok else 'FAIL'} {name:55} {expect}" + (f"  -> {first[0]}" if first else ""))
    failed = [r for r in results if not r[2]]
    print(f"self-test: {len(results) - len(failed)}/{len(results)} ok ({len(fixtures)} invalid fixtures)")
    if not fixtures:
        print("FAIL: tests/invalid에 fixture 없음")
        return 1
    return 1 if failed else 0


def main(argv):
    if argv[1:] == ["--self-test"]:
        return self_test(json.loads((HERE / "schema.json").read_text(encoding="utf-8")))
    corpus_path = Path(argv[1]) if len(argv) > 1 else HERE / "corpus-v1.json"
    try:
        corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
        schema = json.loads((HERE / "schema.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    errors, stats = validate(corpus, schema)
    print(f"corpus: {corpus_path} (version={corpus.get('version')})")
    if errors:
        for e in errors:
            print(f"  FAIL {e}")
        print(f"FAIL ({len(errors)} violations)")
        return 1
    print(f"  sessions={stats['sessions']} requests={stats['requests']} expectMissing={stats['expectMissing']}")
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
