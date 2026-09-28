package com.pm.payment.entity;

import jakarta.persistence.*;
import org.hibernate.annotations.CreationTimestamp;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

@Entity
@Table(name = "payments")
public class Payment {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "payment_id")
    private Long paymentId;
    
    @Column(name = "order_id", nullable = false)
    private Long orderId;
    @Column(name="payment_method", nullable = false)
    private String paymentMethod; // e.g., CREDIT_CARD, UPI, RAZORPAY
    @Column(name="transaction_id", unique = true)
    private String transactionId; // The ID from the Payment Gateway
    private BigDecimal amount;
    private String currency;
    private String status;        // PENDING, COMPLETED, FAILED, REFUNDED

    @CreationTimestamp
    @Column(updatable = false)
    private LocalDateTime createdAt;

    @OneToMany(mappedBy = "payment", cascade = CascadeType.ALL)
    private List<Refund> refunds;

	public Long getPaymentId() {
		return paymentId;
	}

	public void setPaymentId(Long paymentId) {
		this.paymentId = paymentId;
	}

	public Long getOrderId() {
		return orderId;
	}

	public void setOrderId(Long orderId) {
		this.orderId = orderId;
	}

	public String getPaymentMethod() {
		return paymentMethod;
	}

	public void setPaymentMethod(String paymentMethod) {
		this.paymentMethod = paymentMethod;
	}

	public String getTransactionId() {
		return transactionId;
	}

	public void setTransactionId(String transactionId) {
		this.transactionId = transactionId;
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

	public String getStatus() {
		return status;
	}

	public void setStatus(String status) {
		this.status = status;
	}

	public LocalDateTime getCreatedAt() {
		return createdAt;
	}

	public void setCreatedAt(LocalDateTime createdAt) {
		this.createdAt = createdAt;
	}

	public List<Refund> getRefunds() {
		return refunds;
	}

	public void setRefunds(List<Refund> refunds) {
		this.refunds = refunds;
	}

	public Payment(Long paymentId, Long orderId, String paymentMethod, String transactionId, BigDecimal amount,
			String currency, String status, LocalDateTime createdAt, List<Refund> refunds) {
		super();
		this.paymentId = paymentId;
		this.orderId = orderId;
		this.paymentMethod = paymentMethod;
		this.transactionId = transactionId;
		this.amount = amount;
		this.currency = currency;
		this.status = status;
		this.createdAt = createdAt;
		this.refunds = refunds;
	}

	public Payment() {
		super();
		// TODO Auto-generated constructor stub
	}
    
    
}