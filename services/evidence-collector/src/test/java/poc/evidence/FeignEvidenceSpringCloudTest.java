package poc.evidence;

import com.sun.net.httpserver.HttpServer;
import feign.RequestInterceptor;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.openfeign.EnableFeignClients;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.context.annotation.Bean;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

import java.io.IOException;
import java.io.OutputStream;
import java.io.UncheckedIOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Prince Mart와 같은 구성 — Spring Cloud OpenFeign + LoadBalancer + simple discovery(Eureka 끔) — 에서
 * 자동 구성된 Capability가 Feign 클라이언트에 붙는지, 기록되는 host가 논리 서비스 이름인지 확인한다.
 * 앱의 RequestInterceptor(coupon FeignConfig의 X-User-Id 전달과 같은 것)와도 함께 동작해야 한다.
 */
@SpringBootTest(classes = FeignEvidenceSpringCloudTest.App.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = {
                "EVIDENCE_STORE_URL=http://evidence-store.invalid",
                "spring.autoconfigure.exclude="
                        + "poc.evidence.EvidenceAutoConfiguration,"
                        + "org.springframework.boot.jdbc.autoconfigure.DataSourceAutoConfiguration,"
                        + "org.springframework.boot.hibernate.autoconfigure.HibernateJpaAutoConfiguration,"
                        + "org.springframework.boot.kafka.autoconfigure.KafkaAutoConfiguration"
        })
class FeignEvidenceSpringCloudTest {

    record Received(String method, String path, Map<String, List<String>> headers, String body) {
    }

    static final List<Received> RECEIVED = new CopyOnWriteArrayList<>();
    static final HttpServer SERVER = startServer();

    static HttpServer startServer() {
        try {
            HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/", exchange -> {
                String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
                RECEIVED.add(new Received(exchange.getRequestMethod(), exchange.getRequestURI().getRawPath(),
                        Map.copyOf(exchange.getRequestHeaders()), body));
                byte[] response = "{\"valid\":true}".getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().add("Content-Type", "application/json");
                exchange.sendResponseHeaders(200, response.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(response);
                }
            });
            server.start();
            return server;
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    @DynamicPropertySource
    static void discovery(DynamicPropertyRegistry registry) {
        registry.add("spring.cloud.discovery.client.simple.instances.COUPON-SERVICE[0].uri",
                () -> "http://127.0.0.1:" + SERVER.getAddress().getPort());
    }

    @AfterAll
    static void stopServer() {
        SERVER.stop(0);
    }

    @FeignClient(name = "COUPON-SERVICE")
    interface CouponClient {
        @PostMapping(value = "/coupons/validate", consumes = "application/json")
        String validate(@RequestBody String body);

        @GetMapping("/coupons/{code}")
        String get(@PathVariable("code") String code);
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableFeignClients(clients = CouponClient.class)
    static class App {
        /** 앱 쪽 RequestInterceptor — Prince Mart coupon FeignConfig처럼 헤더를 하나 붙인다. */
        @Bean
        RequestInterceptor userIdForwarder() {
            return template -> template.header("X-User-Id", "42");
        }
    }

    @Autowired
    CouponClient client;

    @BeforeEach
    void reset() {
        RECEIVED.clear();
    }

    @AfterEach
    void cleanup() {
        ReplayContext.current().ifPresent(ReplayContext::close);
    }

    @Test
    void capabilityWrapsLoadBalancedClientAndRecordsLogicalHost() {
        ReplayContext context = ReplayContext.open("R000007", "run-sc", "S03", "0.e1");
        String validated = client.validate("{\"code\":\"A\"}");
        String fetched = client.get("A");
        List<Map<String, Object>> calls = context.close().externalCalls();

        assertThat(validated).isEqualTo("{\"valid\":true}");
        assertThat(fetched).isEqualTo("{\"valid\":true}");

        // 서버(로드밸런서가 푼 실제 주소)가 받은 헤더
        assertThat(RECEIVED).hasSize(2);
        Received first = RECEIVED.get(0);
        assertThat(first.headers().get("X-replay-request-id")).containsExactly("R000007");
        assertThat(first.headers().get("X-run-id")).containsExactly("run-sc");
        assertThat(first.headers().get("X-session-id")).containsExactly("S03");
        assertThat(first.headers().get("X-replay-hop-path")).containsExactly("0.e1.h1");
        assertThat(first.headers().get("X-user-id")).containsExactly("42");
        assertThat(RECEIVED.get(1).headers().get("X-replay-hop-path")).containsExactly("0.e1.h2");

        // 기록: host는 주소가 풀리기 전의 논리 서비스 이름
        assertThat(calls).hasSize(2);
        assertThat(calls.get(0)).containsEntry("method", "POST").containsEntry("host", "COUPON-SERVICE")
                .containsEntry("path", "/coupons/validate").containsEntry("status", 200)
                .containsEntry("requestBodyHash", EvidenceWriter.sha256("{\"code\":\"A\"}".getBytes(StandardCharsets.UTF_8)))
                .containsEntry("responseBodyHash", EvidenceWriter.sha256("{\"valid\":true}".getBytes(StandardCharsets.UTF_8)))
                .containsEntry("childHopPath", "0.e1.h1");
        assertThat(calls.get(1)).containsEntry("method", "GET").containsEntry("host", "COUPON-SERVICE")
                .containsEntry("path", "/coupons/A").containsEntry("childHopPath", "0.e1.h2");
    }

    @Test
    void noReplayContextMeansNoReplayHeaders() {
        client.get("A");
        assertThat(RECEIVED.get(0).headers()).doesNotContainKeys("X-replay-request-id", "X-replay-hop-path");
        assertThat(RECEIVED.get(0).headers().get("X-user-id")).containsExactly("42");
    }
}
