package poc.evidence;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * 요청 스레드에 묶인 재생 컨텍스트와 그 요청의 DB 문장 버퍼.
 *
 * <p>EvidenceFilter가 {@link #open}으로 열고 {@code chain.doFilter()}가 반환된 뒤 {@link #close}로 닫는다.
 * 그 사이 같은 스레드에서 나간 SQL만 {@link EvidenceStatementInspector}가 여기에 쌓는다.
 *
 * <p>ThreadLocal이므로 다른 스레드(executor, {@code @Async})로 넘기지 않는다. Evidence는 요청 스레드에서
 * 완성한 뒤 바이트로만 전송 큐에 넘긴다. 다른 스레드로의 전파는 Phase 3.
 */
public final class ReplayContext {

    static final int MAX_STATEMENTS = 200;
    static final int MAX_SQL_LENGTH = 2048;

    private static final ThreadLocal<ReplayContext> CURRENT = new ThreadLocal<>();

    private final String replayRequestId;
    private final String runId;
    private final String sessionId;
    private final List<Map<String, Object>> statements = new ArrayList<>();
    private boolean truncated;

    private ReplayContext(String replayRequestId, String runId, String sessionId) {
        this.replayRequestId = replayRequestId;
        this.runId = runId;
        this.sessionId = sessionId;
    }

    static ReplayContext open(String replayRequestId, String runId, String sessionId) {
        ReplayContext context = new ReplayContext(replayRequestId, runId, sessionId);
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

    /** SQL 원문을 순서대로 기록한다. 가공하지 않는다. 상한을 넘으면 자르거나 버리고 truncated를 켠다. */
    void recordStatement(String sql) {
        if (statements.size() >= MAX_STATEMENTS) {
            truncated = true;
            return;
        }
        String recorded = sql;
        if (sql.length() > MAX_SQL_LENGTH) {
            recorded = sql.substring(0, MAX_SQL_LENGTH);
            truncated = true;
        }
        // Map.of는 순회 순서가 JVM마다 달라 직렬화 바이트가 legacy/new 사이에서 달라진다 — 순서 고정
        Map<String, Object> statement = new LinkedHashMap<>();
        statement.put("seq", statements.size() + 1);
        statement.put("sql", recorded);
        statements.add(statement);
    }

    /** 버퍼를 닫고 스레드에서 떼어낸다. 반환값은 Evidence의 dbAccess. */
    Map<String, Object> close() {
        CURRENT.remove();
        Map<String, Object> dbAccess = new LinkedHashMap<>();
        dbAccess.put("statements", List.copyOf(statements));
        dbAccess.put("truncated", truncated);
        return dbAccess;
    }
}
