package com.pm.coupon.dto;

import java.math.BigDecimal;

public class CouponRequest {
    private String code;
    private BigDecimal orderAmount;

    public CouponRequest() {}

    public String getCode() { return code; }
    public void setCode(String code) { this.code = code; }

    public BigDecimal getOrderAmount() { return orderAmount; }
    public void setOrderAmount(BigDecimal orderAmount) { this.orderAmount = orderAmount; }
}