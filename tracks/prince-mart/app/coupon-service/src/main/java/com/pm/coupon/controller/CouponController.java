package com.pm.coupon.controller;

import com.pm.coupon.dto.CouponRequest;
import com.pm.coupon.dto.CouponResponse;
import com.pm.coupon.entity.Coupon;
import com.pm.coupon.entity.CouponUsage;
import com.pm.coupon.service.CouponService;

import java.util.List;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/coupons")
public class CouponController {

    private final CouponService couponService;

    public CouponController(CouponService couponService) {
        this.couponService = couponService;
    }

    @GetMapping("/welcome")
    public ResponseEntity<String> welcome() {
		return ResponseEntity.ok("Welcome!! This is the Coupon Service for Prince Mart by Prince Inc.");
	}
    
    // ADMIN: Create new coupons
    @PostMapping("/create")
    public ResponseEntity<Coupon> createCoupon(@RequestBody Coupon coupon) {
        return ResponseEntity.ok(couponService.createCoupon(coupon));
    }

    @PostMapping("/validate")
    public ResponseEntity<CouponResponse> validate(
            @RequestHeader("X-User-Id") Long userId, 
            @RequestBody CouponRequest request) {
        return ResponseEntity.ok(couponService.validateCoupon(userId, request));
    }

    @PostMapping("/use")
    public ResponseEntity<Void> useCoupon(
            @RequestHeader("X-User-Id") Long userId,
            @RequestParam Long orderId,
            @RequestParam String code) {
        couponService.recordUsage(userId, orderId, code);
        return ResponseEntity.ok().build();
    }
    
    @GetMapping("/all")
    public ResponseEntity<List<Coupon>> getAllCoupons() {
		return ResponseEntity.ok(couponService.getAllCoupons());
	}
    
    @GetMapping("/usage/all")
    public ResponseEntity<List<CouponUsage>> getAllCouponUsages() {
    			return ResponseEntity.ok(couponService.getAllCouponUsages());
    }
}