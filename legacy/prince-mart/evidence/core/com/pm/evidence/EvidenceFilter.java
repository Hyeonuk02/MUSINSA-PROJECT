package com.pm.evidence;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.Ordered;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.util.ContentCachingResponseWrapper;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Collections;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * [LEGACY_CHANGES L-I2] HTTP 요청 1건의 Evidence(요청·응답·DB 접근·나가는 호출·이벤트·예외·처리 시간)를 남긴다.
 *
 * <p>replayRequestId가 없는 요청(개발용 직접 호출 등)은 기록하지 않는다. 진입 서비스는 X-Replay-Request-Id, Feign으로
 * 호출된 하위 서비스는 OTel baggage로 받는다. 응답 본문을 클라이언트에 먼저 돌려준 뒤 Evidence를 큐에 넣는다.
 * Phase 0 RequestLogFilter의 필드(seq, bodyHash, arrivedAt/completedAt, *Nano)를 그대로 포함한다.
 */
final class EvidenceFilter extends OncePerRequestFilter implements Ordered {

    static final String REPLAY_HEADER = "X-Replay-Request-Id";

    private final EvidenceRecorder recorder;
    private final List<String> headerNames;

    EvidenceFilter(EvidenceRecorder recorder, List<String> headerNames) {
        this.recorder = recorder;
        this.headerNames = List.copyOf(headerNames);
    }

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE + 10;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        Map<String, String> baggage = Baggage.parse(request.getHeader("baggage"));
        String replayId = firstNonBlank(request.getHeader(REPLAY_HEADER), baggage.get("replayRequestId"));
        if (replayId == null) {
            chain.doFilter(request, response);
            return;
        }
        String runId = firstNonBlank(request.getHeader("X-Run-Id"), baggage.get("runId"));
        String sessionId = firstNonBlank(request.getHeader("X-Session-Id"), baggage.get("sessionId"));

        EvidenceContext.Record record = EvidenceContext.start("http", replayId, runId, sessionId);

        byte[] requestBody = new byte[0];
        HttpServletRequest forwarded = request;
        if (!"GET".equals(request.getMethod())) {
            requestBody = request.getInputStream().readAllBytes();
            forwarded = new CachedBodyRequest(request, requestBody);
        }
        ContentCachingResponseWrapper wrapped = new ContentCachingResponseWrapper(response);

        try {
            chain.doFilter(forwarded, wrapped);
        } catch (IOException | ServletException | RuntimeException e) {
            record.error(e);
            throw e;
        } finally {
            int status = wrapped.getStatus();
            byte[] responseBody = wrapped.getContentAsByteArray();
            wrapped.copyBodyToResponse();
            EvidenceContext.clear();

            Map<String, Object> req = new LinkedHashMap<>();
            req.put("method", request.getMethod());
            req.put("uri", request.getRequestURI());
            req.put("query", request.getQueryString() == null ? "" : request.getQueryString());
            req.put("headers", selectedHeaders(request));
            req.put("bodyHash", sha256(requestBody));
            req.put("body", new String(requestBody, StandardCharsets.UTF_8));

            Map<String, Object> res = new LinkedHashMap<>();
            res.put("status", status);
            res.put("contentType", wrapped.getContentType());
            res.put("body", new String(responseBody, StandardCharsets.UTF_8));

            Map<String, Object> body = new LinkedHashMap<>();
            body.put("request", req);
            body.put("response", res);
            recorder.finish(record, body);
        }
    }

    private Map<String, List<String>> selectedHeaders(HttpServletRequest request) {
        Map<String, List<String>> headers = new LinkedHashMap<>();
        for (String name : headerNames) {
            headers.put(name, Collections.list(request.getHeaders(name)));
        }
        return headers;
    }

    static String sha256(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    static String firstNonBlank(String a, String b) {
        if (a != null && !a.isBlank()) return a;
        if (b != null && !b.isBlank()) return b;
        return null;
    }
}
