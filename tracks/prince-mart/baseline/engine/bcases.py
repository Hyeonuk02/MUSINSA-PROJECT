#!/usr/bin/env python3
"""Legacy 버그 B1~B6 재현 판정 (Step 8, corpus-v1 기준). run export만 입력으로 받는다.

  python3 baseline/engine/bcases.py baseline/runs/<runId> [--stack legacy]

세션·요청 순서는 k6-results.jsonl에서 읽는다(corpus-v1의 세션 S02·S04·S05·S07·S08·S09·S10·S11).
"""
import argparse
import json
import pathlib
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--stack", default="legacy")
    a = ap.parse_args()
    run = pathlib.Path(a.run)
    ev = json.loads((run / f"{a.stack}.json").read_text())
    db = json.loads((run / f"db-{a.stack}.json").read_text())
    k6 = [json.loads(l) for l in (run / "k6-results.jsonl").read_text().splitlines() if '"type":"result"' in l]
    rid = {}
    for r in k6:
        rid.setdefault(r["sessionId"], []).append(r["requestId"])

    def http(r, svc="order", path_prefix=None):
        for e in ev:
            if e["replayRequestId"] == r and e["service"] == svc and e["kind"] == "http" and \
                    (path_prefix is None or e["request"]["path"].startswith(path_prefix)):
                return e
        return None

    def body(e):
        return json.loads(e["response"]["body"])

    usage = db["coupon.coupon_usage"]
    cols = usage["columns"]
    usage_orders = [r[cols.index("order_id")] for r in usage["rows"]]
    s11_order = str(body(http(rid["S11"][0]))["orderId"])
    s02 = [body(http(r)) for r in rid["S02"]]
    s07 = [body(http(r)) for r in rid["S07"]]
    use404 = [e for e in ev if e["service"] == "coupon" and e["kind"] == "http" and e["request"]["path"] == "/coupons/use"
              and e["response"]["status"] == 404]
    checks = {
        "B1": {
            "desc": "쿠폰 사용 기록 누락 -> 같은 쿠폰 무제한 재사용",
            "ok": all(x["totalAmount"] == 95000 for x in s02) and all(x["totalAmount"] == 97000 for x in s07)
                  and usage_orders == [s11_order] and len(use404) >= 6
                  and all((e["error"] or {}).get("class", "").endswith("ResourceNotFoundException") for e in use404),
            "observed": {"S02 totals": [x["totalAmount"] for x in s02], "S07(LIMIT 1) totals": [x["totalAmount"] for x in s07],
                         "coupon_usage order_ids": usage_orders, "coupon /use 404 count": len(use404)}},
        "B2": {
            "desc": "취소된 주문에 /coupons/use가 200, 기록됨",
            "ok": http(rid["S11"][2], "coupon")["response"]["status"] == 200 and s11_order in usage_orders,
            "observed": {"status": http(rid["S11"][2], "coupon")["response"]["status"], "usage for order": s11_order}},
        "B3": {
            "desc": "만료·최소금액 미달 쿠폰이 정가 100,000원, 200",
            "ok": all(http(rid[s][0])["response"]["status"] == 200 and body(http(rid[s][0]))["totalAmount"] == 100000
                      for s in ("S04", "S05")),
            "observed": {s: body(http(rid[s][0]))["totalAmount"] for s in ("S04", "S05")}},
        "B4": {
            "desc": "취소된 주문을 verify가 CONFIRMED/PAID로",
            "ok": (lambda b: (b["orderStatus"], b["paymentStatus"]) == ("CONFIRMED", "PAID"))(body(http(rid["S09"][3]))),
            "observed": (lambda b: f'{b["orderStatus"]}/{b["paymentStatus"]}')(body(http(rid["S09"][3])))},
        "B5": {
            "desc": "PAID 주문 취소 후에도 paymentStatus PAID",
            "ok": (lambda b: (b["orderStatus"], b["paymentStatus"]) == ("CANCELLED", "PAID"))(body(http(rid["S10"][2]))),
            "observed": (lambda b: f'{b["orderStatus"]}/{b["paymentStatus"]}')(body(http(rid["S10"][2])))},
        "B6": {
            "desc": "RuntimeException이 모두 404 (재취소 IllegalStateException, 남의 주문 Unauthorized)",
            "ok": http(rid["S08"][2])["response"]["status"] == 404
                  and http(rid["S08"][2])["error"]["class"].endswith("IllegalStateException")
                  and http(rid["S08"][3])["response"]["status"] == 404
                  and http(rid["S08"][3])["error"]["class"].endswith("ResourceNotFoundException"),
            "observed": {"re-cancel": [http(rid["S08"][2])["response"]["status"], http(rid["S08"][2])["error"]["class"]],
                         "other user": [http(rid["S08"][3])["response"]["status"], http(rid["S08"][3])["error"]["class"]]}},
    }
    print(json.dumps({"run": str(run), "stack": a.stack, "checks": checks}, ensure_ascii=False, indent=1))
    sys.exit(0 if all(c["ok"] for c in checks.values()) else 1)


if __name__ == "__main__":
    main()
