# Prince Mart 일반화 기록

팀원 파이프라인(Istio 미러링 -> `services/evidence-collector` -> Evidence Store -> `engine/`)을 처음 보는 오픈소스 MSA인
Prince Mart(order, coupon, payment)에 적용하면서 생긴 일을 단계마다 기록한다. 앱 변경 내역은 [app/LEGACY_CHANGES.md](app/LEGACY_CHANGES.md)에 있다.

| 단계 | 내용 | 상태 |
|---|---|---|
| 1 | collector Feign 지원 | 완료 (2026-11-21) |
| 2 | k8s 매니페스트(pm-legacy, pm-new), 미러링 스모크 | 완료 (2026-11-21) |
| 3 | corpus v2 변환과 재생 | 예정 |
| 4 | A/A 게이트 | 예정 |
| 5 | 결함 New 버전(PF1~PF10)과 기대 판정 사전 등록 | 예정 |
| 6 | 판정과 대조 | 예정 |

## 1. 일반화 발견

팀원 파이프라인이 Prince Mart에서 그대로 성립하지 않은 지점.

| 발견 | 단계 | 원인 | 영향 | 대응 |
|---|---|---|---|---|
| collector가 RestClient만 계측(Feign 미지원) | 1 | 팀원 앱의 하위 호출이 전부 RestClient라 `RestClientCustomizer` 경로만 구현됨 | Prince Mart의 서비스 간 호출과 외부 호출(전부 OpenFeign)에 재생 헤더가 전파되지 않아 하위 홉 Evidence가 생기지 않고, `externalCalls`도 비었다 | collector에 `FeignEvidenceCapability` 추가(Client를 감싸 RestClient 경로와 같은 필드, 같은 규칙으로 기록). 실제 앱에서 `0.h5.h1`, `0.e1.h1` 등 홉 전파 확인 |
| Feign 경로의 host는 논리 서비스 이름, RestClient 경로는 실제 host | 1 | Spring Cloud OpenFeign이 Capability를 로드밸런서 클라이언트 바깥에 씌워, 주소가 풀리기 전 URL(`http://COUPON-SERVICE/...`)을 본다 | legacy와 new 비교에는 영향 없음. host로 대상을 고르는 설정(`OBSERVED_HOSTS`, `--observed-hosts`, contract `observed.hosts`, `gateway_calls_per_idem_key_le_1.host`, 규칙 host 매처)에 서비스 간 호출은 `ORDER-SERVICE` 같은 이름, 가짜 PG는 `wiremock`을 넣어야 한다 | 기록하고 설정값으로 맞춘다(3단계 이후). 여러 Feign 대상이 같은 WireMock을 가리켜도 host가 구분되는 장점이 있다 |
| collector가 Boot 4 전용이라 버전 업그레이드를 New 변경 사례로 쓸 수 없음 | 1 이전 | collector가 Boot 4.1.1 모듈(`spring-boot-restclient`, Jackson 3 `tools.jackson`)에 맞춰 빌드됨. 계측을 붙이려면 Legacy도 Boot 4여야 한다 | 원래 New 정상 변경 사례인 "payment Boot 3 -> 4"가 Legacy로 흡수됐다. 프레임워크 메이저 업그레이드형 교체는 같은 collector로 검증할 수 없다 | PF6를 "payment Jackson 2 -> 3 전환"으로 대체. 한계로 남김 |
| 앱이 `RestClient.create()`로 직접 만든 클라이언트에는 계측이 안 붙음 | 1 | collector는 Boot가 관리하는 `RestClient.Builder`에만 붙는다. `FakePgPaymentGateway`는 정적 팩토리를 썼다 | 가짜 PG `POST /v1/orders`가 Evidence에 없었다. 이 호출은 PF1의 탐지 근거다 | `FakePgPaymentGateway`가 Builder를 주입받게 변경(팀원 Phase 3.1 `PaymentGatewayClient`와 같은 방식). 적용 전에 앱의 HTTP 클라이언트 생성 방식을 점검해야 한다는 점은 한계로 남김 |
| 도구(`run.sh`, `spill-recover.sh`, `dbstate-export.sh`)가 팀원 앱에 고정 | 2 | ns `legacy`/`new`, 앱 라벨 `order`/`coupon`, 토픽 `order.paid`, 그룹 `coupon-settlement`, readiness 경로 `/api/orders/by-key/...`, tooling pod 이름, DB 계정 `poc`, 테이블과 컬럼이 코드에 있다 | reset, preflight, spill 회수, DB 상태 export, run-meta를 Prince Mart에 그대로 쓸 수 없다 | 3단계: 고정값을 env로 받게 하고 기본값은 지금 값 그대로(팀원 실행 불변). 앱 전용으로 남는 것은 `tools/` |
| corpus 스키마가 `/api` 경로와 orderKey 같은 business key를 전제 | 2 | `corpus/schema-v2.json`의 path 패턴이 `^/api/(orders\|coupons)`, `validate.py` v2 규칙이 orderKey, couponKey, Idempotency-Key를 검사한다. `k6/run.js`는 corpus를 `corpus/corpus-v<N>.json`으로만 받는다 | Prince Mart corpus는 구조적으로 팀원 검증기를 통과할 수 없다 | 3단계: Prince Mart 전용 스키마와 검증기를 `corpus/`에 둔다. run.js는 corpus 위치를 env로 |
| business key가 없으면 VU=1 순차 재생만 결정적 | 2 | Prince Mart의 orderId는 auto increment이고, 후속 요청이 orderId와 transactionId(`order_{id}`)를 참조한다. `run.js`에는 응답 값 치환(capture)이 없다 | id를 corpus에 리터럴로 넣어야 하고, S0 리셋 + VU=1 순차일 때만 맞는다. 팀원 A/A 표준(VU=3 x3)은 성립하지 않는다 | 3단계에 VU=1 순차 재생으로 진행하고 한계로 기록(capture 추가 여부는 결정 대기) |
| 게이트웨이 VS 하나에 Store 경로와 팀원 앱 경로가 함께 있음 | 2 | 팀원 `virtualservice-shadow.yaml`이 `/_evidence/`와 `/api/orders`, `/api/coupons`를 한 리소스에 담았다 | Store 경로 때문에 팀원 VS를 그대로 적용하면, 팀원 앱 스택이 없어 `istioctl analyze`가 IST0101(Error) 4건을 낸다. 동작에는 영향 없음 | 팀원 VS는 수정 없이 적용하고 Prince Mart VS를 따로 붙였다(prefix가 겹치지 않음). 이유는 `k8s/README.md`에 기록 |

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

## 3. 수정 없이 그대로 쓴 팀원 구성요소

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
| OTel Java agent 이미지(digest 고정), `curlimages/curl:8.11.1`, `busybox:1.37`, WireMock 3.13.1 digest, `apache/kafka:4.2.1`, `mysql:8.4` | 매니페스트 |
