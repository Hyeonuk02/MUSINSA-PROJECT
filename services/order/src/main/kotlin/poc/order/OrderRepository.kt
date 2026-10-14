package poc.order

import org.springframework.data.jpa.repository.JpaRepository
import java.util.Optional

/** Phase 3.5-v1.2: Java → Kotlin 전환. 반환 타입은 Java 호출부(OrderService)를 위해 Optional 유지. */
interface OrderRepository : JpaRepository<Order, Long> {

    fun findByOrderKey(orderKey: String): Optional<Order>

    fun existsByOrderKey(orderKey: String): Boolean
}
