package com.pm.order.event;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.pm.order.client.AuditClient;
import com.pm.order.client.NotificationClient;
import com.pm.order.dto.AuditLogRequest;
import com.pm.order.dto.NotificationRequest;
import com.pm.order.entity.Order;
import com.pm.order.service.OrderService;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

/**
 * [LEGACY_CHANGES L-F2] PaymentCompleted 이벤트 소비.
 *
 * <p>upstream에서 payment-service {@code completePaymentManually}가 동기로 하던 후속 처리를 같은 순서로 한다.
 * <ol>
 *   <li>주문 상태 변경 — 기존 {@code PUT /orders/{id}/status}가 부르던 {@code OrderService.updateStatus(PAID, CONFIRMED)}
 *       그대로(이력 changedBy=PAYMENT_SERVICE, ORDER_STATUS_UPDATE 감사 로그, 배송 요청 포함)</li>
 *   <li>감사 로그 PAYMENT_COMPLETED_SUCCESS — 본문은 payment-service가 직렬화해 이벤트에 실은 문자열이고,
 *       serviceName도 원본과 같은 "PAYMENT-SERVICE"다(호출 주체만 order-service로 바뀜)</li>
 *   <li>주문 확인 알림 — 실패하면 POST_PAYMENT_NOTIFICATION_FAILED 감사 로그</li>
 * </ol>
 * 예외는 재시도하지 않는다(KafkaConsumerConfig). 재전달되면 이력·감사 로그·배송 요청이 중복되기 때문이다.
 */
@Component
public class PaymentCompletedListener {

    private final OrderService orderService;
    private final AuditClient auditClient;
    private final NotificationClient notificationClient;
    private final ObjectMapper objectMapper;

    public PaymentCompletedListener(OrderService orderService,
                                    AuditClient auditClient,
                                    NotificationClient notificationClient,
                                    ObjectMapper objectMapper) {
        this.orderService = orderService;
        this.auditClient = auditClient;
        this.notificationClient = notificationClient;
        this.objectMapper = objectMapper;
    }

    @KafkaListener(topics = "${app.kafka.payment-events-topic}", groupId = "${app.kafka.consumer-group}")
    public void onPaymentCompleted(String value) throws Exception {
        JsonNode event = objectMapper.readTree(value);
        Long orderId = event.get("orderId").asLong();

        // 1. 기존 핸드셰이크가 하던 상태 변경
        Order orderInfo = orderService.updateStatus(orderId, "PAID", "CONFIRMED");
        System.out.println("Handshake successful for Order: " + orderId);

        // 2. 결제 완료 감사 로그 (payment-service가 보내던 것)
        JsonNode audit = event.get("audit");
        if (audit != null && !audit.isNull()) {
            sendPaymentAuditLog(orderInfo.getUserId(), "PAYMENT_COMPLETED_SUCCESS",
                    audit.get("dataBefore").asText(), audit.get("dataAfter").asText());
        }

        // 3. 알림
        NotificationRequest emailReq = new NotificationRequest();
        emailReq.setUserId(orderInfo.getUserId());
        emailReq.setRecipient(orderInfo.getUserEmail());
        emailReq.setSubject("Order Confirmed - Prince Mart");
        emailReq.setCustomerName(orderInfo.getCustomerName());
        emailReq.setOrderId(orderId.toString());
        emailReq.setAmount(event.get("amount").asText());

        try {
            notificationClient.sendConfirmation(emailReq);
        } catch (Exception e) {
            sendPaymentAuditLog(orderInfo.getUserId(), "POST_PAYMENT_NOTIFICATION_FAILED", null, e.getMessage());
            System.err.println("Non-critical Error: Failed to trigger notification - " + e.getMessage());
        }
    }

    // payment-service의 sendAuditLog와 같은 모양(serviceName "PAYMENT-SERVICE", 실패는 로그만)
    private void sendPaymentAuditLog(Long userId, String action, String dataBefore, String dataAfter) {
        try {
            auditClient.createLog(new AuditLogRequest("PAYMENT-SERVICE", action, userId, dataBefore, dataAfter));
        } catch (Exception e) {
            System.err.println("Audit logging failed in Payment Service: " + e.getMessage());
        }
    }
}
