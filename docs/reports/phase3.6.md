# Phase 3.6 보고서 — 결함 카탈로그 v1 + New v2

- 작업일: 2026-10-14
- 기준선: `phase3.5-v1.4`(`120b212`). Legacy `order-app:phase3.3-base`, Coupon 양쪽 `coupon-app:phase3.3-base`, 엔진 `engine-v1.1`, corpus v2.1
- 진행 상태: 준비·baseline 완료 → F1부터 진행 중 (결함마다 절 추가)
- 결함 표: `docs/fault-catalog.md`, 기대 사전 등록: `docs/fault-expectations.json`, 누적: `docs/phase3-result.md`

## 0. 결정 필요 사항

없음.

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
