# Phase 3.6 보고서 — 결함 카탈로그 v1 + New v2

- 작업일: 2026-10-14
- 기준선: `phase3.5-v1.4`(`120b212`). Legacy `order-app:phase3.3-base`, Coupon 양쪽 `coupon-app:phase3.3-base`, 엔진 `engine-v1.1`, corpus v2.1
- 진행 상태: 준비·baseline 완료 → **F1에서 중단 — 기대 ≠ 실제(정상 경로 1 pair 추가 CV), 결정 필요 1건**. F2~F9 미착수
- 결함 표: `docs/fault-catalog.md`, 기대 사전 등록: `docs/fault-expectations.json`, 누적: `docs/phase3-result.md`

## 0. 결정 필요 사항

**D-6 세션 규칙 위반을 어느 pair에 붙일지 — F1에서 R000007(정상 첫 결제)도 CV**

F1(멱등 검사 제거) 결과, 겨냥한 R000008(같은 키 재결제)은 기대대로 CV다. 그런데 **R000007(S002의 정상 첫 결제, Legacy와 행동 동일)도 CV**가 됐다. 위반 사유는 하나뿐이다: `gateway_calls_per_idem_key_le_1[idem-R000007]: legacy 1 / new 2`. R000007과 R000008은 같은 Idempotency-Key(`idem-R000007`)를 쓰고, 3.4에서 정한 규칙("위반은 그 키를 가진 pair(어느 스택이든)에 붙인다", phase3-plan 3.4 구현 시 확정)이 두 pair에 모두 붙였다. 엔진 버그가 아니라 3.4 설계대로의 동작이고, 사전 등록한 기대(R000008만 CV)가 이 귀속 규칙을 반영하지 못했다. 지시대로 엔진도 기대도 고치지 않고 멈춘다.

선택지:
- **(A) 권장** — 귀속 규칙 변경: 세션 규칙 위반은 **그 키를 가진 pair 중 자기 pair의 게이트웨이 호출 수가 Legacy와 다른 pair**에만 붙인다(F1: R000008만 — legacy 0 / new 1). 그런 pair가 없으면(호출 수는 pair마다 같은데 합만 넘는 경우) 지금처럼 키를 가진 pair 전부에. 엔진 변경(engine-v1.2) + 단위 테스트, p33·p35·p36-base·p36-F1 재판정으로 다른 결과가 바뀌지 않음을 확인하고 F1 판정을 다시 낸다. "결함을 보고 엔진을 고친" 사례가 되므로 보고서에 v1.1 결과(R000007 CV 포함)를 함께 남긴다
- (B) 엔진은 그대로, 기대를 고친다 — F1 기대를 "R000007·R000008 CV"로 정정하고, 정상 경로 오탐 정의에서 "세션 규칙이 같은 세션의 같은 키 pair에 붙은 것"은 제외. 사전 등록 기대를 결과 뒤에 바꾼 것으로 기록
- (C) 세션 규칙 위반을 pair 판정이 아니라 **세션 판정**으로 따로 낸다(verdict.json `sessionChecks`, pair에는 붙이지 않음). 탐지율은 세션 단위로 센다. 엔진 출력 형식 변경이 가장 크다


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

### 1.1 F1 — 결제 멱등 검사 제거 (중단)

| 기준 | 결과 | 근거 |
|---|---|---|
| 브랜치·커밋 1·이미지 | PASS | `fault/F1` = `da92b8e`(phase3.5-v1.4 위 1커밋, push), `order-app:phase3.6-F1`. `git diff phase3.5-v1.4..fault/F1`: `OrderService.kt` 1 file, +1 −3 (클래스 1) |
| 3 run, Undelivered 0, degraded 0 | PASS | `p36-F1-1..3` run.sh exit 0, verify 3/3 PASS(참고: `R000008/0.e1` new만 — 부모가 선언한 행동 차이), settleTimeouts 0, run-meta `dirty: false`(rev `2227518`), images.order new=phase3.6-F1. barrier new 기대 61(폐포가 `R000008/0.e1`을 기다림) |
| target R000008 CV | PASS | 사유: `externalCalls: legacy=[] new=[charge 200]`, `events.published 개수 0/1`, `hop_set: new만 ['0.e1']`, `gateway_calls_per_idem_key_le_1[idem-R000007]: legacy 1 / new 2` (+ Uncertain 후보 callTree·responseHash는 CV가 우선) |
| 정상 경로 오탐 0 | **FAIL** | **R000007/0 CV**(baseline SAME) — 사유는 세션 규칙 하나뿐(0절). 그 밖 57 pair는 baseline과 같음(R000047 CV 포함) |
| 세 run 판정 동일 | PASS | 3 run 모두 CV 3(R000007·R000008·R000047) + SAME 57 |
| B0 / B1 / C | B0 ✔ / B1 ✘ / C ✔ | B0 DIFF 2(R000008 + R000047) — R000008이 원문에서 보임. B1 DIFF 1(R000047만) — B1 축(응답·SQL)에는 R000008 차이가 없다(응답 동일, `markPaid`가 같은 값이라 UPDATE도 없음). C는 외부 호출·이벤트·hop·세션 규칙으로 잡음 |

해석: 멱등성 결함은 **응답과 SQL에 흔적이 없다**(B1 미탐) — 외부 호출 축과 세션 규칙이 있어야 잡힌다. 관측 매트릭스(3.7: "C만 잡는 것은 F1…")와 같은 결과.
로그: `logs/phase3.6-F1-{run,verify,verdict,check}.txt`
