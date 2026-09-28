-- coupon-service S0 시드 데이터 (01-schema.sql 다음에 실행)
--
-- 기준 시각은 APP_FIXED_CLOCK = 2026-09-01T00:00:00Z. 만료 판정은 이 시각 기준이다.
--   만료: 2026-08-01 / 유효: 2026-12-31
-- 장바구니 합계는 100,000원(WireMock cart-my-cart.json). 금액 기대값은 그 기준이다.
-- /coupons/create API로 넣지 않는 이유: 감사 로그 외부 호출이 섞여 S0 정의가 흐려진다.
--
-- min_order_value는 NULL로 두면 validateCoupon이 NPE를 낸다(upstream 코드). 쓰지 않는 경우에도 0을 넣는다.

INSERT INTO coupons (code, discount_type, discount_value, max_discount, min_order_value, expiry_date, usage_limit) VALUES
-- 정상: 고정 5,000원 할인, 최소 50,000원 -> 95,000원
('FIX5000',  'fixed',      5000.00, NULL,    50000.00,  '2026-12-31 23:59:59', NULL),
-- 정상: 10% 할인, 최대 8,000원 -> 92,000원
('PCT10',    'percentage',   10.00, 8000.00,     0.00,  '2026-12-31 23:59:59', NULL),
-- B3: 만료 쿠폰 -> 검증 실패를 삼키고 정가 100,000원, 200
('EXPIRED',  'fixed',      5000.00, NULL,        0.00,  '2026-08-01 00:00:00', NULL),
-- B3: 최소 주문 금액 미달(200,000원 필요) -> 정가 100,000원, 200
('MIN200K',  'fixed',      5000.00, NULL,   200000.00,  '2026-12-31 23:59:59', NULL),
-- 결제 실패 fixture: 1원 할인 -> 99,999원 -> 가짜 PG가 거절(pg-orders-create-decline.json)
('PGFAIL1',  'fixed',         1.00, NULL,        0.00,  '2026-12-31 23:59:59', NULL),
-- B1: 사용 한도 1회. coupon_usage가 기록되지 않으므로 한도를 넘어 재사용된다
('LIMIT1',   'fixed',      3000.00, NULL,        0.00,  '2026-12-31 23:59:59', 1);
