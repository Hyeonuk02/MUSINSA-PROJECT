# 결함 카탈로그 v1 (Phase 3.6)

> 기준선: `phase3.5-v1.4`(`120b212`, Order 전면 Kotlin). Legacy = `order-app:phase3.3-base` 고정.
> 결함마다 브랜치 `fault/F<n>` = 기준선 위 커밋 1개, 이미지 `order-app:phase3.6-F<n>`. Phase 4 입력 = `git diff phase3.5-v1.4..fault/F<n>`.
> **기대 판정은 F run 전에 등록**(`docs/fault-expectations.json`, 이 문서의 "기대" 열). 실제는 run 뒤에 채운다. 엔진은 결함을 보고 고치지 않는다.
> 판정: CV = Contract Violation, UNC = Uncertain, IMP = Improvement. 가시성 B0/B1/C = 그 arm에서 target pair가 DIFF(B0·B1) 또는 기대 판정(C)으로 보였는지.

| id | 브랜치·커밋 | 변경 클래스 | 종류 | 기대 판정(target pair) | 실제 | 보이는 축 | B0 / B1 / C |
|---|---|---|---|---|---|---|---|
| F0 | — (baseline 기지 차이, 주입 아님) | — | 입력 검증 경로 차이(Java 409 vs Kotlin 400) | R000047 CV, R000048 SAME | **R000047 CV ×3, R000048 SAME ×3** — 일치 | response.status 409→400, content-type, writeSet `insert orders` vs ∅, transactions ROLLED_BACK vs 없음 | ✔ / ✔ / ✔ |
| F1 | | | 진짜 결함 | R000008 CV | | 외부 호출 2회(세션 규칙), events, hop `0.e1`(New만) | |
| F2 | | | 진짜 결함 | 주문 생성 9·조회(있음) 10·결제 8 = 27 pair CV + dbstate | | writeSet, 응답 items, dbstate | |
| F3 | | | 진짜 결함 | 첫 결제 7 pair CV | | 타임라인 publish.seq < COMMIT_BEGIN | |
| F4 | | | 진짜 결함 | R000037·R000038 CV + dbstate | | transactions outcome, writeSet, 다음 GET 200 vs 404, dbstate | |
| F5 | | | 정상 리팩터링 | 조회 13 pair UNC → learn 라벨 후 IMP | | dbRead 횟수·fingerprint, callTree | |
| F6 | | | 승인된 개선 | 생성 8·조회 10·결제 8 = 26 pair IMP(사전 규칙) | | response.addedFields itemCount | |
| F7 | | | 설정 변경 결함 | R000041·R000042 CV + dbstate | | 응답 status, externalCalls status, 발행 없음(hop), 다음 GET 값, dbstate | |
| F8 | | | 성능 계약 | 조회(있음) 10 pair: 기본 UNC / maxSelects 선언 CV | | dbRead 횟수, callTree | |
| F9 | | | 진짜 결함 | 쿠폰 주문 생성 4 pair CV | | externalCalls, hop `0.h2`(New만) | |

## F0 — baseline 기지 차이 (S011, 주입 아님)

`p36-base-1..3`(new = `phase3.5-v1.4`, corpus v2.1): 60 pair 중 59 SAME + R000047 CV, 세 run 동일, Undelivered 0, degraded 0, dbstate 일치. R000047(`POST /api/orders`, 항목에 sku 없음): Legacy(Java) — `insert into orders` 뒤 항목 INSERT 단계에서 실패 → `DataIntegrityViolationException` → 컨트롤러 `onConflict` **409** `{"error":"ORDER_KEY_EXISTS","orderKey":null}`, `ROLLED_BACK`. New(Kotlin v1.4) — `ItemRequest(sku: String)` 역직렬화 실패 → **400**, 본문 없음, SQL·트랜잭션 없음. R000048(조회)은 양쪽 404 → SAME. 3.5 보고서의 잠재 차이가 실측으로 확인됐다. F run의 정상 경로 오탐은 이 CV를 뺀(= baseline 판정과 비교한) pair로 센다.
