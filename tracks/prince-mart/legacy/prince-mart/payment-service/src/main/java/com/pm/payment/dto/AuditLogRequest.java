package com.pm.payment.dto;

public class AuditLogRequest {
    private String serviceName;
    private String action;
    private Long userId;
    private String dataBefore;
    private String dataAfter;

    public AuditLogRequest() {}

    public AuditLogRequest(String serviceName, String action, Long userId, String dataBefore, String dataAfter) {
        this.serviceName = serviceName;
        this.action = action;
        this.userId = userId;
        this.dataBefore = dataBefore;
        this.dataAfter = dataAfter;
    }

    // Getters and Setters
    public String getServiceName() { return serviceName; }
    public void setServiceName(String serviceName) { this.serviceName = serviceName; }

    public String getAction() { return action; }
    public void setAction(String action) { this.action = action; }

    public Long getUserId() { return userId; }
    public void setUserId(Long userId) { this.userId = userId; }

    public String getDataBefore() { return dataBefore; }
    public void setDataBefore(String dataBefore) { this.dataBefore = dataBefore; }

    public String getDataAfter() { return dataAfter; }
    public void setDataAfter(String dataAfter) { this.dataAfter = dataAfter; }
}