#!/bin/bash
# Kafka S0: 브로커를 띄우고 토픽을 만든다(토픽 정의는 이 파일 하나가 소유한다 -- MySQL init SQL과 같은 역할).
# 컨테이너 데이터가 tmpfs라 재생성할 때마다 빈 브로커에서 다시 실행된다.
set -e
/etc/kafka/docker/run &
BROKER=$!

until /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list >/dev/null 2>&1; do sleep 1; done

# payment-events: PaymentCompleted (key=orderId). 파티션 1개 -> 스택 안에서 이벤트 순서가 발행 순서와 같다.
/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --if-not-exists \
  --topic payment-events --partitions 1 --replication-factor 1

wait $BROKER
