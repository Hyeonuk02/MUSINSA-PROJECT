#!/usr/bin/env python3
"""Phase 3.4 — 판정 엔진 v1. 클러스터에 접근하지 않는다(D12). 입력은 runs/<runId>/ 파일과 engine/rules/.

pair = (replayRequestId, hopPath). 우선순위 Contract Violation > Uncertain > Improvement > SAME.
  1. 모든 축 SAME → SAME
  2. built-in Contract 검사(rules/contract.yaml에서 켜기·파라미터) 하나라도 위반 → CV(위반 목록)
  3. 남은 diff 항목이 모두 규칙(improvement.yaml 사전 승인 + learned)으로 설명되면 Improvement(하나라도 improvement 규칙)
     또는 SAME(전부 same 규칙, appliedRules 표시)
  4. 그 외 Uncertain
규칙이 덮을 수 있는 diff는 실행 특성 축(dbRead·callTree·transactions name)·response.body·events.payload뿐이다.
status 불일치는 무조건 CV. Undelivered·degraded는 판정이 아니라 지표.

arm(3.7 측정용): B0 = 휘발 필드를 뺀 원문 동일성 / B1 = Normalization만(response status·body + dbAccess fingerprint·횟수)
/ C = 전체(기본). B0·B1은 SAME/DIFF만.

사용: .venv/bin/python engine/verdict.py --run runs/<runId> [--arm C] [--rules engine/rules] [--out <file>]
      기본 출력 runs/<runId>/verdict.json (arm B0·B1은 verdict-<arm>.json)
"""
import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import normalize as nz
from common import ROOT, STACKS, contract_violations, key_of, load_run, load_validator
from ruleset import RuleSet

ENGINE_VERSION = "engine-v1 (phase3.4)"
RULE_COVERABLE = {"response.addedFields", "response.removedFields", "response.valueChanged", "events.payloadFieldsAdded",
                  "dbRead.countDelta", "dbRead.fingerprintReplaced", "callTree.sequenceReplaced",
                  "transactions.nameChanged"}
VOLATILE = {"timing", "capturedAt", "runId", "version", "stack"}


def uid_of(item: dict) -> str:
    """리뷰 항목 식별자 — endpoint + axis + diffKind + 정규화 상세. 특정 요청 값(rid·session)은 들어가지 않는다."""
    basis = {k: item[k] for k in ("endpoint", "axis", "diffKind")} | {"detail": item["detail"]}
    return hashlib.sha256(nz.canonical(basis).encode("utf-8")).hexdigest()[:12]


def item(endpoint, axis, kind, detail) -> dict:
    it = {"endpoint": endpoint, "axis": axis, "diffKind": kind, "detail": detail}
    it["uid"] = uid_of(it)
    return it


def parent_hop(hop: str) -> str | None:
    return hop.rsplit(".", 1)[0] if "." in hop else None


# ---------------------------------------------------------------- 입력
def load_splits(run_dir: Path) -> dict:
    """세션 → split. run 디렉터리의 corpus.json(fixture)이 있으면 그것, 없으면 run-meta의 corpus 경로."""
    local = run_dir / "corpus.json"
    if local.exists():
        corpus = json.loads(local.read_text(encoding="utf-8"))
    else:
        meta = json.loads((run_dir / "run-meta.json").read_text(encoding="utf-8"))
        corpus = json.loads((ROOT / meta["corpus"]["path"]).read_text(encoding="utf-8"))
    order = {r["id"]: i for s in corpus["sessions"] for i, r in enumerate(s["requests"])}
    return {s["id"]: s.get("split") for s in corpus["sessions"]}, order


# ---------------------------------------------------------------- 축별 diff
def body_items(endpoint: str, legacy, new, axis_prefix: str) -> list[dict]:
    """JSON 본문 diff → addedFields / removedFields / valueChanged 항목. events payload면 payloadFieldsAdded만 규칙 대상."""
    d = nz.json_diff(legacy, new)
    out = []
    if axis_prefix == "response":
        if d["added"]:
            out.append(item(endpoint, "response.body", "response.addedFields", {"fields": d["added"]}))
        if d["removed"]:
            out.append(item(endpoint, "response.body", "response.removedFields", {"fields": d["removed"]}))
        for c in d["changed"]:
            out.append(item(endpoint, "response.body", "response.valueChanged", c))
    else:
        if d["added"]:
            out.append(item(endpoint, axis_prefix, "events.payloadFieldsAdded", {"fields": d["added"]}))
        if d["removed"]:
            out.append(item(endpoint, axis_prefix, "events.payloadFieldsRemoved", {"fields": d["removed"]}))
        for c in d["changed"]:
            out.append(item(endpoint, axis_prefix, "events.payloadValueChanged", c))
    return out


def execution_items(endpoint: str, L: dict, N: dict) -> list[dict]:
    out = []
    if L["dbRead.count"] != N["dbRead.count"]:
        out.append(item(endpoint, "dbRead", "dbRead.countDelta",
                        {"from": L["dbRead.count"], "to": N["dbRead.count"]}))
    elif L["dbRead.fingerprints"] != N["dbRead.fingerprints"]:
        # 횟수가 같으면 바뀐 fingerprint만(multiset 차). 집합이 같고 순서만 다르면 전체 순서열을 from/to로
        a, b = Counter(L["dbRead.fingerprints"]), Counter(N["dbRead.fingerprints"])
        removed, added = sorted((a - b).elements()), sorted((b - a).elements())
        out.append(item(endpoint, "dbRead", "dbRead.fingerprintReplaced", {"from": removed, "to": added} if (removed or added)
                        else {"from": L["dbRead.fingerprints"], "to": N["dbRead.fingerprints"]}))
    if L["callTree"] != N["callTree"]:
        out.append(item(endpoint, "callTree", "callTree.sequenceReplaced", {"from": L["callTree"], "to": N["callTree"]}))
    if L["transactions.names"] != N["transactions.names"]:
        out.append(item(endpoint, "transactions.names", "transactions.nameChanged",
                        {"from": L["transactions.names"], "to": N["transactions.names"]}))
    if L["externalCalls.responseHash"] != N["externalCalls.responseHash"]:
        out.append(item(endpoint, "externalCalls.responseHash", "externalCalls.responseHashChanged",
                        {"from": L["externalCalls.responseHash"], "to": N["externalCalls.responseHash"]}))
    return out


def events_compare(endpoint: str, L: list, N: list, axis: str) -> tuple[list[str], list[dict]]:
    """발행 이벤트 목록 비교 → (CV 사유, payload diff 항목). topic·key·ack·개수는 CV, payload는 항목으로."""
    violations, items = [], []
    if len(L) != len(N):
        violations.append(f"{axis}: 개수 legacy {len(L)} / new {len(N)}")
    for i, (a, b) in enumerate(zip(L, N)):
        for f in ("topic", "key", "ack"):
            if a[f] != b[f]:
                violations.append(f"{axis}[{i}].{f}: legacy={a[f]!r} new={b[f]!r}")
        if a["payload"] != b["payload"]:
            items += body_items(endpoint, a["payload"], b["payload"], f"{axis}[{i}].payload")
    return violations, items


# ---------------------------------------------------------------- 판정
class Judge:
    def __init__(self, run_dir: Path, rules: RuleSet):
        self.run_dir, self.rules = run_dir, rules
        summary, records = load_run(run_dir)
        bad = contract_violations(run_dir, records, load_validator())
        if bad:
            raise ValueError("입력 계약 위반: " + "; ".join(bad[:5]))
        self.summary, self.records = summary, records
        self.splits, self.req_order = load_splits(run_dir)
        self.endpoints = nz.Endpoints(rules.contract["endpoints"])
        obs = rules.contract.get("observed", {})
        self.observed_hosts, self.observed_topics = set(obs.get("hosts", [])), set(obs.get("topics", []))
        self.by_key = {s: {key_of(r): r for r in recs} for s, recs in records.items()}
        self.norm = {s: {k: nz.normalize(r, self.endpoints) for k, r in m.items()} for s, m in self.by_key.items()}
        self.sent = summary["sent"]
        sent_set = set(self.sent)
        self.pairs = sorted(k for k in self.by_key["legacy"] if k in self.by_key["new"] and k[0] in sent_set)

    # ---- 지표
    def delivery(self) -> dict:
        undelivered = {s: sorted(r for r in self.sent if (r, "0") not in self.by_key[s]) for s in STACKS}
        return {"undelivered": undelivered,
                "degraded": [{"session": d["session"], "skipped": d["skipped"]} for d in self.summary.get("degraded", [])]}

    # ---- arm B0 / B1
    def judge_simple(self, arm: str) -> list[dict]:
        out = []
        for key in self.pairs:
            lr, nr = self.by_key["legacy"][key], self.by_key["new"][key]
            if arm == "B0":
                same = nz.canonical(_strip(lr)) == nz.canonical(_strip(nr))
            else:
                L, N = self.norm["legacy"][key], self.norm["new"][key]
                axes = ("response.status", "response.body", "dbRead.count", "dbRead.fingerprints")
                same = all(L[a] == N[a] for a in axes) and \
                    [s["fingerprint"] for s in L["_statements"]] == [s["fingerprint"] for s in N["_statements"]]
            out.append(self._pair_head(key) | {"verdict": "SAME" if same else "DIFF"})
        return out

    def _pair_head(self, key) -> dict:
        rec = self.by_key["legacy"][key]
        return {"replayRequestId": key[0], "hopPath": key[1], "sessionId": rec["sessionId"],
                "split": self.splits.get(rec["sessionId"]), "endpoint": self.norm["legacy"][key]["endpoint"]}

    # ---- arm C
    def judge_full(self) -> tuple[list[dict], list[dict]]:
        pv = {key: [] for key in self.pairs}        # CV 사유
        pitems = {key: [] for key in self.pairs}    # 규칙 대상·Uncertain 후보 항목
        pwarn = defaultdict(list)
        chk = self.rules.check

        for key in self.pairs:
            L, N = self.norm["legacy"][key], self.norm["new"][key]
            ep = L["endpoint"]
            v, items = pv[key], pitems[key]
            # 기능 축
            if L["origin"] != N["origin"]:
                v.append(f"origin: legacy={L['origin']} new={N['origin']}")
            if chk("response_status_equal") and L["response.status"] != N["response.status"]:
                v.append(f"response.status: legacy={L['response.status']} new={N['response.status']}")
            if L["response.contentType"] != N["response.contentType"] and chk("response_body_compatible"):
                v.append(f"response.content-type: legacy={L['response.contentType']!r} new={N['response.contentType']!r}")
            if L["response.body"] != N["response.body"]:
                items += body_items(ep, L["response.body"], N["response.body"], "response")
            if chk("write_set_equal") and L["writeSet"] != N["writeSet"]:
                v.append(f"writeSet: legacy={L['writeSet']} new={N['writeSet']}")
            if chk("external_calls_equal") and L["externalCalls"] != N["externalCalls"]:
                v.append(f"externalCalls: legacy={_short(L['externalCalls'])} new={_short(N['externalCalls'])}")
            if chk("events_equal"):
                ev, evitems = events_compare(ep, L["events"], N["events"], "events.published")
                v += ev
                items += evitems
                v += [f"events.published[{i}].ack={p['ack']} (new)" for i, p in enumerate(N["events"]) if p["ack"] != "ok"]
                if (L["event"] is None) != (N["event"] is None):
                    v.append("event: 한쪽에만 있음")
                elif L["event"] is not None:
                    ev, evitems = events_compare(ep, [L["event"] | {"ack": None}], [N["event"] | {"ack": None}], "event")
                    v += ev
                    items += evitems
            if chk("tx_outcome_sequence_equal") and L["transactions.outcomes"] != N["transactions.outcomes"]:
                v.append(f"transactions.outcomes: legacy={L['transactions.outcomes']} new={N['transactions.outcomes']}")
            if chk("error_equal") and L["error"] != N["error"]:
                v.append(f"error: legacy={L['error']} new={N['error']}")
            if chk("consume_outcome_equal") and L["consumeOutcome"] != N["consumeOutcome"]:
                v.append(f"consumeOutcome: legacy={L['consumeOutcome']} new={N['consumeOutcome']}")
            if chk("publish_after_commit_begin") and N["_commitBeginSeqs"]:
                first = min(N["_commitBeginSeqs"])
                early = [s for s in N["_publishSeqs"] if s <= first]
                if early:
                    v.append(f"publish_after_commit_begin: publish.seq {early} <= COMMIT_BEGIN.seq {first} (new)")
            conf = chk("max_selects")
            if conf and ep in (conf.get("endpoints") or {}):
                limit = conf["endpoints"][ep]
                if N["dbRead.count"] > limit:
                    v.append(f"max_selects[{ep}]: new readCount {N['dbRead.count']} > {limit}")
                if L["dbRead.count"] > limit:
                    pwarn[key].append(f"max_selects[{ep}]: legacy readCount {L['dbRead.count']} > {limit} — 선언 확인 필요")
            # 실행 특성 축
            items += execution_items(ep, L, N)

        # hop 집합 (요청 범위, 부모 pair에 붙인다)
        if chk("hop_set_equal"):
            hops = {s: defaultdict(set) for s in STACKS}
            for s in STACKS:
                for rid, hop in self.by_key[s]:
                    if parent_hop(hop) is not None:
                        hops[s][(rid, parent_hop(hop))].add(hop)
            for key in self.pairs:
                a, b = hops["legacy"].get(key, set()), hops["new"].get(key, set())
                if a != b:
                    pv[key].append(f"hop_set: legacy만 {sorted(a - b)} / new만 {sorted(b - a)}")

        self._session_checks(pv)

        # 규칙 적용 → 4분류
        results = []
        for key in self.pairs:
            violations, applied, remaining = list(pv[key]), [], []
            for it in pitems[key]:
                rule = next((r for r in self.rules.rules if it["diffKind"] in RULE_COVERABLE and r.matches(it)), None)
                if rule is None:
                    remaining.append(it)
                    continue
                applied.append({"rule": rule.id, "verdict": rule.verdict, "uid": it["uid"]})
                if rule.verdict == "violation":
                    violations.append(f"rule {rule.id}: {it['diffKind']} {nz.canonical(it['detail'])[:160]}")
            # response_body_compatible / events payload: 규칙이 설명하지 않은 값 변경·삭제는 CV
            for it in list(remaining):
                if it["diffKind"] in ("response.removedFields", "response.valueChanged") and self.rules.check("response_body_compatible"):
                    violations.append(f"response_body_compatible: {it['diffKind']} {nz.canonical(it['detail'])[:200]}")
                    remaining.remove(it)
                elif it["diffKind"] in ("events.payloadFieldsRemoved", "events.payloadValueChanged") and self.rules.check("events_equal"):
                    violations.append(f"events_equal: {it['axis']} {it['diffKind']} {nz.canonical(it['detail'])[:200]}")
                    remaining.remove(it)
            if violations:
                verdict = "CONTRACT_VIOLATION"
            elif remaining:
                verdict = "UNCERTAIN"
            elif any(a["verdict"] == "improvement" for a in applied):
                verdict = "IMPROVEMENT"
            else:
                verdict = "SAME"
            results.append(self._pair_head(key) | {
                "verdict": verdict, "violations": violations, "appliedRules": applied,
                "uncertain": [{"uid": it["uid"], "axis": it["axis"], "diffKind": it["diffKind"], "detail": it["detail"]}
                              for it in remaining],
                "warnings": pwarn.get(key, [])})
        return results, self._run_checks()

    def _session_checks(self, pv: dict) -> None:
        chk = self.rules.check
        sessions = defaultdict(list)
        for key in self.pairs:
            sessions[self.by_key["legacy"][key]["sessionId"]].append(key)
        conf = chk("gateway_calls_per_idem_key_le_1")
        for sid, keys in sessions.items():
            ordered = sorted(keys, key=lambda k: (self.req_order.get(k[0], 0), k[1]))
            if conf:
                counts = {s: Counter() for s in STACKS}
                owners = defaultdict(list)
                for s in STACKS:
                    for (rid, hop), rec in self.by_key[s].items():
                        if rec["sessionId"] != sid:
                            continue
                        idem = self.norm[s][(rid, hop)]["_idempotencyKey"]
                        if not idem:
                            continue
                        n = sum(1 for c in rec.get("externalCalls", []) if c["host"] == conf["host"] and c["path"] == conf["path"])
                        counts[s][idem] += n
                        if (rid, hop) not in owners[idem]:
                            owners[idem].append((rid, hop))
                for idem in sorted(set(counts["legacy"]) | set(counts["new"])):
                    a, b = counts["legacy"][idem], counts["new"][idem]
                    if b > 1 or a > 1 or a != b:
                        for k in owners[idem]:
                            if k in pv:
                                pv[k].append(f"gateway_calls_per_idem_key_le_1[{idem}]: legacy {a} / new {b}")
            if chk("coupon_transition_order"):
                for s in ("legacy", "new"):
                    used = set()
                    for key in ordered:
                        n = self.norm[s][key]
                        if n["endpoint"] == "coupon.use" and n["response.status"] == 200 and isinstance(n["response.body"], dict):
                            used.add(n["response.body"].get("couponKey"))
                        if n["endpoint"] == "consume.order.paid" and ["update", "coupons"] in n["writeSet"]:
                            ck = (n["event"]["payload"] or {}).get("couponKey") if isinstance(n["event"]["payload"], dict) else None
                            if ck not in used:
                                pv[key].append(f"coupon_transition_order[{ck}]: {s}에서 use 없이 SETTLED")

    def _run_checks(self) -> list[dict]:
        out = []
        if self.rules.check("dbstate_equal"):
            paths = {s: self.run_dir / f"dbstate-{s}.json" for s in STACKS}
            if all(p.exists() for p in paths.values()):
                a, b = (json.loads(paths[s].read_text(encoding="utf-8"))["tables"] for s in STACKS)
                diffs = [f"{t}: legacy={_tsum(a.get(t))} new={_tsum(b.get(t))}"
                         for t in sorted(set(a) | set(b)) if _tsum(a.get(t)) != _tsum(b.get(t))]
                out.append({"check": "dbstate_equal", "ok": not diffs, "violations": diffs,
                            "tables": {t: _tsum(a[t]) for t in sorted(a)}})
            else:
                out.append({"check": "dbstate_equal", "ok": None, "violations": ["dbstate 파일 없음"]})
        return out


def _tsum(t):
    return None if t is None else {"count": t["count"], "sum": t["sum"], "sha256": t["sha256"]}


def _strip(rec: dict) -> dict:
    """B0: 휘발 필드(시각·runId·version·stack)와 DB auto id만 뺀 원문. 본문은 id 제거 후 원래 키 순서로 다시 직렬화하고
    그 본문의 hash는 버린다(id가 들어간 hash라서). 그 외(SQL 원문·callTree·seq·hash)는 그대로 비교한다."""
    out = {k: v for k, v in rec.items() if k not in VOLATILE}
    resp = out.get("response")
    if resp and resp.get("body") is not None:
        parsed = nz.parse_json(resp["body"])
        if parsed is not None:
            out["response"] = {k: v for k, v in resp.items() if k != "bodyHash"} | {
                "body": json.dumps(nz.strip_ids(parsed), ensure_ascii=False, separators=(",", ":"))}
    req = out.get("request")
    if req:
        out["request"] = req | {"headers": {k: v for k, v in req["headers"].items() if k != "x-run-id"}}
    return out


def _short(calls: list) -> str:
    return nz.canonical([[c["method"], c["host"], c["path"], c["status"]] for c in calls])


# ---------------------------------------------------------------- 실행
def judge_run(run_dir: Path, rules_dir: Path, arm: str = "C") -> dict:
    rules = RuleSet(rules_dir)
    j = Judge(run_dir, rules)
    if arm == "C":
        pairs, run_checks = j.judge_full()
    else:
        pairs, run_checks = j.judge_simple(arm), []
    by_split, by_ep = defaultdict(Counter), defaultdict(Counter)
    for p in pairs:
        by_split[p["split"] or "-"][p["verdict"]] += 1
        by_ep[p["endpoint"]][p["verdict"]] += 1
    return {
        "engine": {"version": ENGINE_VERSION, "arm": arm, "rules": rules.sha256()},
        "runId": run_dir.name,
        "pairs": pairs,
        "runChecks": run_checks,
        "summary": {
            "pairs": len(pairs),
            "verdicts": dict(sorted(Counter(p["verdict"] for p in pairs).items())),
            "bySplit": {k: dict(sorted(v.items())) for k, v in sorted(by_split.items())},
            "byEndpoint": {k: dict(sorted(v.items())) for k, v in sorted(by_ep.items())},
            **j.delivery(),
        },
    }


def dumps(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def print_table(result: dict) -> None:
    s = result["summary"]
    print(f"== {result['runId']}  arm {result['engine']['arm']}  pairs {s['pairs']}  {s['verdicts']}")
    for split, c in s["bySplit"].items():
        print(f"  split {split:6} {c}")
    for ep, c in s["byEndpoint"].items():
        print(f"  {ep:20} {c}")
    for rc in result["runChecks"]:
        print(f"  run {rc['check']}: {'OK' if rc['ok'] else 'VIOLATION'} {rc['violations'] or ''}")
    print(f"  Undelivered legacy {len(s['undelivered']['legacy'])} / new {len(s['undelivered']['new'])}, degraded {len(s['degraded'])}")
    for p in result["pairs"]:
        if p["verdict"] not in ("SAME",):
            reasons = p.get("violations") or [f"{u['diffKind']}" for u in p.get("uncertain", [])] or [a["rule"] for a in p.get("appliedRules", [])]
            print(f"  {p['verdict']:18} {p['replayRequestId']}/{p['hopPath']} {p['endpoint']}: {'; '.join(reasons)[:220]}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="판정 엔진 v1 (Phase 3.4)")
    ap.add_argument("--run", required=True, type=Path)
    ap.add_argument("--arm", default="C", choices=["B0", "B1", "C"])
    ap.add_argument("--rules", default=ROOT / "engine" / "rules", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    result = judge_run(args.run, args.rules, args.arm)
    out = args.out or args.run / ("verdict.json" if args.arm == "C" else f"verdict-{args.arm}.json")
    out.write_text(dumps(result), encoding="utf-8")
    print_table(result)
    print(f"  → {out}")
    bad = result["summary"]["verdicts"].get("CONTRACT_VIOLATION", 0) or any(rc["ok"] is False for rc in result["runChecks"])
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
