#!/usr/bin/env bash
# Phase 2.4b - Evidence spill 회수
#
# order pod가 Store로 보내지 못한 Evidence는 (pod 안) /var/evidence/spill/<runId>/<replayRequestId>-<stack>.json에
# Store로 보낼 바이트 그대로 남는다(스택별 hostPath: 노드 /var/evidence/spill/<stack>, 노드 1개 전제). 이 스크립트는 그 파일을 읽어
# 게이트웨이 경유 /_evidence/evidence로 POST하고, 200이면 pod에서 지운다.
# 멱등: Store는 같은 키를 덮어쓴다. 2.6 run.sh의 flush barrier가 호출한다.
#
# 각 스택 pod는 자기 hostPath만 보지만, 방어적으로 자기 stack 파일(*-<stack>.json)만 처리한다.
#
# 사용: k6/spill-recover.sh --run-id <runId>
# env:  EVIDENCE_URL (기본 http://localhost/_evidence)
# 종료 코드: 0 = 전부 회수(또는 회수할 것 없음), 1 = 실패 파일 남음, 2 = 사용법·환경 오류
set -euo pipefail

EVIDENCE_URL="${EVIDENCE_URL:-http://localhost/_evidence}"
SPILL_ROOT=/var/evidence/spill
RUN_ID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id) RUN_ID="${2:-}"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
if [[ ! "$RUN_ID" =~ ^[A-Za-z0-9._-]{1,128}$ ]]; then
  echo "usage: $0 --run-id <runId>   ([A-Za-z0-9._-]{1,128})" >&2
  exit 2
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
failed=0

# 종료 중이 아닌 Running order pod 하나
pick_pod() {
  kubectl get pods -n "$1" -l app=order --no-headers \
    -o custom-columns=NAME:.metadata.name,DEL:.metadata.deletionTimestamp,PHASE:.status.phase \
    | awk '$2=="<none>" && $3=="Running" {print $1; exit}'
}

for stack in legacy new; do
  ns="$stack"
  pod=$(pick_pod "$ns")
  if [[ -z "$pod" ]]; then
    echo "[$stack] Running order pod 없음" >&2
    exit 2
  fi
  files=$(kubectl exec -n "$ns" "$pod" -c order -- sh -c "ls -1 '$SPILL_ROOT/$RUN_ID' 2>/dev/null || true" \
          | grep -E "^R[0-9A-Za-z._-]*-${stack}\.json$" || true)
  n=0; ok=0
  for f in $files; do
    n=$((n + 1))
    kubectl exec -n "$ns" "$pod" -c order -- cat "$SPILL_ROOT/$RUN_ID/$f" > "$tmp/body.json"
    code=$(curl -s -o "$tmp/resp" -w '%{http_code}' -X POST \
             -H 'Content-Type: application/json' -H 'X-Evidence-Internal: true' \
             --data-binary @"$tmp/body.json" "$EVIDENCE_URL/evidence" || echo 000)
    if [[ "$code" == "200" ]]; then
      kubectl exec -n "$ns" "$pod" -c order -- rm -f "$SPILL_ROOT/$RUN_ID/$f"
      ok=$((ok + 1))
    else
      echo "[$stack] FAIL $f -> HTTP $code $(cat "$tmp/resp" 2>/dev/null)" >&2
      failed=$((failed + 1))
    fi
  done
  echo "[$stack] pod=$pod spill=$n recovered=$ok"
  # 빈 run 디렉터리 정리(다른 스택 파일이 남아 있으면 rmdir이 실패하고 그대로 둔다)
  kubectl exec -n "$ns" "$pod" -c order -- sh -c "rmdir '$SPILL_ROOT/$RUN_ID' 2>/dev/null || true"
done

for stack in legacy new; do
  echo "store count runId=$RUN_ID stack=$stack: $(curl -s "$EVIDENCE_URL/count?runId=$RUN_ID&stack=$stack")"
done
[[ $failed -eq 0 ]] || { echo "회수 실패 $failed건 — 파일은 pod에 남아 있다" >&2; exit 1; }
