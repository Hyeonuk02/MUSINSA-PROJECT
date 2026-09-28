package com.pm.payment.dto;

public class PaymentResponse {
    private String transactionId;
    private String paymentStatus;
    private String message;

    public PaymentResponse() {}

    private PaymentResponse(Builder builder) {
        this.transactionId = builder.transactionId;
        this.paymentStatus = builder.paymentStatus;
        this.message = builder.message;
    }

    // Getters
    public String getTransactionId() { return transactionId; }
    public String getPaymentStatus() { return paymentStatus; }
    public String getMessage() { return message; }

    // Static Builder Class
    public static class Builder {
        private String transactionId;
        private String paymentStatus;
        private String message;

        public Builder transactionId(String transactionId) {
            this.transactionId = transactionId;
            return this;
        }

        public Builder paymentStatus(String paymentStatus) {
            this.paymentStatus = paymentStatus;
            return this;
        }

        public Builder message(String message) {
            this.message = message;
            return this;
        }

        public PaymentResponse build() {
            return new PaymentResponse(this);
        }
    }

    public static Builder builder() {
        return new Builder();
    }
}