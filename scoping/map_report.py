#!/usr/bin/env python3
"""Phase 4.1 — 맵과 계획 예측의 대조, docs/call-graph-map.md 생성. 맵·계획을 고치지 않는다(차이는 [DIFF]로 출력).

대조: (A) phase4-plan 4.1 사전 등록 예상 맵 (B) 4.2 기대의 전제 (C) 클래스별 관측·세션·요청 예측(0절 표·4.2 표)
(D) 홉 합산 없는 맵의 선택(3절·4.5 ablation b 예측) (E) 미관측 클래스의 단순 이름 참조자(폐포는 4.2 — 여기선 텍스트 사실만).

사용: .venv/bin/python scoping/map_report.py --map scoping/map.json --doc docs/call-graph-map.md
"""
import argparse
import json
import re
import sys
from pathlib import Path

from common import ENTRY_HOP, ROOT, corpus_index, git, load_corpus, load_records
from map import SOURCE_ROOTS, strip_comments

P = "poc.order."
C = "poc.coupon."
BASE = {P + n for n in ("OrderController", "OrderService", "OrderRepository")}
COUPON_SIDE = {P + "CouponClient", C + "CouponController", C + "CouponService", C + "CouponRepository"}
PAY_SIDE = {P + "PaymentGatewayClient", P + "OrderEventPublisher", C + "OrderPaidListener"}
SETTLE_SIDE = {C + "CouponService", C + "CouponRepository"}
COUPON_BASE = {C + n for n in ("CouponController", "CouponService", "CouponRepository")}

# 계획의 예측: 클래스 → (선택 세션, 선택 요청) — phase4-plan 0절 표
PREDICTED = {
    P + "OrderController": (9, 37), P + "OrderService": (9, 37), P + "OrderRepository": (9, 37),
    P + "PaymentGatewayClient": (7, 30), P + "OrderEventPublisher": (7, 30), C + "OrderPaidListener": (7, 30),
    C + "CouponService": (6, 29), C + "CouponRepository": (6, 29), C + "CouponController": (6, 29),
}
PREDICTED_UNOBSERVED = [P + n for n in ("Order", "OrderItem", "OrderPaid", "OrderView", "ClockConfig", "OrderApplication",
                                        "requestlog.RequestLogFilter", "requestlog.CachedBodyRequest")]
NAME_HEADS = ("fc6e6e2", "c64618f", "phase3.5-v1.4")   # v1.2·v1.3 head, F*·C의 기준 head
NAME_TARGETS = ("Order", "OrderItem", "OrderPaid", "OrderView")


def short(fqcn: str) -> str:
    return fqcn.rsplit(".", 1)[1]


def shorts(classes) -> str:
    return ", ".join(sorted(short(c) for c in classes)) or "-"


def session_sizes(corpus: dict) -> dict[str, int]:
    return {s["id"]: len(s["requests"]) for s in corpus["sessions"]}


def coupon_orders(corpus: dict) -> tuple[set, set]:
    """(쿠폰 주문 생성 요청, 쿠폰 결제 요청) — corpus 본문의 couponKey와 결제 경로의 orderKey로."""
    creates, keys = set(), set()
    for s in corpus["sessions"]:
        for r in s["requests"]:
            body = r.get("body") or {}
            if r["method"] == "POST" and r["path"] == "/api/orders" and body.get("couponKey"):
                creates.add(r["id"])
                keys.add(body["orderKey"])
    pays = {r["id"] for s in corpus["sessions"] for r in s["requests"]
            if r["path"].endswith("/pay") and r["path"].split("/")[3] in keys}
    return creates, pays


def check_expected_map(m: dict, corpus: dict) -> list[str]:
    creates, pays = coupon_orders(corpus)
    rules = {"order.create": BASE, "order.get": BASE, "order.cancel": BASE, "order.pay": BASE | PAY_SIDE,
             "coupon.create": COUPON_BASE, "coupon.get": COUPON_BASE, "coupon.use": COUPON_BASE}
    out, misses = [], {}
    for rid, req in sorted(m["requests"].items()):
        want = set(rules[req["endpoint"]])
        if rid in creates:
            want |= COUPON_SIDE
        if rid in pays:
            want |= SETTLE_SIDE
        missing = want - set(req["classes"])
        if missing:
            misses[rid] = missing
    total = {}
    for req in m["requests"].values():
        total[req["endpoint"]] = total.get(req["endpoint"], 0) + 1
    for eid in sorted(total):
        bad = {r: x for r, x in misses.items() if m["requests"][r]["endpoint"] == eid}
        out.append(f"[{'DIFF' if bad else 'OK'}] {eid}: 예상 맵 만족 {total[eid] - len(bad)}/{total[eid]}"
                   + "".join(f" — {r}({m['requests'][r]['session']}) 없음: {shorts(x)}" for r, x in sorted(bad.items())))
    out.append(f"     쿠폰 주문 생성 {len(creates)}건 {sorted(creates)}, 쿠폰 결제 {len(pays)}건 {sorted(pays)}")
    return out


def check_premises(m: dict, records: list[dict]) -> list[str]:
    out = []
    reqs = m["requests"]
    cs = C + "CouponService"
    for eid in ("coupon.create", "coupon.get", "coupon.use"):
        ids = [r for r, q in reqs.items() if q["endpoint"] == eid]
        ok = sum(cs in reqs[r]["byHop"][ENTRY_HOP] for r in ids)
        out.append(f"[{'OK' if ok == len(ids) else 'DIFF'}] CouponService ∈ {eid} 진입 홉 {ok}/{len(ids)}")
    opl = C + "OrderPaidListener"
    hops = [(r, h) for r, q in reqs.items() for h, cs_ in q["byHop"].items() if opl in cs_]
    only_e = all(re.fullmatch(r"0\.e\d+", h) for _, h in hops)
    plain = [(r, h) for r, h in hops if cs not in reqs[r]["byHop"][h]]
    out.append(f"[{'OK' if only_e else 'DIFF'}] OrderPaidListener는 소비 홉에만: {len(hops)}개 홉 전부 0.e* = {only_e}")
    out.append(f"[{'OK' if plain else 'DIFF'}] 쿠폰 없는 결제의 소비 홉에도 있음: {len(plain)}건 {sorted(r for r, _ in plain)}")
    settle = sorted((r["replayRequestId"], r["hopPath"]) for r in records for n in r["callTree"]["nodes"]
                    if n["class"].startswith(cs) and n["method"] == "settle")
    only = all(h.startswith("0.e") for _, h in settle)
    out.append(f"[{'OK' if only else 'DIFF'}] CouponService.settle은 소비 홉에만: {settle}")
    return out


def select(m: dict, rids: set, sizes: dict) -> tuple[list, int]:
    sessions = sorted({m["requests"][r]["session"] for r in rids})
    return sessions, sum(sizes[s] for s in sessions)


def check_classes(m: dict, sizes: dict) -> list[str]:
    out = []
    pays = sum(q["endpoint"] == "order.pay" for q in m["requests"].values())
    for c, (want_s, want_r) in sorted(PREDICTED.items()):
        rids = set(m["classes"].get(c, {}).get("requests", []))
        sessions, n = select(m, rids, sizes)
        out.append(f"[{'OK' if (len(sessions), n) == (want_s, want_r) else 'DIFF'}] {short(c)}: 실행 요청 {len(rids)}, "
                   f"선택 {len(sessions)}/{len(sizes)}세션·{n}/{sum(sizes.values())}요청 (예측 {want_s}·{want_r})")
    for c in sorted(PAY_SIDE):
        rids = m["classes"][c]["requests"]
        out.append(f"[{'OK' if len(rids) == pays else 'DIFF'}] {short(c)}: order.pay {pays}건 중 {len(rids)}건 실행"
                   f" (예측 문구 '모든 order.pay'·'order.pay 전부')")
    for c in PREDICTED_UNOBSERVED:
        out.append(f"[{'DIFF' if c in m['classes'] else 'OK'}] {short(c)}: 미관측 예측 — 맵에 {'있음' if c in m['classes'] else '없음'}")
    return out


def check_no_hop_merge(m: dict, sizes: dict) -> list[str]:
    """자식 홉 합산이 없는 맵(진입 홉 callTree만)에서 클래스별 선택."""
    entry = {c: {r for r, q in m["requests"].items() if c in q["byHop"][ENTRY_HOP]} for c in m["classes"]}
    out = []
    for c, predicted in ((C + "OrderPaidListener", []), (C + "CouponService", ["S004", "S005"])):
        sessions, n = select(m, entry[c], sizes)
        ok = sessions == predicted
        out.append(f"[{'OK' if ok else 'DIFF'}] {short(c)}: 합산 없는 맵 선택 {sessions or '없음(미관측)'} {n}요청 "
                   f"(예측 {predicted or '없음 → 미관측'})")
    cs = C + "CouponService"
    full, only_entry = set(m["classes"][cs]["requests"]), entry[cs]
    out.append(f"     CouponService 영향 요청: 합산 {len(full)} / 합산 없음 {len(only_entry)} — 합산에서만 잡히는 {sorted(full - only_entry)}")
    extra = sorted({(m["requests"][r]["session"], r, m["requests"][r]["endpoint"]) for r in only_entry
                    if m["requests"][r]["session"] not in ("S004", "S005")})
    out.append(f"     S004·S005 밖 진입 홉 실행: {extra}")
    return out


def name_references(m: dict) -> list[str]:
    """단순 이름 참조자(주석·문자열 제외, 자기 파일 제외). 그 파일이 같은 이름을 다른 패키지에서 import하면 표시."""
    out = []
    for head in NAME_HEADS:
        out.append(f"-- {head}")
        files = [f for f in git("ls-tree", "-r", "--name-only", head, "--", *SOURCE_ROOTS).splitlines()
                 if f.endswith((".java", ".kt"))]
        src = {f: strip_comments(git("show", f"{head}:{f}")) for f in files}
        src = {f: re.sub(r'"(?:\\.|[^"\\])*"', '""', s) for f, s in src.items()}
        for name in NAME_TARGETS:
            refs = []
            for f, s in sorted(src.items()):
                stem = Path(f).stem
                if stem == name or not re.search(rf"\b{name}\b", s):
                    continue
                fqcn = next(iter(re.findall(r"^package\s+([\w.]+)", s, re.M))) + "." + stem
                foreign = re.findall(rf"^import\s+([\w.]+\.{name})\b", s, re.M)
                nested = bool(re.search(rf"\b(?:record|class)\s+{name}\b", s))
                note = "" if fqcn in m["classes"] else " 미관측"
                note += f" import {foreign[0]}" if foreign else ""
                note += " 동명 중첩 선언" if nested else ""
                refs.append(f"{fqcn}{note}")
            out.append(f"   {name}: {refs}")
    return out


# ---------------------------------------------------------------- 문서
def doc(m: dict) -> str:
    reqs = m["requests"]
    cov = m["coverage"]
    lines = ["# 동적 Call Graph 맵 (Phase 4.1)", "",
             f"> `scoping/map_report.py`가 `scoping/map.json`에서 생성한다. 손으로 고치지 않는다. 정본 입력 {', '.join(m['builtFrom'])} (Legacy 레코드, {m['corpus']['version']}), "
             f"맵 본문 `{m['bodySha256']}`.", "",
             "맵은 corpus가 실행한 경로만 안다. 매칭은 클래스 단위, 정본은 요청 단위(D23), 엔드포인트 표는 요약이며 corpus 재생의 선택에는 쓰지 않는다.", "",
             "## 커버리지", "",
             f"엔드포인트 {len(cov['endpoints']['observed'])}/{cov['endpoints']['total']}.", "",
             "| 소스 | 빈 클래스 | 맵 등장 | 미관측 빈 | 이유 |", "|---|---|---|---|---|"]
    for ref, s in cov["sources"].items():
        names = "; ".join(short(u["fqcn"]) for u in s["unobservedBeans"]) or "-"
        why = "; ".join(u["reason"] for u in s["unobservedBeans"]) or "-"
        lines.append(f"| `{ref}` | {s['beans']} | {s['beansObserved']} | {names} | {why} |")
    first = next(iter(cov["sources"].values()))
    lines += ["", "빈이 아니라 AOP가 보지 못하는 클래스(변경되면 폐포 대상): " + ", ".join(f"`{n['fqcn'].removeprefix('poc.')}`({n['kind']})" for n in first["nonBeans"]) + ".", "",
              "## 엔드포인트 → 클래스 (요약)", "",
              "| 엔드포인트 | 진입 요청 | 자식 홉 요청 | 세션 | 클래스 |", "|---|---|---|---|---|"]
    for eid, e in sorted(m["endpoints"].items()):
        lines.append(f"| {eid} | {len(e['requests'])} | {len(e['hopRequests'])} | {len(e['sessions'])} | {shorts(e['classes'])} |")
    lines += ["", "## 클래스 → 요청", "", "| 클래스 | 실행 요청 | 세션 | 엔드포인트 |", "|---|---|---|---|"]
    for c, e in sorted(m["classes"].items()):
        sessions = sorted({reqs[r]["session"] for r in e["requests"]})
        lines.append(f"| `{c}` | {len(e['requests'])} | {len(sessions)} ({', '.join(sessions)}) | {', '.join(e['endpoints'])} |")
    lines += ["", "## 서비스 간 간선", "",
              "| 요청 | 세션 | 진입 엔드포인트 | 홉 | 종류 | 실행된 클래스 |", "|---|---|---|---|---|---|"]
    for rid, q in sorted(reqs.items()):
        for hop, classes in sorted(q["byHop"].items()):
            if hop != ENTRY_HOP:
                kind = "HTTP" if ".h" in hop else "Kafka"
                lines.append(f"| {rid} | {q['session']} | {q['endpoint']} | `{hop}` | {kind} | {shorts(classes)} |")
    lines += ["", "## 요청 → 클래스 (정본)", "", "| 요청 | 세션 | 엔드포인트 | 홉 | 클래스(모든 홉 합산) |", "|---|---|---|---|---|"]
    for rid, q in sorted(reqs.items()):
        lines.append(f"| {rid} | {q['session']} | {q['endpoint']} | {', '.join(f'`{h}`' for h in sorted(q['byHop']))} | {shorts(q['classes'])} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="맵 대조·문서 생성(Phase 4.1)")
    ap.add_argument("--map", default=ROOT / "scoping" / "map.json", type=Path)
    ap.add_argument("--corpus", default=ROOT / "corpus" / "corpus-v2.1.json", type=Path)
    ap.add_argument("--records", default=ROOT / "runs" / "p36-base-1", type=Path)
    ap.add_argument("--doc", type=Path)
    args = ap.parse_args(argv)
    m = json.loads(args.map.read_text(encoding="utf-8"))
    corpus = load_corpus(args.corpus)
    assert set(corpus_index(corpus)) == set(m["requests"])
    sizes = session_sizes(corpus)
    sections = (("A. 사전 등록 예상 맵 (4.1)", check_expected_map(m, corpus)),
                ("B. 4.2 기대의 전제", check_premises(m, load_records(args.records))),
                ("C. 클래스별 관측·선택 (0절 표·4.2 표)", check_classes(m, sizes)),
                ("D. 홉 합산 없는 맵 (3절·4.5 ablation b)", check_no_hop_merge(m, sizes)),
                ("E. 미관측 클래스의 단순 이름 참조자 (텍스트 사실 — 폐포 계산은 4.2)", name_references(m)))
    for title, rows in sections:
        print(f"== {title}")
        print("\n".join(rows))
    diffs = sum(r.startswith("[DIFF]") for _, rows in sections for r in rows)
    print(f"== [DIFF] {diffs}건")
    if args.doc:
        args.doc.write_text(doc(m), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
