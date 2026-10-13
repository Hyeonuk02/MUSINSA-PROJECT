package poc.order

import org.slf4j.LoggerFactory
import org.springframework.context.ApplicationEventPublisher
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import org.springframework.web.client.RestClientException
import java.time.Clock

/**
 * Phase 3.2: 주문 비즈니스 로직과 트랜잭션 경계. 컨트롤러는 매핑·DTO·입력 검증만 한다.
 *
 * 결과는 [Outcome](종류 + 응답 본문)으로 돌려준다. 응답 본문은 트랜잭션 안에서 만든다(OrderView 참조).
 * HTTP 상태코드·에러 본문 매핑은 컨트롤러의 몫이다.
 *
 * Phase 3.5-v1.3: Java → Kotlin 전환. `Outcome`·`NewItem`은 아직 Java인 OrderController가 record 접근자
 * (`kind()`, `order()`, 생성자)로 쓰므로 `@JvmRecord`로 Java record와 같은 모양을 유지한다.
 */
@Service
class OrderService(
    private val orderRepository: OrderRepository,
    private val paymentGateway: PaymentGatewayClient,
    private val couponClient: CouponClient,
    private val events: ApplicationEventPublisher,
    private val clock: Clock,
) {

    enum class Kind { CREATED, OK, KEY_EXISTS, NOT_FOUND, ALREADY_PAID, CANCELLED, PAYMENT_FAILED }

    @JvmRecord
    data class Outcome(val kind: Kind, val order: OrderView?) {
        companion object {
            fun of(kind: Kind) = Outcome(kind, null)
        }
    }

    @JvmRecord
    data class NewItem(val sku: String, val qty: Int, val price: Long)

    /**
     * 주문 생성. 쿠폰이 있으면 순서 고정(Phase 3.2): orders·order_items INSERT(flush) → Coupon use → 할인 반영 → 커밋(flush에서 UPDATE).
     * Coupon 실패는 [CouponClient.CouponFailure]로 던져 주문 INSERT까지 롤백한다.
     * "Coupon은 USED인데 주문은 롤백"(보상 누락)은 분산 일관성 문제로 범위 밖이다(phase3-plan 3절).
     */
    @Transactional
    fun create(orderKey: String, items: List<NewItem>, couponKey: String?): Outcome {
        if (orderRepository.existsByOrderKey(orderKey)) {
            return Outcome.of(Kind.KEY_EXISTS)
        }
        val order = Order(orderKey, clock)
        for (item in items) {
            order.addItem(item.sku, item.qty, item.price)
        }
        orderRepository.saveAndFlush(order)
        if (couponKey != null) {
            couponClient.use(couponKey, orderKey)
            val discount = couponClient.use(couponKey, orderKey)
            order.applyCoupon(couponKey, discount)
        }
        return Outcome(Kind.CREATED, OrderView.from(order))
    }

    @Transactional(readOnly = true)
    fun getByKey(orderKey: String): Outcome =
        orderRepository.findByOrderKey(orderKey)
            .map { Outcome(Kind.OK, OrderView.from(it)) }
            .orElseGet { Outcome.of(Kind.NOT_FOUND) }

    /** Phase 1 호환용. id는 스택마다 다를 수 있으니 corpus는 이 경로를 쓰지 않는다. */
    @Transactional(readOnly = true)
    fun getById(id: Long): Outcome =
        orderRepository.findById(id)
            .map { Outcome(Kind.OK, OrderView.from(it)) }
            .orElseGet { Outcome.of(Kind.NOT_FOUND) }

    /**
     * 결제. 같은 Idempotency-Key로 다시 오면 게이트웨이를 다시 부르지 않고 이전 결과를 돌려준다.
     * 이미 다른 키로 결제됐거나 취소된 주문은 충돌.
     */
    @Transactional
    fun pay(orderKey: String, idempotencyKey: String): Outcome {
        val order = orderRepository.findByOrderKey(orderKey).orElse(null)
            ?: return Outcome.of(Kind.NOT_FOUND)
        return when (order.status) {
            Order.PAID ->
                if (idempotencyKey == order.idempotencyKey) Outcome(Kind.OK, OrderView.from(order))
                else Outcome.of(Kind.ALREADY_PAID)
            Order.CANCELLED -> Outcome.of(Kind.CANCELLED)
            else -> {
                val transactionId = try {
                    paymentGateway.charge(orderKey, order.amount, idempotencyKey)
                } catch (e: RestClientException) {
                    log.warn("payment gateway failed orderKey={} idempotencyKey={}", orderKey, idempotencyKey, e)
                    return Outcome.of(Kind.PAYMENT_FAILED)
                } catch (e: IllegalStateException) {
                    log.warn("payment gateway failed orderKey={} idempotencyKey={}", orderKey, idempotencyKey, e)
                    return Outcome.of(Kind.PAYMENT_FAILED)
                }
                order.markPaid(transactionId, idempotencyKey)
                // Phase 3.3: 처음 PAID가 될 때만. 같은 Idempotency-Key 재결제(위 PAID 분기)는 발행하지 않는다.
                events.publishEvent(OrderPaid(orderKey, order.amount, order.couponKey))
                Outcome(Kind.OK, OrderView.from(order))
            }
        }
    }

    /** 취소. PAID면 충돌, 이미 취소된 주문은 그대로 OK(멱등). */
    @Transactional
    fun cancel(orderKey: String): Outcome {
        val order = orderRepository.findByOrderKey(orderKey).orElse(null)
            ?: return Outcome.of(Kind.NOT_FOUND)
        if (Order.PAID == order.status) {
            return Outcome.of(Kind.ALREADY_PAID)
        }
        order.cancel()
        return Outcome(Kind.OK, OrderView.from(order))
    }

    private companion object {
        private val log = LoggerFactory.getLogger(OrderService::class.java)
    }
}
