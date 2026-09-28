package com.pm.order.entity;

import jakarta.persistence.*;
import org.hibernate.annotations.CreationTimestamp;
import java.time.LocalDateTime;

@Entity
@Table(name = "order_status_history")
public class OrderStatusHistory {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name="history_id")
    private Long historyId;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "order_id")
    private Order order;

    private String status;
    
    @CreationTimestamp
    @Column(name="changed_at")
    private LocalDateTime changedAt;
    
    @Column(name="changed_by")
    private String changedBy; // Who did it? "SYSTEM" or "ADMIN_123"

	public Long getHistoryId() {
		return historyId;
	}

	public void setHistoryId(Long historyId) {
		this.historyId = historyId;
	}

	public Order getOrder() {
		return order;
	}

	public void setOrder(Order order) {
		this.order = order;
	}

	public String getStatus() {
		return status;
	}

	public void setStatus(String status) {
		this.status = status;
	}

	public LocalDateTime getChangedAt() {
		return changedAt;
	}

	public void setChangedAt(LocalDateTime changedAt) {
		this.changedAt = changedAt;
	}

	public String getChangedBy() {
		return changedBy;
	}

	public void setChangedBy(String changedBy) {
		this.changedBy = changedBy;
	}

	public OrderStatusHistory(Long historyId, Order order, String status, LocalDateTime changedAt, String changedBy) {
		super();
		this.historyId = historyId;
		this.order = order;
		this.status = status;
		this.changedAt = changedAt;
		this.changedBy = changedBy;
	}

	public OrderStatusHistory() {
		super();
		// TODO Auto-generated constructor stub
	}
    
    
}