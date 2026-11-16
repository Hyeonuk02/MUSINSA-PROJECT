#!/usr/bin/env bash
# 결함 New 버전 이미지를 만든다(브랜치 없이 patch + 빌드 인자, legacy-decision-log L16).
#   baseline/faults/build.sh PF1        # PF1-<svc>.patch가 있는 서비스만 prince-mart/<svc>-service:PF1로 빌드
set -euo pipefail
cd "$(dirname "$0")"
fault=${1:?usage: build.sh PF<n>}
root=../..
built=()
for svc in order coupon payment; do
  [ -f "$fault-$svc.patch" ] || continue
  echo "[build] $fault $svc"
  docker build -q --build-context faults=. --build-arg FAULT="$fault" \
    -f "$root/legacy/prince-mart/$svc-service/DockerFile" -t "prince-mart/$svc-service:$fault" \
    "$root/legacy/prince-mart/$svc-service" >/dev/null
  built+=("$svc")
done
[ ${#built[@]} -gt 0 ] || { echo "[build] no patch files for $fault" >&2; exit 1; }
echo "[build] $fault built: ${built[*]}"
