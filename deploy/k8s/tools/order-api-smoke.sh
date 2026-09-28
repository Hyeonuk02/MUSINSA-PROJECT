#!/usr/bin/env bash
# Phase 2.1 끝난 기준 확인 - business key Order API + WireMock 결제 스텁
#
# legacy의 mesh-check pod(curl)에서 legacy / new 스택을 각각 직접 호출한다
# (Gateway·미러를 거치지 않는다. 2.1은 스택 단위 동작 확인이다).
#   kubectl apply -f deploy/k8s/tools/curl-mesh-check.yaml   # 없으면 먼저
#   deploy/k8s/tools/order-api-smoke.sh [orderKey]
#
# 같은 orderKey / Idempotency-Key를 양쪽에 쓰므로 legacy·new의 transactionId를 나란히 비교할 수 있다.
# 같은 orderKey로 다시 돌리면 생성이 409가 된다 -> S0 리셋(mysql rollout restart) 후 재실행.
set -euo pipefail

KEY="${1:-ok-smoke-1}"
IDEM="idem-${KEY#ok-}"

c() { kubectl exec -n legacy mesh-check -c curl -- curl -s -w '  -> %{http_code}\n' "$@"; }

for ns in legacy new; do
  base="http://order.${ns}.svc.cluster.local:8080/api/orders"
  wm="http://wiremock.${ns}.svc.cluster.local:8080"
  echo "===== ${ns}"
  echo "# create";              c -X POST "$base" -H 'Content-Type: application/json' \
                                  -d "{\"orderKey\":\"${KEY}\",\"items\":[{\"sku\":\"A-1\",\"qty\":2,\"price\":10000},{\"sku\":\"B-2\",\"qty\":1,\"price\":5000}]}"
  echo "# create again (409)";  c -X POST "$base" -H 'Content-Type: application/json' \
                                  -d "{\"orderKey\":\"${KEY}\",\"items\":[{\"sku\":\"A-1\",\"qty\":1,\"price\":10000}]}"
  echo "# get by key";          c "$base/by-key/${KEY}"
  echo "# get unknown (404)";   c "$base/by-key/ok-does-not-exist"
  echo "# pay";                 c -X POST "$base/${KEY}/pay" -H "Idempotency-Key: ${IDEM}"
  echo "# pay again same key";  c -X POST "$base/${KEY}/pay" -H "Idempotency-Key: ${IDEM}"
  echo "# gateway calls (count must be 1)"
  c -X POST "$wm/__admin/requests/count" -H 'Content-Type: application/json' \
    -d "{\"method\":\"POST\",\"urlPath\":\"/gateway/charge\",\"headers\":{\"Idempotency-Key\":{\"equalTo\":\"${IDEM}\"}}}"
  echo "# cancel (409)";        c -X POST "$base/${KEY}/cancel"
done
