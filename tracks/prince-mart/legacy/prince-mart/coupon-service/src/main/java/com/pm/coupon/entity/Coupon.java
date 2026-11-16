package com.pm.coupon.entity;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;

@Entity
@Table(name = "coupons")
public class Coupon {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "coupon_id")
    private Long couponId;

    @Column(unique = true, nullable = false)
    private String code;

    @Column(nullable = false, name = "discount_type")
    private String discountType; // percentage or fixed

    @Column(nullable = false, name = "discount_value")
    private BigDecimal discountValue;

    @Column(name = "max_discount")
    private BigDecimal maxDiscount;

    @Column(name = "min_order_value")
    private BigDecimal minOrderValue;

    @Column(name = "expiry_date")
    private LocalDateTime expiryDate;

    @Column(name = "usage_limit")
    private Integer usageLimit;

    public Coupon() {}

    public Long getCouponId() { return couponId; }
    public void setCouponId(Long couponId) { this.couponId = couponId; }

    public String getCode() { return code; }
    public void setCode(String code) { this.code = code; }

    public String getDiscountType() { return discountType; }
    public void setDiscountType(String discountType) { this.discountType = discountType; }

    public BigDecimal getDiscountValue() { return discountValue; }
    public void setDiscountValue(BigDecimal discountValue) { this.discountValue = discountValue; }

    public BigDecimal getMaxDiscount() { return maxDiscount; }
    public void setMaxDiscount(BigDecimal maxDiscount) { this.maxDiscount = maxDiscount; }

    public BigDecimal getMinOrderValue() { return minOrderValue; }
    public void setMinOrderValue(BigDecimal minOrderValue) { this.minOrderValue = minOrderValue; }

    public LocalDateTime getExpiryDate() { return expiryDate; }
    public void setExpiryDate(LocalDateTime expiryDate) { this.expiryDate = expiryDate; }

    public Integer getUsageLimit() { return usageLimit; }
    public void setUsageLimit(Integer usageLimit) { this.usageLimit = usageLimit; }

	public Coupon(Long couponId, String code, String discountType, BigDecimal discountValue, BigDecimal maxDiscount,
			BigDecimal minOrderValue, LocalDateTime expiryDate, Integer usageLimit) {
		super();
		this.couponId = couponId;
		this.code = code;
		this.discountType = discountType;
		this.discountValue = discountValue;
		this.maxDiscount = maxDiscount;
		this.minOrderValue = minOrderValue;
		this.expiryDate = expiryDate;
		this.usageLimit = usageLimit;
	}
}