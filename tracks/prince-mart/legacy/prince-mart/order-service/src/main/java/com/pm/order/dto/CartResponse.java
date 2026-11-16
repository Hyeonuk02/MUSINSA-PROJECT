package com.pm.order.dto;

import java.util.List;

public class CartResponse {
    private Long cartId;
    private Long userId;
    private String status;
    private List<CartItemResponse> items;
	public Long getCartId() {
		return cartId;
	}
	public void setCartId(Long cartId) {
		this.cartId = cartId;
	}
	public Long getUserId() {
		return userId;
	}
	public void setUserId(Long userId) {
		this.userId = userId;
	}
	public String getStatus() {
		return status;
	}
	public void setStatus(String status) {
		this.status = status;
	}
	public List<CartItemResponse> getItems() {
		return items;
	}
	public void setItems(List<CartItemResponse> items) {
		this.items = items;
	}
	public CartResponse(Long cartId, Long userId, String status, List<CartItemResponse> items) {
		super();
		this.cartId = cartId;
		this.userId = userId;
		this.status = status;
		this.items = items;
	}
	public CartResponse() {
		super();
		// TODO Auto-generated constructor stub
	}
    
    
}