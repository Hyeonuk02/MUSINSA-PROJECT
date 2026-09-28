package poc.order;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface OrderRepository extends JpaRepository<Order, Long> {

    Optional<Order> findByOrderKey(String orderKey);

    boolean existsByOrderKey(String orderKey);
}
