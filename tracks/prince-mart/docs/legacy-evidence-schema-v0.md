# Evidence JSON v0 — Prince Mart 베이스라인 트랙

architecture v10.1 §5(Phase 2.3)의 Evidence 형식을 이 트랙에서 고정한다.
만드는 쪽은 Legacy 계측 코드(`legacy/prince-mart/evidence/`)와 수집 도구(`deploy/compose/tools/collect.py`),
저장은 Evidence Store v0(`baseline/evidence-store/store.py`)다. 설계 근거는 [legacy-decision-log.md](legacy-decision-log.md) L10, L11.

**호환성**: 공통 필드 이름·Store API·export 배치는 hyeonuk-dev `docs/phase2-plan.md`(2.3~2.6)의 계약과 같게 맞췄다.
이 트랙은 별개로 구축하고, 합칠 때 어느 구현을 남길지만 고르면 되도록 한 것이다. DB 접근·나가는 호출·이벤트·예외와
`kind`(한 키 안의 여러 건)는 이 트랙의 확장이다(팀원 계획에서는 Phase 3 항목).

## 키

`(runId, replayRequestId, stack)`. 요청 하나가 여러 서비스를 거치므로 같은 키 안에 `service`·`kind`·`seq`가 다른 여러 건이 있다.
Store는 `(runId, replayRequestId, stack, service, kind, seq)`가 같으면 덮어쓴다(멱등).

| 필드 | 값 |
|---|---|
| `schemaVersion` | `"v0"` |
| `runId` | `X-Run-Id` 헤더, 없으면 baggage `runId` |
| `replayRequestId` | 진입 서비스: `X-Replay-Request-Id`. Feign 하위 서비스·Kafka consumer: baggage `replayRequestId`(OTel agent 전파, L9) |
| `sessionId` | `X-Session-Id`, 없으면 baggage `sessionId` |
| `stack` | `legacy` / `new` (env `EVIDENCE_STACK`) |
| `service` | `order` / `coupon` / `payment` / `wiremock` / `kafka` |
| `version` | 실행 중인 코드(env `EVIDENCE_VERSION`). 베이스라인은 두 스택 모두 `prince-mart-legacy`. v10.1 §3 키의 version |
| `kind` | `http` / `consume` / `external` / `event` (아래) |
| `seq` | http·consume: 서비스 인스턴스 안 순번(리셋 때 앱 재시작으로 1부터). external: 1. event: offset + 1 |

## kind

| kind | 만드는 곳 | 단위 | 비교 수준(v10.1 §5.2) |
|---|---|---|---|
| `http` | 각 서비스 `EvidenceFilter` | 서비스가 받은 HTTP 요청 1건 | 요청 단위 |
| `consume` | order `EvidenceRecordInterceptor` | Kafka 레코드 처리 1건 | 요청 단위 |
| `external` | `collect.py` (스택별 WireMock journal) | 요청 1건이 만든 외부 호출 목록 | 요청 단위(호출 횟수·파라미터·순서) |
| `event` | `collect.py` (스택별 Kafka 토픽) | 레코드 1건 | 요청 단위(발행 수·payload) |

k6 완료 대기와 flush barrier가 세는 것은 앱 Evidence(`http` + `consume`)다. corpus의 `expect.evidence`가 요청별 기대 건수다.

### http / consume 공통

```json
{
  "schemaVersion": "v0", "runId": "run-1", "replayRequestId": "R000001", "sessionId": "S01",
  "stack": "legacy", "service": "order", "version": "prince-mart-legacy", "kind": "http", "seq": 1,
  "request":  {"...": "http만"}, "response": {"...": "http만"}, "message": {"...": "consume만"},
  "error": {"class": "com.pm.order.exception.ResourceNotFoundException", "message": "Order not found"},
  "dbAccess": {"total": 5,
               "summary": [{"op": "INSERT", "table": "orders", "count": 1}, {"op": "INSERT", "table": "order_items", "count": 2}],
               "statements": ["insert into orders (...) values (...)", "..."]},
  "outbound": [{"order": 1, "method": "GET", "url": "http://CART-SERVICE/cart/my-cart", "status": 200, "error": null, "durationMs": 12}],
  "events": [{"order": 1, "topic": "payment-events", "key": "1", "value": "{...}", "headers": {"baggage": "...", "traceparent": "..."}}],
  "timing": {"arrivedAt": "2026-10-12T00:00:00.123Z", "completedAt": "2026-10-12T00:00:00.135Z",
             "arrivedNano": 0, "completedNano": 0, "durationMs": 12.3},
  "capturedAt": "2026-10-12T00:00:00.135Z",
  "runContext": {"runId": "run-1", "sessionId": "S01", "fixedClock": "2026-09-01T00:00:00Z"}
}
```

| 필드 | 내용 | 비교에 쓰는가 |
|---|---|---|
| `error` | 컨트롤러·listener에서 던져진 예외 class와 메시지. 없으면 null. B6처럼 응답이 모두 404여도 class로 구분된다 | 예(Error Path) |
| `dbAccess.summary` | Hibernate가 준비한 SQL의 (동작, 주 테이블, 횟수). 처음 나온 순서 | 예 |
| `dbAccess.statements` | SQL 원문(순서대로) | 참고용 |
| `outbound` | Feign 호출 순서·method·논리 URL(`http://COUPON-SERVICE/...`)·status. Feign이 아닌 호출(가짜 PG)은 `external`에서 본다 | 예(호출 순서) |
| `events` | 처리 중 발행한 Kafka 레코드 | 예 |
| `timing`, `capturedAt` | 도착·완료 시각(ISO), 같은 JVM 안에서만 비교 가능한 nano 값, `durationMs` | 아니오. 참고 지표 |
| `runContext` | 앱이 아는 run 정보. 나머지(iteration·vus·arm·corpusVersion·조건 해시·이미지)는 run script가 `POST /runs`로 등록 | 아니오 |

### http

```json
"request":  {"method": "POST", "path": "/orders/place", "query": "",
             "headers": {"content-type": "application/json", "x-user-id": "101", "x-replay-request-id": "R000001",
                         "x-run-id": "run-1", "x-session-id": "S01", "baggage": "replayRequestId=R000001,...", "host": "nginx"},
             "bodyHash": "sha256:...", "body": "{...}"},
"response": {"status": 200, "headers": {"content-type": "application/json"}, "bodyHash": "sha256:...", "body": "{...}"}
```
헤더는 지정 목록(`evidence.headers`) 중 실제로 있는 것만, 소문자 키, 여러 값은 `", "`로 잇는다.
짝 맞춤(Phase 2.7)은 method·path·query·request.headers·bodyHash로 한다.

### consume

```json
"message": {"topic": "payment-events", "partition": 0, "offset": 0, "key": "1", "value": "{...}", "headers": {"baggage": "...", "traceparent": "..."}}
```

### external

```json
{"schemaVersion": "v0", "runId": "run-1", "replayRequestId": "R000001", "sessionId": "S01", "stack": "legacy",
 "service": "wiremock", "kind": "external", "seq": 1,
 "calls": [{"order": 1, "method": "GET", "url": "/cart/my-cart", "body": "", "status": 200, "headers": {"baggage": "...", "...": "..."}}]}
```
baggage가 없거나 runId가 다른 호출은 넣지 않고 `collect.py` 출력에 개수만 남긴다.

### event

```json
{"schemaVersion": "v0", "runId": "run-1", "replayRequestId": "R000002", "sessionId": "S01", "stack": "legacy",
 "service": "kafka", "kind": "event", "seq": 1,
 "message": {"topic": "payment-events", "partition": 0, "offset": 0, "key": "1", "value": "{...}", "headers": {"baggage": "...", "traceparent": "..."}}}
```

## 알려진 정규화 대상 (비교 엔진, Step 8)

| 위치 | 이유 |
|---|---|
| `headers.traceparent`, `b3`, `X-B3-*` (external·event·consume·events) | OTel trace id는 스택·실행마다 다르다 |
| `stack` 값 자체, external 헤더의 Host 등 스택 이름이 들어가는 곳 | 비교 키이지 비교 대상이 아니다 |
| 응답 `totalAmount` 표기(`100000` / `95000.00` / `100000.00`) | 같은 값의 BigDecimal scale 차이(L6) |
| auto-increment id | v10.1 §5.3. A/A에서는 같지만 New에서 어긋날 수 있다 |
| JSON 키 순서 | Boot/Jackson 버전에 따라 다르다(L7) |
| `timing`, `capturedAt` | 비교하지 않는다 |

## Evidence Store v0 API (`baseline/evidence-store/`, 호스트 8099)

| | | 팀원 계약과 |
|---|---|---|
| `POST /evidence` | 1건(객체) 또는 여러 건(배열). 앱은 `X-Evidence-Internal: true` | 같음(배열은 확장) |
| `GET /exists?runId=&requestId=&stack=` | 있으면 200, 없으면 404 (본문 `{exists, count}`) | 같음 |
| `GET /count?runId=[&stack=]` | `{count}` | 같음. `requestId`·`kind`·`service` 필터는 확장 |
| `GET /export?runId=[&stack=]` | Evidence 배열(정렬: stack, replayRequestId, service, kind, seq) | 같음 |
| `DELETE /runs/{runId}` | run의 Evidence 삭제 | 같음 |
| `POST /runs`, `GET /runs/{runId}` | run 정보 | 확장 |

## run 결과 배치 (`baseline/runs/<runId>/`, gitignore)

| 파일 | 내용 |
|---|---|
| `legacy.json`, `new.json` | 스택별 export(Evidence 배열) |
| `k6-summary.json`, `k6-results.jsonl` | k6 요약, 요청별 결과(status, 완료 대기 시간, 도착 건수) |
| `run-meta.json` | run 정보: corpus 버전, 이미지 digest, 고정 시각, 조건 해시와 비교 유효 조건 해시, barrier 결과, 수집 건수 |
| `db-legacy.json`, `db-new.json` | 테이블별 전체 행(Step 8 테이블 비교) |
