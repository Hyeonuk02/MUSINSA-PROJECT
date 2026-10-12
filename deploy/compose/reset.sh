#!/usr/bin/env bash
# S0 리셋 (Compose 구현)
#
#   ./reset.sh            # 두 스택(legacy, new)
#   ./reset.sh legacy     # 한 스택만
#
# 1. 앱 컨테이너를 멈춘다. 멈추지 않으면 재시작 전의 옛 consumer가 새 브로커 그룹에 먼저 들어가고, 옛 앱이 죽으면서
#    그룹을 깔끔하게 떠나지 못해 새 consumer가 세션 만료(최대 45초)까지 합류하지 못한다(legacy-decision-log L3, 실측).
# 2. MySQL·Kafka 컨테이너 재생성. 데이터가 tmpfs라 새로 만들면 비고, MySQL은 init SQL, Kafka는 init-topics.sh를
#    다시 실행한다. healthy = "스키마/토픽까지 준비됨"(MySQL healthcheck는 -h 127.0.0.1 TCP ping).
# 3. 앱을 다시 시작한다. Kafka 클라이언트가 처음부터 새 브로커에 붙고, 앱 메모리 상태(Evidence seq 등)도 비워진다.
#    nginx는 이름을 요청 시점에 해석하므로 앱 IP가 바뀌어도 된다.
# 4. Order consumer group이 Stable, 멤버 1개, 파티션 할당 상태가 될 때까지 기다린다.
# 5. WireMock journal을 비운다.
# k8s로 합칠 때는 앱 scale 0 -> `kubectl rollout restart deployment/mysql-* deployment/kafka` -> 앱 scale 1 + readiness 대기로 바뀐다.
set -euo pipefail
cd "$(dirname "$0")"

stacks=("$@")
[ ${#stacks[@]} -eq 0 ] && stacks=(legacy new)

data=(); apps=()
for st in "${stacks[@]}"; do
  data+=("mysql-order-$st" "mysql-coupon-$st" "mysql-payment-$st" "kafka-$st")
  apps+=("order-$st" "coupon-$st" "payment-$st")
done

echo "[reset] stop apps: ${apps[*]}"
docker compose stop "${apps[@]}" >/dev/null

echo "[reset] recreate data: ${data[*]}"
docker compose up -d --force-recreate --no-deps --wait "${data[@]}"

echo "[reset] start apps"
docker compose start "${apps[@]}" >/dev/null
docker compose up -d --no-deps --wait "${apps[@]}"

# group 상태가 Stable이고 멤버 1개가 파티션 1개를 가진 상태가 2회 연속(1초 간격)이면 준비된 것으로 본다.
for st in "${stacks[@]}"; do
  echo "[reset] kafka-$st: wait for order-service consumer group (Stable, 1 member, assigned)"
  ok=0
  for i in $(seq 1 90); do
    state=$(docker compose exec -T "kafka-$st" /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
      --describe --group order-service --state 2>/dev/null | awk '$1=="order-service" {print $(NF-1), $NF}')
    parts=$(docker compose exec -T "kafka-$st" /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
      --describe --group order-service --members 2>/dev/null | awk '$1=="order-service" {print $NF}')
    if [ "$state" = "Stable 1" ] && [ "$parts" = "1" ]; then ok=$((ok+1)); else ok=0; fi
    [ "$ok" -ge 2 ] && break
    [ "$i" -eq 90 ] && { echo "[reset] consumer group not ready on kafka-$st (state='$state' partitions='$parts')" >&2; exit 1; }
    sleep 1
  done
done

for st in "${stacks[@]}"; do
  echo "[reset] wiremock-$st: clear request journal"
  docker compose exec -T "wiremock-$st" curl -fs -X DELETE http://127.0.0.1:8080/__admin/requests >/dev/null
done

echo "[reset] done"
