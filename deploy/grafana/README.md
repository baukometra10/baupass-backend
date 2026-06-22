# Grafana — WorkPass dashboards

## Import (manual)

1. Grafana → Dashboards → Import
2. Upload `baupass-dashboard.json`
3. Select Prometheus datasource pointing to your `/metrics` scrape target

## Docker Compose (provisioning)

Mount this folder:

```yaml
grafana:
  image: grafana/grafana:latest
  volumes:
    - ./deploy/grafana/provisioning:/etc/grafana/provisioning
    - ./deploy/grafana/baupass-dashboard.json:/etc/grafana/provisioning/dashboards/json/baupass.json
  ports:
    - "3000:3000"
```

Set Prometheus URL in `provisioning/datasources/prometheus.yml` to your scrape endpoint.

## Metrics source

WorkPass exposes Prometheus metrics at `GET /metrics` on the API service.
