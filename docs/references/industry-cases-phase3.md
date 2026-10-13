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
| 카카오페이 — 자바 프로젝트 3개 코틀린 점진적 전환기 (2023-12-05) | 해외결제 백엔드 1,100 파일·2.5개월·3명, 엔티티·리포지토리·유틸 → 컨트롤러 → 서비스 순, 안전망은 전환 전 테스트 강화뿐(트래픽·사이드이펙트 비교 없음), 자동 변환 후 nullable 오판이 함정, 혼재 1년 뒤 80~90%, git rename 이력 | F0 현업 근거 / 사다리 순서 비교 / Phase 4 혼재 전제 (3.7 추가) |
| ↳ 출처 | [docs/references/kakaopay-kotlin-migration.md](kakaopay-kotlin-migration.md) | |
| 우아한형제들 — Java야 우리 그만 헤어져, Kotlin으로 환승연애 (2025-07-22) | 배민페이 포인트 시스템 3개월·6명·45k라인·배포 10회·장애 0, 테스트 선행 전환(커버리지 61.5→76.7%)+QA+점진 배포(트래픽 복제 없음), null 재설계·Jackson KotlinModule 누락·QueryDSL 생성자 순서·롤백 규칙 변화(실제 원인은 checked 예외의 Spring 기본 롤백 규칙)가 함정 | F0 근거 2 / F4 transactions·dbstate 축 근거 / "현업 전환 검증 = 테스트 커버리지" (3.7 추가) |
| ↳ 출처 | [docs/references/woowahan-kotlin-migration.md](woowahan-kotlin-migration.md) | |
