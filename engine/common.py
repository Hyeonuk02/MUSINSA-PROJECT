"""engine 공용 — run 디렉터리 로딩과 입력 계약 검사.

입력 계약: run 디렉터리(runs/<runId>/)의 legacy.json·new.json 모든 레코드가
docs/evidence-schema-v0.json을 통과하고, runId가 디렉터리 이름과, stack이 파일 이름과 일치한다.
엔진은 앱 코드·매니페스트를 import하지 않는다 — 계약은 이 스키마뿐이다(decision-log D12).
"""
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "docs" / "evidence-schema-v0.json"
STACKS = ("legacy", "new")


def load_validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")), format_checker=FormatChecker())


def load_run(run_dir: Path) -> tuple[dict, dict[str, list[dict]]]:
    """(k6-summary, {stack: 레코드 목록}). 파일이 없거나 JSON이 아니면 OSError/JSONDecodeError."""
    summary = json.loads((run_dir / "k6-summary.json").read_text(encoding="utf-8"))
    records = {s: json.loads((run_dir / f"{s}.json").read_text(encoding="utf-8")) for s in STACKS}
    return summary, records


def contract_violations(run_dir: Path, records: dict[str, list[dict]], validator: Draft202012Validator) -> list[str]:
    """입력 계약 위반 목록(레코드당 첫 위반 하나). 빈 목록이면 통과."""
    run_id = run_dir.name
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
    return bad
