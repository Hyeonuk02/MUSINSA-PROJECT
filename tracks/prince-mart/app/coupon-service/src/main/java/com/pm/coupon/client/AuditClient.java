package com.pm.coupon.client;


import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

import com.pm.coupon.dto.AuditLogRequest;

@FeignClient(name = "AUDIT-SERVICE")
public interface AuditClient {

    @PostMapping("/audit/log")
    void createLog(@RequestBody AuditLogRequest request);
}