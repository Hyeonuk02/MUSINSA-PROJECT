package com.pm.evidence;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * [LEGACY_CHANGES L-I2] Evidence JSON v0 봉투를 만들고 전송기에 넘긴다(docs/evidence-schema-v0.md).
 * HTTP 필터와 Kafka consumer 인터셉터가 같은 봉투를 쓴다.
 */
public final class EvidenceRecorder {

    public static final String SCHEMA = "evidence/v0";

    private final EvidenceSender sender;
    private final String stack;
    private final String service;
    private final String fixedClock;

    EvidenceRecorder(EvidenceSender sender, String stack, String service, String fixedClock) {
        this.sender = sender;
        this.stack = stack;
        this.service = service;
        this.fixedClock = fixedClock;
    }

    /** kind별 본문(request/response 또는 message)을 받아 공통 필드와 합쳐 보낸다. */
    public void finish(EvidenceContext.Record r, Map<String, Object> body) {
        long completedAt = System.currentTimeMillis();
        long completedAtNano = System.nanoTime();

        Map<String, Object> e = new LinkedHashMap<>();
        e.put("schema", SCHEMA);
        e.put("runId", r.runId);
        e.put("replayRequestId", r.replayRequestId);
        e.put("stack", stack);
        e.put("service", service);
        e.put("kind", r.kind);
        e.put("seq", r.seq);
        e.putAll(body);
        e.put("error", r.error());
        e.put("dbAccess", r.dbAccess());
        e.put("outbound", r.outbound);
        e.put("events", r.events);

        Map<String, Object> timing = new LinkedHashMap<>();
        timing.put("arrivedAt", r.arrivedAt);
        timing.put("completedAt", completedAt);
        timing.put("arrivedAtNano", r.arrivedAtNano);
        timing.put("completedAtNano", completedAtNano);
        // 참고 지표(비교 대상 아님). Store POST는 이 시간에 포함되지 않는다(전송은 응답 후 별도 스레드).
        timing.put("durationMs", (completedAtNano - r.arrivedAtNano) / 1_000_000.0);
        e.put("timing", timing);

        Map<String, Object> runContext = new LinkedHashMap<>();
        runContext.put("runId", r.runId);
        runContext.put("sessionId", r.sessionId);
        runContext.put("fixedClock", fixedClock);
        e.put("runContext", runContext);

        sender.submit(Json.write(e));
    }
}
