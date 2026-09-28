package com.pm.coupon.service;

import com.fasterxml.jackson.databind.ObjectMapper; // For JSON conversion
import com.pm.coupon.client.AuditClient; // New client
import com.pm.coupon.client.OrderClient;
import com.pm.coupon.dto.AuditLogRequest; // New DTO
import com.pm.coupon.dto.CouponRequest;
import com.pm.coupon.dto.CouponResponse;
import com.pm.coupon.dto.OrderResponse;
import com.pm.coupon.entity.Coupon;
import com.pm.coupon.entity.CouponUsage;
import com.pm.coupon.exception.ResourceNotFoundException;
import com.pm.coupon.repository.CouponRepository;
import com.pm.coupon.repository.CouponUsageRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

@Service
public class CouponService {

    private final CouponRepository couponRepository;
    private final CouponUsageRepository usageRepository;
    private final OrderClient orderClient;
    private final AuditClient auditClient;
    private final ObjectMapper objectMapper;

    public CouponService(CouponRepository couponRepository, 
                         CouponUsageRepository usageRepository, 
                         OrderClient orderClient,
                         AuditClient auditClient,
                         ObjectMapper objectMapper) {
        this.couponRepository = couponRepository;
        this.usageRepository = usageRepository;
        this.orderClient = orderClient;
        this.auditClient = auditClient;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public Coupon createCoupon(Coupon coupon) {
        Coupon savedCoupon = couponRepository.save(coupon);
        
        // Audit log for creating a new coupon
        sendAuditLog(null, "CREATE_COUPON", null, savedCoupon);
        
        return savedCoupon;
    }

    public CouponResponse validateCoupon(Long userId, CouponRequest request) {
        Coupon coupon = couponRepository.findByCode(request.getCode())
                .orElse(null);

        if (coupon == null) {
            return new CouponResponse(request.getCode(), false, BigDecimal.ZERO, "Invalid coupon code.");
        }

        boolean alreadyUsed = usageRepository.existsByCouponCouponIdAndUserId(coupon.getCouponId(), userId);
        if (alreadyUsed) {
            return new CouponResponse(request.getCode(), false, BigDecimal.ZERO, "You have already used this coupon.");
        }

        if (coupon.getExpiryDate() != null && coupon.getExpiryDate().isBefore(LocalDateTime.now())) {
            return new CouponResponse(request.getCode(), false, BigDecimal.ZERO, "Coupon has expired.");
        }

        if (request.getOrderAmount().compareTo(coupon.getMinOrderValue()) < 0) {
            return new CouponResponse(request.getCode(), false, BigDecimal.ZERO, 
                "Minimum order value of " + coupon.getMinOrderValue() + " required.");
        }

        long totalUsed = usageRepository.countByCouponCouponId(coupon.getCouponId());
        if (coupon.getUsageLimit() != null && totalUsed >= coupon.getUsageLimit()) {
            return new CouponResponse(request.getCode(), false, BigDecimal.ZERO, "Coupon limit reached.");
        }

        BigDecimal discount = calculateDiscount(coupon, request.getOrderAmount());
        return new CouponResponse(request.getCode(), true, discount, "Coupon applied successfully!");
    }

    @Transactional
    public void recordUsage(Long userId, Long orderId, String code) {
        // 1. Find Coupon first
        Coupon coupon = couponRepository.findByCode(code)
                .orElseThrow(() -> new ResourceNotFoundException("Coupon not found: " + code));

        // 2. Check if already used by this user
        if (usageRepository.existsByCouponCouponIdAndUserId(coupon.getCouponId(), userId)) {
            throw new ResourceNotFoundException("User has already used this coupon.");
        }

        // 3. Dynamic Check: Verify Order via Feign
        try {
            OrderResponse order = orderClient.getOrderById(orderId, userId);
            
            if (order == null || !order.getUserId().equals(userId)) {
                throw new ResourceNotFoundException("Order verification failed: This order does not belong to you.");
            }
            
            if ("CANCELLED".equalsIgnoreCase(order.getStatus())) {
                throw new ResourceNotFoundException("Cannot apply coupon to a cancelled order.");
            }

        } catch (Exception e) {
            System.err.println("FEIGN ERROR: " + e.getMessage());
            throw new ResourceNotFoundException("Order Service returned an error or Order ID " + orderId + " was not found.");
        }

        // 4. Record Usage
        CouponUsage usage = new CouponUsage();
        usage.setCoupon(coupon);
        usage.setUserId(userId);
        usage.setOrderId(orderId);
        
        CouponUsage savedUsage = usageRepository.save(usage);
        
        // Audit the consumption of the coupon
        sendAuditLog(userId, "COUPON_CONSUMED", "Code: " + code + " | Order: " + orderId, savedUsage);
    }

    private BigDecimal calculateDiscount(Coupon coupon, BigDecimal orderAmount) {
        BigDecimal discount = BigDecimal.ZERO;
        if ("fixed".equalsIgnoreCase(coupon.getDiscountType())) {
            discount = coupon.getDiscountValue();
        } else if ("percentage".equalsIgnoreCase(coupon.getDiscountType())) {
            discount = orderAmount.multiply(coupon.getDiscountValue()).divide(new BigDecimal("100"));
            if (coupon.getMaxDiscount() != null && discount.compareTo(coupon.getMaxDiscount()) > 0) {
                discount = coupon.getMaxDiscount();
            }
        }
        return discount;
    }

    // Helper for centralized auditing
    private void sendAuditLog(Long userId, String action, Object dataBefore, Object dataAfter) {
        try {
            String before = dataBefore != null ? (dataBefore instanceof String ? (String) dataBefore : objectMapper.writeValueAsString(dataBefore)) : null;
            String after = dataAfter != null ? objectMapper.writeValueAsString(dataAfter) : null;

            auditClient.createLog(new AuditLogRequest(
                "COUPON-SERVICE", 
                action, 
                userId, 
                before, 
                after
            ));
        } catch (Exception e) {
            System.err.println("Audit logging failed in Coupon Service: " + e.getMessage());
        }
    }
    
    public List<Coupon> getAllCoupons() {
		return couponRepository.findAll();
	}
    
    public List<CouponUsage> getAllCouponUsages() {
    	return usageRepository.findAll();
    }
}