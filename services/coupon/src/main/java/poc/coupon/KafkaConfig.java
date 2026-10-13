package poc.coupon;

import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

/**
 * Phase 3.3: 소비 실패 처리 — 재시도 없음(FixedBackOff(0, 0)), 실패 레코드는 {@code order.paid.dlq}(같은 partition)로.
 * DLQ 발행은 그 소비 홉의 Evidence({@code events.published})에 남는다. Boot가 이 CommonErrorHandler를 리스너 컨테이너에 붙인다.
 */
@Configuration
public class KafkaConfig {

    static final String DLQ_TOPIC = "order.paid.dlq";

    @Bean
    public DefaultErrorHandler kafkaErrorHandler(KafkaTemplate<Object, Object> kafkaTemplate) {
        DeadLetterPublishingRecoverer recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate,
                (record, e) -> new TopicPartition(DLQ_TOPIC, record.partition()));
        return new DefaultErrorHandler(recoverer, new FixedBackOff(0L, 0L));
    }
}
