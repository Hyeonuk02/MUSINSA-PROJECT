#!/usr/bin/env bash
# S0 리셋 (Compose 구현)
#
#   ./reset.sh            # legacy 스택
#   ./reset.sh legacy new # 두 스택
#
# MySQL 데이터는 tmpfs에만 있으므로 컨테이너를 새로 만들면 데이터 디렉터리가 비고,
# 이미지가 /docker-entrypoint-initdb.d(init SQL)를 다시 실행한다. healthy는 init SQL까지
# 끝났다는 뜻이다(healthcheck가 -h 127.0.0.1 TCP ping). 이것이 S0 복원이다.
# k8s로 합칠 때는 이 스크립트가 `kubectl rollout restart deployment/mysql-*` + readiness 대기로 바뀐다.
#
# 앱 컨테이너는 재시작하지 않는다. 끊긴 커넥션은 Hikari가 버리고 새로 맺는다.
set -euo pipefail
cd "$(dirname "$0")"

stacks=("$@")
[ ${#stacks[@]} -eq 0 ] && stacks=(legacy)

dbs=()
for st in "${stacks[@]}"; do
  dbs+=("mysql-order-$st" "mysql-coupon-$st" "mysql-payment-$st")
done

echo "[reset] recreate: ${dbs[*]}"
docker compose up -d --force-recreate --no-deps --wait "${dbs[@]}"

for st in "${stacks[@]}"; do
  echo "[reset] wiremock-$st: clear request journal"
  docker compose exec -T "wiremock-$st" curl -fs -X DELETE http://127.0.0.1:8080/__admin/requests >/dev/null
done

echo "[reset] done"
