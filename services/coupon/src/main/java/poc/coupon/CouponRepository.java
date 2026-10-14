package poc.coupon;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface CouponRepository extends JpaRepository<Coupon, Long> {

    Optional<Coupon> findByCouponKey(String couponKey);

    boolean existsByCouponKey(String couponKey);
}
