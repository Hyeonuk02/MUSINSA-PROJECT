package com.pm.payment.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.pm.payment.client.AuditClient; // New Client
import com.pm.payment.client.NotificationClient;
import com.pm.payment.client.OrderClient;
import com.pm.payment.dto.*;
import com.pm.payment.entity.Payment;
import com.pm.payment.exception.ResourceNotFoundException;
import com.pm.payment.repository.PaymentRepository;
import com.razorpay.Order;
import com.razorpay.RazorpayClient;
import org.json.JSONObject;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;

@Service
public class PaymentService {

    private final PaymentRepository paymentRepository;
    private final OrderClient orderClient;
    private final NotificationClient notificationClient;
    private final AuditClient auditClient; // New
    private final ObjectMapper objectMapper; // New

    @Value("${razorpay.key.id}")
    private String razorpayId;

    @Value("${razorpay.key.secret}")
    private String razorpaySecret;

    public PaymentService(PaymentRepository paymentRepository, 
                          OrderClient orderClient,
                          NotificationClient notificationClient,
                          AuditClient auditClient,
                          ObjectMapper objectMapper) {
        this.paymentRepository = paymentRepository;
        this.orderClient = orderClient;
        this.notificationClient = notificationClient;
        this.auditClient = auditClient;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public PaymentResponse processPayment(PaymentRequest request) {
        try {
            RazorpayClient client = new RazorpayClient(razorpayId, razorpaySecret);
            int amountInPaise = request.getAmount().multiply(new BigDecimal(100)).intValue();

            JSONObject orderRequest = new JSONObject();
            orderRequest.put("amount", amountInPaise);
            orderRequest.put("currency", "INR");
            orderRequest.put("receipt", "order_rcptid_" + request.getOrderId());

            Order razorpayOrder = client.orders.create(orderRequest);
            String razorpayOrderId = razorpayOrder.get("id");

            Payment payment = new Payment();
            payment.setOrderId(request.getOrderId());
            payment.setAmount(request.getAmount());
            payment.setCurrency("INR");
            payment.setPaymentMethod("RAZORPAY");
            payment.setTransactionId(razorpayOrderId);
            payment.setStatus("CREATED");
            
            Payment savedPayment = paymentRepository.save(payment);

            // Audit the start of the payment process
            sendAuditLog(null, "PAYMENT_INITIATED", "OrderID: " + request.getOrderId(), savedPayment);

            return PaymentResponse.builder()
                    .transactionId(razorpayOrderId)
                    .paymentStatus("CREATED")
                    .message("Order Created Successfully")
                    .build();

        } catch (Exception e) {
            // Audit the failure to create Razorpay order
            sendAuditLog(null, "PAYMENT_INITIATION_FAILED", "OrderID: " + request.getOrderId(), "Error: " + e.getMessage());
            
            return PaymentResponse.builder()
                    .paymentStatus("FAILED")
                    .message(e.getMessage())
                    .build();
        }
    }

    @Transactional
    public void completePaymentManually(String razorpayOrderId, String paymentId) {
        Payment payment = paymentRepository.findByTransactionId(razorpayOrderId)
                .orElseThrow(() -> new ResourceNotFoundException("Payment not found"));

        String dataBefore = "Status: " + payment.getStatus();

        payment.setStatus("COMPLETED");
        Payment updatedPayment = paymentRepository.save(payment);

        // 1. Handshake: Get the real User Email, Name, and UserID from Order Service
        OrderResponse orderInfo = orderClient.updateOrderStatus(payment.getOrderId(), "PAID", "CONFIRMED");
        System.out.println("Handshake successful for Order: " + payment.getOrderId());

        // Audit the successful payment completion
        sendAuditLog(orderInfo.getUserId(), "PAYMENT_COMPLETED_SUCCESS", dataBefore, updatedPayment);

        // 2. Trigger Notification
        NotificationRequest emailReq = new NotificationRequest();
        emailReq.setUserId(orderInfo.getUserId()); 
        emailReq.setRecipient(orderInfo.getUserEmail()); 
        emailReq.setSubject("Order Confirmed - Prince Mart");
        emailReq.setCustomerName(orderInfo.getCustomerName()); 
        emailReq.setOrderId(payment.getOrderId().toString());
        emailReq.setAmount(payment.getAmount().toString());

        try {
            notificationClient.sendConfirmation(emailReq);
        } catch (Exception e) {
            // Non-critical: Log the notification failure to Audit
            sendAuditLog(orderInfo.getUserId(), "POST_PAYMENT_NOTIFICATION_FAILED", null, e.getMessage());
            System.err.println("Non-critical Error: Failed to trigger notification - " + e.getMessage());
        }
    }

    // Centralized Helper for External Auditing
    private void sendAuditLog(Long userId, String action, Object dataBefore, Object dataAfter) {
        try {
            String before = dataBefore != null ? (dataBefore instanceof String ? (String) dataBefore : objectMapper.writeValueAsString(dataBefore)) : null;
            String after = dataAfter != null ? (dataAfter instanceof String ? (String) dataAfter : objectMapper.writeValueAsString(dataAfter)) : null;

            auditClient.createLog(new AuditLogRequest(
                "PAYMENT-SERVICE", 
                action, 
                userId, 
                before, 
                after
            ));
        } catch (Exception e) {
            System.err.println("Audit logging failed in Payment Service: " + e.getMessage());
        }
    }
}