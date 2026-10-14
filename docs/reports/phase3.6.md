# Phase 3.6 보고서 — 결함 카탈로그 v1 + New v2

- 작업일: 2026-10-14
- 기준선: `phase3.5-v1.4`(`120b212`). Legacy `order-app:phase3.3-base`, Coupon 양쪽 `coupon-app:phase3.3-base`, 엔진 `engine-v1.1`, corpus v2.1
- 결과: **PASS** — baseline + F1~F9 각 3 run, **9/9 결함이 사전 등록한 기대 판정과 pair 단위로 일치**(target 92 pair + F8 maxSelects 10 pair), 정상 경로 오탐 0(F1은 engine-v1.1 기준 1 → D-6 귀속 규칙 engine-v1.2 기준 0), Undelivered 0·degraded 0(전 run), 오판정 0
- 진행: 준비·baseline → F1(v1.1에서 기대와 다름 → D-6 → v1.2 재판정 일치) → F2 → F3 → F4 → F5(learn 라벨 3, eval Uncertain 8→0) → F6 → F7 → F8(두 설정) → F9
- 결함 표: `docs/fault-catalog.md`, 기대 사전 등록: `docs/fault-expectations.json`, 누적: `docs/phase3-result.md`

## 0. 결정 필요 사항

없음. (D-6 세션 검사 귀속은 (A) + 일반 원칙으로 결정 → engine-v1.2, 아래 1.0b)

## 1. 끝난 기준별 결과

### 1.0 준비 · baseline

| 기준 | 결과 | 근거 |
|---|---|---|
| 태그 `phase3.3-base`(98c9356)·`phase3.5-v1.4`(120b212) push | PASS | `git push origin phase3.3-base phase3.5-v1.4` |
| settle 의미 정리(D19 보완) | PASS | `k6/barrier.py` 1단계 = 진입 + 부모가 선언한 settle, `barrier.json` `settleUndeclared`; `k6/run.js` settle 타임아웃 → `settleTimeouts`(degraded 아님); decision-log D19 보완 한 줄. 커밋 `ba6502b` |
| corpus v2.1 (S011) | PASS | `corpus/corpus-v2.1.json` 세션 11·요청 48, validate.py PASS, self-test 22/22(음성 fixture `sku-missing-without-flag` 추가) |
| WireMock 지연 스텁 | PASS | `gateway-charge-slow.json`(priority 1, 2000ms). p36-base-1 R000041 처리 시간 legacy 2029 ms / new 2034 ms(일반 결제 R000003 289 / 311 ms) |
| 엔진 `--contract`(F8 준비) | PASS | `verdict.py --contract`, `engine.contract` 기록, `contract-maxselects.yaml`, pytest 28 passed |
| baseline `p36-base` 3 run | PASS | 3 run 모두 60 pair = 59 SAME + R000047 CV, R000048 SAME, Undelivered 0, degraded 0, settleTimeouts 0, dbstate 일치, verify 3/3 PASS, run-meta `dirty: false`(rev `ba6502b`). `logs/phase3.6-base-{run,verify,verdict,check}.txt` |
| F0 기록 | PASS | `docs/fault-catalog.md` F0 |

### 1.0b engine-v1.2 — 세션 검사 귀속 규칙 (D-6, F1 결과를 본 뒤 일반화)

| 기준 | 결과 | 근거 |
|---|---|---|
| 귀속 규칙 구현(탐지 로직 무변경) | PASS | `engine/verdict.py` `_session_checks` — Legacy와 다른 기여를 한 pair에만 CV, 귀속 pair 없으면 pair 판정 그대로, 양쪽 동일 위반은 `bothStacks` 플래그. `summary.sessionViolations` 추가. `contract.yaml` 설명에 두 출력 명시 |
| 테스트 | PASS | pytest 33 passed — F1형(합계 다름 → 다른 pair만 CV) / 양쪽 2회(pair SAME + bothStacks) / coupon 전이 New만 깨짐(소비 홉 CV + sessionViolations) / 양쪽 깨짐(pair SAME + bothStacks) / fixture sessionViolations 빈 배열 |
| 이전 run 재판정(오염 확인) | PASS | p33-1..3, p35-base·v1.1~v1.4, p36-base 각 3 run × C·B0·B1 = 63 판정: **pair 판정 변경 0, 집계(summary)·runChecks 동일, sessionViolations []**. `logs/phase3.6-rejudge-engine-v1.2.txt` |
| F2 run 전 push | PASS | 이 커밋 |

**이 규칙은 F1 결과를 본 뒤 일반화했다.** 탐지 여부(R000008 CV)는 v1.1·v1.2에서 같아 탐지율에는 영향이 없고, F1의 정상 경로 오탐은 v1.1 기준 1(R000007 — 세션 귀속) / v1.2 기준 0이다. F2~F9는 v1.2가 사전 등록된 엔진이다. `docs/fault-expectations.json`은 바꾸지 않았다(F1 기대 R000008 CV는 맞는 기대였다).

### 1.1 F1 — 결제 멱등 검사 제거

| 기준 | 결과 | 근거 |
|---|---|---|
| 브랜치·커밋 1·이미지 | PASS | `fault/F1` = `da92b8e`(phase3.5-v1.4 위 1커밋, push), `order-app:phase3.6-F1`. `git diff phase3.5-v1.4..fault/F1`: `OrderService.kt` 1 file, +1 −3 (클래스 1) |
| 3 run, Undelivered 0, degraded 0 | PASS | `p36-F1-1..3` run.sh exit 0, verify 3/3 PASS(참고: `R000008/0.e1` new만 — 부모가 선언한 행동 차이), settleTimeouts 0, run-meta `dirty: false`(rev `2227518`), images.order new=phase3.6-F1. barrier new 기대 61(폐포가 `R000008/0.e1`을 기다림) |
| target R000008 CV | PASS | 사유: `externalCalls: legacy=[] new=[charge 200]`, `events.published 개수 0/1`, `hop_set: new만 ['0.e1']`, `gateway_calls_per_idem_key_le_1[idem-R000007]: legacy 1 / new 2` (+ Uncertain 후보 callTree·responseHash는 CV가 우선) |
| 정상 경로 오탐 0 | engine-v1.1 **FAIL** → engine-v1.2 **PASS** | v1.1: **R000007/0 CV**(baseline SAME), 사유는 세션 규칙 하나뿐(세션 귀속) — `logs/phase3.6-F1-check-engine-v1.1.txt`(v1.1 판정은 `runs/p36-F1-*/verdict-engine-v1.1.json`에 보존). v1.2(재실행 없이 같은 run 재판정): R000007 SAME, R000008만 CV, `sessionViolations: [{S002, gateway_calls_per_idem_key_le_1, idem-R000007, legacy 1, new 2, bothStacks false, attributedPairs [R000008/0]}]` — `logs/phase3.6-F1-check-engine-v1.2.txt` 기대와 일치 |
| 세 run 판정 동일 | PASS | v1.1: 3 run 모두 CV 3(R000007·R000008·R000047) + SAME 57 / v1.2: CV 2(R000008·R000047) + SAME 58 |
| B0 / B1 / C | B0 ✔ / B1 ✘ / C ✔ | B0 DIFF 2(R000008 + R000047) — R000008이 원문에서 보임. B1 DIFF 1(R000047만) — B1 축(응답·SQL)에는 R000008 차이가 없다(응답 동일, `markPaid`가 같은 값이라 UPDATE도 없음). C는 외부 호출·이벤트·hop·세션 규칙으로 잡음 |

해석: 멱등성 결함은 **응답과 SQL에 흔적이 없다**(B1 미탐) — 외부 호출 축과 세션 규칙이 있어야 잡힌다. 관측 매트릭스(3.7: "C만 잡는 것은 F1…")와 같은 결과.
로그: `logs/phase3.6-F1-{run,verify,verdict,check}.txt`

### 1.2 F2 — order_items INSERT 누락 (Order.items cascade 제거)

| 기준 | 결과 | 근거 |
|---|---|---|
| 브랜치·커밋 1·이미지 | PASS | `fault/F2` = `a131294`, `order-app:phase3.6-F2`. `Order.kt` 1 file +1 −2 (클래스 1) — `@OneToMany(mappedBy = "order", cascade = [ALL], orphanRemoval = true)` → `@OneToMany(mappedBy = "order")`. 커밋 전 스모크: New에 주문 행만 남고 항목 행 0, 예외 없음 |
| 3 run, Undelivered 0, degraded 0 | PASS | run.sh exit 0 ×3, verify 3/3 PASS, settleTimeouts 0, `dirty: false`(rev `b70a6b7`), new=phase3.6-F2 |
| target 27 pair CV (생성 9·조회 10·결제 8) | PASS | 27/27 ×3. 위반 축: `writeSet`(생성 9 — `insert order_items` 없음), `response_body_compatible`(조회·결제 18 — 응답 items 사라짐) |
| dbstate | PASS(기대대로 위반) | `dbstate_equal` False — order_items legacy 10건 / new 0건 |
| 정상 경로 오탐 0 | PASS | baseline과 다른 non-target 0 (CV 28 = target 27 + F0 R000047) |
| 세 run 판정 동일 | PASS | CV 28 + SAME 32 ×3 |
| B0 / B1 / C | ✔ / ✔ / ✔ | target 27 중 B0 DIFF 27, B1 DIFF 27(쓰기 문장·응답 모두 B1 축), C CV 27 |

해석: 생성 응답은 메모리상 items가 있어 **응답만 보면 정상**이다 — 생성 pair는 쓰기 집합(writeSet)으로만, 그 뒤 조회·결제 pair는 응답 items로, run 전체는 dbstate로 세 겹에서 잡혔다. 로그 `logs/phase3.6-F2-{run,verify,verdict,check,summary}.txt`

### 1.3 F3 — OrderPaid를 @EventListener로 (커밋 전 동기 발행)

| 기준 | 결과 | 근거 |
|---|---|---|
| 브랜치·커밋 1·이미지 | PASS | `fault/F3` = `12482f0`, `order-app:phase3.6-F3`. `OrderEventPublisher.kt` 1 file — `@TransactionalEventListener(AFTER_COMMIT)` → `@EventListener` |
| 3 run, Undelivered 0, degraded 0 | PASS | run.sh exit 0 ×3, verify 3/3 PASS, settleTimeouts 0, `dirty: false`(rev `0a7c1f8`), new=phase3.6-F3 |
| target 첫 결제 7 pair CV | PASS | 7/7 ×3, 위반 축은 `publish_after_commit_begin` 하나뿐 |
| 정상 경로 오탐 0 | PASS | non-target 0 (CV 8 = 7 + F0) |
| 세 run 판정 동일 | PASS | CV 8 + SAME 52 ×3 |
| B0 / B1 / C | ✔ / ✘ / ✔ | B0 DIFF 7(seq 원문), **B1 DIFF 0**, C CV 7 |

타임라인(p36-F3-1 R000003): Legacy `SELECT(1) < CALL(2) < SELECT(3) < COMMIT_BEGIN(4) < UPDATE(5) < PUBLISH(6) < COMPLETED(7)` / New `SELECT(1) < CALL(2) < **PUBLISH(3)** < SELECT(4) < COMMIT_BEGIN(5) < UPDATE(6) < COMPLETED(7)`. 응답·SQL 집합·callTree·이벤트 내용·ack·소비 Evidence가 모두 같고 **순서만** 다르다 — D16(단일 seq 타임라인 + COMMIT_BEGIN)이 없으면 보이지 않는 결함. 로그 `logs/phase3.6-F3-*.txt`

### 1.4 F4 — 쿠폰 실패 시 롤백 누락

| 기준 | 결과 | 근거 |
|---|---|---|
| 브랜치·커밋 1·이미지 | PASS | `fault/F4` = `f83e211`, `order-app:phase3.6-F4`. `OrderService.kt` 1줄 — `create`의 `@Transactional` → `@Transactional(noRollbackFor = [CouponClient.CouponFailure::class])`. 예외는 그대로 컨트롤러로 가서 400 본문은 같고, 트랜잭션은 커밋된다(지시의 "트랜잭션 안에서 삼켜 400은 그대로, 롤백 안 함"을 한 줄 설정 실수로 구현) |
| 3 run, Undelivered 0, degraded 0 | PASS | run.sh exit 0 ×3, verify 3/3 PASS, settleTimeouts 0, `dirty: false`(rev `6f6456d`), new=phase3.6-F4 |
| target R000037·R000038 CV + dbstate | PASS | 2/2 ×3. R000037(USED 쿠폰 주문, 응답 400 동일): `transactions.outcomes` legacy `[COMPLETED ROLLED_BACK]` / new `[COMMIT_BEGIN, COMPLETED COMMITTED]`. R000038(그 주문 조회): `response.status` 404 → 200. dbstate 위반: orders 8 → 9, order_items 10 → 11 |
| 정상 경로 오탐 0 | PASS | non-target 0 (CV 3 = 2 + F0) |
| 세 run 판정 동일 | PASS | CV 3 + SAME 57 ×3 |
| B0 / B1 / C | ✔ / △ / ✔ | B0 DIFF 2/2. **B1 DIFF 1/2** — R000038(다음 조회 404→200)만 보이고 R000037은 못 본다(응답 400·SQL 문장이 같고 차이는 트랜잭션 결과뿐). C CV 2/2 |

해석: 결함이 일어난 요청(R000037)은 응답·SQL이 같아 **트랜잭션 outcome 축으로만** 잡히고, 결과는 다음 요청(R000038)의 응답과 dbstate로 번진다. 쓰기 집합은 같다(INSERT는 양쪽 다 실행됐고 롤백 여부만 다름) — writeSet이 아니라 transactions 축이 필요한 이유. 로그 `logs/phase3.6-F4-*.txt`

### 1.5 F5 — 주문 조회 JOIN FETCH 1쿼리 (정상 리팩터링) + 첫 learn 리뷰

| 기준 | 결과 | 근거 |
|---|---|---|
| 브랜치·커밋 1·이미지 | PASS | `fault/F5` = `1597c73`, `order-app:phase3.6-F5`. 2 files(클래스 2): `OrderRepository.kt` +5(`@Query("select o from Order o join fetch o.items where o.orderKey = :orderKey") findWithItemsByOrderKey`), `OrderService.kt` 1줄(`getByKey`가 그것을 사용). 커밋 전 스모크: HQL 유효, 항목 순서 유지(`order by line_no`), 404 경로 정상 |
| 3 run, Undelivered 0, degraded 0 | PASS | run.sh exit 0 ×3, verify 3/3 PASS, settleTimeouts 0, `dirty: false`(rev `9a6774f`), new=phase3.6-F5 |
| target 조회 13 pair UNCERTAIN(라벨 전) | PASS | 13/13 ×3(learn 5: R2·R4·R28·R30·R38 / eval 8: R6·R9·R11·R14·R34·R42·R46·R48). CV 0(F0 제외), 정상 경로 오탐 0 |
| learn 리뷰 | 3 유형 라벨 | `review.py list --split learn`(p36-F5-1): `5da05fdb147f` dbRead.countDelta 2→1(4건), `989c110b103e` callTree.sequenceReplaced findByOrderKey→findWithItemsByOrderKey(5건), `9a82df6b99b4` dbRead.fingerprintReplaced(404 조회 R38 — 단건 select → join select, 1건). 세 유형 모두 원인이 F5 코드 diff에서 짚힘 → `--as improvement`, reason "JOIN FETCH로 조회 통합, 쓰기 집합·응답 동일 — fault/F5(1597c73) …". 규칙 3개 `engine/rules/learned/{5da05fdb147f,989c110b103e,9a82df6b99b4}.yaml`(provenance: author Hyeonuk02, 2026-10-14, runId p36-F5-1, split learn, sessions S001·S006 / S001·S006·S008 / S008) |
| 재판정(라벨 후, 같은 run) | PASS | 3 run 모두 IMPROVEMENT 13(learn 5 + **eval 8**) + SAME 46 + CV 1(F0). 기대 `afterLearnLabels` 13/13 일치. 라벨 전 판정은 `runs/p36-F5-*/verdict-prelabel.json`에 보존 |
| **eval Uncertain 규칙 전→후** | **8 → 0** | learn 세션(5 pair)에서 만든 규칙 3개가 eval 세션 8 pair(404 조회 R11·R48 포함)의 Uncertain을 모두 Improvement로 — 3.7 Rule 재사용 효과의 첫 데이터 |
| B0 / B1 / C | ✔ / ✔ / ✔(분류) | target 13 중 B0 DIFF 13, B1 DIFF 13(SQL 횟수·fingerprint는 B1 축), C는 DIFF를 UNC → (리뷰 후) IMP로 분류 |

해석: B1도 "다르다"까지는 보지만 결함(CV)인지 개선인지 가르지 못한다. C는 기능 계약 축(응답·쓰기 집합·트랜잭션·이벤트)이 같고 실행 특성 축만 다르다는 것을 근거로 Uncertain으로 올리고, 사람이 learn 5 pair를 본 결과가 eval 8 pair로 재사용됐다. 로그 `logs/phase3.6-F5-*.txt`(리뷰 `logs/phase3.6-F5-review.txt`)

### 1.6 F6 — OrderView에 itemCount 추가 (승인된 개선, 사전 규칙)

| 기준 | 결과 | 근거 |
|---|---|---|
| 사전 승인 규칙(F6 run 전) | PASS | `9648cf1` `engine/rules/improvement.yaml` `order-view-item-count`: endpoint `*`, `response.addedFields [itemCount]`, provenance author·approvedBy·date 2026-10-14 |
| 브랜치·커밋 1·이미지 | PASS | `fault/F6` = `84bd197`, `order-app:phase3.6-F6`. `OrderView.kt` 1 file +2 −1(생성자 끝에 `itemCount: Int`, `from`에서 `items.size`) |
| 3 run, Undelivered 0, degraded 0 | PASS | run.sh exit 0 ×3, verify 3/3 PASS, settleTimeouts 0, `dirty: false`(rev `9648cf1`), new=phase3.6-F6 |
| target 26 pair IMPROVEMENT | PASS | 26/26 ×3(생성 8·조회 10·결제 8 — 응답에 OrderView가 있는 pair 전부), 적용 규칙 `order-view-item-count` 26회. 쿠폰 400(R37)·404 조회·취소 409·소비·쿠폰 pair는 SAME |
| 정상 경로 오탐 0 | PASS | non-target 0 (CV 1 = F0) |
| 오판정(learn 규칙이 가림) | 0 | F5 learned 규칙 3개가 있는 상태로 판정 — 적용된 것은 사전 규칙뿐, learned 규칙 적용 0 |
| B0 / B1 / C | ✔ / ✔ / ✔(분류) | B0 DIFF 26/26, B1 DIFF 26/26(응답 body), C IMPROVEMENT 26 — B1은 개선을 결함과 구분하지 못한다 |

로그 `logs/phase3.6-F6-*.txt`

### 1.7 F7 — 결제 게이트웨이 read timeout 1s (설정 변경 결함)

| 기준 | 결과 | 근거 |
|---|---|---|
| 브랜치·커밋 1·이미지 | PASS | `fault/F7` = `31363ce`, `order-app:phase3.6-F7`. `PaymentGatewayClient.kt` 1줄(+import) — `SimpleClientHttpRequestFactory().apply { setReadTimeout(Duration.ofSeconds(1)) }`. **계획의 "3s→1s"와 다른 점**: Legacy·기준선은 read timeout을 설정하지 않는다(SimpleClientHttpRequestFactory 기본 = 무제한). F7은 "무제한 → 1s"이며, 2s 지연 결제에서 Legacy 성공·New 실패라는 시험 의미는 같다(5절) |
| 3 run, Undelivered 0, degraded 0 | PASS | run.sh exit 0 ×3, verify 3/3 PASS(참고: `R000041/0.e1` legacy만 — 부모가 선언한 행동 차이), `dirty: false`(rev `4e34a7b`), new=phase3.6-F7. **settleTimeouts `R000041/new/0.e1`**(지표), barrier new 1단계 기대 59 = 진입 48 + 선언된 settle 11, `settleUndeclared: R000041/0.e1` → 엔진. **D19 보완(settle 의미 정리)이 없었다면 여기서 degraded·barrier 미달로 run이 멈췄다** |
| target R000041·R000042 CV + dbstate | PASS | 2/2 ×3. R000041: `response.status 200 → 502`(`PAYMENT_FAILED`), `externalCalls` charge status 200 → **0**(타임아웃), `writeSet` `update orders` → ∅, `events.published 1 → 0`, `hop_set legacy만 0.e1`. R000042(그 주문 조회): `status PAID → CREATED`, `transactionId → null`. dbstate orders 해시 다름(count·sum은 같고 상태만) |
| 정상 경로 오탐 0 | PASS | non-target 0. 같은 지연 없는 결제 6건은 SAME(1s 안에 응답) |
| pair 집합 | 기대대로 | `R000041/0.e1`이 baseline에만(New는 발행이 없어 소비 홉이 없다) — hop_set으로 부모 pair에 나타남 |
| 세 run 판정 동일 | PASS | CV 3 + SAME 56 (pair 59) ×3 |
| B0 / B1 / C | ✔ / ✔ / ✔ | B0 DIFF 2/2, B1 DIFF 2/2(응답 status·body), C CV 2/2 |

로그 `logs/phase3.6-F7-*.txt`

### 1.8 F8 — 주문 조회 N+1 (성능 계약, 두 설정)

| 기준 | 결과 | 근거 |
|---|---|---|
| 브랜치·커밋 1·이미지 | PASS | `fault/F8` = `60edcda`, `order-app:phase3.6-F8`. 2 files(클래스 2): `OrderRepository.kt` +5(`@Query("select i from OrderItem i where i.order.orderKey = :orderKey and i.lineNo = :lineNo") findItem`), `OrderService.kt` +4 −1(`getByKey`가 항목마다 `findItem`). 커밋 전 스모크: 응답 정상 |
| 3 run, Undelivered 0, degraded 0 | PASS | run.sh exit 0 ×3, verify 3/3 PASS, settleTimeouts 0, `dirty: false`(rev `cb444fd`), new=phase3.6-F8 |
| 기본 contract(maxSelects 미선언) → 조회 10 pair UNCERTAIN | PASS | 10/10 ×3(learn 4 / eval 6). 항목: `dbRead.countDelta` 2→3(항목 1개 주문 7) · 2→4(항목 2개 주문 3), `callTree.sequenceReplaced`(`OrderRepository.findItem` 추가). 404 조회 3건은 항목이 없어 SAME |
| `--contract contract-maxselects.yaml`(order.get: 2) → CV | PASS | 같은 run 재판정(클러스터 재실행 없음) 10/10 CV ×3, `max_selects[order.get]: new readCount 3 > 2`(또는 4 > 2). `verdict-maxselects.json` `engine.contract = contract-maxselects.yaml`, sha256 `6d4b3c07…`. baseline(p36-base-1)을 같은 계약으로 판정해도 위반·경고 0(Legacy order.get = 2) |
| 정상 경로 오탐 0 | PASS | 두 설정 모두 non-target 0 |
| 오판정(learn 규칙이 가림) | 0 | F5 learned 규칙 3개(countDelta 2→1, callTree findWithItemsByOrderKey, fingerprint)가 있는 상태에서 판정 — F8 항목과 맞지 않아 적용 0. Uncertain으로 남음 |
| 세 run 판정 동일 | PASS | 기본: UNC 10 + CV 1(F0) + SAME 49 / maxSelects: CV 11 + SAME 49 ×3 |
| B0 / B1 / C | ✔ / ✔ / ✔ | B0 DIFF 10, B1 DIFF 10(SELECT 횟수는 B1 축 — 관측 매트릭스대로 F8은 B1에서도 보인다), C는 선언에 따라 UNC/CV |

해석: 같은 Evidence가 **선언(maxSelects)에 따라** Uncertain(사람이 볼 것)과 CV(계약 위반)로 갈린다 — D18 "판정은 선언된 해상도". F5(2→1)와 F8(2→3·4)은 모두 SELECT 수 변화지만, learn 규칙이 F5 유형만 설명하므로 F8은 Improvement로 새지 않았다. 로그 `logs/phase3.6-F8-*.txt`

### 1.9 F9 — 쿠폰 use 두 번 호출

| 기준 | 결과 | 근거 |
|---|---|---|
| 브랜치·커밋 1·이미지 | PASS | `fault/F9` = `f9f80ce`, `order-app:phase3.6-F9`. `OrderService.kt` +1(`couponClient.use(...)` 한 번 더) |
| 3 run, Undelivered 0, degraded 0 | PASS | run.sh exit 0 ×3, verify 3/3 PASS(참고: `0.h2` new만 4건 — 부모가 선언한 행동 차이), settleTimeouts 0, **barrier 2단계 폐포 라운드 1: 기대 new 64**(settle에 없는 `0.h2` 4건을 부모 선언으로 기다림), `dirty: false`(rev `57e99ec`), new=phase3.6-F9 |
| target 쿠폰 주문 생성 4 pair CV | PASS | 4/4 ×3(R27·R32·R36·R44). 위반: `externalCalls`(use 1회 → 2회), `hop_set new만 ['0.h2']`. 응답·쓰기 집합·dbstate 같음(두 번째 use는 같은 orderKey라 Coupon이 멱등 200, UPDATE 없음). R37(USED 쿠폰)은 첫 use가 409라 두 번째 호출이 없어 SAME |
| 정상 경로 오탐 0 | PASS | non-target 0 (CV 5 = 4 + F0) |
| 세 run 판정 동일 | PASS | CV 5 + SAME 55 ×3 |
| B0 / B1 / C | ✔ / ✘ / ✔ | B0 DIFF 4/4, **B1 DIFF 0/4**(응답·SQL 같음), C CV 4/4 |

로그 `logs/phase3.6-F9-*.txt`

## 1.10 결함 표 (끝난 기준)

engine-v1.2(F1은 v1.1 결과 병기). 탐지 = target pair 실제 판정이 기대와 같음(3 run 모두). 오탐 = baseline과 다른 non-target pair. 가시성 = target pair가 B0·B1에서 DIFF / C에서 기대 판정.

| 결함 | 기대 판정 (target pair) | 실제 판정 | 탐지 | 정상 경로 오탐 | UNC learn/eval | 규칙 수(생성) | eval UNC 규칙 전→후 | B0 / B1 / C |
|---|---|---|---|---|---|---|---|---|
| F0 (baseline 기지 차이) | R47 CV, R48 SAME | 같음 | 관측 | — | 0/0 | 0 | 0→0 | ✔ / ✔ / ✔ |
| F1 멱등 검사 제거 | R8 CV (1) | 1/1 CV | ✔ | v1.1: 1(R7 세션 귀속) / v1.2: 0 | 0/0 | 0 | 0→0 | 1 / 0 / 1 |
| F2 order_items INSERT 누락 | 27 CV + dbstate | 27/27 CV, dbstate 위반 | ✔ | 0 | 0/0 | 0 | 0→0 | 27 / 27 / 27 |
| F3 커밋 전 발행 | 7 CV | 7/7 CV | ✔ | 0 | 0/0 | 0 | 0→0 | 7 / 0 / 7 |
| F4 쿠폰 실패 롤백 누락 | 2 CV + dbstate | 2/2 CV, dbstate 위반 | ✔ | 0 | 0/0 | 0 | 0→0 | 2 / 1 / 2 |
| F5 JOIN FETCH(정상 리팩터링) | 13 UNC → 라벨 후 IMP | 13/13 UNC → 13/13 IMP | ✔(분류) | 0 | 5/8 → 0/0 | 3 (learned) | **8→0** | 13 / 13 / 13 |
| F6 itemCount(승인된 개선) | 26 IMP | 26/26 IMP | ✔(분류) | 0 | 0/0 | 1 (사전 승인) | 0→0 | 26 / 26 / 26 |
| F7 read timeout 1s | 2 CV + dbstate | 2/2 CV, dbstate 위반 | ✔ | 0 | 0/0 | 0 | 0→0 | 2 / 2 / 2 |
| F8 N+1 | 10 UNC / maxSelects 10 CV | 10/10 UNC / 10/10 CV | ✔ | 0 | 4/6 | 0 | 6→6 | 10 / 10 / 10 |
| F9 쿠폰 use 두 번 | 4 CV | 4/4 CV | ✔ | 0 | 0/0 | 0 | 0→0 | 4 / 0 / 4 |

**결함 탐지율**: 진짜 결함 6건(F1·F2·F3·F4·F7·F9) **6/6**, 성능 계약 F8 1/1(선언 시 CV, 미선언 시 Uncertain으로 사람에게), 분류 대상 F5·F6 2/2 — 합계 **9/9**. pair 단위 target **92/92**(+ F8 maxSelects 10/10).
**정상 경로 오탐**: 0 (engine-v1.2). F1만 engine-v1.1 기준 1.
**오판정률**(learn·사전 규칙이 F를 SAME·Improvement로 가린 건수): **0**. 현재 규칙 세트 전체(F5 learned 3 + F6 사전 1)로 F1~F9 27 run을 다시 판정해도 진짜 결함 target 중 가려진 pair 0, F5를 제외한 판정 변경 0 — `logs/phase3.6-misjudgment-allrules.txt`(파일 덮어쓰기 없이 임시 판정).
**Rule 재사용(첫 데이터)**: F5 learn 5 pair → 규칙 3 → eval 8 pair Uncertain → Improvement(8→0). F8은 learn 규칙과 맞지 않아 Uncertain 6 그대로(가리지 않음).
**B1(Normalization만) 미탐**: F1·F3·F9 전부, F4 절반 — 응답·SQL 축에 흔적이 없는 결함. B1은 F5·F6·F8에서 "다르다"까지만 보고 분류는 못 한다(3.7 관측 매트릭스).

## 2. 변경 파일·커밋

| 커밋 | 내용 |
|---|---|
| `ba6502b` phase3.6: settle 의미·corpus v2.1·지연 스텁·태그 | `k6/{barrier.py,run.js,run.sh}`, `corpus/{corpus-v2.1.json,schema-v2.json,validate.py,tests/invalid-v2/sku-missing-without-flag.json}`, `deploy/k8s/base/{kustomization.yaml,wiremock.yaml,wiremock-mappings/gateway-charge-slow.json}`, `engine/{ruleset.py,verdict.py,rules/contract-maxselects.yaml,tests/test_engine.py}`, `docs/{decision-log.md,phase3-plan.md}` |
| `2227518` phase3.6: baseline 결과·결함 기대 사전 등록 | `docs/fault-expectations.json`, `docs/fault-catalog.md`, `engine/fault_check.py`, 보고서·결과 |
| `c361ec4` phase3.6-F1: 결과·보고서 — 기대와 다름 | F1 중단 보고 |
| `b70a6b7` phase3.6: engine-v1.2 세션 검사 귀속 규칙(D-6) | `engine/verdict.py`, `engine/rules/contract*.yaml`, `engine/tests/test_engine.py`, docs |
| `0a7c1f8` · `6f6456d` · `9a6774f` · `800b6f1` · `4e34a7b` · `cb444fd` · `57e99ec` | phase3.6-F2 ~ F8: 결과·보고서(`800b6f1`에 learned 규칙 3) |
| `9648cf1` phase3.6: improvement.yaml F6 사전 승인 규칙 | `engine/rules/improvement.yaml` |
| (이 커밋) phase3.6-F9: 결과·보고서 | F9, 1.10 결함 표, `CLAUDE.md`(3.6 상태) |
| 결함 브랜치(각 1커밋, push) | `fault/F1` `da92b8e` · `F2` `a131294` · `F3` `12482f0` · `F4` `f83e211` · `F5` `1597c73` · `F6` `84bd197` · `F7` `31363ce` · `F8` `60edcda` · `F9` `f9f80ce` — `git rev-list --count phase3.5-v1.4..fault/F<n>` = 1, 클래스 1~2 |

## 3. 실행 명령·주요 출력

```
git tag phase3.3-base 98c9356; git tag phase3.5-v1.4 120b212; git push origin <tags>
kubectl apply -k deploy/k8s/{legacy,new}                   # WireMock 지연 스텁 configmap → wiremock 재시작
k6/run.sh --run-id p36-base --iterations 3 --vus 3         # new = phase3.5-v1.4
# 결함마다 (워크트리 → 1커밋 → push → 이미지)
git worktree add <tmp>/wt-F<n> -b fault/F<n> phase3.5-v1.4; (수정); git commit; git push -u origin fault/F<n>
docker build -f services/order/Dockerfile -t order-app:phase3.6-F<n> <wt>/services/ → docker save → kind load image-archive
kubectl kustomize deploy/k8s/new | sed 's#order-app:phase3.5-v1.4#order-app:phase3.6-F<n>#' | kubectl apply -f -
k6/run.sh --run-id p36-F<n> --iterations 3 --vus 3; verify_sameness ×3; verdict.py --arm C|B0|B1 ×3
.venv/bin/python engine/fault_check.py --fault F<n> --run-base p36-F<n>       # 기대 대조
# F5: review.py list --split learn → label ×3 → verdict 재판정 → fault_check --expect-key afterLearnLabels
# F8: verdict.py --contract engine/rules/contract-maxselects.yaml --out verdict-maxselects.json → fault_check --verdict verdict-maxselects.json --expect-key targetsMaxSelects
```
결함별 전문: `docs/reports/logs/phase3.6-F<n>-{run,verify,verdict,check,summary}.txt`

## 4. Legacy/New 비교 (run당, 3 run 동일)

| run | pairs | C (SAME/IMP/UNC/CV) | B0 DIFF | B1 DIFF | dbstate | settleTimeouts |
|---|---|---|---|---|---|---|
| p36-base | 60 | 59/0/0/1 | 1 | 1 | 일치 | 0 |
| p36-F1 (v1.2) | 60 | 58/0/0/2 | 2 | 1 | 일치 | 0 |
| p36-F2 | 60 | 32/0/0/28 | 28 | 28 | 위반 | 0 |
| p36-F3 | 60 | 52/0/0/8 | 8 | 1 | 일치 | 0 |
| p36-F4 | 60 | 57/0/0/3 | 3 | 2 | 위반 | 0 |
| p36-F5 (라벨 후) | 60 | 46/13/0/1 (라벨 전 46/0/13/1) | 14 | 14 | 일치 | 0 |
| p36-F6 | 60 | 33/26/0/1 | 27 | 27 | 일치 | 0 |
| p36-F7 | 59 | 56/0/0/3 | 3 | 3 | 위반 | 1 (R41/new/0.e1) |
| p36-F8 | 60 | 49/0/10/1 (maxSelects 49/0/0/11) | 11 | 11 | 일치 | 0 |
| p36-F9 | 60 | 55/0/0/5 | 5 | 1 | 일치 | 0 |

## 5. 지시와 다르게 구현한 것

- **F7 "3s→1s"**: 기준선·Legacy의 `PaymentGatewayClient`는 read timeout을 설정하지 않는다(SimpleClientHttpRequestFactory 기본 = 무제한). F7은 "무제한 → 1s" 한 줄 — 2s 지연에서 Legacy 성공·New 실패라는 시험 의미와 기대 판정은 같다
- **F4 "트랜잭션 안에서 삼켜"**: `@Transactional(noRollbackFor = [CouponFailure])` 한 줄로 구현 — 예외는 컨트롤러까지 가서 400 본문이 그대로이고 트랜잭션은 커밋된다(지시한 효과와 같음). 사전 기대의 축 목록에 있던 writeSet 차이는 없었다(양쪽 모두 INSERT 실행, 차이는 롤백 여부) — 판정(CV)은 기대와 일치
- **기대 사전 등록 파일**(`docs/fault-expectations.json`)과 대조 도구(`engine/fault_check.py`)를 추가 — 지시의 "기대 판정 = 실제 판정인지 pair 단위로 확인"을 run 전에 고정하기 위해. F0 항목은 baseline 확인용으로 F1 run 전에 추가
- **결함 run 배포**: 레포 new overlay는 `phase3.5-v1.4` 그대로 두고 렌더링 결과의 order 이미지만 `phase3.6-F<n>`으로 치환해 apply(dirty=false)
- **커밋 전 스모크**(F2·F5·F8): 결함 브랜치 커밋 전에 이미지를 올려 재생 헤더 없는 요청 1~2건으로 기동·동작만 확인(Evidence 없음, 다음 run의 S0 리셋으로 지워짐)
- **engine-v1.2(D-6)**: F1 결과를 본 뒤 세션 검사 귀속 규칙을 일반화 — 사용자 결정, 1.0b

## 6. 문제·해결·남은 한계

- **F1 세션 귀속(D-6)** — 1.0b. 탐지에는 영향 없음, 정상 경로 오탐 v1.1 1 → v1.2 0. **귀속 규칙은 F1 결과를 본 뒤 일반화했다**는 점이 평가의 한계로 남는다(F2~F9는 v1.2가 사전 등록 엔진)
- **F0**: 입력 검증 경로의 Legacy/New 차이(409 vs 400)는 corpus에 해당 입력(S011)을 넣어야 보였다 — 차등 검증은 corpus가 닿는 범위만 본다
- **settle 보완의 효과**: F7(New가 발행을 안 함)과 F9(New가 settle에 없는 홉을 더 만듦)이 run을 멈추지 않고 엔진까지 왔다 — 보완 전 규칙이었다면 F7은 degraded·barrier 미달로 판정 전에 멈췄다
- **B1의 한계(3.7 입력)**: F1·F3·F9는 B1에서 DIFF 0, F4는 절반. 응답·SQL만 보는 정규화로는 외부 호출·타임라인·트랜잭션·hop 결함을 못 본다
- **규칙 학습 데이터가 F5 하나뿐**: Rule 재사용 효과(eval 8→0)는 한 유형의 결과다. 3.7에서 v1.3+·F 변형 전체로 다시 잰다
- **F5 learned 규칙의 범위**: `callTree.sequenceReplaced`는 from/to 전체 시퀀스 일치라 좁고, `dbRead.countDelta 2→1`은 endpoint order.get 전체에 적용된다 — 같은 횟수 변화를 내는 다른 원인이 order.get에 생기면 Improvement로 분류될 수 있다(이번 F에서는 해당 없음, 오판정 0)
- `runs/p36-F1-*/verdict-engine-v1.1.json`, `runs/p36-F5-*/verdict-prelabel.json`, `runs/p36-F8-*/verdict-maxselects.json`은 3.7 집계용 보조 판정 파일
