# Phase 3.5 보고서 — New v1 사다리 (Order 점진 Kotlin 전환)

- 작업일: 2026-10-14
- Legacy 고정: `order-app:phase3.3-base`, Coupon 양쪽 `coupon-app:phase3.3-base`. 엔진 `engine-v1.1`
- 진행 상태: base 게이트 재확인 PASS → **v1.1 PASS** → v1.2 진행 중 (단계마다 이 문서에 절을 추가한다)
- 누적 결과 표: `docs/phase3-result.md`

## 0. 결정 필요 사항

없음. (D-5 Metaspace는 (A) 256m·limits 1Gi로 결정되어 반영)

## 1. 끝난 기준별 결과

### 1.0 엔진 소수정 · 설정 변경 · 게이트

| 기준 | 결과 | 근거 |
|---|---|---|
| id 값 마스킹, engine-v1.1, p33-1..3 전 pair SAME | PASS | `94b577b`. p33-1·2·3 × B0·B1·C `{SAME: 58}`, pytest 27 passed |
| Metaspace 256m·limits 1Gi (base 공통, Order·Coupon) | PASS | `d1b283e`. 배포 후 4개 Deployment limits 1Gi, `JAVA_TOOL_OPTIONS ... -XX:MaxMetaspaceSize=256m` |
| base A/A 재확인 `p35-base` (VU=3 ×3) | PASS | 3 run × C·B0·B1 모두 `{SAME: 58}`, Undelivered 0, degraded 0, dbstate OK, verify 3/3 PASS, run-meta `dirty: false`(rev `d1b283e`), order legacy·new = phase3.3-base. `logs/phase3.5-base-{run,verify,verdict}.txt` |
| A/A 뒤 Metaspace 측정 | 기록 | 아래 표. `logs/phase3.5-base-metaspace.txt` |

| (p35-base 뒤) | Metaspace 사용 | 상한 | 클래스 |
|---|---|---|---|
| legacy order | 125.02 MB | 256 MB | 26,701 |
| legacy coupon | 123.31 MB | 256 MB | 26,338 |
| new order | 125.01 MB | 256 MB | 26,688 |
| new coupon | 123.17 MB | 256 MB | 26,323 |

### 1.1 v1.1 — PaymentGatewayClient (Kotlin)

| 기준 | 결과 | 근거 |
|---|---|---|
| commit 1 · 이미지 1 | PASS | `fd839d6`, `order-app:phase3.5-v1.1`(재빌드 없이 재사용). 변경 클래스 1(`PaymentGatewayClient`) + pom(Kotlin 빌드) |
| `poc.evidence` 수정 0줄 | PASS | `git diff 98c9356 -- services/evidence-collector` 0줄 |
| 3 run, Undelivered 0, degraded 0 | PASS | `p35-v1.1-1..3` run.sh exit 0, verify 3/3 PASS, run-meta `dirty: false`(rev `47d7191`), images.order legacy=phase3.3-base / new=phase3.5-v1.1 |
| 모든 diff가 4분류로 설명됨 | PASS (diff 0) | C `{SAME: 58}` ×3, B0·B1 DIFF 0 ×3, dbstate OK. `logs/phase3.5-v1.1-verdict.txt` |
| learn 리뷰 · 규칙 | 해당 없음 | learn Uncertain 유형 0 → 라벨 0, 규칙 0 |
| 3 run 결과 동일 | PASS | 세 run 모두 SAME 58 |

v1.1 해석: Java record `ChargeRequest`를 Kotlin data class로 바꿔도 Boot JsonMapper(+jackson-module-kotlin)가 같은 순서의 JSON을 만든다 — `externalCalls.requestBodyHash`가 양쪽 동일. callTree의 `PaymentGatewayClient.charge`도 FQCN·메서드명이 그대로라 B0(원문)에서도 차이가 없다. Kotlin 전환의 흔적은 행동 Evidence가 아니라 Metaspace(+7.4 MB, +1,801 클래스)에만 남았다.

| (p35-v1.1 뒤) | Metaspace 사용 | 클래스 |
|---|---|---|
| legacy order | 126.79 MB | 26,715 |
| new order (v1.1) | **134.23 MB** | **28,516** |
| legacy / new coupon | 124.78 / 124.66 MB | 26,341 / 26,326 |

## 2. 변경 파일·커밋

| 커밋 | 내용 |
|---|---|
| `94b577b` phase3.4: id 값 마스킹 | `engine/normalize.py`, `engine/verdict.py`, `engine/tests/test_engine.py` |
| `fd839d6` phase3.5-v1.1: PaymentGatewayClient를 Kotlin으로 | `services/order/pom.xml`, `PaymentGatewayClient.java` → `.kt`, `deploy/k8s/new/kustomization.yaml` |
| `3fe2d58` phase3.5-v1.1: 중단 보고 | (이전 판 보고서 — 이 문서로 대체) |
| `d1b283e` phase3.5: Metaspace 상한 256m·limits 1Gi (base 공통) | `deploy/k8s/base/{order,coupon}.yaml`, `docs/phase3-plan.md`(D-2 아래 한 줄 + 3.5 구현 시 확정) |
| `47d7191` phase3.5: run.sh preflight — Store에 같은 runId Evidence가 있으면 중단 | `k6/run.sh` |
| (이 커밋) phase3.5-v1.1: 결과·규칙·보고서 | 이 문서, `docs/phase3-result.md`, `docs/reports/logs/phase3.5-*`, `docs/phase3-plan.md`(구현 시 확정 추가) |

## 3. 실행 명령·주요 출력

```
# 게이트: 레포 overlay는 그대로, order 이미지만 바꿔 apply
kubectl apply -k deploy/k8s/legacy
kubectl kustomize deploy/k8s/new | sed 's#order-app:phase3.5-v1.1#order-app:phase3.3-base#' | kubectl apply -f -
k6/run.sh --run-id p35-base --iterations 3 --vus 3          → exit 0
verify_sameness ×3 → PASS; verdict.py --arm C|B0|B1 ×3 → {SAME: 58}

# v1.1
kubectl apply -k deploy/k8s/new                              → order phase3.5-v1.1
k6/run.sh --run-id p35-v1.1 --iterations 3 --vus 3          → exit 0
verify_sameness ×3 → PASS; verdict C|B0|B1 ×3 → {SAME: 58}; review.py list --split learn → 유형 0
```

## 4. Legacy/New 비교

| 단계 | run | C SAME/IMP/UNC/CV | B0 DIFF | B1 DIFF | Undelivered | degraded | dbstate |
|---|---|---|---|---|---|---|---|
| base(A/A) | p35-base-1..3 | 58/0/0/0 ×3 | 0 | 0 | 0 | 0 | 일치 |
| v1.1 | p35-v1.1-1..3 | 58/0/0/0 ×3 | 0 | 0 | 0 | 0 | 일치 |

## 5. 지시와 다르게 구현한 것

- jackson-module-kotlin을 v1.1에서 추가(지시 규칙 "Kotlin DTO를 역직렬화하는 첫 단계"상 `ChargeResponse`가 v1.1)
- "phase3.3 기준" diff 기준점은 태그가 없어 `98c9356`(phase3.3 마지막 커밋)
- 게이트 run은 레포 overlay를 바꾸지 않고 렌더링 결과의 order 이미지만 치환해 apply(dirty=false 유지). 실제 이미지는 run-meta로 확인
- 지시에 없던 커밋 `47d7191`(run.sh preflight) — 6절의 두 번째 사례를 이 단계에서 고친 것

## 6. 문제·해결·남은 한계

- **환경 결함(Metaspace OOM)을 파이프라인이 잡아낸 사례** — `runs/p35-v1.1-oom-1`(첫 v1.1 run, 사다리 표 제외). New Order가 Metaspace 128m 상한에서 `OutOfMemoryError`(28건, 첫 지점은 지연 생성되는 Kafka producer 클래스 로딩). 파이프라인에는 **degraded 7세션 · `ack: failed` 3건 · 5xx 9건**으로 드러났고, barrier 미달로 run.sh가 export만 하고 멈춰 **판정에 들어가면 안 되는 run을 판정 전에 걸러냈다**. 측정해 보니 legacy(Java)도 128m의 99%(125.85 MB)라 Kotlin 런타임 몇 MB에 넘쳤다. → D-5 (A) 256m·limits 1Gi. 로그 `logs/phase3.5-v1.1-oom-{run,verify,applog}.txt`
- **runId 재사용 사고** — `runs/p35-v1.1-stale-1`(두 번째 v1.1 시도, 사다리 표 제외). OOM run 디렉터리를 옮긴 뒤 같은 runId(`p35-v1.1`)로 재실행했는데, Store에 OOM run의 Evidence 100건이 남아 있었다. k6 완료 폴링(`exists`)이 이전 Evidence를 보고 New가 R000001 생성을 끝내기 전에(New 완료 15:47:31.00, New R000002 도착 15:47:30.39) 다음 요청을 보내 New 쪽 조회·결제가 404 → 발행 없음 → 소비 Evidence 없음 → degraded 4·barrier 미달로 다시 걸러졌다. 엔진·Kotlin과 무관한 운영 실수. 해결: run.sh preflight에 "Store에 같은 runId Evidence 0건" 검사 추가(자동 삭제 없음), 그 Store run은 `DELETE /runs/p35-v1.1-1`(로컬 export는 보존)로 정리 후 재실행. 검사 동작 확인 `logs/phase3.5-preflight-runid.txt`(100건 있음 → exit 1). 로그 `logs/phase3.5-v1.1-stale-{run,verify}.txt`
- 두 실패 run 모두 Evidence 안의 runId가 `p35-v1.1-1`이라 디렉터리 이름과 달라 엔진 입력 계약 대상이 아니다(보존용)
- **측정 도구**: Metaspace는 `jdk-tools:phase3.5`(로컬 빌드 JDK 이미지, kind 로드) ephemeral container로 대상 컨테이너 `/tmp/jdk`에 JDK를 복사한 뒤 `jcmd`. pod 스펙에 ephemeral container 기록이 남는다(재배포 시 사라짐). 측정은 run이 끝난 뒤에만
