# Prince Mart 일반화 검증 결과

팀원 파이프라인(Istio 미러링 -> `services/evidence-collector` -> Evidence Store -> `engine/`)을 처음 보는 오픈소스 MSA인
Prince Mart(order, coupon, payment)에 적용해, 팀원 Phase 3과 같은 절차(A/A 게이트 -> 결함 New 버전 -> 사전 등록 기대와 대조)로 측정했다.
과정에서 생긴 일과 바꾼 것은 [GENERALIZATION.md](GENERALIZATION.md), 앱 변경은 [app/LEGACY_CHANGES.md](app/LEGACY_CHANGES.md)에 있다.
측정일 2026-11-21. 기준 커밋 `f4750e8`(사전 등록), 결함 브랜치 `fault/PF1`~`fault/PF10`(각 1커밋, 서비스 코드만).

## 0. 요약

결론: 정답 대비 불일치 20/102(전부 결함이 아닌 변경 PF7, PF9, PF10), 오판정률 0/153, target 밖 오탐 0/2034. 진짜 결함 4/4와 성능 결함 1/1을 잡았다.

이 문서는 판정 오류를 세 지표로 나눠 쓴다. 오판정률과 정답 대비 불일치를 섞지 않는다.

| 지표 | 무엇을 세나 |
|---|---|
| 정답 대비 불일치 | target pair 중 엔진이 정답과 다른 확정 판정(SAME, IMPROVEMENT, CONTRACT_VIOLATION)을 낸 수 / target pair 수. 검토(UNCERTAIN)와 비교 불성립(MISALIGNED)은 따로 센다 |
| 오판정률 | 진짜 결함 target 판정(3회, 변형 규칙 포함) 중 규칙 때문에 SAME이나 IMPROVEMENT로 바뀐 수. 팀원 phase3-metrics 3절의 오판정률과 같은 이름, 같은 정의다 |
| target 밖 오탐 | target 밖 pair 판정(10 PF x 3회, 기본 규칙) 중 SAME이 아닌 수. 팀원의 "정상 경로 오탐"과 같다 |

| 항목 | 결과 |
|---|---|
| A/A 게이트(VU 1 x3) | 3회 모두 80/80 SAME, dbstate 같음, run 사이 판정 축 차이 0 |
| 결함 탐지(진짜 결함 PF1~PF4) | 4/4. target 47 pair 전부 CV(3회 같음) |
| 성능 결함(PF8) | 기본 계약 검토(UNCERTAIN) 2/2, max_selects 선언 시 CV 2/2 |
| 정답 대비 불일치(기본 규칙, 10 PF) | 20 / 102 (일치 72, 검토 7, 비교 불성립 3, 불일치 + 비교 불성립 23) |
| 정답 대비 불일치(변형 규칙: PF5 learn, PF7 사전 승인, PF8 max_selects) | 19 / 102 (일치 79, 검토 1, 비교 불성립 3, 불일치 + 비교 불성립 22) |
| target 밖 오탐 | 0 / 2034 |
| 오판정률 | 0 / 153 |
| 사전 등록한 예상 엔진 판정과의 일치 | 77 / 102 (PF6 25건이 예측 오류) |
| eval 세션 검토(UNCERTAIN) learn 전 -> 후 | 4 -> 1 |
| 세 run 판정 동일 | 10/10 PF, 모든 변형 |

각주: 검토(UNCERTAIN)를 정답 대비 불일치에 넣으면 기본 규칙 27/102, 변형 규칙 20/102다.
정답 대비 불일치는 모두 결함이 아닌 변경(승인된 개선 PF7, PF9, PF10)에서 나왔다. 원인은 6절.

## 1. 구성

| 구성 | 값 |
|---|---|
| 클러스터 | kind `musinsa-phase1`(팀원 kind-config), Istio 1.31.1, 노드 15.6GiB |
| 스택 | `pm-legacy`, `pm-new`(서비스별 MySQL 3, Kafka, WireMock 매핑 11), 미러 `/orders`, `/coupons`, `/payments` |
| corpus | `pm-corpus-v2`(corpus v1.1 변환, 세션 14, 요청 38, Legacy 버그 B1~B6 경로), capture로 서버 id 치환 |
| 재생 | 팀원 `k6/run.sh` + `tools/pm.env`, VU 1(business key가 없어 순차 재생만 결정적) |
| 판정 | 팀원 `engine/verdict.py`(engine-v1.3), Prince Mart 규칙 `tools/rules/`(팀원 전용 세션 검사 2개와 `publish_after_commit_begin` 끔) |
| 사전 등록 | `tools/faults/fault-expectations.json`: 정답(`targets`)과 예상 엔진 판정(`expectedEngine`)을 나눠 run 전 커밋 |
| 집계 | `tools/fault_metrics.py`(일치, 불일치, 검토, 비교 불성립), 팀원 `engine/fault_check.py --expectations`로 교차 확인(같은 결과) |

## 2. A/A 게이트

| run | pair | 판정 | dbstate | Undelivered | verify_sameness |
|---|---|---|---|---|---|
| p4-aa-1 | 80 | SAME 80 | 같음 | 0 | PASS |
| p4-aa-2 | 80 | SAME 80 | 같음 | 0 | PASS |
| p4-aa-3 | 80 | SAME 80 | 같음 | 0 | PASS |

Compose(branch-park `aa-004-1`)와 k8s의 Legacy 최종 DB 7테이블이 모든 컬럼 값까지 같다. payment 감사 로그 21건도 문자열까지 같다.

## 3. 결함별 판정과 정답 대조

3회 모두 같은 판정이라 한 번의 수치다. "불일치" 열은 정답 대비 불일치이다(0절 정의). targets 밖 pair는 정답 SAME이고, 10 PF 모두 SAME이었다(target 밖 오탐 0/2034).

| PF | 종류 | 규칙 | target | 일치 | 불일치 | 검토 | 비교 불성립 | 불일치+비교 불성립 | 예상 엔진 판정과 같음 | dbstate(기대) | 한쪽에만 있는 홉(등록과 같음) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| PF1 | 진짜 결함 | 기본 | 15 | 15 | 0 | 0 | 0 | 0 | 15/15 | 같음(같음) | 0 |
| PF2 | 진짜 결함 | 기본 | 12 | 12 | 0 | 0 | 0 | 0 | 12/12 | 다름(다름) | legacy 5(예) |
| PF3 | 진짜 결함 | 기본 | 16 | 16 | 0 | 0 | 0 | 0 | 16/16 | 같음(같음) | 0 |
| PF4 | 진짜 결함 | 기본 | 4 | 4 | 0 | 0 | 0 | 0 | 4/4 | 같음(같음) | 0 |
| PF5 | 정상 리팩터링 | 기본 | 5 | 0 | 0 | 5 | 0 | 0 | 5/5 | 같음(같음) | 0 |
| PF5 | | learn(R24, R27 라벨) | 5 | 4 | 0 | 1 | 0 | 0 | 5/5 | | |
| PF6 | 정상 변경(Jackson 2 -> 3) | 기본 | 25 | 25 | 0 | 0 | 0 | 0 | **0/25** | 같음(같음) | 0 |
| PF7 | 승인된 개선(B4) | 기본 | 6 | 0 | 6 | 0 | 0 | 6 | 6/6 | 다름(다름) | 0 |
| PF7 | | 사전 승인 규칙 | 6 | 1 | 5 | 0 | 0 | 5 | 6/6 | | |
| PF8 | 성능 결함(N+1) | 기본 | 2 | 0 | 0 | 2 | 0 | 0 | 2/2 | 같음(같음) | 0 |
| PF8 | | max_selects 선언 | 2 | 2 | 0 | 0 | 0 | 0 | 2/2 | | |
| PF9 | 승인된 개선(멱등) | 기본 | 5 | 0 | 5 | 0 | 0 | 5 | 5/5 | 다름(다름) | 0 |
| PF10 | 승인된 개선(B1) | 기본 | 12 | 0 | 9 | 0 | 3 | 12 | 12/12 | 다름(다름) | legacy 15, new 11(예) |

| 합계 | target | 일치 | 불일치 | 검토 | 비교 불성립 | 불일치+비교 불성립 |
|---|---|---|---|---|---|---|
| 기본 규칙 | 102 | 72 | 20 | 7 | 3 | 23 |
| 변형 규칙(PF5 learn, PF7 사전 승인, PF8 max_selects) | 102 | 79 | 19 | 1 | 3 | 22 |

각주: 검토를 정답 대비 불일치에 넣으면 기본 27/102(= 20 + 7), 변형 20/102(= 19 + 1).

## 4. 팀원 Phase 3(F1~F9)과 나란히

팀원은 기대를 엔진 판정 기준으로 등록했고, 이 검증은 정답(실제로 무엇인가)과 예상 엔진 판정을 나눠 등록했다. 그래서 두 기준을 모두 적는다.

| 지표 | 팀원 Phase 3 (자체 앱) | Prince Mart (처음 보는 앱) |
|---|---|---|
| 결함 탐지(진짜 결함) | 6/6 (F1 F2 F3 F4 F7 F9) | 4/4 (PF1~PF4) |
| 성능 결함 | 1/1 (F8, 기본 UNC, max_selects 선언 시 CV) | 1/1 (PF8, 같은 양상) |
| 분류(리팩터링, 승인된 개선) | 2/2 (F5 learn 후 IMP, F6 사전 규칙 IMP) | PF5 learn 후 IMP 4/4(404 재취소 1건 검토 남음), PF6 SAME 25/25, PF7 1/6, PF9 0/5, PF10 0/12 |
| target 일치(등록 기준) | 92/92 (+ F8 max_selects 10/10), 엔진 판정 기준 | 정답 기준 72/102(변형 79/102), 예상 엔진 판정 기준 77/102 |
| target 밖 오탐(팀원 이름: 정상 경로 오탐) | 0 | 0 / 2034 |
| 오판정률(진짜 결함 target이 규칙으로 SAME, IMP) | 0 / 129 | 0 / 153 |
| 정답 대비 불일치(target pair 중 정답과 다른 확정 판정) | 측정하지 않음(기대를 엔진 판정 기준으로 등록) | 20 / 102 (변형 19 / 102) |
| eval 검토 learn 전 -> 후 | 31 -> 6 | 4 -> 1 |
| 세 run 동일 | 예 | 예 |

진짜 결함과 성능 결함 탐지는 팀원 결과와 같은 양상으로 재현됐다. 차이는 결함이 아닌 변경에서 난다. 팀원 앱의 승인된 개선(F6)은 응답 필드 추가라 규칙으로 덮을 수 있었다.
Prince Mart의 승인된 개선(PF7, PF9, PF10)은 쓰기 집합, 외부 호출, 트랜잭션, 호출 순서를 바꾸는데, 팀원 엔진은 이 축들을 규칙으로 덮지 않는다(기능 축은 무조건 CV).

## 5. learn 규칙과 검토 감소

| 결함 | learn 라벨(사전 등록) | 규칙 | 결과 |
|---|---|---|---|
| PF5 | R000024/0, R000027/0(S010, S011, learn) improvement | `tools/rules/review/PF5/learned/` 2개(dbRead.countDelta 2 -> 1, callTree findById -> findWithItemsByOrderId) | eval R000015, R000019도 IMP. R000016(404 재취소, fingerprint 교체)은 유형이 달라 검토로 남음(사전 등록대로) |
| PF7, PF9 | 없음 | — | branch-park의 소비 홉 learn 라벨은 팀원 엔진에서 그 pair가 CV(트랜잭션 축)라 대상이 아니다 |

eval 세션 검토는 PF5 3건과 PF8 1건으로 4건이었고, learn과 max_selects 선언 뒤에는 PF5 R000016 1건이 남는다.

## 6. 정답 대비 불일치과 비교 불성립의 원인

| 원인 | PF | pair | 근거 |
|---|---|---|---|
| readOnly 트랜잭션(`SimpleJpaRepository.findById`)도 기록되고, 엔진은 트랜잭션 결과 순서열을 기능 축(CV)으로 비교한다 | PF7 4, PF9 4 | 기능이 같은 소비 홉 8 | `transactions.outcomes: legacy 2단계 new 4단계` |
| 승인된 기능 변화(writeSet, externalCalls, response.status)는 규칙으로 덮을 수 없다 | PF7 R20 소비, PF9 R35 소비, PF10 주문 6과 validate 2 | 10 | `writeSet`, `externalCalls`, `response_body_compatible` |
| 자식 hopPath가 호출 순번이라, 관측 서비스 호출의 순서가 바뀌면 같은 키가 다른 호출을 가리킨다 | PF10(쿠폰 use를 결제 뒤로) | 비교 불성립 3(legacy payment.process와 new coupon.use를 비교), 한쪽에만 있는 홉 26 | legacy `0.h5` use -> new `0.h9` use |
| id 마스킹이 키 이름 `id`에만 적용되고 외부 호출 본문은 hash로 비교한다 | PF10 R000028 | 1 | 감사 로그 `usageId` 1 -> 5(auto increment 밀림) |
| (참고, 실제 판정에는 영향 없음) 규칙이 변경 단위 범위를 갖지 않는다 | PF7 규칙으로 PF2를 판정한 대조 | PF2 진짜 결함 2 pair(R000021, R000025)가 IMP로 가려짐. 전역 규칙이었다면 오판정률 6/153 | 3회 같음. 변경별 규칙 디렉터리로 나눠 실제 판정에서는 막았다(오판정률 0/153) |

## 7. 예상과 달랐던 것

| 항목 | 예상 | 실제 | 원인 |
|---|---|---|---|
| PF6(Jackson 2 -> 3) | 감사 로그 `dataAfter` 키 순서가 알파벳순으로 바뀌어 25 pair CV | 25 pair 모두 SAME(키 순서 그대로) | Payment에 직접 쓴 전 필드 생성자(인자 9개, 필드 선언 순서)가 있고, Boot parent가 `-parameters`로 컴파일해 인자 이름이 클래스에 남는다(`MethodParameters`). Jackson 3는 이 생성자를 암묵 creator로 잡고, `MapperFeature.SORT_CREATOR_PROPERTIES_FIRST`(기본 켜짐)에 따라 creator 속성을 생성자 인자 순서로 먼저 쓴다. 전 필드가 creator 속성이라 알파벳순 정렬(`SORT_PROPERTIES_ALPHABETICALLY`, 기본 켜짐)이 적용될 속성이 남지 않는다. jshell 확인: 기본 `JsonMapper`는 선언 순서, `SORT_CREATOR_PROPERTIES_FIRST`만 끄면 알파벳순(amount, createdAt, currency, ...). PF6 이미지가 `tools.jackson.databind.json.JsonMapper`를 쓰고 Evidence version이 PF6인 것도 확인했다 |

나머지 9 PF는 예상 엔진 판정과 pair 단위로 같았다(77/77). PF6은 정답과는 25/25 일치한다(틀린 것은 예측).

## 8. 재현

```bash
# 기준선 A/A
tracks/prince-mart/tools/run-pm.sh --run-id p4-aa --iterations 3
for i in 1 2 3; do .venv/bin/python engine/verdict.py --run runs/p4-aa-$i --rules tracks/prince-mart/tools/rules; done

# 결함마다(이미지는 fault/PF<n> 브랜치에서 빌드, tools/faults/README.md)
tracks/prince-mart/tools/deploy-new.sh PF1
tracks/prince-mart/tools/run-pm.sh --run-id pf1 --iterations 3
.venv/bin/python engine/verdict.py --run runs/pf1-1 --rules tracks/prince-mart/tools/rules
tracks/prince-mart/tools/deploy-new.sh base

# 대조
.venv/bin/python tracks/prince-mart/tools/fault_metrics.py --json tracks/prince-mart/tools/faults/fault-metrics.json
.venv/bin/python engine/fault_check.py --fault PF1 --run-base pf1 --base p4-aa --expectations tracks/prince-mart/tools/faults/fault-expectations.json
```

변형 판정 명령은 `fault-expectations.json`의 `judge`에 있다. 집계 원자료는 `tools/faults/fault-metrics.json`.

## 9. 한계

- VU 1 순차 재생만 했다. business key가 없어 팀원 A/A 표준(VU 3)은 성립하지 않는다.
- run 때 작업 트리에 커밋 전 변경이 있었다(run-meta `git.dirty: true`, 기준 `f4750e8`). 사전 등록의 기대 값은 바뀌지 않았고(집계 정의와 문구, runCheck 형식만, `_revisions`), 도구 변경은 판정 도구(fault_check, review)와 Prince Mart 집계 스크립트다.
- 결함 코퍼스는 corpus v1.1 그대로라 재고 차감 실패 같은 경로가 없다(PF3은 순서 차이로만 보인다).
- `publish_after_commit_begin`을 꺼서 발행과 커밋의 순서가 바뀌는 변경은 다른 축에 드러나지 않는다.
- PF6은 출력 바이트가 바뀌지 않은 변경이라(7절) 엔진 시험 사례로는 약하다. "정상 변경을 SAME으로 통과시킨다"는 것만 보여 주고, 표현만 바뀌는 변경을 엔진이 어떻게 다루는지는 시험하지 못했다.
