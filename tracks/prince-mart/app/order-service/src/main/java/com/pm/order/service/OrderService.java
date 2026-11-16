package com.pm.order.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.pm.order.client.*;
import com.pm.order.dto.*;
import com.pm.order.entity.Order;
import com.pm.order.entity.OrderItem;
import com.pm.order.entity.OrderStatusHistory;
import com.pm.order.exception.ResourceNotFoundException;
import com.pm.order.repository.OrderItemRepository;
import com.pm.order.repository.OrderRepository;
import com.pm.order.repository.OrderStatusHistoryRepository;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.List;
import java.util.stream.Collectors;

@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final OrderStatusHistoryRepository historyRepository;
    private final CartClient cartClient;
    private final InventoryClient inventoryClient;
    private final AddressClient addressClient;
    private final PaymentClient paymentClient;
    private final UserClient userClient;
    private final ShippingClient shippingClient; 
    private final CouponClient couponClient;
    private final AuditClient auditClient; // New client
    private final ObjectMapper objectMapper; // For JSON snapshots

    public OrderService(OrderRepository orderRepository,
                        OrderStatusHistoryRepository historyRepository,
                        CartClient cartClient,
                        InventoryClient inventoryClient,
                        AddressClient addressClient,
                        PaymentClient paymentClient,
                        UserClient userClient,
                        ShippingClient shippingClient,
                        CouponClient couponClient,
                        AuditClient auditClient,
                        ObjectMapper objectMapper,
                        OrderItemRepository orderItemRepository) {
        this.orderRepository = orderRepository;
        this.historyRepository = historyRepository;
        this.cartClient = cartClient;
        this.inventoryClient = inventoryClient;
        this.addressClient = addressClient;
        this.paymentClient = paymentClient;
        this.userClient = userClient;
        this.shippingClient = shippingClient;
        this.couponClient = couponClient;
        this.auditClient = auditClient;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public Order placeOrder(Long userId, OrderRequest request) {
        CartResponse cart = cartClient.getMyCart(userId);
        if (cart == null || cart.getItems().isEmpty()) {
            throw new ResourceNotFoundException("Cannot place order: Cart is empty");
        }

        UserResponse user = userClient.getUserById(userId);
        AddressResponse address = addressClient.getAddressById(request.getShippingAddressId());
        
        String snapshot = String.format("%s\n%s, %s\n%s, %s, %s - %s\nPhone: %s",
                address.getFullName(),
                address.getAddressLine1(),
                address.getAddressLine2() != null ? address.getAddressLine2() : "",
                address.getCity(),
                address.getState(),
                address.getCountry(),
                address.getPostalCode(),
                address.getPhone());

        Order order = new Order();
        order.setUserId(userId);
        order.setCustomerName(user.getFullName());
        order.setUserEmail(user.getEmail());
        order.setOrderStatus("PENDING");
        order.setPaymentStatus("UNPAID");
        order.setCurrency(request.getCurrency());
        order.setShippingAddressId(request.getShippingAddressId());
        order.setBillingAddressId(request.getBillingAddressId());
        order.setShippingAddressSnapshot(snapshot); 

        List<OrderItem> orderItems = cart.getItems().stream().map(cartItem -> {
            OrderItem item = new OrderItem();
            item.setOrder(order);
            item.setProductId(cartItem.getProductId());
            item.setVariantId(cartItem.getVariantId());
            item.setQuantity(cartItem.getQuantity());
            item.setPrice(cartItem.getPriceSnapshot());
            item.setSubtotal(cartItem.getPriceSnapshot().multiply(new BigDecimal(cartItem.getQuantity())));
            return item;
        }).collect(Collectors.toList());

        order.setItems(orderItems);

        BigDecimal cartTotal = orderItems.stream()
                .map(OrderItem::getSubtotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        
        BigDecimal discountAmount = BigDecimal.ZERO;
        String appliedCoupon = request.getCouponCode();

        if (appliedCoupon != null && !appliedCoupon.isEmpty()) {
            try {
                CouponResponse couponRes = couponClient.validateCoupon(userId, 
                    new CouponRequest(appliedCoupon, cartTotal));
                
                if (couponRes.isValid()) {
                    discountAmount = couponRes.getDiscountAmount();
                }
            } catch (Exception e) {
                System.err.println("Coupon validation failed: " + e.getMessage());
            }
        }

        order.setTotalAmount(cartTotal.subtract(discountAmount));

        Order savedOrder = orderRepository.save(order);
        orderRepository.flush(); 

        saveHistory(savedOrder, "PENDING", "SYSTEM");

        // Record Coupon Usage
        if (discountAmount.compareTo(BigDecimal.ZERO) > 0) {
            try {
                couponClient.useCoupon(userId, savedOrder.getOrderId(), appliedCoupon);
            } catch (Exception e) {
                System.err.println("Failed to record coupon usage: " + e.getMessage());
            }
        }

        // Inventory Management
        List<StockUpdateDTO> stockUpdates = savedOrder.getItems().stream()
                .map(item -> new StockUpdateDTO(item.getVariantId(), item.getQuantity()))
                .collect(Collectors.toList());

        try {
            inventoryClient.reduceStock(stockUpdates);
        } catch (Exception e) {
            throw new ResourceNotFoundException("Inventory update failed: " + e.getMessage());
        }

        try {
            cartClient.clearCart(userId);
        } catch (Exception e) {
            System.err.println("Non-critical error: Failed to clear cart - " + e.getMessage());
        }

        // Audit the order creation
        sendAuditLog(userId, "PLACE_ORDER", null, savedOrder);

        PaymentRequest paymentRequest = new PaymentRequest(
                savedOrder.getOrderId(),
                savedOrder.getTotalAmount(),
                savedOrder.getCurrency(),
                "RAZORPAY" 
        );

        try {
            PaymentResponse paymentResponse = paymentClient.process(paymentRequest);
            if ("CREATED".equalsIgnoreCase(paymentResponse.getPaymentStatus()) || 
                "COMPLETED".equalsIgnoreCase(paymentResponse.getPaymentStatus())) {
                savedOrder.setTransactionId(paymentResponse.getTransactionId());
                orderRepository.save(savedOrder);
            } else {
                handlePaymentFailure(savedOrder, stockUpdates, "Payment Rejected");
            }
        } catch (Exception e) {
            handlePaymentFailure(savedOrder, stockUpdates, "Payment Connection Error: " + e.getMessage());
        }

        return savedOrder;
    }

    private void handlePaymentFailure(Order order, List<StockUpdateDTO> stockUpdates, String reason) {
        String dataBefore = null;
        try { dataBefore = objectMapper.writeValueAsString(order); } catch (Exception e) {}

        order.setPaymentStatus("FAILED");
        order.setOrderStatus("CANCELLED");
        Order failedOrder = orderRepository.save(order);
        saveHistory(failedOrder, "ORDER_CANCELLED_PAYMENT_FAILURE", "SYSTEM");

        try {
            inventoryClient.addStock(stockUpdates);
        } catch (Exception e) {
            System.err.println("CRITICAL: Failed to restore stock");
        }

        // Audit the payment failure
        sendAuditLog(order.getUserId(), "PAYMENT_FAILURE_CANCELLATION", dataBefore, failedOrder);
    }

    private void saveHistory(Order order, String status, String changedBy) {
        OrderStatusHistory history = new OrderStatusHistory();
        history.setOrder(order);
        history.setStatus(status);
        history.setChangedBy(changedBy);
        historyRepository.save(history);
    }

    @Transactional
    public Order updateStatus(Long orderId, String paymentStatus, String orderStatus) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new ResourceNotFoundException("Order not found"));
        
        String dataBefore = null;
        try { dataBefore = objectMapper.writeValueAsString(order); } catch (Exception e) {}

        order.setPaymentStatus(paymentStatus);
        order.setOrderStatus(orderStatus);
        Order updatedOrder = orderRepository.save(order);
        saveHistory(updatedOrder, orderStatus, "PAYMENT_SERVICE");

        // Audit the status change
        sendAuditLog(updatedOrder.getUserId(), "ORDER_STATUS_UPDATE", dataBefore, updatedOrder);

        if ("CONFIRMED".equalsIgnoreCase(orderStatus.trim())) {
            try {
                shippingClient.initiateShipment(orderId, updatedOrder.getCustomerName(), updatedOrder.getUserEmail());
            } catch (Exception e) {
                System.err.println("Shipping Trigger Failed");
            }
        }
        return updatedOrder; 
    }

    public List<Order> getOrderHistory(Long userId) {
        return orderRepository.findByUserIdOrderByCreatedAtDesc(userId);
    }

    public Order getOrderDetails(Long orderId, Long userId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new ResourceNotFoundException("Order not found"));
        if (!order.getUserId().equals(userId)) {
            throw new ResourceNotFoundException("Unauthorized");
        }
        return order;
    }
    
    public boolean checkUserPurchasedProduct(Long userId, Long productId) {
        return orderRepository.existsByUserIdAndProductId(userId, productId);
    }

    // Helper for centralized auditing
    private void sendAuditLog(Long userId, String action, Object dataBefore, Object dataAfter) {
        try {
            String before = dataBefore != null ? (dataBefore instanceof String ? (String) dataBefore : objectMapper.writeValueAsString(dataBefore)) : null;
            String after = dataAfter != null ? objectMapper.writeValueAsString(dataAfter) : null;

            auditClient.createLog(new AuditLogRequest(
                "ORDER-SERVICE", 
                action, 
                userId, 
                before, 
                after
            ));
        } catch (Exception e) {
            System.err.println("Audit logging failed in Order Service: " + e.getMessage());
        }
    }
    
    public List<Order> getMyOrders(Long userId) {
		return orderRepository.findByUserId(userId);
	}

    @Transactional
    public Order cancelOrder(Long orderId, Long userId) {
        // 1. Fetch the Order
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new ResourceNotFoundException("Order Registry entry not found"));

        // 2. Security Check: Ensure the order belongs to the user
        if (!order.getUserId().equals(userId)) {
            throw new ResourceNotFoundException("Access Denied: This is not your acquisition.");
        }

        // 3. Business Logic: Check if status is still cancellable
        String currentStatus = order.getOrderStatus().toUpperCase();
        if (currentStatus.equals("SHIPPED") || currentStatus.equals("DELIVERED")) {
            throw new IllegalStateException("Logistics already initiated. Cannot cancel at this stage.");
        }
        
        if (currentStatus.equals("CANCELLED")) {
            throw new IllegalStateException("This order is already revoked.");
        }

        // 4. Capture Data Before for Auditing
        String dataBefore = null;
        try { dataBefore = objectMapper.writeValueAsString(order); } catch (Exception e) {}

        // 5. Inventory Compensation (Restoring Stock)
        List<StockUpdateDTO> stockToRestore = order.getItems().stream()
                .map(item -> new StockUpdateDTO(item.getVariantId(), item.getQuantity()))
                .collect(Collectors.toList());

        try {
            // Using your existing Feign Client method
            inventoryClient.addStock(stockToRestore);
        } catch (Exception e) {
            System.err.println("CRITICAL: Failed to restore stock during user cancellation - " + e.getMessage());
            // Depending on your policy, you might want to throw an exception here 
            // to roll back the order status change if inventory can't be updated.
            throw new RuntimeException("Inventory Service communication failure.");
        }

        // 6. Update Order Status
        order.setOrderStatus("CANCELLED");
        Order cancelledOrder = orderRepository.save(order);
        
        // 7. Record History
        saveHistory(cancelledOrder, "CANCELLED_BY_USER", "CUSTOMER_ACTION");

        // 8. Audit the cancellation
        sendAuditLog(userId, "USER_ORDER_CANCELLATION", dataBefore, cancelledOrder);

        return cancelledOrder;
    }

	public List<Order> getAllOrders() {
		// TODO Auto-generated method stub
		return orderRepository.findAll();
	}
	
	public Order getOrderByIdForAdmin(Long orderId) {
	    return orderRepository.findById(orderId)
	            .orElseThrow(() -> new ResourceNotFoundException("Order " + orderId + " not found in global registry"));
	}
}