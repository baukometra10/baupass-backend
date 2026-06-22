# استمرارية الأعمال (BCP) — WorkPass

## علاقة DR

التفاصيل التقنية: `disaster-recovery-AR.md` · `enterprise-backup-restore-runbook.md`.

## أهداف

| مؤشر | قيمة افتراضية | ملاحظة |
|------|---------------|--------|
| RTO | 4 ساعات | استعادة API + DB |
| RPO | 24 ساعة | نسخ احتياطي يومي |
| RTO بيانات حرجة | 1 ساعة | عند تفعيل PG replication لاحقاً |

## سيناريوهات

1. **تعطل Railway / السحابة** — استعادة من backup على مزود بديل أو on-prem Helm
2. **فساد DB** — restore من `ops/db_backup.py` + التحقق من migrations
3. **اختراق** — `incident-response-AR.md` + تدوير secrets + invalidate sessions
4. **IdP معطل** — fallback محلي (مستخدمين غير SSO فقط) — توثيق في العقد

## اختبار سنوي

- Tabletop exercise (ساعتان)
- Restore drill موثّق (بند 28): تاريخ، نتيجة، فجوات

## تواصل الأزمات

قائمة on-call · قنوات Slack/Teams · إشعار عملاء Enterprise خلال 24h لحوادث P1.
