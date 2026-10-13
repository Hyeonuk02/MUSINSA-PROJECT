package poc.order;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.client.RestClientException;

import java.time.Clock;
import java.util.List;

/**
 * Phase 3.2: 주문 비즈니스 로직과 트랜잭션 경계. 컨트롤러는 매핑·DTO·입력 검증만 한다.
 *
 * <p>결과는 {@link Outcome}(종류 + 응답 본문)으로 돌려준다. 응답 본문은 트랜잭션 안에서 만든다(OrderView 참조).
 * HTTP 상태코드·에러 본문 매핑은 컨트롤러의 몫이다.
 */
@Service
public class OrderService {

    private static final Logger log = LoggerFactory.getLogger(OrderService.class);

    private final OrderRepository orderRepository;
    private final PaymentGatewayClient paymentGateway;
    private final CouponClient couponClient;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    public OrderService(OrderRepository orderRepository, PaymentGatewayClient paymentGateway,
                        CouponClient couponClient, ApplicationEventPublisher events, Clock clock) {
        this.orderRepository = orderRepository;
        this.paymentGateway = paymentGateway;
        this.couponClient = couponClient;
        this.events = events;
        this.clock = clock;
    }

    public enum Kind { CREATED, OK, KEY_EXISTS, NOT_FOUND, ALREADY_PAID, CANCELLED, PAYMENT_FAILED }

    public record Outcome(Kind kind, OrderView order) {
        static Outcome of(Kind kind) {
            return new Outcome(kind, null);
        }
    }

    public record NewItem(String sku, int qty, long price) {
    }

    /**
     * 주문 생성. 쿠폰이 있으면 순서 고정(Phase 3.2): orders·order_items INSERT(flush) → Coupon use → 할인 반영 → 커밋(flush에서 UPDATE).
     * Coupon 실패는 {@link CouponClient.CouponFailure}로 던져 주문 INSERT까지 롤백한다.
     * "Coupon은 USED인데 주문은 롤백"(보상 누락)은 분산 일관성 문제로 범위 밖이다(phase3-plan 3절).
     */
    @Transactional
    public Outcome create(String orderKey, List<NewItem> items, String couponKey) {
        if (orderRepository.existsByOrderKey(orderKey)) {
            return Outcome.of(Kind.KEY_EXISTS);
        }
        Order order = new Order(orderKey, clock);
        for (NewItem item : items) {
            order.addItem(item.sku(), item.qty(), item.price());
        }
        orderRepository.saveAndFlush(order);
        if (couponKey != null) {
            long discount = couponClient.use(couponKey, orderKey);
            order.applyCoupon(couponKey, discount);
        }
        return new Outcome(Kind.CREATED, OrderView.from(order));
    }

    @Transactional(readOnly = true)
    public Outcome getByKey(String orderKey) {
        return orderRepository.findByOrderKey(orderKey)
                .map(order -> new Outcome(Kind.OK, OrderView.from(order)))
                .orElseGet(() -> Outcome.of(Kind.NOT_FOUND));
    }

    /** Phase 1 호환용. id는 스택마다 다를 수 있으니 corpus는 이 경로를 쓰지 않는다. */
    @Transactional(readOnly = true)
    public Outcome getById(Long id) {
        return orderRepository.findById(id)
                .map(order -> new Outcome(Kind.OK, OrderView.from(order)))
                .orElseGet(() -> Outcome.of(Kind.NOT_FOUND));
    }

    /**
     * 결제. 같은 Idempotency-Key로 다시 오면 게이트웨이를 다시 부르지 않고 이전 결과를 돌려준다.
     * 이미 다른 키로 결제됐거나 취소된 주문은 충돌.
     */
    @Transactional
    public Outcome pay(String orderKey, String idempotencyKey) {
        Order order = orderRepository.findByOrderKey(orderKey).orElse(null);
        if (order == null) {
            return Outcome.of(Kind.NOT_FOUND);
        }
        switch (order.getStatus()) {
            case Order.PAID -> {
                if (idempotencyKey.equals(order.getIdempotencyKey())) {
                    return new Outcome(Kind.OK, OrderView.from(order));
                }
                return Outcome.of(Kind.ALREADY_PAID);
            }
            case Order.CANCELLED -> {
                return Outcome.of(Kind.CANCELLED);
            }
            default -> {
                String transactionId;
                try {
                    transactionId = paymentGateway.charge(orderKey, order.getAmount(), idempotencyKey);
                } catch (RestClientException | IllegalStateException e) {
                    log.warn("payment gateway failed orderKey={} idempotencyKey={}", orderKey, idempotencyKey, e);
                    return Outcome.of(Kind.PAYMENT_FAILED);
                }
                order.markPaid(transactionId, idempotencyKey);
                // Phase 3.3: 처음 PAID가 될 때만. 같은 Idempotency-Key 재결제(위 PAID 분기)는 발행하지 않는다.
                events.publishEvent(new OrderPaid(orderKey, order.getAmount(), order.getCouponKey()));
                return new Outcome(Kind.OK, OrderView.from(order));
            }
        }
    }

    /** 취소. PAID면 충돌, 이미 취소된 주문은 그대로 OK(멱등). */
    @Transactional
    public Outcome cancel(String orderKey) {
        Order order = orderRepository.findByOrderKey(orderKey).orElse(null);
        if (order == null) {
            return Outcome.of(Kind.NOT_FOUND);
        }
        if (Order.PAID.equals(order.getStatus())) {
            return Outcome.of(Kind.ALREADY_PAID);
        }
        order.cancel();
        return new Outcome(Kind.OK, OrderView.from(order));
    }
}
