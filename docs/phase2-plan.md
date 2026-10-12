# Phase 2 상세 계획 — 단일 파이프라인 end-to-end

> v3 (2026-10-11): **DB Evidence(StatementInspector, SQL 원문)를 Phase 2에 포함**, Evidence JSON v0에 `dbAccess`·`callTree` 추가, Evidence 전송 큐 유실 금지(spill)·graceful shutdown, 2.8을 **A/A run**으로 명명, 2.3 전 스택 간 DB 네트워크 격리 실측 추가. 2.1 완료(구현 시 확정 사항 반영).
> v2 (검토 반영): 2.8 canonical JSON 비교·비교 유지 필드 명확화·주장 완화, 2.1 WireMock 템플릿 문법 정정, 2.6 kubectl 명령 정정
>
> `CLAUDE.md`는 방향·확정 사항·단계 요약만 담고, **단계별 세부 작업과 완료 기준은 이 문서가 기준**이다. 전체 설계는 `docs/architecture.md`(v10.1). Phase 1 결과와 실측 교훈은 `docs/phase1-result.md`, `docs/isolation-proof.md`, `docs/decision-log.md`. CLAUDE.md와 다르면 이 문서와 architecture.md가 우선한다.

## Phase 2의 목적

Phase 1 인프라 위에서 **k6 → Istio 미러 → Legacy/New → Evidence 필터 → Evidence Store → export JSON**을 한 줄로 관통시킨다. 판정 엔진은 만들지 않는다. 종료 시점에 "같은 요청이 양쪽에 갔고 그 결과가 로컬 JSON으로 있다"가 되어야 하고, **그 JSON 형식이 곧 Phase 3 엔진의 입력 계약**이다. 이후 엔진 개발은 클러스터 없이 진행한다.

Evidence는 Response에 더해 **DB 접근(SQL 원문)**을 요청 단위로 포함한다. 종류·횟수·테이블 등 파생값은 Phase 3 엔진이 원문에서 계산하며, **앱은 가공하지 않는다**("기록은 최대 해상도, 판정은 선언된 해상도").

Phase 2에서 실측으로 확인할 것 (v10.1 2장의 가정): 독립 세션 + client business key + 요청당 New 완료 폴링 조건에서, **현재 corpus로 VU=3 반복 실행 시 요청 pairing과 비교 결과가 안정적으로 유지되는지** → 2.8에서 "VU=3, 3회 반복, diff 집합 동일"로 확인. 이는 "VU=N에서 항상 성립한다"는 일반 명제의 증명이 아니라 **이 corpus·이 조건에서의 안정성 확인**이다(논문·발표에서 그렇게 표현). 실패하면 VU=1(설정값 하나).

## Phase 1에서 배운 것 (반드시 적용)

- **Istio는 Service 포트 이름 접두사로 프로토콜을 판별** — Evidence Store 포트는 `http-evidence`로 명명. 안 하면 sidecar가 TCP로 취급
- `kind load docker-image`는 멀티아치 이미지에서 실패 → `docker save --platform` + `kind load image-archive`, digest는 노드에서 `crictl pull`
- istio-proxy는 native sidecar(initContainer). 주입 확인은 READY 2/2
- `new` 네임스페이스는 default-deny egress. 허용: kube-dns, 같은 ns, istio-system, observability, **verify** — Evidence POST는 이 허용 위에서 감
- 런타임 다운로드 금지 — 새 이미지(Evidence Store)도 kind에 로드해서 사용
- 미러 요청 Host에 접미사 없음(Istio 1.31 기본값). Host 정규화 불필요
- Ingress는 호스트 포트 80 → `http://localhost/...` (port-forward 불필요)
- Jaeger v2 조회 API는 `/api/v3/*`

## 확정 사항 (바꾸지 말 것)

- 트래픽: k6(호스트) → `http://localhost/api/...` → Istio Gateway → VirtualService route(legacy)/mirror(new)
- **replayRequestId는 k6(corpus)가 부여**, `X-Replay-Request-Id` 헤더. Envoy mirror가 헤더를 복사하므로 양쪽 동일
- business key: `orderKey`는 k6가 corpus에서 결정론적 파생(`ok-<replayRequestId>`). **후속 요청은 orderKey로 대상 지정**
- Evidence 키: `(runId, replayRequestId, stack)`. Phase 2의 service는 `order`뿐
- Evidence POST는 `X-Evidence-Internal: true`, 응답 커밋 후 비동기. 비교·span 대상 아님
- **Evidence 전송은 유실 금지**: 큐 상한·재시도 소진 시 버리지 않고 로컬 spill, flush barrier가 회수
- **DB Evidence는 `StatementInspector`가 SQL 원문만 기록**. 앱에서 종류·횟수·테이블 계산이나 SQL 주석 삽입을 하지 않는다. Hibernate JDBC 배치 off, DB 접근은 JPA 경로만(`JdbcTemplate`·native batch 금지)
- 완료 폴링: k6가 요청마다 Evidence Store `exists`로 New 도착 확인 후 다음 요청
- flush barrier: run script가 Store 수신 건수(+spill 회수분) == 기대 건수 확인 후 export·리셋
- 고정 시각 `APP_FIXED_CLOCK` 유지, S0 리셋 = MySQL `rollout restart`
- Legacy/New 앱 코드 동일(Phase 2 내내). 결함 주입은 Phase 3

## 하지 말 것

- Coupon/Payment 실서비스, Kafka, **이벤트·외부 호출 Evidence**(Phase 3). DB Evidence는 Phase 2에 포함하되 **원문 기록까지만**
- `@Async`·Kafka consumer 스레드로의 ReplayContext 전파(Phase 3)
- Normalization·4분류·Rule·Human Review(Phase 3) — 2.8의 비교 스크립트는 최소 정규화(id·시각 제거, SQL alias 치환)만
- Call Graph(Phase 4) — Evidence JSON의 `callTree`는 `null`로 자리만 예약
- 성능 테스트, Istio 추가 기능
- Evidence Store에 DB 도입(파일로 충분), 인증, UI

---

## 단계 — 하나 끝나면 다음

### 2.1 Order API를 business key 기반으로 + WireMock 결제 스텁 양쪽 배포 — ✅ 완료

할 것
- `services/order/`에 API 추가·변경 (기존 `GET /api/orders/{id}`는 유지):
  - `POST /api/orders` body `{orderKey, items:[{sku, qty, price}]}` → 201, `orderKey` UNIQUE. 같은 orderKey 재요청은 409
  - `GET /api/orders/by-key/{orderKey}` → 200 / 404
  - `POST /api/orders/{orderKey}/pay` 헤더 `Idempotency-Key` → WireMock `POST /gateway/charge` 호출(body: orderKey, amount, idempotencyKey) → 성공 시 `status=PAID`, 응답에 `transactionId`. 같은 Idempotency-Key 재요청은 게이트웨이 재호출 없이 이전 결과 반환(200)
  - `POST /api/orders/{orderKey}/cancel` → `status=CANCELLED` (PAID면 409)
- init SQL 갱신: `order_key VARCHAR UNIQUE`, `status`, `amount`, `transaction_id`, `idempotency_key`. **스키마 소유자는 init SQL 하나**(Phase 1 결정 유지, ddl-auto none)
- 게이트웨이 호출은 `RestClient`(또는 RestTemplate)로. URL은 env `PAYMENT_GATEWAY_URL` → `http://wiremock.<ns>.svc.cluster.local:8080`
- WireMock을 `legacy`에도 배포(1.5의 `new` 매니페스트 재사용, 스텁 동일). 스텁: `POST /gateway/charge` → 200, **transactionId는 요청의 Idempotency-Key에서 결정론적으로 생성**(random 절대 금지 — Legacy/New가 같은 값을 받아야 함). Order는 게이트웨이 호출 시 `Idempotency-Key`를 **헤더로도** 전달하고, 스텁은 WireMock 문법대로 `{{request.headers.Idempotency-Key}}`(또는 본문에서 `{{jsonPath request.body '$.idempotencyKey'}}`)를 쓴다. 템플릿이 적용되려면 stub에 `"transformers": ["response-template"]`를 넣거나 시작 옵션 `--global-response-templating`이 필요하다. 구현 시 실제 응답으로 문법 검증
- 이미지 재빌드 → 멀티아치 절차로 kind 로드 → 양쪽 overlay 재배포

구현 시 확정 (2.1 질문 3개)
- 주문 items는 `order_items(order_id, line_no, sku, qty, price)` 테이블로 정규화, 응답에 `line_no` 순서로 포함
- transactionId 형식 `tx-{Idempotency-Key}` (예: `tx-idem-R000003`)
- WireMock 매니페스트는 `deploy/k8s/base/wiremock.yaml`로 이동, legacy/new overlay가 함께 배포(스텁 한 벌)

끝난 기준 (충족)
- 양쪽 스택에서 `curl`로 생성(201) → by-key 조회(200) → pay(200, PAID, transactionId) → 같은 Idempotency-Key로 pay 재요청(200, 게이트웨이 호출 1회 유지 — WireMock `__admin/requests` count로 확인) → cancel(409)
- **legacy와 new에서 같은 Idempotency-Key로 결제하면 transactionId가 동일**(예: `tx-idem-R000003`) — 결정론 확인
- 같은 orderKey로 생성 재요청 409
- `rollout restart`로 S0 복원 후 orderKey 재사용 가능

### 2.2 corpus v1

할 것
- `corpus/corpus-v1.json` (k6가 읽기 쉬우니 JSON):
```json
{
  "version": "corpus-v1",
  "sessions": [
    { "id": "S001", "user": "userA", "requests": [
      { "id": "R000001", "method": "POST", "path": "/api/orders", "body": { "orderKey": "ok-R000001", "items": [ { "sku": "A-1", "qty": 1, "price": 10000 } ] } },
      { "id": "R000002", "method": "GET",  "path": "/api/orders/by-key/ok-R000001" },
      { "id": "R000003", "method": "POST", "path": "/api/orders/ok-R000001/pay", "headers": { "Idempotency-Key": "idem-R000003" } },
      { "id": "R000004", "method": "GET",  "path": "/api/orders/by-key/ok-R000001" }
    ]},
    { "id": "S002", "user": "userB", "requests": [ "...같은 흐름, ok-R000005.." ] },
    { "id": "S003", "user": "userC", "requests": [ "...정상 흐름 + 에러 경로: 없는 키 조회 404, PAID 후 cancel 409" ] }
  ]
}
```
- 규칙: 세션 간 공유 상태 없음(각자 orderKey), 본문에 실행 시점 값 없음, `id` 전역 유일, 파일 버전 고정
- `corpus/schema.json`(JSON Schema)과 검증 스크립트(`corpus/validate.py`): 필수 필드, id 유일, orderKey가 같은 세션 안에서만 참조되는지
- `expectMissing: true` (요청 단위, 선택): 없는 키 조회(404) 요청에 표기. **의미는 `validate.py`에서만** — "orderKey는 같은 세션 안에서 생성된 것만 참조" 규칙의 예외(그 세션에서 만들지 않은 키 참조 허용). k6와 `engine/verify_sameness.py`는 무시한다(판정은 Evidence 비교로만). `schema.json`의 description에 같은 의미를 명시. 409 경로(PAID 후 cancel)는 세션 내 키 참조라 플래그 없음

끝난 기준
- 세션 3개, 요청 12~14건, 에러 경로 2건 포함
- `validate.py` 통과

### 2.3 전 — 스택 간 DB 네트워크 격리 실측 (10분, `docs/isolation-proof.md` 보강)

Phase 1.3a는 데이터 독립성(new 리셋 시 legacy 불변)만 확인했다. 스택 간 격리가 **설정(JDBC URL)이 아니라 네트워크**로 보장됨을 실측한다.

| 시도 | 기대 | 결과 |
|---|---|---|
| `new` ns pod(비주입 curl) → `mysql.legacy.svc.cluster.local:3306` TCP | NetworkPolicy로 타임아웃 | (기입) |
| `new` ns pod(sidecar 주입) → 동일 | 동일 | (기입) |
| `legacy` ns pod → `mysql.new.svc.cluster.local:3306` | 동일 | (기입) |

끝난 기준: 세 경우 모두 연결 실패. 표를 `docs/isolation-proof.md`에 추가(제목: "스택 간 DB 격리").

### 2.3 Evidence Store v0 + Evidence JSON v0

할 것
- `evidence-store/` — **Python(FastAPI) 단일 파일** 권장(Java 선호 시 Spring Boot 단일 모듈). 저장은 JSON Lines 파일, `runId`별 디렉터리(emptyDir 또는 PVC; Phase 2는 emptyDir + export로 충분)
- 엔드포인트:
  - `POST /evidence` — 본문 = Evidence JSON v0. 키 `(runId, replayRequestId, stack)` 중복이면 덮어쓰기(멱등)
  - `GET /exists?runId=&requestId=&stack=` — 200 / 404 (k6 완료 폴링용)
  - `GET /count?runId=&stack=` — `{count}` (flush barrier용)
  - `GET /export?runId=` — 해당 run 전체 JSON 배열 (`stack`별로 나누어 받을 수 있게 `&stack=` 선택)
  - `DELETE /runs/{runId}` — 정리용
- `verify` 네임스페이스에 Deployment + Service(**포트명 `http-evidence`**, 8080). 주입 안 함(Phase 1 결정)
- **호스트에서 접근 경로**: Gateway VirtualService에 `/_evidence/` prefix 라우트 추가 → `evidence-store.verify.svc:8080` (rewrite로 prefix 제거). **이 라우트는 mirror 없음**이고, 같은 VirtualService 안에서 `/api/` 라우트보다 **앞에** 둔다(Istio는 순서대로 매칭)
- Evidence JSON v0 (`docs/evidence-schema-v0.json` + 예시):
```json
{
  "schemaVersion": "v0",
  "runId": "run-20261001-1",
  "replayRequestId": "R000003",
  "sessionId": "S001",
  "stack": "new",
  "service": "order",
  "version": "legacy-eq",
  "request":  { "method": "POST", "path": "/api/orders/ok-R000001/pay", "query": "", "headers": { "content-type": "application/json", "idempotency-key": "idem-R000003" }, "bodyHash": "sha256:..." },
  "response": { "status": 200, "headers": { "content-type": "application/json" }, "bodyHash": "sha256:...", "body": "{...}" },
  "dbAccess": {
    "statements": [
      { "seq": 1, "sql": "select o1_0.id,o1_0.order_key,o1_0.status from orders o1_0 where o1_0.order_key=?" },
      { "seq": 2, "sql": "insert into payments (amount,order_id,transaction_id,id) values (?,?,?,?)" }
    ],
    "truncated": false
  },
  "callTree": null,
  "timing":   { "arrivedAt": "2026-...Z", "completedAt": "2026-...Z", "arrivedNano": 0, "completedNano": 0 },
  "capturedAt": "2026-...Z"
}
```
  - `request.headers`·`response.headers`는 **지정 목록만**(`EVIDENCE_HEADERS`, 2.4(b)). `response.body`는 32KB 상한, 초과 시 hash만
  - `dbAccess.statements[].sql`은 Hibernate가 JDBC로 보내기 직전의 문자열(바인딩 전, 값은 `?`). **가공·파싱·분류 없음**. 상한: 문장당 2,048자(초과분 잘라내고 `truncated: true`), 요청당 200건(초과 시 이후 문장 버리고 `truncated: true`)
  - `callTree`는 Phase 3에서 채움. Phase 2에서는 항상 `null` — 필드 자리만 예약
  - 외부 호출/이벤트 필드는 v0에 없음 — Phase 3에서 추가(`schemaVersion` 올림)

구현 시 확정 (2.3)
- 게이트웨이 표면은 두 개뿐: `/_evidence/` → Store(rewrite `/`, mirror 없음), `/api/` → legacy + mirror new 100%. 그 외 경로는 게이트웨이 404(`NR`). 미러 대상은 선언된 표면이어야 하고, 실험 밖 요청이 조용히 legacy로 들어가는 것보다 404로 드러나는 게 낫다. 확인: `/api/orders/by-key/…` 미러됨(new 로그 1줄), `/_evidence/count` 200, `/foo` 404
- Store: 본문은 해석 없이 그대로 저장·반환, 키 누락·쿼리 파라미터 누락은 400, 중복 키는 append 후 last-wins(count는 키 수, export는 키당 1건, `(replayRequestId, stack)` 순). 메모리 인덱스라 replicas 1·워커 1
- Evidence JSON v0 해석: `response.body`는 32KB 초과 시 `null`(bodyHash 유지) / 요청 본문이 없으면 `bodyHash`는 빈 바이트열의 sha256 / 최상위 `additionalProperties: false`(필드 추가는 schemaVersion 올림)
- 베이스 이미지 digest는 고정하지 않음. run-meta에 빌드된 Store 이미지 digest를 기록(2.6)

끝난 기준
- 클러스터 안에서 `curl` POST → exists 200 → count 정확 → export로 JSON 확보
- 호스트에서 `http://localhost/_evidence/count?runId=x` 응답(200) 및 **미러되지 않음**(new 쪽 로그에 `/_evidence` 요청 없음)
- Store 이미지가 멀티아치 절차로 kind에 로드됨
- `docs/evidence-schema-v0.json`이 `dbAccess`·`callTree`를 포함하고 예시가 schema를 통과

### 2.4 Order 앱의 Evidence 필터 + ReplayContext + StatementInspector

할 것

**(a) 요청 컨텍스트 — `ReplayContext`**
- ThreadLocal 홀더 `ReplayContext { replayRequestId, runId, sessionId }`
- Evidence 필터(`OncePerRequestFilter`, `Ordered.HIGHEST_PRECEDENCE`)가 `X-Replay-Request-Id`·`X-Run-Id`·`X-Session-Id`에서 읽어 set, `finally`에서 clear(스레드 재사용 대비). 헤더가 없는 요청(수동 curl, 스모크)은 **Evidence를 남기지 않음**(로그만)
- 요청별 Evidence 버퍼는 `chain.doFilter()`가 **반환한 뒤** 닫는다 — open-in-view로 컨트롤러 반환 후 직렬화 중에도 SELECT가 나감

**(b) Request/Response 캡처**
- Phase 0 `RequestLogFilter`를 확장(또는 별도 `EvidenceFilter`): `ContentCachingRequestWrapper/ResponseWrapper`로 request/response 캡처 → `chain.doFilter` 완료(응답 커밋) 후 **비동기**(작은 executor)로 Store에 POST
  - 구현(2.4a): 요청 본문은 `ContentCachingRequestWrapper` 대신 필터가 **전체를 먼저 읽는다**(`BufferedBodyRequest`) — `request.bodyHash`는 앱이 읽은 부분이 아니라 "받은 바이트"의 해시여야 하기 때문. 응답은 `ContentCachingResponseWrapper`
- 헤더: `X-Evidence-Internal: true`. `stack`·`service`·`version`은 env(`EVIDENCE_STACK=legacy|new`, `EVIDENCE_SERVICE=order`, `EVIDENCE_VERSION`)
- Evidence POST용 HTTP 클라이언트는 **`java.net.http.HttpClient`**로 하고 OTel agent에서 그 계측만 끔(`OTEL_INSTRUMENTATION_JAVA_HTTP_CLIENT_ENABLED=false`) → 앱 span에 Evidence POST가 안 섞임. 비즈니스 외부 호출(WireMock)은 `RestClient`라 계속 계측됨. Evidence POST는 요청 trace에 섞이지 않고 단일 span의 별도 trace로 남는다(traceparent 미전파, 2.4a 실측). Phase 3 traceTopology는 destination=`evidence-store`인 trace를 방어적으로 제외
- 헤더 목록은 용도별로 분리한다
  - `EVIDENCE_HEADERS` = `X-Replay-Request-Id, X-Run-Id, X-Session-Id, Idempotency-Key, Content-Type` — EvidenceFilter는 이것만 본다. `x-request-id`·`Host`는 넣지 않는다(실행 시점 값, 판정 잡음)
  - `REQUEST_LOG_HEADERS` = Phase 1 목록(`x-request-id, Host, X-Phase1-Smoke-Id`, `Content-Type, Idempotency-Key`) + 재생 헤더 3개 — RequestLogFilter 디버깅 로그용. `x-request-id`로 Envoy 액세스 로그·Jaeger와 맞춰 본다
- 예외 경로(2.4a): `chain.doFilter` 예외 시 Evidence 없음 → k6 degraded·2.7 Undelivered로 드러남. Phase 3에서 schema v1 `error` 필드와 fault catalog '미처리 예외' 항목으로 처리

**(c) DB 접근 — `EvidenceStatementInspector`**
- `implements org.hibernate.resource.jdbc.spi.StatementInspector`. `inspect(sql)`: `ReplayContext`에 id가 있으면 현재 요청 버퍼에 `{seq, sql}` append, 없으면 무시(부팅·스키마 검증 쿼리). 항상 `sql`을 **그대로 반환**
- 등록: `HibernatePropertiesCustomizer` 빈으로 `hibernate.session_factory.statement_inspector`에 **인스턴스**를 넣는다(클래스명 문자열로 넣으면 Spring 빈 주입 불가 → ReplayContext 접근 못 함)
- 고정: `hibernate.jdbc.batch_size` 미설정(배치 off). DB 접근은 JPA 경로만
- Phase 2 범위는 **요청 스레드만**

**(d) 전송 큐 — 유실 금지**
- 비동기 POST 실패 시 재시도 3회. 큐 상한 도달 또는 재시도 소진 시 **버리지 않는다** — 로컬 파일 `/var/evidence/spill/<runId>/<replayRequestId>-<stack>.json`로 spill
- spill 위치는 **hostPath**(kind 노드 `/var/evidence/spill`, `DirectoryOrCreate`)를 order pod의 `/var/evidence/spill`에 마운트. emptyDir은 pod 교체(rollout restart) 시 사라져 "Store 또는 spill에 존재"가 성립하지 않는다. 파일명에 stack이 있어 두 스택이 같은 노드를 써도 충돌 없음. 운영이면 PVC. kind 노드 1개 전제(여러 노드면 회수가 어긋남)
- run script의 flush barrier가 spill 파일까지 회수한 뒤 기대 건수를 센다(2.6)

**(e) graceful shutdown**
- `server.shutdown=graceful`, `spring.lifecycle.timeout-per-shutdown-phase=20s`
- 종료 훅에서 Evidence 큐 flush(미전송분은 spill)
- k8s `terminationGracePeriodSeconds: 30` (앱 타임아웃보다 길게)
- 근거: S0 리셋이 `rollout restart`라 매 run마다 pod가 종료됨 → 마지막 요청들의 Evidence가 큐에 남은 채 죽을 수 있음

- Legacy/New **동일 코드**

끝난 기준
- Ingress로 헤더 붙여 요청 1건 → Store에 legacy·new Evidence 각 1건, 같은 replayRequestId, `request.bodyHash` 동일
- `POST /api/orders` Evidence의 `dbAccess.statements`에 INSERT 포함, `GET by-key`는 SELECT만. 앱 기동 시 스키마 검증 쿼리는 어떤 요청의 `dbAccess`에도 없음
- `callTree`는 `null`
- Jaeger에서 해당 trace의 **앱 span에는 Evidence POST client span이 없음**, Envoy outbound span에만 `evidence-store` 보임 (실측: 그 Envoy span은 요청 trace가 아니라 단일 span의 별도 trace)
- 응답 시간이 Evidence POST와 무관(POST 실패시켜도 응답 정상)
- Store를 내려둔 채 요청 → spill 파일 생성 → Store 올리고 회수 스크립트 실행 → Store에 도착
- 요청 직후 `rollout restart` → 마지막 요청의 Evidence가 Store 또는 spill에 존재

### 2.5 k6 — VU=1, 완료 폴링

할 것
- `k6/run.js`: `corpus-v1.json` 로드. `RUN_ID`, `VUS`(기본 1), `BASE_URL`(`http://localhost`), `EVIDENCE_URL`(`http://localhost/_evidence`) env
- VU마다 세션 목록의 자기 몫(`sessions[i % VUS]`)을 순서대로. 세션 안은 요청 하나씩
- 요청 헤더: `X-Replay-Request-Id`, `X-Run-Id`, `X-Session-Id`, corpus에 있는 헤더(`Idempotency-Key`), `Content-Type`
- **요청마다** 응답 수신 후 `GET /_evidence/exists?runId&requestId&stack=new`를 100ms 간격으로 최대 10초 폴링. 200이면 다음 요청. 타임아웃이면 그 세션에 `degraded=true` 태그를 붙이고 **그 세션의 남은 요청은 건너뜀**(상태가 어긋나므로), 다음 세션으로
- 요청 본문에 실행 시점 값 없음(`Date.now()`·random 금지). `noConnectionReuse` 기본값
- k6 summary를 `runs/<runId>/k6-summary.json`으로

끝난 기준
- VU=1로 corpus 전체 실행 → Store `count` legacy == new == 요청 수, degraded 세션 0
- 폴링이 실제로 기다리는지: New의 Evidence POST에 인위적 지연(env로 1초) 넣고 실행 → k6 iteration 시간이 그만큼 늘어남을 확인 후 지연 제거

### 2.6 run script — 리셋 · barrier · export

할 것
- `k6/run.sh`(또는 Python): 인자 `--run-id --iterations N --vus V`
```
for i in 1..N:
  runId = <base>-<i>
  preflight: istioctl proxy-config secret 으로 istio-system ingressgateway pod, legacy/new 각 order pod의
           proxy 인증서(default, Cert Chain) VALID CERT / NOT AFTER 확인
           → 만료, 또는 istioctl 실패·pod 없음 등으로 정상 확인 불가면 run을 시작하지 않고 중단(fail-closed)
           → 자동 복구(rollout restart 등) 없음 — 사람이 복구 후 재실행
           Store 준비 확인: 게이트웨이 경유 /_evidence/count 200 (Store rollout 직후 endpoint 반영 전 503으로 Evidence가 유실된 2.4a 실측)
  reset:   kubectl rollout restart deployment/mysql -n legacy
           kubectl rollout restart deployment/mysql -n new          (kubectl은 -n을 하나만 받음 — 네임스페이스별로 따로)
           kubectl rollout status  deployment/mysql -n legacy
           kubectl rollout status  deployment/mysql -n new
           → order readiness 대기(양쪽) → WireMock __admin/requests/reset 양쪽
  k6:      RUN_ID=runId VUS=V k6 run k6/run.js
  barrier: (1) 양쪽 order pod의 spill 디렉터리에 runId 파일이 있으면 Store로 재전송 후 삭제
           (2) /_evidence/count?runId&stack=legacy 와 new 가 기대 건수(= 발송 건수 − degraded 세션의 건너뛴 건수)와 같아질 때까지 폴링(최대 30초). 미달 시 누락 requestId 목록 출력 후 중단
  export:  /_evidence/export?runId&stack=legacy → runs/<runId>/legacy.json, new → runs/<runId>/new.json, k6-summary.json, run-meta.json(corpus 버전, 이미지 digest, 고정 시각, VUS)
```
- preflight 근거: 호스트 sleep 후 워크로드 인증서 만료로 메시 전체 503 UC가 난 실측(`docs/isolation-proof.md` "관찰")
- barrier(spill 회수)는 **반드시 다음 iteration의 reset 전**에 끝나야 한다(spill은 hostPath라 pod 재시작에도 남지만, run 경계를 지키기 위해 다음 run 전에 회수)
- `runs/`는 `.gitignore`(결과는 docs에 요약만)

끝난 기준
- `--iterations 3 --vus 1` 실행 → run 3개, 각각 legacy.json/new.json, 누락 0, run-meta 기록
- 리셋 후 첫 요청의 orderKey 재사용이 409 없이 201(진짜 S0)

### 2.7 동일성·pairing 검증 (Phase 0 4.6 이관)

할 것
- `engine/verify_sameness.py --run runs/<runId>`: legacy.json·new.json을 replayRequestId로 짝지어 전건 대조
  - 짝: 양쪽 존재 여부(Undelivered 목록)
  - request: method / path / query / 지정 헤더 / bodyHash 일치
  - 출력: 항목별 PASS(n/n), Undelivered 목록, 실패 시 requestId와 필드
  - `dbAccess`는 여기서 비교하지 않음(요청 동일성만)
  - 메모: `response.body`가 `null`(32KB 초과)이면 `bodyHash`만 비교 (응답을 비교하는 2.8 `diff_v0.py`에도 동일 적용)

끝난 기준
- 2.6의 run 3개 모두 전건 PASS, Undelivered 0

### 2.8 A/A run — VU=3 × 3회 반복, 현재 조건에서 요청 단위 비교의 안정성 확인

코드가 같은 두 스택(Legacy = New)으로 돌리는 **A/A run**이다. 목적은 Legacy/New 차이 탐지가 아니라 **파이프라인 자체가 잡음을 만들지 않음**을 확인하는 것. Phase 3 각 단계의 완료 조건에도 "A/A run 3회, diff 0 또는 잡음 목록 명시"를 둔다.

할 것
- `engine/diff_v0.py --run runs/<runId>`: 비교의 최소판
  - **Response**: `response.status` 일치 + `response.body`가 JSON이면 **parse → 제외 필드 제거 → key 정렬 → canonical JSON 직렬화 → 비교** (문자열 비교 금지: key 순서만 달라도 DIFF가 남). 제외 필드는 **DB auto `id`만**. `orderKey`·`status`·`amount`·`transactionId`(WireMock이 Idempotency-Key에서 결정론적으로 생성)·`createdAt`(고정 시각이므로 양쪽 동일해야 함)은 **유지해서 비교** — createdAt이 다르면 고정 시각이 깨진 것이고, transactionId가 다르면 결제 결과가 다른 것
  - **dbAccess**: 문장 **개수·순서**와 각 `sql`의 정규화 문자열 일치. 정규화 = 소문자화, 연속 공백을 1개로, Hibernate alias(`[a-z]+\d+_\d+`) → `_a_` 치환. 원문 그대로 비교 금지(alias 생성 순서가 바뀔 수 있음). **이 정규화는 이 스크립트에만 둔다 — 앱에 넣지 않는다**
  - 차이 나는 requestId 집합(response / dbAccess 구분)을 출력. 이건 Phase 3 Normalization의 자리표시자이지 엔진이 아님
- `run.sh --iterations 3 --vus 3` → run 3개 → 각 run의 diff 집합 비교

끝난 기준
- 세 run의 diff 집합이 **동일**(코드가 같으므로 공집합 기대). Undelivered 0, degraded 0. 결과는 "현재 corpus·세션 독립 조건에서 VU=3 반복 실행이 안정적"으로 기록(일반화 주장 금지)
- 동일하지 않으면: 차이 난 requestId의 Evidence를 나란히 놓고 원인 분류(타이밍/유실/ID/비결정 쿼리 순서/open-in-view 지연 SELECT) → `docs/phase2-result.md`에 기록 → `--vus 1`로 재실행해 공집합 확인 → **VU=1 확정**을 decision-log에

Phase 2 종료 조건: 2.1~2.8 완료 + `docs/phase2-result.md`(Evidence 스키마 v0 확정본 링크, 2.8 결과, VU 결정, A/A 잡음 목록) + `git tag phase2-done`. **이 시점부터 Phase 3 엔진 개발은 `runs/` JSON만으로 클러스터 없이 진행.**

---

## 레포 구조 (Phase 2에서 채워지는 부분)

```
services/order/          business key API, EvidenceFilter, ReplayContext, EvidenceStatementInspector
evidence-store/          FastAPI 단일 파일 + Dockerfile
corpus/                  corpus-v1.json, schema.json, validate.py
k6/                      run.js, run.sh (spill 회수 포함)
engine/                  verify_sameness.py, diff_v0.py   (로컬 실행, 클러스터 접근 없음)
deploy/k8s/verify/       evidence-store.yaml
deploy/k8s/istio/        virtualservice-shadow.yaml  (/_evidence 라우트 + /api 라우트·mirror)
deploy/k8s/base/         wiremock.yaml (2.1에서 legacy/new 공유로 이동)
runs/                    (gitignore) run별 export
docs/                    evidence-schema-v0.json, phase2-result.md, isolation-proof.md(스택 간 DB 격리 추가)
```

## 추가 결정 필요 (구현 중 정하지 말고 질문)

- ~~Evidence Store 구현 언어~~ → Python(FastAPI)으로 확정 (decision-log D12: 앱 밖은 Python)
- `response.body` 저장 상한(32KB 기본)과 초과 정책
- 완료 폴링 타임아웃(10초 기본)·flush barrier 타임아웃(30초 기본)
- degraded 세션 처리: 남은 요청 건너뜀(기본) vs run 전체 중단
- ~~spill 디렉터리 위치~~ → hostPath(kind 노드 `/var/evidence/spill`)로 확정 (2.4(d))
- `terminationGracePeriodSeconds`·shutdown 타임아웃 값(30s/20s 기본)
- ~~WireMock 응답의 결정론적 transactionId 생성 방식~~ → 2.1에서 `tx-{Idempotency-Key}`로 확정
- 2.8에서 diff 집합이 다를 때 VU=1로 내릴지, 원인이 유실이면 폴링 타임아웃만 늘릴지

## 실행 지시 (CLAUDE.md에도 동일)

위 문서를 기준으로 **"2.3 전" 격리 실측을 먼저 하고 2.2부터** 진행하자(2.1 완료). 한 번에 한 단계만 진행하고, 각 단계에서 무엇을 만들지와 끝난 기준을 먼저 설명한 뒤 내가 실행 결과를 확인하면 다음으로 넘어간다. 오류는 해당 단계에서 해결한다. 문서에 없는 설계 결정이 필요하면 임의로 정하지 말고 질문해라. "하지 말 것" 목록과 Phase 3 이후 항목은 구현하지 않는다. 단계마다 `phase2.x: ...` 형식으로 커밋한다. 시작 전에 루트 `CLAUDE.md`의 Phase 2 표와 확정 사항을 이 문서(v3)와 맞추고, `docs/decision-log.md`에 "DB Evidence v3 / Evidence 전송 큐 정책 / DB 격리의 두 축" 세 항목을 추가해라(내용은 `phase2-plan-patch-v3.md` 3절).
