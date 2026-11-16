# Phase 4 결과 — 스코핑: Git Diff → 동적 Call Graph → 영향 API → Tag/Filter

> 완료 2026-11-02, tag `phase4-done`(4.8·4.9는 태그 뒤 추가). 계획 `docs/phase4-plan.md`(v2 + 구현 시 확정), 지표 `docs/phase4-metrics.md`(생성), 단계 보고 `docs/reports/phase4.0~4.7.md`, 스코핑 도구 impact-v1.1, 엔진 engine-v1.3.

## 결론

Phase 3는 "전체를 재생하면 잡는다"였고, Phase 4는 "무엇을 재생할지를 코드 변경에서 고를 수 있는가"를 쟀다.

1. **고를 수 있다.** 행동 차이가 있는 변형 11개(결함 F1~F9, Coupon 변경 C1·C2)에서 전역 없이 세션을 좁혔고 Observed-diff Recall은 전부 1.0이다.
2. **감소폭은 크지 않다.** 재생 요청 감소율은 22.9%(Order 공통, 9세션) / 37.5%(결제 경로, 7세션) / 39.6%(Coupon, 6세션) / 0%(전역). 계획이 미리 적어 둔 값과 같은 묶음이다. 이득은 변경의 지역성 × 트래픽 구성 × 매칭 해상도의 곱이다.
3. **부분 재생은 전체 재생과 같은 판정을 냈다.** 실제 Filter run 4 변형 12 run에서 재생 pair 판정이 전체 재생과 498/498 일치, run 범위 dbstate도 기대와 일치, Undelivered·degraded 0.
4. **서비스 간 간선이 값을 만든다.** 요청 단위 맵 + 홉 합산이 없으면 C2는 39.6% → 0%(엔드포인트 합집합), C1은 37.5% → 0%(전역)다. Order 쪽 13 변형에서는 이 차이가 보이지 않았다.
5. **세션 단위 선택은 필수였다.** F7의 R000042는 변경 클래스를 실행하지 않지만 앞 요청의 상태 때문에 결함이 나타났다. 요청 단위 Filter였다면 놓쳤다.

스코핑의 성과로 세는 값은 전역이 아닌 행의 Recall뿐이다. 전역으로 떨어진 행은 전체 재생이라 자명하고, 지표 문서는 이를 "전역(자명)"으로 구분한다.

## 맵·규칙·모드

| 항목 | 내용 |
|---|---|
| 맵 | Legacy baseline `p36-base-1..3`, 요청 48·엔드포인트 8·클래스 10, 3 run 동일. 정본은 요청 단위, 한 요청의 모든 홉 합산. 빈 11개 중 10개 관측, 미관측 `RequestLogFilter`(AOP 포인트컷 제외) |
| 변경 → 영향 | `git diff -M`, 클래스 단위 매칭. 관측 → 그 클래스가 실행된 요청. 미관측 → 정적 참조 폐포(깊이 ≤3, 관측 클래스를 지나서도 계속, 합집합). 미해결·resource·build·deploy·삭제 → 전역. docs·test·verify만 → 영향 없음(verify면 A/A 경고) |
| 참조 해석 | 언어 이름 해석 규칙(D24 보완 2), 상위 타입은 프로젝트 소스 선언 타입만(D24 보완 3, 결과를 본 뒤 변경) |
| 선택 단위 | 세션(요청 단위 선택 금지) |
| Tag | 전체 재생 + `tags.json`. `inScope` = 세션 입도, `impactedRequest` 병기, 리뷰 순서 3단. 판정·재생 수 불변, 검토량 감소를 주장하지 않는다 |
| Filter | 영향 세션만 재생, 같은 엔진·규칙 |
| 관측된 차이 | verdict != SAME 또는 appliedRules가 있는 pair(D26). 사람 검토 감소는 규칙 적용 후 verdict |

## 지표

전체 표는 `docs/phase4-metrics.md`.

| 묶음 | 변형 | 세션 | 요청 | 감소(요청) | Recall | B2-S 같은 세션 수 조합의 Recall 1.0 비율 |
|---|---|---|---|---|---|---|
| Order 공통 | F1 F2 F4 F5 F6 F8 F9, v1.2 v1.3 | 9/11 | 37/48 | 22.9% | 1.0(v1.x N/A) | 0.018~0.818 |
| 결제 경로 | F3 F7 C1 | 7/11 | 30/48 | 37.5% | 1.0 | F3 0.003, F7 0.636, C1 0.212 |
| Coupon | C2 | 6/11 | 29/48 | 39.6% | 1.0 | 0.002 |
| 전역 | v1.1 v1.4 | 11/11 | 48/48 | 0% | 전역(자명, 분모 0) | - |

- 결함 탐지 유지: target 전부 선택 세션 안(F1~F9, C1, C2). 전체 재생 Recall에 F0를 포함하면 F3 0.875·F7 0.667·C1 0.75·C2 0.9 — 그 변형의 결함이 아니라 S011을 고르지 않았기 때문이다
- B2-S의 뜻: 무작위 선택이 스코핑을 따라오기 어려운 변형(F3·C2)과 무작위로도 대개 맞히는 변형(F1·F4)이 갈린다. 평균보다 1.0 비율을 본다
- 사람 검토: C2 eval Uncertain 3 → 0(라벨 2건). 규칙이 직접 호출과 Order가 부른 `0.h1`에 함께 적용됐다
- 시간: run 전체 약 35초 중 약 30초가 리셋이다. 요청 수 감소가 시간 감소로 그대로 이어지지 않는다

### 참고: Evidence 수집 오버헤드 (4.9)

기대 없음, 판정과 무관한 참고값이다. Legacy Evidence on/off, VU=1 × 3, run당 48요청(`docs/phase4-overhead.json`, `docs/reports/phase4.9.md`).

| 항목(3 run 중앙값) | on | off |
|---|---|---|
| 응답 지연 p50 | 13.96ms | 11.41ms |
| 응답 지연 p95 | 44.64ms | 32.35ms |
| CPU 코어초(재생 1회) order 앱 / coupon 앱 | 0.955 / 0.850 | 0.835 / 0.626 |
| working set MiB order 앱 / coupon 앱 | 414.3 / 368.3 | 403.0 / 421.7 |

Evidence 건당 p50 1,900B, p95 2,976B, 최대 3,014B, run당 약 121KB. 차이를 소음과 분리하지 못했다(O24): 첫 회끼리는 off가 더 느렸고 메모리는 방향이 일정하지 않다. 운영 부하 추정이 아니다.

### 스코핑이 줄이지 못하는 변경 종류 (fail-closed 비용)

| 사례 | 변경 | 전역 사유 |
|---|---|---|
| E1 | `ClockConfig` 한 줄 | 미관측, 참조 없음 |
| E2 | `application.yml` 값 | resource |
| E6 | `PaymentGatewayClient` 삭제 | 클래스 삭제 |
| v1.1 | `PaymentGatewayClient` + pom | build |
| v1.4 | Controller·설정·필터·메인 전환 | 설정·필터·메인 참조 없음 |

설정·빌드·삭제·진입점 변경은 어디에 영향이 있는지 소스로 알 수 없어 전체를 재생한다. 안전한 쪽으로 실패한 비용이고 스코핑의 오류가 아니다. 사다리 4단계 중 2단계가 여기 든다.

### 스코핑 정확도 — 사전 등록 대조

맹검 대조 **19/21** 일치(13 변형 11/13, C1·C2 2/2, 경계 사례 6/6). 맹검은 도구 출력을 보기 전에 손으로 도출해 커밋했다는 뜻이고, 도출자는 도구 규칙을 알고 있었다.

- 불일치 2건: v1.2·F2(impact-v1.0). `JpaRepository` 공유로 폐포가 Coupon까지 번져 11세션(O18). impact-v1.1로 고쳤다 — **결과를 본 뒤 변경, 사전 등록 아님**
- 회귀 확인 3건: v1.2·F2(impact-v1.1), E5(4.2 whatif에서 본 값). 독립 검증이 아니다

## 한계

- **맵은 Legacy가 corpus로 실행한 경로만 안다.** New만 실행하는 경로(F1의 R000008 게이트웨이 재호출)는 보지 못한다. 세션 단위 선택이 이번에는 덮었다(O15)
- **클래스 커버리지는 상태 전파를 못 본다.** 세션 안은 세션 선택이 덮지만(O19), 세션 경계를 넘는 상태 전파는 덮지 못한다
- **참조 폐포는 보수적 휴리스틱이다.** 안전성이 증명된 회귀 테스트 선택이 아니다. 프로젝트 공통 상위 타입의 형제 오탐은 남아 있고(O18, 테스트로 고정), 프레임워크 타입으로 주입받는 참조자의 누락은 그대로 한계다
- **표본이 작다.** 변형 15, 경계 사례 7, 세션 11. Recall 1.0은 이 corpus 안의 값이고 일반화하지 않는다. 같은 corpus 재실행(3 run)은 결정론 확인이지 새 표본이 아니다
- **세션 독립성은 Filter 4 변형에서 깨지지 않았을 뿐이다.** 공유 자원 경합이 있는 경우는 시험하지 않았다
- **감소율은 corpus 구성에 좌우된다.** 11세션·48요청에서의 값이고 트래픽 구성이 다르면 달라진다. Ekstazi 등의 시간 감소율과 같은 지표가 아니다
- **해상도 한계**: 주석만 바꿔도 영향으로 잡힌다(클래스 단위). Precision이 낮은 것은 정상이다(영향 ≠ 차이)
- **규칙은 호출 경로를 구분하지 못한다.** uid에 hop이 없어 경로별 의미가 다른 변경이면 과적용될 수 있다(O22)
- **도구를 결과 보고 고친 적이 1번 있다**(impact-v1.1). 기대 파일은 고치지 않았고 v1.0 결과를 보존했다
- **검증 레이어 변경 뒤 A/A는 마지막 상태(4.8 뒤, rev `36aac52`)에서 한 번 돌렸다.** 4.4·4.8의 k6·run.sh·barrier.py 변경을 모두 포함한 기본 경로로 base 이미지 양쪽, VU=3 × 3, diff ∅·SAME 60 ×3·dirty false(`p48-aa2-1..3`, `docs/reports/phase4.8.md` 6.1). 4.4~4.8 사이의 중간 상태는 A/A로 확인하지 않았고, `--mirror`·`--impact`·`--tag` 분기는 A/A가 덮지 않는다
- **`dbstate`는 집계 해시다.** 행 값을 직접 읽지 못한다

### 판정 엔진·규칙의 한계 (Phase 4 완료 뒤 추가 검증, 2026-11-13)

Phase 4 결과를 낸 뒤 더한 검증이다. Phase 3·4 실험 당시에 한 검증이 아니며, 기존 수치·판정 파일·엔진(engine-v1.3)·규칙은 바꾸지 않았다. 근거는 코드(`engine/verdict.py`·`ruleset.py`·`fault_check.py`·`metrics.py`), `engine/rules/`, `docs/phase3-metrics.json`과 신규 단위 테스트 `engine/tests/test_rule_scope.py`다. 신규 테스트는 클러스터 run이 아니라 fixture `p33-mini` 사본을 고친 **합성 Evidence**를 실제 `judge_run()`·`RuleSet`(engine/rules 전체 사본)으로 판정한다. 합성 레코드는 입력 계약(스키마·seq 불변식)을 통과하고, 변조한 pair 외 24 pair는 모두 SAME·sessionViolations 없음·dbstate ok로 확인했다.

| 테스트 | 합성 (New만, (c)(e)는 양쪽 기반 변경 포함) | 실제 판정 | appliedRules | violations | uncertain |
|---|---|---|---|---|---|
| (a-1) | order.get R000002: SELECT 2 → JOIN 1, Repository 메서드 교체 | IMPROVEMENT | F5 countDelta·callTree | 없음 | 없음 |
| (a-2) | order.get R000038(404): SELECT 1 → JOIN 1 | IMPROVEMENT | F5 fingerprintReplaced·callTree | 없음 | 없음 |
| (b) | (a-1) + `amount` 10000 → 1 | CONTRACT_VIOLATION | F5 2건 유지 | `response_body_compatible: response.valueChanged amount` | 없음 |
| (c) | 양쪽 외부 호출 1건(wiremock) + New만 2건, (a-1) | CONTRACT_VIOLATION | F5 2건 유지 | `externalCalls: legacy=[1건] new=[2건]` | `externalCalls.responseHashChanged`(규칙 없음, 판정은 CV 우선) |
| (d) | (a-1) + 응답 필드 `note` 추가 | UNCERTAIN | F5 2건 유지 | 없음 | `response.addedFields [note]` |
| (e) | 양쪽 items 2개, New만 `itemCount: 0` | **IMPROVEMENT** (한계) | `order-view-item-count` | 없음 | 없음 |
| (f) | coupon.get R000039, New만 `itemCount: 0` | **IMPROVEMENT** (한계) | `order-view-item-count` | 없음 | 없음 |

`countDelta`와 `fingerprintReplaced`는 한 pair에서 함께 나오지 않는다(`execution_items`: SELECT 수가 다르면 countDelta, 같을 때만 fingerprintReplaced). 그래서 F5 규칙 3개를 한 pair에 동시에 적용하는 테스트는 없다. (c)의 대조로 양쪽에 같은 호출 1건만 더하면 25/25 SAME임도 확인했다.

- **① 판정 우선순위.** `verdict.py`는 CONTRACT_VIOLATION > UNCERTAIN > IMPROVEMENT > SAME 순서다. pair에 violations가 하나라도 있으면 appliedRules와 무관하게 CV다. 위반은 두 경로로 생긴다.
  - **직접 계약 검사**: status, content-type, writeSet, externalCalls, events·event, tx outcome 순서, error, consumeOutcome, hop 집합, 커밋 전 발행, max_selects, 세션 검사. 이 검사는 규칙 적용 전에 확정되고, 규칙으로 해제할 수 없다.
  - **응답·이벤트 본문**: 규칙이 설명하지 못한 `response.removedFields`·`response.valueChanged`는 `response_body_compatible` 위반이 된다. `events.payloadFieldsRemoved`·`payloadValueChanged`는 `events_equal` 위반이 된다.
  - **정확한 경계**: `response.removedFields`·`valueChanged`는 규칙이 덮을 수 있는 diffKind다(`RULE_COVERABLE`·`DIFF_KINDS`). 이 유형의 승인 규칙이 있으면 위반이 아니라 규칙 판정을 따른다. 현재 규칙 세트에는 그런 규칙이 없다.
  - **실제 동작 확인**: (b)~(d)에서 승인된 F5 규칙이 appliedRules에 남은 채 다른 위반이나 미승인 차이를 덮지 못했다.
  - **보장 범위**: 이 보장은 구현된 검사와 관측된 Evidence에 한정된다. 모든 의미적 결함을 탐지한다는 뜻이 아니다(③④).
- **② 오판정 0/129의 정확한 의미.** `phase3-metrics.json` `misjudgment`의 값은 `realTargetPairs` 43, `realTargetPairRuns` 129, `hidden` [], `rate` 0.0이다.
  - **분모**: 진짜 결함 F1·F2·F3·F4·F7·F9(`metrics.py` `REAL`)의 target pair 43개 × 3 run이다.
  - **분자**: 같은 run을 규칙 없이 판정한 결과(`C_norules`)와 규칙을 넣은 결과(`C_rules`)를 비교한다. 규칙 때문에 SAME·IMPROVEMENT로 바뀐 판정의 수이고, 0건이었다.
  - **당시 규칙**: Phase 3 시점의 4개(learned F5 3 + 사전 승인 1)다. C2 same 규칙 2개(4.5)는 이 계산에 들어가지 않았다.
  - **적용 범위**: 기존 결함 카탈로그 안의 관측값이다. 미관측 결함이나 새 유형에 대한 일반적인 오판정률 0%가 아니다. 반례 (e)(f)가 있다.
- **③ 정규화·축약에 따른 탐지 한계.** 정규화·축약 과정에서 제거된 정보는 해당 비교 축에서 직접 검출할 수 없다. 일부 차이는 응답, 외부 호출, 최종 DB 상태 등 다른 Evidence로 발견할 수 있다. 그러나 다른 관측 축에도 드러나지 않고 최종 상태에 남지 않는 중간 실행 차이는 탐지하지 못할 수 있다. 따라서 차등 비교만으로 모든 실행 행동의 동등성을 보장할 수는 없다. 코드에서 확인한 축약은 다음과 같다(`normalize.py`).
  - writeSet은 쓰기 SQL의 (종류, 테이블)뿐이라 쓰기 값의 차이를 그 축에서 직접 검출할 수 없다. 최종 상태 해시(`dbstate_equal`, run 범위)가 달라지면 발견할 수 있지만, 같은 행을 썼다가 되돌리는 중간 차이는 남지 않는다.
  - SQL은 원문의 fingerprint(소문자·공백·alias 정리, 바인딩 자리 `?`)만 비교한다. 바인딩 값은 Evidence에 없다.
  - callTree는 class.method 시퀀스뿐이다(인자 없음, 합성 메서드 제외).
  - 응답·payload의 `id` 키 값은 `<id>`로 가린다.
  - 외부 호출 응답 본문은 hash로만 비교하며 실행 특성 축이다.
- **④ 추가 필드 규칙의 의미 검증 한계.** `order-view-item-count`는 `response.addedFields`의 필드 이름 집합만 본다(`Rule.matches`: `set(fields) <= {itemCount}`). 추가된 값이 맞는지는 검증하지 않는다.
  - **반례**: (e)에서 `items` 2개에 `itemCount: 0`을 넣어도 IMPROVEMENT로 승인됐다.
  - **원인 구분**: 정규화로 인한 누락(③)과 구분되는, 규칙 승인 조건의 한계다.
  - **확인 범위**: 실제 클러스터 run이 아니라 이번 합성 Evidence 단위 테스트로만 확인했다.
  - **다음 연구**: `itemCount == items.size()` 같은 의미 검증 계약의 도입이다. 도입하면 (e)의 기대 판정은 의도적으로 바뀌어야 한다.
- **⑤ endpoint `"*"` 규칙의 적용 범위.** OrderView는 주문 생성·조회·결제의 성공 응답에 공통으로 쓰이므로, 와일드카드는 의도한 선택일 수 있다. 와일드카드 자체를 확정된 결함으로 보지 않는다.
  - **매처 동작**: 매처는 endpoint id(`*`면 전부)와 diffKind·필드만 보고 응답 타입은 구분하지 않는다.
  - **확인 결과**: (f)에서 OrderView가 아닌 `coupon.get` 응답에 `itemCount`만 추가해도 이 규칙이 적용되어 IMPROVEMENT였다.
  - **한계**: 의도한 OrderView 응답 범위를 넘어 추가 필드를 승인할 수 있다. 현재 규칙의 적용 범위 한계다.
- **⑥ events 축의 계약 경계.** 현재 `contract.yaml`에서 `events_equal`이 켜진 상태 기준이다(`verdict.py` `events_compare`·규칙 적용부). 꺼지면 아래 검사와 payload 항목 생성이 모두 빠진다.
  - **직접 계약 위반**: 발행 이벤트의 개수·topic·key·ack 불일치, New의 ack ≠ ok, 소비 이벤트(`event`)가 한쪽에만 있거나 topic·key가 다른 경우다. 규칙으로 해제할 수 없다.
  - **payload 기존 필드의 삭제·값 변경**: `events_equal` 위반이다. 이 두 diffKind는 `RULE_COVERABLE`에 없고 규칙 로더도 거부하므로, 규칙으로 승인할 수 없다.
  - **payload 필드 추가**: `events.payloadFieldsAdded`는 규칙 적용이 가능하다. 설명하는 규칙이 없으면 UNCERTAIN이다. 현재 규칙 세트에는 이 유형의 규칙이 없다.
  - **신규 테스트 범위 밖**: events 축은 이번 신규 테스트에 들어가지 않았다. 위 경계는 코드 확인이고, 단위 테스트로 확인된 것은 기존 `test_ack_failed_is_cv`(ack)뿐이다.
- **⑦ 최종 통과 조건과 종료 코드.**
  - **`verdict.py`**: 판정을 끝까지 수행한 경우 종료 코드는 둘 중 하나다.
    - 1: CONTRACT_VIOLATION pair가 1건 이상이거나, runChecks 중 `ok`가 명시적 `false`인 것이 있을 때. `dbstate` 파일이 없어 `ok: null`이면 실패가 아니다.
    - 0: 그 외 전부. Undelivered·degraded·bothStacks 세션 플래그·UNCERTAIN만으로는 실패하지 않는다.
  - **`fault_check.py`**: 3 run 각각에서 아래 중 하나라도 해당하면 1이다.
    - target 판정이 기대와 불일치
    - 정상 경로 오탐(baseline과 다른 non-target pair)
    - 등록된 runCheck 기대 불일치(`--expect-key targets`일 때만 검사)
    - degraded 또는 Undelivered가 1건 이상
    - 세 run의 판정 서명이 서로 다름
  - **pair 집합 차이**: baseline에만 또는 F run에만 있는 pair는 출력만 하고, 그 자체로는 실패로 치지 않는다.
  - **유실률 임계치 없음**: run 유실률에 대한 별도의 허용 임계치는 정의돼 있지 않다. fault_check은 Undelivered 1건도 실패로 본다.
  - **입력·실행 오류와 구분**: 인자 오류는 argparse 종료 코드 2다. 그러나 입력 계약 위반(`ValueError`)이나 파일 없음 같은 예외는 잡지 않아 Python 기본 종료 코드 1로 끝난다. 이것은 검사 실패의 1과 같은 값이다. 둘은 출력으로 구분한다(traceback이냐, 판정 표·"기대와 다름"이냐).
- **⑧ 규칙 세트 전체.** `RuleSet(engine/rules)`가 실제로 로드하는 규칙은 6개다(신규 `test_all_rules_loaded`로 확인, 사본이 원본과 바이트 동일).

  | id | 종류 | verdict | endpoint | diffKind |
  |---|---|---|---|---|
  | `order-view-item-count` | 사전 승인 | improvement | `*` | response.addedFields [itemCount] |
  | `learned-5da05fdb147f` | learned F5 | improvement | order.get | dbRead.countDelta 2 → 1 |
  | `learned-989c110b103e` | learned F5 | improvement | order.get | callTree.sequenceReplaced findByOrderKey → findWithItemsByOrderKey |
  | `learned-9a82df6b99b4` | learned F5 | improvement | order.get | dbRead.fingerprintReplaced orders → orders join order_items |
  | `learned-aa06c259e967` | learned C2 | same | coupon.use | dbRead.countDelta 1 → 2 |
  | `learned-cfb6811c9f5c` | learned C2 | same | coupon.use | callTree.sequenceReplaced (+ existsByCouponKey) |

  모든 규칙의 scope는 request다. 매칭은 첫 번째로 맞는 규칙 하나(사전 승인 → learned 순)이고, 실행 특성 축·response.body·events.payloadFieldsAdded·외부 응답 hash의 diff에만 적용된다. 신규 테스트가 실제 적용을 확인한 규칙은 4개(사전 승인 1 + F5 3)다. C2 규칙 2개는 이번에 로딩만 확인했고, 적용은 4.5 실제 run(`p45-C2`)의 판정에서 관측한 것이다. 6개 규칙 각각의 모든 조합이나 경계 값을 단위 테스트로 덮었다고 주장하지 않는다.

테스트 실행(2026-11-13): `pytest engine/tests` **49 passed**(신규 10 포함, 실패 0, 스킵 0 — `runs/p33-1..3`이 있어 실제 run 테스트도 실행), `pytest scoping/tests` **88 passed**(실패 0, 스킵 0).

## 결정 (decision-log)

| 번호 | 내용 |
|---|---|
| D23 | 맵은 요청 단위 + 자식 홉 합산, 선택 단위는 세션, 매칭은 클래스 |
| D24 | 미관측 클래스의 참조 폐포는 보수적 휴리스틱, 합집합, 미해결은 전역. 보완 1: 변형 diff 범위(사다리 `services/`만). 보완 2: 언어 이름 해석 규칙. 보완 3: 상위 타입은 프로젝트 선언 타입만(결과를 본 뒤 변경) |
| D25 | 오프라인 부분집합 평가가 주, 실제 Filter run은 동등성 확인 |
| D26 | 기능적으로 동등한 변경은 same 승인, 관측된 차이는 규칙 적용 전 기준 |

## 발견 (findings)

| 번호 | 요지 |
|---|---|
| O14 | 사다리 diff에 배포·엔진 커밋이 섞이고, Java → Kotlin은 rename으로 안 잡힌다 |
| O15 | 같은 엔드포인트 안에서 실행 경로가 갈린다(중복 결제 R000008). Legacy 맵은 New만의 경로를 못 본다 |
| O16 | 세션 단위 선택이 홉 합산의 효과를 가린다 |
| O17 | 단순 이름 토큰이 다른 타입을 참조로 잡는다(`@Order`) |
| O18 | 프레임워크 상위 타입 공유가 무관한 서비스를 잇는다(`JpaRepository`) |
| O19 | 변경 클래스를 실행하지 않은 요청에도 결함이 나타난다(F7 R000042) — 세션 선택의 실측 근거 |
| O20 | 메시 전체 인증서가 한꺼번에 만료된다, 복구 범위가 문서보다 넓다 |
| O21 | 해상도·홉 합산의 효과는 Coupon 변경에서만 나타나고, HTTP 홉 합산은 Tag에서만 보인다 |
| O22 | learn 규칙이 호출 경로를 넘어 재사용된다 |
| O23 | 선택 미러는 Legacy를 그대로 두는 대신 run 범위 상태 비교를 잃는다 |
| O24 | 저부하 VU=1에서 Evidence 오버헤드는 반복 간 소음과 구분되지 않는다 |
| O25 | 실행 중 저장소 안에 로그를 쓰면 run-meta가 dirty로 찍힌다(4.8 추가 A/A) |

## 미실시·다음

- **4.8 선택 미러 시연**: 실시. F3 × 1, pair 판정 40/40 Filter·전체 재생과 일치, New 재생 30/48. 다만 run 범위 dbstate를 비교할 수 없어 Filter의 대체가 아니다(O23, `docs/reports/phase4.8.md`)
- **4.9 Evidence 오버헤드**: 실시, 참고값(지표 절)
- **바이트코드 참조 추출**: 미실시. 계획의 "정적 Call Graph 도구 금지"와 연구 범위 때문이다. 텍스트 폐포의 오탐(O17·O18)과 프레임워크 주입 누락을 줄일 **다음 연구** 후보로 남긴다
- **선택 미러의 상태 비교**: 세션 범위 상태 비교는 다음 연구 후보다(O23)

재현: `scoping/map.py` → `scoping/check_scope.py` → `scoping/evaluate.py`(클러스터 없음). 실제 run은 `k6/run.sh --impact|--tag` → `engine/verdict.py` → `scoping/tag.py` → `scoping/run_check.py`. 임시 경계 브랜치 `scope/E1..E7`은 로컬에만 있다.
