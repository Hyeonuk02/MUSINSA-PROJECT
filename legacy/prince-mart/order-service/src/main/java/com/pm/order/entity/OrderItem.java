package com.pm.order.entity;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "order_items")
public class OrderItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name="order_item_id")
    private Long orderItemId;

    @ManyToOne
    @JoinColumn(name = "order_id")
    private Order order;

    @Column(name="product_id")
    private Long productId;
    
    @Column(name="variant_id")
    private Long variantId;
    private Integer quantity;
    private BigDecimal price;    // Price per unit at time of order
    private BigDecimal subtotal; // quantity * price
	public Long getOrderItemId() {
		return orderItemId;
	}
	public void setOrderItemId(Long orderItemId) {
		this.orderItemId = orderItemId;
	}
	public Order getOrder() {
		return order;
	}
	public void setOrder(Order order) {
		this.order = order;
	}
	public Long getProductId() {
		return productId;
	}
	public void setProductId(Long productId) {
		this.productId = productId;
	}
	public Long getVariantId() {
		return variantId;
	}
	public void setVariantId(Long variantId) {
		this.variantId = variantId;
	}
	public Integer getQuantity() {
		return quantity;
	}
	public void setQuantity(Integer quantity) {
		this.quantity = quantity;
	}
	public BigDecimal getPrice() {
		return price;
	}
	public void setPrice(BigDecimal price) {
		this.price = price;
	}
	public BigDecimal getSubtotal() {
		return subtotal;
	}
	public void setSubtotal(BigDecimal subtotal) {
		this.subtotal = subtotal;
	}
	public OrderItem(Long orderItemId, Order order, Long productId, Long variantId, Integer quantity, BigDecimal price,
			BigDecimal subtotal) {
		super();
		this.orderItemId = orderItemId;
		this.order = order;
		this.productId = productId;
		this.variantId = variantId;
		this.quantity = quantity;
		this.price = price;
		this.subtotal = subtotal;
	}
	public OrderItem() {
		super();
		// TODO Auto-generated constructor stub
	}
    
    
}