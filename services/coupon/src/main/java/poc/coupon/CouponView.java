package poc.coupon;

/** 쿠폰 응답 본문. auto id·시각은 넣지 않는다(스택 간 같다는 보장이 없거나 실행 시점 값). */
public record CouponView(String couponKey, long discountAmount, String status, String usedByOrderKey) {

    static CouponView from(Coupon coupon) {
        return new CouponView(coupon.getCouponKey(), coupon.getDiscountAmount(), coupon.getStatus(),
                coupon.getUsedByOrderKey());
    }
}
