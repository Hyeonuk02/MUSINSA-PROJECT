package com.pm.order.client;

import com.pm.order.dto.PaymentRequest;
import com.pm.order.dto.PaymentResponse;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@FeignClient(name = "PAYMENT-SERVICE") // Must match spring.application.name exactly
public interface PaymentClient {
    @PostMapping("/payments/process")
    PaymentResponse process(@RequestBody PaymentRequest request);
}