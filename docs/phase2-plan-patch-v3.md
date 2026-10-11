# Phase 2 계획 패치 (v2 → v3) — DB Evidence·큐 정책·격리 보강

> 적용 대상: `docs/phase2-plan.md`, 루트 `CLAUDE.md`, `docs/decision-log.md`, `docs/isolation-proof.md`, `docs/architecture.md` 5.1
> 원칙 유지: Phase 2는 엔진 없음. 종료 시점의 Evidence export JSON이 Phase 3 입력 계약. 이 패치는 그 계약에 `dbAccess`를 넣고 수집 안정성을 보강하는 것뿐이며 비교·판정은 추가하지 않는다.

---

## 1. `docs/phase2-plan.md` 수정

### 1.1 Phase 2 목적 문단에 한 줄 추가

> Evidence는 Response에 더해 **DB 접근(SQL 원문)**을 요청 단위로 포함한다. 종류·횟수·테이블 등 파생값은 Phase 3 엔진이 원문에서 계산하며, 앱은 가공하지 않는다.

### 1.2 2.3 Evidence JSON v0 — 필드 추가

레코드(키 `(runId, replayRequestId, stack)`)에 아래 두 필드 추가. 기존 필드는 변경 없음.

```json
"dbAccess": {
  "statements": [
    { "seq": 1, "sql": "select o1_0.id,o1_0.order_key,o1_0.status from orders o1_0 where o1_0.order_key=?" },
    { "seq": 2, "sql": "insert into payments (amount,order_id,transaction_id,id) values (?,?,?,?)" }
  ],
  "truncated": false
},
"callTree": null
```

규칙
- `sql`은 Hibernate가 JDBC로 보내기 직전의 문자열(바인딩 전, 값은 `?`). 가공·파싱·분류 없음
- 상한: 문장당 2,048자(초과분 잘라내고 `truncated: true`), 요청당 200건(초과 시 이후 문장 버리고 `truncated: true`)
- `callTree`는 Phase 3에서 채움. Phase 2에서는 항상 `null` — 필드 자리만 예약
- 2.7 동일성 검증 항목에는 포함하지 않음(2.7은 요청 동일성만). 2.8에서만 아래 비교

### 1.3 2.4 Evidence 필터 — 할 것 추가

기존(request/response 캡처 → 응답 커밋 후 비동기 POST, `X-Evidence-Internal: true`, Legacy/New 동일)에 더해:

**(a) ReplayContext**
- ThreadLocal 홀더 `ReplayContext { replayRequestId, runId, sessionId }`
- Evidence 필터(`OncePerRequestFilter`, `Ordered.HIGHEST_PRECEDENCE`)가 `X-Replay-Request-Id`, `X-Run-Id`, `X-Session-Id` 헤더에서 읽어 set, `finally`에서 clear
- 요청별 Evidence 버퍼는 `chain.doFilter()`가 **반환한 뒤** 닫는다(open-in-view로 컨트롤러 반환 후 직렬화 중에도 SELECT가 나감)

**(b) StatementInspector**
- `EvidenceStatementInspector implements org.hibernate.resource.jdbc.spi.StatementInspector`
- `inspect(sql)`: `ReplayContext`에 id가 있으면 현재 요청 버퍼에 `{seq, sql}` append, 없으면 무시(부팅·스키마 검증 쿼리). 항상 `sql`을 그대로 반환
- 등록: `HibernatePropertiesCustomizer` 빈으로 `hibernate.session_factory.statement_inspector`에 **인스턴스**를 넣는다(클래스명 문자열로 넣으면 Spring 빈 주입 불가)
- 고정: `spring.jpa.properties.hibernate.jdbc.batch_size` 미설정(배치 off — 배치가 켜지면 inspector 호출 수와 문장 수가 어긋남). DB 접근은 JPA(Hibernate) 경로만 사용, `JdbcTemplate`·native batch 금지(inspector가 못 봄)
- Phase 2 범위는 **요청 스레드만**. `@Async`·Kafka consumer 스레드 전파는 Phase 3

**(c) 전송 큐 정책 — 유실 금지**
- 비동기 POST 큐 상한 도달 시 **버리지 않는다**. 로컬 파일(`/var/evidence/spill/<runId>/`)로 spill하고, run script의 flush barrier가 spill 파일까지 회수한 뒤 기대 건수를 센다
- 근거: Evidence는 검증 본체라 유실되면 Undelivered로 잡혀 run이 무효가 됨(토스 로그의 neverBlock=버림과 목적이 반대)

**(d) graceful shutdown**
- `server.shutdown=graceful`, `spring.lifecycle.timeout-per-shutdown-phase=20s`
- 종료 훅에서 Evidence 큐 flush(미전송분은 spill)
- k8s `terminationGracePeriodSeconds: 30` (앱 타임아웃보다 길게)
- 근거: S0 리셋이 `rollout restart`라 매 run마다 pod가 종료됨 → 마지막 요청들의 Evidence가 큐에 남은 채 죽을 수 있음

**끝난 기준(추가)**
- 요청당 Evidence 1건에 `dbAccess.statements`가 비어 있지 않음(POST /api/orders는 INSERT 포함)
- 앱 기동 로그의 스키마 검증 쿼리는 어떤 요청의 `dbAccess`에도 없음
- `rollout restart` 직전에 보낸 마지막 요청의 Evidence가 Store 또는 spill에 존재
- `callTree`는 `null`

### 1.4 2.6 run script — flush barrier 보강

> flush barrier: Store 수신 건수 + spill 파일 건수 == 기대 건수. spill이 있으면 Store로 재전송 후 삭제. 타임아웃 시 누락 ID 보고.

### 1.5 2.8 — 비교 항목 추가

기존 Response canonical JSON 비교에 더해, **A/A 조건(코드 동일)**에서 요청별 `dbAccess`가 반복 run 간·Legacy/New 간 동일한지:
- 비교 단위는 **문장 목록의 순서·개수**와 각 `sql`의 정규화 문자열(소문자화, 연속 공백 1개로, Hibernate alias `[a-z]+\d+_\d+` → `_a_` 치환). 원문 그대로 비교 금지(alias 생성 순서가 바뀔 수 있음)
- 이 정규화는 **2.8 검증 스크립트에만** 둔다. 앱에 넣지 않는다
- 다르면 원인 분류(비결정 쿼리 순서 / open-in-view 지연 SELECT / 배치) 후 보고. 판정 규칙 확정은 Phase 3
- 이 단계의 이름을 **A/A run**으로 부르고, Phase 3 각 단계 완료 조건에도 "A/A run 3회, diff 0 또는 잡음 목록 명시"를 둔다

---

## 2. 루트 `CLAUDE.md`

Phase 2 표의 2.3·2.4·2.6·2.8 행을 위와 같이 갱신. 실행 지시 문단에 한 줄 추가:

> DB Evidence는 StatementInspector로 SQL 원문만 기록한다. 앱에서 종류·횟수·테이블을 계산하거나 SQL 주석을 삽입하지 않는다(그건 Phase 3 엔진 또는 CDC 확장의 몫).

---

## 3. `docs/decision-log.md` 추가

### DB Evidence 수집 방식 (v3, 2026-10-11)

**선택 지점**: Legacy/New의 DB 동작이 같은지를 어떤 수단으로 관측하는가

**이력**
- v1 (아키텍처 v7~v10.1): Hibernate Statistics / Repository AOP로 요청별 횟수(+필요 시 값). 한계: Statistics는 SessionFactory 전역 카운터라 동시 요청에서 요청별 분리 불가, "앱이 보낸 것"만 보고 실제 저장 결과는 안 봄
- v2 (2026-10-01 검토): 토스 세션 "shadow + CDC + dataset(count/sum/hash)"를 보고 Debezium(MySQL binlog)으로 DB 바깥에서 실제 변경 행(before/after) 수집 검토. 난제: binlog에 요청 ID 없음 → SQL 주석(sqlcommenter 패턴)에 rid를 넣고 `binlog_rows_query_log_events=ON` + Debezium `include.query`로 전달하는 매핑 방안 도출(우리 제안, 토스 조합 아님)
- **v3 (확정)**: CDC를 기본에서 제외하고 두 층으로
  1. **요청 단위**: `StatementInspector`로 SQL 원문 `{seq, sql}` 기록. 종류·횟수·테이블은 엔진이 파생. 원문 "DB 접근 횟수" 충족
  2. **run 단위**: run 종료 후 Legacy/New 최종 DB 상태 비교 — business key(orderKey) 조인, id·시각 정규화, count → sum → hash. diff 행은 orderKey로 세션에 역매핑

**근거**
- 원문 요구는 "DB 접근 횟수"이며 inspector로 충족. 비용 0, 의존성 0
- 최종 상태 비교는 현업(토스 정산, Uber 회계, Stripe 이전)과 같은 방식이고 business key가 있어 CDC 없이도 세션 귀속이 됨 → Human Review 범위 축소 지표에 충분
- "기록은 최대 해상도(원문), 판정은 선언된 해상도(엔진 규칙)": 파싱·정규화 규칙을 앱에 넣으면 규칙 변경마다 Legacy/New 양쪽 재배포 → "코드 이외는 상수" 위반. 엔진(클러스터 밖)에 두면 재배포 없이 재분석 가능
- 영향 행 수·바인딩 파라미터까지 필요하면 datasource-proxy(JDBC 프록시)로 교체 가능 — 수집 자리가 같아 스키마 불변

**대안(확장으로 보존)**: CDC + SQL 주석 매핑. 필요해지는 경우: business key 없는 행(공유 카운터) 귀속, 중간 전이(A→B→A) 관측, 요청 단위 정확 귀속. Phase 4 여유 시

**한계 명시**: 최종 상태 비교는 run 종료 스냅샷이라 중간 전이를 못 봄. inspector는 Hibernate 경로만 봄(JPA-only 규약으로 보완). SQL 주석 기법은 ORM 중립(sqlcommenter)이나 CDC까지 살아남는지는 DB 의존(MySQL 가능, PostgreSQL은 request_id 컬럼 필요)

**변경 없음**: S0 리셋은 입력 조건 고정 수단으로 유지

### Evidence 전송 큐 정책 (2026-10-11)

유실 금지. 큐 상한 시 로컬 spill, flush barrier가 회수. graceful shutdown + flush 훅. 근거: 토스 로그 appender(neverBlock=버림)와 목적이 반대 — 로그는 부가 기능, Evidence는 검증 본체

### DB 격리의 두 축 (2026-10-11)

서비스 축(Order↔Coupon, 소유권·사이드이펙트 경계)과 스택 축(legacy↔new, 실험 유효성)은 다른 결정. 실무 shadow testing은 Legacy/New가 같은 DB를 보는 경우가 흔해(Stripe shadow read, Grab DAO mock) 스택 축 격리는 우리의 명시적 선택이며 설정(JDBC URL)이 아니라 네트워크(NetworkPolicy)로 보장한다 → isolation-proof 보강

---

## 4. `docs/isolation-proof.md` 추가 — 스택 간 DB 격리

| 시도 | 기대 | 결과 |
|---|---|---|
| `new` ns pod(비주입 curl) → `mysql.legacy.svc.cluster.local:3306` TCP | NetworkPolicy로 타임아웃 | (실측 기입) |
| `new` ns pod(sidecar 주입) → 동일 | 동일 | (실측 기입) |
| `legacy` ns pod → `mysql.new.svc.cluster.local:3306` | 동일 | (실측 기입) |

통과 기준: 세 경우 모두 연결 실패. 기존 1.3a의 "두 DB가 독립(new 리셋 시 legacy 불변)"은 데이터 독립성이고, 이 표는 **네트워크 도달 불가**를 증명한다.

---

## 5. `docs/architecture.md` 5.1 한 줄 교체

> DB Read·Write(횟수, 필요 시 값) → **DB 접근: StatementInspector가 요청별 SQL 원문을 기록하고, 엔진이 종류·횟수·테이블·지문을 파생한다. 실제 저장 결과는 run 종료 후 최종 DB 상태 비교(business key 조인, count/sum/hash)로 본다.**

---

## Claude Code 실행 지시 (붙여넣기용)

> 위 패치를 `docs/phase2-plan.md`, 루트 `CLAUDE.md`, `docs/decision-log.md`, `docs/isolation-proof.md`, `docs/architecture.md`에 반영해라. 코드 변경은 없고 문서만이다. 반영 후 diff 요약을 보여주고, 확인하면 2.2(corpus v1)로 넘어간다. 2.4에 들어갈 때 이 패치의 1.3 (a)~(d)를 그대로 구현 범위로 삼는다. 문서에 없는 결정이 필요하면 임의로 정하지 말고 질문해라. isolation-proof 4절의 실측은 2.3 전에 10분 내로 끝내고 결과를 표에 기입한다.
