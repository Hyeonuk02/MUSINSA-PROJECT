# 카카오페이손해보험 AOP 섀도우 사례 — 우리 프로젝트 근거 + 가져올 것 (Phase별 적용 메모)

> 작성 2026-10-12. 출처: 카카오페이 기술 블로그 "안전하게 레거시 코드 옮겨 보기" (jay.way, 2026-08)
> https://tech.kakaopay.com/post/kakaopayins-legacy-improvement-with-aop/
> 용도: 보고서 관련 사례 절, 자소서/발표 논거, Phase 2.8 / 3 / 4 설계에 반영. 각 항목에 "어디에 적용" 표시.

---

## 1. 사례 요약 (사실만)

**배경** — `contract` 레포가 레거시 모듈 `product`에 의존해 Spring Boot 2.6에 묶임. `product`를 MSA 서버로 100% 이관해야 하는데, (1) 기능이 뒷단에서 호출돼 전체 케이스 파악·통합 테스트·회귀 스크립트 작성이 어렵고, (2) QA 인력 부족, (3) 업무 부담. → **우리 문제 정의와 동일** (전체 케이스를 모르는 레거시, QA 없이 개발자 역량으로 검증).

**전략** — Fowler의 Strangler 패턴 + AOP 섀도우 비교. 목표: 운영 호출 케이스로 검증 / QA 없이 / 점진 이관.

**구현**
- `@ShadowInquiry(compareBean, compareMethodName, paramTypes, paramIndexes)` — 레거시 메서드마다 붙이고 신규 빈·메서드를 손으로 연결
- `ShadowInquiryAspect`: `@AfterReturning(pointcut="@annotation(shadowInquiry)", returning="result")` → 원본 응답이 나간 뒤 실행. 1~100 랜덤 vs **DB에 저장된 실행률**로 실행 여부 결정(런타임 조절). `ConcurrentHashMap` 메서드 캐시(리플렉션 반복 방지)
- `ShadowInquiryExecutor`: `@Async`(전용 executor)로 신규 메서드 호출 → 두 결과를 **JSON 트리로 비교**(toString 아님) → 다르면 DB 저장 + 알림, 같으면 아무것도 안 함. 예외는 try/catch 후 알림
- `StranglerObjectMapper`: BigDecimal 소수점 정규화(100.0 vs 100.000), **컬렉션 정렬**, 프로퍼티 알파벳순, null 항상 포함. 저자: "더 많은 케이스가 있지만 일단 이것만 대응"
- `@TransactionalEventListener`는 Boot 2.6 버그(리스너 예외가 debug 로그로만 찍힘)로만 언급. 설계 요소 아님

**부하 측정** (SANDBOX, curl 동시요청, 구간당 25초, 3초 샘플링, 지표: CPU/heap/GC/HikariCP pending/threads/avg·P95·P99·Max)
- 적용 전 최대 처리량 100%: avg 1,063ms / P95 1,184 / P99 1,274 / DB pending 26
- 적용 후 최대 처리량 **80% (−20%)**: 83.5% 구간에서 avg 1,352 / P95 1,789 / P99 1,928 / DB pending 42
- 전 구간 5xx 0, timeout 0. 결론: 일반 상황에서 100% 적용 가능, 이상 시 실행률 낮춤

이 구현은 GitHub **Scientist** 패턴(control/candidate 실행 → 비교 → 불일치 publish)의 Spring AOP 판이다.

---

## 2. 우리 프로젝트의 의의·근거로 쓸 것

### 2.1 구조 대비표 (보고서 관련 사례 절 / 발표 슬라이드)

| | 카카오페이손보 (프로세스 안) | 우리 (인프라 레벨) |
|---|---|---|
| 분기 지점 | JVM 안, 메서드 경계(AOP) | 메시 ingress, 스택 경계(Istio mirror) |
| 비교 대상 | 반환값만 | 응답 + DB 접근(dbAccess) + 최종 DB 상태 + (Phase 3) 외부 호출·이벤트 + callTree |
| 쓰기 요청 | **불가** — 같은 DB라 이중 쓰기. 그래서 이름이 `Inquiry`(조회) | 가능 — 스택별 DB 격리(2.3 전 실측, NetworkPolicy) |
| 런타임 교체 | **불가** — 같은 프로세스. 목표가 Boot 버전업인데 그 버전업은 이 방식으로 검증 못 함 | 가능 — New 스택만 다른 Boot/JDK |
| 대상 추가 비용 | 메서드마다 어노테이션 + compareBean 연결(메서드 단위 침투) | 비즈니스 메서드 0줄 수정, 횡단 훅(필터·인스펙터·패키지 포인트컷)만 |
| 비용이 붙는 곳 | 레거시 요청 스레드·같은 커넥션 풀 (−20%) | Legacy는 sidecar 미러 복사만, 나머지는 New 스택 |
| 저장 | 불일치만 (일치 건은 버림 → 재분석 불가) | 전부 저장 → 규칙 바꿔 재판정 가능 |
| 샘플링 | DB 저장 실행률(런타임 조절) | Istio `mirrorPercentage`(kubectl apply, 무중단) |
| 노이즈 처리 | ObjectMapper 규칙 4개, "더 있음" | 정규화 규칙 목록 + A/A run으로 식별 + 사람 리뷰 → 규칙 축적 |

### 2.2 문장으로 (자소서·보고서·발표에서 그대로 쓸 것)

- "운영 트래픽 섀도우 비교는 국내 금융사(카카오페이손해보험)의 실제 레거시 전환에서도 쓰인 검증 방식이다." — 필요성의 국내 실무 근거
- "프로세스 안 섀도우(AOP)는 세 가지 구조적 한계가 있다: 같은 DB를 쓰므로 조회만 가능하고, 같은 프로세스이므로 런타임 교체를 검증할 수 없으며, 대상 메서드마다 코드를 수정해야 한다. 우리는 분기를 서비스 메시로, 비교를 외부 엔진으로 빼서 쓰기·런타임 교체까지 검증 범위에 넣었다." — 아키텍처 선택의 정당화
- "'더 넓은 검증'은 야심이 아니라 스택 격리의 결과다." — 교수님 질문 대비
- "카카오페이도 문자열 비교가 아닌 구조적 JSON 비교를 택했고, 정규화 규칙이 경험적으로 늘어난다고 적었다. 우리 '기록은 최대 해상도, 판정은 선언된 해상도'와 '사람 리뷰 → 규칙 축적'은 그 경험을 설계로 올린 것이다." — novelty 후보의 근거
- 주의: 우리도 앱 안에 훅(필터·StatementInspector·AOP·Kafka 인터셉터)이 있다. "검증 로직이 앱에 전혀 안 들어간다"고 쓰지 말 것. 정확한 표현은 "**비즈니스 메서드 수정 없는 횡단 훅**".

### 2.3 리서치 보고서 위치
- 관련 사례 절에서 Scientist(GitHub) 옆에 "국내 사례: 카카오페이손보 AOP 섀도우(Scientist 패턴의 Spring 구현)"로 추가
- Diffy(응답만) → 카카오페이(반환값만, 프로세스 안) → AREX(아웃바운드까지, 에이전트) → 우리(메시 분기 + 사이드이펙트 + 4분류·Rule) 순서로 배치하면 자연스럽다

---

## 3. 가져올 것 — Phase별

### Phase 2.8 (A/A run, `engine/diff_v0.py`) — 응답 정규화
- 현재 2.8은 이미 "parse → 제외 필드(DB auto id) 제거 → key 정렬 → canonical 직렬화 → 비교"(v2). 카카오페이가 같은 방향을 택했다는 걸 근거로 적기만 하면 됨
- **가져오지 말 것: 전역 컬렉션 정렬.** 우리 `items`는 `line_no` 순서가 계약. 정렬하면 순서 버그가 숨는다. 정렬은 필드별 선언만(현재 선언 필드 없음)
- 숫자 정규화(100.0 vs 100.000), null vs 없음 정책은 **A/A나 Phase 3에서 잡음으로 나올 때** 규칙으로 추가. 미리 넣지 않음

### Phase 3 — 동적 콜그래프 AOP (`callTree`)
- `@AfterReturning` 아님 `@Around`: enter/exit/예외 모두 필요
- `@Async` 금지: `ReplayContext`가 ThreadLocal이라 비동기 넘기면 사라짐. 전송 분리는 spill 큐에서(컨텍스트 캡처 후)
- **Spring AOP는 프록시 기반 → 같은 빈 안의 self-invocation 못 잡음.** 콜 트리 해상도를 "빈 간 public 호출"로 **선언**하고 간다(AspectJ LTW/에이전트는 비용 대비 과함). → decision-log 항목: "callTree 해상도 = Spring 빈 경계"
- 포인트컷은 어노테이션 opt-in이 아니라 패키지 기반(`execution(* ..order..*(..))`). 메서드마다 수정하지 않는 게 우리 차별점
- 리플렉션/메서드 캐시 같은 성능 배려는 참고(우리는 리플렉션 호출 없음)

### Phase 3 — Kafka / 트랜잭션 (병언 영역과 접점)
- Order의 이벤트 발행은 커밋 후(`@TransactionalEventListener(phase = AFTER_COMMIT)`)가 정석. **fault catalog 항목**: "New는 커밋 전에 publish(`@EventListener`)" → 롤백 시 유령 이벤트. 응답으론 안 보이고 **이벤트 Evidence(sum 계약)로만 잡히는 회귀** — 카카오페이 방식(반환값만)은 못 잡는다는 걸 보여주는 케이스
- Boot 2.6 버그 교훈: 리스너 안 예외는 요청을 실패시키지 않고 조용히 사라질 수 있다 → 리스너/프로듀서 쪽 실패는 응답이 아니라 **producer Evidence·DLQ**로 잡아야 함
- **Evidence 스키마 v1 후보: `dbAccess.txOutcome`** — StatementInspector는 SQL이 나간 건 알지만 커밋/롤백은 모름. `TransactionSynchronization.afterCompletion(status)`를 요청 필터에서 등록하면 싸게 얻음(COMMITTED / ROLLED_BACK / UNKNOWN). 최종 DB 상태 비교와 짝을 이룸

### Phase 4 — 오버헤드 측정 (결과 표 템플릿)
- 카카오페이 표 형식 차용: 상대 처리량 구간별 CPU avg/max, heap, DB pool pending max, threads, avg/P95/P99/Max, 합격 기준 5xx·timeout 0
- 측정 대상 두 개:
  1. **Legacy 스택: 미러 on/off** → 운영 시스템이 내는 비용(sidecar 미러 복사만이어야 함)
  2. **New 스택: 필터+인스펙터 on/off** → 섀도우 스택이 내는 비용
- 비교 기준선: 프로세스 안 섀도우 **−20%**(카카오페이). "인프라 섀도우는 Legacy 비즈니스 경로에 ~0"을 숫자로
- `mirrorPercentage`를 운영 적용 절의 샘플링 노브로 서술(카카오페이 "DB 저장 실행률"의 대응물)

### 문서 반영 체크리스트
- [ ] 리서치 보고서 관련 사례 절 — 2.3 위치에 추가
- [ ] `docs/architecture.md` — "왜 인프라 레벨인가" 절에 2.1 표의 3·4·5행 요약
- [ ] `docs/decision-log.md` — Phase 3 진입 시 "callTree 해상도 = 빈 경계" 항목
- [ ] Phase 3 fault catalog — "커밋 전 publish" 항목
- [ ] Phase 3 Evidence 스키마 v1 — `txOutcome` 후보
- [ ] Phase 4 결과 — 오버헤드 표 2개
- [ ] 자소서/발표 — 2.2 문장

---

## 4. 가져오지 않을 것
- 메서드 단위 opt-in 어노테이션 + compareBean 연결 방식 전체 (우리 분기점은 메시)
- `@Async` 비교 실행 (ThreadLocal 컨텍스트 유실)
- 불일치만 저장 (전부 저장이 맞음 — 재판정 가능)
- 전역 컬렉션 정렬 (순서 계약 손실)
