-- Coupon 서비스 스키마 (MySQL 8) — Phase 3.2
--
-- coupon-mysql 데이터는 emptyDir. `kubectl rollout restart deployment/coupon-mysql`이 S0 리셋이다.
-- 스키마 소유자는 이 파일 하나다 (앱은 ddl-auto none).
--
--   coupon_key        클라이언트(corpus)가 정하는 business key (ck-<요청 id>)
--   discount_amount   할인액. Order가 amount = max(0, 항목 합계 - discount_amount)로 반영
--   status            ISSUED | USED | SETTLED(Phase 3.3 예약)
--   used_by_order_key 쿠폰을 쓴 주문의 business key. 같은 주문의 재사용 요청은 멱등
--   created_at·used_at 고정 시각(APP_FIXED_CLOCK)
CREATE TABLE IF NOT EXISTS coupons (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    coupon_key        VARCHAR(64)  NOT NULL,
    discount_amount   BIGINT       NOT NULL,
    status            VARCHAR(20)  NOT NULL,
    used_by_order_key VARCHAR(64)  NULL,
    created_at        DATETIME(6)  NOT NULL,
    used_at           DATETIME(6)  NULL,
    CONSTRAINT uk_coupons_coupon_key UNIQUE (coupon_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
