package poc.evidence;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.transaction.TransactionExecution;
import org.springframework.transaction.TransactionExecutionListener;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

/**
 * 트랜잭션 단계를 현재 요청의 타임라인에 기록한다(D16).
 *
 * <p>Spring Framework 6.1+ {@link TransactionExecutionListener}. Boot가 이 타입의 빈을 트랜잭션 매니저에 붙인다
 * ({@code ExecutionListenersTransactionManagerCustomizer}). 필터에서 동기화를 등록하지 않는다 — 필터 시점엔 트랜잭션이 없다.
 * <ul>
 *   <li>{@code beforeCommit} → {@code COMMIT_BEGIN}
 *   <li>{@code afterCommit} → {@code COMPLETED / COMMITTED}(실패면 {@code COMMIT_FAILED})
 *   <li>{@code afterRollback} → {@code COMPLETED / ROLLED_BACK}
 * </ul>
 * 한 트랜잭션이 타임라인에 두 번 찍힌다. "커밋 전 발행"은 {@code publish.seq < COMMIT_BEGIN.seq}로 판정한다.
 *
 * <p>EVIDENCE_TX_TRACE=true면 콜백 순서를 로그로 남긴다(실측용, 기본 off): 리스너 콜백과, 트랜잭션 시작 때 등록하는
 * 관측용 동기화의 beforeCommit/afterCommit/afterCompletion. doCommit 자체는 JpaTransactionManager DEBUG 로그로 본다.
 */
class EvidenceTransactionListener implements TransactionExecutionListener {

    private static final Logger log = LoggerFactory.getLogger(EvidenceTransactionListener.class);

    private final boolean trace;

    EvidenceTransactionListener(boolean trace) {
        this.trace = trace;
    }

    @Override
    public void afterBegin(TransactionExecution transaction, Throwable beginFailure) {
        if (trace && beginFailure == null && TransactionSynchronizationManager.isSynchronizationActive()) {
            String name = transaction.getTransactionName();
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                @Override
                public void beforeCommit(boolean readOnly) {
                    traceLog("synchronization.beforeCommit", name);
                }

                @Override
                public void afterCommit() {
                    traceLog("synchronization.afterCommit", name);
                }

                @Override
                public void afterCompletion(int status) {
                    traceLog("synchronization.afterCompletion(" + status + ")", name);
                }
            });
        }
    }

    @Override
    public void beforeCommit(TransactionExecution transaction) {
        traceLog("listener.beforeCommit", transaction.getTransactionName());
        ReplayContext.current().ifPresent(c -> c.recordTransaction(transaction.getTransactionName(), "COMMIT_BEGIN", null));
    }

    @Override
    public void afterCommit(TransactionExecution transaction, Throwable commitFailure) {
        traceLog("listener.afterCommit", transaction.getTransactionName());
        String outcome = commitFailure == null ? "COMMITTED" : "COMMIT_FAILED";
        ReplayContext.current().ifPresent(c -> c.recordTransaction(transaction.getTransactionName(), "COMPLETED", outcome));
    }

    @Override
    public void afterRollback(TransactionExecution transaction, Throwable rollbackFailure) {
        traceLog("listener.afterRollback", transaction.getTransactionName());
        ReplayContext.current().ifPresent(c -> c.recordTransaction(transaction.getTransactionName(), "COMPLETED", "ROLLED_BACK"));
    }

    private void traceLog(String callback, String name) {
        if (trace) {
            String request = ReplayContext.current().map(c -> c.replayRequestId() + "/" + c.hopPath()).orElse("-");
            log.info("TX_TRACE {} tx={} request={}", callback, name, request);
        }
    }
}
