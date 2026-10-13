package poc.coupon;

import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Phase 3.2: Coupon API. 에러 본문은 고정 코드만({"code": ...}) — 실행 시점 값·동적 문자열 없음.
 */
@RestController
@RequestMapping("/api/coupons")
public class CouponController {

    private final CouponService couponService;

    public CouponController(CouponService couponService) {
        this.couponService = couponService;
    }

    @PostMapping
    public ResponseEntity<?> issue(@RequestBody IssueRequest request) {
        if (request.couponKey() == null || request.couponKey().isBlank()
                || request.discountAmount() == null || request.discountAmount() < 0) {
            return error(HttpStatus.BAD_REQUEST, "INVALID_REQUEST");
        }
        return respond(couponService.issue(request.couponKey(), request.discountAmount()));
    }

    @GetMapping("/by-key/{couponKey}")
    public ResponseEntity<?> getByKey(@PathVariable String couponKey) {
        return respond(couponService.getByKey(couponKey));
    }

    @PostMapping("/{couponKey}/use")
    public ResponseEntity<?> use(@PathVariable String couponKey, @RequestBody UseRequest request) {
        if (request.orderKey() == null || request.orderKey().isBlank()) {
            return error(HttpStatus.BAD_REQUEST, "INVALID_REQUEST");
        }
        return respond(couponService.use(couponKey, request.orderKey()));
    }

    /** existsByCouponKey 검사와 insert 사이에 같은 키가 들어온 경우 (UNIQUE 제약). */
    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<CodeResponse> onConflict(DataIntegrityViolationException e) {
        return error(HttpStatus.CONFLICT, "COUPON_KEY_EXISTS");
    }

    private static ResponseEntity<?> respond(CouponService.Outcome outcome) {
        return switch (outcome.kind()) {
            case CREATED -> ResponseEntity.status(HttpStatus.CREATED).body(outcome.coupon());
            case OK -> ResponseEntity.ok(outcome.coupon());
            case KEY_EXISTS -> error(HttpStatus.CONFLICT, "COUPON_KEY_EXISTS");
            case NOT_FOUND -> error(HttpStatus.NOT_FOUND, "COUPON_NOT_FOUND");
            case ALREADY_USED -> error(HttpStatus.CONFLICT, "COUPON_ALREADY_USED");
        };
    }

    private static ResponseEntity<CodeResponse> error(HttpStatus status, String code) {
        return ResponseEntity.status(status).body(new CodeResponse(code));
    }

    public record IssueRequest(String couponKey, Long discountAmount) {
    }

    public record UseRequest(String orderKey) {
    }

    public record CodeResponse(String code) {
    }
}
