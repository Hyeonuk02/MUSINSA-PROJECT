CREATE TABLE IF NOT EXISTS orders (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id   VARCHAR(64) NOT NULL,
    quantity     INT         NOT NULL,
    unit_price   BIGINT      NOT NULL,
    total_amount BIGINT      NOT NULL,
    status       VARCHAR(20) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL
);
