package poc.order

import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.runApplication

/** Phase 3.5-v1.4: Java → Kotlin 전환(main은 최상위 함수 — 클래스 `poc.order.OrderApplicationKt`). */
@SpringBootApplication
class OrderApplication

fun main(args: Array<String>) {
    runApplication<OrderApplication>(*args)
}
