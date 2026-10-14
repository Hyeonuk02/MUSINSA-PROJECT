package poc.coupon;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;

/**
 * Phase 3.3: {@code order.paid} 소비 — 결제된 주문의 쿠폰을 확정한다(USED → SETTLED).
 *
 * <p>레코드 단위, group {@code coupon-settlement}. 페이로드 {@code {orderKey, amount, couponKey}}.
 * 쿠폰이 없는 주문은 할 일이 없다(no-op — 소비 Evidence는 남고 dbAccess는 빈 배열).
 * 실패(예: 페이로드 해석 불가)는 던진다 — 에러 핸들러가 재시도 없이 {@code order.paid.dlq}로 보낸다(KafkaConfig).
 */
@Component
public class OrderPaidListener {

    private final CouponService couponService;
    private final JsonMapper jsonMapper;

    public OrderPaidListener(CouponService couponService, JsonMapper jsonMapper) {
        this.couponService = couponService;
        this.jsonMapper = jsonMapper;
    }

    @KafkaListener(topics = "order.paid", groupId = "coupon-settlement")
    public void onOrderPaid(String payload) {
        OrderPaid event = jsonMapper.readValue(payload, OrderPaid.class);
        if (event.orderKey() == null) {
            throw new IllegalArgumentException("order.paid without orderKey");
        }
        if (event.couponKey() != null) {
            couponService.settle(event.couponKey(), event.orderKey());
        }
    }

    record OrderPaid(String orderKey, Long amount, String couponKey) {
    }
}
