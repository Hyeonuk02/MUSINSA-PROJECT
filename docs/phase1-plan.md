# Phase 1 상세 계획 — Kubernetes + Istio 기반

> `CLAUDE.md`는 방향·확정 사항·단계 요약만 담고, **단계별 세부 작업과 완료 기준은 이 문서가 기준**이다. 전체 설계는 `docs/architecture.md`(v10). CLAUDE.md와 다르면 이 문서와 architecture.md가 우선한다.

## 프로젝트 한 줄

Legacy → New 시스템 교체 시 같은 트래픽을 Istio 미러링으로 양쪽에 흘리고, 각 서비스 내부에서 수집한 Evidence(응답·DB 접근·외부 호출·이벤트·순서)를 비교해 차이를 SAME / Improvement / Contract Violation / Uncertain으로 분류, Uncertain만 사람이 검토하고 그 판단을 Rule로 축적하는 검증 파이프라인. 실험 시스템은 주문/쿠폰/결제 Spring Boot 서비스.

## Phase 1의 목적

연구 핵심(Evidence·판정 엔진)이 올라갈 **인프라 바닥을 얇게** 만든다. 이 Phase에서 연구 요구사항에 직접 닿는 건 **1.5(격리 증명)** 하나이고, 나머지는 바닥 공사다.

## 이미 있는 것 (Phase 0, `poc/nginx-mirroring/`)

- 최소 Spring Boot Order 앱: `POST /api/orders`, `GET /api/orders/{id}`, Postgres, auto-increment ID, Java 17 — **Phase 1에서 MySQL 8로 전환**(1.3a). Phase 0 코드는 동결하고 `services/order/`로 복사해 전환
- 같은 이미지로 legacy/new 두 컨테이너, DB 분리 (Docker Compose)
- Request Log 필터: requestId, seq, method, uri, query, headers, bodyHash(SHA-256), arrivedAt/completedAt(ms, nano)
- nginx 미러링 — **Phase 1에서 쓰지 않음.** 최종 delivery는 Istio. 코드는 동결

Phase 1은 이 Order 앱을 k8s에 올린다. 앱 코드 변경은 둘뿐: `APP_FIXED_CLOCK` env, Postgres → MySQL 전환(드라이버·dialect·JDBC URL·스키마 SQL).

## 확정 사항 (바꾸지 말 것)

- 실행 환경: Kubernetes(kind) + Istio/Envoy. Istio의 역할은 **미러링 배달 · REGISTRY_ONLY guardrail · proxy 스팬** 셋뿐
- **격리 경계는 Kubernetes NetworkPolicy.** Istio REGISTRY_ONLY는 보안 경계가 아니라 미등록 의존성 탐지용 guardrail (Istio 보안 모범사례)
- 네임스페이스: `istio-system`, `observability`, `legacy`, `new`, `verify`
- DB는 **MySQL 8** Deployment + emptyDir + init SQL(`/docker-entrypoint-initdb.d`) → `rollout restart`가 곧 S0 리셋. Legacy/New 동일 엔진
- 버전 고정: kind 버전, `kindest/node` 이미지(digest 포함), Istio 버전을 `docs/phase1-result.md`에 기록. Istio는 설치 시점의 공식 Kubernetes 지원 매트릭스로 node 이미지 버전을 맞춘다
- 두 스택 모두 `APP_FIXED_CLOCK` env로 시각 고정
- 트레이싱 샘플링 100% (기본 1%)
- 미러 요청은 Host에 `-shadow`가 붙음 — 앱이 Host에 의존하면 안 됨

## 하지 말 것

- Coupon/Payment 서비스, WireMock 연동 로직, Kafka — Phase 2·3
- Evidence Store, Evidence 필터 확장, k6, 비교 로직 — Phase 2
- Istio의 다른 기능(canary, retry, circuit breaker, mTLS 튜닝, Egress Gateway, Kiali, 오토스케일)
- 성능 튜닝, 리소스 최적화
- Docker Compose 파일 수정 (Phase 0 동결)

---

## Phase 1 단계 — 하나 끝나면 다음

각 단계는 "할 것 → 끝난 기준". 시작 전에 무엇을 만들지와 끝난 기준을 먼저 설명하고, 내가 실행 결과를 확인한 뒤 다음으로 넘어간다.

### 1.1 클러스터와 네임스페이스

할 것
- kind **≥ v0.25.0** 사용(기본 kindnetd에 NetworkPolicy 지원, v0.24의 DNS 이슈 수정판). `kind version` 기록
- 설치할 Istio 버전의 공식 Kubernetes 지원 매트릭스를 확인해 그에 맞는 `kindest/node` 이미지(digest 포함)로 클러스터 생성. 단일 노드
- `kind-config.yaml`에 node 이미지 고정 → `deploy/k8s/kind-config.yaml`
- 네임스페이스 `legacy`, `new`, `verify`, `observability` 생성 (`istio-system`은 1.2에서) → `deploy/k8s/00-namespaces.yaml`
- Phase 0 Order 이미지를 로컬 빌드 → `kind load docker-image` → 노드 안에 들어갔는지 확인
- **NetworkPolicy 스모크**: 임시 네임스페이스에 **HTTP 서버 pod(`nginx` 또는 `http-echo`) + curl client pod**. 정책 없을 때 curl → 200 확인 → 서버 pod를 선택하는 default-deny ingress 정책 적용 → curl 실패(타임아웃) → 정책 삭제 → 다시 200 (kindnetd의 NetworkPolicy가 실제로 동작하는지). curl끼리는 듣는 포트가 없어 테스트가 안 됨

끝난 기준
- `kubectl get nodes` → Ready, 네임스페이스 4개 존재
- `docker exec <kind-node> crictl images | grep order` 에 이미지 존재 (pod 기동은 1.3a에서 — DB 없이는 뜨지 않음)
- NetworkPolicy 스모크 통과. 실패하면 **그때만** 별도 CNI 검토(질문으로 올림)
- `docs/phase1-result.md`에 `kind version / node image(digest) / 예정 Istio 버전` 기록

### 1.2 Istio 설치와 sidecar 주입

할 것
- 1.1에서 정한 Istio 버전의 `istioctl`로 `istioctl install --set profile=default -y`
- `legacy`, `new`에 `istio-injection=enabled` 라벨
- 샘플 pod(예: `curl` 이미지)를 `legacy`에 띄워 주입 확인
- `deploy/k8s/istio/README.md`에 설치 명령·버전 기록

끝난 기준
- pod에 컨테이너 2개 (`app`, `istio-proxy`)
- `istioctl analyze` 경고 없음
- `docs/phase1-result.md`에 Istio 버전 확정 기록 (kind / node image / Istio 세 줄이 모두 채워짐)

### 1.3a 앱 배포 — 기능 확인

할 것
- Phase 0 Order 앱을 `services/order/`로 복사하고 **MySQL 8로 전환**: `mysql-connector-j` 의존성, `MySQLDialect`, JDBC URL에 `serverTimezone=UTC`, 스키마 SQL을 MySQL 문법(`AUTO_INCREMENT`)으로. Phase 0 코드는 건드리지 않음
- Order env에 `APP_FIXED_CLOCK=2026-09-01T00:00:00Z` 추가. 앱에서 이 값으로 `java.time.Clock` 빈을 만들어 `createdAt` 등에 사용 (env 없으면 시스템 시각 — 개발 편의). JVM 타임존은 UTC로 고정
- `legacy`, `new` 각각에: MySQL Deployment(**`strategy: Recreate`** — RollingUpdate면 `rollout restart` 시 새 pod가 먼저 떠서 Service 뒤에 MySQL 두 개가 잠깐 공존함. Recreate여야 '리셋 = 깨끗한 인스턴스 하나'가 보장됨; emptyDir; init SQL은 ConfigMap → `/docker-entrypoint-initdb.d`; `MYSQL_ROOT_PASSWORD`·`MYSQL_DATABASE` env; **readiness probe**: `mysqladmin ping`) + Service, Order Deployment(MySQL readiness 이후 기동하도록 initContainer 또는 재시도) + Service
- `deploy/k8s/base/` + `deploy/k8s/legacy/`, `deploy/k8s/new/` overlay (kustomize, 네임스페이스만 다름)

끝난 기준
- 두 네임스페이스 각각 `kubectl port-forward`로 `POST /api/orders` 201, `GET /api/orders/1` 200, 없는 id 404
- 생성된 주문의 `createdAt`이 고정 시각(2026-09-01T00:00:00Z)
- `kubectl rollout restart deployment/mysql -n new` 후 readiness 통과 → DB가 시드 상태로 복원(주문 없음, 다음 id = 1)

### 1.3b 앱 배포 — 메시 경유 확인

할 것
- sidecar가 주입된 curl pod에서 `http://order.legacy.svc.cluster.local:8080/api/orders/1` 및 `new` 호출

끝난 기준
- 앱 로그에 Envoy가 넣은 `x-request-id` 헤더가 보임
- `istioctl proxy-config routes <curl-pod> -n legacy`에서 order 서비스 경로 확인
- port-forward 결과와 응답 동일

### 1.4 관측: OTel Collector + Jaeger

할 것
- `observability`에 OTel Collector(**OTLP 수신 → OTLP exporter로 Jaeger에 전달**) + Jaeger(OTLP 수신 포트 4317/4318 활성화). 예전 native `jaeger` exporter는 Collector에서 제거됐으므로 쓰지 않음
- Istio 트레이싱은 **두 단계**: (1) `meshConfig.extensionProviders`에 OTel provider 정의(`opentelemetry` 타입, service = Collector의 `observability` 네임스페이스 FQDN, port 4317) — `istioctl install` 시 IstioOperator 또는 `istio` ConfigMap 수정 (2) `Telemetry` 리소스(`istio-system`, 메시 전역)에서 그 provider 이름을 `tracing.providers`로 선택하고 `randomSamplingPercentage: 100`. Telemetry만 만들면 provider를 찾지 못함
- Order 이미지에 OTel Java agent 부착 (HTTP 서버/클라이언트, JDBC 자동 계측). `OTEL_EXPORTER_OTLP_ENDPOINT`를 Collector로
- `deploy/k8s/observability/`, `deploy/k8s/istio/meshconfig-tracing.yaml`(extensionProviders), `deploy/k8s/istio/telemetry.yaml`

끝난 기준
- curl pod → order 호출 1건이 Jaeger에서 **Envoy span과 앱 span이 한 trace**로 보임
- 요청 10건 보내면 trace 10건 (샘플링 100% 확인)

### 1.5 격리 (Fail-closed) — 두 테스트를 원인별로 분리

할 것 (순서 중요)
1. `new`에 WireMock Deployment + Service 배포 (메시 포함, 스텁 하나: `GET /ping` → 200)
2. Istio `outboundTrafficPolicy: REGISTRY_ONLY` (meshConfig) + `new`에 `Sidecar` 리소스(egress 허용: 같은 네임스페이스, `istio-system`, `observability`, `verify`)
3. **테스트 ①** (NetworkPolicy 적용 전): `new`에 **sidecar 주입된 curl pod**(`curlimages/curl`, 주입 기본값)를 띄워 `curl -v https://example.com`. Order 앱 이미지에는 curl이 없고 앱 컨테이너에 exec하는 것도 피함
4. `new`에 NetworkPolicy: default-deny egress + 허용(kube-dns, 같은 네임스페이스, `istio-system`, `observability`, `verify`)
5. **테스트 ②**: `new`에 `sidecar.istio.io/inject: "false"` 어노테이션으로 띄운 **비주입 curl pod**에서 같은 `curl -v https://example.com`
6. 두 curl pod 모두에서 WireMock `GET /ping` 호출은 성공해야 함 (허용 목록이 정상 동작)
- `deploy/k8s/new/networkpolicy.yaml`, `deploy/k8s/istio/sidecar-new.yaml`, `deploy/k8s/new/wiremock.yaml`

끝난 기준 — **두 실패의 서명이 달라야 통과**
- ①: 즉시 HTTP 502, 해당 curl pod의 istio-proxy access log에 `BlackHoleCluster` (= sidecar가 미등록 목적지를 거부 — guardrail)
- ②: HTTP 응답 없이 TCP 연결 타임아웃 (= sidecar가 없어도 NetworkPolicy가 차단 — 경계)
- WireMock 호출 성공 ①② 모두
- 결과(명령, 출력, 로그 발췌)를 `docs/isolation-proof.md`에 기록

주의: REGISTRY_ONLY를 격리의 근거로 쓰지 않는다. ①은 "guardrail이 동작한다"의 증거이고, 격리 증명은 ②다.

### 1.6 Shadow 미러링 스모크

할 것
- Istio Ingress Gateway + `Gateway` 리소스
- `VirtualService`: `route → order.legacy`, `mirror → order.new`, `mirrorPercentage 100`
- Ingress로 `POST /api/orders` 1건, 요청에 **`X-Phase1-Smoke-Id: smoke-001`** 헤더를 직접 넣어 보냄
- `deploy/k8s/istio/gateway.yaml`, `virtualservice-shadow.yaml`

끝난 기준
- legacy·new 앱 로그 모두에 **같은 `X-Phase1-Smoke-Id`** (클라이언트가 넣은 헤더가 미러에 복사됨 — 최종 검증이 의존하는 성질)
- `x-request-id`는 Envoy가 붙였는지 **관찰용**으로만 확인 (양쪽 같으면 기록, 아니어도 실패 아님)
- new 쪽 로그의 Host 헤더에 `-shadow` 접미사
- 클라이언트는 legacy 응답만 받음

Phase 1 종료 조건: 1.1~1.6 완료 + `docs/phase1-result.md`(Istio 버전, 각 단계 확인 결과, isolation-proof 링크).

---

## 레포 구조 (Phase 1에서 채워지는 부분)

```
deploy/k8s/
├── kind-config.yaml   node 이미지 digest 고정
├── 00-namespaces.yaml
├── istio/          설치 명령·버전, telemetry.yaml, sidecar-new.yaml, gateway.yaml, virtualservice-shadow.yaml
├── observability/  otel-collector.yaml, jaeger.yaml
├── base/           order·mysql 매니페스트 (kustomize base)
├── legacy/         overlay
└── new/            overlay + networkpolicy.yaml + wiremock.yaml
services/order/     Phase 0 앱 복사 + MySQL 전환 + APP_FIXED_CLOCK
docs/
├── phase1-result.md   kind / node image / Istio 버전, 단계별 결과
└── isolation-proof.md
```

## 추가 결정 필요 (구현 중 정하지 말고 질문)

- Istio 버전 — 최신 안정 버전으로 시작하되 1.1에서 node 이미지와 함께 확정·기록
- kind 노드 리소스가 부족하면 Jaeger all-in-one 대신 경량 대안을 쓸지
- OTel Java agent 부착 방식 (이미지에 포함 vs initContainer)
- 1.1 NetworkPolicy 스모크가 실패할 때만: 별도 CNI 검토 (기본 kindnetd로 통과하면 그대로 사용)
- MySQL 문자셋·collation 기본값(utf8mb4) 외 특별 설정이 필요한지 — 필요 없으면 기본값

## 실행 지시 (CLAUDE.md에도 동일)

위 내용을 기준으로 Phase 1.1부터 시작하자. 한 번에 여러 단계를 구현하지 말고, 각 단계에서 무엇을 만들지와 끝난 기준을 먼저 설명한 뒤 내가 실행 결과를 확인하면 다음으로 넘어간다. 오류는 해당 단계에서 해결한다. 문서에 없는 설계 결정이 필요하면 임의로 정하지 말고 나에게 질문해라. "하지 말 것" 목록과 Phase 2 이후 항목은 구현하지 않는다.
