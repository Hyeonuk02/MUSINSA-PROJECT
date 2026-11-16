package com.pm.order.service;

import org.springframework.stereotype.Service;

import com.pm.order.entity.OrderItem;
import com.pm.order.exception.ResourceNotFoundException;
import com.pm.order.repository.OrderItemRepository;

@Service
public class OrderItemService {

	private final OrderItemRepository orderItemRepository;
	
	public OrderItemService(OrderItemRepository orderItemRepository) {
		this.orderItemRepository = orderItemRepository;
	}
	
    public OrderItem getOrderItembyId(Long orderId) {
    	return orderItemRepository.findByOrderOrderId(orderId).orElseThrow(() -> new ResourceNotFoundException("OrderItem not found for orderId: " + orderId));
    }
}
