-- Order 서비스 스키마 (MySQL 8)
--
-- MySQL 이미지가 초기화 시 /docker-entrypoint-initdb.d 안의 파일을 실행한다.
-- 데이터 디렉터리가 emptyDir이므로 pod가 새로 뜰 때마다 이 파일이 다시 실행되고,
-- 그것이 곧 S0(시드 상태) 리셋이다 -- `kubectl rollout restart deployment/mysql`.
-- 스키마 소유자는 이 파일 하나다 (앱은 ddl-auto none).
--
-- Phase 0(Postgres)에서 바뀐 점
--   GENERATED ALWAYS AS IDENTITY -> AUTO_INCREMENT
--   TIMESTAMPTZ                  -> DATETIME(6)
--     MySQL에는 timezone-aware 타입이 없다. 세션 타임존을 UTC로 고정하고
--     (JDBC serverTimezone=UTC + JVM -Duser.timezone=UTC) UTC 값을 그대로 저장한다.
--     TIMESTAMP는 2038년 상한이 있어 DATETIME을 쓴다.
--
-- Phase 2.1: business key 기반으로 변경
--   order_key       클라이언트(corpus)가 정하는 business key. 후속 요청은 이 값으로 대상을 지정한다
--                   (auto id는 legacy/new에서 같다는 보장이 없다)
--   amount          sum(order_items.qty * price)
--   transaction_id  결제 게이트웨이가 준 값 (PAID일 때)
--   idempotency_key 결제에 쓰인 Idempotency-Key. 같은 키 재요청은 게이트웨이 재호출 없이 이전 결과
CREATE TABLE IF NOT EXISTS orders (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_key       VARCHAR(64)  NOT NULL,
    amount          BIGINT       NOT NULL,
    status          VARCHAR(20)  NOT NULL,
    transaction_id  VARCHAR(128) NULL,
    idempotency_key VARCHAR(128) NULL,
    created_at      DATETIME(6)  NOT NULL,
    CONSTRAINT uk_orders_order_key UNIQUE (order_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS order_items (
    id       BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_id BIGINT      NOT NULL,
    line_no  INT         NOT NULL,
    sku      VARCHAR(64) NOT NULL,
    qty      INT         NOT NULL,
    price    BIGINT      NOT NULL,
    CONSTRAINT fk_order_items_order FOREIGN KEY (order_id) REFERENCES orders (id),
    CONSTRAINT uk_order_items_line UNIQUE (order_id, line_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
