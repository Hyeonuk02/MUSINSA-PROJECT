package com.pm.payment.gateway;

import org.json.JSONObject;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.nio.charset.StandardCharsets;

/**
 * [LEGACY_CHANGES L-F1] 실험 환경용: 가짜 PG(WireMock)를 HTTP로 호출한다(payment-gateway.type=fake).
 *
 * <p>SDK와 같은 경로(POST /v1/orders)와 본문을 보낸다. HTTP로 호출하므로 외부 호출 Evidence가
 * WireMock journal에 남는다. 가짜 PG는 결정적 id(order_{orderId})를 돌려주고, fixture 규칙에 걸리면
 * Razorpay와 같은 모양의 오류 본문({"error":{"description":...}})으로 4xx를 돌려준다.
 * SDK처럼 오류 설명을 메시지로 가진 예외를 던진다.
 */
@Component
@ConditionalOnProperty(name = "payment-gateway.type", havingValue = "fake")
public class FakePgPaymentGateway implements PaymentGateway {

    private final RestClient restClient;

    public FakePgPaymentGateway(@Value("${payment-gateway.fake-url}") String baseUrl) {
        this.restClient = RestClient.create(baseUrl);
    }

    @Override
    public String createOrder(JSONObject orderRequest) throws Exception {
        String body = restClient.post()
                .uri("/v1/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .body(orderRequest.toString())
                .retrieve()
                .onStatus(HttpStatusCode::isError, (request, response) -> {
                    String error = new String(response.getBody().readAllBytes(), StandardCharsets.UTF_8);
                    throw new FakePgException(new JSONObject(error).getJSONObject("error").getString("description"));
                })
                .body(String.class);
        return new JSONObject(body).getString("id");
    }

    static class FakePgException extends RuntimeException {
        FakePgException(String message) {
            super(message);
        }
    }
}
