# نموذج RBAC المؤسسي

## أدوار الكتالوج (`GET /api/platform/rbac/catalog`)

| الدور | النطاق | الحالة |
|-------|--------|--------|
| platform admin | عالمي | active |
| tenant admin | شركة | active |
| department_admin / department_manager | قسم | planned |
| site_manager | موقع | planned |
| regional_manager | إقليم | planned |
| security_officer | أمن | planned |
| compliance_officer | امتثال | planned |
| auditor | قراءة فقط | planned |
| access endpoint | بوابة | active |

## نموذج الصلاحيات (مستهدف)

```
role_assignment (user_id, role_id, scope_type, scope_id)
permission (id, resource, action)  # e.g. workers.read, reports.export
role_permission (role_id, permission_id)
```

## خريطة legacy → enterprise

- `company-admin` → `tenant_admin` + scopes
- `superadmin` → `platform_admin`

## فرض تدريجي

1. قراءة فقط لـ `auditor`
2. تقارير + audit لـ `compliance_officer`
3. إعدادات أمن لـ `security_officer`
