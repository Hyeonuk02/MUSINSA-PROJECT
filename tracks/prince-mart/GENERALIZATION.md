# Prince Mart 일반화 기록

팀원 파이프라인(Istio 미러링 -> `services/evidence-collector` -> Evidence Store -> `engine/`)을 처음 보는 오픈소스 MSA인
Prince Mart(order, coupon, payment)에 적용하면서 생긴 일을 단계마다 기록한다. 앱 변경 내역은 [app/LEGACY_CHANGES.md](app/LEGACY_CHANGES.md)에 있다.

| 단계 | 내용 | 상태 |
|---|---|---|
| 1 | collector Feign 지원 | 완료 (2026-11-21) |
| 2 | k8s 매니페스트(pm-legacy, pm-new), 미러링 스모크 | 완료 (2026-11-21) |
| 3 | corpus v2 변환과 재생, 팀원 도구 env화 | 완료 (2026-11-21) |
| 4 | A/A 게이트(팀원 엔진, 3회) | 완료 (2026-11-21) |
| 5 | 결함 New 버전(PF1~PF10)과 기대 판정 사전 등록 | 완료 (2026-11-21, `f4750e8`) |
| 6 | 판정과 대조 | 완료 (2026-11-21), 결과 [RESULT.md](RESULT.md) |
| 리뷰 반영 | collector 0.1.0, 팀원 스택 A/A 회귀 | 완료 (2026-11-22), 5절 |

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

### 1.1 결함 판정에서 확인된 발견 (6단계)

사전 등록(5단계)의 예상 원인을 결함 run(각 3회)으로 확인했다. 결과 수치는 [RESULT.md](RESULT.md) 3절.

| 발견 | 단계 | 원인 | 영향(실측) | 대응 |
|---|---|---|---|---|
| readOnly 트랜잭션 차이가 기능 축 CV가 된다 | 6 | collector가 `SimpleJpaRepository.findById`의 readOnly 트랜잭션도 COMMIT_BEGIN과 COMPLETED로 기록하고, 엔진의 `tx_outcome_sequence_equal`이 트랜잭션 결과 순서열을 기능 축으로 비교한다 | PF7, PF9에서 조회 1회만 늘어 기능이 같은 소비 홉 8 pair가 CV(정답 SAME, 불일치 8) | 한계로 남김(엔진 변경 범위 밖). 팀원 앱에는 트랜잭션 밖의 리포지토리 조회 추가가 없었다 |
| 승인된 기능 변화를 규칙으로 표현할 수 없다 | 6 | 팀원 엔진은 writeSet, externalCalls, response.status를 규칙으로 덮지 않는다(기능 축은 무조건 CV). Prince Mart의 승인된 개선은 응답 필드 추가가 아니라 쓰기, 외부 호출, 호출 순서를 바꾼다 | PF7 R20 소비, PF9 R35 소비, PF10 주문 6과 validate 2가 CV(정답 IMPROVEMENT, 불일치 10). 응답 값만 바뀐 PF7 R21은 사전 승인 규칙으로 IMP | 한계로 남김. branch-park 기대는 이를 CV(accept)로 등록했었다 |
| 관측 서비스 호출 순서가 바뀌면 pair 짝이 깨진다 | 6 | 자식 hopPath는 홉 안 HTTP 호출 순번(`<부모>.h<n>`)이다. 쿼리 수 변화에는 안정적이지만(D15) 관측 서비스 호출의 순서가 바뀌면 같은 키가 다른 호출을 가리킨다 | PF10(쿠폰 use를 결제 뒤로): 비교 불성립 3 pair(legacy payment.process와 new coupon.use를 비교), 한쪽에만 있는 홉 26 | 비교 불성립으로 따로 셌다. 한계로 남김 |
| id 마스킹이 외부 호출 본문에 닿지 않는다 | 6 | 엔진은 응답과 payload의 `id` 키만 가리고, 외부 호출은 본문 hash로 비교한다 | PF10 R000028 감사 로그 `usageId` 1 -> 5(auto increment 밀림)가 CV(정답 SAME, 불일치 1). branch-park 사후 보정 항목 | 한계로 남김 |
| 규칙이 변경 단위 범위를 갖지 않는다 | 6 | 규칙은 endpoint와 diff 모양으로만 맞는다. 같은 모양의 차이가 개선(PF7 R21)과 결함(PF2 R21, R25)에 모두 생긴다 | PF7 사전 승인 규칙으로 PF2를 판정하면 진짜 결함 2 pair가 IMPROVEMENT로 가려진다(3회 같음, 대조 실험) | 사전 승인과 learn 규칙을 변경별 디렉터리(`tools/rules/approved/PF7/`, `tools/rules/review/PF5/`)로 나눠 실제 판정에서는 막았다 |
| 직렬화 라이브러리 전환(Jackson 2 -> 3)이 관측 차이를 만들지 않았다(예측 실패, 원인 확정) | 6 | Jackson 3 기본은 알파벳순 정렬(`SORT_PROPERTIES_ALPHABETICALLY`)이지만 `SORT_CREATOR_PROPERTIES_FIRST`(기본 켜짐)가 creator 속성을 먼저 쓴다. Payment에 직접 쓴 전 필드 생성자가 있고 `-parameters` 컴파일(Boot parent)로 인자 이름이 남아, Jackson 3가 이를 암묵 creator로 잡아 전 필드를 선언 순서로 낸다. jshell에서 `SORT_CREATOR_PROPERTIES_FIRST`만 끄면 알파벳순이 된다 | PF6 25 pair가 예상(CV)과 달리 SAME. 정답(SAME)과는 일치. "직렬화 문자열을 바이트로 비교"하는 약점은 이번 변경으로는 드러나지 않았다(출력 바이트가 같음) | 예측 오류로 기록(RESULT.md 7절). 사전 등록 값은 고치지 않았다. 예측은 일반 클래스 기준의 기본값만 보고 했고, 대상 클래스의 생성자를 확인하지 않았다 |

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
| `services/evidence-collector/pom.xml`과 의존하는 5개 pom (`services/order`, `services/coupon`, Prince Mart 3개) | collector 버전 0.0.1 -> 0.1.0(팀원 리뷰 반영, `08f349d`) | Feign 지원이 들어간 collector를 구분 | 없음. 팀원 스택 A/A 회귀로 확인(5절) |

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
| `engine/fault_check.py` (6단계) | `--expectations`(`docs/fault-expectations.json`) | 사전 등록 파일 경로. `--base`는 원래 인자라 `p4-aa`로 준다 |
| `engine/review.py` (6단계) | `--contract`(없음 = `<rules>/contract.yaml`) | 변경별 규칙 디렉터리에 계약 파일을 복사하지 않고 쓰려고(verdict.py `--contract`와 같음) |

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
| `tools/deploy-new.sh` (6단계) | pm-new의 서비스 하나만 결함 이미지와 `EVIDENCE_VERSION=PF<n>`으로 바꾼다(커밋된 overlay는 그대로, `base`로 되돌림) |
| `tools/fault_metrics.py` (6단계) | 사전 등록과 판정을 대조해 일치, 불일치, 검토, 비교 불성립, 예상 대비, 대상 밖, 한쪽에만 있는 홉, 세 run 동일을 센다 |
| `tools/faults/fault-metrics.json` (6단계) | 위 집계 원자료 |

### 2.4 Prince Mart 판정 규칙 (4단계)

팀원 엔진은 고치지 않고 `--rules tracks/prince-mart/tools/rules`로 규칙 디렉터리만 바꾼다.

| 파일 | 내용 | 팀원 `engine/rules`와 다른 점 |
|---|---|---|
| `tools/rules/contract.yaml` | 엔드포인트 11개(진입과 서비스 간 내부 호출, 소비 토픽 `payment-events`), observed host는 논리 이름 3개, 토픽 `payment-events` | 끈 검사 3개: `gateway_calls_per_idem_key_le_1`(Idempotency-Key와 `/gateway/charge` 전제), `coupon_transition_order`(팀원 쿠폰 흐름 전제), `publish_after_commit_begin`(1절, Legacy가 어김). 나머지 검사와 파라미터는 같다 |
| `tools/rules/improvement.yaml` | 사전 승인 규칙 없음(5단계에서 run 전에 넣는다) | 팀원 F6 규칙은 가져오지 않음 |
| `tools/rules/learned/` | 비어 있음 | 팀원 learned 규칙은 가져오지 않음(팀원 앱 엔드포인트 전용) |
| `tools/rules/contract-maxselects.yaml` (5단계) | contract.yaml과 같고 `max_selects`에 `order.mine: 1`만 선언 | 팀원 `contract-maxselects.yaml`과 같은 용도(PF8). A/A 3회에 적용해도 SAME 80 |
| `tools/rules/review/PF5/` (6단계) | PF5 learn 라벨 규칙 2개(`engine/review.py label`, 사전 등록한 R000024, R000027) | 팀원은 learned를 하나의 디렉터리에 쌓는다. 변경별로 나눴다(1.1절) |
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
| 진짜 결함과 성능 결함 탐지가 팀원 앱과 같은 양상으로 재현된다 | 6 | PF1~PF4 target 47 pair 전부 CV(3회), PF8 기본 검토 2/2, max_selects 선언 시 CV 2/2. 10 PF 모두 대상 밖 pair SAME(정상 경로 오탐 0), 세 run 판정 동일. 오판정률(팀원 phase3-metrics와 같은 정의) 0/153, target 밖 오탐 0/2034. 정답 대비 불일치는 20/102로 따로 센다(RESULT.md 0절) |
| 사전 등록 기대 값을 run 뒤에 고치지 않았다 | 6 | `fault-expectations.json`의 `_revisions`는 run 전 수정(집계 정의, 문구, runCheck 형식)뿐이고 targets와 expectedEngine 값은 `f4750e8` 그대로다 |

## 5. 팀원 스택 A/A 회귀 (collector 0.1.0)

collector에 Feign 지원을 더하고 버전을 0.1.0으로 올린 뒤, 팀원 Order, Coupon 스택이 그대로 SAME인지 확인했다.

| 항목 | 값 |
|---|---|
| 실행 날짜 | 2026-11-22 (UTC 14:54 ~ 14:56) |
| 기준 커밋 | `08f349d19f532ab38ed4f6f3149c373775ec5b89` (evidence-collector: 버전 0.0.1 -> 0.1.0). run-meta `git.dirty: false` x3 |
| run ID | `c010-aa-1`, `c010-aa-2`, `c010-aa-3` |
| 명령 | `k6/run.sh --run-id c010-aa --iterations 3 --vus 3` (팀원 기본값: corpus v2.1, ns legacy/new). run마다 `engine/diff_v0.py`, `engine/verify_sameness.py`, `engine/verdict.py --arm C`(engine-v1.3, `engine/rules`) |
| 앱 | 그 커밋의 `services/` 그대로. Order는 Kotlin v1.4, Coupon은 현재 코드, collector 0.1.0 |
| 이미지 | Legacy와 New 모두 `order-app:c010`(imageRef `sha256:5f44e035102fac6582cb7c033c3385d431c0dfabda43e93c6b7df81ce56163a2`), `coupon-app:c010`(imageRef `sha256:71e23d758e9a1aff73bffb4b34eac18eb6541df0cfc63c48d2267f254bf767aa`). 저장소 overlay는 그대로 두고 `kubectl set image`로 임시 교체(팀원 Phase 3 방식) |
| 클러스터 | Prince Mart 스택(pm-legacy, pm-new)을 0으로 줄이고 팀원 legacy, new를 올려 실행. 끝난 뒤 팀원 스택을 지우고 Prince Mart를 다시 올림 |

| 완료 기준 | c010-aa-1 | c010-aa-2 | c010-aa-3 |
|---|---|---|---|
| 전 pair SAME(판정 C) | SAME 60 | SAME 60 | SAME 60 |
| diff 없음(diff_v0, 7축 + dbstate + wiremock) | ∅ | ∅ | ∅ |
| dbstate 일치(`dbstate_equal`) | ok | ok | ok |
| Undelivered 0 | 0 | 0 | 0 |
| degraded 0 | 0 | 0 | 0 |
| (참고) verify_sameness, barrier legacy/new, sessionViolations | PASS, 60/60, 60/60, 0 | PASS, 60/60, 60/60, 0 | PASS, 60/60, 60/60, 0 |

- 팀원 Phase 4.8 6.1의 A/A(`p48-aa2`)는 Legacy와 New 모두 `phase3.3-base`(Order Java, collector 0.0.1)였다. 이번 A/A는 앱 코드가 다르다(Order Kotlin v1.4, Coupon 현재 코드, collector 0.1.0 양쪽).
- 3단계에서 env화한 `k6/run.sh`, `run.js`, `spill-recover.sh`, `dbstate-export.sh`를 팀원 기본값으로 실제 클러스터에서 돌린 첫 run이기도 하다(3단계에서는 stub 비교만 했다). barrier, export, dbstate, wiremock journal, run-meta 모두 기본 경로로 동작했다.
- Feign이 없는 팀원 서비스에는 `FeignEvidenceAutoConfiguration`이 붙지 않으므로, Feign 지원 추가가 기존 RestClient 경로의 Evidence를 바꾸지 않았다는 실측 근거다.
- 복구 확인: pm-legacy 9 pod, pm-new 10 pod Running(앱과 DB 2/2, sidecar 없는 진단 pod만 1/1), 토픽 `payment-events` 재생성과 `order-service` 그룹 할당, readiness 6/6(200), 미러링 스모크 4건 Evidence legacy 10, new 10(2단계와 같음). 이미지는 `:base` 그대로.
- Prince Mart 결과(4~6단계)는 collector 0.0.1 빌드(`:base`)로 실행했다. 그 결과를 낸 커밋 `cf771e6`과 `08f349d` 사이에 collector는 `pom.xml`의 버전 한 줄만 다르다(`git diff cf771e6 08f349d -- services/evidence-collector`). 0.1.0으로도 세 서비스 빌드가 통과한다(`prince-mart/*-service:c010`).