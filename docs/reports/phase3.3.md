# phase3.3 — Kafka: 이벤트 축

## 0. 결정 필요 사항

없음.

## 1. 단계 목표와 끝난 기준별 PASS/FAIL

목표: 스택별 Kafka로 이벤트 축을 붙인다 — Order 결제 커밋 뒤 `order.paid` 발행, Coupon 소비(USED → SETTLED), DLQ. 발행·소비가 Evidence 타임라인·hop에 들어가고 A/A 게이트를 통과.

**전체: PASS**

| 끝난 기준 | 결과 | 근거 |
|---|---|---|
| corpus v2 A/A 3회(VU=3) diff ∅(events 축 포함), dirty=false | PASS | p33-1..3 response·event·dbAccess·callTree·externalCalls·transactions·events 모두 ∅, 3개 run 집합 동일, run-meta `git.dirty: false`(rev `9f9fddb`). `docs/reports/logs/phase3.3-diff-p33.txt` |
| 스택당 Evidence 수 = 기대 집합(진입 46 + http settle 5 + kafka settle N) | PASS | N = 7 → 58. 세 run 모두 legacy·new 58 = 기대 58, 누락 0. `runs/p33-*/barrier.json`, `phase3.3-run-p33.txt` |
| Undelivered 0 | PASS | 진입·internal 모두 0, hop 집합 일치(자식 홉 짝 12 = http 5 + kafka 7). `phase3.3-verify-p33.txt` |
| 쿠폰 결제 Order Evidence: `events.published` 1건 ack ok, COMMIT_BEGIN < publish.seq < COMMITTED | PASS | p33-1 legacy R000029: COMMIT_BEGIN **4** < publish **6** < COMMITTED **7**, ack ok, childHopPath `0.e1`(3절 전문) |
| 짝 소비 Evidence: hopPath 0.e1, origin kafka, UPDATE coupons, COMMITTED | PASS | R000029/0.e1: consumeOutcome ok, `SELECT → COMMIT_BEGIN → UPDATE coupons → COMMITTED`(3절 전문) |
| dbstate coupons SETTLED 양쪽 동일 | PASS | 세 run 모두 dbstate legacy == new. 결제된 쿠폰 주문의 쿠폰 3개(ck-R000026·R000031·R000043) SETTLED, 미결제 3개 USED — 양쪽 동일 |
| 쿠폰 없는 결제의 소비 Evidence(no-op, dbAccess []) | PASS | R000003/0.e1: consumeOutcome ok, dbAccess `[]`, transactions 없음(3절 전문) |
| 재결제 요청 events.published 0건 | PASS | R000008(S002, 같은 Idempotency-Key): published 0 |
| 소비 실패 → DLQ 1건, consumeOutcome failed, 재시도 0, dlq 발행 기록, barrier는 dlq 홉을 기다리지 않음(exit 0) | PASS | 양쪽 `order.paid.dlq:0:1`, consumeOutcome failed(error StreamReadException @ OrderPaidListener.onOrderPaid), published `order.paid.dlq` ack ok child `0.e1.e1`, 소비 Evidence POST 스택당 1회, barrier 기대 2·도착 2 exit 0(0초). `phase3.3-dlq.txt` |
| Kafka 격리 표 | PASS | 스택 축 2·서비스 축 1 차단, 대조군 2 성공 — 4절, `docs/isolation-proof.md` "Kafka 격리" |
| Kafka 추가 후 working set·노드 사용량 | PASS | 4절. 노드 7.06GiB / 11.67GiB(60.5%), available 약 4.1GiB |

## 2. 변경 파일과 커밋 해시

| 커밋 | 내용 |
|---|---|
| `9f9fddb` phase3.3: Kafka 브로커·발행·소비·DLQ, Evidence 이벤트 축 (A/A 전 코드) | `deploy/k8s/base/{kafka,kafka-networkpolicy}.yaml`, base order·coupon(KAFKA_BOOTSTRAP, 이미지 phase3.3-base), `deploy/k8s/tools/kafka-probe.yaml`, `services/evidence-collector`(EvidenceWriter, EvidenceProducerInterceptor, KafkaTemplateSendAdvice, KafkaEvidenceInterceptor, ReplayContext·EvidenceFilter·AutoConfiguration 수정, spring-kafka provided), `services/order`(OrderPaid, OrderEventPublisher, OrderService 발행, kafka 설정), `services/coupon`(OrderPaidListener, KafkaConfig, CouponService.settle, kafka 설정), `docs/evidence-schema-v1.json`(payload·consumeOutcome), `corpus/`(settle 0.e1·규칙·fixture), `k6/{run.sh,barrier.py}`, `engine/verify_sameness.py` |
| `2729866` phase3.3: diff_v0 — origin=kafka 홉은 event 축 | `engine/diff_v0.py` (A/A 뒤 오프라인 엔진 수정 — 6절) |
| (이 보고서 커밋) | `docs/reports/phase3.3.md`, `docs/reports/logs/phase3.3-*`, `docs/phase3-plan.md`(3.3 구현 시 확정), `docs/isolation-proof.md`(Kafka 격리), `docs/evidence-schema-v1.json`(예시 = 실측), `CLAUDE.md` |

이미지: `order-app:phase3.3-base`, `coupon-app:phase3.3-base` — **3.5 사다리의 Legacy 고정 이미지**(run-meta `images.order/coupon`에 태그·imageRef), `apache/kafka:4.2.1`, `evidence-store:phase3.2`.

## 3. 실행 명령과 주요 출력

```
docker pull --platform linux/arm64 apache/kafka:4.2.1 → docker save → kind load image-archive
docker build -f services/{order,coupon}/Dockerfile -t {order,coupon}-app:phase3.3-base services/ → kind load
kubectl apply -k deploy/k8s/legacy ; kubectl apply -k deploy/k8s/new
git commit 9f9fddb (A/A 전 코드) → k6/run.sh --run-id p33 --iterations 3 --vus 3 → exit 0
  reset 46s / 48s / 48s ("kafka legacy/new: coupon-settlement 그룹이 order.paid partition 할당받음")
  1단계 기대: 스택당 58 (진입 46 + settle 12 {'kafka': 7, 'http': 5}) / legacy 58·new 58 도착, 누락 0
.venv/bin/python engine/diff_v0.py --run runs/p33-{1,2,3}        → exit 0 (2729866 이후)
.venv/bin/python engine/verify_sameness.py --run runs/p33-{1,2,3} → exit 0
```

**쿠폰 결제 Order Evidence 전문 — p33-1 legacy R000029 `POST /api/orders/ok-R000027/pay` (hopPath 0)**
```json
{
  "schemaVersion": "v1",
  "runId": "p33-1",
  "replayRequestId": "R000029",
  "hopPath": "0",
  "sessionId": "S006",
  "stack": "legacy",
  "service": "order",
  "origin": "http",
  "version": "legacy",
  "request": {
    "method": "POST",
    "path": "/api/orders/ok-R000027/pay",
    "query": "",
    "headers": {
      "x-replay-request-id": "R000029",
      "x-run-id": "p33-1",
      "x-session-id": "S006",
      "x-replay-hop-path": "0",
      "idempotency-key": "idem-R000029"
    },
    "bodyHash": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  },
  "response": {
    "status": 200,
    "headers": {
      "content-type": "application/json"
    },
    "bodyHash": "sha256:dc19296cc1508deba1f6031848c0e656a8b74a92fd4ddb446b01400bdd8dbefb",
    "body": "{\"id\":4,\"orderKey\":\"ok-R000027\",\"items\":[{\"sku\":\"D-1\",\"qty\":2,\"price\":5000}],\"amount\":7000,\"couponKey\":\"ck-R000026\",\"discountAmount\":3000,\"status\":\"PAID\",\"transactionId\":\"tx-idem-R000029\",\"createdAt\":\"2026-09-01T00:00:00Z\"}"
  },
  "event": null,
  "dbAccess": {
    "statements": [
      {
        "seq": 1,
        "sql": "select o1_0.id,o1_0.amount,o1_0.coupon_key,o1_0.created_at,o1_0.discount_amount,o1_0.idempotency_key,o1_0.order_key,o1_0.status,o1_0.transaction_id from orders o1_0 where o1_0.order_key=?"
      },
      {
        "seq": 3,
        "sql": "select i1_0.order_id,i1_0.id,i1_0.line_no,i1_0.price,i1_0.qty,i1_0.sku from order_items i1_0 where i1_0.order_id=? order by i1_0.line_no"
      },
      {
        "seq": 5,
        "sql": "update orders set amount=?,coupon_key=?,created_at=?,discount_amount=?,idempotency_key=?,order_key=?,status=?,transaction_id=? where id=?"
      }
    ],
    "truncated": false
  },
  "externalCalls": [
    {
      "seq": 2,
      "method": "POST",
      "host": "wiremock",
      "path": "/gateway/charge",
      "requestBodyHash": "sha256:9c8f75762be881c0a0781b87cd0e382f6f7fa9d51351e5035925371de715a33c",
      "status": 200,
      "responseBodyHash": "sha256:5b45367fee9c5ec928350f77ab384a08338c1d0ff9b8f70782ba9189d60cb8e3",
      "childHopPath": "0.h1"
    }
  ],
  "events": {
    "published": [
      {
        "seq": 6,
        "topic": "order.paid",
        "key": "ok-R000027",
        "payloadHash": "sha256:e4a7a2858707721eaa2feb2900e9a735e59c7c58ebe10eed67743213d147a72d",
        "payload": "{\"orderKey\":\"ok-R000027\",\"amount\":7000,\"couponKey\":\"ck-R000026\"}",
        "ack": "ok",
        "childHopPath": "0.e1"
      }
    ]
  },
  "transactions": [
    {
      "seq": 4,
      "name": "poc.order.OrderService.pay",
      "phase": "COMMIT_BEGIN",
      "outcome": null
    },
    {
      "seq": 7,
      "name": "poc.order.OrderService.pay",
      "phase": "COMPLETED",
      "outcome": "COMMITTED"
    }
  ],
  "callTree": {
    "nodes": [
      {
        "seq": 1,
        "depth": 0,
        "class": "poc.order.OrderController",
        "method": "pay",
        "threw": false
      },
      {
        "seq": 2,
        "depth": 1,
        "class": "poc.order.OrderService",
        "method": "pay",
        "threw": false
      },
      {
        "seq": 3,
        "depth": 2,
        "class": "poc.order.OrderRepository",
        "method": "findByOrderKey",
        "threw": false
      },
      {
        "seq": 4,
        "depth": 2,
        "class": "poc.order.PaymentGatewayClient",
        "method": "charge",
        "threw": false
      },
      {
        "seq": 5,
        "depth": 2,
        "class": "poc.order.OrderEventPublisher",
        "method": "onOrderPaid",
        "threw": false
      }
    ],
    "truncated": false
  },
  "error": null,
  "timing": {
    "arrivedAt": "2026-10-13T11:40:20.848530588Z",
    "completedAt": "2026-10-13T11:40:20.937757713Z",
    "arrivedNano": 16305340974679,
    "completedNano": 16305430203971
  },
  "capturedAt": "2026-10-13T11:40:20.939072505Z"
}
```

**짝 소비 Evidence 전문 — p33-1 legacy R000029 hopPath 0.e1 (origin kafka)**
```json
{
  "schemaVersion": "v1",
  "runId": "p33-1",
  "replayRequestId": "R000029",
  "hopPath": "0.e1",
  "sessionId": "S006",
  "stack": "legacy",
  "service": "coupon",
  "origin": "kafka",
  "version": "legacy",
  "request": null,
  "response": null,
  "event": {
    "topic": "order.paid",
    "key": "ok-R000027",
    "payloadHash": "sha256:e4a7a2858707721eaa2feb2900e9a735e59c7c58ebe10eed67743213d147a72d",
    "payload": "{\"orderKey\":\"ok-R000027\",\"amount\":7000,\"couponKey\":\"ck-R000026\"}"
  },
  "consumeOutcome": "ok",
  "dbAccess": {
    "statements": [
      {
        "seq": 1,
        "sql": "select c1_0.id,c1_0.coupon_key,c1_0.created_at,c1_0.discount_amount,c1_0.status,c1_0.used_at,c1_0.used_by_order_key from coupons c1_0 where c1_0.coupon_key=?"
      },
      {
        "seq": 3,
        "sql": "update coupons set coupon_key=?,created_at=?,discount_amount=?,status=?,used_at=?,used_by_order_key=? where id=?"
      }
    ],
    "truncated": false
  },
  "externalCalls": [],
  "events": {
    "published": []
  },
  "transactions": [
    {
      "seq": 2,
      "name": "poc.coupon.CouponService.settle",
      "phase": "COMMIT_BEGIN",
      "outcome": null
    },
    {
      "seq": 4,
      "name": "poc.coupon.CouponService.settle",
      "phase": "COMPLETED",
      "outcome": "COMMITTED"
    }
  ],
  "callTree": {
    "nodes": [
      {
        "seq": 1,
        "depth": 0,
        "class": "poc.coupon.OrderPaidListener",
        "method": "onOrderPaid",
        "threw": false
      },
      {
        "seq": 2,
        "depth": 1,
        "class": "poc.coupon.CouponService",
        "method": "settle",
        "threw": false
      },
      {
        "seq": 3,
        "depth": 2,
        "class": "poc.coupon.CouponRepository",
        "method": "findByCouponKey",
        "threw": false
      }
    ],
    "truncated": false
  },
  "error": null,
  "timing": {
    "arrivedAt": "2026-10-13T11:40:20.934522838Z",
    "completedAt": "2026-10-13T11:40:20.969888297Z",
    "arrivedNano": 16305426967096,
    "completedNano": 16305462334221
  },
  "capturedAt": "2026-10-13T11:40:20.970061797Z"
}
```

**쿠폰 없는 결제의 소비 Evidence(no-op) 전문 — p33-1 legacy R000003 hopPath 0.e1**
```json
{
  "schemaVersion": "v1",
  "runId": "p33-1",
  "replayRequestId": "R000003",
  "hopPath": "0.e1",
  "sessionId": "S001",
  "stack": "legacy",
  "service": "coupon",
  "origin": "kafka",
  "version": "legacy",
  "request": null,
  "response": null,
  "event": {
    "topic": "order.paid",
    "key": "ok-R000001",
    "payloadHash": "sha256:14541388187d3c78fca3efb2f10bd051b786cba4942a9621ec6d5ba85cfac622",
    "payload": "{\"orderKey\":\"ok-R000001\",\"amount\":10000,\"couponKey\":null}"
  },
  "consumeOutcome": "ok",
  "dbAccess": {
    "statements": [],
    "truncated": false
  },
  "externalCalls": [],
  "events": {
    "published": []
  },
  "transactions": [],
  "callTree": {
    "nodes": [
      {
        "seq": 1,
        "depth": 0,
        "class": "poc.coupon.OrderPaidListener",
        "method": "onOrderPaid",
        "threw": false
      }
    ],
    "truncated": false
  },
  "error": null,
  "timing": {
    "arrivedAt": "2026-10-13T11:40:20.112215088Z",
    "completedAt": "2026-10-13T11:40:20.113015713Z",
    "arrivedNano": 16304604658804,
    "completedNano": 16304605459387
  },
  "capturedAt": "2026-10-13T11:40:20.113059880Z"
}
```

**DLQ (임시 유도, runId t33-dlq)** — `docs/reports/logs/phase3.3-dlq.txt`
```
legacy R990001/0.e1 origin=kafka consumeOutcome=failed error={type: tools.jackson.core.exc.StreamReadException, where: poc.coupon.OrderPaidListener.onOrderPaid}
    events.published seq=1 topic=order.paid.dlq ack=ok childHopPath=0.e1.e1 payload=not-json-payload
new    (동일)
order.paid.dlq 레코드: legacy 1, new 1 / 소비 Evidence POST: 스택당 1회(재시도 0)
barrier(관측 토픽 order.paid): 기대 2 도착 2 → exit 0, 0초 / 대조(dlq도 관측): 10초 대기 후 누락 R990001/0.e1.e1
```

## 4. Legacy/New 비교 결과와 수치

**corpus v2 A/A (VU=3, Legacy 고정 이미지)**

| run | Evidence L / N | 기대 L / N | kafka 홉 L / N | hop 집합 | Undelivered | degraded | diff | dbstate | wiremock | reset | dirty |
|---|---|---|---|---|---|---|---|---|---|---|---|
| p33-1 | 58 / 58 | 58 / 58 | 7 / 7 | 동일 | 0 / 0 | 0 | ∅ (event·events 포함 7축) | 동일 | 동일 | 46s | false |
| p33-2 | 58 / 58 | 58 / 58 | 7 / 7 | 동일 | 0 / 0 | 0 | ∅ (event·events 포함 7축) | 동일 | 동일 | 48s | false |
| p33-3 | 58 / 58 | 58 / 58 | 7 / 7 | 동일 | 0 / 0 | 0 | ∅ (event·events 포함 7축) | 동일 | 동일 | 48s | false |

**Kafka 격리** (`kafka-broker-api-versions.sh`, 20s 상한 — `phase3.3-kafka-isolation.txt`)

| 축 | 시도 | 결과 |
|---|---|---|
| 스택 | legacy(app=order) → `kafka.new:9092` | 차단 |
| 스택 | new(app=order) → `kafka.legacy:9092` | 차단 |
| 서비스 | legacy(app=kprobe) → `kafka.legacy:9092` | 차단 |
| 대조 | legacy·new(app=order) → 같은 스택 `kafka:9092` | 성공(broker id 1, API 버전 응답) |

**Kafka 추가 후 working set** (p33 직후, `phase3.3-workingset.txt`)

| 컨테이너 | legacy | new |
|---|---|---|
| kafka | 273 MiB | 301 MiB |
| order | 435 MiB | 425 MiB |
| coupon | 442 MiB | 426 MiB |
| istio-proxy(kafka) | 37 MiB | 38 MiB |

kind 노드 7.06GiB / 11.67GiB(60.5%), `available` 4,112MiB, 컨테이너 합계 6,386MiB. 12GiB 대비 여유 약 4GiB.

## 5. 지시와 다르게 구현한 것과 이유

- **ack 확정 방식**: 계획 문구는 "get()이 돌아온 호출 스레드에서 기록". 앱의 `get()` 직후 지점을 검증 레이어가 잡을 수 없어서, `KafkaTemplate.send*()` advisor가 반환 future를 발행 기록에 붙이고 **Evidence를 닫을 때(같은 호출 스레드) future 상태로 ack를 정한다**. 앱이 `get(5s)`로 기다린 뒤라 그 시점엔 이미 끝나 있다. 타임아웃·실패면 `failed`. `onAcknowledgement`(I/O 스레드)는 쓰지 않는다.
- **소비 Evidence 확정 시점**: `clearThreadState`만이 아니라 **다음 레코드의 intercept 또는 clearThreadState 중 먼저 오는 쪽**. 한 poll에 레코드가 여럿이면 clearThreadState는 poll 끝에 한 번만 불려 앞 레코드가 섞이기 때문. DLQ 발행은 에러 핸들러가 다음 레코드 전에 끝내므로 그 홉에 들어간다(실측).
- **Kafka 이미지는 태그로 참조**: digest(Docker Hub index digest)로 참조하면 kind load한 arm64 이미지와 digest가 달라 노드가 레지스트리에서 받으려 한다(런타임 다운로드 금지). 실제 imageRef는 run-meta.
- **diff_v0를 A/A 뒤에 고쳤다**(`2729866`): origin=kafka 홉은 `response`가 null이라 diff_v0가 실패했다. 오프라인 엔진이라 run 데이터·dirty 규칙과 무관 — 같은 run을 다시 비교했다. 커밋 4개(코드·엔진·보고서).
- **소비 실패 유도는 코드 변경 없이** console producer로 해석 불가 레코드를 넣었다(실제 요청 R990001의 재생 헤더 + hop 0.e1).

## 6. 발견한 문제·해결·남은 한계

- **diff_v0가 Kafka 홉에서 실패 → 해결**: event 축 추가, 변조 음성 확인(consumeOutcome·ack 변경 → `event`·`events` diff).
- **`Future.state()` 사용 불가(JDK 17) → 해결**: 완료 확인 후 `get()`으로 판정.
- **리셋 시간 증가**: 3.2 약 18s → 3.3 46~48s(Kafka 재시작 + 컨슈머 그룹 할당 대기). 3회 run 약 3분.
- **발행 실패 경로는 이번에 실측하지 않음**: 브로커를 내린 상태의 `ack: failed`·응답 200은 설계·코드로만 보장(`max.block.ms=5000`, `delivery.timeout.ms=5000`). 3.6 결함 시험이나 별도 지시 때 실측 가능.
- **보상·원자성은 범위 밖**: 커밋 뒤 발행이 실패하면 주문은 PAID인데 쿠폰은 USED로 남는다(Outbox 범위 밖, 계획 3절). 이벤트 축(`ack: failed`)과 dbstate로만 드러난다.
- **남은 한계**: 소비 홉은 단일 partition·단일 컨슈머 전제(순서 결정론). DLQ 토픽은 소비자가 없어 그 홉의 Evidence는 없다(설계상 기다리지 않음).
