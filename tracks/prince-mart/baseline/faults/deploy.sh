#!/usr/bin/env bash
# new 스택을 결함 버전(또는 legacy)으로 바꾼다. legacy 스택은 항상 Legacy 이미지다.
#   baseline/faults/deploy.sh PF1       # PF1 이미지가 있는 서비스는 PF1, 나머지는 legacy
#   baseline/faults/deploy.sh legacy    # A/A로 되돌림
# deploy/compose/.env(커밋하지 않음)에 NEW_<SVC>_TAG와 NEW_VERSION을 쓴다. 이후 reset.sh·run.py도 같은 값을 쓴다.
set -euo pipefail
cd "$(dirname "$0")/../../deploy/compose"
target=${1:?usage: deploy.sh PF<n>|legacy}
{
  echo "# baseline/faults/deploy.sh $target ($(date -u +%FT%TZ))"
  for svc in order coupon payment; do
    tag=legacy
    if [ "$target" != legacy ] && docker image inspect "prince-mart/$svc-service:$target" >/dev/null 2>&1; then tag=$target; fi
    echo "NEW_$(echo $svc | tr a-z A-Z)_TAG=$tag"
  done
  [ "$target" = legacy ] && echo "NEW_VERSION=prince-mart-legacy" || echo "NEW_VERSION=prince-mart-$target"
} > .env
cat .env
docker compose up -d --wait order-new coupon-new payment-new 2>&1 | grep -E 'Error|unhealthy' || true
for svc in order coupon payment; do
  echo "[deploy] $svc-new image=$(docker inspect prince-mart-$svc-new-1 --format '{{.Config.Image}}')"
done
