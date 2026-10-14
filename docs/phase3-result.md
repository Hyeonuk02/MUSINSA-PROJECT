# Phase 3 결과 — 처음으로 Legacy ≠ New

> 2026-10-14 완료, tag `phase3-done`. 계획 `docs/phase3-plan.md`(v2.1 + 구현 시 확정). 단계별 상세 `docs/reports/phase3.0~3.7.md`, 지표 `docs/phase3-metrics.md`(`engine/metrics.py` 생성), 결함 `docs/fault-catalog.md`, 발견 `docs/findings.md`, 결정 `docs/decision-log.md` D15~D22. 3.8(런타임 교체)은 미실시 — Phase 4 이후 선택.

## 결론

1. **실험 대상이 MSA다** — Order·Coupon(각자 DB) + Payment(WireMock) + Kafka(스택별 브로커), 스택 간 공유 자원 없음(isolation-proof). A/A(base, VU=3 ×3) 전 pair SAME.
2. **New ≠ Legacy** — Order를 Java에서 Kotlin으로 4단계 점진 전환(v1.1~v1.4, Order 전면 Kotlin)했고 결함 카탈로그 9건을 기준선 위 1커밋씩 주입했다.
3. **Evidence가 4축 + 실행 경로 + 타임라인이다** — 응답 / DB 접근(SQL 원문 + 최종 상태) / 외부 호출 / 이벤트(발행·소비) + callTree + 트랜잭션(COMMIT_BEGIN·outcome), 한 요청의 기록이 단일 seq로 순서 복원.
4. **엔진이 판정한다** — 결함 9/9를 사전 등록한 기대대로 판정(pair 92/92), 정상 경로 오탐 0, 오판정 0/129, eval 세션 수동 검토 대상 31 → 6(F8 제외 25 → 0). learn 세션 5 pair에서 만든 규칙 3개가 eval 세션 8 pair를 처리했다.
5. **Kotlin 점진 전환은 이 corpus 범위에서 행동 Evidence를 한 바이트도 바꾸지 않았다**(B0 원문까지 0). 흔적은 Metaspace(+6~7 MB)에만. 단 corpus가 닿지 않는 입력(sku 없음)에서는 Legacy 409 / Kotlin 400 차이가 있었다(F0 — corpus v2.1로 실측).

## Evidence 스키마 v1 확정

`docs/evidence-schema-v1.json`(strict, `schemaVersion: "v1"`)을 Phase 3 확정본으로 선언한다. 키 `(runId, replayRequestId, stack, hopPath)`(D15), 필드 service·origin(http|kafka), 단일 seq 타임라인(dbAccess.statements·externalCalls·events.published·transactions — D16), callTree(별도 seq, depth 불변식), error, event·consumeOutcome(kafka), events.published[].payload·event.payload(3.3 추가). 3.1~3.6의 모든 run Evidence가 이 스키마와 엔진 입력 계약(`engine/common.py`)을 통과했다. 변경은 추가만 했다(3.3). 엔진 판정 버전은 `engine-v1.2`(3.4 v1 → 3.5 v1.1 id 값 마스킹 → 3.6 v1.2 세션 검사 귀속 D20).

## 지표 4개 (eval 세션 기준 — 정의·분모는 `docs/reports/phase3.7.md` 4절)

| 지표 | 값 |
|---|---|
| 결함 탐지율 — 결함 단위 | 진짜 결함 **6/6**(F1·F2·F3·F4·F7·F9), 성능 계약 **1/1**(F8), 분류 대상 **2/2**(F5·F6), 합계 **9/9** |
| 결함 탐지율 — pair 단위 | **92/92** + F8 maxSelects **10/10** |
| 정상 경로 오탐 | 0 (engine-v1.2; F1만 v1.1 기준 1 — D20) |
| 수동 검토 감소율 | eval Uncertain **31 → 6 (80.7%)**, F8 제외 **25 → 0 (100%)** — learned 8 + 사전 승인 17. F8의 6은 maxSelects 미선언 시 의도된 결과 |
| 오판정률 | **0/129**(진짜 결함 target 43 pair × 3 run 중 규칙이 SAME·Improvement로 바꾼 판정) |
| Rule 재사용 효과 | (a) F5 eval **8**, (b) 다른 변형 **0**, (c) 사다리 v1.3·v1.4 **0** — 과적용 없음 |
| B1(Normalization만) 미탐 | target 13 pair — F1·F3·F9 전부, F4 절반. 관측 매트릭스 8칸 일치 + F4 반 칸 |
| 운영 | Phase 3 run 57(판정·게이트 55, 걸러진 run 2), Undelivered 0, degraded 0, settleTimeouts 3(F7 증상), 3 run 판정 일치 16/16 |

## 한계

- **규칙 학습 데이터가 F5 한 유형** — 재사용 효과는 같은 유형의 다른 세션에 대한 것. (b)·(c) 0은 "과적용 없음"으로만 해석
- **D20(세션 검사 귀속)은 F1 결과를 본 뒤 일반화** — F2~F9는 v1.2가 사전 등록 엔진. 탐지율 영향 없음, F1 오탐 1 → 0
- **corpus 커버리지 = 검증 범위** — F0은 corpus에 해당 입력을 넣은 뒤에야 보였다(findings O6). Legacy 자체의 잘못된 응답(409 ORDER_KEY_EXISTS)도 함께 드러났다(O7)
- **규모** — 단일 노드 kind(12GiB), corpus v2.1 48 요청(60 pair), 변형당 3 run(결정론 재생이라 반복은 새 표본이 아님 — 평가 분리는 세션·변형으로)
- **잡음** — 설계로 잡음을 0으로 만든 환경이라 B0의 운영 잡음 오탐은 재지 못함
- **분류 정답은 사람이 정한 것** — F5(라벨)·F6(사전 승인). 규칙 적용의 정확성을 잰 것이지 라벨의 옳음을 잰 것이 아님
- **범위 밖**: 보상 누락·Outbox(분산 일관성), 오버헤드, 콜트리 합성·스코핑(Phase 4), 운영 시연
- 단계별 남은 한계는 각 보고서 6절과 findings

## Phase 4 입력

| 항목 | 값 |
|---|---|
| 새 기준선 | tag `phase3.5-v1.4`(`120b212`) — Order 전면 Kotlin, 이미지 `order-app:phase3.5-v1.4` |
| Legacy 고정 | tag `phase3.3-base`(`98c9356`), 이미지 `order-app:phase3.3-base`, `coupon-app:phase3.3-base` |
| 사다리 | 커밋 `fd839d6`(v1.1) · `fc6e6e2`(v1.2) · `c64618f`(v1.3) · `120b212`(v1.4), 이미지 `order-app:phase3.5-v1.1~v1.4`, runs `runs/p35-v1.{1..4}-1..3`, base A/A `runs/p35-base-1..3` |
| 결함 | 브랜치 `fault/F1`~`F9`(각 기준선 위 1커밋 — `da92b8e` `a131294` `12482f0` `f83e211` `1597c73` `84bd197` `31363ce` `60edcda` `f9f80ce`), 이미지 `order-app:phase3.6-F<n>`, runs `runs/p36-F<n>-1..3`, baseline `runs/p36-base-1..3`, 코드 diff `git diff -M phase3.5-v1.4..fault/F<n>` |
| corpus | `corpus/corpus-v2.1.json`(세션 11·요청 48, split learn 4 / eval 7, settle, allowMissingSku S011) |
| 기대 사전 등록 | `docs/fault-expectations.json` |
| 규칙 | `engine/rules/contract.yaml`(+ `contract-maxselects.yaml`), `improvement.yaml`(F6 사전 승인 1), `learned/`(F5 learn 3: `5da05fdb147f`·`989c110b103e`·`9a82df6b99b4`) |
| 엔진 | `engine-v1.2`(`engine/verdict.py`), 평가 도구 `engine/fault_check.py`·`engine/metrics.py` |
| 주의 | 변경 클래스 추출은 `git diff -M`, 사다리·결함 브랜치 squash 금지(call-graph.md 메모) |

---

# 단계별 누적 표

> 3.5 표의 판정은 run 당시 engine-v1.1. 3.6에서 engine-v1.2로 전부 재판정해 pair 판정·집계 변화 0(`docs/reports/logs/phase3.6-rejudge-engine-v1.2.txt`).

## 3.5 New v1 사다리 — Order 점진 Kotlin 전환

Legacy = `order-app:phase3.3-base`(고정), Coupon 양쪽 `coupon-app:phase3.3-base`, corpus v2(58 pair/run, learn 25 · eval 33), VU=3 ×3, 엔진 `engine-v1.1`. 판정 수는 run당 값(세 run이 같으면 하나로 적는다). 규칙은 v1.1·v1.2에서만 생성.

| 단계 | commit | order 이미지(new) | runs | 변경 클래스(코드 diff) | SAME | IMP | UNC | CV | learn 리뷰 | 생성 규칙 | eval UNC 전→후 | B0 DIFF | B1 DIFF | Metaspace order legacy/new (MB, 참고) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | `d1b283e` | phase3.3-base | `runs/p35-base-1..3` | — (A/A) | 58 | 0 | 0 | 0 | 0 | 0 | 0→0 | 0 | 0 | 125.02 / 125.01 |
| v1.1 | `fd839d6` | phase3.5-v1.1 | `runs/p35-v1.1-1..3` | `PaymentGatewayClient` (.java −56 → .kt +50), pom +104 | 58 | 0 | 0 | 0 | 0 | 0 | 0→0 | 0 | 0 | 126.79 / 134.23 |
| v1.2 | `fc6e6e2` | phase3.5-v1.2 | `runs/p35-v1.2-1..3` | `Order`, `OrderItem`, `OrderRepository` (.java −175 → .kt +171) | 58 | 0 | 0 | 0 | 0 | 0 | 0→0 | 0 | 0 | 128.18 / 134.90 |
| v1.3 | `c64618f` | phase3.5-v1.3 | `runs/p35-v1.3-1..3` | `OrderService`(+Kind·Outcome·NewItem), `OrderPaid`, `OrderEventPublisher` (.java −188 → .kt +173) | 58 | 0 | 0 | 0 | 0 | 0 (규칙 생성 없는 단계) | 0→0 | 0 | 0 | 128.98 / 134.71 |
| v1.4 | `120b212` | phase3.5-v1.4 | `runs/p35-v1.4-1..3` | `OrderController`(+DTO), `OrderView`, `CouponClient`, `ClockConfig`, `OrderApplication`, `requestlog.RequestLogFilter`, `requestlog.CachedBodyRequest` (.java −428 → .kt +349) = Order 전면 Kotlin | 58 | 0 | 0 | 0 | 0 | 0 (규칙 생성 없는 단계) | 0→0 | 0 | 0 | 128.94 / 135.33 |

요약: 이 corpus가 닿는 행동 범위에서 Order의 점진 Kotlin 전환(1 → 전면 클래스)은 행동 Evidence를 바꾸지 않았다 — 네 단계 모두 C·B0·B1 전 pair SAME(B0 원문까지). Uncertain이 없어 learn 리뷰 0·규칙 0, eval Uncertain 0→0이라 Rule 재사용 효과는 3.6의 F 변형에서 처음 측정된다. Kotlin 전환의 흔적은 Metaspace(new order +6.4~7.4 MB, 클래스 +1,800~2,300)에만 남았다. Kotlin v1.4가 3.6 결함 카탈로그의 새 기준선이다.

Phase 4 입력(스코핑): 단계별 commit = 위 표 commit 열, 이미지 = `order-app:phase3.5-v1.x`, runs = `runs/p35-v1.x-1..3`, 코드 diff = `git diff <이전 단계 commit> <commit> -- services/order`.

사다리 표에서 제외한 run: `runs/p35-v1.1-oom-1`(Metaspace OOM), `runs/p35-v1.1-stale-1`(runId 재사용) — `docs/reports/phase3.5.md` 6절.

## 3.6 결함 카탈로그 v1 + New v2

기준선 `phase3.5-v1.4`, corpus v2.1(60 pair/run, learn 25 · eval 35), VU=3 ×3, 엔진 `engine-v1.2`(F1 이후 D-6 귀속 규칙, F2~F9의 사전 등록 엔진). 기대 판정은 run 전에 `docs/fault-expectations.json`에 등록. 상세 `docs/fault-catalog.md`, `docs/reports/phase3.6.md`.

| 변형 | 브랜치·commit | 이미지(new) | runs | 변경 클래스 | 기대(target) | 실제(target) | 탐지 | 정상 경로 오탐 | UNC learn/eval | 규칙 수(생성) | eval UNC 규칙 전→후 | B0 / B1 / C 가시성 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | `phase3.5-v1.4` | phase3.5-v1.4 | `runs/p36-base-1..3` | — | F0: R000047 CV, R000048 SAME | 59 SAME + R000047 CV ×3 | (F0 관측) | — | 0/0 | 0 | 0→0 | B0 DIFF 1 / B1 DIFF 1 / C CV 1 |
| F1 | `fault/F1` `da92b8e` | phase3.6-F1 | `runs/p36-F1-1..3` | `OrderService` | R000008 CV | R000008 CV ✔ | ✔ | v1.1: 1(R000007 세션 귀속) / v1.2: 0 | 0/0 | 0 | 0→0 | B0 ✔ / B1 ✘ / C ✔ |
| F2 | `fault/F2` `a131294` | phase3.6-F2 | `runs/p36-F2-1..3` | `Order` | 27 pair CV + dbstate | 27/27 CV, dbstate 위반 | ✔ | 0 | 0/0 | 0 | 0→0 | B0 ✔ / B1 ✔ / C ✔ |
| F3 | `fault/F3` `12482f0` | phase3.6-F3 | `runs/p36-F3-1..3` | `OrderEventPublisher` | 첫 결제 7 pair CV | 7/7 CV | ✔ | 0 | 0/0 | 0 | 0→0 | B0 ✔ / B1 ✘ / C ✔ |
| F4 | `fault/F4` `f83e211` | phase3.6-F4 | `runs/p36-F4-1..3` | `OrderService` | R000037·R000038 CV + dbstate | 2/2 CV, dbstate 위반 | ✔ | 0 | 0/0 | 0 | 0→0 | B0 ✔ / B1 △(1/2) / C ✔ |
| F5 | `fault/F5` `1597c73` | phase3.6-F5 | `runs/p36-F5-1..3` | `OrderRepository`, `OrderService` | 조회 13 UNC → 라벨 후 IMP | 13/13 UNC → 13/13 IMP | ✔(분류) | 0 | 5/8 → 0/0 | 3 (learned, learn 세션) | **8→0** | B0 ✔ / B1 ✔(DIFF) / C ✔ |
| F6 | `fault/F6` `84bd197` | phase3.6-F6 | `runs/p36-F6-1..3` | `OrderView` | 26 pair IMP(사전 규칙) | 26/26 IMP | ✔(분류) | 0 | 0/0 | 1 (사전 승인, improvement.yaml) | 0→0 | B0 ✔ / B1 ✔(DIFF) / C ✔ |
| F7 | `fault/F7` `31363ce` | phase3.6-F7 | `runs/p36-F7-1..3` | `PaymentGatewayClient` | R000041·R000042 CV + dbstate | 2/2 CV, dbstate 위반 | ✔ | 0 | 0/0 | 0 | 0→0 | B0 ✔ / B1 ✔ / C ✔ |
| F8 | `fault/F8` `60edcda` | phase3.6-F8 | `runs/p36-F8-1..3` | `OrderRepository`, `OrderService` | 조회 10: 기본 UNC / maxSelects CV | 10/10 UNC / 10/10 CV | ✔ | 0 | 4/6 | 0 | 6→6 (규칙 없음, learn 규칙 적용 0) | B0 ✔ / B1 ✔ / C ✔ |
| F9 | `fault/F9` `f9f80ce` | phase3.6-F9 | `runs/p36-F9-1..3` | `OrderService` | 쿠폰 주문 생성 4 CV | 4/4 CV | ✔ | 0 | 0/0 | 0 | 0→0 | B0 ✔ / B1 ✘ / C ✔ |

요약: 결함 탐지율 9/9(진짜 결함 6/6, 성능 계약 1/1, 분류 2/2), target pair 92/92, 정상 경로 오탐 0(engine-v1.2), 오판정 0, Rule 재사용 F5 eval Uncertain 8→0. B1 미탐: F1·F3·F9(전부), F4(1/2).
