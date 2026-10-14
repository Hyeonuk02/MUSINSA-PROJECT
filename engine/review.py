#!/usr/bin/env python3
"""Phase 3.4 — Human Review (비대화형). 클러스터에 접근하지 않는다(D12).

  list   learn 세션의 Uncertain 항목만, uid별로 묶어 보여준다(eval 세션은 절대 보이지 않는다).
         uid = endpoint + axis + diffKind + 정규화 상세의 sha256 앞 12자 — 특정 요청 값(rid·session)은 들어가지 않으므로
         같은 유형의 diff는 learn·eval에서 같은 uid가 된다.
  label  uid 하나에 사람이 내린 판정(same|improvement|violation)을 rules/learned/<uid>.yaml로 남긴다.
         provenance(author·date·runId·split=learn·sessions)는 자동. match는 제안 템플릿, 또는 --match-file로 사람이 좁힌 것.
         eval 세션에만 있는 uid는 거부한다(평가 데이터로 규칙을 만들지 않는다 — 3.6 학습/평가 분리).

규칙이 덮을 수 있는 diffKind만 label할 수 있다(ruleset.DIFF_KINDS). 그 외(externalCalls.responseHashChanged 등)는
규칙이 아니라 계약(contract.yaml)·코드 판단이 필요하다는 뜻이라 거부한다.

사용: .venv/bin/python engine/review.py list  --run runs/<runId> --split learn [--rules engine/rules]
      .venv/bin/python engine/review.py label --run runs/<runId> --uid <uid> --as improvement --reason "..." [--match-file m.yaml]
"""
import argparse
import datetime
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import yaml

from common import ROOT
from ruleset import DIFF_KINDS, Rule, RuleError
from verdict import judge_run

AS_VERDICT = {"same": "same", "improvement": "improvement", "violation": "violation"}


def collect(result: dict) -> dict:
    """uid → {item, occurrences{split: [(rid, hop, session)]}} — Uncertain 항목만."""
    out = {}
    for p in result["pairs"]:
        if p["verdict"] != "UNCERTAIN":
            continue
        for u in p["uncertain"]:
            entry = out.setdefault(u["uid"], {"endpoint": p["endpoint"], "axis": u["axis"], "diffKind": u["diffKind"],
                                              "detail": u["detail"], "occurrences": defaultdict(list)})
            entry["occurrences"][p["split"]].append((p["replayRequestId"], p["hopPath"], p["sessionId"]))
    return out


def template(entry: dict) -> dict | None:
    """제안 matcher. 값은 그대로(정규식이면 escape) — 사람이 --match-file로 넓히거나 좁힌다."""
    kind, d = entry["diffKind"], entry["detail"]
    if kind not in DIFF_KINDS:
        return None
    m = {"endpoint": entry["endpoint"], "diffKind": kind}
    if kind in ("response.addedFields", "response.removedFields", "events.payloadFieldsAdded"):
        m["fields"] = list(d["fields"])
    elif kind == "response.valueChanged":
        m |= {"path": d["path"], "from": re.escape(_s(d["from"])), "to": re.escape(_s(d["to"]))}
    elif kind == "dbRead.fingerprintReplaced":
        m |= {"from": [re.escape(x) for x in d["from"]], "to": [re.escape(x) for x in d["to"]]}
    else:  # countDelta, callTree.sequenceReplaced, transactions.nameChanged
        m |= {"from": d["from"], "to": d["to"]}
    return m


def _s(v) -> str:
    return "null" if v is None else str(v)


def author() -> str:
    if os.environ.get("REVIEW_AUTHOR"):
        return os.environ["REVIEW_AUTHOR"]
    try:
        return subprocess.run(["git", "config", "user.name"], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip() or "unknown"
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def cmd_list(args) -> int:
    if args.split != "learn":
        print("list는 --split learn만 허용한다(eval 세션 diff는 사람에게 보이지 않는다)", file=sys.stderr)
        return 2
    entries = collect(judge_run(args.run, args.rules, "C"))
    shown = {uid: e for uid, e in sorted(entries.items()) if e["occurrences"].get("learn")}
    print(f"== {args.run.name}  learn Uncertain 유형 {len(shown)}")
    for uid, e in shown.items():
        occ = e["occurrences"]["learn"]
        print(f"\n[{uid}] {e['endpoint']}  {e['axis']}  {e['diffKind']}  ({len(occ)}건: "
              + ", ".join(f"{r}/{h}" for r, h, _ in occ) + ")")
        print("  detail: " + yaml.safe_dump(e["detail"], allow_unicode=True, default_flow_style=True, width=200).strip())
        t = template(e)
        print("  제안 match: " + (yaml.safe_dump(t, allow_unicode=True, default_flow_style=True, width=200).strip()
                                 if t else "(규칙으로 덮을 수 없는 diffKind — 계약·코드 판단 필요)"))
    return 0


def cmd_label(args) -> int:
    entries = collect(judge_run(args.run, args.rules, "C"))
    e = entries.get(args.uid)
    if e is None:
        print(f"uid {args.uid}: 이 run의 Uncertain 항목에 없음", file=sys.stderr)
        return 2
    learn = e["occurrences"].get("learn", [])
    if not learn:
        print(f"uid {args.uid}: eval 세션에서만 나온 항목 — 평가 데이터로 규칙을 만들 수 없다", file=sys.stderr)
        return 2
    if args.match_file:
        match = yaml.safe_load(args.match_file.read_text(encoding="utf-8"))
    else:
        match = template(e)
        if match is None:
            print(f"uid {args.uid}: diffKind {e['diffKind']}는 규칙으로 덮을 수 없다", file=sys.stderr)
            return 2
    rule = {
        "id": f"learned-{args.uid}",
        "scope": "request",
        "verdict": AS_VERDICT[args.as_],
        "reason": args.reason,
        "provenance": {"author": author(), "date": datetime.date.today().isoformat(), "runId": args.run.name,
                       "split": "learn", "sessions": sorted({s for _, _, s in learn}), "uid": args.uid},
        "match": match,
    }
    try:
        Rule(rule, f"learned/{args.uid}.yaml")
    except RuleError as err:
        print(f"규칙 거부: {err}", file=sys.stderr)
        return 2
    out = args.rules / "learned" / f"{args.uid}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(rule, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"→ {out}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Human Review (Phase 3.4, 비대화형)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("list", "label"):
        p = sub.add_parser(name)
        p.add_argument("--run", required=True, type=Path)
        p.add_argument("--rules", default=ROOT / "engine" / "rules", type=Path)
    sub.choices["list"].add_argument("--split", required=True)
    lab = sub.choices["label"]
    lab.add_argument("--uid", required=True)
    lab.add_argument("--as", dest="as_", required=True, choices=sorted(AS_VERDICT))
    lab.add_argument("--reason", required=True)
    lab.add_argument("--match-file", type=Path)
    args = ap.parse_args(argv)
    return cmd_list(args) if args.cmd == "list" else cmd_label(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
