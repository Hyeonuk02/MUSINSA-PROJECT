"""Phase 3.4 — 규칙 파일 로더와 매칭.

rules/contract.yaml   기능 계약 선언(엔드포인트 표·built-in 검사 켜기·파라미터)
rules/improvement.yaml 사전 승인 규칙
rules/learned/*.yaml   Human Review로 만든 규칙(review.py label)

규칙은 데이터다 — 실행 코드·임의 식을 넣지 않는다. match는 endpoint(id 또는 *) + diffKind 하나와 그 파라미터뿐.
match에 replayRequestId·sessionId·runId를 쓰면 로더가 거부한다(규칙은 특정 요청이 아니라 유형을 설명해야 한다).
learned 규칙은 실행 특성 축·response.body·events.payload의 diff에만 적용된다 — 기능 축 CV를 덮을 수 없다(판정 로직이 보장).
"""
import hashlib
import re
from pathlib import Path

import yaml

FORBIDDEN_MATCH_KEYS = {"replayRequestId", "sessionId", "runId"}
SCOPES = {"request", "session", "run"}
VERDICTS = {"same", "improvement", "violation"}
# diffKind → 허용 파라미터
DIFF_KINDS = {
    "response.addedFields": {"fields"},
    "response.removedFields": {"fields"},
    "response.valueChanged": {"path", "from", "to"},
    "dbRead.countDelta": {"from", "to"},
    "dbRead.fingerprintReplaced": {"from", "to"},
    "callTree.sequenceReplaced": {"from", "to"},
    "transactions.nameChanged": {"from", "to"},
    "events.payloadFieldsAdded": {"fields"},
}


class RuleError(ValueError):
    pass


class Rule:
    def __init__(self, raw: dict, source: str):
        self.raw, self.source = raw, source
        for key in ("id", "scope", "verdict", "reason", "provenance", "match"):
            if key not in raw:
                raise RuleError(f"{source}: 규칙에 {key}가 없다")
        if raw["scope"] not in SCOPES:
            raise RuleError(f"{source}: scope는 {sorted(SCOPES)} 중 하나 (실제 {raw['scope']})")
        if raw["verdict"] not in VERDICTS:
            raise RuleError(f"{source}: verdict는 {sorted(VERDICTS)} 중 하나 (실제 {raw['verdict']})")
        match = raw["match"]
        if not isinstance(match, dict):
            raise RuleError(f"{source}: match는 매핑이어야 한다")
        bad = FORBIDDEN_MATCH_KEYS & set(match)
        if bad:
            raise RuleError(f"{source}: match에 {sorted(bad)}를 쓸 수 없다 — 규칙은 특정 요청·세션·run이 아니라 유형을 설명해야 한다")
        kind = match.get("diffKind")
        if kind not in DIFF_KINDS:
            raise RuleError(f"{source}: diffKind는 {sorted(DIFF_KINDS)} 중 하나 (실제 {kind})")
        extra = set(match) - {"endpoint", "diffKind"} - DIFF_KINDS[kind]
        if extra:
            raise RuleError(f"{source}: {kind}에 쓸 수 없는 match 키 {sorted(extra)}")
        if "endpoint" not in match:
            raise RuleError(f"{source}: match.endpoint가 없다(id 또는 '*')")
        self.id, self.scope, self.verdict, self.match = raw["id"], raw["scope"], raw["verdict"], match

    def matches(self, item: dict) -> bool:
        """diff 항목({endpoint, diffKind, detail})이 이 규칙에 맞는지."""
        m = self.match
        if m["diffKind"] != item["diffKind"]:
            return False
        if m["endpoint"] not in ("*", item["endpoint"]):
            return False
        d = item["detail"]
        kind = m["diffKind"]
        if kind in ("response.addedFields", "response.removedFields", "events.payloadFieldsAdded"):
            return set(d["fields"]) <= set(m.get("fields", []))
        if kind == "response.valueChanged":
            return (m.get("path") == d["path"]
                    and re.fullmatch(str(m.get("from", ".*")), _s(d["from"])) is not None
                    and re.fullmatch(str(m.get("to", ".*")), _s(d["to"])) is not None)
        if kind == "dbRead.countDelta":
            return m.get("from") == d["from"] and m.get("to") == d["to"]
        if kind == "dbRead.fingerprintReplaced":
            return (_all_match(d["from"], m.get("from", [])) and _all_match(d["to"], m.get("to", [])))
        if kind in ("callTree.sequenceReplaced", "transactions.nameChanged"):
            return m.get("from") == d["from"] and m.get("to") == d["to"]
        return False


def _s(value) -> str:
    return "null" if value is None else str(value)


def _all_match(values: list[str], patterns: list[str]) -> bool:
    return all(any(re.fullmatch(p, v) for p in patterns) for v in values)


class RuleSet:
    def __init__(self, rules_dir: Path, contract: Path | None = None):
        """contract: 기능 계약 파일. 기본 rules_dir/contract.yaml. 같은 run을 다른 계약 선언으로 판정할 때(F8 maxSelects) 바꾼다."""
        self.dir = rules_dir
        self.contract_path = contract or rules_dir / "contract.yaml"
        self.contract = yaml.safe_load(self.contract_path.read_text(encoding="utf-8"))
        self.improvement = self._load(rules_dir / "improvement.yaml")
        self.learned = []
        for path in sorted((rules_dir / "learned").glob("*.yaml")):
            self.learned += self._load(path)
        ids = [r.id for r in self.improvement + self.learned]
        dup = sorted({i for i in ids if ids.count(i) > 1})
        if dup:
            raise RuleError(f"규칙 id 중복: {dup}")

    @staticmethod
    def _load(path: Path) -> list[Rule]:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        raws = doc.get("rules", []) if isinstance(doc, dict) and "rules" in doc else [doc]
        return [Rule(r, f"{path.name}#{i}") for i, r in enumerate(raws) if r]

    @property
    def rules(self) -> list[Rule]:
        return self.improvement + self.learned

    def check(self, name: str) -> dict | None:
        """built-in 검사 설정. 꺼져 있으면 None."""
        conf = (self.contract.get("checks") or {}).get(name) or {}
        return conf if conf.get("enabled") else None

    def sha256(self) -> dict:
        """규칙 파일별 sha256 — verdict.json에 기록(같은 규칙·같은 입력 → 같은 판정)."""
        files = [self.contract_path, self.dir / "improvement.yaml"] + sorted((self.dir / "learned").glob("*.yaml"))
        return {self._name(p): "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest() for p in files}

    def contract_name(self) -> str:
        return self._name(self.contract_path)

    def _name(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.dir.resolve()))
        except ValueError:
            return str(path)
