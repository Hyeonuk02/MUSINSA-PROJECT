package poc.evidence;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.DisposableBean;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

/**
 * 완성된 Evidence 바이트를 Store로 비동기 POST한다.
 *
 * <p>클라이언트는 {@code java.net.http.HttpClient}다. OTel agent에서 이 계측만 끄면
 * ({@code OTEL_INSTRUMENTATION_JAVA_HTTP_CLIENT_ENABLED=false}) 앱 span에 Evidence POST가 섞이지 않는다.
 * 비즈니스 외부 호출(WireMock)은 RestClient라 계속 계측된다.
 *
 * <p>executor는 POST만 한다. ReplayContext 같은 요청 스레드 상태는 넘겨받지 않는다.
 * Phase 2.4a: 실패·큐 초과는 로그만 남긴다(재시도·spill·종료 시 flush는 2.4b).
 */
public class EvidenceSender implements DisposableBean {

    static final String INTERNAL_HEADER = "X-Evidence-Internal";

    private static final Logger log = LoggerFactory.getLogger(EvidenceSender.class);
    private static final int QUEUE_CAPACITY = 1000;
    private static final Duration CONNECT_TIMEOUT = Duration.ofSeconds(2);
    private static final Duration REQUEST_TIMEOUT = Duration.ofSeconds(5);

    private final URI endpoint;
    private final HttpClient client = HttpClient.newBuilder().connectTimeout(CONNECT_TIMEOUT).build();
    private final ThreadPoolExecutor executor = new ThreadPoolExecutor(
            1, 1, 0L, TimeUnit.MILLISECONDS, new ArrayBlockingQueue<>(QUEUE_CAPACITY),
            runnable -> {
                Thread thread = new Thread(runnable, "evidence-sender");
                thread.setDaemon(true);
                return thread;
            });

    public EvidenceSender(String storeUrl) {
        this.endpoint = URI.create(storeUrl.replaceAll("/+$", "") + "/evidence");
    }

    /** 요청 스레드에서 호출한다. 블로킹하지 않는다. */
    void enqueue(String label, byte[] evidence) {
        try {
            executor.execute(() -> post(label, evidence));
        } catch (RejectedExecutionException e) {
            log.warn("EVIDENCE_DROPPED queue full: {}", label);
        }
    }

    private void post(String label, byte[] evidence) {
        HttpRequest request = HttpRequest.newBuilder(endpoint)
                .timeout(REQUEST_TIMEOUT)
                .header("Content-Type", "application/json")
                .header(INTERNAL_HEADER, "true")
                .POST(HttpRequest.BodyPublishers.ofByteArray(evidence))
                .build();
        try {
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() != 200) {
                log.warn("EVIDENCE_POST_FAILED {} status={} body={}", label, response.statusCode(), response.body());
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            log.warn("EVIDENCE_POST_FAILED {} interrupted", label);
        } catch (Exception e) {
            log.warn("EVIDENCE_POST_FAILED {} {}", label, e.toString());
        }
    }

    @Override
    public void destroy() throws InterruptedException {
        executor.shutdown();
        executor.awaitTermination(5, TimeUnit.SECONDS);
    }
}
