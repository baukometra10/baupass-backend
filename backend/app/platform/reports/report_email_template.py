"""Branded HTML/plain templates for Reporting department outbound mail."""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Any


def _load_branding() -> dict[str, str]:
    from backend.server import (
        DEFAULT_BRAND_ACCENT,
        DEFAULT_BRAND_PRIMARY,
        DEFAULT_OPERATOR_NAME,
        DEFAULT_PLATFORM_NAME,
        get_db,
    )

    platform_name = DEFAULT_PLATFORM_NAME
    operator_name = DEFAULT_OPERATOR_NAME
    primary = DEFAULT_BRAND_PRIMARY
    accent = DEFAULT_BRAND_ACCENT
    try:
        row = get_db().execute(
            """
            SELECT platform_name, operator_name, invoice_primary_color, invoice_accent_color
            FROM settings WHERE id = 1
            """
        ).fetchone()
        if row:
            platform_name = str(row["platform_name"] or platform_name).strip() or platform_name
            operator_name = str(row["operator_name"] or operator_name).strip() or operator_name
            primary = str(row["invoice_primary_color"] or primary).strip() or primary
            accent = str(row["invoice_accent_color"] or accent).strip() or accent
    except Exception:
        pass
    return {
        "platform_name": platform_name,
        "operator_name": operator_name,
        "primary": primary,
        "accent": accent,
    }


def _logo_svg(primary: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="52" height="52" viewBox="0 0 310 310" '
        'role="img" aria-label="Logo">'
        f'<rect width="310" height="310" rx="46" fill="{html.escape(primary)}"/>'
        '<path d="M56 224 L156 92 L256 224 Z" fill="#ffffff" opacity="0.94"/>'
        '<path d="M96 224 L156 144 L216 224 Z" fill="#12343b" opacity="0.95"/>'
        '<circle cx="235" cy="88" r="20" fill="#fff4e6"/>'
        "</svg>"
    )


def _split_message_lines(message: str) -> list[str]:
    lines: list[str] = []
    for raw in re.split(r"\r?\n+", (message or "").strip()):
        line = raw.strip()
        if line and line.lower() not in {"suppix", "workpass"}:
            lines.append(line)
    return lines or ["Ihr Bericht liegt als Anhang bei dieser E-Mail."]


def _attachment_cards_html(attachments: list[dict[str, str]], primary: str) -> str:
    if not attachments:
        return ""
    cards = []
    for item in attachments:
        name = html.escape(str(item.get("name") or "Anhang"))
        kind = html.escape(str(item.get("kind") or "Datei"))
        cards.append(
            f"""
            <tr>
              <td style="padding:0 0 10px;">
                <table width="100%" cellpadding="0" cellspacing="0"
                  style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;">
                  <tr>
                    <td style="width:54px;padding:14px 0 14px 16px;vertical-align:middle;">
                      <div style="width:38px;height:38px;border-radius:9px;
                        background:linear-gradient(135deg,{html.escape(primary)} 0%,#64748b 100%);
                        text-align:center;line-height:38px;color:#fff;font-size:11px;font-weight:700;">
                        {html.escape(kind[:4].upper())}
                      </div>
                    </td>
                    <td style="padding:14px 16px 14px 0;vertical-align:middle;">
                      <div style="font-size:14px;font-weight:600;color:#0f172a;">{name}</div>
                      <div style="font-size:12px;color:#64748b;margin-top:2px;">Im Anhang dieser E-Mail</div>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            """
        )
    return (
        '<table width="100%" cellpadding="0" cellspacing="0" style="margin:22px 0 8px;">'
        + "".join(cards)
        + "</table>"
    )


def build_report_email_bodies(
    *,
    report_title: str,
    message: str,
    company_name: str = "",
    period: str = "",
    report_badge: str = "Reporting",
    report_subtitle: str = "",
    attachment_labels: list[dict[str, str]] | None = None,
) -> tuple[str, str]:
    """Return (plain_text, html) for a branded reporting e-mail."""
    brand = _load_branding()
    platform = brand["platform_name"]
    operator = brand["operator_name"]
    primary = brand["primary"]
    accent = brand["accent"]
    period_label = period or datetime.now(timezone.utc).strftime("%d.%m.%Y")
    message_lines = _split_message_lines(message)
    attachments = list(attachment_labels or [])

    title_safe = report_title.strip() or "Bericht"
    subtitle_safe = (report_subtitle or "Automatischer Export aus dem Reporting-Bereich").strip()
    company_safe = company_name.strip()
    badge_safe = report_badge.strip() or "Reporting"

    plain_parts = [
        title_safe,
        "",
        *message_lines,
        "",
        f"Zeitraum: {period_label}",
    ]
    if company_safe:
        plain_parts.insert(2, f"Firma: {company_safe}")
    if attachments:
        plain_parts.extend(["", "Anhänge:"])
        plain_parts.extend(f"  • {a.get('name', 'Anhang')} ({a.get('kind', 'Datei')})" for a in attachments)
    plain_parts.extend(["", f"{platform} · {operator}", "Diese E-Mail wurde automatisch generiert."])
    plain = "\n".join(plain_parts)

    company_chip = ""
    if company_safe:
        company_chip = (
            f'<span style="display:inline-block;margin-top:10px;padding:6px 12px;'
            f'border-radius:999px;background:rgba(255,255,255,0.16);color:#fff;'
            f'font-size:12px;font-weight:600;letter-spacing:0.3px;">'
            f"{html.escape(company_safe)}</span>"
        )

    message_html = "".join(
        f'<p style="margin:0 0 12px;color:#334155;font-size:15px;line-height:1.65;">'
        f"{html.escape(line)}</p>"
        for line in message_lines
    )

    html_out = f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{html.escape(title_safe)}</title>
</head>
<body style="margin:0;padding:0;background:#eef2f7;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#eef2f7;padding:34px 12px;">
    <tr><td align="center">
      <table width="620" cellpadding="0" cellspacing="0"
        style="max-width:620px;width:100%;background:#ffffff;border-radius:16px;overflow:hidden;
        box-shadow:0 10px 40px rgba(15,23,42,0.10);">
        <tr>
          <td style="padding:0;background:linear-gradient(120deg,{html.escape(primary)} 0%,{html.escape(accent)} 100%);">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="padding:28px 32px 22px;">
                  <table cellpadding="0" cellspacing="0">
                    <tr>
                      <td style="vertical-align:middle;padding-right:14px;">{_logo_svg(primary)}</td>
                      <td style="vertical-align:middle;">
                        <div style="color:rgba(255,255,255,0.82);font-size:11px;font-weight:700;
                          letter-spacing:2.4px;text-transform:uppercase;">{html.escape(badge_safe)}</div>
                        <div style="color:#ffffff;font-size:24px;font-weight:800;line-height:1.2;margin-top:4px;">
                          {html.escape(platform)}
                        </div>
                        <div style="color:rgba(255,255,255,0.78);font-size:13px;margin-top:4px;">
                          {html.escape(subtitle_safe)}
                        </div>
                        {company_chip}
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:30px 32px 8px;">
            <div style="display:inline-block;padding:5px 10px;border-radius:999px;background:#f1f5f9;
              color:#475569;font-size:11px;font-weight:700;letter-spacing:1.6px;text-transform:uppercase;">
              Bericht bereit
            </div>
            <h1 style="margin:14px 0 8px;color:#0f172a;font-size:26px;line-height:1.25;font-weight:800;">
              {html.escape(title_safe)}
            </h1>
            <p style="margin:0;color:#64748b;font-size:13px;">Stand: {html.escape(period_label)}</p>
          </td>
        </tr>
        <tr>
          <td style="padding:8px 32px 0;">
            <table width="100%" cellpadding="0" cellspacing="0"
              style="background:linear-gradient(180deg,#f8fafc 0%,#ffffff 100%);
              border:1px solid #e2e8f0;border-radius:12px;">
              <tr>
                <td style="padding:22px 22px 18px;">
                  {message_html}
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:8px 32px 26px;">
            {_attachment_cards_html(attachments, primary)}
            <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:8px;">
              <tr>
                <td style="padding:14px 16px;border-radius:10px;background:#eff6ff;border:1px solid #bfdbfe;">
                  <span style="font-size:13px;color:#1e40af;font-weight:600;">
                    Tipp: Öffnen Sie den PDF-Anhang direkt in Ihrem Mail-Programm oder speichern Sie ihn für Ihr Archiv.
                  </span>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="background:#f8fafc;border-top:1px solid #e2e8f0;padding:18px 32px;text-align:center;">
            <p style="margin:0 0 6px;color:#475569;font-size:13px;font-weight:600;">
              {html.escape(platform)} · {html.escape(operator)}
            </p>
            <p style="margin:0;color:#94a3b8;font-size:11px;line-height:1.5;">
              Automatisch generiert aus dem Reporting-Bereich.<br>
              Bitte antworten Sie nicht auf diese E-Mail.
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
    return plain, html_out


def attachment_label_from_filename(filename: str) -> dict[str, str]:
    name = str(filename or "anhang.bin").strip()
    lower = name.lower()
    if lower.endswith(".pdf"):
        kind = "PDF"
    elif lower.endswith(".csv"):
        kind = "CSV"
    elif lower.endswith(".xlsx") or lower.endswith(".xls"):
        kind = "Excel"
    else:
        kind = "Datei"
    return {"name": name, "kind": kind}


def build_report_meta(
    *,
    report_title: str,
    message: str,
    company_name: str = "",
    period: str = "",
    report_badge: str = "Reporting",
    report_subtitle: str = "",
    pdf_filename: str = "",
    extra_filenames: list[str] | None = None,
) -> dict[str, Any]:
    labels = []
    if pdf_filename:
        labels.append(attachment_label_from_filename(pdf_filename))
    for fn in extra_filenames or []:
        labels.append(attachment_label_from_filename(fn))
    return {
        "report_title": report_title,
        "message": message,
        "company_name": company_name,
        "period": period,
        "report_badge": report_badge,
        "report_subtitle": report_subtitle,
        "attachment_labels": labels,
    }
