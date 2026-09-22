package poc.order;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderRepository orderRepository;

    public OrderController(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @PostMapping
    @Transactional
    public ResponseEntity<OrderResponse> create(@RequestBody CreateOrderRequest request) {
        Order order = orderRepository.save(
                new Order(request.productId(), request.quantity(), request.unitPrice()));
        return ResponseEntity.status(HttpStatus.CREATED).body(OrderResponse.from(order));
    }

    @GetMapping("/{id}")
    @Transactional(readOnly = true)
    public ResponseEntity<OrderResponse> get(@PathVariable Long id) {
        return orderRepository.findById(id)
                .map(OrderResponse::from)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    public record CreateOrderRequest(String productId, int quantity, long unitPrice) {
    }

    public record OrderResponse(Long id, String productId, int quantity, long unitPrice,
                                long totalAmount, String status, Instant createdAt) {

        static OrderResponse from(Order order) {
            return new OrderResponse(order.getId(), order.getProductId(), order.getQuantity(),
                    order.getUnitPrice(), order.getTotalAmount(), order.getStatus(), order.getCreatedAt());
        }
    }
}
