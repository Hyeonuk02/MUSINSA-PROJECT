# Call Graph 설계 확정 — 동적 수집 + 합성, 별도 도구 없음

> 2026-10-12. 상태: 확정(교수님 확인 1건 대기). 이 문서는 `docs/decision-log.md` D14와 `docs/call-graph.md`의 원본이다.
> 관련: `docs/architecture.md` §7(Layer 1 스코핑)·§8(평가), `docs/phase2-result.md` 8절, `docs/references/kakaopay-aop-shadow.md`.

---

## 1. 한 줄

정적 Call Graph 도구는 쓰지 않는다. **매 run에서 AOP·OTel·Envoy가 기록한 실행 경로를 합쳐 "엔드포인트 → 거친 클래스" 맵을 만들고, Git Diff와 대조해 영향 API를 고른다.** 모르면 포함한다(fail-closed).

```
[매 run — Phase 3]
요청 재생 → Spring AOP가 거친 빈·메서드 기록(Evidence callTree)
          → OTel/Envoy가 서비스 간 호출 기록
[코드 변경 — Phase 4]
Git Diff → 바뀐 클래스 → Legacy run의 맵과 대조 → 영향 API
          → 비-빈 클래스는 정적 참조로 보정, 못 찾으면 전역 영향
[운용]
Tag 모드(기본): 전체 미러 + 영향 API에 impactScope 태그 → 리뷰 우선순위
Filter 모드(평가 arm B2): 영향 세션만 재생 → Recall·재생 수 감소 실측
```

## 2. 용어

| 용어 | 뜻 | 어디에 |
|---|---|---|
| 콜트리 | 요청 1건이 실제로 거친 실행 트리 | Evidence `callTree` (기록 단위) |
| 동적 Call Graph | 여러 요청의 콜트리를 합친 것 = "엔드포인트 → 클래스·메서드 집합" 맵 | 엔진 산출물 (분석 단위) |
| 영향 API | Git Diff의 변경 클래스를 거친 엔드포인트 | 엔진 산출물 |

콜그래프는 별도 산출물이 아니라 **기록을 합친 결과**다. 우리가 추가로 만드는 건 (1) 합치는 스크립트, (2) diff 대조 스크립트 두 개뿐이다.

## 3. 무엇을 누가 기록하나 — 수집 범위 (명시)

| 간선 | 기록 주체 | 잡히는 것 | 안 잡히는 것 |
|---|---|---|---|
| 서비스 **안** | Spring AOP `@Around`, 포인트컷 `poc.order..*`(이후 `poc.coupon..*`), `poc.evidence` 제외 | 빈(컨트롤러·서비스·리포지토리·클라이언트) public 메서드 호출 | self-invocation, private·static·final, **빈이 아닌 클래스**(엔티티·DTO·유틸·enum), 프레임워크 내부 |
| 서비스 **사이** — 존재 | Envoy sidecar access log·span | 메시를 지나는 모든 HTTP 호출 (앱 무관) | 메시를 안 지나는 호출(없어야 함, REGISTRY_ONLY) |
| 서비스 **사이** — 요청 귀속 | 재생 헤더 3개 전파(RestClient 인터셉터) + OTel Baggage | 전파된 호출 | 전파 안 된 호출 → "미귀속"으로 따로 집계 |
| DB | StatementInspector (이미 있음) | SQL 원문 | — |

OTel agent는 계측 목록의 라이브러리만 span으로 남긴다(Evidence POST에서 계측을 꺼서 span이 없는 것이 실례). Spring AOP는 프록시 기반이라 빈 경계만 본다. **둘 다 "전체"가 아니며, 위 표가 범위의 전부다.**

## 4. 규칙

1. **기록은 메서드, 판정은 클래스.** AOP는 메서드마다 걸리므로 메서드 단위로 기록(공짜)하고, 영향 매칭은 클래스 단위로 한다. self-invocation 누락은 클래스 단위 판정에 영향이 없다. 메서드 기록은 Legacy/New 콜트리 비교(예: New가 서비스 호출을 건너뜀)에 쓴다.
2. **맵은 Legacy run에서 만든다**(변경 전 기준). New의 콜트리는 비교용이지 스코핑용이 아니다.
3. **미관측 클래스**(변경 클래스가 맵에 없음 — 비-빈이든, corpus가 그 경로를 안 탔든, AOP가 못 봤든 **원인을 구분하지 않는다**): 정적 참조 폐포(참조·import·`implements`/`extends`, 깊이 ≤ 3)를 따라가 **맵에 있는 클래스에 닿으면** 그 클래스들의 엔드포인트로 확장한다. 닿지 못하거나 모호하면(구현체 다수, 리플렉션, 문자열 빈 조회) 전역 영향. 영향 산출물에 `미관측 변경 클래스 수`와 `전역 영향 발동 여부`를 항상 기록한다 — Filter arm의 재생 수 감소가 0이 되면 그 이유가 숫자로 남아야 한다.
4. **비클래스 변경**(설정 yaml, init SQL, build.gradle, 의존성)과 **삭제·개명 클래스**: 전역 영향(모든 API).
5. **검증 레이어 변경**(`poc.evidence`, 엔진, corpus 도구): 영향 선정에서 제외.
6. **fail-closed.** 모르면 포함한다. Filter arm에서 놓침(FN)이 나오면 규칙 버그로 취급해 규칙을 고친다.
7. **Tag 모드가 기본.** Filter 모드는 평가 arm B2로만 쓴다(architecture §7).

## 5. Evidence 스키마 v1 `callTree` (Phase 3에서 채움)

```json
"callTree": {
  "nodes": [
    { "seq": 1, "depth": 0, "class": "poc.order.api.OrderController", "method": "pay", "threw": false },
    { "seq": 2, "depth": 1, "class": "poc.order.service.OrderService", "method": "pay", "threw": false },
    { "seq": 3, "depth": 2, "class": "poc.order.repo.OrderRepository", "method": "findByOrderKey", "threw": false },
    { "seq": 4, "depth": 2, "class": "poc.order.client.PaymentGatewayClient", "method": "charge", "threw": false }
  ],
  "truncated": false
}
```

- 요청당 상한 500노드, 초과 시 `truncated: true`. 시간은 넣지 않는다(잡음). 캡처는 요청 스레드만(ReplayContext ThreadLocal), `@Async`·consumer 스레드는 Phase 3 Kafka 항목에서.
- 리포지토리 프록시 호출이 잡히므로 `dbAccess`와 자연히 대응된다.
- **트리 복원 규칙**: 노드는 pre-order로 나열하고 `depth`로 부모를 복원한다(부모 = 앞쪽에서 가장 가까운 `depth−1` 노드). 이것이 성립하려면 depth 관리가 정확해야 하므로 캡처 규칙을 고정한다:
  - ThreadLocal 스택. `@Around` 진입 시 `depth = 스택 크기`로 노드를 기록하고 push → `proceed()`를 try/catch/finally로 감싸 catch에서 `threw = true` 후 rethrow → **finally에서 pop**. 재귀·중첩·예외 모두 이 규칙으로 depth가 맞는다.
  - 상한(500) 초과 후에도 스택은 유지한다(depth는 계속 맞고 기록만 생략).
  - 엔진 입력 계약: 첫 노드 `depth = 0`, 모든 i에 대해 `depth[i] ≤ depth[i−1] + 1`. 위반이면 FAIL(depth 관리 버그 탐지). `parentSeq`는 두지 않는다 — 불변식 검사가 있으면 depth만으로 충분하다.

## 6. Phase 분할

| Phase | 할 것 | 산출물 |
|---|---|---|
| 3 | AOP 애스펙트 → `callTree` 기록(스키마 v1). A/A 3회 diff ∅ 게이트에 callTree 포함(정규화: 클래스·메서드명만, 순서 유지) | Evidence v1 |
| 4 | `engine/impact.py`: ① Legacy run의 callTree 합성 → `endpoint → {class}` 맵 ② `git diff <base>..<head>` → 변경 클래스 → 규칙 3~6 적용 → 영향 API ③ Tag/Filter 출력(VirtualService `match` 렌더링은 선택) | 맵 JSON, 영향 API 목록, B2 corpus |
| 4 평가 | 아래 지표 표. New v1~v3, 반복 run ≥3. B2-S(같은 수 무작위)와 대비 | 결과 표 |

**평가 지표 — "Recall" 하나로 부르지 않는다.** 전체 미러에서 엔진이 diff를 낸 엔드포인트를 정답으로 쓰면 그건 같은 Evidence 렌즈로 본 **관측된 차이**에 대한 지표다. 관측과 독립인 정답은 **결함 주입 카탈로그**(어느 클래스에 무엇을 넣었고 어느 엔드포인트가 영향받는지 구성상 알고 있음)이고, architecture §8의 "결함 탐지율"이 그것이다.

| 지표 | 정의 | 정답 출처 | 재는 것 |
|---|---|---|---|
| **결함 탐지율** (주 지표) | 주입 결함 중 전체 미러 + 엔진이 잡은 비율 | 결함 카탈로그 (관측 독립) | 파이프라인의 탐지 능력 |
| **Observed-diff Recall** | 전체 미러에서 diff 난 엔드포인트 중 Filter가 포함한 비율 | 전체 미러 arm의 관측 | 스코핑으로 잃는 것 |
| **재생 수 감소율** | 1 − (Filter 재생 수 / 전체 재생 수) | — | 스코핑으로 얻는 것 |
| (선택) Filter Precision | Filter가 포함한 엔드포인트 중 카탈로그상 진짜 영향 비율 | 결함 카탈로그 | 과포함 |
| (맥락) corpus 커버리지 | 맵에 등장한 엔드포인트·클래스 수 / 전체 | 코드 | 분모 밖이 얼마나 되는지 |

## 7. 근거 (업계·학계)

- 현업 APM(Pinpoint 등)은 Java agent 바이트코드 계측으로 트랜잭션별 call stack을 모으고 그것을 합쳐 서비스 맵을 만든다. 정적 분석기로 그래프를 따로 뽑지 않는다.
- 학계 모니터링 프레임워크 Kieker는 AspectJ 프로브로 실행 트레이스를 기록해 call tree·dependency graph를 복원한다 — "AOP로 콜트리"는 학계의 표준 방식.
- 회귀 테스트 선택 Ekstazi는 **클래스(파일) 단위** 동적 의존성으로 32% 시간 절감, Apache Camel·CXF 채택 — 영향 분석에 클래스 단위면 충분하다는 선례. 단 Ekstazi는 agent로 로드된 클래스 전부를 추적하므로 완전하고, 우리는 AOP(빈만)라 맵에 없는 변경 클래스를 규칙 3(미관측 → 정적 폐포 → 전역)으로 보정한다.
- 카카오페이손보는 Spring AOP를 인하우스 섀도우에 사용(빈 경계).
- 정적 Call Graph의 DI/AOP/리플렉션 unsoundness 보정 비용 대비, 이미 돌리는 run에서 실제 경로가 공짜로 나온다.

## 8. 한계 (보고서에 그대로)

- 맵은 corpus가 실행한 경로만 안다. corpus 밖 API는 "영향 없음"이 아니라 "정보 없음"이며, Tag 모드에서는 어차피 전부 미러된다.
- 수집 범위는 3절 표가 전부다. 표 밖의 호출은 기록되지 않으며, 그 위험은 규칙 3·4·6으로 fail-closed 처리한다. 맵에 없는 변경 클래스는 원인(비-빈/미실행/미관측)을 구분할 수 없으므로 모두 "미관측"으로 같게 다룬다.
- Observed-diff Recall은 관측된 차이에 대한 지표다. 미실행 경로와 Evidence가 못 잡는 차이는 분모에 없으며, 그 크기는 corpus 커버리지로 따로 보고한다. 관측 독립 지표는 결함 탐지율뿐이다.
- 교수님 확인 필요: 원 요구 "Call Graph"를 동적 수집·합성으로 해석해도 되는지.

## 메모 (Phase 3.7, 2026-10-14) — Phase 4 변경 클래스 추출

- 변경 클래스 추출은 `git diff -M`(rename 감지)으로 한다. Java → Kotlin 전환은 `Foo.java` 삭제 + `Foo.kt` 추가로 기록되며, rename 감지 없이는 "클래스 삭제 + 새 클래스"로 잘못 읽힌다(FQCN은 같음 — D17). 현업 전환기 두 곳도 git rename 이력 보존을 주의점으로 꼽았다(references/kakaopay·woowahan-kotlin-migration.md)
- 사다리(`phase3.5-v1.x` 커밋)·결함 브랜치(`fault/F<n>`, 기준선 위 1커밋)는 **squash 금지** — 커밋 하나가 Phase 4 스코핑 입력 단위다
