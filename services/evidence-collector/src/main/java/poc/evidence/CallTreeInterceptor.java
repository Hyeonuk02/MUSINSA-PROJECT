package poc.evidence;

import org.aopalliance.intercept.MethodInterceptor;
import org.aopalliance.intercept.MethodInvocation;
import org.springframework.aop.ProxyMethodInvocation;
import org.springframework.aop.support.AopUtils;
import org.springframework.util.ClassUtils;

import java.util.List;

/**
 * callTree 수집 — 빈 메서드 호출을 현재 요청의 {@link ReplayContext}에 pre-order + depth로 기록한다(call-graph.md 5절).
 *
 * <p>스택 규칙: 진입 시 노드 기록·depth 증가 → {@code proceed()} → 예외면 {@code threw=true} 후 다시 던짐 → finally에서 depth 감소.
 * 재귀·중첩·예외 모두 이 규칙으로 depth가 맞는다. ReplayContext가 없는 스레드(부팅, 재생 헤더 없는 요청)는 기록하지 않는다.
 *
 * <p>기록하는 class는 사용자 코드의 FQCN이다. Spring Data 리포지토리처럼 대상이 프레임워크 클래스인 프록시는
 * 프록시가 구현한 대상 패키지의 인터페이스(예: {@code poc.order.OrderRepository})를 기록한다.
 * Spring AOP는 프록시 기반이라 self-invocation·private·static·final은 보지 못한다 — 수집 범위의 한계(call-graph.md 3절).
 */
class CallTreeInterceptor implements MethodInterceptor {

    private final List<String> packages;

    CallTreeInterceptor(List<String> packages) {
        this.packages = List.copyOf(packages);
    }

    @Override
    public Object invoke(MethodInvocation invocation) throws Throwable {
        ReplayContext context = ReplayContext.current().orElse(null);
        if (context == null) {
            return invocation.proceed();
        }
        int node = context.enterCall(className(invocation), invocation.getMethod().getName());
        boolean threw = false;
        try {
            return invocation.proceed();
        } catch (Throwable t) {
            threw = true;
            throw t;
        } finally {
            context.exitCall(node, threw);
        }
    }

    private String className(MethodInvocation invocation) {
        Object target = invocation.getThis();
        if (target != null) {
            Class<?> user = ClassUtils.getUserClass(AopUtils.getTargetClass(target));
            if (inPackages(user)) {
                return user.getName();
            }
        }
        if (invocation instanceof ProxyMethodInvocation proxyInvocation) {
            for (Class<?> iface : proxyInvocation.getProxy().getClass().getInterfaces()) {
                if (inPackages(iface)) {
                    return iface.getName();
                }
            }
        }
        return invocation.getMethod().getDeclaringClass().getName();
    }

    private boolean inPackages(Class<?> type) {
        String name = type.getName();
        return packages.stream().anyMatch(p -> name.startsWith(p + "."));
    }
}
