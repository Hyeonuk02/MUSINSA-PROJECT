# Phase 3.6 보고서 — 결함 카탈로그 v1 + New v2

- 작업일: 2026-10-14
- 기준선: `phase3.5-v1.4`(`120b212`). Legacy `order-app:phase3.3-base`, Coupon 양쪽 `coupon-app:phase3.3-base`, 엔진 `engine-v1.1`, corpus v2.1
- 진행 상태: 준비·baseline 완료 → F1(engine-v1.1에서 기대와 다름 → D-6 결정 → engine-v1.2 재판정으로 일치) → F2부터 진행 중
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
