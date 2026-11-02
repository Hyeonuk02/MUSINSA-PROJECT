#!/usr/bin/env python3
"""결함 패치 생성기 (E2). 결함마다 Legacy 소스의 어느 부분을 어떻게 바꾸는지가 여기 한 곳에 있다.

  python3 baseline/faults/make_patches.py     # baseline/faults/PF<n>-<svc>.patch를 다시 만들고 git apply --check로 확인

Legacy 소스는 바꾸지 않는다. 패치는 이미지 빌드 때만 적용된다(build.sh, DockerFile의 FAULT 빌드 인자).
같은 입력이면 같은 바이트의 패치가 나온다(머리줄 시각 제거).
"""
import pathlib, subprocess, shutil, tempfile
ROOT=pathlib.Path(__file__).resolve().parents[2]
LEG=ROOT/"legacy/prince-mart"; OUT=ROOT/"baseline/faults"
OS="src/main/java/com/pm/order/service/OrderService.java"
OR="src/main/java/com/pm/order/repository/OrderRepository.java"
OL="src/main/java/com/pm/order/event/PaymentCompletedListener.java"
PS="src/main/java/com/pm/payment/service/PaymentService.java"

def make(fault, svc, edits, header):
    tmp=pathlib.Path(tempfile.mkdtemp())
    out=[f"# {fault}-{svc}: {header}\n# git apply로 legacy/prince-mart/{svc}-service 아래에 적용(baseline/faults/build.sh)\n"]
    for rel, reps in edits.items():
        src=(LEG/f"{svc}-service"/rel).read_text()
        new=src
        for a,b in reps:
            assert new.count(a)==1, (fault, rel, a[:60], new.count(a))
            new=new.replace(a,b)
        (tmp/"a"/rel).parent.mkdir(parents=True, exist_ok=True); (tmp/"b"/rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp/"a"/rel).write_text(src); (tmp/"b"/rel).write_text(new)
        d=subprocess.run(["diff","-u",f"a/{rel}",f"b/{rel}"],cwd=tmp,capture_output=True,text=True).stdout
        # 파일 머리줄의 시각을 지워 다시 만들어도 같은 바이트가 되게 한다
        d="".join(l.split("\t")[0]+"\n" if l.startswith(("--- a/","+++ b/")) else l for l in d.splitlines(keepends=True))
        out.append(d)
    (OUT/f"{fault}-{svc}.patch").write_text("".join(out))
    shutil.rmtree(tmp)
    # 적용 가능 확인
    chk=pathlib.Path(tempfile.mkdtemp()); shutil.copytree(LEG/f"{svc}-service"/"src", chk/"src")
    r=subprocess.run(["git","apply","--check",str(OUT/f"{fault}-{svc}.patch")],cwd=chk,capture_output=True,text=True)
    shutil.rmtree(chk)
    print(f"{fault}-{svc}.patch", "OK" if r.returncode==0 else "FAIL "+r.stderr)

make("PF1","payment",{PS:[(
"""            String razorpayOrderId = paymentGateway.createOrder(orderRequest);
""","""            String razorpayOrderId = paymentGateway.createOrder(orderRequest);
            paymentGateway.createOrder(orderRequest);   // PF1: PG 주문 생성을 한 번 더 호출(중복 호출 결함)
""")]}, "진짜 결함: 결제 처리에서 가짜 PG 주문 생성을 2번 호출")

make("PF2","payment",{PS:[(
"""        paymentEventPublisher.publishPaymentCompleted(updatedPayment, dataBefore);
    }""","""        // PF2: PaymentCompleted 발행 누락(이벤트 누락 결함)
    }""")]}, "진짜 결함: 결제 확정에서 PaymentCompleted를 발행하지 않음")

make("PF3","order",{OS:[(
"""        try {
            inventoryClient.reduceStock(stockUpdates);
        } catch (Exception e) {
            throw new ResourceNotFoundException("Inventory update failed: " + e.getMessage());
        }

        try {
            cartClient.clearCart(userId);
        } catch (Exception e) {
            System.err.println("Non-critical error: Failed to clear cart - " + e.getMessage());
        }
""","""        // PF3: 장바구니 비우기를 재고 차감보다 먼저 호출(동기 호출 순서 뒤바뀜)
        try {
            cartClient.clearCart(userId);
        } catch (Exception e) {
            System.err.println("Non-critical error: Failed to clear cart - " + e.getMessage());
        }

        try {
            inventoryClient.reduceStock(stockUpdates);
        } catch (Exception e) {
            throw new ResourceNotFoundException("Inventory update failed: " + e.getMessage());
        }
""")]}, "진짜 결함: 주문 생성에서 장바구니 비우기와 재고 차감의 호출 순서를 뒤바꿈")

make("PF4","order",{OS:[(
"""        try {
            // Using your existing Feign Client method
            inventoryClient.addStock(stockToRestore);
        } catch (Exception e) {""","""        try {
            // PF4: 취소 시 재고 복구 호출 누락(보상 누락 결함) - inventoryClient.addStock(stockToRestore) 제거
        } catch (Exception e) {""")]}, "진짜 결함: 주문 취소에서 재고 복구(add-stock-bulk) 호출 누락")

make("PF5","order",{OR:[(
"""    List<Order> findByUserId(Long userId);
}""","""    List<Order> findByUserId(Long userId);

    // PF5: 취소에서 주문과 품목을 한 번에 읽는다(fetch join)
    @Query("SELECT o FROM Order o LEFT JOIN FETCH o.items WHERE o.orderId = :orderId")
    java.util.Optional<Order> findWithItemsByOrderId(@Param("orderId") Long orderId);
}""")], OS:[(
"""        // 1. Fetch the Order
        Order order = orderRepository.findById(orderId)""","""        // 1. Fetch the Order (PF5: fetch join으로 품목까지 한 번에)
        Order order = orderRepository.findWithItemsByOrderId(orderId)""")]}, "정상 리팩터링: 주문 취소에서 주문·품목을 fetch join 한 번으로 조회(SELECT 2 -> 1)")

make("PF7","order",{OL:[(
"""        Long orderId = event.get("orderId").asLong();
""","""        Long orderId = event.get("orderId").asLong();

        // PF7: B4 수정 - 취소된 주문은 결제 완료 이벤트로 확정하지 않는다
        if ("CANCELLED".equalsIgnoreCase(orderService.getOrderByIdForAdmin(orderId).getOrderStatus())) {
            System.out.println("Skip PaymentCompleted for cancelled order: " + orderId);
            return;
        }
""")]}, "승인된 개선(B4 수정): 취소된 주문에 대한 PaymentCompleted는 상태를 바꾸지 않음")

make("PF8","order",{OS:[(
"""    public List<Order> getMyOrders(Long userId) {
		return orderRepository.findByUserId(userId);
	}""","""    public List<Order> getMyOrders(Long userId) {
		List<Order> orders = orderRepository.findByUserId(userId);
		orders.forEach(o -> o.getItems().size());   // PF8: 주문마다 품목을 지연 로딩(N+1)
		return orders;
	}""")]}, "성능 계약: 내 주문 조회에서 주문마다 품목을 따로 읽음(N+1)")

make("PF9","order",{OL:[(
"""        Long orderId = event.get("orderId").asLong();
""","""        Long orderId = event.get("orderId").asLong();

        // PF9: 멱등성 추가 - 이미 확정·결제된 주문의 재확정은 무시한다(이력·배송·감사·알림 중복 방지)
        Order before = orderService.getOrderByIdForAdmin(orderId);
        if ("CONFIRMED".equalsIgnoreCase(before.getOrderStatus()) && "PAID".equalsIgnoreCase(before.getPaymentStatus())) {
            System.out.println("Skip duplicate PaymentCompleted for order: " + orderId);
            return;
        }
""")]}, "승인된 개선(멱등성): 이미 확정·결제된 주문의 PaymentCompleted 재처리를 무시")

make("PF10","order",{OS:[(
"""import org.springframework.transaction.annotation.Transactional;
""","""import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
"""),("""        // Record Coupon Usage
        if (discountAmount.compareTo(BigDecimal.ZERO) > 0) {
            try {
                couponClient.useCoupon(userId, savedOrder.getOrderId(), appliedCoupon);
            } catch (Exception e) {
                System.err.println("Failed to record coupon usage: " + e.getMessage());
            }
        }""","""        // Record Coupon Usage (PF10: B1 수정 - 주문이 커밋된 뒤에 기록해서 Coupon의 역조회가 주문을 찾게 한다)
        if (discountAmount.compareTo(BigDecimal.ZERO) > 0) {
            final Long couponOrderId = savedOrder.getOrderId();
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    try {
                        couponClient.useCoupon(userId, couponOrderId, appliedCoupon);
                    } catch (Exception e) {
                        System.err.println("Failed to record coupon usage: " + e.getMessage());
                    }
                }
            });
        }""")]}, "승인된 개선(B1 수정): 쿠폰 사용 기록을 주문 커밋 뒤로 옮김(응답 status가 404 -> 200으로 바뀜)")
