#!/usr/bin/env python3
"""Convert Arabic code comments/docstrings in backend/app to English (not UI strings)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "backend" / "app"

# Phrase-level replacements (longest first) for comment/docstring lines only.
REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("يُضيف", "Adds"),
    ("يُنفَّذ", "Executed"),
    ("يُنفذ", "Executes"),
    ("يُسجّل", "Registers"),
    ("يُسجل", "Registers"),
    ("يُعيد", "Returns"),
    ("يُحدد", "Determines"),
    ("يُجبر", "Requires"),
    ("يُرفق", "Attaches"),
    ("يُغلق", "Closes"),
    ("يُعيّن", "Sets"),
    ("يُطلق", "Raises"),
    ("يُستورد", "Imported"),
    ("يُضاف", "Added"),
    ("يُحذف", "Removed"),
    ("يُنقل", "Moved"),
    ("يُفعَّل", "Activates"),
    ("يُفعّل", "Activates"),
    ("للتطوير المحلي", "for local development"),
    ("للاختبارات الآلية", "for automated tests"),
    ("للإنتاج", "for production"),
    ("جميع القيم الحساسة", "All sensitive values"),
    ("لا توجد قيم حساسة", "No hardcoded secrets"),
    ("مسؤوليات هذا الملف", "Responsibilities of this module"),
    ("انتقال إلى PostgreSQL", "PostgreSQL migration path"),
    ("عند الجاهزية", "When ready"),
    ("مع الحفاظ على", "while keeping"),
    ("نفس الواجهة", "the same interface"),
    ("يمنع تشغيل migrations بالتوازي", "Prevents parallel migration runs"),
    ("يُحدد مسار قاعدة البيانات", "Resolves database file path"),
    ("بالأولوية", "priority order"),
    ("الطلبات التي تُعدّل البيانات", "Mutating HTTP methods"),
    ("تحتاج CSRF protection", "require CSRF protection"),
    ("Endpoints مستثناة", "CSRF-exempt endpoints"),
    ("APIs التي تستخدم Bearer tokens", "APIs using Bearer tokens only"),
    ("لها حماية خاصة", "have separate protection"),
    ("Security headers", "Security headers"),
    ("فقط على HTTPS", "HTTPS only"),
    ("إخفاء معلومات الـ server", "Strip server identification headers"),
    ("CSRF Token في cookies", "CSRF token cookie for SPA"),
    ("يجب أن يقرأه JavaScript", "readable by JavaScript (not HttpOnly)"),
    ("Admin/mobile APIs with Bearer token", "Admin/mobile APIs with Bearer token"),
    ("استثناء Content-Type", "Skip CSRF for JSON content type"),
    ("نتحقق من Origin بدلاً من", "validate Origin instead of"),
    ("CSRF Token check", "CSRF token check"),
    ("form submissions", "form submissions"),
    ("يتحقق من Origin header", "Validates Origin header"),
    ("طلبات بدون Origin", "Requests without Origin"),
    ("مسموحة", "allowed"),
    ("Origin يطابق host", "Origin matches host"),
    ("Origin في القائمة البيضاء", "Origin in allowlist"),
    ("ملاحظة: لا نرفض هنا", "Note: log only; CORS enforces rejection"),
    ("يتحقق من صحة الـ context", "Validates tenant context"),
    ("هل يمكن لهذا المستخدم", "Whether this user may"),
    ("الوصول لبيانات شركة", "access a given company's data"),
    ("يُعيد الـ tenant context", "Returns tenant context for current request"),
    ("غير authenticated", "when unauthenticated"),
    ("يُعيّن الـ tenant context", "Sets tenant context"),
    ("يُستدعى من auth decorators", "called from auth decorators"),
    ("يُطلق استثناء", "raises on violation"),
    ("خطأ أمني خطير", "critical security violation"),
    ("يُسجَّل ويُرفع", "logged and raised"),
    ("لا نُعيد تفاصيل الخطأ", "do not expose details to client"),
    ("للـ rate limiting", "for rate limiting"),
    ("Lua Script", "Lua script"),
    ("atomic في Redis", "atomic in Redis"),
    ("atomic operation", "atomic operation"),
    ("لمنع race conditions", "prevents race conditions"),
    ("هل هذا الـ IP محظور", "Is IP banned"),
    ("حذف الطلبات القديمة", "Remove stale requests"),
    ("عدد الطلبات الحالية", "Current request count"),
    ("حظر IP", "Ban IP"),
    ("بشكل متكرر", "repeatedly"),
    ("تسجيل الطلب الحالي", "Record current request"),
    ("في حالة فشل Redis", "On Redis failure"),
    ("fail open", "fail open"),
    ("لتجنب outage", "to avoid outage"),
    ("يتحقق إذا كان IP محظوراً", "Checks if IP is banned"),
    ("حظر IP يدوي", "Manual IP ban"),
    ("من admin", "by admin"),
    ("إعادة تعيين عدador IP", "Reset IP counter"),
    ("IPs الداخلية", "Internal IPs"),
    ("لا تخضع لـ rate limiting", "exempt from rate limiting"),
    ("تحديد الـ scope", "Resolve rate-limit scope"),
    ("بناءً على المسار", "from request path"),
    ("يُحدد الـ scope المناسب", "Maps path to rate-limit scope"),
    ("المفتاح يُبنى في Redis", "Redis key pattern"),
    ("تعريفات الـ scopes", "Scope definitions"),
    ("مدة حظر IP", "IP ban duration"),
    ("بالثواني", "in seconds"),
    ("دقيقة", "minutes"),
    ("فشل", "failures"),
    ("ثم lockout", "then lockout"),
    ("البوابات تُولّد طلبات أكثر", "gates generate more requests"),
    ("تحديد مسار SQLite", "SQLite path or DATABASE_URL"),
    ("SQLite tuning", "SQLite tuning"),
    ("Flask Core", "Flask core"),
    ("Database", "Database"),
    ("Redis", "Redis"),
    ("Rate Limiting", "Rate limiting"),
    ("تسجيل جميع blueprints", "Register all blueprints"),
    ("يُضاف blueprint جديد", "Register new blueprints here when extracted"),
    ("من server.py", "from server.py"),
    ("يُستورد هنا لتفعيل", "Imported to register"),
    ("تسجيل الـ routes", "route handlers"),
    ("Health Check Routes", "Health check routes"),
    ("نموذج على blueprint", "Example blueprint module"),
    ("أول route منقول", "First route migrated"),
    ("Architecture الجديدة", "new architecture"),
)

ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


def _translate_line(line: str) -> str:
    if not ARABIC_RE.search(line):
        return line
    # Skip likely UI/i18n dict values (labelAr, Arabic user strings in quotes)
    if re.search(r'labelAr|"ar"\s*:|\'ar\'\s*:', line):
        return line
    if re.search(r'["\'][^"\']*[\u0600-\u06FF][^"\']*["\']', line) and "#" not in line.split('"')[0]:
        # Arabic inside string literal on non-comment line — keep (UI copy)
        if not line.strip().startswith("#") and '"""' not in line and "'''" not in line:
            return line
    out = line
    for ar, en in REPLACEMENTS:
        out = out.replace(ar, en)
    return out


def process_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    changed = False
    new_lines: list[str] = []
    in_module_doc = False
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if i == 0 and stripped.startswith('"""'):
            in_module_doc = True
        if in_module_doc:
            new_line = _translate_line(line)
            if new_line != line:
                changed = True
            new_lines.append(new_line)
            if '"""' in line and i > 0:
                in_module_doc = False
            continue
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
            new_line = _translate_line(line)
            if new_line != line:
                changed = True
            new_lines.append(new_line)
        else:
            new_lines.append(line)
    if changed:
        path.write_text("".join(new_lines), encoding="utf-8")
    return changed


def main() -> int:
    count = 0
    for path in sorted(ROOT.rglob("*.py")):
        if process_file(path):
            print(f"updated: {path.relative_to(ROOT.parent.parent)}")
            count += 1
    print(f"Done. {count} file(s) updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
