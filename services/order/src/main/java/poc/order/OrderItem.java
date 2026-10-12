package poc.order;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

/**
 * 주문 라인. 응답의 items 순서는 요청 순서({@code lineNo})로 고정한다.
 */
@Entity
@Table(name = "order_items")
public class OrderItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private Order order;

    @Column(name = "line_no", nullable = false)
    private int lineNo;

    @Column(nullable = false)
    private String sku;

    @Column(nullable = false)
    private int qty;

    @Column(nullable = false)
    private long price;

    protected OrderItem() {
    }

    OrderItem(Order order, int lineNo, String sku, int qty, long price) {
        this.order = order;
        this.lineNo = lineNo;
        this.sku = sku;
        this.qty = qty;
        this.price = price;
    }

    public int getLineNo() { return lineNo; }
    public String getSku() { return sku; }
    public int getQty() { return qty; }
    public long getPrice() { return price; }
}
