package poc.order.requestlog;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import tools.jackson.databind.json.JsonMapper;

import java.io.IOException;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Collections;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Phase 0 요청 로그. 요청 1건당 "REQUEST_LOG {json}" 한 줄을 남긴다.
 *
 * <p>arrivedAt/completedAt은 epoch ms, arrivedAtNano/completedAtNano는 같은 JVM 안에서만
 * 비교 가능한 System.nanoTime 값이다 (직렬 판정용).
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestLogFilter extends OncePerRequestFilter {

    public static final String REQUEST_ID_HEADER = "X-Replay-Request-Id";

    private static final Logger log = LoggerFactory.getLogger(RequestLogFilter.class);

    private final AtomicLong sequence = new AtomicLong();
    private final JsonMapper jsonMapper = JsonMapper.builder().build();
    private final List<String> headerNames;

    public RequestLogFilter(@Value("${request-log.headers}") List<String> headerNames) {
        this.headerNames = List.copyOf(headerNames);
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        long arrivedAt = System.currentTimeMillis();
        long arrivedAtNano = System.nanoTime();
        long seq = sequence.incrementAndGet();

        HttpServletRequest forwarded = request;
        String bodyHash = null;
        if (!"GET".equals(request.getMethod())) {
            // 프레임워크가 본문을 해석하기 전에 원시 바이트를 전부 읽어 해시하고, 같은 바이트를 다시 읽을 수 있게 넘긴다.
            byte[] body = request.getInputStream().readAllBytes();
            bodyHash = sha256Hex(body);
            forwarded = new CachedBodyRequest(request, body);
        }

        try {
            chain.doFilter(forwarded, response);
        } finally {
            long completedAt = System.currentTimeMillis();
            long completedAtNano = System.nanoTime();

            Map<String, Object> entry = new LinkedHashMap<>();
            entry.put("requestId", request.getHeader(REQUEST_ID_HEADER));
            entry.put("seq", seq);
            entry.put("method", request.getMethod());
            entry.put("uri", request.getRequestURI());
            entry.put("query", request.getQueryString() == null ? "" : request.getQueryString());
            entry.put("headers", selectedHeaders(request));
            entry.put("bodyHash", bodyHash);
            entry.put("arrivedAt", arrivedAt);
            entry.put("completedAt", completedAt);
            entry.put("arrivedAtNano", arrivedAtNano);
            entry.put("completedAtNano", completedAtNano);
            log.info("REQUEST_LOG {}", jsonMapper.writeValueAsString(entry));
        }
    }

    private Map<String, List<String>> selectedHeaders(HttpServletRequest request) {
        Map<String, List<String>> headers = new LinkedHashMap<>();
        for (String name : headerNames) {
            headers.put(name, Collections.list(request.getHeaders(name)));
        }
        return headers;
    }

    private static String sha256Hex(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
