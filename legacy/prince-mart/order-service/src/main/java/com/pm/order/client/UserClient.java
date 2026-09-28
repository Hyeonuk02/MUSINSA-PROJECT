package com.pm.order.client;

import com.pm.order.dto.UserResponse;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(name = "IDENTITY-SERVICE", contextId = "userClient")
public interface UserClient {
    // Assuming your Identity Service has this endpoint
    @GetMapping("/auth/id/{userId}")
    UserResponse getUserById(@PathVariable("userId") Long userId);
}