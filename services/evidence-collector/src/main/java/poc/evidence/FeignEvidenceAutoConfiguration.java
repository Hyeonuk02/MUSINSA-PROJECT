package poc.evidence;

import feign.Capability;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

/**
 * Feign 외부 호출 전파와 기록 등록. OpenFeign(feign-core)이 클래스패스에 있는 서비스에만 붙는다.
 * Feign이 없는 서비스(services/order, services/coupon)는 이 구성이 평가되지 않는다.
 *
 * <p>{@link EvidenceAutoConfiguration}과 같이 EVIDENCE_STORE_URL이 있을 때만 켠다. 다른 수집기 빈에 의존하지 않는다
 * (ReplayContext만 쓴다). Spring Cloud OpenFeign이 Capability 빈을 모든 Feign 클라이언트에 붙인다.
 */
@AutoConfiguration
@ConditionalOnProperty("EVIDENCE_STORE_URL")
@ConditionalOnClass(name = "feign.Capability")
public class FeignEvidenceAutoConfiguration {

    @Bean
    public Capability evidenceFeignCapability() {
        return new FeignEvidenceCapability();
    }
}
