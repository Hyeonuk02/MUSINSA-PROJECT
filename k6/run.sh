#!/usr/bin/env bash
# Phase 2.6 - run script: preflight → (reset → k6 → barrier → export) × N
#
# 사용: k6/run.sh --run-id <base> --iterations N --vus V
#   iteration i의 runId = <base>-<i>. 결과는 runs/<runId>/{legacy.json,new.json,k6-summary.json,run-meta.json}
#
# preflight(루프 전 1회) — 하나라도 실패하면 run을 시작하지 않고 exit 1. 자동 복구는 하지 않는다.
#   노드 응답 / Istio 인증서(ingressgateway·order legacy·order new의 default NOT AFTER > 지금, fail-closed)
#   / Store 준비(게이트웨이 /_evidence/count 200) / corpus validate.py
# reset: MySQL rollout restart(S0) → order readiness(없는 키 조회 404) → WireMock request journal 비움
#   WireMock admin은 게이트웨이로 열지 않고 tooling pod(kubectl exec)로 호출한다(게이트웨이 표면은 /api/, /_evidence/뿐)
# barrier: spill 회수 → Store count가 legacy·new 모두 기대 건수(= k6-summary.json의 sent 길이)가 될 때까지 최대 30초.
#   미달이면 누락 requestId를 출력하고 export(디버깅용)만 한 뒤 exit 1 — 다음 iteration으로 가지 않는다
# export(3.1): Evidence(legacy.json·new.json) + 최종 DB 상태(dbstate-<stack>.json) + WireMock journal(wiremock-<stack>.json)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
BASE_URL="${BASE_URL:-http://localhost}"
EVIDENCE_URL="${EVIDENCE_URL:-http://localhost/_evidence}"
CORPUS=corpus/corpus-v1.json
READINESS_PATH=/api/orders/by-key/ok-readiness-check   # corpus에 없는 키 — 404면 order가 DB를 조회할 수 있는 상태
BARRIER_TIMEOUT_S=30
READY_TIMEOUT_S=180

BASE=""; ITERATIONS=""; VUS=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id) BASE="${2:-}"; shift 2 ;;
    --iterations) ITERATIONS="${2:-}"; shift 2 ;;
    --vus) VUS="${2:-}"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
if [[ ! "$BASE" =~ ^[A-Za-z0-9._-]{1,100}$ || ! "$ITERATIONS" =~ ^[1-9][0-9]*$ || ! "$VUS" =~ ^[1-9][0-9]*$ ]]; then
  echo "usage: $0 --run-id <base> --iterations N --vus V" >&2
  exit 2
fi

log() { echo "[$(date -u +%H:%M:%S)] $*"; }
fail() { echo "[$(date -u +%H:%M:%S)] FAIL: $*" >&2; exit 1; }
http_code() { curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$@" || echo 000; }

# 종료 중이 아닌 Running pod 하나
pick_pod() {  # ns selector
  kubectl get pods -n "$1" -l "$2" --no-headers \
    -o custom-columns=NAME:.metadata.name,DEL:.metadata.deletionTimestamp,PHASE:.status.phase 2>/dev/null \
    | awk '$2=="<none>" && $3=="Running" {print $1; exit}'
}

# ---------------------------------------------------------------- preflight
preflight() {
  log "preflight"
  kubectl get nodes --request-timeout=10s >/dev/null 2>&1 || fail "preflight: kubectl get nodes 응답 없음"
  log "  nodes: $(kubectl get nodes --no-headers | awk '{print $1"("$2")"}' | tr '\n' ' ')"

  command -v istioctl >/dev/null || fail "preflight: istioctl 없음 — 인증서를 확인할 수 없다(fail-closed)"
  local target ns sel pod table verdict
  for target in "istio-system istio=ingressgateway" "legacy app=order" "new app=order"; do
    ns="${target%% *}"; sel="${target#* }"
    pod=$(pick_pod "$ns" "$sel")
    [[ -n "$pod" ]] || fail "preflight: $ns/$sel Running pod 없음"
    table=$(istioctl proxy-config secret "$pod.$ns" 2>&1) || fail "preflight: istioctl proxy-config secret $pod.$ns 실패: $table"
    # 표의 default 행: RESOURCE NAME / TYPE(Cert Chain, 두 단어) / STATUS / VALID CERT / SERIAL / NOT AFTER / NOT BEFORE
    verdict=$(echo "$table" | "$PY" -c '
import sys, datetime as dt
rows = [l.split() for l in sys.stdin if l.startswith("default ")]
if len(rows) != 1 or len(rows[0]) < 8:
    sys.exit("default 인증서 행을 해석할 수 없다")
valid, not_after = rows[0][4], rows[0][6]
try:
    exp = dt.datetime.strptime(not_after, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
except ValueError:
    sys.exit(f"NOT AFTER를 해석할 수 없다: {not_after}")
now = dt.datetime.now(dt.timezone.utc)
if valid != "true" or exp <= now:
    sys.exit(f"만료 또는 무효: VALID CERT={valid} NOT AFTER={not_after}")
print(f"VALID CERT={valid} NOT AFTER={not_after} (남은 {int((exp - now).total_seconds() // 60)}분)")
' 2>&1) || fail "preflight: $ns/$pod 인증서 — $verdict"
    log "  cert $ns/$pod: $verdict"
  done

  local code
  code=$(http_code "$EVIDENCE_URL/count?runId=preflight")
  [[ "$code" == 200 ]] || fail "preflight: Store 준비 안 됨 — $EVIDENCE_URL/count → HTTP $code"
  log "  store: /_evidence/count 200"

  "$PY" corpus/validate.py "$CORPUS" >/dev/null || fail "preflight: corpus/validate.py 실패"
  log "  corpus: validate.py PASS"
}

# ---------------------------------------------------------------- reset
wait_until() {  # timeout_s description command...
  local timeout="$1" what="$2"; shift 2
  local deadline=$((SECONDS + timeout))
  until "$@"; do
    (( SECONDS < deadline )) || fail "$what: ${timeout}s 안에 준비되지 않음"
    sleep 1
  done
}
legacy_order_ready() { [[ "$(http_code "$BASE_URL$READINESS_PATH")" == 404 ]]; }
new_order_ready() {
  [[ "$(kubectl exec -n new isolation-injected -c curl -- curl -s -o /dev/null -w '%{http_code}' --max-time 5 \
        "http://order.new.svc.cluster.local:8080$READINESS_PATH" 2>/dev/null)" == 404 ]]
}
wiremock_reset() {  # ns tooling-pod
  local code
  code=$(kubectl exec -n "$1" "$2" -c curl -- curl -s -o /dev/null -w '%{http_code}' --max-time 5 \
         -X DELETE "http://wiremock.$1.svc.cluster.local:8080/__admin/requests")
  [[ "$code" == 200 ]] || fail "reset: WireMock $1 request journal 비우기 실패(HTTP $code)"
}

reset_s0() {
  log "reset: MySQL rollout restart (S0)"
  kubectl rollout restart deployment/mysql -n legacy >/dev/null
  kubectl rollout restart deployment/mysql -n new >/dev/null
  kubectl rollout status deployment/mysql -n legacy --timeout="${READY_TIMEOUT_S}s" >/dev/null
  kubectl rollout status deployment/mysql -n new --timeout="${READY_TIMEOUT_S}s" >/dev/null
  wait_until "$READY_TIMEOUT_S" "reset: legacy order readiness" legacy_order_ready
  wait_until "$READY_TIMEOUT_S" "reset: new order readiness" new_order_ready
  log "  order legacy/new: 없는 키 조회 404 (새 MySQL 질의 가능)"
  wiremock_reset legacy mesh-check
  wiremock_reset new isolation-injected
  log "  wiremock legacy/new: DELETE /__admin/requests 200"
}

# ---------------------------------------------------------------- barrier / export
store_count() {  # runId stack
  curl -s --max-time 5 "$EVIDENCE_URL/count?runId=$1&stack=$2" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["count"])' 2>/dev/null || echo -1
}

export_run() {  # runId dir
  local stack
  for stack in legacy new; do
    curl -sf --max-time 30 "$EVIDENCE_URL/export?runId=$1&stack=$stack" -o "$2/$stack.json" \
      || fail "export: $stack 실패"
  done
  log "export: $2/legacy.json ($("$PY" -c "import json;print(len(json.load(open('$2/legacy.json'))))")건), $2/new.json ($("$PY" -c "import json;print(len(json.load(open('$2/new.json'))))")건)"
}

# k6-summary.json의 sent와 비교해 Store에 없는 id (stack별)
missing_ids() {  # dir
  "$PY" - "$1" <<'EOF'
import json, sys
d = sys.argv[1]
sent = json.load(open(f"{d}/k6-summary.json"))["sent"]
for stack in ("legacy", "new"):
    have = {e["replayRequestId"] for e in json.load(open(f"{d}/{stack}.json"))}
    miss = [r for r in sent if r not in have]
    print(f"  missing {stack}: {len(miss)} {' '.join(miss)}")
EOF
}

barrier() {  # runId dir
  log "barrier: spill 회수"
  k6/spill-recover.sh --run-id "$1" | sed 's/^/  /' || fail "barrier: spill-recover 실패"
  local expected
  expected=$("$PY" - "$2/k6-summary.json" <<'EOF'
import json, sys
s = json.load(open(sys.argv[1]))
skipped = {r for d in s["degraded"] for r in d["skipped"]}
assert not skipped & set(s["sent"]), "skipped 요청이 sent에 있다"
print(len(s["sent"]))
EOF
)
  log "barrier: 기대 건수 $expected (= sent 길이; 건너뛴 요청은 sent에 없다)"
  local deadline=$((SECONDS + BARRIER_TIMEOUT_S)) legacy new
  while :; do
    legacy=$(store_count "$1" legacy); new=$(store_count "$1" new)
    if [[ "$legacy" == "$expected" && "$new" == "$expected" ]]; then
      log "  count legacy=$legacy new=$new — 충족"
      return 0
    fi
    if (( SECONDS >= deadline )); then
      log "  count legacy=$legacy new=$new — ${BARRIER_TIMEOUT_S}s 안에 기대 건수 $expected 미달"
      export_run "$1" "$2"
      missing_ids "$2"
      fail "barrier 미달 — export만 하고 중단한다(다음 iteration 진행 안 함): runs/$1"
    fi
    sleep 1
  done
}

container_image() {  # ns container → "image@imageRef" (노드 containerd 기준)
  local node
  node=$(kubectl get nodes -o jsonpath='{.items[0].metadata.name}')
  docker exec "$node" crictl ps -o json 2>/dev/null | "$PY" -c '
import json, sys
ns, name = sys.argv[1], sys.argv[2]
for c in json.load(sys.stdin)["containers"]:
    l = c["labels"]
    if l.get("io.kubernetes.pod.namespace") == ns and l.get("io.kubernetes.container.name") == name:
        print(c["imageRef"]); break
' "$1" "$2"
}

export_wiremock() {  # dir
  local stack pod
  for stack in legacy new; do
    pod=$([[ "$stack" == legacy ]] && echo mesh-check || echo isolation-injected)
    kubectl exec -n "$stack" "$pod" -c curl -- curl -sf --max-time 10 \
      "http://wiremock.$stack.svc.cluster.local:8080/__admin/requests" > "$1/wiremock-$stack.json" \
      || fail "export: WireMock $stack journal 실패"
  done
  log "export: wiremock journal legacy $("$PY" -c "import json;print(len(json.load(open('$1/wiremock-legacy.json'))['requests']))")건, new $("$PY" -c "import json;print(len(json.load(open('$1/wiremock-new.json'))['requests']))")건"
}

write_meta() {  # runId dir started finished
  local fixed_legacy fixed_new
  fixed_legacy=$(kubectl get deploy order -n legacy -o jsonpath='{.spec.template.spec.containers[?(@.name=="order")].env[?(@.name=="APP_FIXED_CLOCK")].value}')
  fixed_new=$(kubectl get deploy order -n new -o jsonpath='{.spec.template.spec.containers[?(@.name=="order")].env[?(@.name=="APP_FIXED_CLOCK")].value}')
  RUN_ID="$1" DIR="$2" STARTED="$3" FINISHED="$4" VUS="$VUS" CORPUS="$CORPUS" \
  FIXED_LEGACY="$fixed_legacy" FIXED_NEW="$fixed_new" \
  ORDER_LEGACY_TAG="$(kubectl get deploy order -n legacy -o jsonpath='{.spec.template.spec.containers[?(@.name=="order")].image}')" \
  ORDER_NEW_TAG="$(kubectl get deploy order -n new -o jsonpath='{.spec.template.spec.containers[?(@.name=="order")].image}')" \
  ORDER_LEGACY_REF="$(container_image legacy order)" ORDER_NEW_REF="$(container_image new order)" \
  STORE_TAG="$(kubectl get deploy evidence-store -n verify -o jsonpath='{.spec.template.spec.containers[0].image}')" \
  STORE_REF="$(container_image verify evidence-store)" \
  WM_TAG="$(kubectl get deploy wiremock -n legacy -o jsonpath='{.spec.template.spec.containers[0].image}')" \
  WM_LEGACY_REF="$(container_image legacy wiremock)" WM_NEW_REF="$(container_image new wiremock)" \
  GIT_REV="$(git rev-parse HEAD)" GIT_DIRTY="$([[ -n "$(git status --porcelain)" ]] && echo true || echo false)" \
  K6_VERSION="$(k6 version 2>/dev/null | head -1)" \
  ISTIO_VERSION="$(istioctl version --short 2>/dev/null | tr '\n' ' ' | sed 's/ *$//')" \
  "$PY" - <<'EOF'
import hashlib, json, os
e = os.environ
corpus = json.load(open(e["CORPUS"]))
meta = {
    "runId": e["RUN_ID"],
    "corpus": {"version": corpus["version"], "path": e["CORPUS"],
               "sha256": hashlib.sha256(open(e["CORPUS"], "rb").read()).hexdigest()},
    "images": {
        "order": {"legacy": {"image": e["ORDER_LEGACY_TAG"], "imageRef": e["ORDER_LEGACY_REF"]},
                  "new": {"image": e["ORDER_NEW_TAG"], "imageRef": e["ORDER_NEW_REF"]}},
        "evidenceStore": {"image": e["STORE_TAG"], "imageRef": e["STORE_REF"]},
        "wiremock": {"image": e["WM_TAG"], "imageRef": {"legacy": e["WM_LEGACY_REF"], "new": e["WM_NEW_REF"]}},
    },
    "appFixedClock": {"legacy": e["FIXED_LEGACY"], "new": e["FIXED_NEW"]},
    "vus": int(e["VUS"]),
    "git": {"rev": e["GIT_REV"], "dirty": e["GIT_DIRTY"] == "true"},
    "k6Version": e["K6_VERSION"],
    "istioVersion": e["ISTIO_VERSION"],
    "startedAt": e["STARTED"],
    "finishedAt": e["FINISHED"],
}
json.dump(meta, open(os.path.join(e["DIR"], "run-meta.json"), "w"), indent=2)
EOF
  log "run-meta: $2/run-meta.json"
}

# ---------------------------------------------------------------- main
preflight
for ((i = 1; i <= ITERATIONS; i++)); do
  run_id="$BASE-$i"
  dir="runs/$run_id"
  [[ ! -e "$dir" ]] || fail "$dir 가 이미 있다 — 다른 --run-id를 쓴다"
  mkdir -p "$dir"
  started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  log "===== iteration $i/$ITERATIONS runId=$run_id vus=$VUS"
  reset_s0
  log "k6: RUN_ID=$run_id VUS=$VUS k6 run k6/run.js"
  RUN_ID="$run_id" VUS="$VUS" BASE_URL="$BASE_URL" EVIDENCE_URL="$EVIDENCE_URL" k6 run --quiet k6/run.js | sed 's/^/  /'
  [[ -f "$dir/k6-summary.json" ]] || fail "k6-summary.json 없음: $dir"
  barrier "$run_id" "$dir"
  export_run "$run_id" "$dir"
  k6/dbstate-export.sh --run-id "$run_id" | sed 's/^/  /' || fail "export: dbstate 실패"
  export_wiremock "$dir"
  write_meta "$run_id" "$dir" "$started" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
done
log "done: $ITERATIONS run(s) — runs/$BASE-1 .. runs/$BASE-$ITERATIONS"
