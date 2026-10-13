package poc.evidence;

import org.apache.kafka.clients.producer.ProducerInterceptor;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.apache.kafka.common.header.Headers;

import java.nio.charset.StandardCharsets;
import java.util.Map;

/**
 * Kafka 발행 — 재생 헤더 전파 + {@code events.published} 기록 (Phase 3.3, D16).
 *
 * <p>{@code onSend}는 {@code KafkaTemplate.send()}를 부른 스레드에서 돈다 — ReplayContext가 있으면:
 * 자식 hopPath({@code <hopPath>.e<n>})를 정하고 재생 헤더 4개를 레코드 헤더로 붙이며(이미 있으면 교체 — DLQ 재발행처럼
 * 원본 헤더를 복사한 레코드도 이 홉의 자식이 된다), 타임라인 seq와 함께 발행을 기록한다.
 * {@code onAcknowledgement}는 Producer I/O 스레드라 ReplayContext가 없으므로 쓰지 않는다 — ack는 Evidence를 닫을 때
 * 호출 스레드에서 send()가 돌려준 future 상태로 정한다(KafkaTemplateSendAdvice).
 *
 * <p>Kafka가 클래스 이름으로 만든다(producer 설정 {@code interceptor.classes}) — public, 인자 없는 생성자.
 */
public class EvidenceProducerInterceptor implements ProducerInterceptor<Object, Object> {

    @Override
    public ProducerRecord<Object, Object> onSend(ProducerRecord<Object, Object> record) {
        ReplayContext context = ReplayContext.current().orElse(null);
        if (context == null) {
            return record;
        }
        String childHop = context.nextEventChildHop();
        Headers headers = record.headers();
        put(headers, EvidenceFilter.REPLAY_REQUEST_ID_HEADER, context.replayRequestId());
        put(headers, EvidenceFilter.RUN_ID_HEADER, context.runId());
        put(headers, EvidenceFilter.SESSION_ID_HEADER, context.sessionId());
        put(headers, EvidenceFilter.HOP_PATH_HEADER, childHop);
        context.recordPublish(record.topic(), record.key() == null ? null : String.valueOf(record.key()),
                bytes(record.value()), childHop);
        return record;
    }

    private static void put(Headers headers, String name, String value) {
        headers.remove(name);
        headers.add(name, value.getBytes(StandardCharsets.UTF_8));
    }

    static byte[] bytes(Object value) {
        if (value == null) {
            return new byte[0];
        }
        if (value instanceof byte[] b) {
            return b;
        }
        return String.valueOf(value).getBytes(StandardCharsets.UTF_8);
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
