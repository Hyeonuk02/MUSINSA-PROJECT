# Phase 3.4 보고서 — Normalization v1 + 판정 엔진 v1 + Rule + Human Review

- 작업일: 2026-10-13
- 범위: `engine/`만. 클러스터 접근 없음(D12). 입력은 `runs/p33-1..3`(3.3 A/A 산출물)와 `engine/rules/`. 수집기(poc.evidence)·스키마·앱 코드는 건드리지 않았다(Legacy 고정 이미지 `order-app`·`coupon-app:phase3.3-base` 그대로)
- 결과: **PASS** — p33-1..3 전 pair SAME(각 58), Uncertain 0, dbstate 일치, 변조 테스트 포함 pytest 26건 통과

## 0. 결정 필요 사항

없음. 계획에 없던 결정은 모두 `docs/phase3-plan.md` 3.4 "구현 시 확정 (3.4)"에 적었다. 그중 확인해 두면 좋은 것 두 가지(질문 아님, 다음 단계에서 바꿀 수 있음):
- 응답·payload의 **키 이름 `id` 제외**(모든 깊이) — Phase 2 diff_v0와 같은 유일한 제외 필드. 이게 없으면 VU=3에서 auto id 교차로 p33-1에서 8 pair가 DIFF(B0·B1·C 공통)
- learned 규칙은 **eval 세션에도 적용된다**(그게 3.6 평가의 의미). eval은 *규칙을 만드는* 데만 쓰이지 않는다

## 1. 끝난 기준별 결과

| 기준 | 결과 | 근거 |
|---|---|---|
| A/A run(p33-1..3) 전 pair SAME, Uncertain 0 | PASS | 각 run pairs 58 → `{SAME: 58}` (eval 33 / learn 25). `logs/phase3.4-verdict-p33.txt` |
| 집계(dbstate) 일치 | PASS | 3 run 모두 `dbstate_equal OK` — orders 8건(amount 합 61500), order_items 10건, coupons 6건, 테이블 sha256 3 run 동일 |
| Undelivered·degraded 지표 | 0 / 0 | summary.undelivered legacy 0·new 0, degraded 0 (3 run) |
| B0·B1·C 모두 A/A 전 pair SAME | PASS | p33-1..3 × 3 arm 모두 `{SAME: 58}` |
| 출력 결정론 | PASS | 같은 run 2회 실행 sha256 동일(p33-1 `becdbba2…`, p33-2 `23f504f2…`, p33-3 `8bf8e721…`), `test_output_deterministic` |
| 변조: amount 변경 → CV(응답) | PASS | `test_amount_change_is_cv` — `response_body_compatible` |
| 변조: INSERT 삭제 → CV(쓰기 집합) | PASS | `test_insert_removed_is_cv_write_set` — order_items INSERT 제거 → `writeSet` |
| 변조: 응답 필드 추가 → Uncertain → 라벨 → Improvement | PASS | `test_response_field_added_is_uncertain`, `test_review.py::test_response_field_added_uncertain_then_label_improvement` |
| 변조: 게이트웨이 2회 → CV(세션 규칙) | PASS | `gateway_calls_per_idem_key_le_1[idem-R000029]: legacy 1 / new 2` |
| 변조: publish seq를 COMMIT_BEGIN 앞으로 → CV(타임라인) | PASS | publish 6↔COMMIT_BEGIN 4 교환 → `publish_after_commit_begin` |
| 변조: `0.h2` 복제 → CV(hop 집합) | PASS | `hop_set: legacy만 [] / new만 ['0.h2']`, 0.h2는 pair로 세지 않음 |
| 변조: SELECT +1 → Uncertain(미선언) / CV(선언) | PASS | 미선언: `dbRead.countDelta` 하나만 Uncertain / `max_selects.endpoints: {order.get: 2}` → `new readCount 3 > 2` |
| 추가: ack failed → CV | PASS | `events.published[0].ack` |
| 추가: consumeOutcome failed → CV | PASS | R000029/0.e1 (`consume.order.paid`) |
| 추가: callTree만 다름 → Uncertain | PASS | `callTree.sequenceReplaced` 하나만 |
| 추가: transactions name만 다름 → Uncertain | PASS | `transactions.nameChanged` 하나만 |
| 추가: 규칙에 sessionId 등 → 로더 거부 | PASS | sessionId·replayRequestId·runId 3건 parametrize |
| 추가: learn 라벨이 eval Uncertain을 지움 | PASS | R000028(S006 learn)·R000034(S007 eval) 같은 uid → learn 라벨 → 둘 다 해소. `logs/phase3.4-review-demo.txt` |
| (추가) eval에만 있는 uid는 list에 안 보이고 label 거부 | PASS | `test_eval_only_uid_cannot_be_labeled` (exit 2, 파일 생성 없음) |
| (추가) 쿠폰 전이 순서 위반 → CV | PASS | use 응답 409로 변조 → settle 소비 홉 `coupon_transition_order[ck-R000026]` |
| (추가) CGLIB·Kt 접미사만 다른 callTree → SAME | PASS | `test_proxy_and_kotlin_names_normalized` |
| (추가) status 불일치는 규칙과 무관하게 CV | PASS | `test_status_mismatch_never_explained_by_rule` |
| pytest가 커밋된 코드에서 통과 | PASS | 커밋 1 직후 미커밋 파일을 stash한 트리에서 23 passed, 커밋 2 후 26 passed. `logs/phase3.4-pytest.txt` |

판정 요약 표 (p33-1·2·3 동일)

| split | SAME | IMPROVEMENT | UNCERTAIN | CV |
|---|---|---|---|---|
| learn | 25 | 0 | 0 | 0 |
| eval | 33 | 0 | 0 | 0 |

| endpoint | SAME | 나머지 |
|---|---|---|
| order.create | 9 | 0 |
| order.get | 12 | 0 |
| order.pay | 8 | 0 |
| order.cancel | 1 | 0 |
| coupon.create | 6 | 0 |
| coupon.get | 6 | 0 |
| coupon.use | 9 | 0 |
| consume.order.paid | 7 | 0 |

Undelivered 0, degraded 0, runChecks `dbstate_equal` OK.

## 2. 변경 파일·커밋

| 커밋 | 내용 |
|---|---|
| `0319e45` phase3.4: normalize·verdict·rules·tests | `engine/normalize.py`, `engine/ruleset.py`, `engine/verdict.py`, `engine/rules/{contract.yaml, improvement.yaml, learned/.gitkeep}`, `engine/tests/{conftest.py, test_engine.py, make_fixture.py, fixtures/p33-mini/}`, `requirements.txt`(PyYAML 6.0.3, pytest 8.4.2), `.gitignore`(.pytest_cache), `docs/phase3-plan.md`(3.4 구현 시 확정 추가) |
| (이 커밋) phase3.4: review + 보고서 | `engine/review.py`, `engine/tests/test_review.py`, `engine/verdict.py`(게이트웨이 위반을 양쪽 스택 pair에 붙임), `docs/phase3-plan.md`(같은 문구), `docs/reports/phase3.4.md`, `docs/reports/logs/phase3.4-*.txt`, `CLAUDE.md`(3.4 상태) |

## 3. 실행 명령·주요 출력

```
.venv/bin/python -m pytest engine/tests -v            → 26 passed   (logs/phase3.4-pytest.txt)
.venv/bin/python engine/verdict.py --run runs/p33-N [--arm B0|B1]
  == p33-1  arm C  pairs 58  {'SAME': 58}  … run dbstate_equal: OK, Undelivered 0/0, degraded 0
  == p33-1  arm B0 pairs 58  {'SAME': 58}   == p33-1  arm B1 pairs 58  {'SAME': 58}   (p33-2·3 동일)
                                                       (logs/phase3.4-verdict-p33.txt)
.venv/bin/python engine/review.py list --run runs/p33-N --split learn
  == p33-N  learn Uncertain 유형 0                     (logs/phase3.4-review-list-p33.txt)
review 데모(fixture 사본, R000028·R000034에 note 추가):
  UNCERTAIN 2 → list: [501c42bf89a5] order.get response.addedFields {fields:[note]} (learn 1건만 표시)
  → label --as improvement → rules/learned/501c42bf89a5.yaml → IMPROVEMENT 2 (eval 포함)
                                                       (logs/phase3.4-review-demo.txt)
verdict.json engine: {version: "engine-v1 (phase3.4)", rules: {contract.yaml: sha256:b81bbec6…, improvement.yaml: sha256:da4339d1…}}
```

## 4. Legacy/New 비교 표 (3 run, arm C)

| 축 | p33-1 | p33-2 | p33-3 |
|---|---|---|---|
| response.status·body(id 제외) | 58/58 동일 | 58/58 | 58/58 |
| writeSet | 동일 | 동일 | 동일 |
| externalCalls(WireMock·coupon) | 동일 | 동일 | 동일 |
| events.published·event(소비) | 동일, ack ok | 동일 | 동일 |
| transactions outcome·name | 동일 | 동일 | 동일 |
| consumeOutcome | 7/7 ok | 7/7 | 7/7 |
| hop 집합 | 동일 | 동일 | 동일 |
| readCount·fingerprint·callTree | 동일 | 동일 | 동일 |
| dbstate(orders·order_items·coupons) | 동일 | 동일 | 동일 |
| 세션 검사(게이트웨이 ≤1, 쿠폰 전이) | 위반 0 | 0 | 0 |

## 5. 지시와 다르게 구현한 것

- **fixture에 S007(eval) 추가**: 지시는 S001·S006·S008(모두 learn). "learn 라벨이 eval Uncertain을 지움"·"eval uid 라벨 거부"를 fixture만으로 보이려면 같은 유형(order.get)의 eval 세션이 필요해 S007을 넣었다
- **fixture runId 치환**: 입력 계약(runId == 디렉터리 이름) 때문에 `runId`·`x-run-id`를 `p33-mini`로. 그 외 Evidence는 원문. corpus는 해당 세션만 담은 `corpus.json` 사본(verdict는 run 디렉터리의 corpus.json을 run-meta 경로보다 먼저 씀). dbstate는 run 전체 값(세션별로 자를 수 없음 — 양쪽 동일성만 보므로 충분)
- **built-in `response_body_compatible`** 추가: 지시의 built-in 목록에 없으나 "amount 변경 → CV(응답)"과 "필드 추가 → Uncertain"을 함께 만족시키려면 응답 body 값 변경·삭제를 CV로 보는 검사가 필요. 규칙이 설명하면 예외(값 변경을 Improvement로 승인하는 경로를 남김)
- **테스트 파일 분리**: review 라벨 흐름 테스트 3건은 `test_review.py`로 — 커밋 1(review.py 없음)에서도 pytest가 통과해야 해서. 커밋 1에는 "필드 추가 → Uncertain"까지만
- **B0의 "휘발 필드"**에 body의 `id`(와 그것을 포함한 bodyHash), 요청 헤더 `x-run-id`를 포함 — 없으면 A/A에서 B0이 SAME이 될 수 없다
- **`dbRead.orderChanged` 없음**: 같은 SELECT 집합이 순서만 바뀐 경우도 `dbRead.fingerprintReplaced`(from/to = 전체 순서열)로 — diffKind 목록을 지시 범위로 유지

## 6. 문제·해결·한계

- **문제**: 첫 실행에서 p33-1 eval 8 pair가 CV(`response.valueChanged id 1→3`). 원인 VU=3에서 세션 간 auto id 교차. **해결**: Normalization v1에 Phase 2와 같은 `id` 키 제외. 이후 3 run × 3 arm 전 pair SAME
- **한계 — 규칙 scope**: 3.4의 매칭은 요청 단위 diff 항목에만 적용. `scope: session|run`은 로더가 받고 기록하지만 세션·run 단위 매칭 의미는 아직 없다(필요해지면 확장)
- **한계 — 라벨 불가 diff**: `externalCalls.responseHashChanged`, events payload 값 변경·삭제는 matcher가 없어 라벨할 수 없다 → Uncertain 또는 CV로만. 계약 판단이 필요한 영역이라 의도적
- **세션 검사 위치**: `gateway_calls_per_idem_key_le_1` 위반은 세션 전체가 아니라 그 Idempotency-Key를 가진 pair(양쪽 어느 스택에서든)에 붙인다
- **한계 — dbstate 단위**: fixture의 dbstate는 run 전체 값이라 fixture 세션 부분과 일치하지 않는다(양쪽 동일성 검사만 하므로 판정에는 영향 없음)
- uid는 detail 전체를 해시하므로 같은 diffKind라도 필드 집합이 다르면 다른 uid. 넓은 규칙은 `--match-file`로 사람이 직접 쓴다
