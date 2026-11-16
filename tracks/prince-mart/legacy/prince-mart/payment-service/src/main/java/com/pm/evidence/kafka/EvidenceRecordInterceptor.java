package com.pm.evidence.kafka;

import com.pm.evidence.Baggage;
import com.pm.evidence.EvidenceContext;
import com.pm.evidence.EvidenceRecorder;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.listener.RecordInterceptor;

import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * [LEGACY_CHANGES L-I2] Kafka 레코드 처리 1건의 Evidence(kind=consume).
 *
 * <p>replayRequestId는 레코드 헤더의 baggage(OTel agent가 발행 쪽에서 실음, legacy-decision-log L9)에서 읽는다.
 * 처리 중 SQL·Feign 호출·예외가 같은 스레드에서 쌓인다. k6는 이 Evidence의 도착까지 기다려 Kafka 비동기 처리를 마친 뒤
 * 다음 요청을 보낸다.
 */
final class EvidenceRecordInterceptor implements RecordInterceptor<Object, Object> {

    private final EvidenceRecorder recorder;

    EvidenceRecordInterceptor(EvidenceRecorder recorder) {
        this.recorder = recorder;
    }

    @Override
    public ConsumerRecord<Object, Object> intercept(ConsumerRecord<Object, Object> record, Consumer<Object, Object> consumer) {
        Map<String, String> baggage = Baggage.parse(header(record, "baggage"));
        String replayId = baggage.get("replayRequestId");
        if (replayId != null) {
            EvidenceContext.start("consume", replayId, baggage.get("runId"), baggage.get("sessionId"));
        }
        return record;
    }

    @Override
    public void failure(ConsumerRecord<Object, Object> record, Exception exception, Consumer<Object, Object> consumer) {
        EvidenceContext.Record r = EvidenceContext.current();
        if (r != null) r.error(exception.getCause() != null ? exception.getCause() : exception);
    }

    @Override
    public void afterRecord(ConsumerRecord<Object, Object> record, Consumer<Object, Object> consumer) {
        EvidenceContext.Record r = EvidenceContext.current();
        if (r == null) return;
        EvidenceContext.clear();

        Map<String, String> headers = new LinkedHashMap<>();
        for (Header h : record.headers()) {
            headers.put(h.key(), h.value() == null ? null : new String(h.value(), StandardCharsets.UTF_8));
        }
        Map<String, Object> message = new LinkedHashMap<>();
        message.put("topic", record.topic());
        message.put("partition", record.partition());
        message.put("offset", record.offset());
        message.put("key", record.key() == null ? null : record.key().toString());
        message.put("value", record.value() == null ? null : record.value().toString());
        message.put("headers", headers);

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("message", message);
        recorder.finish(r, body);
    }

    private static String header(ConsumerRecord<?, ?> record, String key) {
        Header h = record.headers().lastHeader(key);
        return h == null || h.value() == null ? null : new String(h.value(), StandardCharsets.UTF_8);
    }
}
