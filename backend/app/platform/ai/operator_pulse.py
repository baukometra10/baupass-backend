"""Prioritized daily recommendations for the AI Operator FAB (+ morning dispatch)."""
from __future__ import annotations

from typing import Any


def normalize_surface(surface: str | None = None, *, tab: str | None = None, path: str | None = None) -> str:
    """Map URL/tab hints to a stable surface key."""
    s = str(surface or "").strip().lower()
    t = str(tab or "").strip().lower()
    p = str(path or "").strip().lower()
    if s in {
        "contracts",
        "docs",
        "workers",
        "operations",
        "inbox",
        "hub",
        "ops",
        "ai",
        "billing",
        "chat",
        "access",
        "overview",
        "general",
    }:
        return s
    if "contracts" in p:
        return "contracts"
    if "docs" in p:
        return "docs"
    if "enterprise-hub" in p or p.endswith("/hub"):
        return "hub"
    if "ops-command" in p:
        return "ops"
    if "ai-command" in p:
        return "ai"
    if "chat" in p:
        return "chat"
    if t in {"workers", "access", "operations", "inbox", "billing", "overview", "copilot"}:
        return "access" if t == "access" else t
    return "general"


def _surface_boosts(surface: str) -> dict[str, int]:
    """Extra priority points by current admin surface (Site Copilot context)."""
    table = {
        "contracts": {"docs": 25, "leave": 15, "contracts_nav": 40, "briefing": 5},
        "docs": {"docs": 35, "export": 20, "docs_nav": 40, "briefing": 5},
        "workers": {"onsite": 25, "late": 30, "docs": 15, "plan": 35, "risk": 10},
        "access": {"onsite": 30, "late": 35, "security": 10},
        "operations": {"briefing": 25, "security": 20, "broadcast": 20, "forecast": 15},
        "inbox": {"leave": 35, "inbox_nav": 40, "security": 10},
        "hub": {"security": 25, "briefing": 15, "risk": 15, "emergency": 10},
        "ops": {"security": 30, "emergency": 20, "briefing": 15, "onsite": 10},
        "ai": {"briefing": 20, "export": 15, "prioritize": 25},
        "billing": {"briefing": 15, "export": 10},
        "chat": {"broadcast": 25, "inbox_nav": 15},
        "overview": {"briefing": 20, "security": 15, "onsite": 10},
        "general": {},
    }
    return table.get(surface) or {}


def format_morning_dispatch(
    pulse: dict[str, Any],
    *,
    briefing_answer: str | None = None,
    company_name: str = "",
) -> str:
    """Build Slack/email body: snapshot + top priorities (+ optional LLM briefing)."""
    from .langs import normalize_ui_lang
    from .sector_copy import sector_vocab

    lang = normalize_ui_lang(pulse.get("lang"))
    snap = pulse.get("snapshot") or {}
    recs = pulse.get("recommendations") or []
    name = (company_name or pulse.get("companyId") or "").strip()
    _workers, site, _gate = sector_vocab(pulse.get("sectorTerms") or {}, lang)

    copy = {
        "de": {
            "head": f"Morgen-Betriebs-Pulse — {name}".strip(" —"),
            "onsite": f"Am {site}",
            "security": "Offene Security",
            "leave": "Offene Urlaubsanträge",
            "docs": "Abgelaufene Dokumente",
            "risk": "Risiko-Level",
            "prio": "Prioritäten heute:",
            "empty": "Keine kritischen Prioritäten — Tageslage im System prüfen.",
            "emergency": "Aktiver Notfall",
            "details": "Details:",
        },
        "en": {
            "head": f"Morning operations pulse — {name}".strip(" —"),
            "onsite": f"At {site}",
            "security": "Open security",
            "leave": "Pending leave",
            "docs": "Expired documents",
            "risk": "Risk level",
            "prio": "Priorities today:",
            "empty": "No critical priorities — review the in-app briefing.",
            "emergency": "Active emergency",
            "details": "Details:",
        },
        "ar": {
            "head": f"ملخص تشغيل صباحي — {name}".strip(" —"),
            "onsite": f"في {site}",
            "security": "أمن مفتوح",
            "leave": "إجازات معلّقة",
            "docs": "وثائق منتهية",
            "risk": "مستوى المخاطر",
            "prio": "أولويات اليوم:",
            "empty": "لا أولويات حرجة — راجع الملخص في النظام.",
            "emergency": "طوارئ نشطة",
            "details": "تفاصيل إضافية:",
        },
        "tr": {
            "head": f"Sabah operasyon özeti — {name}".strip(" —"),
            "onsite": site,
            "security": "Açık güvenlik",
            "leave": "Bekleyen izin",
            "docs": "Süresi dolmuş belgeler",
            "risk": "Risk seviyesi",
            "prio": "Bugünün öncelikleri:",
            "empty": "Kritik öncelik yok — uygulamadaki özeti kontrol edin.",
            "emergency": "Aktif acil durum",
            "details": "Ayrıntılar:",
        },
        "fr": {
            "head": f"Pulse opérations du matin — {name}".strip(" —"),
            "onsite": "Sur site",
            "security": "Sécurité ouverte",
            "leave": "Congés en attente",
            "docs": "Documents expirés",
            "risk": "Niveau de risque",
            "prio": "Priorités du jour :",
            "empty": "Aucune priorité critique — consultez le briefing dans l’app.",
            "emergency": "Urgence active",
            "details": "Détails :",
        },
        "es": {
            "head": f"Pulso operativo matutino — {name}".strip(" —"),
            "onsite": "En obra",
            "security": "Seguridad abierta",
            "leave": "Vacaciones pendientes",
            "docs": "Documentos caducados",
            "risk": "Nivel de riesgo",
            "prio": "Prioridades de hoy:",
            "empty": "Sin prioridades críticas — revise el briefing en la app.",
            "emergency": "Emergencia activa",
            "details": "Detalles:",
        },
        "it": {
            "head": f"Pulse operativo mattutino — {name}".strip(" —"),
            "onsite": "In cantiere",
            "security": "Sicurezza aperta",
            "leave": "Ferie in sospeso",
            "docs": "Documenti scaduti",
            "risk": "Livello di rischio",
            "prio": "Priorità di oggi:",
            "empty": "Nessuna priorità critica — controlla il briefing nell’app.",
            "emergency": "Emergenza attiva",
            "details": "Dettagli:",
        },
        "pl": {
            "head": f"Poranny pulse operacyjny — {name}".strip(" —"),
            "onsite": "Na miejscu",
            "security": "Otwarte bezpieczeństwo",
            "leave": "Oczekujące urlopy",
            "docs": "Wygasłe dokumenty",
            "risk": "Poziom ryzyka",
            "prio": "Priorytety na dziś:",
            "empty": "Brak krytycznych priorytetów — sprawdź briefing w aplikacji.",
            "emergency": "Aktywny stan awaryjny",
            "details": "Szczegóły:",
        },
    }
    t = copy.get(lang) or copy["en"]
    lines = [
        f"**{t['head']}**",
        f"- {t['onsite']}: {snap.get('workersOnSite', 0)}",
        f"- {t['security']}: {snap.get('openSecurityFindings', 0)}",
        f"- {t['leave']}: {snap.get('pendingLeave', 0)}",
        f"- {t['docs']}: {snap.get('expiredDocuments', 0)}",
        f"- {t['risk']}: {snap.get('riskLevel', 'low')}",
        "",
        f"**{t['prio']}**",
    ]
    if snap.get("emergencyActive"):
        lines.insert(1, f"- ⚠️ {t['emergency']}")

    bullets = []
    for i, rec in enumerate(recs[:5], 1):
        label = str(rec.get("label") or rec.get("prompt") or "").strip()
        reason = str(rec.get("reason") or "").strip()
        if not label:
            continue
        bullets.append(f"{i}. *{label}* — {reason}" if reason else f"{i}. *{label}*")
    lines.extend(bullets or [t["empty"]])

    extra = (briefing_answer or "").strip()
    if extra:
        lines.extend(["", f"**{t['details']}**", extra[:2200]])

    lines.append("\n— WorkPass AI Operator")
    return "\n".join(lines).strip()


def build_operator_pulse(
    db,
    company_id: str,
    *,
    role: str = "company-admin",
    lang: str = "de",
    surface: str | None = None,
    tab: str | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    from .context_builder import build_compact_context, deterministic_briefing

    from .langs import normalize_ui_lang
    from .sector_copy import (
        load_company_sector_terms,
        rewrite_prompt_map,
        rewrite_pulse_pack,
        sector_meta_payload,
        sector_vocab,
    )

    lang = normalize_ui_lang(lang)
    surface_key = normalize_surface(surface, tab=tab, path=path)
    boosts = _surface_boosts(surface_key)
    terms = load_company_sector_terms(db, company_id, lang=lang)
    workers, site, _gate = sector_vocab(terms, lang)

    ctx = build_compact_context(db, company_id, role)
    sec = ctx.get("security") or {}
    intel = ctx.get("intelligence") or {}
    risk = intel.get("risk") or {}
    at_risk = (intel.get("attendance") or {}).get("at_risk") or []
    em = ctx.get("emergency") or {}

    on_site = int(ctx.get("workersOnSite") or 0)
    open_sec = int(sec.get("openFindings") or sec.get("openAlerts") or 0)
    pending_leave = int(ctx.get("pendingLeave") or 0)
    expired_docs = int(risk.get("expired_documents") or 0)
    risk_level = str(risk.get("level") or "low").lower()
    emergency = bool(em.get("active"))

    recommendations: list[dict[str, Any]] = []

    def prio(base: int, key: str) -> int:
        return base + int(boosts.get(key) or 0)

    def add(
        *,
        id: str,
        priority: int,
        prompt: str,
        label: str,
        reason: str,
        action: str | None = None,
        params: dict | None = None,
        navigate: dict | None = None,
        boost_key: str | None = None,
    ) -> None:
        item: dict[str, Any] = {
            "id": id,
            "priority": prio(priority, boost_key or id),
            "prompt": prompt,
            "label": label,
            "reason": reason,
            "surface": surface_key,
        }
        if action:
            item["action"] = action
            item["params"] = params or {}
            item["type"] = "execute"
        elif navigate:
            item["type"] = "navigate"
            item.update(navigate)
        else:
            item["type"] = "prompt"
        recommendations.append(item)

    packs = {
        "de": {
            "emergency": ("Notfall prüfen", "Aktiver Notfall — sofort Status prüfen."),
            "security": ("Security prüfen", f"{open_sec} offene Security-Befunde."),
            "leave": ("Urlaub prüfen", f"{pending_leave} offene Urlaubsanträge."),
            "docs": ("Dokumente erinnern", f"{expired_docs} abgelaufene Dokumente."),
            "risk": ("Ausfallrisiko", f"{len(at_risk)} Mitarbeiter mit Ausfallrisiko."),
            "briefing": ("Tageslage", f"{on_site} Personen vor Ort — Tageslage anzeigen."),
            "export": ("Snapshot exportieren", "Betriebs-Snapshot als Markdown exportieren."),
            "onsite": ("Wer ist vor Ort?", "Aktuelle Anwesenheit prüfen."),
            "late": ("Verspätungen", "Zu spät / Erinnerung vorbereiten."),
            "plan": ("Einsatzplan", "Einsatzplan vorbereiten."),
            "broadcast": ("An alle schreiben", "Kurze Mitteilung an das Team."),
            "forecast": ("Morgen-Prognose", "Prognose für morgen anzeigen."),
            "prioritize": ("Prioritäten", "Was soll ich heute priorisieren?"),
            "contracts_nav": ("Verträge öffnen", "Kontext: Verträge — Seite öffnen."),
            "docs_nav": ("Docs öffnen", "Kontext: Dokumente — Seite öffnen."),
            "inbox_nav": ("Inbox öffnen", "Kontext: Inbox — offene Aufgaben."),
        },
        "en": {
            "emergency": ("Check emergency", "Active emergency — check status now."),
            "security": ("Check security", f"{open_sec} open security findings."),
            "leave": ("Review leave", f"{pending_leave} pending leave requests."),
            "docs": ("Remind documents", f"{expired_docs} expired documents."),
            "risk": ("Attendance risk", f"{len(at_risk)} workers at risk."),
            "briefing": ("Daily briefing", f"{on_site} on site — show briefing."),
            "export": ("Export snapshot", "Export operations snapshot as markdown."),
            "onsite": ("Who is on site?", "Check current attendance."),
            "late": ("Late workers", "Prepare late reminder."),
            "plan": ("Deployment plan", "Prepare deployment plan."),
            "broadcast": ("Message everyone", "Short message to the team."),
            "forecast": ("Tomorrow forecast", "Show tomorrow forecast."),
            "prioritize": ("Priorities", "What should I prioritize today?"),
            "contracts_nav": ("Open contracts", "Context: contracts — open page."),
            "docs_nav": ("Open docs", "Context: documents — open page."),
            "inbox_nav": ("Open inbox", "Context: inbox — open tasks."),
        },
        "ar": {
            "emergency": ("فحص الطوارئ", "طارئ نشط — افحص الحالة الآن."),
            "security": ("فحص الأمن", f"{open_sec} تنبيهات أمنية مفتوحة."),
            "leave": ("مراجعة الإجازات", f"{pending_leave} طلبات إجازة معلّقة."),
            "docs": ("تذكير الوثائق", f"{expired_docs} وثائق منتهية."),
            "risk": ("مخاطر الغياب", f"{len(at_risk)} موظفون بخطر غياب."),
            "briefing": ("ملخص اليوم", f"{on_site} في الموقع — اعرض الملخص."),
            "export": ("تصدير لقطة", "صدّر لقطة التشغيل كـ Markdown."),
            "onsite": ("من في الموقع؟", "تحقق من الحضور الحالي."),
            "late": ("المتأخرون", "جهّز تذكير التأخير."),
            "plan": ("خطة الانتشار", "جهّز خطة الانتشار."),
            "broadcast": ("رسالة للجميع", "رسالة قصيرة للفريق."),
            "forecast": ("توقع الغد", "اعرض توقع الغد."),
            "prioritize": ("الأولويات", "ماذا أفعل اليوم أولاً؟"),
            "contracts_nav": ("فتح العقود", "السياق: العقود — افتح الصفحة."),
            "docs_nav": ("فتح الوثائق", "السياق: الوثائق — افتح الصفحة."),
            "inbox_nav": ("فتح الوارد", "السياق: الوارد — المهام المفتوحة."),
        },
        "tr": {
            "emergency": ("Acil durumu kontrol et", "Aktif acil durum — hemen durumu kontrol edin."),
            "security": ("Güvenliği kontrol et", f"{open_sec} açık güvenlik bulgusu."),
            "leave": ("İzinleri incele", f"{pending_leave} bekleyen izin talebi."),
            "docs": ("Belgeleri hatırlat", f"{expired_docs} süresi dolmuş belge."),
            "risk": ("Devamsızlık riski", f"{len(at_risk)} çalışan risk altında."),
            "briefing": ("Günlük özet", f"{on_site} kişi sahada — özeti göster."),
            "export": ("Anlık görüntü dışa aktar", "Operasyon anlık görüntüsünü Markdown olarak dışa aktar."),
            "onsite": ("Sahada kim var?", "Güncel devam durumunu kontrol et."),
            "late": ("Geç kalanlar", "Geç kalma hatırlatması hazırla."),
            "plan": ("Görev planı", "Görev planını hazırla."),
            "broadcast": ("Herkese yaz", "Ekibe kısa mesaj."),
            "forecast": ("Yarın tahmini", "Yarın için tahmini göster."),
            "prioritize": ("Öncelikler", "Bugün neyi önceliklendireyim?"),
            "contracts_nav": ("Sözleşmeleri aç", "Bağlam: sözleşmeler — sayfayı aç."),
            "docs_nav": ("Belgeleri aç", "Bağlam: belgeler — sayfayı aç."),
            "inbox_nav": ("Gelen kutusunu aç", "Bağlam: gelen kutusu — açık görevler."),
        },
        "fr": {
            "emergency": ("Vérifier l’urgence", "Urgence active — vérifier le statut maintenant."),
            "security": ("Vérifier la sécurité", f"{open_sec} constats de sécurité ouverts."),
            "leave": ("Examiner les congés", f"{pending_leave} demandes de congé en attente."),
            "docs": ("Rappeler les documents", f"{expired_docs} documents expirés."),
            "risk": ("Risque d’absence", f"{len(at_risk)} collaborateurs à risque."),
            "briefing": ("Briefing du jour", f"{on_site} sur site — afficher le briefing."),
            "export": ("Exporter l’instantané", "Exporter l’instantané opérationnel en Markdown."),
            "onsite": ("Qui est sur site ?", "Vérifier la présence actuelle."),
            "late": ("Retards", "Préparer un rappel de retard."),
            "plan": ("Plan de déploiement", "Préparer le plan de déploiement."),
            "broadcast": ("Écrire à tous", "Court message à l’équipe."),
            "forecast": ("Prévision demain", "Afficher la prévision pour demain."),
            "prioritize": ("Priorités", "Que dois-je prioriser aujourd’hui ?"),
            "contracts_nav": ("Ouvrir les contrats", "Contexte : contrats — ouvrir la page."),
            "docs_nav": ("Ouvrir les docs", "Contexte : documents — ouvrir la page."),
            "inbox_nav": ("Ouvrir la boîte", "Contexte : boîte de réception — tâches ouvertes."),
        },
        "es": {
            "emergency": ("Revisar emergencia", "Emergencia activa — revise el estado ahora."),
            "security": ("Revisar seguridad", f"{open_sec} hallazgos de seguridad abiertos."),
            "leave": ("Revisar vacaciones", f"{pending_leave} solicitudes de vacaciones pendientes."),
            "docs": ("Recordar documentos", f"{expired_docs} documentos caducados."),
            "risk": ("Riesgo de ausencia", f"{len(at_risk)} trabajadores en riesgo."),
            "briefing": ("Resumen del día", f"{on_site} en obra — mostrar resumen."),
            "export": ("Exportar instantánea", "Exportar instantánea operativa como Markdown."),
            "onsite": ("¿Quién está en obra?", "Comprobar la presencia actual."),
            "late": ("Retrasos", "Preparar recordatorio de retraso."),
            "plan": ("Plan de despliegue", "Preparar el plan de despliegue."),
            "broadcast": ("Escribir a todos", "Mensaje breve al equipo."),
            "forecast": ("Pronóstico mañana", "Mostrar el pronóstico de mañana."),
            "prioritize": ("Prioridades", "¿Qué debo priorizar hoy?"),
            "contracts_nav": ("Abrir contratos", "Contexto: contratos — abrir página."),
            "docs_nav": ("Abrir docs", "Contexto: documentos — abrir página."),
            "inbox_nav": ("Abrir bandeja", "Contexto: bandeja — tareas abiertas."),
        },
        "it": {
            "emergency": ("Controlla emergenza", "Emergenza attiva — controlla subito lo stato."),
            "security": ("Controlla sicurezza", f"{open_sec} segnalazioni di sicurezza aperte."),
            "leave": ("Esamina ferie", f"{pending_leave} richieste di ferie in sospeso."),
            "docs": ("Ricorda documenti", f"{expired_docs} documenti scaduti."),
            "risk": ("Rischio assenza", f"{len(at_risk)} lavoratori a rischio."),
            "briefing": ("Briefing odierno", f"{on_site} in cantiere — mostra briefing."),
            "export": ("Esporta snapshot", "Esporta lo snapshot operativo in Markdown."),
            "onsite": ("Chi è in cantiere?", "Controlla la presenza attuale."),
            "late": ("Ritardi", "Prepara un promemoria ritardo."),
            "plan": ("Piano di dispiegamento", "Prepara il piano di dispiegamento."),
            "broadcast": ("Scrivi a tutti", "Breve messaggio al team."),
            "forecast": ("Previsione domani", "Mostra la previsione di domani."),
            "prioritize": ("Priorità", "Cosa dovrei prioritizzare oggi?"),
            "contracts_nav": ("Apri contratti", "Contesto: contratti — apri pagina."),
            "docs_nav": ("Apri docs", "Contesto: documenti — apri pagina."),
            "inbox_nav": ("Apri inbox", "Contesto: inbox — attività aperte."),
        },
        "pl": {
            "emergency": ("Sprawdź awarię", "Aktywny stan awaryjny — sprawdź status teraz."),
            "security": ("Sprawdź bezpieczeństwo", f"{open_sec} otwartych alertów bezpieczeństwa."),
            "leave": ("Sprawdź urlopy", f"{pending_leave} oczekujących wniosków urlopowych."),
            "docs": ("Przypomnij dokumenty", f"{expired_docs} wygasłych dokumentów."),
            "risk": ("Ryzyko nieobecności", f"{len(at_risk)} pracowników zagrożonych."),
            "briefing": ("Podsumowanie dnia", f"{on_site} na miejscu — pokaż podsumowanie."),
            "export": ("Eksportuj migawkę", "Eksportuj migawkę operacyjną jako Markdown."),
            "onsite": ("Kto jest na budowie?", "Sprawdź aktualną obecność."),
            "late": ("Spóźnienia", "Przygotuj przypomnienie o spóźnieniu."),
            "plan": ("Plan rozmieszczenia", "Przygotuj plan rozmieszczenia."),
            "broadcast": ("Napisz do wszystkich", "Krótka wiadomość do zespołu."),
            "forecast": ("Prognoza na jutro", "Pokaż prognozę na jutro."),
            "prioritize": ("Priorytety", "Co mam dziś priorytetyzować?"),
            "contracts_nav": ("Otwórz umowy", "Kontekst: umowy — otwórz stronę."),
            "docs_nav": ("Otwórz dokumenty", "Kontekst: dokumenty — otwórz stronę."),
            "inbox_nav": ("Otwórz skrzynkę", "Kontekst: skrzynka — otwarte zadania."),
        },
    }
    labels = rewrite_pulse_pack(packs.get(lang) or packs["en"], workers=workers, site=site, lang=lang)

    prompts = {
        "de": {
            "security": "Security-Alerts zeigen",
            "leave": "Offene Urlaubsanträge genehmigen",
            "docs": "Abgelaufene Dokumente erinnern",
            "risk": "Welche Mitarbeiter haben erhöhtes Ausfallrisiko?",
            "briefing": "Was ist heute wichtig? Tageslage",
            "onsite": "Wer ist heute vor Ort?",
            "late": "Wer kommt zu spät? Erinnerung vorbereiten",
            "plan": "Einsatzplan vorbereiten",
            "broadcast": "Mitteilung an alle: Bitte pünktlich erscheinen",
            "forecast": "Morgen-Prognose zeigen",
            "prioritize": "Was soll ich heute priorisieren?",
            "emergency": "Gibt es einen aktiven Notfall — was ist der Status?",
        },
        "en": {
            "security": "Show security alerts",
            "leave": "Approve pending leave requests",
            "docs": "Remind expired documents",
            "risk": "Which workers have elevated no-show risk?",
            "briefing": "What matters today? Daily briefing",
            "onsite": "Who is on site today?",
            "late": "Who is late? Prepare reminder",
            "plan": "Prepare deployment plan",
            "broadcast": "Message everyone: please arrive on time",
            "forecast": "Show tomorrow forecast",
            "prioritize": "What should I prioritize today?",
            "emergency": "Is there an active emergency — what is the status?",
        },
        "ar": {
            "security": "اعرض تنبيهات الأمن",
            "leave": "وافق على طلبات الإجازة المعلّقة",
            "docs": "ذكّر بالوثائق المنتهية",
            "onsite": "من في الموقع اليوم؟",
            "late": "من يتأخر؟ جهّز تذكيراً",
            "plan": "جهّز خطة الانتشار",
            "broadcast": "رسالة للجميع: يرجى الحضور في الوقت",
            "forecast": "أظهر توقع الغد",
            "prioritize": "ماذا أفعل اليوم أولاً؟",
            "briefing": "ما المهم اليوم؟ ملخص اليوم",
            "risk": "من لديه خطر غياب مرتفع؟",
            "emergency": "هل هناك طوارئ نشطة — ما الحالة؟",
        },
        "tr": {
            "security": "Güvenlik uyarılarını göster",
            "leave": "Bekleyen izin taleplerini onayla",
            "docs": "Süresi dolmuş belgeleri hatırlat",
            "risk": "Hangi çalışanların devamsızlık riski yüksek?",
            "briefing": "Bugün ne önemli? Günlük özet",
            "onsite": "Bugün sahada kim var?",
            "late": "Kim geç kalıyor? Hatırlatma hazırla",
            "plan": "Görev planını hazırla",
            "broadcast": "Herkese mesaj: lütfen zamanında gelin",
            "forecast": "Yarın tahmini göster",
            "prioritize": "Bugün neyi önceliklendireyim?",
            "emergency": "Aktif acil durum var mı — durum nedir?",
        },
        "fr": {
            "security": "Afficher les alertes de sécurité",
            "leave": "Approuver les congés en attente",
            "docs": "Rappeler les documents expirés",
            "risk": "Quels collaborateurs ont un risque d’absence élevé ?",
            "briefing": "Qu’est-ce qui compte aujourd’hui ? Briefing",
            "onsite": "Qui est sur site aujourd’hui ?",
            "late": "Qui est en retard ? Préparer un rappel",
            "plan": "Préparer le plan de déploiement",
            "broadcast": "Message à tous : veuillez arriver à l’heure",
            "forecast": "Afficher la prévision de demain",
            "prioritize": "Que dois-je prioriser aujourd’hui ?",
            "emergency": "Y a-t-il une urgence active — quel est le statut ?",
        },
        "es": {
            "security": "Mostrar alertas de seguridad",
            "leave": "Aprobar vacaciones pendientes",
            "docs": "Recordar documentos caducados",
            "risk": "¿Qué trabajadores tienen alto riesgo de ausencia?",
            "briefing": "¿Qué importa hoy? Resumen diario",
            "onsite": "¿Quién está en obra hoy?",
            "late": "¿Quién llega tarde? Preparar recordatorio",
            "plan": "Preparar plan de despliegue",
            "broadcast": "Mensaje a todos: por favor lleguen a tiempo",
            "forecast": "Mostrar pronóstico de mañana",
            "prioritize": "¿Qué debo priorizar hoy?",
            "emergency": "¿Hay una emergencia activa — cuál es el estado?",
        },
        "it": {
            "security": "Mostra avvisi di sicurezza",
            "leave": "Approva ferie in sospeso",
            "docs": "Ricorda documenti scaduti",
            "risk": "Quali lavoratori hanno rischio assenza elevato?",
            "briefing": "Cosa conta oggi? Briefing giornaliero",
            "onsite": "Chi è in cantiere oggi?",
            "late": "Chi è in ritardo? Prepara promemoria",
            "plan": "Prepara piano di dispiegamento",
            "broadcast": "Messaggio a tutti: arrivate in orario",
            "forecast": "Mostra previsione di domani",
            "prioritize": "Cosa dovrei prioritizzare oggi?",
            "emergency": "C’è un’emergenza attiva — qual è lo stato?",
        },
        "pl": {
            "security": "Pokaż alerty bezpieczeństwa",
            "leave": "Zatwierdź oczekujące urlopy",
            "docs": "Przypomnij o wygasłych dokumentach",
            "risk": "Którzy pracownicy mają podwyższone ryzyko nieobecności?",
            "briefing": "Co dziś ważne? Podsumowanie dnia",
            "onsite": "Kto jest dziś na budowie?",
            "late": "Kto się spóźnia? Przygotuj przypomnienie",
            "plan": "Przygotuj plan rozmieszczenia",
            "broadcast": "Wiadomość do wszystkich: proszę przyjść na czas",
            "forecast": "Pokaż prognozę na jutro",
            "prioritize": "Co mam dziś priorytetyzować?",
            "emergency": "Czy jest aktywny stan awaryjny — jaki jest status?",
        },
    }
    pr = rewrite_prompt_map(prompts.get(lang) or prompts["en"], workers=workers, site=site, lang=lang)

    if emergency:
        add(
            id="emergency",
            priority=100,
            prompt=pr["emergency"],
            label=labels["emergency"][0],
            reason=labels["emergency"][1],
            navigate={"url": "/ops-command-center.html"},
            boost_key="emergency",
        )
    if open_sec > 0:
        add(
            id="security",
            priority=90,
            prompt=pr["security"],
            label=labels["security"][0],
            reason=labels["security"][1],
            action="resolve_open_security_alerts",
            params={},
            boost_key="security",
        )
    if pending_leave > 0:
        add(
            id="leave",
            priority=80,
            prompt=pr["leave"],
            label=labels["leave"][0],
            reason=labels["leave"][1],
            boost_key="leave",
        )
    if expired_docs > 0:
        add(
            id="docs",
            priority=75,
            prompt=pr["docs"],
            label=labels["docs"][0],
            reason=labels["docs"][1],
            action="remind_expired_documents",
            params={},
            boost_key="docs",
        )
    if at_risk:
        add(
            id="risk",
            priority=70,
            prompt=pr["risk"],
            label=labels["risk"][0],
            reason=labels["risk"][1],
            boost_key="risk",
        )

    # Always-available core + surface-aware extras
    add(
        id="briefing",
        priority=40,
        prompt=pr["briefing"],
        label=labels["briefing"][0],
        reason=labels["briefing"][1],
        boost_key="briefing",
    )
    add(
        id="onsite",
        priority=20,
        prompt=pr["onsite"],
        label=labels["onsite"][0],
        reason=labels["onsite"][1],
        boost_key="onsite",
    )
    add(
        id="export",
        priority=15,
        prompt="export_ops_snapshot",
        label=labels["export"][0],
        reason=labels["export"][1],
        action="export_ops_snapshot",
        params={"lang": lang},
        boost_key="export",
    )

    if surface_key in {"workers", "access", "operations", "general"}:
        add(
            id="late",
            priority=18,
            prompt=pr["late"],
            label=labels["late"][0],
            reason=labels["late"][1],
            boost_key="late",
        )
        add(
            id="plan",
            priority=16,
            prompt=pr["plan"],
            label=labels["plan"][0],
            reason=labels["plan"][1],
            boost_key="plan",
        )
    if surface_key in {"operations", "chat", "hub"}:
        add(
            id="broadcast",
            priority=14,
            prompt=pr["broadcast"],
            label=labels["broadcast"][0],
            reason=labels["broadcast"][1],
            boost_key="broadcast",
        )
    if surface_key in {"operations", "ai", "hub"}:
        add(
            id="forecast",
            priority=12,
            prompt=pr["forecast"],
            label=labels["forecast"][0],
            reason=labels["forecast"][1],
            boost_key="forecast",
        )
    if surface_key in {"ai", "overview", "general"}:
        add(
            id="prioritize",
            priority=22,
            prompt=pr["prioritize"],
            label=labels["prioritize"][0],
            reason=labels["prioritize"][1],
            boost_key="prioritize",
        )
    if surface_key == "contracts":
        add(
            id="contracts_nav",
            priority=45,
            prompt="Öffne Verträge" if lang == "de" else ("Open contracts" if lang == "en" else "افتح العقود"),
            label=labels["contracts_nav"][0],
            reason=labels["contracts_nav"][1],
            navigate={"url": "/admin-v2/contracts.html"},
            boost_key="contracts_nav",
        )
    if surface_key == "docs":
        add(
            id="docs_nav",
            priority=45,
            prompt="Öffne Docs" if lang == "de" else ("Open docs" if lang == "en" else "افتح الوثائق"),
            label=labels["docs_nav"][0],
            reason=labels["docs_nav"][1],
            navigate={"url": "/admin-v2/docs.html"},
            boost_key="docs_nav",
        )
    if surface_key == "inbox":
        add(
            id="inbox_nav",
            priority=45,
            prompt="Öffne Inbox" if lang == "de" else ("Open inbox" if lang == "en" else "افتح الوارد"),
            label=labels["inbox_nav"][0],
            reason=labels["inbox_nav"][1],
            navigate={"tab": "inbox", "url": "/admin-v2/index.html?tab=inbox"},
            boost_key="inbox_nav",
        )

    recommendations.sort(key=lambda r: (-int(r.get("priority") or 0), str(r.get("id") or "")))
    # Dedupe by id keeping highest priority first
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for rec in recommendations:
        rid = str(rec.get("id") or "")
        if not rid or rid in seen:
            continue
        seen.add(rid)
        deduped.append(rec)

    urgency = 0
    if emergency:
        urgency += 3
    if open_sec > 0:
        urgency += min(3, open_sec)
    if pending_leave > 0:
        urgency += 1
    if expired_docs > 0:
        urgency += 1
    if risk_level in {"high", "critical"}:
        urgency += 1

    snapshot_md = deterministic_briefing(ctx, lang=lang)
    sector = sector_meta_payload(terms, lang)
    return {
        "companyId": company_id,
        "lang": lang,
        "surface": surface_key,
        "urgency": min(urgency, 9),
        "urgent": urgency > 0,
        "sectorTerms": sector,
        "snapshot": {
            "workersOnSite": on_site,
            "openSecurityFindings": open_sec,
            "pendingLeave": pending_leave,
            "expiredDocuments": expired_docs,
            "riskLevel": risk_level,
            "emergencyActive": emergency,
            "attendanceAtRisk": len(at_risk),
        },
        "recommendations": deduped[:8],
        "snapshotMarkdown": snapshot_md,
    }
