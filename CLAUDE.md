# CLAUDE.md

전체 프로젝트 설계는 docs/architecture.md 를 기준으로 한다.
현재는 Phase 1만 진행한다.

## 프로젝트 방향

Legacy → New 시스템 교체 시 동일 트래픽을 Istio Shadow Mirroring으로
양쪽에 전달하고, 실행 Evidence를 비교하여 변경 전후 행동 차이를 찾는다.

전체 흐름:
Git Diff → Call Graph → 영향 API → k6 → Istio Mirroring → Legacy / New → Evidence → Verification Engine → Human Review

목표는 사람이 직접 검토해야 하는 범위를 줄이는 것이다.

## 현재 Phase: Phase 1

Phase 1의 목적은 앞으로 검증 시스템이 동작할 Kubernetes + Istio 기반 환경을 만드는 것이다.

### 1.1 Kubernetes 기반
- kind 클러스터 생성, namespace 생성, Order 이미지 load, NetworkPolicy 동작 확인

### 1.2 Istio
- Istio 설치, legacy/new sidecar injection 확인

### 1.3 Legacy / New 배포
- 기존 Order 앱을 services/order로 옮겨 사용, MySQL 8 전환
- Legacy/New 각각 Order + DB 배포, APP_FIXED_CLOCK 적용

### 1.4 Observability
- OTel Collector + Jaeger, Envoy/App trace 연결, sampling 100%

### 1.5 New 격리
- REGISTRY_ONLY guardrail 확인
- Kubernetes NetworkPolicy로 실제 외부 egress 차단 확인

### 1.6 Shadow Mirroring
- Istio Gateway + VirtualService, route → Legacy, mirror → New
- 동일 테스트 ID가 양쪽에 전달되는지 확인

## 확정 사항

- Kubernetes: kind (≥ v0.25)
- Service Mesh: Istio / Envoy
- DB: MySQL 8
- namespace: istio-system, observability, legacy, new, verify
- 실제 격리 경계는 Kubernetes NetworkPolicy
- REGISTRY_ONLY는 guardrail
- Istio는 mirroring / guardrail / proxy tracing 용도로만 사용

## 하지 말 것

Phase 1에서는 다음을 구현하지 않는다.
Coupon / Payment, Kafka, k6, Evidence Store, Verification Engine, Call Graph, Rule / Human Review, 성능 테스트, Istio의 추가 기능.

## 작업 방식

- 반드시 Phase 1.1부터 순서대로 진행한다.
- 한 번에 한 단계만 진행한다.
- 구현 전에 이번 단계에서 무엇을 할지와 완료 기준을 먼저 설명한다.
- 내가 실행 결과를 확인한 뒤 다음 단계로 넘어간다.
- 오류는 현재 단계에서 해결한다.
- 중요한 설계 결정이 필요하면 임의로 정하지 말고 질문한다.
- 단계별 세부 작업과 완료 기준은 @docs/phase1-plan.md 를 따른다. 전체 설계는 docs/architecture.md 를 참고한다. 두 문서가 CLAUDE.md와 다르면 두 문서가 우선한다.
