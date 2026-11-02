# Phase 4.4 보고서 — 파이프라인 Tag/Filter + 실제 run

- 작업일: 2026-11-02
- 범위: `k6/run.js`·`run.sh` `--impact`·`--tag`, `scoping/tag.py`·`run_check.py`, `engine/fault_check.py --impact`, 기대 사전 등록, 실제 run 8회(Filter F3·F9 ×3, Tag F8·F3 ×1)
- 결과: **PASS** — Filter 재생 pair 판정 == 전체 재생 같은 pair 89/89(3 run씩), dbstate 기대 일치, Undelivered·degraded 0, Tag 비-SAME pair 전부 inScope. 사전 등록과 불일치 0. **결정 필요 1건**

## 0. 결정 필요 사항

**D-4.4a C2의 구체 리팩터링 — 4.5 시작 전에 필요 (계획 7절이 질문으로 남긴 항목)**

`CouponService.use`는 지금 `findByCouponKey` SELECT 1회 뒤 필요하면 UPDATE한다(R000017·R000020·`0.h1` 실측). 이미 1쿼리라 "2쿼리 → 1쿼리"는 할 수 없다.
- **(A) 권장** 1쿼리 → 2쿼리: `use` 앞에서 `existsByCouponKey`로 존재를 확인하고 없으면 NOT_FOUND, 있으면 기존대로 `findByCouponKey`. 쓰기 집합·응답·최종 상태가 같고 SELECT만 1 늘어 계획의 기대(dbRead Uncertain → learn 라벨 → eval 0)에 맞는다. callTree에 `existsByCouponKey` 노드가 추가되므로 callTree Uncertain도 함께 나올 수 있다 — 4.5 `fault-expectations.json`에 함께 등록한다
- (B) `findByCouponKey` 대신 다른 조회(예: `@Query` 조회 메서드)로 교체 — SELECT 수는 1 그대로이고 SQL 문장만 바뀐다. 읽기 횟수가 아니라 문장 차이를 시험한다. 계획의 "존재 확인 + 조회" 예시에서 멀어진다

## 1. 끝난 기준별 결과

| 기준 | 결과 | 근거 |
|---|---|---|
| 기대를 run 전에 등록 | PASS | `docs/filter-expectations.json`, `2914f59`(run의 `git.rev`, dirty false). `scope-expectations.json`은 변경 없음 |
| Filter: 재생 pair 판정 == 전체 재생 같은 pair(100%) | PASS | F3 40 pair ×3, F9 49 pair ×3 전부 일치, pair 집합 동일. `logs/phase4.4-run-check.txt` |
| Filter: 세션 검사 동일 | PASS | 선택 세션 안 `sessionViolations` 전체 재생과 동일(둘 다 0건) |
| Filter: run 범위 dbstate 판정이 기대와 같음 | PASS | F3·F9 `dbstate_equal` true ×3. 실제 부분 상태로 비교됐다(4절) |
| Filter: Undelivered·degraded 0 | PASS | 6 run 모두 0, settleTimeouts 0, verify_sameness 6/6 PASS |
| Filter: 재생 수 = impact.json 선택 수 | PASS | F3 30, F9 37, 요청 집합까지 동일(run.sh가 불일치면 중단) |
| Filter: 시간 기록(참고) | PASS | 4절 |
| `fault_check --impact` | PASS | F3 target 7/7, F9 4/4, not replayed 0, 정상 경로 오탐 0, 세 run 동일. `logs/phase4.4-fault-check.txt` |
| Tag: 비-SAME pair 전부 inScope 구간 안 | PASS | F3 7/7, F8 10/10(F0 제외, Recall 정의). `logs/phase4.4-tags.txt` |
| Tag: 판정·Uncertain·재생 수 전체 재생과 동일 | PASS | F3 CV 8·SAME 52, F8 UNCERTAIN 10·CV 1·SAME 49, 48요청, pair별 일치 |
| 회귀 | PASS | pytest scoping 84·engine 39 passed, `check_inputs` 64/64, `check_scope` 불일치 0 |

**D-4.3a 이행**: `inScope` = 세션 입도, `impactedRequest` 병기, 리뷰 순서 3단(영향 요청 → 같은 세션의 나머지 → 범위 밖), 요청 입도는 보조(4절). O15 ↔ O19 상호 링크 추가.

## 2. 변경 파일·커밋

| 커밋 | 내용 |
|---|---|
| `2914f59` phase4.4: Filter·Tag 파이프라인, tag.py·run_check.py, 기대 사전 등록(run 전) | `k6/{run.js,run.sh}`, `engine/fault_check.py`, `engine/tests/test_fault_check.py`, `scoping/{tag,run_check}.py`, `scoping/tests/test_tag.py`, `docs/filter-expectations.json`, `docs/findings.md`(O15·O19 링크), `docs/phase4-plan.md`(구현 시 확정 (4.4)) |
| (이 커밋) phase4.4: 결과·보고서 | 이 문서, `docs/reports/logs/phase4.4-*.txt`, `docs/findings.md`(O20), `CLAUDE.md` |

## 3. 실행 명령·주요 출력

```
kubectl kustomize deploy/k8s/new | sed 's#order-app:phase3.5-v1.4#order-app:phase3.6-F<n>#' | kubectl apply -f -
k6/run.sh --run-id p44-F3-f --iterations 3 --vus 3 --impact scoping/impacts/F3.json
k6/run.sh --run-id p44-F3-t --iterations 1 --vus 3 --tag scoping/impacts/F3.json
k6/run.sh --run-id p44-F9-f --iterations 3 --vus 3 --impact scoping/impacts/F9.json
k6/run.sh --run-id p44-F8-t --iterations 1 --vus 3 --tag scoping/impacts/F8.json
verify_sameness ×8 → PASS / verdict.py --arm C ×8 / scoping/tag.py ×2
.venv/bin/python scoping/run_check.py      → 불일치 run 0건
.venv/bin/python engine/fault_check.py --fault F<n> --run-base p44-F<n>-f --impact …   → 기대와 일치
```

전문: `docs/reports/logs/phase4.4-{runs,run-check,fault-check,tags,pytest}.txt`. run 뒤 new order를 `phase3.5-v1.4`로 되돌렸다.

## 4. Legacy/New 비교 결과와 수치

**Filter** — 판정은 3 run 동일

| 변형 | 세션 | 재생 요청 | pair | 판정 | 전체 재생 같은 pair | target | dbstate |
|---|---|---|---|---|---|---|---|
| F3 | 7/11 | 30/48 | 40 | CV 7, SAME 33 | 40/40 ×3 | 7/7 | true |
| F9 | 9/11 | 37/48 | 49 | CV 5, SAME 44 | 49/49 ×3 | 4/4 | true |

F9의 CV 5는 target 4 + F0(`R000047/0`, S011 선택됨)이다. F3은 S011을 재생하지 않아 F0가 없다.

**run 범위 dbstate — 부분집합에서 실제로 잰 값**(재구성 아님, run 1)

| 변형 | 재생 | coupons | order_items | orders | 판정 |
|---|---|---|---|---|---|
| F3 | Filter | 3 | 9 | 7 | 일치 |
| F3 | 전체 | 6 | 10 | 8 | 일치 |
| F9 | Filter | 4 | 10 | 8 | 일치 |
| F9 | 전체 | 6 | 10 | 8 | 일치 |

**시간(참고, run 3회 범위)** — 요청 수 감소가 시간 감소로 그대로 이어지지 않는다

| 변형 | 재생 | run 전체(초) | 그중 리셋(초) | k6 최장 VU(초) |
|---|---|---|---|---|
| F3 | Filter 30요청 | 34~37 | 29~32 | 2.5~3.6 |
| F3 | 전체 48요청 | 37~42 | 30~35 | 3.6~4.6 |
| F9 | Filter 37요청 | 34~36 | 28~31 | 3.0~3.9 |
| F9 | 전체 48요청 | 37~43 | 32~36 | 3.2~4.5 |

run 전체의 약 85%가 리셋(MySQL·Kafka rollout restart)이다. 전체 재생 시각은 다른 날 측정이라 직접 비교용이 아니다.

**Tag**(`tags.json`, 전체 재생 60 pair)

| 변형 | tier 1 영향 요청 | tier 2 같은 세션 | tier 3 범위 밖 | 세션 입도 예산·포함 | 요청 입도(보조) 예산·포함 |
|---|---|---|---|---|---|
| F3 | 14 | 26 | 20 | 66.7%·7/7 | 23.3%·7/7 |
| F8 | 44 | 5 | 11 | 81.7%·10/10 | 73.3%·10/10 |

F3의 F0(`R000047/0`)는 tier 3이다. 끝난 기준은 Recall 정의대로 F0를 뺐다. Tag는 판정·재생 수를 바꾸지 않았고 검토량 감소를 뜻하지 않는다.

## 5. 지시와 다르게 구현한 것

- **`docs/filter-expectations.json` 별도 파일**: `scope-expectations.json`을 그대로 두라는 D-4.2a 조건을 지키려고 나눴다
- **dbstate 기대**: 계획 "결함 변형이면 위반"을 그대로 쓰면 F3·F9는 위반이어야 하지만 전체 재생에서 두 변형 모두 일치다. 전체 재생 값을 기대로 등록했다(구현 시 확정 (4.4))
- **`scoping/run_check.py` 추가**(계획 밖) — Filter·Tag 대조를 재현 가능하게
- **k6-summary에 `sessions` 필드 추가**, run-meta에 `scope`(스코프 run만). `SESSIONS` 없는 기본 경로의 재생 동작은 같다 — F3·F8 Tag run(전체 재생)의 판정이 Phase 3와 pair별로 같아 회귀를 확인했다. 별도 A/A run은 하지 않았다
- **인증서 복구 범위**: 문서의 ingressgateway·order 재시작보다 넓게, `legacy`·`new`의 사이드카 Deployment 전체와 도구 pod 2개를 재시작했다(6절)

## 6. 문제·해결·남은 한계

- **메시 전체 인증서 만료(O20)**: 시작 시점에 워크로드 인증서가 약 3시간 전 만료된 상태였다(`VALID CERT false`). 호스트 sleep 후 갱신 누락으로 보인다(기존 관찰과 같은 양상, 원인 검증은 안 함). 재시작 후 유효 2026-11-03T11:37Z. run은 재시작 뒤에만 돌렸고 preflight도 통과했다
- **실행 스크립트 중단(해결)**: 내 스크립트가 `set -e`로 돌아, CV가 있으면 exit 1인 `verdict.py`에서 `p44-F3-f-1` 판정 뒤 멈췄다. 끝난 run 3개는 다시 돌리지 않고 판정만 이어서 재개했다. run 결과에는 영향 없음
- **세션 독립성**: 이 두 변형·세 run에서 깨지지 않았다. 세션을 맡는 VU가 전체 재생과 달라졌는데도 판정이 같다. 변형 2개로 일반화하지 않는다
- **결정론 확인이지 새 표본이 아니다**: 3 run은 같은 corpus 재실행이다
- **스코핑 도구는 impact-v1.1**: F3·F9의 impact는 v1.0과 같아 D-4.2a 영향이 없다
- **`~/.claude/stop-hook-git-check.sh`**: 지시로 제거하려 했으나 `~/.claude/settings.json`(theme만), 프로젝트 설정, 플러그인 어디에도 이 훅이 없고 스크립트 파일도 없다. 변경 없음
