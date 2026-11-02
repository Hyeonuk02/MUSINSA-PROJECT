# Phase 4.8 보고서 — 선택 미러 시연

- 작업일: 2026-11-02
- 범위: VirtualService `match` 기반 선택 미러, F3 × 1 run
- 결과: **PASS** — 등록 기대와 일치. D-4.7a 조건(4.9 뒤 반나절 안)을 충족해 실시했다. 결정 필요 0건

## 0. 결정 필요 사항

없음.

## 1. 끝난 기준별 결과

| 기준 | 결과 | 근거 |
|---|---|---|
| 기대 run 전 등록 | PASS | `docs/filter-expectations.json` `F3-mirror`, `c9a04f9`(run의 `git.rev`, dirty false) |
| Legacy 전체·New 영향 세션만 | PASS | Legacy 48요청·Evidence 60, New 30요청·Evidence 40, WireMock journal 양쪽 7 |
| barrier New 기대 = 선택 세션 | PASS | legacy 60/60, new 40/40, 누락 0 |
| 재생 pair 판정 == 전체 재생 같은 pair | PASS | 40/40, CV 7·SAME 33, F3 Filter와 같음. `logs/phase4.8-run-check.txt` |
| Undelivered(new) = 미러하지 않은 요청 | PASS | 정확히 18건, Legacy 0, degraded·settleTimeouts 0 |
| verify_sameness | 기대대로 FAIL | Undelivered(new) 18 때문이고 pairing된 40건의 요청 동일성은 전부 PASS. 엔진 고정이라 고치지 않았다 |
| run 범위 dbstate | 기대대로 위반 | New가 부분 상태(coupons 3 / 6, orders 7 / 8). 판정 근거가 아니다 |
| 복원 | PASS | 레포 VS 재적용(`x-impact` 0건), new overlay `phase3.5-v1.4` |

## 2. 변경 파일·커밋

`c9a04f9`: `scoping/render_vs.py`, `k6/{run.js,run.sh,barrier.py}`, `scoping/run_check.py`, `docs/filter-expectations.json`, 계획 구현 시 확정 (4.8). 레포의 VS 파일은 변경 없음.

## 3. 실행 명령·주요 출력

```
.venv/bin/python scoping/render_vs.py | kubectl apply -f -
k6/run.sh --run-id p48-F3-m --iterations 1 --vus 3 --mirror scoping/impacts/F3.json
verdict.py --arm C → CV 7, SAME 33, Undelivered new 18
.venv/bin/python scoping/run_check.py --case F3-mirror → 기대 일치
```

전문: `docs/reports/logs/phase4.8-{run,run-check,metrics}.txt`

## 4. Legacy/New 비교

| 방식 | Legacy 요청 | New 요청 | pair | 판정 | run 범위 dbstate |
|---|---|---|---|---|---|
| 전체 재생 | 48 | 48 | 60 | CV 8, SAME 52 | 일치 |
| Filter | 30 | 30 | 40 | CV 7, SAME 33 | 일치 |
| 선택 미러 | 48 | 30 | 40 | CV 7, SAME 33 | 위반(부분 상태) |

## 5. 지시와 다르게 구현한 것

- **`mirrorPercentage` 100은 남겼다**: 표본 추출이 아니라 원래 값이다. 선택은 헤더 match로만 한다
- **mirror 없는 세션은 Legacy 도착을 폴링**: 세션 순서를 유지하려고 `run.js`에 분기를 넣었다. `MIRROR_SESSIONS`가 없으면 기존 동작과 같다
- **`run.js`·`run.sh`·`barrier.py` 변경**: verify 레이어 변경이다. 기본 경로는 그대로이고, 변경 뒤 전체 재생 A/A는 돌리지 않았다

## 6. 문제·해결·남은 한계

- **barrier 출력 표기**: `1단계 new: 기대 40 (진입 48 + 선언된 settle -8)`처럼 내역이 어긋나게 찍힌다. 기대 수는 맞다. 표시만의 문제라 고치지 않았다
- **선택 미러는 Filter를 대체하지 못한다**: findings O23
- 1 run 시연이다. 결정론 확인이 아니다
