# Phase 3 결과 (누적)

> 단계별 상세는 `docs/reports/phase3.<step>.md`. 이 문서는 표만 누적한다. Phase 3 종료 시 결론·한계를 더한다.

## 3.5 New v1 사다리 — Order 점진 Kotlin 전환

Legacy = `order-app:phase3.3-base`(고정), Coupon 양쪽 `coupon-app:phase3.3-base`, corpus v2(58 pair/run, learn 25 · eval 33), VU=3 ×3, 엔진 `engine-v1.1`. 판정 수는 run당 값(세 run이 같으면 하나로 적는다). 규칙은 v1.1·v1.2에서만 생성.

| 단계 | commit | order 이미지(new) | runs | 변경 클래스(코드 diff) | SAME | IMP | UNC | CV | learn 리뷰 | 생성 규칙 | eval UNC 전→후 | B0 DIFF | B1 DIFF | Metaspace order legacy/new (MB, 참고) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | `d1b283e` | phase3.3-base | `runs/p35-base-1..3` | — (A/A) | 58 | 0 | 0 | 0 | 0 | 0 | 0→0 | 0 | 0 | 125.02 / 125.01 |
| v1.1 | `fd839d6` | phase3.5-v1.1 | `runs/p35-v1.1-1..3` | `PaymentGatewayClient` (.java −56 → .kt +50), pom +104 | 58 | 0 | 0 | 0 | 0 | 0 | 0→0 | 0 | 0 | 126.79 / 134.23 |
| v1.2 | `fc6e6e2` | phase3.5-v1.2 | `runs/p35-v1.2-1..3` | `Order`, `OrderItem`, `OrderRepository` (.java −175 → .kt +171) | 58 | 0 | 0 | 0 | 0 | 0 | 0→0 | 0 | 0 | 128.18 / 134.90 |
| v1.3 | `c64618f` | phase3.5-v1.3 | `runs/p35-v1.3-1..3` | `OrderService`(+Kind·Outcome·NewItem), `OrderPaid`, `OrderEventPublisher` (.java −188 → .kt +173) | 58 | 0 | 0 | 0 | 0 | 0 (규칙 생성 없는 단계) | 0→0 | 0 | 0 | 128.98 / 134.71 |
| v1.4 | `120b212` | phase3.5-v1.4 | `runs/p35-v1.4-1..3` | `OrderController`(+DTO), `OrderView`, `CouponClient`, `ClockConfig`, `OrderApplication`, `requestlog.RequestLogFilter`, `requestlog.CachedBodyRequest` (.java −428 → .kt +349) = Order 전면 Kotlin | 58 | 0 | 0 | 0 | 0 | 0 (규칙 생성 없는 단계) | 0→0 | 0 | 0 | 128.94 / 135.33 |

요약: 이 corpus가 닿는 행동 범위에서 Order의 점진 Kotlin 전환(1 → 전면 클래스)은 행동 Evidence를 바꾸지 않았다 — 네 단계 모두 C·B0·B1 전 pair SAME(B0 원문까지). Uncertain이 없어 learn 리뷰 0·규칙 0, eval Uncertain 0→0이라 Rule 재사용 효과는 3.6의 F 변형에서 처음 측정된다. Kotlin 전환의 흔적은 Metaspace(new order +6.4~7.4 MB, 클래스 +1,800~2,300)에만 남았다. Kotlin v1.4가 3.6 결함 카탈로그의 새 기준선이다.

Phase 4 입력(스코핑): 단계별 commit = 위 표 commit 열, 이미지 = `order-app:phase3.5-v1.x`, runs = `runs/p35-v1.x-1..3`, 코드 diff = `git diff <이전 단계 commit> <commit> -- services/order`.

사다리 표에서 제외한 run: `runs/p35-v1.1-oom-1`(Metaspace OOM), `runs/p35-v1.1-stale-1`(runId 재사용) — `docs/reports/phase3.5.md` 6절.

## 3.6 결함 카탈로그 v1 + New v2

기준선 `phase3.5-v1.4`, corpus v2.1(60 pair/run, learn 25 · eval 35), VU=3 ×3, 엔진 `engine-v1.2`(F1 이후 D-6 귀속 규칙, F2~F9의 사전 등록 엔진). 기대 판정은 run 전에 `docs/fault-expectations.json`에 등록. 상세 `docs/fault-catalog.md`, `docs/reports/phase3.6.md`.

| 변형 | 브랜치·commit | 이미지(new) | runs | 변경 클래스 | 기대(target) | 실제(target) | 탐지 | 정상 경로 오탐 | UNC learn/eval | 규칙 수(생성) | eval UNC 규칙 전→후 | B0 / B1 / C 가시성 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | `phase3.5-v1.4` | phase3.5-v1.4 | `runs/p36-base-1..3` | — | F0: R000047 CV, R000048 SAME | 59 SAME + R000047 CV ×3 | (F0 관측) | — | 0/0 | 0 | 0→0 | B0 DIFF 1 / B1 DIFF 1 / C CV 1 |
| F1 | `fault/F1` `da92b8e` | phase3.6-F1 | `runs/p36-F1-1..3` | `OrderService` | R000008 CV | R000008 CV ✔ | ✔ | v1.1: 1(R000007 세션 귀속) / v1.2: 0 | 0/0 | 0 | 0→0 | B0 ✔ / B1 ✘ / C ✔ |
| F2 | `fault/F2` `a131294` | phase3.6-F2 | `runs/p36-F2-1..3` | `Order` | 27 pair CV + dbstate | 27/27 CV, dbstate 위반 | ✔ | 0 | 0/0 | 0 | 0→0 | B0 ✔ / B1 ✔ / C ✔ |
| F3 | `fault/F3` `12482f0` | phase3.6-F3 | `runs/p36-F3-1..3` | `OrderEventPublisher` | 첫 결제 7 pair CV | 7/7 CV | ✔ | 0 | 0/0 | 0 | 0→0 | B0 ✔ / B1 ✘ / C ✔ |
| F4 | `fault/F4` `f83e211` | phase3.6-F4 | `runs/p36-F4-1..3` | `OrderService` | R000037·R000038 CV + dbstate | 2/2 CV, dbstate 위반 | ✔ | 0 | 0/0 | 0 | 0→0 | B0 ✔ / B1 △(1/2) / C ✔ |
