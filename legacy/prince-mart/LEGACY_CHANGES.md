# Prince Mart Legacy 변경 내역

이 디렉터리는 [PrajwalSH1930/prince-mart-e-commerce-backend](https://github.com/PrajwalSH1930/prince-mart-e-commerce-backend)
커밋 `c56bac8de91bfc1cdd8863bd720cfe7e4568276d`의 `order-service`, `coupon-service`, `payment-service`를
복사한 것이다(라이선스 EPL-2.0, [LICENSE](LICENSE)). 원본 스냅샷은 수정 없이 먼저 커밋했고,
그 뒤의 모든 변경을 이 문서에 기록한다(EPL-2.0 변경 내역 요건).

이 코드는 "운영 트래픽 재현과 변경 전후 행동 비교를 통한 시스템 교체 검증" 실험의 **Legacy**다.
Legacy의 동작은 비교의 기준이므로, 변경은 아래 세 등급으로 나누고 등급별로 커밋을 분리한다.

| 등급 | 범위 | 비즈니스 동작 |
|---|---|---|
| **C (설정)** | yml, profile, pom 드라이버, Dockerfile, env | 바꾸지 않는다 |
| **I (통제·계측)** | 시각 고정, Evidence 필터, OTel | 바꾸지 않는다(결과 값의 시각 출처만 Clock으로 바뀜) |
| **F (기능 패치)** | 이번에 허용된 것은 둘뿐: (a) Razorpay 대체, (b) Kafka 이벤트 | 바꾼다. 범위를 명시한다 |

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

## C — 설정

### L-C1. DB 드라이버: PostgreSQL → MySQL

- 파일: `{order,coupon,payment}-service/pom.xml`
- 변경: `org.postgresql:postgresql` → `com.mysql:mysql-connector-j` (runtime, 버전은 각 Boot parent의 관리 버전)
- 이유: 실험 시스템 DB는 MySQL 8로 확정(architecture v10.1). Boot/Cloud 버전은 **통일하지 않는다**
  (order 4.0.3 / coupon 4.0.5 / payment 3.4.2 그대로). 버전 업그레이드는 New의 "정상 변경" 실험 케이스로 쓴다.

### L-C2. `local` profile 추가

- 파일: `{order,coupon,payment}-service/src/main/resources/application-local.yml` (신규)
- upstream `application.yml`은 수정하지 않고, `SPRING_PROFILES_ACTIVE=local`에서 이 파일이 덮어쓴다.
- 변경
  - datasource driver `com.mysql.cj.jdbc.Driver`, dialect `MySQLDialect`
  - `spring.jpa.hibernate.ddl-auto: none`, `spring.sql.init.mode: never` — 스키마 소유자는 MySQL init SQL 하나
    (`deploy/compose/mysql-initdb/<service>/01-schema.sql`)
  - `eureka.client.enabled: false`
  - Feign 대상 주소를 `spring.cloud.discovery.client.simple.instances`로 고정. 주소는 env
    (`ORDER_SERVICE_URI`, `CART_SERVICE_URI`, …)로 받는다. 서비스별로 실제 쓰는 Feign 대상만 선언
    - order: CART, IDENTITY(userClient/addressClient), COUPON, INVENTORY, PAYMENT, AUDIT, SHIPPING
    - coupon: ORDER, AUDIT
    - payment: ORDER, NOTIFICATION, AUDIT
- JDBC URL(`*_DB_URL` env)에는 `serverTimezone=UTC`를 붙인다(compose에서 지정).
- 참고: `ddl-auto: none`이면 upstream의 `ddl-auto: update`는 무시된다. upstream 설정의 `show-sql: true`는 그대로 둔다.

### L-C3. 멀티스테이지 Docker 빌드

- 파일: `{order,coupon,payment}-service/DockerFile`, `.dockerignore` (내용 교체)
- upstream은 미리 빌드된 `target/*.jar`를 복사하는 방식이었고, `.dockerignore`가 `src/`와 `pom.xml`을 제외했다.
  재현 가능하게 소스에서 빌드하도록 `maven:3.9-eclipse-temurin-21` → `eclipse-temurin:21-jre`(digest 고정)
  멀티스테이지로 바꿨다.
- 런타임 옵션은 upstream 값(`-Xmx384M -Xms256M -XX:+UseSerialGC`)을 유지하고 `-Duser.timezone=UTC`만 추가했다.
- 파일명: macOS 파일시스템은 대소문자를 구분하지 않아 `Dockerfile`을 따로 둘 수 없으므로 upstream `DockerFile`의 내용을 교체했다.
- OTel Java agent는 이미지에 넣지 않는다(hyeonuk-dev decision-log D5와 같은 방식으로 실행 시 주입).

---

## I — 통제·계측

### L-I1. 시각 고정 (`APP_FIXED_CLOCK` → `java.time.Clock`)

- 신규: `{order,coupon,payment}-service/.../config/ClockConfig.java`, `config/AppClock.java`
  - `app.fixed-clock`(`application-local.yml`, env `APP_FIXED_CLOCK`)이 있으면 `Clock.fixed(값, UTC)`, 없으면 `Clock.systemUTC()`.
    hyeonuk-dev `services/order`의 `ClockConfig`와 같은 방식이다.
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
  코드에서 호출되지 않는다. 비즈니스 로직은 건드리지 않고 이 성질을 문서화한다(docs/legacy-decision-log.md L5).
- `Refund`는 upstream 코드에 생성 경로가 없다(엔티티와 리포지토리만 있음). 교체만 하고 실행 확인 대상에서 뺀다.

---

## F — 기능 패치

### L-F1. (a) Razorpay 대체: `PaymentGateway`

- 이유: Razorpay SDK(`razorpay-java` 1.4.3)는 API 호스트를 `static final`로 고정하고 있어 설정만으로 가짜 서버를 붙일 수 없다.
  실험 환경에서는 실제 Razorpay로 나가면 안 되고(외부 의존·비결정), 외부 호출 Evidence가 WireMock journal에 남아야 한다.
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
- 가짜 PG(WireMock, `deploy/compose/wiremock/mappings/pg-orders-create*.json`)
  - 성공: `{"id":"order_{receipt의 주문 번호}", ...}` — 결정적 id
  - 실패 fixture: `amount == 9999900`(99,999원) → 400 `{"error":{"code":"BAD_REQUEST_ERROR","description":"Payment declined by fake PG (fixture: amount 99999)"}}`
