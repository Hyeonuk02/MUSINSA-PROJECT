package com.pm.order.client;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;

@FeignClient(name = "SHIPPING-SERVICE") // Or your service name
public interface ShippingClient {
    @PostMapping("/shipments/initiate/{orderId}")
    void initiateShipment(
        @PathVariable("orderId") Long orderId,
        @RequestParam("customerName") String customerName,
        @RequestParam("customerEmail") String customerEmail
    );
}