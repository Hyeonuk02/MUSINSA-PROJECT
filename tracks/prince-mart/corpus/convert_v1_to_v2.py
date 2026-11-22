#!/usr/bin/env python3
"""Prince Mart corpus v1.1 -> pm-corpus-v2 변환 (팀원 corpus v2 구조에 맞춘다).

사용: .venv/bin/python tracks/prince-mart/corpus/convert_v1_to_v2.py [--check]
  입력 corpus-v1.1.json(branch-park 베이스라인 corpus 그대로), 출력 corpus-v2.json. 결정론(같은 입력 -> 같은 바이트).
  --check: 파일을 쓰지 않고, 지금 corpus-v2.json이 변환 결과와 같은지만 본다(종료 코드 0 = 같음).

변환 규칙
  1. 세션 id S01 -> S001(팀원 형식 ^S[0-9]{3}$). 요청 id(R000001~)는 그대로
  2. 세션 userId -> 모든 요청의 X-User-Id 헤더. v1.1은 k6가 세션 값으로 넣었고, 팀원 run.js는 corpus의 headers만 붙인다.
     v1.1 요청이 X-User-Id를 덮어쓴 경우(R000017, 남의 주문 조회)는 그 값을 쓰고 asOtherUser: true로 표시한다
  3. capture, ${변수}는 그대로(run.js 선택 기능 capture가 치환한다). business key가 없어 서버가 만든 id를 다음 요청이 참조한다
  4. settle: /payments/verify에 {hop 0.e1, service order, origin kafka}. 결제 확정 뒤 Order consumer가 비동기로 상태를 바꾸므로
     다음 요청 전에 양쪽 스택의 소비 홉을 기다려야 한다. HTTP 하위 홉은 부모 응답 전에 끝나므로 settle에 넣지 않는다
     (barrier가 관측 host 폐포로 기다린다)
  5. expect(status, evidence), note, tags, description, flow, split은 그대로 둔다(run.js는 무시, 결과 대조용)
  6. 원본 파일의 sha256을 source에 남긴다
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "corpus-v1.1.json"
DST = HERE / "corpus-v2.json"

VERIFY_SETTLE = [{"hop": "0.e1", "service": "order", "origin": "kafka"}]


def convert(src: dict, src_sha: str) -> dict:
    sessions = []
    for s in src["sessions"]:
        sid = "S" + s["id"][1:].zfill(3)
        user_id = str(s["userId"])
        requests = []
        for r in s["requests"]:
            out = {"id": r["id"], "method": r["method"], "path": r["path"]}
            override = (r.get("headers") or {}).get("X-User-Id")
            out["headers"] = {"X-User-Id": override if override is not None else user_id}
            if override is not None and override != user_id:
                out["asOtherUser"] = True
            if "body" in r:
                out["body"] = r["body"]
            if "capture" in r:
                out["capture"] = r["capture"]
            if r["method"] == "POST" and r["path"].startswith("/payments/verify"):
                out["settle"] = VERIFY_SETTLE
            out["expect"] = r["expect"]
            if "note" in r:
                out["note"] = r["note"]
            requests.append(out)
        session = {"id": sid, "user": s["user"], "userId": s["userId"], "flow": s["flow"], "split": s["split"],
                   "tags": s.get("tags", []), "description": s.get("description", ""), "requests": requests}
        sessions.append(session)
    return {
        "version": "pm-corpus-v2",
        "description": "Prince Mart corpus v2. corpus-v1.1.json을 convert_v1_to_v2.py로 변환했다(세션 14, 요청 38, Legacy 버그 B1~B6 경로 포함). "
                       "구조는 팀원 corpus v2(세션 flow/split, 요청 settle)를 따르고, business key가 없어 capture와 ${변수} 치환을 쓴다.",
        "source": {"file": SRC.name, "version": src["version"], "sha256": src_sha},
        "sessions": sessions,
    }


def render(doc: dict) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    raw = SRC.read_bytes()
    text = render(convert(json.loads(raw), hashlib.sha256(raw).hexdigest()))
    if args.check:
        same = DST.exists() and DST.read_text(encoding="utf-8") == text
        print(f"{DST.name}: {'변환 결과와 같음' if same else '변환 결과와 다름'}")
        return 0 if same else 1
    DST.write_text(text, encoding="utf-8")
    doc = json.loads(text)
    print(f"{DST.name}: 세션 {len(doc['sessions'])}, 요청 {sum(len(s['requests']) for s in doc['sessions'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
