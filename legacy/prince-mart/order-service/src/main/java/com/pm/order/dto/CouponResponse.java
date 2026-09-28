package com.pm.order.dto;

public class CouponResponse {
    private String code;
    private boolean valid;
    private java.math.BigDecimal discountAmount;
    private String message;
    // Getters/Setters...
    
    public CouponResponse() {
	}
    
    	public CouponResponse(String code, boolean valid, java.math.BigDecimal discountAmount, String message) {
		this.code = code;
		this.valid = valid;
		this.discountAmount = discountAmount;
		this.message = message;
	}

		public String getCode() {
			return code;
		}

		public void setCode(String code) {
			this.code = code;
		}

		public boolean isValid() {
			return valid;
		}

		public void setValid(boolean valid) {
			this.valid = valid;
		}

		public java.math.BigDecimal getDiscountAmount() {
			return discountAmount;
		}

		public void setDiscountAmount(java.math.BigDecimal discountAmount) {
			this.discountAmount = discountAmount;
		}

		public String getMessage() {
			return message;
		}

		public void setMessage(String message) {
			this.message = message;
		}
    	
    	
}