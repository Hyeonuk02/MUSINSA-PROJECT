package poc.coupon;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;

/** 쿠폰 비즈니스 로직과 트랜잭션 경계. 컨트롤러는 매핑·입력 검증만. */
@Service
public class CouponService {

    private final CouponRepository couponRepository;
    private final Clock clock;

    public CouponService(CouponRepository couponRepository, Clock clock) {
        this.couponRepository = couponRepository;
        this.clock = clock;
    }

    public enum Kind { CREATED, OK, KEY_EXISTS, NOT_FOUND, ALREADY_USED }

    public record Outcome(Kind kind, CouponView coupon) {
        static Outcome of(Kind kind) {
            return new Outcome(kind, null);
        }
    }

    @Transactional
    public Outcome issue(String couponKey, long discountAmount) {
        if (couponRepository.existsByCouponKey(couponKey)) {
            return Outcome.of(Kind.KEY_EXISTS);
        }
        return new Outcome(Kind.CREATED, CouponView.from(couponRepository.save(new Coupon(couponKey, discountAmount, clock))));
    }

    @Transactional(readOnly = true)
    public Outcome getByKey(String couponKey) {
        return couponRepository.findByCouponKey(couponKey)
                .map(c -> new Outcome(Kind.OK, CouponView.from(c)))
                .orElseGet(() -> Outcome.of(Kind.NOT_FOUND));
    }

    /**
     * 쿠폰 사용. orderKey 기준 멱등 — 같은 (couponKey, orderKey) 재호출은 상태를 바꾸지 않고 현재 상태를 돌려준다(UPDATE 없음).
     * 다른 주문이 이미 쓴 쿠폰이면 충돌. 이렇게 해야 "use 두 번 호출"(F9)이 응답 변화 없이 hop 집합으로만 드러난다.
     */
    @Transactional
    public Outcome use(String couponKey, String orderKey) {
        Coupon coupon = couponRepository.findByCouponKey(couponKey).orElse(null);
        if (coupon == null) {
            return Outcome.of(Kind.NOT_FOUND);
        }
        if (Coupon.ISSUED.equals(coupon.getStatus())) {
            coupon.use(orderKey, clock);
            return new Outcome(Kind.OK, CouponView.from(coupon));
        }
        if (orderKey.equals(coupon.getUsedByOrderKey())) {
            return new Outcome(Kind.OK, CouponView.from(coupon));
        }
        return Outcome.of(Kind.ALREADY_USED);
    }

    /**
     * Phase 3.3: 결제된 주문의 쿠폰 확정(order.paid 소비). USED이고 그 주문이 쓴 쿠폰이면 SETTLED(flush에서 UPDATE).
     * 이미 SETTLED이거나 다른 상태·다른 주문이면 바꾸지 않는다(멱등, 소비 Evidence의 dbAccess에는 SELECT만).
     */
    @Transactional
    public void settle(String couponKey, String orderKey) {
        couponRepository.findByCouponKey(couponKey)
                .filter(c -> Coupon.USED.equals(c.getStatus()) && orderKey.equals(c.getUsedByOrderKey()))
                .ifPresent(Coupon::settle);
    }
}
