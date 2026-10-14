# 우아한형제들 — Java야 우리 그만 헤어져, Kotlin으로 환승연애 (2025-07-22)

- 출처: 우아한형제들 기술 블로그, "Java야 우리 그만 헤어져, Kotlin으로 환승연애", 2025-07-22, 배민페이플랫폼팀 — https://techblog.woowahan.com/22586/
- 정리: 2026-10-14, Phase 3.7

## 요지

- **대상·규모**: 포인트 시스템, 3개월, 6명, 45k 라인, 배포 10회, 장애 0
- **안전망**: 테스트 선행 전환(Kotest/MockK, 커버리지 61.5% → 76.7%) + QA + 기능 단위 점진 배포. 트래픽 복제·출력 비교는 없음
- **가장 많은 테스트가 든 구간**: null 처리 재설계
- **함정으로 기록한 것**: Jackson `KotlinModule` 누락, QueryDSL 생성자(프로젝션) 순서, 트랜잭션 롤백 규칙 변화. 글은 롤백 변화를 `@Throws` 탓으로 설명하지만, 실제 원인은 예외가 checked 예외 클래스라는 점이다 — Spring 기본 롤백 규칙은 unchecked(RuntimeException·Error)만 롤백하고, Kotlin에는 checked 예외 구분이 없어 Java에서 쓰던 checked 예외 계층을 그대로 던지면 롤백되지 않는다
- **기타**: git rename·squash 머지 주의(이력 보존)

## 이 프로젝트에 반영

| 요지 | 반영 |
|---|---|
| null 처리가 최다 테스트 구간 | **F0 근거 2**(카카오페이 2023과 함께) — findings O6 |
| 롤백 규칙 변화가 함정 | **F4(transactions·dbstate 축) 현업 근거** — 롤백 누락은 응답·SQL이 같고 트랜잭션 outcome과 후속 조회·최종 DB 상태로만 드러났다(findings O10). 이 프로젝트의 F4는 `noRollbackFor`로 만들었지만 관측 축은 같다 |
| Jackson KotlinModule 누락 | 사다리 v1.1에서 jackson-module-kotlin을 Kotlin DTO 역직렬화 첫 단계에 추가(3.5 구현 시 확정). 응답 바이트가 Java와 같음을 B0으로 확인(findings O5) |
| 생성자 순서(QueryDSL) | 이 프로젝트는 Java record ↔ Kotlin data class 직렬화 필드 순서가 같음을 B0으로 확인. 순서가 바뀌었다면 C는 canonical 비교라 SAME, B0만 DIFF |
| 안전망 = 테스트 커버리지·QA·점진 배포, 트래픽 복제 없음 | 카카오페이 2023과 묶어 "현업 전환 검증 = 테스트 커버리지" 서술. 장애 0은 결과이지 행동 동일성의 증거는 아니다 — 이 프로젝트가 재는 것(행동 Evidence 차이)과 다른 층 |
| git rename·squash 주의 | Phase 4 `git diff -M`, 사다리·결함 브랜치 squash 금지(call-graph.md 메모) |
