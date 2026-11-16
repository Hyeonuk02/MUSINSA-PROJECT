package com.pm.order.dto;

import java.math.BigDecimal;

public class PaymentRequest {
    private Long orderId;
    private BigDecimal amount;
    private String currency;
    private String paymentMethod;

    public PaymentRequest() {}

    public PaymentRequest(Long orderId, BigDecimal amount, String currency, String paymentMethod) {
        this.orderId = orderId;
        this.amount = amount;
        this.currency = currency;
        this.paymentMethod = paymentMethod;
    }

    // Getters
    public Long getOrderId() { return orderId; }
    public BigDecimal getAmount() { return amount; }
    public void setOrderId(Long orderId) {
		this.orderId = orderId;
	}

	public void setAmount(BigDecimal amount) {
		this.amount = amount;
	}

	public void setCurrency(String currency) {
		this.currency = currency;
	}

	public void setPaymentMethod(String paymentMethod) {
		this.paymentMethod = paymentMethod;
	}

	public String getCurrency() { return currency; }
    public String getPaymentMethod() { return paymentMethod; }
}