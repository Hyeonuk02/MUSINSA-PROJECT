package poc.order

import jakarta.persistence.CascadeType
import jakarta.persistence.Column
import jakarta.persistence.Entity
import jakarta.persistence.GeneratedValue
import jakarta.persistence.GenerationType
import jakarta.persistence.Id
import jakarta.persistence.OneToMany
import jakarta.persistence.OrderBy
import jakarta.persistence.Table
import java.time.Clock
import java.time.Instant

/**
 * Phase 2.1: business key(orderKey) 기반 주문.
 *
 * DB auto `id`는 legacy/new에서 같다는 보장이 없으므로 후속 요청은 전부
 * `orderKey`로 대상을 지정한다. id는 기존 `GET /api/orders/{id}` 호환용으로만 남는다.
 *
 * Phase 3.5-v1.2: Java → Kotlin 전환. data class 금지(D17), 필드 접근(애노테이션은 필드로), all-open(Entity)·no-arg(jpa).
 * nullable 컬럼만 `?` 타입. setter는 protected — 상태 변경은 아래 메서드로만(Java와 같음).
 */
@Entity
@Table(name = "orders")
class Order protected constructor() {

    companion object {
        const val CREATED = "CREATED"
        const val PAID = "PAID"
        const val CANCELLED = "CANCELLED"
    }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    var id: Long? = null
        protected set

    @Column(name = "order_key", nullable = false, unique = true)
    lateinit var orderKey: String
        protected set

    @Column(nullable = false)
    var amount: Long = 0
        protected set

    @Column(nullable = false)
    lateinit var status: String
        protected set

    @Column(name = "transaction_id")
    var transactionId: String? = null
        protected set

    @Column(name = "idempotency_key")
    var idempotencyKey: String? = null
        protected set

    @Column(name = "created_at", nullable = false)
    lateinit var createdAt: Instant
        protected set

    /** Phase 3.2: 주문에 사용한 쿠폰. 없으면 null. */
    @Column(name = "coupon_key")
    var couponKey: String? = null
        protected set

    /** Phase 3.2: 쿠폰 할인액. 쿠폰이 없으면 0. amount = max(0, 항목 합계 − discountAmount). */
    @Column(name = "discount_amount", nullable = false)
    var discountAmount: Long = 0
        protected set

    @OneToMany(mappedBy = "order", cascade = [CascadeType.ALL], orphanRemoval = true)
    @OrderBy("lineNo ASC")
    var items: MutableList<OrderItem> = ArrayList()
        protected set

    constructor(orderKey: String, clock: Clock) : this() {
        this.orderKey = orderKey
        this.status = CREATED
        // 시스템 시각이 아니라 주입된 Clock을 쓴다 (ClockConfig / APP_FIXED_CLOCK).
        this.createdAt = Instant.now(clock)
    }

    fun addItem(sku: String, qty: Int, price: Long) {
        items.add(OrderItem(this, items.size + 1, sku, qty, price))
        amount += price * qty
    }

    /** 쿠폰 할인 반영. 항목을 다 넣은 뒤 한 번만 호출한다. */
    fun applyCoupon(couponKey: String, discountAmount: Long) {
        this.couponKey = couponKey
        this.discountAmount = discountAmount
        this.amount = maxOf(0, amount - discountAmount)
    }

    fun markPaid(transactionId: String, idempotencyKey: String) {
        this.status = PAID
        this.transactionId = transactionId
        this.idempotencyKey = idempotencyKey
    }

    fun cancel() {
        this.status = CANCELLED
    }
}
