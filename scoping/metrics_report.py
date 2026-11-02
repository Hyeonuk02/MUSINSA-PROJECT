"""Phase 4.7 — docs/phase4-metrics.md 렌더링. evaluate.py가 phase4-metrics.json 내용으로 호출한다(손으로 고치지 않는다)."""

FAULTS = tuple(f"F{i}" for i in range(1, 10))
LADDER = ("v1.1", "v1.2", "v1.3", "v1.4")
CHANGES = ("C1", "C2")
V10 = "@impact-v1.0"


def fmt(v) -> str:
    return "N/A" if v is None else f"{v:.4g}"


def recall_kind(r: dict) -> str:
    """Recall의 성격. 전체를 재생하면 1.0은 스코핑이 맞힌 값이 아니다."""
    if r["global"]:
        return "global-trivial"
    if r["selectedSessions"] == 11:
        return "all-selected-trivial"
    return "not-applicable" if r["recall"] is None else "scoped"


def recall_label(r: dict) -> str:
    kind = recall_kind(r)
    if kind == "global-trivial":
        return "전역(자명)" if r["recall"] is not None else "전역(자명, 분모 0)"
    if kind == "all-selected-trivial":
        return "전체 선택(자명)" if r["recall"] is not None else "전체 선택(자명, 분모 0)"
    return fmt(r["recall"])


def tool(r: dict) -> str:
    return r["toolVersion"].removeprefix("impact-")


def variant_rows(metrics: dict, names, with_b2s: bool) -> list[str]:
    out = []
    for v in names:
        for key in (f"{v}{V10}", v):
            r = metrics["variants"].get(key)
            if r is None:
                continue
            d = r["detection"]
            b = r["b2s"]
            same = b["sameSessionCount"] if b else None
            budget = b["requestBudget"] if b else None
            row = (f"| {v} | {tool(r)} | {r['selectedSessions']}/11 | {r['selectedRequests']}/48 | {r['reductionRequests']:.1%} | {r['reductionSessions']:.1%} "
                   f"| {recall_label(r)} | {f'{d['selected']}/{d['total']}' if d else 'N/A'} | {fmt(r['precision'])} | {r['sessionChecks']['inSelected']}/{r['sessionChecks']['full']}")
            if with_b2s:
                row += (f" | {f'{same['mean']:.3f} / {same['min']:.3f} / {same['fullRecallRate']:.4f} ({same['subsets']})' if same else 'N/A'}"
                        f" | {f'{budget['mean']:.3f} / {budget['fullRecallRate']:.4f} ({budget['subsets']})' if budget else 'N/A'}")
            out.append(row + " |")
    return out


def render(m: dict) -> str:
    v = m["variants"]
    reg = m["registration"]
    blind = [c for c in reg.values() if c["kind"] == "blind"]
    regress = [c for c in reg.values() if c["kind"] == "regression"]
    out = ["# Phase 4 지표 (scoping/evaluate.py 생성 — 손으로 고치지 않는다)", "",
           f"스코핑 도구 `{m['tool']}`, 맵 본문 `{m['mapBodySha256']}`. 입력은 `runs/`의 전체 재생 판정(C, 규칙 후)과 `scoping/impacts/`. 값은 `docs/phase4-metrics.json`.", "",
           "표기", "",
           "- **Recall** = Observed-diff Recall, F0 `R000047/0` 제외. 관측된 차이 pair = verdict != SAME 또는 appliedRules가 있는 pair(D26). 분모 0은 N/A",
           "- **전역(자명)** = 전역 규칙으로 전체를 재생해 Recall을 스코핑이 맞힌 것이 아닌 행. **전체 선택(자명)** = 전역은 아니지만 11세션을 모두 고른 행. 둘 다 스코핑의 성과로 세지 않는다",
           "- 감소율 분모는 corpus v2.1의 48요청·11세션. 사다리 run은 corpus v2(46요청)로 돌았다",
           "- B2-S k개 = 같은 세션 수의 모든 조합의 Recall 평균 / 최소 / 1.0 비율(조합 수). 예산 = 요청 수 ≤ 선택 요청 수인 모든 부분집합의 평균 / 1.0 비율(개수)", "",
           "## 1. 결함·변경 변형 (행동 차이 있음)", "",
           "| 변형 | 도구 | 세션 | 요청 | 감소(요청) | 감소(세션) | Recall | 탐지 유지 | Precision | 세션 검사 | B2-S k개 | B2-S 예산 |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    out += variant_rows(m, FAULTS + CHANGES, True)
    out += ["", "`v1.0` 행은 D-4.2a 전 결과이고, F2의 `v1.1`은 결과를 본 뒤의 도구 변경이다(사전 등록 아님).", "",
            "## 2. 행동 차이 없는 변형 (사다리)", "",
            "| 변형 | 도구 | 세션 | 요청 | 감소(요청) | 감소(세션) | Recall | 탐지 유지 | Precision | 세션 검사 |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    out += variant_rows(m, LADDER, False)
    out += ["", "## 3. 스코핑이 줄이지 못하는 변경 종류 (fail-closed 비용)", "",
            "규칙대로 전역이 된 변경이다. 재생 감소 0%이고 Recall은 자명하다. 안전한 쪽으로 실패한 비용이며 스코핑의 오류가 아니다.", "",
            "| 사례 | 변경 | 전역 사유 | 세션 | 감소(요청) |", "|---|---|---|---|---|"]
    for c in m["failClosed"]:
        out.append(f"| {c['case']} | {c['change']} | {'; '.join(f'`{x}`' for x in c['reasons'])} | {c['sessions']}/11 | {c['reduction']:.1%} |")
    out += ["", "## 4. 스코핑 정확도 — 사전 등록 대조", "",
            "맹검 = 기대를 도구 출력을 보기 전에 손으로 도출해 커밋한 대조다. 도출자는 도구 규칙과 맵을 알고 있었다 — 독립 평가자의 대조는 아니다.", "",
            f"맹검 대조 **{sum(c['match'] for c in blind)}/{len(blind)}** 일치. 회귀 확인 {sum(c['match'] for c in regress)}/{len(regress)}건은 결과를 이미 본 뒤의 일치라 맹검 대조에 넣지 않는다.", "",
            "| 사례 | 구분 | 도구 | 일치 | 비고 |", "|---|---|---|---|---|"]
    for name, c in reg.items():
        label = "맹검" if c["kind"] == "blind" else "회귀 확인"
        out.append(f"| {c['case']} | {label} | {c['tool'].removeprefix('impact-')} | {'일치' if c['match'] else '**불일치**'} | {c.get('note', '')} |")
    out += ["", "## 5. 경계 사례 E1~E7", "",
            "| 사례 | 변경 | 구분 | 전역 | 영향 요청 | 세션 | 재생 | 경고 |", "|---|---|---|---|---|---|---|---|"]
    for c in m["boundary"]:
        out.append(f"| {c['case']} | {c['change']} | {c['label']} | {'전역' if c['global'] else '-'} | {c['impacted']} | {c['sessions']}/11 | {c['requests']}/48 | {'A/A 게이트' if c['warning'] else '-'} |")
    out += ["", "## 6. ablation (맵 해상도·서비스 간 간선, impact-v1.1)", "",
            "(a) 엔드포인트 합집합 맵 (b) 자식 홉 합산 없는 맵. 13 변형은 선택 세션·재생 요청이 정본과 같아 달라진 것만 싣는다. 전체 값은 `phase4-metrics.json`.", "",
            "| 변형 | 맵 | 전역 | 세션 | 요청 | 영향 요청 | 감소(요청) | Recall | Tag 요청 입도 예산·포함 |", "|---|---|---|---|---|---|---|---|---|"]
    for name in CHANGES:
        r = v[name]
        for label, x in (("정본", r), ("(a)", r["ablation"]["endpointUnion"]), ("(b)", r["ablation"]["noHopMerge"])):
            t = x["tag"]["request"]
            out.append(f"| {name} | {label} | {'전역' if x['global'] else '-'} | {x['selectedSessions']} | {x['selectedRequests']} | {x['impactedRequests']} | {x['reductionRequests']:.1%} | {recall_label(x)} | {fmt(t['budget'])}·{fmt(t['rate'])} |")
    same = [n for n in FAULTS + LADDER if all(v[n]["ablation"][k]["selectedSessions"] == v[n]["selectedSessions"] for k in ("endpointUnion", "noHopMerge"))]
    out += ["", f"선택 세션이 정본과 같은 변형: {len(same)}/13.", "",
            "## 7. Tag 순위 품질 (리뷰 우선순위, 감소 지표 아님)", "",
            "세션 입도(계획 정의)는 Recall과 같다. 요청 입도는 보조다.", "",
            "| 변형 | 세션 입도 예산·포함 | 요청 입도 예산·포함 |", "|---|---|---|"]
    for name in FAULTS + CHANGES:
        s, q = v[name]["tag"]["session"], v[name]["tag"]["request"]
        out.append(f"| {name} | {fmt(s['budget'])}·{s['diffsInScope']}/{s['diffs']} | {fmt(q['budget'])}·{q['diffsInScope']}/{q['diffs']} |")
    out += ["", "## 8. 실제 Filter·Tag run (전체 재생과의 동등성)", "",
            "| 케이스 | run | 재생 요청 | pair | 전체 재생 같은 pair 판정 일치 | 판정 | dbstate | Undelivered·degraded |", "|---|---|---|---|---|---|---|---|"]
    for c in m["runs"]:
        out.append(f"| {c['case']} | {c['iterations']} | {c['replayed']} | {c['pairs']} | {c['pairsMatched']}/{c['pairsTotal']} | {c['verdicts']} | {'일치' if c['dbstate'] else '위반'} | {c['undelivered']}·{c['degraded']} |")
    out += ["", "`F3-mirror`(4.8)의 Undelivered 18은 미러하지 않은 요청이고 전달 실패가 아니다. New가 부분 상태라 dbstate 위반은 기대이며 판정 근거가 아니다."]
    r = v["C2"]["review"]
    out += ["", "## 9. 사람 검토 감소 (규칙 적용 후 verdict 기준)", "",
            f"C2 eval Uncertain {r['evalUncertainBefore']} → {r['evalUncertainAfter']}, learn {r['learnUncertainBefore']} → {r['learnUncertainAfter']}, 유형 {', '.join(f'`{k}`' for k in r['uncertainDiffKinds'])}. 최종 SAME 중 규칙 적용 {r['sameWithRules']} pair.", "",
            "## 10. 오프라인으로 재지 않은 것", "",
            ", ".join(f"`{k}`" for k in m["notEvaluatedOffline"]) + " = `not evaluated offline`. 실제 run의 값은 8절.", "",
            f"3 run 판정 동일: {sum(m['verdictSameAcrossRuns'].values())}/{len(m['verdictSameAcrossRuns'])}. Recall < 1 결함·변경 변형: {m['recallBelowOne'] or '없음'}."]
    return "\n".join(out) + "\n"
