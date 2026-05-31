# بيئات مخصصة (Dev / UAT / Production)

## الوضع الحالي

- **Production:** Railway (أو on-prem Helm)
- **Staging:** `docs/staging-railway-AR.md`
- **Local:** `docs/local-dev-quickstart-AR.md`

## نموذج Enterprise

| بيئة | DB | بيانات |
|------|-----|--------|
| Development | منفصلة | بيانات وهمية |
| UAT / Staging | منفصلة | anonymized copy |
| Production | معزولة | حية |

## Variables

نسخ `BAUPASS_*` لكل بيئة — لا مشاركة `OPENAI_API_KEY` production مع UAT إن أمكن.

## CI

نشر UAT من فرع `staging`؛ موافقة عميل قبل promote إلى production tag.
