package com.pm.evidence.kafka;

import com.pm.evidence.EvidenceRecorder;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.listener.RecordInterceptor;

/**
 * [LEGACY_CHANGES L-I2] Kafka consumer 처리 1건도 Evidence 1건(kind=consume)으로 남긴다.
 * Boot의 Kafka 자동 구성이 RecordInterceptor 빈을 listener container에 붙인다(Boot 3.4, 4.0 모두).
 * 발행 이벤트는 kafka-clients ProducerInterceptor(EvidenceProducerInterceptor)로 잡는다(설정: interceptor.classes).
 */
@AutoConfiguration(afterName = "com.pm.evidence.EvidenceAutoConfiguration")
@ConditionalOnClass(name = "org.springframework.kafka.listener.RecordInterceptor")
@ConditionalOnProperty(name = "evidence.enabled", havingValue = "true")
public class EvidenceKafkaAutoConfiguration {

    @Bean
    @ConditionalOnBean(EvidenceRecorder.class)
    RecordInterceptor<Object, Object> evidenceRecordInterceptor(EvidenceRecorder recorder) {
        return new EvidenceRecordInterceptor(recorder);
    }
}
