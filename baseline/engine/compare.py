#!/usr/bin/env python3
"""베이스라인 비교 (Step 8-2). run 하나의 export만 입력으로 받는다(클러스터·compose에 접근하지 않는다).

  python3 baseline/engine/compare.py baseline/runs/<runId> [--rules baseline/engine/normalization.json]

입력: <run>/legacy.json, new.json (Evidence 배열), db-legacy.json, db-new.json, k6-results.jsonl, run-meta.json
출력: <run>/compare.json + 요약 출력

비교 항목
  pairing    legacy·new Evidence를 (replayRequestId, service, kind, seq)로 짝짓는다. 한쪽에만 있으면 Undelivered/Unexpected.
             http는 request의 method·path·query·headers·bodyHash를 전건 대조한다(Phase 2.7).
  B0         exact diff: 짝지은 Evidence 전체를 그대로 비교(식별 필드 stack만 제외). 차이를 범주로 나눈다.
  B1         normalization.json 규칙을 적용한 뒤 비교. A/A 기대값 0.
  tables     테이블별 행 수 · 숫자 열 합 · 정렬된 행 해시.
  order      서비스별로 seq 순서대로 처리한 (replayRequestId, kind) 순서가 양쪽 같은지(nginx mirror 순서 보존).
  timing     처리 시간(durationMs)을 나란히 기록만 한다(판정 기준 아님).
"""
import argparse
import hashlib
import json
import pathlib
import re
import statistics
import sys

STACKS = ("legacy", "new")


# ------------------------------------------------------------------ helpers
def load(run):
    ev = {st: json.loads((run / f"{st}.json").read_text()) for st in STACKS}
    db = {st: json.loads((run / f"db-{st}.json").read_text()) for st in STACKS}
    meta = json.loads((run / "run-meta.json").read_text())
    k6 = [json.loads(l) for l in (run / "k6-results.jsonl").read_text().splitlines() if '"type":"result"' in l]
    return ev, db, meta, k6


def key(e):
    return (e["replayRequestId"], e["service"], e["kind"], int(e.get("seq") or 0))


def flatten(v, prefix=""):
    """{"a":{"b":[1,2]}} -> {"a.b[0]":1, "a.b[1]":2}. 빈 dict/list도 값으로 남긴다."""
    out = {}
    if isinstance(v, dict) and v:
        for k, x in v.items():
            out.update(flatten(x, f"{prefix}.{k}" if prefix else k))
    elif isinstance(v, list) and v:
        for i, x in enumerate(v):
            out.update(flatten(x, f"{prefix}[{i}]"))
    else:
        out[prefix] = v
    return out


def pattern(path):
    """calls[3].headers.traceparent -> calls[].headers.traceparent"""
    return re.sub(r"\[\d+\]", "[]", path)


# ------------------------------------------------------------------ normalization (B1)
def canonical(v, rules):
    if isinstance(v, dict):
        items = sorted(v.items()) if rules["jsonBodies"].get("sortKeys") else v.items()
        return {k: canonical(x, rules) for k, x in items}
    if isinstance(v, list):
        return [canonical(x, rules) for x in v]
    if isinstance(v, (int, float)) and not isinstance(v, bool) and rules["jsonBodies"].get("canonicalNumbers"):
        f = float(v)
        return int(f) if f.is_integer() else f
    return v


def parse_json_string(s, rules):
    if not isinstance(s, str) or not s.strip():
        return s
    try:
        return {"$json": canonical(json.loads(s), rules)}
    except (ValueError, TypeError):
        return s


def normalize(e, rules):
    e = json.loads(json.dumps(e))  # deep copy
    for f in rules["identityFields"]["fields"]:
        e.pop(f, None)
    for p in rules["ignoreFields"]["paths"]:
        if p.endswith("[].durationMs"):
            for item in e.get(p.split("[]")[0], []) or []:
                item.pop("durationMs", None)
        else:
            e.pop(p, None)
    drop = {h.lower() for h in rules["dropHeaders"]["names"]}

    def strip_headers(v):
        if isinstance(v, dict):
            for k, x in list(v.items()):
                if k == "headers" and isinstance(x, dict):
                    for hk in list(x):
                        if hk.lower() in drop:
                            del x[hk]
                else:
                    strip_headers(x)
        elif isinstance(v, list):
            for x in v:
                strip_headers(x)
    strip_headers(e)

    for p in rules["jsonBodies"]["paths"]:
        parent, _, field = p.rpartition(".")
        if "[]" in parent:
            for item in e.get(parent.replace("[]", ""), []) or []:
                if field in item:
                    item[field] = parse_json_string(item[field], rules)
        elif parent in e and isinstance(e[parent], dict) and field in e[parent]:
            e[parent][field] = parse_json_string(e[parent][field], rules)

    if rules["maskAutoIncrementIds"]["enabled"]:
        ids = set(rules["maskAutoIncrementIds"]["fields"])

        def mask(v):
            if isinstance(v, dict):
                return {k: ("<id>" if k in ids else mask(x)) for k, x in v.items()}
            if isinstance(v, list):
                return [mask(x) for x in v]
            return v
        e = mask(e)
    return e


# ------------------------------------------------------------------ B0 categories
def b0_category(path, rules):
    p = pattern(path)
    if p.startswith("timing") or p == "capturedAt":
        return "timing"
    if p.endswith(".durationMs"):
        return "durationMs"
    m = re.search(r"headers\.([^.\[]+)$", p)
    if m and m.group(1).lower() in {h.lower() for h in rules["dropHeaders"]["names"]}:
        return "trace-headers"
    if any(p.startswith(b.replace("[]", "[]")) for b in rules["jsonBodies"]["paths"]):
        return "json-body-text"
    return "other"


def diff_paths(a, b):
    fa, fb = flatten(a), flatten(b)
    return sorted(p for p in set(fa) | set(fb) if fa.get(p, "<absent>") != fb.get(p, "<absent>"))


# ------------------------------------------------------------------ tables
def table_summary(t):
    cols, rows = t["columns"], t["rows"]
    sums = {}
    for i, c in enumerate(cols):
        vals = [r[i] for r in rows if i < len(r) and r[i] not in ("NULL", "")]
        try:
            sums[c] = round(sum(float(v) for v in vals), 6) if vals else 0
        except ValueError:
            pass
    h = hashlib.sha256("\n".join("\t".join(r) for r in sorted(rows)).encode()).hexdigest()
    return {"count": len(rows), "sums": sums, "hash": h}


# ------------------------------------------------------------------ main
def compare(run, rules):
    ev, db, meta, k6 = load(run)
    idx = {st: {key(e): e for e in ev[st]} for st in STACKS}
    keys_l, keys_n = set(idx["legacy"]), set(idx["new"])
    paired = sorted(keys_l & keys_n)

    # pairing (http request 동일성)
    pairing_fields = ["method", "path", "query", "headers", "bodyHash"]
    pairing = {f: {"pass": 0, "fail": []} for f in pairing_fields}
    for k in paired:
        if k[2] != "http":
            continue
        rl, rn = idx["legacy"][k]["request"], idx["new"][k]["request"]
        for f in pairing_fields:
            if rl.get(f) == rn.get(f):
                pairing[f]["pass"] += 1
            else:
                pairing[f]["fail"].append({"key": list(k), "legacy": rl.get(f), "new": rn.get(f)})

    # B0 / B1
    b0, b1 = [], []
    for k in paired:
        a = {x: y for x, y in idx["legacy"][k].items() if x not in rules["identityFields"]["fields"]}
        b = {x: y for x, y in idx["new"][k].items() if x not in rules["identityFields"]["fields"]}
        for p in diff_paths(a, b):
            b0.append({"key": list(k), "path": p, "category": b0_category(p, rules)})
        for p in diff_paths(normalize(idx["legacy"][k], rules), normalize(idx["new"][k], rules)):
            b1.append({"key": list(k), "path": p})
    b0_by_cat = {}
    for d in b0:
        b0_by_cat.setdefault(d["category"], {"diffs": 0, "patterns": set()})
        b0_by_cat[d["category"]]["diffs"] += 1
        b0_by_cat[d["category"]]["patterns"].add(pattern(d["path"]))
    b0_by_cat = {c: {"diffs": v["diffs"], "patterns": sorted(v["patterns"])} for c, v in sorted(b0_by_cat.items())}

    # tables
    tables = {}
    for t in sorted(db["legacy"]):
        sl, sn = table_summary(db["legacy"][t]), table_summary(db["new"].get(t, {"columns": [], "rows": []}))
        tables[t] = {"legacy": sl, "same": {"count": sl["count"] == sn["count"], "sums": sl["sums"] == sn["sums"],
                                            "hash": sl["hash"] == sn["hash"]},
                     "rawEqual": db["legacy"][t] == db["new"].get(t)}

    # order (서비스별 seq 순서)
    order = {}
    for svc in sorted({k[1] for k in keys_l | keys_n if k[2] in ("http", "consume")}):
        seqs = {st: [(e["replayRequestId"], e["kind"]) for e in sorted(
            (e for e in ev[st] if e["service"] == svc and e["kind"] in ("http", "consume")), key=lambda e: e["seq"])]
            for st in STACKS}
        order[svc] = {"same": seqs["legacy"] == seqs["new"], "length": len(seqs["legacy"])}

    # timing (참고)
    def stats(st, kind):
        xs = [e["timing"]["durationMs"] for e in ev[st] if e["kind"] == kind and e.get("timing")]
        return {"n": len(xs), "mean": round(statistics.mean(xs), 1), "p50": round(statistics.median(xs), 1),
                "max": round(max(xs), 1)} if xs else {"n": 0}
    timing = {kind: {st: stats(st, kind) for st in STACKS} for kind in ("http", "consume")}

    report = {
        "runId": meta["runId"], "validityHash": meta["validityHash"], "rules": rules["version"],
        "requestsSent": meta["requestsSent"], "degradedSessions": meta["degradedSessions"],
        "evidence": {st: len(ev[st]) for st in STACKS},
        "evidenceByKind": {st: {kd: sum(1 for e in ev[st] if e["kind"] == kd) for kd in ("http", "consume", "external", "event")}
                           for st in STACKS},
        "paired": len(paired),
        "undelivered": [list(k) for k in sorted(keys_l - keys_n)],
        "unexpected": [list(k) for k in sorted(keys_n - keys_l)],
        "pairing": {f: {"pass": v["pass"], "fail": len(v["fail"]), "failures": v["fail"][:5]} for f, v in pairing.items()},
        "b0": {"diffs": len(b0), "pairsWithDiff": len({tuple(d["key"]) for d in b0}), "byCategory": b0_by_cat,
               "other": [d for d in b0 if d["category"] == "other"][:20]},
        "b1": {"diffs": len(b1), "items": b1[:50]},
        "tables": tables,
        "order": order,
        "timing": timing,
        # 반복 간 비교용 diff 집합(키 + 경로)
        "diffSets": {"b0": sorted({f"{'|'.join(map(str, d['key']))}::{d['path']}" for d in b0}),
                     "b1": sorted({f"{'|'.join(map(str, d['key']))}::{d['path']}" for d in b1})},
    }
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--rules", default=str(pathlib.Path(__file__).with_name("normalization.json")))
    args = ap.parse_args()
    run = pathlib.Path(args.run)
    rules = json.loads(pathlib.Path(args.rules).read_text())
    r = compare(run, rules)
    (run / "compare.json").write_text(json.dumps(r, ensure_ascii=False, indent=1))

    pf = ", ".join(f"{f} {v['pass']}/{v['pass'] + v['fail']}" for f, v in r["pairing"].items())
    print(f"run {r['runId']}  evidence legacy={r['evidence']['legacy']} new={r['evidence']['new']}  paired={r['paired']}  "
          f"undelivered={len(r['undelivered'])} unexpected={len(r['unexpected'])}")
    print(f"  pairing(http): {pf}")
    print(f"  B0 diffs={r['b0']['diffs']} in {r['b0']['pairsWithDiff']} pairs: "
          + ", ".join(f"{c}={v['diffs']}" for c, v in r["b0"]["byCategory"].items()))
    print(f"  B1 diffs={r['b1']['diffs']}")
    t_bad = [t for t, v in r["tables"].items() if not all(v["same"].values())]
    print(f"  tables: {len(r['tables'])} compared, mismatched={t_bad}")
    print(f"  order: " + ", ".join(f"{s}={'same' if v['same'] else 'DIFF'}({v['length']})" for s, v in r["order"].items()))
    ok = (not r["undelivered"] and not r["unexpected"] and all(v["fail"] == 0 for v in r["pairing"].values())
          and r["b1"]["diffs"] == 0 and not t_bad and all(v["same"] for v in r["order"].values()))
    print(f"  => {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
