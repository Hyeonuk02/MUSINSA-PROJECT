# Phase 3 산업 사례 — 요지와 반영 위치

> 2026-10-13. 원본: `docs/phase3-plan.md` 8절 표. 각 행 아래 줄이 출처.

| 사례 | 요지 | 반영 위치 |
|---|---|---|
| Uber — Shifting E2E Testing Left (BITS, 2024) | 테넌시 식별자를 baggage로 전파해 운영 서비스에 테스트 트래픽; Jaeger 트레이스로 "테스트 → 서비스·엔드포인트" 인덱스를 만들어 변경 시 돌릴 테스트 선택; placebo run; 설정 변경이 incident 30%; 71% 감소 | 재생 헤더·hopPath 전파(3.1·3.2) / D14 근거 / A/A ≙ placebo / F7 |
| ↳ 출처 | https://www.uber.com/us/en/blog/shifting-e2e-testing-left/ | |
| LinkedIn — inCapacity (실시간 콜그래프) | request ID로 트레이스를 묶어 15분마다 집계; 용도에 impact analysis 명시; 두 구간 콜그래프 비교로 근본 원인 | D14 근거 / callTree Legacy·New 구조 비교(3.4) |
| ↳ 출처 | https://engineering.linkedin.com/distributed-service-call-graph/real-time-distributed-tracing-website-performance-and-efficiency | |
| 토스 — Gateway (2023) | Passport 전파; Dynamic Security가 재전송(replay) 차단 → 운영 재현은 게이트웨이 인증 **뒤**에서 미러 | 전파 패턴 / architecture "운영 적용" 절 |
| ↳ 출처 | https://toss.tech/article/22910 | |
| 우아한형제들 — WireMock (2024) | `fixedDelayMilliseconds`, `priority` 기본 stub, `equalToJson` 본문 매칭 | F7 지연 세션 / journal 본문 비교(3.1·3.6) |
| ↳ 출처 | https://techblog.woowahan.com/17674/ | |
| 카카오페이손보 — AOP 섀도우 (2026) | 프로세스 안 섀도우의 한계(조회만·같은 런타임·메서드마다 수정); 정규화 규칙은 경험적으로 늘어남 | 대비 서술 / `@Around`·ThreadLocal / 규칙 축적 근거 |
| ↳ 출처 | [docs/references/kakaopay-aop-shadow.md](kakaopay-aop-shadow.md) | |
| Twitter — Diffy (2015) | primary/secondary/candidate로 잡음을 통계 추정; 응답만; "similar" | A/A = secondary, 설계로 잡음 0 → "same" |
| ↳ 출처 | https://blog.x.com/engineering/en_us/a/2015/diffy-testing-services-without-writing-tests | |
| Spring Framework 문서 | `afterCommit`에서 트랜잭션 리소스가 활성으로 보일 수 있음; `TransactionExecutionListener`(6.1) | D16 타임라인 설계 |
| ↳ 출처 | https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html | |
| AWS — Transactional Outbox | 커밋과 발행 원자성 문제의 표준 해법 | 범위 밖 명시, 동기 ack로 관측만 |
| ↳ 출처 | https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html | |
