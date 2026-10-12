package poc.evidence;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.SmartLifecycle;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Duration;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;

/**
 * 완성된 Evidence 바이트를 Store로 비동기 POST한다. <b>유실 금지</b>: 버리지 않고 로컬에 spill한다.
 *
 * <ul>
 *   <li>클라이언트는 {@code java.net.http.HttpClient}. OTel agent에서 이 계측만 꺼서
 *       ({@code OTEL_INSTRUMENTATION_JAVA_HTTP_CLIENT_ENABLED=false}) 앱 span에 섞이지 않는다
 *   <li>실패 시 재시도 3회(0.5s/1s/1.5s 뒤). 재시도는 스레드에서 잠들지 않고 예약한다 —
 *       Store 장애 중에도 뒤에 들어온 Evidence가 앞 건의 재시도 대기에 막히지 않게
 *   <li>재시도 소진, 대기 건수 상한(1000) 초과, 종료 시 미전송분은
 *       {@code <spillDir>/<runId>/<replayRequestId>-<stack>.json}에 Store로 보낼 바이트 그대로 쓴다.
 *       spill마저 실패할 때만 EVIDENCE_LOST 로그(마지막 수단)
 *   <li>종료: 웹 서버가 요청을 다 처리하고 멈춘 뒤(낮은 phase) 최대 10초 drain, 남은 것은 spill
 *   <li>EVIDENCE_DELAY_MS(기본 0): 첫 POST를 그만큼 늦게 예약한다. k6 완료 폴링이 실제로 기다리는지 보는 검증용이며
 *       평소에는 어떤 overlay에도 설정하지 않는다
 * </ul>
 *
 * <p>executor는 바이트만 다룬다. ReplayContext 같은 요청 스레드 상태는 넘겨받지 않는다.
 */
public class EvidenceSender implements SmartLifecycle {

    static final String INTERNAL_HEADER = "X-Evidence-Internal";

    private static final Logger log = LoggerFactory.getLogger(EvidenceSender.class);
    private static final int MAX_PENDING = 1000;
    private static final long[] RETRY_DELAYS_MS = {500, 1000, 1500};
    private static final Duration CONNECT_TIMEOUT = Duration.ofSeconds(2);
    private static final Duration REQUEST_TIMEOUT = Duration.ofSeconds(5);
    private static final long DRAIN_TIMEOUT_SECONDS = 10;
    /** Store가 디렉터리 이름으로 쓰는 규칙과 같다. 이 밖의 runId는 경로로 쓰지 않는다. */
    private static final Pattern SAFE_SEGMENT = Pattern.compile("^[A-Za-z0-9._-]{1,128}$");

    private final URI endpoint;
    private final Path spillDir;
    private final long delayMs;
    private final HttpClient client = HttpClient.newBuilder().connectTimeout(CONNECT_TIMEOUT).build();
    private final Semaphore permits = new Semaphore(MAX_PENDING);
    /** 아직 Store에도 spill에도 가지 않은 건. 종료 시 drain 시간을 넘기면 여기 남은 것을 spill한다. */
    private final Set<Payload> pending = ConcurrentHashMap.newKeySet();
    private final ScheduledThreadPoolExecutor executor = new ScheduledThreadPoolExecutor(1, runnable -> {
        Thread thread = new Thread(runnable, "evidence-sender");
        thread.setDaemon(true);
        return thread;
    });
    private volatile boolean running;

    public EvidenceSender(String storeUrl, Path spillDir, long delayMs) {
        this.endpoint = URI.create(storeUrl.replaceAll("/+$", "") + "/evidence");
        this.spillDir = spillDir;
        this.delayMs = delayMs;
    }

    /** 요청 스레드에서 호출한다. 대기 건수 상한이면 그 자리에서 spill한다(블로킹 POST는 하지 않음). */
    void enqueue(String runId, String replayRequestId, String stack, byte[] evidence) {
        Payload payload = new Payload(runId, replayRequestId, stack, evidence);
        if (!permits.tryAcquire()) {
            spill(payload, "queue full");
            return;
        }
        pending.add(payload);
        try {
            if (delayMs > 0) {
                executor.schedule(new Attempt(payload, 0), delayMs, TimeUnit.MILLISECONDS);
            } else {
                executor.execute(new Attempt(payload, 0));
            }
        } catch (RejectedExecutionException e) {
            done(payload, "sender stopped");
        }
    }

    /** Store로 보낼 바이트와 spill 경로를 정하는 키. 식별은 객체 동일성. */
    private record Payload(String runId, String replayRequestId, String stack, byte[] evidence) {
        String label() {
            return runId + "/" + replayRequestId + "/" + stack;
        }

        @Override
        public boolean equals(Object other) {
            return this == other;
        }

        @Override
        public int hashCode() {
            return System.identityHashCode(this);
        }
    }

    /** 한 건을 끝낸다. spillReason이 null이면 전송 성공. pending에서 처음 빠질 때만 spill·permit 반환(중복 방지). */
    private void done(Payload payload, String spillReason) {
        if (!pending.remove(payload)) {
            return;
        }
        try {
            if (spillReason != null) {
                spill(payload, spillReason);
            }
        } finally {
            permits.release();
        }
    }

    private final class Attempt implements Runnable {
        final Payload payload;
        final int retry;

        Attempt(Payload payload, int retry) {
            this.payload = payload;
            this.retry = retry;
        }

        @Override
        public void run() {
            String failure;
            try {
                failure = post(payload.evidence());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                done(payload, "interrupted during shutdown");
                return;
            }
            if (failure == null) {
                done(payload, null);
                return;
            }
            if (retry >= RETRY_DELAYS_MS.length) {
                done(payload, "retries exhausted: " + failure);
                return;
            }
            log.info("EVIDENCE_RETRY {} #{} in {}ms: {}", payload.label(), retry + 1, RETRY_DELAYS_MS[retry], failure);
            try {
                executor.schedule(new Attempt(payload, retry + 1), RETRY_DELAYS_MS[retry], TimeUnit.MILLISECONDS);
            } catch (RejectedExecutionException e) {
                done(payload, "sender stopped: " + failure);
            }
        }
    }

    /** 성공이면 null, 실패면 사유. */
    private String post(byte[] evidence) throws InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(endpoint)
                .timeout(REQUEST_TIMEOUT)
                .header("Content-Type", "application/json")
                .header(INTERNAL_HEADER, "true")
                .POST(HttpRequest.BodyPublishers.ofByteArray(evidence))
                .build();
        try {
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
            return response.statusCode() == 200 ? null : "status=" + response.statusCode() + " body=" + response.body();
        } catch (IOException e) {
            return e.toString();
        }
    }

    private void spill(Payload payload, String reason) {
        if (!SAFE_SEGMENT.matcher(payload.runId()).matches() || !SAFE_SEGMENT.matcher(payload.replayRequestId()).matches()
                || !SAFE_SEGMENT.matcher(payload.stack()).matches()) {
            log.error("EVIDENCE_LOST {} unsafe path segment ({})", payload.label(), reason);
            return;
        }
        try {
            Path dir = Files.createDirectories(spillDir.resolve(payload.runId()));
            Path target = dir.resolve(payload.replayRequestId() + "-" + payload.stack() + ".json");
            Path tmp = Files.createTempFile(dir, ".spill-", ".tmp");
            Files.write(tmp, payload.evidence());
            Files.move(tmp, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
            log.warn("EVIDENCE_SPILLED {} -> {} ({})", payload.label(), target, reason);
        } catch (IOException | RuntimeException e) {
            log.error("EVIDENCE_LOST {} spill failed: {} ({})", payload.label(), e, reason);
        }
    }

    @Override
    public void start() {
        running = true;
    }

    /**
     * 웹 서버 graceful shutdown(요청 처리 완료)과 정지보다 뒤에 멈춘다 — 그때까지 들어온 Evidence가 모두 큐에 있다.
     * 최대 10초 동안 전송·재시도를 계속하고, 남은 건은 spill한다.
     */
    @Override
    public void stop() {
        running = false;
        executor.shutdown();  // 예약된 재시도는 shutdown 뒤에도 실행된다(기본 정책)
        try {
            if (!executor.awaitTermination(DRAIN_TIMEOUT_SECONDS, TimeUnit.SECONDS)) {
                executor.shutdownNow();  // 실행 중인 POST는 interrupt → 스스로 spill
                executor.awaitTermination(5, TimeUnit.SECONDS);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        for (Payload payload : Set.copyOf(pending)) {
            done(payload, "shutdown drain timeout");
        }
        log.info("EVIDENCE_SENDER_STOPPED in-flight={}", MAX_PENDING - permits.availablePermits());
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        // WebServerGracefulShutdownLifecycle(DEFAULT_PHASE - 1024), WebServerStartStopLifecycle(DEFAULT_PHASE - 2048)
        // 보다 낮게 — stop은 phase 내림차순이므로 웹 서버가 멈춘 뒤에 drain한다.
        return SmartLifecycle.DEFAULT_PHASE - 4096;
    }
}
