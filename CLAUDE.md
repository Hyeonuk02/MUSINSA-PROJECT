# CLAUDE.md

전체 프로젝트 설계는 docs/architecture.md 를 기준으로 한다.
현재는 Phase 2만 진행한다. Phase 1은 완료됐다 (tag phase1-done, docs/phase1-result.md).

## 프로젝트 방향

Legacy → New 시스템 교체 시 동일 트래픽을 Istio Shadow Mirroring으로
양쪽에 전달하고, 실행 Evidence를 비교하여 변경 전후 행동 차이를 찾는다.

전체 흐름:
Git Diff → Call Graph → 영향 API → k6 → Istio Mirroring → Legacy / New → Evidence → Verification Engine → Human Review

목표는 사람이 직접 검토해야 하는 범위를 줄이는 것이다.

## 현재 Phase: Phase 2 — 단일 파이프라인 end-to-end

Phase 1 인프라 위에서 k6 → Istio 미러 → Legacy/New → Evidence 필터 → Evidence Store → export JSON을
한 줄로 관통시킨다. 판정 엔진은 만들지 않는다.
종료 시점의 Evidence JSON 형식이 Phase 3 엔진의 입력 계약이 된다.

### 2.1 Order API를 business key 기반으로
- POST /api/orders {orderKey}, GET /api/orders/by-key/{orderKey}, POST /api/orders/{orderKey}/pay (Idempotency-Key), cancel
- WireMock 결제 스텁을 legacy/new 양쪽에

### 2.2 corpus v1
- 독립 세션 3개, 각 세션은 생성→조회→결제→조회, 에러 경로 포함. JSON + 스키마 검증

### 2.3 Evidence Store v0 + Evidence JSON v0
- verify 네임스페이스, POST/exists/count/export. 포트명 http-evidence
- Gateway에 /_evidence/ 라우트(mirror 없음, /api 라우트보다 앞)

### 2.4 Order 앱 Evidence 필터
- request/response 캡처 → 응답 커밋 후 비동기 POST, X-Evidence-Internal: true
- Evidence POST 클라이언트는 java.net.http.HttpClient + 해당 계측만 off

### 2.5 k6 VU=1 + 요청당 New 완료 폴링
### 2.6 run script — S0 리셋 → k6 → flush barrier → export
### 2.7 동일성·pairing 검증 (전건 대조)
### 2.8 VU=3 × 3회 반복 → diff 집합 동일 확인. 실패 시 VU=1

## 확정 사항

- replayRequestId는 k6(corpus)가 부여, X-Replay-Request-Id. Envoy mirror가 헤더 복사
- business key(orderKey)는 corpus에서 결정론적 파생. 후속 요청은 orderKey로 대상 지정
- Evidence 키 (runId, replayRequestId, stack). Evidence POST는 비교·span 대상 아님
- 완료 폴링: 요청마다 Store exists로 New 도착 확인 후 다음 요청
- flush barrier: Store count == 기대 건수 확인 후 export·리셋
- Legacy/New 앱 코드 동일. 고정 시각 유지. S0 리셋 = MySQL rollout restart
- Phase 1 교훈 적용: Service 포트명 접두사(http-/grpc-), 멀티아치 이미지 로드 절차, 런타임 다운로드 금지, new는 default-deny egress(verify 허용됨)

## 하지 말 것

Phase 2에서는 다음을 구현하지 않는다.
Coupon/Payment 실서비스, Kafka, DB·이벤트·외부 호출 Evidence, Normalization·4분류·Rule·Human Review, Call Graph, 결함 주입, 성능 테스트, Istio 추가 기능, Evidence Store DB·인증·UI.

## 작업 방식

- 반드시 Phase 2.1부터 순서대로 진행한다.
- 한 번에 한 단계만 진행한다.
- 구현 전에 이번 단계에서 무엇을 할지와 완료 기준을 먼저 설명한다.
- 내가 실행 결과를 확인한 뒤 다음 단계로 넘어간다.
- 오류는 현재 단계에서 해결한다.
- 중요한 설계 결정이 필요하면 임의로 정하지 말고 질문한다.
- 단계마다 "phase2.x: ..." 형식으로 커밋한다.
- 단계별 세부 작업과 완료 기준은 @docs/phase2-plan.md 를 따른다. 전체 설계는 docs/architecture.md, Phase 1 실측 교훈은 docs/phase1-result.md 를 참고한다. 문서들이 CLAUDE.md와 다르면 문서가 우선한다.
