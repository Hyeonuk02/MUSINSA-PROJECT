package poc.order;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import tools.jackson.databind.json.JsonMapper;

import java.util.concurrent.TimeUnit;

/**
 * Phase 3.3: {@link OrderPaid}를 커밋 뒤에 Kafka {@code order.paid}로 발행한다.
 *
 * <p>{@code @TransactionalEventListener(AFTER_COMMIT)} — 롤백된 결제는 발행하지 않는다. 발행은 동기({@code send().get(5s)}).
 * 발행 실패(예외·타임아웃)는 요청 결과에 영향을 주지 않는다 — 로그만 남기고 응답은 그대로다(Outbox는 범위 밖, phase3-plan 3절).
 * key = orderKey, 페이로드 JSON {@code {orderKey, amount, couponKey}}(쿠폰 없으면 couponKey null).
 */
@Component
public class OrderEventPublisher {

    static final String TOPIC = "order.paid";

    private static final Logger log = LoggerFactory.getLogger(OrderEventPublisher.class);

    private final KafkaTemplate<String, String> kafkaTemplate;
    private final JsonMapper jsonMapper;

    public OrderEventPublisher(KafkaTemplate<String, String> kafkaTemplate, JsonMapper jsonMapper) {
        this.kafkaTemplate = kafkaTemplate;
        this.jsonMapper = jsonMapper;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderPaid(OrderPaid event) {
        String payload = jsonMapper.writeValueAsString(event);
        try {
            kafkaTemplate.send(TOPIC, event.orderKey(), payload).get(5, TimeUnit.SECONDS);
        } catch (Exception e) {
            if (e instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            log.warn("order.paid publish failed orderKey={}: {}", event.orderKey(), e.toString());
        }
    }
}
