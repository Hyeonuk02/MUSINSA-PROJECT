-- Order 서비스 스키마 (MySQL 8)
--
-- MySQL 이미지가 초기화 시 /docker-entrypoint-initdb.d 안의 파일을 실행한다.
-- 데이터 디렉터리가 emptyDir이므로 pod가 새로 뜰 때마다 이 파일이 다시 실행되고,
-- 그것이 곧 S0(시드 상태) 리셋이다 -- `kubectl rollout restart deployment/mysql`.
--
-- Phase 0(Postgres)에서 바뀐 점
--   GENERATED ALWAYS AS IDENTITY -> AUTO_INCREMENT
--   TIMESTAMPTZ                  -> DATETIME(6)
--     MySQL에는 timezone-aware 타입이 없다. 세션 타임존을 UTC로 고정하고
--     (JDBC serverTimezone=UTC + JVM -Duser.timezone=UTC) UTC 값을 그대로 저장한다.
--     TIMESTAMP는 2038년 상한이 있어 DATETIME을 쓴다.
CREATE TABLE IF NOT EXISTS orders (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    product_id   VARCHAR(64) NOT NULL,
    quantity     INT         NOT NULL,
    unit_price   BIGINT      NOT NULL,
    total_amount BIGINT      NOT NULL,
    status       VARCHAR(20) NOT NULL,
    created_at   DATETIME(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
