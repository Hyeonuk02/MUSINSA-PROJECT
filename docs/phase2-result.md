# Phase 2 결과 — 단일 파이프라인 end-to-end

> 완료 2026-10-12. 계획: [phase2-plan.md](phase2-plan.md) (v3). 전체 설계: [architecture.md](architecture.md).
> 결정 기록: [decision-log.md](decision-log.md) D9~D13. 격리 증명: [isolation-proof.md](isolation-proof.md).
> 이 문서의 숫자는 `runs/`의 산출물과 Phase 2 진행 중 실측 보고에 있는 값만 쓴다. 표본이 작은 값은 **참고**로 표시한다.

---

## 1. 요약

k6(호스트) → Istio Gateway(route legacy / mirror new) → Legacy·New Order → Evidence 필터 → Evidence Store → `runs/<runId>/` JSON까지 한 줄로 연결됐다.
같은 코드를 두 스택에 올린 A/A run을 VU=1로 3회(p26-1..3), VU=3으로 3회(p28-1..3) 돌렸고,
여섯 run 모두 요청 14건이 양쪽에 빠짐없이 도착했으며(Undelivered 0, degraded 0) 응답·DB 접근 비교의 diff 집합은 모두 공집합(∅)이었다.
이 export JSON 형식이 Phase 3 엔진의 입력 계약이고, 이후 엔진 개발은 클러스터 없이 이 파일만으로 진행한다.

## 2. 산출물

**코드·매니페스트·스크립트**

| 영역 | 경로 |
|---|---|
| Order API (business key) | `services/order/src/main/java/poc/order/` |
| Evidence 수집기 | `services/order/src/main/java/poc/evidence/` (ReplayContext, EvidenceFilter, EvidenceStatementInspector, EvidenceSender, BufferedBodyRequest, EvidenceAutoConfiguration) + `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` |
| Evidence Store | `evidence-store/` (`app.py`, `Dockerfile`, `requirements.txt`) |
| corpus | `corpus/corpus-v1.json`, `corpus/schema.json`, `corpus/validate.py`, `corpus/tests/invalid/*.json` |
| 재생·실행 | `k6/run.js`, `k6/run.sh`, `k6/spill-recover.sh` |
| 엔진(로컬) | `engine/common.py`, `engine/verify_sameness.py`, `engine/diff_v0.py` |
| 매니페스트 | `deploy/k8s/base/` (order, mysql, `mysql-networkpolicy.yaml`, wiremock), `deploy/k8s/{legacy,new}/order-otel.yaml`, `deploy/k8s/verify/evidence-store.yaml`, `deploy/k8s/istio/virtualservice-shadow.yaml`, `deploy/k8s/tools/mysql-probe.yaml` |
| 호스트 의존성 | `requirements.txt` (루트 `.venv` 하나) |

**문서**: `docs/evidence-schema-v0.json`, `docs/phase2-plan.md`, `docs/phase2-result.md`(이 문서), `docs/isolation-proof.md`("스택 간 DB 격리"·"관찰" 절), `docs/decision-log.md`(D9~D13), `docs/references/kakaopay-aop-shadow.md`

**커밋 범위**: `7bf3f3b` phase2.1 ~ `7dfc535` phase2.8 (+ 이 문서 커밋)

**이미지**

| 이미지 | 태그 / 식별자 |
|---|---|
| order (legacy·new 동일) | `order-app:phase2-5`, imageRef `sha256:845712191714f8890785835105113d14642d7b7f07ac797de2f3497d7a4eb9b0` |
| evidence-store | `evidence-store:phase2`, imageRef `sha256:8d2b4d2cc56f5de20189988e6300972b57f521c9a160af2d29043ef3c17f09c7` |
| wiremock | `wiremock/wiremock@sha256:d61e7720f89483fdef5366843b58d1dfd06bcce5828179c9f2f54de5c28354b0` (3.13.1) |

imageRef는 kind 노드 containerd의 이미지 config digest(run-meta에 기록). 로컬 빌드 이미지는 kind load로만 존재해 레지스트리 manifest digest가 없다.

## 3. Evidence 스키마 v0 확정

스키마: [`docs/evidence-schema-v0.json`](evidence-schema-v0.json) (JSON Schema 2020-12, `examples`에 예시 1건 — 스키마 통과 확인)

- **키**: `(runId, replayRequestId, stack)`. Store는 같은 키를 덮어쓴다(멱등)
- **필드**: `schemaVersion`(`v0`) · `runId` · `replayRequestId` · `sessionId` · `stack`(legacy/new) · `service` · `version` ·
  `request{method, path, query, headers, bodyHash}` · `response{status, headers, bodyHash, body}` ·
  `dbAccess{statements[{seq, sql}], truncated}` · `callTree` · `timing{arrivedAt, completedAt, arrivedNano, completedNano}` · `capturedAt`
- `headers`는 `EVIDENCE_HEADERS` 5개(`X-Replay-Request-Id, X-Run-Id, X-Session-Id, Idempotency-Key, Content-Type`)만, 소문자 키
- `dbAccess.statements[].sql`은 Hibernate가 JDBC로 보내기 직전의 원문(바인딩 전). 앱은 가공하지 않는다. 문장당 2,048자·요청당 200건 상한, 넘으면 `truncated: true`

**확정된 해석**
1. `response.body`가 32KB를 넘으면 `null`, `bodyHash`는 유지
2. 요청 본문이 없으면 `request.bodyHash`는 빈 바이트열의 sha256 (`null` 아님)
3. 최상위 `additionalProperties: false` — 필드를 추가하려면 `schemaVersion`을 올린다

- `callTree`는 v0에서 항상 `null` — Phase 3 자리 예약
- 요청 처리 중 예외가 필터 밖으로 나가면(`chain.doFilter` 예외) Evidence를 남기지 않는다. k6 degraded·2.7 Undelivered로 드러나며, Phase 3에서 schema v1 `error` 필드로 다룬다

## 4. 실측 수치

### (a) A/A 결과

| run | VU | count L/N | Undelivered L/N | degraded | response diff | dbAccess diff |
|---|---|---|---|---|---|---|
| p26-1 | 1 | 14 / 14 | 0 / 0 | 0 | ∅ | ∅ |
| p26-2 | 1 | 14 / 14 | 0 / 0 | 0 | ∅ | ∅ |
| p26-3 | 1 | 14 / 14 | 0 / 0 | 0 | ∅ | ∅ |
| p28-1 | 3 | 14 / 14 | 0 / 0 | 0 | ∅ | ∅ |
| p28-2 | 3 | 14 / 14 | 0 / 0 | 0 | ∅ | ∅ |
| p28-3 | 3 | 14 / 14 | 0 / 0 | 0 | ∅ | ∅ |

- 여섯 run 모두 Evidence 28건이 스키마 통과, Unexpected 0, 중복 키 0, request 동일성(method·path·query·헤더 5개·bodyHash) 14/14, k6 status == legacy response.status 14/14
- 세 run의 diff 집합 동일: p26 PASS, p28 PASS
- 매 run의 R000001 = 201(S0 리셋 확인), R000013 = 404, R000014 = 409, R000003 transactionId = `tx-idem-R000003`(양쪽)

### (b) 완료·도착 시각 차이 (new − legacy, ms)

| run | completedAt min / median / max | arrivedAt min / median / max | n |
|---|---|---|---|
| p26-1 | −8.7 / 0.3 / 2.4 | −0.9 / 0.0 / 0.2 | 14 |
| p26-2 | −1.2 / 0.6 / 1.9 | −0.2 / 0.0 / 0.6 | 14 |
| p26-3 | −1.2 / 0.1 / 1.3 | −0.1 / 0.0 / 0.1 | 14 |
| p28-1 | 1.7 / 11.1 / 94.2 | −0.8 / 0.4 / 1.7 | 14 |
| p28-2 | −0.9 / 1.9 / 6.4 | −0.2 / 0.3 / 1.4 | 14 |
| p28-3 | −0.5 / 3.1 / 8.2 | 0.0 / 0.3 / 1.1 | 14 |

- 같은 kind 노드라 pod 간 시계 차이는 무시한다
- **해석**: Envoy가 route(legacy)와 mirror(new)를 동시에 내보낸다(병렬 실행). 도착 시각 차이는 1ms 안팎이고 음수(new가 먼저)도 나온다
- **표현 주의**: 미러가 뒤따라오는 "지연"이 아니라 **완료 시각 차이**다. VU=3에서 차이가 커진 것(p28-1 최대 94.2ms)은 동시 요청 처리의 영향으로 보며, 판정에는 영향이 없었다

### (c) Evidence 레이어의 요청 경로 영향 (참고 — 같은 GET 각 30건, 헤더 없는 워밍업 5회 후)

| 측정 | Store 상태 | status | avg | p50 | p95 | max |
|---|---|---|---|---|---|---|
| 2.4a (실패 시 로그만) | 정상 | 200×30 | 9.6ms | 9.2ms | 12.3ms | 17.1ms |
| 2.4a | 내림(replicas=0) | 200×30 | 10.3ms | 9.0ms | 16.0ms | 29.7ms |
| 2.4a | 복구 직후 | 200×30 | 8.3ms | 7.8ms | 9.4ms | 15.6ms |
| 2.4b (재시도·spill) | 정상 | 200×30 | 14.9ms | 10.9ms | 31.0ms | 57.1ms |
| 2.4b | 내림(replicas=0) | 200×29 | 15.5ms | 13.1ms | 25.4ms | 28.5ms |

- Store 상태와 무관하게 응답은 모두 정상이고 같은 측정 안에서 Store 정상/내림의 차이는 작다. 2.4b가 2.4a보다 높은 것은 측정 직전 pod 재시작(워밍업)으로 본다
- 2.4b 내림의 n=29는 같은 30건 중 POST 1건을 GET 비교에서 뺀 것(200 아닌 응답 없음)
- 2.4a의 "복구 직후" 측정에서 Evidence 2건이 유실됐다(Store rollout Ready 후 Envoy endpoint 반영 전 503). 2.4b 재시도·spill과 2.6 preflight의 Store 준비 확인이 이 실측에서 나왔다

### (d) run 소요 (run-meta·run.sh 로그 기준)

| 구간 | 값 |
|---|---|
| reset (MySQL rollout restart 양쪽 → order readiness → WireMock journal 비움) | 12~17s |
| k6 iteration | VU=1: 0.33~0.38s / VU=3: 0.19~0.74s (VU별 iteration) |
| run 1회 전체(startedAt → finishedAt, preflight 제외) | 14~19s |

### (e) 전송 신뢰성 (2.4b)

| 시험 | 결과 |
|---|---|
| Store 내림 상태에서 30건 | 재시도 3회(0.5/1/1.5s) 후 spill 60개(legacy 30, new 30), 모두 스키마 통과 → `spill-recover.sh`로 회수 60/60, Store count 30/30, 재실행 멱등 |
| Store rollout restart 구간에 0.2s 간격 30건 | 503 재시도 로그 10건/스택, spill 0, count 30/30 — 유실 0 |
| 요청 직후 order pod 종료(SIGTERM) | graceful shutdown 후 drain 중 spill 3건/스택 → 새 pod에서 보임(hostPath) → 회수 3/3 |
| Store 정상 30건 | spill 0, 재시도 0 |
| sidecar 종료 순서 때문에 실패한 건 | 0 (istio-proxy는 native sidecar라 앱 sender보다 늦게 종료) |

### (f) 격리

- 스택 간 DB 격리: [isolation-proof.md "스택 간 DB 격리"](isolation-proof.md) — 처음 legacy → mysql.new가 열려 있었고, `base/mysql-networkpolicy.yaml`(mysql ingress ← 같은 ns의 `app=order` 3306만)로 막은 뒤 교차 스택 세 경우 모두 차단, 대조군 성공
- spill 디렉터리도 스택별 hostPath(`/var/evidence/spill/legacy`·`/var/evidence/spill/new`)로 분리 — 두 스택 사이 공유 자원 없음

## 5. VU 결정

[decision-log D13](decision-log.md): **기본 VU=3, 진단용 VU=1.** VU=1·VU=3 모두 3회 diff ∅(p26-1..3, p28-1..3).
세션 독립 + New 완료 폴링으로 동시 재생이 안정적이라는 것이 핵심 설계 주장이므로 A/A 표준 조건을 VU=3으로 둔다.
Phase 3에서 diff가 나오면 같은 corpus를 VU=1로 재실행해 동시성 잡음과 실제 차이를 분리한다.
현재 corpus(세션 3개, 세션 간 상태 공유 없음) 조건에서의 결과이며 일반화하지 않는다.

## 6. A/A 잡음 목록

**발견된 잡음: 0건** (p26·p28 여섯 run, response·dbAccess 모두 diff ∅)

**설계로 선제 차단한 잡음** — 0건은 우연이 아니라 아래 결정의 결과다. 각 항목은 그대로 두었다면 A/A에서 거짓 diff를 만들었을 원인이다.

| 잡음 원인 | 차단 방법 | 단계 |
|---|---|---|
| `Map.of` 순회 순서가 JVM마다 달라 dbAccess 직렬화 바이트가 갈림 | `LinkedHashMap`으로 순서 고정 (실제로 첫 배포에서 legacy `sql,seq` / new `seq,sql`로 갈린 것을 보고 고침) | 2.4a |
| Hibernate alias 번호(`o1_0`) | 엔진에서만 정규화 `[a-z]+\d+_\d+` → `_a_` (앱은 원문 기록) | 2.8 |
| DB auto id | 비교에서 키 `id` 제외 (엔진) | 2.8 |
| 실행 시각(`createdAt`) | `APP_FIXED_CLOCK` 양쪽 동일 → 비교 유지 | 1.3a |
| 결제 `transactionId` | WireMock이 Idempotency-Key에서 결정론적 생성(`tx-{Idempotency-Key}`) → 비교 유지 | 2.1 |
| open-in-view 지연 SELECT | `spring.jpa.open-in-view: false` (버퍼는 `chain.doFilter()` 반환 뒤 닫음) | Phase 2 이전부터 |
| JDBC 배치로 inspector 호출 수와 문장 수 불일치 | `hibernate.jdbc.batch_size` 미설정 | 2.4a |
| `x-request-id`·`Host`(실행 시점 값) | `EVIDENCE_HEADERS`에서 제외 (로그용 `REQUEST_LOG_HEADERS`와 분리) | 2.4a |
| Spring 기본 에러 본문의 timestamp | 컨트롤러가 고정 에러 본문 반환 | 2.1 |
| 응답 body key 순서 | 엔진에서 key 정렬 후 canonical 비교(배열 순서는 유지) | 2.8 |

**탐지 경로 확인**: 잡음이 0이라 diff_v0의 탐지 경로는 변조 시험으로 확인했다(p28-1 사본).
- 음성: new R000001의 응답 `amount` 변경 → `response:R000001`, exit 1 / dbAccess 문장 1개 삭제 → `dbAccess:R000001`, exit 1
- 양성: new R000001의 응답 body 키 순서를 모든 깊이에서 뒤집고 sql alias 번호 변경 → diff ∅, exit 0 (정규화가 잡음을 흡수)
- verify_sameness: p26bf-1(2.6 barrier 실패 run)에서 Undelivered new 2건(R000005, R000009)을 짚고 exit 1. 사본 변조(bodyHash·헤더 변경, dbAccess 삭제)도 해당 requestId·필드로 FAIL

## 7. 한계

- **예외 경로 Evidence 없음**: `chain.doFilter` 예외 시 Evidence를 남기지 않는다 → degraded·Undelivered로만 드러남 (Phase 3 `error` 필드)
- **Store는 emptyDir**: export 전에 Store pod가 재생성되면 그 run의 Evidence가 사라진다. run마다 즉시 export로 회수한다
- **spill hostPath는 kind 전용**: 노드 1개 전제. 운영이면 PVC
- **k6 helper metric**: VU 간 상태 공유가 없어 요청 id별 metric으로 수집한다. 요청이 수백 건이 되면 `--out json` + 태그 기반으로 전환이 필요하다
- **요청 스레드만 캡처**: `@Async`·Kafka consumer 스레드의 DB 접근은 dbAccess에 없다 (Phase 3)
- **callTree 미구현**: v0에서는 `null`
- **dbAccess 비교는 v0 정규화뿐**: 소문자·공백·alias. 파생(종류·횟수·테이블)과 판정 규칙은 Phase 3 Normalization
- **표본과 환경**: 단일 노드 kind, corpus 세션 3개·요청 14건, A/A 각 3회. 이 조건에서의 안정성 확인이며 일반화하지 않는다. 응답 시간 표는 n=30 참고값
- **인증서 만료는 감지만**: run.sh preflight가 만료를 감지해 중단할 뿐 자동 복구는 없다(복구 절차: phase2-plan 2.6). 호스트 sleep 후 갱신 누락으로 메시 전체가 503이 된 실측이 있다(isolation-proof "관찰")

## 8. Phase 3 입력 계약

```
runs/<runId>/
  legacy.json      Store export (stack=legacy) — Evidence JSON v0 배열, (replayRequestId, stack) 순
  new.json         Store export (stack=new)
  k6-summary.json  runId, corpusVersion, vus, sent[], degraded[{session, skipped[]}], status{id: code}, newWaitMs{id: ms}, newWaitMsNote, k6 기본 지표
  run-meta.json    corpus 버전·sha256, 이미지 imageRef(order legacy/new·evidence-store·wiremock), APP_FIXED_CLOCK, vus, git rev·dirty, k6·istio 버전, 시작·종료 시각
```

- "보낸 것"의 기준은 `k6-summary.json`의 `sent`. 입력 계약 검사(스키마 + runId·stack 일치)는 `engine/common.py`
- **엔진 개발은 이 파일만으로, 클러스터 없이 진행한다.** 기준 데이터: `runs/p26-1..3`(VU=1), `runs/p28-1..3`(VU=3)

**Phase 3 진입 시 꺼낼 항목** (출처: [references/kakaopay-aop-shadow.md](references/kakaopay-aop-shadow.md), phase2-plan Phase 3 메모)
- callTree 해상도 결정 — Spring 빈 경계(프록시 AOP는 self-invocation을 못 잡음)
- `dbAccess.txOutcome` 후보 — 커밋/롤백 결과(`TransactionSynchronization.afterCompletion`)
- fault catalog "커밋 전 publish"(롤백 시 유령 이벤트 — 응답으로는 안 보이고 이벤트 Evidence로만 잡힘)
- Kafka 헤더 전파·`RecordInterceptor`(ReplayContext를 consumer 스레드로)
- 외부 호출 Evidence 2층 — 클라이언트 인터셉터 + WireMock request journal
- Coupon MySQL NetworkPolicy(`app=coupon`, `base/mysql-networkpolicy.yaml`과 같은 형태)
- 단계마다 A/A 3회 diff ∅ 게이트(기본 VU=3, D13)

## 9. 팀 공유 규약 — Coupon에 적용할 것

- **수집기 재사용**: 패키지 `poc.evidence`를 그대로 넣고 `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`로 등록한다. 비즈니스 코드(컨트롤러·서비스·리포지토리)는 수정하지 않는다
- **헤더**: `EVIDENCE_HEADERS` = `X-Replay-Request-Id,X-Run-Id,X-Session-Id,Idempotency-Key,Content-Type`. 재생 헤더 3개가 없는 요청은 Evidence를 남기지 않는다(로그 한 줄)
- **env**: `EVIDENCE_STORE_URL`, `EVIDENCE_STACK`(legacy/new), `EVIDENCE_SERVICE`(coupon), `EVIDENCE_VERSION`, `EVIDENCE_HEADERS`, `EVIDENCE_SPILL_DIR`(기본 `/var/evidence/spill`, 스택별 hostPath), `OTEL_INSTRUMENTATION_JAVA_HTTP_CLIENT_ENABLED=false`. `EVIDENCE_DELAY_MS`는 검증용이라 설정하지 않는다
- **DB**: Coupon은 Coupon DB만 쓴다. 스키마 소유자는 init SQL, `ddl-auto: none`. `hibernate.jdbc.batch_size` 미설정, `spring.jpa.open-in-view: false`, DB 접근은 JPA 경로만(`JdbcTemplate`·native batch 금지)
- **결정성**: `APP_FIXED_CLOCK` 양쪽 동일. 응답(에러 본문 포함)에 실행 시점 값을 넣지 않는다
- **메시**: 검증 대상 서비스 pod는 sidecar 주입 필수(MySQL server-first + PERMISSIVE mTLS 제약). Service 포트명은 `http-`/`grpc-` 접두사
- **종료**: `server.shutdown: graceful`, `spring.lifecycle.timeout-per-shutdown-phase: 20s`, `terminationGracePeriodSeconds: 30`
