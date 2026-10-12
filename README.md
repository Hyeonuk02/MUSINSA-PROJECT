# 운영 트래픽 재현과 변경 전후 행동 비교를 통한 시스템 교체 검증

Legacy → New 시스템 교체 시 동일한 트래픽을 Istio 미러링으로 양쪽에 전달하고, 각 서비스가 남긴 실행 Evidence(응답 · DB 접근 · 외부 호출 · 이벤트 · 순서)를 비교해 변경 전후의 행동 차이를 `SAME` / `Improvement` / `Contract Violation` / `Uncertain`으로 분류한다. 자동으로 판정되지 않는 `Uncertain`만 사람이 검토하고 그 판단을 Rule로 축적하여, 시스템 교체 때 사람이 직접 검토해야 하는 범위를 줄이는 것이 목표다.

## 문서

- [docs/architecture.md](docs/architecture.md) — 전체 아키텍처 설계
- [docs/phase1-plan.md](docs/phase1-plan.md) — Phase 1 (Kubernetes + Istio 기반) 상세 계획
- [docs/phase1-result.md](docs/phase1-result.md) — Phase 1 실행 결과 (버전 고정, 단계별 확인)
- [docs/isolation-proof.md](docs/isolation-proof.md) — `new` 네임스페이스 격리 증명
- [docs/decision-log.md](docs/decision-log.md) — 구현 중 내린 결정 (결정 / 근거 / 대안)

## 디렉터리

- `poc/nginx-mirroring/` — Phase 0 개념 확인용 PoC (동결, 최종 delivery 레이어 아님)
