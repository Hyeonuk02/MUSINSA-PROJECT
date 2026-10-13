# CLAUDE.md

전체 프로젝트 설계는 docs/architecture.md 를 기준으로 한다.
Phase 1은 완료됐다 (tag phase1-done, docs/phase1-result.md). Phase 2도 완료됐다 (docs/phase2-result.md).

## 프로젝트 방향

Legacy → New 시스템 교체 시 동일 트래픽을 Istio Shadow Mirroring으로
양쪽에 전달하고, 실행 Evidence를 비교하여 변경 전후 행동 차이를 찾는다.

전체 흐름:
Git Diff → Call Graph → 영향 API → k6 → Istio Mirroring → Legacy / New → Evidence → Verification Engine → Human Review

목표는 사람이 직접 검토해야 하는 범위를 줄이는 것이다.

## Phase 2 — 단일 파이프라인 end-to-end: 완료 (2026-10-12)

결과: docs/phase2-result.md. 계획: docs/phase2-plan.md. A/A(VU=1 ×3, VU=3 ×3) diff ∅.
종료 시점의 Evidence JSON(runs/<runId>/{legacy,new,k6-summary,run-meta}.json)이 Phase 3 엔진의 입력 계약이다.

| 단계 | 내용 | 상태 |
|---|---|---|
| 2.1 | business key Order API + WireMock 결제 스텁 양쪽 | 완료 |
| 2.2 | corpus v1 (세션 3·요청 14·에러 경로 2) + schema·validate.py | 완료 |
| 2.3 전 | 스택 간 DB 네트워크 격리 실측 + mysql ingress NetworkPolicy | 완료 |
| 2.3 | Evidence Store v0 + Evidence JSON v0, 게이트웨이 표면 /api/·/_evidence/ | 완료 |
| 2.4a | ReplayContext, EvidenceFilter, StatementInspector (poc.evidence) | 완료 |
| 2.4b | 전송 큐 유실 금지(재시도·spill), graceful shutdown, spill-recover | 완료 |
| 2.5 | k6 corpus 재생 + New 완료 폴링 | 완료 |
| 2.6 | run.sh — preflight·reset·barrier·export | 완료 |
| 2.7 | verify_sameness — pairing·request 동일성 | 완료 |
| 2.8 | diff_v0 + A/A run VU=3 | 완료 |

## Phase 3 — 완료 (2026-10-14, tag phase3-done)

결과: docs/phase3-result.md. 지표: docs/phase3-metrics.md. 발견: docs/findings.md.

계획: docs/phase3-plan.md (v2.1). 단계별 세부 작업과 끝난 기준은 그 문서가 기준이다.
목표: New ≠ Legacy — MSA 확장(Order·Coupon·Payment(WireMock)·Kafka) + Order 점진 Kotlin 전환 사다리 + 결함 카탈로그 + 판정 엔진(4분류·Rule).

| 단계 | 내용 | 상태 |
|---|---|---|
| 3.0 | 사전 점검 — 버전·자원·ObjectMapper, Phase 2 잔여 | 완료(결정 대기 2건: 스택 전제·메모리) — docs/reports/phase3.0.md |
| 3.1 | Evidence v1 — 타임라인·callTree·외부 호출·트랜잭션·error·최종 DB 상태 | 완료 — docs/reports/phase3.1.md |
| 3.2 | Coupon 서비스 + Store v1 키 + corpus v2 | 완료 — docs/reports/phase3.2.md |
| 3.3 | Kafka — 이벤트 축 | 완료 — docs/reports/phase3.3.md (Legacy 고정 이미지 order·coupon-app:phase3.3-base) |
| 3.4 | Normalization v1 + 판정 엔진 v1 + Rule + Human Review | 완료 — docs/reports/phase3.4.md (engine-v1, p33-1..3 전 pair SAME) |
| 3.5 | New v1 사다리 — Order 점진 Kotlin 전환 (v1.1~v1.4) | 완료 — docs/reports/phase3.5.md, docs/phase3-result.md (v1.1~v1.4 전 pair SAME, Order 전면 Kotlin = 3.6 기준선 order-app:phase3.5-v1.4) |
| 3.6 | 결함 카탈로그 v1 + New v2 | 완료 — docs/reports/phase3.6.md, docs/fault-catalog.md (9/9 기대 일치, 오탐 0·오판정 0, engine-v1.2) |
| 3.7 | 사다리 첫 측정 — B0 / B1 / C + 평가 지표 | 완료 — docs/reports/phase3.7.md, docs/phase3-metrics.md (탐지 9/9, eval UNC 31→6, 오판정 0/129) |
| 3.8 | (선택) New v3 — 런타임 교체 | 미실시 — Phase 4 이후 선택 |

### Phase 3 확정 사항 (요약 — 원문은 phase3-plan 3절)

- Evidence 키 = (runId, replayRequestId, stack, hopPath). service·origin(http|kafka)은 필드 (D15)
- hopPath: 진입 "0", 홉 안 n번째 HTTP 호출 "<부모>.h<n>", n번째 이벤트 소비 "<부모>.e<n>" — 종류별 순번. k6가 X-Replay-Hop-Path: 0, 전파 인터셉터·ProducerInterceptor가 자식 계산, RecordInterceptor가 consumer 스레드 컨텍스트. OTel Baggage 미사용. EVIDENCE_HEADERS에 X-Replay-Hop-Path 추가
- 타임라인: 요청 버퍼의 단일 seq 카운터(SQL·외부 호출·이벤트 발행·트랜잭션). 트랜잭션은 TransactionExecutionListener로 COMMIT_BEGIN / COMMITTED|ROLLED_BACK|COMMIT_FAILED. 이벤트 발행은 동기 send().get(), ack는 호출 스레드에서 기록. "커밋 전 발행" = publish.seq < COMMIT_BEGIN.seq (D16)
- Kafka: 스택별 1브로커·partition 1·재시도 0·DLQ, NetworkPolicy로 같은 ns만 (D19)
- 쿠폰 주문 순서 고정: 주문 INSERT → Coupon use → 커밋. 실패면 400 + 롤백. 보상 누락은 범위 밖. Coupon은 Phase 3 내내 Java 동일 코드
- 검증 레이어: poc.evidence는 Java 그대로 Coupon·Kotlin New에 수정 없이 부착. JSON은 패키지 안 고정 설정 private ObjectMapper(앱 빈 공유 금지). 자체 writer 금지
- Kotlin 전환(D17): FQCN·API 경로·응답 계약 유지, kotlin-spring·kotlin-jpa 필수, 엔티티 data class 금지, 결함은 v2에만, 단계마다 commit 1·이미지 1
- DB 계약 두 층(D18): 쓰기 집합·최종 상태·불변식 위반 = Contract Violation, 읽기 횟수·순서 = Uncertain(maxSelects 선언 시에만 CV)
- 판정 우선순위 CV > Uncertain > Improvement > SAME. Undelivered는 전달 지표
- 내부 Evidence 완료는 corpus settle 선언을 양쪽 스택에서 폴링, barrier는 corpus 기대 집합 + 도착 Evidence의 childHopPath 폐포 (D19)
- Rule은 learn 세션(split)과 v1.1~v1.2에서만 만들고 eval 세션·v1.3+·F 변형에서 잰다
- A/A 게이트(VU=3 ×3 diff ∅)는 3.1~3.4와 base 이미지, 3.5·3.6은 "모든 diff가 설명됨"

### Phase 3 하지 말 것

콜트리 합성·endpoint → class 맵·git diff 대조·Tag/Filter·B2 arm(Phase 4) / 정적 Call Graph / 운영 시연·mirrorPercentage / 오버헤드 측정 / LLM 보조 판정 / Store DB·인증·UI / @Async 스레드 전파(Kafka consumer 스레드만) / Coupon 코드 변경 / 결함을 v1 사다리에 섞는 것 / Outbox·Saga / 자체 JSON writer / 같은 데이터로 규칙을 만들고 같은 데이터로 평가하는 것

## 확정 사항 (Phase 1~2, Phase 3에도 유효 — Phase 3에서 바뀐 키는 위 요약이 우선)

- replayRequestId는 k6(corpus)가 부여, X-Replay-Request-Id. Envoy mirror가 헤더 복사
- business key(orderKey)는 corpus에서 결정론적 파생. 후속 요청은 orderKey로 대상 지정
- Evidence 키 (runId, replayRequestId, stack). Evidence POST는 비교·span 대상 아님
- Evidence 전송은 유실 금지: 큐 상한·재시도 소진 시 버리지 않고 로컬 spill, flush barrier가 회수
- DB Evidence는 StatementInspector가 SQL 원문만 기록. 앱에서 종류·횟수·테이블 계산이나 SQL 주석 삽입 금지. Hibernate JDBC 배치 off, DB 접근은 JPA 경로만(JdbcTemplate·native batch 금지)
- 완료 폴링: 요청마다 Store exists로 New 도착 확인 후 다음 요청
- flush barrier: Store count(+spill 회수분) == 기대 건수 확인 후 export·리셋
- Legacy/New 앱 코드 동일. 고정 시각 유지. S0 리셋 = MySQL rollout restart
- legacy/new의 검증 대상 서비스 pod(order, 이후 coupon)는 sidecar 주입 필수 (MySQL server-first + PERMISSIVE mTLS 제약, docs/isolation-proof.md "관찰"). probe/tooling/verify pod에는 적용하지 않음
- A/A 표준 조건은 VU=3, 진단용 VU=1 (decision-log D13). diff가 나오면 같은 corpus를 VU=1로 재실행해 동시성 잡음과 실제 차이를 분리
- Call Graph는 동적 수집·합성(D14). Phase 3에서 callTree 기록, Phase 4에서 합성·영향 API 선정
- Phase 1 교훈 적용: Service 포트명 접두사(http-/grpc-), 멀티아치 이미지 로드 절차, 런타임 다운로드 금지, new는 default-deny egress(verify 허용됨)

## 하지 말 것 (Phase 2 — 기록용, Phase 3는 위 "Phase 3 하지 말 것")

Phase 2에서는 다음을 구현하지 않는다.
Coupon/Payment 실서비스, Kafka, 이벤트·외부 호출 Evidence(DB Evidence는 원문 기록까지만 포함), @Async·Kafka consumer 스레드로의 ReplayContext 전파, Normalization·4분류·Rule·Human Review(2.8 스크립트의 최소 정규화 제외), Call Graph(callTree는 null 예약만), 결함 주입, 성능 테스트, Istio 추가 기능, Evidence Store DB·인증·UI.

## 작업 방식

- Phase 3는 3.0부터 순서대로 진행한다.
- DB Evidence는 StatementInspector로 SQL 원문만 기록한다. 앱에서 종류·횟수·테이블을 계산하거나 SQL 주석을 삽입하지 않는다(그건 Phase 3 엔진 또는 CDC 확장의 몫).
- 한 번에 한 단계만 진행한다.
- 구현 전에 이번 단계에서 무엇을 할지와 완료 기준을 먼저 설명한다.
- 내가 실행 결과를 확인한 뒤 다음 단계로 넘어간다.
- 오류는 현재 단계에서 해결한다.
- 중요한 설계 결정이 필요하면 임의로 정하지 말고 질문한다.
- 단계마다 "phase3.x: ..." 형식으로 커밋한다. 사다리·결함은 "phase3.5-v1.1: ...", "phase3.6-F1: ..." 형식으로 단계당 1개.
- 단계별 세부 작업과 완료 기준은 @docs/phase3-plan.md 를 따른다. 전체 설계는 docs/architecture.md, Phase 1 실측 교훈은 docs/phase1-result.md 를 참고한다. 문서들이 CLAUDE.md와 다르면 문서가 우선한다.

## 단계 완료 보고 규칙
- 단계가 끝나면 콘솔에 긴 결과를 출력하지 말고 `docs/reports/phase<N>.<step>.md`를 작성하고 커밋한 뒤 `git push origin hyeonuk-dev` 한다. 콘솔에는 보고서 경로, 전체 PASS/FAIL 한 줄, "결정 필요" 항목 개수만 출력한다.
- 보고서 절 순서(고정):
  0. 결정 필요 사항 — 내 답이 있어야 진행되는 것. 없으면 "없음".
  1. 단계 목표와 끝난 기준별 PASS/FAIL — PASS에는 반드시 근거 수치와 근거 파일 경로.
  2. 변경 파일과 커밋 해시.
  3. 실행 명령과 주요 출력 — 길면 요약하고 전문은 `docs/reports/logs/<보고서명>-<항목>.txt`로 저장 후 경로.
  4. Legacy/New 비교 결과와 수치 — 표.
  5. 지시와 다르게 구현한 것과 이유.
  6. 발견한 문제·해결·남은 한계.
- 6절에 적는 발견(관측)은 `docs/findings.md`에도 O번호로 적는다(날짜·단계 / 무엇을 봤나 / 근거 / 왜 중요한가 / 후속). 결정은 decision-log.
- 다음 단계는 내 승인 후에만 시작한다.
- 문서 수정 범위: `docs/phase*-plan.md`의 기존 문장은 수정 금지, "구현 시 확정" 절 추가는 허용. `docs/architecture.md`는 지시 없이 수정 금지. 문서에 없는 설계 결정은 임의로 하지 말고 0절에 질문으로 올린다.
