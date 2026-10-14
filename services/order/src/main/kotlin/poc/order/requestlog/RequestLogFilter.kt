package poc.order.requestlog

import jakarta.servlet.FilterChain
import jakarta.servlet.http.HttpServletRequest
import jakarta.servlet.http.HttpServletResponse
import org.slf4j.LoggerFactory
import org.springframework.beans.factory.annotation.Value
import org.springframework.core.Ordered
import org.springframework.core.annotation.Order
import org.springframework.stereotype.Component
import org.springframework.web.filter.OncePerRequestFilter
import tools.jackson.databind.json.JsonMapper
import java.security.MessageDigest
import java.util.Collections
import java.util.HexFormat
import java.util.concurrent.atomic.AtomicLong

/**
 * Phase 0 요청 로그. 요청 1건당 "REQUEST_LOG {json}" 한 줄을 남긴다.
 *
 * arrivedAt/completedAt은 epoch ms, arrivedAtNano/completedAtNano는 같은 JVM 안에서만
 * 비교 가능한 System.nanoTime 값이다 (직렬 판정용).
 *
 * Phase 3.5-v1.4: Java → Kotlin 전환.
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
class RequestLogFilter(@Value("\${request-log.headers}") headerNames: List<String>) : OncePerRequestFilter() {

    private val sequence = AtomicLong()
    private val jsonMapper: JsonMapper = JsonMapper.builder().build()
    private val headerNames: List<String> = headerNames.toList()

    override fun doFilterInternal(request: HttpServletRequest, response: HttpServletResponse, chain: FilterChain) {
        val arrivedAt = System.currentTimeMillis()
        val arrivedAtNano = System.nanoTime()
        val seq = sequence.incrementAndGet()

        var forwarded: HttpServletRequest = request
        var bodyHash: String? = null
        if ("GET" != request.method) {
            // 프레임워크가 본문을 해석하기 전에 원시 바이트를 전부 읽어 해시하고, 같은 바이트를 다시 읽을 수 있게 넘긴다.
            val body = request.inputStream.readAllBytes()
            bodyHash = sha256Hex(body)
            forwarded = CachedBodyRequest(request, body)
        }

        try {
            chain.doFilter(forwarded, response)
        } finally {
            val completedAt = System.currentTimeMillis()
            val completedAtNano = System.nanoTime()

            val entry = linkedMapOf<String, Any?>(
                "requestId" to request.getHeader(REQUEST_ID_HEADER),
                "seq" to seq,
                "method" to request.method,
                "uri" to request.requestURI,
                "query" to (request.queryString ?: ""),
                "headers" to selectedHeaders(request),
                "bodyHash" to bodyHash,
                "arrivedAt" to arrivedAt,
                "completedAt" to completedAt,
                "arrivedAtNano" to arrivedAtNano,
                "completedAtNano" to completedAtNano,
            )
            log.info("REQUEST_LOG {}", jsonMapper.writeValueAsString(entry))
        }
    }

    private fun selectedHeaders(request: HttpServletRequest): Map<String, List<String>> =
        headerNames.associateWithTo(LinkedHashMap()) { Collections.list(request.getHeaders(it)) }

    companion object {
        const val REQUEST_ID_HEADER = "X-Replay-Request-Id"
        private val log = LoggerFactory.getLogger(RequestLogFilter::class.java)

        private fun sha256Hex(bytes: ByteArray): String =
            HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes))
    }
}
