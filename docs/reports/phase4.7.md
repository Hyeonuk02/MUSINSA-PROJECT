# Phase 4.7 보고서 — 지표·보고, Phase 4 마감

- 작업일: 2026-11-02
- 범위: `docs/phase4-metrics.{json,md}` 생성, `docs/phase4-result.md`, 태그 `phase4-done`. 클러스터 접근 없음, run 없음
- 결과: **PASS** — Phase 4 종료 조건 충족. **결정 필요 1건**(4.8·4.9 실시 여부)

## 0. 결정 필요 사항

**D-4.7a 4.8·4.9 실시 여부 — 지시대로 결과를 보고 정한다**

| 항목 | 내용 | 판단 재료 |
|---|---|---|
| 4.8 선택 미러 시연 | VirtualService match로 New에만 영향 세션 미러, F3 × 1 | Filter가 재생을 줄이는 것을 이미 보였고, 4.8은 미러 경로에서 같은 것을 보이는 시연이다. 판정 동등성 근거는 추가되지 않는다 |
| 4.9 Evidence 오버헤드 | Legacy Evidence on/off, VU=1 × 3 | Phase 4 지표와 무관한 참고값이다. "운영 적용 비용"을 말하려면 필요하다 |
| 바이트코드 참조 보조 검증 | 계획 7절 미정 | O17·O18 텍스트 폐포 오탐의 근본 대안. 계획의 "정적 Call Graph 도구 금지"와 경계가 있어 범위 결정이 필요하다 |

## 1. 끝난 기준별 결과

| 기준 | 결과 | 근거 |
|---|---|---|
| `docs/phase4-metrics.md`(4.3 + 4.5 + 4.6 + ablation) | PASS | `scoping/evaluate.py` 생성(`scoping/metrics_report.py`), 손 수정 없음, 재실행 동일 |
| 전역 행 Recall 구분 | PASS | v1.1·v1.4·C1 ablation(b) = "전역(자명)". 1절 표기·4절 참조 |
| 경계 사례 구분 | PASS | E5 = "회귀 확인(4.2 whatif에서 본 값)", 나머지 6건 = 맹검 일치. 지표 5절 |
| fail-closed 비용 한 절 | PASS | E1·E2·E6·v1.1·v1.4, 지표 3절·결과 문서 |
| `docs/phase4-result.md` | PASS | 결론·맵·규칙·모드·지표·한계·결정 D23~D26·발견 O14~O22 |
| 기존 값 불변 | PASS | 지표 json의 기존 변형 값이 4.5와 동일(`recallKind` 추가 제외). 판정·impact 파일 변경 없음 |
| 회귀 | PASS | pytest scoping 88·engine 39, `check_inputs` 64/64, `check_scope` 불일치 0, `run_check` 불일치 0 |
| 태그 `phase4-done` | PASS | 이 커밋에 태그, 원격 push |
| 클러스터 상태 | PASS | new overlay 정상(order `phase3.5-v1.4`, coupon `phase3.3-base`) |

## 2. 변경 파일·커밋

| 커밋 | 내용 |
|---|---|
| (이 커밋, tag `phase4-done`) phase4.7: 지표·결과·보고서, Phase 4 완료 | `scoping/{evaluate,metrics_report,run_check}.py`, `scoping/tests/test_evaluate.py`, `docs/phase4-metrics.{json,md}`, `docs/phase4-result.md`, 이 문서, 로그, `CLAUDE.md` |

## 3. 실행 명령·주요 출력

```
.venv/bin/python scoping/evaluate.py   → docs/phase4-metrics.{json,md}, 3 run 판정 동일 15/15, Recall < 1 없음
.venv/bin/python scoping/check_scope.py / scoping/run_check.py / scoping/check_inputs.py → 불일치 0, 불일치 0, FAIL 0
git tag phase4-done; git push origin hyeonuk-dev phase4-done
```

전문: `docs/reports/logs/phase4.7-{metrics,pytest}.txt`

## 4. 결과 요약

표 전체는 `docs/phase4-metrics.md`.

| 지표 | 값 |
|---|---|
| 재생 요청 감소율 | 22.9% / 37.5% / 39.6%, 전역 0% |
| Recall(전역 아닌 행) | 행동 차이 변형 11/11 = 1.0 |
| 실제 Filter 판정 동등성 | 498/498 pair(4 변형 × 3 run) |
| Tag 판정 동등성 | 120/120 pair(2 run) |
| 맹검 사전 등록 대조 | 19/21, 회귀 확인 3/3 별도 |
| C2 eval Uncertain | 3 → 0 |

## 5. 지시와 다르게 구현한 것

- **v1.1·v1.4 Recall은 1.0이 아니라 N/A다**: 행동 차이가 없어 분모가 0이다. 표기는 "전역(자명, 분모 0)"으로 해서 지시의 구분을 지키면서 1.0으로 읽히지 않게 했다
- **"전체 선택(자명)" 추가**: 전역은 아니지만 11세션을 전부 고른 행(C2 ablation(a), F2·v1.2의 impact-v1.0)도 Recall이 자명하다. 지시에 없지만 같은 이유로 구분했다
- **`scoping/metrics_report.py` 분리**: 렌더링만 담당하고 `evaluate.py`가 호출한다
- **지표 4절의 13 변형 도구는 impact-v1.0**: 맹검 대조가 그때 이뤄졌다. 11 변형은 v1.1 결과도 같다
- **지표 json에 `registration`·`failClosed`·`boundary`·`runs`·`recallKind` 추가**
- **"맹검"의 정의를 문서에 적었다**: 도구 출력을 보기 전 손 도출 후 커밋. 도출자가 규칙을 알고 있으므로 독립 평가자의 대조가 아니다

## 6. 문제·해결·남은 한계

- 새 문제 없음. 새 발견 번호 없음
- 한계 전체는 `docs/phase4-result.md`. 가장 큰 것은 표본 크기(변형 15, 세션 11)와 "참조 폐포는 휴리스틱"이다
- 임시 경계 브랜치 `scope/E1..E7`은 로컬에만 있어 다른 클론에서 E 사례 재실행은 브랜치를 다시 만들어야 한다. 커밋 해시는 달라지지만 결과는 같다
