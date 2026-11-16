package com.pm.order.client;

import com.pm.order.dto.AuditLogRequest;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@FeignClient(name = "AUDIT-SERVICE")
public interface AuditClient {

    @PostMapping("/audit/log")
    void createLog(@RequestBody AuditLogRequest request);
}