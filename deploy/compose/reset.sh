#!/usr/bin/env bash
# S0 리셋 (Compose 구현)
#
#   ./reset.sh            # 두 스택(legacy, new)
#   ./reset.sh legacy     # 한 스택만
#
# 1. MySQL·Kafka 컨테이너 재생성. 데이터가 tmpfs라 새로 만들면 비고, MySQL은 init SQL, Kafka는 init-topics.sh를
#    다시 실행한다. healthy = "스키마/토픽까지 준비됨"(MySQL healthcheck는 -h 127.0.0.1 TCP ping).
# 2. 앱 컨테이너 재시작. Kafka 클라이언트가 처음부터 새 브로커에 붙게 하고(재시작 없이 다시 붙으면 rebalance가
#    한두 번 더 일어나 리셋 직후 요청과 겹칠 수 있다, legacy-decision-log L3), 앱 메모리 상태(Evidence seq 등)도 비운다.
# 3. Order consumer가 파티션을 받고 그 상태가 유지될 때까지 기다린다.
# 4. WireMock journal을 비운다.
# k8s로 합칠 때는 `kubectl rollout restart deployment/mysql-* deployment/kafka` + 앱 rollout restart + readiness 대기로 바뀐다.
set -euo pipefail
cd "$(dirname "$0")"

stacks=("$@")
[ ${#stacks[@]} -eq 0 ] && stacks=(legacy new)

data=(); apps=()
for st in "${stacks[@]}"; do
  data+=("mysql-order-$st" "mysql-coupon-$st" "mysql-payment-$st" "kafka-$st")
  apps+=("order-$st" "coupon-$st" "payment-$st")
done

echo "[reset] recreate data: ${data[*]}"
docker compose up -d --force-recreate --no-deps --wait "${data[@]}"

# restart는 같은 컨테이너를 다시 띄우므로 네트워크 주소가 유지된다(nginx upstream이 그대로 유효).
echo "[reset] restart apps: ${apps[*]}"
docker compose restart "${apps[@]}" >/dev/null
docker compose up -d --no-deps --wait "${apps[@]}"

# consumer가 파티션을 받은 뒤 같은 member로 3초 연속 유지되면 안정된 것으로 본다.
for st in "${stacks[@]}"; do
  echo "[reset] kafka-$st: wait for a stable order-service consumer"
  prev=""; stable=0
  for i in $(seq 1 90); do
    member=$(docker compose exec -T "kafka-$st" /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
      --describe --group order-service 2>/dev/null | awk '$1=="order-service" && $7 ~ /^consumer-/ {print $7}')
    if [ -n "$member" ] && [ "$member" = "$prev" ]; then stable=$((stable+1)); else stable=0; fi
    prev="$member"
    [ "$stable" -ge 3 ] && break
    [ "$i" -eq 90 ] && { echo "[reset] consumer did not stabilize on kafka-$st" >&2; exit 1; }
    sleep 1
  done
done

for st in "${stacks[@]}"; do
  echo "[reset] wiremock-$st: clear request journal"
  docker compose exec -T "wiremock-$st" curl -fs -X DELETE http://127.0.0.1:8080/__admin/requests >/dev/null
done

echo "[reset] done"
