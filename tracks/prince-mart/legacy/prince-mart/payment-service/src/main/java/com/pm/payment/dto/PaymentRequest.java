package com.pm.payment.dto;

import java.math.BigDecimal;

public class PaymentRequest {
    private Long orderId;
    private BigDecimal amount;
    private String currency;
    private String paymentMethod; // e.g., "RAZORPAY", "STRIPE", "COD"
	public Long getOrderId() {
		return orderId;
	}
	public void setOrderId(Long orderId) {
		this.orderId = orderId;
	}
	public BigDecimal getAmount() {
		return amount;
	}
	public void setAmount(BigDecimal amount) {
		this.amount = amount;
	}
	public String getCurrency() {
		return currency;
	}
	public void setCurrency(String currency) {
		this.currency = currency;
	}
	public String getPaymentMethod() {
		return paymentMethod;
	}
	public void setPaymentMethod(String paymentMethod) {
		this.paymentMethod = paymentMethod;
	}
	public PaymentRequest(Long orderId, BigDecimal amount, String currency, String paymentMethod) {
		super();
		this.orderId = orderId;
		this.amount = amount;
		this.currency = currency;
		this.paymentMethod = paymentMethod;
	}
	public PaymentRequest() {
		super();
		// TODO Auto-generated constructor stub
	}
    
    
}