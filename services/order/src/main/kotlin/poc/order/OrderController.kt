package poc.order

import org.springframework.dao.DataIntegrityViolationException
import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.ExceptionHandler
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestHeader
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

/**
 * Phase 2.1: business key(orderKey) 기반 Order API. Phase 3.2: 비즈니스 로직·트랜잭션은 [OrderService]로 옮기고
 * 컨트롤러는 매핑·DTO·입력 검증만 한다.
 *
 * 에러 응답은 전부 이 컨트롤러가 고정된 본문으로 만든다. Spring 기본 에러 본문에는
 * timestamp가 들어가서 legacy/new 응답 비교에 실행 시점 값이 섞이기 때문이다.
 *
 * Phase 3.5-v1.4: Java → Kotlin 전환. 요청 DTO는 Java가 null을 검사하던 필드(orderKey·items·couponKey)를 `?`로,
 * Java primitive(qty·price)는 값이 없을 때 Java처럼 0이 되도록 기본값 0.
 */
@RestController
@RequestMapping("/api/orders")
class OrderController(private val orderService: OrderService) {

    @PostMapping
    fun create(@RequestBody request: CreateOrderRequest): ResponseEntity<*> {
        if (request.orderKey.isNullOrBlank() || request.items.isNullOrEmpty()) {
            return error(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", request.orderKey)
        }
        val items = request.items.map { OrderService.NewItem(it.sku, it.qty, it.price) }
        val couponKey = if (request.couponKey.isNullOrBlank()) null else request.couponKey
        return respond(orderService.create(request.orderKey, items, couponKey), request.orderKey)
    }

    @GetMapping("/by-key/{orderKey}")
    fun getByKey(@PathVariable orderKey: String): ResponseEntity<*> =
        respond(orderService.getByKey(orderKey), orderKey)

    /** Phase 1 호환용. id는 스택마다 다를 수 있으니 corpus는 이 경로를 쓰지 않는다. */
    @GetMapping("/{id}")
    fun get(@PathVariable id: Long): ResponseEntity<*> =
        respond(orderService.getById(id), null)

    @PostMapping("/{orderKey}/pay")
    fun pay(
        @PathVariable orderKey: String,
        @RequestHeader(name = "Idempotency-Key", required = false) idempotencyKey: String?,
    ): ResponseEntity<*> {
        if (idempotencyKey.isNullOrBlank()) {
            return error(HttpStatus.BAD_REQUEST, "IDEMPOTENCY_KEY_REQUIRED", orderKey)
        }
        return respond(orderService.pay(orderKey, idempotencyKey), orderKey)
    }

    @PostMapping("/{orderKey}/cancel")
    fun cancel(@PathVariable orderKey: String): ResponseEntity<*> =
        respond(orderService.cancel(orderKey), orderKey)

    /** existsByOrderKey 검사와 insert 사이에 같은 키가 들어온 경우 (UNIQUE 제약). */
    @ExceptionHandler(DataIntegrityViolationException::class)
    fun onConflict(e: DataIntegrityViolationException): ResponseEntity<ErrorResponse> =
        error(HttpStatus.CONFLICT, "ORDER_KEY_EXISTS", null)

    /** 쿠폰 사용 실패 — 주문은 롤백됐다. 본문은 고정 코드만(동적 문자열 없음). */
    @ExceptionHandler(CouponClient.CouponFailure::class)
    fun onCouponFailure(e: CouponClient.CouponFailure): ResponseEntity<CodeResponse> = when (e.kind) {
        CouponClient.CouponFailure.Kind.NOT_FOUND ->
            ResponseEntity.status(HttpStatus.BAD_REQUEST).body(CodeResponse("COUPON_NOT_FOUND"))
        CouponClient.CouponFailure.Kind.ALREADY_USED ->
            ResponseEntity.status(HttpStatus.BAD_REQUEST).body(CodeResponse("COUPON_ALREADY_USED"))
        CouponClient.CouponFailure.Kind.UNAVAILABLE ->
            ResponseEntity.status(HttpStatus.BAD_GATEWAY).body(CodeResponse("COUPON_UNAVAILABLE"))
    }

    private fun respond(outcome: OrderService.Outcome, orderKey: String?): ResponseEntity<*> = when (outcome.kind) {
        OrderService.Kind.CREATED -> ResponseEntity.status(HttpStatus.CREATED).body(outcome.order)
        OrderService.Kind.OK -> ResponseEntity.ok(outcome.order)
        OrderService.Kind.KEY_EXISTS -> error(HttpStatus.CONFLICT, "ORDER_KEY_EXISTS", orderKey)
        OrderService.Kind.NOT_FOUND -> error(HttpStatus.NOT_FOUND, "ORDER_NOT_FOUND", orderKey)
        OrderService.Kind.ALREADY_PAID -> error(HttpStatus.CONFLICT, "ALREADY_PAID", orderKey)
        OrderService.Kind.CANCELLED -> error(HttpStatus.CONFLICT, "ORDER_CANCELLED", orderKey)
        OrderService.Kind.PAYMENT_FAILED -> error(HttpStatus.BAD_GATEWAY, "PAYMENT_FAILED", orderKey)
    }

    private fun error(status: HttpStatus, code: String, orderKey: String?): ResponseEntity<ErrorResponse> =
        ResponseEntity.status(status).body(ErrorResponse(code, orderKey))

    data class CreateOrderRequest(val orderKey: String?, val items: List<ItemRequest>?, val couponKey: String?)

    data class ItemRequest(val sku: String, val qty: Int = 0, val price: Long = 0)

    data class ErrorResponse(val error: String, val orderKey: String?)

    data class CodeResponse(val code: String)
}
