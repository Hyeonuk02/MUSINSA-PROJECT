# 관측·발견 로그 (findings)

> decision-log(결정)와 분리해 **발견만** O1, O2 … 번호로 누적한다. 결정으로 이어진 것은 후속 칸에 D번호, 결함·시험으로 이어진 것은 F번호.
> 항목: 날짜·단계 / 무엇을 봤나(한 줄) / 근거(run·로그·Evidence 경로) / 왜 중요한가 / 후속.
> 단계 보고서 6절에 적는 발견은 여기에도 적는다(CLAUDE.md 보고 규칙). 2026-10-14에 Phase 3 보고서 3.1~3.7·fault-catalog에서 소급해 채웠다.

### O1. 트랜잭션 콜백 순서가 계획 가정과 다르다 — 동기화 afterCommit이 리스너 afterCommit보다 먼저
- 날짜·단계: 2026-10-13, 3.1
- 봤다: `beforeCommit`(동기화) → 리스너 `beforeCommit`(COMMIT_BEGIN) → doCommit → 동기화 `afterCommit` → `afterCompletion` → 리스너 `afterCommit`(COMMITTED). `@TransactionalEventListener(AFTER_COMMIT)`의 발행은 COMMIT_BEGIN과 COMMITTED **사이** seq를 받는다
- 근거: `docs/reports/logs/phase3.1-tx-callback-order.txt`, 3.3 실측 `COMMIT_BEGIN(4) < UPDATE(5) < PUBLISH(6) < COMMITTED(7)`(p33-1 R000029)
- 왜 중요: "커밋 전 발행"을 콜백 순서나 `isActualTransactionActive()`로 판정하면 흔들린다. COMMIT_BEGIN 기준 seq 비교는 순서와 무관하게 성립
- 후속: D16(단일 seq + COMMIT_BEGIN), F3

### O2. 쓰기 SQL(flush)은 COMMIT_BEGIN 뒤에 나간다
- 날짜·단계: 2026-10-13, 3.1
- 봤다: 결제의 `UPDATE orders`(seq 5)가 COMMIT_BEGIN(seq 4) 뒤 — Hibernate가 doCommit 안에서 flush
- 근거: `docs/reports/phase3.1.md` 6절, p33·p35 결제 Evidence 타임라인
- 왜 중요: "커밋 전 SQL" 같은 판정을 seq로 하면 오판한다. 쓰기 집합 비교(순서 무관)는 영향 없음
- 후속: Normalization v1의 writeSet은 정렬 multiset(3.4)

### O3. Legacy(Java)도 Metaspace 128m 상한의 99%였다
- 날짜·단계: 2026-10-14, 3.5
- 봤다: `jcmd VM.metaspace` legacy order 125.85 / 128 MB(26,538 클래스). Kotlin 런타임 몇 MB에 New가 넘쳤다
- 근거: `docs/reports/phase3.5.md` 6절, `docs/reports/logs/phase3.5-v1.1-oom-applog.txt`
- 왜 중요: 3.0에서 "실측 후 조정 가능"으로 둔 자원 상한이 실측 없이 굳어 있었다. 결함이 아니라 환경이 비교를 깨뜨릴 수 있다
- 후속: D22(256m·limits 1Gi), 단계마다 Metaspace 참고 측정(new order +6.4~7.4 MB, +1,800~2,300 클래스)

### O4. 판정에 들어가면 안 되는 run을 파이프라인이 판정 전에 걸렀다 — OOM run, stale run
- 날짜·단계: 2026-10-14, 3.5
- 봤다: ① Metaspace OOM run(`runs/p35-v1.1-oom-1`): degraded 7·ack failed 3·5xx 9 → barrier 미달로 run.sh가 export만 하고 중단 ② 같은 runId 재사용 run(`runs/p35-v1.1-stale-1`): Store에 남은 이전 Evidence 100건 때문에 k6 완료 폴링이 New 완료 전에 다음 요청을 보냄(New 완료 15:47:31.00 > 다음 요청 도착 15:47:30.39) → 404 → degraded 4 → 다시 걸러짐
- 근거: `docs/reports/logs/phase3.5-v1.1-{oom,stale}-*.txt`, `docs/phase3-metrics.md` 5절
- 왜 중요: degraded·barrier가 "판정할 자격이 없는 run"의 문지기로 동작했다. 두 run 모두 엔진에 들어갔다면 Kotlin 전환 결함처럼 보였을 것
- 후속: run.sh preflight "Store에 같은 runId Evidence 0건"(`47d7191`), D22

### O5. Order의 Java → Kotlin 전면 전환은 원문(B0)까지 행동 차이 0
- 날짜·단계: 2026-10-14, 3.5
- 봤다: v1.1~v1.4 각 3 run, C·B0·B1 전 pair SAME(58/58). SQL 원문, 응답 바이트(Java record ↔ Kotlin data class 직렬화 순서 동일), `order.paid` 페이로드, 트랜잭션 이름, callTree 모두 같음
- 근거: `docs/reports/phase3.5.md`, `runs/p35-v1.{1..4}-*`, `docs/phase3-metrics.md`(arm 표)
- 왜 중요: "전환이 안전하다"의 증거가 이 corpus 범위에서 행동 Evidence로 나왔다. 흔적은 Metaspace에만(O3). 단 corpus가 닿는 범위까지(O6)
- 후속: 새 기준선 `phase3.5-v1.4`(3.6·Phase 4)

### O6. 예측했던 잠재 차이(sku 없음)가 실측으로 확인됐다 — Legacy 409 / Kotlin 400
- 날짜·단계: 예측 2026-10-14 3.5(6절) → 실측 3.6 baseline
- 봤다: 3.5에서 코드 리뷰로 "sku 없는 항목은 Java 409, Kotlin 400일 것"이라 적었고, corpus v2.1 S011(R000047)을 넣자 정확히 그렇게 나왔다(CV: status·content-type·writeSet·transactions). 그 전까지 사다리 run은 전부 SAME이었다
- 근거: `runs/p36-base-*` R000047, `docs/fault-catalog.md` F0, `docs/reports/phase3.6.md` 1.0
- 왜 중요: **corpus 커버리지 = 검증 범위**. 차등 검증은 corpus가 닿지 않는 입력의 차이를 보지 못한다. 현업 Kotlin 전환기 두 곳 모두 null 처리를 최대 함정으로 꼽았다(references/kakaopay·woowahan-kotlin-migration.md)
- 후속: F0(baseline 기지 차이), corpus v2.1, Phase 4 corpus 보강

### O7. Legacy의 `onConflict`가 무관한 무결성 위반을 "주문 키 중복"으로 응답한다
- 날짜·단계: 2026-10-14, 3.6 baseline
- 봤다: Legacy R000047(sku 없음)은 항목 INSERT 단계의 무결성 위반을 `@ExceptionHandler(DataIntegrityViolationException)`가 잡아 **409 `{"error":"ORDER_KEY_EXISTS","orderKey":null}`**로 응답. 키 중복이 아닌데 키 중복 코드, orderKey는 null
- 근거: `runs/p36-base-1/legacy.json` R000047, `docs/fault-catalog.md` F0
- 왜 중요: 비교 대상인 **Legacy 자체의 결함**을 차등 검증이 드러냈다. New(400)가 "틀린" 게 아니라 Legacy 응답이 계약상 잘못이다 — CV가 곧 New 결함이라는 해석은 성립하지 않는 경우가 있다
- 후속: Phase 4 — CV 리뷰에서 "Legacy 결함" 분류 필요성 검토

### O8. 세션 검사 위반이 같은 키를 공유한 정상 pair에까지 퍼졌다
- 날짜·단계: 2026-10-14, 3.6 F1
- 봤다: F1(멱등 검사 제거)에서 겨냥한 R000008과 함께 정상 첫 결제 R000007도 CV — 사유는 `gateway_calls_per_idem_key_le_1[idem-R000007]: legacy 1 / new 2` 하나뿐
- 근거: `runs/p36-F1-*/verdict-engine-v1.1.json`, `docs/reports/logs/phase3.6-F1-check-engine-v1.1.txt`
- 왜 중요: 세션 범위 검사는 "어디서 울렸나"와 "어느 요청이 다르게 행동했나"가 다르다. 표시 위치가 틀리면 리뷰 범위가 넓어진다
- 후속: D20(engine-v1.2 귀속 규칙) — F1 결과를 본 뒤 일반화했다는 한계를 함께 기록

### O9. 순서만 다른 결함 — F3(커밋 전 발행)은 타임라인 축 하나로만 보인다
- 날짜·단계: 2026-10-14, 3.6 F3
- 봤다: New `PUBLISH(3) < COMMIT_BEGIN(5)` vs Legacy `COMMIT_BEGIN(4) < PUBLISH(6)`. 응답·SQL 집합·callTree·이벤트 내용·ack·소비 Evidence 전부 같음 — 위반은 `publish_after_commit_begin` 하나
- 근거: `runs/p36-F3-1` R000003, `docs/reports/phase3.6.md` 1.3
- 왜 중요: 단일 seq 타임라인(D16)이 없으면 보이지 않는 결함 유형. B1 0/7
- 후속: D16 검증 사례, 3.7 B1 미탐 목록

### O10. 롤백 누락(F4)은 트랜잭션 축으로만 보이고, 결과는 다음 요청과 dbstate로 번진다
- 날짜·단계: 2026-10-14, 3.6 F4
- 봤다: R000037(USED 쿠폰 주문) 응답 400·SQL·쓰기 집합 동일, 차이는 transactions outcome(ROLLED_BACK → COMMITTED)뿐. 같은 주문 조회 R000038이 404 → 200, dbstate orders·order_items +1. 사전 기대에 적은 writeSet 차이는 없었다(양쪽 모두 INSERT 실행)
- 근거: `runs/p36-F4-*`, `docs/reports/phase3.6.md` 1.4
- 왜 중요: 결함이 일어난 요청과 증상이 드러나는 요청이 다르다. 쓰기 집합이 아니라 트랜잭션 결과를 기록해야 잡힌다. 현업 전환기(우아한형제들)가 롤백 규칙 변화를 함정으로 기록한 것과 같은 축
- 후속: B1 반 칸(3.7 매트릭스)

### O11. B1(응답 canonical + SQL)이 못 잡는 결함 목록
- 날짜·단계: 2026-10-14, 3.7
- 봤다: target pair 기준 B1 미탐 13 — F1 1(R000008), F3 7(첫 결제 전부), F4 1(R000037), F9 4(쿠폰 주문 생성 전부). 모두 외부 호출·타임라인·트랜잭션·hop 축에만 흔적
- 근거: `docs/phase3-metrics.md` arm 표, `docs/reports/phase3.7.md` 2·3절
- 왜 중요: "응답 비교 + SQL 비교"까지 해도 멱등성·발행 시점·롤백·중복 호출 결함은 지나간다 — 사이드이펙트 축(D18·D16·D15)의 존재 이유
- 후속: Phase 4 스코핑 평가에서 축별 기여 측정

### O12. settle 의미를 고치지 않았다면 F7 run은 판정 전에 멈췄다
- 날짜·단계: 2026-10-14, 3.6 F7
- 봤다: F7에서 New 결제가 타임아웃 → 발행 없음 → New에 `R000041/0.e1` 없음. 이전 규칙(settle = 기대 집합)이면 k6 degraded + barrier 미달로 run 중단. D19 보완 뒤에는 settleTimeouts 지표 1·`settleUndeclared`로 남고 엔진이 hop 집합 차이(CV)로 판정
- 근거: `docs/reports/logs/phase3.6-F7-run.txt`, `runs/p36-F7-*/barrier.json`
- 왜 중요: "기대한 Evidence가 없다"는 전달 실패일 수도, 결함의 증상일 수도 있다. 부모가 선언했는지로 둘을 가른다
- 후속: D19 보완(2026-10-14)

### O13. VU=3에서 DB auto id가 세션 사이에 엇갈린다
- 날짜·단계: 2026-10-13, 3.4
- 봤다: 정규화 없이 판정하자 p33-1 eval 8 pair가 `response.valueChanged id 1→3` — 세션 간 생성 순서가 스택마다 달라 auto id가 교차
- 근거: `docs/reports/phase3.4.md` 6절
- 왜 중요: 동시성이 있으면 결정론적 재생에서도 auto id는 같지 않다. 값만 가리고 키 유무는 비교해야(engine-v1.1) id 누락 결함은 여전히 잡힌다
- 후속: Normalization v1(3.4), engine-v1.1 id 값 마스킹(3.5)

### O14. 사다리 커밋의 diff에는 서비스 코드 말고도 overlay 이미지 태그(deploy)가 들어 있고, Java → Kotlin 이동은 rename으로 안 잡힌다
- 날짜·단계: 2026-10-14, 4.0
- 봤다: `git diff -M --name-status <v1.x>~1..<v1.x>`가 네 단계 모두 `M deploy/k8s/new/kustomization.yaml`(new order 이미지 태그) + 서비스 파일 `D *.java` / `A *.kt`(같은 FQCN). 계획 1절의 범위 `phase3.3-base..phase3.5-v1.x`는 그 사이의 엔진·문서·run.sh·base 매니페스트 커밋까지 포함한다. 결함 브랜치(`phase3.5-v1.4..fault/F<n>`)는 서비스 코드 1~2 파일만
- 근거: `docs/reports/logs/phase4.0-inputs.txt`, `scoping/tests/test_common.py::test_name_status_ladder_and_fault_shapes`
- 왜 중요: D24를 글자 그대로 적용하면 deploy 변경 → 전역, 클래스 삭제(D) → 전역이라 사다리 4단계가 모두 전역이 된다(계획 4.2 기대: v1.2·v1.3은 order.* 9세션). 실험을 위해 한 커밋에 배포 설정을 함께 바꾼 것이 스코핑 결과를 바꾼다 — 실제 레포에서도 "코드 + 배포 매니페스트" 동시 커밋은 흔하다
- 후속: 4.0 보고서 0절(사다리 diff 범위), 구현 시 확정(같은 FQCN D+A = 수정)
