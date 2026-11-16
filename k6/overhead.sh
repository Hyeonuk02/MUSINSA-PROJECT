#!/usr/bin/env bash
# Phase 4.9 - Legacy Evidence on/off 오버헤드 측정(참고값, 판정 없음).
# off = legacy order·coupon에서 EVIDENCE_STORE_URL을 뺀다(수집기 전체 미등록, EvidenceAutoConfiguration). 이미지는 같다.
# 모드마다: env 적용 → rollout → 웜업 재생 1회(버림) → (S0 리셋 → 재생 → 자원·Evidence 수집) × N. 끝나면 legacy overlay 복원.
# 사용: k6/overhead.sh --iterations 3
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
EVIDENCE_URL="${EVIDENCE_URL:-http://localhost/_evidence}"
BASE_URL="${BASE_URL:-http://localhost}"
NODE=$(kubectl get nodes -o jsonpath='{.items[0].metadata.name}')
ITER=3
[[ "${1:-}" == "--iterations" ]] && ITER="$2"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }
restore() {
  log "restore: legacy overlay"
  kubectl apply -k deploy/k8s/legacy >/dev/null
  kubectl rollout status deployment/order -n legacy --timeout=240s | tail -1
  kubectl rollout status deployment/coupon -n legacy --timeout=240s | tail -1
}
trap restore EXIT

http_code() { curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$1" || echo 000; }
wait_404() {
  local deadline=$((SECONDS + 180))
  until [[ "$(http_code "$1")" == 404 ]]; do
    (( SECONDS < deadline )) || { log "FAIL: $1 준비 안 됨"; exit 1; }
    sleep 1
  done
}
wait_ready() {
  wait_404 "$BASE_URL/api/orders/by-key/ok-readiness-check"
  wait_404 "$BASE_URL/api/coupons/by-key/ck-readiness-check"
}
reset_db() {  # 재생이 끝나고 소비가 멎은 뒤 DB만 S0으로(Kafka·앱은 그대로 — JVM 웜업을 유지)
  sleep 3
  local db ns
  for db in mysql coupon-mysql; do for ns in legacy new; do kubectl rollout restart "deployment/$db" -n "$ns" >/dev/null; done; done
  for db in mysql coupon-mysql; do for ns in legacy new; do kubectl rollout status "deployment/$db" -n "$ns" --timeout=180s >/dev/null; done; done
  wait_ready
}
stats() {  # 파일 — legacy order·coupon의 앱·sidecar 누적 CPU와 working set
  docker exec "$NODE" crictl stats -o json > "$1"
}
replay() {  # runId
  mkdir -p "runs/$1"
  RUN_ID="$1" BASE_URL="$BASE_URL" k6 run --quiet k6/overhead.js >/dev/null
}
mode_block() {  # on|off
  local mode="$1" i rid
  log "===== mode $mode"
  if [[ "$mode" == off ]]; then
    kubectl set env deployment/order deployment/coupon -n legacy EVIDENCE_STORE_URL- >/dev/null
  else
    kubectl rollout restart deployment/order deployment/coupon -n legacy >/dev/null
  fi
  kubectl rollout status deployment/order -n legacy --timeout=240s | tail -1
  kubectl rollout status deployment/coupon -n legacy --timeout=240s | tail -1
  reset_db
  log "웜업 재생(버림)"
  replay "p49-$mode-warm"
  for ((i = 1; i <= ITER; i++)); do
    reset_db
    rid="p49-$mode-$i"
    log "측정 $rid"
    mkdir -p "runs/$rid"
    stats "runs/$rid/stats-before.json"
    replay "$rid"
    sleep 3
    stats "runs/$rid/stats-after.json"
    if [[ "$mode" == on ]]; then
      curl -sf --max-time 30 "$EVIDENCE_URL/export?runId=$rid&stack=legacy" -o "runs/$rid/legacy.json"
    fi
    "$PY" - "$rid" "$mode" <<'PY'
import json, subprocess, sys
rid, mode = sys.argv[1:]
def out(*a): return subprocess.run(a, capture_output=True, text=True).stdout.strip()
meta = {"runId": rid, "mode": mode, "git": {"rev": out("git", "rev-parse", "HEAD"), "dirty": bool(out("git", "status", "--porcelain"))},
        "images": {s: out("kubectl", "get", "deploy", s, "-n", "legacy", "-o", "jsonpath={.spec.template.spec.containers[0].image}") for s in ("order", "coupon")},
        "evidenceStoreUrl": {s: out("kubectl", "get", "deploy", s, "-n", "legacy", "-o", 'jsonpath={.spec.template.spec.containers[0].env[?(@.name=="EVIDENCE_STORE_URL")].value}') for s in ("order", "coupon")}}
json.dump(meta, open(f"runs/{rid}/run-meta.json", "w"), indent=2)
PY
  done
}
mode_block on
mode_block off
log "done"
