package com.pm.order.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.pm.order.entity.OrderItem;
import com.pm.order.service.OrderItemService;

@RestController
@RequestMapping("/order-items")
public class OrderItemController {

	private final OrderItemService orderItemService;
	
	public OrderItemController(OrderItemService orderItemService) {
		this.orderItemService = orderItemService;
	}
	
    @GetMapping("/orderitem/{orderItemId}")
    public ResponseEntity<OrderItem> getOrderByOrderItemId(
			@PathVariable Long orderItemId) {
		
		OrderItem orderItem = orderItemService.getOrderItembyId(orderItemId);
		return ResponseEntity.ok(orderItem);
	}
}
