# 결함 카탈로그 v1 (Phase 3.6)

> 기준선: `phase3.5-v1.4`(`120b212`, Order 전면 Kotlin). Legacy = `order-app:phase3.3-base` 고정.
> 결함마다 브랜치 `fault/F<n>` = 기준선 위 커밋 1개, 이미지 `order-app:phase3.6-F<n>`. Phase 4 입력 = `git diff phase3.5-v1.4..fault/F<n>`.
> **기대 판정은 F run 전에 등록**(`docs/fault-expectations.json`, 이 문서의 "기대" 열). 실제는 run 뒤에 채운다. 엔진은 결함을 보고 고치지 않는다.
> 판정: CV = Contract Violation, UNC = Uncertain, IMP = Improvement. 가시성 B0/B1/C = 그 arm에서 target pair가 DIFF(B0·B1) 또는 기대 판정(C)으로 보였는지.

| id | 브랜치·커밋 | 변경 클래스 | 종류 | 기대 판정(target pair) | 실제 | 보이는 축 | B0 / B1 / C |
|---|---|---|---|---|---|---|---|
| F0 | — (baseline 기지 차이, 주입 아님) | — | 입력 검증 경로 차이(Java 409 vs Kotlin 400) | R000047 CV, R000048 SAME | **R000047 CV ×3, R000048 SAME ×3** — 일치 | response.status 409→400, content-type, writeSet `insert orders` vs ∅, transactions ROLLED_BACK vs 없음 | ✔ / ✔ / ✔ |
| F1 | `fault/F1` `da92b8e` | `OrderService`(+1 −3) | 진짜 결함 | R000008 CV | R000008 CV ×3 ✔. 정상 경로: engine-v1.1에서 R000007도 CV(세션 귀속) → D-6 → engine-v1.2 재판정 R000007 SAME(오탐 0), sessionViolations `idem-R000007` legacy 1 / new 2 → R000008 | externalCalls, events, hop `0.e1`(New만), 세션 규칙 `idem-R000007` legacy 1 / new 2 | B0 ✔ / B1 ✘ / C ✔ — 응답·SQL에 흔적이 없어 B1은 놓치고 B0(원문 DIFF)·C(CV)는 잡음 |
| F2 | `fault/F2` `a131294` | `Order`(+1 −2, cascade 제거) | 진짜 결함 | 주문 생성 9·조회(있음) 10·결제 8 = 27 pair CV + dbstate | 27/27 CV ×3 ✔, dbstate 위반(order_items 10 vs 0), 정상 경로 오탐 0 | writeSet(생성 9), 응답 items(조회·결제 18), dbstate | B0 ✔ / B1 ✔ / C ✔ |
| F3 | | | 진짜 결함 | 첫 결제 7 pair CV | | 타임라인 publish.seq < COMMIT_BEGIN | |
| F4 | | | 진짜 결함 | R000037·R000038 CV + dbstate | | transactions outcome, writeSet, 다음 GET 200 vs 404, dbstate | |
| F5 | | | 정상 리팩터링 | 조회 13 pair UNC → learn 라벨 후 IMP | | dbRead 횟수·fingerprint, callTree | |
| F6 | | | 승인된 개선 | 생성 8·조회 10·결제 8 = 26 pair IMP(사전 규칙) | | response.addedFields itemCount | |
| F7 | | | 설정 변경 결함 | R000041·R000042 CV + dbstate | | 응답 status, externalCalls status, 발행 없음(hop), 다음 GET 값, dbstate | |
| F8 | | | 성능 계약 | 조회(있음) 10 pair: 기본 UNC / maxSelects 선언 CV | | dbRead 횟수, callTree | |
| F9 | | | 진짜 결함 | 쿠폰 주문 생성 4 pair CV | | externalCalls, hop `0.h2`(New만) | |

## F0 — baseline 기지 차이 (S011, 주입 아님)

`p36-base-1..3`(new = `phase3.5-v1.4`, corpus v2.1): 60 pair 중 59 SAME + R000047 CV, 세 run 동일, Undelivered 0, degraded 0, dbstate 일치. R000047(`POST /api/orders`, 항목에 sku 없음): Legacy(Java) — `insert into orders` 뒤 항목 INSERT 단계에서 실패 → `DataIntegrityViolationException` → 컨트롤러 `onConflict` **409** `{"error":"ORDER_KEY_EXISTS","orderKey":null}`, `ROLLED_BACK`. New(Kotlin v1.4) — `ItemRequest(sku: String)` 역직렬화 실패 → **400**, 본문 없음, SQL·트랜잭션 없음. R000048(조회)은 양쪽 404 → SAME. 3.5 보고서의 잠재 차이가 실측으로 확인됐다. F run의 정상 경로 오탐은 이 CV를 뺀(= baseline 판정과 비교한) pair로 센다.

## F1 — 결제 멱등 검사 제거

변경(`fault/F1`): `OrderService.pay`의 `Order.PAID ->` 분기를 `Order.PAID if idempotencyKey != order.idempotencyKey -> ALREADY_PAID`로 — 같은 키로 다시 오면 PAID 분기를 지나 게이트웨이를 다시 호출하고 `markPaid`·`OrderPaid` 발행까지 한다(발행 로직은 그대로).
실제(`p36-F1-1..3`, 세 run 동일): R000008(S002 같은 키 재결제) New에서 charge 1회 + `order.paid` 발행(ack ok, `0.e1` → Coupon no-op 소비) → CV. 응답은 같은 transactionId(WireMock이 키에서 결정론적 생성)라 동일, `markPaid`가 같은 값이라 UPDATE 없음 → **응답·SQL 축에는 흔적 없음**. engine-v1.1에서는 R000007도 CV — 세션 규칙 위반이 같은 키를 가진 pair 전부에 붙는 3.4 귀속 규칙 때문. D-6으로 귀속 규칙을 일반화(engine-v1.2: Legacy와 다른 기여를 한 pair에만)한 뒤 같은 run 재판정: R000007 SAME, R000008만 CV. **귀속 규칙은 F1 결과를 본 뒤 일반화했다.**

## F2 — order_items INSERT 누락

변경(`fault/F2`): `Order.items`의 `cascade = [CascadeType.ALL], orphanRemoval = true` 제거(Kotlin 전환 때 흔히 빠뜨리는 매핑 옵션 형태). 주문 행은 저장되고 항목은 메모리에만 남는다.
실제(`p36-F2-1..3`, 세 run 동일): 생성 9 pair(쿠폰 400 롤백 R000037 포함) — 응답은 같고 `writeSet`만 다름(`insert order_items` 없음) → CV. 조회 10·결제 8 pair — 응답 `items`가 빈 배열 → `response_body_compatible` CV. dbstate order_items 10 → 0. 정상 경로(쿠폰·소비·404 조회·취소 409) 오탐 0.
