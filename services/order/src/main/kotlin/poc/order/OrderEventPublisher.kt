package poc.order

import org.slf4j.LoggerFactory
import org.springframework.kafka.core.KafkaTemplate
import org.springframework.stereotype.Component
import org.springframework.context.event.EventListener
import tools.jackson.databind.json.JsonMapper
import java.util.concurrent.TimeUnit

/**
 * Phase 3.3: [OrderPaid]를 커밋 뒤에 Kafka `order.paid`로 발행한다.
 *
 * `@TransactionalEventListener(AFTER_COMMIT)` — 롤백된 결제는 발행하지 않는다. 발행은 동기(`send().get(5s)`).
 * 발행 실패(예외·타임아웃)는 요청 결과에 영향을 주지 않는다 — 로그만 남기고 응답은 그대로다(Outbox는 범위 밖, phase3-plan 3절).
 * key = orderKey, 페이로드 JSON `{orderKey, amount, couponKey}`(쿠폰 없으면 couponKey null).
 *
 * Phase 3.5-v1.3: Java → Kotlin 전환.
 */
@Component
class OrderEventPublisher(
    private val kafkaTemplate: KafkaTemplate<String, String>,
    private val jsonMapper: JsonMapper,
) {

    @EventListener
    fun onOrderPaid(event: OrderPaid) {
        val payload = jsonMapper.writeValueAsString(event)
        try {
            kafkaTemplate.send(TOPIC, event.orderKey, payload).get(5, TimeUnit.SECONDS)
        } catch (e: Exception) {
            if (e is InterruptedException) {
                Thread.currentThread().interrupt()
            }
            log.warn("order.paid publish failed orderKey={}: {}", event.orderKey, e.toString())
        }
    }

    companion object {
        const val TOPIC = "order.paid"
        private val log = LoggerFactory.getLogger(OrderEventPublisher::class.java)
    }
}
