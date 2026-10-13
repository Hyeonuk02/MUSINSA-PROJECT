# Phase 3.6 보고서 — 결함 카탈로그 v1 + New v2

- 작업일: 2026-10-14
- 기준선: `phase3.5-v1.4`(`120b212`). Legacy `order-app:phase3.3-base`, Coupon 양쪽 `coupon-app:phase3.3-base`, 엔진 `engine-v1.1`, corpus v2.1
- 진행 상태: 준비·baseline 완료 → F1(engine-v1.1에서 기대와 다름 → D-6 결정 → engine-v1.2 재판정으로 일치) → F2 일치 → F3 일치 → F4 일치 → F5부터 진행 중
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
