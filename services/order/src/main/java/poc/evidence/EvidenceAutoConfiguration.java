package poc.evidence;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.aop.Advisor;
import org.springframework.aop.aspectj.AspectJExpressionPointcutAdvisor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.hibernate.autoconfigure.HibernatePropertiesCustomizer;
import org.springframework.boot.restclient.RestClientCustomizer;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.transaction.TransactionExecutionListener;

import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;

/**
 * Evidence 수집 등록. 앱 코드에서 import하지 않고 auto-configuration으로 붙는다
 * (META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports).
 * 같은 패키지를 넣은 다른 서비스(Coupon, Kotlin New)도 비즈니스 코드 수정 없이 같은 수집기를 얻는다.
 *
 * <p>설정은 env로만 받는다. legacy/new는 같은 이미지이고 overlay env만 다르다.
 * <ul>
 *   <li>EVIDENCE_STORE_URL — 없으면 수집기 전체를 등록하지 않는다(로컬 실행용)
 *   <li>EVIDENCE_STACK / EVIDENCE_SERVICE / EVIDENCE_VERSION / EVIDENCE_HEADERS / EVIDENCE_APP_PACKAGES
 *       — STORE_URL이 있는데 비어 있으면 기동 실패
 *   <li>EVIDENCE_APP_PACKAGES — callTree 수집 대상 패키지(쉼표 구분, 예: {@code poc.order}). error.where 판단에도 쓴다
 *   <li>EVIDENCE_SPILL_DIR — 전송 실패분을 쓰는 디렉터리(기본 /var/evidence/spill, k8s는 hostPath)
 *   <li>EVIDENCE_HEADERS — Evidence에 남길 요청·응답 헤더 목록. 디버깅 로그용 REQUEST_LOG_HEADERS와 분리한다
 *       (x-request-id·Host 같은 실행 시점 값은 로그에는 필요하지만 Evidence에는 판정 잡음)
 *   <li>EVIDENCE_TX_TRACE — true면 트랜잭션 콜백 순서를 로그로 남긴다(실측용, 기본 off)
 * </ul>
 */
@AutoConfiguration
@ConditionalOnProperty("EVIDENCE_STORE_URL")
public class EvidenceAutoConfiguration {

    private static final Logger log = LoggerFactory.getLogger(EvidenceAutoConfiguration.class);

    @Bean
    public EvidenceStatementInspector evidenceStatementInspector() {
        return new EvidenceStatementInspector();
    }

    /** 클래스명 문자열이 아니라 인스턴스로 넣는다(Spring이 만든 빈을 Hibernate가 그대로 쓰게). */
    @Bean
    public HibernatePropertiesCustomizer evidenceStatementInspectorCustomizer(EvidenceStatementInspector inspector) {
        return properties -> properties.put("hibernate.session_factory.statement_inspector", inspector);
    }

    /** Boot가 TransactionExecutionListener 빈을 트랜잭션 매니저에 붙인다(ExecutionListenersTransactionManagerCustomizer). */
    @Bean
    public TransactionExecutionListener evidenceTransactionListener(@Value("${EVIDENCE_TX_TRACE:false}") boolean trace) {
        return new EvidenceTransactionListener(trace);
    }

    /**
     * callTree advisor. 대상: EVIDENCE_APP_PACKAGES 아래 빈의 메서드.
     * 제외: 검증 레이어 자신, 서블릿 필터(OncePerRequestFilter의 final 메서드를 CGLIB 프록시가 가로채지 못해 프록시 상태로 호출되면 깨진다),
     * {@code @Configuration} 클래스(이미 CGLIB 강화됨, 요청 경로가 아님).
     */
    @Bean
    public static Advisor evidenceCallTreeAdvisor(@Value("${EVIDENCE_APP_PACKAGES:}") List<String> packages) {
        AspectJExpressionPointcutAdvisor advisor = new AspectJExpressionPointcutAdvisor();
        advisor.setExpression(callTreeExpression(packages));
        advisor.setAdvice(new CallTreeInterceptor(packages));
        advisor.setOrder(Ordered.HIGHEST_PRECEDENCE);  // 트랜잭션 프록시보다 바깥 — 트랜잭션 경계 안팎의 호출을 같은 노드로 본다
        return advisor;
    }

    static String callTreeExpression(List<String> packages) {
        if (packages.isEmpty()) {
            throw new IllegalStateException("EVIDENCE_STORE_URL이 있으면 EVIDENCE_APP_PACKAGES가 필요하다");
        }
        String targets = packages.stream()
                .map(p -> "execution(* " + p + "..*.*(..))")
                .collect(Collectors.joining(" || ", "(", ")"));
        return targets
                + " && !within(poc.evidence..*)"
                + " && !within(jakarta.servlet.Filter+)"
                + " && !@within(org.springframework.context.annotation.Configuration)";
    }

    @Bean
    public EvidenceSender evidenceSender(@Value("${EVIDENCE_STORE_URL}") String storeUrl,
                                         @Value("${EVIDENCE_SPILL_DIR:/var/evidence/spill}") String spillDir,
                                         @Value("${EVIDENCE_DELAY_MS:0}") long delayMs) {
        if (delayMs > 0) {
            log.warn("EVIDENCE_DELAY_MS={} — 검증용 지연이 켜져 있다", delayMs);
        }
        return new EvidenceSender(storeUrl, Path.of(spillDir), delayMs);
    }

    @Bean
    public FilterRegistrationBean<EvidenceFilter> evidenceFilterRegistration(
            EvidenceSender sender,
            @Value("${EVIDENCE_STACK:}") String stack,
            @Value("${EVIDENCE_SERVICE:}") String service,
            @Value("${EVIDENCE_VERSION:}") String version,
            @Value("${EVIDENCE_HEADERS:}") List<String> headerNames,
            @Value("${EVIDENCE_APP_PACKAGES:}") List<String> packages) {
        if (stack.isBlank() || service.isBlank() || version.isBlank() || headerNames.isEmpty() || packages.isEmpty()) {
            throw new IllegalStateException(
                    "EVIDENCE_STORE_URL이 있으면 EVIDENCE_STACK/SERVICE/VERSION/HEADERS/APP_PACKAGES가 모두 필요하다");
        }
        log.info("EVIDENCE_ENABLED stack={} service={} version={} headers={} packages={} callTree=[{}]",
                stack, service, version, headerNames, packages, callTreeExpression(packages));
        FilterRegistrationBean<EvidenceFilter> registration =
                new FilterRegistrationBean<>(new EvidenceFilter(sender, stack, service, version, headerNames, packages));
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE);
        registration.addUrlPatterns("/*");
        return registration;
    }

    /** 외부 호출 전파·기록. RestClient 자동 구성(spring-boot-restclient)이 있는 서비스에만 붙는다. */
    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(RestClientCustomizer.class)
    static class RestClientPropagation {

        @Bean
        RestClientCustomizer evidenceRestClientCustomizer() {
            ReplayPropagatingInterceptor interceptor = new ReplayPropagatingInterceptor();
            return builder -> builder.requestInterceptor(interceptor);
        }
    }
}
