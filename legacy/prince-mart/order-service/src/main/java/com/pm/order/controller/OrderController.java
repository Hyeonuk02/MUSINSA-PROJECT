package com.pm.order.controller;

import com.pm.order.dto.OrderRequest;
import com.pm.order.entity.Order;
import com.pm.order.service.OrderService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import java.util.List;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }
    
    @GetMapping("/welcome")
    public String welcome() {
        return "Welcome!! This is the Order Service for Prince Mart by Prince Inc.";
    }
    
    @GetMapping("/all")
    public ResponseEntity<List<Order>> getAllOrders() {
		return ResponseEntity.ok(orderService.getAllOrders());
	}

    @PostMapping("/place")
    public ResponseEntity<Order> placeOrder(
            @RequestHeader("X-User-Id") Long userId, 
            @RequestBody OrderRequest request) {
        return ResponseEntity.ok(orderService.placeOrder(userId, request));
    }
    
    @GetMapping("/history")
    public ResponseEntity<List<Order>> getOrderHistory(@RequestHeader("X-User-Id") Long userId) {
        return ResponseEntity.ok(orderService.getOrderHistory(userId));
    }
    
    @GetMapping("/order/{orderId}")
    public ResponseEntity<Order> getOrderDetails(
            @PathVariable Long orderId, 
            @RequestHeader("X-User-Id") Long userId) {
        return ResponseEntity.ok(orderService.getOrderDetails(orderId, userId));
    }
    
 // Inside OrderController.java

    @GetMapping("/admin/order/{orderId}")
    public ResponseEntity<Order> getOrderDetailsForAdmin(@PathVariable Long orderId) {
        // We call the service without the userId restriction
        // Make sure to add this method to your OrderService as well
        return ResponseEntity.ok(orderService.getOrderByIdForAdmin(orderId));
    }
    
    @PutMapping("/{orderId}/status")
    public ResponseEntity<Order> updateStatus(
            @PathVariable Long orderId,
            @RequestParam String paymentStatus,
            @RequestParam String orderStatus) {
        // Now returns the Order object which contains the userId needed for notifications
        Order updatedOrder = orderService.updateStatus(orderId, paymentStatus, orderStatus);
        return ResponseEntity.ok(updatedOrder);
    }
    
 // Inside OrderController.java

    @GetMapping("/check-purchase/{userId}/{productId}")
    public ResponseEntity<Boolean> hasPurchasedProduct(
            @PathVariable Long userId, 
            @PathVariable Long productId) {
        
        boolean purchased = orderService.checkUserPurchasedProduct(userId, productId);
        return ResponseEntity.ok(purchased);
    }
    
    @GetMapping("/my-orders")
    public ResponseEntity<List<Order>> getMyOrders(@RequestHeader("X-User-Id") Long userId) {
		List<Order> orders = orderService.getMyOrders(userId);
		return ResponseEntity.ok(orders);
	}
    
 // Inside OrderController.java
    @PutMapping("/{orderId}/cancel")
    public ResponseEntity<Order> cancelOrder(
        @PathVariable Long orderId, 
        @RequestHeader("X-User-Id") Long userId) {
        
        // Logic: Find order, verify userId, check if status is PENDING/CONFIRMED, 
        // then set to CANCELLED and trigger Inventory Release.
        Order cancelledOrder = orderService.cancelOrder(orderId, userId);
        return ResponseEntity.ok(cancelledOrder);
    }
}