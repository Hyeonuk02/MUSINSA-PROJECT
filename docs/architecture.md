# 프로젝트 아키텍처 v10.1

**운영 트래픽 재현과 변경 전후 행동 비교를 통한 시스템 교체 검증**
System Migration Verification Using Production Traffic Replay and Pre/Post Behavioral Comparison

> v10.1: 실험 시스템 DB를 MySQL 8로 확정, Phase 1 세부는 `docs/phase1-plan.md`가 기준
>
> v9.3 → v10 변경 요지: **Shadow-only 단일 파이프라인.** 별도 Deterministic Mode·Orchestrator·심볼릭 참조·Golden 배치를 제거하고, 그것들이 주던 보장을 (1) 독립 세션 corpus 설계 (2) client business key (3) k6의 요청당 New 완료 폴링 (4) 반복 run 으로 대체한다. 트래픽은 k6(VU=N, VU 안 순차) → Istio Ingress → VirtualService route(Legacy)/mirror(New). 판정은 요청 단위를 기본으로 유지하고, 세션 간 불변식만 집계 계약으로 본다. Undelivered는 4분류 밖 별도 버킷.
> 유지: NetworkPolicy 격리(REGISTRY_ONLY는 guardrail), Evidence Collector/Store/스키마, Evidence POST 제외 규칙, flush barrier, Normalization/Engine(클러스터 밖), 4분류 + Rule 루프, Layer 1 스코핑, 고정 시각, S0 리셋, replayRequestId, Phase 1 전체.

---

## 0. 연구 질문과 검증 범위

**연구 질문**: Legacy/New의 실행 행동 차이를 어디까지 자동으로 판별하여, 사람이 검토해야 하는 범위를 줄일 수 있는가?

**검증 범위 선언** (발표·문서에 그대로 사용)
> 본 시스템은 **관찰된 입력 집합(corpus)에 대해, 세션 간 독립성이 보장된 실행 조건에서** Legacy/New의 동작 보존을 검증한다. 세션을 가로지르는 동시 요청 간 상호작용(race, lock 경합, 트랜잭션 격리 수준)과 부하·용량 특성(풀 고갈, 스레드 모델, GC)은 검증 범위 밖이며, 실무에서 Canary Release·부하 테스트·모니터링이 담당하는 층이다. VU=N은 운영 부하의 재현이 아니라 "동시 사용자가 존재하는 조건"이며, 세션 독립성 때문에 경합을 검증하지 않는다.

**변경 없는 확정 사항**: 경험적 검증 / SAME·Improvement·Contract Violation·Uncertain 4분류 / Uncertain만 Human Review → Rule 축적 / Root Cause Analysis 제외 / Latency·throughput은 판정 기준 아님 / 주문·쿠폰·결제 MSA / Legacy·New 분리, 동일 S0, 고정 시각.

**연구 핵심 vs 인프라**
```
연구 핵심: Layer 1 스코핑 → corpus/k6 실행 규칙 → Evidence Collector/Store → Normalization → Engine → Human Review → Rule 축적
인프라:   Kubernetes NetworkPolicy(격리 경계) / Istio·Envoy(미러링 배달, REGISTRY_ONLY guardrail, proxy 스팬)
판단 규칙: 인프라 작업은 "연구 질문에 답하거나 고정 입력·격리 조건에 필요한가"를 통과해야 한다.
```

---

## 1. 전체 구조

```
Git Diff → 정적 Call Graph(+어노테이션 보정) → 영향 API → (Tag: 전체 미러 + 태그 / Filter: 세션 부분집합)
                                                            │
corpus  (독립 세션 × VU, client business key, replayRequestId, 고정 파일)
   │
  k6   VU=N (3~5). VU 안은 순차. 요청마다 New 완료 폴링 후 다음 요청.
   │
Istio Ingress Gateway → VirtualService ── route  → legacy ns (order·coupon·payment, DB, wiremock)
                                        └─ mirror → new ns    (동일 구성, NetworkPolicy로 외부 egress 차단)
                                   │                          │
                            Evidence Collector          Evidence Collector     (서비스 내부 필터, replayRequestId)
                                   └──────────┬───────────────┘
                                        Evidence Store (verify ns)
                                run script: k6 종료 → 기대 건수 대기(flush barrier) → export → S0 리셋
                                              │ export JSON
═══════════════════════════════════════════════╪══════════════════════════════ 클러스터 경계
                                              ↓
                             Normalization → Verification Engine (클러스터 밖, CLI)
                              ├ 요청 단위 비교: 요청 내부 사이드이펙트, 세션 내 응답·상태 (business key 조인)
                              ├ 집계 비교:     세션 간 불변식
                              └ 전달 품질:     Undelivered 계수
                                              │
                      SAME / Improvement / Contract Violation / Uncertain   (+ Undelivered 버킷)
                                              │
                                 Uncertain → Human Review → Rule/Contract 축적 → 다음 run Engine 입력
```

### 1.1 클러스터

```
Kubernetes (kind ≥ v0.25)
├─ istio-system      Istiod, Ingress Gateway
├─ observability     OTel Collector, Jaeger (샘플링 100%)
├─ legacy            order / coupon / payment (+sidecar), 각 MySQL 8(emptyDir + init SQL, strategy Recreate), wiremock
├─ new               동일. NetworkPolicy default-deny egress(허용: DNS, 메시 내부, wiremock, verify)
└─ verify            Evidence Store (Service + PVC/export). Engine·Human Review·Rule 저장소는 클러스터 밖
```

### 1.2 Istio/Envoy의 역할 (이 셋으로 한정)

| 역할 | 구현 |
|---|---|
| 미러링 배달 | VirtualService `route→legacy`, `mirror→new`, `mirrorPercentage 100`. fire-and-forget, 미러 요청 Host에 `-shadow` |
| 격리 보조 (guardrail) | `outboundTrafficPolicy: REGISTRY_ONLY` + `Sidecar` 리소스 — 미등록 외부 의존성을 sidecar 로그로 드러냄. **보안 경계 아님**(Istio 보안 모범사례). 경계는 NetworkPolicy |
| proxy 스팬 | sidecar span → OTel Collector → Jaeger. Telemetry API로 샘플링 100% |

Istio가 해주지 않는 것(우리 몫): 헤더 전파(replayRequestId·traceparent — OTel Java agent Baggage), replayRequestId 부여(k6), 완료 대기(k6 폴링), Evidence 값, 판정, `-shadow` Host 정규화.

---

## 2. 왜 이 구조로 요청 단위 판정이 성립하는가

fire-and-forget + 동시성에서 요청 단위 비교가 깨지는 원인은 셋이고, 각각 설계로 막는다.

| 깨지는 원인 | 대응 |
|---|---|
| **세션 간 인터리빙**으로 상태가 갈라짐 | **세션 독립성**: 세션 간 공유 상태 없음(사용자별 주문·쿠폰). 공유 자원(선착순 쿠폰 수량, 재고)이 필요한 시나리오는 **한 세션 안에 넣어 순차로**. 세션이 독립이면 VU=N은 "N개의 순차 실행"이고 인터리빙은 결과에 영향 없음 |
| **체인 요청의 ID 불일치** — Legacy가 발급한 orderId를 New에 미러하면 다른 주문 | **client business key**: 주문 키를 k6가 생성(`orderKey`, replayRequestId에서 결정론적 파생). **후속 요청이 business key로 대상을 지정**(`POST /orders/{orderKey}/pay`, `GET /orders/by-key/{orderKey}`). 저장만 하고 dbId로 호출하면 무의미. 결제 idempotency key도 동일 방식. auto-increment id는 정규화 대상 |
| **New에서 앞 요청이 끝나기 전에 다음 요청 도착** | **k6 요청당 완료 폴링**: 다음 요청 전에 Evidence Store에서 `replayRequestId`의 New Evidence 도착을 확인(또는 New `/internal/settled?requestId=`). 요청당 1회, 타임아웃 시 해당 세션을 degraded로 표시. Kafka 도입 후엔 이벤트 처리 완료까지 포함 |

세 조건이 성립하면 요청 단위 비교(Response, 사이드이펙트, 순서)가 VU=N에서도 유효하다. 성립 여부는 **Phase 2 완료 조건(반복 run 간 diff 집합 동일)**로 실측한다. 실패하면 VU=1로 내린다(설정값 하나).

---

## 3. 식별자

| ID | 소유 | 역할 | 수명 |
|---|---|---|---|
| **replayRequestId** (`X-Replay-Request-Id`) | corpus / k6 | logical request 정체성, Legacy↔New 페어링 키. Envoy mirror가 헤더를 복사하므로 원본/미러 양쪽 동일 | corpus 고정 → run·arm을 넘어 안정. 반복 실행 시 `runId`와 결합 |
| business key (`orderKey`, `Idempotency-Key`) | corpus / k6 | 세션 내 상태 조인 키 | replayRequestId에서 결정론적 파생 |
| x-request-id | Envoy | proxy access log 상관 | 실행별 proxy correlation ID, 생성/보존은 Envoy 설정에 따름. 검증 논리는 의존하지 않음 |
| traceId | OTel(스택별) | 그 실행의 MSA 경로 조회 | Legacy≠New, 실행마다 다름 |

Evidence 키: `(runId, replayRequestId, stack, version)`. `runContext = {runId, iteration, vu, sessionId, arm, fixedClock, corpusVersion, s0Version, imageDigest}`.

---

## 4. Corpus와 실행 규칙

### 4.1 Corpus
```yaml
version: corpus-v1
sessions:
  - id: S001
    user: userA
    requests:
      - id: R000001  method: POST  path: /api/orders                          body: { orderKey: "ok-R000001", items: [...] }
      - id: R000002  method: POST  path: /api/orders/ok-R000001/coupon        body: { couponCode: "C-A1" }
      - id: R000003  method: POST  path: /api/orders/ok-R000001/pay           headers: { Idempotency-Key: "idem-R000003" }
      - id: R000004  method: GET   path: /api/orders/by-key/ok-R000001
  - id: S002 ...
```
- 세션 = 상태 의존성의 단위이자 독립성의 단위. 세션 안 순서 고정, 세션 간 공유 상태 없음
- 정상 흐름 + 에러 경로(만료 쿠폰, 결제 실패) 포함. 본문에 실행 시점 생성값 금지. 파일로 버전 고정
- 경합 시나리오는 별도 세션에 격리(집계 계약 + Needs Review 대상)

### 4.2 k6 실행 규칙
| 규칙 | 내용 |
|---|---|
| VU | N개(3~5). 각 VU가 세션 목록의 자기 몫을 순서대로. VU 안은 한 번에 요청 하나 |
| 완료 폴링 | 요청마다 New Evidence 도착 확인 후 다음 요청. 타임아웃 → 세션 degraded |
| 헤더 | `X-Replay-Request-Id`, `X-Run-Id`, `X-Session-Id`, business key |
| 반복 | 같은 corpus·S0·arm으로 **3회 이상**. 반복 간 diff 집합이 같아야 판정으로 인정, 다르면 그 차이를 아티팩트율로 보고 |
| 부하 아님 | RPS·램핑·VU 확대는 목적 아님 |

### 4.3 run script (S0 리셋 · flush barrier · export)
```
for iteration in 1..K:
  reset: 두 스택 DB(6) rollout restart → readiness 대기, Kafka 오프셋·WireMock 카운트 리셋
  k6 run (runId=..., iteration=...)
  flush barrier: Store 수신 건수 == 기대 건수(요청 수 × 서비스 수 × 2스택 − Undelivered) 대기, 타임아웃 시 누락 ID 보고
  export JSON (runId)
```
고정 시각: 두 스택 모두 `APP_FIXED_CLOCK` → Spring `Clock` 빈. 비교 유효 조건 해시 = hash(corpus, S0, WireMock 매핑, 고정 시각, 이미지 digest, Normalization 규칙).

---

## 5. Evidence

### 5.1 항목과 수집
Response / DB Read·Write(횟수, 필요 시 값) / External API Call / Event / Error Path / 실행 순서. 서비스 내부 필터(`OncePerRequestFilter` 등)가 수집해 응답 커밋 후 비동기로 Store에 POST.

**관측 트래픽 제외 규칙**: Store POST에 `X-Evidence-Internal: true`. traceTopology·External API Call 비교에서 제외, OTel span 억제, 요청 처리 시간에 영향 없게 비동기. flush barrier가 도착을 보장.

### 5.2 비교 수준

| Evidence | 비교 단위 | 근거 |
|---|---|---|
| 요청 내부 사이드이펙트 — 외부 호출 횟수·파라미터, DB 접근 횟수, 이벤트 발행 수·payload, 호출 순서, 에러 class | **요청 단위** | 다른 VU와 무관. **중복 결제·이벤트 누락 탐지는 여기** |
| 세션 내 응답·상태 (주문 생성 응답, 결제 결과, 조회 결과) | **요청 단위**, business key 조인 | 세션 독립 + 완료 폴링이면 결정적 |
| DB 최종 상태 | **business key 단위** 레코드 비교 | id·timestamp 정규화 |
| 세션 간 불변식 — 결제 승인 수 = 성공 주문 수, OrderCreated 수 = 주문 수, 외부 호출 총량 | **집계** | 순서 불변 |
| 경합 세션 | 집계 + Needs Review | 비결정적 |
| 전달 품질 | replayRequestId 기준 Legacy/New 도착 계수 | **Undelivered** |

### 5.3 Normalization
timestamp·UUID·auto-increment id·key 순서 정규화. **미러 요청의 Host `-shadow`는 비교 제외**(앱은 Host에 의존하지 않음). 정규화 대상은 도메인 모델에서 필드별 선언.

---

## 6. 판정

| 판정 | 정의 |
|---|---|
| SAME | 정규화 후 동일, 또는 승인된 의미적 동등 |
| Improvement | 사전 승인된 의도적 변화 Rule에 매칭 |
| Contract Violation | 계약 위반. **계약은 두 수준**: 요청 단위(횟수·순서·값) / 집계(불변식) |
| Uncertain | 규칙으로 판단 불가 → Human Review |
| **Undelivered** (4분류 밖) | New 미도착. 판정이 아니라 전달 품질 지표. 유실 이후 같은 세션의 요청은 degraded → 판정 제외. run 유실률이 임계치 초과 시 run 무효 |

요청 단위 통합: Contract Violation > Uncertain > Improvement > SAME. Uncertain만 Human Review → Rule/Contract 등록 → 다음 run부터 자동 처리.

---

## 7. Layer 1 스코핑

| 모드 | 동작 | 용도 |
|---|---|---|
| **Tag (기본, C)** | 전체 corpus 미러 + 영향 API 포함 요청/세션에 `impactScope=true`. Engine이 검토 우선순위·사전 확률로 사용 | FN 없음 |
| **Filter (B2)** | k6가 영향 API를 포함하는 **세션만** 실행. 세션이 의존 폐포이므로 별도 계산 불필요 | 재생 수 감소 vs 탐지율 하락 실측 |
| B2-S | 같은 세션 수 무작위 | Call Graph의 랜덤 대비 정당성 |
| 운영 서사 | Layer 1 결과 → VirtualService `match` 렌더링 → `kubectl apply` (선택적 미러) | 시연 |

정적 Call Graph의 unsoundness(DI/AOP/reflection)는 어노테이션 보정 + 확신 없는 지점은 클래스/엔드포인트 단위로 넓힘 + run 트레이스로 보정. 놓친 범위는 B1↔B2에서 실측.

---

## 8. 평가

| 단 | 구성 |
|---|---|
| B0 | 전체 미러 + exact diff |
| B1 | + Normalization (실무 도구 Diffy 수준 — Diffy 자체를 참조 실행으로 별도 돌릴 수 있음, arm은 아님) |
| B2 / B2-S | + 세션 Filter / 랜덤 |
| **C** | + 사이드이펙트 Evidence + 4분류 + Rule 누적 |

고정 입력: corpus, S0, 결함 주입 카탈로그(진짜 결함 / 정상 리팩터링 / 승인된 개선 — 동기 호출 순서 뒤바뀜, 결제 중복 호출, 이벤트 누락 포함), New v1→v3. **모든 arm은 같은 k6 프로파일, 반복 run(≥3)**. 지표: 결함 탐지율, SAME 오판, 재생 요청 수, Human Review 건수·라운드별 추세, Undelivered율, 반복 간 아티팩트율.

---

## 9. Phase

| Phase | 내용 | 상태 |
|---|---|---|
| 0 | nginx Mirroring Concept PoC (4.4까지) | 완료·보존 (`poc/nginx-mirroring/`, 배너: 최종 delivery 아님) |
| 1 | k8s + Istio 기반 | 다음 |
| 2 | Order(business key API) + Collector/Store/export + k6 + run script + 완료 폴링 + 반복 run 검증 | |
| 3 | Coupon·Payment(WireMock) + Normalization + Engine(요청 단위 + 집계) + 4분류 + Rule 루프 | |
| 4 | Call Graph → Tag/Filter + 사다리(반복 run) + 결함 주입 + (선택) 경합 세션·VS match 시연 | |

### Phase 1 — k8s + Istio 기반

아래는 요약이다. **단계별 세부 작업·완료 기준·버전 고정·설정 세부는 `docs/phase1-plan.md`가 기준**이며, 다르면 그 문서가 우선한다.

| # | 할 것 | 끝난 기준 |
|---|---|---|
| 1.1 | kind(≥ v0.25) 클러스터, node 이미지·Istio 버전 고정, 네임스페이스 4개, 로컬 이미지 로드, NetworkPolicy 스모크 | Ready, 노드 안에 이미지 존재(`crictl images`), 스모크 통과 |
| 1.2 | istioctl default 프로파일, `legacy`/`new` 주입 | sidecar 2컨테이너, `istioctl analyze` 경고 없음 |
| 1.3a | Phase 0 Order 앱을 `services/order/`로 복사해 **MySQL 8** 전환 + MySQL(emptyDir, init SQL, Recreate, readiness) + `APP_FIXED_CLOCK` | port-forward로 POST/GET, `rollout restart`로 S0 복원 |
| 1.3b | sidecar 주입된 curl pod에서 호출 | 앱 로그에 `x-request-id`, `istioctl proxy-config` 경로 확인 |
| 1.4 | OTel Collector(OTLP→OTLP→Jaeger) + `meshConfig.extensionProviders` + Telemetry 샘플링 100% + OTel Java agent | Envoy span + 앱 span 한 trace |
| 1.5 | NetworkPolicy(경계) + REGISTRY_ONLY(guardrail) + WireMock in `new` | ① sidecar pod: 즉시 502 + `BlackHoleCluster` 로그(NetworkPolicy 전) ② 비주입 pod: TCP 타임아웃(NetworkPolicy 후). 서명이 달라야 통과. `docs/isolation-proof.md` |
| 1.6 | Ingress Gateway + VirtualService(route→legacy, mirror→new) | 직접 넣은 `X-Phase1-Smoke-Id`가 양쪽 로그에 동일, new 쪽 Host `-shadow` |

### Phase 2 — 단일 파이프라인 end-to-end

| # | 할 것 | 끝난 기준 |
|---|---|---|
| 2.1 | Order API를 **business key** 기반으로: `POST /api/orders {orderKey}`, `GET /api/orders/by-key/{orderKey}`, `POST /api/orders/{orderKey}/pay {Idempotency-Key}`. 결제는 WireMock 스텁 | 양쪽 스택에서 orderKey로 생성·조회·결제 |
| 2.2 | corpus v1: 독립 세션 3개 × (생성→조회→결제→조회), 에러 경로 1개 | 스키마 검증 통과 |
| 2.3 | Evidence Store v0 (`verify` ns, POST 수신 → `(runId, replayRequestId, stack)` 저장, `count?runId=`·`exists?requestId=&stack=new`·export 엔드포인트) + Evidence JSON v0 고정 | export로 로컬 파일 확보 |
| 2.4 | Evidence 필터: request/response 캡처 → 응답 커밋 후 비동기 POST(`X-Evidence-Internal`). Legacy/New 동일 | 요청당 1건, Jaeger에서 Store POST가 비즈니스 span과 구분 |
| 2.5 | k6: VU=1 → 세션 순차, 헤더 주입, **요청당 New Evidence 도착 폴링** | Ingress 경유로 양쪽 Evidence 짝 맞음 |
| 2.6 | run script: reset → k6 → flush barrier → export | 3회 실행, 누락 0 |
| 2.7 | 동일성·pairing 검증(Phase 0 4.6 이관): method/URI/query/헤더/bodyHash 전건 대조 | 전건 PASS |
| 2.8 | **VU=3으로 올려 3회 반복** | 반복 간 diff 집합 동일(코드 동일이므로 diff 0 기대). 다르면 원인 분류 후 VU=1로 |

Phase 2 종료 = Evidence export JSON 확보 → **이후 Engine 개발은 클러스터 없이** 진행.

### Phase 3, 4 (개요)
- 3: Coupon 실서비스(Feign, Baggage 전파) + Payment(WireMock verify) + DB 접근·이벤트(Kafka + settled 폴링 확장)·순서 Evidence / Normalization / 요청 단위 + 집계 Engine / 4분류 / Rule 등록 / 결함 주입 New v1 / Human Review 최소 흐름
- 4: Call Graph + 어노테이션 보정 → Tag/세션 Filter / New v1~v3 / 사다리 반복 run / Undelivered·아티팩트율 보고 / (선택) 경합 세션, VS match 렌더링 시연, Diffy 참조 실행

---

## 10. 레포·문서 구조

```
migration-verification/
├── README.md            목적 → 1장 구조도 → Phase 현황 → 실행 → 문서 링크
├── CLAUDE.md            현재 Phase의 표 + 실행 지시만
├── docs/                architecture.md(v10.1) · phase1-plan.md · decision-log.md · phase0-nginx-poc.md(아카이브) · isolation-proof.md · related-work.md
├── poc/nginx-mirroring/ Phase 0 코드(동결)
├── deploy/k8s/          네임스페이스, Istio, NetworkPolicy, 앱·DB 매니페스트
├── services/{order,coupon,payment}/
├── corpus/              독립 세션 × VU, business key
├── k6/                  실행 스크립트(완료 폴링 포함), run script
├── evidence-store/
└── engine/              Normalization + Engine (로컬 CLI)
```

decision-log 항목: **"전달 방식 v4 — Shadow-only 단일 파이프라인. Deterministic Mode·Orchestrator 제거. 그 보장은 독립 세션·client business key·요청당 완료 폴링·반복 run으로 대체. 요청 단위 판정 유지, 세션 간 불변식만 집계. Undelivered는 판정 밖. 동시성·용량은 검증 범위 밖으로 명시. v9의 두 모드 분리는 '실행 통제 장치가 실험 구조를 복잡하게 만든다'는 판단으로 정정."**

---

## 11. 추가 결정 필요

1. 완료 폴링 방식 — Store `exists` vs New `/internal/settled`. Phase 2는 Store로 시작, Kafka 도입 시 settled 필요
2. Evidence Store 저장소 — 파일 vs 경량 DB (실험 시스템 DB인 MySQL과는 별개)
3. VU 수(3~5)와 세션 배분 방식
4. Undelivered 임계치(run 무효 기준)
5. 경합 세션을 Phase 4에 넣을지
6. Call Graph 도구, SAME 허용 범위 — Phase 3 diff 데이터 후
7. Diffy 참조 실행 여부

---

## 실행 지시 (구현 대화용)

위 문서를 기준으로 Phase 1.1부터 시작하자. 한 번에 여러 단계를 구현하지 말고, 각 단계에서 무엇을 만들지와 끝난 기준을 먼저 설명한 뒤 내가 실행 결과를 확인하면 다음으로 넘어간다. 오류는 해당 단계에서 해결한다. 문서에 없는 설계 결정이 필요하면 임의로 정하지 말고 질문해라. 1.2의 Istio 역할 세 가지 밖의 mesh 기능, Phase 3 이후 항목은 구현하지 않는다.
