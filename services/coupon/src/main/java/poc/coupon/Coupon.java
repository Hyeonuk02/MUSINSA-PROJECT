package poc.coupon;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.Clock;
import java.time.Instant;

/**
 * 쿠폰. 상태 ISSUED → USED(주문에 사용) → SETTLED(결제 확정, Phase 3.3 예약).
 * 사용은 orderKey 기준 멱등: 같은 주문의 재사용 요청은 상태를 바꾸지 않는다.
 */
@Entity
@Table(name = "coupons")
public class Coupon {

    public static final String ISSUED = "ISSUED";
    public static final String USED = "USED";
    public static final String SETTLED = "SETTLED";

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "coupon_key", nullable = false, unique = true)
    private String couponKey;

    @Column(name = "discount_amount", nullable = false)
    private long discountAmount;

    @Column(nullable = false)
    private String status;

    @Column(name = "used_by_order_key")
    private String usedByOrderKey;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "used_at")
    private Instant usedAt;

    protected Coupon() {
    }

    public Coupon(String couponKey, long discountAmount, Clock clock) {
        this.couponKey = couponKey;
        this.discountAmount = discountAmount;
        this.status = ISSUED;
        this.createdAt = Instant.now(clock);
    }

    public void use(String orderKey, Clock clock) {
        this.status = USED;
        this.usedByOrderKey = orderKey;
        this.usedAt = Instant.now(clock);
    }

    public String getCouponKey() { return couponKey; }
    public long getDiscountAmount() { return discountAmount; }
    public String getStatus() { return status; }
    public String getUsedByOrderKey() { return usedByOrderKey; }
}
