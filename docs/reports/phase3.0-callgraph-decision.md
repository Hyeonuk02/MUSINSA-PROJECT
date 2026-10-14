# phase3.0 — Call Graph 설계 확정 반영 (D14, 문서만)

## 0. 결정 필요 사항

없음.

(참고: 문서 안의 "교수님 확인 필요 — 'Call Graph'를 동적 수집·합성으로 해석해도 되는지"는 원문 그대로 옮긴 외부 확인 항목이며, 이 반영 작업의 진행을 막지 않는다.)

## 1. 단계 목표와 끝난 기준별 PASS/FAIL

목표: `~/Downloads/call-graph-decision.md`의 결정을 문서에 반영. 코드 변경 없음.

| 기준 | 결과 | 근거 |
|---|---|---|
| `docs/call-graph.md` = 원본 1~8절 그대로("decision-log 항목"·"Claude Code 지시" 절 제외) | PASS | 원본의 제목·머리말·1~8절과 `diff` 결과 차이는 파일 끝 빈 줄 1개뿐(본문 107줄 일치). `docs/call-graph.md` |
| `docs/decision-log.md`에 D14 = 원본 "decision-log 항목" 블록 그대로 | PASS | 코드 펜스 안 블록 문자열이 decision-log에 그대로 포함됨(포함 검사 True). `docs/decision-log.md` 367행 `### D14.` |
| `docs/architecture.md` §7 제목 아래 한 줄 추가 | PASS | "Call Graph는 동적 수집·합성(D14, docs/call-graph.md). 정적 Call Graph는 범위 밖." — `docs/architecture.md` §7 |
| §7 "정적 Call Graph의 unsoundness…" 문단 유지 + 앞에 참고 표시 | PASS | 문단 원문 유지, 앞에 "(참고: 정적 방식을 택했을 때의 보정 — 현재는 동적 방식)" |
| architecture.md 그 외 수정 없음 | PASS | `git diff`: +2줄(추가 1줄·빈 줄 1줄), 변경 1줄(위 문단 접두) |
| `CLAUDE.md` 확정 사항 한 줄 | PASS | "Call Graph는 동적 수집·합성(D14). Phase 3에서 callTree 기록, Phase 4에서 합성·영향 API 선정" |
| 코드 변경 없음 | PASS | 커밋 변경 파일 4개 모두 문서(`docs/*.md`, `CLAUDE.md`) |

## 2. 변경 파일과 커밋 해시

| 커밋 | 파일 |
|---|---|
| `046b52b` docs: D14 Call Graph 동적 수집·합성 확정, call-graph.md | `docs/call-graph.md`(신규), `docs/decision-log.md`(+20), `docs/architecture.md`(+3 −1), `CLAUDE.md`(+1) |
| (이 보고서 커밋) docs: phase3.0 callgraph decision 보고서 | `docs/reports/phase3.0-callgraph-decision.md` |

## 3. 실행 명령과 주요 출력

```
$ head -n <원본 'decision-log 항목' 직전> ~/Downloads/call-graph-decision.md | diff - docs/call-graph.md
108d107
<            (원본의 절 구분 앞 빈 줄 1개 — 본문 차이 없음)
$ (D14 블록 원문이 docs/decision-log.md에 포함되는지) → True
$ git diff --stat (046b52b)
 CLAUDE.md            |  1 +
 docs/architecture.md |  4 +++-
 docs/decision-log.md | 20 ++++++++++++++++++++
 docs/call-graph.md   | (신규)
```

## 4. Legacy/New 비교 결과와 수치

해당 없음(문서 반영 단계, run 없음).

## 5. 지시와 다르게 구현한 것과 이유

- 없음. 다만 해석 하나: "1~8절 그대로"를 **제목과 머리말 인용 블록까지 포함**해 옮겼다(제외 대상은 지시대로 "decision-log 항목"·"Claude Code 지시" 두 절만). 그 결과 `docs/call-graph.md` 머리말에 원문 문장 "이 문서는 `docs/decision-log.md` D14와 `docs/call-graph.md`의 원본이다"가 그대로 남아 자기 자신을 가리킨다. 원문 보존을 우선해 손대지 않았다.
- D14는 원문 블록 형식(결정/근거/한계를 굵은 글씨 없이)을 그대로 두었다. 기존 D1~D13의 `**결정**` 표기와 모양이 다르다.

## 6. 발견한 문제·해결·남은 한계

- 문제 없음.
- 남은 한계(원문 8절과 동일): 맵은 corpus가 실행한 경로만 안다 / 수집 범위는 call-graph.md 3절 표가 전부 / Observed-diff Recall은 관측된 차이에 대한 지표 / "Call Graph" 해석에 대한 교수님 확인 대기.
- `phase2-done` 태그는 아직 없다(지시 대기).
