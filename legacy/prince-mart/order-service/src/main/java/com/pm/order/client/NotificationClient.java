package com.pm.order.client;

import com.pm.order.dto.NotificationRequest;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

// [LEGACY_CHANGES L-F2] payment-service의 NotificationClient를 그대로 복사. 알림 발송이 Order consumer로 옮겨왔다.
@FeignClient(name = "NOTIFICATION-SERVICE")
public interface NotificationClient {

    @PostMapping("/notifications/order-confirmation")
    String sendConfirmation(@RequestBody NotificationRequest request);
}