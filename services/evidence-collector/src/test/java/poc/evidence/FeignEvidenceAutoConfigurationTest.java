package poc.evidence;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

/** Feign 자동 구성의 켜짐 조건 — Feign이 없는 서비스(services/order, services/coupon)에는 붙지 않는다. */
class FeignEvidenceAutoConfigurationTest {

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(FeignEvidenceAutoConfiguration.class));

    @Test
    void registersCapabilityWhenFeignPresentAndEvidenceEnabled() {
        runner.withPropertyValues("EVIDENCE_STORE_URL=http://evidence-store")
                .run(context -> assertThat(context).hasSingleBean(FeignEvidenceCapability.class));
    }

    @Test
    void skippedWithoutFeignOnClasspath() {
        runner.withPropertyValues("EVIDENCE_STORE_URL=http://evidence-store")
                .withClassLoader(new FilteredClassLoader("feign."))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean("evidenceFeignCapability");
                });
    }

    @Test
    void skippedWhenEvidenceDisabled() {
        runner.run(context -> assertThat(context).doesNotHaveBean("evidenceFeignCapability"));
    }
}
