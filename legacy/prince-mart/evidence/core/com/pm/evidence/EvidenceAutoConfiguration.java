package com.pm.evidence;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

import java.util.Arrays;

/**
 * [LEGACY_CHANGES L-I2] Evidence 계측 등록. 서비스 코드는 건드리지 않고 자동 구성으로 붙인다
 * (META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports).
 *
 * <p>{@code evidence.enabled=true}이고 {@code evidence.store-url}이 있을 때만 켜진다(local profile).
 * Boot 3(payment)·Boot 4(order, coupon)에서 위치가 같은 Spring 코어 API만 쓴다(Filter 빈은 Ordered로 자동 등록).
 */
@AutoConfiguration
@ConditionalOnProperty(name = "evidence.enabled", havingValue = "true")
public class EvidenceAutoConfiguration {

    @Bean(destroyMethod = "shutdown")
    EvidenceSender evidenceSender(@Value("${evidence.store-url}") String storeUrl) {
        return new EvidenceSender(storeUrl);
    }

    @Bean
    EvidenceRecorder evidenceRecorder(EvidenceSender sender,
                                      @Value("${evidence.stack}") String stack,
                                      @Value("${evidence.service}") String service,
                                      @Value("${app.fixed-clock:}") String fixedClock) {
        return new EvidenceRecorder(sender, stack, service, fixedClock);
    }

    @Bean
    EvidenceFilter evidenceFilter(EvidenceRecorder recorder, @Value("${evidence.headers}") String headers) {
        return new EvidenceFilter(recorder, Arrays.stream(headers.split(",")).map(String::trim).toList());
    }

    @Bean
    EvidenceErrorRecorder evidenceErrorRecorder() {
        return new EvidenceErrorRecorder();
    }

    @Bean
    EvidenceFeignCapability evidenceFeignCapability() {
        return new EvidenceFeignCapability();
    }
}
