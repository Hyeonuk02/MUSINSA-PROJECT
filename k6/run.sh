#!/usr/bin/env bash
# Phase 2.6 - run script: preflight → (reset → k6 → barrier → export) × N
#
# 사용: k6/run.sh --run-id <base> --iterations N --vus V
#   iteration i의 runId = <base>-<i>. 결과는 runs/<runId>/{legacy.json,new.json,k6-summary.json,run-meta.json}
#
# preflight(루프 전 1회) — 하나라도 실패하면 run을 시작하지 않고 exit 1. 자동 복구는 하지 않는다.
#   노드 응답 / Istio 인증서(ingressgateway·order legacy·order new의 default NOT AFTER > 지금, fail-closed)
#   / Store 준비(게이트웨이 /_evidence/count 200) / corpus validate.py / Store에 같은 runId Evidence 없음(3.5)
# reset: MySQL rollout restart(S0) → order readiness(없는 키 조회 404) → WireMock request journal 비움
#   WireMock admin은 게이트웨이로 열지 않고 tooling pod(kubectl exec)로 호출한다(게이트웨이 표면은 /api/, /_evidence/뿐)
# barrier v2(Phase 3.2, D19): spill 회수 → k6/barrier.py — 스택별 기대 집합 = sent의 진입 홉 + corpus settle 홉(최대 30초),
#   그다음 도착 Evidence가 선언한 자식 홉 폐포(관측 호스트 OBSERVED_HOSTS로 나간 호출만, 최대 10초, 반복).
#   미달이면 누락 (requestId, hopPath)를 출력하고 export(디버깅용)만 한 뒤 exit 1 — 다음 iteration으로 가지 않는다
# export(3.1): Evidence(legacy.json·new.json) + 최종 DB 상태(dbstate-<stack>.json) + WireMock journal(wiremock-<stack>.json)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
BASE_URL="${BASE_URL:-http://localhost}"
EVIDENCE_URL="${EVIDENCE_URL:-http://localhost/_evidence}"
CORPUS=corpus/corpus-v2.json
# 관측 서비스 호스트 — externalCalls.childHopPath를 barrier 폐포에 넣는 대상(WireMock 등 외부는 Evidence를 남기지 않음)
OBSERVED_HOSTS="${OBSERVED_HOSTS:-order,coupon}"
# 관측 토픽 — events.published.childHopPath를 폐포에 넣는 대상(소비자가 있는 토픽만. order.paid.dlq는 소비자 없음)
OBSERVED_TOPICS="${OBSERVED_TOPICS:-order.paid}"
KAFKA_TOPICS="order.paid order.paid.dlq"
KAFKA_BIN=/opt/kafka/bin
READINESS_PATH=/api/orders/by-key/ok-readiness-check   # corpus에 없는 키 — 404면 order가 DB를 조회할 수 있는 상태
COUPON_READINESS_PATH=/api/coupons/by-key/ck-readiness-check
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
  for target in "istio-system istio=ingressgateway" "legacy app=order" "new app=order" "legacy app=coupon" "new app=coupon" "legacy app=kafka" "new app=kafka"; do
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

  # Phase 3.5: Store에 같은 runId의 Evidence가 남아 있으면 시작하지 않는다(자동 삭제 없음).
  # 남아 있으면 k6 완료 폴링(exists)이 이전 Evidence를 보고 New 완료 전에 다음 요청을 보낸다 — p35-v1.1-stale-1에서 실측
  local i rid n
  for ((i = 1; i <= ITERATIONS; i++)); do
    rid="$BASE-$i"
    n=$(curl -s --max-time 5 "$EVIDENCE_URL/count?runId=${rid}" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["count"])') \
      || fail "preflight: Store count 조회 실패 — runId=${rid}"
    [[ "$n" == 0 ]] || fail "preflight: Store에 runId=${rid} Evidence ${n}건이 이미 있다 — 다른 --run-id를 쓰거나 DELETE /runs/${rid} 후 재실행"
  done
  log "  store: runId $BASE-1..$ITERATIONS 비어 있음"
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
legacy_coupon_ready() { [[ "$(http_code "$BASE_URL$COUPON_READINESS_PATH")" == 404 ]]; }
new_coupon_ready() {
  [[ "$(kubectl exec -n new isolation-injected -c curl -- curl -s -o /dev/null -w '%{http_code}' --max-time 5 \
        "http://coupon.new.svc.cluster.local:8080$COUPON_READINESS_PATH" 2>/dev/null)" == 404 ]]
}
kafka_exec() {  # ns command...
  local ns="$1" pod; shift
  pod=$(pick_pod "$ns" app=kafka)
  [[ -n "$pod" ]] || return 1
  kubectl exec -n "$ns" "$pod" -c kafka -- "$@"
}
kafka_ready() { kafka_exec "$1" "$KAFKA_BIN/kafka-topics.sh" --bootstrap-server localhost:9092 --list >/dev/null 2>&1; }
# Coupon 컨슈머 그룹이 order.paid partition을 할당받았는지(CONSUMER-ID가 "-"가 아님)
coupon_assigned() {
  kafka_exec "$1" "$KAFKA_BIN/kafka-consumer-groups.sh" --bootstrap-server localhost:9092 \
      --describe --group coupon-settlement 2>/dev/null \
    | awk '$1=="coupon-settlement" && $2=="order.paid" && $7!="-" && $7!="" {found=1} END {exit !found}'
}
legacy_kafka_ready() { kafka_ready legacy; }
new_kafka_ready() { kafka_ready new; }
legacy_coupon_assigned() { coupon_assigned legacy; }
new_coupon_assigned() { coupon_assigned new; }
wiremock_reset() {  # ns tooling-pod
  local code
  code=$(kubectl exec -n "$1" "$2" -c curl -- curl -s -o /dev/null -w '%{http_code}' --max-time 5 \
         -X DELETE "http://wiremock.$1.svc.cluster.local:8080/__admin/requests")
  [[ "$code" == 200 ]] || fail "reset: WireMock $1 request journal 비우기 실패(HTTP $code)"
}

reset_s0() {
  log "reset: MySQL·Coupon MySQL·Kafka rollout restart (S0)"
  local db ns topic
  for db in mysql coupon-mysql kafka; do
    for ns in legacy new; do kubectl rollout restart "deployment/$db" -n "$ns" >/dev/null; done
  done
  for db in mysql coupon-mysql kafka; do
    for ns in legacy new; do kubectl rollout status "deployment/$db" -n "$ns" --timeout="${READY_TIMEOUT_S}s" >/dev/null; done
  done
  # Kafka: 브로커 준비 → 토픽 생성(auto.create 꺼짐, 앱의 KafkaAdmin에 기대지 않는다) → Coupon 컨슈머 할당 확인
  wait_until "$READY_TIMEOUT_S" "reset: legacy kafka 브로커" legacy_kafka_ready
  wait_until "$READY_TIMEOUT_S" "reset: new kafka 브로커" new_kafka_ready
  for ns in legacy new; do
    for topic in $KAFKA_TOPICS; do
      kafka_exec "$ns" "$KAFKA_BIN/kafka-topics.sh" --bootstrap-server localhost:9092 --create --if-not-exists \
        --topic "$topic" --partitions 1 --replication-factor 1 >/dev/null || fail "reset: $ns 토픽 $topic 생성 실패"
    done
  done
  log "  kafka legacy/new: 토픽 $KAFKA_TOPICS (partition 1)"
  wait_until "$READY_TIMEOUT_S" "reset: legacy order readiness" legacy_order_ready
  wait_until "$READY_TIMEOUT_S" "reset: new order readiness" new_order_ready
  wait_until "$READY_TIMEOUT_S" "reset: legacy coupon readiness" legacy_coupon_ready
  wait_until "$READY_TIMEOUT_S" "reset: new coupon readiness" new_coupon_ready
  log "  order·coupon legacy/new: 없는 키 조회 404 (새 DB 질의 가능)"
  wait_until "$READY_TIMEOUT_S" "reset: legacy coupon 컨슈머 할당" legacy_coupon_assigned
  wait_until "$READY_TIMEOUT_S" "reset: new coupon 컨슈머 할당" new_coupon_assigned
  log "  kafka legacy/new: coupon-settlement 그룹이 order.paid partition 할당받음"
  wiremock_reset legacy mesh-check
  wiremock_reset new isolation-injected
  log "  wiremock legacy/new: DELETE /__admin/requests 200"
}

# ---------------------------------------------------------------- barrier / export
export_run() {  # runId dir
  local stack
  for stack in legacy new; do
    curl -sf --max-time 30 "$EVIDENCE_URL/export?runId=$1&stack=$stack" -o "$2/$stack.json" \
      || fail "export: $stack 실패"
  done
  log "export: $2/legacy.json ($("$PY" -c "import json;print(len(json.load(open('$2/legacy.json'))))")건), $2/new.json ($("$PY" -c "import json;print(len(json.load(open('$2/new.json'))))")건)"
}

barrier() {  # runId dir
  log "barrier: spill 회수"
  k6/spill-recover.sh --run-id "$1" | sed 's/^/  /' || fail "barrier: spill-recover 실패"
  log "barrier: 기대 집합(corpus settle + 자식 홉 폐포, 관측 호스트 $OBSERVED_HOSTS, 관측 토픽 $OBSERVED_TOPICS)"
  if ! "$PY" k6/barrier.py --run-dir "$2" --corpus "$CORPUS" --evidence-url "$EVIDENCE_URL" \
        --observed-hosts "$OBSERVED_HOSTS" --observed-topics "$OBSERVED_TOPICS" | sed 's/^/  /'; then
    export_run "$1" "$2"
    fail "barrier 미달 — export만 하고 중단한다(다음 iteration 진행 안 함): runs/$1"
  fi
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

write_meta() {  # runId dir started finished resetSeconds
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
  COUPON_LEGACY_TAG="$(kubectl get deploy coupon -n legacy -o jsonpath='{.spec.template.spec.containers[?(@.name=="coupon")].image}')" \
  COUPON_NEW_TAG="$(kubectl get deploy coupon -n new -o jsonpath='{.spec.template.spec.containers[?(@.name=="coupon")].image}')" \
  COUPON_LEGACY_REF="$(container_image legacy coupon)" COUPON_NEW_REF="$(container_image new coupon)" \
  KAFKA_TAG="$(kubectl get deploy kafka -n legacy -o jsonpath='{.spec.template.spec.containers[?(@.name=="kafka")].image}')" \
  KAFKA_LEGACY_REF="$(container_image legacy kafka)" KAFKA_NEW_REF="$(container_image new kafka)" \
  RESET_SECONDS="$5" \
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
        "coupon": {"legacy": {"image": e["COUPON_LEGACY_TAG"], "imageRef": e["COUPON_LEGACY_REF"]},
                   "new": {"image": e["COUPON_NEW_TAG"], "imageRef": e["COUPON_NEW_REF"]}},
        "kafka": {"image": e["KAFKA_TAG"], "imageRef": {"legacy": e["KAFKA_LEGACY_REF"], "new": e["KAFKA_NEW_REF"]}},
        "evidenceStore": {"image": e["STORE_TAG"], "imageRef": e["STORE_REF"]},
        "wiremock": {"image": e["WM_TAG"], "imageRef": {"legacy": e["WM_LEGACY_REF"], "new": e["WM_NEW_REF"]}},
    },
    "appFixedClock": {"legacy": e["FIXED_LEGACY"], "new": e["FIXED_NEW"]},
    "vus": int(e["VUS"]),
    "resetSeconds": int(e["RESET_SECONDS"]),
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
  reset_start=$SECONDS
  reset_s0
  reset_seconds=$((SECONDS - reset_start))
  log "  reset 소요 ${reset_seconds}s"
  log "k6: RUN_ID=$run_id VUS=$VUS k6 run k6/run.js"
  RUN_ID="$run_id" VUS="$VUS" CORPUS="$(basename "$CORPUS")" BASE_URL="$BASE_URL" EVIDENCE_URL="$EVIDENCE_URL" \
    k6 run --quiet k6/run.js | sed 's/^/  /'
  [[ -f "$dir/k6-summary.json" ]] || fail "k6-summary.json 없음: $dir"
  barrier "$run_id" "$dir"
  export_run "$run_id" "$dir"
  k6/dbstate-export.sh --run-id "$run_id" | sed 's/^/  /' || fail "export: dbstate 실패"
  export_wiremock "$dir"
  write_meta "$run_id" "$dir" "$started" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$reset_seconds"
done
log "done: $ITERATIONS run(s) — runs/$BASE-1 .. runs/$BASE-$ITERATIONS"
