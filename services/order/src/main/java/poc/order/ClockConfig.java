package poc.order;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

/**
 * Phase 1.3a: 시각 고정.
 *
 * <p>Legacy와 New가 같은 트래픽을 받았을 때 시각 때문에 결과가 달라지면
 * Evidence 비교에서 실제 행동 차이와 구분되지 않는다. 두 스택 모두 같은
 * {@code APP_FIXED_CLOCK} 값을 받아 {@code createdAt}이 결정적으로 나오게 한다.
 *
 * <p>값이 비어 있으면 시스템 시각을 쓴다 (로컬 개발 편의). 존은 항상 UTC다.
 */
@Configuration
public class ClockConfig {

    @Bean
    public Clock clock(@Value("${app.fixed-clock:}") String fixedClock) {
        if (fixedClock == null || fixedClock.isBlank()) {
            return Clock.systemUTC();
        }
        return Clock.fixed(Instant.parse(fixedClock), ZoneOffset.UTC);
    }
}
