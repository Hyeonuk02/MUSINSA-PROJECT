package poc.order;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/**
 * Phase 2.1: 결제 게이트웨이(WireMock {@code POST /gateway/charge}) 호출.
 *
 * <p>요청 팩토리를 {@link SimpleClientHttpRequestFactory}(HttpURLConnection)로 고정한다.
 * 2.4의 Evidence POST는 java.net.http.HttpClient를 쓰고 OTel agent에서 그 계측만 끈다.
 * RestClient 기본값에 맡겨 이 호출도 JDK HttpClient를 타게 되면 비즈니스 외부 호출 span까지
 * 같이 사라지므로, 두 경로의 HTTP 클라이언트를 처음부터 분리해 둔다.
 */
@Component
public class PaymentGatewayClient {

    private final RestClient restClient;

    public PaymentGatewayClient(@Value("${payment.gateway-url}") String gatewayUrl) {
        this.restClient = RestClient.builder()
                .baseUrl(gatewayUrl)
                .requestFactory(new SimpleClientHttpRequestFactory())
                .build();
    }

    /**
     * 결제를 요청하고 게이트웨이가 준 transactionId를 돌려준다. 2xx가 아니면 예외.
     * Idempotency-Key는 본문과 헤더 양쪽에 싣는다 (스텁은 헤더에서 transactionId를 만든다).
     */
    public String charge(String orderKey, long amount, String idempotencyKey) {
        ChargeResponse response = restClient.post()
                .uri("/gateway/charge")
                .contentType(MediaType.APPLICATION_JSON)
                .header("Idempotency-Key", idempotencyKey)
                .body(new ChargeRequest(orderKey, amount, idempotencyKey))
                .retrieve()
                .body(ChargeResponse.class);
        if (response == null || response.transactionId() == null) {
            throw new IllegalStateException("payment gateway returned no transactionId");
        }
        return response.transactionId();
    }

    record ChargeRequest(String orderKey, long amount, String idempotencyKey) {
    }

    record ChargeResponse(String transactionId, String status) {
    }
}
