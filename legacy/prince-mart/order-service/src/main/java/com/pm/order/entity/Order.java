package com.pm.order.entity;

import jakarta.persistence.*;
import org.hibernate.annotations.CreationTimestamp;
import com.fasterxml.jackson.annotation.JsonIgnore;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

@Entity
@Table(name = "orders")
public class Order {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name="order_id")
    private Long orderId;

    @Column(name="user_id")
    private Long userId;
    
    @Column(name="order_status")
    private String orderStatus;   // PENDING, CONFIRMED, SHIPPED, DELIVERED, CANCELLED
    
    @Column(name="payment_status")
    private String paymentStatus; // UNPAID, PAID, REFUNDED

    @Column(name="transaction_id") // Added for tracking payment
    private String transactionId;
    
    @Column(name="total_amount")
    private BigDecimal totalAmount;
    private String currency;      // INR, USD, etc.
    
    @Column(name="shipping_address_id")
    private Long shippingAddressId;
    
    @Column(name="billing_address_id")
    private Long billingAddressId;

    @Column(name="customer_name")
    private String customerName; // NEW: To store name from Identity Service

    @Column(name="user_email")
    private String userEmail; 
    
    @CreationTimestamp
    @Column(name="created_at")
    private LocalDateTime createdAt;

    @OneToMany(mappedBy = "order", cascade = CascadeType.ALL, orphanRemoval = true)
    @JsonIgnore
    private List<OrderItem> items;

    @Column(columnDefinition = "TEXT")
    private String shippingAddressSnapshot;
    
    // Getters and Setters
    public String getTransactionId() {
        return transactionId;
    }

    public void setTransactionId(String transactionId) {
        this.transactionId = transactionId;
    }

    public String getShippingAddressSnapshot() {
        return shippingAddressSnapshot;
    }

    public void setShippingAddressSnapshot(String shippingAddressSnapshot) {
        this.shippingAddressSnapshot = shippingAddressSnapshot;
    }

    public Long getOrderId() {
        return orderId;
    }

    public void setOrderId(Long orderId) {
        this.orderId = orderId;
    }

    public Long getUserId() {
        return userId;
    }

    public void setUserId(Long userId) {
        this.userId = userId;
    }

    public String getOrderStatus() {
        return orderStatus;
    }

    public void setOrderStatus(String orderStatus) {
        this.orderStatus = orderStatus;
    }

    public String getPaymentStatus() {
        return paymentStatus;
    }

    public void setPaymentStatus(String paymentStatus) {
        this.paymentStatus = paymentStatus;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public void setTotalAmount(BigDecimal totalAmount) {
        this.totalAmount = totalAmount;
    }

    public String getCurrency() {
        return currency;
    }

    public void setCurrency(String currency) {
        this.currency = currency;
    }

    public Long getShippingAddressId() {
        return shippingAddressId;
    }

    public void setShippingAddressId(Long shippingAddressId) {
        this.shippingAddressId = shippingAddressId;
    }

    public Long getBillingAddressId() {
        return billingAddressId;
    }

    public void setBillingAddressId(Long billingAddressId) {
        this.billingAddressId = billingAddressId;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
    }

    public List<OrderItem> getItems() {
        return items;
    }

    public void setItems(List<OrderItem> items) {
        this.items = items;
    }

    // Updated Constructor
    

    public Order() {
        super();
    }

	public Order(Long orderId, Long userId, String orderStatus, String paymentStatus, String transactionId,
			BigDecimal totalAmount, String currency, Long shippingAddressId, Long billingAddressId, String customerName,
			String userEmail, LocalDateTime createdAt, List<OrderItem> items, String shippingAddressSnapshot) {
		super();
		this.orderId = orderId;
		this.userId = userId;
		this.orderStatus = orderStatus;
		this.paymentStatus = paymentStatus;
		this.transactionId = transactionId;
		this.totalAmount = totalAmount;
		this.currency = currency;
		this.shippingAddressId = shippingAddressId;
		this.billingAddressId = billingAddressId;
		this.customerName = customerName;
		this.userEmail = userEmail;
		this.createdAt = createdAt;
		this.items = items;
		this.shippingAddressSnapshot = shippingAddressSnapshot;
	}

	public String getCustomerName() {
		return customerName;
	}

	public void setCustomerName(String customerName) {
		this.customerName = customerName;
	}

	public String getUserEmail() {
		return userEmail;
	}

	public void setUserEmail(String userEmail) {
		this.userEmail = userEmail;
	}
}