# Audit Trail وسلامة السجلات

## اليوم

- جدول `audit_logs` مع `event_type`, `actor`, `company_id`, `created_at`
- تصدير CSV / تقارير PDF

## تحسينات مستهدفة

1. **Hash chain** لكل سطر (prev_hash + payload_hash)
2. تصدير **SIEM** (JSON Lines / CEF)
3. منع UPDATE/DELETE على `audit_logs` (DB trigger أو role)
4. نسخ يومي إلى WORM storage للعملاء الحكوميين

## أحداث حرجة (يجب أن تُسجّل دائماً)

- login / logout / SSO
- تغيير صلاحيات
- تصدير بيانات
- legal hold
- فشل امتثال / قفل مستأجر
