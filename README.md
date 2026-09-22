# 운영 트래픽 재현과 변경 전후 행동 비교를 통한 시스템 교체 검증

Legacy → New 시스템 교체 시 동일한 트래픽을 양쪽에 전달하고,
실행 결과(응답 + 사이드이펙트)를 비교하여 차이를 자동으로 분류하는 검증 파이프라인입니다.

최종적으로 실행 결과를 다음 네 가지로 분류하고,
자동 판단이 어려운 `Uncertain` 케이스만 사람이 검토하는 것을 목표로 합니다.

- `SAME`
- `Improvement`
- `Contract Violation`
- `Uncertain`

## 현재 상태

**Phase 0 — nginx Mirroring Feasibility PoC**

현재 nginx mirroring을 향후 Legacy/New 비교 실험의
트래픽 전달 방식으로 사용할 수 있는지 검증하고 있습니다.

- [x] 4.1 최소 Spring Boot 주문 API
- [x] 4.2 Legacy / New 애플리케이션 및 DB 분리
- [x] 4.3 nginx mirroring 및 Request ID 전달
- [x] 4.4 Application Request Logging
- [ ] 4.5 k6 deterministic traffic
- [ ] 4.6 자동 검증 및 최종 PASS / FAIL 판정

## 현재 구조

```text
                    Client
                      |
                      v
                  nginx :8080
                  /         \
          main request      mirror
              |               |
              v               v
          Legacy App       New App
              |               |
              v               v
          Legacy DB        New DB
