#!/usr/bin/env bash
# 스키마 초기 생성(1회). Hibernate ddl-auto=update로 만든 스키마를 mysqldump --no-data로 떠서
# deploy/compose/mysql-initdb/<service>/01-schema.sql에 고정한다. 결과는 사람이 검토 후 커밋한다.
# 엔티티가 바뀌지 않는 한 다시 실행할 일이 없다. (hyeonuk-dev D4: 스키마 소유자는 init SQL 하나)
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p tools/empty-initdb
DC=(docker compose -f docker-compose.yml -f tools/schema-gen.override.yml)

"${DC[@]}" up -d --build --wait --force-recreate \
  mysql-order-legacy mysql-coupon-legacy mysql-payment-legacy order-legacy coupon-legacy payment-legacy

for svc in order coupon payment; do
  out="mysql-initdb/$svc/01-schema.sql"
  {
    echo "-- $svc-service 스키마 (MySQL 8.4) -- S0의 스키마 부분"
    echo "--"
    echo "-- 생성: deploy/compose/tools/dump-schema.sh (Hibernate ddl-auto=update 1회 -> mysqldump --no-data)"
    echo "-- MySQL 이미지가 초기화 시 /docker-entrypoint-initdb.d를 MYSQL_DATABASE(${svc}_db)에 실행한다."
    echo "-- 앱은 ddl-auto: none이므로 스키마는 이 파일 하나가 소유한다."
    echo "-- mysqldump는 테이블을 이름순으로 내보내므로 FK 참조 순서와 다르다. 생성 중에만 FK 검사를 끈다."
    echo "SET FOREIGN_KEY_CHECKS=0;"
    echo
    "${DC[@]}" exec -T "mysql-$svc-legacy" sh -c \
      'mysqldump -u root -p"$MYSQL_ROOT_PASSWORD" --no-data --skip-comments --skip-add-drop-table --skip-set-charset --compact "$MYSQL_DATABASE" 2>/dev/null' \
      | sed -E 's/ AUTO_INCREMENT=[0-9]+//; s#^/\*!4010[0-9] SET [^*]*\*/;$##; s#^/\*!50503 SET [^*]*\*/;$##' | sed '/^$/d'
    echo
    echo "SET FOREIGN_KEY_CHECKS=1;"
  } > "$out"
  echo "wrote $out"
done

"${DC[@]}" down
