#!/usr/bin/env python3
"""Phase 2.8 — 응답·DB 접근 비교의 최소판 (A/A run용).

Phase 3 Normalization의 자리표시자다. 아래 규칙 외에는 넣지 않는다.

입력 계약(verify_sameness와 같은 schema·runId·stack 검사)을 먼저 통과해야 한다.
짝이 있는 요청(k6 sent 중 legacy·new 둘 다 있는 것)마다:

  response
    - status 일치
    - body가 둘 다 JSON이면: parse → 키 이름이 정확히 "id"인 필드를 모든 깊이에서 제거(DB auto id)
      → key 정렬, 배열 순서는 유지 → canonical JSON 직렬화 → 비교 (문자열 비교 금지)
      orderKey·status·amount·transactionId·createdAt은 유지해서 비교
    - body가 null(32KB 초과)이거나 JSON이 아니면 bodyHash 비교
  dbAccess
    - 문장 개수·순서 일치, truncated 일치
    - 각 sql의 정규화 문자열 일치: 소문자화 → 연속 공백 1개로 → Hibernate alias [a-z]+\\d+_\\d+ → _a_
      (원문 그대로 비교하지 않는다 — alias 번호는 생성 순서에 따라 바뀔 수 있다)
      이 정규화는 이 스크립트에만 둔다. 앱에는 넣지 않는다

  v1 레코드(Phase 3.1)는 추가로 — 짝 키는 (replayRequestId, hopPath)
    - origin=kafka 홉(Phase 3.3)은 response 대신 event 축: topic·key·consumeOutcome 일치 + payload를 response body와 같은 방식으로
      (JSON이면 id 제거·canonical, 아니면 payloadHash)
    - callTree: class.method 시퀀스(순서 유지)
    - externalCalls: 개수·순서·method·path·requestBodyHash·responseBodyHash
    - transactions: 개수와 (phase, outcome) 순서
    - events.published: 개수·순서·topic·payloadHash·ack
  run 단위(파일이 있을 때): dbstate-legacy.json == dbstate-new.json, WireMock journal(정규화: method·url·body 순서 목록) 동일

출력: run마다 diff 집합(축별 requestId[/hopPath] 목록)과 차이 난 요청의 정규화 후 legacy·new 값.
여러 --run이면 마지막에 diff 집합이 모든 run에서 같은지 PASS/FAIL.

사용: .venv/bin/python engine/diff_v0.py --run runs/<runId> [--run runs/<runId> ...]
종료 코드: 0 = 모든 run diff 없음, 1 = diff·계약 위반·집합 불일치, 2 = 사용법·파일 오류
"""
import argparse
import json
import re
import sys
from pathlib import Path

from common import ENTRY_HOP, contract_violations, key_of, load_run, load_validator

ALIAS = re.compile(r"[a-z]+\d+_\d+")
WHITESPACE = re.compile(r"\s+")


def strip_ids(value):
    """키 이름이 정확히 "id"인 필드를 모든 깊이에서 제거한다. 배열 순서는 그대로."""
    if isinstance(value, dict):
        return {k: strip_ids(v) for k, v in value.items() if k != "id"}
    if isinstance(value, list):
        return [strip_ids(v) for v in value]
    return value


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def normalized_body(response: dict) -> tuple[str, str]:
    """(비교 방식, 비교 값). JSON이면 canonical, 아니면 bodyHash."""
    body = response["body"]
    if body is not None:
        try:
            return "json", canonical(strip_ids(json.loads(body)))
        except json.JSONDecodeError:
            pass
    return "bodyHash", response["bodyHash"]


def normalize_sql(sql: str) -> str:
    return ALIAS.sub("_a_", WHITESPACE.sub(" ", sql.lower()))


def compare_response(legacy: dict, new: dict) -> list[str]:
    diffs = []
    if legacy["status"] != new["status"]:
        diffs.append(f"status: legacy={legacy['status']} new={new['status']}")
    (lk, lv), (nk, nv) = normalized_body(legacy), normalized_body(new)
    if lk != nk:
        # 한쪽만 JSON으로 읽힌 경우 — 같은 기준으로 bodyHash를 비교한다
        lk, lv, nk, nv = "bodyHash", legacy["bodyHash"], "bodyHash", new["bodyHash"]
    if lv != nv:
        diffs.append(f"body({lk}):\n            legacy={lv}\n            new   ={nv}")
    return diffs


def compare_event(legacy: dict, new: dict) -> list[str]:
    """origin=kafka 홉: 소비한 레코드와 소비 결과."""
    diffs = []
    le, ne = legacy["event"], new["event"]
    for field in ("topic", "key"):
        if le[field] != ne[field]:
            diffs.append(f"event.{field}: legacy={le[field]!r} new={ne[field]!r}")
    if legacy.get("consumeOutcome") != new.get("consumeOutcome"):
        diffs.append(f"consumeOutcome: legacy={legacy.get('consumeOutcome')} new={new.get('consumeOutcome')}")
    as_body = lambda e: {"body": e["payload"], "bodyHash": e["payloadHash"]}
    (lk, lv), (nk, nv) = normalized_body(as_body(le)), normalized_body(as_body(ne))
    if lk != nk:
        lk, lv, nk, nv = "payloadHash", le["payloadHash"], "payloadHash", ne["payloadHash"]
    if lv != nv:
        diffs.append(f"event.payload({lk}):\n            legacy={lv}\n            new   ={nv}")
    return diffs


def compare_db(legacy: dict, new: dict) -> list[str]:
    diffs = []
    if legacy["truncated"] != new["truncated"]:
        diffs.append(f"truncated: legacy={legacy['truncated']} new={new['truncated']}")
    ls = [normalize_sql(s["sql"]) for s in legacy["statements"]]
    ns = [normalize_sql(s["sql"]) for s in new["statements"]]
    if ls != ns:
        diffs.append(f"statements: legacy {len(ls)}건 / new {len(ns)}건")
        for i in range(max(len(ls), len(ns))):
            a = ls[i] if i < len(ls) else "(없음)"
            b = ns[i] if i < len(ns) else "(없음)"
            mark = "  " if a == b else "≠ "
            diffs.append(f"  {mark}#{i + 1} legacy: {a}")
            if a != b:
                diffs.append(f"     #{i + 1} new:    {b}")
    return diffs


def compare_sequences(name: str, legacy: list, new: list) -> list[str]:
    if legacy == new:
        return []
    diffs = [f"{name}: legacy {len(legacy)}건 / new {len(new)}건"]
    for i in range(max(len(legacy), len(new))):
        a = legacy[i] if i < len(legacy) else "(없음)"
        b = new[i] if i < len(new) else "(없음)"
        if a != b:
            diffs.append(f"  ≠ #{i + 1} legacy: {a}")
            diffs.append(f"     #{i + 1} new:    {b}")
    return diffs


def v1_axes(legacy: dict, new: dict) -> list[tuple[str, list[str]]]:
    def tree(r):
        return [f"{n['class']}.{n['method']}" for n in r["callTree"]["nodes"]]

    def calls(r):
        return [(c["method"], c["path"], c["requestBodyHash"], c["responseBodyHash"]) for c in r["externalCalls"]]

    def txs(r):
        return [(t["phase"], t["outcome"]) for t in r["transactions"]]

    def events(r):
        return [(p["topic"], p["payloadHash"], p["ack"]) for p in r["events"]["published"]]

    axes = [("callTree", compare_sequences("callTree", tree(legacy), tree(new)))]
    if legacy["callTree"]["truncated"] != new["callTree"]["truncated"]:
        axes[0][1].append(f"callTree.truncated: legacy={legacy['callTree']['truncated']} new={new['callTree']['truncated']}")
    axes += [("externalCalls", compare_sequences("externalCalls", calls(legacy), calls(new))),
             ("transactions", compare_sequences("transactions", txs(legacy), txs(new))),
             ("events", compare_sequences("events.published", events(legacy), events(new)))]
    return axes


def wiremock_requests(path: Path) -> list:
    journal = json.loads(path.read_text(encoding="utf-8"))
    rows = [(r["request"].get("method"), r["request"].get("url"), r["request"].get("body", ""))
            for r in journal.get("requests", [])]
    return sorted(rows)  # journal은 최신순으로 나온다 — 순서가 아니라 집합(중복 포함)으로 비교


def run_level(run_dir: Path) -> tuple[set[tuple[str, str]], list[str]]:
    diff_set, lines = set(), []
    pairs = (("dbstate", "dbstate-legacy.json", "dbstate-new.json", lambda p: json.loads(p.read_text(encoding="utf-8"))),
             ("wiremock", "wiremock-legacy.json", "wiremock-new.json", wiremock_requests))
    for name, lf, nf, load in pairs:
        lp, np_ = run_dir / lf, run_dir / nf
        if not (lp.exists() and np_.exists()):
            continue
        a, b = load(lp), load(np_)
        if a == b:
            lines.append(f"  PASS  {name:13} legacy == new")
        else:
            diff_set.add((name, "run"))
            lines.append(f"  DIFF  {name:13} legacy != new")
            lines.append(f"          legacy={json.dumps(a, ensure_ascii=False)[:600]}")
            lines.append(f"          new   ={json.dumps(b, ensure_ascii=False)[:600]}")
    return diff_set, lines


def diff_run(run_dir: Path, validator) -> tuple[bool, set[tuple[str, str]] | None, list[str]]:
    """(계약 통과, diff 집합 {(kind, requestId)}, 출력 줄)."""
    lines = []
    try:
        summary, records = load_run(run_dir)
    except (OSError, json.JSONDecodeError) as e:
        return False, None, [f"  FAIL  입력 파일을 읽을 수 없다: {e}"]
    bad = contract_violations(run_dir, records, validator)
    total = sum(len(v) for v in records.values())
    if bad:
        lines.append(f"  FAIL  입력 계약 (schema·runId·stack)  {total - len(bad)}/{total}")
        lines += [f"          {b}" for b in bad[:10]]
        return False, None, lines
    lines.append(f"  PASS  입력 계약 (schema·runId·stack)  {total}/{total}")

    by_key = {stack: {key_of(r): r for r in recs} for stack, recs in records.items()}
    sent = summary["sent"]
    entry_paired = [(i, ENTRY_HOP) for i in sent if (i, ENTRY_HOP) in by_key["legacy"] and (i, ENTRY_HOP) in by_key["new"]]
    child_paired = sorted(k for k in by_key["legacy"] if k[1] != ENTRY_HOP and k in by_key["new"] and k[0] in set(sent))
    paired = entry_paired + child_paired
    lines.append(f"        비교 대상: sent {len(sent)}건 중 진입 홉 짝 {len(entry_paired)}건 + 자식 홉 짝 {len(child_paired)}건"
                 + ("" if len(entry_paired) == len(sent) else " (짝 없는 요청은 verify_sameness의 Undelivered)"))

    diff_set = set()
    details = []
    kinds = ["response", "event", "dbAccess"]
    for key in paired:
        legacy, new = by_key["legacy"][key], by_key["new"][key]
        label = key[0] if key[1] == ENTRY_HOP else f"{key[0]}/{key[1]}"
        if legacy.get("origin") == "kafka" or new.get("origin") == "kafka":
            same_origin = legacy.get("origin") == new.get("origin")
            axes = [("event", compare_event(legacy, new) if same_origin
                     else [f"origin: legacy={legacy.get('origin')} new={new.get('origin')}"])]
        else:
            axes = [("response", compare_response(legacy["response"], new["response"]))]
        axes.append(("dbAccess", compare_db(legacy["dbAccess"], new["dbAccess"])))
        if legacy["schemaVersion"] == "v1":
            axes += v1_axes(legacy, new)
        for kind, found in axes:
            if kind not in kinds:
                kinds.append(kind)
            if found:
                diff_set.add((kind, label))
                where = (f"{legacy['request']['method']} {legacy['request']['path']}" if legacy.get("request")
                         else f"event {legacy['event']['topic']}" if legacy.get("event") else "")
                details.append(f"        [{kind}] {label} {where}")
                details += [f"          {d}" for d in found]
    for kind in kinds:
        ids = sorted(r for k, r in diff_set if k == kind)
        lines.append(f"  {'PASS' if not ids else 'DIFF'}  {kind:13} diff {len(ids)}건" + (f"  {' '.join(ids)}" if ids else ""))
    lines += details
    run_diffs, run_lines = run_level(run_dir)
    diff_set |= run_diffs
    lines += run_lines
    return True, diff_set, lines


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Legacy/New 최소 비교 (Phase 2.8, v1 축은 3.1)")
    parser.add_argument("--run", action="append", required=True, type=Path, help="runs/<runId> (여러 번 가능)")
    args = parser.parse_args(argv)
    try:
        validator = load_validator()
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: schema를 읽을 수 없다: {e}", file=sys.stderr)
        return 2

    results = []
    for run_dir in args.run:
        if not run_dir.is_dir():
            print(f"ERROR: run 디렉터리가 없다: {run_dir}", file=sys.stderr)
            return 2
        ok, diff_set, lines = diff_run(run_dir, validator)
        verdict = "FAIL" if not ok else ("DIFF" if diff_set else "PASS")
        print(f"== {run_dir}  {verdict}")
        print("\n".join(lines))
        results.append((run_dir, ok, diff_set))

    failed = any(not ok or diff_set for _, ok, diff_set in results)
    print("== 요약")
    for run_dir, ok, diff_set in results:
        shown = "계약 위반" if not ok else (", ".join(f"{k}:{r}" for k, r in sorted(diff_set)) or "∅")
        print(f"  {run_dir}  diff 집합 = {shown}")
    if len(results) > 1:
        sets = [frozenset(d) if ok else None for _, ok, d in results]
        same = all(s is not None for s in sets) and len(set(sets)) == 1
        print(f"  {'PASS' if same else 'FAIL'}  {len(results)}개 run의 diff 집합 동일" + ("" if same else " 아님"))
        failed |= not same
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
