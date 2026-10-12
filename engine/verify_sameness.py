#!/usr/bin/env python3
"""Phase 2.7 — 동일성·pairing 검증 (Phase 0 4.6 이관).

같은 요청이 Legacy와 New에 실제로 같은 모습으로 갔는지를 run 단위로 전건 대조한다.
클러스터에 접근하지 않는다. 입력은 run 디렉터리(runs/<runId>/)의 파일뿐이다.

  runs/<runId>/k6-summary.json  "보낸 것"의 기준(sent, status)
  runs/<runId>/legacy.json      Store export (stack=legacy)
  runs/<runId>/new.json         Store export (stack=new)

검사 (하나라도 실패하면 그 run은 FAIL)
  1. 입력 계약: 모든 레코드가 docs/evidence-schema-v0.json 통과, runId·stack이 run·파일과 일치. 실패 시 즉시 FAIL
  2. 중복 키 없음: 스택별 replayRequestId 유일
  3. pairing: Undelivered = sent − 레코드 id (스택별), Unexpected = 레코드 id − sent (스택별, 0이어야 함)
  4. request 동일성(짝이 있는 요청): method / path / query / EVIDENCE_HEADERS 5개 / bodyHash
  5. k6 ↔ legacy: k6-summary status[id] == legacy response.status (게이트웨이가 legacy로 라우팅했는지)
참고 통계(판정 아님): 미러 지연 = new − legacy 의 completedAt·arrivedAt 차이(ms)

dbAccess·response body는 비교하지 않는다(2.8).

사용: .venv/bin/python engine/verify_sameness.py --run runs/<runId> [--run runs/<runId> ...]
종료 코드: 0 = 모든 run PASS, 1 = 하나라도 FAIL, 2 = 사용법·파일 오류
"""
import argparse
import json
import re
import statistics
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "docs" / "evidence-schema-v0.json"
STACKS = ("legacy", "new")
# deploy/k8s/base/order.yaml의 EVIDENCE_HEADERS와 같은 목록(Evidence에는 소문자 키로 남는다).
# 엔진은 앱·매니페스트를 import하지 않는다 — 계약은 이 목록과 evidence-schema-v0.json이다.
EVIDENCE_HEADERS = ("x-replay-request-id", "x-run-id", "x-session-id", "idempotency-key", "content-type")
REQUEST_FIELDS = ("method", "path", "query") + tuple(f"headers.{h}" for h in EVIDENCE_HEADERS) + ("bodyHash",)
ISO = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?Z$")


class RunReport:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.lines: list[str] = []
        self.failed = False

    def check(self, name: str, passed: int, total: int, details: list[str] | None = None) -> None:
        ok = passed == total
        self.failed |= not ok
        self.lines.append(f"  {'PASS' if ok else 'FAIL'}  {name:34} {passed}/{total}")
        for d in details or []:
            self.lines.append(f"          {d}")

    def listing(self, name: str, items: list[str], must_be_empty: bool = True) -> None:
        ok = not items or not must_be_empty
        self.failed |= not ok
        self.lines.append(f"  {'PASS' if ok else 'FAIL'}  {name:34} {len(items)}" + (f"  {' '.join(items)}" if items else ""))

    def note(self, text: str) -> None:
        self.lines.append(f"        {text}")


def epoch_ns(text: str) -> int:
    """Java Instant.toString()(소수 0~9자리, Z)을 epoch ns로. datetime은 마이크로초까지라 직접 계산한다."""
    import datetime as dt
    m = ISO.match(text)
    if not m:
        raise ValueError(f"시각 형식이 아니다: {text}")
    base = dt.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc)
    fraction = (m.group(2) or "").ljust(9, "0")
    return int(base.timestamp()) * 1_000_000_000 + int(fraction)


def field(record: dict, path: str):
    if path.startswith("headers."):
        return record["request"]["headers"].get(path.split(".", 1)[1])
    return record["request"][path]


def stats_ms(values: list[float]) -> str:
    if not values:
        return "-"
    return f"min={min(values):.1f} median={statistics.median(values):.1f} max={max(values):.1f} (n={len(values)})"


def verify(run_dir: Path, validator: Draft202012Validator) -> RunReport:
    report = RunReport(run_dir)
    run_id = run_dir.name
    try:
        summary = json.loads((run_dir / "k6-summary.json").read_text(encoding="utf-8"))
        records = {s: json.loads((run_dir / f"{s}.json").read_text(encoding="utf-8")) for s in STACKS}
    except (OSError, json.JSONDecodeError) as e:
        report.failed = True
        report.lines.append(f"  FAIL  입력 파일을 읽을 수 없다: {e}")
        return report

    # 1. 입력 계약
    total = sum(len(v) for v in records.values())
    bad = []
    for stack, recs in records.items():
        for i, rec in enumerate(recs):
            errors = [e.message for e in validator.iter_errors(rec)]
            if not errors:
                if rec["runId"] != run_id:
                    errors.append(f"runId={rec['runId']} (run 디렉터리 {run_id})")
                if rec["stack"] != stack:
                    errors.append(f"stack={rec['stack']} ({stack}.json)")
            if errors:
                bad.append(f"{stack}.json[{i}] {rec.get('replayRequestId', '?')}: {errors[0]}")
    report.check("입력 계약 (schema·runId·stack)", total - len(bad), total, bad[:10])
    if bad:
        report.lines.append("        입력 계약 위반 — 이후 검사를 하지 않는다")
        return report

    sent = summary["sent"]
    sent_set = set(sent)
    by_id = {}
    for stack, recs in records.items():
        ids = [r["replayRequestId"] for r in recs]
        dups = sorted({i for i in ids if ids.count(i) > 1})
        report.listing(f"중복 키 ({stack})", dups)
        by_id[stack] = {r["replayRequestId"]: r for r in recs}

    # 3. pairing — 기준은 k6가 보낸 것(sent)
    report.lines.append(f"        sent {len(sent)}건 (k6-summary.json)")
    for stack in STACKS:
        report.listing(f"Undelivered ({stack})", [i for i in sent if i not in by_id[stack]])
    for stack in STACKS:
        report.listing(f"Unexpected ({stack})", sorted(set(by_id[stack]) - sent_set))

    paired = [i for i in sent if i in by_id["legacy"] and i in by_id["new"]]

    # 4. request 동일성
    for name in REQUEST_FIELDS:
        diffs = []
        for rid in paired:
            a, b = field(by_id["legacy"][rid], name), field(by_id["new"][rid], name)
            if a != b:
                diffs.append(f"{rid} request.{name}: legacy={a!r} new={b!r}")
        report.check(f"request.{name}", len(paired) - len(diffs), len(paired), diffs)
    extra = sorted({h for stack in STACKS for r in by_id[stack].values()
                    for h in r["request"]["headers"] if h not in EVIDENCE_HEADERS})
    if extra:
        report.note(f"참고: EVIDENCE_HEADERS 밖의 헤더 키 {extra}")

    # 5. k6 ↔ legacy
    status = summary.get("status", {})
    mismatches = []
    checked = [i for i in sent if i in by_id["legacy"]]
    for rid in checked:
        k6_status, legacy_status = status.get(rid), by_id["legacy"][rid]["response"]["status"]
        if k6_status != legacy_status:
            mismatches.append(f"{rid}: k6 status={k6_status} legacy response.status={legacy_status}")
    report.check("k6 status == legacy response.status", len(checked) - len(mismatches), len(checked), mismatches)

    # 참고 통계 — 미러 지연
    completed, arrived = [], []
    for rid in paired:
        lt, nt = by_id["legacy"][rid]["timing"], by_id["new"][rid]["timing"]
        completed.append((epoch_ns(nt["completedAt"]) - epoch_ns(lt["completedAt"])) / 1e6)
        arrived.append((epoch_ns(nt["arrivedAt"]) - epoch_ns(lt["arrivedAt"])) / 1e6)
    report.lines.append("  참고  미러 지연 (new − legacy, ms) — 같은 kind 노드라 pod 간 시계 차이는 무시한다")
    report.note(f"completedAt: {stats_ms(completed)}")
    report.note(f"arrivedAt:   {stats_ms(arrived)}")
    return report


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Legacy/New 요청 동일성·pairing 검증 (Phase 2.7)")
    parser.add_argument("--run", action="append", required=True, type=Path, help="runs/<runId> (여러 번 가능)")
    args = parser.parse_args(argv)

    try:
        validator = Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")), format_checker=FormatChecker())
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: schema를 읽을 수 없다: {e}", file=sys.stderr)
        return 2

    results = []
    for run_dir in args.run:
        if not run_dir.is_dir():
            print(f"ERROR: run 디렉터리가 없다: {run_dir}", file=sys.stderr)
            return 2
        report = verify(run_dir, validator)
        print(f"== {run_dir}  {'PASS' if not report.failed else 'FAIL'}")
        print("\n".join(report.lines))
        results.append((run_dir, report.failed))

    print("== 요약")
    for run_dir, failed in results:
        print(f"  {'FAIL' if failed else 'PASS'}  {run_dir}")
    return 1 if any(f for _, f in results) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
