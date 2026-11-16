# Phase 4.5 보고서 — 서비스 간 변경 Coupon C1·C2

- 작업일: 2026-11-02
- 범위: 관측된 차이 정의 변경(D26), C1·C2 사전 등록, 브랜치·이미지, 전체 재생 3회 + Filter 3회씩, same 라벨, ablation·B2-S. Legacy 이미지·기존 판정 파일 변경 없음
- 결과: **PASS** — C1·C2 판정·영향·Recall·Filter 동등성 모두 등록 기대와 일치, 13 변형 지표 변화 0. 재생 기대와의 작은 차이 1건은 6절에 기록(판정 영향 없음). **결정 필요 0건**

## 0. 결정 필요 사항

없음.

## 1. 끝난 기준별 결과

**범위 확인**(`logs/phase4.5-branches.txt`)

| 브랜치 | 커밋 | diff(`phase3.3-base..`) |
|---|---|---|
| `change/C1` | `bc4edbe`, 1개 | `M services/coupon/.../OrderPaidListener.java`, -1줄(`couponService.settle` 호출) |
| `change/C2` | `1cba45e`, 1개 | `M services/coupon/.../CouponService.java`, +3줄(`existsByCouponKey` 확인, 뒤의 NOT_FOUND 처리 유지) |

두 변경 모두 `services/coupon`의 파일 1개만 바뀐다. 이미지도 대조했다: 의존성 jar 75개 이름·크기 동일, evidence-collector 클래스 차이 0, JRE 17.0.20.1 동일.

**관측된 차이 정의(D26)**

| 기준 | 결과 | 근거 |
|---|---|---|
| C2 첫 run 전 등록 | PASS | `f7a2636` — `docs/phase4-plan.md` 구현 시 확정 (4.5), `docs/fault-expectations.json` `_observedDiff`, decision-log D26 |
| 기존 13 변형 회귀 확인 | PASS | 정의 변경 전후 `phase4-metrics.json` **바이트 동일**(`logs/phase4.5-metric-regression.txt`). C1·C2 추가 후에도 기존 항목 동일. 엔진·판정 파일 변경 없음 |

**C1**

| 기준 | 결과 | 근거 |
|---|---|---|
| 쿠폰 결제 `0.e1` 3 pair CV ×3 run | PASS | R000029·R000033·R000045, 3 run 동일, 정상 경로 오탐 0. `logs/phase4.5-fault-check.txt` |
| dbstate 위반 | PASS | `dbstate_equal` false ×3, coupons 해시 불일치(건수 6 동일). 정본은 집계 해시라 "SETTLED 3 → 0"을 행으로 읽지는 못했고, Legacy `update coupons`가 있는 3개 소비 홉이 New에서 사라진 것으로 확인 |
| 영향 7세션·37.5% | PASS | 사전 등록 일치, 영향 요청 7(R000008 제외) |
| Recall 1.0 | PASS | 3/3, 3 run 동일 |
| ablation(b) 미관측 → 전역 | PASS | `OrderPaidListener` 진입 홉에 없음 → 참조 없음 → 전역, 11세션·0% |
| Filter 판정 동일 | PASS | 40 pair ×3 전체 재생과 일치, dbstate false 재현(부분 상태 coupons 3건) |

**C2**

| 기준 | 결과 | 근거 |
|---|---|---|
| Uncertain 9 pair, 유형 2종 | PASS | 라벨 전 UNCERTAIN 9(learn 6 + eval 3), `dbRead.countDelta` 1→2·`callTree.sequenceReplaced`뿐. 정상 경로 오탐 0 |
| learn 라벨 same | PASS | uid `aa06c259e967`, `cfb6811c9f5c`를 `same`으로 라벨(`215b8cb`, provenance runId `p45-C2-1`, split learn, S004·S006·S008) |
| eval Uncertain 3 → 0 | PASS | 라벨 후 Uncertain 0. 최종 SAME 9 pair 모두 `appliedRules` 2개 유지 |
| 영향 6세션·40% | PASS | 6세션·29요청, 감소율 39.6%(계획의 40%는 반올림) |
| Recall 1.0 | PASS | 9/9, D26 정의 기준. 옛 정의였다면 분모 0이다 |
| ablation(a) 11세션 | PASS | 11세션·0% |
| ablation(b) 6세션·Recall 1.0, 영향 요청 24 → 16 | PASS | 일치(D-4.1b 등록). Tag 보조: 요청 입도 9 → 4(4절) |
| Filter 판정 동일 | PASS | 37 pair ×3 전체 재생과 일치, SAME 37 중 9 pair `appliedRules` 유지, dbstate true |
| Rule 재사용 기록 | PASS | 직접 `coupon.use`(hop `0`)와 Order가 부른 `0.h1`이 같은 uid(엔드포인트가 둘 다 `coupon.use`) — eval의 R000024/0, R000032/0.h1, R000044/0.h1에 적용 |

**공통**

| 기준 | 결과 | 근거 |
|---|---|---|
| B2-S C1 ≈ 0.21 | PASS | 330 조합 중 Recall 1.0 비율 **0.2121**(C(8,4)/C(11,7)) |
| 사전 등록 대조 | PASS | 영향 C1·C2 일치(impact-v1.1, 도구 변경 후 처음 재본 독립 대조), 판정 `fault_check` 5건 일치, Filter `run_check` 불일치 0 |
| 전달·재현 | PASS | 12 run Undelivered·degraded·settleTimeouts 0, verify 12/12 PASS, `dirty: false`, 3 run 판정 동일 |
| 회귀 | PASS | `rejudge_check` 변화 0(same 규칙 추가 후 기존 150 판정 파일), p44·p45-C1도 0, pytest scoping 87·engine 39, `check_inputs` 64/64 |

## 2. 변경 파일·커밋

| 커밋 | 내용 |
|---|---|
| `f7a2636` phase4.5: 관측된 차이 정의(D26)·C1·C2 기대 사전 등록, 13 변형 회귀 확인 | `scoping/{evaluate,tag,run_check,check_scope}.py`, 테스트, `docs/{fault-expectations,filter-expectations}.json`, `docs/{decision-log,phase4-plan}.md` |
| `bc4edbe` (change/C1), `1cba45e` (change/C2) | 각 1커밋, 이미지 `coupon-app:phase4-C1`·`phase4-C2` |
| `672357c` phase4.5: C1·C2 impact | `scoping/impacts/{C1,C2}.json`, 범위 기록 |
| `215b8cb` phase4.5: C2 learn 라벨 same 2건 | `engine/rules/learned/{aa06c259e967,cfb6811c9f5c}.yaml` |
| (이 커밋) phase4.5: 결과·보고서 | `scoping/evaluate.py`(C1·C2), 테스트, `docs/phase4-metrics.json`, 이 문서, 로그, `docs/findings.md`(O21), `CLAUDE.md` |

## 3. 실행 명령·주요 출력

```
docker build -f services/coupon/Dockerfile -t coupon-app:phase4-C<n> <wt>/services/ → docker save → kind load image-archive
kubectl kustomize deploy/k8s/new | sed 's#coupon-app:phase3.3-base#coupon-app:phase4-C<n>#' | kubectl apply -f -
k6/run.sh --run-id p45-C<n> --iterations 3 --vus 3
k6/run.sh --run-id p45-C<n>-f --iterations 3 --vus 3 --impact scoping/impacts/C<n>.json
verdict.py --out verdict-prelabel.json(C2) → review.py label --as same ×2 → verdict.py → fault_check --expect-key afterLearnLabels
.venv/bin/python scoping/evaluate.py   → 3 run 판정 동일 15/15, Recall < 1 없음
.venv/bin/python scoping/run_check.py  → 불일치 run 0건
```

전문: `docs/reports/logs/phase4.5-{branches,metric-regression,scope-check,runs,fault-check,run-check,rejudge,metrics,pytest}.txt`. run 뒤 new overlay를 복원했다(coupon `phase3.3-base`, order `phase3.5-v1.4`).

## 4. Legacy/New 비교 결과와 수치

| 변형 | 세션 | 요청 | 감소(요청) | 감소(세션) | Recall | +F0 | 탐지 유지 | Precision | B2-S k개 평균·최소·1.0 비율 | B2-S 예산 평균·1.0 비율 |
|---|---|---|---|---|---|---|---|---|---|---|
| C1 | 7 | 30 | 37.5% | 36.4% | 1.0 | 0.75 | 3/3 | 0.075 | 0.636·0·**0.2121** (330) | 0.450·0.078 (1651) |
| C2 | 6 | 29 | 39.6% | 45.5% | 1.0 | 0.9 | 9/9 | 0.243 | 0.545·0.111·**0.0022** (462) | 0.431·0.001 (1570) |

**판정**(pair, 3 run 동일)

| run | 판정 | dbstate |
|---|---|---|
| C1 전체 60 | CV 4(target 3 + F0), SAME 56 | false |
| C1 Filter 40 | CV 3, SAME 37 | false |
| C2 전체, 라벨 전 60 | UNCERTAIN 9, CV 1(F0), SAME 50 | true |
| C2 전체, 라벨 후 60 | CV 1(F0), SAME 59(그중 9 pair 규칙 적용) | true |
| C2 Filter 37 | SAME 37(그중 9 pair 규칙 적용) | true |

**ablation** — 13 변형에서는 없던 차이가 여기서 처음 나타난다

| 변형 | 맵 | 전역 | 세션 | 요청 | 영향 요청 | 감소 | Recall | Tag 세션 입도 예산·포함 | Tag 요청 입도 예산·포함 |
|---|---|---|---|---|---|---|---|---|---|
| C1 | 정본 | - | 7 | 30 | 7 | 37.5% | 1.0 | 66.7%·1.0 | 23.3%·1.0 |
| C1 | (a) 엔드포인트 | - | 7 | 30 | 8 | 37.5% | 1.0 | 66.7%·1.0 | 25.0%·1.0 |
| C1 | (b) 합산 없음 | **전역** | 11 | 48 | 48 | **0%** | 1.0 | 100%·1.0 | 100%·1.0 |
| C2 | 정본 | - | 6 | 29 | 24 | 39.6% | 1.0 | 61.7%·1.0 | 53.3%·1.0 |
| C2 | (a) 엔드포인트 | - | **11** | 48 | 34 | **0%** | 1.0 | 100%·1.0 | 76.7%·1.0 |
| C2 | (b) 합산 없음(Tag 보조) | - | 6 | 29 | **16** | 39.6% | 1.0 | 61.7%·1.0 | 26.7%·**0.444** |

세 ablation 효과가 갈린다.
- **요청 단위 맵 vs 엔드포인트 합집합**: C2 감소율 39.6% → 0%
- **홉 합산 vs 없음(Kafka 홉)**: C1 37.5% → 0%(fail-closed 전역)
- **홉 합산 vs 없음(HTTP 홉)**: C2 세션 선택은 같고, 요청 입도 Tag만 9 → 4로 떨어진다. `0.h1` 5 pair가 영향 요청에서 빠진다(D-4.1b 예상대로)

**사람 검토 감소**(규칙 적용 후 verdict): C2 eval Uncertain 3 → 0, learn 6 → 0, 라벨 2건.

**시간(참고)**: run 전체 C1 34~36초 / C1 Filter 34~36초 / C2 35~36초 / C2 Filter 31~34초, 리셋이 28~32초. C2 Filter의 k6 최장 VU 0.6~1.0초(전체 2.7~3.4초)는 재생 수보다 S009의 2초 지연 스텁이 선택에서 빠진 영향이 크다.

## 5. 지시와 다르게 구현한 것

- **Precision도 새 정의를 쓴다**: 지시 목록에 없지만 옛 정의를 두면 C2에서 0이 되어 Recall과 어긋난다. 13 변형 수치는 그대로다
- **결함 탐지 유지는 정의 변경 영향이 없다**: target 기준이라 코드 변경 없음
- **`_observedDiff`는 `fault-expectations.json`에 등록**: `scope-expectations.json`은 4.2 이후 그대로 두라는 조건을 지켰다. 이 파일의 C1·C2 기대도 변경 없음
- **`filter-expectations.json` v2로 C1·C2 케이스 추가**: 4.4 케이스는 그대로
- **`check_scope.py`**: `status`가 있어도 head 브랜치가 생기면 실행하도록 변경
- **C1 `settle` 호출 1줄 삭제로 빈 `if`가 남는다**: 계획의 "1 클래스 1줄"을 그대로 따랐다
- **p44 Tag run의 `tags.json` 재생성**: 새 필드 `observedDiff` 때문. 판정 파일은 그대로, `run_check`로 다시 확인

## 6. 문제·해결·남은 한계

- **등록과 다른 점 1건(판정 영향 없음)**: C1의 등록 축은 `writeSet`·`callTree`였는데, 실제 CV 사유에는 `transactions.outcomes`도 있다(settle 트랜잭션이 사라짐). 등록에서 놓친 축이고 고치지 않았다
- **`dbstate`로는 행 값을 못 읽는다**: 집계 해시·건수·합계만 있어 "SETTLED 3 → 0"은 쓰기 집합으로 간접 확인했다
- **이미지 크기 약 3MB 차이**: `coupon-app:phase3.3-base`와 새 이미지의 베이스 레이어 차이다. JRE·의존성·검증 모듈은 같고, `eclipse-temurin:17-jre`가 고정 digest가 아니라서 생긴 것으로 보인다(원인 검증은 안 함)
- **Recall 1.0은 corpus 안의 값이다**: C1은 쿠폰 결제 세션이 첫 결제 세션의 부분집합이라 맞았다. 클래스 입도라 쿠폰 없는 결제 4세션도 재생했다(Precision 0.075) — 영향 ≠ 차이
- **C2의 규칙 재사용**: Order 코드가 아니라 Coupon이 처리한 `0.h1` 홉에 적용된 것이다. 부모 `order.create` pair는 원래 SAME이다
- **O21**: HTTP 홉 합산의 효과가 세션 선택에서 보이지 않는 이유 — findings
