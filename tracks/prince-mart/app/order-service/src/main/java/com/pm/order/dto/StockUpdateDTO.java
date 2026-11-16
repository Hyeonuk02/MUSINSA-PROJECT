package com.pm.order.dto;

public class StockUpdateDTO {
    private Long variantId;
    private Integer quantity;
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
	public StockUpdateDTO(Long variantId, Integer quantity) {
		super();
		this.variantId = variantId;
		this.quantity = quantity;
	}
	public StockUpdateDTO() {
		super();
		// TODO Auto-generated constructor stub
	}
}