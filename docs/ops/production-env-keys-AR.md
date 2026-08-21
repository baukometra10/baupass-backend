# مفاتيح الإنتاج — ما تضعها على Railway (Platform + Platform-Worker)

بعد Postgres + Worker: انسخ القيم أدناه في **Variables** لكل خدمة حسب العمود.

## Platform (API)

| المفتاح | القيمة المقترحة | ملاحظة |
|--------|------------------|--------|
| `SUPPIX_PG_RUNTIME` | `1` | يعمل الآن |
| `SUPPIX_PG_REQUIRED` | `1` | بعد التفعيل النهائي (لا رجوع تلقائي لـ SQLite) |
| `SUPPIX_EMBED_RQ_WORKER` | `0` | Worker منفصل |
| `SUPPIX_WEB_REPLICAS` | `1` → ثم `2` | **فقط بعد S3** |
| `DATABASE_URL` | مرجع Postgres | `${{Postgres.DATABASE_URL}}` |
| `REDIS_URL` | مرجع Redis | `${{Redis.REDIS_URL}}` |
| `BAUPASS_DB_PATH` | `/data/baupass.db` | احتياطي rollback فقط |
| `BAUPASS_PG_DR_SNAPSHOT_SCHEDULE` | `1` | لقطات DR مجدولة |
| `BAUPASS_PG_DR_UPLOAD_S3` | `1` | بعد ضبط S3 |
| `UPLOAD_BACKEND` | `s3` | بعد إنشاء الـ bucket |
| `S3_BUCKET` | *(منك)* | اسم الـ bucket |
| `S3_ENDPOINT_URL` | *(منك)* | R2/MinIO؛ فارغ لـ AWS |
| `S3_REGION` | *(منك)* | مثل `auto` أو `eu-central-1` |
| `S3_ACCESS_KEY` | *(منك)* | Access Key |
| `S3_SECRET_KEY` | *(منك)* | Secret Key |
| `BAUPASS_SAML_USE_SIGNXML` | `1` | بعد أن تتضمن الصورة `signxml` (الصورة الجديدة) |
| `BAUPASS_FIELD_ENCRYPTION_KEY` | *(سري قوي)* | إن لم يكن مضبوطًا |
| `BAUPASS_SECRET_KEY` / `SUPPIX_SECRET_KEY` | *(سري ≥32)* | موجود عادة |
| `PUBLIC_BASE_URL` | `https://suppix-ai-workpass.com` | موجود |

## Platform-Worker

| المفتاح | القيمة |
|--------|--------|
| `SUPPIX_PROCESS_ROLE` | `worker` |
| `SUPPIX_EMBED_RQ_WORKER` | `0` |
| `SUPPIX_PG_RUNTIME` | `1` |
| `DATABASE_URL` | نفس Postgres |
| `REDIS_URL` | نفس Redis |
| نفس أسرار التشفير/JWT كما في Platform | منسوخة |

## S3 — أنشئ أنت ثم الصق

**Cloudflare R2 (موصى به):**
1. R2 → Create bucket → انسخ اسم الـ bucket  
2. Manage R2 API Tokens → Create API token  
3 ضع على Platform (وWorker إن لزم للوسائط):

```text
UPLOAD_BACKEND=s3
S3_BUCKET=YOUR_BUCKET
S3_ENDPOINT_URL=https://YOUR_ACCOUNT_ID.r2.cloudflarestorage.com
S3_REGION=auto
S3_ACCESS_KEY=YOUR_ACCESS_KEY_ID
S3_SECRET_KEY=YOUR_SECRET_ACCESS_KEY
BAUPASS_PG_DR_UPLOAD_S3=1
```

**AWS S3:** نفس المفاتيح بدون `S3_ENDPOINT_URL` (أو endpoint إقليمي)، و`S3_REGION` مثل `eu-central-1`.

## بعد لصق S3

1. Redeploy Platform (+ Worker إن نسخت المفاتيح)  
2. `SUPPIX_WEB_REPLICAS=2` ثم:  
   `railway scale --service Platform eu-west=2`  
3. تحقق:  
   `python backend/ops/railway_ha_verify.py --base-url https://suppix-ai-workpass.com`

## خارج السيرفر (ليس env)

- اعتماد DATEV LODAS / ELSTER الرسمي عند الشريك
