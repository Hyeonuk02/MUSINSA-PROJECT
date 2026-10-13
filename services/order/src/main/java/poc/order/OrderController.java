package poc.order;

import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * Phase 2.1: business key(orderKey) 기반 Order API. Phase 3.2: 비즈니스 로직·트랜잭션은 {@link OrderService}로 옮기고
 * 컨트롤러는 매핑·DTO·입력 검증만 한다.
 *
 * <p>에러 응답은 전부 이 컨트롤러가 고정된 본문으로 만든다. Spring 기본 에러 본문에는
 * timestamp가 들어가서 legacy/new 응답 비교에 실행 시점 값이 섞이기 때문이다.
 */
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public ResponseEntity<?> create(@RequestBody CreateOrderRequest request) {
        if (request.orderKey() == null || request.orderKey().isBlank()
                || request.items() == null || request.items().isEmpty()) {
            return error(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", request.orderKey());
        }
        List<OrderService.NewItem> items = request.items().stream()
                .map(i -> new OrderService.NewItem(i.sku(), i.qty(), i.price()))
                .toList();
        String couponKey = request.couponKey() == null || request.couponKey().isBlank() ? null : request.couponKey();
        return respond(orderService.create(request.orderKey(), items, couponKey), request.orderKey());
    }

    @GetMapping("/by-key/{orderKey}")
    public ResponseEntity<?> getByKey(@PathVariable String orderKey) {
        return respond(orderService.getByKey(orderKey), orderKey);
    }

    /** Phase 1 호환용. id는 스택마다 다를 수 있으니 corpus는 이 경로를 쓰지 않는다. */
    @GetMapping("/{id}")
    public ResponseEntity<?> get(@PathVariable Long id) {
        return respond(orderService.getById(id), null);
    }

    @PostMapping("/{orderKey}/pay")
    public ResponseEntity<?> pay(@PathVariable String orderKey,
                                 @RequestHeader(name = "Idempotency-Key", required = false) String idempotencyKey) {
        if (idempotencyKey == null || idempotencyKey.isBlank()) {
            return error(HttpStatus.BAD_REQUEST, "IDEMPOTENCY_KEY_REQUIRED", orderKey);
        }
        return respond(orderService.pay(orderKey, idempotencyKey), orderKey);
    }

    @PostMapping("/{orderKey}/cancel")
    public ResponseEntity<?> cancel(@PathVariable String orderKey) {
        return respond(orderService.cancel(orderKey), orderKey);
    }

    /** existsByOrderKey 검사와 insert 사이에 같은 키가 들어온 경우 (UNIQUE 제약). */
    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<ErrorResponse> onConflict(DataIntegrityViolationException e) {
        return error(HttpStatus.CONFLICT, "ORDER_KEY_EXISTS", null);
    }

    /** 쿠폰 사용 실패 — 주문은 롤백됐다. 본문은 고정 코드만(동적 문자열 없음). */
    @ExceptionHandler(CouponClient.CouponFailure.class)
    public ResponseEntity<CodeResponse> onCouponFailure(CouponClient.CouponFailure e) {
        return switch (e.kind()) {
            case NOT_FOUND -> ResponseEntity.status(HttpStatus.BAD_REQUEST).body(new CodeResponse("COUPON_NOT_FOUND"));
            case ALREADY_USED -> ResponseEntity.status(HttpStatus.BAD_REQUEST).body(new CodeResponse("COUPON_ALREADY_USED"));
            case UNAVAILABLE -> ResponseEntity.status(HttpStatus.BAD_GATEWAY).body(new CodeResponse("COUPON_UNAVAILABLE"));
        };
    }

    private static ResponseEntity<?> respond(OrderService.Outcome outcome, String orderKey) {
        return switch (outcome.kind()) {
            case CREATED -> ResponseEntity.status(HttpStatus.CREATED).body(outcome.order());
            case OK -> ResponseEntity.ok(outcome.order());
            case KEY_EXISTS -> error(HttpStatus.CONFLICT, "ORDER_KEY_EXISTS", orderKey);
            case NOT_FOUND -> error(HttpStatus.NOT_FOUND, "ORDER_NOT_FOUND", orderKey);
            case ALREADY_PAID -> error(HttpStatus.CONFLICT, "ALREADY_PAID", orderKey);
            case CANCELLED -> error(HttpStatus.CONFLICT, "ORDER_CANCELLED", orderKey);
            case PAYMENT_FAILED -> error(HttpStatus.BAD_GATEWAY, "PAYMENT_FAILED", orderKey);
        };
    }

    private static ResponseEntity<ErrorResponse> error(HttpStatus status, String code, String orderKey) {
        return ResponseEntity.status(status).body(new ErrorResponse(code, orderKey));
    }

    public record CreateOrderRequest(String orderKey, List<ItemRequest> items, String couponKey) {
    }

    public record ItemRequest(String sku, int qty, long price) {
    }

    public record ErrorResponse(String error, String orderKey) {
    }

    public record CodeResponse(String code) {
    }
}
