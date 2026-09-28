package com.pm.coupon.dto;

import java.math.BigDecimal;

public class CouponResponse {
    private String code;
    private boolean valid;
    private BigDecimal discountAmount;
    private String message;

    public CouponResponse(String code, boolean valid, BigDecimal discountAmount, String message) {
        this.code = code;
        this.valid = valid;
        this.discountAmount = discountAmount;
        this.message = message;
    }

    public String getCode() { return code; }
    public boolean isValid() { return valid; }
    public BigDecimal getDiscountAmount() { return discountAmount; }
    public String getMessage() { return message; }
}