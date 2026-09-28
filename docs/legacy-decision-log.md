# Legacy 트랙 Decision Log — Prince Mart Legacy (Compose 선행 트랙)

박병언 트랙. Prince Mart(order/coupon/payment)를 Legacy로 구축하고 Kafka·요청 ID 전파·Evidence 계측·
베이스라인(A/A)까지 진행한다. 실행 환경(Compose + nginx)만 임시이고, 그 밖의 규약은 architecture v10.1과
Phase 1 결정(hyeonuk-dev 브랜치 `docs/decision-log.md`의 D1~D8)을 따른다.
형식은 그 문서와 같다(**결정 / 근거 / 대안**). 두 트랙을 합칠 때 이 문서를 그쪽 decision-log에 이어 붙인다.

Legacy 코드 변경 내역 자체는 [`legacy/prince-mart/LEGACY_CHANGES.md`](../legacy/prince-mart/LEGACY_CHANGES.md)에 있다.
본문의 D3·D4·D5·D8은 hyeonuk-dev `docs/decision-log.md`의 항목을 가리킨다.

---

### L1. Prince Mart를 VU=1, business key 없이 돌린다

**결정**
Prince Mart API를 그대로 쓴다(`POST /orders/place`, 자동 증가 `orderId`, `transactionId`).
business key(`orderKey`)를 추가하지 않고, k6는 **VU=1로 세션을 순서대로** 실행한다.
체인 요청(결제 확정, 취소)은 legacy 응답의 `orderId`/`transactionId`를 이어받는다.

**근거**
v10.1 §2가 VU=N에서 요청 단위 비교를 성립시키는 수단은 client business key다.
Prince Mart에는 그것이 없고, 추가하면 Legacy 코드에 허용 범위(기능 패치 2개) 밖의 변경이 생긴다.
k6는 legacy 응답만 보므로 new에는 **legacy가 발급한 ID가 그대로 미러된다.** 이 ID가 new에서도 같은 대상을
가리키려면 두 스택의 자동 증가 순서가 같아야 하고, 그 조건은 VU=1 + 같은 S0 + 같은 요청 순서일 때만 성립한다.
가짜 PG가 결정적 ID(`order_{orderId}`)를 돌려주는 것도 같은 이유다.

한계: New가 어떤 요청에서 행을 하나 덜/더 만들면 그 뒤 같은 스택의 ID가 밀려 이후 체인 요청이 연쇄로 어긋난다.
세션마다 사용자를 나눠도 `orderId`는 전역 시퀀스라 이 연쇄는 세션을 넘는다.

**대안**
- Prince Mart에 `orderKey` 추가 — v10.1 원안. Legacy 기능 변경이 되어 "허용된 기능 패치 2개" 원칙과 충돌.
- VU=N — 스택마다 자동 증가 ID가 어긋날 수 있어 체인 요청이 성립하지 않는다.

**미결(팀 합의 필요)**: 합칠 때 Prince Mart가 `services/{order,coupon,payment}`를 대체하는지.

### L2. Compose에서 스택 = 네트워크, 스택 안은 짧은 이름

**결정**
`deploy/compose/docker-compose.yml`에서 스택마다 네트워크 하나를 두고, 컨테이너에 네트워크 alias
(`order`, `coupon`, `payment`, `mysql-order`, `mysql-coupon`, `mysql-payment`, `wiremock`)를 준다.
앱 env는 `x-app-env` 하나를 legacy/new가 공유한다.

**근거**
k8s 네임스페이스 안에서 짧은 Service 이름으로 찾는 구조와 같다. legacy/new의 설정이 바이트 단위로 같아
"설정 차이가 관측 차이로 섞이는" 경우를 없앤다. 합칠 때는 네트워크 → 네임스페이스, alias → Service 이름으로 옮긴다.

**대안**
- 스택별 컨테이너 이름(`order-legacy`)을 env에 직접 쓰기 — 스택마다 env가 달라진다.

### L3. S0 = MySQL 컨테이너 재생성(tmpfs) + init SQL

**결정**
MySQL 데이터 디렉터리를 tmpfs에 둔다. `deploy/compose/reset.sh`가 MySQL 컨테이너를 `--force-recreate`로
새로 만들고 healthy(`mysqladmin ping -h 127.0.0.1`, D3)까지 기다린다. 앱은 재시작하지 않는다.
스키마는 Hibernate `ddl-auto=update`로 한 번 만든 뒤 `mysqldump --no-data`로 떠서
`deploy/compose/mysql-initdb/<service>/01-schema.sql`에 고정했다(`tools/dump-schema.sh`).

**근거**
k8s의 emptyDir + `strategy: Recreate` + `rollout restart`(D4)와 같은 의미다. TRUNCATE 방식은
"초기화 주체가 앱/스크립트 둘"이 되고 시퀀스 리셋을 테이블마다 따로 챙겨야 한다.
앱 커넥션은 Hikari가 빌려줄 때 검증해 끊긴 것을 버리고 다시 맺는다(`Failed to validate connection` 후 정상 처리, 실측).

`mysqldump`는 테이블을 이름순으로 내보내 FK 참조 순서와 어긋나므로(`coupon_usage` → `coupons`)
init SQL을 `SET FOREIGN_KEY_CHECKS=0/1`로 감쌌다.

**대안**
- `TRUNCATE ... RESTART IDENTITY`(사전 검증에서 Postgres로 사용) — MySQL에는 `RESTART IDENTITY`가 없고, 위 이유로 배제.
- 앱까지 재시작 — 리셋 시간이 늘고, 커넥션 복구 여부를 확인할 기회를 없앤다.

### L4. MySQL은 메모리만 줄여서 띄운다

**결정**
`--performance-schema=OFF --innodb-buffer-pool-size=64M`. 그 외(문자셋, collation, 격리 수준)는 기본값.

**근거**
Docker 메모리 8GB에서 베이스라인 단계에 MySQL 6 + JVM 6 + Kafka + WireMock 2 + 관측 스택을 함께 띄워야 한다.
두 옵션은 SQL 의미에 영향이 없다.

### L5. 시각 고정은 `Clock` 빈 + 엔티티용 정적 holder, 동점 정렬은 문서화만

**결정**
세 서비스에 `ClockConfig`(`APP_FIXED_CLOCK` → `Clock.fixed`, 없으면 `systemUTC`)를 두고,
`@CreationTimestamp` 4곳·`CouponUsage.usedAt`은 정적 holder `AppClock`을 읽는 `@PrePersist`로,
`validateCoupon`과 `GlobalExceptionHandler`는 생성자 주입 Clock으로 바꿨다(`LEGACY_CHANGES.md` L-I1).
고정 시각 때문에 생기는 `ORDER BY created_at` 동점은 **코드로 막지 않고** 기록한다.

**근거**
엔티티 콜백은 Spring 빈 주입을 받을 수 없다. JPA `@EntityListeners` + Hibernate의 Spring bean container로도
가능하지만 Boot 3(payment)/Boot 4(order, coupon)에서 모두 같은 방식으로 동작하는지 따로 확인해야 해서
가장 단순한 정적 holder를 택했다.

동점 실측: 같은 사용자 주문 3건에서 `/orders/history`가 `[1,2,3]`(PK 오름차순)으로 3회 동일.
같은 MySQL 버전·같은 데이터·같은 실행 계획이면 결정적이라 A/A에서는 차이가 나지 않는다.
다만 SQL 표준상 동점 순서는 보장되지 않고, New가 인덱스를 추가하는 등 실행 계획이 바뀌면 순서가 바뀔 수 있다.
그 차이는 "고정 시각이 만든 인공물"이지 New의 행동 차이가 아니다.

**대안**
- 호출마다 1ms씩 증가하는 stepping clock — 동점은 없어지지만, New가 `now()` 호출 수를 하나만 바꿔도
  이후 모든 시각이 밀려 거짓 차이가 대량으로 생긴다.
- 코드에 2차 정렬 키(`orderId`) 추가 — Legacy 비즈니스 로직 변경이라 허용 범위 밖.
- `/orders/history` 응답 목록을 정규화에서 정렬 — 진짜 순서 회귀를 숨긴다. Step 8(Normalization 규칙)에서 다시 판단한다.

### L6. 외부 의존성 fixture: 장바구니 100,000원, 결제 실패는 99,999원

**결정**
- WireMock 장바구니는 모든 사용자에게 같은 응답이다. 상품·옵션·수량은 사전 검증과 같고(101/1001 ×2, 102/1002 ×1) 가격만
  20,000 / 60,000으로 바꿔 **합계 100,000원**으로 둔다.
- 가짜 PG는 **금액이 99,999원(9,999,900 paise)이면 거절**한다. 이 금액은 1원 고정 할인 쿠폰(`PGFAIL1`)으로 만든다.
- 가짜 PG의 주문 id는 receipt(`order_rcptid_{orderId}`)에서 뽑은 `order_{orderId}`로 결정적이다.
- 쿠폰 fixture는 coupon DB의 S0 시드(`deploy/compose/mysql-initdb/coupon/02-seed.sql`)로 넣는다. 만료일은 고정 시각(2026-09-01) 기준
  과거 2026-08-01 / 미래 2026-12-31.

**근거**
- 99,999는 "100,000에서 1원 모자람"이라 응답·DB·journal에서 실패 fixture임이 바로 보인다. 원안(합계 60,000원, 59,999원)보다 식별이 쉽다.
- 실패를 장바구니 응답(사용자별 매핑)이 아니라 쿠폰으로 만들면 WireMock 장바구니 매핑이 하나로 유지된다.
- 결정적 PG id가 있어야 k6가 legacy 응답에서 받은 `transactionId`를 new에 미러해도 같은 결제를 가리킨다(L1).
- `/coupons/create` API로 쿠폰을 넣으면 감사 로그 외부 호출이 섞여 S0 정의가 흐려진다.

**대안**
- 사용자 ID 기반 실패(특정 사용자 장바구니만 99,999원) — 매핑이 사용자별로 갈라진다.
- receipt(주문 번호) 기반 실패 — 자동 증가 ID에 묶여 corpus 순서가 바뀌면 실패 대상도 바뀐다.

**실측(Step 4)**: `deploy/compose/tools/scenarios.py`로 시나리오와 B1~B6 26항목 PASS. 같은 시나리오 2회 실행에서 응답 27건·
WireMock journal 127건(본문 포함)·DB 7테이블이 **정규화 없이 동일**했다(결제 성공·확정 경로 포함).
관찰된 표기 차이(정규화 후보): 주문 생성 응답 `totalAmount`는 쿠폰이 없으면 `100000`, 쿠폰이 있으면 `95000.00`(할인액의 scale을 따라감),
재조회는 항상 `100000.00`(DB `decimal(38,2)`). 이 차이는 같은 스택 안에서도 요청 종류에 따라 생기므로 A/A에서는 양쪽이 같다.

### L7. Kafka: 스택별 브로커, 후속 처리 전부 Order consumer, 재시도 없음

**결정**
- 브로커는 **스택마다 하나**(KRaft 단일 노드, `apache/kafka:4.3.1` digest 고정). 스택 네트워크의 `kafka`로 찾는다.
  토픽 `payment-events`(파티션 1)와 consumer group `order-service`는 두 스택에서 이름이 같다.
- 데이터는 tmpfs. 초기화 = 브로커 재생성(토픽·offset·group이 모두 빈다). 토픽은 `deploy/compose/kafka/init-topics.sh`가
  만들고 healthy = "토픽까지 준비됨". 자동 토픽 생성은 끈다. `reset.sh`는 Order consumer가 새 브로커에서 파티션을 받을 때까지 기다린다.
- 결제 확정 후속 처리 셋(주문 상태 변경, PAYMENT_COMPLETED_SUCCESS 감사 로그, 알림)을 **모두 Order consumer**로 옮긴다.
  감사 로그 본문은 Payment가 직렬화해 이벤트에 싣는다. consumer는 재시도하지 않는다.

**근거**
- 스택별 브로커: new 격리 규칙(hyeonuk-dev `deploy/k8s/new/networkpolicy.yaml`, `istio/sidecar-new.yaml`)에 Kafka 자리가 없다.
  공유 브로커면 합칠 때 Kafka를 verify ns에 두거나 팀원 파일을 고쳐야 한다. 스택별이면 k8s에서도 각 ns 안에 두면 되고,
  토픽·group 이름이 같아 legacy/new env가 완전히 같아진다(L2). 대가는 브로커 1개분 메모리(약 300~400MB).
- 후속 처리 전부 consumer: 원본 동기 흐름의 외부 호출 순서가 그대로 보존된다(한 스레드에서 순서대로).
  감사 로그만 Payment에 남기면 Payment와 consumer가 동시에 외부 호출을 해 journal 순서가 매번 달라질 수 있다.
  없는 주문에서 감사 로그가 나가지 않는 점도 원본과 같다.
- 재시도 없음: 상태 변경 뒤 실패해 재전달되면 이력·감사 로그·배송 요청이 중복된다.

**실측에서 나온 것**
- Boot 4(Jackson 3)는 기본 JSON 직렬화가 **속성 알파벳순**이다. payment에서 order로 복사한 `NotificationRequest`가 그대로면
  알림 본문 키 순서가 바뀌었다. 전체 필드 생성자가 있는 DTO(`AuditLogRequest`)는 생성자 파라미터 순서를 따라 영향이 없었다.
  `@JsonPropertyOrder`로 원본 순서를 고정해 전환 전후 journal이 바이트 단위로 같아졌다.
  → New의 "정상 변경" 실험(Payment를 Boot 4로 올리기)에서 **JSON 키 순서 차이**가 생긴다는 뜻이다. Normalization에 키 순서 정규화가 필요하다(v10.1 §5.3).
- 앱을 재시작하지 않아도 브로커 재생성 후 consumer가 약 2초 만에 다시 붙는다(`auto-offset-reset: earliest`로 리셋 직후 이벤트를 놓치지 않음).

**대안**
- 공유 브로커 + 스택별 토픽(프롬프트 원안) — 위 격리 규칙 문제로 배제.
- 감사 로그는 Payment에 남기기 — 호출 순서 비결정성으로 배제.
- 이벤트 value를 Spring JsonSerializer로 — Boot 3(Jackson 2)와 Boot 4(Jackson 3)의 타입 헤더·직렬화 차이를 피하려고 문자열로 보낸다.
