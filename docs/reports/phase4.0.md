# Phase 4.0 보고서 — 준비

- 작업일: 2026-10-14
- 범위: 계획·결정 기록, `scoping/` 골격, Phase 3 입력 점검, engine-v1.3(additive matcher 1건). 클러스터 접근 없음, run 없음
- 결과: **PASS** — 입력 점검 64/64 OK, engine-v1.3 재판정 150 판정 파일 변화 0, pytest engine 37 + scoping 27 통과. **결정 필요 2건**

## 0. 결정 필요 사항

**D-4.0a 사다리 변형(v1.1~v1.4)의 코드 diff 범위 — 4.2 기대(scope-expectations) 등록 전에 필요**

입력 점검에서 다음을 확인했다(findings O14):
- 계획 1절의 `git diff -M phase3.3-base..phase3.5-v1.x`는 그 사이 hyeonuk-dev의 **엔진·문서·run.sh·base 매니페스트 커밋까지** 포함한다. 예: `phase3.3-base..fd839d6`(v1.1)에 `engine/*`, `docs/*`, `.gitignore`, `deploy/k8s/new/kustomization.yaml`이 섞인다
- 사다리 커밋 하나만 봐도(`<v1.x>~1..<v1.x>`) 네 단계 모두 **`deploy/k8s/new/kustomization.yaml`(new order 이미지 태그)**이 함께 바뀌었다 — D24대로면 deploy → 전역
- 결함 브랜치(`phase3.5-v1.4..fault/F<n>`)는 서비스 코드 1~2 파일만이라 문제 없음

계획 4.2 표의 기대(v1.1 = pom 때문에 전역, v1.2·v1.3 = order.* 9세션, v1.4 = 설정·필터·메인 때문에 전역)는 "서비스 코드 변경만"을 전제로 쓰였다. 선택지:
- **(A) 권장** — 사다리 변형의 diff = **이전 단계 커밋 → 그 단계 커밋, pathspec `services/`**(v1.1의 이전 = `phase3.3-base`). 근거: overlay 이미지 태그 교체는 "그 변경을 배포한 것"이지 별도 변경이 아니고, 사이의 엔진·문서 커밋은 사다리 변경이 아니다. 결과: v1.1 = `pom.xml`(build → 전역) + `PaymentGatewayClient`, v1.2~v1.4 = 서비스 파일만 → 계획 표와 같은 전제. impact.json에 사용한 base·head·pathspec을 기록
- (B) 커밋 단위 diff(`<v1.x>~1..<v1.x>`)를 그대로 쓰고, deploy 변경 중 "이미지 태그만 바뀐 경우"를 영향 없음으로 보는 예외를 D24에 추가 — 도구 규칙 변경
- (C) 계획 문구 그대로(`phase3.3-base..phase3.5-v1.x`) — 사다리 4단계 모두 전역(감소율 0%)이 사전 등록 기대가 된다

**D-4.0b 교수님 10/13 피드백 내용** — 계획 4.0의 "교수님 10/13 피드백 반영 자리"를 채울 내용을 받지 못했다. 내용을 주시면 해당 단계(또는 4.1 착수 전)에 반영 위치를 정한다.

## 1. 끝난 기준별 결과

| 기준 | 결과 | 근거 |
|---|---|---|
| `docs/phase4-plan.md`, decision-log D23~D25, CLAUDE.md Phase 4 표·확정 사항·하지 말 것 | PASS | 커밋 `809d827`(plan은 `~/Downloads/phase4-plan-v2.md`와 바이트 동일, D23~D25는 10절 그대로) |
| `scoping/` 골격(Python, 엔진 import 금지) | PASS | `scoping/{common,map,impact,evaluate,check_inputs}.py`, `tests/`(fixture `p36-base-1-mini`). map·impact·evaluate는 CLI·입출력 형식까지(exit 2 — 4.1~4.3에서 채움). 엔진 import 0 |
| Phase 3 입력 점검 표 | PASS | `scoping/check_inputs.py` **64/64 OK**: 태그 3(`phase3.3-base`=98c9356, `phase3.5-v1.4`=120b212, `phase3-done`), 사다리 커밋 4, `fault/F1~F9`(로컬=원격=사전 기록 커밋, 기준선 위 1커밋, 서비스 코드만), run 48개(p33·p35-base·v1.1~v1.4·p36-base·F1~F9 × 3)의 Evidence·k6-summary·run-meta·dbstate·verdict·B0·B1 + F5 prelabel·F8 maxselects·F1 engine-v1.1, run-meta 이미지(order legacy phase3.3-base / new 단계별, coupon 양쪽 phase3.3-base), `dirty: false`, p36 corpus = corpus-v2.1(경로·sha256). `logs/phase4.0-inputs.txt` |
| engine-v1.3 additive matcher | PASS | `externalCalls.responseHashChanged{host, path}` — diff detail에 `changed: [{host, path}]`, ruleset matcher(정규식 fullmatch, 바뀐 호출 전부), review 제안 템플릿, `RULE_COVERABLE` 포함. 테스트 4건(Uncertain + host·path / 규칙 일치 → Improvement / path 불일치 → Uncertain 유지 / learn 라벨 → SAME) |
| engine-v1.3 재판정 변화 0 | PASS | `engine/rejudge_check.py`(메모리 판정, 파일 덮어쓰기 없음): p33·p35-base·v1.1~v1.4·p36-base·F1~F9 × 3의 verdict·B0·B1·prelabel·maxselects **150 파일 — pair 판정·집계(verdicts·bySplit·byEndpoint·undelivered·degraded·sessionViolations)·runChecks 변화 0**. `logs/phase4.0-rejudge-engine-v1.3.txt` |
| pytest 통과 | PASS | engine 37 passed, scoping 27 passed(두 디렉터리는 따로 실행 — 6절). `logs/phase4.0-pytest.txt` |
| 교수님 10/13 피드백 반영 자리 | 대기 | 0절 D-4.0b |

## 2. 변경 파일·커밋

| 커밋 | 내용 |
|---|---|
| `809d827` phase4: plan v2, D23~D25 | `docs/phase4-plan.md`, `docs/decision-log.md`, `CLAUDE.md` |
| `9d9ed36` phase4.0: scoping 골격·입력 점검·engine-v1.3 | `scoping/*`, `engine/{verdict,ruleset,review,rejudge_check}.py`, `engine/tests/*`, `docs/phase4-plan.md`(구현 시 확정 (4.0)) |
| (이 커밋) phase4.0: 보고서 | 이 문서, `docs/reports/logs/phase4.0-*.txt`, `docs/findings.md`(O14), `CLAUDE.md`(4.0 상태) |

## 3. 실행 명령·주요 출력

```
.venv/bin/python scoping/check_inputs.py            → 점검 64건, FAIL 0
.venv/bin/python engine/rejudge_check.py            → 엔진 engine-v1.3 … 변화 있는 판정 파일: 0  (150 파일)
.venv/bin/python -m pytest engine/tests             → 37 passed
.venv/bin/python -m pytest scoping/tests            → 27 passed
.venv/bin/python scoping/tests/make_fixture.py      → p36-base-1-mini: legacy 60 records, pairs 60
git diff -M --name-status <v1.x>~1 <v1.x>           → 4단계 모두 M deploy/k8s/new/kustomization.yaml + D *.java / A *.kt
```

## 4. Legacy/New 비교

해당 없음(run 없음). engine-v1.3 재판정에서 Legacy/New pair 판정은 Phase 3 기록과 전부 같다(1절).

## 5. 지시와 다르게 구현한 것

- `engine/rejudge_check.py` 추가 — 계획의 "p33·p35·p36 전 run 재판정 pair 판정 변화 0 확인"을 판정 파일 덮어쓰기 없이(하지 말 것) 하려고 메모리 판정 + 비교 도구로
- `scoping/check_inputs.py` 추가 — 입력 점검 표를 재현 가능하게
- 스코핑 3도구는 골격(exit 2)만 — 계획 4.0의 "scoping/(…) map.py, impact.py, evaluate.py, tests/"를 4.1~4.3 본 구현 전의 형식 고정으로 해석

## 6. 문제·해결·남은 한계

- **사다리 diff 범위**(0절 D-4.0a, findings O14). 4.2 기대 등록 전에 결정 필요
- **Java → Kotlin 이동이 git rename으로 안 잡힘**: `git diff -M`이 같은 FQCN을 `D *.java` + `A *.kt`로 낸다(내용 변화가 커서). 4.2에서 "같은 diff 안 같은 FQCN 삭제·추가 = 같은 클래스의 수정"으로 처리한다(구현 시 확정 (4.0) — D17·D24 해석). 이게 없으면 규칙 4(클래스 삭제 → 전역)로 사다리 전체가 전역
- **분류 밖 파일**(`.gitignore` 등)은 build = 전역으로 분류(fail-closed). 사다리 범위를 (A)로 하면 `services/` 밖이라 영향 없음
- **pytest 두 디렉터리 분리 실행**: `engine/`과 `scoping/` 모두 평평한 모듈 이름 `common`을 써서 한 pytest 프로세스로 돌리면 충돌(27 실패로 확인). 따로 실행하면 모두 통과. 이름을 바꾸는 것은 4.0 범위 밖이라 그대로 둠
- engine-v1.3의 matcher는 C2가 응답을 바꾸지 않도록 설계되므로 실제로는 안 쓰일 수 있다(계획 4.0 문구 그대로)
