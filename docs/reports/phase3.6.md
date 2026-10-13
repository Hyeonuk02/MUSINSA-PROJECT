# Phase 3.6 보고서 — 결함 카탈로그 v1 + New v2

- 작업일: 2026-10-14
- 기준선: `phase3.5-v1.4`(`120b212`). Legacy `order-app:phase3.3-base`, Coupon 양쪽 `coupon-app:phase3.3-base`, 엔진 `engine-v1.1`, corpus v2.1
- 진행 상태: 준비·baseline 완료 → F1(engine-v1.1에서 기대와 다름 → D-6 결정 → engine-v1.2 재판정으로 일치) → F2 일치 → F3 일치 → F4 일치 → F5 일치(learn 라벨 3, eval Uncertain 8→0) → F6 일치 → F7 일치 → F8 일치(두 설정) → F9부터 진행 중
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
