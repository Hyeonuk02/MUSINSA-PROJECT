# Phase 3 결과 (누적)

> 단계별 상세는 `docs/reports/phase3.<step>.md`. 이 문서는 표만 누적한다. Phase 3 종료 시 결론·한계를 더한다.

## 3.5 New v1 사다리 — Order 점진 Kotlin 전환

Legacy = `order-app:phase3.3-base`(고정), Coupon 양쪽 `coupon-app:phase3.3-base`, corpus v2(58 pair/run, learn 25 · eval 33), VU=3 ×3, 엔진 `engine-v1.1`. 판정 수는 run당 값(세 run이 같으면 하나로 적는다). 규칙은 v1.1·v1.2에서만 생성.

| 단계 | commit | order 이미지(new) | runs | 변경 클래스(코드 diff) | SAME | IMP | UNC | CV | learn 리뷰 | 생성 규칙 | eval UNC 전→후 | B0 DIFF | B1 DIFF | Metaspace order legacy/new (MB, 참고) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | `d1b283e` | phase3.3-base | `runs/p35-base-1..3` | — (A/A) | 58 | 0 | 0 | 0 | 0 | 0 | 0→0 | 0 | 0 | 125.02 / 125.01 |
| v1.1 | `fd839d6` | phase3.5-v1.1 | `runs/p35-v1.1-1..3` | `PaymentGatewayClient` (.java −56 → .kt +50), pom +104 | 58 | 0 | 0 | 0 | 0 | 0 | 0→0 | 0 | 0 | 126.79 / 134.23 |
| v1.2 | `fc6e6e2` | phase3.5-v1.2 | `runs/p35-v1.2-1..3` | `Order`, `OrderItem`, `OrderRepository` (.java −175 → .kt +171) | 58 | 0 | 0 | 0 | 0 | 0 | 0→0 | 0 | 0 | 128.18 / 134.90 |

사다리 표에서 제외한 run: `runs/p35-v1.1-oom-1`(Metaspace OOM), `runs/p35-v1.1-stale-1`(runId 재사용) — `docs/reports/phase3.5.md` 6절.
