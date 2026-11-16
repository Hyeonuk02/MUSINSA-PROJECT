package com.pm.payment.event;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.pm.payment.entity.Payment;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;

/**
 * [LEGACY_CHANGES L-F2] PaymentCompleted 이벤트 발행.
 *
 * <p>upstream의 {@code completePaymentManually}는 Order에 동기 Feign으로 상태 변경을 요청하고, 그 응답(userId, 이메일,
 * 이름)으로 감사 로그와 알림을 보냈다. 이 셋을 Order consumer가 하도록 이벤트 하나로 바꿨다.
 *
 * <ul>
 *   <li>key = orderId, value = JSON 문자열(StringSerializer). Payment(Boot 3, Jackson 2)와 Order(Boot 4)의
 *       JSON 타입 헤더 차이를 피하려고 문자열로 보낸다.</li>
 *   <li>{@code amount}는 원래 알림에 넣던 {@code payment.getAmount().toString()} 그대로다.</li>
 *   <li>{@code audit}은 원래 Payment가 보내던 감사 로그의 dataBefore/dataAfter 문자열이다(이 서비스의 ObjectMapper로
 *       직렬화). 직렬화에 실패하면 원본처럼 감사 로그를 건너뛰도록 null로 보낸다.</li>
 *   <li>발행은 동기(완료까지 대기)다. 실패하면 예외가 나서 결제 상태 변경 트랜잭션도 롤백된다.</li>
 * </ul>
 */
@Component
public class PaymentEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;
    private final ObjectMapper objectMapper;
    private final String topic;

    public PaymentEventPublisher(KafkaTemplate<String, String> kafkaTemplate,
                                 ObjectMapper objectMapper,
                                 @Value("${app.kafka.payment-events-topic}") String topic) {
        this.kafkaTemplate = kafkaTemplate;
        this.objectMapper = objectMapper;
        this.topic = topic;
    }

    public void publishPaymentCompleted(Payment payment, String auditDataBefore) {
        Map<String, Object> audit = null;
        try {
            audit = new LinkedHashMap<>();
            audit.put("dataBefore", auditDataBefore);
            audit.put("dataAfter", objectMapper.writeValueAsString(payment));
        } catch (Exception e) {
            audit = null;
            System.err.println("Audit logging failed in Payment Service: " + e.getMessage());
        }

        Map<String, Object> event = new LinkedHashMap<>();
        event.put("eventType", "PaymentCompleted");
        event.put("orderId", payment.getOrderId());
        event.put("transactionId", payment.getTransactionId());
        event.put("amount", payment.getAmount().toString());
        event.put("currency", payment.getCurrency());
        event.put("audit", audit);

        try {
            String value = objectMapper.writeValueAsString(event);
            kafkaTemplate.send(topic, payment.getOrderId().toString(), value).get(10, TimeUnit.SECONDS);
        } catch (Exception e) {
            throw new IllegalStateException("PaymentCompleted publish failed: " + e.getMessage(), e);
        }
    }
}
