package com.pm.order.client;

import com.pm.order.dto.CouponRequest;
import com.pm.order.dto.CouponResponse;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;

@FeignClient(name = "COUPON-SERVICE")
public interface CouponClient {

    @PostMapping("/coupons/validate")
    CouponResponse validateCoupon(
        @RequestHeader("X-User-Id") Long userId, 
        @RequestBody CouponRequest request
    );

    @PostMapping("/coupons/use")
    void useCoupon(
        @RequestHeader("X-User-Id") Long userId,
        @org.springframework.web.bind.annotation.RequestParam("orderId") Long orderId,
        @org.springframework.web.bind.annotation.RequestParam("code") String code
    );
}