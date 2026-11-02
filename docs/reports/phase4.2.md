# Phase 4.2 보고서 — 영향 산출 + 변형 사전 등록

- 작업일: 2026-11-02
- 범위: D-4.1a·b·c 반영, `docs/scope-expectations.json` 사전 등록, `scoping/impact.py`·`check_scope.py`, 13 변형 + 보조 4건 실행. 클러스터 접근 없음, run 없음
- 결과: **FAIL(부분) — 멈춤**. 13 변형 중 **11 일치, 2 불일치(v1.2·F2)**, 보조 4/4 일치. 기준대로 도구·기대를 고치지 않았다. **결정 필요 1건**

## 0. 결정 필요 사항

**D-4.2a `Order` 폐포가 프레임워크 상위 타입 `JpaRepository`를 타고 Coupon으로 번진다 (findings O18)**

| 변형 | 사전 등록 | 결과 |
|---|---|---|
| v1.2 (Order, OrderItem, OrderRepository) | order.* 32요청, 9세션·37요청, 22.9% | **48요청, 11세션·48요청, 0%**, 전역 아님 |
| F2 (Order) | 같음 | **같음** |

경로(전문 `logs/phase4.2-scope-check.txt`):

```
Order <- OrderRepository <- CouponRepository <- CouponService
          └ 둘 다 JpaRepository를 상속 — "상위 타입 이름을 참조하는 클래스"
```

D24의 "그 클래스의 상위 타입·인터페이스 이름"을 경로 중간 노드에도 적용한 결과다. `OrderRepository`와 `CouponRepository`는 프레임워크 타입을 공유할 뿐 서로 관계가 없다. 전역이 아니라 **폐포 합집합이 Coupon 클래스를 포함해** 11세션이 된 것이므로 `globalTriggered`는 false다.

**원인은 내 쪽에 있다.** 기대를 손으로 도출할 때 상위 타입 간선을 빠뜨렸고, 탐색을 관측 클래스 너머로 계속하기로 한 것은 내 해석이다(구현 시 확정 (4.2)). 탐색을 계속하지 않았다면 이 경로는 생기지 않는다. 4.1 보고서의 "D-4.1c (A)면 9세션 유지"도 이 간선을 몰랐던 예측이라 이번 결과로 틀렸음이 확인됐다.

선택지별 결과(저장소 코드를 바꾸지 않은 일회성 계산, `logs/phase4.2-whatif.txt`):

| 선택지 | v1.2·F2 | E5 | 사전 등록 일치 | 약해지는 것 |
|---|---|---|---|---|
| **(A) 권장** 상위 타입은 **프로젝트 소스에 선언된 타입만** 확장 | 9세션·37요청 | 9세션 | **13/13** | 외부 타입으로 주입받는 참조자(`Filter`·`Clock` 등)를 못 본다. 단 다른 참조자가 없으면 전역으로 흡수된다 |
| (B) 상위 타입 확장은 **변경 클래스에서만**(폐포 중간 노드 제외) | 9세션·37요청 | 9세션 | 13/13 | 미관측 중간 노드의 다형 참조를 못 본다 |
| (C) **관측 클래스에서 탐색 정지** | 9세션·37요청 | 9세션 | 세션 수 13/13, `reachedClasses` 불일치 5건 → 기대 재등록 필요 | 계획 3절 "첫 도달에서 멈추지 않는다"와 어긋날 수 있다 |
| (D) 그대로 둠 | 11세션·48요청·0% | 11세션 | 11/13 → 기대를 결과에 맞춰 재등록 | Filter 이득. F2는 Order 변경인데 Coupon 전용 세션까지 재생 |

(A) 권장 이유: 상위 타입 확장의 목적은 그 타입으로 다루는 코드를 찾는 것이고, 프로젝트가 선언한 타입이어야 그 근거가 소스에 있다. `JpaRepository` 공유는 관계의 증거가 아니다.

(A)~(C)는 전부 **결과를 본 뒤의 도구 변경**이다. 어느 쪽이든 계획 2절대로 버전·사유·전후 결과·"사전 등록 아님"을 명시한다. 기대(`scope-expectations.json`)는 (A)·(B)에서 그대로 둔다. (D)와 (C)는 기대를 바꾸게 되므로 같은 표시가 필요하다. Recall에는 어느 쪽도 영향이 없을 것으로 본다 — 불일치는 과포함 방향이고, target 세션 포함은 전 변형 n/n이다(4절). (A)·(B)·(C)의 Recall은 4.3에서 측정한다.

## 1. 끝난 기준별 결과

| 기준 | 결과 | 근거 |
|---|---|---|
| 사전 등록을 impact 실행 전에 커밋 | PASS | 등록 `534bbaf` → 도구 `0e8020b` → 첫 실행 순서. `impact.py`는 등록 시점에 골격(exit 2) |
| 13 변형 impact.json 커밋 | PASS | `scoping/impacts/{v1.1~v1.4,F1~F9}.json`, 보조 `scoping/impacts/aux/` 4건. v1.2·F2는 불일치 결과 그대로 |
| 사전 등록과 일치 여부 표 | **FAIL(부분)** | 일치 **11/13**, 불일치 v1.2·F2(0절). 보조 4/4 일치. 4절 표 |
| 미관측 클래스 폐포 경로 전부 기록 | PASS | `unobserved[].closurePaths`(합집합), `reachedClasses`, `unresolvedClasses`. `logs/phase4.2-scope-check.txt` |
| 결정론 | PASS | `check_scope.py` 재실행 sha 동일, CLI 단독 실행(F3)과 일괄 실행 결과 동일 |
| 입력·회귀 | PASS | `check_inputs.py` 64/64, pytest scoping 66·engine 37 passed |

**D-4.1 지시 이행**

| 결정 | 이행 | 위치 |
|---|---|---|
| D-4.1a (A) | order.pay 영향 = 첫 결제 7건. F3·F7 impact에서 R000008 제외, 7세션·30요청 일치 | `scope-expectations.json` `first_pay`, findings O15 한계·결정 추가 |
| D-4.1b (A) | C2 ablation(b) 6세션·Recall 1.0·영향 요청 24 → 16, Tag 순위 품질 보조 등록. 새 지표 없음 | `scope-expectations.json` C2, plan 구현 시 확정 (4.2) |
| D-4.1c (A) | 언어 이름 해석 구현(단일 타입 import·같은 파일 선언은 제외, 와일드카드·별칭은 참조). D24 보완 2 | `impact.py`, `decision-log.md`, 테스트 5건 |
| D-4.1c 원래 문구 결과 | 아래 표 | `--name-resolution literal` |

**원래 문구의 결과 — 텍스트 폐포 오탐 사례**

| 사례 | 원래 문구 | 사유 | 이름 해석 적용 후 |
|---|---|---|---|
| v1.2 | 전역 11세션·0% | `Order` ← `RequestLogFilter`(Spring `@Order`) ← 참조자 없음 → 미해결 | 전역 해소, 그러나 D-4.2a로 11세션 |
| F2 | 전역 11세션·0% | 같음 | 같음 |
| E5 (OrderItem만, 정본 등록은 4.6) | 전역 11세션·0% | `OrderItem` ← `Order` ← `RequestLogFilter` | 같음 |

세 건 모두 등록과 일치. 같은 부류의 오탐이 두 층에 있다. 이름 충돌(O17)을 고치자 상위 타입 공유(O18)가 드러났다.

## 2. 변경 파일·커밋

| 커밋 | 내용 |
|---|---|
| `534bbaf` phase4.2: 영향 기대 사전 등록, D-4.1a·b·c 반영 | `docs/scope-expectations.json`, `docs/decision-log.md`(D24 보완 2), `docs/findings.md`(O15), `docs/phase4-plan.md`(구현 시 확정 (4.2)) |
| `0e8020b` phase4.2: impact.py·check_scope.py | `scoping/{impact,check_scope}.py`, `scoping/tests/{test_impact,test_common}.py` |
| (이 커밋) phase4.2: 결과·보고서 | `scoping/impacts/`, 이 문서, `docs/reports/logs/phase4.2-*.txt`, `docs/findings.md`(O18), `CLAUDE.md` |

## 3. 실행 명령·주요 출력

```
.venv/bin/python scoping/check_scope.py --explain   → 불일치 2건, exit 1
.venv/bin/python scoping/impact.py --base phase3.5-v1.4 --head fault/F3 --out … --explain   → 일괄 결과와 동일
.venv/bin/python -m pytest scoping/tests            → 66 passed
.venv/bin/python -m pytest engine/tests             → 37 passed
.venv/bin/python scoping/check_inputs.py            → 점검 64건, FAIL 0
```

전문: `docs/reports/logs/phase4.2-{scope-check,whatif,pytest}.txt`

## 4. 변형별 결과

Legacy/New 비교는 해당 없음(run 없음).

| 변형 | 범위 | 변경 / 관측 / 미관측 | 전역 | 영향 요청 | 세션 | 재생 | 감소(요청) | target 세션 포함 | 사전 등록 |
|---|---|---|---|---|---|---|---|---|---|
| v1.1 | `phase3.3-base..fd839d6` | 1 / 1 / 0 | 전역(pom) | 48 | 11 | 48 | 0% | - | 일치 |
| v1.2 | `fd839d6..fc6e6e2` | 3 / 1 / 2 | - | 48 | 11 | 48 | 0% | - | **불일치** |
| v1.3 | `fc6e6e2..c64618f` | 3 / 2 / 1 | - | 32 | 9 | 37 | 22.9% | - | 일치 |
| v1.4 | `c64618f..120b212` | 7 / 2 / 5 | 전역(미해결 4) | 48 | 11 | 48 | 0% | - | 일치 |
| F1 | `phase3.5-v1.4..fault/F1` | 1 / 1 / 0 | - | 32 | 9 | 37 | 22.9% | 1/1 | 일치 |
| F2 | `…fault/F2` | 1 / 0 / 1 | - | 48 | 11 | 48 | 0% | 27/27 | **불일치** |
| F3 | `…fault/F3` | 1 / 1 / 0 | - | 7 | 7 | 30 | 37.5% | 7/7 | 일치 |
| F4 | `…fault/F4` | 1 / 1 / 0 | - | 32 | 9 | 37 | 22.9% | 2/2 | 일치 |
| F5 | `…fault/F5` | 2 / 2 / 0 | - | 32 | 9 | 37 | 22.9% | 13/13 | 일치 |
| F6 | `…fault/F6` | 1 / 0 / 1 | - | 32 | 9 | 37 | 22.9% | 26/26 | 일치 |
| F7 | `…fault/F7` | 1 / 1 / 0 | - | 7 | 7 | 30 | 37.5% | 2/2 | 일치 |
| F8 | `…fault/F8` | 2 / 2 / 0 | - | 32 | 9 | 37 | 22.9% | 10/10 | 일치 |
| F9 | `…fault/F9` | 1 / 1 / 0 | - | 32 | 9 | 37 | 22.9% | 4/4 | 일치 |
| C1·C2 | `phase3.3-base..change/C<n>` | 등록만 — 4.5에서 실행 | | | | | | | 대기 |

"target 세션 포함"은 `fault-expectations.json` target 요청 중 선택 세션에 든 수다(요청 기준). Recall 측정이 아니며 Recall은 4.3이다. 보조: `v1.1-ignore-build` 7세션·30요청 일치.

## 5. 지시와 다르게 구현한 것

- **`check_scope.py` 추가**(계획 밖) — 변형 일괄 실행·대조를 재현 가능하게. 불일치는 출력만 하고 exit 1
- **`impact.py` 옵션 추가**: `--path-filter`, `--name-resolution literal`, `--assume-changed`(E5 재현용). 출력에 `baseCommit`·`headCommit`·`pathFilter`·`nameResolution`·`ignoreKind`·`assumedChanged`·`warnings`, `unobserved[].unresolvedClasses`
- **폐포 탐색 해석**: 관측 클래스를 지나서도 계속 — 계획 "첫 도달에서 멈추지 않는다"의 내 해석이고 0절 불일치의 조건 중 하나다
- **같은 파일의 같은 이름 선언**: 지시의 "중첩 타입"을 최상위 선언까지 넓혔다. `poc.coupon.ClockConfig`가 `poc.order.ClockConfig`를 참조로 잡지 않게 하려는 것으로, 같은 이름 해석 규칙의 경우다
- **v1.4 미해결**: 계획 표는 3개, 등록·결과는 `CachedBodyRequest`를 더한 4개(→ `RequestLogFilter` → 참조 없음). 전역 결론은 같다

## 6. 문제·해결·남은 한계

- **v1.2·F2 불일치**: 미해결, 0절. findings O18
- **`impact.py` 버그(실제 변형 실행 전 해결)**: 상위 타입을 선언한 파일 자신이 참조자로 잡혔다. 합성 테스트로 발견, 자기 선언 제외
- **4.1 보고서 정정**: D-4.1c "(A)면 계획 표 9세션 유지"는 틀렸다. 이름 해석만으로는 9세션이 되지 않는다
- **결과를 본 뒤 선택지를 계산했다**: `logs/phase4.2-whatif.txt`는 결정 자료이며 어느 선택이든 "사전 등록 아님"이다
- **타입 모호 검사는 이 코드베이스에서 발동하지 않았다**: 구현체 다수 인터페이스·리플렉션 사례가 없어 합성 테스트로만 확인했다
- **C1·C2**: 브랜치가 없어 등록만 했다. `services/`만 바뀌는지는 4.5에서 확인
