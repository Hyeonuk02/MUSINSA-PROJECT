#!/usr/bin/env bash
# [LEGACY_CHANGES L-I2] Evidence 계측 코드를 서비스에 같은 바이트로 복사한다. 원본은 이 디렉터리 하나다.
#   ./sync.sh          # 복사
#   ./sync.sh --check  # 서비스 쪽 복사본이 원본과 같은지 확인(다르면 exit 1)
#
# core  (com.pm.evidence)       -> order, coupon, payment
# kafka (com.pm.evidence.kafka) -> order, payment   (coupon은 Kafka를 쓰지 않는다)
# 서비스마다 Docker 빌드 컨텍스트가 따로라 공유 모듈 대신 복사본을 둔다.
set -euo pipefail
cd "$(dirname "$0")"

mode=${1:-copy}
rc=0

sync_set() {  # src_dir dst_subdir service...
  local src=$1 sub=$2; shift 2
  for svc in "$@"; do
    local dst="../$svc/src/main/java/com/pm/$sub"
    if [ "$mode" = "--check" ]; then
      for f in "$src"/*.java; do
        cmp -s "$f" "$dst/$(basename "$f")" || { echo "DIFF: $dst/$(basename "$f")"; rc=1; }
      done
      for f in "$dst"/*.java; do
        [ -e "$src/$(basename "$f")" ] || { echo "EXTRA: $f"; rc=1; }
      done
    else
      mkdir -p "$dst"
      find "$dst" -maxdepth 1 -name '*.java' -delete
      cp "$src"/*.java "$dst"/
    fi
  done
}

sync_set core/com/pm/evidence        evidence       order-service coupon-service payment-service
sync_set kafka/com/pm/evidence/kafka evidence/kafka order-service payment-service

if [ "$mode" = "--check" ]; then
  [ $rc -eq 0 ] && echo "evidence copies: identical"
  exit $rc
fi
echo "evidence copied: core -> order, coupon, payment / kafka -> order, payment"
