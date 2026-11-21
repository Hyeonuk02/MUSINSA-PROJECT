package com.pm.order.repository;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param; // FIXED: Correct Param import
import org.springframework.stereotype.Repository;
import com.pm.order.entity.Order;

@Repository
public interface OrderRepository extends JpaRepository<Order, Long> {
    
    List<Order> findByUserIdOrderByCreatedAtDesc(Long userId);
    
    @Query("SELECT COUNT(o) > 0 FROM Order o JOIN o.items i " +
           "WHERE o.userId = :userId " +
           "AND i.productId = :productId " +
           "AND o.orderStatus = 'CONFIRMED'")
    boolean existsByUserIdAndProductId(@Param("userId") Long userId, @Param("productId") Long productId);
    
    List<Order> findByUserId(Long userId);

    // PF5: 취소에서 주문과 품목을 한 번에 읽는다(fetch join)
    @Query("SELECT o FROM Order o LEFT JOIN FETCH o.items WHERE o.orderId = :orderId")
    java.util.Optional<Order> findWithItemsByOrderId(@Param("orderId") Long orderId);
}