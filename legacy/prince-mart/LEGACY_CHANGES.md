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
