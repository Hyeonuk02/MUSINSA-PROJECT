package com.pm.evidence;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

/**
 * [LEGACY_CHANGES L-I2] 처리 중인 요청(HTTP 1건 또는 Kafka 레코드 1건)의 Evidence를 모으는 스레드 로컬 저장소.
 *
 * <p>요청 처리는 한 스레드에서 끝난다(Feign 호출, JPA, Kafka 발행 모두 동기). 그래서 필터/consumer 인터셉터가 시작한
 * 기록에 SQL(StatementInspector), 나가는 호출(Feign Capability), 발행 이벤트(ProducerInterceptor), 예외(HandlerExceptionResolver)가
 * 같은 스레드에서 쌓인다.
 */
public final class EvidenceContext {

    /** 서비스 인스턴스 안에서 Evidence 순번. 리셋 때 앱을 재시작하므로 run마다 1부터 시작한다(legacy-decision-log L3). */
    private static final AtomicLong SEQUENCE = new AtomicLong();
    private static final ThreadLocal<Record> CURRENT = new ThreadLocal<>();

    private EvidenceContext() {
    }

    public static Record start(String kind, String replayRequestId, String runId, String sessionId) {
        Record r = new Record(kind, replayRequestId, runId, sessionId, SEQUENCE.incrementAndGet());
        CURRENT.set(r);
        return r;
    }

    public static Record current() {
        return CURRENT.get();
    }

    public static void clear() {
        CURRENT.remove();
    }

    public static final class Record {
        public final String kind;
        public final String replayRequestId;
        public final String runId;
        public final String sessionId;
        public final long seq;
        public final long arrivedAt = System.currentTimeMillis();
        public final long arrivedAtNano = System.nanoTime();
        final List<String> statements = new ArrayList<>();
        final List<Map<String, Object>> outbound = new ArrayList<>();
        final List<Map<String, Object>> events = new ArrayList<>();
        String errorClass;
        String errorMessage;

        Record(String kind, String replayRequestId, String runId, String sessionId, long seq) {
            this.kind = kind;
            this.replayRequestId = replayRequestId;
            this.runId = runId;
            this.sessionId = sessionId;
            this.seq = seq;
        }

        public void sql(String sql) {
            statements.add(sql);
        }

        public void outbound(String method, String url, Integer status, String error, long durationMs) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("order", outbound.size() + 1);
            m.put("method", method);
            m.put("url", url);
            m.put("status", status);
            m.put("error", error);
            m.put("durationMs", durationMs);
            outbound.add(m);
        }

        public void event(String topic, String key, String value, Map<String, String> headers) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("order", events.size() + 1);
            m.put("topic", topic);
            m.put("key", key);
            m.put("value", value);
            m.put("headers", headers);
            events.add(m);
        }

        /** 같은 요청에서 먼저 기록된 예외를 유지한다(핸들러 예외 -> 이후 래핑 예외 순서). */
        public void error(Throwable t) {
            if (errorClass == null && t != null) {
                errorClass = t.getClass().getName();
                errorMessage = t.getMessage();
            }
        }

        /** 비교 키: (동작, 테이블, 횟수). 처음 나온 순서를 유지한다. 원문은 statements에 참고용으로 남긴다. */
        Map<String, Object> dbAccess() {
            Map<String, Integer> counts = new LinkedHashMap<>();
            for (String s : statements) {
                counts.merge(operation(s) + " " + table(s), 1, Integer::sum);
            }
            List<Map<String, Object>> summary = new ArrayList<>();
            counts.forEach((k, n) -> {
                String[] p = k.split(" ", 2);
                Map<String, Object> m = new LinkedHashMap<>();
                m.put("op", p[0]);
                m.put("table", p[1]);
                m.put("count", n);
                summary.add(m);
            });
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("total", statements.size());
            m.put("summary", summary);
            m.put("statements", statements);
            return m;
        }

        Map<String, Object> error() {
            if (errorClass == null) return null;
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("class", errorClass);
            m.put("message", errorMessage);
            return m;
        }
    }

    static String operation(String sql) {
        String s = sql.stripLeading();
        int sp = s.indexOf(' ');
        return (sp < 0 ? s : s.substring(0, sp)).toUpperCase(Locale.ROOT);
    }

    /** 주 테이블: insert into X / update X / delete from X / select ... from X. */
    static String table(String sql) {
        String s = sql.toLowerCase(Locale.ROOT).replaceAll("\\s+", " ").trim();
        String marker = switch (operation(sql)) {
            case "INSERT" -> "insert into ";
            case "UPDATE" -> "update ";
            case "DELETE" -> "delete from ";
            default -> " from ";
        };
        int i = s.indexOf(marker);
        if (i < 0) return "?";
        String rest = s.substring(i + marker.length());
        int end = 0;
        while (end < rest.length() && (Character.isLetterOrDigit(rest.charAt(end)) || rest.charAt(end) == '_' || rest.charAt(end) == '.')) {
            end++;
        }
        return end == 0 ? "?" : rest.substring(0, end);
    }
}
