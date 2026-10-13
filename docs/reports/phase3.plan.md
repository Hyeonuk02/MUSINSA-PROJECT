# phase3.plan — Phase 3 계획 v2.1 반영 (문서만)

## 0. 결정 필요 사항

없음. (계획 전제와 실제 스택의 차이 — Gradle/Framework 6.1/Jackson 2 vs Maven/Boot 4.1.1/Jackson 3 — 는 3.0 사전 점검의 범위라 `phase3.0` 보고서 0절에 올린다.)

## 1. 단계 목표와 끝난 기준별 PASS/FAIL

| 기준 | 결과 | 근거 |
|---|---|---|
| `docs/phase3-plan.md` = 원문(맨 아래 "Claude Code 지시" 절만 제외) | PASS | 원문 1~331행과 `diff` 차이는 파일 끝 빈 줄 1개뿐 |
| `docs/decision-log.md` D15~D19 = 10절 블록 | PASS | `결정/근거/대안/한계:`에 굵은 글씨만 입힘. 굵은 글씨를 걷어낸 문자열이 원문 블록과 일치(True). 387~405행 |
| `docs/references/industry-cases-phase3.md` = 8절 표 + 행마다 출처 | PASS | 8행 그대로, 각 행 아래 `↳ 출처` 행에 지시된 URL(카카오페이는 레포 문서 링크) |
| `CLAUDE.md` Phase 3 절 | PASS | "Phase 2 완료" 절 유지, 그 아래 "## Phase 3 — 진행 중": 단계 표 3.0~3.8(상태 열), 확정 사항 요약(키·hopPath·타임라인·Kafka·쿠폰 순서·검증 레이어·Kotlin·DB 두 층·판정·settle·Rule 분리·게이트), 하지 말 것(4절). 작업 방식 phase2 → phase3. 보고 규칙 절 그대로 |
| `docs/architecture.md` §9 Phase 3 행만 | PASS | `git diff`: 그 행 상태 칸만 "진행 중 — docs/phase3-plan.md" |

## 2. 변경 파일과 커밋 해시

| 커밋 | 파일 |
|---|---|
| `1991511` phase3: plan v2, D15~D19, 참고 사례 | `docs/phase3-plan.md`(신규), `docs/references/industry-cases-phase3.md`(신규), `docs/decision-log.md`(+23), `CLAUDE.md`, `docs/architecture.md`(1행) |
| (이 보고서 커밋) | `docs/reports/phase3.plan.md` |

## 3. 실행 명령과 주요 출력

```
$ head -n <'Claude Code 지시' 절 직전> ~/Downloads/phase3-plan-v2.md | diff - docs/phase3-plan.md
332d331  (절 구분 앞 빈 줄 1개)
$ D15~D19 내용 일치(굵은 글씨 제거 후): True
$ git diff docs/architecture.md → Phase 3 행 1줄만 변경
```

## 4. Legacy/New 비교 결과와 수치

해당 없음(문서 단계).

## 5. 지시와 다르게 구현한 것과 이유

- **CLAUDE.md 기존 절 제목 두 개에 범위 표시를 붙였다**: "## 확정 사항" → "## 확정 사항 (Phase 1~2, Phase 3에도 유효 — Phase 3에서 바뀐 키는 위 요약이 우선)", "## 하지 말 것" → "## 하지 말 것 (Phase 2 — 기록용, Phase 3는 위 "Phase 3 하지 말 것")". 이유: 기존 절에 "Evidence 키 (runId, replayRequestId, stack)", "Coupon/Payment 실서비스·Kafka 구현하지 않는다"가 남아 있어 Phase 3 확정 사항(hopPath 키, Coupon·Kafka 구현)과 정면 충돌한다. 본문은 지우지 않고 제목으로 범위만 밝혔다. 원치 않으면 되돌린다.
- 작업 방식의 커밋 형식에 계획서 "실행 지시"의 사다리·결함 커밋 형식(`phase3.5-v1.1`, `phase3.6-F1`)을 함께 적었다.
- 산업 사례 표의 출처는 표가 깨지지 않도록 각 행 바로 아래 `| ↳ 출처 | URL | |` 행으로 넣었다.

## 6. 발견한 문제·해결·남은 한계

- 계획서가 전제한 빌드·런타임(Gradle, Spring Framework 6.1+, Jackson 2, "3.8에서 Boot 4")과 현재 레포(Maven, Spring Boot 4.1.1 = Framework 7, Jackson 3 `tools.jackson`, Hibernate 7.4)가 다르다. 3.0에서 버전 표로 확인하고 결정 사항으로 올린다.
