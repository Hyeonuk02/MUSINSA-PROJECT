# Phase 3 지표 (engine/metrics.py 생성 — 손으로 고치지 않는다)

엔진 `engine-v1.2 (phase3.6: 세션 검사 귀속 규칙)`. 규칙 세트 sha256은 `docs/phase3-metrics.json` `engine.rules`. 입력 run은 `inputs`.

## 1. 결함 탐지율

| 결함 | 분류 | target pair (보기별 ok/n, 3 run 모두) | runCheck | 정상 경로 오탐 | 탐지 |
|---|---|---|---|---|---|
| F0 | baseline | C_rules 2/2 | OK | 0 | ✔ |
| F1 | real | C_rules 1/1 | OK | 0 (engine-v1.1 기준 1: R000007/0) | ✔ |
| F2 | real | C_rules 27/27 | OK | 0 | ✔ |
| F3 | real | C_rules 7/7 | OK | 0 | ✔ |
| F4 | real | C_rules 2/2 | OK | 0 | ✔ |
| F5 | classify | pre(C_norules) 13/13, post(C_rules) 13/13 | OK | 0 | ✔ |
| F6 | classify | C_rules 26/26 | OK | 0 | ✔ |
| F7 | real | C_rules 2/2 | OK | 0 | ✔ |
| F8 | perf | C_rules 10/10, C_maxsel 10/10 | OK | 0 | ✔ |
| F9 | real | C_rules 4/4 | OK | 0 | ✔ |

- 결함 단위: 진짜 결함 6/6 (100.0%), 성능 계약 1/1 (100.0%), 분류 대상 2/2 (100.0%), 합계 9/9 (100.0%)
- pair 단위: 92/92 (100.0%) (F5는 규칙 전 UNC·후 IMP 둘 다 맞아야 1) + F8 maxSelects 10/10 (100.0%)

## 2. 수동 검토 감소율 (eval 세션 기준, run당 — 세 run 동일)

| 변형 | eval pair | eval UNC 규칙 전 → 후 | 감소 출처 | learn UNC 전 → 후 (참고) |
|---|---|---|---|---|
| F1 | 35 | 0 → 0 | - | 0 → 0 |
| F2 | 35 | 0 → 0 | - | 0 → 0 |
| F3 | 35 | 0 → 0 | - | 0 → 0 |
| F4 | 35 | 0 → 0 | - | 0 → 0 |
| F5 | 35 | 8 → 0 | {'learned': 8} | 5 → 0 |
| F6 | 35 | 17 → 0 | {'approved': 17} | 9 → 0 |
| F7 | 34 | 0 → 0 | - | 0 → 0 |
| F8 | 35 | 6 → 6 | - | 4 → 4 |
| F9 | 35 | 0 → 0 | - | 0 → 0 |
| **합계(F1~F9)** | 314 | **31 → 6** (감소율 80.7%) | | 18 → 4 |
| **합계(F8 제외)** | 279 | **25 → 0** (감소율 100.0%) | | 14 → 0 |

## 3. 오판정률

진짜 결함(F1·F2·F3·F4·F7·F9) target pair 43개 × 3 run = 129 판정 중 규칙(learned 3 + 사전 1)에 의해 SAME·IMPROVEMENT로 바뀐 것: **0 / 129** (0.0%)

| 변형 | learned 규칙 적용(run1, pair-규칙 수) | 사전 승인 규칙 적용 | 세 run 동일 |
|---|---|---|---|
| base | 0 | 0 | ✔ |
| v1.1 | 0 | 0 | ✔ |
| v1.2 | 0 | 0 | ✔ |
| v1.3 | 0 | 0 | ✔ |
| v1.4 | 0 | 0 | ✔ |
| F0 | 0 | 0 | ✔ |
| F1 | 0 | 0 | ✔ |
| F2 | 0 | 0 | ✔ |
| F3 | 0 | 0 | ✔ |
| F4 | 0 | 0 | ✔ |
| F5 | 26 | 0 | ✔ |
| F6 | 0 | 26 | ✔ |
| F7 | 0 | 0 | ✔ |
| F8 | 0 | 0 | ✔ |
| F9 | 0 | 0 | ✔ |

## 4. Rule 재사용 효과 (F5 learn 5 pair → learned 규칙 3)

- (a) F5 eval: Uncertain → Improvement **8** pair
- (b) 다른 변형(F0~F4, F6~F9): **0**
- (c) 사다리 v1.3·v1.4: **0** (사다리 전체 0)

| 변형 | learn | eval |
|---|---|---|
| base | 0 | 0 |
| v1.1 | 0 | 0 |
| v1.2 | 0 | 0 |
| v1.3 | 0 | 0 |
| v1.4 | 0 | 0 |
| F0 | 0 | 0 |
| F1 | 0 | 0 |
| F2 | 0 | 0 |
| F3 | 0 | 0 |
| F4 | 0 | 0 |
| F5 | 5 | 8 |
| F6 | 0 | 0 |
| F7 | 0 | 0 |
| F8 | 0 | 0 |
| F9 | 0 | 0 |

## 5. 운영 지표 (참고)

- Phase 3 run 디렉터리(p31~p36): 57 (판정·게이트 대상 55, 걸러진 run 2: p35-v1.1-oom-1, p35-v1.1-stale-1)
- 판정·게이트 대상 run 합계: Undelivered(진입 홉) 0, degraded 0, settleTimeouts 3
- 3 run 판정 일치(C, pair 단위 완전 일치): 16/16 그룹
- sessionViolations(C, 판정한 run 전체): 3건 — pair 귀속 3, bothStacks 0; p36-F1-1 gateway_calls_per_idem_key_le_1[idem-R000007] legacy 1 / new 2 → ['R000008/0']; p36-F1-2 gateway_calls_per_idem_key_le_1[idem-R000007] legacy 1 / new 2 → ['R000008/0']; p36-F1-3 gateway_calls_per_idem_key_le_1[idem-R000007] legacy 1 / new 2 → ['R000008/0']

| run | sent | Undelivered | degraded | settleTimeouts | 걸러짐 |
|---|---|---|---|---|---|
| p31-1 | 14 | 0 | 0 | 0 |  |
| p31-2 | 14 | 0 | 0 | 0 |  |
| p31-3 | 14 | 0 | 0 | 0 |  |
| p32-1 | 46 | 0 | 0 | 0 |  |
| p32-2 | 46 | 0 | 0 | 0 |  |
| p32-3 | 46 | 0 | 0 | 0 |  |
| p32a-1 | 14 | 0 | 0 | 0 |  |
| p33-1 | 46 | 0 | 0 | 0 |  |
| p33-2 | 46 | 0 | 0 | 0 |  |
| p33-3 | 46 | 0 | 0 | 0 |  |
| p35-base-1 | 46 | 0 | 0 | 0 |  |
| p35-base-2 | 46 | 0 | 0 | 0 |  |
| p35-base-3 | 46 | 0 | 0 | 0 |  |
| p35-v1.1-1 | 46 | 0 | 0 | 0 |  |
| p35-v1.1-2 | 46 | 0 | 0 | 0 |  |
| p35-v1.1-3 | 46 | 0 | 0 | 0 |  |
| p35-v1.1-oom-1 | 36 | 0 | 7 | 0 | ✔ |
| p35-v1.1-stale-1 | 40 | 0 | 4 | 0 | ✔ |
| p35-v1.2-1 | 46 | 0 | 0 | 0 |  |
| p35-v1.2-2 | 46 | 0 | 0 | 0 |  |
| p35-v1.2-3 | 46 | 0 | 0 | 0 |  |
| p35-v1.3-1 | 46 | 0 | 0 | 0 |  |
| p35-v1.3-2 | 46 | 0 | 0 | 0 |  |
| p35-v1.3-3 | 46 | 0 | 0 | 0 |  |
| p35-v1.4-1 | 46 | 0 | 0 | 0 |  |
| p35-v1.4-2 | 46 | 0 | 0 | 0 |  |
| p35-v1.4-3 | 46 | 0 | 0 | 0 |  |
| p36-F1-1 | 48 | 0 | 0 | 0 |  |
| p36-F1-2 | 48 | 0 | 0 | 0 |  |
| p36-F1-3 | 48 | 0 | 0 | 0 |  |
| p36-F2-1 | 48 | 0 | 0 | 0 |  |
| p36-F2-2 | 48 | 0 | 0 | 0 |  |
| p36-F2-3 | 48 | 0 | 0 | 0 |  |
| p36-F3-1 | 48 | 0 | 0 | 0 |  |
| p36-F3-2 | 48 | 0 | 0 | 0 |  |
| p36-F3-3 | 48 | 0 | 0 | 0 |  |
| p36-F4-1 | 48 | 0 | 0 | 0 |  |
| p36-F4-2 | 48 | 0 | 0 | 0 |  |
| p36-F4-3 | 48 | 0 | 0 | 0 |  |
| p36-F5-1 | 48 | 0 | 0 | 0 |  |
| p36-F5-2 | 48 | 0 | 0 | 0 |  |
| p36-F5-3 | 48 | 0 | 0 | 0 |  |
| p36-F6-1 | 48 | 0 | 0 | 0 |  |
| p36-F6-2 | 48 | 0 | 0 | 0 |  |
| p36-F6-3 | 48 | 0 | 0 | 0 |  |
| p36-F7-1 | 48 | 0 | 0 | 1 |  |
| p36-F7-2 | 48 | 0 | 0 | 1 |  |
| p36-F7-3 | 48 | 0 | 0 | 1 |  |
| p36-F8-1 | 48 | 0 | 0 | 0 |  |
| p36-F8-2 | 48 | 0 | 0 | 0 |  |
| p36-F8-3 | 48 | 0 | 0 | 0 |  |
| p36-F9-1 | 48 | 0 | 0 | 0 |  |
| p36-F9-2 | 48 | 0 | 0 | 0 |  |
| p36-F9-3 | 48 | 0 | 0 | 0 |  |
| p36-base-1 | 48 | 0 | 0 | 0 |  |
| p36-base-2 | 48 | 0 | 0 | 0 |  |
| p36-base-3 | 48 | 0 | 0 | 0 |  |

## arm 비교 B0 / B1 / C (run1 — 세 run 동일 여부 열)

| 변형 | pairs | B0 DIFF | B1 DIFF | C (규칙 후) | C 규칙 전 | target | B0 target DIFF | B1 target DIFF | C 기대 일치 | 사전 선언 매트릭스 | 실제 | 일치 | 세 run 동일 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 58 | 0 | 0 | {'SAME': 58} | {'SAME': 58} | - | - | - | - | - | - | - | ✔ |
| v1.1 | 58 | 0 | 0 | {'SAME': 58} | {'SAME': 58} | - | - | - | - | - | - | - | ✔ |
| v1.2 | 58 | 0 | 0 | {'SAME': 58} | {'SAME': 58} | - | - | - | - | - | - | - | ✔ |
| v1.3 | 58 | 0 | 0 | {'SAME': 58} | {'SAME': 58} | - | - | - | - | - | - | - | ✔ |
| v1.4 | 58 | 0 | 0 | {'SAME': 58} | {'SAME': 58} | - | - | - | - | - | - | - | ✔ |
| F0 | 60 | 1 | 1 | {'CONTRACT_VIOLATION': 1, 'SAME': 59} | {'CONTRACT_VIOLATION': 1, 'SAME': 59} | - | - | - | - | - | - | - | ✔ |
| F1 | 60 | 2 | 1 | {'CONTRACT_VIOLATION': 2, 'SAME': 58} | {'CONTRACT_VIOLATION': 2, 'SAME': 58} | 1 | 1 | 0 | ✔ | C만 | B1 미탐(C만) | 일치 | ✔ |
| F2 | 60 | 28 | 28 | {'CONTRACT_VIOLATION': 28, 'SAME': 32} | {'CONTRACT_VIOLATION': 28, 'SAME': 32} | 27 | 27 | 27 | ✔ | B1·C | B1 가시 | 일치 | ✔ |
| F3 | 60 | 8 | 1 | {'CONTRACT_VIOLATION': 8, 'SAME': 52} | {'CONTRACT_VIOLATION': 8, 'SAME': 52} | 7 | 7 | 0 | ✔ | C만 | B1 미탐(C만) | 일치 | ✔ |
| F4 | 60 | 3 | 2 | {'CONTRACT_VIOLATION': 3, 'SAME': 57} | {'CONTRACT_VIOLATION': 3, 'SAME': 57} | 2 | 2 | 1 | ✔ | C만 | B1 일부(1/2) | 반 칸(결함 요청 B1 미탐, 후속 조회 가시) | ✔ |
| F5 | 60 | 14 | 14 | {'CONTRACT_VIOLATION': 1, 'IMPROVEMENT': 13, 'SAME': 46} | {'CONTRACT_VIOLATION': 1, 'SAME': 46, 'UNCERTAIN': 13} | 13 | 13 | 13 | ✔ | 분류(B1 DIFF, C 분류) | B1 가시 | 일치 | ✔ |
| F6 | 60 | 27 | 27 | {'CONTRACT_VIOLATION': 1, 'IMPROVEMENT': 26, 'SAME': 33} | {'CONTRACT_VIOLATION': 1, 'SAME': 33, 'UNCERTAIN': 26} | 26 | 26 | 26 | ✔ | 분류(B1 DIFF, C 분류) | B1 가시 | 일치 | ✔ |
| F7 | 59 | 3 | 3 | {'CONTRACT_VIOLATION': 3, 'SAME': 56} | {'CONTRACT_VIOLATION': 3, 'SAME': 56} | 2 | 2 | 2 | ✔ | 분류(B1 DIFF, C 분류) | B1 가시 | 일치 | ✔ |
| F8 | 60 | 11 | 11 | {'CONTRACT_VIOLATION': 1, 'SAME': 49, 'UNCERTAIN': 10} / maxSel {'CONTRACT_VIOLATION': 11, 'SAME': 49} | {'CONTRACT_VIOLATION': 1, 'SAME': 49, 'UNCERTAIN': 10} | 10 | 10 | 10 | ✔ | B1에서도 | B1 가시 | 일치 | ✔ |
| F9 | 60 | 5 | 1 | {'CONTRACT_VIOLATION': 5, 'SAME': 55} | {'CONTRACT_VIOLATION': 5, 'SAME': 55} | 4 | 4 | 0 | ✔ | C만 | B1 미탐(C만) | 일치 | ✔ |

B1 미탐(target pair가 B1에서 SAME): F1 1건 (R000008/0); F3 7건 (R000003/0, R000007/0, R000012/0, R000029/0, R000033/0, R000041/0, R000045/0); F4 1건 (R000037/0); F9 4건 (R000027/0, R000032/0, R000036/0, R000044/0)

각주: 사전 선언의 "C만 잡는다"는 "B1이 못 잡는다(B0은 원문 비교라 DIFF까지는 보지만 분류는 못 함)"로 읽는다. 세션 검사 위반의 pair 귀속은 engine-v1.2 규칙(D-6/D20), bothStacks 플래그는 오탐·탐지율에 세지 않고 별도 보고(5절 sessionViolations).

## 판정 파일 무결성

디스크의 verdict*.json이 같은 pair 판정을 내는 메모리 보기(B0·B1·C_norules·C_rules·C_maxsel). `docs/phase3-metrics.json` `integrity`에 run별 전체.

- p35-base-1: verdict-B0.json = B0; verdict-B1.json = B1; verdict.json = C_norules, C_rules
- p35-v1.1-1: verdict-B0.json = B0; verdict-B1.json = B1; verdict.json = C_norules, C_rules
- p35-v1.2-1: verdict-B0.json = B0; verdict-B1.json = B1; verdict.json = C_norules, C_rules
- p35-v1.3-1: verdict-B0.json = B0; verdict-B1.json = B1; verdict.json = C_norules, C_rules
- p35-v1.4-1: verdict-B0.json = B0; verdict-B1.json = B1; verdict.json = C_norules, C_rules
- p36-base-1: verdict-B0.json = B0; verdict-B1.json = B1; verdict.json = C_norules, C_rules
- p36-F1-1: verdict-B0.json = B0; verdict-B1.json = B1; verdict-engine-v1.1.json = (없음 — 다른 엔진 버전의 기록); verdict.json = C_norules, C_rules
- p36-F2-1: verdict-B0.json = B0; verdict-B1.json = B1; verdict.json = C_norules, C_rules
- p36-F3-1: verdict-B0.json = B0; verdict-B1.json = B1; verdict.json = C_norules, C_rules
- p36-F4-1: verdict-B0.json = B0; verdict-B1.json = B1; verdict.json = C_norules, C_rules
- p36-F5-1: verdict-B0.json = B0; verdict-B1.json = B1; verdict-prelabel.json = C_norules; verdict.json = C_rules
- p36-F6-1: verdict-B0.json = B0; verdict-B1.json = B1; verdict.json = C_rules
- p36-F7-1: verdict-B0.json = B0; verdict-B1.json = B1; verdict.json = C_norules, C_rules
- p36-F8-1: verdict-B0.json = B0; verdict-B1.json = B1; verdict-maxselects.json = C_maxsel; verdict.json = C_norules, C_rules
- p36-F9-1: verdict-B0.json = B0; verdict-B1.json = B1; verdict.json = C_norules, C_rules
- p33-1: verdict-B0.json = B0; verdict-B1.json = B1; verdict.json = C_norules, C_rules
