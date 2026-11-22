package poc.evidence;

import feign.Client;
import feign.Feign;
import feign.FeignException;
import feign.Headers;
import feign.Param;
import feign.Request;
import feign.RequestLine;
import feign.Response;
import feign.Retryer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

/**
 * Feign 경로(FeignEvidenceCapability) 단위 테스트와 RestClient 경로(ReplayPropagatingInterceptor) 동형 대조.
 * 로드밸런서 없는 Feign으로 같은 URL을 호출하므로 host까지 같아야 한다.
 */
class FeignEvidenceCapabilityTest {

    static final String BASE = "http://coupon-service";
    static final String VALIDATE_BODY = "{\"code\":\"WELCOME10\",\"amount\":12000}";
    static final String VALIDATE_RESPONSE = "{\"valid\":true,\"discount\":1200}";

    interface CouponApi {
        @RequestLine("POST /coupons/validate")
        @Headers("Content-Type: application/json")
        String validate(String body);

        @RequestLine("GET /coupons/{code}")
        String get(@Param("code") String code);

        @RequestLine("GET /coupons/{code}")
        @Headers("X-Replay-Hop-Path: stale")
        String getWithStaleHop(@Param("code") String code);
    }

    /** 받은 요청을 모아 두고 정해진 응답을 돌려주는 가짜 Client. */
    static final class StubClient implements Client {
        final List<Request> received = new ArrayList<>();
        final int status;
        final String body;

        StubClient(int status, String body) {
            this.status = status;
            this.body = body;
        }

        @Override
        public Response execute(Request request, Request.Options options) {
            received.add(request);
            Response.Builder builder = Response.builder().status(status).reason("stub").request(request)
                    .headers(Map.of("Content-Type", List.of("application/json")));
            if (body != null) {
                builder.body(body, StandardCharsets.UTF_8);
            }
            return builder.build();
        }
    }

    static CouponApi feign(Client client) {
        return Feign.builder()
                .addCapability(new FeignEvidenceCapability())
                .client(client)
                .retryer(Retryer.NEVER_RETRY)
                .target(CouponApi.class, BASE);
    }

    static ReplayContext open() {
        return ReplayContext.open("R000001", "run-test", "S01", "0");
    }

    @AfterEach
    void cleanup() {
        ReplayContext.current().ifPresent(ReplayContext::close);
    }

    static String single(Request request, String name) {
        Collection<String> values = request.headers().get(name);
        assertThat(values).as(name).hasSize(1);
        return values.iterator().next();
    }

    // ---------------------------------------------------------------- Feign 경로

    @Test
    void propagatesReplayHeadersAndRecordsExternalCalls() {
        StubClient stub = new StubClient(200, VALIDATE_RESPONSE);
        CouponApi api = feign(stub);
        ReplayContext context = open();

        String first = api.validate(VALIDATE_BODY);
        String second = api.get("WELCOME10");
        List<Map<String, Object>> calls = context.close().externalCalls();

        // 디코더가 버퍼링된 본문을 그대로 읽는다
        assertThat(first).isEqualTo(VALIDATE_RESPONSE);
        assertThat(second).isEqualTo(VALIDATE_RESPONSE);

        // 헤더 전파: 재생 헤더 4개 + 호출 순번별 자식 hopPath
        assertThat(stub.received).hasSize(2);
        for (Request r : stub.received) {
            assertThat(single(r, "X-Replay-Request-Id")).isEqualTo("R000001");
            assertThat(single(r, "X-Run-Id")).isEqualTo("run-test");
            assertThat(single(r, "X-Session-Id")).isEqualTo("S01");
        }
        assertThat(single(stub.received.get(0), "X-Replay-Hop-Path")).isEqualTo("0.h1");
        assertThat(single(stub.received.get(1), "X-Replay-Hop-Path")).isEqualTo("0.h2");
        // 앱이 붙인 헤더와 원래 requestTemplate은 유지된다
        assertThat(single(stub.received.get(0), "Content-Type")).isEqualTo("application/json");
        assertThat(stub.received.get(0).requestTemplate()).isNotNull();

        // externalCalls: 키 순서와 값
        assertThat(calls).hasSize(2);
        assertThat(calls.get(0).keySet()).containsExactly(
                "seq", "method", "host", "path", "requestBodyHash", "status", "responseBodyHash", "childHopPath");
        assertThat(calls.get(0)).containsEntry("seq", 1).containsEntry("method", "POST")
                .containsEntry("host", "coupon-service").containsEntry("path", "/coupons/validate")
                .containsEntry("requestBodyHash", EvidenceWriter.sha256(VALIDATE_BODY.getBytes(StandardCharsets.UTF_8)))
                .containsEntry("status", 200)
                .containsEntry("responseBodyHash", EvidenceWriter.sha256(VALIDATE_RESPONSE.getBytes(StandardCharsets.UTF_8)))
                .containsEntry("childHopPath", "0.h1");
        assertThat(calls.get(1)).containsEntry("seq", 2).containsEntry("method", "GET")
                .containsEntry("path", "/coupons/WELCOME10")
                .containsEntry("requestBodyHash", EvidenceWriter.sha256(new byte[0]))
                .containsEntry("childHopPath", "0.h2");
    }

    @Test
    void sharesTimelineSeqWithOtherEvidence() {
        CouponApi api = feign(new StubClient(200, VALIDATE_RESPONSE));
        ReplayContext context = open();
        context.recordStatement("select 1");     // seq 1
        api.get("A");                             // seq 2
        context.recordStatement("select 2");     // seq 3
        ReplayContext.Captured captured = context.close();
        assertThat(captured.externalCalls().get(0)).containsEntry("seq", 2);
    }

    @Test
    void replacesExistingReplayHeader() {
        StubClient stub = new StubClient(200, "{}");
        CouponApi api = feign(stub);
        ReplayContext context = open();
        api.getWithStaleHop("A");
        context.close();
        assertThat(single(stub.received.get(0), "X-Replay-Hop-Path")).isEqualTo("0.h1");
    }

    @Test
    void passesThroughWithoutReplayContext() {
        StubClient stub = new StubClient(200, "{}");
        feign(stub).get("A");
        Request r = stub.received.get(0);
        assertThat(r.headers()).doesNotContainKeys("X-Replay-Request-Id", "X-Run-Id", "X-Session-Id", "X-Replay-Hop-Path");
    }

    @Test
    void recordsErrorStatusBeforeFeignDecodesIt() {
        CouponApi api = feign(new StubClient(404, "{\"message\":\"not found\"}"));
        ReplayContext context = open();
        assertThatThrownBy(() -> api.get("NONE")).isInstanceOf(FeignException.NotFound.class);
        List<Map<String, Object>> calls = context.close().externalCalls();
        assertThat(calls).singleElement().satisfies(c -> assertThat(c).containsEntry("status", 404)
                .containsEntry("responseBodyHash",
                        EvidenceWriter.sha256("{\"message\":\"not found\"}".getBytes(StandardCharsets.UTF_8))));
    }

    @Test
    void bodylessResponseIsReturnedAsIs() throws IOException {
        StubClient stub = new StubClient(204, null);
        Client client = new FeignEvidenceCapability().enrich(stub);
        ReplayContext context = open();
        Request request = Request.create(Request.HttpMethod.DELETE, BASE + "/coupons/A", Map.of(), null,
                StandardCharsets.UTF_8, null);
        Response response = client.execute(request, new Request.Options());
        List<Map<String, Object>> calls = context.close().externalCalls();
        assertThat(response.body()).isNull();
        assertThat(calls.get(0)).containsEntry("status", 204)
                .containsEntry("responseBodyHash", EvidenceWriter.sha256(new byte[0]));
    }

    @Test
    void ioExceptionRecordsStatusZeroAndRethrows() {
        Client failing = (request, options) -> {
            throw new IOException("connection refused");
        };
        Client client = new FeignEvidenceCapability().enrich(failing);
        ReplayContext context = open();
        Request request = Request.create(Request.HttpMethod.GET, BASE + "/coupons/A", Map.of(), null,
                StandardCharsets.UTF_8, null);
        assertThatThrownBy(() -> client.execute(request, new Request.Options()))
                .isInstanceOf(IOException.class).hasMessage("connection refused");
        List<Map<String, Object>> calls = context.close().externalCalls();
        assertThat(calls).singleElement().satisfies(c -> assertThat(c).containsEntry("status", 0)
                .containsEntry("responseBodyHash", EvidenceWriter.sha256(new byte[0]))
                .containsEntry("childHopPath", "0.h1"));
    }

    // ---------------------------------------------------------------- RestClient 경로와 동형 대조

    /** 같은 호출 순서(POST 200 -> GET 200 -> GET 404)를 RestClient 경로로. */
    static List<Map<String, Object>> viaRestClient() {
        RestClient.Builder builder = RestClient.builder().requestInterceptor(new ReplayPropagatingInterceptor());
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        RestClient client = builder.baseUrl(BASE).build();
        server.expect(requestTo(BASE + "/coupons/validate")).andExpect(method(HttpMethod.POST))
                .andExpect(header("X-Replay-Hop-Path", "0.h1"))
                .andRespond(withSuccess(VALIDATE_RESPONSE, MediaType.APPLICATION_JSON));
        server.expect(requestTo(BASE + "/coupons/WELCOME10")).andExpect(header("X-Replay-Hop-Path", "0.h2"))
                .andRespond(withSuccess(VALIDATE_RESPONSE, MediaType.APPLICATION_JSON));
        server.expect(requestTo(BASE + "/coupons/NONE")).andExpect(header("X-Replay-Hop-Path", "0.h3"))
                .andRespond(withStatus(HttpStatus.NOT_FOUND).contentType(MediaType.APPLICATION_JSON)
                        .body("{\"message\":\"not found\"}"));

        ReplayContext context = open();
        client.post().uri("/coupons/validate").contentType(MediaType.APPLICATION_JSON).body(VALIDATE_BODY)
                .retrieve().body(String.class);
        client.get().uri("/coupons/{code}", "WELCOME10").retrieve().body(String.class);
        assertThatThrownBy(() -> client.get().uri("/coupons/{code}", "NONE").retrieve().body(String.class))
                .isInstanceOf(RestClientResponseException.class);
        List<Map<String, Object>> calls = context.close().externalCalls();
        server.verify();
        return calls;
    }

    /** 같은 호출 순서를 Feign 경로로(로드밸런서 없음, 같은 URL). */
    static List<Map<String, Object>> viaFeign() {
        Client stub = (request, options) -> {
            boolean notFound = request.url().endsWith("/NONE");
            return Response.builder().status(notFound ? 404 : 200).reason("stub").request(request)
                    .headers(Map.of("Content-Type", List.of("application/json")))
                    .body(notFound ? "{\"message\":\"not found\"}" : VALIDATE_RESPONSE, StandardCharsets.UTF_8)
                    .build();
        };
        CouponApi api = feign(stub);
        ReplayContext context = open();
        api.validate(VALIDATE_BODY);
        api.get("WELCOME10");
        assertThatThrownBy(() -> api.get("NONE")).isInstanceOf(FeignException.NotFound.class);
        return context.close().externalCalls();
    }

    @Test
    void feignAndRestClientLeaveIdenticalExternalCalls() {
        List<Map<String, Object>> rest = viaRestClient();
        List<Map<String, Object>> feign = viaFeign();
        assertThat(feign).hasSize(3);
        for (int i = 0; i < rest.size(); i++) {
            assertThat(List.copyOf(feign.get(i).keySet())).as("키 순서 #%d", i)
                    .isEqualTo(List.copyOf(rest.get(i).keySet()));
        }
        assertThat(feign).isEqualTo(rest);
    }
}
