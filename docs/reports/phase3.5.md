# Phase 3.5 보고서 — New v1 사다리 (Order 점진 Kotlin 전환)

- 작업일: 2026-10-14
- Legacy 고정: `order-app:phase3.3-base`, Coupon 양쪽 `coupon-app:phase3.3-base`
- 진행 상태: **v1.1에서 중단 — 결정 필요 1건**(배포 자원 설정). 엔진 소수정(0)은 완료

## 0. 결정 필요 사항

**D-5 Order JVM Metaspace 상한(`-XX:MaxMetaspaceSize=128m`)을 어떻게 할지**

v1.1 첫 run에서 New Order가 `java.lang.OutOfMemoryError: Metaspace`(28건)를 냈다. 처음 실패한 것은 첫 결제 때 지연 생성되는 Kafka producer 클래스 로딩이었다(15:24:33 producer network thread가 죽음). 그 뒤로 order.paid 발행이 `ack: failed`, 5xx 9건, Kafka 소비 Evidence 미도착으로 degraded 7세션이 나왔다. 코드 문제가 아니라 자원 상한 문제다.

실측(`jcmd VM.metaspace`, run 직후):

| | 클래스 | Metaspace 사용 | 상한 |
|---|---|---|---|
| legacy (Java, phase3.3-base) | 26,538 | **125.85 MB (99%)** | 128 MB |
| new (v1.1, Kotlin stdlib·reflect·jackson-module-kotlin) | 27,596 | 127.31 MB (상한 도달, OOM) | 128 MB |

Legacy도 이미 99%라 사실상 여유가 없었다. 128m은 3.0 D-2 (C)에서 "실측 후 조정 가능"으로 둔 값이다. Kotlin 런타임(+약 1,000 클래스)이 들어오면 v1.2~v1.4에서는 더 늘어난다.

선택지:
- **(A) 권장** — base 매니페스트(양쪽 공통)의 상한을 **192m**으로 올리고, 메모리 limit 768Mi는 그대로 둔다(heap 384m + metaspace 192m + 그 밖). 양쪽 JVM 설정이 같게 유지된다. legacy **이미지**는 그대로지만 legacy **매니페스트**가 바뀌므로(지시 "legacy 매니페스트 무변경"과 충돌), base 이미지로 A/A 3회(VU=3)를 다시 돌려 게이트를 확인한 뒤 v1.1을 재실행한다
- (B) new overlay에만 192m — legacy 매니페스트는 그대로지만 두 스택의 JVM 설정이 달라지고, legacy는 99%에 머문다
- (C) 상한을 없앤다(`MaxMetaspaceSize` 제거) — 메모리 limit 768Mi가 유일한 상한이 된다

## 1. 끝난 기준별 결과

| 기준 | 결과 | 근거 |
|---|---|---|
| (0) 엔진 id 값 마스킹, engine-v1.1, p33-1..3 전 pair SAME | PASS | 커밋 `94b577b`. p33-1·2·3 × B0·B1·C 모두 `{SAME: 58}`, pytest 27 passed(`test_id_value_masked_but_key_compared` 추가) |
| v1.1 코드 커밋·이미지·배포 | PASS | `fd839d6`, `order-app:phase3.5-v1.1`, new overlay만(`kubectl kustomize`: legacy order=phase3.3-base, new order=phase3.5-v1.1, coupon 양쪽 phase3.3-base) |
| `poc.evidence` 수정 0줄 | PASS | `git diff 98c9356 -- services/evidence-collector` 0줄 |
| v1.1 3 run, Undelivered 0, degraded 0 | **FAIL(중단)** | p35-v1.1-1: degraded 7세션, barrier new 누락 7 → run.sh가 iteration 1에서 중단. `logs/phase3.5-v1.1-run.txt`, `logs/phase3.5-v1.1-verify.txt` |
| v1.2~v1.4 | 미착수 | 0절 결정 대기 |

## 2. 변경 파일·커밋

| 커밋 | 내용 |
|---|---|
| `94b577b` phase3.4: id 값 마스킹 | `engine/normalize.py`(`mask_ids`), `engine/verdict.py`(engine-v1.1, B0도 마스킹), `engine/tests/test_engine.py` |
| `fd839d6` phase3.5-v1.1: PaymentGatewayClient를 Kotlin으로 | `services/order/pom.xml`(Kotlin 혼합 빌드, kotlin-stdlib·reflect, jackson-module-kotlin), `PaymentGatewayClient.java` → `src/main/kotlin/poc/order/PaymentGatewayClient.kt`, `deploy/k8s/new/kustomization.yaml`(images) |
| (이 커밋) phase3.5-v1.1: 중단 보고 | `docs/reports/phase3.5.md`, `docs/reports/logs/phase3.5-v1.1-*.txt`, `docs/phase3-plan.md`(구현 시 확정 (3.5)) |

## 3. 실행 명령·주요 출력

```
docker build -f services/order/Dockerfile -t order-app:phase3.5-v1.1 services/ → docker save → kind load image-archive
kubectl apply -k deploy/k8s/new          → deployment.apps/order configured (2/2)
k6/run.sh --run-id p35-v1.1 --iterations 3 --vus 3      → exit 1 (iteration 1)
  DEGRADED S001 R000003 / S002 R000007 / S003 R000012 / S006 R000029 / S007 R000033 / S009 R000041: settle new/0.e1 미도착
  DEGRADED S010 R000044: settle new/0.h1 미도착
  barrier new: 기대 47, 도착 40, 누락 7 → export만 하고 중단
new order 로그: TimeoutException "Topic order.paid not present in metadata after 5000 ms"(producer 스레드 사망 뒤)
               → OutOfMemoryError: Metaspace 28건        (logs/phase3.5-v1.1-oom.txt)
jcmd VM.metaspace (jdk-tools 임시 이미지로 측정): legacy 125.85/128 MB, new 127.31/128 MB
```

p35-v1.1-1 Evidence 요약: legacy 47건 발행 6건 모두 ack ok / new 40건 발행 3건 모두 ack failed, 5xx 9건. 이 run은 판정하지 않았다(run-meta 없음, 인프라 실패 run).

## 4. Legacy/New 비교

판정 전 단계에서 중단 — 비교 표 없음. Kotlin 전환 자체로 인한 차이(requestBodyHash 등)는 실패 전 요청에서 관찰되지 않았다(R000003 charge `requestBodyHash` 양쪽 동일, 응답 200).

## 5. 지시와 다르게 구현한 것

- jackson-module-kotlin을 v1.4가 아니라 **v1.1**에서 추가 — 지시의 규칙("Kotlin DTO를 역직렬화하는 첫 단계")대로 하면 `PaymentGatewayClient.ChargeResponse`가 v1.1에서 처음이다
- "phase3.3 기준" diff 기준점은 태그가 없어 phase3.3 마지막 커밋 `98c9356`을 썼다

## 6. 문제·해결·한계

- **문제**: Metaspace 128m 상한 초과 → 0절. 해결은 결정 대기
- **측정 도구 흔적**: `jcmd`를 쓰려고 임시 이미지 `jdk-tools:phase3.5`(로컬 빌드 JDK, kind에 로드)로 ephemeral container를 붙였고, JDK를 대상 컨테이너 `/tmp/jdk`에 복사했다. legacy·new order pod 스펙에 ephemeral container 기록이 남는다(pod를 재생성하면 사라짐). 0절 (A)든 (B)든 다음 run 전에 pod가 재생성된다
- 현재 new order pod는 Metaspace OOM 상태 — 다음 배포 전까지 쓰지 않는다
