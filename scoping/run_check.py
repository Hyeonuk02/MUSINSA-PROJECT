#!/usr/bin/env python3
"""Phase 4.4 — 실제 Filter·Tag run을 docs/filter-expectations.json(사전 등록)과 대조한다. 판정 파일은 읽기만 한다.

Filter: 재생 pair 판정 == 전체 재생 같은 pair(100%), pair 집합 일치, 세션 검사 동일, run 범위 dbstate 기대, Undelivered·degraded 0,
        재생 수 = impact 선택 수, run-meta(scope·이미지·dirty).
Tag:    판정·Uncertain 수·재생 수가 전체 재생과 동일, F0를 뺀 비-SAME pair가 모두 inScope, 리뷰 순서에서 tier 순서 유지.

사용: .venv/bin/python scoping/run_check.py [--case F3-filter ...]   종료 코드 0 = 전부 기대와 일치
"""
import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from common import ROOT, load_verdict

EXPECT = ROOT / "docs" / "filter-expectations.json"
F0_PAIR = "R000047/0"


def pair_map(verdict: dict) -> dict:
    return {f"{p['replayRequestId']}/{p['hopPath']}": p for p in verdict["pairs"]}


def compare_pairs(run: dict, full: dict, sessions: set | None) -> list[str]:
    """run의 pair 판정과 전체 재생 판정을 비교. sessions가 있으면 전체 재생을 그 세션으로 제한."""
    got, want = pair_map(run), pair_map(full)
    if sessions is not None:
        want = {k: p for k, p in want.items() if p["sessionId"] in sessions}
    bad = []
    if set(got) != set(want):
        bad.append(f"pair 집합 다름: 전체 재생에만 {sorted(set(want) - set(got))}, run에만 {sorted(set(got) - set(want))}")
    diffs = {k: (want[k]["verdict"], got[k]["verdict"]) for k in set(got) & set(want) if got[k]["verdict"] != want[k]["verdict"]}
    if diffs:
        bad.append(f"판정 다름(전체→run): {dict(sorted(diffs.items()))}")
    return bad


def session_violations(verdict: dict, sessions: set | None) -> list:
    found = verdict["summary"]["sessionViolations"]
    return sorted((json.dumps(v, sort_keys=True) for v in found if sessions is None or v["session"] in sessions))


def check_common(case: dict, verdict: dict, run_dir: Path, full: dict, sessions: set | None, sent_want: set | None) -> list[str]:
    bad = compare_pairs(verdict, full, sessions)
    if session_violations(verdict, sessions) != session_violations(full, sessions):
        bad.append("세션 검사가 전체 재생과 다르다")
    want = case["verdicts"]
    if dict(Counter(p["verdict"] for p in verdict["pairs"])) != want:
        bad.append(f"판정 집계: 기대 {want} / 결과 {dict(Counter(p['verdict'] for p in verdict['pairs']))}")
    dbstate = {c["check"]: c["ok"] for c in verdict["runChecks"]}.get("dbstate_equal")
    if dbstate != case["dbstateEqual"]:
        bad.append(f"dbstate_equal: 기대 {case['dbstateEqual']} / 결과 {dbstate}")
    s = verdict["summary"]
    if any(s["undelivered"].values()) or s["degraded"]:
        bad.append(f"Undelivered {s['undelivered']}, degraded {s['degraded']}")
    summary = json.loads((run_dir / "k6-summary.json").read_text(encoding="utf-8"))
    if len(summary["sent"]) != case["replayedRequests"]:
        bad.append(f"재생 수: 기대 {case['replayedRequests']} / 결과 {len(summary['sent'])}")
    if sent_want is not None and set(summary["sent"]) != sent_want:
        bad.append("재생 요청 집합이 impact 선택과 다르다")
    if summary["vus"] != case["vus"]:
        bad.append(f"VU: 기대 {case['vus']} / 결과 {summary['vus']}")
    if summary["settleTimeouts"]:
        bad.append(f"settleTimeouts {summary['settleTimeouts']}")
    meta = json.loads((run_dir / "run-meta.json").read_text(encoding="utf-8"))
    if meta["git"]["dirty"]:
        bad.append("dirty run")
    if meta["images"]["order"]["new"]["image"] != case["image"]:
        bad.append(f"new order 이미지 {meta['images']['order']['new']['image']}")
    coupon = meta["images"]["coupon"]["new"]["image"]
    if coupon != case.get("couponImage", "coupon-app:phase3.3-base"):
        bad.append(f"new coupon 이미지 {coupon}")
    impact_sha = hashlib.sha256((ROOT / case["impact"]).read_bytes()).hexdigest()
    if meta.get("scope", {}).get("sha256") != impact_sha or meta.get("scope", {}).get("mode") != case["mode"]:
        bad.append(f"run-meta scope 불일치: {meta.get('scope')}")
    return bad


def check_tag(run_dir: Path) -> list[str]:
    tags = json.loads((run_dir / "tags.json").read_text(encoding="utf-8"))
    rows = {r["pair"]: r for r in tags["pairs"]}
    outside = [r["pair"] for r in tags["pairs"] if r["observedDiff"] and r["pair"] != F0_PAIR and not r["inScope"]]
    bad = [f"관측된 차이 pair가 inScope 밖: {outside}"] if outside else []
    tiers = [rows[k]["tier"] for k in tags["reviewOrder"]]
    if tiers != sorted(tiers) or set(tags["reviewOrder"]) != set(rows):
        bad.append("리뷰 순서가 tier 순이 아니다")
    return bad


def run_case(name: str, case: dict) -> tuple[int, list[str]]:
    impact = json.loads((ROOT / case["impact"]).read_text(encoding="utf-8"))
    filter_mode = case["mode"] == "filter"
    sessions = set(impact["selectedSessions"]) if filter_mode else None
    sent_want = set(impact["selectedRequests"]) if filter_mode else None
    lines, failures = [], 0
    for i in range(1, case["iterations"] + 1):
        run_dir = ROOT / "runs" / f"{case['runBase']}-{i}"
        verdict = load_verdict(run_dir)
        full = load_verdict(ROOT / "runs" / f"{case['fullRunBase']}-{i}")
        bad = check_common(case, verdict, run_dir, full, sessions, sent_want)
        if not filter_mode:
            bad += check_tag(run_dir)
        failures += bool(bad)
        lines.append(f"{run_dir.name}: pairs {len(verdict['pairs'])} {dict(Counter(p['verdict'] for p in verdict['pairs']))} " + ("기대 일치" if not bad else f"**불일치** {bad}"))
    return failures, lines


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Filter·Tag run 대조(Phase 4.4)")
    ap.add_argument("--case", action="append")
    args = ap.parse_args(argv)
    cases = json.loads(EXPECT.read_text(encoding="utf-8"))["cases"]
    total = 0
    for name, case in cases.items():
        if args.case and name not in args.case:
            continue
        failures, lines = run_case(name, case)
        total += failures
        print(f"== {name}")
        print("\n".join("   " + l for l in lines))
    print(f"불일치 run {total}건")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
