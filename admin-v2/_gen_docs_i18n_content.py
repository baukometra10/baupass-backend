# -*- coding: utf-8 -*-
"""Generate high-quality docs template bodies (8 langs) + topic catalog."""
from __future__ import annotations

import json
from pathlib import Path


def compact(html: str) -> str:
    return "".join(line.strip() for line in html.strip().splitlines())


def pack_de() -> dict[str, str]:
    return {
        "letter": compact(
            """
            <p class="wp-letter">{{company.name}}<br>{{company.address}}<br>{{company.email}} · {{company.contact}}</p>
            <p class="wp-recipient">{{worker.name}}<br>{{site.name}}</p>
            <p class="wp-date">{{date.today}}</p>
            <p class="wp-subject"><strong>Betreff:</strong> [kurzer, klarer Betreff]</p>
            <p>Sehr geehrte Damen und Herren,</p>
            <p>hiermit beziehen wir uns auf unser Gespräch / Ihre Anfrage und teilen Ihnen Folgendes mit:</p>
            <p>[Sachverhalt in 2–4 Sätzen: Was ist der Anlass? Was wurde vereinbart? Was ist als Nächstes erforderlich?]</p>
            <p>Bitte teilen Sie uns bis zum ________ mit, ob Sie dem Vorgehen zustimmen bzw. welche Unterlagen noch fehlen.</p>
            <p>Für Rückfragen stehen wir Ihnen unter {{company.email}} gerne zur Verfügung.</p>
            <p class="wp-sign">Mit freundlichen Grüßen<br>{{manager.name}}<br>{{company.name}}</p>
            """
        ),
        "warning": compact(
            """
            <h1 class="wp-doc-title">Schriftlicher Hinweis</h1>
            <p class="wp-subtitle">{{company.name}} · {{date.today}} · vertraulich</p>
            <p class="wp-meta"><strong>Mitarbeiter/in:</strong> {{worker.name}} ({{worker.badge}})<br>
            <strong>Standort / Bereich:</strong> {{site.name}}<br>
            <strong>Verantwortlich:</strong> {{manager.name}}</p>
            <h2>1. Sachverhalt</h2>
            <p>Am [Datum / Uhrzeit] wurde festgestellt, dass [konkreter Vorfall, Ort, Zeugen falls vorhanden].</p>
            <h2>2. Bewertung</h2>
            <p>Dieses Verhalten entspricht nicht den betrieblichen Vorgaben / der Betriebsanweisung vom [Datum].</p>
            <h2>3. Erwartung</h2>
            <p>Wir erwarten, dass Sie ab sofort [konkrete Regel / Verhalten] einhalten und Rückfragen unverzüglich an {{manager.name}} richten.</p>
            <h2>4. Hinweis auf Folgen</h2>
            <p>Weitere Verstöße können arbeitsrechtliche Maßnahmen nach sich ziehen. Dieses Schreiben dient der Dokumentation.</p>
            <p class="wp-sign">{{site.name}}, {{date.today}}<br>{{manager.name}}<br>{{company.name}}<br>{{company.email}}</p>
            """
        ),
        "policy": compact(
            """
            <h1 class="wp-doc-title">Betriebsanweisung</h1>
            <p class="wp-subtitle">{{company.name}} · Stand {{date.today}} · Standort {{site.name}}</p>
            <h2>1. Geltungsbereich</h2>
            <p>Diese Anweisung gilt für alle Beschäftigten, Nachunternehmer und Besucher am Standort {{site.name}}.</p>
            <h2>2. Allgemeine Regeln</h2>
            <ol>
              <li>Persönliche Schutzausrüstung (PSA) ist vollständig zu tragen.</li>
              <li>Wege, Fluchtwege und Notausgänge sind freizuhalten.</li>
              <li>Maschinen und Geräte nur nach Einweisung und Freigabe bedienen.</li>
              <li>Unfälle, Beinahe-Unfälle und Schäden unverzüglich melden.</li>
            </ol>
            <h2>3. Verhalten im Notfall</h2>
            <p>Ruhe bewahren, Gefahrenstelle sichern, Ersthelfer / Notruf verständigen, Sammelpunkt aufsuchen.</p>
            <h2>4. Verstöße</h2>
            <p>Verstöße können arbeitsrechtliche Folgen haben und den Zutritt zum Standort einschränken.</p>
            <p class="wp-sign">Verantwortlich: {{manager.name}} · {{company.contact}} · {{company.email}}</p>
            """
        ),
        "certificate": compact(
            """
            <h1 class="wp-doc-title">Bescheinigung</h1>
            <p class="wp-subtitle">{{company.name}}</p>
            <p>Hiermit wird bestätigt, dass</p>
            <p class="wp-center"><strong>{{worker.name}}</strong><br>Ausweis / Badge: {{worker.badge}}</p>
            <p>im Zeitraum vom ________ bis ________ für {{company.name}} tätig / anwesend war.</p>
            <p class="wp-meta"><strong>Standort:</strong> {{site.name}}<br>
            <strong>Zweck:</strong> [Nachweis / Behörde / Kunde / Versicherung]</p>
            <p>Diese Bescheinigung wird auf Wunsch ausgestellt und ersetzt keine arbeitsvertragliche Regelung.</p>
            <p>Ort, Datum: {{site.name}}, {{date.today}}</p>
            <p class="wp-sign">_______________________________<br>{{manager.name}}<br>{{company.name}}<br>{{company.email}}</p>
            """
        ),
        "meeting": compact(
            """
            <h1 class="wp-doc-title">Protokoll</h1>
            <p class="wp-meta"><strong>Datum:</strong> {{date.today}} · <strong>Ort:</strong> {{site.name}} · <strong>Firma:</strong> {{company.name}}<br>
            <strong>Leitung:</strong> {{manager.name}} · <strong>Protokoll:</strong> [Name]<br>
            <strong>Teilnehmer:</strong> {{worker.name}}, [weitere]</p>
            <h2>1. Tagesordnung</h2>
            <ol><li>Begrüßung und Ziel</li><li>Sachstand</li><li>Beschlüsse</li><li>Verschiedenes</li></ol>
            <h2>2. Diskussion / Sachstand</h2>
            <p>[Wesentliche Punkte in Stichworten]</p>
            <h2>3. Beschlüsse</h2>
            <ul><li>Beschluss 1 — verantwortlich: … — Termin: …</li><li>Beschluss 2 — verantwortlich: … — Termin: …</li></ul>
            <h2>4. Nächste Schritte</h2>
            <ul><li>…</li></ul>
            <p>Ende: ____ Uhr · Nächstes Treffen: ________</p>
            """
        ),
        "invitation": compact(
            """
            <h1 class="wp-doc-title">Einladung</h1>
            <p class="wp-subtitle">{{company.name}}</p>
            <p>Sehr geehrte/r {{worker.name}},</p>
            <p>wir laden Sie herzlich ein zu:</p>
            <p class="wp-meta"><strong>Thema:</strong> [Unterweisung / Meeting / Veranstaltung]<br>
            <strong>Datum:</strong> {{date.today}} · <strong>Uhrzeit:</strong> ____ Uhr<br>
            <strong>Ort:</strong> {{site.name}}<br>
            <strong>Dauer:</strong> ca. ____ Minuten</p>
            <p>Bitte bestätigen Sie Ihre Teilnahme kurz an {{company.email}} oder bei {{manager.name}}.</p>
            <p>Falls Sie verhindert sind, teilen Sie uns bitte eine Vertretung mit.</p>
            <p class="wp-sign">Mit freundlichen Grüßen<br>{{manager.name}}<br>{{company.name}}</p>
            """
        ),
        "access": compact(
            """
            <h1 class="wp-doc-title">Zutritts-/Einsatzbestätigung</h1>
            <p class="wp-subtitle">{{company.name}} · {{date.today}}</p>
            <p class="wp-meta"><strong>Person:</strong> {{worker.name}} ({{worker.badge}})<br>
            <strong>Standort / Bereich:</strong> {{site.name}}<br>
            <strong>Gültig ab:</strong> {{date.today}} · <strong>bis:</strong> ________</p>
            <p>Die genannte Person ist berechtigt, den genannten Bereich zu betreten und dort tätig zu werden, sofern PSA, Unterweisung und betriebliche Vorgaben eingehalten werden.</p>
            <p>Der Ausweis / Badge ist sichtbar zu tragen. Bei Verlust ist {{manager.name}} unverzüglich zu informieren.</p>
            <p class="wp-sign">{{manager.name}}<br>{{company.name}}<br>{{company.contact}} · {{company.email}}</p>
            """
        ),
        "reminder": compact(
            """
            <h1 class="wp-doc-title">Erinnerung / Frist</h1>
            <p class="wp-subtitle">{{company.name}} · {{date.today}}</p>
            <p>Sehr geehrte/r {{worker.name}},</p>
            <p>wir erinnern freundlich an folgende offene Angelegenheit:</p>
            <p class="wp-meta"><strong>Betreff:</strong> [Dokument / Unterweisung / Rückgabe / Frist]<br>
            <strong>fällig bis:</strong> ________ · <strong>Standort:</strong> {{site.name}}</p>
            <p>Bitte erledigen Sie den Vorgang rechtzeitig oder melden Sie sich bei {{manager.name}} ({{company.email}}), falls Hindernisse bestehen.</p>
            <p class="wp-sign">Mit freundlichen Grüßen<br>{{company.name}}</p>
            """
        ),
        "praise": compact(
            """
            <h1 class="wp-doc-title">Anerkennung</h1>
            <p class="wp-subtitle">{{company.name}} · {{date.today}}</p>
            <p>Sehr geehrte/r {{worker.name}},</p>
            <p>wir möchten uns ausdrücklich für Ihren Einsatz bedanken:</p>
            <p class="wp-meta"><strong>Anlass:</strong> [Projekt / Schicht / Unterstützung]<br>
            <strong>Standort:</strong> {{site.name}}</p>
            <p>Ihr Beitrag war für das Team und {{company.name}} besonders wertvoll. Vielen Dank für die zuverlässige und professionelle Arbeit.</p>
            <p class="wp-sign">Mit freundlichen Grüßen<br>{{manager.name}}<br>{{company.name}}</p>
            """
        ),
        "absence": compact(
            """
            <h1 class="wp-doc-title">Abwesenheitsbestätigung</h1>
            <p class="wp-subtitle">{{company.name}}</p>
            <p class="wp-meta"><strong>Mitarbeiter/in:</strong> {{worker.name}} ({{worker.badge}})<br>
            <strong>Standort:</strong> {{site.name}}<br>
            <strong>Zeitraum:</strong> vom ________ bis ________</p>
            <p>Hiermit wird bestätigt, dass die genannte Person im genannten Zeitraum abwesend war / freigestellt war.</p>
            <p><strong>Grund (optional):</strong> [Urlaub / Krankheit / Dienstreise / Sonstiges]</p>
            <p>Ort, Datum: {{site.name}}, {{date.today}}</p>
            <p class="wp-sign">_______________________________<br>{{manager.name}}<br>{{company.name}}</p>
            """
        ),
        "handover": compact(
            """
            <h1 class="wp-doc-title">Übergabeprotokoll</h1>
            <p class="wp-subtitle">{{company.name}} · {{date.today}} · {{site.name}}</p>
            <p class="wp-meta"><strong>Übergeben von:</strong> {{worker.name}} ({{worker.badge}})<br>
            <strong>Übernommen von:</strong> ________ · <strong>Leitung:</strong> {{manager.name}}</p>
            <h2>1. Übergabegegenstände</h2>
            <ul><li>Schlüssel / Badge / Geräte: ________</li><li>Unterlagen / Pläne: ________</li><li>Offene Punkte: ________</li></ul>
            <h2>2. Zustand / Hinweise</h2>
            <p>[Kurzbeschreibung Zustand, Mängel, Besonderheiten]</p>
            <h2>3. Bestätigung</h2>
            <p>Beide Seiten bestätigen die Vollständigkeit der Übergabe zum genannten Datum.</p>
            <p class="wp-sign">Übergeber: ____________ &nbsp;&nbsp; Übernehmer: ____________<br>{{manager.name}} · {{company.name}}</p>
            """
        ),
        "induction": compact(
            """
            <h1 class="wp-doc-title">Einweisung / Unterweisung</h1>
            <p class="wp-subtitle">{{company.name}} · {{date.today}} · {{site.name}}</p>
            <p class="wp-meta"><strong>Teilnehmer/in:</strong> {{worker.name}} ({{worker.badge}})<br>
            <strong>Durchgeführt von:</strong> {{manager.name}}</p>
            <h2>Inhalte</h2>
            <ol>
              <li>Sicherheitsregeln und PSA</li>
              <li>Notfallwege und Sammelpunkt</li>
              <li>Arbeitsbereich und Zuständigkeiten</li>
              <li>Meldewege und Ansprechpartner</li>
            </ol>
            <p>Die Unterweisung wurde verstanden. Rückfragen wurden geklärt.</p>
            <p class="wp-sign">Teilnehmer: ____________ &nbsp;&nbsp; Unterweiser: ____________<br>{{company.name}} · {{company.email}}</p>
            """
        ),
        "complaint_ack": compact(
            """
            <h1 class="wp-doc-title">Eingangsbestätigung</h1>
            <p class="wp-subtitle">{{company.name}} · {{date.today}}</p>
            <p>Sehr geehrte/r {{worker.name}},</p>
            <p>wir bestätigen den Eingang Ihrer Mitteilung / Beschwerde vom ________.</p>
            <p class="wp-meta"><strong>Betreff:</strong> [Kurzbeschreibung]<br>
            <strong>Aktenzeichen (intern):</strong> ________ · <strong>Standort:</strong> {{site.name}}</p>
            <p>Wir prüfen den Vorgang und melden uns bis spätestens ________ bei Ihnen. Ansprechpartner: {{manager.name}} ({{company.email}}).</p>
            <p class="wp-sign">Mit freundlichen Grüßen<br>{{manager.name}}<br>{{company.name}}</p>
            """
        ),
        "vacation": compact(
            """
            <h1 class="wp-doc-title">Urlaubsbestätigung</h1>
            <p class="wp-subtitle">{{company.name}}</p>
            <p class="wp-meta"><strong>Mitarbeiter/in:</strong> {{worker.name}} ({{worker.badge}})<br>
            <strong>Standort:</strong> {{site.name}}<br>
            <strong>Urlaub vom:</strong> ________ <strong>bis:</strong> ________</p>
            <p>Der beantragte Urlaub wurde genehmigt. Bitte stellen Sie vor Beginn die Übergabe offener Aufgaben sicher.</p>
            <p>Bei Änderungen informieren Sie bitte {{manager.name}} unter {{company.email}}.</p>
            <p>Ort, Datum: {{site.name}}, {{date.today}}</p>
            <p class="wp-sign">_______________________________<br>{{manager.name}}<br>{{company.name}}</p>
            """
        ),
        "blank": "<p><br></p>",
        "snGreeting": "<p>Sehr geehrte/r {{worker.name}},</p>",
        "snClosing": "<p>Mit freundlichen Grüßen<br>{{manager.name}}<br>{{company.name}}</p>",
        "snAddress": '<p class="wp-letter">{{company.name}}<br>{{company.address}}<br>{{company.email}}<br>{{company.contact}}</p>',
        "snWorker": "<p><strong>Mitarbeiter/in:</strong> {{worker.name}} ({{worker.badge}})<br><strong>Standort:</strong> {{site.name}}</p>",
        "snDate": "<p>{{date.today}}</p>",
        "snSign": "<p>_______________________________<br>{{manager.name}}<br>{{company.name}}</p>",
    }


def pack_en() -> dict[str, str]:
    return {
        "letter": compact(
            """
            <p class="wp-letter">{{company.name}}<br>{{company.address}}<br>{{company.email}} · {{company.contact}}</p>
            <p class="wp-recipient">{{worker.name}}<br>{{site.name}}</p>
            <p class="wp-date">{{date.today}}</p>
            <p class="wp-subject"><strong>Subject:</strong> [clear, short subject]</p>
            <p>Dear Sir or Madam,</p>
            <p>further to our conversation / your enquiry, we would like to inform you as follows:</p>
            <p>[Matter in 2–4 sentences: reason, agreement, next step]</p>
            <p>Please confirm by ________ whether you agree with this approach or which documents are still missing.</p>
            <p>If you have any questions, contact us at {{company.email}}.</p>
            <p class="wp-sign">Yours sincerely<br>{{manager.name}}<br>{{company.name}}</p>
            """
        ),
        "warning": compact(
            """
            <h1 class="wp-doc-title">Written notice</h1>
            <p class="wp-subtitle">{{company.name}} · {{date.today}} · confidential</p>
            <p class="wp-meta"><strong>Employee:</strong> {{worker.name}} ({{worker.badge}})<br>
            <strong>Site / area:</strong> {{site.name}}<br>
            <strong>Responsible:</strong> {{manager.name}}</p>
            <h2>1. Facts</h2>
            <p>On [date / time] it was found that [specific incident, place, witnesses if any].</p>
            <h2>2. Assessment</h2>
            <p>This conduct does not comply with company rules / the work instruction dated [date].</p>
            <h2>3. Expectation</h2>
            <p>We expect you to follow [specific rule / behaviour] with immediate effect and to raise questions with {{manager.name}} without delay.</p>
            <h2>4. Consequences</h2>
            <p>Further breaches may lead to employment-law measures. This letter is for documentation.</p>
            <p class="wp-sign">{{site.name}}, {{date.today}}<br>{{manager.name}}<br>{{company.name}}<br>{{company.email}}</p>
            """
        ),
        "policy": compact(
            """
            <h1 class="wp-doc-title">Work instruction</h1>
            <p class="wp-subtitle">{{company.name}} · as of {{date.today}} · site {{site.name}}</p>
            <h2>1. Scope</h2>
            <p>This instruction applies to all employees, subcontractors and visitors at site {{site.name}}.</p>
            <h2>2. General rules</h2>
            <ol>
              <li>Wear full personal protective equipment (PPE).</li>
              <li>Keep routes, escape routes and emergency exits clear.</li>
              <li>Operate machines only after briefing and approval.</li>
              <li>Report accidents, near misses and damage immediately.</li>
            </ol>
            <h2>3. Emergency behaviour</h2>
            <p>Stay calm, secure the hazard, alert first aid / emergency services, go to the assembly point.</p>
            <h2>4. Breaches</h2>
            <p>Breaches may have employment-law consequences and may restrict site access.</p>
            <p class="wp-sign">Responsible: {{manager.name}} · {{company.contact}} · {{company.email}}</p>
            """
        ),
        "certificate": compact(
            """
            <h1 class="wp-doc-title">Certificate</h1>
            <p class="wp-subtitle">{{company.name}}</p>
            <p>This is to confirm that</p>
            <p class="wp-center"><strong>{{worker.name}}</strong><br>ID / Badge: {{worker.badge}}</p>
            <p>was employed / present for {{company.name}} from ________ to ________.</p>
            <p class="wp-meta"><strong>Site:</strong> {{site.name}}<br>
            <strong>Purpose:</strong> [proof / authority / client / insurance]</p>
            <p>This certificate is issued on request and does not replace any employment-contract terms.</p>
            <p>Place, date: {{site.name}}, {{date.today}}</p>
            <p class="wp-sign">_______________________________<br>{{manager.name}}<br>{{company.name}}<br>{{company.email}}</p>
            """
        ),
        "meeting": compact(
            """
            <h1 class="wp-doc-title">Minutes</h1>
            <p class="wp-meta"><strong>Date:</strong> {{date.today}} · <strong>Place:</strong> {{site.name}} · <strong>Company:</strong> {{company.name}}<br>
            <strong>Chair:</strong> {{manager.name}} · <strong>Minutes:</strong> [name]<br>
            <strong>Attendees:</strong> {{worker.name}}, [others]</p>
            <h2>1. Agenda</h2>
            <ol><li>Welcome and objective</li><li>Status</li><li>Decisions</li><li>AOB</li></ol>
            <h2>2. Discussion / status</h2>
            <p>[Key points in brief]</p>
            <h2>3. Decisions</h2>
            <ul><li>Decision 1 — owner: … — due: …</li><li>Decision 2 — owner: … — due: …</li></ul>
            <h2>4. Next steps</h2>
            <ul><li>…</li></ul>
            <p>End: ____ · Next meeting: ________</p>
            """
        ),
        "invitation": compact(
            """
            <h1 class="wp-doc-title">Invitation</h1>
            <p class="wp-subtitle">{{company.name}}</p>
            <p>Dear {{worker.name}},</p>
            <p>you are warmly invited to:</p>
            <p class="wp-meta"><strong>Topic:</strong> [briefing / meeting / event]<br>
            <strong>Date:</strong> {{date.today}} · <strong>Time:</strong> ____<br>
            <strong>Place:</strong> {{site.name}}<br>
            <strong>Duration:</strong> approx. ____ minutes</p>
            <p>Please confirm attendance briefly to {{company.email}} or {{manager.name}}.</p>
            <p>If you cannot attend, please name a deputy.</p>
            <p class="wp-sign">Yours sincerely<br>{{manager.name}}<br>{{company.name}}</p>
            """
        ),
        "access": compact(
            """
            <h1 class="wp-doc-title">Access / assignment confirmation</h1>
            <p class="wp-subtitle">{{company.name}} · {{date.today}}</p>
            <p class="wp-meta"><strong>Person:</strong> {{worker.name}} ({{worker.badge}})<br>
            <strong>Site / area:</strong> {{site.name}}<br>
            <strong>Valid from:</strong> {{date.today}} · <strong>until:</strong> ________</p>
            <p>The named person is authorised to enter and work in the area above, provided PPE, briefing and company rules are followed.</p>
            <p>The badge must be worn visibly. Loss must be reported to {{manager.name}} immediately.</p>
            <p class="wp-sign">{{manager.name}}<br>{{company.name}}<br>{{company.contact}} · {{company.email}}</p>
            """
        ),
        "reminder": compact(
            """
            <h1 class="wp-doc-title">Reminder / deadline</h1>
            <p class="wp-subtitle">{{company.name}} · {{date.today}}</p>
            <p>Dear {{worker.name}},</p>
            <p>we kindly remind you of the following open matter:</p>
            <p class="wp-meta"><strong>Subject:</strong> [document / briefing / return / deadline]<br>
            <strong>due by:</strong> ________ · <strong>Site:</strong> {{site.name}}</p>
            <p>Please complete this in time or contact {{manager.name}} ({{company.email}}) if there are obstacles.</p>
            <p class="wp-sign">Yours sincerely<br>{{company.name}}</p>
            """
        ),
        "praise": compact(
            """
            <h1 class="wp-doc-title">Appreciation</h1>
            <p class="wp-subtitle">{{company.name}} · {{date.today}}</p>
            <p>Dear {{worker.name}},</p>
            <p>we would like to thank you expressly for your contribution:</p>
            <p class="wp-meta"><strong>Reason:</strong> [project / shift / support]<br>
            <strong>Site:</strong> {{site.name}}</p>
            <p>Your work was especially valuable for the team and {{company.name}}. Thank you for reliable and professional performance.</p>
            <p class="wp-sign">Yours sincerely<br>{{manager.name}}<br>{{company.name}}</p>
            """
        ),
        "absence": compact(
            """
            <h1 class="wp-doc-title">Absence confirmation</h1>
            <p class="wp-subtitle">{{company.name}}</p>
            <p class="wp-meta"><strong>Employee:</strong> {{worker.name}} ({{worker.badge}})<br>
            <strong>Site:</strong> {{site.name}}<br>
            <strong>Period:</strong> from ________ to ________</p>
            <p>This confirms that the named person was absent / released during the period above.</p>
            <p><strong>Reason (optional):</strong> [leave / sick / travel / other]</p>
            <p>Place, date: {{site.name}}, {{date.today}}</p>
            <p class="wp-sign">_______________________________<br>{{manager.name}}<br>{{company.name}}</p>
            """
        ),
        "handover": compact(
            """
            <h1 class="wp-doc-title">Handover protocol</h1>
            <p class="wp-subtitle">{{company.name}} · {{date.today}} · {{site.name}}</p>
            <p class="wp-meta"><strong>Handed over by:</strong> {{worker.name}} ({{worker.badge}})<br>
            <strong>Received by:</strong> ________ · <strong>Lead:</strong> {{manager.name}}</p>
            <h2>1. Items handed over</h2>
            <ul><li>Keys / badge / devices: ________</li><li>Documents / plans: ________</li><li>Open points: ________</li></ul>
            <h2>2. Condition / notes</h2>
            <p>[Short description of condition, defects, specifics]</p>
            <h2>3. Confirmation</h2>
            <p>Both sides confirm a complete handover on the date above.</p>
            <p class="wp-sign">Handover: ____________ &nbsp;&nbsp; Receiver: ____________<br>{{manager.name}} · {{company.name}}</p>
            """
        ),
        "induction": compact(
            """
            <h1 class="wp-doc-title">Induction / briefing</h1>
            <p class="wp-subtitle">{{company.name}} · {{date.today}} · {{site.name}}</p>
            <p class="wp-meta"><strong>Participant:</strong> {{worker.name}} ({{worker.badge}})<br>
            <strong>Conducted by:</strong> {{manager.name}}</p>
            <h2>Contents</h2>
            <ol>
              <li>Safety rules and PPE</li>
              <li>Emergency routes and assembly point</li>
              <li>Work area and responsibilities</li>
              <li>Reporting lines and contacts</li>
            </ol>
            <p>The briefing was understood. Questions were clarified.</p>
            <p class="wp-sign">Participant: ____________ &nbsp;&nbsp; Trainer: ____________<br>{{company.name}} · {{company.email}}</p>
            """
        ),
        "complaint_ack": compact(
            """
            <h1 class="wp-doc-title">Acknowledgement of receipt</h1>
            <p class="wp-subtitle">{{company.name}} · {{date.today}}</p>
            <p>Dear {{worker.name}},</p>
            <p>we confirm receipt of your message / complaint dated ________.</p>
            <p class="wp-meta"><strong>Subject:</strong> [short description]<br>
            <strong>Internal ref.:</strong> ________ · <strong>Site:</strong> {{site.name}}</p>
            <p>We will review the matter and get back to you by ________ at the latest. Contact: {{manager.name}} ({{company.email}}).</p>
            <p class="wp-sign">Yours sincerely<br>{{manager.name}}<br>{{company.name}}</p>
            """
        ),
        "vacation": compact(
            """
            <h1 class="wp-doc-title">Leave confirmation</h1>
            <p class="wp-subtitle">{{company.name}}</p>
            <p class="wp-meta"><strong>Employee:</strong> {{worker.name}} ({{worker.badge}})<br>
            <strong>Site:</strong> {{site.name}}<br>
            <strong>Leave from:</strong> ________ <strong>to:</strong> ________</p>
            <p>The requested leave has been approved. Please ensure handover of open tasks before departure.</p>
            <p>For changes, contact {{manager.name}} at {{company.email}}.</p>
            <p>Place, date: {{site.name}}, {{date.today}}</p>
            <p class="wp-sign">_______________________________<br>{{manager.name}}<br>{{company.name}}</p>
            """
        ),
        "blank": "<p><br></p>",
        "snGreeting": "<p>Dear {{worker.name}},</p>",
        "snClosing": "<p>Yours sincerely<br>{{manager.name}}<br>{{company.name}}</p>",
        "snAddress": '<p class="wp-letter">{{company.name}}<br>{{company.address}}<br>{{company.email}}<br>{{company.contact}}</p>',
        "snWorker": "<p><strong>Employee:</strong> {{worker.name}} ({{worker.badge}})<br><strong>Site:</strong> {{site.name}}</p>",
        "snDate": "<p>{{date.today}}</p>",
        "snSign": "<p>_______________________________<br>{{manager.name}}<br>{{company.name}}</p>",
    }


def pack_ar() -> dict[str, str]:
    """Fully Arabic templates. Only emails / phones / badge codes stay Latin (LTR)."""
    # Contact values must stay Latin; isolate LTR so RTL layout does not scramble them.
    em = '<span class="wp-ltr" dir="ltr">{{company.email}}</span>'
    ph = '<span class="wp-ltr" dir="ltr">{{company.contact}}</span>'
    badge = '<span class="wp-ltr" dir="ltr">{{worker.badge}}</span>'
    blank = "………………"

    def hint(text: str) -> str:
        # Arabic guillemets — neat fill-in prompts (no Latin square brackets).
        return f"«{text}»"

    return {
        "letter": compact(
            f"""
            <p class="wp-letter">{{{{company.name}}}}<br>{{{{company.address}}}}<br>
            <strong>البريد الإلكتروني:</strong> {em}<br>
            <strong>الهاتف:</strong> {ph}</p>
            <p class="wp-recipient">{{{{worker.name}}}}<br>{{{{site.name}}}}</p>
            <p class="wp-date">{{{{date.today}}}}</p>
            <p class="wp-subject"><strong>الموضوع:</strong> {hint("موضوع واضح ومختصر")}</p>
            <p>السادة المحترمون،</p>
            <p>بالإشارة إلى حديثنا أو إلى طلبكم، نودّ إبلاغكم بما يلي:</p>
            <p>{hint("اكتبوا هنا السبب، وما تم الاتفاق عليه، والخطوة التالية في جملتين إلى أربع")}</p>
            <p>يرجى إبلاغنا حتى تاريخ {blank} بموافقتكم، أو بالمستندات الناقصة إن وُجدت.</p>
            <p>للاستفسار يُرجى التواصل عبر البريد: {em}</p>
            <p class="wp-sign">مع أطيب التحيات<br>{{{{manager.name}}}}<br>{{{{company.name}}}}</p>
            """
        ),
        "warning": compact(
            f"""
            <h1 class="wp-doc-title">تنبيه كتابي</h1>
            <p class="wp-subtitle">{{{{company.name}}}} · {{{{date.today}}}} · سري</p>
            <p class="wp-meta"><strong>الموظف / الموظفة:</strong> {{{{worker.name}}}} · <strong>رقم الشارة:</strong> {badge}<br>
            <strong>الموقع / القسم:</strong> {{{{site.name}}}}<br>
            <strong>المسؤول:</strong> {{{{manager.name}}}}</p>
            <h2>١. الوقائع</h2>
            <p>بتاريخ {hint("اليوم والساعة")} تبيّن أن {hint("وصف الواقعة والمكان والشهود إن وُجدوا")}.</p>
            <h2>٢. التقييم</h2>
            <p>هذا السلوك لا يتوافق مع قواعد الشركة أو تعليمات التشغيل الصادرة بتاريخ {hint("تاريخ التعليمات")}.</p>
            <h2>٣. المطلوب</h2>
            <p>نتوقع الالتزام فوراً بـ {hint("القاعدة أو السلوك المطلوب")}، وتوجيه أي استفسار إلى {{{{manager.name}}}} دون تأخير.</p>
            <h2>٤. العواقب</h2>
            <p>قد تترتب على المخالفات الإضافية إجراءات وفق أنظمة العمل المعمول بها. يُحفظ هذا الكتاب للتوثيق.</p>
            <p class="wp-sign">{{{{site.name}}}}، {{{{date.today}}}}<br>{{{{manager.name}}}}<br>{{{{company.name}}}}<br>
            <strong>البريد:</strong> {em}</p>
            """
        ),
        "policy": compact(
            f"""
            <h1 class="wp-doc-title">تعليمات تشغيل</h1>
            <p class="wp-subtitle">{{{{company.name}}}} · بتاريخ {{{{date.today}}}} · موقع {{{{site.name}}}}</p>
            <h2>١. النطاق</h2>
            <p>تسري هذه التعليمات على جميع العاملين والمقاولين من الباطن والزوار في موقع {{{{site.name}}}}.</p>
            <h2>٢. قواعد عامة</h2>
            <ol>
              <li>ارتداء معدات الحماية الشخصية كاملة في مواقع العمل المحددة.</li>
              <li>إبقاء الممرات ومسارات الإخلاء ومخارج الطوارئ خالية دائماً.</li>
              <li>تشغيل الآلات والمعدات فقط بعد التوجيه والحصول على الموافقة.</li>
              <li>الإبلاغ فوراً عن الحوادث والحوادث الوشيكة والأضرار.</li>
            </ol>
            <h2>٣. سلوك الطوارئ</h2>
            <p>المحافظة على الهدوء، تأمين مصدر الخطر إن أمكن، استدعاء الإسعاف أو الطوارئ، ثم التوجه إلى نقطة التجمع.</p>
            <h2>٤. المخالفات</h2>
            <p>قد تترتب على المخالفات عواقب وفق أنظمة العمل، وقد يُقيَّد الدخول إلى الموقع.</p>
            <p class="wp-sign"><strong>المسؤول:</strong> {{{{manager.name}}}}<br>
            <strong>الهاتف:</strong> {ph} · <strong>البريد:</strong> {em}</p>
            """
        ),
        "certificate": compact(
            f"""
            <h1 class="wp-doc-title">شهادة</h1>
            <p class="wp-subtitle">{{{{company.name}}}}</p>
            <p>يُشهد بموجب هذا أنّ:</p>
            <p class="wp-center"><strong>{{{{worker.name}}}}</strong><br>
            <strong>رقم الشارة / الهوية:</strong> {badge}</p>
            <p>كان يعمل أو حاضراً لدى {{{{company.name}}}} من تاريخ {blank} إلى تاريخ {blank}.</p>
            <p class="wp-meta"><strong>الموقع:</strong> {{{{site.name}}}}<br>
            <strong>الغرض:</strong> {hint("إثبات · جهة رسمية · عميل · تأمين")}</p>
            <p>تُصدر هذه الشهادة عند الطلب، ولا تحلّ محل أي بند من بنود علاقة العمل.</p>
            <p>المكان والتاريخ: {{{{site.name}}}}، {{{{date.today}}}}</p>
            <p class="wp-sign">التوقيع: {blank}<br>{{{{manager.name}}}}<br>{{{{company.name}}}}<br>
            <strong>البريد:</strong> {em}</p>
            """
        ),
        "meeting": compact(
            f"""
            <h1 class="wp-doc-title">محضر اجتماع</h1>
            <p class="wp-meta"><strong>التاريخ:</strong> {{{{date.today}}}} · <strong>المكان:</strong> {{{{site.name}}}} · <strong>الشركة:</strong> {{{{company.name}}}}<br>
            <strong>رئاسة الجلسة:</strong> {{{{manager.name}}}} · <strong>كاتب المحضر:</strong> {hint("الاسم")}<br>
            <strong>الحضور:</strong> {{{{worker.name}}}}، {hint("أسماء الحاضرين الآخرين")}</p>
            <h2>١. جدول الأعمال</h2>
            <ol>
              <li>الترحيب وهدف الاجتماع</li>
              <li>عرض الوضع الحالي</li>
              <li>اتخاذ القرارات</li>
              <li>مواضيع متفرقة</li>
            </ol>
            <h2>٢. النقاش والوضع</h2>
            <p>{hint("اكتبوا النقاط الرئيسية باختصار")}</p>
            <h2>٣. القرارات</h2>
            <ul>
              <li>القرار الأول — المسؤول: {hint("الاسم")} — الموعد: {blank}</li>
              <li>القرار الثاني — المسؤول: {hint("الاسم")} — الموعد: {blank}</li>
            </ul>
            <h2>٤. الخطوات التالية</h2>
            <ul><li>{hint("المهمة التالية")}</li></ul>
            <p>وقت الانتهاء: {blank} · موعد الاجتماع القادم: {blank}</p>
            """
        ),
        "invitation": compact(
            f"""
            <h1 class="wp-doc-title">دعوة</h1>
            <p class="wp-subtitle">{{{{company.name}}}}</p>
            <p>عزيزي / عزيزتي {{{{worker.name}}}}،</p>
            <p>يسعدنا دعوتكم للمشاركة في:</p>
            <p class="wp-meta"><strong>الموضوع:</strong> {hint("تدريب · اجتماع · فعالية")}<br>
            <strong>التاريخ:</strong> {{{{date.today}}}} · <strong>الوقت:</strong> {blank}<br>
            <strong>المكان:</strong> {{{{site.name}}}}<br>
            <strong>المدة التقريبية:</strong> {blank} دقيقة</p>
            <p>يرجى تأكيد الحضور عبر البريد {em} أو بالتواصل مع {{{{manager.name}}}}.</p>
            <p>في حال التعذّر، يُرجى تسمية بديل مناسب.</p>
            <p class="wp-sign">مع أطيب التحيات<br>{{{{manager.name}}}}<br>{{{{company.name}}}}</p>
            """
        ),
        "access": compact(
            f"""
            <h1 class="wp-doc-title">تأكيد دخول وتكليف</h1>
            <p class="wp-subtitle">{{{{company.name}}}} · {{{{date.today}}}}</p>
            <p class="wp-meta"><strong>الشخص:</strong> {{{{worker.name}}}} · <strong>رقم الشارة:</strong> {badge}<br>
            <strong>الموقع / المنطقة:</strong> {{{{site.name}}}}<br>
            <strong>ساري من:</strong> {{{{date.today}}}} · <strong>حتى:</strong> {blank}</p>
            <p>يُخوَّل الشخص المذكور بدخول المنطقة أعلاه والعمل فيها، مع الالتزام بمعدات الحماية الشخصية، والتوجيه، وقواعد الشركة.</p>
            <p>يجب إظهار الشارة بشكل واضح. عند فقدانها يُبلَّغ {{{{manager.name}}}} فوراً.</p>
            <p class="wp-sign">{{{{manager.name}}}}<br>{{{{company.name}}}}<br>
            <strong>الهاتف:</strong> {ph} · <strong>البريد:</strong> {em}</p>
            """
        ),
        "reminder": compact(
            f"""
            <h1 class="wp-doc-title">تذكير ومهلة</h1>
            <p class="wp-subtitle">{{{{company.name}}}} · {{{{date.today}}}}</p>
            <p>عزيزي / عزيزتي {{{{worker.name}}}}،</p>
            <p>نذكّركم بلطف بالأمر المفتوح التالي:</p>
            <p class="wp-meta"><strong>الموضوع:</strong> {hint("مستند · تدريب · إرجاع · مهلة")}<br>
            <strong>يستحق حتى:</strong> {blank} · <strong>الموقع:</strong> {{{{site.name}}}}</p>
            <p>يرجى إنجاز المطلوب في الوقت المحدد، أو التواصل مع {{{{manager.name}}}} عبر البريد {em} عند وجود أي عائق.</p>
            <p class="wp-sign">مع أطيب التحيات<br>{{{{company.name}}}}</p>
            """
        ),
        "praise": compact(
            f"""
            <h1 class="wp-doc-title">شكر وتقدير</h1>
            <p class="wp-subtitle">{{{{company.name}}}} · {{{{date.today}}}}</p>
            <p>عزيزي / عزيزتي {{{{worker.name}}}}،</p>
            <p>نتقدم إليكم بجزيل الشكر على إسهامكم المميز:</p>
            <p class="wp-meta"><strong>المناسبة:</strong> {hint("مشروع · وردية · دعم للفريق")}<br>
            <strong>الموقع:</strong> {{{{site.name}}}}</p>
            <p>كان عملكم قيّماً للفريق ولشركة {{{{company.name}}}}. نشكركم على الأداء الموثوق والمهني.</p>
            <p class="wp-sign">مع أطيب التحيات<br>{{{{manager.name}}}}<br>{{{{company.name}}}}</p>
            """
        ),
        "absence": compact(
            f"""
            <h1 class="wp-doc-title">تأكيد غياب</h1>
            <p class="wp-subtitle">{{{{company.name}}}}</p>
            <p class="wp-meta"><strong>الموظف / الموظفة:</strong> {{{{worker.name}}}} · <strong>رقم الشارة:</strong> {badge}<br>
            <strong>الموقع:</strong> {{{{site.name}}}}<br>
            <strong>الفترة:</strong> من {blank} إلى {blank}</p>
            <p>يُؤكَّد أن الشخص المذكور كان غائباً أو مُعفى خلال الفترة المبيّنة أعلاه.</p>
            <p><strong>السبب (اختياري):</strong> {hint("إجازة · مرض · مهمة رسمية · أخرى")}</p>
            <p>المكان والتاريخ: {{{{site.name}}}}، {{{{date.today}}}}</p>
            <p class="wp-sign">التوقيع: {blank}<br>{{{{manager.name}}}}<br>{{{{company.name}}}}</p>
            """
        ),
        "handover": compact(
            f"""
            <h1 class="wp-doc-title">محضر تسليم واستلام</h1>
            <p class="wp-subtitle">{{{{company.name}}}} · {{{{date.today}}}} · {{{{site.name}}}}</p>
            <p class="wp-meta"><strong>المُسلِّم:</strong> {{{{worker.name}}}} · <strong>رقم الشارة:</strong> {badge}<br>
            <strong>المستلم:</strong> {blank} · <strong>المسؤول:</strong> {{{{manager.name}}}}</p>
            <h2>١. المواد المسلَّمة</h2>
            <ul>
              <li>مفاتيح / شارة / أجهزة: {blank}</li>
              <li>مستندات / مخططات: {blank}</li>
              <li>نقاط مفتوحة: {blank}</li>
            </ul>
            <h2>٢. الحالة والملاحظات</h2>
            <p>{hint("وصف مختصر للحالة والعيوب وأي خصوصيات")}</p>
            <h2>٣. التأكيد</h2>
            <p>يؤكد الطرفان اكتمال التسليم في التاريخ المذكور أعلاه.</p>
            <p class="wp-sign">توقيع المسلّم: {blank}<br>توقيع المستلم: {blank}<br>
            {{{{manager.name}}}} · {{{{company.name}}}}</p>
            """
        ),
        "induction": compact(
            f"""
            <h1 class="wp-doc-title">توجيه وتدريب تمهيدي</h1>
            <p class="wp-subtitle">{{{{company.name}}}} · {{{{date.today}}}} · {{{{site.name}}}}</p>
            <p class="wp-meta"><strong>المشارك / المشاركة:</strong> {{{{worker.name}}}} · <strong>رقم الشارة:</strong> {badge}<br>
            <strong>نفّذه:</strong> {{{{manager.name}}}}</p>
            <h2>المحتويات</h2>
            <ol>
              <li>قواعد السلامة ومعدات الحماية الشخصية</li>
              <li>مسارات الطوارئ ونقطة التجمع</li>
              <li>منطقة العمل والمسؤوليات</li>
              <li>قنوات الإبلاغ وجهات الاتصال</li>
            </ol>
            <p>تم استيعاب التوجيه، والإجابة عن جميع الأسئلة المطروحة.</p>
            <p class="wp-sign">توقيع المشارك: {blank}<br>توقيع المدرّب: {blank}<br>
            {{{{company.name}}}} · <strong>البريد:</strong> {em}</p>
            """
        ),
        "complaint_ack": compact(
            f"""
            <h1 class="wp-doc-title">إقرار بالاستلام</h1>
            <p class="wp-subtitle">{{{{company.name}}}} · {{{{date.today}}}}</p>
            <p>عزيزي / عزيزتي {{{{worker.name}}}}،</p>
            <p>نؤكد استلام رسالتكم أو شكواكم بتاريخ {blank}.</p>
            <p class="wp-meta"><strong>الموضوع:</strong> {hint("وصف مختصر")}<br>
            <strong>المرجع الداخلي:</strong> {blank} · <strong>الموقع:</strong> {{{{site.name}}}}</p>
            <p>سنراجع الأمر ونعاود التواصل معكم حتى تاريخ {blank} كحد أقصى.</p>
            <p><strong>جهة الاتصال:</strong> {{{{manager.name}}}} · <strong>البريد:</strong> {em}</p>
            <p class="wp-sign">مع أطيب التحيات<br>{{{{manager.name}}}}<br>{{{{company.name}}}}</p>
            """
        ),
        "vacation": compact(
            f"""
            <h1 class="wp-doc-title">تأكيد إجازة</h1>
            <p class="wp-subtitle">{{{{company.name}}}}</p>
            <p class="wp-meta"><strong>الموظف / الموظفة:</strong> {{{{worker.name}}}} · <strong>رقم الشارة:</strong> {badge}<br>
            <strong>الموقع:</strong> {{{{site.name}}}}<br>
            <strong>الإجازة من:</strong> {blank} <strong>إلى:</strong> {blank}</p>
            <p>تمت الموافقة على الإجازة المطلوبة. يُرجى تسليم المهام المفتوحة قبل المغادرة.</p>
            <p>عند أي تغيير، يُرجى التواصل مع {{{{manager.name}}}} عبر البريد {em}.</p>
            <p>المكان والتاريخ: {{{{site.name}}}}، {{{{date.today}}}}</p>
            <p class="wp-sign">التوقيع: {blank}<br>{{{{manager.name}}}}<br>{{{{company.name}}}}</p>
            """
        ),
        "blank": "<p><br></p>",
        "snGreeting": "<p>عزيزي / عزيزتي {{worker.name}}،</p>",
        "snClosing": "<p>مع أطيب التحيات<br>{{manager.name}}<br>{{company.name}}</p>",
        "snAddress": compact(
            f"""
            <p class="wp-letter">{{{{company.name}}}}<br>{{{{company.address}}}}<br>
            <strong>البريد الإلكتروني:</strong> {em}<br>
            <strong>الهاتف:</strong> {ph}</p>
            """
        ),
        "snWorker": compact(
            f"""
            <p><strong>الموظف / الموظفة:</strong> {{{{worker.name}}}} · <strong>رقم الشارة:</strong> {badge}<br>
            <strong>الموقع:</strong> {{{{site.name}}}}</p>
            """
        ),
        "snDate": "<p>{{date.today}}</p>",
        "snSign": compact(
            f"""
            <p>التوقيع: {blank}<br>{{{{manager.name}}}}<br>{{{{company.name}}}}</p>
            """
        ),
    }


# Lightweight locale overlays for other langs (start from EN, replace headings)
REPL = {
    "tr": [
        ("Written notice", "Yazılı uyarı"),
        ("Work instruction", "İş talimatı"),
        ("Certificate", "Belge"),
        ("Minutes", "Tutanak"),
        ("Invitation", "Davetiye"),
        ("Access / assignment confirmation", "Giriş / görev onayı"),
        ("Reminder / deadline", "Hatırlatma / süre"),
        ("Appreciation", "Takdir"),
        ("Absence confirmation", "Devamsızlık onayı"),
        ("Handover protocol", "Devir tutanağı"),
        ("Induction / briefing", "Oryantasyon / talimat"),
        ("Acknowledgement of receipt", "Alındı bildirimi"),
        ("Leave confirmation", "İzin onayı"),
        ("Subject:", "Konu:"),
        ("Employee:", "Çalışan:"),
        ("Site:", "Lokasyon:"),
        ("Dear ", "Sayın "),
        ("Yours sincerely", "Saygılarımızla"),
        ("confidential", "gizli"),
    ],
    "fr": [
        ("Written notice", "Avertissement écrit"),
        ("Work instruction", "Consignes de travail"),
        ("Certificate", "Attestation"),
        ("Minutes", "Procès-verbal"),
        ("Invitation", "Invitation"),
        ("Access / assignment confirmation", "Confirmation d’accès / mission"),
        ("Reminder / deadline", "Rappel / délai"),
        ("Appreciation", "Remerciement"),
        ("Absence confirmation", "Attestation d’absence"),
        ("Handover protocol", "Procès-verbal de remise"),
        ("Induction / briefing", "Accueil / consigne"),
        ("Acknowledgement of receipt", "Accusé de réception"),
        ("Leave confirmation", "Confirmation de congés"),
        ("Subject:", "Objet :"),
        ("Employee:", "Salarié :"),
        ("Site:", "Site :"),
        ("Dear ", "Cher/Chère "),
        ("Yours sincerely", "Cordialement"),
        ("confidential", "confidentiel"),
    ],
    "es": [
        ("Written notice", "Aviso escrito"),
        ("Work instruction", "Instrucción de trabajo"),
        ("Certificate", "Certificado"),
        ("Minutes", "Acta"),
        ("Invitation", "Invitación"),
        ("Access / assignment confirmation", "Confirmación de acceso / misión"),
        ("Reminder / deadline", "Recordatorio / plazo"),
        ("Appreciation", "Reconocimiento"),
        ("Absence confirmation", "Confirmación de ausencia"),
        ("Handover protocol", "Acta de entrega"),
        ("Induction / briefing", "Inducción / instrucción"),
        ("Acknowledgement of receipt", "Acuse de recibo"),
        ("Leave confirmation", "Confirmación de vacaciones"),
        ("Subject:", "Asunto:"),
        ("Employee:", "Empleado:"),
        ("Site:", "Sitio:"),
        ("Dear ", "Estimado/a "),
        ("Yours sincerely", "Atentamente"),
        ("confidential", "confidencial"),
    ],
    "it": [
        ("Written notice", "Richiamo scritto"),
        ("Work instruction", "Istruzione operativa"),
        ("Certificate", "Attestato"),
        ("Minutes", "Verbale"),
        ("Invitation", "Invito"),
        ("Access / assignment confirmation", "Conferma accesso / incarico"),
        ("Reminder / deadline", "Promemoria / scadenza"),
        ("Appreciation", "Riconoscimento"),
        ("Absence confirmation", "Conferma assenza"),
        ("Handover protocol", "Verbale di consegna"),
        ("Induction / briefing", "Inserimento / istruzione"),
        ("Acknowledgement of receipt", "Conferma di ricezione"),
        ("Leave confirmation", "Conferma ferie"),
        ("Subject:", "Oggetto:"),
        ("Employee:", "Dipendente:"),
        ("Site:", "Sede:"),
        ("Dear ", "Gentile "),
        ("Yours sincerely", "Cordiali saluti"),
        ("confidential", "riservato"),
    ],
    "pl": [
        ("Written notice", "Upomnienie pisemne"),
        ("Work instruction", "Instrukcja pracy"),
        ("Certificate", "Zaświadczenie"),
        ("Minutes", "Protokół"),
        ("Invitation", "Zaproszenie"),
        ("Access / assignment confirmation", "Potwierdzenie dostępu / zadania"),
        ("Reminder / deadline", "Przypomnienie / termin"),
        ("Appreciation", "Podziękowanie"),
        ("Absence confirmation", "Potwierdzenie nieobecności"),
        ("Handover protocol", "Protokół przekazania"),
        ("Induction / briefing", "Wdrożenie / szkolenie"),
        ("Acknowledgement of receipt", "Potwierdzenie odbioru"),
        ("Leave confirmation", "Potwierdzenie urlopu"),
        ("Subject:", "Temat:"),
        ("Employee:", "Pracownik:"),
        ("Site:", "Lokalizacja:"),
        ("Dear ", "Szanowny/a "),
        ("Yours sincerely", "Z poważaniem"),
        ("confidential", "poufne"),
    ],
}


def localize(base: dict[str, str], pairs: list[tuple[str, str]]) -> dict[str, str]:
    out = {}
    for k, v in base.items():
        text = v
        for a, b in pairs:
            text = text.replace(a, b)
        out[k] = text
    return out


TOPICS = {
    "correspondence": ["letter", "invitation", "reminder", "complaint_ack"],
    "hr": ["warning", "certificate", "praise", "absence", "vacation"],
    "ops": ["access", "handover", "induction"],
    "safety": ["policy"],
    "meetings": ["meeting"],
    "blank": ["blank"],
}


def main() -> None:
    en = pack_en()
    packs = {
        "de": pack_de(),
        "en": en,
        "ar": pack_ar(),
        "tr": localize(en, REPL["tr"]),
        "fr": localize(en, REPL["fr"]),
        "es": localize(en, REPL["es"]),
        "it": localize(en, REPL["it"]),
        "pl": localize(en, REPL["pl"]),
    }
    # letter/snippets overrides for extras already partly in letter from localize Subject etc.
    packs["tr"]["letter"] = localize({"letter": en["letter"]}, REPL["tr"] + [("Dear Sir or Madam,", "Sayın ilgili,")])["letter"]
    packs["tr"]["snGreeting"] = "<p>Sayın {{worker.name}},</p>"
    packs["tr"]["snClosing"] = "<p>Saygılarımızla<br>{{manager.name}}<br>{{company.name}}</p>"
    packs["fr"]["snGreeting"] = "<p>Cher/Chère {{worker.name}},</p>"
    packs["fr"]["snClosing"] = "<p>Cordialement<br>{{manager.name}}<br>{{company.name}}</p>"
    packs["es"]["snGreeting"] = "<p>Estimado/a {{worker.name}}:</p>"
    packs["es"]["snClosing"] = "<p>Atentamente<br>{{manager.name}}<br>{{company.name}}</p>"
    packs["it"]["snGreeting"] = "<p>Gentile {{worker.name}},</p>"
    packs["it"]["snClosing"] = "<p>Cordiali saluti<br>{{manager.name}}<br>{{company.name}}</p>"
    packs["pl"]["snGreeting"] = "<p>Szanowny/a {{worker.name}},</p>"
    packs["pl"]["snClosing"] = "<p>Z poważaniem<br>{{manager.name}}<br>{{company.name}}</p>"

    out = Path(__file__).with_name("docs-i18n-content.js")
    payload = {
        "bodies": packs,
        "topics": TOPICS,
    }
    text = (
        "/** High-quality template bodies + topic catalog — 8 languages. */\n"
        "window.DocsContentI18n = "
        + json.dumps(packs, ensure_ascii=False, indent=2)
        + ";\n"
        "window.DocsTemplateTopics = "
        + json.dumps(TOPICS, ensure_ascii=False, indent=2)
        + ";\n"
    )
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out} templates={len(en)} langs={list(packs)}")


if __name__ == "__main__":
    main()
