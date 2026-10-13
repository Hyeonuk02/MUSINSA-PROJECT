# phase3.1 — Evidence v1: 타임라인·callTree·외부 호출·트랜잭션·error·최종 DB 상태

## 0. 결정 필요 사항

**D-3. Order에 Service 계층이 없다 — 3.5 사다리 v1.3과 callTree 기대 형태에 영향 (3.5 착수 전까지).**
현재 Order는 `OrderController`가 `OrderRepository`·`PaymentGatewayClient`를 직접 호출한다(2.1 구현). 그래서 callTree는 계획이 예시로 든 Controller→**Service**→Repository→Client가 아니라 **Controller→Repository / Client**다(1절). 계획 3.5의 v1.3 "`OrderService` Kotlin"은 대상 클래스가 없다.

| 선택지 | 내용 | 영향 |
|---|---|---|
| (A) 3.2에서 base에 `OrderService`를 추출 (추천) | 3.2는 어차피 Order에 쿠폰 처리(주문 INSERT → Coupon use → 커밋)를 넣는다. 그때 트랜잭션 경계와 비즈니스 로직을 `OrderService`로 옮기고 컨트롤러는 HTTP만 담당. Legacy/New 동일 base라 A/A로 검증 | 사다리 v1.1~v1.4 계획 그대로. callTree가 계획 예시 형태가 됨. 트랜잭션 이름이 `OrderService.*`로 바뀜 |
| (B) 그대로 두고 사다리 재정의 | v1.3을 다른 클래스 묶음(예: 도메인 `Order`·`OrderItem`)으로 | 서비스 계층 전환 실험이 사라짐 |

나머지 구현 결정은 `docs/phase3-plan.md` 3.1 "구현 시 확정 (3.1)"에 적었다.

## 1. 단계 목표와 끝난 기준별 PASS/FAIL

목표: Evidence를 v1(타임라인·callTree·외부 호출·트랜잭션·error)로 올리고, 최종 DB 상태·WireMock journal을 run마다 남긴다. base A/A 게이트.

**전체: PASS** (callTree 기대 형태 1건은 코드 구조 차이 — 0절 D-3)

| 끝난 기준 | 결과 | 근거 |
|---|---|---|
| `order-app:phase3-base`로 A/A 3회(VU=3) diff ∅ — callTree·externalCalls·transactions 포함 | **PASS** | p31-1..3 모두 response·dbAccess·callTree·externalCalls·transactions·events diff 0, 3개 run diff 집합 동일. `docs/reports/logs/phase3.1-diff-p31.txt` |
| `POST /pay` Evidence: externalCalls 1건(charge, `childHopPath "0.h1"`) | **PASS** | p31-1 legacy R000003: `externalCalls` 1건, `POST /gateway/charge`, status 200, `childHopPath "0.h1"` (아래 전문, `docs/reports/logs/phase3.1-evidence-pay-legacy.json`) |
| transactions에 COMMIT_BEGIN·COMMITTED 각 1건, **외부 호출 seq < COMMIT_BEGIN seq < COMMITTED seq** | **PASS** | externalCalls seq **2** < COMMIT_BEGIN seq **4** < COMMITTED seq **6** (같은 레코드) |
| callTree에 Controller→Service→Repository→Client | **형태 다름** | 실측 `0:OrderController.pay > 1:OrderRepository.findByOrderKey > 1:PaymentGatewayClient.charge` — Service 계층이 코드에 없음(0절 D-3). 수집 자체는 정상(리포지토리 프록시·클라이언트 모두 잡힘) |
| 리스너가 `JpaTransactionManager`에 실제로 붙어 양쪽에서 transactions 기록 | **PASS** | p31 모든 레코드(28×3)에 transactions 존재, 양쪽 동일. Boot `ExecutionListenersTransactionManagerCustomizer` 경유 |
| 콜백 순서 실측 기록 | **PASS (계획 가정과 다른 순서)** | `docs/reports/logs/phase3.1-tx-callback-order.txt` — 아래 3절 |
| 같은 Idempotency-Key 재결제: externalCalls 0건 | **PASS** | R910003(idem-R910002 재사용) legacy·new 모두 `externalCalls` 0건. `docs/reports/logs/phase3.1-pay-repay.txt` |
| 임시 예외 엔드포인트로 error 경로 1건, ROLLED_BACK | **PASS** | `error {type: java.lang.IllegalStateException, where: poc.order.TempFailController.fail}`, `response.status 0`, transactions `[COMPLETED/ROLLED_BACK]`, callTree `threw=true`, DB 행 0(롤백). 엔드포인트 삭제·이미지 원복. `docs/reports/logs/phase3.1-error-path.txt` |
| dbstate·wiremock journal 양쪽 동일 | **PASS** | p31-1..3 모두 `dbstate legacy == new`(orders 3, order_items 4), `wiremock legacy == new`(각 3건). `runs/p31-*/dbstate-*.json`, `wiremock-*.json` |
| phase2-result 한계 "예외 경로 Evidence 없음" 해소 기록 | **PASS** | `docs/phase2-result.md` 7절 해당 항목 아래 해소 기록 |
| (D-2 (C)) JVM·MySQL 상한 + resources, base A/A로 확인 | **PASS** | 위 A/A가 상한 적용 이미지·매니페스트에서 수행됨. working set 표는 4절 |
| 배포 후 preflight | **PASS** | 노드 Ready, 인증서 3개 VALID(ingressgateway NOT AFTER 2026-10-14T05:32Z — 갱신 확인), Store 200, corpus PASS. run.sh preflight도 3회 통과(`phase3.1-run-p31.txt`) |

## 2. 변경 파일과 커밋 해시

| 커밋 | 내용 |
|---|---|
| `a94841e` phase3.0: 실제 스택 반영 결정 | phase3-plan "3.0 확정" 블록, D16 주석 |
| `fed5990` phase3.1: Evidence v1 수집기·스키마·매니페스트 (배포 전 중간 커밋) | `services/order/pom.xml`(restclient starter), `poc/order/PaymentGatewayClient.java`(Builder 주입), `poc/evidence/`{ReplayContext, EvidenceFilter, EvidenceAutoConfiguration} 수정 + {CallTreeInterceptor, EvidenceTransactionListener, ReplayPropagatingInterceptor} 신규, `docs/evidence-schema-v1.json`, `deploy/k8s/base/{order,mysql}.yaml`, `k6/run.js`(hop 헤더), `k6/run.sh`(dbstate·wiremock export), `k6/dbstate-export.sh`, `engine/{common,verify_sameness,diff_v0}.py` |
| (이 보고서 커밋) phase3.1: base A/A·실측 결과, 스키마 예시, 구현 시 확정 | `docs/evidence-schema-v1.json`(examples = 실측 Evidence), `docs/phase3-plan.md`(3.1 구현 시 확정), `docs/phase2-result.md`(한계 해소), `CLAUDE.md`(3.1 완료), `docs/reports/phase3.1.md`, `docs/reports/logs/phase3.1-*` |

이미지: `order-app:phase3-base`(legacy·new 동일). 임시 `order-app:phase3-errtest`는 시험 후 노드에서 삭제.

## 3. 실행 명령과 주요 출력

```
# 배포
docker build -t order-app:phase3-base ./services/order → docker save --platform linux/arm64 → kind load image-archive
kubectl apply -k deploy/k8s/legacy ; kubectl apply -k deploy/k8s/new      (Order·MySQL 재시작 = S0)

# base A/A
k6/run.sh --run-id p31 --iterations 3 --vus 3          → exit 0   (전문 docs/reports/logs/phase3.1-run-p31.txt)
.venv/bin/python engine/diff_v0.py --run runs/p31-1 --run runs/p31-2 --run runs/p31-3   → exit 0 (phase3.1-diff-p31.txt)
.venv/bin/python engine/verify_sameness.py --run runs/p31-1 … p31-3                     → exit 0 (phase3.1-verify-p31.txt)
```

**실측 콜백 순서** (legacy, POST /pay R910022, 임시 `EVIDENCE_TX_TRACE=true` + `SPRING_APPLICATION_JSON`으로 JpaTransactionManager·org.hibernate.SQL DEBUG — 실측 후 제거, live == manifest 확인)
```
06:18:36.411  synchronization.beforeCommit
06:18:36.412  JpaTransactionManager: Initiating transaction commit
06:18:36.412  listener.beforeCommit                      ← COMMIT_BEGIN 기록
06:18:36.412  JpaTransactionManager: Committing JPA transaction on EntityManager   ← doCommit
06:18:36.414  org.hibernate.SQL: update orders set …    ← flush는 doCommit 안 (COMMIT_BEGIN 뒤)
06:18:36.418  synchronization.afterCommit
06:18:36.418  synchronization.afterCompletion(0)
06:18:36.418  listener.afterCommit                       ← COMMITTED 기록
```
계획이 가정한 "beforeCommit → doCommit → afterCommit → 동기화 afterCommit"과 달리 **동기화 afterCommit이 리스너 afterCommit보다 먼저**다. 3.3의 `@TransactionalEventListener(AFTER_COMMIT)` 발행은 COMMIT_BEGIN과 COMMITTED **사이**의 seq를 받는다. F3 판정은 COMMIT_BEGIN 기준이라 영향 없다(D16 설계 의도대로).

**v1 축 음성 확인** (p31-1 사본 변조): new R000003의 externalCalls 삭제 → `externalCalls diff R000003` / callTree depth 3으로 변조 → 입력 계약 FAIL "depth 불변식 위반" / COMMITTED → ROLLED_BACK → `transactions diff R000003`.

**Evidence v1 전문 — p31-1 legacy POST /api/orders/ok-R000001/pay (R000003)** (스키마 예시로도 등록, 스키마 통과)
```json
{
  "schemaVersion": "v1",
  "runId": "p31-1",
  "replayRequestId": "R000003",
  "hopPath": "0",
  "sessionId": "S001",
  "stack": "legacy",
  "service": "order",
  "origin": "http",
  "version": "legacy",
  "request": {
    "method": "POST",
    "path": "/api/orders/ok-R000001/pay",
    "query": "",
    "headers": {
      "x-replay-request-id": "R000003",
      "x-run-id": "p31-1",
      "x-session-id": "S001",
      "x-replay-hop-path": "0",
      "idempotency-key": "idem-R000003"
    },
    "bodyHash": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  },
  "response": {
    "status": 200,
    "headers": {
      "content-type": "application/json"
    },
    "bodyHash": "sha256:d6cb8342ef57683a035030f11d8571e5e0fb550f264b36968eb0018319dc30d5",
    "body": "{\"id\":1,\"orderKey\":\"ok-R000001\",\"items\":[{\"sku\":\"A-1\",\"qty\":1,\"price\":10000}],\"amount\":10000,\"status\":\"PAID\",\"transactionId\":\"tx-idem-R000003\",\"createdAt\":\"2026-09-01T00:00:00Z\"}"
  },
  "event": null,
  "dbAccess": {
    "statements": [
      {
        "seq": 1,
        "sql": "select o1_0.id,o1_0.amount,o1_0.created_at,o1_0.idempotency_key,o1_0.order_key,o1_0.status,o1_0.transaction_id from orders o1_0 where o1_0.order_key=?"
      },
      {
        "seq": 3,
        "sql": "select i1_0.order_id,i1_0.id,i1_0.line_no,i1_0.price,i1_0.qty,i1_0.sku from order_items i1_0 where i1_0.order_id=? order by i1_0.line_no"
      },
      {
        "seq": 5,
        "sql": "update orders set amount=?,created_at=?,idempotency_key=?,order_key=?,status=?,transaction_id=? where id=?"
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
      "requestBodyHash": "sha256:1287ab8951f7a96da951f365c4212b92d57b847e824fae4e2fbf2a68ca396112",
      "status": 200,
      "responseBodyHash": "sha256:7be4e9d634535f8f35e8cd926b57c69127adf84ced0a6e615a593fe269d39f7f",
      "childHopPath": "0.h1"
    }
  ],
  "events": {
    "published": []
  },
  "transactions": [
    {
      "seq": 4,
      "name": "poc.order.OrderController.pay",
      "phase": "COMMIT_BEGIN",
      "outcome": null
    },
    {
      "seq": 6,
      "name": "poc.order.OrderController.pay",
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
        "class": "poc.order.OrderRepository",
        "method": "findByOrderKey",
        "threw": false
      },
      {
        "seq": 3,
        "depth": 1,
        "class": "poc.order.PaymentGatewayClient",
        "method": "charge",
        "threw": false
      }
    ],
    "truncated": false
  },
  "error": null,
  "timing": {
    "arrivedAt": "2026-10-13T06:20:52.629011459Z",
    "completedAt": "2026-10-13T06:20:52.702400251Z",
    "arrivedNano": 2433079732736,
    "completedNano": 2433153121652
  },
  "capturedAt": "2026-10-13T06:20:52.702608209Z"
}
```

## 4. Legacy/New 비교 결과와 수치

**base A/A (VU=3, order-app:phase3-base)**

| run | count L/N | Undelivered L/N | degraded | response | dbAccess | callTree | externalCalls | transactions | events | dbstate | wiremock | R000001 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| p31-1 | 14/14 | 0/0 | 0 | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | 동일 | 동일 | 201 |
| p31-2 | 14/14 | 0/0 | 0 | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | 동일 | 동일 | 201 |
| p31-3 | 14/14 | 0/0 | 0 | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | 동일 | 동일 | 201 |

완료 시각 차이(new − legacy, ms, 참고): p31-1 −9.8 / −0.1 / 21.4, p31-2 −3.0 / −0.4 / 5.8, p31-3 −10.2 / −2.2 / 4.3 (min/median/max).

**JVM·MySQL 상한 적용 후 working set** (p31 직후, `docs/reports/logs/phase3.1-workingset.txt`)

| 컨테이너 | legacy | new | 3.0 실측(상한 전) |
|---|---|---|---|
| order | 432 MiB | 420 MiB | 590 / 588 |
| mysql | 443 MiB | 443 MiB | 473 / 473 |
| wiremock | 182 MiB | 194 MiB | 236 / 233 |
| istio-proxy (order·mysql·wiremock) | 41·36·49 | 39·38·42 | (ns 합산 164 / 161) |
| evidence-store (verify) | 59 MiB | — | 39 |

kind 노드: 4.72GiB / **11.67GiB** 사용(40%), `available` 7,220MiB — Docker VM은 이미 증설된 상태(3.0 때 7.65GiB). 컨테이너 합계 3,979MiB.

## 5. 지시와 다르게 구현한 것과 이유

- **Order 비즈니스 코드 2곳 변경**: `pom.xml`에 `spring-boot-starter-restclient`, `PaymentGatewayClient`가 정적 `RestClient.builder()` 대신 Boot `RestClient.Builder` 주입. 정적 builder에는 `poc.evidence`가 인터셉터를 붙일 지점이 없고, Boot 4는 Builder 자동 구성이 별도 모듈이다. 요청 팩토리(`SimpleClientHttpRequestFactory`)는 그대로라 OTel 계측 경로도 같다. legacy·new 동일 base.
- **포인트컷을 계획의 고정 식(`poc.order..*`) 대신 env `EVIDENCE_APP_PACKAGES`로**: Coupon(`poc.coupon`)에 `poc.evidence`를 수정 없이 붙이기 위해. 서블릿 필터·`@Configuration` 제외를 추가(구현 시 확정 참조).
- **Evidence에 재생 헤더 4개 필수**(hopPath 포함). 하나라도 없으면 Evidence 없음(로그 한 줄) — Phase 2의 3개 규칙을 키 확장에 맞춤.
- **WireMock journal은 정렬한 다중집합으로 비교**: journal이 최신순이고 VU=3에서 요청 간 순서가 정해지지 않아서.
- **resources는 order·mysql에만**: 지시 범위(Order·MySQL). WireMock·Store는 손대지 않았다.

## 6. 발견한 문제·해결·남은 한계

- **COMMIT_BEGIN이 flush SQL보다 먼저 찍힌다**: 결제의 UPDATE(seq 5)가 COMMIT_BEGIN(seq 4) 뒤. Hibernate가 doCommit 안에서 flush하기 때문이며 실제 동작 그대로다. Phase 3 엔진이 "커밋 전 SQL"을 판단할 때 주의(쓰기 집합 비교에는 영향 없음).
- **콜백 순서가 계획 가정과 다름**(3절). F3 판정은 영향 없음.
- **배포 직후 order 로그의 `JDBCConnectionException`**: MySQL과 Order가 같은 apply로 함께 재시작돼 Hibernate가 기동 중 DB 메타데이터 조회에 실패한 경고. 앱은 정상 기동했고 readiness·A/A 모두 정상. run.sh의 S0 리셋은 MySQL만 재시작하므로 해당 없음.
- **환경변수로 로그 레벨 지정 시 대소문자 손실**: `LOGGING_LEVEL_…_JPATRANSACTIONMANAGER`는 소문자 로거명이 돼 매칭되지 않았다 → `SPRING_APPLICATION_JSON`으로 해결(실측용, 원복).
- **p31 run-meta의 `git.dirty: true`**: run 시점에 이 보고서용 로그 파일(`docs/reports/logs/phase3.1-tx-callback-order.txt`)이 untracked였기 때문. 코드·매니페스트는 커밋 `fed5990`와 같다.
- **남은 한계**: Store는 아직 v0 키(hopPath 미포함) — 자식 홉 Evidence가 생기는 3.2에서 Store v1. callTree는 빈 경계만(self-invocation·private 미수집, call-graph.md 3절). error 경로의 실제 응답 상태(500)는 Evidence에 없다(0으로 기록).
