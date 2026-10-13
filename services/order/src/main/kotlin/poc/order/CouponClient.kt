package poc.order

import org.springframework.beans.factory.annotation.Value
import org.springframework.http.MediaType
import org.springframework.http.client.SimpleClientHttpRequestFactory
import org.springframework.stereotype.Component
import org.springframework.web.client.RestClient
import org.springframework.web.client.RestClientException
import java.time.Duration

/**
 * Phase 3.2: Coupon 서비스 호출(`POST /api/coupons/{couponKey}/use`).
 *
 * 같은 네임스페이스의 Coupon을 직접 부른다(`http://coupon:8080`) — 게이트웨이를 거치지 않으므로 미러되지 않는다.
 * Boot의 [RestClient.Builder]를 주입받아 검증 레이어의 전파 인터셉터가 붙는다(자식 hopPath, externalCalls).
 * 요청 팩토리는 PaymentGatewayClient와 같은 이유로 [SimpleClientHttpRequestFactory], connect 1s·read 3s.
 *
 * 실패는 [CouponFailure]로 던진다 — 서비스의 @Transactional 경계를 넘어가 주문 INSERT까지 롤백된다.
 *
 * Phase 3.5-v1.4: Java → Kotlin 전환.
 */
@Component
class CouponClient(builder: RestClient.Builder, @Value("\${coupon.url}") couponUrl: String) {

    private val restClient: RestClient = builder
        .baseUrl(couponUrl)
        .requestFactory(
            SimpleClientHttpRequestFactory().apply {
                setConnectTimeout(Duration.ofSeconds(1))
                setReadTimeout(Duration.ofSeconds(3))
            },
        )
        .build()

    /** 쿠폰을 이 주문에 사용하고 할인액을 돌려준다. 같은 (couponKey, orderKey) 재호출은 Coupon 쪽에서 멱등. */
    fun use(couponKey: String, orderKey: String): Long {
        try {
            return restClient.post()
                .uri("/api/coupons/{couponKey}/use", couponKey)
                .contentType(MediaType.APPLICATION_JSON)
                .body(UseRequest(orderKey))
                .exchange { _, response ->
                    when (response.statusCode.value()) {
                        200 -> response.bodyTo(CouponUse::class.java)?.discountAmount
                            ?: throw CouponFailure(CouponFailure.Kind.UNAVAILABLE)
                        404 -> throw CouponFailure(CouponFailure.Kind.NOT_FOUND)
                        409 -> throw CouponFailure(CouponFailure.Kind.ALREADY_USED)
                        else -> throw CouponFailure(CouponFailure.Kind.UNAVAILABLE)
                    }
                }
        } catch (e: RestClientException) {
            throw CouponFailure(CouponFailure.Kind.UNAVAILABLE)
        }
    }

    data class UseRequest(val orderKey: String)

    data class CouponUse(val couponKey: String?, val discountAmount: Long, val status: String?, val usedByOrderKey: String?)

    /** 쿠폰 사용 실패. 메시지·원인 없이 종류만 — 응답 본문에 동적 문자열이 섞이지 않게. */
    class CouponFailure internal constructor(val kind: Kind) : RuntimeException(kind.name, null, false, false) {
        enum class Kind { NOT_FOUND, ALREADY_USED, UNAVAILABLE }
    }
}
