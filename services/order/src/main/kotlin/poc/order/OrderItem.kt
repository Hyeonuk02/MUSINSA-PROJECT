package poc.order

import jakarta.persistence.Column
import jakarta.persistence.Entity
import jakarta.persistence.FetchType
import jakarta.persistence.GeneratedValue
import jakarta.persistence.GenerationType
import jakarta.persistence.Id
import jakarta.persistence.JoinColumn
import jakarta.persistence.ManyToOne
import jakarta.persistence.Table

/**
 * 주문 라인. 응답의 items 순서는 요청 순서(`lineNo`)로 고정한다.
 *
 * Phase 3.5-v1.2: Java → Kotlin 전환. id·order는 Java처럼 getter 없이(private) 둔다.
 */
@Entity
@Table(name = "order_items")
class OrderItem protected constructor() {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private var id: Long? = null

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private var order: Order? = null

    @Column(name = "line_no", nullable = false)
    var lineNo: Int = 0
        protected set

    @Column(nullable = false)
    lateinit var sku: String
        protected set

    @Column(nullable = false)
    var qty: Int = 0
        protected set

    @Column(nullable = false)
    var price: Long = 0
        protected set

    internal constructor(order: Order, lineNo: Int, sku: String, qty: Int, price: Long) : this() {
        this.order = order
        this.lineNo = lineNo
        this.sku = sku
        this.qty = qty
        this.price = price
    }
}
