# Phase 4.9 보고서 — Evidence 수집 오버헤드 (참고값)

- 작업일: 2026-11-02
- 범위: Legacy Evidence on/off, VU=1 × 3, 응답 지연·CPU·메모리·Evidence 건당 크기
- 결과: **PASS** — 측정 완료. **기대 없음, 판정과 무관한 참고값**이다. 결정 필요 0건

## 0. 결정 필요 사항

없음.

## 1. 끝난 기준별 결과

| 기준 | 결과 | 근거 |
|---|---|---|
| on/off VU=1 × 3 | PASS | `p49-on-1..3`, `p49-off-1..3`, 각 48요청, `dirty: false`, Legacy 이미지 동일. off에서 Store legacy 건수 0, on에서 60 |
| p50·p95·CPU·메모리·건당 크기 | PASS | `docs/phase4-overhead.json`, `logs/phase4.9-overhead.txt` |
| 판정 무관 | PASS | 판정·규칙·run 파일 변경 없음 |
| 복원 | PASS | legacy overlay 복원, `EVIDENCE_STORE_URL` 양쪽 복귀 |

## 2. 변경 파일·커밋

`d0ba9b9`(측정 도구: `k6/overhead.{js,sh}`, `scoping/overhead_report.py`), `4887688`(결과), 이 보고서 커밋.

## 3. 실행 명령·주요 출력

```
k6/overhead.sh --iterations 3
.venv/bin/python scoping/overhead_report.py
```

## 4. 결과

run별

| run | p50 ms | p95 ms | CPU 코어초 order 앱 / coupon 앱 | working set MiB order / coupon |
|---|---|---|---|---|
| on-1 | 14.63 | 54.44 | 1.168 / 0.912 | 399.2 / 353.9 |
| on-2 | 13.96 | 44.64 | 0.955 / 0.850 | 414.3 / 368.3 |
| on-3 | 13.18 | 42.95 | 0.818 / 0.716 | 417.0 / 371.0 |
| off-1 | 15.54 | 50.75 | 1.053 / 0.626 | 399.8 / 403.4 |
| off-2 | 11.41 | 31.82 | 0.835 / 0.654 | 403.0 / 421.7 |
| off-3 | 11.34 | 32.35 | 0.757 / 0.461 | 423.5 / 423.6 |

3 run 중앙값

| 항목 | on | off | 차이 |
|---|---|---|---|
| p50 | 13.96ms | 11.41ms | +2.55ms |
| p95 | 44.64ms | 32.35ms | +12.29ms |
| CPU 코어초(재생 1회) order 앱 | 0.955 | 0.835 | +0.120 |
| CPU 코어초 coupon 앱 | 0.850 | 0.626 | +0.224 |
| CPU 코어초 sidecar order / coupon | 0.115 / 0.111 | 0.103 / 0.085 | +0.012 / +0.026 |

Evidence 건당 크기(JSON, Legacy 180건): p50 1,900B, p95 2,976B, 최대 3,014B, run당 약 121KB(60건). order 평균이 coupon보다 크다(p50 2,120B / 1,755B).

## 5. 지시와 다르게 구현한 것

- **`EVIDENCE_ENABLED`는 스위치가 아니다**: 계획의 이름은 기동 로그 문구였다. `EVIDENCE_STORE_URL`을 뺐다(수집기 전체 미등록)
- **`run.sh`를 쓰지 않았다**: Legacy Evidence를 전제로 해서 barrier가 끝나지 않는다. 폴링 없는 `k6/overhead.js`, 요청 간격 0.1초 고정
- **`kubectl top` 대신 `crictl stats`**: metrics-server가 없다
- **Legacy만 껐다**: New 쪽 Evidence와 미러는 그대로다. 게이트웨이 경유 측정이다

## 6. 문제·해결·남은 한계

- **차이를 소음과 분리하지 못한다**: 모드마다 첫 회가 가장 느리다(off-1 p50 15.54ms > on-1 14.63ms). run당 48요청이라 p95는 상위 2~3건으로 정해지고, S009의 2초 지연 스텁이 max를 정한다. on → off 순서를 고정해 순서 효과도 분리하지 않았다
- **메모리는 Evidence 효과로 읽을 수 없다**: off의 coupon working set이 오히려 크다. JVM 힙 증가 시점의 차이로 보인다(원인 검증은 안 함)
- **운영 부하 추정이 아니다**: VU=1, 요청 간격 0.1초의 저부하다. 전송 큐·재시도 비용이 드러나는 조건이 아니다
- findings O24
