package poc.evidence;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpRequest;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.client.ClientHttpRequestExecution;
import org.springframework.http.client.ClientHttpRequestInterceptor;
import org.springframework.http.client.ClientHttpResponse;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * RestClient 외부 호출 — 재생 헤더 전파 + {@code externalCalls} 기록.
 *
 * <p>현재 요청에 ReplayContext가 있으면:
 * <ol>
 *   <li>자식 hopPath({@code <hopPath>.h<n>})를 정하고 재생 헤더 4개를 붙인다(호출 대상이 Evidence를 남기는 서비스면 그 키가 된다)
 *   <li>타임라인 seq를 호출 시작 시점에 받는다
 *   <li>응답 본문을 버퍼링해 해시하고, 같은 바이트를 호출자에게 돌려준다
 * </ol>
 * 기록: {@code {seq, method, host, path, requestBodyHash, status, responseBodyHash, childHopPath}}.
 * I/O 예외면 status 0, 응답 해시는 빈 바이트열로 기록하고 예외를 그대로 던진다.
 */
class ReplayPropagatingInterceptor implements ClientHttpRequestInterceptor {

    @Override
    public ClientHttpResponse intercept(HttpRequest request, byte[] body, ClientHttpRequestExecution execution)
            throws IOException {
        ReplayContext context = ReplayContext.current().orElse(null);
        if (context == null) {
            return execution.execute(request, body);
        }
        String childHop = context.nextHttpChildHop();
        HttpHeaders headers = request.getHeaders();
        headers.set(EvidenceFilter.REPLAY_REQUEST_ID_HEADER, context.replayRequestId());
        headers.set(EvidenceFilter.RUN_ID_HEADER, context.runId());
        headers.set(EvidenceFilter.SESSION_ID_HEADER, context.sessionId());
        headers.set(EvidenceFilter.HOP_PATH_HEADER, childHop);

        Map<String, Object> call = new LinkedHashMap<>();
        call.put("seq", context.nextSeq());
        call.put("method", request.getMethod().name());
        call.put("host", request.getURI().getHost());
        call.put("path", request.getURI().getRawPath());
        call.put("requestBodyHash", EvidenceFilter.sha256(body));
        try {
            ClientHttpResponse response = execution.execute(request, body);
            byte[] responseBody;
            try (InputStream in = response.getBody()) {
                responseBody = in.readAllBytes();
            }
            call.put("status", response.getStatusCode().value());
            call.put("responseBodyHash", EvidenceFilter.sha256(responseBody));
            call.put("childHopPath", childHop);
            context.recordExternalCall(call);
            return new BufferedResponse(response, responseBody);
        } catch (IOException e) {
            call.put("status", 0);
            call.put("responseBodyHash", EvidenceFilter.sha256(new byte[0]));
            call.put("childHopPath", childHop);
            context.recordExternalCall(call);
            throw e;
        }
    }

    /** 읽어 둔 본문을 다시 제공하는 응답 래퍼. */
    private static final class BufferedResponse implements ClientHttpResponse {
        private final ClientHttpResponse delegate;
        private final byte[] body;

        BufferedResponse(ClientHttpResponse delegate, byte[] body) {
            this.delegate = delegate;
            this.body = body;
        }

        @Override
        public HttpStatusCode getStatusCode() throws IOException {
            return delegate.getStatusCode();
        }

        @Override
        public String getStatusText() throws IOException {
            return delegate.getStatusText();
        }

        @Override
        public HttpHeaders getHeaders() {
            return delegate.getHeaders();
        }

        @Override
        public InputStream getBody() {
            return new ByteArrayInputStream(body);
        }

        @Override
        public void close() {
            delegate.close();
        }
    }
}
