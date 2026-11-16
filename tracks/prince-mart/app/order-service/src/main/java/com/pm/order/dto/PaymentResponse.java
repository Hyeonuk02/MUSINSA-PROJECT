package com.pm.order.dto;

public class PaymentResponse {
    private String transactionId;
    private String paymentStatus;
    private String message;

    public PaymentResponse() {}

    public PaymentResponse(String transactionId, String paymentStatus, String message) {
        this.transactionId = transactionId;
        this.paymentStatus = paymentStatus;
        this.message = message;
    }

    public String getTransactionId() { return transactionId; }
    public void setTransactionId(String transactionId) { this.transactionId = transactionId; }

    public String getPaymentStatus() { return paymentStatus; }
    public void setPaymentStatus(String paymentStatus) { this.paymentStatus = paymentStatus; }

    public String getMessage() { return message; }
    public void setMessage(String message) { this.message = message; }
}