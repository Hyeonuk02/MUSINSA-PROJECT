package com.pm.payment.gateway;

import com.razorpay.Order;
import com.razorpay.RazorpayClient;
import org.json.JSONObject;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * [LEGACY_CHANGES L-F1] upstream 동작 그대로: Razorpay SDK로 주문을 만든다(기본값).
 * PaymentService에 있던 코드를 옮기기만 했다.
 */
@Component
@ConditionalOnProperty(name = "payment-gateway.type", havingValue = "razorpay", matchIfMissing = true)
public class RazorpayPaymentGateway implements PaymentGateway {

    @Value("${razorpay.key.id}")
    private String razorpayId;

    @Value("${razorpay.key.secret}")
    private String razorpaySecret;

    @Override
    public String createOrder(JSONObject orderRequest) throws Exception {
        RazorpayClient client = new RazorpayClient(razorpayId, razorpaySecret);
        Order razorpayOrder = client.orders.create(orderRequest);
        return razorpayOrder.get("id");
    }
}
