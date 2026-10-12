package poc.evidence;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.hibernate.autoconfigure.HibernatePropertiesCustomizer;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.core.Ordered;

import java.util.List;

/**
 * Evidence 수집 등록. 앱 코드에서 import하지 않고 auto-configuration으로 붙는다
 * (META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports).
 * 같은 패키지를 넣은 다른 서비스(Coupon)도 비즈니스 코드 수정 없이 같은 수집기를 얻는다.
 *
 * <p>설정은 env로만 받는다. legacy/new는 같은 이미지이고 overlay env만 다르다.
 * <ul>
 *   <li>EVIDENCE_STORE_URL — 없으면 수집기 전체를 등록하지 않는다(로컬 실행용)
 *   <li>EVIDENCE_STACK / EVIDENCE_SERVICE / EVIDENCE_VERSION — STORE_URL이 있는데 비어 있으면 기동 실패
 *   <li>request-log.headers(REQUEST_LOG_HEADERS) — Evidence에 남길 요청·응답 헤더 목록
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

    @Bean
    public EvidenceSender evidenceSender(@Value("${EVIDENCE_STORE_URL}") String storeUrl) {
        return new EvidenceSender(storeUrl);
    }

    @Bean
    public FilterRegistrationBean<EvidenceFilter> evidenceFilterRegistration(
            EvidenceSender sender,
            @Value("${EVIDENCE_STACK:}") String stack,
            @Value("${EVIDENCE_SERVICE:}") String service,
            @Value("${EVIDENCE_VERSION:}") String version,
            @Value("${request-log.headers:Content-Type}") List<String> headerNames) {
        if (stack.isBlank() || service.isBlank() || version.isBlank()) {
            throw new IllegalStateException("EVIDENCE_STORE_URL이 있으면 EVIDENCE_STACK/SERVICE/VERSION이 모두 필요하다");
        }
        log.info("EVIDENCE_ENABLED stack={} service={} version={} headers={}", stack, service, version, headerNames);
        FilterRegistrationBean<EvidenceFilter> registration =
                new FilterRegistrationBean<>(new EvidenceFilter(sender, stack, service, version, headerNames));
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE);
        registration.addUrlPatterns("/*");
        return registration;
    }
}
