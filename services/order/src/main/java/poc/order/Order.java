package poc.order;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.OrderBy;
import jakarta.persistence.Table;

import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/**
 * Phase 2.1: business key(orderKey) 기반 주문.
 *
 * <p>DB auto {@code id}는 legacy/new에서 같다는 보장이 없으므로 후속 요청은 전부
 * {@code orderKey}로 대상을 지정한다. id는 기존 {@code GET /api/orders/{id}} 호환용으로만 남는다.
 */
@Entity
@Table(name = "orders")
public class Order {

    public static final String CREATED = "CREATED";
    public static final String PAID = "PAID";
    public static final String CANCELLED = "CANCELLED";

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_key", nullable = false, unique = true)
    private String orderKey;

    @Column(nullable = false)
    private long amount;

    @Column(nullable = false)
    private String status;

    @Column(name = "transaction_id")
    private String transactionId;

    @Column(name = "idempotency_key")
    private String idempotencyKey;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    /** Phase 3.2: 주문에 사용한 쿠폰. 없으면 null. */
    @Column(name = "coupon_key")
    private String couponKey;

    /** Phase 3.2: 쿠폰 할인액. 쿠폰이 없으면 0. amount = max(0, 항목 합계 − discountAmount). */
    @Column(name = "discount_amount", nullable = false)
    private long discountAmount;

    @OneToMany(mappedBy = "order", cascade = CascadeType.ALL, orphanRemoval = true)
    @OrderBy("lineNo ASC")
    private List<OrderItem> items = new ArrayList<>();

    protected Order() {
    }

    public Order(String orderKey, Clock clock) {
        this.orderKey = orderKey;
        this.status = CREATED;
        // 시스템 시각이 아니라 주입된 Clock을 쓴다 (ClockConfig / APP_FIXED_CLOCK).
        this.createdAt = Instant.now(clock);
    }

    public void addItem(String sku, int qty, long price) {
        items.add(new OrderItem(this, items.size() + 1, sku, qty, price));
        amount += price * qty;
    }

    /** 쿠폰 할인 반영. 항목을 다 넣은 뒤 한 번만 호출한다. */
    public void applyCoupon(String couponKey, long discountAmount) {
        this.couponKey = couponKey;
        this.discountAmount = discountAmount;
        this.amount = Math.max(0, amount - discountAmount);
    }

    public void markPaid(String transactionId, String idempotencyKey) {
        this.status = PAID;
        this.transactionId = transactionId;
        this.idempotencyKey = idempotencyKey;
    }

    public void cancel() {
        this.status = CANCELLED;
    }

    public Long getId() { return id; }
    public String getOrderKey() { return orderKey; }
    public long getAmount() { return amount; }
    public String getStatus() { return status; }
    public String getTransactionId() { return transactionId; }
    public String getIdempotencyKey() { return idempotencyKey; }
    public Instant getCreatedAt() { return createdAt; }
    public String getCouponKey() { return couponKey; }
    public long getDiscountAmount() { return discountAmount; }
    public List<OrderItem> getItems() { return items; }
}
