# النشر التلقائي — Railway + GitHub

الإنتاج: **https://baupass-production.up.railway.app**

## الوضع الحالي (تم التحقق)

| المسار | الوظيفة |
|--------|---------|
| **Railway ← GitHub** (الأساسي) | كل `git push` على `main` يبني Docker ويشغّل `python backend/entrypoint.py --mode prod` |
| **GitHub Actions** (احتياطي) | يعمل فقط إذا وُضعت الأسرار أدناه — وإلا يُتخطى بصمت |

تحقق سريع من جهازك:

```powershell
cd C:\Users\u4363\Desktop\baustelle
powershell -ExecutionPolicy Bypass -File .\deploy\verify-production-deploy.ps1
```

نجاح = `Production matches local HEAD` + `/api/health/platform` = OK + `platform-unified.css` في `index.html`.

بعد النشر في المتصفح: **Ctrl+F5** حتى لا يبقى `app.js` قديمًا في الكاش.

---

## 1) التأكد أن Railway مربوط بالمستودع

1. [railway.app](https://railway.app) → مشروع **baupass-production**
2. خدمة **web** (أو الاسم عندك) → **Settings** → **Source**
3. يجب أن يكون:
   - Repo: `baukometra10/baupass-backend`
   - Branch: `main`
4. إن ظهر `repository not found`:
   - **Disconnect** ثم **Connect Repo** من جديد
   - GitHub → [Railway App](https://github.com/settings/installations) → منح الوصول لـ `baupass-backend`

---

## 2) إعدادات الخدمة (مرة واحدة)

| الإعداد | القيمة |
|---------|--------|
| Builder | Dockerfile (`railway.json`) |
| Start | `python backend/entrypoint.py --mode prod` |
| Volume | mount **`/data`** |
| `BAUPASS_DB_PATH` | `/data/baupass.db` |
| `PUBLIC_BASE_URL` | `https://baupass-production.up.railway.app` |

تحقق:

```text
GET https://baupass-production.up.railway.app/api/health
```

- `deploy.railwayGitCommit` = آخر commit على `main`
- `db.persistent` = **true**

---

## 3) GitHub Actions كنسخة احتياطية (اختياري)

إذا تعطل نشر Railway من GitHub، فعّل Workflow:

**https://github.com/baukometra10/baupass-backend/settings/secrets/actions**

| Secret | من أين |
|--------|--------|
| `RAILWAY_TOKEN` | Railway → Account → [Tokens](https://railway.com/account/tokens) |
| `RAILWAY_SERVICE_ID` | Railway → Service **web** → Settings → **Service ID** |
| `PUBLIC_BASE_URL` | `https://baupass-production.up.railway.app` |
| `BAUPASS_SMOKE_TOKEN` | (اختياري) لاختبار E2E في الـ workflow |

ثم: **Actions** → **railway-deploy** → **Run workflow**.

بدون الأسرار الأولى يظهر في اللوق: `Railway deploy skipped` — هذا طبيعي إذا كان النشر عبر Railway مباشرة يعمل.

---

## 4) Railway CLI على جهازك (للمراقبة)

```powershell
npm install -g @railway/cli
powershell -ExecutionPolicy Bypass -File .\deploy\fix-railway-login.ps1
railway link   # Workspace -> baupass-production -> Service web
powershell -ExecutionPolicy Bypass -File .\deploy\railway-cli-status.ps1
```

نشر يدوي من المجلد (بدون انتظار Git):

```powershell
$env:RAILWAY_SERVICE_ID = "YOUR_SERVICE_ID"
powershell -ExecutionPolicy Bypass -File .\deploy\railway-up.ps1
```

---

## 5) سير العمل اليومي

```powershell
git add .
git commit -m "وصف التغيير"
git push origin main
# انتظر 2–5 دقائق
powershell -ExecutionPolicy Bypass -File .\deploy\verify-production-deploy.ps1
```

---

## 6) مشاكل شائعة

| العرض | الحل |
|--------|------|
| الموقع قديم لكن `/api/health` commit جديد | Ctrl+F5؛ أو مسح كاش المتصفح |
| `railwayGitCommit` قديم | Railway → Deployments → **Redeploy**؛ تحقق من فرع `main` |
| بيانات اختفت بعد النشر | Volume `/data` غير مربوط |
| `/api/health/platform` = 404 | أعد النشر بعد commit `a91771e` أو أحدث |
| Workflow لا ينشر | أضف `RAILWAY_TOKEN` + `RAILWAY_SERVICE_ID` أو اعتمد على Railway Git فقط |

مراجع: [github-railway.md](./github-railway.md) · [RAILWAY-COMPLETE-AR.md](./RAILWAY-COMPLETE-AR.md) · [railway-deploy-fix.md](./railway-deploy-fix.md)
