package com.pm.payment.client;

import com.pm.payment.dto.OrderResponse;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestParam;

@FeignClient(name = "ORDER-SERVICE")
public interface OrderClient {

    @PutMapping("/orders/{orderId}/status")
    OrderResponse updateOrderStatus(
            @PathVariable("orderId") Long orderId, 
            @RequestParam("paymentStatus") String paymentStatus,
            @RequestParam("orderStatus") String orderStatus);
}