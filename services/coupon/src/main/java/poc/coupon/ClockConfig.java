package poc.coupon;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

/** 시각 고정 — Order의 ClockConfig와 같다. legacy/new 모두 같은 APP_FIXED_CLOCK. */
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
