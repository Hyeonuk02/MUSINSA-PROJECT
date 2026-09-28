package com.pm.order.dto;

import java.math.BigDecimal;

public class CartItemResponse {
    private Long productId;
    private Long variantId;
    private Integer quantity;
    private BigDecimal priceSnapshot;
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
	public BigDecimal getPriceSnapshot() {
		return priceSnapshot;
	}
	public void setPriceSnapshot(BigDecimal priceSnapshot) {
		this.priceSnapshot = priceSnapshot;
	}
	public CartItemResponse(Long productId, Long variantId, Integer quantity, BigDecimal priceSnapshot) {
		super();
		this.productId = productId;
		this.variantId = variantId;
		this.quantity = quantity;
		this.priceSnapshot = priceSnapshot;
	}
	public CartItemResponse() {
		super();
		// TODO Auto-generated constructor stub
	}
    
    
}