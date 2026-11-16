package com.pm.order.dto;

public class CouponRequest {
    private String code;
    private java.math.BigDecimal orderAmount;
    
    public CouponRequest(String code, java.math.BigDecimal orderAmount) {
        this.code = code;
        this.orderAmount = orderAmount;
    }
    // Getters/Setters...

	public String getCode() {
		return code;
	}

	public void setCode(String code) {
		this.code = code;
	}

	public java.math.BigDecimal getOrderAmount() {
		return orderAmount;
	}

	public void setOrderAmount(java.math.BigDecimal orderAmount) {
		this.orderAmount = orderAmount;
	}
    
}