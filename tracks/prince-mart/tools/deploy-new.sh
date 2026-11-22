#!/usr/bin/env bash
# pm-new에 올릴 New 버전을 바꾼다. legacy(pm-legacy)는 건드리지 않는다.
#
# 사용: tracks/prince-mart/tools/deploy-new.sh base        # 매니페스트 그대로(:base, EVIDENCE_VERSION=legacy-eq)
#       tracks/prince-mart/tools/deploy-new.sh PF<n>       # 매니페스트로 되돌린 뒤 그 결함의 서비스만 :PF<n>, EVIDENCE_VERSION=PF<n>
#   이미지 prince-mart/<svc>-service:PF<n>은 미리 빌드해 kind에 넣어 둔다(tools/faults/README.md).
#   커밋된 new overlay는 바꾸지 않는다(결함 run은 kubectl set image/env로만). 실제 이미지는 run-meta.json에 남는다.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
NS=pm-new
target="${1:-}"
case "$target" in
  base) svc="" ;;
  PF1|PF2|PF6) svc=payment ;;
  PF3|PF4|PF5|PF7|PF8|PF9|PF10) svc=order ;;
  *) echo "usage: $0 base|PF<n>" >&2; exit 2 ;;
esac
kubectl apply -k tracks/prince-mart/k8s/new >/dev/null
if [[ -n "$svc" ]]; then
  kubectl set image "deployment/$svc" "$svc=prince-mart/$svc-service:$target" -n "$NS" >/dev/null
  kubectl set env "deployment/$svc" "EVIDENCE_VERSION=$target" -n "$NS" -c "$svc" >/dev/null
fi
for d in order coupon payment; do
  kubectl rollout status "deployment/$d" -n "$NS" --timeout=300s >/dev/null
done
for d in order coupon payment; do
  img=$(kubectl get deploy "$d" -n "$NS" -o jsonpath="{.spec.template.spec.containers[?(@.name==\"$d\")].image}")
  ver=$(kubectl get deploy "$d" -n "$NS" -o jsonpath="{.spec.template.spec.containers[?(@.name==\"$d\")].env[?(@.name==\"EVIDENCE_VERSION\")].value}")
  echo "pm-new $d: $img (EVIDENCE_VERSION=$ver)"
done
