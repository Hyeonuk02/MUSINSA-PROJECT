# Phase 4.6 보고서 — 스코핑 경계 사례

- 작업일: 2026-11-02
- 범위: E1~E7 기대 사전 등록, 로컬 임시 브랜치, impact 산출. 클러스터 접근 없음, run 없음
- 결과: **PASS** — 7건 모두 사전 등록과 일치, 도구·기대 변경 없음. **결정 필요 0건**
- 도구: impact-v1.1(D24 보완 3 적용 후)

## 0. 결정 필요 사항

없음.

## 1. 끝난 기준별 결과

| 기준 | 결과 | 근거 |
|---|---|---|
| 기대를 impact 실행 전 등록 | PASS | `docs/scope-expectations.json` `boundaryCases`, `e8edae1`. 기존 키는 그대로(비교 확인). 브랜치·첫 실행은 그 뒤 |
| 7건 impact.json과 기대 일치 표 | PASS | **7/7**, 4절. `scoping/impacts/boundary/E<n>.json`, `logs/phase4.6-scope-check.txt` |
| 임시 브랜치 로컬, push 없음 | PASS | `scope/E1..E7`, 원격 0개. 각 `phase3.5-v1.4` 위 1커밋 |
| 보고서에 diff 요약만 | PASS | 4절, `logs/phase4.6-branches.txt` |
| 결정론·회귀 | PASS | 재실행 sha 동일, `phase4-metrics.json` 변화 없음, pytest scoping 87·engine 39, `check_inputs` 64/64 |

**요청받은 기록**: C2 규칙 재사용 = findings **O22**. 전역 행 Recall "전역(자명)" 표기 = `docs/phase4-plan.md` 구현 시 확정 (4.7, 미리 적어둠).

## 2. 변경 파일·커밋

| 커밋 | 내용 |
|---|---|
| `e8edae1` phase4.6: E1~E7 기대 사전 등록(impact 실행 전), O22, 전역 행 표기 메모 | `docs/scope-expectations.json`(`boundaryCases` 추가), `scoping/check_scope.py`, `docs/findings.md`(O22), `docs/phase4-plan.md` |
| (이 커밋) phase4.6: 결과·보고서 | `scoping/impacts/boundary/`, 이 문서, `docs/reports/logs/phase4.6-*.txt`, `CLAUDE.md` |

## 3. 실행 명령·주요 출력

```
git worktree add … phase3.5-v1.4 → 사례별 scope/E<n> 1커밋(로컬)
.venv/bin/python scoping/check_scope.py --explain   → 불일치 0건, exit 0
```

전문: `docs/reports/logs/phase4.6-{branches,scope-check,pytest}.txt`

## 4. 결과 표

Legacy/New 비교는 해당 없음(run 없음).

| 사례 | diff 요약 | 관측 | 미관측 | 결과 | 사유 | 영향 요청 | 세션 | 재생 | 사전 등록 |
|---|---|---|---|---|---|---|---|---|---|
| E1 | `ClockConfig.kt` 한 줄 | 0 | 1 | **전역** | 미관측 → 참조 없음 → 미해결 | 48 | 11 | 48 | 일치 |
| E2 | `application.yml` 값 1개 | 0 | 0 | **전역** | resource | 48 | 11 | 48 | 일치 |
| E3 | `README.md`·`docs/call-graph.md` | 0 | 0 | 영향 없음 | docs | 0 | 0 | 0 | 일치 |
| E4 | evidence-collector 한 줄 | 0 | 0 | 영향 없음 + **A/A 경고** | verify | 0 | 0 | 0 | 일치 |
| E5 | `OrderItem.kt` 한 줄 | 0 | 1 | order.* | 폐포 → Controller·Repository·Service | 32 | 9 | 37 | 일치 |
| E6 | `PaymentGatewayClient.kt` 삭제 | 1 | 0 | **전역** | 규칙 4(`deleted`) | 48 | 11 | 48 | 일치 |
| E7 | `CouponRepository.java` 한 줄 | 1 | 0 | coupon.* + 홉 | 관측 | 24 | 6 | 29 | 일치 |

E1·E2는 한 줄 변경이 전체 재생으로 이어지는 fail-closed 비용을 보인다. E6은 삭제가 아니었다면 7세션인 클래스다 — 관측 여부보다 규칙 4가 앞선다. E4는 재생 0이지만 경고가 남아, 검증 레이어 변경이 "영향 없음"으로 조용히 지나가지 않는다.

## 5. 지시와 다르게 구현한 것

- **E6 대상을 관측 클래스로 골랐다**: 계획은 클래스를 지정하지 않았다. 미관측 클래스면 규칙 4 없이도 폐포로 전역이 될 수 있어 관측 클래스가 더 분명한 시험이다
- **E7 변경은 주석 한 줄이다**: 클래스 단위 매칭이라 내용과 무관하게 같은 결과다. E1·E4·E5도 같다
- **`check_scope.py`에 경계 사례 표 추가**, 산출 위치 `scoping/impacts/boundary/`(`evaluate.py`는 읽지 않는다)

## 6. 문제·해결·남은 한계

- 문제 없음. 도구·기대를 고친 것은 없다
- **E5는 완전한 맹검 대조가 아니다**: 9세션·37요청은 D-4.2a 선택지 계산(`logs/phase4.2-whatif.txt`)에서 이미 본 값이다. 원래 문구의 전역 결과는 `aux/E5-literal`에 있다. 나머지 6건은 이번에 처음 실행했다
- **주석 변경도 영향으로 잡힌다**: 클래스 단위 `git diff` 매칭의 해상도 한계다. 과포함 방향이다
- **E6은 가정 커밋이다**: 삭제된 클래스를 쓰는 코드가 남아 있어 컴파일되지 않는 상태이고, 스코핑 규칙만 시험한다. E2도 빌드·실행하지 않았다
- **변경은 전부 `phase3.5-v1.4` 위 1커밋이다**: 여러 변경이 섞인 diff는 사다리·결함 변형이 다뤘고, 경계 사례는 규칙 하나씩만 본다
