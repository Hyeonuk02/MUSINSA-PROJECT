package com.pm.order.config;

import java.time.Clock;
import java.time.LocalDateTime;

/**
 * [LEGACY_CHANGES L-I1] JPA 엔티티 콜백(@PrePersist)이 쓰는 Clock holder.
 *
 * <p>엔티티는 Spring 빈을 주입받을 수 없으므로 {@link ClockConfig}가 만든 Clock을 여기에도 담아 둔다.
 * 컨텍스트가 뜨기 전 기본값은 {@link Clock#systemUTC()}다.
 */
public final class AppClock {

    private static volatile Clock clock = Clock.systemUTC();

    private AppClock() {
    }

    static void set(Clock value) {
        clock = value;
    }

    public static LocalDateTime now() {
        return LocalDateTime.now(clock);
    }
}
