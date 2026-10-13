package poc.order

import java.time.Instant

/**
 * 주문 응답 본문. 트랜잭션 안(OrderService)에서 만든다 — open-in-view가 꺼져 있어 items 지연 로딩은 트랜잭션 안에서만 된다.
 * JSON 필드는 Phase 2의 OrderController.OrderResponse에 Phase 3.2의 couponKey(없으면 null)·discountAmount(없으면 0)를 더한 것.
 *
 * Phase 3.5-v1.4: Java record → Kotlin data class(응답 JSON은 앱 JsonMapper + jackson-module-kotlin).
 */
data class OrderView(
    val id: Long?,
    val orderKey: String,
    val items: List<Item>,
    val amount: Long,
    val couponKey: String?,
    val discountAmount: Long,
    val status: String,
    val transactionId: String?,
    val createdAt: Instant,
    val itemCount: Int,
) {

    data class Item(val sku: String, val qty: Int, val price: Long)

    companion object {
        fun from(order: Order): OrderView = OrderView(
            order.id, order.orderKey, order.items.map { Item(it.sku, it.qty, it.price) }, order.amount,
            order.couponKey, order.discountAmount, order.status, order.transactionId, order.createdAt, order.items.size,
        )
    }
}
