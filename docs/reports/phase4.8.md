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
- **`run.js`·`run.sh`·`barrier.py` 변경**: verify 레이어 변경이다. 기본 경로는 그대로이고, 변경 뒤 전체 재생 A/A는 6.1에서 추가로 돌렸다(VU=3 × 3 diff ∅)

## 6. 문제·해결·남은 한계

- **barrier 출력 표기**: `1단계 new: 기대 40 (진입 48 + 선언된 settle -8)`처럼 내역이 어긋나게 찍힌다. 기대 수는 맞다. 표시만의 문제라 고치지 않았다
- **선택 미러는 Filter를 대체하지 못한다**: findings O23
- 1 run 시연이다. 결정론 확인이 아니다

### 6.1 (추가, 2026-11-12) 검증 레이어 변경 뒤 A/A 게이트 — PASS

main 머지 전 확인. 4.8에서 바뀐 `run.sh`·`run.js`·`barrier.py`(rev `36aac52`)로 기본 경로(`--impact`·`--tag`·`--mirror` 없음)를 돌렸다.

- 조건: Order·Coupon 양쪽 `phase3.3-base`(New Order만 `kubectl set image`로 임시 교체, 저장소 overlay는 그대로), 게이트웨이 VS는 기본(헤더 match 없음, mirror 100), VU=3 × 3, corpus v2.1
- 명령: `k6/run.sh --run-id p48-aa2 --iterations 3 --vus 3` → exit 0. 그 뒤 run마다 `engine/diff_v0.py`·`engine/verify_sameness.py`·`engine/verdict.py --arm C`(engine-v1.3)
- 끝나고 New Order를 `phase3.5-v1.4`로 되돌렸다. `kubectl diff -k deploy/k8s/new` 차이 없음

| run | dirty | diff_v0 (7축 + dbstate + wiremock) | verify_sameness | barrier legacy / new | 판정 C |
|---|---|---|---|---|---|
| p48-aa2-1 | false | ∅ (exit 0) | PASS | 60/60, 60/60 | SAME 60 |
| p48-aa2-2 | false | ∅ (exit 0) | PASS | 60/60, 60/60 | SAME 60 |
| p48-aa2-3 | false | ∅ (exit 0) | PASS | 60/60, 60/60 | SAME 60 |

Undelivered 0·degraded 0·sessionViolations 0, `dbstate_equal` ok ×3. 로그: `logs/phase4.8-aa-{run,diff,verify,verdict}.txt`

- **첫 시도 `p48-aa`는 쓰지 않았다**: 실행 로그를 `docs/reports/logs/`로 바로 리다이렉트해서 미추적 파일이 생겼고 run-meta가 `dirty: true`로 찍혔다. 코드 변경은 없었고 diff_v0·verify_sameness는 3 run 모두 ∅·PASS였지만, 게이트 조건(dirty=false)을 못 맞춰 로그를 저장소 밖에 두고 `p48-aa2`로 다시 돌렸다. `runs/p48-aa-1..3`은 지우지 않고 남겼다. findings O25
- **덮은 범위는 기본 경로뿐이다**: `--mirror`·`--impact`·`--tag` 분기는 이 A/A로 확인되지 않는다. 각각 4.8 시연, 4.4·4.5 Filter·Tag run이 근거다
