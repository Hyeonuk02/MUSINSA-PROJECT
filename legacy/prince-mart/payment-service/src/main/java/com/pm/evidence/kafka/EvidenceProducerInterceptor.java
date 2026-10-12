package com.pm.evidence.kafka;

import com.pm.evidence.EvidenceContext;
import org.apache.kafka.clients.producer.ProducerInterceptor;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.apache.kafka.common.header.Header;

import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * [LEGACY_CHANGES L-I2] 발행 이벤트: 요청 처리 중 보낸 Kafka 레코드(토픽·key·value·헤더)를 현재 요청의 Evidence에 기록한다.
 *
 * <p>kafka-clients가 send()를 부른 스레드(=요청 스레드)에서 onSend를 호출하므로 스레드 로컬 Evidence에 붙일 수 있다.
 * 레코드는 바꾸지 않는다. 설정: {@code spring.kafka.producer.properties[interceptor.classes]}.
 */
public class EvidenceProducerInterceptor implements ProducerInterceptor<Object, Object> {

    @Override
    public ProducerRecord<Object, Object> onSend(ProducerRecord<Object, Object> record) {
        EvidenceContext.Record r = EvidenceContext.current();
        if (r != null) {
            Map<String, String> headers = new LinkedHashMap<>();
            for (Header h : record.headers()) {
                headers.put(h.key(), h.value() == null ? null : new String(h.value(), StandardCharsets.UTF_8));
            }
            r.event(record.topic(),
                    record.key() == null ? null : record.key().toString(),
                    record.value() == null ? null : record.value().toString(),
                    headers);
        }
        return record;
    }

    @Override
    public void onAcknowledgement(RecordMetadata metadata, Exception exception) {
    }

    @Override
    public void close() {
    }

    @Override
    public void configure(Map<String, ?> configs) {
    }
}
