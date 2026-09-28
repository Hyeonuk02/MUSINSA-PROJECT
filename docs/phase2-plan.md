# Phase 2 상세 계획 — 단일 파이프라인 end-to-end

> v2 (검토 반영): 2.8 canonical JSON 비교·비교 유지 필드 명확화·주장 완화, 2.1 WireMock 템플릿 문법 정정, 2.6 kubectl 명령 정정
>
> `CLAUDE.md`는 방향·확정 사항·단계 요약만 담고, **단계별 세부 작업과 완료 기준은 이 문서가 기준**이다. 전체 설계는 `docs/architecture.md`(v10.1). Phase 1 결과와 실측 교훈은 `docs/phase1-result.md`, `docs/isolation-proof.md`, `docs/decision-log.md`. CLAUDE.md와 다르면 이 문서와 architecture.md가 우선한다.

## Phase 2의 목적

Phase 1 인프라 위에서 **k6 → Istio 미러 → Legacy/New → Evidence 필터 → Evidence Store → export JSON**을 한 줄로 관통시킨다. 판정 엔진은 만들지 않는다. 종료 시점에 "같은 요청이 양쪽에 갔고 그 결과가 로컬 JSON으로 있다"가 되어야 하고, **그 JSON 형식이 곧 Phase 3 엔진의 입력 계약**이다. 이후 엔진 개발은 클러스터 없이 진행한다.

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
- 완료 폴링: k6가 요청마다 Evidence Store `exists`로 New 도착 확인 후 다음 요청
- flush barrier: run script가 Store 수신 건수 == 기대 건수 확인 후 export·리셋
- 고정 시각 `APP_FIXED_CLOCK` 유지, S0 리셋 = MySQL `rollout restart`
- Legacy/New 앱 코드 동일(Phase 2 내내). 결함 주입은 Phase 3

## 하지 말 것

- Coupon/Payment 실서비스, Kafka, DB 접근·이벤트·외부 호출 Evidence(Phase 3)
- Normalization·4분류·Rule·Human Review(Phase 3) — 2.8의 비교 스크립트는 최소 정규화(id·시각 제거)만
- Call Graph(Phase 4), 성능 테스트, Istio 추가 기능
- Evidence Store에 DB 도입(파일로 충분), 인증, UI

---

## 단계 — 하나 끝나면 다음

### 2.1 Order API를 business key 기반으로 + WireMock 결제 스텁 양쪽 배포

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

끝난 기준
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

끝난 기준
- 세션 3개, 요청 12~14건, 에러 경로 2건 포함
- `validate.py` 통과

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
  "timing":   { "arrivedAt": "2026-...Z", "completedAt": "2026-...Z", "arrivedNano": 0, "completedNano": 0 },
  "capturedAt": "2026-...Z"
}
```
  - `request.headers`·`response.headers`는 **지정 목록만**(REQUEST_LOG_HEADERS 재사용). `response.body`는 32KB 상한, 초과 시 hash만
  - DB/외부 호출/이벤트 필드는 v0에 없음 — Phase 3에서 추가(`schemaVersion` 올림)

끝난 기준
- 클러스터 안에서 `curl` POST → exists 200 → count 정확 → export로 JSON 확보
- 호스트에서 `http://localhost/_evidence/count?runId=x` 응답(200) 및 **미러되지 않음**(new 쪽 로그에 `/_evidence` 요청 없음)
- Store 이미지가 멀티아치 절차로 kind에 로드됨

### 2.4 Order 앱의 Evidence 필터

할 것
- Phase 0 `RequestLogFilter`를 확장(또는 별도 `EvidenceFilter`): `ContentCachingRequestWrapper/ResponseWrapper`로 request/response 캡처 → `chain.doFilter` 완료(응답 커밋) 후 **비동기**(작은 executor)로 Store에 POST
- 헤더: `X-Evidence-Internal: true`. `stack`·`service`·`version`은 env(`EVIDENCE_STACK=legacy|new`, `EVIDENCE_SERVICE=order`, `EVIDENCE_VERSION`)
- `runId`·`replayRequestId`·`sessionId`는 요청 헤더 `X-Run-Id`·`X-Replay-Request-Id`·`X-Session-Id`에서. 헤더가 없는 요청(수동 curl, 스모크)은 **Evidence를 남기지 않음**(로그만)
- Evidence POST용 HTTP 클라이언트는 **`java.net.http.HttpClient`**로 하고 OTel agent에서 그 계측만 끔(`OTEL_INSTRUMENTATION_JAVA_HTTP_CLIENT_ENABLED=false`) → 앱 span에 Evidence POST가 안 섞임. 비즈니스 외부 호출(WireMock)은 `RestClient`라 계속 계측됨. Envoy outbound span은 남으니 Phase 3에서 destination이 `evidence-store`인 span은 traceTopology에서 제외
- 실패 시 재시도 3회 후 로그. 큐 상한. 앱 종료 시 flush
- `REQUEST_LOG_HEADERS`에 `X-Replay-Request-Id, X-Run-Id, X-Session-Id, Idempotency-Key, Content-Type` 
- Legacy/New **동일 코드**

끝난 기준
- Ingress로 헤더 붙여 요청 1건 → Store에 legacy·new Evidence 각 1건, 같은 replayRequestId, `request.bodyHash` 동일
- Jaeger에서 해당 trace의 **앱 span에는 Evidence POST client span이 없음**, Envoy outbound span에만 `evidence-store` 보임
- 응답 시간이 Evidence POST와 무관(POST 실패시켜도 응답 정상)

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
  reset:   kubectl rollout restart deployment/mysql -n legacy
           kubectl rollout restart deployment/mysql -n new          (kubectl은 -n을 하나만 받음 — 네임스페이스별로 따로)
           kubectl rollout status  deployment/mysql -n legacy
           kubectl rollout status  deployment/mysql -n new
           → order readiness 대기(양쪽) → WireMock __admin/requests/reset 양쪽
  k6:      RUN_ID=runId VUS=V k6 run k6/run.js
  barrier: /_evidence/count?runId&stack=legacy 와 new 가 기대 건수(= 발송 건수 − degraded 세션의 건너뛴 건수)와 같아질 때까지 폴링(최대 30초). 미달 시 누락 requestId 목록 출력 후 중단
  export:  /_evidence/export?runId&stack=legacy → runs/<runId>/legacy.json, new → runs/<runId>/new.json, k6-summary.json, run-meta.json(corpus 버전, 이미지 digest, 고정 시각, VUS)
```
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

끝난 기준
- 2.6의 run 3개 모두 전건 PASS, Undelivered 0

### 2.8 VU=3 × 3회 반복 — 현재 조건에서 요청 단위 비교의 안정성 확인

할 것
- `engine/diff_v0.py --run runs/<runId>`: 응답 비교의 최소판. `response.status` 일치 + `response.body`가 JSON이면 **parse → 제외 필드 제거 → key 정렬 → canonical JSON 직렬화 → 비교** (문자열 비교 금지: key 순서만 달라도 DIFF가 남). 제외 필드는 **DB auto `id`만**. `orderKey`·`status`·`amount`·`transactionId`(WireMock이 Idempotency-Key에서 결정론적으로 생성)·`createdAt`(고정 시각이므로 양쪽 동일해야 함)은 **유지해서 비교** — createdAt이 다르면 고정 시각이 깨진 것이고, transactionId가 다르면 결제 결과가 다른 것. 차이 나는 requestId 집합을 출력. 이건 Phase 3 Normalization의 자리표시자이지 엔진이 아님
- `run.sh --iterations 3 --vus 3` → run 3개 → 각 run의 diff 집합 비교

끝난 기준
- 세 run의 diff 집합이 **동일**(코드가 같으므로 공집합 기대). Undelivered 0, degraded 0. 결과는 "현재 corpus·세션 독립 조건에서 VU=3 반복 실행이 안정적"으로 기록(일반화 주장 금지)
- 동일하지 않으면: 차이 난 requestId의 Evidence를 나란히 놓고 원인 분류(타이밍/유실/ID) → `docs/phase2-result.md`에 기록 → `--vus 1`로 재실행해 공집합 확인 → **VU=1 확정**을 decision-log에

Phase 2 종료 조건: 2.1~2.8 완료 + `docs/phase2-result.md`(Evidence 스키마 v0 확정본 링크, 2.8 결과, VU 결정) + `git tag phase2-done`. **이 시점부터 Phase 3 엔진 개발은 `runs/` JSON만으로 클러스터 없이 진행.**

---

## 레포 구조 (Phase 2에서 채워지는 부분)

```
services/order/          business key API, EvidenceFilter
evidence-store/          FastAPI 단일 파일 + Dockerfile
corpus/                  corpus-v1.json, schema.json, validate.py
k6/                      run.js, run.sh
engine/                  verify_sameness.py, diff_v0.py   (로컬 실행, 클러스터 접근 없음)
deploy/k8s/verify/       evidence-store.yaml
deploy/k8s/istio/        virtualservice-gateway.yaml (/_evidence 라우트 + /api 라우트·mirror)
deploy/k8s/legacy/       wiremock.yaml 추가
runs/                    (gitignore) run별 export
docs/                    evidence-schema-v0.json, phase2-result.md
```

## 추가 결정 필요 (구현 중 정하지 말고 질문)

- Evidence Store 구현 언어 — 기본 Python(FastAPI). Java로 통일하고 싶으면 그때 결정
- `response.body` 저장 상한(32KB 기본)과 초과 정책
- 완료 폴링 타임아웃(10초 기본)·flush barrier 타임아웃(30초 기본)
- degraded 세션 처리: 남은 요청 건너뜀(기본) vs run 전체 중단
- WireMock 응답의 결정론적 transactionId 생성 방식
- 2.8에서 diff 집합이 다를 때 VU=1로 내릴지, 원인이 유실이면 폴링 타임아웃만 늘릴지

## 실행 지시 (CLAUDE.md에도 동일)

위 문서를 기준으로 Phase 2.1부터 시작하자. 한 번에 한 단계만 진행하고, 각 단계에서 무엇을 만들지와 끝난 기준을 먼저 설명한 뒤 내가 실행 결과를 확인하면 다음으로 넘어간다. 오류는 해당 단계에서 해결한다. 문서에 없는 설계 결정이 필요하면 임의로 정하지 말고 질문해라. "하지 말 것" 목록과 Phase 3 이후 항목은 구현하지 않는다. 단계마다 `phase2.x: ...` 형식으로 커밋한다.
