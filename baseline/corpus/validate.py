#!/usr/bin/env python3
"""corpus 검증 (Step 7-1, v10.1 §4.1 규칙)

  python3 baseline/corpus/validate.py [baseline/corpus/corpus-v1.json]

검사
- 구조: version, sessions[].{id, userId, requests[]}, requests[].{id, method, path, expect.status, expect.evidence}
- id 전역 유일(세션, 요청), 요청 id 형식 R000000
- 세션 독립성: userId가 세션마다 다르다. 쿠폰 코드(body.couponCode, path의 code=)가 세션 사이에 겹치지 않는다
- ${변수}는 같은 세션의 앞선 요청이 capture한 것만 쓴다
- 실행 시점 값 금지: 본문·경로에 Date/now/random/uuid 같은 토큰이 없다
"""
import json
import re
import sys

METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH"}
VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
RUNTIME = re.compile(r"(?i)\b(now|today|random|uuid|timestamp)\b|Date\.|Math\.random")


def main(path):
    c = json.load(open(path))
    errors = []
    err = errors.append
    if not c.get("version"):
        err("version 없음")
    seen_sessions, seen_requests, users, coupons = set(), set(), {}, {}
    total_ev = 0
    for s in c.get("sessions", []):
        sid = s.get("id")
        if not sid or sid in seen_sessions:
            err(f"세션 id 중복/누락: {sid}")
        seen_sessions.add(sid)
        uid = s.get("userId")
        if uid is None:
            err(f"{sid}: userId 없음")
        elif uid in users:
            err(f"{sid}: userId {uid}가 {users[uid]}와 겹침(세션 독립성)")
        users[uid] = sid
        captured = set()
        if not s.get("requests"):
            err(f"{sid}: 요청 없음")
        for r in s.get("requests", []):
            rid = r.get("id", "")
            if not re.fullmatch(r"R\d{6}", rid) or rid in seen_requests:
                err(f"{sid}: 요청 id 형식/중복: {rid}")
            seen_requests.add(rid)
            if r.get("method") not in METHODS:
                err(f"{rid}: method {r.get('method')}")
            if not str(r.get("path", "")).startswith("/"):
                err(f"{rid}: path")
            exp = r.get("expect") or {}
            if not isinstance(exp.get("status"), int) or not isinstance(exp.get("evidence"), int) or exp["evidence"] < 1:
                err(f"{rid}: expect.status/evidence")
            total_ev += exp.get("evidence", 0)
            text = r.get("path", "") + json.dumps(r.get("body", ""), ensure_ascii=False) + json.dumps(r.get("headers", {}))
            for v in VAR.findall(text):
                if v not in captured:
                    err(f"{rid}: ${{{v}}}를 앞선 요청이 capture하지 않음")
            if RUNTIME.search(text):
                err(f"{rid}: 실행 시점 값으로 보이는 토큰: {RUNTIME.search(text).group(0)}")
            codes = re.findall(r"code=([A-Za-z0-9-]+)", r.get("path", ""))
            if isinstance(r.get("body"), dict) and r["body"].get("couponCode"):
                codes.append(r["body"]["couponCode"])
            for code in codes:
                owner = coupons.setdefault(code, sid)
                if owner != sid:
                    err(f"{rid}: 쿠폰 {code}를 {owner}와 공유(세션 독립성)")
            captured |= set((r.get("capture") or {}).keys())
    print(json.dumps({"corpus": path, "version": c.get("version"), "sessions": len(seen_sessions),
                      "requests": len(seen_requests), "expectedEvidencePerStack": total_ev,
                      "errors": errors}, ensure_ascii=False, indent=1))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "baseline/corpus/corpus-v1.json"))
