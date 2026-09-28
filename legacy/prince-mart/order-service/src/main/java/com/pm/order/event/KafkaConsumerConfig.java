package com.pm.order.event;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.listener.CommonErrorHandler;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

/**
 * [LEGACY_CHANGES L-F2] consumer 오류 처리: 재시도 없음.
 *
 * <p>Spring Kafka 기본값은 실패한 레코드를 최대 9번 다시 전달한다. 상태 변경 뒤에 실패하면 이력·감사 로그·
 * 배송 요청이 중복되므로 재시도하지 않고 로그만 남긴 뒤 다음 레코드로 넘어간다(offset은 커밋된다).
 */
@Configuration
public class KafkaConsumerConfig {

    @Bean
    public CommonErrorHandler kafkaErrorHandler() {
        return new DefaultErrorHandler(new FixedBackOff(0L, 0L));
    }
}
