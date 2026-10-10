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

### L3. S0 = MySQL·Kafka 컨테이너 재생성(tmpfs) + init SQL/토픽 + 앱 재시작

**결정**
MySQL과 Kafka 데이터 디렉터리를 tmpfs에 둔다. `deploy/compose/reset.sh`는
1. MySQL·Kafka 컨테이너를 `--force-recreate`로 새로 만들고 healthy(`mysqladmin ping -h 127.0.0.1`(D3) / 토픽 존재)까지 기다린다.
2. **앱 컨테이너를 재시작**한다(같은 컨테이너라 네트워크 주소가 유지되어 nginx upstream이 그대로 유효).
3. Order consumer가 파티션을 받고 같은 member로 3초 연속 유지될 때까지 기다린다.
4. WireMock journal을 비운다.

스키마는 Hibernate `ddl-auto=update`로 한 번 만든 뒤 `mysqldump --no-data`로 떠서
`deploy/compose/mysql-initdb/<service>/01-schema.sql`에 고정했다(`tools/dump-schema.sh`).

**근거**
k8s의 emptyDir + `strategy: Recreate` + `rollout restart`(D4)와 같은 의미다. TRUNCATE 방식은
"초기화 주체가 앱/스크립트 둘"이 되고 시퀀스 리셋을 테이블마다 따로 챙겨야 한다.

처음(Step 2~5)에는 앱을 재시작하지 않았다. DB 커넥션은 Hikari가 빌려줄 때 검증해 끊긴 것을 버리고 다시 맺어서 문제가 없었다.
**Step 6에서 앱 재시작을 추가했다.** 이유:
- Kafka 브로커를 재생성하면, 재시작하지 않은 consumer는 "할당 → 토픽 ID 변경 감지 → revoke·UNKNOWN_MEMBER_ID → 재할당"을
  한두 번 더 거친다(실측 타임라인). 리셋 스크립트가 첫 할당에서 끝나면 직후 요청이 이 과도기와 겹친다.
  실제로 시나리오 1회가 24/26으로 흔들렸다(같은 코드로 이어진 4회는 26/26). 결정성을 클라이언트 재연결 타이밍에 맡기지 않는다.
- 6-5의 Evidence `seq` 같은 앱 메모리 상태가 run마다 1부터 시작해야 legacy/new를 맞출 수 있다.
- 재생성된 DB·브로커의 IP가 바뀌어도 앱이 오래된 DNS 캐시(JVM 기본 30초)를 쓰지 않는다.

**실측**
- 앱 재시작 방식: 리셋 46초. 스택마다 consumer 할당 정확히 1회, 리셋 후 20초 동안 rebalance 0회.
  시나리오 5회 연속 26/26, 5회의 응답·외부 호출·DB가 모두 동일.
- (이전) 앱 재시작 없이 MySQL만 재생성: 11초, 첫 요청에서 Hikari가 끊긴 커넥션을 버리고 재연결(`Failed to validate connection`).

`mysqldump`는 테이블을 이름순으로 내보내 FK 참조 순서와 어긋나므로(`coupon_usage` → `coupons`)
init SQL을 `SET FOREIGN_KEY_CHECKS=0/1`로 감쌌다.

**대안**
- `TRUNCATE ... RESTART IDENTITY`(사전 검증에서 Postgres로 사용) — MySQL에는 `RESTART IDENTITY`가 없고, 위 이유로 배제.
- 앱 재시작 없이 consumer 안정 대기만 강화 — 토픽 ID 변경 rebalance가 언제 일어날지(metadata 갱신 시점)에 달려 있어 보장이 없다.

### L4. MySQL은 메모리만 줄여서 띄운다

**결정**
`--performance-schema=OFF --innodb-buffer-pool-size=64M --innodb-redo-log-capacity=8M`. 그 외(문자셋, collation, 격리 수준)는 기본값.
Docker Desktop 메모리는 8GB → 12GB로 올렸다(Step 6 사전 작업).

**근거**
Docker 메모리 8GB에서 베이스라인 단계에 MySQL 6 + JVM 6 + Kafka + WireMock 2 + 관측 스택을 함께 띄워야 한다.
세 옵션은 SQL 의미에 영향이 없다. redo log는 기본 100MB가 tmpfs(=메모리)에 올라가므로 최소값 8MB로 줄였다.

**실측(Step 6-0b)**: MySQL 1개의 tmpfs 사용량 209MB → 117MB. 두 스택(MySQL 6, 앱 6, Kafka 2, WireMock 2) 합계 약 5.5GB / 12GB.

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
  만들고 healthy = "토픽까지 준비됨". 자동 토픽 생성은 끈다. `reset.sh`는 브로커 재생성 후 앱을 재시작하고 Order consumer가 안정적으로 할당될 때까지 기다린다(L3).
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
- 앱을 재시작하지 않으면 브로커 재생성 후 consumer가 약 2초 만에 다시 붙지만, 그 뒤 rebalance가 한두 번 더 일어난다. Step 6에서 리셋에 앱 재시작을 추가했다(L3).

**대안**
- 공유 브로커 + 스택별 토픽(프롬프트 원안) — 위 격리 규칙 문제로 배제.
- 감사 로그는 Payment에 남기기 — 호출 순서 비결정성으로 배제.
- 이벤트 value를 Spring JsonSerializer로 — Boot 3(Jackson 2)와 Boot 4(Jackson 3)의 타입 헤더·직렬화 차이를 피하려고 문자열로 보낸다.

### L8. 두 번째 스택(new)은 같은 템플릿·같은 이미지, 전달은 nginx 경로별 mirror

**결정**
- compose의 서비스 정의를 `x-*` 템플릿으로 묶고 legacy/new가 공유한다. 스택마다 다른 것은 네트워크뿐이다.
  new는 legacy와 **같은 이미지**를 쓴다(A/A). new 네트워크는 `internal: true`(외부로 나갈 수 없음).
- `reset.sh`는 기본으로 두 스택을 함께 초기화한다(MySQL 6 + Kafka 2 재생성, consumer 재할당 대기, WireMock journal 2개 비움).
- nginx(`deploy/compose/nginx/default.conf`, 호스트 8000): `/orders/`·`/coupons/`·`/payments/`만 받아 legacy로 route,
  new로 mirror. 그 밖의 경로는 404.
  - 헤더는 복사만 한다(ID 생성 없음). Host는 `proxy_set_header Host $http_host`로 원본을 양쪽에 그대로 보낸다(D8).
    nginx 기본값은 Host를 upstream 이름으로 바꿔 legacy/new가 달라진다.
  - nginx는 두 네트워크에 붙으므로 짧은 이름(`order`)이 모호하다. 서비스 이름(`order-legacy`, `order-new`)으로 찾는다.
  - 호스트 포트 8000: 8080은 루트 Phase 0 PoC가 쓴다.

**근거**
- 템플릿 공유로 "설정 차이가 관측 차이로 섞이는" 경우를 구조적으로 막는다. 실측으로 서비스 3개의 env·이미지 ID가 legacy/new 동일.
- nginx는 Istio VirtualService가 하는 일(route/mirror/헤더 복사/Host 유지)만 한다. 합칠 때 이 파일만 VirtualService로 바뀐다.

**실측(Step 6-1, 6-2)**
- 두 스택에 데이터를 만든 뒤 `reset.sh`: 6개 DB 0건, 다음 ID 1, 두 Kafka end offset 0, 두 journal 0
  (앱 재시작 없는 방식 18초 → 앱 재시작을 추가한 뒤 46초, L3).
- new 격리: new에서 `https://example.com` 호출 실패(curl exit 6, 이름 해석 불가), legacy는 200.
  k8s NetworkPolicy(D6 ②)는 DNS를 허용해 "이름은 풀리는데 연결 타임아웃(exit 28)"이므로 실패 서명이 다르다. 격리라는 결과는 같다.
- nginx 경유 체인(주문 생성 → legacy 응답의 `transactionId`로 결제 확정 → 조회): 클라이언트는 legacy 응답만 받고,
  두 스택의 DB(orders·이력·상품·결제·쿠폰 사용)와 WireMock 외부 호출 12건(메서드·URL·본문)이 해시까지 동일했다.
  결정적 PG id(L6) 덕분에 legacy가 발급한 `order_1`이 new에서도 같은 결제를 가리킨다.

**대안**
- new에 별도 compose 파일 — 정의가 두 벌이 되어 어긋날 수 있다.
- nginx에서 짧은 이름 + 네트워크별 resolver — 설정이 복잡해지고 얻는 것이 없다.

### L9. 요청 ID 전파는 OTel Java agent(실행 시 주입), Collector·Jaeger는 팀원과 같은 구성

**결정**
- OTel Java agent 2.31.1을 digest 고정 이미지에서 `otel-agent-init`이 공유 볼륨으로 복사하고, 앱은 `JAVA_TOOL_OPTIONS`로 붙인다(hyeonuk-dev D5).
  앱 이미지와 Legacy 코드는 바뀌지 않는다.
- agent env는 hyeonuk-dev `deploy/k8s/base/order.yaml`과 같다(OTLP gRPC, `always_on`, metrics/logs 끔,
  propagators `tracecontext,baggage,b3,b3multi`). 스택마다 다른 env는 `OTEL_SERVICE_NAME`(`order-legacy`/`order-new` …)과
  `OTEL_RESOURCE_ATTRIBUTES=service.namespace=legacy|new`뿐이다.
- 서버 span에 요청 헤더 `X-Replay-Request-Id`, `X-Run-Id`, `X-Session-Id`, `baggage`, `Host`를 기록한다
  (`OTEL_INSTRUMENTATION_HTTP_SERVER_CAPTURE_REQUEST_HEADERS`).
- Collector(`deploy/compose/otel/collector.yaml`: OTLP → batch → Jaeger)와 Jaeger v2는 같은 digest. Collector는 두 스택 네트워크에 붙고,
  Jaeger는 별도 `observability` 네트워크(UI `localhost:16686`).
- nginx는 upstream 이름을 요청 시점에 Docker DNS로 해석한다(`resolver 127.0.0.11`). 앱 컨테이너가 재생성되어 IP가 바뀌어도
  nginx를 다시 띄울 필요가 없다.

**근거**
- 코드 변경 없이 Feign·Kafka 헤더로 baggage가 전파된다. Coupon의 `FeignConfig`처럼 인터셉터를 직접 짤 필요가 없었다.
- 팀원 구성과 같아야 합칠 때 compose env가 k8s Deployment env로 그대로 옮겨진다.

**실측(Step 6-3, 6-4)** — nginx 경유 체인(쿠폰 주문 R000001 → verify R000002 → 조회 R000003)
- Boot 4.0.3(order)·4.0.5(coupon)·3.4.2(payment) 모두 agent 2.31.1이 오류 없이 붙었다(`opentelemetry-javaagent - version: 2.31.1`).
- 요청 1건 = 스택마다 trace 1개. R000001은 order·coupon·payment span 53개가 한 trace(B1의 Coupon→Order 역조회 span도 보인다).
- 진입 서비스 서버 span: `X-Replay-Request-Id`가 legacy·new 모두 도착. Host는 양쪽 `localhost:8000`(D8 확인).
  Feign으로 호출된 coupon·payment 서버 span에는 X-Replay-Request-Id가 없고 `baggage: replayRequestId=R000001,runId=smoke`가 있다
  → Evidence는 baggage에서 replayRequestId를 읽어야 한다.
- Kafka: `PaymentCompleted` 레코드 헤더에 `baggage: replayRequestId=R000002,runId=smoke`(+ traceparent, b3)가 실린다.
  payment `publish`와 order `process` span이 같은 trace이고, consumer가 낸 외부 호출 4건(감사·배송·감사·알림)에도 같은 baggage가 붙는다.
- span 1개짜리 trace는 앱 기동 시 Hibernate의 DB 메타데이터 조회(`INFORMATION_SCHEMA.KEYWORDS` 등)뿐이다. 요청과 무관하다.
- agent를 붙여도 시나리오 26/26, 응답·DB·외부 호출(메서드·URL·본문)이 붙이기 전과 같다.
  외부 호출과 Kafka 레코드에는 `traceparent`·`baggage`·`b3` 헤더가 새로 붙는다(스택마다 trace id가 달라 정규화 대상).

**대안**
- Feign 인터셉터 + Kafka 헤더 직접 전파(계측 등급 코드) — agent가 동작해 필요 없었다.
- 앱 이미지에 agent 포함 — D5에서 기각된 방식.
