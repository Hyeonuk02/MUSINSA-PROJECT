"""engine 공용 — run 디렉터리 로딩과 입력 계약 검사.

입력 계약: run 디렉터리(runs/<runId>/)의 legacy.json·new.json 모든 레코드가 자기 schemaVersion의
스키마(docs/evidence-schema-v0.json / v1.json)를 통과하고, runId가 디렉터리 이름과, stack이 파일 이름과 일치한다.
v1은 추가로:
  - hopPath 형식(스키마) — 짝 키는 (replayRequestId, hopPath)
  - callTree depth 불변식: 첫 노드 depth 0, depth[i] <= depth[i-1] + 1 (call-graph.md 5절)
  - callTree seq: 1부터 1씩 증가(별도 카운터)
  - 타임라인 seq: dbAccess·externalCalls·events.published·transactions의 seq가 서로 겹치지 않고, 각 배열 안에서 증가
한 run 안에서 schemaVersion이 섞이면 위반.
엔진은 앱 코드·매니페스트를 import하지 않는다 — 계약은 스키마뿐이다(decision-log D12).
"""
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = {v: ROOT / "docs" / f"evidence-schema-{v}.json" for v in ("v0", "v1")}
STACKS = ("legacy", "new")
# 짝 키에 쓰는 hopPath. v0 레코드에는 hopPath가 없으므로 진입 홉 "0"으로 본다.
ENTRY_HOP = "0"


class Validators:
    def __init__(self):
        self.by_version = {
            v: Draft202012Validator(json.loads(p.read_text(encoding="utf-8")), format_checker=FormatChecker())
            for v, p in SCHEMAS.items()
        }

    def iter_errors(self, record: dict):
        validator = self.by_version.get(record.get("schemaVersion"))
        if validator is None:
            yield f"알 수 없는 schemaVersion: {record.get('schemaVersion')!r}"
            return
        for e in validator.iter_errors(record):
            yield e.message


def load_validator() -> Validators:
    return Validators()


def load_run(run_dir: Path) -> tuple[dict, dict[str, list[dict]]]:
    """(k6-summary, {stack: 레코드 목록}). 파일이 없거나 JSON이 아니면 OSError/JSONDecodeError."""
    summary = json.loads((run_dir / "k6-summary.json").read_text(encoding="utf-8"))
    records = {s: json.loads((run_dir / f"{s}.json").read_text(encoding="utf-8")) for s in STACKS}
    return summary, records


def hop_of(record: dict) -> str:
    return record.get("hopPath", ENTRY_HOP)


def key_of(record: dict) -> tuple[str, str]:
    """짝 키 (replayRequestId, hopPath)."""
    return record["replayRequestId"], hop_of(record)


def v1_violations(rec: dict) -> list[str]:
    """스키마로 표현하기 어려운 v1 불변식."""
    errors = []
    nodes = rec["callTree"]["nodes"]
    for i, node in enumerate(nodes):
        if node["seq"] != i + 1:
            errors.append(f"callTree seq가 1부터 1씩 증가하지 않음: nodes[{i}].seq={node['seq']}")
            break
        if i == 0 and node["depth"] != 0:
            errors.append(f"callTree 첫 노드 depth={node['depth']} (0이어야 함)")
            break
        if i > 0 and node["depth"] > nodes[i - 1]["depth"] + 1:
            errors.append(f"callTree depth 불변식 위반: nodes[{i}].depth={node['depth']} > nodes[{i - 1}].depth+1")
            break
    timeline = {
        "dbAccess.statements": [s["seq"] for s in rec["dbAccess"]["statements"]],
        "externalCalls": [c["seq"] for c in rec["externalCalls"]],
        "events.published": [p["seq"] for p in rec["events"]["published"]],
        "transactions": [t["seq"] for t in rec["transactions"]],
    }
    for name, seqs in timeline.items():
        if any(b <= a for a, b in zip(seqs, seqs[1:])):
            errors.append(f"타임라인 seq가 {name} 안에서 증가하지 않음: {seqs}")
    flat = [s for seqs in timeline.values() for s in seqs]
    if len(flat) != len(set(flat)):
        errors.append("타임라인 seq가 배열 사이에서 겹침")
    return errors


def contract_violations(run_dir: Path, records: dict[str, list[dict]], validators: Validators) -> list[str]:
    """입력 계약 위반 목록(레코드당 첫 위반 하나). 빈 목록이면 통과."""
    run_id = run_dir.name
    bad = []
    versions = set()
    for stack, recs in records.items():
        for i, rec in enumerate(recs):
            versions.add(rec.get("schemaVersion"))
            errors = list(validators.iter_errors(rec))
            if not errors:
                if rec["runId"] != run_id:
                    errors.append(f"runId={rec['runId']} (run 디렉터리 {run_id})")
                if rec["stack"] != stack:
                    errors.append(f"stack={rec['stack']} ({stack}.json)")
                if rec["schemaVersion"] == "v1":
                    errors += v1_violations(rec)
            if errors:
                bad.append(f"{stack}.json[{i}] {rec.get('replayRequestId', '?')}/{hop_of(rec)}: {errors[0]}")
    if len(versions) > 1:
        bad.append(f"한 run 안에 schemaVersion이 섞임: {sorted(str(v) for v in versions)}")
    return bad
