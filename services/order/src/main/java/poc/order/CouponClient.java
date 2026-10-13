package poc.order;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import java.time.Duration;

/**
 * Phase 3.2: Coupon 서비스 호출({@code POST /api/coupons/{couponKey}/use}).
 *
 * <p>같은 네임스페이스의 Coupon을 직접 부른다({@code http://coupon:8080}) — 게이트웨이를 거치지 않으므로 미러되지 않는다.
 * Boot의 {@link RestClient.Builder}를 주입받아 검증 레이어의 전파 인터셉터가 붙는다(자식 hopPath, externalCalls).
 * 요청 팩토리는 PaymentGatewayClient와 같은 이유로 {@link SimpleClientHttpRequestFactory}, connect 1s·read 3s.
 *
 * <p>실패는 {@link CouponFailure}로 던진다 — 서비스의 @Transactional 경계를 넘어가 주문 INSERT까지 롤백된다.
 */
@Component
public class CouponClient {

    private final RestClient restClient;

    public CouponClient(RestClient.Builder builder, @Value("${coupon.url}") String couponUrl) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(1));
        factory.setReadTimeout(Duration.ofSeconds(3));
        this.restClient = builder
                .baseUrl(couponUrl)
                .requestFactory(factory)
                .build();
    }

    /** 쿠폰을 이 주문에 사용하고 할인액을 돌려준다. 같은 (couponKey, orderKey) 재호출은 Coupon 쪽에서 멱등. */
    public long use(String couponKey, String orderKey) {
        try {
            return restClient.post()
                    .uri("/api/coupons/{couponKey}/use", couponKey)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new UseRequest(orderKey))
                    .exchange((request, response) -> {
                        int status = response.getStatusCode().value();
                        if (status == 200) {
                            CouponUse body = response.bodyTo(CouponUse.class);
                            if (body == null) {
                                throw new CouponFailure(CouponFailure.Kind.UNAVAILABLE);
                            }
                            return body.discountAmount();
                        }
                        if (status == 404) {
                            throw new CouponFailure(CouponFailure.Kind.NOT_FOUND);
                        }
                        if (status == 409) {
                            throw new CouponFailure(CouponFailure.Kind.ALREADY_USED);
                        }
                        throw new CouponFailure(CouponFailure.Kind.UNAVAILABLE);
                    });
        } catch (RestClientException e) {
            throw new CouponFailure(CouponFailure.Kind.UNAVAILABLE);
        }
    }

    record UseRequest(String orderKey) {
    }

    record CouponUse(String couponKey, long discountAmount, String status, String usedByOrderKey) {
    }

    /** 쿠폰 사용 실패. 메시지·원인 없이 종류만 — 응답 본문에 동적 문자열이 섞이지 않게. */
    public static class CouponFailure extends RuntimeException {
        public enum Kind { NOT_FOUND, ALREADY_USED, UNAVAILABLE }

        private final Kind kind;

        CouponFailure(Kind kind) {
            super(kind.name(), null, false, false);
            this.kind = kind;
        }

        public Kind kind() {
            return kind;
        }
    }
}
