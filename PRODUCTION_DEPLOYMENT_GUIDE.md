# SUPPIX Platform — Production Deployment Guide

## Pre-Deployment Checklist

### 1. Database Optimization
```bash
# Create production database indexes
# PostgreSQL indexes for geospatial queries
CREATE INDEX idx_cameras_location 
  ON cameras USING GIST (
    ll_to_earth(latitude, longitude)
  );

CREATE INDEX idx_workers_company_location 
  ON workers (company_id, latitude, longitude);

CREATE INDEX idx_cameras_company 
  ON cameras (company_id);

CREATE INDEX idx_offline_records_device_id 
  ON offline_cache (device_id, sync_status);

CREATE INDEX idx_battery_stats_worker 
  ON battery_stats (worker_id, timestamp DESC);

# Analyze query plans
ANALYZE;
VACUUM ANALYZE;
```

### 2. Environment Configuration

**Production .env**
```
BAUPASS_ENV=production
DATABASE_URL=postgresql://user:pass@db.prod.internal:5432/suppix_prod
REDIS_URL=redis://cache.prod.internal:6379/0
SOCKET_IO_REDIS_URL=redis://cache.prod.internal:6379/1
SECRET_KEY=<generate-secure-key>
AUTH_TOKEN_EXPIRY=86400

# SUPPIX Configuration
SUPPIX_GEOSPATIAL_CACHE_TTL=3600
SUPPIX_OFFLINE_SYNC_INTERVAL=300
SUPPIX_BATTERY_SAMPLING_INTERVAL=30
SUPPIX_EDGE_AI_WEBHOOK_TIMEOUT=5

# Monitoring
SENTRY_DSN=https://xxxxx@sentry.io/xxxxx
DATADOG_API_KEY=xxxxxxxx
```

### 3. Production Database Migration

```bash
# Backup production database before migration
pg_dump -Fc suppix_prod > suppix_prod_backup_$(date +%Y%m%d).dump

# Run migrations
uv run --python 3.11 -- python -m alembic upgrade head

# Verify schema
psql suppix_prod -c "\d" | grep -E "cameras|workers|offline_cache|battery_stats"
```

### 4. WebSocket Configuration

**Production Socket.IO Settings**
```python
# backend/config.py additions
SOCKETIO_CONFIG = {
    'async_mode': 'threading',
    'cors_allowed_origins': ['https://app.suppix.io', 'https://dashboard.suppix.io'],
    'ping_timeout': 60,
    'ping_interval': 25,
    'max_http_buffer_size': 1e6,
    'engineio_logger': False,
}

SOCKETIO_MESSAGE_QUEUE = 'redis://cache.prod.internal:6379/1'
```

### 5. Monitoring & Alerts Setup

**Prometheus Metrics**
```yaml
# prometheus.yml additions
  - job_name: 'suppix-platform'
    static_configs:
      - targets: ['localhost:5000']
    metrics_path: '/api/suppix/metrics'
```

**Key Metrics to Monitor**
- `suppix_geospatial_query_latency_ms` (should be < 20ms)
- `suppix_websocket_connections_active` (should be stable)
- `suppix_offline_sync_queue_length` (should be < 100)
- `suppix_battery_sampling_intervals` (should match config)
- `suppix_edge_ai_detection_latency_ms` (should be < 200ms)

**Alert Rules**
```yaml
groups:
  - name: suppix_alerts
    rules:
      - alert: GeospatialQueryLatencyHigh
        expr: suppix_geospatial_query_latency_ms > 50
        for: 5m
        
      - alert: WebSocketConnectionLoss
        expr: rate(suppix_websocket_disconnects[5m]) > 0.1
        for: 2m
        
      - alert: OfflineSyncBacklog
        expr: suppix_offline_sync_queue_length > 500
        for: 10m
```

### 6. Security Audit

**Authentication & Authorization**
- [ ] All endpoints require Bearer token authentication
- [ ] Tokens validated against auth service
- [ ] Role-based access control (RBAC) enforced
- [ ] Company isolation verified in all queries

**Data Protection**
- [ ] TLS 1.3 required for all HTTPS connections
- [ ] Database connections use SSL
- [ ] Redis connections authenticated and encrypted
- [ ] Sensitive data (tokens, credentials) not logged

**API Security**
- [ ] Rate limiting enabled (10 req/sec per IP)
- [ ] CORS configured for authorized origins only
- [ ] CSRF protection on state-changing endpoints
- [ ] Input validation on all endpoints
- [ ] SQL injection prevention verified

**Infrastructure**
- [ ] VPC network isolated from public internet
- [ ] Security groups restrict ports
- [ ] WAF rules configured
- [ ] DDoS protection enabled
- [ ] VPN required for database access

### 7. Load Testing Results

**Target: 1000+ Concurrent Workers**

Run load test before production:
```bash
# Update CONFIG in backend/tests/load_test_suppix.py
CONFIG["CONCURRENT_USERS"] = 1000

# Run test
uv run --python 3.11 -- python backend/tests/load_test_suppix.py
```

**Success Criteria**
- Success rate: > 99.5%
- Avg response time: < 50ms
- P99 response time: < 200ms
- No connection timeouts
- Geospatial queries: < 20ms avg

### 8. Staging Deployment

**1. Create Staging Environment**
```bash
# Deploy to staging cluster
kubectl apply -f k8s/staging/suppix-deployment.yaml
kubectl apply -f k8s/staging/suppix-service.yaml
```

**2. Data Migration**
```bash
# Create anonymized staging data
pg_dump --data-only suppix_prod | \
  sed 's/real_email@example.com/test_emailXXXX@staging.local/g' | \
  psql suppix_staging
```

**3. Smoke Tests**
```bash
# Run integration tests against staging
uv run --python 3.11 -- pytest backend/tests/test_websocket_integration.py \
  --base-url=https://api-staging.suppix.io
```

### 9. Rollout Plan (Blue-Green Deployment)

**Week 1: Canary Release (5% of traffic)**
- Deploy to 1 production pod
- Monitor error rates and latency
- 99%+ success rate required

**Week 2: Gradual Rollout (25% → 50% → 75%)**
- Increase production pods daily
- Monitor per-region metrics
- Rollback plan ready

**Week 3: Full Production**
- 100% traffic to new version
- Keep v1 running for 24 hours (quick rollback)
- Archive logs and metrics

### 10. Post-Deployment Tasks

**1. Verify Integration**
```bash
# Health check
curl -H "Authorization: Bearer $TOKEN" \
  https://api.suppix.io/api/suppix/health

# Geospatial optimization
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.suppix.io/api/suppix/geospatial/nearest-cameras?latitude=40.7128&longitude=-74.0060&company_id=production&max_results=10"

# WebSocket connection
# Test via dashboard: https://dashboard.suppix.io/map
```

**2. Monitor First 24 Hours**
- Check error rates in Datadog
- Verify database query performance
- Monitor WebSocket connection stability
- Check battery optimization metrics

**3. Enable Advanced Features**
```bash
# After 24h of stability:
# - Enable edge AI processing
# - Increase offline sync frequency
# - Enable aggressive caching
```

## Rollback Procedure

If issues occur during production deployment:

```bash
# 1. Switch traffic back to v1
kubectl set image deployment/suppix-api \
  suppix-container=suppix:v1.0.0

# 2. Monitor metrics (10 minutes)
# - Error rate should return to baseline
# - Latency should normalize

# 3. Analyze root cause
# - Check error logs in Datadog
# - Review database performance
# - Inspect WebSocket stability

# 4. Fix and redeploy
# - Create hotfix branch
# - Run full test suite
# - Deploy to staging first
# - Then production canary (5%)
```

## Success Metrics (30 days post-deployment)

| Metric | Target | Current |
|--------|--------|---------|
| Uptime | 99.9% | - |
| Avg Response Time | < 20ms | - |
| P99 Latency | < 100ms | - |
| Error Rate | < 0.1% | - |
| Battery Improvement | +40-60% | - |
| Data Loss | 0 | - |
| WebSocket Stability | 99.5%+ | - |
| Geospatial Cache Hit Rate | 90%+ | - |

## Emergency Contacts

- On-Call Eng: Slack #suppix-oncall
- Database Admin: db-team@suppix.io
- Security Team: security@suppix.io
- Product Manager: pm@suppix.io

## Documentation

- Architecture: WEBSOCKETS_ARCHITECTURE_GUIDE.md
- Geospatial: GEOSPATIAL_OPTIMIZER_GUIDE.md
- Battery: FUSED_LOCATION_PROVIDER_GUIDE.md
- Offline: OFFLINE_GATEWAY_GUIDE.md
- Edge AI: EDGE_AI_GATEWAY_GUIDE.md
