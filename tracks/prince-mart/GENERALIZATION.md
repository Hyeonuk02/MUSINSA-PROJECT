# Prince Mart 일반화 기록

팀원 파이프라인(Istio 미러링 -> `services/evidence-collector` -> Evidence Store -> `engine/`)을 처음 보는 오픈소스 MSA인
Prince Mart(order, coupon, payment)에 적용하면서 생긴 일을 단계마다 기록한다. 앱 변경 내역은 [app/LEGACY_CHANGES.md](app/LEGACY_CHANGES.md)에 있다.

| 단계 | 내용 | 상태 |
|---|---|---|
| 1 | collector Feign 지원 | 완료 (2026-11-21) |
| 2 | k8s 매니페스트(pm-legacy, pm-new), 미러링 스모크 | 완료 (2026-11-21) |
| 3 | corpus v2 변환과 재생, 팀원 도구 env화 | 완료 (2026-11-21) |
| 4 | A/A 게이트(팀원 엔진, 3회) | 완료 (2026-11-21) |
| 5 | 결함 New 버전(PF1~PF10)과 기대 판정 사전 등록 | 사전 등록안 작성 (2026-11-21), 커밋 대기 |
| 6 | 판정과 대조 | 예정 |

## 1. 일반화 발견

팀원 파이프라인이 Prince Mart에서 그대로 성립하지 않은 지점.

| 발견 | 단계 | 원인 | 영향 | 대응 |
|---|---|---|---|---|
| collector가 RestClient만 계측(Feign 미지원) | 1 | 팀원 앱의 하위 호출이 전부 RestClient라 `RestClientCustomizer` 경로만 구현됨 | Prince Mart의 서비스 간 호출과 외부 호출(전부 OpenFeign)에 재생 헤더가 전파되지 않아 하위 홉 Evidence가 생기지 않고, `externalCalls`도 비었다 | collector에 `FeignEvidenceCapability` 추가(Client를 감싸 RestClient 경로와 같은 필드, 같은 규칙으로 기록). 실제 앱에서 `0.h5.h1`, `0.e1.h1` 등 홉 전파 확인 |
| Feign 경로의 host는 논리 서비스 이름, RestClient 경로는 실제 host | 1 | Spring Cloud OpenFeign이 Capability를 로드밸런서 클라이언트 바깥에 씌워, 주소가 풀리기 전 URL(`http://COUPON-SERVICE/...`)을 본다 | legacy와 new 비교에는 영향 없음. host로 대상을 고르는 설정(`OBSERVED_HOSTS`, `--observed-hosts`, contract `observed.hosts`, `gateway_calls_per_idem_key_le_1.host`, 규칙 host 매처)에 서비스 간 호출은 `ORDER-SERVICE` 같은 이름, 가짜 PG는 `wiremock`을 넣어야 한다 | 기록하고 설정값으로 맞춘다(3단계 이후). 여러 Feign 대상이 같은 WireMock을 가리켜도 host가 구분되는 장점이 있다 |
| collector가 Boot 4 전용이라 버전 업그레이드를 New 변경 사례로 쓸 수 없음 | 1 이전 | collector가 Boot 4.1.1 모듈(`spring-boot-restclient`, Jackson 3 `tools.jackson`)에 맞춰 빌드됨. 계측을 붙이려면 Legacy도 Boot 4여야 한다 | 원래 New 정상 변경 사례인 "payment Boot 3 -> 4"가 Legacy로 흡수됐다. 프레임워크 메이저 업그레이드형 교체는 같은 collector로 검증할 수 없다 | PF6를 "payment Jackson 2 -> 3 전환"으로 대체. 한계로 남김 |
| 앱이 `RestClient.create()`로 직접 만든 클라이언트에는 계측이 안 붙음 | 1 | collector는 Boot가 관리하는 `RestClient.Builder`에만 붙는다. `FakePgPaymentGateway`는 정적 팩토리를 썼다 | 가짜 PG `POST /v1/orders`가 Evidence에 없었다. 이 호출은 PF1의 탐지 근거다 | `FakePgPaymentGateway`가 Builder를 주입받게 변경(팀원 Phase 3.1 `PaymentGatewayClient`와 같은 방식). 적용 전에 앱의 HTTP 클라이언트 생성 방식을 점검해야 한다는 점은 한계로 남김 |
| 도구(`run.sh`, `spill-recover.sh`, `dbstate-export.sh`)가 팀원 앱에 고정 | 2 | ns `legacy`/`new`, 앱 라벨 `order`/`coupon`, 토픽 `order.paid`, 그룹 `coupon-settlement`, readiness 경로 `/api/orders/by-key/...`, tooling pod 이름, DB 계정 `poc`, 테이블과 컬럼이 코드에 있다 | reset, preflight, spill 회수, DB 상태 export, run-meta를 Prince Mart에 그대로 쓸 수 없다 | 3단계에 env화(2절 표). 기본값은 지금 값 그대로이고, 수정 전후 run.sh를 기본값으로 돌려 콘솔 출력과 run-meta가 같음을 확인. Prince Mart 값은 `tools/pm.env` |
| corpus 스키마가 `/api` 경로와 orderKey 같은 business key를 전제 | 2 | `corpus/schema-v2.json`의 path 패턴이 `^/api/(orders\|coupons)`, `validate.py` v2 규칙이 orderKey, couponKey, Idempotency-Key를 검사한다. `k6/run.js`는 corpus를 `corpus/corpus-v<N>.json`으로만 받는다 | Prince Mart corpus는 구조적으로 팀원 검증기를 통과할 수 없다 | Prince Mart 전용 스키마와 검증기(`corpus/schema-v2.json`, `corpus/validate.py`, 규칙 10종, self-test 17건)를 두고, run.sh의 검증기 경로와 run.js의 corpus 위치를 env로 받게 했다 |
| business key가 없으면 VU=1 순차 재생만 결정적 | 2 | Prince Mart의 orderId는 auto increment이고, 후속 요청이 orderId와 transactionId(`order_{id}`)를 참조한다. `run.js`에는 응답 값 치환(capture)이 없다 | 세션이 병렬로 돌면 auto increment id가 세션 사이에서 섞이고 legacy와 new 사이에서도 순서가 달라질 수 있다. 팀원 A/A 표준(VU=3 x3)은 성립하지 않는다 | S0 리셋 + VU=1 순차 재생. `tools/run-pm.sh`가 VU 1만 허용한다. 한계로 남김 |
| business key가 없는 시스템은 corpus에 응답 값 치환이 필요하다 | 3 | 팀원 corpus는 클라이언트가 정한 business key(orderKey)로 후속 요청의 대상을 정해, 요청 바이트가 corpus만으로 정해진다. Prince Mart는 서버가 만든 id를 받아야 다음 요청을 만들 수 있다 | id를 corpus에 리터럴로 미리 계산해 넣으면, 실패한 insert도 auto increment를 소비하는 등 앱 동작에 따라 틀어진다 | `k6/run.js`에 선택 기능 capture를 추가했다(2절). legacy 응답의 최상위 필드를 세션 변수로 저장하고 다음 요청의 path와 body의 `${변수}`를 치환한다. 3단계 재생에서 38건 모두 치환됨 |
| 팀원 DB 상태 export가 정수 금액과 한 줄 값을 전제 | 3 | `dbstate-export.sh`는 sum을 `int()`로 계산하고 `mysql -B` 출력을 줄 단위로 읽는다. Prince Mart 금액은 decimal, `orders.shipping_address_snapshot`은 줄바꿈을 포함한다. business key가 없어 행 정렬과 테이블 연결도 auto increment id로 해야 한다 | 그대로 넣으면 sum에서 실패하거나 행이 깨진다 | 스크립트는 고치지 않고 Prince Mart 테이블 정의(`tools/dbstate-tables.txt`)에서 금액은 `CAST(x*100 AS SIGNED)`, 스냅샷은 `MD5(...)`로 바꾸고 id를 행에 남겼다(VU=1에서만 유효) |
| 팀원 contract의 절대 불변식 하나를 Legacy가 이미 어김 | 4 | `publish_after_commit_begin`은 legacy와 비교하지 않고 New만 보는 절대 검사다(팀원 D16, 커밋 전 발행 금지). Prince Mart payment verify는 Legacy부터 커밋 전에 발행한다(PUBLISH -> COMMIT_BEGIN, LEGACY_CHANGES.md) | 팀원 contract 그대로면 A/A(New = Legacy 코드)에서도 verify 5건이 3회 모두 CV다(80 pair 중 75 SAME, 5 CV). 게이트가 성립하지 않는다 | Prince Mart contract에서 끔(`tools/rules/contract.yaml`). 팀원 엔진은 이 검사를 엔드포인트별로 끌 수 없어(엔드포인트별 파라미터는 `max_selects`만) 전체를 껐다. Prince Mart에서 발행하는 홉은 payment.verify뿐이라 지금은 효과가 같다. 한계: 엔진에 발행과 커밋의 순서를 legacy와 비교하는 차등 검사가 없어, 순서가 바뀌는 변경은 다른 축에 드러나지 않는다. 결함 카탈로그(PF1~PF10)에는 이 순서를 바꾸는 결함이 없다 |
| readiness 확인이 "헤더 없는 GET"을 전제 | 3 | 팀원 run.sh는 readiness 경로를 헤더 없이 부른다. Prince Mart의 주문 조회는 `X-User-Id`가 없으면 500이다 | 팀원처럼 "없는 키 조회 404"를 쓸 수 없다 | DB를 읽는 헤더 없는 GET(`/orders/all`, `/coupons/all`)을 쓰고 기대 코드도 env로 받는다. payment는 DB를 읽는 GET이 없어 `/payments/welcome`으로 기동만 확인한다 |
| 게이트웨이 VS 하나에 Store 경로와 팀원 앱 경로가 함께 있음 | 2 | 팀원 `virtualservice-shadow.yaml`이 `/_evidence/`와 `/api/orders`, `/api/coupons`를 한 리소스에 담았다 | Store 경로 때문에 팀원 VS를 그대로 적용하면, 팀원 앱 스택이 없어 `istioctl analyze`가 IST0101(Error) 4건을 낸다. 동작에는 영향 없음 | 팀원 VS는 수정 없이 적용하고 Prince Mart VS를 따로 붙였다(prefix가 겹치지 않음). 이유는 `k8s/README.md`에 기록 |

### 1.1 판정 전 예상 (5단계 사전 등록, 6단계 판정 뒤 확정)

사전 등록안(`tools/faults/fault-expectations.json`)에서 정답과 예상 엔진 판정이 갈리는 곳의 원인. 판정 run 뒤 실제로 그런지 확인하고 위 표로 옮긴다.

| 예상 원인 | 해당 | 예상 영향 |
|---|---|---|
| 자식 hopPath가 호출 순번이라, 관측 서비스 호출의 순서가 바뀌면 같은 키가 서로 다른 호출을 가리킨다 | PF10(use를 결제 뒤로) | 정렬 오류 pair 3개(legacy payment.process와 new coupon.use 비교), 나머지는 한쪽에만 있는 홉 |
| collector가 readOnly 트랜잭션도 기록하고, 엔진은 트랜잭션 결과 순서열을 기능 축으로 비교한다 | PF7, PF9(소비마다 findById 1회) | 기능이 같은 소비 홉 8개가 CV |
| 직렬화된 JSON을 담은 문자열 필드와 외부 호출 본문은 바이트(hash) 비교다 | PF6(Jackson 3 키 순서) | 의미가 같은 25 pair가 CV |
| id 마스킹이 키 이름 `id`만 대상이고 외부 호출 본문에는 적용되지 않는다 | PF10 R000028(usageId 1 -> 5) | 1 pair CV |
| 승인된 기능 변화(writeSet, externalCalls, response.status)는 규칙으로 덮을 수 없다 | PF7 R20, PF9 R35, PF10 | 정답 IMPROVEMENT인 pair가 CV |
| 규칙이 변경(버전) 단위로 범위를 가지지 않는다. 같은 모양의 차이가 개선(PF7 R21)과 결함(PF2 R21)에 모두 생긴다 | PF7 승인 규칙 | 전역 규칙이면 결함을 개선으로 가린다. PF7 판정에만 쓰는 규칙 디렉터리(`tools/rules/approved/PF7/`)로 분리했다 |

## 2. 일반화를 위해 추가하거나 바꾼 것

| 파일 | 바꾼 내용 | 이유 | 팀원 실행 영향 |
|---|---|---|---|
| `services/evidence-collector/src/main/java/poc/evidence/FeignEvidenceCapability.java` (신규) | Feign Client를 감싸 재생 헤더 4개 전파(원래 requestTemplate 유지), 자식 hopPath, 호출 시작 시점 seq, 응답 버퍼링과 해시, IOException이면 status 0 | Feign 미지원 | 없음. Feign이 없으면 로드되지 않는다 |
| `services/evidence-collector/src/main/java/poc/evidence/FeignEvidenceAutoConfiguration.java` (신규) | `@ConditionalOnClass(name = "feign.Capability")` + `@ConditionalOnProperty("EVIDENCE_STORE_URL")`로 Capability 빈 등록 | Feign이 있는 서비스에만 켜기 | 없음(자동 구성 조건 테스트로 확인) |
| `services/evidence-collector/src/main/resources/META-INF/spring/...AutoConfiguration.imports` | 한 줄 추가 | 위 자동 구성 등록 | 없음 |
| `services/evidence-collector/pom.xml` | `feign-core`(provided, Spring Cloud 2025.1.3 BOM), 테스트 의존성 | Feign 컴파일과 테스트 | 없음. 기존 의존성 83개 버전 동일(`dependency:list` 대조) |
| `services/evidence-collector/src/test/` (신규) | 테스트 13개: Feign 단위 8, RestClient 동형 대조, Spring Cloud OpenFeign + LoadBalancer 통합 2, 자동 구성 조건 3 | Feign 경로 검증, 두 경로가 같은 Evidence를 남기는지 대조 | 없음. collector 빌드 때 테스트도 컴파일된다 |
| `tracks/prince-mart/app/payment-service/.../FakePgPaymentGateway.java` | `RestClient.create()` -> Boot `RestClient.Builder` 주입 | 정적 팩토리 클라이언트에는 계측이 안 붙음 | 해당 없음(Prince Mart 앱) |
| `tracks/prince-mart/app/payment-service/pom.xml` | `spring-boot-starter-restclient` 추가 | Boot 4는 Builder 자동 구성이 별도 모듈 | 해당 없음 |
| `tracks/prince-mart/k8s/` (신규) | 팀원 `deploy/k8s` 구조를 따른 Prince Mart 스택. 팀원과 다른 점은 `k8s/README.md` 표 | Prince Mart 배포 | 없음(별도 네임스페이스) |

### 2.1 팀원 도구 env화 (3단계)

규칙: 고정값을 env(또는 인자)로 받고 기본값은 지금 값 그대로. 확인: 외부 명령을 기록하는 stub으로 수정 전(HEAD) run.sh와 수정 후 run.sh를 기본값으로 끝까지 돌려 비교했다.
콘솔 출력과 run-meta.json은 같고, 외부 명령 107건도 같다. 다른 점은 k6에 `CORPUS_DIR=../corpus`(run.js 기본값과 같음)를 넘기는 것과 run-meta를 만들 때 읽기 전용 조회 3건의 순서뿐이다. 두 버전 모두 실제 k6로 팀원 corpus 로드를 확인했다.

| 파일 | 변수(기본값) | 바꾼 내용 |
|---|---|---|
| `k6/run.sh` | `CORPUS`(`corpus/corpus-v2.1.json`), `CORPUS_VALIDATOR`(`corpus/validate.py`), `KAFKA_TOPICS`(`order.paid order.paid.dlq`) | 상수 -> env |
| `k6/run.sh` | `NS_LEGACY`/`NS_NEW`(`legacy`/`new`), `TOOL_POD_LEGACY`/`TOOL_POD_NEW`(`mesh-check`/`isolation-injected`) | 스택 이름(legacy/new, Store와 파일 이름)과 네임스페이스를 분리. reset, export_wiremock, run-meta가 네임스페이스를 쓴다 |
| `k6/run.sh` | `READINESS_CHECKS`(`order:8080:/api/orders/by-key/ok-readiness-check:404 coupon:8080:/api/coupons/by-key/ck-readiness-check:404`) | 서비스별 readiness 함수 4개 -> 목록 순회 함수 2개. 기본값이면 로그 문구도 같다 |
| `k6/run.sh` | `CERT_APPS`(`order coupon kafka`) | preflight 인증서 확인 대상. 순서도 같다 |
| `k6/run.sh` | `RESET_DEPLOYMENTS`(`mysql coupon-mysql kafka`) | S0 rollout restart 대상. 기본값이면 로그 문구도 같다 |
| `k6/run.sh` | `CONSUMER_GROUP`/`CONSUMER_TOPIC`(`coupon-settlement`/`order.paid`) | 리셋 뒤 파티션 할당 대기 |
| `k6/run.sh` | `META_APPS`(`order coupon`), `CLOCK_DEPLOY`(`order`) | run-meta images와 appFixedClock. 기본값이면 JSON 키와 순서가 같다 |
| `k6/run.sh` | (k6 호출) | k6에 `CORPUS_DIR=../<CORPUS의 디렉터리>`를 넘긴다. `CORPUS`를 basename으로 바꾸는 할당보다 앞에 둔다(bash는 앞 접두 할당을 뒤 할당의 확장에서 본다) |
| `k6/run.js` | `CORPUS_DIR`(`../corpus`) | corpus 디렉터리 |
| `k6/spill-recover.sh` | `NS_LEGACY`/`NS_NEW`(`legacy`/`new`) | 스택과 네임스페이스 분리. order pod 하나로 충분한 이유를 주석으로(spill hostPath가 스택 디렉터리 전체) |
| `k6/dbstate-export.sh` | `DBSTATE_TABLES_FILE`(없음 = 지금 TABLES 배열), `DB_USER`/`DB_PASSWORD`(`poc`), `NS_LEGACY`/`NS_NEW` | 테이블 정의 파일, DB 계정, 네임스페이스 |
| `engine/verify_sameness.py` | `--evidence-headers`(지금 `EVIDENCE_HEADERS` 목록) | request 동일성에서 비교할 헤더. Prince Mart는 `idempotency-key` 대신 `x-user-id` |

### 2.2 기능 추가 (3단계)

| 파일 | 내용 | 이유 | 팀원 실행 영향 |
|---|---|---|---|
| `k6/run.js` | 응답 값 치환(capture). 요청의 `capture {변수: 응답 필드}`로 legacy 응답 JSON 최상위 필드를 세션 변수에 저장하고, 이후 요청의 path와 body 문자열의 `${변수}`를 치환. 변수가 없으면 그 요청을 보내지 않고 세션을 degraded로 끝낸다. k6 태그는 치환 전 경로 | business key가 없는 시스템(1절) | 없음. 팀원 corpus에는 capture와 `${`가 없어(팀원 `corpus/validate.py`가 v1, v2 모두 `${` 치환자를 실행 시점 값으로 금지) 요청 바이트가 같다 |

### 2.3 Prince Mart 전용 파일 (3단계)

| 파일 | 내용 |
|---|---|
| `corpus/corpus-v1.1.json` | branch-park 베이스라인 corpus 원본 그대로(세션 14, 요청 38) |
| `corpus/convert_v1_to_v2.py` | v1.1 -> `corpus-v2.json` 변환(결정론, `--check`). 세션 id S001 형식, X-User-Id를 요청 헤더로, 결제 확정에 Kafka 소비 홉 settle |
| `corpus/schema-v2.json`, `corpus/validate.py`, `corpus/tests/invalid/` | Prince Mart 스키마와 검증기(팀원 검증기와 같은 방식, 규칙 10종, `--self-test` 17건) |
| `tools/pm.env` | 2.1의 env에 넣을 Prince Mart 값 |
| `tools/run-pm.sh` | pm.env를 읽고 팀원 `k6/run.sh`를 부른다. VU 1만 허용 |
| `tools/dbstate-tables.txt` | Prince Mart 테이블 7개의 DB 상태 정의(1절 dbstate 항목) |

### 2.4 Prince Mart 판정 규칙 (4단계)

팀원 엔진은 고치지 않고 `--rules tracks/prince-mart/tools/rules`로 규칙 디렉터리만 바꾼다.

| 파일 | 내용 | 팀원 `engine/rules`와 다른 점 |
|---|---|---|
| `tools/rules/contract.yaml` | 엔드포인트 11개(진입과 서비스 간 내부 호출, 소비 토픽 `payment-events`), observed host는 논리 이름 3개, 토픽 `payment-events` | 끈 검사 3개: `gateway_calls_per_idem_key_le_1`(Idempotency-Key와 `/gateway/charge` 전제), `coupon_transition_order`(팀원 쿠폰 흐름 전제), `publish_after_commit_begin`(1절, Legacy가 어김). 나머지 검사와 파라미터는 같다 |
| `tools/rules/improvement.yaml` | 사전 승인 규칙 없음(5단계에서 run 전에 넣는다) | 팀원 F6 규칙은 가져오지 않음 |
| `tools/rules/learned/` | 비어 있음 | 팀원 learned 규칙은 가져오지 않음(팀원 앱 엔드포인트 전용) |
| `tools/rules/contract-maxselects.yaml` (5단계) | contract.yaml과 같고 `max_selects`에 `order.mine: 1`만 선언 | 팀원 `contract-maxselects.yaml`과 같은 용도(PF8). A/A 3회에 적용해도 SAME 80 |
| `tools/rules/approved/PF7/` (5단계) | PF7 사전 승인 규칙 2개(order.get 응답 orderStatus CONFIRMED -> CANCELLED, paymentStatus PAID -> UNPAID) | 팀원은 사전 승인 규칙을 `improvement.yaml` 하나에 둔다. Prince Mart는 같은 모양의 결함 차이를 가리지 않게 변경별 디렉터리로 분리(1.1절). A/A 3회에 적용해도 SAME 80 |

### 2.5 결함과 정상 변경 New 버전 (5단계)

| 파일 | 내용 |
|---|---|
| `tools/faults/make_patches.py`, `PF<n>-<svc>.patch` | branch-park PF 편집을 지금 코드에 맞춰 옮긴 패치 10개(저장소 루트 기준, `git apply --check`와 컴파일 확인). PF6은 Jackson 2 -> 3 전환 |
| `tools/faults/fault-expectations.json` | 사전 등록: 정답(`targets`)과 예상 엔진 판정(`expectedEngine`)을 나눠 적고, pair 키를 팀원 엔진 키로 다시 매겼다. branch-park 옛 키와 사후 보정 출처를 pair마다 남겼다 |
| `tools/faults/branch-park/` | branch-park 기대, 사후 보정, 카탈로그 원본 그대로 |

## 3. 수정 없이 그대로 쓴 팀원 구성요소

2절에서 env화한 파일(`k6/run.sh`, `run.js`, `spill-recover.sh`, `dbstate-export.sh`, `engine/verify_sameness.py`)은 기본 동작이 같지만 수정한 파일이라 여기서 뺀다.

| 구성요소 | 쓰는 곳 |
|---|---|
| `deploy/k8s/kind-config.yaml` (노드 이미지 digest 포함) | 클러스터 |
| `deploy/k8s/istio/istio-install.yaml` (Istio 1.31.1, 메시 전역 REGISTRY_ONLY) | 메시 |
| `deploy/k8s/istio/gateway.yaml`, `telemetry.yaml`, `virtualservice-shadow.yaml` | 게이트웨이, 트레이싱, Store 경로 `/_evidence/` |
| `deploy/k8s/00-namespaces.yaml` | verify, observability (함께 생기는 빈 legacy, new도 그대로 둠) |
| `deploy/k8s/observability/` | OTel Collector, Jaeger |
| `deploy/k8s/verify/evidence-store.yaml`, `evidence-store/` (이미지 `evidence-store:phase3.2`) | Evidence Store |
| collector 기존 클래스 전부(`EvidenceFilter`, `EvidenceWriter`, `EvidenceSender`, `EvidenceStatementInspector`, `EvidenceTransactionListener`, `CallTreeInterceptor`, `ReplayPropagatingInterceptor`, Kafka 인터셉터 3종, `EvidenceAutoConfiguration`) | 세 Prince Mart 서비스 |
| `docs/evidence-schema-v1.json` | Evidence 계약 |
| `k6/barrier.py` | barrier(관측 host와 토픽은 인자) |
| `evidence-store/` API(`/evidence`, `/exists`, `/count`, `/export`) | k6 완료 폴링, barrier, export |
| OTel Java agent 이미지(digest 고정), `curlimages/curl:8.11.1`, `busybox:1.37`, WireMock 3.13.1 digest, `apache/kafka:4.2.1`, `mysql:8.4` | 매니페스트 |

## 4. 확인된 성립 사항

| 확인 | 단계 | 근거 |
|---|---|---|
| 환경을 Compose에서 k8s로 옮겨도 Legacy 최종 상태가 같다 | 4 | branch-park Compose A/A `aa-004-1`(corpus v1.1, VU 1)과 k8s `p3-replay-1`의 legacy DB 7테이블이 행 수와 모든 컬럼 값까지 같다(orders 16, order_items 32, order_status_history 26, coupons 14, coupon_usage 1, payments 15, refunds 0). coupon_usage 1건은 R000028(S011, 취소된 주문에 `/coupons/use` 직접 호출, B2)에서 생긴다. 주문 경로의 쿠폰 사용은 커밋 전 역조회 404(B1)라 기록이 없다 |
| payment 감사 로그의 `dataAfter` 키 순서가 Jackson 2 선언 순서 그대로다 | 4 | `PAYMENT_COMPLETED_SUCCESS`의 키가 Payment 엔티티 필드 선언 순서(paymentId, orderId, paymentMethod, transactionId, amount, currency, status, createdAt, refunds)와 같다. payment 감사 로그 21건이 Compose와 k8s에서 action, dataBefore, dataAfter 문자열까지 같다 |
| A/A 게이트: 팀원 엔진 판정이 3회 모두 전부 SAME | 4 | `p4-aa-1..3`, 각 80 pair SAME 80, dbstate_equal OK, Undelivered 0, degraded 0, barrier 80/80. verify_sameness 3회 PASS |
| run 사이 결정성 | 4 | `p4-aa-1` legacy의 판정 축(기능, 실행 특성)이 `p4-aa-2`, `p4-aa-3`, `p3-replay-1`의 legacy와 new 모든 pair에서 같다. dbstate도 3회 같다. branch-park에서 겪은 Kafka rebalance, 컨슈머 그룹 잔류 문제는 나타나지 않았다(리셋마다 브로커가 새로 뜨고 run.sh가 그룹 할당을 기다린다) |
| 엔진의 id 마스킹 범위(`id` 키만)로 충분하다(VU 1 기준) | 4 | 응답과 payload의 `orderId`, `paymentId` 등은 마스킹되지 않지만 S0 리셋 + VU 1 순차 재생에서 legacy와 new 값이 같아 차이가 없었다. Prince Mart 규칙 파일에 정규화를 둘 필요가 없었다 |
