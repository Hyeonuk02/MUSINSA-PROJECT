package poc.evidence;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.util.ContentCachingResponseWrapper;
import tools.jackson.databind.json.JsonMapper;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.Collections;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * 요청 1건 × 스택 1개의 Evidence JSON v0(docs/evidence-schema-v0.json)를 만들어 Store로 보낸다.
 *
 * <ol>
 *   <li>X-Replay-Request-Id·X-Run-Id·X-Session-Id가 모두 있을 때만 동작한다. 없으면 로그 한 줄만 남기고 통과
 *   <li>요청 본문을 전부 읽어 해시하고, {@link ReplayContext}를 연다
 *   <li>{@code chain.doFilter()}가 반환된 뒤 컨텍스트를 닫는다 — 직렬화 중 지연 SELECT까지 포함
 *   <li>응답 본문을 클라이언트로 내보내고(copyBodyToResponse) 커밋한 뒤, 요청 스레드에서 Evidence를 완성해 큐에 넣는다
 * </ol>
 *
 * <p>비즈니스 코드와 Order 도메인에 의존하지 않는다. 같은 패키지를 다른 서비스(Coupon)가 그대로 쓴다.
 */
public class EvidenceFilter extends OncePerRequestFilter {

    static final String REPLAY_REQUEST_ID_HEADER = "X-Replay-Request-Id";
    static final String RUN_ID_HEADER = "X-Run-Id";
    static final String SESSION_ID_HEADER = "X-Session-Id";
    static final int MAX_RESPONSE_BODY_BYTES = 32 * 1024;

    private static final Logger log = LoggerFactory.getLogger(EvidenceFilter.class);

    private final EvidenceSender sender;
    private final String stack;
    private final String service;
    private final String version;
    private final List<String> headerNames;
    private final JsonMapper jsonMapper = JsonMapper.builder().build();

    public EvidenceFilter(EvidenceSender sender, String stack, String service, String version, List<String> headerNames) {
        this.sender = sender;
        this.stack = stack;
        this.service = service;
        this.version = version;
        this.headerNames = List.copyOf(headerNames);
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String replayRequestId = request.getHeader(REPLAY_REQUEST_ID_HEADER);
        String runId = request.getHeader(RUN_ID_HEADER);
        String sessionId = request.getHeader(SESSION_ID_HEADER);
        if (isBlank(replayRequestId) || isBlank(runId) || isBlank(sessionId)) {
            log.info("EVIDENCE_SKIP no replay headers: {} {} (replayRequestId={}, runId={}, sessionId={})",
                    request.getMethod(), request.getRequestURI(), replayRequestId, runId, sessionId);
            chain.doFilter(request, response);
            return;
        }

        Instant arrivedAt = Instant.now();
        long arrivedNano = System.nanoTime();
        byte[] requestBody = request.getInputStream().readAllBytes();
        HttpServletRequest bufferedRequest = new BufferedBodyRequest(request, requestBody);
        ContentCachingResponseWrapper cachingResponse = new ContentCachingResponseWrapper(response);

        ReplayContext context = ReplayContext.open(replayRequestId, runId, sessionId);
        Map<String, Object> dbAccess;
        try {
            chain.doFilter(bufferedRequest, cachingResponse);
        } finally {
            // 예외로 빠져나가도 스레드 재사용에 대비해 반드시 뗀다. 예외 시 Evidence는 남기지 않는다(컨테이너 에러 처리로 넘김).
            dbAccess = context.close();
        }
        Instant completedAt = Instant.now();
        long completedNano = System.nanoTime();

        byte[] responseBody = cachingResponse.getContentAsByteArray();
        int status = cachingResponse.getStatus();
        Map<String, String> responseHeaders = selectedResponseHeaders(cachingResponse);
        cachingResponse.copyBodyToResponse();
        response.flushBuffer();  // 응답을 먼저 커밋하고, Evidence 조립·enqueue는 그 뒤

        Map<String, Object> requestPart = new LinkedHashMap<>();
        requestPart.put("method", request.getMethod());
        requestPart.put("path", request.getRequestURI());
        requestPart.put("query", request.getQueryString() == null ? "" : request.getQueryString());
        requestPart.put("headers", selectedRequestHeaders(request));
        requestPart.put("bodyHash", sha256(requestBody));

        Map<String, Object> responsePart = new LinkedHashMap<>();
        responsePart.put("status", status);
        responsePart.put("headers", responseHeaders);
        responsePart.put("bodyHash", sha256(responseBody));
        responsePart.put("body", responseBody.length <= MAX_RESPONSE_BODY_BYTES
                ? new String(responseBody, StandardCharsets.UTF_8) : null);

        Map<String, Object> timing = new LinkedHashMap<>();
        timing.put("arrivedAt", arrivedAt.toString());
        timing.put("completedAt", completedAt.toString());
        timing.put("arrivedNano", arrivedNano);
        timing.put("completedNano", completedNano);

        Map<String, Object> evidence = new LinkedHashMap<>();
        evidence.put("schemaVersion", "v0");
        evidence.put("runId", runId);
        evidence.put("replayRequestId", replayRequestId);
        evidence.put("sessionId", sessionId);
        evidence.put("stack", stack);
        evidence.put("service", service);
        evidence.put("version", version);
        evidence.put("request", requestPart);
        evidence.put("response", responsePart);
        evidence.put("dbAccess", dbAccess);
        evidence.put("callTree", null);
        evidence.put("timing", timing);
        evidence.put("capturedAt", Instant.now().toString());

        sender.enqueue(runId + "/" + replayRequestId + "/" + stack, jsonMapper.writeValueAsBytes(evidence));
    }

    private Map<String, String> selectedRequestHeaders(HttpServletRequest request) {
        Map<String, String> headers = new LinkedHashMap<>();
        for (String name : headerNames) {
            List<String> values = Collections.list(request.getHeaders(name));
            if (!values.isEmpty()) {
                headers.put(name.toLowerCase(Locale.ROOT), String.join(",", values));
            }
        }
        return headers;
    }

    private Map<String, String> selectedResponseHeaders(HttpServletResponse response) {
        Map<String, String> headers = new LinkedHashMap<>();
        for (String name : headerNames) {
            // Content-Type은 헤더 목록이 아니라 setContentType으로 잡히는 경우가 있어 따로 읽는다
            List<String> values = "content-type".equalsIgnoreCase(name)
                    ? (response.getContentType() == null ? List.of() : List.of(response.getContentType()))
                    : List.copyOf(response.getHeaders(name));
            if (!values.isEmpty()) {
                headers.put(name.toLowerCase(Locale.ROOT), String.join(",", values));
            }
        }
        return headers;
    }

    private static String sha256(byte[] bytes) {
        try {
            return "sha256:" + HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}
