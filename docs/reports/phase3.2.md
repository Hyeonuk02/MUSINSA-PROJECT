# phase3.2 — Coupon 서비스 + Store v1 키 + corpus v2

## 0. 결정 필요 사항

없음.

## 1. 단계 목표와 끝난 기준별 PASS/FAIL

목표: Coupon 실서비스(전용 DB)를 양쪽 스택에 올리고, 서비스 간 호출로 생기는 내부 Evidence(hopPath)를 Store·k6·barrier·verify가 다루게 한다. base에 OrderService 추출(D-3 (A)). corpus v2로 A/A 게이트.

**전체: PASS**

| 끝난 기준 | 결과 | 근거 |
|---|---|---|
| Coupon 양쪽 배포 | PASS | legacy·new 모두 `coupon`·`coupon-mysql` 2/2 Running, `EVIDENCE_ENABLED service=coupon`(poc.evidence 수정 0줄로 부착) |
| 격리 실측(교차 차단·대조군 성공) | PASS | 스택 축 3·서비스 축 2 차단, 대조군 3 성공 — 4절 표, `docs/isolation-proof.md` "Coupon 격리" |
| corpus v2 A/A 3회(VU=3) diff ∅ | PASS | p32-1..3 모든 축(response·dbAccess·callTree·externalCalls·transactions·events) ∅, 3개 run diff 집합 동일. `docs/reports/logs/phase3.2-diff-p32.txt` |
| 스택당 Evidence 수 = 기대 집합 크기 | PASS | 세 run 모두 legacy·new 51 = 기대 51(진입 46 + settle 5), 누락 0. `runs/p32-*/barrier.json`, `phase3.2-run-p32.txt` |
| hop 집합 동일, Undelivered 0 | PASS | 세 run 모두 자식 홉 짝 5, Undelivered(진입·internal) 0, "hop 집합 불일치" 0. `phase3.2-verify-p32.txt` |
| 쿠폰 주문: Order `externalCalls`에 use(`0.h1`) + 결제 시 charge, Coupon Evidence `hopPath 0.h1`·UPDATE·COMMITTED | PASS | p32-1 R000027: Order 타임라인 `INSERT orders → INSERT order_items → CALL coupon/use(0.h1, 200) → COMMIT_BEGIN → UPDATE orders → COMMITTED`, 짝 Coupon `0.h1`: `SELECT → COMMIT_BEGIN → UPDATE coupons → COMMITTED`. 결제 R000029의 charge(wiremock, 할인 후 7000원) — 3절 전문 |
| 실패 경로: USED 쿠폰 → Order 400, ROLLED_BACK, dbstate에 주문 없음(양쪽 동일) | PASS | S008 R000037: 400 `{"code":"COUPON_ALREADY_USED"}`, transactions `[COMPLETED/ROLLED_BACK]`, Coupon 0.h1은 409. R000038 조회 404, dbstate orders에 `ok-R000037` 없음(양쪽 orders 8건 동일, 현재 DB 행 수 0). `phase3.2-coupon-flows.txt` |
| dbstate(orders·coupons)·wiremock 동일 | PASS | 세 run 모두 legacy == new (coupons 6, order_items 10, orders 8 / wiremock 7건) |
| callTree Controller → Service → Repository/Client | PASS | R000027 `0:OrderController.create > 1:OrderService.create > 2:OrderRepository.existsByOrderKey > 2:OrderRepository.saveAndFlush > 2:CouponClient.use`, Coupon `0:CouponController.use > 1:CouponService.use > 2:CouponRepository.findByCouponKey` |

## 2. 변경 파일과 커밋 해시

| 커밋 | 내용 |
|---|---|
| `b856eff` phase3.2: OrderService 추출 (base) | `OrderService`·`OrderView` 신규, `OrderController`(매핑만), `deploy/k8s/base/order.yaml`(phase3.2-base), decision-log D16 실측 메모. corpus v1 A/A 1회 diff ∅(`runs/p32a-1`) |
| `d51bf22` phase3.2: Coupon 서비스·매니페스트·격리 | `services/evidence-collector/`(poc.evidence 이동 + spill 파일명 hopPath), `services/coupon/`, Order `CouponClient`·쿠폰 흐름·스키마, `evidence-store/app.py`(Store v1), `deploy/k8s/base/{coupon,coupon-mysql,coupon-mysql-networkpolicy,coupon-networkpolicy}.yaml`·`coupon-mysql-initdb`, overlay `coupon-otel.yaml`, VS 표면, `deploy/k8s/tools/coupon-probe.yaml`, isolation-proof, k6 exists `hopPath=0` |
| (이 보고서 커밋) phase3.2: Store v1·k6 v2·corpus v2·barrier v2·보고서 | `corpus/{corpus-v2.json, schema-v2.json, validate.py, tests/invalid-v2/}`, `k6/{run.js, run.sh, barrier.py, dbstate-export.sh}`, `engine/verify_sameness.py`, `docs/phase3-plan.md`(3.2 구현 시 확정), `CLAUDE.md`, 보고서·로그 |

이미지: `order-app:phase3.2-base`, `coupon-app:phase3.2-base`, `evidence-store:phase3.2` (run-meta `images.order/coupon/evidenceStore`에 태그·imageRef 기록 확인).

## 3. 실행 명령과 주요 출력

```
docker build -f services/{order,coupon}/Dockerfile -t {order,coupon}-app:phase3.2-base services/   → kind load image-archive
kubectl apply -f deploy/k8s/verify/evidence-store.yaml ; kubectl apply -f deploy/k8s/istio/virtualservice-shadow.yaml
kubectl apply -k deploy/k8s/legacy ; kubectl apply -k deploy/k8s/new
.venv/bin/python corpus/validate.py            → PASS (sessions=10 requests=46 expectMissing=2 settle=5, flows 3종 모두 learn·eval)
.venv/bin/python corpus/validate.py --self-test → 18/18 ok (v1·v2 정상 corpus + 음성 fixture 16)
k6/run.sh --run-id p32 --iterations 3 --vus 3  → exit 0 (전문 docs/reports/logs/phase3.2-run-p32.txt)
.venv/bin/python engine/diff_v0.py --run runs/p32-{1,2,3}        → exit 0 (phase3.2-diff-p32.txt)
.venv/bin/python engine/verify_sameness.py --run runs/p32-{1,2,3} → exit 0 (phase3.2-verify-p32.txt)
```

verify v2 분류 음성 확인(p32-1 사본 변조): new의 `R000027/0.h1` 삭제 → `Undelivered internal (new) 1 R000027/0.h1` FAIL / new 주문이 Coupon use를 두 번(부모 `externalCalls`에 `0.h2` + `0.h2` Evidence) → "행동 차이(엔진으로) R000027/0.h2(new만)" — verify는 PASS(판정은 엔진).

**쿠폰 주문 Order Evidence 전문 — p32-1 legacy R000027 `POST /api/orders` (hopPath 0)**
```json
{
  "schemaVersion": "v1",
  "runId": "p32-1",
  "replayRequestId": "R000027",
  "hopPath": "0",
  "sessionId": "S006",
  "stack": "legacy",
  "service": "order",
  "origin": "http",
  "version": "legacy",
  "request": {
    "method": "POST",
    "path": "/api/orders",
    "query": "",
    "headers": {
      "x-replay-request-id": "R000027",
      "x-run-id": "p32-1",
      "x-session-id": "S006",
      "x-replay-hop-path": "0",
      "content-type": "application/json"
    },
    "bodyHash": "sha256:8f278cec72d03d318a82e13af9fc61c2df86da1221f16dacd92e520d92f96056"
  },
  "response": {
    "status": 201,
    "headers": {
      "content-type": "application/json"
    },
    "bodyHash": "sha256:374106f86d0a797be9d55874e858a9a124e552a0dd7b0b4aa086660bf5e43306",
    "body": "{\"id\":4,\"orderKey\":\"ok-R000027\",\"items\":[{\"sku\":\"D-1\",\"qty\":2,\"price\":5000}],\"amount\":7000,\"couponKey\":\"ck-R000026\",\"discountAmount\":3000,\"status\":\"CREATED\",\"transactionId\":null,\"createdAt\":\"2026-09-01T00:00:00Z\"}"
  },
  "event": null,
  "dbAccess": {
    "statements": [
      {
        "seq": 1,
        "sql": "select o1_0.id from orders o1_0 where o1_0.order_key=? limit ?"
      },
      {
        "seq": 2,
        "sql": "insert into orders (amount,coupon_key,created_at,discount_amount,idempotency_key,order_key,status,transaction_id) values (?,?,?,?,?,?,?,?)"
      },
      {
        "seq": 3,
        "sql": "insert into order_items (line_no,order_id,price,qty,sku) values (?,?,?,?,?)"
      },
      {
        "seq": 6,
        "sql": "update orders set amount=?,coupon_key=?,created_at=?,discount_amount=?,idempotency_key=?,order_key=?,status=?,transaction_id=? where id=?"
      }
    ],
    "truncated": false
  },
  "externalCalls": [
    {
      "seq": 4,
      "method": "POST",
      "host": "coupon",
      "path": "/api/coupons/ck-R000026/use",
      "requestBodyHash": "sha256:b452301e42cc93adb3bef02066ab1f02b57843f5555594fe2d545b93efd3837c",
      "status": 200,
      "responseBodyHash": "sha256:abc14f371d104736ead0dfce5b51d48fdf16496eba216e27f0ed07f2262fc93a",
      "childHopPath": "0.h1"
    }
  ],
  "events": {
    "published": []
  },
  "transactions": [
    {
      "seq": 5,
      "name": "poc.order.OrderService.create",
      "phase": "COMMIT_BEGIN",
      "outcome": null
    },
    {
      "seq": 7,
      "name": "poc.order.OrderService.create",
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
        "method": "create",
        "threw": false
      },
      {
        "seq": 2,
        "depth": 1,
        "class": "poc.order.OrderService",
        "method": "create",
        "threw": false
      },
      {
        "seq": 3,
        "depth": 2,
        "class": "poc.order.OrderRepository",
        "method": "existsByOrderKey",
        "threw": false
      },
      {
        "seq": 4,
        "depth": 2,
        "class": "poc.order.OrderRepository",
        "method": "saveAndFlush",
        "threw": false
      },
      {
        "seq": 5,
        "depth": 2,
        "class": "poc.order.CouponClient",
        "method": "use",
        "threw": false
      }
    ],
    "truncated": false
  },
  "error": null,
  "timing": {
    "arrivedAt": "2026-10-13T10:58:39.848117833Z",
    "completedAt": "2026-10-13T10:58:39.911885167Z",
    "arrivedNano": 13804363201333,
    "completedNano": 13804426968500
  },
  "capturedAt": "2026-10-13T10:58:39.912099875Z"
}
```

**짝 Coupon Evidence 전문 — p32-1 legacy R000027 `POST /api/coupons/ck-R000026/use` (hopPath 0.h1)**
```json
{
  "schemaVersion": "v1",
  "runId": "p32-1",
  "replayRequestId": "R000027",
  "hopPath": "0.h1",
  "sessionId": "S006",
  "stack": "legacy",
  "service": "coupon",
  "origin": "http",
  "version": "legacy",
  "request": {
    "method": "POST",
    "path": "/api/coupons/ck-R000026/use",
    "query": "",
    "headers": {
      "x-replay-request-id": "R000027",
      "x-run-id": "p32-1",
      "x-session-id": "S006",
      "x-replay-hop-path": "0.h1",
      "content-type": "application/json"
    },
    "bodyHash": "sha256:b452301e42cc93adb3bef02066ab1f02b57843f5555594fe2d545b93efd3837c"
  },
  "response": {
    "status": 200,
    "headers": {
      "content-type": "application/json"
    },
    "bodyHash": "sha256:abc14f371d104736ead0dfce5b51d48fdf16496eba216e27f0ed07f2262fc93a",
    "body": "{\"couponKey\":\"ck-R000026\",\"discountAmount\":3000,\"status\":\"USED\",\"usedByOrderKey\":\"ok-R000027\"}"
  },
  "event": null,
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
      "name": "poc.coupon.CouponService.use",
      "phase": "COMMIT_BEGIN",
      "outcome": null
    },
    {
      "seq": 4,
      "name": "poc.coupon.CouponService.use",
      "phase": "COMPLETED",
      "outcome": "COMMITTED"
    }
  ],
  "callTree": {
    "nodes": [
      {
        "seq": 1,
        "depth": 0,
        "class": "poc.coupon.CouponController",
        "method": "use",
        "threw": false
      },
      {
        "seq": 2,
        "depth": 1,
        "class": "poc.coupon.CouponService",
        "method": "use",
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
    "arrivedAt": "2026-10-13T10:58:39.871018958Z",
    "completedAt": "2026-10-13T10:58:39.900261Z",
    "arrivedNano": 13804386102417,
    "completedNano": 13804415344958
  },
  "capturedAt": "2026-10-13T10:58:39.901109958Z"
}
```

**실패 경로 (S008, p32-1 legacy)** — `docs/reports/logs/phase3.2-coupon-flows.txt`
```
R000036/0   주문 A + ck-R000035 → 201, amount 6500(9000−2500), use 0.h1 → 200 USED(ok-R000036)
R000037/0   주문 B + 같은 쿠폰  → 400 {"code":"COUPON_ALREADY_USED"}
            타임라인 SELECT | INSERT orders | INSERT order_items | CALL coupon/use(0.h1) → 409 | TX COMPLETED ROLLED_BACK
            callTree OrderController.create(threw) > OrderService.create(threw) > … > CouponClient.use(threw) > [depth 0] OrderController.onCouponFailure
R000037/0.h1 Coupon use → 409 {"code":"COUPON_ALREADY_USED"} (읽기만, COMMITTED)
R000038/0   GET ok-R000037 → 404 (롤백 확인)     dbstate orders: ok-R000037 없음 (legacy·new 동일)
```

## 4. Legacy/New 비교 결과와 수치

**corpus v2 A/A (VU=3)**

| run | Evidence L / N | 기대 집합 L / N | hop 집합 | Undelivered(진입·internal) | degraded | diff 6축 | dbstate | wiremock | R000001 |
|---|---|---|---|---|---|---|---|---|---|
| p32-1 | 51 / 51 | 51 / 51 | 동일 (5개 자식 홉) | 0 / 0 | 0 | ∅ | 동일 (coupons 6, order_items 10, orders 8) | 동일 (7 / 7) | 201 |
| p32-2 | 51 / 51 | 51 / 51 | 동일 (5개 자식 홉) | 0 / 0 | 0 | ∅ | 동일 (coupons 6, order_items 10, orders 8) | 동일 (7 / 7) | 201 |
| p32-3 | 51 / 51 | 51 / 51 | 동일 (5개 자식 홉) | 0 / 0 | 0 | ∅ | 동일 (coupons 6, order_items 10, orders 8) | 동일 (7 / 7) | 201 |

**격리 실측** (`deploy/k8s/tools/coupon-probe.yaml`, 레이블 흉내 probe — 측정 후 삭제)

| 축 | 시도 | 결과 |
|---|---|---|
| 스택 | legacy(app=order) → `coupon.new:8080` | 차단 — HTTP 000(5s) |
| 스택 | legacy(app=order) → `coupon-mysql.new:3306` | 차단 — ERROR 2013 (110) |
| 스택 | new(app=order) → `coupon-mysql.legacy:3306` | 차단 — ERROR 2013 (new egress) |
| 서비스 | new(app=order) → `coupon-mysql.new:3306` | 차단 — ERROR 2013 (110) |
| 서비스 | legacy(app=order) → `coupon-mysql.legacy:3306` | 차단 — ERROR 2013 (110) |
| 대조 | new·legacy(app=order) → 같은 스택 `coupon:8080` | HTTP 404(정상 조회) |
| 대조 | new(app=coupon) → `coupon-mysql.new:3306` | 로그인 성공 |

**Coupon 추가 후 working set** (p32 직후, `docs/reports/logs/phase3.2-workingset.txt`)

| 컨테이너 | legacy | new |
|---|---|---|
| order | 422 MiB | 419 MiB |
| coupon | 408 MiB | 419 MiB |
| mysql | 443 MiB | 442 MiB |
| coupon-mysql | 442 MiB | 442 MiB |
| wiremock | 237 MiB | 245 MiB |
| istio-proxy(앱 pod당) | 37~53 MiB | 38~42 MiB |
| evidence-store | 40 MiB | — |

kind 노드 6.94GiB / 11.67GiB(59.5%), `available` 4,942MiB, 컨테이너 합계 6,136MiB (3.1 대비 +2.2GiB). 3.3 Kafka 2개(각 0.6~1GiB 추정)는 여유 안.

## 5. 지시와 다르게 구현한 것과 이유

- **Store v1을 커밋 3이 아니라 커밋 2에 넣었다**: Store가 v0 키(runId, rid, stack)면 Coupon `0.h1` Evidence가 같은 요청의 Order `0` Evidence를 덮어써서 커밋 2의 쿠폰 주문 검증이 성립하지 않는다.
- **`poc.evidence`를 공용 Maven 모듈로 분리**(`services/evidence-collector`): Coupon이 같은 수집기를 "그대로" 쓰기 위해. 코드 내용은 바꾸지 않았고(git rename), Dockerfile 빌드 컨텍스트가 `services/`로 바뀌었다.
- **`poc.evidence` 변경 1건 — spill 파일명에 hopPath**: Coupon 부착에 필요한 수정이 아니라 Store v1 키 변경(3.2 범위)에 따른 것. 이게 없으면 같은 스택 hostPath에서 Order·Coupon, 또는 F9의 `0.h1`·`0.h2` spill이 서로 덮어쓴다.
- **egress NetworkPolicy는 추가하지 않았다**: new의 default-deny egress가 이미 같은 ns·verify·DNS를 허용해 order→coupon, coupon→coupon-mysql, coupon→Store가 동작한다(실측). 대신 ingress 두 개(Coupon API, Coupon DB)를 추가했다 — legacy에는 egress 제한이 없어 Coupon ingress가 없으면 legacy → new Coupon이 열린다.
- **corpus 세션에 `flow` 필드 추가**: "흐름 유형마다 learn·eval 각 ≥1"을 validate.py가 검사하려면 유형이 명시돼야 해서. F7 지연 세션(S009)은 order 유형, 예비(S010)는 order-coupon 유형.
- **Coupon 전용 세션의 use `orderKey`는 외부 키 `ok-ext-<요청 id>`**: Order를 거치지 않는 세션이라 주문이 없다. validate.py가 이 형식만 예외로 허용.
- **run-meta `git.dirty: true`**(p32-1..3): 커밋 수 제한(3개) 때문에 이번 단계의 k6·barrier·corpus 변경이 보고서와 같은 커밋에 들어가 run 시점엔 미커밋이었다. 코드는 이 보고서 커밋과 같다.

## 6. 발견한 문제·해결·남은 한계

- **dbstate export 실패 → 해결**: coupon-mysql 매니페스트를 mysql.yaml에서 파생하며 컨테이너 이름도 `coupon-mysql`이 됐는데 스크립트가 `-c mysql` 고정이었다. 레이블 값으로 컨테이너를 고르게 고쳤다.
- **corpus 생성기의 요청 id 순서 → 해결**: 첫 생성에서 세션 안 요청 id가 비순차였다(규칙 위반은 아님). 순차 생성으로 다시 만들고 run을 새로 돌렸다(첫 시도 run은 삭제).
- **쿠폰 실패 시 callTree 루트가 둘**: `@ExceptionHandler`가 컨트롤러 빈 메서드라 depth 0 노드가 하나 더 찍힌다. 입력 계약(첫 노드 depth 0, depth[i] ≤ depth[i−1]+1)은 만족하며 양쪽 동일. 3.4 정규화에서 루트가 여럿일 수 있음을 전제로 한다.
- **보상 누락은 범위 밖**: 쿠폰 use 성공 뒤 Order가 다른 이유로 롤백되면 Coupon은 USED로 남는다(분산 일관성, phase3-plan 3절). 양쪽이 같으면 SAME으로 본다.
- **남은 한계**: 내부 Evidence 완료는 corpus settle 선언에 의존(D19) — 3.3에서 이벤트 홉(`0.e1`) 추가 예정. barrier 폐포는 관측 호스트 목록(`OBSERVED_HOSTS`)에 의존한다. Coupon 전용 세션의 use는 실제 주문 없이 쿠폰만 USED로 만든다(외부 주문 키).
