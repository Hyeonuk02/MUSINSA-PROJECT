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
1. **앱 컨테이너를 멈춘다.**
2. MySQL·Kafka 컨테이너를 `--force-recreate`로 새로 만들고 healthy(`mysqladmin ping -h 127.0.0.1`(D3) / 토픽 존재)까지 기다린다.
3. **앱을 다시 시작**한다.
4. Order consumer group이 `Stable`, 멤버 1개, 파티션 할당 상태로 2회 연속 확인될 때까지 기다린다.
5. WireMock journal을 비운다.

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

처음 구현(Kafka 재생성 → 앱 restart)에도 구멍이 있었다. 재생성과 restart 사이 몇 초 동안 **옛 앱의 consumer가 새 브로커 그룹에 먼저 들어가고**,
restart로 죽으면서 그룹을 깔끔하게 떠나지 못했다. 새 consumer는 브로커가 옛 멤버의 세션 만료를 기다리는 동안(실측 22초) 합류하지 못했고,
리셋 스크립트의 "같은 member 3초 유지" 판정은 죽은 옛 멤버를 보고 통과했다. 그 결과 체인 도중 할당이 일어나 verify의 consumer 처리가
3초 늦어졌고, 그 사이 조회·취소가 먼저 처리됐다. 그래서 순서를 **앱 정지 → 재생성 → 앱 시작**으로 바꾸고 판정을
"group Stable + 멤버 1개 + 파티션 1개"로 강화했다.

**실측**
- 앱 재시작 방식(최초): 리셋 46초. 스택마다 consumer 할당 1회. 시나리오 5회 연속 26/26, 5회 결과 동일.
- 앱 정지 → 재생성 → 시작(최종): 리셋 약 53초. 앱 시작 후 약 0.3초 만에 그룹 합류·할당 1회.
  nginx 경유 체인에서 verify의 consumer 처리가 바로 다음 순번(seq 3)으로 들어가고 legacy/new seq 순서가 같다.
- (이전) 앱 재시작 없이 MySQL만 재생성: 11초, 첫 요청에서 Hikari가 끊긴 커넥션을 버리고 재연결(`Failed to validate connection`).

`mysqldump`는 테이블을 이름순으로 내보내 FK 참조 순서와 어긋나므로(`coupon_usage` → `coupons`)
init SQL을 `SET FOREIGN_KEY_CHECKS=0/1`로 감쌌다.

**대안**
- `TRUNCATE ... RESTART IDENTITY`(사전 검증에서 Postgres로 사용) — MySQL에는 `RESTART IDENTITY`가 없고, 위 이유로 배제.
- 앱 재시작 없이 consumer 안정 대기만 강화 — 토픽 ID 변경 rebalance가 언제 일어날지(metadata 갱신 시점)에 달려 있어 보장이 없다.
- 앱 restart(정지 없이) — 위 "옛 멤버" 문제로 배제.

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

### L10. Evidence: 서비스 내부 계측 + 앱 밖 수집, Store는 Python·SQLite, Store POST는 별도 trace

**결정**
- 앱 안(`legacy/prince-mart/evidence/`, LEGACY_CHANGES L-I2): HTTP 요청 1건·Kafka 레코드 처리 1건마다 Evidence 1건.
  응답, DB 접근(StatementInspector, (동작·테이블·횟수) + 원문), Feign 호출 순서, 발행 이벤트, 예외 class, 처리 시간(참고 지표).
  replayRequestId는 `X-Replay-Request-Id` 또는 baggage에서 읽는다(OTel API 없이 헤더 문자열 파싱).
- 앱 밖(`deploy/compose/tools/collect.py`): run 뒤 스택별 WireMock journal을 baggage로 묶어 `kind=external`, Kafka 토픽을 처음부터 읽어
  `kind=event`로 같은 키에 넣는다.
- Evidence Store v0(`baseline/evidence-store/`): Python 표준 라이브러리 + SQLite 파일. 두 스택이 공유하고 호스트 8099.
  v10.1 §11-2(Store 저장소 파일 vs 경량 DB)가 미결이라 **임시 선택**이다. 엔드포인트와 export 형식이 같으면 바꿔도 비교 엔진은 영향이 없다.
- **Store POST는 억제하지 않고 비즈니스 trace와 분리한다.** 요청 스레드는 큐에 넣기만 하고 전용 스레드가 보낸다.
  OTel agent는 큐를 거친 작업에 context를 잇지 않으므로 POST는 별도 trace가 된다. 분석(Observed edge)은 replayRequestId가 찍힌
  서버 span이 있는 trace만 쓰고, 안전장치로 목적지가 evidence-store인 span을 버린다. `X-Evidence-Internal: true`는 그대로 붙인다.
- 스키마는 [legacy-evidence-schema-v0.md](legacy-evidence-schema-v0.md)에 고정한다. 키 `(runId, replayRequestId, stack)` + service·kind·seq.

**근거**
- k8s + Istio에서는 앱에서 억제해도 Store POST의 Envoy span이 남는다(나가는 sidecar, Store sidecar). 앱 억제(`InstrumentationUtil.suppressInstrumentation`,
  OTel internal API)에 기대면 compose와 k8s 결과가 달라지고 분석 단계 필터링은 어차피 필요하다. 분리 방식은 두 환경에서 같은 결과(별도 trace)이고
  Envoy span도 그 별도 trace에 붙는다. 헤더가 아니라 replayRequestId·목적지로 거르므로 팀원 Telemetry에 customTags가 필요 없다.
- 공통 코드를 복사본으로 두되 원본 하나 + `sync.sh --check`로 같은 바이트를 보장한다. Jackson을 쓰지 않아 Boot 3/4 차이가 Evidence에 섞이지 않는다.
- 외부 호출을 앱 Feign 기록과 WireMock journal 둘로 보는 이유: Feign 기록은 내부 서비스 호출까지 포함한 호출 순서, journal은 Feign이 아닌
  호출(가짜 PG RestClient)까지 포함한 외부 의존성의 실제 수신 내용이다.

**실측(Step 6-5~6-7)** — nginx 경유 체인(쿠폰 주문, verify, 조회, 취소, 재취소), 요청마다 양쪽 Evidence 기대 건수까지 대기
- 요청별 Evidence 건수 legacy = new: R000001 5건(order place, coupon validate, coupon use, B1 역조회, payment process), R000002 2건(verify + consume),
  나머지 1건. 앱 Evidence 전부 `X-Evidence-Internal` 포함. `collect.py`: 외부 호출 14건·이벤트 1건, baggage 없는 호출 0건.
- 요청 하나가 replayRequestId로 order·coupon·payment·WireMock·Kafka에 걸쳐 묶이고 legacy/new가 같은 구성으로 짝지어진다(Step 6 완료 기준).
- Error Path: B1 coupon `/use` 404 = `ResourceNotFoundException`, B6 재취소 404 = `IllegalStateException`.
- 완료 대기 시간: 요청당 약 5~135ms(verify는 consumer 처리 포함 134ms).
- Store POST trace 분리: 최근 3분간 비즈니스 trace 20개, Store POST trace 40개(모두 span 1개), 겹침 0.
- 계측 전후 시나리오 26/26, 응답·DB·외부 호출 동일. 세 서비스 복사본 동일(`sync.sh --check`).

**대안**
- `opentelemetry-api` + suppressInstrumentation — 위 이유로 배제.
- Collector filter processor로 Store span 제거 — core Collector 이미지에 없고(contrib 필요), 팀원 구성과 달라진다.
- 서비스별로 계측 코드를 따로 작성 — 어긋날 수 있다.

### L11. 베이스라인 도구는 `baseline/`에 별도로, 형식은 팀원 Phase 2 계약에 맞춘다

**배경**
hyeonuk-dev에 Phase 2 계획(v2)과 2.1 구현이 올라왔다(팀원 order 앱 + business key). 루트의 `corpus/`, `k6/`, `engine/`,
`evidence-store/`, `runs/`, `docs/evidence-schema-v0.json`을 만들 계획이다. 이 트랙은 Prince Mart Legacy(베이스라인)를
**별개로 구축**하는 일이고, 팀원 설계는 합치기 쉽게 참고만 한다.

**결정**
- 이 트랙의 도구는 모두 `baseline/` 아래에 둔다: `baseline/evidence-store/`(Step 6에서 루트에 올린 것을 옮김),
  `baseline/corpus/`, `baseline/k6/`, (Step 8) `baseline/engine/`, 결과는 `baseline/runs/`(gitignore).
  스키마 문서는 `docs/legacy-evidence-schema-v0.md`.
- 형식은 팀원 계약(phase2-plan 2.2~2.6)에 맞추고 필요한 것만 확장한다.
  - Evidence 공통 필드: `schemaVersion`, `sessionId`, `version`, `request.path`, 소문자 헤더 맵, `bodyHash: "sha256:..."`,
    `response.headers/bodyHash`, ISO 시각 + `arrivedNano/completedNano`, `capturedAt` (계측 코드 L-I2 수정)
  - Store API: `exists` 200/404, `count&stack`, `export` 배열·`&stack`, `DELETE /runs/{runId}`. 같은 Evidence 재전송은 덮어씀
  - corpus: `{version, sessions[{id, user, requests[{id, method, path, body, headers}]}]}` JSON + 확장 `userId`, `capture`, `expect`
  - 결과 배치: `runs/<runId>/legacy.json·new.json·k6-summary.json·run-meta.json`
  - degraded 정책: 완료 대기 타임아웃이면 그 세션의 남은 요청을 건너뜀

**근거**
같은 루트 경로를 쓰면 합칠 때 `evidence-store/Dockerfile`, `corpus/corpus-v1.json`, `k6/run.sh` 등이 충돌하고 같은 도구가 두 벌 생긴다.
형식이 같으면 합칠 때는 "어느 구현을 남길지"만 고르면 된다. Store 저장소는 팀원 계획(파일, Phase 2에서 DB 금지)과 다르게
SQLite다(L10, v10.1 §11-2 미결). API가 같아 바꿔도 k6·엔진은 영향이 없다.

### L12. corpus·k6·run script: 세션 독립, 양쪽 스택 완료 대기, flush barrier에서 consumer lag

**결정**
- corpus(`baseline/corpus/corpus-v1.json`): `scenarios.py` 26항목을 독립 세션 11개, 요청 28건으로 옮겼다.
  세션마다 다른 사용자(201~211)와 **세션 전용 쿠폰**(`S02-FIX5000` 등, coupon S0 시드에 추가)을 쓴다.
  쿠폰 사용 한도 판정은 쿠폰 전체 사용 수를 세므로 쿠폰을 공유하면 세션이 서로 영향을 준다.
  체인 값(`orderId`, `transactionId`)은 `capture`로 legacy 응답에서 이어받고 `${이름}`으로 쓴다(business key 없음, L1).
  `expect.evidence` = 스택당 기대 앱 Evidence 건수(쿠폰 없는 주문 2, 할인 쿠폰 주문 5, 무효 쿠폰 주문 3, verify 2, 직접 쿠폰 사용 2, 그 밖 1).
  `validate.py`가 구조·id 유일·사용자/쿠폰 비공유·변수 바인딩·실행 시점 토큰을 검사한다.
- k6(`baseline/k6/run.js`, `grafana/k6` v2.3.0 digest 고정): VU=1, 세션 순서대로. 헤더 `X-User-Id`, `X-Replay-Request-Id`,
  `X-Run-Id`, `X-Session-Id`, `baggage: replayRequestId,runId,sessionId`. 요청마다 **legacy·new 두 스택의 Evidence가 `expect.evidence`에
  도달할 때까지**(50ms 간격, 10초) 기다린다. compose의 legacy 네트워크에서 nginx로 보낸다(외부 클라이언트 위치).
- consumer offset: `enable.auto.commit = false`(Spring Kafka 기본, 기동 로그로 확인). consume Evidence는 처리 직후(afterRecord)에 남으므로
  "Evidence 도착 = 처리 완료"다. offset 커밋은 그 뒤라 **consumer lag 0은 flush barrier에서 한 번** 확인한다(k6는 HTTP만 할 수 있다).
- run script(`baseline/k6/run.py`): reset → 조건 해시·run 정보 등록 → k6 → flush barrier(스택별 count == 보낸 요청의 기대 합 + lag 0)
  → `collect.py` → export·DB 덤프. 비교 유효 조건 해시 = hash(corpus, S0 init SQL+토픽, WireMock 매핑, 고정 시각, 이미지 ID, Normalization 규칙).

**근거**
- Kafka 때문에 "new 도착"만 보는 팀원 방식(`exists?stack=new`)으로는 legacy 쪽 consumer 처리 전에 다음 요청이 갈 수 있다(Step 6에서 실측:
  consumer 지연 동안 조회·취소가 먼저 처리됨). 요청별 기대 건수를 양쪽에서 기다리면 두 스택 모두 비동기 처리까지 끝난 뒤 다음 요청을 보낸다.

**실측(Step 7, run `smoke-7`)**
- corpus 검증 오류 0. 28/28 전송, legacy 응답 status 전부 기대값, degraded 0.
- 완료 대기: 요청당 최대 168ms, 합 1.7초. barrier: legacy·new 앱 Evidence 65/65, lag 0.
- collect: 스택마다 외부 호출 127건(21요청), 이벤트 3건, baggage 없는 호출·이벤트 0.
- 순서 민감 케이스가 양쪽 같음: B4(취소 후 verify) CONFIRMED/PAID, B5(verify 후 취소) CANCELLED/PAID.
- 소요: 리셋 58초, k6 6초, 전체 79초.

**대안**
- corpus를 YAML로 — k6가 YAML을 읽지 못하고 Python 표준 라이브러리에도 없다. 팀원 계약도 JSON.
- 요청마다 lag 0 확인 — k6에서 불가, consume Evidence로 같은 의미를 얻는다.

### L13. 비교 엔진: export만 입력, B0/B1, 짝 맞춤은 요청 안 순서(norm-v1.1)

**결정**
- `baseline/engine/`의 비교 도구는 run export(`legacy.json`, `new.json`, `db-*.json`, `run-meta.json`, `k6-results.jsonl`)만 입력으로 받는다.
- B0 = 식별 필드(`stack`)만 빼고 그대로 비교, 차이를 범주(trace 헤더·시각·소요 시간·그 밖)로 센다. B1 = `normalization.json` 적용 후 비교.
- 짝 맞춤 키는 `(replayRequestId, service, kind, 그 요청 안에서 몇 번째)`. 서비스 단위 순번(`seq`)과 Kafka `offset`은 요청 단위 비교에서 뺀다(위치 값).
  실행 순서는 서비스별 처리 순서 검사가 따로 본다.
- 자동 증가 ID 마스킹은 A/A에서 끈다(켜면 결정성 깨짐을 숨긴다).

**근거**
- 실패 경로 실측(F1)에서 `seq`를 키로 쓰자 consume 1건 누락이 그 뒤 order Evidence 전체를 밀어 Undelivered 27 / Unexpected 18로 과다 보고했다
  (실제 누락 9). New 비교에서도 내부 호출 하나가 늘거나 줄면 이후 전체가 차이로 쏟아져 진짜 차이가 묻힌다.
  요청 안 위치로 짝지은 뒤 F1 보고가 실제 누락과 정확히 일치했고 aa-001 결과는 그대로였다.

**대안**
- hyeonuk-dev의 hopPath(`0.h1`, `0.e1`) 키 — 부모·자식 호출 관계까지 담아 더 정밀하다. 홉 경로 헤더를 서비스 사이에 전파하는 계측이 필요해
  이번에는 요청 안 위치로 충분한지 먼저 본다(E3에서 재검토).

### L14. Evidence v1: 요청 안 하나의 seq 타임라인과 트랜잭션 경계

**결정**
요청 하나 안에서 SQL·Feign 호출·이벤트 발행·트랜잭션 경계(`COMMIT_BEGIN`, `COMPLETED`)가 같은 카운터로 seq를 받는다(LEGACY_CHANGES L-I3).
트랜잭션 경계는 Spring `TransactionExecutionListener`를 BeanPostProcessor로 매니저에 붙여 코드 변경 없이 잡는다.

**근거**
hyeonuk-dev Phase 3 결과(findings O11): 응답 + SQL 비교(B1)만으로는 멱등성·발행 시점·롤백·중복 호출 결함 13 pair를 놓쳤다.
"커밋 전 발행"은 콜백 순서가 아니라 `publish.seq < COMMIT_BEGIN.seq`로 판정해야 한다(O9). 같은 축을 이 트랙에도 둔다.
실측: payment verify는 Legacy에서 원래 커밋 전에 발행한다(PUBLISH 3 → COMMIT_BEGIN 4 → UPDATE 5). 팀원이 F3 결함으로 주입한 패턴이
이 Legacy에서는 기준 동작이다. order 주문 생성은 `coupons/use`(9)를 커밋(14) 전에 호출한다 — B1의 원인이 타임라인에 보인다.

**대안**
- `TransactionSynchronization`을 요청마다 등록 — 트랜잭션을 여는 코드에 손을 대야 한다.
- Hibernate 이벤트 리스너 — JPA 범위만 보인다(트랜잭션 이름·롤백 결과가 약하다).

### L15. corpus v1.1: flow·split, 빈 곳 보강

**결정**
- v1의 세션 11개는 그대로 두고 세션마다 `flow`(order·order-coupon·coupon)와 `split`(learn·eval)을 붙였다(hyeonuk-dev corpus v2와 같은 의미·규칙:
  flow마다 learn·eval 각 1개 이상). learn 4(S01·S02·S10·S11), eval 10.
- 세션 3개 추가: S12(사용자당 주문 2건 → history·my-orders, 시각 동점), S13(같은 결제 재확정, Legacy 멱등성 없음),
  S14(쿠폰 API 직접 호출). 세션 전용 쿠폰 `S14-FIX5000`을 S0 시드에 추가. 14세션·38요청, 스택당 앱 Evidence 80.
- v1 결과(aa-001)는 보존한다. run script는 `--corpus`로 v1을 다시 돌릴 수 있다.

**근거**
규칙은 learn에서만 만들고 지표는 eval로 센다(팀원 방식). 결정론적 재생이라 run 반복은 새 표본이 아니므로 세션 단위로 홀드아웃한다.
S13은 멱등성 결함(팀원 F1에 대응) 주입 자리, S12는 L5의 동점 정렬이 드러나는 자리다.

### L16. 엔진 정렬 방침: 각자 완성하되 평가 입력·지표는 팀원과 맞춘다

**결정** (2026-11-02, hyeonuk-dev `30e9c2c` Phase 3·4 문서를 읽고)
- 두 엔진은 각자 완성한 뒤 결과를 비교해 고르거나 장점을 합친다. 그래서 형식은 맞춘다:
  `fault-expectations.json`(run 전에 기대 판정을 커밋), `verdict.json`(pair별 판정·위반·적용 규칙, 요약),
  Rule YAML과 uid(match에 요청·세션 ID 금지), learn/eval 분리, 지표 정의와 arm(B0 / B1 / C_norules / C_rules).
- 결함 New 버전은 브랜치가 아니라 `baseline/faults/PF<n>.patch` + Docker 빌드 인자로 만든다(이미지 `prince-mart/*:PF<n>`).
- **응답 status 변경은 항상 Contract Violation**이고 사전 승인 규칙으로 덮지 않는다. 대신 변경 내역(엔드포인트, legacy/new status, 예외 class)을
  남기고, Human Review가 CV uid마다 처분 `accept`(의도된 계약 변경) / `fault`(결함)를 붙인다. 판정은 CV 그대로이고 지표에서 둘을 나눠 센다.
- 팀원 쪽에서 가져올 것: 트랜잭션 경계·타임라인(L14), SELECT 수 변화는 기본 UNC이고 `max_selects` 선언 시에만 CV,
  세션 범위 위반은 Legacy와 다르게 기여한 pair에만 귀속.

**근거**
- 평가 입력과 지표가 같아야 두 엔진을 같은 기준으로 비교하고 장점을 빼 올 수 있다.
- 브랜치를 만들지 않는 것은 branch-park만 수정한다는 작업 원칙과 리소스 때문이다.
- status 변경에 사전 승인 규칙을 두면 "어떤 status 변경까지 개선인가"에서 엣지 케이스가 생긴다(B6 수정 404→409/403 등).
  판정은 보수적으로 두고 처분으로 구분하면 판정 기준이 흔들리지 않는다.

**대안**
- 사전 승인 규칙으로 status 변경을 IMP 인정 — 위 엣지 케이스로 배제.
- 팀원 엔진을 그대로 사용 — Prince Mart의 여러 서비스·Kafka·실제 Legacy 버그를 다루는 축이 팀원 엔진에 없어 이 트랙에서 먼저 확인한다.

### L17. 완료 대기를 고정 건수에서 스택별 폐포(closure)로

**결정** (2026-11-02, E2)
- k6의 요청별 대기와 run.py barrier가 corpus의 `expect.evidence` 건수 대신 **스택이 스스로 선언한 하위 처리**로 완료를 판단한다.
  스택 하나의 완료 = 진입 Evidence(`x-replay-request-id`를 받은 http)가 있고, 도착한 Evidence의 `outbound` 중 응답을 받은
  내부 서비스 호출(ORDER/COUPON/PAYMENT-SERVICE) 수와 `events` 수만큼 서비스별 하위 http·consume Evidence가 도착함.
  barrier는 여기에 두 스택 consumer lag 0을 더한다. 같은 규칙이 `k6/run.js`와 `k6/run.py`의 `closure()` 두 곳에 있다.
- legacy는 corpus `expect.evidence`와도 대조해 `legacyCountOk`(k6 결과)·`legacyCountMismatch`(barrier)로 남긴다.
- run-meta에 떠 있는 컨테이너의 스택별 이미지(`stackImages`)와 `newVersion`, arm(A/A 또는 `fault <버전>`)을 기록한다.
  유효성 해시의 images는 legacy 스택만 덮는다 — 조건이 같고 arm만 다른 run(A/A와 PF<n>)이 같은 해시를 갖게.

**근거**
- 결함 버전은 하위 호출·이벤트 수를 바꾼다(PF2는 consume이 없고 PF10은 coupon use가 사라진다). 고정 건수로 기다리면
  new가 타임아웃 → degraded → 남은 요청을 건너뛰어, 결함이 '전달 실패'로 보이고 판정 대상이 사라진다.
- 팀원의 2단계 settle(부모가 선언한 hop을 기다림)과 같은 발상이다. 선언하지 않은 하위 처리는 기다리지 않으므로
  "부르지 않은 것"과 "아직 안 온 것"이 구분된다.
- aa-003(재빌드한 legacy 이미지, A/A 1회): 38/38, barrier ok, legacy 80/80 일치, settle 최대 224ms(aa-002 217ms), B1 0.
  offline으로 aa-002-1의 38개 요청 모두 closure 완료, consume 하나를 빼면 미완료로 판정됨을 확인.

**대안**
- 결함별로 기대 건수를 corpus에 따로 둠 — 기대 판정과 대기 조건이 섞이고, 사전 등록 전에 결함 결과를 알아야 해서 배제.

### L18. 결함 카탈로그 PF<n>와 기대 판정 사전 등록

**결정** (2026-11-02, E2)
- 결함 9개(PF1~5, PF7~10; PF6은 마지막에 따로)를 `baseline/faults/PF<n>-<svc>.patch`로 두고 기대 판정을
  `baseline/faults/fault-expectations.json`에 **결함 run 전에 커밋**한다. 기대는 패치와 A/A Evidence(aa-003)만 보고 정했다.
- pair 키는 `<replayRequestId>/<service>.<kind>.<n>`(compare.py pair_index). 한쪽 스택에만 생기는 pair는 `legacyOnly`/`newOnly`로 따로 둔다.
- CV에는 기대 처분(`cvDisposition`: fault | accept)을 같이 등록한다. 승인된 개선 중 status를 바꾸는 PF10은 CV + accept(L16).
- 승인된 개선(PF7·PF9)의 승인 규칙은 결함 의도(패치 설명)로 판정 전에 커밋하고, 결함 run 결과로 만들지 않는다.

**근거**
- 결과를 본 뒤 기대를 고치면 탐지율을 잴 수 없다(팀원 Phase 3.6과 같은 원칙).
- 코드와 A/A 데이터를 읽으며 처음 계획과 달라진 점을 그대로 등록했다: PF1은 PGFAIL(R11)에서 첫 호출이 예외라 SAME(15건),
  PF7·PF9는 모든 consume에 SELECT가 하나 늘어 대상 밖 consume도 UNC, PF5의 404 취소(R16)는 learn 규칙과 유형이 달라 라벨 후에도 UNC,
  PF10은 B1 수정으로 같은 사용자 재사용(R7·R13)이 alreadyUsed가 되어 B3 경로(정가)로 바뀐다.
