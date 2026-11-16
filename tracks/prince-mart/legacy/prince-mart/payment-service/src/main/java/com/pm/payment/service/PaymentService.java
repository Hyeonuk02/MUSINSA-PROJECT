package com.pm.payment.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.pm.payment.client.AuditClient; // New Client
import com.pm.payment.dto.*;
import com.pm.payment.entity.Payment;
import com.pm.payment.exception.ResourceNotFoundException;
import com.pm.payment.repository.PaymentRepository;
import com.pm.payment.event.PaymentEventPublisher;
import com.pm.payment.gateway.PaymentGateway;
import org.json.JSONObject;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;

@Service
public class PaymentService {

    private final PaymentRepository paymentRepository;
    private final AuditClient auditClient; // New
    private final ObjectMapper objectMapper; // New
    // [LEGACY_CHANGES L-F1] Razorpay SDK 직접 호출 대신 PaymentGateway (키 설정은 RazorpayPaymentGateway로 이동)
    private final PaymentGateway paymentGateway;
    // [LEGACY_CHANGES L-F2] OrderClient/NotificationClient 대신 이벤트 발행
    private final PaymentEventPublisher paymentEventPublisher;

    public PaymentService(PaymentRepository paymentRepository, 
                          AuditClient auditClient,
                          ObjectMapper objectMapper,
                          PaymentGateway paymentGateway,
                          PaymentEventPublisher paymentEventPublisher) {
        this.paymentRepository = paymentRepository;
        this.auditClient = auditClient;
        this.objectMapper = objectMapper;
        this.paymentGateway = paymentGateway;
        this.paymentEventPublisher = paymentEventPublisher;
    }

    @Transactional
    public PaymentResponse processPayment(PaymentRequest request) {
        try {
            int amountInPaise = request.getAmount().multiply(new BigDecimal(100)).intValue();

            JSONObject orderRequest = new JSONObject();
            orderRequest.put("amount", amountInPaise);
            orderRequest.put("currency", "INR");
            orderRequest.put("receipt", "order_rcptid_" + request.getOrderId());

            // [LEGACY_CHANGES L-F1] client.orders.create(orderRequest).get("id") -> PaymentGateway
            String razorpayOrderId = paymentGateway.createOrder(orderRequest);

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

        // [LEGACY_CHANGES L-F2] 동기 Feign 핸드셰이크(PUT /orders/{id}/status) + 감사 로그 + 알림 발송을
        // PaymentCompleted 이벤트 발행으로 대체했다. 세 가지 후속 처리는 Order consumer가 같은 순서로 한다.
        // 감사 로그 본문(dataBefore/dataAfter)은 여기서 직렬화해 이벤트에 싣는다(원본과 같은 ObjectMapper).
        paymentEventPublisher.publishPaymentCompleted(updatedPayment, dataBefore);
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