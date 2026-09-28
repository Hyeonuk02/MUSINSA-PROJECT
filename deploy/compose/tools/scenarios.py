#!/usr/bin/env python3
"""Legacy 시나리오 재현 확인 (Step 4 완료 기준)

legacy 스택을 S0로 리셋한 뒤 시나리오와 Legacy 버그 B1~B6을 순서대로 재현하고 기대값과 대조한다.
세션마다 다른 사용자를 써서 서로 상태를 공유하지 않는다(corpus 규칙과 같음).
k6/corpus(Step 7)가 생기기 전의 개발용 확인 도구다. 결과 판정은 사람이 읽는 표로 출력한다.

  python3 deploy/compose/tools/scenarios.py            # 리셋 후 실행
  python3 deploy/compose/tools/scenarios.py --dump out.json   # 응답·DB·WireMock journal도 저장
"""
import argparse
import json
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent.parent  # deploy/compose
ORDER, COUPON, PAYMENT, WIREMOCK = (
    "http://localhost:8085", "http://localhost:8091", "http://localhost:8086", "http://localhost:8089")
FIXED = "2026-09-01T00:00:00"

results = []   # (id, 설명, ok, 관측)
trace = []     # 요청/응답 기록 (--dump)


def http(method, url, body=None, user=None):
    headers = {"Content-Type": "application/json"}
    if user is not None:
        headers["X-User-Id"] = str(user)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            status, raw = r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read().decode()
    try:
        parsed = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        parsed = raw
    trace.append({"method": method, "url": url, "user": user, "body": body, "status": status, "response": parsed})
    return status, parsed


def sql(svc, query):
    out = subprocess.run(
        ["docker", "compose", "exec", "-T", f"mysql-{svc}-legacy", "sh", "-c",
         f'mysql -N -B -u root -p"$MYSQL_ROOT_PASSWORD" {svc}_db -e "{query}" 2>/dev/null'],
        cwd=HERE, capture_output=True, text=True, check=True).stdout
    return [line.split("\t") for line in out.strip().splitlines() if line]


def journal():
    with urllib.request.urlopen(WIREMOCK + "/__admin/requests") as r:
        reqs = json.load(r)["requests"]
    # WireMock은 최신순으로 준다. 도착 순서로 뒤집는다.
    return [{"method": x["request"]["method"], "url": x["request"]["url"],
             "status": x["responseDefinition"]["status"], "body": x["request"].get("body", "")}
            for x in reversed(reqs)]


def settle(timeout=30):
    """비동기 처리(Kafka consumer)가 끝날 때까지 기다린다.

    order-service consumer group의 lag이 0이면 받은 이벤트를 모두 처리하고 offset까지 커밋한 것이다.
    Kafka가 없는 구성(Step 4 이전)에서는 아무것도 하지 않는다.
    """
    if subprocess.run(["docker", "compose", "ps", "-q", "kafka-legacy"], cwd=HERE,
                      capture_output=True, text=True).stdout.strip() == "":
        return
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        out = subprocess.run(
            ["docker", "compose", "exec", "-T", "kafka-legacy", "/opt/kafka/bin/kafka-consumer-groups.sh",
             "--bootstrap-server", "localhost:9092", "--describe", "--group", "order-service"],
            cwd=HERE, capture_output=True, text=True).stdout
        rows = [l.split() for l in out.splitlines() if l.startswith("order-service")]
        # GROUP TOPIC PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG ...
        # LAG "-"는 커밋된 offset이 없다는 뜻이다. 토픽이 비어 있으면(LOG-END 0) 처리할 것도 없다.
        if rows and all(r[5] == "0" or (r[5] == "-" and r[4] == "0") for r in rows):
            return
        time.sleep(0.3)
    raise RuntimeError("consumer lag did not reach 0 within timeout")


def check(rid, desc, ok, observed):
    results.append((rid, desc, bool(ok), observed))


def place(user, coupon=None):
    body = {"shippingAddressId": 1, "billingAddressId": 1, "currency": "INR"}
    if coupon:
        body["couponCode"] = coupon
    return http("POST", ORDER + "/orders/place", body, user)


def get_order(oid, user):
    return http("GET", f"{ORDER}/orders/order/{oid}", user=user)


def verify(txn, pid):
    r = http("POST", f"{PAYMENT}/payments/verify?orderId={txn}&paymentId={pid}")
    settle()
    return r


def cancel(oid, user):
    return http("PUT", f"{ORDER}/orders/{oid}/cancel", user=user)


def amt(v):
    return None if v is None else float(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump")
    ap.add_argument("--no-reset", action="store_true")
    args = ap.parse_args()

    if not args.no_reset:
        subprocess.run(["./reset.sh"], cwd=HERE, check=True, capture_output=True)

    # --- S1 정상 주문(쿠폰 없음) -> 결제 확정 -> 조회
    s, o = place(101)
    oid, txn = o["orderId"], o.get("transactionId")
    check("S1-a", "정상 주문(쿠폰 없음): 200, 100,000원, PENDING/UNPAID",
          s == 200 and amt(o["totalAmount"]) == 100000 and (o["orderStatus"], o["paymentStatus"]) == ("PENDING", "UNPAID"),
          f"{s} total={o['totalAmount']} {o['orderStatus']}/{o['paymentStatus']}")
    check("S1-b", "가짜 PG 결정적 transactionId = order_{orderId}", txn == f"order_{oid}", txn)
    check("S1-c", "주문 createdAt 고정 시각", o["createdAt"] == FIXED, o["createdAt"])
    pay = sql("payment", f"SELECT status,created_at,amount FROM payments WHERE order_id={oid}")
    check("S1-d", "결제 행 CREATED, createdAt 고정 시각",
          pay and pay[0][0] == "CREATED" and pay[0][1].startswith("2026-09-01 00:00:00"), pay)
    n0 = len(journal())
    s, r = verify(txn, "pay_S1")
    verify_calls = journal()[n0:]
    check("S1-e", "/payments/verify 200", s == 200, f"{s} {r}")
    s, g = get_order(oid, 101)
    check("S1-f", "결제 확정 후 CONFIRMED/PAID", (g["orderStatus"], g["paymentStatus"]) == ("CONFIRMED", "PAID"),
          f"{g['orderStatus']}/{g['paymentStatus']}")
    check("S1-g", "재조회 금액 소수점 표기(생성 응답과 다름 -> 정규화 대상)", True,
          f"place={o['totalAmount']!r} get={g['totalAmount']!r}")
    s, lst = http("GET", ORDER + "/orders/my-orders", user=101)
    check("S1-h", "조회 /orders/my-orders", s == 200 and [x["orderId"] for x in lst] == [oid], f"{s} {[x['orderId'] for x in lst]}")
    s, lst = http("GET", ORDER + "/orders/history", user=101)
    check("S1-i", "조회 /orders/history", s == 200 and len(lst) == 1, f"{s} n={len(lst)}")

    # --- S2 정상 주문(고정 할인 쿠폰) + B1 기록 누락
    s, o = place(102, "FIX5000")
    check("S2-a", "쿠폰 FIX5000: 95,000원", s == 200 and amt(o["totalAmount"]) == 95000, f"{s} total={o['totalAmount']}")
    usage = sql("coupon", "SELECT count(*) FROM coupon_usage")[0][0]
    check("B1-a", "쿠폰 사용 기록 누락: coupon_usage 0건", usage == "0", f"coupon_usage={usage}")
    s, o2 = place(102, "FIX5000")
    check("B1-b", "같은 사용자가 같은 쿠폰 재사용 -> 다시 할인", s == 200 and amt(o2["totalAmount"]) == 95000,
          f"{s} total={o2['totalAmount']}")

    # --- S3 퍼센트 쿠폰(최대 할인 적용)
    s, o = place(103, "PCT10")
    check("S3", "쿠폰 PCT10(10%, 최대 8,000): 92,000원", s == 200 and amt(o["totalAmount"]) == 92000,
          f"{s} total={o['totalAmount']}")

    # --- B3 만료 / 최소 금액 미달
    s, o = place(104, "EXPIRED")
    check("B3-a", "만료 쿠폰 -> 정가 100,000원, 200", s == 200 and amt(o["totalAmount"]) == 100000, f"{s} total={o['totalAmount']}")
    s, o = place(105, "MIN200K")
    check("B3-b", "최소 금액 미달 -> 정가 100,000원, 200", s == 200 and amt(o["totalAmount"]) == 100000, f"{s} total={o['totalAmount']}")

    # --- S6 결제 실패 (99,999원 -> 가짜 PG 거절)
    s, o = place(106, "PGFAIL1")
    check("S6", "결제 실패: 99,999원, CANCELLED/FAILED, transactionId 없음",
          s == 200 and amt(o["totalAmount"]) == 99999 and (o["orderStatus"], o["paymentStatus"]) == ("CANCELLED", "FAILED")
          and o.get("transactionId") is None,
          f"{s} total={o['totalAmount']} {o['orderStatus']}/{o['paymentStatus']} txn={o.get('transactionId')}")

    # --- B1 사용 한도 무시
    r1 = place(107, "LIMIT1")[1]
    r2 = place(107, "LIMIT1")[1]
    check("B1-c", "usage_limit=1 쿠폰을 두 번 사용 -> 둘 다 97,000원",
          amt(r1["totalAmount"]) == 97000 and amt(r2["totalAmount"]) == 97000, f"{r1['totalAmount']}, {r2['totalAmount']}")

    # --- S8 취소 + B6
    s, o = place(108)
    s, c = cancel(o["orderId"], 108)
    check("S8", "주문 취소(PENDING) -> CANCELLED", s == 200 and c["orderStatus"] == "CANCELLED", f"{s} {c.get('orderStatus')}")
    s, c = cancel(o["orderId"], 108)
    check("B6-a", "이미 취소된 주문 재취소(IllegalStateException) -> 404", s == 404, f"{s} {c.get('message')}")
    s, c = get_order(o["orderId"], 999)
    check("B6-b", "남의 주문 조회(Unauthorized) -> 404", s == 404, f"{s} {c.get('message')}")

    # --- B4 취소된 주문을 verify가 확정
    s, o = place(109)
    cancel(o["orderId"], 109)
    s, r = verify(o["transactionId"], "pay_B4")
    s2, g = get_order(o["orderId"], 109)
    check("B4", "CANCELLED 주문을 /payments/verify가 CONFIRMED/PAID로",
          s == 200 and (g["orderStatus"], g["paymentStatus"]) == ("CONFIRMED", "PAID"),
          f"verify={s} -> {g['orderStatus']}/{g['paymentStatus']}")

    # --- B5 결제 완료 주문 취소 후에도 PAID
    s, o = place(110)
    verify(o["transactionId"], "pay_B5")
    s, c = cancel(o["orderId"], 110)
    check("B5", "PAID 주문 취소 -> CANCELLED인데 paymentStatus PAID 유지",
          s == 200 and (c["orderStatus"], c["paymentStatus"]) == ("CANCELLED", "PAID"),
          f"{s} {c['orderStatus']}/{c['paymentStatus']}")

    # --- B2 취소된 주문에 쿠폰 사용 기록이 허용됨 (status 필드명 불일치로 null)
    s, o = place(111)
    cancel(o["orderId"], 111)
    s, _ = http("POST", f"{COUPON}/coupons/use?orderId={o['orderId']}&code=FIX5000", user=111)
    rows = sql("coupon", f"SELECT order_id,used_at FROM coupon_usage WHERE order_id={o['orderId']}")
    check("B2", "커밋된 CANCELLED 주문에 /coupons/use -> 200, 기록됨(거절돼야 함)",
          s == 200 and len(rows) == 1, f"{s} rows={rows}")
    check("T-usedAt", "coupon_usage.used_at 고정 시각", rows and rows[0][1].startswith("2026-09-01 00:00:00"), rows)

    # --- 외부 호출 요약
    j = journal()
    by = {}
    for x in j:
        key = f"{x['method']} {x['url'].split('?')[0]}"
        key = "POST /shipments/initiate/{id}" if key.startswith("POST /shipments/initiate/") else key
        by[key] = by.get(key, 0) + 1
    pg_decline = [x for x in j if x["url"] == "/v1/orders" and x["status"] == 400]
    check("X-pg", "가짜 PG 거절 호출 1건(99,999원)", len(pg_decline) == 1, f"{len(pg_decline)}")
    unmatched = [x for x in j if x["status"] == 404]
    check("X-unmatched", "WireMock 미매핑(404) 호출 0건", not unmatched, [f"{x['method']} {x['url']}" for x in unmatched])

    width = max(len(r[1]) for r in results)
    fails = 0
    for rid, desc, ok, obs in results:
        fails += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {rid:<11} {desc:<{width}}  | {obs}")
    print("\n외부 호출(WireMock journal):")
    for k, v in sorted(by.items()):
        print(f"  {v:>3}  {k}")
    print("\nS1 verify 한 건이 만든 외부 호출(도착 순서):")
    for x in verify_calls:
        action = json.loads(x["body"]).get("action") if x["url"] == "/audit/log" else ""
        print(f"  {x['method']} {x['url']} {action}")
    print(f"\n{len(results) - fails}/{len(results)} PASS")

    if args.dump:
        dump = {"requests": trace, "wiremock": j, "s1_verify_calls": verify_calls,
                "db": {svc: {t: sql(svc, f"SELECT * FROM {t} ORDER BY 1") for t in tables}
                       for svc, tables in {"order": ["orders", "order_items", "order_status_history"],
                                           "coupon": ["coupons", "coupon_usage"],
                                           "payment": ["payments", "refunds"]}.items()}}
        pathlib.Path(args.dump).write_text(json.dumps(dump, ensure_ascii=False, indent=1))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
