# phase3.0 — 사전 점검

## 0. 결정 필요 사항

**D-1. 계획의 빌드·런타임 전제와 실제 스택이 다르다.** phase3-plan은 Gradle, Spring Framework 6.1+, Jackson 2를 전제로 쓰였고 3.8 v3b를 "Spring Boot 4로 교체"로 둔다. 실제 레포는 **Maven, Spring Boot 4.1.1(Framework 7.0.9), Hibernate 7.4.5, Jackson 3.1.5(`tools.jackson`)** 이다(1절 표). 아래 세 가지를 정해야 3.1을 시작할 수 있다.

| # | 질문 | 선택지 | 추천 |
|---|---|---|---|
| D-1a | 빌드 도구 | (A) Maven 유지 + `kotlin-maven-plugin`(spring·jpa 컴파일러 플러그인) / (B) Gradle로 이전 | **A** — 혼합 빌드가 Boot 4.1.1에서 동작함을 실측(6절). 이전은 Phase 3 범위 밖 작업이고 Phase 2 이미지·스크립트가 Maven 기준 |
| D-1b | `poc.evidence`의 JSON 라이브러리 | (A) 지금처럼 Jackson 3 `JsonMapper`를 **패키지 안 private 고정 인스턴스**로(앱 빈 미사용) / (B) 계획 문구대로 Jackson 2 `ObjectMapper` — 클래스패스에 Jackson 2는 `jackson-annotations` 2.21뿐이라 `jackson-databind` 2를 명시 의존으로 추가해야 함 | **A** — 계획의 요구(앱 빈 공유 금지, Kotlin 모듈 등록에 영향 없음)는 이미 충족. Coupon도 Boot 4라 같은 Jackson 3. 계획 3절의 "Jackson 2" 문구는 "Boot 기본 Jackson"으로 읽는다 |
| D-1c | 3.8 v3b "Spring Boot 4" | 이미 Boot 4.1.1이라 해당 실험이 성립하지 않음. (A) v3b 삭제, v3a(JDK만, 17 → 21/25)만 선택 과제로 / (B) v3b를 다른 런타임 교체(예: Boot 4.1 → 4.0 다운그레이드, Hibernate 마이너 변경)로 재정의 / (C) 3.8 전체 삭제 | **A** — 3.8은 원래 선택이고 "제외해도 Phase 3 결론에 영향 없음"(계획 3.8) |

**D-2. kind 메모리가 Phase 3 구성을 올리기에 부족하다.** Docker VM 7.65GiB 중 사용 4.69GiB(61%), 노드 `available` 2,471MiB. Phase 3 추가분 추정은 스택당 Coupon 앱(Order 실측 590MiB 기준) + Coupon MySQL(470MiB) + sidecar(~80MiB) + Kafka(0.6~1GiB) = **1.7~2.1GiB × 2스택 = 3.5~4.3GiB** (추정 근거 `docs/reports/logs/phase3.0-resources.txt`).

| 선택지 | 내용 | 영향 |
|---|---|---|
| (A) Docker Desktop 메모리 증설 (추천) | 호스트 16GiB 중 Docker VM을 **12GiB 이상**으로. 사용자가 Docker Desktop 설정에서 변경 → kind 재시작 필요 여부 확인 | 계획 그대로(스택별 브로커, D19) |
| (B) 공유 브로커 + 토픽 접두사 | 계획 3.3·D19의 후퇴안. Kafka 1개 절약(0.6~1GiB) | Kafka가 스택 축 격리의 예외 → isolation-proof에 명시. 이것만으로는 여유가 부족할 수 있음 |
| (C) JVM heap 상한 | Order·Coupon·Kafka에 `-Xmx`(예: 앱 384m, Kafka 512m) | (A)·(B)와 병행 가능. 앱 이미지·매니페스트 변경이라 base A/A 재확인 필요 |

## 1. 단계 목표와 끝난 기준별 PASS/FAIL

목표: 3.1 착수 전에 버전·자원·직렬화 방식을 확인하고 Phase 2 잔여를 정리한다.

| 기준 | 결과 | 근거 |
|---|---|---|
| 버전 표 | PASS | 아래 표. `docs/reports/logs/phase3.0-deps.txt` |
| Spring Framework 6.1+ (`TransactionExecutionListener`) | PASS — 7.0.9 | `spring-tx-7.0.9.jar`에 `org/springframework/transaction/TransactionExecutionListener.class` 존재. Boot 4.1.1 `spring-boot-transaction`에 `TransactionManagerCustomizer`·`ExecutionListenersTransactionManagerCustomizer` 존재(리스너 빈을 트랜잭션 매니저에 붙이는 Boot 경로) → 계획 7절 "Framework < 6.1 폴백" 불필요 |
| Kotlin 플러그인 추가 가능 여부 | PASS | Boot 4.1.1 parent + `kotlin-maven-plugin`(BOM Kotlin **2.3.21**) + `spring`·`jpa` 컴파일러 플러그인으로 Java↔Kotlin 혼합 컴파일 exit 0. `@Component` Kotlin 클래스가 open, Kotlin 엔티티에 no-arg 생성자 생성 확인. `docs/reports/logs/phase3.0-kotlin-probe.txt` |
| `poc.evidence` JSON 생성 방식 보고 | PASS | 아래 ObjectMapper 표 |
| kind 호스트 자원 | **FAIL(부족)** — 0절 D-2 | `docs/reports/logs/phase3.0-resources.txt` |
| Phase 2 잔여: `phase2-done` 태그 | PASS | 태그 `phase2-done` → `e9d4676`, 원격 `refs/tags/phase2-done^{}` = `e9d46768…` |
| Phase 2 잔여: phase2-result 4절 (g) 관측 분리 | PASS(해석 포함, 5절) | `docs/phase2-result.md` 4절 (g) |
| Phase 2 잔여: README 문서 목록 | PASS | `README.md` 문서·디렉터리 목록 갱신 |
| `docs/references/industry-cases-phase3.md` | PASS | 계획 반영 커밋 `1991511`에서 생성 |

**버전 표**

| 항목 | 값 | 출처 |
|---|---|---|
| 빌드 도구 | **Maven** 3.9 (빌드 이미지 `maven:3.9-eclipse-temurin-17`), Gradle 아님 | `services/order/Dockerfile`, `pom.xml` |
| Spring Boot | 4.1.1 | `spring-boot-starter-parent` |
| Spring Framework | 7.0.9 | `spring-core`·`spring-tx`·`spring-aop` 7.0.9 |
| JDK (빌드·런타임) | 17 (Eclipse Temurin), `java.version` 17 | Dockerfile, pom |
| Hibernate ORM | 7.4.5.Final | `hibernate-core` |
| Jackson | databind·core **3.1.5** (`tools.jackson`), Jackson 2는 `jackson-annotations` 2.21만 | deps |
| AspectJ | `aspectjweaver` 1.9.25.1 (클래스패스에 있음 → Boot `AopAutoConfiguration`으로 `@Aspect` 사용 가능) | deps |
| MySQL Connector/J | 9.7.0 | deps |
| Kotlin (BOM 관리) | 2.3.21 | `spring-boot-dependencies-4.1.1.pom` |
| Spring for Apache Kafka / kafka-clients (BOM 관리) | 4.1.1 / 4.2.1 | 같은 BOM (아직 의존성 없음) |

**ObjectMapper 표 — `poc.evidence`의 JSON 생성**

| 위치 | 방식 | 앱 ObjectMapper 빈 공유 | 계획 요구와의 관계 |
|---|---|---|---|
| `poc/evidence/EvidenceFilter.java:51` | `private final JsonMapper jsonMapper = JsonMapper.builder().build()` (Jackson 3, 기본 설정 고정 인스턴스) | **공유 안 함** | "패키지 안 private 고정 매퍼, 앱 빈 미사용" 충족. 라이브러리 버전만 계획 문구(Jackson 2)와 다름 → D-1b |
| `poc/evidence/*` 그 외 | JSON 직렬화 없음(Sender는 바이트만 전송) | — | — |
| (참고) `poc/order/requestlog/RequestLogFilter.java:41` | 같은 방식의 private `JsonMapper` | 공유 안 함 | 로그용, Evidence 아님 |

## 2. 변경 파일과 커밋 해시

| 커밋 | 내용 |
|---|---|
| `e9d4676` phase3.0: Phase 2 잔여 — phase2-result 4절 (g) 관측 분리, README 문서 목록 | `docs/phase2-result.md`(4절 (g) 추가), `README.md` |
| 태그 `phase2-done` | `e9d4676` (annotated) |
| (이 보고서 커밋) | `docs/reports/phase3.0.md`, `docs/reports/logs/phase3.0-{deps,resources,kotlin-probe}.txt` |

코드·매니페스트 변경 없음. Kotlin 시험은 scratchpad에서만 했다(레포에 남기지 않음).

## 3. 실행 명령과 주요 출력

```
$ mvn -q dependency:list -DincludeScope=runtime   (services/order)   → docs/reports/logs/phase3.0-deps.txt
$ unzip -l spring-tx-7.0.9.jar | grep TransactionExecutionListener  → 존재
$ unzip -l spring-boot-transaction-4.1.1.jar | grep TransactionManagerCustomizer → TransactionManagerCustomizer, ExecutionListenersTransactionManagerCustomizer
$ (scratchpad) mvn -q compile  — Kotlin 혼합 빌드 → exit 0           → docs/reports/logs/phase3.0-kotlin-probe.txt
$ docker info / docker stats / free -m / crictl stats              → docs/reports/logs/phase3.0-resources.txt
  Docker VM CPUs=10 MemTotal=7.65GiB, 노드 사용 4.69GiB(61%), available 2,471MiB, 컨테이너 working set 합계 4,011MiB
  (order 590/588, mysql 473/473, wiremock 236/233, istio-proxy 164/161, kube-apiserver 525 …)
$ git tag -a phase2-done && git push origin phase2-done
```

## 4. Legacy/New 비교 결과와 수치

해당 없음(사전 점검, run 없음).

## 5. 지시와 다르게 구현한 것과 이유

- **"phase2-result 4절 (g) 관측 분리"의 해석**: 정의된 문서가 없어 architecture §5.1의 "관측 트래픽 제외 규칙"(Evidence POST를 비교·span 대상에서 제외)을 Phase 2 실측으로 확인한 내용을 (g)로 묶은 것으로 해석했다 — `/_evidence` 미러 안 됨(2.3), 앱 span에 Evidence POST 없음·별도 단일 span trace(2.4a), `X-Evidence-Internal`, Evidence에서 `x-request-id`·Host 제외, 응답 시간 분리. 다른 뜻이었다면 알려 주면 고치고 태그를 옮긴다.
- 태그는 (g)·README 커밋(`e9d4676`) 위에 달았다(Phase 2 결과 문서가 확정된 시점).

## 6. 발견한 문제·해결·남은 한계

- **계획 전제와 실제 스택 불일치**(0절 D-1): 계획이 Boot 3.x/Gradle/Jackson 2 기준으로 쓰였다. 기능상 필요한 것(`TransactionExecutionListener`, Boot 리스너 등록 경로, AOP, Kotlin 혼합 빌드, private 고정 매퍼)은 현재 스택에서 모두 가능함을 확인했다. 결정은 도구·문구 정합성 문제다.
- **메모리 부족**(0절 D-2): 3.1(Evidence v1)은 현재 구성으로 진행 가능하다. 부족은 3.2(Coupon)·3.3(Kafka)부터 문제가 된다. 따라서 D-2는 3.2 착수 전까지만 정해지면 된다.
- Kafka 이미지(`apache/kafka`)와 Kotlin 의존성은 아직 받지 않았다. "런타임 다운로드 금지" 규칙대로 Kafka 이미지는 3.3에서 호스트 pull → `docker save --platform` → `kind load image-archive`로 넣는다.
- `ingressgateway` 인증서는 이후 갱신이 확인돼야 한다(다음 run의 preflight가 검사).
