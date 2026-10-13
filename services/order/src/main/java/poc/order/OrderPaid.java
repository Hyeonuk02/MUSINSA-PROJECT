package poc.order;

/** Phase 3.3: 결제가 처음 PAID로 바뀐 사실. 트랜잭션 커밋 뒤 order.paid로 발행된다(OrderEventPublisher). */
public record OrderPaid(String orderKey, long amount, String couponKey) {
}
