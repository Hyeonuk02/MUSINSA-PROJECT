package com.pm.order.dto;

import com.fasterxml.jackson.annotation.JsonPropertyOrder;

// [LEGACY_CHANGES L-F2] payment-service의 NotificationRequest를 그대로 복사했다.
// payment(Boot 3, Jackson 2)는 필드 선언 순서로 직렬화했지만 order(Boot 4, Jackson 3)는 기본이 알파벳순이라
// 알림 요청 본문의 키 순서가 달라진다. 원본과 같은 본문을 보내도록 선언 순서를 명시한다.
@JsonPropertyOrder({"userId", "recipient", "subject", "customerName", "orderId", "amount"})

public class NotificationRequest {
	private Long userId; // Added to link notifications to users
    private String recipient;
    private String subject;
    private String customerName;
    private String orderId;
    private String amount;

    // Standard Getters and Setters (No Lombok)
    public Long getUserId() { return userId; }
    public void setUserId(Long userId) { this.userId = userId; }
    public String getRecipient() { return recipient; }
    public void setRecipient(String recipient) { this.recipient = recipient; }
    public String getSubject() { return subject; }
    public void setSubject(String subject) { this.subject = subject; }
    public String getCustomerName() { return customerName; }
    public void setCustomerName(String customerName) { this.customerName = customerName; }
    public String getOrderId() { return orderId; }
    public void setOrderId(String orderId) { this.orderId = orderId; }
    public String getAmount() { return amount; }
    public void setAmount(String amount) { this.amount = amount; }
}