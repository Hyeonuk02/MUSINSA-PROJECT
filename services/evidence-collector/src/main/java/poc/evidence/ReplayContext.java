package poc.evidence;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.Future;

/**
 * 요청 스레드에 묶인 재생 컨텍스트와 그 홉(hop)의 Evidence 버퍼.
 *
 * <p>EvidenceFilter가 {@link #open}으로 열고 {@code chain.doFilter()}가 반환된 뒤 {@link #close}로 닫는다.
 * 그 사이 같은 스레드에서 일어난 일을 모은다.
 * <ul>
 *   <li><b>타임라인</b>: SQL 문장·외부 호출·이벤트 발행·트랜잭션 단계가 <b>하나의 seq 카운터</b>로 번호를 받는다(D16).
 *       그래서 각 배열 안의 seq는 연속이 아니고, 배열을 합쳐 seq로 정렬하면 요청 안 순서가 복원된다
 *   <li><b>callTree</b>: 빈 메서드 진입·종료. 노드 수가 많아 타임라인과 섞지 않도록 별도 카운터. pre-order + depth,
 *       depth는 스택으로 관리하고 상한(500)을 넘어도 스택은 유지한다(call-graph.md 5절)
 *   <li><b>자식 hopPath</b>: 이 홉에서 나간 n번째 HTTP 호출 = {@code <hopPath>.h<n>}, n번째 이벤트 = {@code <hopPath>.e<n>}.
 *       종류별 순번이라 쿼리 수가 바뀌어도 짝이 유지된다(D15)
 * </ul>
 *
 * <p>ThreadLocal이므로 다른 스레드로 넘기지 않는다. Evidence는 요청 스레드에서 완성한 뒤 바이트로만 전송 큐에 넘긴다.
 */
public final class ReplayContext {

    static final int MAX_STATEMENTS = 200;
    static final int MAX_SQL_LENGTH = 2048;
    static final int MAX_CALL_NODES = 500;
    static final int MAX_PAYLOAD_BYTES = 32 * 1024;

    private static final ThreadLocal<ReplayContext> CURRENT = new ThreadLocal<>();

    private final String replayRequestId;
    private final String runId;
    private final String sessionId;
    private final String hopPath;

    private int seq;
    private final List<Map<String, Object>> statements = new ArrayList<>();
    private boolean statementsTruncated;
    private final List<Map<String, Object>> externalCalls = new ArrayList<>();
    private final List<PublishEntry> published = new ArrayList<>();
    private final List<Map<String, Object>> transactions = new ArrayList<>();
    private int httpChildren;
    private int eventChildren;

    /** 직전 발행 기록 — ProducerInterceptor.onSend가 남기고 KafkaTemplate send advisor가 future를 붙인다(같은 호출 스레드). */
    private static final ThreadLocal<PublishEntry> LAST_PUBLISH = new ThreadLocal<>();

    private final List<Map<String, Object>> callNodes = new ArrayList<>();
    private int callSeq;
    private int callDepth;
    private boolean callTreeTruncated;

    private ReplayContext(String replayRequestId, String runId, String sessionId, String hopPath) {
        this.replayRequestId = replayRequestId;
        this.runId = runId;
        this.sessionId = sessionId;
        this.hopPath = hopPath;
    }

    static ReplayContext open(String replayRequestId, String runId, String sessionId, String hopPath) {
        ReplayContext context = new ReplayContext(replayRequestId, runId, sessionId, hopPath);
        CURRENT.set(context);
        return context;
    }

    public static Optional<ReplayContext> current() {
        return Optional.ofNullable(CURRENT.get());
    }

    public String replayRequestId() {
        return replayRequestId;
    }

    public String runId() {
        return runId;
    }

    public String sessionId() {
        return sessionId;
    }

    public String hopPath() {
        return hopPath;
    }

    /** 타임라인 다음 번호. */
    int nextSeq() {
        return ++seq;
    }

    /** 이 홉에서 나가는 다음 HTTP 호출의 hopPath. */
    String nextHttpChildHop() {
        return hopPath + ".h" + (++httpChildren);
    }

    /** 이 홉에서 나가는 다음 이벤트 발행의 hopPath(그 이벤트의 소비 홉). */
    String nextEventChildHop() {
        return hopPath + ".e" + (++eventChildren);
    }

    /**
     * 이벤트 발행 1건(ProducerInterceptor.onSend, 호출 스레드). seq는 발행 시점의 타임라인 번호.
     * ack는 여기서 정하지 않는다 — Evidence를 닫을 때(호출 스레드) 붙은 future의 상태로 정한다.
     */
    PublishEntry recordPublish(String topic, String key, byte[] payload, String childHopPath) {
        PublishEntry entry = new PublishEntry(nextSeq(), topic, key, payload, childHopPath);
        published.add(entry);
        LAST_PUBLISH.set(entry);
        return entry;
    }

    static void clearLastPublish() {
        LAST_PUBLISH.remove();
    }

    static PublishEntry takeLastPublish() {
        PublishEntry entry = LAST_PUBLISH.get();
        LAST_PUBLISH.remove();
        return entry;
    }

    /** 발행 기록. future는 KafkaTemplate.send가 돌려준 것(없으면 ack failed). */
    static final class PublishEntry {
        final int seq;
        final String topic;
        final String key;
        final byte[] payload;
        final String childHopPath;
        volatile Future<?> future;

        PublishEntry(int seq, String topic, String key, byte[] payload, String childHopPath) {
            this.seq = seq;
            this.topic = topic;
            this.key = key;
            this.payload = payload;
            this.childHopPath = childHopPath;
        }

        /** 호출 스레드에서 Evidence를 닫을 때. 앱이 get()으로 기다린 뒤라면 future는 이미 끝나 있다. */
        Map<String, Object> toEvidence() {
            boolean ok = false;
            Future<?> f = future;
            if (f != null && f.isDone() && !f.isCancelled()) {
                try {
                    f.get();  // 이미 끝난 future — 즉시 돌아온다
                    ok = true;
                } catch (Exception e) {
                    ok = false;
                }
            }
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("seq", seq);
            m.put("topic", topic);
            m.put("key", key);
            m.put("payloadHash", EvidenceWriter.sha256(payload));
            m.put("payload", payload.length <= MAX_PAYLOAD_BYTES ? new String(payload, java.nio.charset.StandardCharsets.UTF_8) : null);
            m.put("ack", ok ? "ok" : "failed");
            m.put("childHopPath", childHopPath);
            return m;
        }
    }

    /** SQL 원문을 순서대로 기록한다. 가공하지 않는다. 상한을 넘으면 자르거나 버리고 truncated를 켠다. */
    void recordStatement(String sql) {
        if (statements.size() >= MAX_STATEMENTS) {
            statementsTruncated = true;
            return;
        }
        String recorded = sql;
        if (sql.length() > MAX_SQL_LENGTH) {
            recorded = sql.substring(0, MAX_SQL_LENGTH);
            statementsTruncated = true;
        }
        Map<String, Object> statement = new LinkedHashMap<>();
        statement.put("seq", nextSeq());
        statement.put("sql", recorded);
        statements.add(statement);
    }

    /** 외부 호출 1건. seq는 호출 시작 때 받아 둔 값(타임라인상 호출이 나간 시점). */
    void recordExternalCall(Map<String, Object> call) {
        externalCalls.add(call);
    }

    /** 트랜잭션 단계. phase = COMMIT_BEGIN | COMPLETED, outcome은 COMPLETED일 때만. */
    void recordTransaction(String name, String phase, String outcome) {
        Map<String, Object> tx = new LinkedHashMap<>();
        tx.put("seq", nextSeq());
        tx.put("name", name);
        tx.put("phase", phase);
        tx.put("outcome", outcome);
        transactions.add(tx);
    }

    /** 빈 메서드 진입. 기록한 노드의 인덱스, 상한을 넘었으면 -1. 상한과 무관하게 depth는 올린다. */
    int enterCall(String className, String method) {
        int index = -1;
        if (callNodes.size() < MAX_CALL_NODES) {
            Map<String, Object> node = new LinkedHashMap<>();
            node.put("seq", ++callSeq);
            node.put("depth", callDepth);
            node.put("class", className);
            node.put("method", method);
            node.put("threw", false);
            callNodes.add(node);
            index = callNodes.size() - 1;
        } else {
            callTreeTruncated = true;
        }
        callDepth++;
        return index;
    }

    /** 빈 메서드 종료(finally에서 호출). */
    void exitCall(int index, boolean threw) {
        callDepth--;
        if (index >= 0 && threw) {
            callNodes.get(index).put("threw", true);
        }
    }

    /** 버퍼를 닫고 스레드에서 떼어낸다. 반환값은 Evidence의 v1 사이드이펙트 필드들. */
    Captured close() {
        CURRENT.remove();
        LAST_PUBLISH.remove();
        Map<String, Object> dbAccess = new LinkedHashMap<>();
        dbAccess.put("statements", List.copyOf(statements));
        dbAccess.put("truncated", statementsTruncated);
        Map<String, Object> events = new LinkedHashMap<>();
        events.put("published", published.stream().map(PublishEntry::toEvidence).toList());
        Map<String, Object> callTree = new LinkedHashMap<>();
        callTree.put("nodes", List.copyOf(callNodes));
        callTree.put("truncated", callTreeTruncated);
        return new Captured(dbAccess, List.copyOf(externalCalls), events, List.copyOf(transactions), callTree);
    }

    record Captured(Map<String, Object> dbAccess, List<Map<String, Object>> externalCalls, Map<String, Object> events,
                    List<Map<String, Object>> transactions, Map<String, Object> callTree) {
    }
}
