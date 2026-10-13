# Phase 3.7 보고서 — 사다리 첫 측정: B0 / B1 / C + 평가 지표

- 작업일: 2026-10-14
- 범위: `engine/`과 `docs/`만. 클러스터 접근 없음, run 재실행 없음. 입력은 기존 run 산출물(p33·p35·p36)과 판정 파일(verdict·B0·B1·prelabel·maxselects·engine-v1.1)
- 결과: **PASS** — 지표 4개를 eval 세션 기준으로 보고, arm × 변형 표, 사전 선언 관측 매트릭스와 실제 일치(8칸 일치 + F4 반 칸)
- 도구: `engine/metrics.py`(평가 도구) → `docs/phase3-metrics.json`(결정론)·`docs/phase3-metrics.md`(표 전문)

## 0. 결정 필요 사항

없음.

## 1. 끝난 기준별 결과

| 기준 | 결과 | 근거 |
|---|---|---|
| 같은 runs를 엔진 설정만 바꿔 재판정(B0 / B1 / C) | PASS | `metrics.py`가 p35-base·v1.1~v1.4·p36-base·F1~F9·p33 각 3 run(48 run)을 메모리에서 B0·B1·C 규칙 전·C 규칙 후(+F8 maxSelects)로 판정. 디스크 판정 파일과 무결성 대조 — 모든 verdict·B0·B1 파일이 해당 보기와 pair 판정 동일(`verdict-engine-v1.1.json`만 다른 버전 기록) |
| arm × 변형 표(diff·Uncertain·탐지율·오탐) | PASS | 아래 2절 |
| 관측 매트릭스와 실제 일치 | PASS | 9칸 중 8칸 일치 + F4 반 칸(결함 요청 R000037은 B1 미탐, 후속 조회 R000038은 B1 가시) — 3절 |
| 지표 4개가 eval 세션 기준으로 보고됨 | PASS | 4절. 분모·분자 명시 |
| 결정론 | PASS | `metrics.py` 2회 실행 `phase3-metrics.json` 바이트 동일(`cmp`) |

## 2. arm × 변형 (run1 값 — 세 run 동일, 15/15 그룹)

| 변형 | pairs | B0 DIFF | B1 DIFF | C 규칙 전 | C 규칙 후 | target | B0 / B1 target DIFF | C 기대 일치 | 정상 경로 오탐 |
|---|---|---|---|---|---|---|---|---|---|
| base(A/A) | 58 | 0 | 0 | SAME 58 | SAME 58 | — | — | — | — |
| v1.1 | 58 | 0 | 0 | SAME 58 | SAME 58 | — | — | — | — |
| v1.2 | 58 | 0 | 0 | SAME 58 | SAME 58 | — | — | — | — |
| v1.3 | 58 | 0 | 0 | SAME 58 | SAME 58 | — | — | — | — |
| v1.4 | 58 | 0 | 0 | SAME 58 | SAME 58 | — | — | — | — |
| F0 (baseline) | 60 | 1 | 1 | SAME 59 · CV 1 | 같음 | R47 CV · R48 SAME | 1/1 | ✔ | — |
| F1 멱등 검사 제거 | 60 | 2 | 1 | SAME 58 · CV 2 | 같음 | 1 | 1 / **0** | ✔ | 0 (v1.1 기준 1) |
| F2 order_items INSERT 누락 | 60 | 28 | 28 | SAME 32 · CV 28 | 같음 | 27 | 27 / 27 | ✔ | 0 |
| F3 커밋 전 발행 | 60 | 8 | 1 | SAME 52 · CV 8 | 같음 | 7 | 7 / **0** | ✔ | 0 |
| F4 롤백 누락 | 60 | 3 | 2 | SAME 57 · CV 3 | 같음 | 2 | 2 / **1** | ✔ | 0 |
| F5 JOIN FETCH | 60 | 14 | 14 | SAME 46 · UNC 13 · CV 1 | SAME 46 · **IMP 13** · CV 1 | 13 | 13 / 13 | ✔(전·후) | 0 |
| F6 itemCount | 60 | 27 | 27 | SAME 33 · UNC 26 · CV 1 | SAME 33 · **IMP 26** · CV 1 | 26 | 26 / 26 | ✔ | 0 |
| F7 timeout 1s | 59 | 3 | 3 | SAME 56 · CV 3 | 같음 | 2 | 2 / 2 | ✔ | 0 |
| F8 N+1 | 60 | 11 | 11 | SAME 49 · UNC 10 · CV 1 | 같음 (maxSelects: SAME 49 · CV 11) | 10 | 10 / 10 | ✔(두 설정) | 0 |
| F9 쿠폰 use 2회 | 60 | 5 | 1 | SAME 55 · CV 5 | 같음 | 4 | 4 / **0** | ✔ | 0 |

B1 미탐(target pair가 B1에서 SAME): F1 1건(R000008), F3 7건(첫 결제 전부), F4 1건(R000037), F9 4건(쿠폰 주문 생성 전부) — 합계 13 pair. 모두 응답·SQL 축에 흔적이 없고 외부 호출·타임라인·트랜잭션·hop 축에만 있다.

## 3. 사전 선언 관측 매트릭스(계획 3.7) vs 실제

| 결함 | 사전 선언 | 실제(B1 target DIFF) | 일치 |
|---|---|---|---|
| F1 | C만 | 0/1 | 일치 |
| F2 | B1(쓰기 문장)·C 모두 | 27/27 | 일치 |
| F3 | C만 | 0/7 | 일치 |
| F4 | C만 | 1/2 | **반 칸** — 결함 요청(R000037: 응답 400·SQL 같음, 트랜잭션 outcome만 다름)은 B1 미탐, 후속 조회(R000038: 404→200)는 B1 가시 |
| F5 | 분류(B1 DIFF까지, C가 Improvement로) | 13/13 DIFF, C UNC→IMP | 일치 |
| F6 | 분류 | 26/26 DIFF, C IMP | 일치 |
| F7 | 분류(C가 CV로) | 2/2 DIFF, C CV | 일치 |
| F8 | B1에서도 보인다(SQL 횟수) | 10/10 | 일치 |
| F9 | C만 | 0/4 | 일치 |

각주: 사전 선언의 "C만 잡는다"는 **"B1이 못 잡는다"**로 읽는다 — B0은 원문 비교라 DIFF까지는 보지만(F1·F3·F4·F9 target 모두 B0 DIFF) 그것이 결함인지 개선인지 잡음인지 분류하지 못한다(사다리·A/A에서는 B0 DIFF 0이라 이번 데이터로는 B0의 잡음 오탐을 재지 못함 — 7절 한계). 세션 검사 위반의 pair 귀속은 engine-v1.2 규칙(D20), bothStacks 플래그는 오탐·탐지율에 세지 않고 별도 보고 — 판정한 run 전체에서 sessionViolations 3건(F1 세 run, 모두 R000008 귀속), bothStacks 0건.

## 4. 지표 4개 (eval 세션 기준)

### 4.1 결함 탐지율

- **결함 단위**(3 run 모두 target 판정·runCheck가 기대와 일치): 진짜 결함 **6/6**(F1·F2·F3·F4·F7·F9), 성능 계약 **1/1**(F8 — 기본 UNC·maxSelects CV 둘 다), 분류 대상 **2/2**(F5 규칙 전 UNC·후 IMP, F6 IMP) — 합계 **9/9**
- **pair 단위**: **92/92**(F1 1 + F2 27 + F3 7 + F4 2 + F5 13 + F6 26 + F7 2 + F8 10 + F9 4; F5는 전·후 둘 다 맞아야 1) + F8 maxSelects **10/10**
- 정상 경로 오탐(baseline과 다른 non-target): 전 변형 0. F1만 engine-v1.1 기준 1(R000007, 세션 귀속 — D20)

### 4.2 수동 검토 감소율 (eval 세션, run당 — 세 run 동일)

규칙 전 = `C_norules`(contract.yaml만), 규칙 후 = `C_rules`(learned 3 + 사전 승인 1).

| 변형 | eval pair | eval UNC 규칙 전 → 후 | 감소 출처 | learn UNC 전 → 후 (참고) |
|---|---|---|---|---|
| F1~F4 | 35 ×4 | 0 → 0 | — | 0 → 0 |
| F5 | 35 | **8 → 0** | learned 8 | 5 → 0 |
| F6 | 35 | **17 → 0** | 사전 승인 17 | 9 → 0 |
| F7 | 34 | 0 → 0 | — | 0 → 0 |
| F8 | 35 | 6 → 6 | — | 4 → 4 |
| F9 | 35 | 0 → 0 | — | 0 → 0 |
| **합계(F1~F9)** | 314 | **31 → 6 (감소율 80.7%)** | learned 8 + 사전 17 | 18 → 4 |
| **합계(F8 제외)** | 279 | **25 → 0 (감소율 100.0%)** | | 14 → 0 |

각주: F8의 eval Uncertain 6은 maxSelects 미선언 시 **의도된 결과**(성능 계약이 선언되지 않은 실행 특성 차이는 사람에게 — D18)라 규칙으로 줄일 대상이 아니다. 숫자에서 빼지 않고 두 줄로 보인다. 3 run 합계로는 ×3(93 → 18).
비율의 분모를 eval pair 전체로 잡으면 Uncertain 비율은 31/314(9.9%) → 6/314(1.9%).

### 4.3 오판정률

진짜 결함(F1·F2·F3·F4·F7·F9) target pair **43개 × 3 run = 129 판정** 중 규칙(learned 3 + 사전 1)에 의해 SAME·IMPROVEMENT로 바뀐 것: **0/129 (0.0%)**.

규칙 적용 횟수(run1, pair-규칙 수 — 세 run 동일): learned는 F5에서만 26(13 pair × 규칙 2), 사전 승인은 F6에서만 26. 사다리 base·v1.1~v1.4, F0~F4, F7~F9에서는 learned·사전 모두 **0** — F5 외 변형에서 learned 규칙 적용 0.

### 4.4 Rule 재사용 효과 (F5 learn 5 pair → learned 규칙 3)

- (a) F5 eval: Uncertain → Improvement **8 pair**
- (b) 다른 변형(F0~F4, F6~F9): **0**
- (c) 사다리 v1.3·v1.4: **0**(사다리 전체 0 — 사다리에는 Uncertain 자체가 없었다)

해석: (b)·(c)의 0은 "재사용되지 않음 = **과적용 없음**"의 증거다. 특히 F8(SELECT 2 → 3·4)은 F5 규칙(2 → 1, 특정 callTree)과 같은 "SELECT 수 변화"지만 규칙이 맞지 않아 Uncertain으로 남았다. 재사용의 양(eval 8)은 같은 유형(F5)의 다른 세션에서만 나왔고, 다른 유형으로의 일반화는 이번 데이터에 없다.

### 4.5 운영 지표 (참고)

- Phase 3 run 디렉터리(p31~p36): 57 — 판정·게이트 대상 55, 판정 전에 걸러진 run 2(`p35-v1.1-oom-1` Metaspace OOM: degraded 7 / `p35-v1.1-stale-1` runId 재사용: degraded 4)
- 판정·게이트 대상 55 run 합계: Undelivered(진입 홉) **0**, degraded **0**, settleTimeouts **3**(p36-F7 세 run의 `R000041/new/0.e1` — F7 결함 증상, D19 보완으로 지표화)
- 3 run 판정 일치(C, pair 단위 완전 일치): **16/16 그룹**(A/A p33, 사다리 5, F0~F9)

## 5. 변경 파일·커밋

| 커밋 | 내용 |
|---|---|
| (이 커밋) phase3.7: 지표·arm 비교·보고서 | `engine/metrics.py`, `docs/phase3-metrics.json`, `docs/phase3-metrics.md`, `docs/reports/phase3.7.md`, `docs/phase3-plan.md`(3.7·3.8 구현 시 확정), `docs/decision-log.md`(D20·D21·D22) |
| 다음 커밋 phase3: result·findings·references, Phase 3 완료 | `docs/phase3-result.md`, `docs/findings.md`, `docs/references/{kakaopay,woowahan}-kotlin-migration.md`, `industry-cases-phase3.md`, `call-graph.md` 메모, `CLAUDE.md` → tag `phase3-done` |

## 6. 실행 명령·주요 출력

```
.venv/bin/python engine/metrics.py          → docs/phase3-metrics.json · docs/phase3-metrics.md (stdout = md)
  결함 단위 9/9, pair 92/92 + maxSelects 10/10, eval UNC 31→6(80.7%) / F8 제외 25→0, 오판정 0/129,
  재사용 (a) 8 (b) 0 (c) 0, 3 run 일치 16/16, Undelivered 0 · degraded 0 · settleTimeouts 3
.venv/bin/python engine/metrics.py (2회) → cmp phase3-metrics.json 동일
```

## 7. 해석·한계

해석
- **C가 B1 위에 더한 것**은 두 가지다. ① **보이지 않던 결함**: 응답·SQL에 흔적이 없는 13 target pair(F1·F3·F4 일부·F9)를 외부 호출·타임라인·트랜잭션·hop 축으로 잡았다. ② **분류**: B1이 "다르다"까지만 본 F5·F6·F8을 Improvement(규칙)·Uncertain(사람)·CV(선언 시)로 갈랐다. 수동 검토 감소(eval 31 → 6)는 이 분류에서 나온다
- 사다리(v1.1~v1.4)는 B0까지 0이라 "Kotlin 점진 전환은 이 corpus 범위에서 행동을 바꾸지 않았다"는 결론은 arm과 무관하다

한계
- **규칙 학습 데이터가 F5 한 유형**: learned 규칙 3개는 모두 F5에서 나왔다. Rule 재사용 효과(eval 8)는 같은 유형의 다른 세션에 대한 것이고, 다른 유형으로의 재사용(b·c = 0)은 "과적용 없음"으로만 해석할 수 있다
- **D20(세션 귀속)은 F1 결과를 본 뒤 일반화**: F1의 정상 경로 오탐 0은 v1.2 기준이다(v1.1 기준 1). 탐지율에는 영향 없음
- **corpus 커버리지 = 검증 범위**: F0(sku 없음 409 vs 400)은 corpus에 해당 입력을 넣은 뒤에야 보였다. corpus가 닿지 않는 입력·경로의 차이는 어느 arm으로도 보이지 않는다
- **규모**: 단일 노드 kind, corpus v2.1 48 요청(60 pair), 변형당 3 run. 결정론적 재생이라 같은 corpus의 반복은 새 표본이 아니다(평가 분리는 세션·변형으로)
- **B0의 잡음 오탐은 재지 못함**: 설계로 잡음을 0으로 만든 환경이라(A/A·사다리 B0 DIFF 0) B0이 실제 운영에서 낼 잡음 DIFF는 이 데이터에 없다
- **분류 대상의 정답은 사람이 정한 것**: F5(Improvement)·F6(사전 승인)의 "정답"은 라벨·승인이며, 규칙이 맞게 적용됐는지를 잰 것이지 라벨 자체의 옳음을 잰 것은 아니다
