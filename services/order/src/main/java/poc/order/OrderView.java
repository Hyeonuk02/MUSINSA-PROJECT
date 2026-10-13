package poc.order;

import java.time.Instant;
import java.util.List;

/**
 * 주문 응답 본문. 트랜잭션 안(OrderService)에서 만든다 — open-in-view가 꺼져 있어 items 지연 로딩은 트랜잭션 안에서만 된다.
 * JSON 필드는 Phase 2의 OrderController.OrderResponse에 Phase 3.2의 couponKey(없으면 null)·discountAmount(없으면 0)를 더한 것.
 */
public record OrderView(Long id, String orderKey, List<Item> items, long amount, String couponKey,
                        long discountAmount, String status, String transactionId, Instant createdAt) {

    public record Item(String sku, int qty, long price) {
    }

    static OrderView from(Order order) {
        List<Item> items = order.getItems().stream()
                .map(i -> new Item(i.getSku(), i.getQty(), i.getPrice()))
                .toList();
        return new OrderView(order.getId(), order.getOrderKey(), items, order.getAmount(), order.getCouponKey(),
                order.getDiscountAmount(), order.getStatus(), order.getTransactionId(), order.getCreatedAt());
    }
}
