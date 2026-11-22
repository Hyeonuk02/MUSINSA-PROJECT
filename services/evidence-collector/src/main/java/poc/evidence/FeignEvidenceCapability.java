package poc.evidence;

import feign.Capability;
import feign.Client;
import feign.Request;
import feign.Response;

import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/**
 * Feign 외부 호출 — 재생 헤더 전파 + {@code externalCalls} 기록. {@link ReplayPropagatingInterceptor}(RestClient)와
 * 같은 일을 Feign 호출에서 한다. 두 경로가 남기는 항목은 키와 순서, 값의 규칙이 같다(FeignEvidenceCapabilityTest가 대조).
 *
 * <p>Feign {@code RequestInterceptor}는 응답을 보지 못하므로 {@link Capability#enrich(Client)}로 Client를 감싼다.
 * Spring Cloud OpenFeign은 컨텍스트의 Capability 빈을 모든 Feign 클라이언트에 붙이고, 로드밸런서 클라이언트를 바깥에서 감싼다.
 * 그래서 이 래퍼가 보는 URL은 주소가 풀리기 전의 논리 이름이다({@code http://COUPON-SERVICE/coupons/validate} -> host
 * {@code COUPON-SERVICE}). RestClient 경로는 실제 URI host를 기록한다.
 *
 * <p>현재 스레드에 ReplayContext가 있으면:
 * <ol>
 *   <li>자식 hopPath({@code <hopPath>.h<n>})를 정하고 재생 헤더 4개를 교체한 새 Request를 만든다(원래 requestTemplate 유지)
 *   <li>타임라인 seq를 호출 시작 시점에 받는다
 *   <li>응답 본문을 버퍼링해 해시하고, 같은 바이트를 호출자에게 돌려준다(본문이 없는 응답은 그대로 돌려준다)
 * </ol>
 * 기록: {@code {seq, method, host, path, requestBodyHash, status, responseBodyHash, childHopPath}}.
 * I/O 예외면 status 0, 응답 해시는 빈 바이트열로 기록하고 예외를 그대로 던진다.
 *
 * <p>public이어야 한다 — Feign이 {@code enrich}를 리플렉션으로 호출한다(package-private이면 IllegalAccessException).
 */
public class FeignEvidenceCapability implements Capability {

    @Override
    public Client enrich(Client client) {
        return new EvidenceClient(client);
    }

    static final class EvidenceClient implements Client {
        private final Client delegate;

        EvidenceClient(Client delegate) {
            this.delegate = delegate;
        }

        @Override
        public Response execute(Request request, Request.Options options) throws IOException {
            ReplayContext context = ReplayContext.current().orElse(null);
            if (context == null) {
                return delegate.execute(request, options);
            }
            String childHop = context.nextHttpChildHop();
            Map<String, Collection<String>> headers = new TreeMap<>(String.CASE_INSENSITIVE_ORDER);
            headers.putAll(request.headers());
            headers.put(EvidenceFilter.REPLAY_REQUEST_ID_HEADER, List.of(context.replayRequestId()));
            headers.put(EvidenceFilter.RUN_ID_HEADER, List.of(context.runId()));
            headers.put(EvidenceFilter.SESSION_ID_HEADER, List.of(context.sessionId()));
            headers.put(EvidenceFilter.HOP_PATH_HEADER, List.of(childHop));
            Request propagated = Request.create(request.httpMethod(), request.url(), headers, request.body(),
                    request.charset(), request.requestTemplate());

            byte[] body = request.body() == null ? new byte[0] : request.body();
            URI uri = URI.create(request.url());
            Map<String, Object> call = new LinkedHashMap<>();
            call.put("seq", context.nextSeq());
            call.put("method", request.httpMethod().name());
            call.put("host", uri.getHost());
            call.put("path", uri.getRawPath());
            call.put("requestBodyHash", EvidenceWriter.sha256(body));
            try {
                Response response = delegate.execute(propagated, options);
                byte[] responseBody;
                Response returned;
                if (response.body() == null) {
                    responseBody = new byte[0];
                    returned = response;
                } else {
                    try (InputStream in = response.body().asInputStream()) {
                        responseBody = in.readAllBytes();
                    } finally {
                        response.close();
                    }
                    returned = response.toBuilder().body(responseBody).build();
                }
                call.put("status", response.status());
                call.put("responseBodyHash", EvidenceWriter.sha256(responseBody));
                call.put("childHopPath", childHop);
                context.recordExternalCall(call);
                return returned;
            } catch (IOException e) {
                call.put("status", 0);
                call.put("responseBodyHash", EvidenceWriter.sha256(new byte[0]));
                call.put("childHopPath", childHop);
                context.recordExternalCall(call);
                throw e;
            }
        }
    }
}
