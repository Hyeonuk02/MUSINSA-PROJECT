package com.pm.payment.entity;

import jakarta.persistence.*;
import org.hibernate.annotations.CreationTimestamp;
import java.math.BigDecimal;
import java.time.LocalDateTime;

@Entity
@Table(name = "refunds")
public class Refund {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "refund_id")
    private Long refundId;

    @ManyToOne
    @JoinColumn(name = "payment_id")
    private Payment payment;

    private BigDecimal amount;
    private String reason;
    private String status; // PENDING, PROCESSED, FAILED

    @CreationTimestamp
    private LocalDateTime createdAt;

	public Long getRefundId() {
		return refundId;
	}

	public void setRefundId(Long refundId) {
		this.refundId = refundId;
	}

	public Payment getPayment() {
		return payment;
	}

	public void setPayment(Payment payment) {
		this.payment = payment;
	}

	public BigDecimal getAmount() {
		return amount;
	}

	public void setAmount(BigDecimal amount) {
		this.amount = amount;
	}

	public String getReason() {
		return reason;
	}

	public void setReason(String reason) {
		this.reason = reason;
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

	public Refund(Long refundId, Payment payment, BigDecimal amount, String reason, String status,
			LocalDateTime createdAt) {
		super();
		this.refundId = refundId;
		this.payment = payment;
		this.amount = amount;
		this.reason = reason;
		this.status = status;
		this.createdAt = createdAt;
	}

	public Refund() {
		super();
		// TODO Auto-generated constructor stub
	}
    
    
}