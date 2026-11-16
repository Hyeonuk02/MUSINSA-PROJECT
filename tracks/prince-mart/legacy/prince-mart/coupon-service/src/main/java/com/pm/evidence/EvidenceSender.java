package com.pm.evidence;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

/**
 * [LEGACY_CHANGES L-I2] Evidence를 Evidence Store로 비동기 POST한다.
 *
 * <p>요청 스레드는 큐에 넣기만 한다(처리 시간에 POST가 섞이지 않음). 전송은 기동 시 만든 전용 스레드 하나가 한다.
 * OTel agent는 ExecutorService로 넘긴 작업에는 trace context를 이어 주지만 큐를 거친 작업에는 잇지 않는다.
 * 그래서 Store POST는 비즈니스 trace에 붙지 않고 별도 trace가 된다(OTel API 없이, compose·k8s에서 같은 결과).
 * Store POST에는 {@code X-Evidence-Internal: true}를 붙인다(v10.1 §5.1).
 */
public final class EvidenceSender {

    private final BlockingQueue<String> queue = new LinkedBlockingQueue<>(100_000);
    private final HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();
    private final URI endpoint;
    private final Thread worker;
    private volatile boolean running = true;

    EvidenceSender(String storeUrl) {
        this.endpoint = URI.create(storeUrl.replaceAll("/+$", "") + "/evidence");
        this.worker = new Thread(this::loop, "evidence-sender");
        this.worker.setDaemon(true);
        this.worker.start();
    }

    void submit(String json) {
        if (!queue.offer(json)) {
            System.err.println("EVIDENCE_DROPPED queue full");
        }
    }

    private void loop() {
        while (running || !queue.isEmpty()) {
            try {
                String json = queue.poll(500, TimeUnit.MILLISECONDS);
                if (json != null) post(json);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
        }
    }

    private void post(String json) throws InterruptedException {
        HttpRequest req = HttpRequest.newBuilder(endpoint)
                .timeout(Duration.ofSeconds(5))
                .header("Content-Type", "application/json")
                .header("X-Evidence-Internal", "true")
                .POST(HttpRequest.BodyPublishers.ofString(json, StandardCharsets.UTF_8))
                .build();
        for (int attempt = 1; attempt <= 5; attempt++) {
            try {
                HttpResponse<Void> res = client.send(req, HttpResponse.BodyHandlers.discarding());
                if (res.statusCode() / 100 == 2) return;
                System.err.println("EVIDENCE_POST_FAILED status=" + res.statusCode() + " attempt=" + attempt);
            } catch (java.io.IOException e) {
                System.err.println("EVIDENCE_POST_FAILED " + e + " attempt=" + attempt);
            }
            Thread.sleep(200L * attempt);
        }
        System.err.println("EVIDENCE_DROPPED after retries");
    }

    void shutdown() {
        running = false;
        try {
            worker.join(5_000);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
