package poc.order;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClientException;

import java.time.Clock;
import java.time.Instant;
import java.util.List;

/**
 * Phase 2.1: business key(orderKey) 기반 Order API.
 *
 * <p>에러 응답은 전부 이 컨트롤러가 고정된 본문으로 만든다. Spring 기본 에러 본문에는
 * timestamp가 들어가서 legacy/new 응답 비교에 실행 시점 값이 섞이기 때문이다.
 */
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private static final Logger log = LoggerFactory.getLogger(OrderController.class);

    private final OrderRepository orderRepository;
    private final PaymentGatewayClient paymentGateway;
    private final Clock clock;

    public OrderController(OrderRepository orderRepository, PaymentGatewayClient paymentGateway,
                           Clock clock) {
        this.orderRepository = orderRepository;
        this.paymentGateway = paymentGateway;
        this.clock = clock;
    }

    @PostMapping
    @Transactional
    public ResponseEntity<?> create(@RequestBody CreateOrderRequest request) {
        if (request.orderKey() == null || request.orderKey().isBlank()
                || request.items() == null || request.items().isEmpty()) {
            return error(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", request.orderKey());
        }
        if (orderRepository.existsByOrderKey(request.orderKey())) {
            return error(HttpStatus.CONFLICT, "ORDER_KEY_EXISTS", request.orderKey());
        }
        Order order = new Order(request.orderKey(), clock);
        for (ItemRequest item : request.items()) {
            order.addItem(item.sku(), item.qty(), item.price());
        }
        return ResponseEntity.status(HttpStatus.CREATED).body(OrderResponse.from(orderRepository.save(order)));
    }

    @GetMapping("/by-key/{orderKey}")
    @Transactional(readOnly = true)
    public ResponseEntity<?> getByKey(@PathVariable String orderKey) {
        return orderRepository.findByOrderKey(orderKey)
                .<ResponseEntity<?>>map(order -> ResponseEntity.ok(OrderResponse.from(order)))
                .orElseGet(() -> error(HttpStatus.NOT_FOUND, "ORDER_NOT_FOUND", orderKey));
    }

    /** Phase 1 호환용. id는 스택마다 다를 수 있으니 corpus는 이 경로를 쓰지 않는다. */
    @GetMapping("/{id}")
    @Transactional(readOnly = true)
    public ResponseEntity<?> get(@PathVariable Long id) {
        return orderRepository.findById(id)
                .<ResponseEntity<?>>map(order -> ResponseEntity.ok(OrderResponse.from(order)))
                .orElseGet(() -> error(HttpStatus.NOT_FOUND, "ORDER_NOT_FOUND", null));
    }

    /**
     * 결제. 같은 Idempotency-Key로 다시 오면 게이트웨이를 다시 부르지 않고 이전 결과를 돌려준다.
     * 이미 다른 키로 결제됐거나 취소된 주문은 409.
     */
    @PostMapping("/{orderKey}/pay")
    @Transactional
    public ResponseEntity<?> pay(@PathVariable String orderKey,
                                 @RequestHeader(name = "Idempotency-Key", required = false) String idempotencyKey) {
        if (idempotencyKey == null || idempotencyKey.isBlank()) {
            return error(HttpStatus.BAD_REQUEST, "IDEMPOTENCY_KEY_REQUIRED", orderKey);
        }
        Order order = orderRepository.findByOrderKey(orderKey).orElse(null);
        if (order == null) {
            return error(HttpStatus.NOT_FOUND, "ORDER_NOT_FOUND", orderKey);
        }
        switch (order.getStatus()) {
            case Order.PAID -> {
                if (idempotencyKey.equals(order.getIdempotencyKey())) {
                    return ResponseEntity.ok(OrderResponse.from(order));
                }
                return error(HttpStatus.CONFLICT, "ALREADY_PAID", orderKey);
            }
            case Order.CANCELLED -> {
                return error(HttpStatus.CONFLICT, "ORDER_CANCELLED", orderKey);
            }
            default -> {
                String transactionId;
                try {
                    transactionId = paymentGateway.charge(orderKey, order.getAmount(), idempotencyKey);
                } catch (RestClientException | IllegalStateException e) {
                    log.warn("payment gateway failed orderKey={} idempotencyKey={}", orderKey, idempotencyKey, e);
                    return error(HttpStatus.BAD_GATEWAY, "PAYMENT_FAILED", orderKey);
                }
                order.markPaid(transactionId, idempotencyKey);
                return ResponseEntity.ok(OrderResponse.from(order));
            }
        }
    }

    /** 취소. PAID면 409, 이미 취소된 주문은 그대로 200(멱등). */
    @PostMapping("/{orderKey}/cancel")
    @Transactional
    public ResponseEntity<?> cancel(@PathVariable String orderKey) {
        Order order = orderRepository.findByOrderKey(orderKey).orElse(null);
        if (order == null) {
            return error(HttpStatus.NOT_FOUND, "ORDER_NOT_FOUND", orderKey);
        }
        if (Order.PAID.equals(order.getStatus())) {
            return error(HttpStatus.CONFLICT, "ALREADY_PAID", orderKey);
        }
        order.cancel();
        return ResponseEntity.ok(OrderResponse.from(order));
    }

    /** existsByOrderKey 검사와 insert 사이에 같은 키가 들어온 경우 (UNIQUE 제약). */
    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<ErrorResponse> onConflict(DataIntegrityViolationException e) {
        return error(HttpStatus.CONFLICT, "ORDER_KEY_EXISTS", null);
    }

    private static ResponseEntity<ErrorResponse> error(HttpStatus status, String code, String orderKey) {
        return ResponseEntity.status(status).body(new ErrorResponse(code, orderKey));
    }

    public record CreateOrderRequest(String orderKey, List<ItemRequest> items) {
    }

    public record ItemRequest(String sku, int qty, long price) {
    }

    public record ErrorResponse(String error, String orderKey) {
    }

    public record ItemResponse(String sku, int qty, long price) {
    }

    public record OrderResponse(Long id, String orderKey, List<ItemResponse> items, long amount,
                                String status, String transactionId, Instant createdAt) {

        static OrderResponse from(Order order) {
            List<ItemResponse> items = order.getItems().stream()
                    .map(i -> new ItemResponse(i.getSku(), i.getQty(), i.getPrice()))
                    .toList();
            return new OrderResponse(order.getId(), order.getOrderKey(), items, order.getAmount(),
                    order.getStatus(), order.getTransactionId(), order.getCreatedAt());
        }
    }
}
