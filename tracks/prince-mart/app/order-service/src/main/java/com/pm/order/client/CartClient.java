package com.pm.order.client;

import com.pm.order.dto.CartResponse;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;

@FeignClient(name = "CART-SERVICE")
public interface CartClient {
    
    @GetMapping("/cart/my-cart")
    CartResponse getMyCart(@RequestHeader("X-User-Id") Long userId);

    @DeleteMapping("/cart/clear") // New method
    void clearCart(@RequestHeader("X-User-Id") Long userId);
}