#!/usr/bin/env bash
# Phase 3.1 - 최종 DB 상태 export (run 단위 집계 비교의 입력)
#
# 스택별 MySQL에서 테이블마다 count, 숫자 컬럼 sum, business key 순 canonical 행의 sha256을 뽑아
# runs/<runId>/dbstate-<stack>.json에 쓴다. auto id·시각 컬럼은 행에서 뺀다(스택 간 같다는 보장이 없거나 잡음).
# 외래키(order_items.order_id)는 auto id라 business key(order_key)로 바꿔 넣는다.
#
# 사용: k6/dbstate-export.sh --run-id <runId>   (run.sh가 barrier·export 뒤에 호출)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
RUN_ID=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id) RUN_ID="${2:-}"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ "$RUN_ID" =~ ^[A-Za-z0-9._-]{1,128}$ ]] || { echo "usage: $0 --run-id <runId>" >&2; exit 2; }
DIR="$ROOT/runs/$RUN_ID"
mkdir -p "$DIR"

# 테이블 정의: 이름 | 행 SELECT(business key 순, id·시각 제외) | sum 대상 컬럼(쉼표)
TABLES=(
  "orders|SELECT order_key, status, amount, transaction_id, idempotency_key FROM orders ORDER BY order_key|amount"
  "order_items|SELECT o.order_key, i.line_no, i.sku, i.qty, i.price FROM order_items i JOIN orders o ON o.id = i.order_id ORDER BY o.order_key, i.line_no|qty,price"
)

for stack in legacy new; do
  pod=$(kubectl get pods -n "$stack" -l app=mysql --no-headers \
        -o custom-columns=NAME:.metadata.name,DEL:.metadata.deletionTimestamp,PHASE:.status.phase \
        | awk '$2=="<none>" && $3=="Running" {print $1; exit}')
  [[ -n "$pod" ]] || { echo "[$stack] Running mysql pod 없음" >&2; exit 1; }
  tmp=$(mktemp -d)
  for spec in "${TABLES[@]}"; do
    name="${spec%%|*}"; rest="${spec#*|}"; query="${rest%%|*}"
    kubectl exec -n "$stack" "$pod" -c mysql -- \
      mysql -upoc -ppoc orders -N -B --raw -e "$query" 2>/dev/null > "$tmp/$name.tsv"
  done
  TABLES_SPEC="$(printf '%s\n' "${TABLES[@]}")" TMP="$tmp" OUT="$DIR/dbstate-$stack.json" "$PY" - <<'EOF'
import hashlib, json, os
out = {"tables": {}}
for spec in os.environ["TABLES_SPEC"].strip().splitlines():
    name, query, sums = spec.split("|")
    rows = [line.split("\t") for line in open(os.path.join(os.environ["TMP"], f"{name}.tsv"), encoding="utf-8").read().splitlines()]
    cols = [c.strip().split(".")[-1].split(" ")[-1] for c in query.split("SELECT", 1)[1].split("FROM", 1)[0].split(",")]
    canonical = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    out["tables"][name] = {
        "count": len(rows),
        "sum": {c: sum(int(r[cols.index(c)]) for r in rows if r[cols.index(c)] != "NULL") for c in sums.split(",") if c},
        "sha256": "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "columns": cols,
    }
json.dump(out, open(os.environ["OUT"], "w"), ensure_ascii=False, indent=2, sort_keys=True)
EOF
  rm -rf "$tmp"
  echo "[$stack] dbstate: $("$PY" -c "import json;d=json.load(open('$DIR/dbstate-$stack.json'));print(', '.join(f\"{t}={v['count']}\" for t,v in d['tables'].items()))")"
done
