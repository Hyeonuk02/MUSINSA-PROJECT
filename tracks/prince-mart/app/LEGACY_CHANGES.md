# Prince Mart Legacy 변경 내역

이 디렉터리는 [PrajwalSH1930/prince-mart-e-commerce-backend](https://github.com/PrajwalSH1930/prince-mart-e-commerce-backend)
커밋 `c56bac8de91bfc1cdd8863bd720cfe7e4568276d`의 `order-service`, `coupon-service`, `payment-service`를
복사한 것이다(라이선스 EPL-2.0, [LICENSE](LICENSE)). upstream에서 바꾼 것을 모두 이 문서에 기록한다(EPL-2.0 변경 내역 요건).
코드에서 바꾼 곳에는 `[LEGACY_CHANGES]` 주석을 달았다.

이 코드는 "운영 트래픽 재현과 변경 전후 행동 비교를 통한 시스템 교체 검증" 실험의 **Legacy**다.
루트 파이프라인(k8s + Istio 미러링, `services/evidence-collector`, `engine/`)이 실험용으로 만든 앱이 아닌
외부 시스템에서도 동작하는지 확인하는 일반화 검증에 쓴다.
Legacy의 동작은 비교의 기준이므로 비즈니스 동작은 꼭 필요한 두 곳(Razorpay 대체, Kafka 이벤트)만 바꿨다.

> 이 코드는 처음에 Docker Compose 기반 독립 트랙(`branch-park` 브랜치)에서 준비했고, 루트 파이프라인에 맞춰 이 위치로 옮겼다.
> Compose 구성, 자체 Evidence 계측, 결함 패치 빌드 등 그때의 구성과 실측 기록은 `branch-park`에 남아 있다.

## 고치지 않는 Legacy 버그

New의 "승인된 개선" 정답 데이터로 쓰기 위해 **의도적으로 남겨 둔다.** 재현 여부만 확인한다.

| ID | 내용 |
|---|---|
| B1 | 쿠폰 사용 기록 누락. Order가 커밋 전에 `/coupons/use`를 호출하고, Coupon이 `GET /orders/order/{id}`로 역조회하면 404. Order는 로그만 남기고 진행하므로 `coupon_usage`가 항상 비고, 같은 쿠폰을 무제한 재사용할 수 있다 |
| B2 | Coupon `OrderResponse.status`가 Order의 `orderStatus`와 필드명이 달라 항상 null. 취소 주문 확인이 동작하지 않는다 |
| B3 | 만료 쿠폰이나 최소 금액 미달 쿠폰을 넣어도 정가로 주문되고 200 |
| B4 | `/payments/verify`가 CANCELLED 주문을 CONFIRMED/PAID로 바꾼다 |
| B5 | PAID 주문을 취소해도 paymentStatus가 PAID로 남는다 |
| B6 | 모든 RuntimeException이 404로 매핑된다 |

---

## 설정 (비즈니스 동작 변경 없음)

### DB 드라이버: PostgreSQL → MySQL

- 파일: `{order,coupon,payment}-service/pom.xml`
- 변경: `org.postgresql:postgresql` → `com.mysql:mysql-connector-j` (runtime, 버전은 Boot parent의 관리 버전)
- 이유: 실험 시스템 DB는 MySQL 8로 확정(architecture v10.1)

### 버전 통일

- 파일: `{order,coupon,payment}-service/pom.xml`
- 변경: Spring Boot order 4.0.3 / coupon 4.0.5 / payment 3.4.2 → **4.1.1**(루트 `services/`와 같음),
  Spring Cloud 2025.1.0 / 2025.1.1 / 2024.0.0 → **2025.1.3**(Boot 4.1을 지원하는 Oakwood 최신), Java 21 → **17**(루트와 같음. 21 전용 문법 사용 없음)
- payment는 Boot 3 → 4라 starter 이름이 바뀐다: `spring-boot-starter-web` → `spring-boot-starter-webmvc`,
  `spring-kafka` → `spring-boot-starter-kafka`, `spring-boot-starter-test` → `spring-boot-starter-{data-jpa,webmvc}-test`
- 이유: 루트 `services/evidence-collector`가 Boot 4.1.1로 빌드된다. 이 때문에 원래 계획한 New 변경 "Payment Boot 4 업그레이드"는
  Legacy에 흡수됐다. 대신 New 정상 변경 사례로 payment의 Jackson 2 → 3 전환을 쓴다(팀원 합의).
- 확인할 것: payment는 Jackson 2 `ObjectMapper`(`com.fasterxml`)를 주입받는다. order·coupon과 같은 의존성 구성이라
  같은 방식으로 주입된다고 보지만, 감사 로그 `dataAfter`의 키 순서(Jackson 2 선언 순서)가 그대로인지 A/A에서 확인한다.

### `local` profile 추가

- 파일: `{order,coupon,payment}-service/src/main/resources/application-local.yml` (신규)
- upstream `application.yml`은 수정하지 않고, `SPRING_PROFILES_ACTIVE=local`에서 이 파일이 덮어쓴다.
- 변경
  - datasource driver `com.mysql.cj.jdbc.Driver`, dialect `MySQLDialect`
  - `spring.jpa.hibernate.ddl-auto: none`, `spring.sql.init.mode: never` — 스키마 소유자는 MySQL init SQL 하나
  - `eureka.client.enabled: false`
  - Feign 대상 주소를 `spring.cloud.discovery.client.simple.instances`로 고정. 주소는 env
    (`ORDER_SERVICE_URI`, `CART_SERVICE_URI`, …)로 받는다. 서비스별로 실제 쓰는 Feign 대상만 선언
    - order: CART, IDENTITY(userClient/addressClient), COUPON, INVENTORY, PAYMENT, AUDIT, SHIPPING, NOTIFICATION
    - coupon: ORDER, AUDIT
    - payment: ORDER, NOTIFICATION, AUDIT
- JDBC URL(`*_DB_URL` env)에는 `serverTimezone=UTC`를 붙인다.
- 참고: `ddl-auto: none`이면 upstream의 `ddl-auto: update`는 무시된다. upstream 설정의 `show-sql: true`는 그대로 둔다.

### Docker 빌드

- 파일: `{order,coupon,payment}-service/DockerFile` (내용 교체)
- upstream은 미리 빌드된 `target/*.jar`를 복사했다. 소스에서 재현 가능하게 빌드하도록 멀티스테이지로 바꿨다.
  루트 `services/*/Dockerfile`과 같이 빌드 컨텍스트는 저장소 루트이고, `services/evidence-collector`를 먼저 `mvn install`한 뒤 앱을 빌드한다.
- 베이스 이미지: `maven:3.9-eclipse-temurin-17` / `eclipse-temurin:17-jre`
- 런타임 옵션은 upstream 값(`-Xmx384M -Xms256M -XX:+UseSerialGC`)을 유지하고 `-Duser.timezone=UTC`만 추가했다.
- 파일명: macOS 파일시스템은 대소문자를 구분하지 않아 `Dockerfile`을 따로 둘 수 없으므로 upstream `DockerFile`의 내용을 교체했다.
- 서비스별 `.dockerignore`는 upstream 파일이다. 빌드 컨텍스트가 저장소 루트라 지금은 쓰이지 않는다.
- 빌드: `docker build -f tracks/prince-mart/app/<svc>-service/DockerFile -t prince-mart/<svc>-service:<tag> .`

---

## 통제·계측 (비즈니스 동작 변경 없음)

### 시각 고정 (`APP_FIXED_CLOCK` → `java.time.Clock`)

- 신규: `{order,coupon,payment}-service/.../config/ClockConfig.java`, `config/AppClock.java`
  - `app.fixed-clock`(`application-local.yml`, env `APP_FIXED_CLOCK`)이 있으면 `Clock.fixed(값, UTC)`, 없으면 `Clock.systemUTC()`.
    루트 `services/order`의 `ClockConfig`와 같은 방식이다.
  - JPA 엔티티는 Spring 빈을 주입받을 수 없으므로 `ClockConfig`가 같은 Clock을 정적 holder `AppClock`에도 담는다.
- 교체한 곳 (12곳)

| 파일 | 전 | 후 |
|---|---|---|
| order `entity/Order.java` `createdAt` | `@CreationTimestamp` | `@PrePersist` → `AppClock.now()` |
| order `entity/OrderStatusHistory.java` `changedAt` | `@CreationTimestamp` | `@PrePersist` → `AppClock.now()` |
| payment `entity/Payment.java` `createdAt` | `@CreationTimestamp` | `@PrePersist` → `AppClock.now()` |
| payment `entity/Refund.java` `createdAt` | `@CreationTimestamp` | `@PrePersist` → `AppClock.now()` |
| coupon `entity/CouponUsage.java` `usedAt` | `@PrePersist` `LocalDateTime.now()` | `@PrePersist` `AppClock.now()` |
| coupon `service/CouponService.java` `validateCoupon` 만료 판정 | `LocalDateTime.now()` | `LocalDateTime.now(clock)` (생성자 주입) |
| `{order,coupon,payment}` `exception/GlobalExceptionHandler.java` `ErrorDetails.timestamp` ×2씩 | `LocalDateTime.now()` | `LocalDateTime.now(clock)` (생성자 주입) |

- 동작: insert마다 무조건 값을 채우는 `@CreationTimestamp`의 동작은 유지하고 시각 출처만 Clock으로 바꿨다.
  `APP_FIXED_CLOCK`이 없으면 시스템 시각(UTC, JVM도 `-Duser.timezone=UTC`)이라 upstream과 같다.
- **알려진 부수효과 — 시각 동점 정렬**: 고정 시각에서는 모든 `created_at`이 같다. `GET /orders/history`
  (`findByUserIdOrderByCreatedAtDesc`)가 동점이 되어 MySQL 8.4에서 **PK 오름차순**으로 나온다(실측 `[1,2,3]`, 3회 동일).
  실제 시각이면 최신순(`[3,2,1]`)이다. `OrderStatusHistoryRepository.findByOrderOrderIdOrderByChangedAtDesc`도 같은 성질이지만
  코드에서 호출되지 않는다. 비즈니스 로직은 건드리지 않고 이 성질을 문서화한다.
- `Refund`는 upstream 코드에 생성 경로가 없다(엔티티와 리포지토리만 있음). 교체만 하고 실행 확인 대상에서 뺀다.

### Evidence 계측: 루트 `evidence-collector`

- 추가: `poc:evidence-collector:0.0.1` 의존성(세 서비스). Spring Boot 자동 구성으로 붙고 서비스 코드는 수정하지 않는다.
- 설정은 모두 env로 k8s 매니페스트가 넣는다: `EVIDENCE_STORE_URL`, `EVIDENCE_STACK`, `EVIDENCE_SERVICE`, `EVIDENCE_VERSION`,
  `EVIDENCE_HEADERS`, `EVIDENCE_APP_PACKAGES=com.pm`. `EVIDENCE_STORE_URL`이 없으면 계측이 꺼진다.
- Kafka: producer 인터셉터와 consumer `RecordInterceptor`는 collector가 Boot 자동 구성으로 붙인다.
  order의 consumer는 Boot 기본 리스너 컨테이너 팩토리를 쓰므로 따로 설정할 것이 없다.
- **Feign 호출 (해소)**: 처음에는 collector의 하위 호출 전파와 `externalCalls` 기록이 `RestClient` 인터셉터뿐이었다. Prince Mart의 서비스 간 호출과
  외부 호출은 전부 OpenFeign이라 이 홉이 Evidence에 남지 않았다. Prince Mart 코드를 RestClient로 바꾸지 않고, 팀원 합의대로 collector에
  Feign 지원을 더했다(`poc.evidence.FeignEvidenceCapability`, `FeignEvidenceAutoConfiguration`). OpenFeign이 클래스패스에 있을 때만 켜지고,
  RestClient 경로와 같은 필드와 같은 규칙으로 기록한다. 서비스 코드 변경은 없다.
- **가짜 PG 호출**: 아래 "가짜 PG 호출: `RestClient.Builder` 주입" 참조. 이 변경 전에는 `RestClient.create()`로 만든 클라이언트라 collector가 붙지 못했다.
- **관측(일반화 검증 발견)**: `externalCalls[].host`의 값은 클라이언트 종류에 따라 출처가 다르다.
  - RestClient 경로(가짜 PG): 실제 URI의 host(예: `PAYMENT_GATEWAY_URL`의 host)
  - Feign 경로(서비스 간 호출, WireMock 대상 호출): 로드밸런서가 주소를 풀기 전의 논리 서비스 이름(예: `COUPON-SERVICE`, `AUDIT-SERVICE`).
    Spring Cloud OpenFeign이 Capability로 감싸는 대상이 로드밸런서 클라이언트이기 때문이다(collector 통합 테스트로 확인)
  - legacy와 new는 같은 경로를 쓰므로 비교 결과에는 영향이 없다. 다만 팀원 도구에서 host로 대상을 고르는 설정(`OBSERVED_HOSTS`,
    `verify_sameness --observed-hosts`, contract의 `observed.hosts`, `gateway_calls_per_idem_key_le_1.host`, 규칙의 host 매처)은
    Prince Mart에 맞는 값을 넣어야 한다. 서비스 간 호출은 논리 이름, 가짜 PG는 실제 host다.
    여러 Feign 대상이 같은 WireMock 주소를 가리켜도 host가 서로 구분되는 장점도 있다.
- 실측으로 드러난 Legacy 성질(고치지 않음, `branch-park`의 자체 계측에서 확인): payment verify는 **커밋 전에 이벤트를 발행**한다
  (PUBLISH → COMMIT_BEGIN → UPDATE). order 주문 생성은 `coupons/use`를 커밋 전에 호출한다(B1의 원인).

### 가짜 PG 호출: `RestClient.Builder` 주입

- 파일: `payment-service/.../gateway/FakePgPaymentGateway.java`, `payment-service/pom.xml`
- 변경
  - 생성자: `RestClient.create(baseUrl)` -> Boot가 관리하는 `RestClient.Builder`를 주입받아 `builder.baseUrl(baseUrl).build()`
  - `pom.xml`: `spring-boot-starter-restclient` 추가(Boot 4는 `RestClient.Builder` 자동 구성이 별도 모듈이다)
- 이유: 정적 팩토리로 만든 RestClient에는 collector가 `RestClientCustomizer`로 인터셉터를 붙일 수 없다. 그러면 결제 생성의
  `POST /v1/orders`가 `externalCalls`에 남지 않고 재생 헤더도 전파되지 않는다. 이 호출은 결함 탐지 근거로 쓰이는 유일한 실제 외부 호출이다.
- 전례: 팀원도 루트 `services/order`의 `PaymentGatewayClient`를 Phase 3.1에서 같은 이유로 바꿨다(정적 `RestClient.builder()` ->
  Boot `RestClient.Builder` 주입, `spring-boot-starter-restclient` 추가. `docs/reports/phase3.1.md` 6절).
- 동작: 요청 경로, 본문, 오류 처리는 그대로다. 요청 팩토리도 같다. payment 클래스패스에 Apache HttpClient 5가 있어서
  `RestClient.create()`와 Boot Builder 모두 `HttpComponentsClientHttpRequestFactory`를 고른다.
  달라지는 것은 collector가 붙인 재생 헤더 4개(`X-Replay-*`)가 가짜 PG 요청에 더해진다는 점뿐이다.

---

## 기능 패치 (비즈니스 동작 변경, 범위 명시)

### Razorpay 대체: `PaymentGateway`

- 이유: Razorpay SDK(`razorpay-java` 1.4.3)는 API 호스트를 `static final`로 고정하고 있어 설정만으로 가짜 서버를 붙일 수 없다.
  실험 환경에서는 실제 Razorpay로 나가면 안 되고(외부 의존·비결정), 외부 호출은 WireMock으로 받아야 한다.
- 신규: `payment-service/.../gateway/`
  - `PaymentGateway` — `String createOrder(JSONObject orderRequest) throws Exception`. SDK 호출과 같은 계약(요청 본문, PG 주문 id 반환, 실패 시 예외)
  - `RazorpayPaymentGateway` — **기본값**(`payment-gateway.type` 없음 또는 `razorpay`). PaymentService에 있던 SDK 호출과 키 설정(`razorpay.key.*`)을 그대로 옮겼다
  - `FakePgPaymentGateway` — `payment-gateway.type=fake`(local profile). `POST {payment-gateway.fake-url}/v1/orders`로 SDK와 같은 본문을 보내고,
    4xx면 Razorpay 오류 본문의 `error.description`을 메시지로 가진 예외를 던진다
- 변경: `service/PaymentService.java`
  - `new RazorpayClient(...)` + `client.orders.create(orderRequest).get("id")` → `paymentGateway.createOrder(orderRequest)`
  - `@Value razorpay.key.*` 필드 제거(RazorpayPaymentGateway로 이동), 생성자에 `PaymentGateway` 추가
  - **그 외 PaymentService 로직은 바꾸지 않았다**(요청 본문 구성, 저장, 감사 로그, 실패 시 `FAILED` 응답과 메시지 전달 모두 그대로)
- 설정: `application-local.yml`에 `payment-gateway.type: fake`, `payment-gateway.fake-url: ${PAYMENT_GATEWAY_URL}`
- 가짜 PG(WireMock 매핑)
  - 성공: `{"id":"order_{receipt의 주문 번호}", ...}` — 결정적 id
  - 실패 fixture: `amount == 9999900`(99,999원) → 400 `{"error":{"code":"BAD_REQUEST_ERROR","description":"Payment declined by fake PG (fixture: amount 99999)"}}`

### Kafka 이벤트: `PaymentCompleted`

- 이유: 결제 확정 후 Payment → Order 동기 Feign 호출(`PUT /orders/{id}/status`)을 이벤트로 대체한다.
  이벤트 발행 횟수·payload는 Evidence 비교 항목이다.
- payment-service
  - `pom.xml`: `spring-boot-starter-kafka` 추가
  - 신규 `event/PaymentEventPublisher.java`: 토픽 `payment-events`, key = orderId, value = JSON 문자열
    `{"eventType":"PaymentCompleted","orderId","transactionId","amount","currency","audit":{"dataBefore","dataAfter"}}`
    - `amount`는 원래 알림에 넣던 `payment.getAmount().toString()`
    - `audit`은 원래 Payment가 보내던 감사 로그의 dataBefore/dataAfter 문자열(이 서비스 ObjectMapper로 직렬화). 직렬화 실패 시 null(원본처럼 감사 로그 생략)
    - 동기 발행(완료까지 대기). 실패하면 예외 → 결제 상태 변경 트랜잭션 롤백
  - `service/PaymentService.java` `completePaymentManually`: 결제를 COMPLETED로 저장한 뒤 **이벤트 발행으로 끝난다.**
    제거: `orderClient.updateOrderStatus(...)`, `PAYMENT_COMPLETED_SUCCESS` 감사 로그, 알림 발송(실패 시 감사 로그 포함).
    `OrderClient`/`NotificationClient` 필드와 생성자 인자 제거. 인터페이스 파일(`client/OrderClient.java`, `client/NotificationClient.java`)과
    DTO는 diff를 줄이려고 남겼다(이제 호출되지 않음)
  - `application-local.yml`: `spring.kafka.bootstrap-servers`, `app.kafka.payment-events-topic`
- order-service
  - `pom.xml`: `spring-boot-starter-kafka` 추가
  - 신규 `event/PaymentCompletedListener.java` — 원래 Payment가 하던 후속 처리를 **같은 순서로** 한다
    1. `OrderService.updateStatus(orderId, "PAID", "CONFIRMED")` — 기존 `PUT /orders/{id}/status`와 같은 메서드(이력·ORDER_STATUS_UPDATE 감사 로그·배송 요청)
    2. 감사 로그 `PAYMENT_COMPLETED_SUCCESS` — 이벤트의 audit 문자열 그대로, `serviceName: "PAYMENT-SERVICE"` 그대로(호출 주체만 order-service)
    3. 주문 확인 알림 — 실패 시 `POST_PAYMENT_NOTIFICATION_FAILED` 감사 로그
  - 신규 `event/KafkaConsumerConfig.java`: `DefaultErrorHandler(FixedBackOff(0, 0))` — **재시도 없음**(재전달 시 이력·감사 로그·배송 요청 중복 방지)
  - 신규 `client/NotificationClient.java`, `dto/NotificationRequest.java`: payment-service에서 복사.
    `@JsonPropertyOrder`로 필드 선언 순서를 명시했다 — order의 Jackson 3는 기본 직렬화가 **알파벳순**이라
    그대로 두면 알림 본문의 키 순서가 원본(payment, Jackson 2, 선언 순서)과 달라진다(실측)
  - `application-local.yml`: NOTIFICATION-SERVICE 주소, `spring.kafka.*`(`auto-offset-reset: earliest`), 토픽·consumer group
- **동작 차이(의도된 것, 이 패치의 결과)**
  - `/payments/verify`는 주문 상태 변경을 기다리지 않고 200을 돌려준다. 상태 변경·감사 로그·배송·알림은 consumer가 비동기로 한다
  - 없는 주문의 결제를 verify하면 원본은 Order 404 → 롤백 → 404였다. 이제는 결제가 COMPLETED로 커밋되고 200,
    consumer는 `Order not found`로 실패(재시도 없음). 외부 호출은 원본과 같이 0건(실측)
  - 감사 로그 PAYMENT_COMPLETED_SUCCESS와 알림의 호출 주체가 payment-service에서 order-service로 바뀐다
- 실측(`branch-park`): Kafka 전환 전후로 시나리오 26항목의 응답·DB 7테이블·WireMock journal(본문 포함)이 **바이트 단위로 같다.**
  verify 1건의 외부 호출 순서도 같다(ORDER_STATUS_UPDATE 감사 → 배송 → PAYMENT_COMPLETED_SUCCESS 감사 → 알림).
