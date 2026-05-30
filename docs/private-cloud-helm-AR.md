# سحابة خاصة — Helm على Kubernetes

## المتطلبات

- Cluster (AKS / on-prem K8s)
- `kubectl`, `helm` 3+
- Secret `baupass-secrets` (PostgreSQL, SMTP, مفاتيح التشفير، …)

## تثبيت سريع

```bash
kubectl create namespace baupass
kubectl -n baupass create secret generic baupass-secrets --from-env-file=.env.production

helm upgrade --install baupass ./deploy/helm/baupass \
  -n baupass \
  --set image.repository=your-registry/baupass \
  --set image.tag=latest \
  --set ingress.enabled=true \
  --set ingress.host=baupass.yourdomain.ae
```

## الملفات

| المسار | الوصف |
|--------|--------|
| `deploy/helm/baupass/` | Chart كامل (API + RQ worker + HPA) |
| `deploy/k8s/` | Manifests خام (بدون Helm) |

## متغيرات مهمة في Secret

- `DATABASE_URL` — PostgreSQL
- `BAUPASS_RTSP_BRIDGE_TOKEN`, `BAUPASS_SIGNATURE_BRIDGE_TOKEN`
- `BAUPASS_AZURE_FACE_*` — مطابقة وجه اختيارية
- `BAUPASS_ENTRA_*` — SSO (انظر `docs/sso-entra-AR.md`)

## Railway مقابل خاص

Railway مناسب للتجربة والإنتاج الصغير. Helm للجهات التي تطلب **بيانات داخل الإمارات/أوروبا** وعزل شبكة كامل.
