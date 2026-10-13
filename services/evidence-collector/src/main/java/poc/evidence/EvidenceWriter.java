package poc.evidence;

import tools.jackson.databind.json.JsonMapper;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Evidence JSON v1 조립과 전송 — HTTP 홉(EvidenceFilter)과 Kafka 소비 홉(KafkaEvidenceInterceptor)이 같이 쓴다.
 * 필드 순서를 한 곳에서 고정한다. JSON은 패키지 안 고정 설정 매퍼(앱의 매퍼 빈을 쓰지 않는다).
 */
final class EvidenceWriter {

    static final int MAX_BODY_BYTES = 32 * 1024;

    private final EvidenceSender sender;
    private final String stack;
    private final String service;
    private final String version;
    private final List<String> appPackages;
    private final JsonMapper jsonMapper = JsonMapper.builder().build();

    EvidenceWriter(EvidenceSender sender, String stack, String service, String version, List<String> appPackages) {
        this.sender = sender;
        this.stack = stack;
        this.service = service;
        this.version = version;
        this.appPackages = List.copyOf(appPackages);
    }

    record Ids(String runId, String replayRequestId, String sessionId, String hopPath) {
    }

    /**
     * @param consumeOutcome origin=kafka일 때 ok|failed, http면 null(필드 생략)
     */
    void emit(Ids ids, String origin, Map<String, Object> request, Map<String, Object> response, Map<String, Object> event,
              String consumeOutcome, ReplayContext.Captured captured, Map<String, Object> error,
              Instant arrivedAt, long arrivedNano, Instant completedAt, long completedNano) {
        Map<String, Object> timing = new LinkedHashMap<>();
        timing.put("arrivedAt", arrivedAt.toString());
        timing.put("completedAt", completedAt.toString());
        timing.put("arrivedNano", arrivedNano);
        timing.put("completedNano", completedNano);

        Map<String, Object> evidence = new LinkedHashMap<>();
        evidence.put("schemaVersion", "v1");
        evidence.put("runId", ids.runId());
        evidence.put("replayRequestId", ids.replayRequestId());
        evidence.put("hopPath", ids.hopPath());
        evidence.put("sessionId", ids.sessionId());
        evidence.put("stack", stack);
        evidence.put("service", service);
        evidence.put("origin", origin);
        evidence.put("version", version);
        evidence.put("request", request);
        evidence.put("response", response);
        evidence.put("event", event);
        if (consumeOutcome != null) {
            evidence.put("consumeOutcome", consumeOutcome);
        }
        evidence.put("dbAccess", captured.dbAccess());
        evidence.put("externalCalls", captured.externalCalls());
        evidence.put("events", captured.events());
        evidence.put("transactions", captured.transactions());
        evidence.put("callTree", captured.callTree());
        evidence.put("error", error);
        evidence.put("timing", timing);
        evidence.put("capturedAt", Instant.now().toString());

        sender.enqueue(ids.runId(), ids.replayRequestId(), ids.hopPath(), stack, jsonMapper.writeValueAsBytes(evidence));
    }

    /** 예외의 원인 타입과 발생 위치. 래핑 예외는 원인까지 벗긴다. where = 앱 패키지 안 첫 스택 프레임의 class.method. */
    Map<String, Object> describe(Throwable failure) {
        Throwable root = failure;
        while (root.getCause() != null && root.getCause() != root && isWrapper(root)) {
            root = root.getCause();
        }
        String where = null;
        for (StackTraceElement frame : root.getStackTrace()) {
            String cls = frame.getClassName();
            if (appPackages.stream().anyMatch(p -> cls.startsWith(p + "."))) {
                where = cls + "." + frame.getMethodName();
                break;
            }
        }
        if (where == null && root.getStackTrace().length > 0) {
            StackTraceElement top = root.getStackTrace()[0];
            where = top.getClassName() + "." + top.getMethodName();
        }
        Map<String, Object> error = new LinkedHashMap<>();
        error.put("type", root.getClass().getName());
        error.put("where", where);
        return error;
    }

    /** 서블릿·Kafka 리스너 래핑 예외(원인을 감싸기만 하는 것). */
    private static boolean isWrapper(Throwable t) {
        String name = t.getClass().getName();
        return name.equals("jakarta.servlet.ServletException")
                || name.equals("org.springframework.kafka.listener.ListenerExecutionFailedException")
                || name.equals("org.springframework.messaging.MessagingException")
                || name.equals("org.springframework.messaging.handler.invocation.MethodArgumentResolutionException");
    }

    static String sha256(byte[] bytes) {
        try {
            return "sha256:" + HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    static String bodyOrNull(byte[] bytes) {
        return bytes.length <= MAX_BODY_BYTES ? new String(bytes, java.nio.charset.StandardCharsets.UTF_8) : null;
    }
}
