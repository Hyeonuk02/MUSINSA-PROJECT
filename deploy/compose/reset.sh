#!/usr/bin/env bash
# S0 리셋 (Compose 구현)
#
#   ./reset.sh            # legacy 스택
#   ./reset.sh legacy new # 두 스택
#
# MySQL 데이터는 tmpfs에만 있으므로 컨테이너를 새로 만들면 데이터 디렉터리가 비고,
# 이미지가 /docker-entrypoint-initdb.d(init SQL)를 다시 실행한다. healthy는 init SQL까지
# 끝났다는 뜻이다(healthcheck가 -h 127.0.0.1 TCP ping). 이것이 S0 복원이다.
# Kafka도 같은 방식이다(tmpfs + 재생성 + healthy = 토픽 준비됨).
# k8s로 합칠 때는 이 스크립트가 `kubectl rollout restart deployment/mysql-* deployment/kafka` + readiness 대기로 바뀐다.
#
# 앱 컨테이너는 재시작하지 않는다. 끊긴 커넥션은 Hikari가 버리고 새로 맺는다.
set -euo pipefail
cd "$(dirname "$0")"

stacks=("$@")
[ ${#stacks[@]} -eq 0 ] && stacks=(legacy)

dbs=()
for st in "${stacks[@]}"; do
  dbs+=("mysql-order-$st" "mysql-coupon-$st" "mysql-payment-$st" "kafka-$st")
done

# Kafka도 tmpfs라 재생성하면 토픽·offset·consumer group이 모두 비고, init-topics.sh가 토픽을 다시 만든다.
echo "[reset] recreate: ${dbs[*]}"
docker compose up -d --force-recreate --no-deps --wait "${dbs[@]}"

# 앱은 재시작하지 않으므로 Order consumer가 새 브로커에 다시 붙어 파티션을 받을 때까지 기다린다.
# 이 대기가 없으면 리셋 직후 첫 PaymentCompleted를 consumer가 늦게 읽는다(결과는 같지만 완료 대기가 길어진다).
for st in "${stacks[@]}"; do
  echo "[reset] kafka-$st: wait for order-service consumer to be assigned"
  for i in $(seq 1 60); do
    if docker compose exec -T "kafka-$st" /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
        --describe --group order-service 2>/dev/null | grep -q '^order-service .*consumer-'; then
      break
    fi
    [ "$i" -eq 60 ] && { echo "[reset] consumer did not rejoin kafka-$st" >&2; exit 1; }
    sleep 1
  done
done

for st in "${stacks[@]}"; do
  echo "[reset] wiremock-$st: clear request journal"
  docker compose exec -T "wiremock-$st" curl -fs -X DELETE http://127.0.0.1:8080/__admin/requests >/dev/null
done

echo "[reset] done"
