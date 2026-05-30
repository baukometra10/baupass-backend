# Security Architecture — BauPass (ملخص)

```mermaid
flowchart TB
  subgraph clients [Clients]
    CP[Control Pass Web]
    WA[Worker App]
    ADM[Admin v2]
    TS[Turnstile]
  end
  subgraph edge [Edge]
    TLS[HTTPS / WAF]
    CDN[CDN optional]
  end
  subgraph app [Application]
    API[Flask API server.py + domains + platform]
    SSO[SSO: Entra Google Keycloak SAML]
  end
  subgraph data [Data]
    PG[(PostgreSQL)]
    OBJ[Object storage uploads]
    REDIS[(Redis queues)]
  end
  clients --> TLS --> API
  API --> SSO
  API --> PG
  API --> OBJ
  API --> REDIS
```

## مبادئ

- **عزل المستأجر:** `company_id` في كل استعلام حساس
- **أقل صلاحية:** RBAC + أدوار مؤسسية تدريجياً
- **تشفير النقل:** TLS إلزامي
- **أسرار:** Env / Key Vault — لا في Git
- **تدقيق:** `audit_logs` + تصدير PDF

## Trust boundaries

| Zone | وصف |
|------|-----|
| Public internet | متصفحات العملاء |
| App tier | API + workers |
| Data tier | PostgreSQL, Redis, blobs |
| IdP | Entra / Keycloak / SAML IdP |
