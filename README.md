# 운영 트래픽 재현과 변경 전후 행동 비교를 통한 시스템 교체 검증

Legacy → New 시스템 교체 시 동일한 트래픽을 Istio 미러링으로 양쪽에 전달하고, 각 서비스가 남긴 실행 Evidence(응답 · DB 접근 · 외부 호출 · 이벤트 · 순서)를 비교해 변경 전후의 행동 차이를 `SAME` / `Improvement` / `Contract Violation` / `Uncertain`으로 분류한다. 자동으로 판정되지 않는 `Uncertain`만 사람이 검토하고 그 판단을 Rule로 축적하여, 시스템 교체 때 사람이 직접 검토해야 하는 범위를 줄이는 것이 목표다.

## 문서

- [docs/architecture.md](docs/architecture.md) — 전체 아키텍처 설계
- [docs/decision-log.md](docs/decision-log.md) — 구현 중 내린 결정 (결정 / 근거 / 대안)
- Phase 1 — Kubernetes + Istio 기반
  - [docs/phase1-plan.md](docs/phase1-plan.md) — 상세 계획
  - [docs/phase1-result.md](docs/phase1-result.md) — 실행 결과 (버전 고정, 단계별 확인)
  - [docs/isolation-proof.md](docs/isolation-proof.md) — `new` 격리 증명, 스택 간 DB 격리, 관찰
- Phase 2 — 단일 파이프라인 end-to-end
  - [docs/phase2-plan.md](docs/phase2-plan.md) — 상세 계획
  - [docs/phase2-result.md](docs/phase2-result.md) — 결과 (A/A diff ∅, Phase 3 입력 계약)
  - [docs/evidence-schema-v0.json](docs/evidence-schema-v0.json) — Evidence JSON v0 스키마
- Phase 3 — MSA 확장 + 점진 전환 사다리 + 판정 엔진 (진행 중)
  - [docs/phase3-plan.md](docs/phase3-plan.md) — 상세 계획
  - [docs/call-graph.md](docs/call-graph.md) — Call Graph 동적 수집·합성 (D14)
- 참고
  - [docs/references/kakaopay-aop-shadow.md](docs/references/kakaopay-aop-shadow.md) — 카카오페이손보 AOP 섀도우 사례
  - [docs/references/industry-cases-phase3.md](docs/references/industry-cases-phase3.md) — Phase 3 산업 사례
- [docs/reports/](docs/reports/) — 단계 완료 보고서

## 디렉터리

- `services/order/` — Order 서비스(Spring Boot). `poc.evidence` 수집기 포함
- `evidence-store/` — Evidence Store (FastAPI)
- `corpus/` — 재생 corpus와 검증 스크립트
- `k6/` — 재생(`run.js`), run script(`run.sh`), spill 회수
- `engine/` — 로컬 검증 엔진(클러스터 접근 없음)
- `deploy/k8s/` — kind·Istio·legacy/new·verify·observability 매니페스트
- `poc/nginx-mirroring/` — Phase 0 개념 확인용 PoC (동결, 최종 delivery 레이어 아님)
- `runs/` — run별 export (gitignore)
