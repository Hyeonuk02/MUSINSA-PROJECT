package com.pm.order.client;

import com.pm.order.dto.AddressResponse;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(name = "IDENTITY-SERVICE", contextId = "addressClient")
public interface AddressClient {
    
    // We'll add this endpoint to AuthController next
    @GetMapping("/auth/addresses/id/{id}")
    AddressResponse getAddressById(@PathVariable("id") Long id);
}