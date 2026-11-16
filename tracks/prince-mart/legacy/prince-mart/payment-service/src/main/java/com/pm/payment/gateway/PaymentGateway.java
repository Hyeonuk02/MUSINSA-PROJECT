package com.pm.payment.gateway;

import org.json.JSONObject;

/**
 * [LEGACY_CHANGES L-F1] 결제 대행사(PG) 주문 생성 호출을 PaymentService에서 분리한 인터페이스.
 *
 * <p>upstream은 PaymentService 안에서 Razorpay SDK를 직접 호출했다. SDK(razorpay-java 1.4.3)는
 * API 호스트를 static final로 고정하고 있어 설정만으로 가짜 서버를 붙일 수 없으므로, 호출만 이 뒤로 옮긴다.
 * 요청 본문(amount/currency/receipt)과 반환값(PG 주문 id), 실패 시 예외를 던지는 계약은 SDK 호출과 같다.
 */
public interface PaymentGateway {

    /**
     * PG에 주문을 만들고 PG 주문 id를 돌려준다. 실패하면 예외를 던진다(메시지는 PG의 오류 설명).
     *
     * @param orderRequest {@code {"amount": paise, "currency": "INR", "receipt": "order_rcptid_{orderId}"}}
     */
    String createOrder(JSONObject orderRequest) throws Exception;
}
