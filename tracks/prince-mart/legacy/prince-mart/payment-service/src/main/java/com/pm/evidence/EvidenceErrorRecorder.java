package com.pm.evidence;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.Ordered;
import org.springframework.web.servlet.HandlerExceptionResolver;
import org.springframework.web.servlet.ModelAndView;

/**
 * [LEGACY_CHANGES L-I2] Error Path: 컨트롤러에서 던져진 예외 class를 기록한다.
 *
 * <p>가장 먼저 호출되는 resolver로 등록되어 예외를 기록만 하고 null을 돌려준다. 그러면 기존 GlobalExceptionHandler
 * (@ControllerAdvice)가 그대로 처리한다(응답은 바뀌지 않는다). B6처럼 모든 RuntimeException이 404가 되는 경우에도
 * 실제 예외 class(ResourceNotFoundException, IllegalStateException …)를 구분할 수 있다.
 */
final class EvidenceErrorRecorder implements HandlerExceptionResolver, Ordered {

    @Override
    public ModelAndView resolveException(HttpServletRequest request, HttpServletResponse response, Object handler, Exception ex) {
        EvidenceContext.Record r = EvidenceContext.current();
        if (r != null) r.error(ex);
        return null;
    }

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }
}
