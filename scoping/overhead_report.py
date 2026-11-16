#!/usr/bin/env python3
"""Phase 4.9 — Evidence on/off 측정 요약(참고값). 기대 없음, 판정과 무관하다.

입력 runs/p49-{on,off}-1..3: k6-summary.json(api_latency), stats-before/after.json(crictl stats), legacy.json(on, Evidence 크기).
출력 docs/phase4-overhead.json, 표는 stdout. 사용: .venv/bin/python scoping/overhead_report.py
"""
import json
import statistics
import sys

from common import ROOT, dumps

MODES = ("on", "off")
CONTAINERS = {("order", "order"), ("order", "istio-proxy"), ("coupon", "coupon"), ("coupon", "istio-proxy")}


def container_stats(path) -> dict:
    """(서비스, 컨테이너) → {cpuNs, memBytes}. legacy의 order·coupon pod만, 앱 pod 이름 접두로 구분."""
    out = {}
    for s in json.loads(path.read_text(encoding="utf-8"))["stats"]:
        labels = s["attributes"]["labels"]
        pod, name = labels["io.kubernetes.pod.name"], labels["io.kubernetes.container.name"]
        if labels["io.kubernetes.pod.namespace"] != "legacy":
            continue
        service = next((x for x in ("order", "coupon") if pod.startswith(f"{x}-") and not pod.startswith("coupon-mysql")), None)
        if service and (service, name) in CONTAINERS and s.get("cpu") and s.get("memory"):
            key = f"{service}/{name}"
            cpu = int(s["cpu"]["usageCoreNanoSeconds"]["value"])
            if key not in out or cpu > out[key]["cpuNs"]:      # 종료된 이전 컨테이너가 남아 있으면 현재(누적 큰 쪽)
                out[key] = {"cpuNs": cpu, "memBytes": int(s["memory"]["workingSetBytes"]["value"])}
    return out


def run_row(mode: str, i: int) -> dict:
    d = ROOT / "runs" / f"p49-{mode}-{i}"
    lat = json.loads((d / "k6-summary.json").read_text(encoding="utf-8"))["api_latency"]
    before, after = container_stats(d / "stats-before.json"), container_stats(d / "stats-after.json")
    return {"run": d.name, "requests": lat["count"], "p50": round(lat["med"], 2), "p95": round(lat["p(95)"], 2), "max": round(lat["max"], 2),
            "cpuCoreSeconds": {k: round((after[k]["cpuNs"] - before[k]["cpuNs"]) / 1e9, 3) for k in sorted(after) if k in before},
            "workingSetMiB": {k: round(v["memBytes"] / 2**20, 1) for k, v in sorted(after.items())},
            "meta": json.loads((d / "run-meta.json").read_text(encoding="utf-8"))}


def evidence_sizes() -> dict:
    sizes = {}
    for i in (1, 2, 3):
        for rec in json.loads((ROOT / "runs" / f"p49-on-{i}" / "legacy.json").read_text(encoding="utf-8")):
            sizes.setdefault(rec["service"], []).append(len(json.dumps(rec, ensure_ascii=False, separators=(",", ":")).encode()))
    total = sorted(x for v in sizes.values() for x in v)
    def row(v):
        v = sorted(v)
        return {"records": len(v), "p50": int(statistics.median(v)), "p95": v[int(len(v) * 0.95)], "max": v[-1], "sumPerRun": sum(v) // 3}
    return {"all": row(total), **{k: row(v) for k, v in sorted(sizes.items())}}


def main() -> int:
    rows = {m: [run_row(m, i) for i in (1, 2, 3)] for m in MODES}
    def med(m, f):
        return round(statistics.median(f(r) for r in rows[m]), 3)
    keys = sorted(rows["on"][0]["cpuCoreSeconds"])
    summary = {m: {"p50": med(m, lambda r: r["p50"]), "p95": med(m, lambda r: r["p95"]),
                   "cpuCoreSeconds": {k: med(m, lambda r: r["cpuCoreSeconds"][k]) for k in keys},
                   "workingSetMiB": {k: med(m, lambda r: r["workingSetMiB"][k]) for k in keys}} for m in MODES}
    result = {"note": "참고값. 기대 없음, 판정과 무관. VU=1 × 3, 표본 run당 48요청", "runs": rows, "medianOfRuns": summary, "evidenceBytes": evidence_sizes()}
    (ROOT / "docs" / "phase4-overhead.json").write_text(dumps(result), encoding="utf-8")
    print("| run | 요청 | p50 ms | p95 ms | max ms | CPU 코어초(order앱 / order sidecar / coupon앱 / coupon sidecar) | working set MiB(앱 order / coupon) |\n|---|---|---|---|---|---|---|")
    for m in MODES:
        for r in rows[m]:
            c, w = r["cpuCoreSeconds"], r["workingSetMiB"]
            print(f"| {r['run']} | {r['requests']} | {r['p50']} | {r['p95']} | {r['max']} | {c.get('order/order')} / {c.get('order/istio-proxy')} / {c.get('coupon/coupon')} / {c.get('coupon/istio-proxy')} | {w.get('order/order')} / {w.get('coupon/coupon')} |")
    print(json.dumps(summary, ensure_ascii=False))
    print(json.dumps(result["evidenceBytes"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
