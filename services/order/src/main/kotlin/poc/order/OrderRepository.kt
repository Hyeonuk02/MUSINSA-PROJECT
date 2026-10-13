package poc.order

import org.springframework.data.jpa.repository.JpaRepository
import org.springframework.data.jpa.repository.Query
import java.util.Optional

/** Phase 3.5-v1.2: Java → Kotlin 전환. 반환 타입은 Java 호출부(OrderService)를 위해 Optional 유지. */
interface OrderRepository : JpaRepository<Order, Long> {

    fun findByOrderKey(orderKey: String): Optional<Order>

    /** 조회 전용: 주문과 항목을 JOIN FETCH 한 번에(조회 2쿼리 → 1쿼리). */
    @Query("select o from Order o join fetch o.items where o.orderKey = :orderKey")
    fun findWithItemsByOrderKey(orderKey: String): Optional<Order>

    fun existsByOrderKey(orderKey: String): Boolean
}
