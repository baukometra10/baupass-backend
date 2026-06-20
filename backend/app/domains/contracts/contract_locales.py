from __future__ import annotations

import re
from typing import Any


SUPPORTED_LANGS = frozenset({"de", "en", "ar", "tr", "fr", "es", "it", "pl"})

JURISDICTION_META: dict[str, dict[str, Any]] = {
    "DE": {"currency": "EUR", "default_lang": "de", "names": {"de": "Deutschland", "en": "Germany", "ar": "ألمانيا"}},
    "AT": {"currency": "EUR", "default_lang": "de", "names": {"de": "Österreich", "en": "Austria", "ar": "النمسا"}},
    "CH": {"currency": "CHF", "default_lang": "de", "names": {"de": "Schweiz", "en": "Switzerland", "ar": "سويسرا"}},
    "FR": {"currency": "EUR", "default_lang": "fr", "names": {"de": "Frankreich", "en": "France", "ar": "فرنسا"}},
    "NL": {"currency": "EUR", "default_lang": "en", "names": {"de": "Niederlande", "en": "Netherlands", "ar": "هولندا"}},
    "BE": {"currency": "EUR", "default_lang": "en", "names": {"de": "Belgien", "en": "Belgium", "ar": "بلجيكا"}},
    "IT": {"currency": "EUR", "default_lang": "it", "names": {"de": "Italien", "en": "Italy", "ar": "إيطاليا"}},
    "ES": {"currency": "EUR", "default_lang": "es", "names": {"de": "Spanien", "en": "Spain", "ar": "إسبانيا"}},
    "PL": {"currency": "PLN", "default_lang": "pl", "names": {"de": "Polen", "en": "Poland", "ar": "بولندا"}},
    "EU": {"currency": "EUR", "default_lang": "en", "names": {"de": "Europäische Union", "en": "European Union", "ar": "الاتحاد الأوروبي"}},
    "SA": {"currency": "SAR", "default_lang": "ar", "names": {"de": "Saudi-Arabien", "en": "Saudi Arabia", "ar": "المملكة العربية السعودية"}},
    "AE": {"currency": "AED", "default_lang": "ar", "names": {"de": "Vereinigte Arabische Emirate", "en": "United Arab Emirates", "ar": "الإمارات العربية المتحدة"}},
    "QA": {"currency": "QAR", "default_lang": "ar", "names": {"de": "Katar", "en": "Qatar", "ar": "قطر"}},
    "KW": {"currency": "KWD", "default_lang": "ar", "names": {"de": "Kuwait", "en": "Kuwait", "ar": "الكويت"}},
    "BH": {"currency": "BHD", "default_lang": "ar", "names": {"de": "Bahrain", "en": "Bahrain", "ar": "البحرين"}},
    "OM": {"currency": "OMR", "default_lang": "ar", "names": {"de": "Oman", "en": "Oman", "ar": "عُمان"}},
    "JO": {"currency": "JOD", "default_lang": "ar", "names": {"de": "Jordanien", "en": "Jordan", "ar": "الأردن"}},
    "LB": {"currency": "LBP", "default_lang": "ar", "names": {"de": "Libanon", "en": "Lebanon", "ar": "لبنان"}},
    "EG": {"currency": "EGP", "default_lang": "ar", "names": {"de": "Ägypten", "en": "Egypt", "ar": "مصر"}},
    "TR": {"currency": "TRY", "default_lang": "tr", "names": {"de": "Türkei", "en": "Turkey", "ar": "تركيا"}},
    "US": {"currency": "USD", "default_lang": "en", "names": {"de": "USA", "en": "United States", "ar": "الولايات المتحدة"}},
    "CA": {"currency": "CAD", "default_lang": "en", "names": {"de": "Kanada", "en": "Canada", "ar": "كندا"}},
    "MX": {"currency": "MXN", "default_lang": "en", "names": {"de": "Mexiko", "en": "Mexico", "ar": "المكسيك"}},
    "BR": {"currency": "BRL", "default_lang": "en", "names": {"de": "Brasilien", "en": "Brazil", "ar": "البرازيل"}},
    "IN": {"currency": "INR", "default_lang": "en", "names": {"de": "Indien", "en": "India", "ar": "الهند"}},
    "PK": {"currency": "PKR", "default_lang": "en", "names": {"de": "Pakistan", "en": "Pakistan", "ar": "باكستان"}},
    "SG": {"currency": "SGD", "default_lang": "en", "names": {"de": "Singapur", "en": "Singapore", "ar": "سنغافورة"}},
    "MY": {"currency": "MYR", "default_lang": "en", "names": {"de": "Malaysia", "en": "Malaysia", "ar": "ماليزيا"}},
    "AU": {"currency": "AUD", "default_lang": "en", "names": {"de": "Australien", "en": "Australia", "ar": "أستراليا"}},
    "MA": {"currency": "MAD", "default_lang": "ar", "names": {"de": "Marokko", "en": "Morocco", "ar": "المغرب"}},
    "TN": {"currency": "TND", "default_lang": "ar", "names": {"de": "Tunesien", "en": "Tunisia", "ar": "تونس"}},
    "ZA": {"currency": "ZAR", "default_lang": "en", "names": {"de": "Südafrika", "en": "South Africa", "ar": "جنوب أفريقيا"}},
    "INT": {"currency": "EUR", "default_lang": "en", "names": {"de": "International", "en": "International", "ar": "دولي"}},
}


def normalize_lang(lang: str | None) -> str:
    code = str(lang or "de").strip().lower()[:2]
    return code if code in SUPPORTED_LANGS else "de"


def normalize_jurisdiction(code: str | None) -> str:
    value = str(code or "DE").strip().upper()
    return value if value in JURISDICTION_META else "INT"


def jurisdiction_name(code: str | None, lang: str | None) -> str:
    jurisdiction = normalize_jurisdiction(code)
    lang_code = normalize_lang(lang)
    meta = JURISDICTION_META[jurisdiction]
    return str(meta["names"].get(lang_code) or meta["names"]["en"])


def default_currency_for_jurisdiction(code: str | None) -> str:
    return str(JURISDICTION_META.get(normalize_jurisdiction(code), {}).get("currency") or "EUR")


def default_lang_for_jurisdiction(code: str | None) -> str:
    return normalize_lang(JURISDICTION_META.get(normalize_jurisdiction(code), {}).get("default_lang"))


def _t(lang: str, de: str, en: str, ar: str) -> str:
    lang_code = normalize_lang(lang)
    if lang_code == "ar":
        return ar
    if lang_code == "en":
        return en
    if lang_code == "de":
        return de
    # tr, fr, es, it, pl — fallback to English until dedicated strings are added
    return en


def _legal_basis(lang: str, jurisdiction: str) -> str:
    jurisdiction = normalize_jurisdiction(jurisdiction)
    lang = normalize_lang(lang)
    country = jurisdiction_name(jurisdiction, lang)
    mapping: dict[str, dict[str, str]] = {
        "DE": {
            "de": "Es gilt deutsches Arbeitsrecht (u. a. BGB, NachwG, EntgFG, BUrlG).",
            "en": "German employment law applies (including BGB, NachwG, EntgFG, BUrlG).",
            "ar": "يسري نظام العمل الألماني (بما في ذلك BGB وNachwG).",
        },
        "AT": {
            "de": "Es gilt österreichisches Arbeitsrecht (u. a. ABGB, ArbVG, AZG).",
            "en": "Austrian employment law applies (including ABGB, ArbVG, AZG).",
            "ar": "يسري نظام العمل النمساوي.",
        },
        "CH": {
            "de": "Es gilt schweizerisches Arbeitsrecht (u. a. OR, ArG).",
            "en": "Swiss employment law applies (including OR, ArG).",
            "ar": "يسري نظام العمل السويسري.",
        },
        "FR": {
            "de": "Es gilt französisches Arbeitsrecht (Code du travail).",
            "en": "French employment law applies (Code du travail).",
            "ar": "يسري قانون العمل الفرنسي.",
        },
        "US": {
            "de": f"Es gilt das Arbeitsrecht der USA ({country}); Beschäftigung kann „at-will“ sein, sofern nicht abweichend vereinbart.",
            "en": f"United States employment law applies ({country}); employment may be at-will unless otherwise agreed.",
            "ar": f"يسري قانون العمل في {country}؛ وقد تكون العلاقة «at-will» ما لم يُتفق على خلاف ذلك.",
        },
        "SA": {
            "de": "Es gilt das saudische Arbeitsrecht (Labor Law / نظام العمل).",
            "en": "Saudi Labor Law applies.",
            "ar": "يسري نظام العمل السعودي.",
        },
        "AE": {
            "de": "Es gilt das Arbeitsrecht der VAE (Federal Decree-Law No. 33 of 2021).",
            "en": "UAE Federal Decree-Law No. 33 of 2021 on employment applies.",
            "ar": "يسري المرسوم الاتحادي رقم 33 لسنة 2021 بشأن تنظيم علاقات العمل في الإمارات.",
        },
        "QA": {
            "de": "Es gilt das katarische Arbeitsgesetz (Law No. 14 of 2004).",
            "en": "Qatar Labour Law No. 14 of 2004 applies.",
            "ar": "يسري قانون العمل القطري رقم 14 لسنة 2004.",
        },
        "EG": {
            "de": "Es gilt ägyptisches Arbeitsrecht (Law No. 12 of 2003).",
            "en": "Egyptian Labour Law No. 12 of 2003 applies.",
            "ar": "يسري قانون العمل المصري رقم 12 لسنة 2003.",
        },
        "TR": {
            "de": "Es gilt türkisches Arbeitsrecht (Arbeitsgesetz Nr. 4857).",
            "en": "Turkish Labour Law No. 4857 applies.",
            "ar": "يسري قانون العمل التركي رقم 4857.",
        },
    }
    if jurisdiction in mapping:
        return mapping[jurisdiction].get(lang) or mapping[jurisdiction]["en"]
    return _t(
        lang,
        f"Es gelten die arbeitsrechtlichen Bestimmungen von {country}.",
        f"The employment laws of {country} apply.",
        f"تسري أحكام قانون العمل في {country}.",
    )


def salary_label(form: dict[str, Any], lang: str, jurisdiction: str) -> str:
    lang = normalize_lang(lang)
    salary_type = str(form.get("salary_type") or "monthly_fixed").strip()
    currency = str(form.get("currency") or default_currency_for_jurisdiction(jurisdiction)).strip()
    if salary_type == "hourly":
        rate = str(form.get("hourly_rate") or "").strip()
        if rate:
            return _t(lang, f"einen Stundenlohn von {rate} {currency}", f"an hourly wage of {rate} {currency}", f"أجرًا بالساعة قدره {rate} {currency}")
        return _t(lang, "einen Stundenlohn nach Vereinbarung", "an hourly wage as agreed", "أجرًا بالساعة وفق الاتفاق")
    amount = str(form.get("salary_gross_monthly") or "").strip()
    if amount:
        return _t(lang, f"eine monatliche Bruttovergütung von {amount} {currency}", f"a gross monthly remuneration of {amount} {currency}", f"راتبًا شهريًا إجماليًا قدره {amount} {currency}")
    return _t(lang, "eine monatliche Bruttovergütung nach Vereinbarung", "gross monthly remuneration as agreed", "راتبًا شهريًا وفق الاتفاق")


def document_title(lang: str, jurisdiction: str, contract_title: str | None = None) -> str:
    if contract_title and str(contract_title).strip() not in ("Arbeitsvertrag", "Employment Contract", "عقد عمل"):
        return str(contract_title).strip()
    jurisdiction = normalize_jurisdiction(jurisdiction)
    if normalize_lang(lang) == "de" and jurisdiction in {"DE", "AT", "CH"}:
        return "Arbeitsvertrag (ohne Tarifbindung)"
    return _t(lang, "Arbeitsvertrag", "Employment Contract", "عقد عمل")


def preamble_html(
    *,
    lang: str,
    jurisdiction: str,
    company_name: str,
    employee_name: str,
    employee_address: str,
) -> str:
    lang = normalize_lang(lang)
    jurisdiction_label = jurisdiction_name(jurisdiction, lang)
    addr = employee_address or _t(lang, "………………………………………………………………………………………..", "………………………………………………………………………………………..", "………………………………………………………………………………………..")
    if lang == "ar":
        return (
            f"بين <b>{company_name}</b> — المشار إليها فيما يلي بـ «صاحب العمل» —<br/>"
            f"والسيد/السيدة <b>{employee_name}</b><br/>"
            f"المقيم/ة في {addr}<br/>"
            f"— المشار إليه/ا فيما يلي بـ «الموظف/ة» —<br/><br/>"
            f"في إطار قانون العمل المعمول به في {jurisdiction_label}، يتم إبرام عقد العمل التالي:"
        )
    if lang == "en":
        return (
            f"Between <b>{company_name}</b><br/>"
            f"— hereinafter referred to as the \"Employer\" —<br/><br/>"
            f"and<br/><br/>"
            f"<b>{employee_name}</b><br/>"
            f"residing at {addr}<br/>"
            f"— hereinafter referred to as the \"Employee\" —<br/><br/>"
            f"Under the employment laws of {jurisdiction_label}, the following employment contract is concluded:"
        )
    return (
        f"Zwischen <b>{company_name}</b><br/>"
        f"- nachfolgend „Arbeitgeber“ genannt -<br/><br/>"
        f"und<br/><br/>"
        f"Herrn/Frau <b>{employee_name}</b><br/>"
        f"wohnhaft {addr}<br/>"
        f"- nachfolgend „Arbeitnehmer/-in“ genannt -<br/><br/>"
        f"unter dem für {jurisdiction_label} geltenden Arbeitsrecht wird folgender Arbeitsvertrag geschlossen:"
    )


def signing_note(lang: str) -> str:
    return _t(
        lang,
        (
            "Hinweis zur Unterzeichnung: Sind Arbeitgeber und Arbeitnehmer/-in nicht am selben Ort, "
            "kann dieser Vertrag ausgedruckt, handschriftlich unterschrieben und gescannt oder postalisch "
            "übermittelt werden. Alternativ ist eine elektronische Unterzeichnung zulässig "
            "(z. B. qualifizierte elektronische Signatur oder eindeutig zugeordnete E-Mail-Bestätigung)."
        ),
        (
            "Signing note: If Employer and Employee are not in the same location, this contract may be printed, "
            "signed by hand, and sent by scan or post. Electronic signing is also permitted "
            "(e.g. qualified electronic signature or clearly attributable email confirmation)."
        ),
        (
            "ملاحظة التوقيع: إذا لم يكن صاحب العمل والموظف/ة في المكان نفسه، يمكن طباعة هذا العقد "
            "وتوقيعه يدويًا وإرساله مسحًا ضوئيًا أو بالبريد. ويُسمح أيضًا بالتوقيع الإلكتروني "
            "(مثل التوقيع الإلكتروني المؤهل أو تأكيد البريد الإلكتروني المنسوب بوضوح)."
        ),
    )


def signature_labels(lang: str) -> tuple[str, str, str]:
    lang = normalize_lang(lang)
    if lang == "ar":
        return ("المكان، التاريخ", "توقيع صاحب العمل", "توقيع الموظف/ة")
    if lang == "en":
        return ("Place, Date", "Employer signature", "Employee signature")
    return ("Ort, Datum", "Unterschrift Arbeitgeber", "Unterschrift Arbeitnehmer/-in")


def footer_text(lang: str) -> str:
    return _t(lang, "Erstellt mit BauPass", "Created with BauPass", "أُنشئ بواسطة BauPass")


def section_prefix(lang: str) -> str:
    if normalize_lang(lang) == "ar":
        return "المادة"
    if normalize_lang(lang) == "en":
        return "Section"
    return "§"


def format_section_heading(lang: str, number: int, title: str) -> str:
    prefix = section_prefix(lang)
    if normalize_lang(lang) == "de":
        return f"{prefix} {number} {title}"
    return f"{prefix} {number} — {title}"


def split_body_blocks(body_text: str, lang: str) -> list[str]:
    text = str(body_text or "").strip()
    if not text:
        return []
    lang = normalize_lang(lang)
    patterns = {
        "de": r"\n(?=§\s*\d+)",
        "en": r"\n(?=(?:Section|Article)\s+\d+)",
        "ar": r"\n(?=المادة\s*\d+)",
    }
    chunks = re.split(patterns.get(lang, patterns["de"]), text)
    if len(chunks) <= 1:
        chunks = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def is_section_heading(line: str, lang: str) -> bool:
    line = line.strip()
    lang = normalize_lang(lang)
    if lang == "de":
        return bool(re.match(r"^§\s*\d+", line))
    if lang == "en":
        return bool(re.match(r"^(Section|Article)\s+\d+", line, re.I))
    return line.startswith("المادة")


def build_fallback_contract_body(
    *,
    lang: str,
    jurisdiction: str,
    form: dict[str, Any],
    notes: str,
) -> str:
    lang = normalize_lang(lang)
    jurisdiction = normalize_jurisdiction(jurisdiction)
    job_title = str(form.get("job_title") or "………………………………").strip()
    work_location = str(form.get("work_location") or "").strip()
    start_date = str(form.get("start_date") or "").strip() or _t(lang, "nach Vereinbarung", "as agreed", "وفق الاتفاق")
    end_date = str(form.get("end_date") or "").strip()
    weekly_hours = str(form.get("weekly_hours") or "").strip() or _t(lang, "nach Vereinbarung", "as agreed", "وفق الاتفاق")
    probation_months = str(form.get("probation_months") or "6").strip()
    vacation_days = str(form.get("vacation_days") or "").strip() or _t(lang, "nach Vereinbarung", "as agreed", "وفق الاتفاق")
    salary_line = salary_label(form, lang, jurisdiction)
    legal = _legal_basis(lang, jurisdiction)
    location_clause = (
        f" {_t(lang, 'Arbeitsort:', 'Place of work:', 'مكان العمل:')} {work_location}."
        if work_location
        else ""
    )

    if lang == "ar":
        sections = [
            (1, "بداية العمل", f"يبدأ عقد العمل في {start_date}."),
            (2, "فترة التجربة", f"تُعتبر أول {probation_months} أشهر فترة تجربة وفق قانون العمل المعمول به في {jurisdiction_name(jurisdiction, lang)}."),
            (3, "الوظيفة", f"يُعيَّن الموظف/ة في وظيفة {job_title}.{location_clause}"),
            (4, "الأجر", f"يتقاضى الموظف/ة {salary_line}."),
            (5, "ساعات العمل", f"ساعات العمل الأسبوعية المنتظمة: {weekly_hours} ساعة."),
            (6, "الإجازة", f"يستحق الموظف/ة إجازة سنوية وفق القانون، بالإضافة إلى {vacation_days} يومًا إضافيًا إن وُجد."),
            (7, "المرض", "يجب إبلاغ صاحب العمل فورًا عن التعذر عن العمل وتقديم التقارير الطبية عند الطلب."),
            (8, "السرية", "يلتزم الموظف/ة بالحفاظ على سرية معلومات العمل والشركة."),
            (9, "عمل إضافي", "لا يجوز للموظف/ة القيام بعمل إضافي دون موافقة صاحب العمل."),
            (10, "إنهاء العقد", "يخضع إنهاء العقد للإجراءات والمدد المنصوص عليها في القانون المعمول به."),
            (11, "أحكام إضافية", notes or legal),
            (12, "تعديل العقد", "تتطلب أي تعديلات على هذا العقد موافقة خطية من الطرفين."),
        ]
        if end_date:
            sections.insert(1, (2, "مدة العقد", f"هذا العقد محدد المدة حتى {end_date}."))
        return "\n\n".join(f"{format_section_heading(lang, n, t)}\n{b}" for n, t, b in sections)

    if lang == "en":
        sections = [
            (1, "Commencement", f"Employment begins on {start_date}."),
            (2, "Probation", f"The first {probation_months} months constitute a probation period as permitted under the laws of {jurisdiction_name(jurisdiction, lang)}."),
            (3, "Position", f"The Employee is employed as {job_title}.{location_clause}"),
            (4, "Remuneration", f"The Employee receives {salary_line}."),
            (5, "Working hours", f"Regular weekly working time is {weekly_hours} hours."),
            (6, "Leave", f"Annual leave follows statutory minimums, plus {vacation_days} contractual days where agreed."),
            (7, "Sickness", "The Employee must notify the Employer without delay and provide medical certificates when required."),
            (8, "Confidentiality", "The Employee must keep business and trade secrets confidential."),
            (9, "Secondary employment", "Paid or conflicting secondary employment requires the Employer's consent."),
            (10, "Termination", "Termination follows statutory notice periods and formal requirements of applicable law."),
            (11, "Governing law", legal),
            (12, "Additional terms", notes or "No additional terms unless expressly agreed in writing."),
            (13, "Amendments", "Amendments to this contract require written form."),
        ]
        if end_date:
            sections.insert(1, (2, "Fixed term", f"This contract is fixed-term until {end_date}."))
        if jurisdiction == "US":
            sections.insert(10, (10, "At-will employment", "Unless otherwise stated, employment is at-will and may be terminated by either party subject to applicable law."))
        return "\n\n".join(f"{format_section_heading(lang, n, t)}\n{b}" for n, t, b in sections)

    # German default (DACH-style Muster)
    sections = [
        (1, "Beginn des Arbeitsverhältnisses", f"Das Arbeitsverhältnis beginnt am {start_date}."),
        (2, "Probezeit", f"Die ersten {probation_months} Monate gelten als Probezeit. Während der Probezeit kann das Arbeitsverhältnis beiderseits mit einer Frist von zwei Wochen gekündigt werden."),
        (3, "Tätigkeit", f"Der Arbeitnehmer wird als {job_title} eingestellt.{location_clause} Er verpflichtet sich, auch andere zumutbare Arbeiten auszuführen."),
        (4, "Arbeitsvergütung", f"Der Arbeitnehmer erhält {salary_line}."),
        (5, "Arbeitszeit", f"Die regelmäßige wöchentliche Arbeitszeit beträgt {weekly_hours} Stunden."),
        (6, "Urlaub", f"Der Arbeitnehmer hat Anspruch auf gesetzlichen Mindesturlaub sowie zusätzlich {vacation_days} vertragliche Urlaubstage, soweit vereinbart."),
        (7, "Krankheit", "Die Arbeitsverhinderung ist dem Arbeitgeber unverzüglich mitzuteilen. Eine ärztliche Bescheinigung ist spätestens am vierten Kalendertag vorzulegen."),
        (8, "Verschwiegenheitspflicht", "Der Arbeitnehmer verpflichtet sich, über Betriebs- und Geschäftsgeheimnisse Stillschweigen zu bewahren."),
        (9, "Nebentätigkeit", "Entgeltliche oder das Arbeitsverhältnis beeinträchtigende Nebenbeschäftigung bedarf der Zustimmung des Arbeitgebers."),
        (10, "Vertragsstrafe", "Bei schuldhafter Verletzung wesentlicher Vertragspflichten kann der Arbeitgeber eine Vertragsstrafe verhängen, soweit gesetzlich zulässig."),
        (11, "Kündigung", "Die Kündigung bedarf der Schriftform und richtet sich nach den gesetzlichen Fristen."),
        (12, "Verfall- und Ausschlussfristen", "Ansprüche aus dem Arbeitsverhältnis verfallen, wenn sie nicht innerhalb von drei Monaten nach Fälligkeit schriftlich geltend gemacht werden."),
        (13, "Zusätzliche Vereinbarungen", notes or legal),
        (14, "Vertragsänderungen und Nebenabreden", "Änderungen und Ergänzungen dieses Vertrages bedürfen der Schriftform."),
    ]
    if end_date:
        sections.insert(1, (2, "Befristung", f"Der Vertrag ist befristet bis zum {end_date}."))
    return "\n\n".join(f"{format_section_heading(lang, n, t)}\n{b}" for n, t, b in sections)


def build_ai_instructions(lang: str, jurisdiction: str) -> list[str]:
    lang = normalize_lang(lang)
    jurisdiction = normalize_jurisdiction(jurisdiction)
    country = jurisdiction_name(jurisdiction, lang)
    legal = _legal_basis(lang, jurisdiction)
    prefix = section_prefix(lang)

    structure_hint = {
        "de": (
            f"Use German Muster-style numbered paragraphs ({prefix} 1–{prefix} 14): "
            "Beginn, Probezeit/Befristung, Tätigkeit, Arbeitsvergütung, Arbeitszeit, Urlaub, Krankheit, "
            "Verschwiegenheit, Nebentätigkeit, Vertragsstrafe, Kündigung, Verfall-/Ausschlussfristen, "
            "Zusätzliche Vereinbarungen, Vertragsänderungen."
        ),
        "en": (
            f"Use numbered sections ({prefix} 1–{prefix} 13+): commencement, probation/fixed term, position, "
            "remuneration, working hours, leave, sickness, confidentiality, secondary employment, "
            "termination, governing law, additional terms, amendments."
        ),
        "ar": (
            f"Use numbered articles ({prefix} 1–{prefix} 12+): بداية العمل، فترة التجربة، الوظيفة، الأجر، "
            "ساعات العمل، الإجازة، المرض، السرية، عمل إضافي، إنهاء العقد، أحكام إضافية، تعديل العقد."
        ),
    }[lang]

    missing = {
        "de": "nach Vereinbarung",
        "en": "as agreed",
        "ar": "وفق الاتفاق",
    }[lang]

    return [
        f"Write the entire contract in language code '{lang}' only.",
        f"Jurisdiction / country of employment law: {country} ({jurisdiction}). {legal}",
        structure_hint,
        "Use complete legal sentences suitable for printing and signature — not bullet fragments.",
        "Industry-neutral wording (retail, office, healthcare, production, services, logistics, etc.).",
        "Support both fixed monthly salary and hourly compensation when specified in the form.",
        f"Do not invent facts; use '{missing}' for missing values.",
        "Do not include party preamble or signature lines (added automatically in PDF).",
        "Return only the contract body text without markdown fences.",
    ]
