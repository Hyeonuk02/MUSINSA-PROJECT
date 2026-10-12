package poc.evidence;

import org.hibernate.resource.jdbc.spi.StatementInspector;

/**
 * Hibernate가 JDBC로 보내기 직전의 SQL 원문(바인딩 전, 값은 ?)을 현재 요청의 {@link ReplayContext}에 기록한다.
 *
 * <p>종류·횟수·테이블 계산, 정규화, SQL 주석 삽입을 하지 않는다 — 파생은 엔진의 몫이다.
 * ReplayContext가 없는 스레드(부팅, 스키마 검증, 재생 헤더 없는 요청)의 SQL은 무시한다.
 * SQL은 항상 그대로 반환한다.
 */
public class EvidenceStatementInspector implements StatementInspector {

    @Override
    public String inspect(String sql) {
        ReplayContext.current().ifPresent(context -> context.recordStatement(sql));
        return sql;
    }
}
