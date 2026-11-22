#!/usr/bin/env bash
# Prince Mart 재생 실행: tools/pm.env를 읽고 팀원 k6/run.sh를 그대로 부른다.
#
# 사용: tracks/prince-mart/tools/run-pm.sh --run-id <base> --iterations N [--vus 1]
#   VU는 1만 허용한다. Prince Mart에는 business key가 없어 후속 요청이 서버가 만든 id(capture)를 참조한다.
#   세션이 병렬로 돌면 auto increment id가 섞이고 legacy/new 사이에서도 순서가 달라질 수 있다(GENERALIZATION.md 1절).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
  if [[ "${args[$i]}" == --vus && "${args[$((i + 1))]:-}" != 1 ]]; then
    echo "Prince Mart는 --vus 1만 허용한다(business key 없음)" >&2
    exit 2
  fi
done
[[ " ${args[*]} " == *" --vus "* ]] || args+=(--vus 1)
set -a
# shellcheck source=pm.env
source tracks/prince-mart/tools/pm.env
set +a
exec k6/run.sh "${args[@]}"
