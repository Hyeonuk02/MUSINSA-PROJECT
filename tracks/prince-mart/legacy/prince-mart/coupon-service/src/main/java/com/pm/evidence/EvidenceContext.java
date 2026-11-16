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
 * 기록에 SQL(StatementInspector), 나가는 호출(Feign Capability), 발행 이벤트(ProducerInterceptor), 트랜잭션 경계
 * (TransactionExecutionListener), 예외(HandlerExceptionResolver)가 같은 스레드에서 쌓인다.
 *
 * <p>[L-I3] SQL·호출·이벤트·트랜잭션 경계는 요청 하나 안에서 **하나의 카운터로 seq**를 받는다(타임라인).
 * "커밋 전에 발행했는가"를 publish.seq &lt; COMMIT_BEGIN.seq로 판정할 수 있다(hyeonuk-dev findings O9·O11과 같은 방식).
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
        private int timeline;   // 요청 안 타임라인 seq (1부터)
        final List<Map<String, Object>> statements = new ArrayList<>();
        final List<Map<String, Object>> transactions = new ArrayList<>();
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
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("seq", ++timeline);
            m.put("sql", sql);
            statements.add(m);
        }

        /** 새로 시작된 트랜잭션의 경계. phase: COMMIT_BEGIN(커밋 직전) / COMPLETED(outcome: COMMITTED·ROLLED_BACK·FAILED). */
        public void transaction(String name, String phase, String outcome) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("seq", ++timeline);
            m.put("name", name);
            m.put("phase", phase);
            m.put("outcome", outcome);
            transactions.add(m);
        }

        /** 시작 시점에 타임라인 seq를 잡아 둔다(호출처럼 시작과 끝 사이에 다른 기록이 끼일 수 있는 것). */
        public int nextSeq() {
            return ++timeline;
        }

        /** seq는 호출 시작 시점에 nextSeq()로 잡은 값이다. */
        public void outbound(int seq, String method, String url, Integer status, String error, long durationMs) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("order", outbound.size() + 1);
            m.put("seq", seq);
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
            m.put("seq", ++timeline);
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
            for (Map<String, Object> st : statements) {
                String s = (String) st.get("sql");
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
