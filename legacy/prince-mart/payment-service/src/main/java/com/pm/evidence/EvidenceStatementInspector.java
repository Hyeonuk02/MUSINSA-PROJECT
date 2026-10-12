package com.pm.evidence;

import org.hibernate.resource.jdbc.spi.StatementInspector;

/**
 * [LEGACY_CHANGES L-I2] DB 접근: Hibernate가 준비하는 SQL을 현재 요청의 Evidence에 기록한다. SQL은 바꾸지 않는다.
 * 설정: {@code spring.jpa.properties.hibernate.session_factory.statement_inspector}.
 */
public class EvidenceStatementInspector implements StatementInspector {

    @Override
    public String inspect(String sql) {
        EvidenceContext.Record r = EvidenceContext.current();
        if (r != null) r.sql(sql);
        return sql;
    }
}
