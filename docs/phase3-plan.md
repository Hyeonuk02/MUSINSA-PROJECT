# Phase 3 상세 계획 — 처음으로 Legacy ≠ New: MSA 확장 + 점진 전환 사다리 + 판정 엔진

> **v2.1 (2026-10-13)** — v1 초안에 GPT 1차 검토(P0 4건·P1 4건·평가 설계)와 2차 검토(ACK 기록 스레드·추가 홉 폐포·F7 정답)를 반영. 변경 요약은 9절.
> 전제: Phase 2 완료(`docs/phase2-result.md`, A/A diff ∅), Call Graph 결정(D14, `docs/call-graph.md`), 단계 완료 보고 규칙(`CLAUDE.md`).
> `CLAUDE.md`는 방향·확정 사항·단계 요약만, **단계별 세부 작업과 끝난 기준은 이 문서가 기준**. 전체 설계는 `docs/architecture.md`. 다르면 이 문서와 architecture.md가 우선.

### 3.0 확정 (실제 스택 반영)

3.0 사전 점검(`docs/reports/phase3.0.md`)에서 확인한 실제 스택과 그에 따른 결정. **3절·3.1·7절의 Jackson 2·Gradle·Framework < 6.1 폴백 문구는 이 블록이 우선한다.**

| 항목 | 실제 |
|---|---|
| 빌드 | Maven |
| Spring Boot | 4.1.1 |
| Spring Framework | 7.0.9 (`TransactionExecutionListener` 있음) |
| Hibernate ORM | 7.4.5.Final |
| Jackson | 3.1.5 (`tools.jackson`) |
| JDK | 17 |
| Kotlin (Boot BOM) | 2.3.21 |

- **D-1a 빌드**: Maven 유지 + `kotlin-maven-plugin`(`spring`·`jpa` 컴파일러 플러그인). 3.5에서 그대로 쓴다. 계획의 "Gradle Kotlin 플러그인"은 이것으로 읽는다
- **D-1b JSON**: `poc.evidence`는 Jackson 3 `JsonMapper`를 패키지 안 private 고정 인스턴스로 쓴다(앱 빈 공유 금지는 그대로). 계획의 "Jackson 2"는 "Boot 기본 Jackson(현재 3.1.5)"으로 읽는다
- **D-1c 3.8**: v3b(Spring Boot 4) 삭제 — 이미 Boot 4.1.1. **v3a = JDK 17 → 25(LTS)만** 선택 과제로 남긴다. Legacy가 JDK 17이라 다음 두 변경을 넘어가는 실험이 된다 — v3a의 관찰 포인트:
  - JDK 18 (JEP 400): 기본 charset이 UTF-8로 고정(`file.encoding` 기본값 변경)
  - JDK 19: `Double.toString`·`Float.toString`이 최단 표현으로 바뀜(일부 값의 문자열이 달라짐)
- **D-2 자원**: (A) Docker Desktop 메모리를 3.2 전까지 12GiB로 증설(사용자) + (C) JVM·MySQL 상한과 k8s resources를 base 매니페스트에(양쪽 동일). Order는 3.1에서 `JAVA_TOOL_OPTIONS`에 `-Xmx384m -XX:MaxMetaspaceSize=128m`(실측 후 조정 가능), MySQL `--innodb-buffer-pool-size=64M`, requests·limits. Coupon·Kafka는 3.2·3.3에서 같은 방식. D19(스택별 Kafka) 유지, 공유 브로커는 12GiB에서도 부족할 때만
- Framework < 6.1 폴백(Hibernate Interceptor)은 불필요 — 7.0.9 실측

---

## 0. Phase 3의 목적

Phase 2는 "같은 코드를 양쪽에 올리면 차이 0"까지였다. Phase 3는 **New를 실제로 다르게 만들고, 그 차이를 엔진이 판정**하는 단계다. 끝나면 다음이 성립해야 한다.

1. **실험 대상이 MSA다** — Order·Coupon 실서비스(각자 DB) + Payment(WireMock, 외부 PSP) + Kafka 이벤트. 스택마다 한 벌, 스택 간 공유 자원 없음.
2. **New ≠ Legacy** — Order를 Java에서 Kotlin으로 **점진 전환**(v1.1 → v1.4)하고, 결함 카탈로그로 정답 있는 변경(v2)을 만든다. 각 단계가 작은 commit이라 Phase 4 스코핑 평가의 입력이 된다.
3. **Evidence가 4축 + 실행 경로 + 타임라인이다** — 응답 / DB 접근(SQL 원문 + 최종 상태) / 외부 호출 / 이벤트 + callTree(AOP) + 트랜잭션 완료. 한 요청 안의 모든 기록이 **하나의 seq 카운터**를 공유해 순서가 복원된다. 서비스 간 간선은 Envoy·OTel.
4. **엔진이 판정한다** — Normalization → 요청 단위 + 집계 비교 → **SAME / Improvement / Contract Violation / Uncertain** → Uncertain만 사람 → Rule 등록 → **학습에 쓰지 않은 세션·변형**에서도 Uncertain이 줄어드는 것을 숫자로 보인다.

### 세 종류의 diff — 혼동 금지

| | 코드 diff (git) | 행동 diff (Evidence) |
|---|---|---|
| **A/A** (같은 이미지 양쪽) | 없음 | **0이어야 함.** 아니면 파이프라인 잡음 → 먼저 고친다 |
| **A/B v1** (Kotlin 전환) | 매 단계 반드시 있음 | 0이면 "전환이 안전함"의 증거, 아니면 "어디가 왜"를 분류. **0을 요구하지 않는다** |
| **A/B v2** (결함 주입) | 클래스 1~2개 | **있어야 함.** 기대 판정과 일치해야 탐지 성공 |

Phase 3에서 **하지 않는 것**: 콜트리 합성·영향 API 선정·Tag/Filter·스코핑 평가(Phase 4, D14), 운영 시연, 오버헤드 측정, 정적 Call Graph, UI, 인증, Store DB, Transactional Outbox·Saga(분산 일관성은 범위 밖으로 명시).

## 1. 실험 설계 한눈에

```
Legacy (고정, Java)             New 사다리 (같은 corpus v2, 같은 Legacy)
Order + Coupon + Kafka          v1.1  Order: PaymentGatewayClient만 Kotlin    코드 diff 1클래스
+ WireMock                      v1.2  + 엔티티·리포지토리 Kotlin              JPA 함정 구간
                                v1.3  + OrderService Kotlin
                                v1.4  + OrderController Kotlin (= Order 전면)
                                v2.x  v1.4 위에 결함 카탈로그 1건씩           정답 있음
                                v3a/b (선택) JDK만 / Spring Boot 4           전역 영향 케이스
```

| 변경 | 코드 diff | Phase 3에서 재는 것 | Phase 4에서 재는 것 |
|---|---|---|---|
| v1.1~v1.4 점진 Kotlin | 1 → 전부 | 엔진: 응답엔 없고 SQL·트랜잭션에만 보이는 차이를 잡나. 0이어도 결과 | 스코핑: 재생 수 감소율이 변경 범위에 따라 어떻게 줄어드나 |
| v2 결함 카탈로그 | 1~2 클래스 | 결함 탐지율(관측 독립 정답), 오판정률, Rule 전후 검토 감소 | Observed-diff Recall |
| v3 런타임 | 빌드·설정 | Normalization·Rule 루프(형식 차이 대량) | 규칙 4 → 전역(스코핑 비적용 케이스) |

평가 지표는 `docs/call-graph.md` 6절의 세 지표에 더해 3.7의 네 지표(결함 탐지율 / 수동 검토 감소율 / 오판정률 / Rule 재사용 효과)를 쓴다. **Rule은 학습 세트에서만 만들고 평가 세트에서 잰다**(3.4·3.7).

## 2. Phase 2에서 배운 것 (반드시 적용)

- A/A 표준 조건 VU=3 ×3, diff ∅ — **인프라·엔진 단계(3.1~3.4)와 base 이미지의 게이트**. A/B 단계(3.5·3.6)의 끝난 기준은 "모든 diff가 설명됨"(D13·0절 표)
- 설계로 차단한 잡음 10항목 유지(`phase2-result.md` 6절). 새 서비스·컴포넌트에도 동일 적용: `APP_FIXED_CLOCK`, batch off, open-in-view off, 고정 에러 본문, `x-request-id`·Host 제외
- Store 준비 확인·인증서 preflight·spill hostPath 스택별·sidecar 필수·`EVIDENCE_HEADERS` 분리
- 보고는 `docs/reports/phase3.<step>.md`, 결정 필요 사항은 0절, 문서에 없는 결정은 질문
- 엔진은 `runs/` 파일만 읽고 클러스터에 접근하지 않는다(D12). 앱·매니페스트 import 금지
- 결정론 때문에 **같은 corpus의 재실행은 새 데이터가 아니다** — 평가 분리는 run 번호가 아니라 세션·변형으로 한다

## 3. 확정 사항 (바꾸지 말 것)

**식별·전파**
- **Evidence 키 = `(runId, replayRequestId, stack, hopPath)`.** `service`·`origin`(`http`|`kafka`)은 키가 아니라 필드. 같은 서비스를 한 요청이 두 번 부르면 Evidence가 두 건 남는다(D15)
- **`hopPath`**: 진입 요청 `"0"`. 어떤 홉에서 나간 n번째 HTTP 호출로 생긴 Evidence는 `<부모>.h<n>`, n번째 이벤트 발행의 소비 Evidence는 `<부모>.e<n>`. n은 **그 홉 안에서의 종류별 순번**(요청 전역 seq가 아님 — 쿼리 수가 바뀌어도 hopPath는 안 바뀌어야 짝이 유지된다). 예: `0`, `0.h1`, `0.e1`, `0.h1.h1`
- k6가 `X-Replay-Hop-Path: 0`을 붙이고, 전파 인터셉터(RestClient)와 ProducerInterceptor가 자식 hopPath를 계산해 헤더로 전달. RecordInterceptor가 consumer 스레드의 ReplayContext를 설정·정리. OTel Baggage는 쓰지 않는다
- `EVIDENCE_HEADERS` = 재생 헤더 3개 + `X-Replay-Hop-Path` + `Idempotency-Key` + `Content-Type`

**타임라인·트랜잭션·이벤트 (D16)**
- 요청 버퍼에 **단일 seq 카운터**. SQL 문장, 외부 호출, 이벤트 발행, 트랜잭션 완료가 모두 같은 카운터로 번호를 받는다. 각 배열 안에서 seq는 연속이 아니다
- 트랜잭션은 **`TransactionExecutionListener`**(Spring Framework 6.1+)를 트랜잭션 매니저에 등록해 ReplayContext로 귀속 → `transactions: [{seq, name, phase, outcome}]`. **`beforeCommit`에서 `COMMIT_BEGIN`, `afterCommit`/`afterRollback`에서 `COMMITTED | ROLLED_BACK | COMMIT_FAILED`** — 한 트랜잭션이 타임라인에 두 번 찍힌다. 필터에서 동기화를 등록하지 않는다(트랜잭션 밖에서는 등록 불가). Framework < 6.1이면 Hibernate `Interceptor.afterTransactionCompletion` 폴백(이때 COMMIT_BEGIN은 `beforeTransactionCompletion`)
- 이벤트 발행은 **동기**(`send(...).get(timeout)`), `events.published[{seq, topic, key, payloadHash, ack: ok|failed}]`. **ack는 `get()`이 돌아온 호출 스레드에서 기록한다** — `ProducerInterceptor.onAcknowledgement()`는 Producer I/O 스레드라 ReplayContext가 없으므로 헤더 전파(`onSend`)에만 쓴다. "커밋 전 발행"은 불리언이 아니라 **`publish.seq < 그 트랜잭션의 COMMIT_BEGIN.seq`**로 판정 — `afterCommit` 리스너와 `@TransactionalEventListener(AFTER_COMMIT)` 중 어느 쪽이 먼저 불리든 판정이 흔들리지 않는다(Spring 문서: AFTER_COMMIT 콜백 안에서도 트랜잭션 리소스가 활성으로 보일 수 있어 `isActualTransactionActive()`로는 못 가른다). 실제 콜백 순서는 3.1·3.3에서 실측해 기록
- Kafka: 스택별 1브로커, partition 1, producer 재시도 0, consumer `DefaultErrorHandler(FixedBackOff(0, 0))` + DLQ recoverer — 재시도 없음. 소비 Evidence `origin: kafka`, `event{topic, key, payloadHash}`, `consumeOutcome: ok|failed`

**격리·구성**
- 서비스 축: Order는 Order DB만, Coupon은 Coupon DB만(mysql ingress = 소유 서비스 podSelector). 스택 축: Kafka도 NetworkPolicy로 같은 ns만(D19)
- Payment = WireMock(외부 PSP), 스택별 1개, 스텁 동일, journal을 run마다 export
- **Order의 쿠폰 주문 처리 순서 고정: 주문 행 INSERT → Coupon `use` 호출 → 커밋.** Coupon 실패(404·409)면 400 + 로컬 롤백. "Coupon은 USED인데 Order는 실패"(보상 누락)는 **분산 일관성 문제로 범위 밖**이며, 차등 검증은 양쪽이 같으면 SAME으로 본다는 한계를 명시
- Legacy/New의 Coupon은 Phase 3 내내 동일 코드(Java). Coupon 변경은 Phase 4 서비스 간 영향 실험에서

**검증 레이어**
- `poc.evidence`는 Java 그대로, Coupon·Kotlin New에 **수정 없이** 부착. 의존은 Servlet API·Hibernate SPI·Spring AOP·Spring TX·java.net.http·Jackson 2. **JSON 직렬화는 패키지 안의 고정 설정 private `ObjectMapper`** — 앱의 ObjectMapper 빈을 쓰지 않는다(New가 `jackson-module-kotlin`을 등록해도 Evidence 바이트가 안 바뀌어야 함). 자체 writer는 만들지 않는다(3.8 Boot 4를 실제로 할 때 `jackson-core` 2 명시 의존으로 해결)

**전환·엔진**
- Kotlin 전환 규칙(D17): 패키지·클래스 FQCN·API 경로·응답 계약 유지. `kotlin-spring`(all-open)·`kotlin-jpa`(no-arg) 필수. 엔티티는 data class 금지. **일부러 흔한 실수를 남기지 않는다** — v1에서 나오는 차이가 발견이고, 결함은 v2에서만. 단계마다 commit 1·이미지 태그 1(`order-app:phase3-v1.1` …)
- **DB 계약은 두 층**(D18): 기능 계약 = 쓰기 문장 집합(INSERT/UPDATE/DELETE × 테이블)·최종 DB 상태·불변식 → 위반 시 Contract Violation. 실행 특성 = 읽기 횟수·순서 → 기본 Uncertain, 엔드포인트별 **쿼리 예산**(`maxSelects`)이 선언된 경우에만 초과 시 Contract Violation
- 판정 우선순위 Contract Violation > Uncertain > Improvement > SAME. Undelivered는 판정이 아니라 전달 지표
- **Rule 학습/평가 분리**: corpus v2 세션에 `split: learn|eval`. 규칙은 learn 세션과 v1.1~v1.2에서만 만들고, eval 세션·v1.3 이후·F 변형에서 효과를 잰다. YAML 규칙은 데이터이며 실행 코드를 넣지 않는다. 요청 단위 규칙과 세션·run 단위 규칙을 구분

## 4. 하지 말 것

콜트리 합성·`endpoint → class` 맵·git diff 대조·Tag/Filter·B2 arm(Phase 4) / 정적 Call Graph / 운영 시연·`mirrorPercentage` / 오버헤드 측정 / LLM 보조 판정 / Store DB·인증·UI / `@Async` 스레드 전파(Kafka consumer 스레드만) / Coupon 코드 변경 / 결함을 v1 사다리에 섞는 것 / Outbox·Saga / 자체 JSON writer / 같은 데이터로 규칙을 만들고 같은 데이터로 평가하는 것

---

## 5. 단계 — 하나 끝나면 다음

### 3.0 사전 점검 (반나절)

할 것
- 버전 보고: Spring Boot·**Spring Framework(6.1 이상인지 — `TransactionExecutionListener`)**·JDK·Hibernate·Jackson·Gradle, Kotlin 플러그인 추가 가능 여부
- `poc.evidence`가 현재 JSON을 어떻게 만드는지(앱 ObjectMapper 빈 공유 여부) 보고
- kind 호스트 자원: 스택별 Kafka 브로커 2개(각 512MB~1GB) 여유. 부족하면 3.3 대안
- Phase 2 잔여: `phase2-done` 태그, phase2-result 4절 (g) 관측 분리, README 문서 목록
- `docs/references/industry-cases-phase3.md`(8절 내용)

끝난 기준: 보고서 `phase3.0`에 버전·자원·ObjectMapper 표, 잔여 3건 커밋·태그 push

### 3.1 Evidence v1 — 타임라인·callTree·외부 호출·트랜잭션·error·최종 DB 상태

할 것
- `docs/evidence-schema-v1.json` (strict, `schemaVersion: "v1"`). v0 대비:
  - `hopPath`(string), `service`, `origin`(`http`|`kafka`)
  - 단일 seq: `dbAccess.statements[].seq`, `externalCalls[].seq`, `events.published[].seq`, `transactions[].seq`가 **같은 카운터**
  - `callTree: {nodes: [{seq, depth, class, method, threw}], truncated}` — `call-graph.md` 5절 규칙(ThreadLocal 스택, finally pop, 500 상한, `depth[i] ≤ depth[i−1]+1`). callTree의 seq는 별도 카운터(노드 수가 많아 타임라인과 섞지 않음)
  - `externalCalls: [{seq, method, host, path, requestBodyHash, status, responseBodyHash, childHopPath}]`
  - `events: {published: [{seq, topic, key, payloadHash, ack, childHopPath}]}` — 3.1은 빈 배열
  - `transactions: [{seq, name, phase, outcome}]` — phase ∈ `COMMIT_BEGIN | COMPLETED`, outcome은 COMPLETED일 때만
  - `error: {type, where} | null` — `chain.doFilter` 예외 시. `response.status`는 컨테이너가 보낸 값을 못 얻으면 `0`
  - `event: {topic, key, payloadHash} | null` — `origin=kafka`일 때 `request` 대신. `request`·`response`는 그때 null 허용
- `poc.evidence` 추가: `CallTreeAspect`(`@Around("execution(* poc.order..*(..)) && !within(poc.evidence..*)")`), `ReplayPropagatingInterceptor`(RestClient: 재생 헤더 + 자식 hopPath + externalCalls 기록), `EvidenceTransactionListener`(`TransactionExecutionListener`, `TransactionManagerCustomizer`로 등록), private 고정 `ObjectMapper`
- 최종 DB 상태: `k6/dbstate-export.sh` — 스택별 테이블마다 `count`, 숫자 컬럼 `sum`, business key 순 canonical 행(id·timestamp 제거)의 `sha256` → `runs/<runId>/dbstate-<stack>.json`
- WireMock journal: run.sh export 단계에 `__admin/requests` → `runs/<runId>/wiremock-<stack>.json`
- `engine/common.py`: v1 입력 계약(스키마 + runId·stack·hopPath 형식 + depth 불변식 + seq 단조 증가). `diff_v0.py`는 v1 필드도 비교(callTree는 class+method 순서, externalCalls는 개수·순서·method·path·bodyHash, transactions는 개수·outcome 순서, events.published는 개수·topic·payloadHash·ack)

구현 시 확정 (자리)
- `error` 상태코드 획득 / `TransactionManagerCustomizer` 등록 방식 / 포인트컷 최종 식 / callTree seq와 타임라인 seq 분리 확인

구현 시 확정 (3.1)
- **error 상태코드**: `chain.doFilter` 예외 시점에는 컨테이너가 보낼 상태코드를 알 수 없어 `response.status = 0`, `headers {}`, `body ""`(bodyHash는 빈 바이트열). `error.type` = 원인 예외(ServletException 래핑 제거), `error.where` = `EVIDENCE_APP_PACKAGES` 안 첫 스택 프레임의 `class.method`. Evidence를 남긴 뒤 예외를 그대로 던진다(컨테이너 에러 처리는 그대로 — 실측 응답 500, Spring 기본 에러 본문)
- **트랜잭션 리스너 등록**: `TransactionExecutionListener` 빈 하나. Boot 4.1의 `ExecutionListenersTransactionManagerCustomizer`가 `JpaTransactionManager`에 붙인다(별도 `TransactionManagerCustomizer` 불필요). 롤백 경로에는 `COMMIT_BEGIN` 없이 `COMPLETED/ROLLED_BACK`만 찍힌다. `readOnly` 트랜잭션(GET)도 `COMMIT_BEGIN`·`COMMITTED`가 찍힌다
- **포인트컷 최종 식**: 대상 패키지를 env `EVIDENCE_APP_PACKAGES`(쉼표, Order는 `poc.order`)로 받아 `AspectJExpressionPointcutAdvisor`로 등록 — `poc.evidence`를 Coupon·Kotlin New에 수정 없이 붙이기 위함. 식: `(execution(* <pkg>..*.*(..))) && !within(poc.evidence..*) && !within(jakarta.servlet.Filter+) && !@within(org.springframework.context.annotation.Configuration)`. 필터 제외 이유: `OncePerRequestFilter`의 final 메서드를 CGLIB 프록시가 가로채지 못해 프록시 상태로 호출되면 깨진다. advisor order는 최우선(트랜잭션 프록시 바깥)
- **callTree class**: 사용자 클래스 FQCN. Spring Data 리포지토리 프록시는 대상 패키지의 인터페이스(`poc.order.OrderRepository`)로 기록 — `save`처럼 `CrudRepository`에 선언된 메서드도 `OrderRepository`로 잡힘(실측)
- **callTree seq와 타임라인 seq 분리**: 확인. callTree는 1부터 1씩, 타임라인은 SQL·외부 호출·트랜잭션이 한 카운터(배열 안에서 비연속). 엔진 입력 계약이 둘 다 검사(`engine/common.py`)
- **외부 호출 인터셉터 부착**: Boot 4는 `RestClient.Builder` 자동 구성이 `spring-boot-restclient` 모듈로 분리돼 있어 Order에 `spring-boot-starter-restclient`를 추가하고, `PaymentGatewayClient`가 정적 `RestClient.builder()` 대신 Boot의 `RestClient.Builder`를 주입받도록 바꿨다(요청 팩토리 `SimpleClientHttpRequestFactory` 고정은 유지). `poc.evidence`는 `RestClientCustomizer`로 인터셉터를 붙인다(클래스가 있을 때만)
- **재생 헤더**: Evidence는 `X-Replay-Request-Id`·`X-Run-Id`·`X-Session-Id`·`X-Replay-Hop-Path` 넷이 모두 있을 때만 남긴다. `EVIDENCE_HEADERS`·`REQUEST_LOG_HEADERS`에 `X-Replay-Hop-Path` 추가. k6가 `X-Replay-Hop-Path: 0`
- **Store 키**: 3.1은 진입 홉만 있으므로 Store는 v0 키 그대로. hopPath 키는 3.2(Store v1)
- **실측 콜백 순서**(`docs/reports/logs/phase3.1-tx-callback-order.txt`): 동기화 `beforeCommit` → 리스너 `beforeCommit`(**COMMIT_BEGIN**) → `doCommit`(JPA "Committing") → Hibernate flush SQL(**UPDATE가 COMMIT_BEGIN 뒤**) → 동기화 `afterCommit` → 동기화 `afterCompletion` → 리스너 `afterCommit`(**COMMITTED**). 즉 동기화 afterCommit이 리스너 afterCommit보다 먼저다. `@TransactionalEventListener(AFTER_COMMIT)`의 발행은 COMMIT_BEGIN과 COMMITTED **사이** seq를 받게 되고, F3 판정(`publish.seq < COMMIT_BEGIN.seq`)은 이 순서와 무관하게 성립한다
- **dbstate**: `k6/dbstate-export.sh` — 테이블별 `count`, 숫자 컬럼 `sum`, business key 순 행(auto id·시각 제외, 외래키는 `order_key`로 치환)의 canonical JSON sha256. 엔진(`diff_v0`)은 legacy·new 파일 전체 동일성을 본다
- **WireMock journal 비교**: journal은 최신순으로 나오고 VU=3에서는 요청 간 순서가 보장되지 않아 `(method, url, body)` 목록을 정렬한 **다중집합**으로 비교한다
- **자원(D-2 (C))**: Order `-Xmx384m -XX:MaxMetaspaceSize=128m`, requests 100m/512Mi·limits 2/768Mi. MySQL `--innodb-buffer-pool-size=64M`, requests 100m/256Mi·limits 1/512Mi. 실측 working set: order 432/420MiB(전 590/588), mysql 443/443MiB(전 473/473) — `docs/reports/logs/phase3.1-workingset.txt`

끝난 기준
- Legacy·New 동일 이미지(`order-app:phase3-base`)로 A/A 3회(VU=3) diff ∅ — callTree·externalCalls·transactions 포함
- `POST /pay` Evidence: `externalCalls` 1건(charge, `childHopPath: "0.h1"`), `transactions`에 `COMMIT_BEGIN`·`COMMITTED` 각 1건, 타임라인에서 **외부 호출 seq < COMMIT_BEGIN seq < COMMITTED seq**, callTree에 Controller→Service→Repository→Client
- `JpaTransactionManager`에 리스너가 실제로 붙어 양쪽 스택에서 `transactions`가 기록됨을 확인(Boot `TransactionManagerCustomizer` 경유). `beforeCommit` → `doCommit` → `afterCommit` → 동기화 `afterCommit`의 실제 순서를 로그로 실측해 보고서에 기록(3.3 F3 판정의 근거)
- 같은 Idempotency-Key 재결제: `externalCalls` 0건
- 임시 예외 엔드포인트(테스트 후 제거)로 `error` 경로 1건, 트랜잭션이 있었다면 `ROLLED_BACK`
- dbstate·wiremock journal 양쪽 동일
- phase2-result 한계 "예외 경로 Evidence 없음" 해소 기록

### 3.2 Coupon 서비스 + Store v1 키 + corpus v2

할 것
- `services/coupon/` (Java, Order 패턴 복제): `POST /api/coupons {couponKey, discountAmount}` 201(중복 409) / `GET /api/coupons/by-key/{couponKey}` 200·404 / `POST /api/coupons/{couponKey}/use {orderKey}` 200 `USED`(이미 USED 409, 없음 404). Coupon MySQL(init SQL, ddl-auto none), 고정 시각·batch off·open-in-view off·고정 에러 본문
- Order(Java, 양쪽 동일): `POST /api/orders`에 선택 `couponKey`. **순서: 주문 INSERT → Coupon use → 커밋**. 실패면 400 + 롤백(`transactions: ROLLED_BACK`)
- 매니페스트: `base/{coupon, coupon-mysql, coupon-mysql-networkpolicy}.yaml`(`app=coupon`만 3306), 양쪽 overlay, sidecar, 포트명 `http-`, `poc.evidence` imports + env(`EVIDENCE_SERVICE=coupon`)
- 게이트웨이 표면: `/api/coupons/` 추가(legacy + mirror new 100%). 표면 = `/_evidence/`, `/api/orders`, `/api/coupons`
- **Store v1**: 키 `(runId, replayRequestId, stack, hopPath)`. `exists?runId&requestId&stack&hopPath`, `count?runId&stack[&service&origin]`, export 전체. 중복 last-wins 유지. Phase 2 run(v0)은 `runs/phase2/`로 옮겨 보존, 엔진은 v1만
- **k6 v2**: 요청마다 `exists(stack=new, hopPath="0")` 폴링 + corpus `settle`에 선언된 hopPath를 **양쪽 스택** 모두 폴링(Legacy의 소비 Evidence도 비동기). `settle: [{hop: "0.h1", service: "coupon", origin: "http"}]`
- **run.sh barrier v2**: 두 단계. (1) 스택별 기대 집합 = sent의 `"0"` + 각 요청의 `settle` hop — **corpus에서 결정론적으로 계산**, 도착까지 대기. (2) **자식 홉 폐포**: 도착한 Evidence의 `externalCalls[].childHopPath`·`events.published[].childHopPath`를 읽어 **부모가 실제로 만든 자식 홉**(settle에 없는 `0.h2` 같은 추가 호출 포함)까지 집합에 더하고, 그것들이 도착할 때까지 최대 10초 대기. 새로 도착한 Evidence가 또 자식을 선언하면 반복. 안정화 휴리스틱 없음. 미달이면 누락 `(requestId, hopPath)` 출력, export만 하고 exit 1. — settle만 기다리면 F9의 `0.h2`처럼 **한쪽에만 생긴 추가 호출**의 Evidence가 늦게 와서 누락될 수 있기 때문
- **verify_sameness v2**: 짝 = `(replayRequestId, hopPath)`. 한쪽에만 있는 hop은 "hop 집합 불일치"로 보고하되, 부모 Evidence의 `externalCalls`/`events`에 그 childHopPath가 있으면 **행동 차이(엔진으로)**, 없으면 **Undelivered(internal)**
- **corpus v2** (`corpus/corpus-v2.json`, validate.py v2): 세션 ≥ 10, 요청 ≥ 40, 각 세션 `split: learn|eval`(흐름 유형마다 양쪽에 최소 1개)
  - Order 전용 3 / **Coupon 전용 2**(Order를 안 거침 — Phase 4 스코핑에서 제외될 세션, 필수) / Order+Coupon 3(발급 → 쿠폰 주문 → 조회 → 결제 → 조회; 하나는 USED 쿠폰으로 400 + 롤백) / F7용 지연 세션 1(3.6 — Legacy의 3s 안에는 들어오고 New의 1s는 넘는 2s 지연) / 예비 1
  - 규칙: 세션 간 상태 공유 없음, 키 결정론(`ck-<id>`), `settle`·`expectMissing`·`split`
- `docs/isolation-proof.md`: Coupon DB 스택 간 격리 실측 표

구현 시 확정 (자리)
- Coupon 실패 시 Order 상태코드·본문 / Store 인덱스 재구성 / `settle` 스키마

구현 시 확정 (3.2)
- **OrderService 추출(base, D-3 (A))**: `@Transactional`·비즈니스 로직을 `poc.order.OrderService`로, 컨트롤러는 매핑·DTO·입력 검증만. Service는 `Outcome(kind, OrderView)`를 돌려주고 HTTP 매핑은 컨트롤러가 한다. 응답 본문(`OrderView`)은 트랜잭션 안에서 만든다(open-in-view off — items 지연 로딩). 트랜잭션 이름 `poc.order.OrderService.*`, callTree `Controller → Service → Repository/Client` — 3.5 사다리의 기준 형태. 쿠폰 실패 응답은 컨트롤러 `@ExceptionHandler`가 만들어 callTree에 depth 0 노드로 한 번 더 찍힌다(`OrderController.onCouponFailure`)
- **쿠폰 주문 흐름**: 선택 `couponKey`. 순서 고정 orders·order_items INSERT(`saveAndFlush`) → Coupon `use {orderKey}` → 할인 반영(`amount = max(0, 항목 합계 − discountAmount)`) → 커밋(flush에서 `UPDATE orders`). 결제 charge 금액 = 할인 후 amount. 응답에 `couponKey`(없으면 null)·`discountAmount`(없으면 0). orders 테이블에 `coupon_key`·`discount_amount`
- **Coupon 실패 시 Order 상태코드·본문**(자리 해소): 전부 롤백(`transactions ROLLED_BACK`), 본문 고정 — Coupon 404 → 400 `{"code":"COUPON_NOT_FOUND"}` / 409 → 400 `{"code":"COUPON_ALREADY_USED"}` / 5xx·I/O → 502 `{"code":"COUPON_UNAVAILABLE"}`. `CouponClient`는 주입된 `RestClient.Builder`(전파 인터셉터 부착), `SimpleClientHttpRequestFactory` connect 1s·read 3s, `http://coupon:8080`(같은 ns 직접 호출 — 게이트웨이를 거치지 않아 미러 없음)
- **Coupon API**: `coupons(id, coupon_key UNIQUE, discount_amount, status ISSUED|USED|SETTLED, used_by_order_key, created_at, used_at)`, SETTLED는 3.3 예약, 고정 시각. `use`는 orderKey 기준 멱등 — 같은 (couponKey, orderKey) 재호출은 200(UPDATE 없음), 다른 orderKey면 409(계획의 "이미 USED 409"). F9를 응답 변화 없이 hop 집합(`0.h2`)으로만 잡기 위함. 응답·GET by-key `{couponKey, discountAmount, status, usedByOrderKey}`, 에러 본문 `{"code": ...}` 고정. `EVIDENCE_APP_PACKAGES=poc.coupon`, `EVIDENCE_SERVICE=coupon`
- **검증 레이어 공유**: `poc.evidence`를 공용 Maven 모듈 `services/evidence-collector`(jar, Spring 의존 provided)로 분리 — 코드 내용 변경 없이 위치만. Order·Coupon이 의존성으로 쓴다. Dockerfile 빌드 컨텍스트는 `services/`(모듈 install → 서비스 package). Coupon에 붙이는 데 `poc.evidence` 수정 0줄(RestClient 쪽은 `@ConditionalOnClass`로 Coupon에서 비활성)
- **spill 파일명**: Store v1 키에 맞춰 `<replayRequestId>-<hopPath>-<stack>.json`(Order·Coupon이 같은 스택 hostPath를 공유해도, 같은 서비스를 두 번 불러도 충돌 없음). 이것은 Coupon 부착을 위한 수정이 아니라 Store v1 키 변경에 따른 `poc.evidence` 변경이다
- **Store 인덱스 재구성**(자리 해소): JSONL 한 줄 = `{runId, replayRequestId, stack, hopPath, service, origin, raw}`. 키 `(runId, replayRequestId, stack, hopPath)` last-wins, 컨테이너 재시작 시 파일에서 복원. `exists`는 `hopPath` 필수(기본값 없음), `count`는 `stack`·`service`·`origin` 필터, export는 `(replayRequestId, hopPath, stack)` 순. Coupon Evidence가 Order Evidence를 덮어쓰지 않도록 Store v1은 Coupon과 같은 커밋에 넣었다
- **`settle` 스키마**(자리 해소): 요청의 `settle: [{hop, service, origin}]`, hop 형식 `^0(\.[he][1-9][0-9]*)+$`. 3.2에서는 쿠폰 주문 생성에만(`{hop: "0.h1", service: "coupon", origin: "http"}` 필수), 3.3에서 이벤트 홉(`0.e1`)이 추가된다
- **corpus v2**: 세션 10·요청 46. 세션에 `flow`(order|coupon|order-coupon)·`split`(learn|eval) — 흐름 유형마다 learn·eval 각 1개 이상. Order 전용 3(S001 learn, S002·S003 eval) + F7 지연 1(S009, `idem-slow-*` 키만 예약, 지연 스텁은 3.6) / Coupon 전용 2(S004 learn·S005 eval — Order를 거치지 않음, use의 orderKey는 외부 키 `ok-ext-<요청 id>`) / Order+Coupon 3(S006 learn, S007 eval, S008 learn = USED 쿠폰으로 400 + 롤백) + 예비 1(S010 eval, 할인 > 합계 → amount 0). 키 결정론 `ok-<id>`·`ck-<id>`·`idem-<id>`. validate.py v2: settle 형식·쿠폰 주문 settle 필수, split 커버리지, 세션 간 키 공유 금지, 결제 키는 같은 세션 결제 요청의 id(멱등 재결제 포함). 음성 fixture `corpus/tests/invalid-v2/` 7개
- **k6 v2**: 진입 홉(new, `hopPath=0`) 폴링 후 settle 홉을 legacy·new 양쪽에서 폴링(응답 수신 시각 기준 10초), 타임아웃이면 degraded. summary에 `settleWaitMs`. `CORPUS` env(기본 corpus-v2.json)
- **barrier v2**(`k6/barrier.py`): 1단계 기대 = sent 진입 홉 + corpus settle(최대 30초), 2단계 = 도착 Evidence의 `externalCalls[].childHopPath`(host ∈ `OBSERVED_HOSTS=order,coupon`) + `events.published[].childHopPath` 폐포(최대 10초, 반복). WireMock 홉은 Evidence가 없으므로 제외. 결과 `runs/<runId>/barrier.json`
- **verify_sameness v2**: 짝 = `(replayRequestId, hopPath)`. 선언된 관측 자식 홉이 같은 스택에 없으면 Undelivered(internal, FAIL). 한쪽에만 있는 홉은 그 스택 부모가 선언했고 다른 스택 부모는 선언하지 않았으면 "행동 차이(엔진으로)"(verify는 FAIL로 보지 않음), 아무도 선언하지 않았으면 "hop 집합 불일치 — 선언 없음"(FAIL). 관측 호스트 필터는 barrier와 같다
- **네트워크**: new의 default-deny egress는 이미 같은 ns·verify·DNS를 허용하므로 order→coupon, coupon→coupon-mysql, coupon→Store에 egress 추가가 필요 없었다(실측 동작). 추가한 것은 ingress 두 개 — `coupon-networkpolicy.yaml`(Coupon 8080 ← 같은 ns pod + istio-system; legacy에 egress 제한이 없어 이것이 없으면 legacy가 coupon.new를 부를 수 있다), `coupon-mysql-networkpolicy.yaml`(← `app=coupon`만 3306)
- **게이트웨이 표면**: `/_evidence/`, `/api/orders`, `/api/coupons`(prefix, 끝 슬래시 없음 — `POST /api/coupons`가 매칭되도록)
- **dbstate**: 3.2부터 Coupon DB의 `coupons`(coupon_key, discount_amount, status, used_by_order_key; 시각 제외) 포함, orders에 `coupon_key`·`discount_amount`. DB pod 레이블과 컨테이너 이름(`mysql`/`coupon-mysql`)으로 대상 지정
- **run.sh v2**: preflight 인증서에 legacy·new Coupon 추가, reset에 `coupon-mysql` rollout restart + Coupon readiness(없는 쿠폰 조회 404), run-meta에 Coupon 이미지
- **이미지**: 단계별 태그 `order-app:phase3.2-base`, `coupon-app:phase3.2-base`, `evidence-store:phase3.2`. 3.3이 끝난 base가 사다리의 Legacy 고정 이미지. 계획의 `phase3-base`는 "현재 base"의 뜻
- Phase 2 runs(v0)는 `runs/phase2/`로 옮겼다. 엔진의 입력 계약은 v0도 읽지만 Phase 3 run은 v1만

끝난 기준
- Coupon 양쪽 배포, 격리 실측(교차 차단·대조군 성공)
- corpus v2 A/A 3회(VU=3) diff ∅ — 스택당 Evidence 수 = 기대 집합 크기, hop 집합 동일, Undelivered 0
- 쿠폰 주문: Order `externalCalls`에 use(`0.h1`) + 결제 시 charge, Coupon Evidence `hopPath: "0.h1"`·`dbAccess`에 UPDATE·`transactions: COMMITTED`
- 실패 경로: USED 쿠폰 → Order 400, `ROLLED_BACK`, dbstate에 주문 없음(양쪽 동일)

### 3.3 Kafka — 이벤트 축

할 것
- 스택별 Kafka 1브로커(KRaft, `apache/kafka`), `base/kafka.yaml`, 포트명 `tcp-kafka`, NetworkPolicy(같은 ns의 order·coupon만 9092). 토픽 `order.paid`, partition 1, producer `retries=0`
- Order: 결제 커밋 후 `OrderPaid{orderKey, amount, couponKey?}` 발행 — `@TransactionalEventListener(AFTER_COMMIT)` → `KafkaTemplate.send(...).get(5s)`. ProducerInterceptor가 재생 헤더 + 자식 hopPath(`0.e1`)를 레코드 헤더로. `events.published[]`에 seq·ack
- Coupon: `order.paid` 소비 → 쿠폰 `USED → SETTLED`(UPDATE). RecordInterceptor가 헤더 → ReplayContext 설정·정리, record-level 리스너, `DefaultErrorHandler(FixedBackOff(0,0))` + DLQ `order.paid.dlq`. Evidence `origin: kafka`, `hopPath: "0.e1"`, `event{...}`, `dbAccess`, `transactions`, `consumeOutcome`
- corpus: 결제 요청에 `settle: [{hop: "0.e1", service: "coupon", origin: "kafka"}]` (쿠폰 주문일 때)
- run.sh: reset에 토픽 비우기, dbstate에 coupons 포함

구현 시 확정 (자리)
- 자원 부족 시 대안: 브로커 1개 공유 + 스택별 토픽 접두사 — 이 경우 Kafka는 스택 축 격리의 예외로 isolation-proof에 명시 / 토픽 리셋 방식

구현 시 확정 (3.3)
- **커밋 규칙**: A/A 게이트 run은 커밋된 코드로 — 코드를 먼저 커밋하고 run, 보고서·로그는 마지막 별도 커밋. run-meta `git.dirty: false`(p33-1..3 확인). 실행 로그는 run 중 레포 밖에 쓰고 나중에 복사(레포 안에 쓰면 그 자체로 dirty)
- **브로커**: 스택별 `apache/kafka:4.2.1`(클라이언트 kafka-clients 4.2.1과 같은 버전) KRaft combined 1노드, `CLUSTER_ID` 고정, 스토리지 emptyDir, `KAFKA_HEAP_OPTS=-Xmx256m -Xms128m`, requests 256Mi / limits 768Mi, 포트명 `tcp-kafka`, advertised `PLAINTEXT://kafka:9092`(같은 ns Service 이름), offsets topic replication 1·partition 1, group initial rebalance delay 0. sidecar 주입(2/2) — Kafka는 client-first라 PERMISSIVE mTLS와 충돌 없음. 이미지는 태그(`apache/kafka:4.2.1`) + IfNotPresent로 참조 — Docker Hub index digest로 참조하면 kind load한 arm64 이미지와 digest가 달라 노드가 레지스트리에서 받으려 한다. 실제 imageRef는 run-meta
- **토픽**: `auto.create.topics.enable=false`. `order.paid`·`order.paid.dlq`(partition 1)는 run.sh가 리셋 뒤에 만든다(앱의 KafkaAdmin에 기대지 않음)
- **토픽 리셋 방식**(자리 해소): Kafka도 `rollout restart`(emptyDir — 로그·오프셋·컨슈머 그룹 전부 초기화) → 브로커 준비(`kafka-topics.sh --list` 성공) → 토픽 2개 생성 → 양쪽 `coupon-settlement` 그룹이 `order.paid` partition을 할당받았는지 `kafka-consumer-groups.sh --describe`(CONSUMER-ID ≠ "-")로 확인한 뒤 k6. 고정 대기 없음. Coupon consumer `metadata.max.age.ms=2000`(토픽 생성을 빨리 알아채도록). 리셋 소요 46~48s를 run-meta `resetSeconds`에 기록
- **자원 부족 시 대안**(자리 해소): 불필요 — 12GiB에서 스택별 브로커로 노드 사용 60.5%(available 약 4.1GiB). 공유 브로커로 후퇴하지 않았다
- **NetworkPolicy**: 9092 ← 같은 ns `app in (order, coupon)`만(스택 축·서비스 축). isolation-proof "Kafka 격리"
- **발행(Order)**: `OrderPaid`는 결제가 처음 PAID로 바뀔 때만(`ApplicationEventPublisher`), `OrderEventPublisher`의 `@TransactionalEventListener(AFTER_COMMIT)`에서 `KafkaTemplate.send(order.paid, orderKey, json).get(5s)`. 페이로드 `{orderKey, amount, couponKey}`(앱 JsonMapper 빈). producer `retries=0`, `enable.idempotence=false`, `acks=all`, `delivery.timeout.ms=5000`, `request.timeout.ms=4000`, `max.block.ms=5000`. 발행 실패는 요청 결과에 영향 없음(로그, 응답 200) — 응답 축을 깨끗하게 두고 이벤트 축만 시험하기 위해
- **실측 타임라인**: 결제 `… COMMIT_BEGIN(4) < UPDATE orders(5) < PUBLISH order.paid(6) < COMMITTED(7)` — 3.1 실측(동기화 afterCommit이 리스너 afterCommit보다 먼저)대로 AFTER_COMMIT 발행은 COMMIT_BEGIN과 COMMITTED **사이** seq. callTree에 `OrderEventPublisher.onOrderPaid`가 `OrderService.pay` 아래(depth 2)로 찍힌다
- **발행 수집(poc.evidence)**: `EvidenceProducerInterceptor`(producer `interceptor.classes`, Boot `DefaultKafkaProducerFactoryCustomizer`)의 `onSend`(호출 스레드)가 자식 hopPath(`<hop>.e<n>`)·재생 헤더 4개(있으면 교체 — DLQ 재발행도 그 소비 홉의 자식이 된다)·발행 기록(seq, topic, key, payloadHash, payload, childHopPath). `KafkaTemplate.send*()` advisor가 반환 future를 그 기록에 붙이고, **ack는 Evidence를 닫을 때(호출 스레드) future 상태로** 정한다(앱이 get()으로 기다린 뒤라 이미 끝나 있음, 안 끝났으면 failed). `onAcknowledgement`는 쓰지 않는다(I/O 스레드)
- **소비(Coupon)**: `@KafkaListener` record 단위, group `coupon-settlement`, `auto.offset.reset=earliest`. couponKey가 있고 그 주문이 쓴 USED 쿠폰이면 SETTLED(flush UPDATE), 없으면 no-op(Evidence는 남고 dbAccess 빈 배열·transactions 없음). `DefaultErrorHandler(DeadLetterPublishingRecoverer → order.paid.dlq 같은 partition, FixedBackOff(0, 0))` — Boot가 CommonErrorHandler 빈을 컨테이너에 붙인다
- **소비 수집(poc.evidence)**: `RecordInterceptor` 빈(Boot가 컨테이너에 붙임)이 레코드 헤더의 재생 헤더 4개로 consumer 스레드에 ReplayContext를 연다(없으면 Evidence 없음). **확정 시점은 다음 레코드의 intercept 또는 `clearThreadState` 중 먼저 오는 쪽** — 에러 핸들러의 DLQ 발행까지 그 소비 홉에 들어간다(실측: `events.published`에 `order.paid.dlq`, childHopPath `0.e1.e1`, ack ok). `consumeOutcome`: success → ok, failure → failed, `error{type, where}`는 래핑(ListenerExecutionFailedException) 벗긴 원인. traceparent 등 다른 헤더는 Evidence에 넣지 않는다
- **스키마 v1 추가**(strict 유지): `events.published[].payload`, `event.payload`(32KB 상한, 초과 시 null), `consumeOutcome`(origin=kafka일 때 필수, http면 없음). 3.1·3.2 run Evidence 418건이 그대로 통과(추가만). 예시 = 실측 결제·소비 Evidence
- **barrier·verify**: `events.published[].childHopPath` 폐포는 관측 토픽 `OBSERVED_TOPICS=order.paid`만(DLQ는 소비자가 없어 Evidence가 오지 않는다). verify의 Undelivered(internal)도 같은 필터(`--observed-topics`). diff_v0는 origin=kafka 홉을 response 대신 event 축(topic·key·consumeOutcome·payload)으로 비교
- **corpus v2 갱신**: 처음 PAID가 되는 모든 `/pay`에 settle `{hop: "0.e1", service: "coupon", origin: "kafka"}`(7건), 같은 주문의 두 번째 이후 `/pay`에는 금지 — validate.py 규칙과 음성 fixture 2개. 세션 구성·split 그대로. 기대 집합 = 진입 46 + http settle 5 + kafka settle 7 = 58
- **소비 실패 유도**: 코드 변경 없이 — 실제 요청 하나를 보내고, 같은 재생 헤더(hop `0.e1`)를 단 해석 불가 레코드를 `kafka-console-producer`로 양쪽 브로커에 넣었다. 재시도 0은 Store의 append-only 기록에서 소비 Evidence POST가 스택당 1회인 것으로 확인
- **이미지**: `order-app:phase3.3-base`, `coupon-app:phase3.3-base` — 3.5 사다리의 Legacy 고정 이미지(run-meta에 태그·imageRef)

끝난 기준
- corpus v2 A/A 3회 diff ∅ — `events.published` 1건(`ack: ok`, 호출 스레드에서 기록), **publish seq > COMMIT_BEGIN seq**(타임라인), 소비 Evidence 양쪽 존재, 쿠폰 SETTLED 양쪽 동일. 3.1에서 실측한 콜백 순서와 일치함을 기록
- Kafka 격리 실측: 교차 스택 9092 차단
- 소비 실패 경로(임시 유도) → DLQ 1건, `consumeOutcome: failed`, 재시도 0

### 3.4 Normalization v1 + 판정 엔진 v1 + Rule + Human Review

할 것 (전부 `engine/`, 클러스터 없이)
- `engine/normalize.py`: response canonical(+규칙 파일 필드 선언) / dbAccess 파생 `{type, tables, fingerprint}` + 요청별 `type×table count` + **쓰기 집합과 읽기 횟수 분리** / externalCalls / events / transactions / callTree(`class.method` 시퀀스, `*Kt`·람다 제거)
- `engine/verdict.py --run runs/<runId>`:
  - 축별 SAME/DIFF → DIFF면 `engine/rules/`: **Contract 규칙**(쓰기 집합 동일, `transactions` outcome 동일, 같은 Idempotency-Key 게이트웨이 호출 ≤ 1(세션 단위), `publish.seq > COMMIT_BEGIN.seq`, hop 집합 동일, 선언된 `maxSelects` 이내, 쿠폰 상태 전이 순서) → Contract Violation / **Improvement 규칙**(사전 승인) / 아니면 Uncertain
  - 집계: dbstate 테이블별 count·sum·hash + run 불변식
  - Undelivered·degraded는 지표
  - 출력 `runs/<runId>/verdict.json` + 표
- `engine/review.py --run X --split learn`: **learn 세션의 Uncertain만** 보여줌 → 사람이 `same|improvement|violation` 라벨 + 매칭 조건(축·필드 경로·값 패턴) → `rules/learned/*.yaml`(run id·작성자·근거 포함) → 재판정. eval 세션은 보여주지 않는다
- 규칙 스키마: 요청 단위(`scope: request`) / 세션 단위(`scope: session`) / run 단위(`scope: run`)

구현 시 확정 (자리)
- 규칙 YAML 스키마 / fingerprint 정의 / 불변식 목록 / `maxSelects` 선언 위치(`rules/contract.yaml`의 엔드포인트별)

구현 시 확정 (3.4)
- **구조**: `engine/normalize.py`(정규형), `engine/ruleset.py`(규칙 로더·매처), `engine/verdict.py`(판정·arm), `engine/review.py`(비대화형 라벨), `engine/rules/{contract.yaml, improvement.yaml, learned/}`, `engine/tests/`(pytest, fixture `p33-mini`). 앱 코드 import 없음(D12) — 입력은 Evidence 스키마와 run 파일뿐. 의존성 `PyYAML`·`pytest`(requirements.txt)
- **엔드포인트 식별**: `contract.yaml`의 endpoints 표 — HTTP는 method + path 정규식(`order.create/get/pay/cancel`, `coupon.create/get/use`), Kafka 소비 홉은 topic(`order.paid` → `consume.order.paid`). 어느 것에도 안 맞으면 `unknown`
- **pair**: `(replayRequestId, hopPath)`가 양쪽에 있고 rid가 k6 sent에 있는 것. 한쪽에만 있는 홉은 pair가 아니라 부모 pair의 `hop_set_equal` 위반으로 드러난다. Undelivered(진입 홉 "0" 부재)·degraded는 summary 지표
- **Normalization v1**: response = status(별도 축) + content-type + body(JSON parse → **키 이름 `id` 제거(모든 깊이, DB auto id — Phase 2 diff_v0와 같은 유일한 제외 필드)** → canonical). VU=3에서 auto id가 세션 간 교차하므로(p33-1 실측 8 pair) 이 제외 없이는 A/A가 SAME이 될 수 없다. event payload도 같은 처리. SQL fingerprint = 소문자·공백 축약·Hibernate alias(`[a-z]+\d+_\d+` → `t`), `?` 유지. writeSet = (type, table) 정렬 multiset(INSERT/UPDATE/DELETE), readCount = SELECT 수, readFingerprints = 순서 유지 목록. callTree = depth 0마다 새 루트, 루트별 `class.method` 시퀀스, `$$…`(CGLIB·Lambda)·`$lambda…`·`$DefaultImpls`·클래스명 `Kt` 접미사·`access$`/`lambda$` 메서드 제거
- **축의 두 층**: 기능 = response.status·content-type·body, writeSet, externalCalls(method·host·path·status·requestBodyHash, 순서 유지), events.published(topic·key·payload·ack)·event(소비), transactions (phase, outcome) 순서열, error, consumeOutcome, hop 집합. 실행 특성 = readCount·readFingerprints, callTree, transactions name, externalCalls.responseBodyHash
- **built-in `response_body_compatible`**(계획 목록에 추가): 응답 body의 기존 필드 값 변경·삭제, content-type 변경 → 규칙(improvement·learned)이 설명하지 않으면 CV. **필드 추가**는 CV가 아니라 Uncertain(규칙 대상). events payload도 같음 — 필드 추가는 `events.payloadFieldsAdded`(규칙 대상), 값 변경·삭제는 `events_equal` 위반. "amount 변경 → CV(응답)"이 이 검사로 나온다
- **status 불일치**는 항상 CV(규칙 예외 없음). 규칙은 `RULE_COVERABLE` diffKind(응답·payload 필드, dbRead·callTree·transactions name)에만 적용 — 기능 축 위반(writeSet·externalCalls·ack·outcome·error·consumeOutcome·hop·타임라인·세션 규칙)은 규칙으로 덮을 수 없다. `externalCalls.responseHashChanged`는 실행 특성이지만 matcher가 없어 Uncertain으로만 남는다(라벨 불가 — 계약 판단 필요)
- **diff 항목(diffKind)**: `response.addedFields{fields}` / `removedFields{fields}` / `valueChanged{path,from,to}`(리프 경로 `a.b[0].c`) / `events.payloadFieldsAdded` / `dbRead.countDelta{from,to}`(횟수 다르면) / `dbRead.fingerprintReplaced{from,to}`(횟수 같으면 multiset 차, 집합이 같고 순서만 다르면 전체 순서열) / `callTree.sequenceReplaced{from,to}`(루트별 시퀀스 목록) / `transactions.nameChanged{from,to}`
- **uid** = sha256(canonical{endpoint, axis, diffKind, detail})[:12] — rid·session이 들어가지 않으므로 같은 유형 diff는 learn·eval에서 같은 uid
- **세션·run 검사**: `gateway_calls_per_idem_key_le_1` — 세션 안 레코드의 요청 헤더 `idempotency-key`별로 externalCalls(host `wiremock`, path `/gateway/charge`) 수 합, 스택별 ≤ 1이고 양쪽 같아야 함, 위반은 그 키를 가진 pair(어느 스택이든)에 붙인다. `coupon_transition_order` — 세션의 corpus 요청 순서·hop 순으로, `consume.order.paid` 홉이 `coupons` UPDATE를 했으면 그 payload couponKey의 `coupon.use` 200이 앞서 있어야 함(스택별). `publish_after_commit_begin` — new 홉에 COMMIT_BEGIN이 있으면 모든 publish.seq > 첫 COMMIT_BEGIN.seq. `dbstate_equal` — `dbstate-{stack}.json` 테이블별 count·sum·sha256 동일(run 단위, runChecks)
- **`maxSelects`**: 선언 단위 = endpoint id, `contract.yaml` `checks.max_selects.endpoints: {<id>: n}`, 기본 선언 없음. new readCount > n → CV, legacy가 넘으면 그 pair에 warning(선언 확인 필요)
- **규칙 YAML**: `{id, scope(request|session|run), verdict(same|improvement|violation), reason, provenance{author,date,runId,split,sessions[]}, match{endpoint(id|*), diffKind, 파라미터}}`. 파일은 `rules:` 목록 또는 규칙 하나. match에 `replayRequestId`·`sessionId`·`runId` → 로더 거부. 허용 외 키·diffKind → 거부. id 중복 거부. 임의 식 없음 — `fields`는 부분집합, `valueChanged`의 from/to는 정규식 fullmatch(null은 "null"), 나머지는 값 동일. 3.4의 매칭은 요청 단위 항목에만 적용(scope는 기록용 — session·run 규칙 매칭은 필요해지면 확장). `improvement.yaml`은 형식 예시(주석)만, F6 규칙은 3.6
- **판정 결과 이름**: `SAME` / `IMPROVEMENT` / `UNCERTAIN` / `CONTRACT_VIOLATION`(arm C), `SAME` / `DIFF`(B0·B1). learned `violation` 규칙이 맞으면 CV
- **arm**: B0 = 휘발 필드(timing·capturedAt·runId·version·stack, 요청 헤더 x-run-id)와 body의 auto `id`(그리고 id를 포함한 bodyHash)만 뺀 레코드 원문 canonical 동일성. B1 = Normalization 후 response status·body + dbAccess fingerprint 순서열·SELECT 수. C = 전체. 출력 `verdict.json`(C) / `verdict-B0.json`·`verdict-B1.json`
- **결정론**: verdict.json은 `sort_keys`·시각 없음·pair 정렬, `engine.version`(`engine-v1 (phase3.4)`)·`engine.rules`(규칙 파일별 sha256). 같은 입력·규칙 → 바이트 동일(테스트)
- **review.py**: `list --split learn`만 허용(eval은 표시 안 함), uid별로 묶어 건수·위치·제안 matcher. `label --uid --as --reason [--match-file]` → `rules/learned/<uid>.yaml`, id `learned-<uid>`, provenance 자동(author = `REVIEW_AUTHOR` 또는 git user.name, date, runId, split learn, sessions = 그 uid가 나온 learn 세션). eval 세션에만 있는 uid·matcher 없는 diffKind는 거부(exit 2)
- **fixture `p33-mini`**: runs/p33-1의 S001·S006·S008(learn) + **S007(eval)** — "learn 라벨이 eval Uncertain을 지움"을 보이려면 같은 유형의 eval 세션이 필요(S006 order.get ↔ S007 order.get). 입력 계약(runId == 디렉터리 이름) 때문에 runId·x-run-id를 `p33-mini`로 치환, corpus 사본(`corpus.json`, verdict는 run-meta 경로보다 먼저 사용), dbstate는 run 전체 값 그대로. 생성 스크립트 `engine/tests/make_fixture.py`

끝난 기준
- A/A run(3.3 산출물): 전 요청 SAME, Uncertain 0, 집계 일치
- 변조 시험: amount 변경 → CV(응답) / INSERT 삭제 → CV(쓰기 집합) / 응답 필드 추가 → Uncertain → Improvement 규칙 후 Improvement / 게이트웨이 2회 호출 → CV(세션 규칙) / publish seq를 commit 앞으로 → CV(타임라인) / Coupon 호출 복제(`0.h2` 추가) → CV(hop 집합) / SELECT 1건 추가 → Uncertain(예산 미선언) 또는 CV(예산 선언)
- review.py로 learn 세션 Uncertain 1건 라벨 → 규칙 → 같은 유형의 **eval 세션** Uncertain이 사라짐

### 3.5 New v1 사다리 — Order 점진 Kotlin 전환

할 것 (각 단계 = commit 1 + 이미지 1 + run 3회 + verdict + 보고서)
- Gradle Kotlin 플러그인(`kotlin-jvm`·`kotlin-spring`·`kotlin-jpa`), 혼합 빌드. Legacy = `phase3-base` 고정
- v1.1 `PaymentGatewayClient` / v1.2 엔티티·리포지토리 / v1.3 `OrderService` / v1.4 `OrderController`·나머지
- 각 단계: base A/A(이미 ∅, 재사용) → `run.sh --run-id p35-v1.x --iterations 3 --vus 3` → verify_sameness → verdict → learn 세션 Uncertain은 review → 규칙 → eval 세션에서 재판정 → 4분류·규칙 수를 `docs/phase3-result.md`에 누적. diff는 코드로 원인 설명. 재작성 버그면 기록하고 다음 단계는 고친 버전 위에서
- 변형 자체의 A/A(v1.x를 양쪽에)는 diff 원인이 비결정으로 의심될 때만(D13 VU=1 규칙과 같은 자리)
- Phase 4 입력: 단계별 commit·이미지·runs 경로 표

구현 시 확정 (자리): 혼합 빌드 / Kotlin 버전

끝난 기준
- v1.1~v1.4 각 3 run, Undelivered 0, degraded 0, **모든 diff가 4분류 중 하나로 설명됨**(0건이어도 통과)
- `poc.evidence` 수정 0줄로 Kotlin New에 부착(이식성)
- 결과 표: 단계 × (SAME/Improvement/CV/Uncertain, learn 리뷰 건수, 생성 규칙 수, eval Uncertain 전후)

### 3.6 결함 카탈로그 v1 + New v2

`docs/fault-catalog.md`. v1.4 위에 1건씩 commit·이미지. **기대 판정과 관측 축을 미리 적는다**(관측 매트릭스는 3.7).

| id | 변경 | 종류 | 기대 판정 | 보이는 축 |
|---|---|---|---|---|
| F1 | 같은 Idempotency-Key 재결제 시 게이트웨이 재호출 | 진짜 결함 | CV (세션 규칙: 호출 ≤ 1) | 외부 호출 |
| F2 | `order_items` INSERT 누락 | 진짜 결함 | CV (쓰기 집합·집계) | DB 기능 계약 |
| F3 | `OrderPaid`를 `@EventListener`(커밋 전)로 발행 | 진짜 결함 | CV (`publish.seq < COMMIT_BEGIN.seq`) | 타임라인 |
| F4 | 쿠폰 use 실패 시 롤백 누락(주문 행이 남음) | 진짜 결함 | CV (`transactions` 불일치 + dbstate) | 트랜잭션·집계 |
| F5 | 조회 2쿼리 → 1쿼리 (쓰기 집합·최종 상태 동일) | 정상 리팩터링 | **Uncertain → 리뷰 → Improvement 규칙** | DB 실행 특성 |
| F6 | 응답에 `itemCount` 추가 | 승인된 개선 | Improvement (사전 규칙) | 응답 |
| F7 | 게이트웨이 timeout **3s→1s** (설정만, 코드 변경 없음) | 설정 변경 결함 | 정상 세션 SAME; 지연 세션(WireMock `fixedDelayMilliseconds` 2s, 특정 Idempotency-Key만)에서 Legacy 성공·New 타임아웃 → CV(응답 status + `externalCalls.status`) | 외부 호출·응답 |
| F8 | N+1 (items fetch 전략 변경) | 성능 계약 | `maxSelects` 선언 시 CV, 미선언 시 Uncertain — **둘 다 실험** | DB 실행 특성 |
| F9 | Coupon `use`를 두 번 호출 | 진짜 결함 | CV (hop 집합: `0.h2` 출현) | 외부 호출·hop |

끝난 기준
- 결함별 3 run, 기대 판정 = 실제 판정 표(**결함 탐지율**), 정상 경로 오탐 0, **오판정률**(learn에서 만든 규칙이 F를 SAME·Improvement로 가린 건수) 0
- 각 결함 commit의 코드 diff가 클래스 1~2개(Phase 4 입력)

### 3.7 사다리 첫 측정 — B0 / B1 / C + 평가 지표

할 것
- 같은 runs를 엔진 설정만 바꿔 재판정: **B0** exact(정규화 없음) / **B1** Normalization만(응답 canonical + SQL fingerprint·횟수; 사이드이펙트 축·규칙 없음) / **C** 전체(4축 + 타임라인 + 집계 + 규칙)
- **관측 매트릭스**(미리 선언): F8은 B1에서도 보인다(SQL 횟수는 B1 축). C만 잡는 것은 F1·F3·F4·F9(외부 호출·타임라인·트랜잭션·hop). F2는 B1(쓰기 문장)·C 모두. F5·F6·F7은 분류의 문제(B1은 DIFF까지만, C는 Improvement/CV로 가름)
- 지표 4개: **결함 탐지율** / **수동 검토 감소율**(전체 비교 중 Uncertain 비율, 규칙 전후, **eval 세션 기준**) / **오판정률**(F를 SAME·Improvement로 판정한 비율) / **Rule 재사용 효과**(learn에서 만든 규칙이 eval 세션·v1.3+·F 변형에서 줄인 Uncertain)

끝난 기준
- 표: arm × 변형 → diff·Uncertain·탐지율·오탐. 매트릭스와 실제가 일치. 지표 4개가 eval 세션 기준으로 보고됨

### 3.8 (선택) New v3 — 런타임 교체
- v3a JDK만 / v3b Spring Boot 4(Jackson 3·Hibernate 7.1). 기대: v3a ∅, v3b 형식 차이 다수 → 규칙 라운드 수. 일정이 밀리면 Phase 4로 — 제외해도 Phase 3 결론에 영향 없음

### Phase 3 종료 조건
3.1~3.7 완료 + `docs/phase3-result.md`(스키마 v1 확정, 사다리 결과 표, 결함 탐지율·오판정률·검토 감소율·Rule 재사용, 한계) + `git tag phase3-done`. Phase 4 입력: 단계별 commit·이미지·runs, corpus v2(split 포함), Kotlin v1.4 = 새 기준선.

---

## 6. 레포 구조 (Phase 3에서 추가)

```
services/order/           Kotlin 혼합 빌드. 수집기는 poc.evidence(CallTreeAspect, ReplayPropagatingInterceptor, EvidenceTransactionListener, private ObjectMapper)
services/coupon/          Java, poc.evidence 재사용
deploy/k8s/base/          coupon.yaml, coupon-mysql.yaml, coupon-mysql-networkpolicy.yaml, kafka.yaml, kafka-networkpolicy.yaml
corpus/                   corpus-v2.json(settle·split), schema v2, validate.py
k6/                       run.js v2(hopPath·settle 양쪽 폴링), run.sh v2(Kafka 리셋·기대 집합 barrier·dbstate·wiremock export), dbstate-export.sh
engine/                   normalize.py, verdict.py, review.py, rules/{contract,improvement}.yaml, rules/learned/
runs/phase2/              v0 산출물 보존
docs/                     evidence-schema-v1.json, fault-catalog.md, phase3-result.md, references/industry-cases-phase3.md
```

## 7. 추가 결정 필요 (구현 중 정하지 말고 질문)

- `error` 경로 상태코드 획득 방법
- Kafka 자원 부족 시 공유 브로커 + 토픽 접두사 허용 여부
- `maxSelects` 선언 단위(엔드포인트 vs 요청 유형)
- 리뷰 라벨 매칭 조건의 표현 범위
- Framework < 6.1일 때 폴백(Hibernate Interceptor) 채택 여부

## 8. 산업 사례 반영 (→ `docs/references/industry-cases-phase3.md`)

| 사례 | 요지 | 반영 위치 |
|---|---|---|
| Uber — Shifting E2E Testing Left (BITS, 2024) | 테넌시 식별자를 baggage로 전파해 운영 서비스에 테스트 트래픽; Jaeger 트레이스로 "테스트 → 서비스·엔드포인트" 인덱스를 만들어 변경 시 돌릴 테스트 선택; placebo run; 설정 변경이 incident 30%; 71% 감소 | 재생 헤더·hopPath 전파(3.1·3.2) / D14 근거 / A/A ≙ placebo / F7 |
| LinkedIn — inCapacity (실시간 콜그래프) | request ID로 트레이스를 묶어 15분마다 집계; 용도에 impact analysis 명시; 두 구간 콜그래프 비교로 근본 원인 | D14 근거 / callTree Legacy·New 구조 비교(3.4) |
| 토스 — Gateway (2023) | Passport 전파; Dynamic Security가 재전송(replay) 차단 → 운영 재현은 게이트웨이 인증 **뒤**에서 미러 | 전파 패턴 / architecture "운영 적용" 절 |
| 우아한형제들 — WireMock (2024) | `fixedDelayMilliseconds`, `priority` 기본 stub, `equalToJson` 본문 매칭 | F7 지연 세션 / journal 본문 비교(3.1·3.6) |
| 카카오페이손보 — AOP 섀도우 (2026) | 프로세스 안 섀도우의 한계(조회만·같은 런타임·메서드마다 수정); 정규화 규칙은 경험적으로 늘어남 | 대비 서술 / `@Around`·ThreadLocal / 규칙 축적 근거 |
| Twitter — Diffy (2015) | primary/secondary/candidate로 잡음을 통계 추정; 응답만; "similar" | A/A = secondary, 설계로 잡음 0 → "same" |
| Spring Framework 문서 | `afterCommit`에서 트랜잭션 리소스가 활성으로 보일 수 있음; `TransactionExecutionListener`(6.1) | D16 타임라인 설계 |
| AWS — Transactional Outbox | 커밋과 발행 원자성 문제의 표준 해법 | 범위 밖 명시, 동기 ack로 관측만 |

## 9. 검토 반영 기록 (v1 → v2)

| 지적 | 판단 | v2 |
|---|---|---|
| ① 필터에서 트랜잭션 동기화 등록 불가 | 동의(오류) | `TransactionExecutionListener` → `transactions[]` |
| ② `inTx` 불리언 불신뢰, send 비동기 | 동의(오류) | 단일 seq 타임라인 + 동기 send ack; F3 = seq 비교 |
| ③ 키가 반복 호출을 덮어씀 | 동의(오류, 핵심) | 키에 `hopPath`(종류별 순번), service·origin은 필드; F9 추가 |
| ④ A/A 게이트가 A/B와 충돌 | 동의(문구) | A/A = 3.1~3.4·base, A/B = "전부 설명됨" |
| ⑤ SQL 횟수 ≠ 자동 CV | 동의 | DB 계약 두 층, F5·F8 기대 수정, `maxSelects` |
| ⑥ Order·Coupon 별개 DB | 동의 | 처리 순서 고정, 보상 누락은 범위 밖 명시 |
| ⑦ 안정화 대기는 증거 아님 | 동의 + 보완 | `settle` 양쪽 폴링(Legacy 소비도 비동기), 기대 집합 corpus에서 계산 |
| ⑧ 자체 JSON writer 비추천 | 동의 + 대안 | writer 삭제, **private 고정 ObjectMapper**(앱 빈 공유 금지) |
| Rule 학습/평가 분리 | 강하게 동의 + 방법 수정 | 결정론이라 run 홀드아웃 불가 → **세션(`split`)·변형 홀드아웃**, 지표 4개, 관측 매트릭스(F8은 B1에서도) |
| 3.8 | 동의 | 선택 유지, 밀리면 제외 |
| **2차** ACK 기록 스레드 불명확, 콜백 순서 가정 | 동의 | ack는 `get()` 후 호출 스레드에서 기록; `COMMIT_BEGIN`을 타임라인에 추가해 F3 판정을 **콜백 순서와 무관**하게; 순서는 3.1에서 실측 |
| **2차** settle 밖 추가 홉(F9 `0.h2`) 누락 가능 | 동의 | barrier 2단계: settle 집합 → **부모가 선언한 childHopPath 폐포**까지 대기 |
| **2차** F7 정답(1s→3s는 Improvement) | 동의 | **3s→1s**로 뒤집어 설정 변경 결함으로. Improvement는 F6이 담당 |

## 10. decision-log 항목 (그대로 추가)

```
### D15. Evidence 키에 hopPath — 같은 서비스 반복 호출을 구분한다 (2026-10-13)
결정: 키 = (runId, replayRequestId, stack, hopPath). service·origin은 필드. hopPath는 진입 "0", 홉 안 n번째 HTTP 호출 "<부모>.h<n>", n번째 이벤트 소비 "<부모>.e<n>" — 종류별 순번(요청 전역 seq 아님).
근거: (…, service, origin) 키는 한 요청이 같은 서비스를 두 번 부르면 last-wins로 첫 기록을 덮어, 중복 사이드이펙트 결함(F1·F9)을 숨긴다. 순번을 종류별로 두는 이유는 쿼리 수가 바뀌어도 짝이 유지되어야 하기 때문.
한계: hopPath는 호출 순서가 결정론적일 때만 안정. 요청 스레드 안 순차 호출만 다룬다.

### D16. 요청 타임라인은 단일 seq, 트랜잭션은 TransactionExecutionListener (2026-10-13)
결정: SQL·외부 호출·이벤트 발행·트랜잭션 단계가 요청 버퍼의 한 카운터로 번호를 받는다. 트랜잭션은 Spring TransactionExecutionListener(6.1+)로 수집해 beforeCommit에서 COMMIT_BEGIN, 완료 시 COMMITTED/ROLLED_BACK/COMMIT_FAILED를 transactions[{seq,name,phase,outcome}]에 기록. 이벤트 발행은 동기이며 ack는 get()이 돌아온 호출 스레드에서 기록(onAcknowledgement는 I/O 스레드라 컨텍스트 없음). "커밋 전 발행"은 publish.seq < 그 트랜잭션의 COMMIT_BEGIN.seq로 판정.
근거: 필터 시점엔 트랜잭션이 없어 동기화 등록이 불가. AFTER_COMMIT 콜백 안에서도 트랜잭션 리소스가 활성으로 보일 수 있어 불리언 판정은 오탐. COMMIT_BEGIN 기준이면 afterCommit 리스너와 AFTER_COMMIT 이벤트 리스너의 호출 순서를 가정하지 않아도 된다. 타임라인이면 롤백 시나리오 없이도 결정론적으로 판정된다.
대안: Hibernate Interceptor.afterTransactionCompletion(Framework < 6.1 폴백). Outbox는 범위 밖.

### D17. New v1은 Order의 점진 Kotlin 전환 사다리 (2026-10-13)
결정: v1.1 클라이언트 → v1.2 엔티티·리포지토리 → v1.3 서비스 → v1.4 컨트롤러. 같은 Boot·JDK, FQCN·API 유지, kotlin-spring·kotlin-jpa 필수, 엔티티 data class 금지, 결함을 섞지 않음. 단계마다 commit·이미지 1개. A/A 게이트는 인프라·엔진 단계와 base에만, A/B 단계의 기준은 "모든 diff가 4분류로 설명됨"(0건 포함).
근거: 교체(새 코드베이스)라는 주제 적합성, 응답엔 없고 DB·트랜잭션에만 보이는 차이가 나오는 영역, 같은 런타임이라 귀속이 깔끔, 작은 commit이 Phase 4 스코핑 입력. JDK만은 차이가 거의 없고 Boot 4는 빌드 변경이라 전역 영향 — v3(선택)로.

### D18. DB 계약은 두 층 — 기능 계약과 실행 특성 (2026-10-13)
결정: 쓰기 문장 집합·최종 DB 상태·불변식 위반은 Contract Violation. 읽기 횟수·순서 차이는 기본 Uncertain(사람 → 규칙), 엔드포인트별 maxSelects가 선언된 경우에만 초과 시 Contract Violation.
근거: 쿼리 통합(F5)과 N+1(F8)이 같은 "SELECT 수 변화"인데 기대가 달랐던 모순. "판정은 선언된 해상도" 원칙의 적용.

### D19. Kafka는 스택별 브로커, 내부 Evidence 완료는 settle 선언으로 (2026-10-13)
결정: 스택별 1브로커·NetworkPolicy·partition 1·재시도 0·DLQ. 내부 Evidence(서비스 간 호출·소비)의 완료는 corpus의 settle 선언을 k6가 양쪽 스택에서 폴링해 확인하고, barrier 기대 집합은 corpus에서 계산한 뒤 도착한 Evidence가 선언한 childHopPath 폐포까지 넓혀 기다린다. 안정화 대기 휴리스틱은 쓰지 않는다. 없는 Evidence는 Undelivered(internal)이며 양쪽에 없어도 SAME이 아니다.
근거: "1초간 변화 없음"은 완료의 증거가 아님. Legacy의 소비 Evidence도 비동기라 New만 폴링하면 export 전에 빠질 수 있음. settle만 기다리면 한쪽에만 생긴 추가 호출(F9)의 Evidence를 놓칠 수 있음.
한계: 자원 부족 시 공유 브로커 + 토픽 접두사로 후퇴할 수 있으며 그때 Kafka는 스택 축 격리의 예외.
```

## 실행 지시 (확정 후 CLAUDE.md에 동일)

이 문서를 기준으로 3.0부터 순서대로 진행한다. 한 번에 한 단계만, 시작 전에 무엇을 만들지와 끝난 기준을 설명하고, 끝나면 `docs/reports/phase3.<step>.md`를 작성·커밋·push하고 멈춘다. 다음 단계는 내 승인 후. 오류는 해당 단계에서 해결한다. 문서에 없는 설계 결정은 임의로 정하지 말고 보고서 0절에 질문으로 올린다. "하지 말 것"과 Phase 4 항목은 구현하지 않는다. 커밋은 `phase3.x: ...`, 사다리·결함은 `phase3.5-v1.1: ...`, `phase3.6-F1: ...` 형식으로 단계당 1개. **A/A 게이트(VU=3 ×3 diff ∅)는 3.1~3.4와 base 이미지에 적용하고, 3.5·3.6은 "모든 diff가 설명됨"이 기준이다.** Rule은 learn 세션에서만 만든다.
