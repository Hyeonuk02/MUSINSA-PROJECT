# 결함 카탈로그 PF (E2)

> 기준선: Legacy = `prince-mart/*-service:legacy`(A/A `aa-003`, B1 0). 결함 New = 같은 소스 + `PF<n>-<svc>.patch`(브랜치 없음, LEGACY_CHANGES L-C4).
> **기대 판정은 결함 run 전에 커밋**(`fault-expectations.json`, 이 문서의 "기대" 열). "실제"는 run 뒤에 채운다. 엔진은 결함을 보고 고치지 않는다.
> 판정: CV = Contract Violation, UNC = Uncertain, IMP = Improvement. pair = `R<id>/<service>.<kind>.<n>`. 처분(CV): fault | accept (legacy-decision-log L16).
> 형식은 hyeonuk-dev `docs/fault-catalog.md`·`fault-expectations.json`과 맞췄다.

| id | 패치 | 종류 | 기대(target pair) | 실제 | 보일 축 |
|---|---|---|---|---|---|
| PF1 | `PF1-payment` | 진짜 결함 | 주문 15건 `wiremock.external.1` CV(fault). R11(PGFAIL) SAME | | external 호출 `POST /v1/orders` 1→2 |
| PF2 | `PF2-payment` | 진짜 결함 | verify 5건 `payment.http.1` + verify 뒤 조회·취소 7건 `order.http.1` = 12 CV(fault), legacyOnly 15, dbstate 다름 | | events 1→0, consume·consumer external 없음, 응답 orderStatus/paymentStatus |
| PF3 | `PF3-order` | 진짜 결함 | 주문 16건 × (`order.http.1`, `wiremock.external.1`) = 32 CV(fault) | | outbound·external 순서(reduce-stock ↔ cart/clear) |
| PF4 | `PF4-order` | 진짜 결함 | 성공 취소 4건 × (`order.http.1`, `wiremock.external.1`) = 8 CV(fault) | | outbound `add-stock-bulk` 없음, external 2→1 |
| PF5 | `PF5-order` | 정상 리팩터링 | 취소 5건 `order.http.1` UNC → learn(R24·R27) 라벨 후 성공 취소 4건 IMP, R16(404) UNC 유지 | | SELECT 2→1, fingerprint(fetch join) |
| PF6 | (예정) | 정상 변경 | Payment Boot 4 업그레이드 — 패치 후 run 전에 따로 등록 | | |
| PF7 | `PF7-order` | 승인된 개선(B4) | R20 consume·R21 조회 IMP(승인 규칙), 다른 consume 4건 UNC → learn(R2·R23) 후 IMP, legacyOnly R20 external, dbstate 다름 | | 취소 주문 consume: 쓰기·outbound 없음, R21 CONFIRMED/PAID → CANCELLED/UNPAID, SELECT +1 |
| PF8 | `PF8-order` | 성능 | my-orders 2건(R4, R32) 기본 UNC / `max_selects`(my-orders 1) 선언 시 CV | | SELECT 1→2, 1→3 (N+1) |
| PF9 | `PF9-order` | 승인된 개선(재확정 멱등) | R35 consume IMP(승인 규칙), 다른 consume 4건 UNC → learn 후 IMP, legacyOnly R35 external, dbstate 다름 | | 재확정 consume: 쓰기·outbound 없음, SELECT +1 |
| PF10 | `PF10-order` | 승인된 개선(B1) | 첫 사용 4건(R6·R8·R11·R12) × 4 pair + 재사용 2건(R7·R13) × 4 pair = 24 CV(accept), legacyOnly 4, dbstate 다름 | | coupon `/use`·역조회 404→200, use가 결제 뒤로, R7·R13 alreadyUsed → 정가(B3) |

## 기대를 정하며 확인한 것 (A/A Evidence와 코드)

- **PF1** — 중복 호출은 첫 `createOrder`가 성공한 뒤에만 일어난다. R11은 99,999원이라 첫 호출이 거절(400) → 예외 → 두 번째 호출 없음.
  PG 호출은 Feign이 아니라 `payment.http` outbound에 없고 external(WireMock journal)에서만 보인다.
- **PF2** — verify의 external 4건(audit·shipments·audit·notification)은 모두 Order consumer가 부른다. 이벤트가 없으면
  `kafka.event.1`·`order.consume.1`·`wiremock.external.1`이 legacy에만 생긴다. 주문 상태는 consumer가 바꾸므로
  verify 뒤 그 주문을 읽는 R3·R4·R5(S01)·R21(S09)·R24·R25(S10)·R36(S13)의 응답이 달라진다. S12 목록(R31·R32)은 verify가 없어 같다.
- **PF4** — 결제 실패 보상(`handlePaymentFailure`)은 `cancelOrder`가 아니므로 R11은 같다. 404 재취소(R16)는 addStock 전에 실패.
- **PF5** — 성공 취소는 SELECT 2개(orders, order_items)가 1개로, R16은 SELECT 1개가 fetch join 1개로 바뀐다(개수 같음, fingerprint 교체).
  learn 라벨(R24·R27)은 성공 취소 유형만 덮으므로 R16은 라벨 후에도 UNC로 등록했다(규칙 일반화의 한계를 잰다).
  `Order.items`는 `@JsonIgnore`라 응답은 같다.
- **PF7·PF9** — 추가된 `getOrderByIdForAdmin`은 `SimpleJpaRepository.findById`(readOnly 트랜잭션)라 **모든 consume**에 SELECT 1개와
  트랜잭션 1쌍이 늘어난다. 그래서 건너뛰지 않는 consume도 UNC 대상이다(learn R2·R23).
- **PF8** — legacy `getMyOrders`는 items를 읽지 않는다(`@JsonIgnore`). R4는 주문 1건(+1), R32는 2건(+2). `/orders/history`는 다른 메서드.
- **PF10** — `placeOrder` 트랜잭션은 `payments/process`까지 감싸므로 `afterCommit`으로 옮긴 `useCoupon`은 결제 뒤에 불린다.
  주문이 커밋돼 Coupon의 역조회 `GET /orders/order/{id}`가 200이 되고 `coupon_usage`가 기록된다(+ 감사 `COUPON_CONSUMED`).
  그 결과 같은 사용자의 두 번째 주문(S02 R7, S07 R13)은 validate가 `alreadyUsed`로 `valid:false` → B3 경로로 정가 100,000원,
  결제 금액이 바뀌고 use 호출이 없다. R28(S11 직접 use, 앞선 사용 없음)·R37·R38은 같다.

## 실행 (결함마다)

```
baseline/faults/build.sh PF<n>          # prince-mart/<svc>-service:PF<n>
baseline/faults/deploy.sh PF<n>         # New 스택만 교체, NEW_VERSION=prince-mart-PF<n>
python3 baseline/k6/run.py --run-id pf<n> --iterations 3
python3 baseline/engine/compare.py baseline/runs/pf<n>-1    # 실현 확인: B1 차이가 기대 대상에만
baseline/faults/deploy.sh legacy        # 되돌림
```
