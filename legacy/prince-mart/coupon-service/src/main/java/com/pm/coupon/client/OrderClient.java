package com.pm.coupon.client;

import com.pm.coupon.config.FeignConfig;
import com.pm.coupon.dto.OrderResponse;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;

@FeignClient(name = "ORDER-SERVICE", configuration = FeignConfig.class)
public interface OrderClient {

    @GetMapping("/orders/order/{orderId}")
    OrderResponse getOrderById(
        @PathVariable("orderId") Long orderId,
        @RequestHeader("X-User-Id") Long userId // Add this to match Controller!
    );
}