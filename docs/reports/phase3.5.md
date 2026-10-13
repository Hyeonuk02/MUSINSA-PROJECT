# Phase 3.5 보고서 — New v1 사다리 (Order 점진 Kotlin 전환)

- 작업일: 2026-10-14
- Legacy 고정: `order-app:phase3.3-base`, Coupon 양쪽 `coupon-app:phase3.3-base`. 엔진 `engine-v1.1`
- 결과: **PASS** — base 게이트 재확인 → v1.1 → v1.2 → v1.3 → v1.4 모두 3 run × C·B0·B1 **전 pair SAME**(58/58), Undelivered 0, degraded 0, CV 0, Uncertain 0. Order는 Java 0파일·Kotlin 전면. `poc.evidence` 수정 0줄
- 요약: 이 corpus(46 요청·58 pair)가 닿는 행동 범위에서 Kotlin 점진 전환은 **행동 Evidence를 한 바이트도 바꾸지 않았다**(B0 원문 비교까지 0). 흔적은 Metaspace(+6.4~7.4 MB, +1,800~2,300 클래스)에만 남았다. learn Uncertain이 없어 v1.1·v1.2에서 만든 규칙 0 — 3.7의 Rule 재사용 효과는 3.6(F 변형)에서 처음 측정된다
- 누적 결과 표: `docs/phase3-result.md`

## 0. 결정 필요 사항

없음. (D-5 Metaspace는 (A) 256m·limits 1Gi로 결정되어 반영)

## 1. 끝난 기준별 결과

### 1.0 엔진 소수정 · 설정 변경 · 게이트

| 기준 | 결과 | 근거 |
|---|---|---|
| id 값 마스킹, engine-v1.1, p33-1..3 전 pair SAME | PASS | `94b577b`. p33-1·2·3 × B0·B1·C `{SAME: 58}`, pytest 27 passed |
| Metaspace 256m·limits 1Gi (base 공통, Order·Coupon) | PASS | `d1b283e`. 배포 후 4개 Deployment limits 1Gi, `JAVA_TOOL_OPTIONS ... -XX:MaxMetaspaceSize=256m` |
| base A/A 재확인 `p35-base` (VU=3 ×3) | PASS | 3 run × C·B0·B1 모두 `{SAME: 58}`, Undelivered 0, degraded 0, dbstate OK, verify 3/3 PASS, run-meta `dirty: false`(rev `d1b283e`), order legacy·new = phase3.3-base. `logs/phase3.5-base-{run,verify,verdict}.txt` |
| A/A 뒤 Metaspace 측정 | 기록 | 아래 표. `logs/phase3.5-base-metaspace.txt` |

| (p35-base 뒤) | Metaspace 사용 | 상한 | 클래스 |
|---|---|---|---|
| legacy order | 125.02 MB | 256 MB | 26,701 |
| legacy coupon | 123.31 MB | 256 MB | 26,338 |
| new order | 125.01 MB | 256 MB | 26,688 |
| new coupon | 123.17 MB | 256 MB | 26,323 |

### 1.1 v1.1 — PaymentGatewayClient (Kotlin)

| 기준 | 결과 | 근거 |
|---|---|---|
| commit 1 · 이미지 1 | PASS | `fd839d6`, `order-app:phase3.5-v1.1`(재빌드 없이 재사용). 변경 클래스 1(`PaymentGatewayClient`) + pom(Kotlin 빌드) |
| `poc.evidence` 수정 0줄 | PASS | `git diff 98c9356 -- services/evidence-collector` 0줄 |
| 3 run, Undelivered 0, degraded 0 | PASS | `p35-v1.1-1..3` run.sh exit 0, verify 3/3 PASS, run-meta `dirty: false`(rev `47d7191`), images.order legacy=phase3.3-base / new=phase3.5-v1.1 |
| 모든 diff가 4분류로 설명됨 | PASS (diff 0) | C `{SAME: 58}` ×3, B0·B1 DIFF 0 ×3, dbstate OK. `logs/phase3.5-v1.1-verdict.txt` |
| learn 리뷰 · 규칙 | 해당 없음 | learn Uncertain 유형 0 → 라벨 0, 규칙 0 |
| 3 run 결과 동일 | PASS | 세 run 모두 SAME 58 |

v1.1 해석: Java record `ChargeRequest`를 Kotlin data class로 바꿔도 Boot JsonMapper(+jackson-module-kotlin)가 같은 순서의 JSON을 만든다 — `externalCalls.requestBodyHash`가 양쪽 동일. callTree의 `PaymentGatewayClient.charge`도 FQCN·메서드명이 그대로라 B0(원문)에서도 차이가 없다. Kotlin 전환의 흔적은 행동 Evidence가 아니라 Metaspace(+7.4 MB, +1,801 클래스)에만 남았다.

| (p35-v1.1 뒤) | Metaspace 사용 | 클래스 |
|---|---|---|
| legacy order | 126.79 MB | 26,715 |
| new order (v1.1) | **134.23 MB** | **28,516** |
| legacy / new coupon | 124.78 / 124.66 MB | 26,341 / 26,326 |

### 1.2 v1.2 — Order·OrderItem 엔티티 + OrderRepository (Kotlin)

| 기준 | 결과 | 근거 |
|---|---|---|
| commit 1 · 이미지 1 | PASS | `fc6e6e2`, `order-app:phase3.5-v1.2`. 변경 클래스 3(`Order`, `OrderItem`, `OrderRepository`) — 7 files, +172 −176 |
| `poc.evidence` 수정 0줄 | PASS | `git diff 98c9356 -- services/evidence-collector` 0줄 |
| 3 run, Undelivered 0, degraded 0 | PASS | `p35-v1.2-1..3` run.sh exit 0, verify 3/3 PASS, `dirty: false`(rev `fc6e6e2`), images.order legacy=phase3.3-base / new=phase3.5-v1.2 |
| 모든 diff가 4분류로 설명됨 | PASS (diff 0) | C `{SAME: 58}` ×3, B0·B1 DIFF 0 ×3, dbstate OK. `logs/phase3.5-v1.2-verdict.txt` |
| learn 리뷰 · 규칙 | 해당 없음 | learn Uncertain 유형 0 → 라벨 0, 규칙 0 |

전환 내용(D17 준수): data class 아님, `class X protected constructor()` + no-arg(jpa), all-open으로 클래스·메서드 open(`javap`: `public class poc.order.Order`, getter non-final), JPA 애노테이션은 필드에(필드 접근 — Java와 같음), nullable 컬럼(`transaction_id`·`idempotency_key`·`coupon_key`)만 `String?`, 나머지는 `lateinit`/기본값 + `protected set`, `OneToMany(cascade = ALL, orphanRemoval = true)`·`@OrderBy("lineNo ASC")` 그대로, 상수는 `companion object const val`(Java `switch case Order.PAID`가 그대로 컴파일), `OrderItem`의 id·order는 Java처럼 getter 없는 private. Boolean 프로퍼티 없음. `OrderRepository`는 Java 호출부를 위해 `Optional` 반환 유지.

v1.2 해석: SQL 원문(B0)까지 같다 — Hibernate가 매핑 메타데이터에서 SQL을 만들고 필드 접근·컬럼·연관 설정이 같으면 클래스가 Kotlin이어도 문장이 같다. lazy `items` 로딩(`select … from order_items … order by line_no`) 횟수·위치도 같아 dbRead 축 차이 0 — all-open을 처음부터 넣은 효과(빠뜨렸다면 final 엔티티로 프록시가 깨질 수 있는 구간).

| (p35-v1.2 뒤) | Metaspace 사용 | 클래스 |
|---|---|---|
| legacy order | 128.18 MB | 26,717 |
| new order (v1.2) | **134.90 MB** | **28,764** |
| legacy / new coupon | 125.59 / 125.67 MB | 26,345 / 26,330 |

### 1.3 v1.3 — OrderService·Outcome·OrderPaid·OrderEventPublisher (Kotlin)

| 기준 | 결과 | 근거 |
|---|---|---|
| commit 1 · 이미지 1 | PASS | `c64618f`, `order-app:phase3.5-v1.3`. 변경 클래스 3 파일(`OrderService`(+`Kind`·`Outcome`·`NewItem`), `OrderPaid`, `OrderEventPublisher`) — 7 files, +174 −189 |
| `poc.evidence` 수정 0줄 | PASS | `git diff 98c9356 -- services/evidence-collector` 0줄 |
| 3 run, Undelivered 0, degraded 0 | PASS | `p35-v1.3-1..3` run.sh exit 0, verify 3/3 PASS, `dirty: false`(rev `c64618f`), images.order new=phase3.5-v1.3 |
| 모든 diff가 4분류로 설명됨 | PASS (diff 0) | C `{SAME: 58}` ×3, B0·B1 DIFF 0 ×3, dbstate OK. `logs/phase3.5-v1.3-verdict.txt` |
| learn 리뷰 · 규칙 | 해당 없음 | learn Uncertain 0. v1.3은 규칙을 만들지 않는 단계(만들 것도 없음) — 적용된 규칙 0, eval Uncertain 0→0 |

전환 내용: 생성자 주입은 primary constructor, `@Transactional`·`@TransactionalEventListener`는 그대로(spring all-open으로 프록시 가능), `Outcome`·`NewItem`은 아직 Java인 `OrderController`가 record 접근자(`kind()`·`order()`)·생성자로 쓰므로 **`@JvmRecord data class`**(`javap`: `extends java.lang.Record`, `kind()`·`order()`) — 컨트롤러 무변경. `Kind`는 Kotlin `enum class`(Java `switch`가 그대로 동작). `OrderPaid`는 Java 사용처가 없어져 plain data class(페이로드는 앱 JsonMapper + jackson-module-kotlin). `catch (RestClientException | IllegalStateException)`은 catch 두 개로. 로거는 companion.

v1.3 해석: B0(원문)까지 같다 — 트랜잭션 이름(`poc.order.OrderService.pay`, Spring이 `클래스.메서드`로 만든다), callTree(`OrderController.pay → OrderService.pay → OrderRepository.findByOrderKey → PaymentGatewayClient.charge → OrderEventPublisher.onOrderPaid`), 타임라인(COMMIT_BEGIN 4 < UPDATE 5 < PUBLISH 6 < COMMITTED 7), `order.paid` 페이로드 바이트(`{"orderKey":…,"amount":…,"couponKey":…}` — record와 data class가 같은 순서)가 모두 같다.

| (p35-v1.3 뒤) | Metaspace 사용 | 클래스 |
|---|---|---|
| legacy order | 128.98 MB | 26,720 |
| new order (v1.3) | **134.71 MB** | **28,699** |
| legacy / new coupon | 126.44 / 126.44 MB | 26,347 / 26,331 |

### 1.4 v1.4 — OrderController·DTO·OrderView·CouponClient·ClockConfig·OrderApplication·requestlog (Kotlin, Order 전면)

| 기준 | 결과 | 근거 |
|---|---|---|
| commit 1 · 이미지 1 | PASS | `120b212`, `order-app:phase3.5-v1.4`. 변경 클래스 7 파일(`OrderController`(+DTO 4), `OrderView`(+`Item`), `CouponClient`(+`UseRequest`·`CouponUse`·`CouponFailure`), `ClockConfig`, `OrderApplication`, `requestlog.RequestLogFilter`, `requestlog.CachedBodyRequest`) — 15 files, +350 −429. `services/order/src/main/java` 0파일 |
| `poc.evidence` 수정 0줄 | PASS | `git diff 98c9356 -- services/evidence-collector` 0줄 — **Kotlin 전면 New에 수정 없이 부착(이식성)** |
| 3 run, Undelivered 0, degraded 0 | PASS | `p35-v1.4-1..3` run.sh exit 0, verify 3/3 PASS, `dirty: false`(rev `120b212`), images.order new=phase3.5-v1.4. new 기동 로그 `Starting OrderApplicationKt` |
| 모든 diff가 4분류로 설명됨 | PASS (diff 0) | C `{SAME: 58}` ×3, B0·B1 DIFF 0 ×3, dbstate OK. `logs/phase3.5-v1.4-verdict.txt` |
| learn 리뷰 · 규칙 | 해당 없음 | learn Uncertain 0, 규칙 생성 없는 단계 — 적용 규칙 0, eval Uncertain 0→0 |

전환 내용: 컨트롤러 메서드명(`create`·`getByKey`·`get`·`pay`·`cancel`·`onConflict`·`onCouponFailure`)·경로·`@ExceptionHandler` 유지, Java `static respond/error`는 private 멤버(프록시를 거치지 않아 callTree에 없음 — Java와 같음). 요청 DTO는 Java가 null을 검사하던 필드(`orderKey`·`items`·`couponKey`)만 `?`, Java primitive였던 `qty`·`price`는 기본값 0(값이 없을 때 Java record처럼 0). `CouponFailure`는 `RuntimeException(kind.name, null, false, false)`(스택·메시지 억제 그대로), `kind`는 Kotlin 프로퍼티. `OrderView`는 data class + companion `from`. `ClockConfig`는 `@Configuration`(all-open으로 CGLIB 가능). main은 최상위 함수(`Start-Class: poc.order.OrderApplicationKt`). `RequestLogFilter`는 `linkedMapOf`로 로그 키 순서 유지. jackson-module-kotlin은 v1.1에서 이미 추가돼 있어 이 단계의 요청 DTO 역직렬화에 그대로 쓰였다.

v1.4 해석: 응답 본문 바이트(B0)까지 같다 — Java record `OrderView`와 Kotlin data class `OrderView`가 Boot JsonMapper(+kotlin 모듈)에서 같은 필드 순서(생성자 순서)로 직렬화된다. 쿠폰 실패 400(S008 USED 쿠폰)도 `OrderController.onCouponFailure`가 depth-0 노드로 찍히는 callTree·`ROLLED_BACK`·고정 본문까지 같다.

| (p35-v1.4 뒤) | Metaspace 사용 | 클래스 |
|---|---|---|
| legacy order | 128.94 MB | 26,423 |
| new order (v1.4) | **135.33 MB** | **28,726** |
| legacy / new coupon | 126.93 / 126.86 MB | 26,348 / 26,332 |

## 2. 변경 파일·커밋

| 커밋 | 내용 |
|---|---|
| `94b577b` phase3.4: id 값 마스킹 | `engine/normalize.py`, `engine/verdict.py`, `engine/tests/test_engine.py` |
| `fd839d6` phase3.5-v1.1: PaymentGatewayClient를 Kotlin으로 | `services/order/pom.xml`, `PaymentGatewayClient.java` → `.kt`, `deploy/k8s/new/kustomization.yaml` |
| `3fe2d58` phase3.5-v1.1: 중단 보고 | (이전 판 보고서 — 이 문서로 대체) |
| `d1b283e` phase3.5: Metaspace 상한 256m·limits 1Gi (base 공통) | `deploy/k8s/base/{order,coupon}.yaml`, `docs/phase3-plan.md`(D-2 아래 한 줄 + 3.5 구현 시 확정) |
| `47d7191` phase3.5: run.sh preflight — Store에 같은 runId Evidence가 있으면 중단 | `k6/run.sh` |
| `71c8f04` phase3.5-v1.1: 결과·규칙·보고서 | 이 문서, `docs/phase3-result.md`, `docs/reports/logs/phase3.5-*`, `docs/phase3-plan.md`(구현 시 확정 추가) |
| `fc6e6e2` phase3.5-v1.2: Order·OrderItem 엔티티와 OrderRepository를 Kotlin으로 | `Order.java`·`OrderItem.java`·`OrderRepository.java` → `.kt`, new overlay `phase3.5-v1.2` |
| `cc4dab9` phase3.5-v1.2: 결과·규칙·보고서 | 이 문서, `docs/phase3-result.md`, `docs/reports/logs/phase3.5-v1.2-*` |
| `c64618f` phase3.5-v1.3: OrderService·Outcome·OrderPaid·OrderEventPublisher를 Kotlin으로 | 3 파일 `.java` → `.kt`, new overlay `phase3.5-v1.3` |
| `21cdc4d` phase3.5-v1.3: 결과·규칙·보고서 | 이 문서, `docs/phase3-result.md`, `docs/reports/logs/phase3.5-v1.3-*` |
| `120b212` phase3.5-v1.4: OrderController·DTO·OrderView·CouponClient·설정·Application을 Kotlin으로 (Order 전면 Kotlin) | 7 파일 `.java` → `.kt`(`requestlog` 포함), `src/main/java` 제거, new overlay `phase3.5-v1.4` |
| (이 커밋) phase3.5-v1.4: 결과·규칙·보고서 | 이 문서, `docs/phase3-result.md`, `docs/reports/logs/phase3.5-v1.4-*`, `docs/phase3-plan.md`(3.5 구현 시 확정), `CLAUDE.md`(3.5 상태) |

## 3. 실행 명령·주요 출력

```
# 게이트: 레포 overlay는 그대로, order 이미지만 바꿔 apply
kubectl apply -k deploy/k8s/legacy
kubectl kustomize deploy/k8s/new | sed 's#order-app:phase3.5-v1.1#order-app:phase3.3-base#' | kubectl apply -f -
k6/run.sh --run-id p35-base --iterations 3 --vus 3          → exit 0
verify_sameness ×3 → PASS; verdict.py --arm C|B0|B1 ×3 → {SAME: 58}

# v1.1
kubectl apply -k deploy/k8s/new                              → order phase3.5-v1.1
k6/run.sh --run-id p35-v1.1 --iterations 3 --vus 3          → exit 0
verify_sameness ×3 → PASS; verdict C|B0|B1 ×3 → {SAME: 58}; review.py list --split learn → 유형 0

# v1.2 (단계마다 같은 절차)
docker build -f services/order/Dockerfile -t order-app:phase3.5-v1.2 services/ → docker save → kind load image-archive
kubectl apply -k deploy/k8s/new; k6/run.sh --run-id p35-v1.2 --iterations 3 --vus 3   → exit 0
verify ×3 PASS; verdict C|B0|B1 ×3 → {SAME: 58}; review list → 유형 0
```

## 4. Legacy/New 비교

| 단계 | run | C SAME/IMP/UNC/CV | B0 DIFF | B1 DIFF | Undelivered | degraded | dbstate |
|---|---|---|---|---|---|---|---|
| base(A/A) | p35-base-1..3 | 58/0/0/0 ×3 | 0 | 0 | 0 | 0 | 일치 |
| v1.1 | p35-v1.1-1..3 | 58/0/0/0 ×3 | 0 | 0 | 0 | 0 | 일치 |
| v1.2 | p35-v1.2-1..3 | 58/0/0/0 ×3 | 0 | 0 | 0 | 0 | 일치 |
| v1.3 | p35-v1.3-1..3 | 58/0/0/0 ×3 | 0 | 0 | 0 | 0 | 일치 |
| v1.4 | p35-v1.4-1..3 | 58/0/0/0 ×3 | 0 | 0 | 0 | 0 | 일치 |

Metaspace(참고값, run 뒤 측정) — order legacy / new: base 125.02 / 125.01 → v1.1 126.79 / 134.23 → v1.2 128.18 / 134.90 → v1.3 128.98 / 134.71 → v1.4 128.94 / 135.33 MB. 클래스 수 new − legacy: v1.1 +1,801 · v1.2 +2,047 · v1.3 +1,979 · v1.4 +2,303. 증가분 대부분은 v1.1에서 들어온 Kotlin stdlib·reflect·jackson-module-kotlin(런타임 의존)이고, 이후 단계의 변화는 측정 시점의 로딩 차이 수준이다. 256m 상한 대비 53%

## 5. 지시와 다르게 구현한 것

- jackson-module-kotlin을 v1.1에서 추가(지시 규칙 "Kotlin DTO를 역직렬화하는 첫 단계"상 `ChargeResponse`가 v1.1)
- "phase3.3 기준" diff 기준점은 태그가 없어 `98c9356`(phase3.3 마지막 커밋)
- 게이트 run은 레포 overlay를 바꾸지 않고 렌더링 결과의 order 이미지만 치환해 apply(dirty=false 유지). 실제 이미지는 run-meta로 확인
- 지시에 없던 커밋 `47d7191`(run.sh preflight) — 6절의 두 번째 사례를 이 단계에서 고친 것

## 6. 문제·해결·남은 한계

- **환경 결함(Metaspace OOM)을 파이프라인이 잡아낸 사례** — `runs/p35-v1.1-oom-1`(첫 v1.1 run, 사다리 표 제외). New Order가 Metaspace 128m 상한에서 `OutOfMemoryError`(28건, 첫 지점은 지연 생성되는 Kafka producer 클래스 로딩). 파이프라인에는 **degraded 7세션 · `ack: failed` 3건 · 5xx 9건**으로 드러났고, barrier 미달로 run.sh가 export만 하고 멈춰 **판정에 들어가면 안 되는 run을 판정 전에 걸러냈다**. 측정해 보니 legacy(Java)도 128m의 99%(125.85 MB)라 Kotlin 런타임 몇 MB에 넘쳤다. → D-5 (A) 256m·limits 1Gi. 로그 `logs/phase3.5-v1.1-oom-{run,verify,applog}.txt`
- **runId 재사용 사고** — `runs/p35-v1.1-stale-1`(두 번째 v1.1 시도, 사다리 표 제외). OOM run 디렉터리를 옮긴 뒤 같은 runId(`p35-v1.1`)로 재실행했는데, Store에 OOM run의 Evidence 100건이 남아 있었다. k6 완료 폴링(`exists`)이 이전 Evidence를 보고 New가 R000001 생성을 끝내기 전에(New 완료 15:47:31.00, New R000002 도착 15:47:30.39) 다음 요청을 보내 New 쪽 조회·결제가 404 → 발행 없음 → 소비 Evidence 없음 → degraded 4·barrier 미달로 다시 걸러졌다. 엔진·Kotlin과 무관한 운영 실수. 해결: run.sh preflight에 "Store에 같은 runId Evidence 0건" 검사 추가(자동 삭제 없음), 그 Store run은 `DELETE /runs/p35-v1.1-1`(로컬 export는 보존)로 정리 후 재실행. 검사 동작 확인 `logs/phase3.5-preflight-runid.txt`(100건 있음 → exit 1). 로그 `logs/phase3.5-v1.1-stale-{run,verify}.txt`
- **잠재 차이(관측 안 됨) — sku 없는 주문 항목**: Java(Legacy)는 `sku` null이 INSERT까지 가서 실패(`DataIntegrityViolationException` → 컨트롤러 `onConflict` 409 `ORDER_KEY_EXISTS`)했을 것이다. Kotlin은 v1.2에서 `addItem(sku: String)`(컬럼 `nullable = false` → 지시대로 non-null), v1.4에서 `ItemRequest(sku: String)`이라 요청 역직렬화에서 실패(400, Spring 기본 에러 본문)한다. corpus에 sku 없는 항목이 없어 run에는 나타나지 않는다 — **corpus가 덮지 않는 입력 경로의 차이는 차등 검증으로 보이지 않는다**는 한계의 실례. 3.6 결함 카탈로그나 corpus 보강 후보
- 두 실패 run 모두 Evidence 안의 runId가 `p35-v1.1-1`이라 디렉터리 이름과 달라 엔진 입력 계약 대상이 아니다(보존용)
- **측정 도구**: Metaspace는 `jdk-tools:phase3.5`(로컬 빌드 JDK 이미지, kind 로드) ephemeral container로 대상 컨테이너 `/tmp/jdk`에 JDK를 복사한 뒤 `jcmd`. pod 스펙에 ephemeral container 기록이 남는다(재배포 시 사라짐). 측정은 run이 끝난 뒤에만
