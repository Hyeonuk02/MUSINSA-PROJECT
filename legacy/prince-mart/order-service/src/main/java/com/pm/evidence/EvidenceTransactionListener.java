package com.pm.evidence;

import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.transaction.ConfigurableTransactionManager;
import org.springframework.transaction.TransactionExecution;
import org.springframework.transaction.TransactionExecutionListener;

/**
 * [LEGACY_CHANGES L-I3] 트랜잭션 경계를 현재 요청의 Evidence 타임라인에 기록한다(서비스 코드 변경 없음).
 *
 * <p>Spring 6.1+의 TransactionExecutionListener를 트랜잭션 매니저에 붙인다. 새로 시작된 트랜잭션만 기록한다
 * (참여한 트랜잭션은 커밋하지 않는다). 커밋 직전 = COMMIT_BEGIN, 커밋/롤백 뒤 = COMPLETED(outcome).
 * Hibernate의 flush SQL은 커밋 과정에서 나가므로 COMMIT_BEGIN 뒤에 찍힌다(hyeonuk-dev findings O2).
 *
 * <p>리스너는 빈으로 등록하지 않고 BeanPostProcessor로 매니저에 직접 붙인다. Boot가 TransactionExecutionListener 빈을
 * 매니저에 자동으로 붙이는 버전에서 두 번 등록되는 일을 막는다. API는 Spring 6.2(payment)·7.0(order, coupon)에서 같다.
 */
final class EvidenceTransactionListener implements TransactionExecutionListener {

    @Override
    public void beforeCommit(TransactionExecution tx) {
        record(tx, "COMMIT_BEGIN", null);
    }

    @Override
    public void afterCommit(TransactionExecution tx, Throwable failure) {
        record(tx, "COMPLETED", failure == null ? "COMMITTED" : "FAILED");
    }

    @Override
    public void afterRollback(TransactionExecution tx, Throwable failure) {
        record(tx, "COMPLETED", failure == null ? "ROLLED_BACK" : "FAILED");
    }

    private static void record(TransactionExecution tx, String phase, String outcome) {
        EvidenceContext.Record r = EvidenceContext.current();
        if (r != null && tx.isNewTransaction()) {
            r.transaction(tx.getTransactionName(), phase, outcome);
        }
    }

    /** 컨텍스트의 트랜잭션 매니저마다 리스너를 붙인다. */
    static final class Registrar implements BeanPostProcessor {
        private final EvidenceTransactionListener listener = new EvidenceTransactionListener();

        @Override
        public Object postProcessAfterInitialization(Object bean, String beanName) {
            if (bean instanceof ConfigurableTransactionManager tm) {
                tm.addListener(listener);
            }
            return bean;
        }
    }
}
