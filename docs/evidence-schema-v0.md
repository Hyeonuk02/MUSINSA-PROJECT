# Evidence JSON v0

architecture v10.1 §5(Phase 2.3)의 Evidence 형식을 고정한다. 만드는 쪽은 Legacy 계측 코드(`legacy/prince-mart/evidence/`)와
수집 도구(`deploy/compose/tools/collect.py`), 저장은 Evidence Store v0(`evidence-store/store.py`)다.
설계 근거는 [legacy-decision-log.md](legacy-decision-log.md) L10.

## 키

`(runId, replayRequestId, stack)`. 요청 하나가 여러 서비스를 거치므로 같은 키 안에 `service`·`kind`·`seq`가 다른 여러 건이 있다.
v10.1 §3의 `version`(New v1~v3 구분)은 `stack`과 run 정보(`POST /runs`의 arm)로 대신한다.

| 필드 | 값 |
|---|---|
| `schema` | `"evidence/v0"` |
| `runId` | `X-Run-Id` 헤더, 없으면 baggage `runId` |
| `replayRequestId` | 진입 서비스: `X-Replay-Request-Id` 헤더. Feign 하위 서비스와 Kafka consumer: baggage `replayRequestId`(OTel agent가 전파, L9) |
| `stack` | `legacy` / `new` (env `EVIDENCE_STACK`) |
| `service` | `order` / `coupon` / `payment` / `wiremock` / `kafka` |
| `kind` | 아래 4종 |
| `seq` | http·consume: 서비스 인스턴스 안 순번(리셋 때 앱 재시작으로 1부터). external: 1. event: offset + 1 |

## kind

| kind | 만드는 곳 | 단위 | 비교 수준(v10.1 §5.2) |
|---|---|---|---|
| `http` | 각 서비스 `EvidenceFilter` | 서비스가 받은 HTTP 요청 1건 | 요청 단위 |
| `consume` | order `EvidenceRecordInterceptor` | Kafka 레코드 처리 1건 | 요청 단위 |
| `external` | `collect.py` (WireMock journal) | 요청 1건이 만든 외부 호출 목록 | 요청 단위(호출 횟수·파라미터·순서) |
| `event` | `collect.py` (Kafka 토픽) | 레코드 1건 | 요청 단위(발행 수·payload) |

### 공통 (http, consume)

```json
{
  "schema": "evidence/v0",
  "runId": "run-1", "replayRequestId": "R000001", "stack": "legacy", "service": "order", "kind": "http", "seq": 1,
  "error": {"class": "com.pm.order.exception.ResourceNotFoundException", "message": "Order not found"},
  "dbAccess": {
    "total": 5,
    "summary": [{"op": "INSERT", "table": "orders", "count": 1}, {"op": "INSERT", "table": "order_items", "count": 2}],
    "statements": ["insert into orders (...) values (...)", "..."]
  },
  "outbound": [{"order": 1, "method": "GET", "url": "http://CART-SERVICE/cart/my-cart", "status": 200, "error": null, "durationMs": 12}],
  "events": [{"order": 1, "topic": "payment-events", "key": "1", "value": "{...}", "headers": {"baggage": "...", "traceparent": "..."}}],
  "timing": {"arrivedAt": 0, "completedAt": 0, "arrivedAtNano": 0, "completedAtNano": 0, "durationMs": 12.3},
  "runContext": {"runId": "run-1", "sessionId": "S001", "fixedClock": "2026-09-01T00:00:00Z"}
}
```

| 필드 | 내용 | 비교에 쓰는가 |
|---|---|---|
| `error` | 컨트롤러·listener에서 던져진 예외 class와 메시지. 없으면 null. 응답 status와 따로 본다(B6: 모두 404지만 class가 다름) | 예(Error Path) |
| `dbAccess.summary` | Hibernate가 준비한 SQL의 (동작, 주 테이블, 횟수). 처음 나온 순서 | 예 |
| `dbAccess.statements` | SQL 원문(순서대로) | 참고용 |
| `outbound` | Feign 호출 순서·method·논리 URL(`http://COUPON-SERVICE/...`)·status. Feign이 아닌 호출(가짜 PG)은 `external`에서 본다 | 예(호출 순서) |
| `events` | 처리 중 발행한 Kafka 레코드 | 예 |
| `timing` | Phase 0 RequestLogFilter와 같은 필드 + `durationMs` | 아니오. 참고 지표 |
| `runContext` | 앱이 아는 run 정보. iteration·vu·arm·corpusVersion·s0Version·imageDigest는 run script가 `POST /runs`로 등록하고 export에 합친다 | 아니오 |

### http

```json
"request":  {"method": "POST", "uri": "/orders/place", "query": "",
             "headers": {"Content-Type": ["application/json"], "X-User-Id": ["101"], "X-Replay-Request-Id": ["R000001"],
                         "X-Run-Id": ["run-1"], "X-Session-Id": ["S001"], "baggage": ["replayRequestId=R000001,..."],
                         "Host": ["localhost:8000"], "Idempotency-Key": []},
             "bodyHash": "sha256 hex", "body": "{...}"},
"response": {"status": 200, "contentType": "application/json", "body": "{...}"}
```
기록 헤더 목록은 `evidence.headers`(local profile). 짝 맞춤(Phase 2.7)은 method·uri·query·headers·bodyHash로 한다.

### consume

```json
"message": {"topic": "payment-events", "partition": 0, "offset": 0, "key": "1", "value": "{...}", "headers": {"baggage": "...", "traceparent": "..."}}
```

### external

```json
{"schema": "evidence/v0", "runId": "run-1", "replayRequestId": "R000001", "stack": "legacy", "service": "wiremock", "kind": "external", "seq": 1,
 "calls": [{"order": 1, "method": "GET", "url": "/cart/my-cart", "body": "", "status": 200, "headers": {"baggage": "...", "...": "..."}}]}
```
baggage가 없거나 runId가 다른 호출은 넣지 않고 `collect.py` 출력에 개수만 남긴다.

### event

```json
{"schema": "evidence/v0", "runId": "run-1", "replayRequestId": "R000002", "stack": "legacy", "service": "kafka", "kind": "event", "seq": 1,
 "message": {"topic": "payment-events", "partition": 0, "offset": 0, "key": "1", "value": "{...}", "headers": {"baggage": "...", "traceparent": "..."}}}
```

## 알려진 정규화 대상 (비교 엔진, Step 8)

| 위치 | 이유 |
|---|---|
| `headers.traceparent`, `b3`, `X-B3-*` (external·event·consume·events) | OTel trace id는 스택·실행마다 다르다 |
| 응답 `totalAmount` 표기(`100000` / `95000.00` / `100000.00`) | 같은 값의 BigDecimal scale 차이(L6) |
| auto-increment id | v10.1 §5.3. A/A에서는 같지만 New에서 어긋날 수 있다 |
| JSON 키 순서 | Boot/Jackson 버전에 따라 다르다(L7) |
| `timing.*` | 비교하지 않는다 |

## Store 엔드포인트 (evidence-store v0)

| | |
|---|---|
| `POST /evidence` | 1건(객체) 또는 여러 건(배열). 앱은 `X-Evidence-Internal: true`를 붙인다 |
| `POST /runs` | run 정보(runContext 나머지) |
| `GET /count?runId=[&requestId=][&stack=][&kind=]` | 건수(k6 완료 대기, flush barrier) |
| `GET /exists?requestId=&stack=[&runId=]` | 존재 여부 |
| `GET /export?runId=` | run 정보 + Evidence 전체. 정렬: stack, replayRequestId, service, kind, seq |
