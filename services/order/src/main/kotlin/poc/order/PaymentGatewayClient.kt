package poc.order

import org.springframework.beans.factory.annotation.Value
import org.springframework.http.MediaType
import org.springframework.http.client.SimpleClientHttpRequestFactory
import org.springframework.stereotype.Component
import org.springframework.web.client.RestClient
import org.springframework.web.client.body
import java.time.Duration

/**
 * Phase 2.1: 결제 게이트웨이(WireMock `POST /gateway/charge`) 호출.
 *
 * 요청 팩토리를 [SimpleClientHttpRequestFactory](HttpURLConnection)로 고정한다.
 * 2.4의 Evidence POST는 java.net.http.HttpClient를 쓰고 OTel agent에서 그 계측만 끈다.
 * RestClient 기본값에 맡겨 이 호출도 JDK HttpClient를 타게 되면 비즈니스 외부 호출 span까지
 * 같이 사라지므로, 두 경로의 HTTP 클라이언트를 처음부터 분리해 둔다.
 *
 * Phase 3.1: 정적 `RestClient.builder()` 대신 Boot가 관리하는 [RestClient.Builder]를 주입받는다.
 * 그래야 검증 레이어(poc.evidence)가 RestClientCustomizer로 재생 헤더 전파 인터셉터를 붙일 수 있다.
 * 요청 팩토리 고정은 그대로다.
 *
 * Phase 3.5-v1.1: Java → Kotlin 전환(FQCN·메서드 시그니처 유지).
 */
@Component
class PaymentGatewayClient(builder: RestClient.Builder, @Value("\${payment.gateway-url}") gatewayUrl: String) {

    private val restClient: RestClient = builder
        .baseUrl(gatewayUrl)
        .requestFactory(SimpleClientHttpRequestFactory().apply { setReadTimeout(Duration.ofSeconds(1)) })
        .build()

    /**
     * 결제를 요청하고 게이트웨이가 준 transactionId를 돌려준다. 2xx가 아니면 예외.
     * Idempotency-Key는 본문과 헤더 양쪽에 싣는다 (스텁은 헤더에서 transactionId를 만든다).
     */
    fun charge(orderKey: String, amount: Long, idempotencyKey: String): String {
        val response = restClient.post()
            .uri("/gateway/charge")
            .contentType(MediaType.APPLICATION_JSON)
            .header("Idempotency-Key", idempotencyKey)
            .body(ChargeRequest(orderKey, amount, idempotencyKey))
            .retrieve()
            .body<ChargeResponse>()
        return response?.transactionId ?: throw IllegalStateException("payment gateway returned no transactionId")
    }

    data class ChargeRequest(val orderKey: String, val amount: Long, val idempotencyKey: String)

    data class ChargeResponse(val transactionId: String?, val status: String?)
}
