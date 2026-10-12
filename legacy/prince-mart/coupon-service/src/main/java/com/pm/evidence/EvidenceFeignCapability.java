package com.pm.evidence;

import feign.Capability;
import feign.Client;
import feign.Response;

/**
 * [LEGACY_CHANGES L-I2] 나가는 호출: Feign 호출의 순서·method·URL·status를 현재 요청의 Evidence에 기록한다.
 *
 * <p>URL은 로드밸런서가 주소를 풀기 전의 논리 이름이다(http://COUPON-SERVICE/coupons/validate). 그래서 legacy/new가 같다.
 * Feign을 쓰지 않는 호출(가짜 PG RestClient)은 여기 잡히지 않고 WireMock journal로 수집한다.
 */
public final class EvidenceFeignCapability implements Capability {

    @Override
    public Client enrich(Client client) {
        return (request, options) -> {
            EvidenceContext.Record r = EvidenceContext.current();
            long start = System.nanoTime();
            try {
                Response response = client.execute(request, options);
                if (r != null) r.outbound(request.httpMethod().name(), request.url(), response.status(), null,
                        (System.nanoTime() - start) / 1_000_000);
                return response;
            } catch (java.io.IOException | RuntimeException e) {
                if (r != null) r.outbound(request.httpMethod().name(), request.url(), null, e.getClass().getName(),
                        (System.nanoTime() - start) / 1_000_000);
                throw e;
            }
        };
    }
}
