# Phase 4 상세 계획 — 스코핑: Git Diff → 동적 Call Graph → 영향 API → Tag/Filter, 그리고 그 효과의 측정

> **v2 (2026-10-14)** — v1에 외부 검토(P0 2건·P1 2건·P2 5건)를 반영. 변경 요약은 9절, 기대값 전후 차이표는 9.1절. **아직 아무 run도 돌지 않았다** — 9절의 기대값 변경은 전부 run 전의 설계 수정이다.
> 전제: Phase 3 완료(`docs/phase3-result.md`, tag `phase3-done`), Call Graph 결정 D14(`docs/call-graph.md`), 단계 완료 보고 규칙(`CLAUDE.md`).
> `CLAUDE.md`는 방향·확정 사항·단계 요약만, **단계별 세부 작업과 끝난 기준은 이 문서가 기준**. 전체 설계는 `docs/architecture.md` §7·§8. 다르면 이 문서와 call-graph.md가 우선.

---

## 0. Phase 4의 목적

Phase 3까지는 "**전체 corpus를 미러하면** 엔진이 결함을 잡는다"(9/9, 오탐 0)였다. Phase 4는 전체 흐름의 **앞부분**을 채운다.

```
Git Diff → Call Graph → 영향 API → k6 → Istio Mirroring → Legacy / New → Evidence → Engine → Human Review
└──────────── Phase 4 ────────────┘   └──────────────────── Phase 2·3 (완료) ────────────────────┘
```

끝나면 다음이 성립해야 한다.

1. **맵이 합성된다** — Phase 3 baseline run의 Legacy callTree(+hopPath로 묶인 자식 홉)를 합쳐 **corpus 요청 → {클래스}** 맵(정본)과 그 합집합인 **엔드포인트 → {클래스}** 맵(요약·미지 요청용)을 만들고, run마다 같다(결정론).
2. **커밋이 영향 집합으로 바뀐다** — `git diff -M <base>..<head>` → 변경 클래스(**클래스 단위 매칭**, 메서드 단위 아님) → 규칙 1~6 → `impact.json`(영향 요청·선택 세션·근거·전역 발동 여부). Phase 3 변형 13개 + Coupon 변경 2개의 기대 영향을 **run 전에 등록**하고 맞춘다.
3. **Tag/Filter가 파이프라인에 들어간다** — Tag: 전체 재생 + 영향 pair 태그 = **리뷰 우선순위**(재생·검토량을 줄이지 않는다). Filter(B2): 영향 세션만 재생. 둘 다 Phase 3와 같은 엔진·규칙으로 판정.
4. **스코핑의 득실이 숫자로 나온다** — 재생 수 감소율 / Observed-diff Recall / Filter 하 결함 탐지 유지 / 전체 조합 대비(B2-S). **오프라인으로 잴 수 있는 것과 실제 Filter run에서만 잴 수 있는 것을 분리**해서 보고한다(3절 "평가").
5. **서비스 간 영향이 처음으로 시험된다** — Coupon 변경 2건(C1·C2). Kafka 홉(`0.e1`)과 HTTP 홉(`0.h1`)을 거슬러 Order 요청으로 영향이 전파되는 것을 맵이 잡는지, **홉 합산이 없는 맵과 대조**(ablation)해 보인다.

### 정직하게 미리 적어두는 것 — 감소율은 크지 않을 것이다 (v2에서 재계산)

corpus v2.1(세션 11·요청 48). 선택 단위는 세션. 매칭은 클래스 단위, 맵은 요청 단위(3절). v1의 표는 메서드 단위를 암묵적으로 가정해 틀렸다(9절 P0-1).

| 변경 클래스 | 그 클래스가 실행된 corpus 요청 | 선택 세션 | 재생 요청 | 예상 감소율(요청) |
|---|---|---|---|---|
| Order 공통(`OrderService`·`OrderRepository`·`OrderController`, 폐포로 닿는 `Order`·`OrderView` 등) | 모든 `order.*` 요청 | 9/11 | 37/48 | **23%** |
| `PaymentGatewayClient`·`OrderEventPublisher` | `order.pay` 요청만 | 7/11 | 30/48 | **37.5%** |
| `OrderPaidListener`(poc.coupon — Kafka 소비 홉에서만 실행) | 모든 `order.pay` 요청(소비 홉, 쿠폰 유무 무관) | 7/11 | 30/48 | **37.5%** (C1) |
| `CouponService`·`CouponRepository`·`CouponController` | `coupon.*` 직접 요청 + 쿠폰 주문 생성(HTTP 홉) + 쿠폰 결제(Kafka 홉 settle) | 6/11 | 29/48 | **40%** (C2) |
| 전역(설정·빌드·배포·필터·설정 클래스·삭제) | 전부 | 11/11 | 48/48 | 0% |
| 검증 레이어·문서·테스트만 | 없음 | 0/11 | 0 | 재생 불필요 |

**이것이 결과다** — "스코핑 이득 = 변경의 지역성 × 트래픽 구성 × 매칭 해상도(클래스·요청·세션)"를 숫자로 보이는 것이 목적이지, 큰 감소율을 만드는 것이 목적이 아니다. corpus는 v2.1 그대로 둔다. Ekstazi 등의 "테스트 **시간** 감소율"과 우리 "HTTP **요청 수** 감소율"은 같은 지표가 아니므로 나란히 비교하지 않는다.

## 1. 실험 설계 한눈에

```
입력 (Phase 3 산출물 — 전부 레포·runs에 있음, 수정 금지)
  Legacy 레코드: runs/p36-base-1..3 (정본), p33-1..3·p35-base-1..3 (안정성 확인)
  변형 13 + 전체 재생 run: 사다리 v1.1~v1.4 (p35-v1.x-*), 결함 F1~F9 (p36-F<n>-*), 각 3 run, verdict C·B0·B1·prelabel·maxselects
  코드 diff: git diff -M phase3.3-base..phase3.5-v1.x / phase3.5-v1.4..fault/F<n>

4.1 맵 합성        legacy.json ──▶ 요청 → {class} (+ 자식 홉 합산) ──▶ 엔드포인트 요약        scoping/map.json
4.2 영향 산출      git diff ──▶ 변경 클래스 ──▶ 규칙 1~6 ──▶ impact.json (세션 선택)       기대 사전 등록 13+2
4.3 오프라인 평가  감소율 · Recall(요청 단위) · 탐지 유지(요청 단위) · 전체 조합 B2-S · ablation 2종   클러스터 없음
4.4 파이프라인     k6 --impact(세션 부분집합)·--tag, 실제 Filter run 2 변형 × 3, Tag run 2 변형 × 1
4.5 Coupon 변경    C1(OrderPaidListener 결함, Kafka 홉) · C2(CouponService.use 리팩터링, HTTP 홉)   전체 3 + Filter 3
4.6 스코핑 경계    미관측 → 폐포 / 전역 / 영향 없음 사례 7건 (impact만)
4.7 지표·보고      arm × 변형 표, Phase 4 result, phase4-done
4.8 (선택) 선택적 미러 시연 — VirtualService match      4.9 (선택) Evidence 오버헤드 측정
```

### 지표 (정의·분모 고정 — 3절 "평가"에 오프라인/실제 구분)

| 지표 | 정의 | 정답 출처 | 어디서 재나 |
|---|---|---|---|
| **재생 수 감소율** | 1 − 선택 요청 수 / 48 (세션 단위도 병기: 1 − 선택 세션 / 11) | — | 오프라인 |
| **Observed-diff Recall** (주) | 전체 재생 verdict(C, 규칙 후)에서 SAME이 아닌 pair 중 **baseline 기지 차이(F0 = `R000047/0`)를 뺀** 집합 대비, 선택 세션에 든 pair 비율. **분모 0이면 N/A**(1.0 아님) | Phase 3 전체 재생 verdict | 오프라인 |
| Observed-diff Recall (보조) | F0 포함 | 〃 | 오프라인 |
| **결함 탐지 유지(Filter)** | `fault-expectations.json`의 target pair 중 선택 세션에 든 비율 — 행동 차이 없는 변형(v1.1~v1.4)은 N/A | 결함 카탈로그 | 오프라인 + 실제 Filter run |
| **B2-S 전체 조합 대비** | 같은 세션 수의 **모든 부분집합**(C(11,k))의 Recall 평균·최소·Recall 1.0 비율. 보조: 요청 수 ≤ Filter 선택 요청 수인 모든 부분집합 | 전체 재생 verdict | 오프라인(열거, 결정론) |
| **Tag 순위 품질** | 비-SAME pair가 inScope(앞쪽) 구간에 든 비율(= Recall)과 inScope 비율(리뷰 예산). **감소 지표가 아니다** | 전체 재생 verdict | 오프라인 + Tag run |
| (선택) Filter Precision | 선택 pair 중 실제 비-SAME 비율 — 낮은 게 정상(영향 ≠ 차이) | 〃 | 오프라인 |
| (맥락) corpus 커버리지 | 맵에 등장한 빈 클래스 / 코드의 빈 클래스, 엔드포인트 8/8 | 코드 | 4.1 |
| **스코핑 정확도** | 15 변형 + 경계 사례 7건에 대해 run 전 등록한 기대 영향 집합과 impact.json의 일치 | `docs/scope-expectations.json` | 4.2·4.5·4.6 |

## 2. Phase 3에서 배운 것 (반드시 적용)

- **기대는 run 전에 등록** — `docs/scope-expectations.json`(변형별 기대 변경 클래스·미관측 클래스·폐포 결과·영향 요청·선택 세션·전역 여부)과 `fault-expectations.json`(C1·C2 판정). 결과 보고 기대를 바꾸지 않는다. 틀리면 숫자로 남기고 멈춰서 질문
- **도구를 결과 보고 고치지 않는다** — 규칙 1~6은 call-graph.md에 있다. 고쳐야 하면 engine-v1.2 때처럼 버전·사유·전후 결과를 함께 남기고 "사전 등록 아님"을 명시
- 커밋된 코드로 run(dirty=false), 결과·보고서 별도 커밋, 브랜치 squash 금지, 변경 클래스는 `git diff -M`
- 같은 corpus 재실행은 새 표본이 아니다 — 3 run은 결정론 확인용
- 발견은 `docs/findings.md` O14~, 결정은 decision-log D23~
- 엔진(engine-v1.2 → 4.0에서 additive matcher 1건으로 v1.3)·규칙 세트·corpus v2.1·Legacy 이미지·Phase 3 run은 **고정**. 스코핑 도구는 엔진을 import하지 않고 `runs/*/verdict*.json`·`legacy.json`·git만 읽는다

## 3. 확정 사항 (바꾸지 말 것)

**맵 (D23)**
- **Legacy 레코드**로만 만든다(규칙 2). 정본 입력 `runs/p36-base-1..3/legacy.json`(corpus v2.1). `p33-1..3`·`p35-base-1..3`으로 만든 맵은 안정성 확인용(차이는 S011뿐이어야 함)
- **정본 맵은 요청 단위**: `corpus 요청 id → {클래스 FQCN}`. 한 요청의 **모든 홉**(`0`, `0.h*`, `0.e*`)의 callTree 클래스를 그 요청에 합산한다(서비스 간 간선). 홉별 내역 `byHop` 보존
- **엔드포인트 단위 맵은 요약**: 같은 엔드포인트 id(`contract.yaml` endpoints 표)의 요청 집합 합집합. 용도는 사람이 읽는 표와 **corpus 밖 미지 요청**의 fail-closed 스코핑. corpus 재생의 선택에는 쓰지 않는다
  - 이유(v1 → v2 변경): 엔드포인트 합집합으로 선택하면 쿠폰 없는 주문 생성 요청까지 `CouponService` 영향으로 선택돼 Coupon 변경이 사실상 전역(11/11)이 된다. 요청 단위 맵은 이미 있는 데이터(요청별 callTree)를 그대로 쓰는 것이고 매칭은 여전히 **클래스** 단위다 — 메서드 단위 정밀도가 아니다. 두 해상도의 차이는 4.3 ablation으로 **측정**한다(숨기지 않는다)
- 매칭은 클래스(규칙 1). `$`·`Kt`·CGLIB 접미는 엔진 Normalization과 같은 규칙으로 정리
- 산출물 `scoping/map.json`: `{builtFrom, requests: {rid: {session, endpoint, classes, byHop}}, endpoints: {id: {classes, requests, sessions}}, classes: {fqcn: {requests, endpoints}}, coverage}`. 결정론. 커밋한다

**변경 추출·영향 (D24)**
- `git diff -M --name-status <base>..<head>`. 파일 분류: `class`(`src/main/{java,kotlin}`) / `test` / `resource`(`src/main/resources`) / `build`(`pom.xml`, `Dockerfile`) / `deploy`(`deploy/`) / `verify`(`services/evidence-collector`, `engine/`, `corpus/`, `k6/`, `evidence-store/`, `scoping/`) / `docs`
- `class` 파일 → FQCN: 패키지 경로 + 파일명. Kotlin 파일의 추가 최상위 선언(`class|interface|object|enum class|data class`) 전부, 최상위 함수만이면 `<파일>Kt`. 중첩 클래스는 바깥 클래스로. rename(`R`)은 같은 클래스의 수정
- 규칙(call-graph.md 4절 그대로, 폐포만 v2에서 보강):
  - 변경 클래스가 맵에 있으면(**관측**) → 그 클래스가 실행된 요청 전부
  - 맵에 없으면(**미관측**) → **정적 참조 폐포**: head 체크아웃 `src/main` 소스에서 그 클래스의 단순 이름(+그 클래스의 상위 타입·인터페이스 이름)을 import 또는 토큰 경계로 참조하는 클래스를 **전부** 모은다(자기 파일·주석·문자열 제외). 깊이 ≤ 3 BFS. **도달한 관측 클래스를 모두 합집합**으로(첫 도달에서 멈추지 않는다). 깊이 3 안에 관측 클래스에 닿지 못한 가지가 하나라도 남거나, 참조가 전혀 없거나(설정 클래스·필터·메인), 타입이 모호하면(인터페이스 구현체 다수, 리플렉션·문자열 빈 조회) → **전역**
  - 깊이 3의 근거: 이 코드베이스의 계층이 Controller → Service → Repository → Entity/DTO라 비-빈 클래스에서 빈까지 최대 3간선. 더 깊은 참조는 전역으로 흡수(과포함은 fail-closed 방향)
  - 이것은 **보수적 휴리스틱**이지 안전성이 증명된 회귀 테스트 선택이 아니다. Spring DI의 타입 주입·`@Bean`·`@Qualifier`·프록시·리플렉션은 소스 텍스트로 복원되지 않으며, 그런 경우를 전역으로 흡수하는 것이 유일한 보장이다. "모든 실행 경로를 확인했다"는 표현은 쓰지 않는다
  - `resource`·`build`·`deploy` 변경, 클래스 삭제 → **전역**(규칙 4). `verify`·`docs`·`test`만 → **영향 없음**(재생 0, verify 변경이면 "A/A 게이트 필요" 경고). 전역이 하나라도 발동하면 결과는 전역(fail-closed)
- 선택 단위 **세션**: 영향 요청을 하나라도 가진 세션 전체(세션 = 의존 폐포). 요청 단위 선택 금지
- 산출물 `impact.json`: `{base, head, changedFiles[{path,status,kind,fqcns}], changedClasses, observed[], unobserved[{fqcn, closurePaths[], reachedClasses[], unresolved: bool}], globalTriggered, globalReasons[], impactedRequests{rid: reasons[]}, impactedEndpoints(요약), selectedSessions, selectedRequests, reductionRequests, reductionSessions, mapRef}`. 결정론

**모드**
- **Tag(기본)**: 전체 corpus 재생. verdict 뒤 `runs/<runId>/tags.json`(pair → inScope, 근거)과 리뷰 순서(inScope 먼저). **판정·Uncertain 수·재생 수는 바뀌지 않는다** — Tag의 효과는 "비-SAME pair가 앞쪽에 모이는가"(순위 품질)뿐이며, 검토량 감소를 주장하지 않는다. 검토량 감소는 Phase 3의 Rule(수동 검토 감소율)과 Filter(재생 감소)의 몫
- **Filter(B2)**: `run.sh --impact impact.json` → 선택 세션만 재생(VU=min(3, 세션 수)), barrier 기대 집합은 재생 세션으로, dbstate·wiremock export 그대로. 판정은 Phase 3와 같은 엔진·규칙. `fault_check.py --impact`가 target 중 미재생 pair를 "not replayed"로 분리
- **B2-S**: 실제 run 없음 — 전체 조합 열거로만

**Coupon 변경 (4.5) — v2에서 재설계**
- Phase 3에서 Coupon은 양쪽 동일. Phase 4에서 처음으로 **New Coupon ≠ Legacy Coupon**. New Order는 `phase3.5-v1.4` 유지, Legacy는 Order `phase3.3-base`·Coupon `phase3.3-base`. baseline = `p36-base`(재사용)
- 브랜치 `change/C1`·`change/C2` = `phase3.3-base` 위 커밋 1개(Coupon 코드만), 이미지 `coupon-app:phase4-C<n>`, new overlay의 coupon 이미지만 교체
- **C1(진짜 결함, Kafka 홉 전용 클래스)**: `poc.coupon.OrderPaidListener`가 couponKey가 있어도 `settle`을 부르지 않음(1 클래스 1줄). 이 클래스는 **Kafka 소비 홉에서만** 실행된다(쿠폰 없는 결제도 no-op 소비로 실행 — 3.3 실측). 기대 판정: 쿠폰 결제 3건(S006·S007·S010)의 `0.e1` pair에서 writeSet CV(`update coupons` 없음), callTree 차이(실행 특성), dbstate coupons 위반(SETTLED 3 → 0). 기대 영향(클래스 단위·요청 단위 맵): 모든 `order.pay` 요청 → 7세션, 감소율 37.5%. 홉 합산이 없는 맵에서는 이 클래스가 **어느 요청에도 없어** 미관측 → 폐포(참조 없음) → 전역 — ablation으로 대조
- **C2(정상 리팩터링, HTTP 홉)**: `poc.coupon.CouponService.use`의 조회를 바꿈(쓰기 집합·응답·최종 상태 동일 — 예: 존재 확인 + 조회 2쿼리 → 1쿼리 또는 그 반대). 기대 판정: `coupon.use` pair(S004·S005 직접)와 `0.h1` pair(S006·S007·S008·S010 쿠폰 주문 생성)에서 dbRead Uncertain → learn(S004·S006·S008) 라벨 improvement → eval(S005·S007·S010) Uncertain 0. 기대 영향: `CouponService`가 실행된 모든 요청 = `coupon.*` 직접 + 쿠폰 주문 생성 + 쿠폰 결제(settle) → 6세션, 감소율 40%. 홉 합산 없는 맵에서는 S004·S005만 선택 → Order 쪽 `0.h1` Uncertain pair가 빠져 Recall < 1 — ablation으로 대조
- v1의 "C1 = CouponService.settle, 3세션·73%"는 **클래스 단위 매칭과 모순**이라 폐기(9절 P0-1)

**평가 — 오프라인에서 재는 것과 실제 run에서만 재는 것 (D25)**
- 오프라인(전체 재생 verdict를 선택 세션으로 제한): 선택 세션·요청 수, 감소율, 요청 단위 Observed-diff Recall(F0 제외 주·포함 보조), 요청 단위 결함 탐지 유지, **세션 범위 검사**(`sessionViolations`는 세션별이므로 선택 세션만 남기면 재계산과 같다), B2-S 전체 조합, Tag 순위 품질, ablation
- 오프라인으로 **못 재는 것** — 표에 `not evaluated offline`으로 표기: run 범위 `dbstate_equal`(전체 DB 집계 해시라 부분집합의 최종 상태를 재구성할 수 없다), Undelivered·degraded·settleTimeouts, 재생·리셋 시간, 세션 독립성 자체
- 실제 Filter run의 끝난 기준: 재생된 pair의 판정 == 전체 재생 run의 같은 pair 판정(pair 단위 100%), 세션 검사 동일, **run 범위 dbstate 판정이 실제 부분집합 실행에서 기대와 같음**(결함 변형이면 위반, 아니면 일치), Undelivered·degraded 0. 다르면 세션 독립성이 깨진 것 — O번호 발견으로 기록, 지표에서 숨기지 않는다

## 4. 하지 말 것

정적 Call Graph 도구(Soot·WALA) / 메서드 단위 매칭 / LLM 보조 / corpus 확장(v2.1 고정) / 엔진·규칙·Legacy 이미지 변경(4.0 additive matcher 1건만, C2 run 전 사전 등록) / Phase 3 run 재실행·판정 파일 덮어쓰기 / 결함 추가(C1·C2 외) / 요청 단위 Filter / 결과 보고 규칙·기대·corpus 수정 / 운영 트래픽·UI / `mirrorPercentage`(4.8은 match 기반 선택 미러만)

---

## 5. 단계 — 하나 끝나면 다음

### 4.0 준비 (반나절)

할 것
- `docs/phase4-plan.md`(이 문서) 커밋, decision-log D23~D25(10절), CLAUDE.md Phase 4 표·확정 사항·하지 말 것
- `scoping/`(Python, 엔진 import 금지): `map.py`, `impact.py`, `evaluate.py`, `tests/`(fixture = `runs/p36-base-1` 축약본)
- Phase 3 입력 점검 표: 태그·브랜치·runs·run-meta 이미지·verdict 파일(C·B0·B1·prelabel·maxselects·engine-v1.1) 존재
- 엔진 additive matcher 1건 → engine-v1.3(C2 run 전 사전 등록): `externalCalls.responseHashChanged{host, path}`를 규칙으로 설명 가능하게. 3.4에서 "matcher 없어 라벨 불가"로 둔 항목. C2는 응답을 바꾸지 않도록 설계하므로 실제로는 안 쓰일 수 있다. p33·p35·p36 전 run 재판정 pair 판정 변화 0 확인·기록
- 교수님 10/13 피드백 반영 자리

끝난 기준: 입력 점검 표, engine-v1.3 재판정 변화 0, pytest 통과, 보고서 `phase4.0`

구현 시 확정 (4.0)
- **scoping/ 골격**: `common.py`(run·corpus·git 읽기, 클래스 이름 정리 `clean_class`·바깥 클래스 `match_class`, contract.yaml 엔드포인트 표로 엔드포인트 식별, 파일 분류 `classify_path`, `name_status`(`git diff -M --name-status`, pathspec 선택)), `map.py`·`impact.py`·`evaluate.py`(CLI·입출력 형식만 — 4.1~4.3에서 채움, 지금은 exit 2), `check_inputs.py`(Phase 3 입력 점검), `tests/`(fixture `p36-base-1-mini` = runs/p36-base-1의 legacy 축약 60 레코드 + verdict pair 판정, `tests/make_fixture.py`). 엔진 import 없음 — 이름 정리는 엔진 Normalization과 같은 규칙을 다시 구현하고 테스트로 같음을, 엔드포인트 식별은 같은 contract.yaml 표로 엔진 판정 파일의 endpoint와 60/60 같음을 확인
- **매칭 키**: `match_class` = 정리 후 바깥 클래스(`$` 앞) — 중첩 클래스는 바깥 클래스로(D24 "중첩 클래스는 바깥 클래스로")
- **파일 분류 순서**: verify(`services/evidence-collector/`, `engine/`, `corpus/`, `k6/`, `evidence-store/`, `scoping/`) → deploy → docs(`docs/`, `*.md`) → test(`/src/test/`) → class(`src/main/{java,kotlin}/**/*.{java,kt}`) → resource(`src/main/resources/`) → build(`pom.xml`·`Dockerfile`·gradle). **분류 밖 파일(`.gitignore` 등)은 build = 전역**(fail-closed)
- **engine-v1.3**: `externalCalls.responseHashChanged` diff 항목 detail에 `changed: [{host, path}]`(응답 hash가 달라진 호출) 추가, matcher `{host, path}`(정규식 fullmatch, 바뀐 호출 전부가 맞아야), review 제안 템플릿(escape한 host·path), 규칙 대상(`RULE_COVERABLE`)에 포함. 기존 run 판정은 메모리에서만 다시 내고 판정 파일은 덮어쓰지 않는다(`engine/rejudge_check.py`) — 150 판정 파일 pair 판정·집계·runChecks 변화 0. 이 diffKind가 있던 pair(F1 R000008, F7 R000041, F9 쿠폰 주문 생성 4)는 모두 CV라 판정 영향 없음(Uncertain 후보 detail에만 `changed` 추가)
- **테스트 실행**: `engine/tests`와 `scoping/tests`는 각각 따로 실행한다(두 디렉터리 모두 평평한 모듈 이름 `common`을 써서 한 프로세스에서 섞이면 충돌)
- **Java → Kotlin 이동은 git rename(R)으로 잡히지 않는다**(내용이 크게 바뀌어 D + A): 4.2 영향 산출에서 **같은 diff 안에서 같은 FQCN이 삭제·추가되면 같은 클래스의 수정**으로 본다(D17 FQCN 유지, D24 "rename은 같은 클래스의 수정"의 일반화). 삭제만 있고 같은 FQCN 추가가 없을 때만 규칙 4 "클래스 삭제 → 전역"
- **교수님 10/13 피드백 반영 자리**: 내용을 받지 못해 비워 둠(보고서 0절)

### 4.1 맵 합성

할 것
- `scoping/map.py --runs runs/p36-base-1 runs/p36-base-2 runs/p36-base-3 --out scoping/map.json`: Legacy 레코드만, 요청 단위 + 자식 홉 합산 + 엔드포인트 요약 + 클래스 역색인
- 결정론·안정성: p36-base 3 run 각각의 맵 동일(sha256). p33·p35-base 맵과 차이는 S011만
- 커버리지: head 소스의 빈 클래스(`@RestController/@Service/@Repository/@Component`·리포지토리 인터페이스·`@KafkaListener` 클래스·클라이언트) 대비 맵 등장 클래스. 미관측 빈이 있으면 이름·이유
- `docs/call-graph-map.md`: 요청·엔드포인트별 클래스 표, 서비스 간 간선 표(어느 Order 요청이 어느 홉으로 어느 Coupon 클래스를 실행했나)
- **4.2 기대의 사실 확인**(기대를 고치는 게 아니라 전제를 확인): `CouponService`가 `coupon.create/get/use` 전부에 있는지, `OrderPaidListener`가 소비 홉에만 있고 쿠폰 없는 결제의 소비 홉에도 있는지, `CouponService.settle`이 쿠폰 결제의 소비 홉에만 있는지. 전제가 틀리면 멈추고 보고(기대 표를 조용히 바꾸지 않는다)

끝난 기준
- 맵 JSON 커밋, 3 run 동일, 커버리지 표(엔드포인트 8/8), 서비스 간 간선 2종(HTTP `0.h1`, Kafka `0.e1`) 존재
- 사전 등록 예상 맵: `order.create` 요청 ⊇ {OrderController, OrderService, OrderRepository}, 쿠폰 주문이면 + {CouponClient, CouponController, CouponService, CouponRepository} / `order.pay` ⊇ {…, PaymentGatewayClient, OrderEventPublisher, OrderPaidListener}, 쿠폰 결제면 + {CouponService, CouponRepository} / `order.get`·`order.cancel` ⊇ {OrderController, OrderService, OrderRepository} / `coupon.*` ⊇ {CouponController, CouponService, CouponRepository}

### 4.2 영향 산출 + 15 변형 사전 등록

할 것
- `scoping/impact.py --map scoping/map.json --base <ref> --head <ref> --repo . --corpus corpus/corpus-v2.1.json --out impact.json [--explain] [--ignore-kind build]`
- **사전 등록** `docs/scope-expectations.json`(impact.py 실행 전 커밋). 초안:

| 변형 | 변경 클래스 | 맵 관측 | 기대 영향(요청) | 기대 선택 세션 | 비고 |
|---|---|---|---|---|---|
| v1.1 | PaymentGatewayClient + **pom** | 관측 | **build → 전역** | 11 | 정본 전역. `--ignore-kind build` 보조 산출 = pay 요청 → 7 |
| v1.2 | Order, OrderItem, OrderRepository | Order·OrderItem 미관측 → 폐포(OrderRepository·OrderService·OrderView·OrderController …) | order.* 전부 | 9 | 규칙 3 실례 — 폐포 경로 전부 기록 |
| v1.3 | OrderService, OrderPaid, OrderEventPublisher(+Outcome 등) | OrderPaid 미관측 → 폐포 | order.* 전부 | 9 | |
| v1.4 | OrderController, OrderView, CouponClient, ClockConfig, OrderApplication, RequestLogFilter, CachedBodyRequest | ClockConfig·RequestLogFilter·OrderApplication → 참조 없음 → **전역** | 전역 | 11 | 설정·필터·메인은 fail-closed |
| F1 | OrderService | 관측 | order.* | 9 | target R000008(S002) ⊂ |
| F2 | Order | 미관측 → 폐포 | order.* | 9 | |
| F3 | OrderEventPublisher | 관측(pay) | order.pay | 7 | target 첫 결제 7 ⊂ |
| F4 | OrderService | 관측 | order.* | 9 | target S008 ⊂ |
| F5 | OrderRepository, OrderService | 관측 | order.* | 9 | |
| F6 | OrderView | 미관측 → 폐포(OrderService·OrderController) | order.* | 9 | |
| F7 | PaymentGatewayClient | 관측(pay) | order.pay | 7 | target S009 ⊂ |
| F8 | OrderRepository, OrderService | 관측 | order.* | 9 | |
| F9 | OrderService | 관측 | order.* | 9 | |
| C1 | OrderPaidListener(coupon) | 관측(소비 홉만) | order.pay 전부(Kafka 홉) | 7 | target 쿠폰 결제 3 ⊂ |
| C2 | CouponService | 관측 | coupon.* + 쿠폰 주문 생성(HTTP 홉) + 쿠폰 결제(Kafka 홉) | 6 | target 직접 use + `0.h1` ⊂ |

끝난 기준
- 13 변형 impact.json 커밋(`scoping/impacts/<변형>.json`), 사전 등록과 일치 여부 표. **불일치는 고치지 말고 멈춰서 보고**
- 미관측 클래스의 폐포 경로가 impact.json에 전부 기록됨(합집합)

### 4.3 오프라인 평가 — 13 변형 + ablation (클러스터 없음)

할 것
- `scoping/evaluate.py --impacts scoping/impacts --runs runs --expectations docs/fault-expectations.json --out docs/phase4-metrics.json`:
  - 변형별: 감소율(요청·세션), Observed-diff Recall(F0 제외 주 / 포함 보조, **분모 0 → N/A**), 결함 탐지 유지(행동 차이 없는 변형은 N/A), Filter Precision, 세션 검사 재계산 결과, **run 범위 dbstate = not evaluated offline**
  - **B2-S 전체 조합**: 같은 세션 수 k의 모든 C(11,k) 부분집합(최대 462)에 대해 Recall 평균·최소·Recall 1.0 비율. 보조: 선택 요청 수 이하인 모든 부분집합(2,048개 중)에 대해 같은 값. 결정론
  - **ablation 2종**(같은 변형, 맵만 바꿈): (a) 엔드포인트 합집합 맵으로 선택 (b) 자식 홉 합산 없는 요청 단위 맵. 각각 감소율·Recall — "매칭 해상도"와 "서비스 간 간선"의 효과를 숫자로. C1·C2는 4.5에서 같은 ablation
  - Tag 순위 품질: inScope 비율, 비-SAME pair의 inScope 포함 비율
- 표는 **결함 변형(F1~F9)**과 **행동 차이 없는 변형(v1.1~v1.4)**을 나눠 싣는다

끝난 기준
- 13 변형 표. 기대: F 변형 Recall 1.0, v1.x는 N/A(감소율만), 감소율 세 묶음(0% / 23% / 37.5%), F3·F7에서 B2-S 전체 조합의 Recall 1.0 비율이 1 미만(예: 7/11 선택에서 S009 포함 확률 7/11)
- Recall < 1.0인 결함 변형이 있으면 규칙 6 위반(FN) — 멈추고 보고

### 4.4 파이프라인 Tag/Filter + 실제 run

할 것
- `k6/run.js`·`run.sh`: `--impact impact.json`(선택 세션만, VU=min(3,세션 수)), barrier 기대 집합을 재생 세션으로, run-meta에 `impact`(sha256·세션). `--tag impact.json`(전체 재생 + `tags.json`)
- `engine/fault_check.py --impact`(평가 도구): target 중 미재생 분리
- 실제 Filter run **2 변형 × 3**: **F3**(pay, 7세션)·**F9**(order.*, 9세션). 이미지 Phase 3 재사용. (v1의 v1.4 전역 Filter run은 전체 재생과 같아 정보가 없어 제외)
- Tag run **2 변형 × 1**: **F8**(현재 규칙으로도 Uncertain 10이 남는 변형 — 리뷰 순서가 의미 있는 경우)·**F3**(CV). F5는 learned 규칙 적용 후 Uncertain 0이라 Tag 평가 대상이 아님(P2-4)

끝난 기준
- Filter run: 재생 pair 판정 == 전체 재생 run 같은 pair(100%), 세션 검사 동일, run 범위 dbstate 판정 기대와 같음, Undelivered·degraded 0, 재생 수 = impact.json 선택 수, 시간 기록(참고)
- Tag run: tags.json 순서에서 비-SAME pair가 모두 inScope 구간 안(= Recall 1.0), Uncertain·판정 수는 전체 재생과 동일(바뀌면 안 된다)

### 4.5 서비스 간 변경 — Coupon C1·C2

할 것
- 브랜치·이미지(3절). `fault-expectations.json`(판정)·`scope-expectations.json`(영향)에 run 전 등록
- 각각 전체 재생 3 run(`p45-C<n>-1..3`) → verdict → fault_check → impact.json → 오프라인 평가(ablation 포함) → 실제 Filter run 3(`p45-C<n>-f-1..3`)
- C2: learn 세션 라벨 → learned 규칙(provenance C2) → eval 재판정. Coupon 규칙이 Order 쪽 `0.h1` pair에도 적용되는지(같은 uid — 서비스를 넘는 Rule 재사용) 기록

끝난 기준
- C1: 쿠폰 결제 `0.e1` 3 pair CV ×3 run, dbstate 위반, 영향 = order.pay 7세션(37.5%), Recall 1.0, ablation(b)에서 미관측→전역, Filter run 판정 동일
- C2: Uncertain → 라벨 → eval 0, 영향 6세션(40%), Recall 1.0, ablation(a)에서 11세션(0%)·ablation(b)에서 2세션·Recall < 1
- B2-S: C1(7/11)에서 쿠폰 결제 세션 3개가 모두 든 조합 비율 = C(8,4)/C(11,7) ≈ 0.21 — 전체 조합 대비 스코핑의 가치

### 4.6 스코핑 경계 사례 (impact만, run 없음)

| 사례 | 변경 | 기대 |
|---|---|---|
| E1 | `ClockConfig` 한 줄 | 미관측(@Configuration 포인트컷 제외) → 참조 없음 → **전역** |
| E2 | `application.yml` 값 | resource → **전역** |
| E3 | `README.md`·`docs/` | docs → **영향 없음** |
| E4 | `services/evidence-collector` 한 줄 | verify → **영향 없음** + "A/A 게이트 필요" 경고 |
| E5 | `OrderItem`만 | 미관측 → 폐포(`Order`→`OrderRepository`…) → order.* |
| E6 | 클래스 삭제(가정 커밋) | 규칙 4 → **전역** |
| E7 | `CouponRepository` | 관측 → coupon.* + 쿠폰 주문 생성 + 쿠폰 결제 (홉) → 6세션 |

끝난 기준: 7건 impact.json과 기대 일치 표. 임시 브랜치는 로컬 워크트리(push 없음), 보고서에 diff 요약만

### 4.7 지표·보고 + Phase 4 마감

- `docs/phase4-metrics.md`(4.3 + 4.5 + 4.6 + ablation), `docs/reports/phase4.7.md`, `docs/phase4-result.md`(맵·규칙·모드·지표·한계·최종 보고 입력), findings O14~, decision-log
- 한계(미리): 맵은 corpus가 실행한 경로만(F0와 같은 원리) / 참조 폐포는 보수적 휴리스틱(DI 타입 주입·리플렉션 불가 → 전역) / 감소율은 corpus 구성·변경 지역성·해상도에 좌우 / 변형 15·세션 11 / 실제 Filter run은 결정론 확인용 / 요청 수 감소 ≠ 시간 감소
- `git tag phase4-done`

### 4.8 (선택) 선택적 미러 시연 — VirtualService `match`
- impact.json → VS 렌더링: 재생 헤더 `X-Impact-Scope: 1`인 요청만 `mirror`. Tag run에서 k6가 선택 세션 요청에 헤더 → Legacy 전체·New 영향 세션만. barrier New 기대 = 선택 세션. 1 변형(F3) × 1 run

### 4.9 (선택) Evidence 수집 오버헤드
- Legacy `EVIDENCE_ENABLED=false` vs true, VU=1 ×3, k6 p50/p95·CPU·메모리. 판정 없음, 참고값

### Phase 4 종료 조건
4.1~4.7 완료 + `docs/phase4-result.md` + `git tag phase4-done`. 4.8·4.9는 밀리면 제외.

---

## 6. 레포 구조 (Phase 4에서 추가)

```
scoping/                 map.py, impact.py, evaluate.py, tests/, map.json, impacts/<변형>.json
docs/                    phase4-plan.md, scope-expectations.json, call-graph-map.md, phase4-metrics.{json,md}, phase4-result.md
k6/                      run.js·run.sh --impact / --tag
engine/                  fault_check.py --impact, ruleset.py matcher 1건(engine-v1.3)
change/C1, change/C2     Coupon 변경 브랜치 (phase3.3-base 위 1커밋)
```

## 7. 추가 결정 필요 (구현 중 정하지 말고 질문)

- C2의 구체 리팩터링(응답·쓰기 집합이 안 바뀌는 쪽) / 4.8 실시 여부 / 바이트코드 참조 추출을 보조 검증으로 둘지

## 8. 산업·학계 근거 (call-graph.md 7절 + 추가)

| 사례 | 요지 | 반영 |
|---|---|---|
| Ekstazi (ISSTA 2015) | 클래스 단위 동적 의존성으로 회귀 테스트 선택, 테스트 **시간** 32% 절감 | 클래스 단위 매칭, 세션 = 테스트 단위. 시간 vs 요청 수는 다른 지표 |
| Uber BITS (2024) | 트레이스 인덱스 "테스트 → 서비스·엔드포인트"로 변경 시 돌릴 테스트 선택 | 요청 단위 맵 = 트레이스 인덱스 |
| Google Dapper / LinkedIn inCapacity | request ID로 분산 실행 흐름 수집·집계, impact analysis | 홉 합산(D23) |
| 카카오페이·우아한형제들 Kotlin 전환기 | 혼재 상태가 길고 전환이 작은 커밋으로 흩어짐, git rename 보존 | 커밋 단위 스코핑의 현실성, `git diff -M` |

## 9. 검토 반영 기록 (v1 → v2)

| 지적 | 판단 | v2 |
|---|---|---|
| **P0-1** C1·C2 기대가 메서드 단위를 암묵 가정 | **동의(내 오류)**. 더 나아가 엔드포인트 합집합 맵에선 Coupon 변경이 사실상 전역(11/11)이 되는 것도 확인 | 정본 맵을 **요청 단위**(클래스 매칭 유지)로, 엔드포인트 맵은 요약·미지 요청용. C1을 `OrderPaidListener`(Kafka 홉 전용 클래스)로, C2는 `CouponService.use` 유지하되 6세션·40%로 재계산. 해상도 차이는 ablation으로 측정 |
| **P0-2** 분모 0 Recall을 1.0으로 | 동의 | N/A, 결함 변형과 행동 차이 없는 변형을 표에서 분리 |
| **P1-1** 오프라인·실제 run 구분 | 동의 + 정밀화: 세션 범위 검사는 세션별 결과라 오프라인 재계산 가능, run 범위 dbstate는 불가 | 3절 "평가"에 두 목록, `not evaluated offline` 표기, Filter run 끝난 기준에 dbstate 추가 |
| **P1-2** 참조 폐포는 안전 보장 아님 | 동의 | BFS 합집합·미해결 가지 → 전역·깊이 3 근거·"보수적 휴리스틱" 명시·impact.json에 모든 경로 기록 |
| **P2-1** 무작위 1,000회 → 전체 조합 | 동의 | C(11,k) 전부 열거 + 요청 예산 기준 보조 |
| **P2-2** F0 제외만 보고하지 말 것 | 동의 | 주(제외)·보조(포함), pair id `R000047/0` 명시 |
| **P2-3** v1.1 pom 전역 | 동의(v1과 같음) | 정본 전역, `--ignore-kind build` 보조 |
| **P2-4** Tag는 감소가 아니다 | 동의 | "순위 품질"로 정의, F5 → F8·F3으로 교체 |
| **P2-5** 낮은 감소율 서술 | 동의 | "지역성 × 트래픽 구성 × 매칭 해상도", Ekstazi 시간 vs 요청 수 비교 금지, corpus 불변 |
| 검토 질문 1·3·4·5·7 | 동의 | 반영 |
| 검토 질문 2(DI 타입 주입) | 동의 — 소스로 못 본다, 전역이 맞다 | 규칙 3 문구 |
| 검토 질문 6(C1·C2 유지) | 동의하되 C1 클래스 교체 | 위 P0-1 |

### 9.1 기대값 전후 차이표 (run 전 수정, 2026-10-14)

| 항목 | v1 기대 | v2 기대 | 이유 |
|---|---|---|---|
| C1 변경 클래스·영향 | `CouponService.settle` → 3세션·73% | `OrderPaidListener` → 7세션(`order.pay` 전부)·37.5% | 클래스 단위 매칭에서 settle만 격리 불가. Kafka 홉에서만 실행되는 클래스로 교체 |
| C2 영향 | 6세션·40%(메서드 단위 가정) | 6세션·40%(요청 단위 맵·클래스 매칭) | 숫자는 같으나 근거가 바뀜. 엔드포인트 합집합 맵이면 11세션·0% — ablation |
| v1.1~v1.4 Recall | 1.0 | **N/A**(관측된 신규 차이 0) | 분모 0 |
| F 변형 Recall | 1.0 | 1.0(F0 제외 주), 보조로 F0 포함 값 | 정의 분리 |
| B2-S | 무작위 1,000회 | 전체 조합 열거(C(11,k)) + 요청 예산 보조 | 결정론·정확 |
| Tag run 변형 | F5 | F8·F3 | F5는 규칙 후 Uncertain 0 |
| Filter run 변형 | F3·F9·v1.4 | F3·F9 | v1.4 전역은 전체 재생과 같음 |
| 맵 정본 | 엔드포인트 → 클래스 | **요청 → 클래스**(엔드포인트는 요약) | P0-1 분석 중 발견 — Coupon 변경이 엔드포인트 맵에선 전역화 |
| dbstate(Filter) | 오프라인 재계산 암묵 | `not evaluated offline`, 실제 run 기준 | 집계 해시로 재구성 불가 |

## 10. decision-log 항목 (그대로 추가)

```
### D23. 스코핑 맵은 요청 단위(+자식 홉 합산), 선택 단위는 세션, 매칭은 클래스 (2026-10-14)
결정: Legacy baseline 레코드로 corpus 요청 → {클래스} 맵을 만든다. 한 요청의 진입 홉과 자식 홉(HTTP 0.h*, Kafka 0.e*)의 callTree 클래스를 그 요청에 합산한다(서비스 간 간선). 엔드포인트 → {클래스}는 요청 맵의 합집합으로 요약·미지 요청의 fail-closed 스코핑에만 쓴다. Filter·Tag의 선택 단위는 세션(영향 요청을 가진 세션 전체). 매칭은 클래스 단위.
근거: 세션은 의존 폐포라 요청 단위 선택은 상태를 깨뜨린다. 엔드포인트 합집합으로 선택하면 일부 요청에서만 실행된 클래스(쿠폰 주문의 CouponService)가 그 엔드포인트의 모든 요청을 영향으로 만들어 Coupon 변경이 사실상 전역이 된다. 요청별 callTree는 이미 있는 데이터이며 메서드 단위 정밀도가 아니다. 두 해상도의 차이는 ablation으로 측정한다.
한계: 맵은 corpus가 실행한 경로만 안다.

### D24. 미관측 변경 클래스의 참조 폐포는 보수적 휴리스틱 — 합집합·미해결은 전역 (2026-10-14)
결정: 변경 클래스가 맵에 없으면 head 소스에서 그 클래스(및 상위 타입·인터페이스)의 단순 이름을 참조하는 클래스를 전부 모아 깊이 ≤3 BFS로 관측 클래스에 닿는 것을 모두 합집합한다. 깊이 3 안에 해결되지 않는 가지가 있거나, 참조가 없거나(설정 클래스·필터·메인), 타입이 모호하면 전역. 리소스·빌드·배포 변경·클래스 삭제는 전역. 검증 레이어·문서·테스트만 변경은 영향 없음.
근거: Controller→Service→Repository→Entity 계층에서 비-빈 클래스에서 빈까지 최대 3간선. Spring DI의 타입 주입·@Bean·@Qualifier·프록시·리플렉션은 소스 텍스트로 복원되지 않으므로 전역으로 흡수하는 것이 유일한 보장이다. 안전성이 증명된 회귀 테스트 선택이 아니라 fail-closed 휴리스틱이다.
한계: 과포함(전역 발동)은 Filter 이득을 0으로 만든다 — impact.json에 미관측 수·전역 사유를 항상 남긴다.

### D25. 스코핑 평가는 Phase 3 전체 재생 verdict의 오프라인 부분집합이 주, 실제 Filter run은 부분집합 실행의 동등성 확인 (2026-10-14)
결정: 감소율·요청 단위 Observed-diff Recall(F0 제외 주·포함 보조, 분모 0은 N/A)·요청 단위 결함 탐지 유지·세션 범위 검사·B2-S 전체 조합·Tag 순위 품질·ablation은 오프라인으로 계산한다. run 범위 dbstate·Undelivered·degraded·시간·세션 독립성은 오프라인으로 재지 않고(not evaluated offline) 실제 Filter run(F3·F9·C1·C2 × 3)에서 "부분집합 재생의 pair 판정 == 전체 재생의 같은 pair 판정 + dbstate 판정 기대와 일치"로 확인한다.
근거: 전체 재생 run이 이미 있으므로 요청 단위 결과는 그 안에 있다. 집계 해시는 부분집합으로 재구성할 수 없다.
한계: 세션 독립성이 깨지는 경우(공유 자원 경합)는 Filter run에서 판정이 달라지는 것으로만 드러난다.
```

## Claude Code 지시

```
~/Downloads/phase4-plan-v2.md 를 읽고 docs/phase4-plan.md 로 저장해라. 그 문서 10절의 D23~D25를 docs/decision-log.md 끝에 그대로 추가하고, CLAUDE.md에 "Phase 4 — 진행 중" 절(4.0~4.9 표, 상태 빈칸)과 "Phase 4 확정 사항" 요약·"Phase 4 하지 말 것"을 문서 3·4절에서 만들어 넣어라. Phase 3 절은 그대로 둔다. 커밋 `phase4: plan v2, D23~D25` 후 push. 그 다음 4.0을 시작해라 — 시작 전에 무엇을 만들지와 끝난 기준을 설명하고, 끝나면 docs/reports/phase4.0.md 작성·push 후 멈춰라. 4.1부터는 내 승인 후. 계획에 없는 결정은 "구현 시 확정"에 적고, 내 답이 필요한 것만 0절에.
```
