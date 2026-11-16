# Prince Mart Legacy 베이스라인(A/A) 테스트 결과

실행: 2026-10-12, run `aa-001-1` ~ `aa-001-3` (branch-park `991d039`). 실패 경로 실측: 2026-11-02, run `fault-f1`, `fault-f2`, `recover-001`
설계 근거: [legacy-decision-log.md](legacy-decision-log.md) (L1~L12), Evidence 형식: [legacy-evidence-schema-v0.md](legacy-evidence-schema-v0.md),
Legacy 코드 변경 내역: [`legacy/prince-mart/LEGACY_CHANGES.md`](../legacy/prince-mart/LEGACY_CHANGES.md)

## 1. 목적

같은 Legacy를 두 벌(legacy, new) 띄우고 같은 트래픽을 미러링했을 때 **정규화 후 차이가 0인지** 확인한다.
0이면 이후 New와의 비교에서 나오는 차이를 "환경 노이즈"가 아니라 "행동 차이"로 볼 수 있다. 비교 파이프라인의 영점 확인이다.

## 2. 구성

| 항목 | 내용 |
|---|---|
| 시스템 | Prince Mart order / coupon / payment (Boot 4.0.3 / 4.0.5 / 3.4.2). 두 스택 모두 같은 Legacy 이미지 |
| 스택 | 스택마다 서비스 3개 + MySQL 8.4 3개 + Kafka 1개 + WireMock 1개. new는 외부 차단 네트워크(`internal`) |
| 전달 | nginx: `/orders`·`/coupons`·`/payments`를 legacy로 route, new로 mirror. 헤더는 복사만, Host는 원본 유지(D8) |
| 통제 | 고정 시각 2026-09-01T00:00:00Z, S0 초기화(앱 정지 → MySQL·Kafka 재생성 → 앱 시작), 외부 의존성 WireMock, 결제는 가짜 PG |
| 요청 ID 전파 | OTel Java agent 2.31.1이 Feign·Kafka 헤더로 `baggage`(replayRequestId, runId, sessionId) 전파. 코드 변경 없음 |
| Evidence | 서비스 내부 필터: 응답, DB 접근(동작·테이블·횟수), Feign 호출 순서, 발행 이벤트, 예외 class, 처리 시간. 앱 밖 수집: WireMock 외부 호출, Kafka 이벤트 |
| 입력 | `baseline/corpus/corpus-v1.json`: 독립 세션 11개(세션마다 다른 사용자·전용 쿠폰), 요청 28건. 정상·에러·B1~B6 포함 |
| 실행 | k6 v2.3.0, VU=1, 세션 순서대로. 요청마다 legacy·new 두 스택의 Evidence가 기대 건수에 도달할 때까지 대기(Kafka consumer 처리 포함) |
| 반복 | 같은 조건 3회 |

비교 유효 조건 해시 = hash(corpus, S0 init SQL·토픽, WireMock 매핑, 고정 시각, 이미지 ID, 정규화 규칙)
= `48f8fd307495eb97e580986b864012734dc1e64851fc62d5cca9fc63ef5ce5c4` (3회 동일)

## 3. 결과

| 항목 | run 1 | run 2 | run 3 |
|---|---|---|---|
| 요청 전송 / degraded 세션 | 28/28 / 0 | 28/28 / 0 | 28/28 / 0 |
| Evidence(스택당) | 89 | 89 | 89 |
| flush barrier 누락 / consumer lag | 0 / 0 | 0 / 0 | 0 / 0 |
| Undelivered | 0 | 0 | 0 |
| 짝 맞춤(HTTP 62건 × method·path·query·헤더·bodyHash) | 전건 PASS | 전건 PASS | 전건 PASS |
| **B0** (exact diff) | 978 | 963 | 931 |
| └ trace 헤더 | 544 | 544 | 544 |
| └ 시각(도착·완료·nano·capturedAt) | 344 | 339 | 329 |
| └ 호출 소요 시간 | 90 | 80 | 58 |
| └ 그 밖 | **0** | **0** | **0** |
| **B1** (정규화 후 diff) | **0** | **0** | **0** |
| DB 테이블 7개(행 수·숫자 합·행 해시) | 전부 일치 | 전부 일치 | 전부 일치 |
| 서비스별 처리 순서(seq) | 일치 | 일치 | 일치 |

스택당 Evidence 89건 = HTTP 62 + Kafka consumer 처리 3 + 외부 호출 묶음 21(호출 127건) + 이벤트 3.

### 반복 간 일치

- B1 diff 집합: 3회 모두 공집합으로 동일.
- B0 diff 집합: **시각·소요 시간을 빼면 3회가 완전히 같다**(trace 헤더 544건은 위치까지 동일).
  시각·소요 시간 건수가 흔들리는 이유는 양쪽 값이 같은 ms로 찍히면 우연히 diff에서 빠지기 때문이다(run 3에서 소요 시간이 같은 쌍 90건).
  이 둘은 판정에 쓰지 않는 참고 지표다.
- 환경 drift: run 1의 Legacy Evidence(정규화 후)와 DB를 run 2·3과 비교 → **차이 0**.

### nginx mirror 순서

서비스마다 seq 순서로 정렬한 (요청 ID, 종류)가 legacy·new에서 같았다(order 34, coupon 15, payment 16).
**VU=1 + 요청마다 완료 대기** 조건에서의 결과다.

### B1~B6 재현 (3회 × 2스택 모두 재현)

| 버그 | 관측 |
|---|---|
| B1 쿠폰 사용 기록 누락 | 같은 쿠폰 2회 모두 95,000원, 한도 1회 쿠폰도 2회 모두 97,000원. `coupon_usage`는 B2의 1건뿐. coupon `/use` 404가 6건, 모두 `ResourceNotFoundException` |
| B2 취소 주문 쿠폰 사용 | 200, 기록됨 |
| B3 무효 쿠폰 | 만료·최소 금액 미달 모두 정가 100,000원, 200 |
| B4 취소 후 결제 확정 | CONFIRMED/PAID |
| B5 결제 후 취소 | CANCELLED/PAID |
| B6 예외 매핑 | 재취소 404 `IllegalStateException`, 남의 주문 조회 404 `ResourceNotFoundException` |

### 처리 시간 (참고, 판정 대상 아님)

| | legacy HTTP 평균 / 중앙값 / 최대 | new HTTP 평균 / 중앙값 / 최대 | consumer 평균 legacy / new |
|---|---|---|---|
| run 1 | 78.8 / 12.8 / 1074 ms | 78.8 / 13.2 / 1064 ms | 40.6 / 41.7 ms |
| run 2 | 82.9 / 15.9 / 1035 ms | 82.2 / 14.0 / 1047 ms | 40.0 / 44.4 ms |
| run 3 | 72.1 / 11.3 / 1115 ms | 72.4 / 11.7 / 1126 ms | 34.9 / 36.6 ms |

요청마다 완료 대기 최대 164ms, run당 합계 약 1.7초. run 1회 소요: 초기화 50~55초, k6 약 6초.

## 4. 정규화 규칙 (`baseline/engine/normalization.json`, norm-v1.1)

| 규칙 | 이유 | A/A 적용 |
|---|---|---|
| `stack` 제외 | 비교 키이지 비교 대상이 아님 | 적용 |
| 위치 값 `seq`·`message.offset` 제외, 짝 맞춤은 요청 안 순서로 | 앞쪽 Evidence가 하나 빠지거나 더해지면 뒤가 모두 밀린다. 실행 순서는 서비스별 처리 순서 검사가 따로 본다. **v1.1에서 추가**(8장) | 적용 |
| 시각·소요 시간 무시 | 실측값, 판정 기준 아님 | 적용 |
| trace 헤더 제거(`traceparent`, `b3`, `X-B3-*`) | OTel trace id는 스택마다 다름 | 적용 |
| JSON 본문 키 정렬·숫자 값 비교 | Boot 4(Jackson 3)는 키를 알파벳순으로 직렬화(L7), 금액 표기 `100000`/`95000.00` 차이(L6) | 적용(A/A에서는 차이 없음) |
| 자동 증가 ID 마스킹 | New에서 ID가 밀릴 수 있음 | **끔**. A/A에서는 ID가 같아야 하고, 켜면 결정성 깨짐을 숨김 |
| Host | Istio 1.31은 미러 Host를 바꾸지 않음(D8) | 규칙 없음 |
| `baggage` | replayRequestId·runId·sessionId만 담겨 양쪽 같음 | 규칙 없음 |

aa-001 3회는 v1.1로 다시 비교해도 결과가 같다(B1 0, B0 건수 동일, drift 0). 3장의 조건 해시는 run 당시 기록값(v1)이다.

## 5. 진행 중 발견하고 고친 결정성 문제

1. **Kafka 재생성 후 consumer rebalance**: 앱 재시작 없이 브로커만 새로 만들면 consumer가 붙은 뒤 토픽 ID 변경을 감지해
   한두 번 더 재할당된다. 이 과도기와 요청이 겹쳐 시나리오 1회가 24/26으로 흔들렸다 → 초기화에 앱 재시작 추가(L3).
2. **옛 consumer의 그룹 잔류**: "Kafka 재생성 → 앱 재시작" 순서에서는 재시작 전 앱의 consumer가 새 브로커 그룹에 먼저 들어간 뒤
   깔끔하게 빠지지 못해 새 consumer가 22초간 합류하지 못했다. 그 사이 결제 확정 후속 처리가 3초 늦어져 조회·취소가 먼저 처리됐다
   → 순서를 "앱 정지 → 재생성 → 앱 시작"으로, 판정을 "그룹 Stable + 멤버 1 + 파티션 할당"으로(L3).
3. **완료 대기 기준**: new 도착만 보면 legacy 쪽 Kafka 처리 전에 다음 요청이 갈 수 있다
   → 양쪽 스택의 요청별 기대 Evidence 건수(consumer 처리 포함)를 기다린다(L12).

## 6. 쿠폰 DB 격리

- **구성상 근거**: 스택마다 coupon DB(MySQL 컨테이너)가 따로 있고 new는 외부 차단 네트워크다. 세션마다 전용 쿠폰을 써서 세션 사이에도
  공유 상태가 없다(쿠폰 사용 한도 판정은 쿠폰 전체 사용 수를 세므로 쿠폰을 공유하면 세션이 서로 영향을 준다).
- **측정 근거**: A/A 3회에서 사용 한도 1회 쿠폰(S07) 시나리오를 포함해 `coupon.coupons`·`coupon.coupon_usage` 테이블 diff 0.
- **확인 필요**: 교수님 코멘트의 "격리"가 스택 간 DB 분리를 뜻하는지, 트랜잭션 격리 수준을 뜻하는지 여쭤본다.
  트랜잭션 격리 수준(MySQL 기본 REPEATABLE READ)은 바꾸지 않았고, VU=1이라 동시 트랜잭션 경합은 검증 범위 밖이다(v10.1 §0).

## 7. 남은 이슈

- **늦은 도착(late delivery) 미검증**: 실패 경로 실측(8장)은 "끝까지 오지 않는" 장애만 걸었다. 완료 대기 타임아웃 뒤에 늦게 도착하는
  Evidence(예: 브로커가 잠깐 멈췄다 돌아오는 경우)를 엔진이 어떻게 다루는지는 보지 않았다.
- **범위 한정**: 순서 보존·결정성은 VU=1 + 요청마다 완료 대기 조건의 결과다. Prince Mart에는 business key가 없어 VU=N은 하지 않았다(L1).
- **New 비교에서 처음 켜질 규칙**: ID 마스킹·키 순서·금액 표기 규칙은 A/A에서 차이가 없어 실효성을 검증하지 못했다.
  New(예: Payment Boot 4 업그레이드)에서 처음 확인된다.
- **corpus 범위**: 28건. `/orders/history`의 시각 동점 정렬(L5)은 사용자당 주문이 1건이라 드러나지 않는다.
  없는 주문 verify(consumer 실패) 경로도 corpus에 없다.
- **팀 합의 필요**
  - 실험 대상: 팀원 Phase 2는 자기 order 앱 + business key. 팀원 Phase 3(coupon·payment·Kafka)가 이 트랙과 겹친다
  - Evidence Store 저장소: 이 트랙은 SQLite, 팀원 계획은 파일. API는 맞춰 두었다(L11)
  - Store POST span 처리: 이 트랙은 별도 trace로 분리(L10), 팀원은 JDK HttpClient 계측 끄기

## 8. 실패 경로 실측

3장은 "잘 될 때 diff 0"만 보여 준다. 파이프라인이 "잘못되면 잡아낸다"는 것을 보이려고, corpus·시스템 코드·run script를 바꾸지 않고
장애만 걸었다(`baseline/k6/fault.py`: run.py 출력에서 리셋이 끝나고 k6가 시작되는 순간 장애를 걸고, 풀지 않는다).

| 실험 | 장애 | 결과 |
|---|---|---|
| **F1** new consumer 처리 불가 | new Kafka 브로커를 스택 네트워크에서 끊음 | 아래 |
| **F2** new order 서비스 중단 | `order-new` 정지 | 아래 |
| **R** 복구 | 장애를 풀지 않은 채 일반 run | 리셋만으로 S0 복구 |

### F1 — new Kafka 단절 (`fault-f1`)

- **k6**: verify 3건(R000002·R000020·R000023)에서 new consume Evidence가 오지 않아 10초 뒤 타임아웃 →
  S01·S09·S10을 degraded로 표시하고 남은 요청 6건을 건너뜀(22/28 전송). Kafka를 쓰지 않는 나머지 8세션은 정상.
- **flush barrier**: 실패 판정, 누락 3건 정확히 보고(new 1/2). new 외부 호출 113건 = legacy 125건 − consumer 몫 4건 × 3.
- **엔진**: Undelivered 9(consume 3, event 3, external 3), Unexpected 0, 짝 맞춤 HTTP 56/56.
  B1 84 = verify 3건의 payment Evidence 28 × 3(new 응답 404, `IllegalStateException: PaymentCompleted publish failed`, 이벤트 없음, DB 접근 차이).
  테이블 orders·payments·이력 불일치, order 처리 순서 불일치.
  **클라이언트는 legacy 응답만 받아 status가 모두 정상이었는데, Evidence 비교가 new의 숨은 실패를 드러냈다.**

### F2 — new order 서비스 중단 (`fault-f2`)

- 리셋: F1 장애(Kafka 단절)가 남은 상태에서 정상 완료(51.6초).
- **k6**: 9세션이 첫 요청에서 타임아웃 → degraded, 남은 요청 건너뜀(16/28 전송). S01·S02는 `order-new`가 내려가기 전(정지에 몇 초)에 처리됨.
- **flush barrier**: 실패 판정, 누락 9건 보고(new 18 / 기대 46).
- **엔진**: Undelivered 36(order 12, coupon 7, payment 9, external 8), Unexpected 0, 도달한 HTTP 17건 짝 맞춤 PASS.
  테이블 4개·세 서비스 처리 순서 불일치. B1은 R000008의 외부 호출에서만(내려가는 도중 일부만 처리된 요청).

### R — 복구 (`recover-001`)

- 리셋: F2 장애(`order-new` 정지)가 남은 상태에서 정상 완료(50.7초).
- 28/28, 누락 0, Undelivered 0, 짝 맞춤 62/62, B1 0, 테이블 7개·순서 일치, B1~B6 재현.
- aa-001-1과 비교: 조건 해시 5개(corpus·S0·WireMock·고정 시각·이미지) 동일(정규화만 v1.1), B1 집합·시각 제외 B0 집합 동일,
  **Legacy Evidence·DB drift 0**. 장애 두 번 뒤에도 리셋만으로 같은 상태로 돌아온다.

### 실측에서 고친 것: 짝 맞춤 키 (norm-v1.1)

F1 첫 비교에서 엔진이 Undelivered 27 / Unexpected 18로 **과다 보고**했다(실제 누락 9).
짝 맞춤 키에 서비스 단위 순번(`seq`)을 넣었기 때문이다. new에서 consume 1건이 빠지자 그 뒤 order Evidence의 순번이 모두 밀려
같은 요청인데도 짝을 못 짓거나 다른 Evidence끼리 짝지어졌다(R000006의 "주문 생성"과 "B1 역조회"를 비교한 가짜 차이 22건).
New 비교에서도 New가 내부 호출을 하나만 더하거나 빼면 이후 전체가 차이로 쏟아져 진짜 차이가 묻힌다.
→ 짝 맞춤 키를 `(replayRequestId, service, kind, 그 요청 안에서 몇 번째)`로 바꾸고, `seq`·Kafka `offset`을 요청 단위 비교에서 뺐다(norm-v1.1).
수정 뒤 F1 보고가 실제 누락과 정확히 일치했고, aa-001 결과는 그대로다.

## 9. k8s + Istio로 합칠 때 바꿀 목록

| 지금 (Compose) | k8s / Istio |
|---|---|
| nginx `default.conf` (경로별 route + mirror, Host 유지) | Gateway + VirtualService: `/orders`·`/coupons`·`/payments` 각각 route legacy, mirror new. Host 기본값 유지(D8) |
| 스택 = compose 네트워크, 스택 안은 짧은 이름 | 네임스페이스 `legacy` / `new`, Service 이름 |
| new 네트워크 `internal: true` | NetworkPolicy default-deny egress(팀원 파일 그대로). Kafka가 각 ns 안에 있어 정책 수정 불필요 |
| `reset.sh`: 앱 정지 → MySQL·Kafka 재생성 → 앱 시작 → consumer group 확인 | 앱 scale 0 → `rollout restart` mysql-*·kafka(Recreate, emptyDir) → 앱 scale 1 → readiness + `kubectl exec`로 group 확인 |
| MySQL tmpfs + init SQL 디렉터리 | emptyDir + ConfigMap(configMapGenerator) → `/docker-entrypoint-initdb.d` |
| Kafka tmpfs + `init-topics.sh` | emptyDir + ConfigMap 스크립트, readiness = 토픽 존재. Service 포트 이름 `tcp-kafka`(Istio 프로토콜 판별) |
| `otel-agent-init` 서비스 + 공유 볼륨 | initContainer + emptyDir(팀원 D5와 같은 이미지·digest) |
| OTel Collector·Jaeger (compose) | `observability` ns의 팀원 구성 그대로. 앱 env 동일 |
| Evidence Store (compose, 호스트 8099) | `verify` ns Deployment + Service(포트 이름 `http-evidence`). k6는 Gateway `/_evidence` 라우트(미러 없음)로 접근 |
| k6를 compose legacy 네트워크에서 실행 | 호스트에서 `http://localhost`(Ingress). `BASE_URL`·`STORE_URL` env만 변경 |
| `collect.py`의 `docker compose exec` | `kubectl exec`(WireMock journal, Kafka 콘솔 consumer) |
| WireMock 매핑 디렉터리 | 두 ns 공통 ConfigMap(팀원이 WireMock을 base로 옮김) |
| 앱 이미지 로컬 빌드 | 멀티아치 절차(`docker save --platform` → `kind load image-archive`) |
| Store POST 별도 trace | Envoy span도 그 별도 trace에 붙는다. 분석은 replayRequestId·목적지(`evidence-store`)로 거른다 |
| 메모리: 두 스택 + 관측 약 6.3GB | kind 노드에 sidecar까지 더해 여유 확보 필요 |

## 10. 재현 방법

```bash
docker compose -f deploy/compose/docker-compose.yml up -d --build --wait
python3 baseline/k6/run.py --run-id aa-001 --iterations 3          # 결과: baseline/runs/aa-001-{1,2,3}/
for i in 1 2 3; do python3 baseline/engine/compare.py baseline/runs/aa-001-$i; done
python3 baseline/engine/iterations.py baseline/runs/aa-001-{1,2,3}
python3 baseline/engine/bcases.py baseline/runs/aa-001-1 --stack legacy

# 실패 경로(장애는 풀지 않는다 -> 다음 run의 리셋이 복구)
python3 baseline/k6/fault.py --run-id fault-f1 --fault kafka-new-disconnect
python3 baseline/k6/fault.py --run-id fault-f2 --fault order-new-stop
python3 baseline/k6/run.py --run-id recover-001
```

## 11. 산출물 위치

| 경로 | 내용 |
|---|---|
| `legacy/prince-mart/` | Legacy 코드, `LEGACY_CHANGES.md`, 계측 원본 `evidence/` |
| `deploy/compose/` | 실행 환경, `reset.sh`, nginx, OTel, 수집 도구(`tools/collect.py`), 개발용 `tools/scenarios.py` |
| `baseline/` | corpus, k6·run script·장애 주입(`k6/fault.py`), Evidence Store, 비교 엔진. 결과 `baseline/runs/`는 커밋하지 않음 |
| `docs/legacy-decision-log.md` | 결정 기록 L1~L12 |
| `docs/legacy-evidence-schema-v0.md` | Evidence 스키마 |
