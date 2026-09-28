package com.pm.payment.controller;

import com.pm.payment.dto.PaymentRequest;
import com.pm.payment.dto.PaymentResponse;
import com.pm.payment.service.PaymentService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/payments")
public class PaymentController {

    private final PaymentService paymentService;

    public PaymentController(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    @PostMapping("/process")
    public ResponseEntity<PaymentResponse> process(@RequestBody PaymentRequest request) {
        return ResponseEntity.ok(paymentService.processPayment(request));
    }
    
    @GetMapping("/welcome")
    public String welcome() {
		return "Welcome!! This is the Payment Service for Prince Mart by Prince Inc.";
	}
    
    @PostMapping("/verify")
    public ResponseEntity<String> verifyPayment(@RequestParam String orderId, @RequestParam String paymentId) {
        // In a real app, we verify the 'razorpay_signature' here.
        // For now, let's manually trigger the success handshake!
        paymentService.completePaymentManually(orderId, paymentId);
        return ResponseEntity.ok("Payment Verified and Order Confirmed!");
    }
}