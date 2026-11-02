# Phase 4.1 보고서 — 맵 합성

- 작업일: 2026-11-02
- 범위: `scoping/map.json`, 안정성·커버리지, `docs/call-graph-map.md`, 4.2 기대의 사실 확인, D-4.0a 범위 검증. 클러스터 접근 없음, run 없음
- 결과: **부분 PASS** — 끝난 기준 5개 중 4개 PASS. 사전 등록 예상 맵은 `order.pay` 7/8로 불일치(R000008). **결정 필요 3건**. 맵·계획표는 고치지 않았다

## 0. 결정 필요 사항

세 건 모두 **4.2 기대 등록 전에 필요**하다.

**D-4.1a 중복 결제 R000008은 결제·발행·소비를 실행하지 않는다 (findings O15)**

| 항목 | 계획 | 맵 |
|---|---|---|
| 4.1 예상 맵 `order.pay` ⊇ {PaymentGatewayClient, OrderEventPublisher, OrderPaidListener} | 전부 | **7/8** — R000008(S002) 3개 클래스 없음 |
| 0절·3절·4.2 표 "모든 `order.pay`", "order.pay 전부" | 8건 | 영향 요청 **7건** |
| 선택 세션·재생 요청 | 7·30 | **7·30(일치)** |

세션·감소율은 그대로다. S002가 첫 결제 R000007로 선택되므로 F1 target R000008도 빠지지 않는다. 바뀌는 것은 요청 단위 기대뿐이다.
- **(A) 권장**: 4.2 `scope-expectations.json`의 영향 요청을 "첫 결제 7건"(R000008 제외)으로 등록한다. 세션·재생 수 기대는 유지. 예상 맵 불일치는 이 보고서와 O15에 남긴다
- (B) "order.pay 전부"(8건)로 등록해 F3·F7·C1·v1.1 보조 산출에서 요청 단위 불일치를 그대로 기록한다

**D-4.1b C2 ablation(b)의 예측 "2세션·Recall < 1"은 이 corpus에서 성립하지 않는다 (findings O16)**

| 맵 | CouponService 영향 요청 | 선택 세션 | 재생 요청 |
|---|---|---|---|
| 요청 단위 + 홉 합산 | 24 | 6 (S004·S005·S006·S007·S008·S010) | 29 |
| 홉 합산 없음 — 계획 예측 | - | 2 (S004·S005) | - |
| 홉 합산 없음 — 맵 실측 | **16** | **6 (같음)** | **29** |

쿠폰 세션 4개는 `coupon.create`(진입 홉)로 먼저 쿠폰을 발급하므로 진입 홉만으로도 `CouponService`가 관측된다(R000026·R000031·R000035·R000043, S008은 R000039 `coupon.get`도). C2 대상 `0.h1` pair가 전부 그 세션 안에 있으므로 **Recall도 1.0일 것으로 예상**한다(4.5 run 전이라 미측정). 4.5 끝난 기준 "ablation(b)에서 2세션·Recall < 1"은 달성할 수 없다. C1 대조(`OrderPaidListener` → 합산 없으면 미관측)는 예측과 일치해 유효하다.
- **(A) 권장**: 4.5 기준을 "ablation(b) = 6세션·Recall 1.0 기대, 영향 요청 24 → 16 병기"로 run 전에 등록한다. 홉 합산 효과는 세션 선택 지표로는 C1에서만 드러난다고 보고한다
- (B) A에 더해 계획에 없는 보조 지표를 둔다 — "영향 **요청** 안에 든 비-SAME pair 비율"(요청 단위 맵의 근거 품질). 합산 없는 맵에서 `0.h1` pair는 세션 경유로 우연히 포함될 뿐 영향 요청은 아니라는 차이를 숫자로 보인다. 재생 단위는 여전히 세션

**D-4.1c 단순 이름 폐포가 Spring `@Order`를 `poc.order.Order` 참조로 잡는다 — v1.2·F2·E5 예측에 영향 (findings O17)**

D24 문구는 "단순 이름을 import 또는 토큰 경계로 참조"이고, 제외 대상은 자기 파일·주석·문자열뿐이다. 그대로 구현하면:

```
Order ← RequestLogFilter(@Order, 미관측) ← 참조자 없음 → 미해결 가지 → 전역
```

| 변형 | 계획 | D24 문구 그대로(예상) |
|---|---|---|
| v1.2 (Order, OrderItem, OrderRepository) | order.* 9세션·23% | **전역 11세션·0%** |
| F2 (Order) | 9세션·23% | **전역 11세션·0%** |
| E5 (OrderItem → Order) | order.* | **전역** |
| v1.3·F6 등 나머지 | 변화 없음 | 변화 없음 |

위 "예상"은 참조자 텍스트 사실(`logs/phase4.1-plan-compare.txt` E절)에서 도출한 것이다. 폐포 계산은 4.2 구현에서 나온다. `RequestLogFilter`는 `org.springframework.core.annotation.Order`를 import하므로 이 참조는 `poc.order.Order`가 아니다. 같은 부류로 `OrderPaidListener`의 중첩 record `OrderPaid`도 잡히지만 관측 클래스라 세션 수는 안 바뀐다.
- **(A) 권장**: 4.2 등록 전에 D24 토큰 참조를 정밀화한다 — 그 파일이 같은 단순 이름을 **다른 패키지에서 import하거나 자체 중첩 선언**하면 대상 클래스 참조로 세지 않는다(같은 패키지·대상 import·FQCN 참조만 인정). 계획 표(9세션)가 유지된다. 전역을 줄이는 방향이므로 fail-closed를 약화하는 변경이고, 그래서 승인을 요청한다
- (B) D24 그대로 둔다. v1.2·F2·E5 기대를 전역으로 등록하고 4.3 "F 변형 감소율 묶음"에서 F2가 0%로 바뀐다. 텍스트 폐포의 오탐 비용 실례로 보고한다

## 1. 끝난 기준별 결과

| 기준 | 결과 | 근거 |
|---|---|---|
| 맵 JSON 커밋 | PASS | `scoping/map.json` — 요청 48, 엔드포인트 8, 클래스 10 |
| 3 run 동일 | PASS | p36-base-1·2·3 맵 본문 sha256 `2c968eee…6668e` 동일. `logs/phase4.1-map-stability.txt` |
| 안정성(p33·p35-base 차이는 S011만) | PASS | 6 run 모두 차이 세션 = S011(R000047·R000048)뿐. 같은 로그 |
| 커버리지 표, 엔드포인트 8/8 | PASS | 엔드포인트 8/8, 빈 11 중 10 관측(`phase3.3-base`·`phase3.5-v1.4` 동일). 미관측 빈 1 = `RequestLogFilter`, 이유 = AOP 포인트컷 `!within(jakarta.servlet.Filter+)`. `docs/call-graph-map.md` 커버리지 절 |
| 서비스 간 간선 2종 | PASS | HTTP `0.h1` 5건(쿠폰 주문 생성), Kafka `0.e1` 7건(결제). `docs/call-graph-map.md` 간선 표 |
| 사전 등록 예상 맵 | **FAIL(부분)** | 7개 엔드포인트 중 6개 전 요청 만족, `order.pay` **7/8**(R000008 — D-4.1a). 쿠폰 주문·쿠폰 결제 조건은 전부 만족. `logs/phase4.1-plan-compare.txt` A절 |
| 4.2 기대의 사실 확인 | PASS | `CouponService` ∈ coupon.create 6/6·get 6/6·use 4/4, `OrderPaidListener` 7개 홉 전부 `0.e*`이고 쿠폰 없는 결제 4건 포함, `CouponService.settle`은 쿠폰 결제 `0.e1` 3건에만. 같은 로그 B절 |

**예측 대조 요약**(`logs/phase4.1-plan-compare.txt`, [DIFF] 5건은 전부 위 D-4.1a·b)

| 예측 | 결과 |
|---|---|
| 관측 클래스별 선택 — Order 공통 9·37 / 결제·발행·리스너 7·30 / Coupon 6·29 | 9개 클래스 **전부 일치** |
| 미관측 — Order, OrderItem, OrderPaid, OrderView, ClockConfig, OrderApplication, RequestLogFilter, CachedBodyRequest | 8개 **전부 일치** |
| "order.pay 전부" 표현(PaymentGatewayClient·OrderEventPublisher·OrderPaidListener) | **3건 불일치** → D-4.1a(예상 맵 불일치 1건 포함) |
| 합산 없는 맵: OrderPaidListener 미관측 / CouponService 2세션 | 전자 일치, 후자 **불일치** → D-4.1b |
| 폐포 경유 세션 수(v1.2·F2·E5) | 4.2 계산 전. D24 문구 그대로면 **불일치 예상** → D-4.1c |

**D-4.0 지시 이행**

| 항목 | 결과 | 근거 |
|---|---|---|
| 사다리 범위의 `services/` 필터 | 확인 — 범위 안 비코드 커밋 전부 services 파일 0건(v1.1: 3커밋, v1.2: 4커밋(v1.1 중단 보고 `3fe2d58` 포함), v1.3·v1.4: 각 1커밋) | `logs/phase4.1-diff-ranges.txt` |
| 필터 후 변경 | v1.1 pom + PaymentGatewayClient, v1.2 3클래스, v1.3 3파일, v1.4 7파일. 모두 계획 표의 변경 클래스와 같다 | 같은 로그 |
| F1~F9 | 각 1커밋, `services/order`의 kt 1~2 파일만(`M`) | 같은 로그 |
| C1·C2 | 브랜치가 아직 없다 — 4.5에서 같은 방식으로 확인 | - |
| D24 보완 한 줄 | 추가 | `docs/decision-log.md` |
| O14 해석, D-4.0b | 구현 시 확정 (4.1)에 기록 | `docs/phase4-plan.md` |

## 2. 변경 파일·커밋

| 커밋 | 내용 |
|---|---|
| `ce70b16` phase4.1: 맵 합성·계획 대조 도구, D24 diff 범위 보완 | `scoping/{map.py,map.json,map_report.py}`, `scoping/tests/{test_map.py,test_common.py}`, `docs/call-graph-map.md`, `docs/decision-log.md`, `docs/phase4-plan.md`(구현 시 확정 (4.1)) |
| (이 커밋) phase4.1: 보고서 | 이 문서, `docs/reports/logs/phase4.1-*.txt`, `docs/findings.md`(O15~O17), `CLAUDE.md`(4.1 상태) |

## 3. 실행 명령·주요 출력

```
.venv/bin/python scoping/map.py --runs runs/p36-base-1 runs/p36-base-2 runs/p36-base-3 --out scoping/map.json \
    --compare runs/p33-1 runs/p33-2 runs/p33-3 runs/p35-base-1 runs/p35-base-2 runs/p35-base-3
  → 3 run sha256 동일, requests 48, endpoints 8, classes 10, compare 6건 모두 S011만, exit 0
.venv/bin/python scoping/map_report.py --doc docs/call-graph-map.md   → [DIFF] 5건
.venv/bin/python -m pytest scoping/tests   → 38 passed
.venv/bin/python -m pytest engine/tests    → 37 passed
.venv/bin/python scoping/check_inputs.py   → 점검 64건, FAIL 0
```

전문: `docs/reports/logs/phase4.1-{map-stability,plan-compare,diff-ranges,pytest}.txt`

## 4. Legacy/New 비교

해당 없음(맵은 Legacy 레코드만, run 없음).

| 클래스 | 실행 요청 | 선택 세션 | 재생 요청 | 감소율(요청) |
|---|---|---|---|---|
| OrderController·OrderService·OrderRepository | 32 | 9 | 37/48 | 22.9% |
| PaymentGatewayClient·OrderEventPublisher·OrderPaidListener | 7 | 7 | 30/48 | 37.5% |
| CouponService·CouponRepository | 24 | 6 | 29/48 | 39.6% |
| CouponController | 21 | 6 | 29/48 | 39.6% |

## 5. 지시와 다르게 구현한 것

- `map.json`에 계획 형식 밖의 필드 추가: `corpus`, `bodySha256`, `endpoints[id].hopRequests`. `consume.order.paid`는 진입 요청이 없어 hopRequests 없이는 8/8을 표현할 수 없다(구현 시 확정 (4.1))
- 커버리지 소스를 "head" 하나가 아니라 `phase3.3-base`·`phase3.5-v1.4` 두 태그로 했다. 맵의 기준은 Legacy 코드이고 변형의 head는 사다리 끝 쪽이다. 두 태그 결과는 같다
- 계획에 없던 `scoping/map_report.py` 추가 — 예측 대조를 재현 가능하게 하고 `docs/call-graph-map.md`를 맵에서 생성하기 위해
- 4.5 ablation(b)와 폐포 참조자는 4.1 범위 밖이지만 4.2 등록 전에 예측 차이를 찾으려고 텍스트·맵 사실만 미리 확인했다(`impact.py`는 손대지 않음)
- `test_skeleton_clis_exit_2`에서 map 항목 제거(골격이 끝났으므로)

## 6. 문제·해결·남은 한계

- **예측 차이 3건**: 0절, findings O15~O17
- **커버리지 파서 버그(해결)**: Kotlin 생성자의 `"\${…}"`에서 헤더가 끊겨 `RequestLogFilter`의 이유가 "원인 미상"으로 나왔다. `${`를 빼고 헤더를 판단하도록 고치고 테스트 추가
- **범위 필터로 빠지는 base 매니페스트**: v1.2 범위의 `d1b283e`(Metaspace 256m·limits 1Gi, `deploy/k8s/base`)는 양쪽 스택 공통 변경이라 스코핑 대상이 아니지만, `services/` 필터가 빠뜨리는 실제 배포 변경의 예다. 범위 규칙의 한계로 기록
- **맵은 corpus가 실행한 경로만 안다**: 클래스 10개는 corpus 경로의 빈이다. 비-빈 12개는 폐포로만 닿는다(`docs/call-graph-map.md`)
- **Coupon 클래스의 예상 맵 판정**은 `coupon.*` 진입 홉·쿠폰 주문·쿠폰 결제를 corpus 본문의 couponKey와 결제 경로의 orderKey로 식별했다. 다른 방식(응답·verdict)과 교차 확인은 하지 않았다
