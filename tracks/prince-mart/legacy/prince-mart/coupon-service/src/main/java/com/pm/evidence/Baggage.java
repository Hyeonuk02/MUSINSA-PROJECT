package com.pm.evidence;

import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * [LEGACY_CHANGES L-I2] W3C baggage 헤더 파싱({@code k1=v1,k2=v2;prop}).
 *
 * <p>replayRequestId는 진입 서비스에는 X-Replay-Request-Id로, Feign 하위 호출과 Kafka consumer에는 OTel agent가 전파한
 * baggage로만 도착한다(legacy-decision-log L9). OTel API에 의존하지 않도록 헤더 문자열을 직접 읽는다.
 */
public final class Baggage {

    private Baggage() {
    }

    public static Map<String, String> parse(String header) {
        Map<String, String> out = new LinkedHashMap<>();
        if (header == null || header.isBlank()) return out;
        for (String member : header.split(",")) {
            String kv = member.split(";", 2)[0].trim();
            int eq = kv.indexOf('=');
            if (eq <= 0) continue;
            out.put(kv.substring(0, eq).trim(),
                    URLDecoder.decode(kv.substring(eq + 1).trim(), StandardCharsets.UTF_8));
        }
        return out;
    }
}
