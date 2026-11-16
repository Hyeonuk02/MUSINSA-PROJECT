package com.pm.coupon.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import com.pm.coupon.entity.CouponUsage;

@Repository
public interface CouponUsageRepository extends JpaRepository<CouponUsage, Long> {
	 long countByCouponCouponId(Long couponId);
	    
    // To check if a specific user has already used this coupon
    boolean existsByCouponCouponIdAndUserId(Long couponId, Long userId);
}
