package poc.evidence;

import org.aopalliance.intercept.MethodInterceptor;
import org.aopalliance.intercept.MethodInvocation;

import java.util.concurrent.Future;

/**
 * {@code KafkaTemplate.send*()} 둘레 — 방금 ProducerInterceptor.onSend가 기록한 발행에 send()가 돌려준 future를 붙인다.
 * 같은 호출 스레드에서 일어나므로 ThreadLocal로 짝을 짓는다. ack는 Evidence를 닫을 때 이 future로 정한다.
 */
class KafkaTemplateSendAdvice implements MethodInterceptor {

    @Override
    public Object invoke(MethodInvocation invocation) throws Throwable {
        if (ReplayContext.current().isEmpty()) {
            return invocation.proceed();
        }
        ReplayContext.clearLastPublish();
        Object result = invocation.proceed();
        ReplayContext.PublishEntry entry = ReplayContext.takeLastPublish();
        if (entry != null && result instanceof Future<?> future) {
            entry.future = future;
        }
        return result;
    }
}
