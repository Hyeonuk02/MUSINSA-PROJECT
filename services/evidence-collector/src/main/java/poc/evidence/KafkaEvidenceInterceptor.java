package poc.evidence;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.listener.RecordInterceptor;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Kafka 소비 홉의 Evidence (Phase 3.3). origin=kafka, request·response는 null, event = 소비한 레코드.
 *
 * <p>레코드 헤더의 재생 헤더 4개(X-Replay-*·X-Replay-Hop-Path)로 consumer 스레드에 ReplayContext를 연다. 없으면 Evidence 없음.
 * 그 사이 SQL·트랜잭션·callTree·발행(DLQ 포함)이 이 홉에 쌓인다. traceparent 등 다른 헤더는 Evidence에 넣지 않는다.
 *
 * <p>확정 시점은 success/failure가 아니라 그 뒤 — 에러 핸들러(DefaultErrorHandler + DeadLetterPublishingRecoverer)의
 * DLQ 발행까지 이 홉에 들어가야 하기 때문이다. 다음 레코드의 intercept 또는 clearThreadState(poll 처리 끝) 중 먼저 오는 쪽.
 * consumeOutcome은 success → ok, failure → failed.
 */
class KafkaEvidenceInterceptor implements RecordInterceptor<Object, Object> {

    private static final Logger log = LoggerFactory.getLogger(KafkaEvidenceInterceptor.class);

    private final EvidenceWriter writer;
    private final ThreadLocal<Pending> pending = new ThreadLocal<>();

    KafkaEvidenceInterceptor(EvidenceWriter writer) {
        this.writer = writer;
    }

    private static final class Pending {
        final ReplayContext context;
        final EvidenceWriter.Ids ids;
        final Map<String, Object> event;
        final Instant arrivedAt;
        final long arrivedNano;
        String outcome = "failed";  // success()가 오지 않으면 실패로 본다
        Exception failure;

        Pending(ReplayContext context, EvidenceWriter.Ids ids, Map<String, Object> event) {
            this.context = context;
            this.ids = ids;
            this.event = event;
            this.arrivedAt = Instant.now();
            this.arrivedNano = System.nanoTime();
        }
    }

    @Override
    public ConsumerRecord<Object, Object> intercept(ConsumerRecord<Object, Object> record, Consumer<Object, Object> consumer) {
        finish();
        String replayRequestId = header(record, EvidenceFilter.REPLAY_REQUEST_ID_HEADER);
        String runId = header(record, EvidenceFilter.RUN_ID_HEADER);
        String sessionId = header(record, EvidenceFilter.SESSION_ID_HEADER);
        String hopPath = header(record, EvidenceFilter.HOP_PATH_HEADER);
        if (replayRequestId == null || runId == null || sessionId == null || hopPath == null) {
            log.info("EVIDENCE_SKIP no replay headers: kafka {}-{}@{}", record.topic(), record.partition(), record.offset());
            return record;
        }
        byte[] payload = EvidenceProducerInterceptor.bytes(record.value());
        Map<String, Object> event = new LinkedHashMap<>();
        event.put("topic", record.topic());
        event.put("key", record.key() == null ? null : String.valueOf(record.key()));
        event.put("payloadHash", EvidenceWriter.sha256(payload));
        event.put("payload", EvidenceWriter.bodyOrNull(payload));
        ReplayContext context = ReplayContext.open(replayRequestId, runId, sessionId, hopPath);
        pending.set(new Pending(context, new EvidenceWriter.Ids(runId, replayRequestId, sessionId, hopPath), event));
        return record;
    }

    @Override
    public void success(ConsumerRecord<Object, Object> record, Consumer<Object, Object> consumer) {
        Pending p = pending.get();
        if (p != null) {
            p.outcome = "ok";
        }
    }

    @Override
    public void failure(ConsumerRecord<Object, Object> record, Exception exception, Consumer<Object, Object> consumer) {
        Pending p = pending.get();
        if (p != null) {
            p.outcome = "failed";
            p.failure = exception;
        }
    }

    @Override
    public void clearThreadState(Consumer<?, ?> consumer) {
        finish();
    }

    /** 열린 소비 홉을 닫고 Evidence를 낸다. */
    private void finish() {
        Pending p = pending.get();
        if (p == null) {
            return;
        }
        pending.remove();
        ReplayContext.Captured captured = p.context.close();
        Map<String, Object> error = p.failure == null ? null : writer.describe(p.failure);
        writer.emit(p.ids, "kafka", null, null, p.event, p.outcome, captured, error,
                p.arrivedAt, p.arrivedNano, Instant.now(), System.nanoTime());
    }

    private static String header(ConsumerRecord<?, ?> record, String name) {
        Header h = record.headers().lastHeader(name);
        if (h == null || h.value() == null || h.value().length == 0) {
            return null;
        }
        return new String(h.value(), StandardCharsets.UTF_8);
    }
}
