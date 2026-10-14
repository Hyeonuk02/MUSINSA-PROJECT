package poc.order

/**
 * Phase 3.3: 결제가 처음 PAID로 바뀐 사실. 트랜잭션 커밋 뒤 order.paid로 발행된다(OrderEventPublisher).
 *
 * Phase 3.5-v1.3: Java record → Kotlin data class. Java 사용처가 남지 않아 `@JvmRecord`를 쓰지 않는다
 * (페이로드 JSON은 앱 JsonMapper + jackson-module-kotlin이 만든다).
 */
data class OrderPaid(val orderKey: String, val amount: Long, val couponKey: String?)
