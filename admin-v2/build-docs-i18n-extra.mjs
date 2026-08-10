#!/usr/bin/env node
/**
 * Build docs-i18n-extra.js from HTML fallbacks + curated plain-language strings.
 * Run: node admin-v2/build-docs-i18n-extra.mjs
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const root = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.join(root, "docs.html"), "utf8");
const app = fs.readFileSync(path.join(root, "docs-app.js"), "utf8");
const i18nSrc = fs.readFileSync(path.join(root, "docs-i18n.js"), "utf8");
const report = JSON.parse(
  fs.readFileSync(path.join(root, "i18n-reports", "docs-i18n-report.json"), "utf8")
);

function extractObjectLiteral(src, marker) {
  const start = src.indexOf(marker);
  if (start < 0) throw new Error("marker not found: " + marker);
  const braceStart = src.indexOf("{", start);
  let depth = 0;
  let inStr = false;
  let quote = "";
  let esc = false;
  for (let i = braceStart; i < src.length; i++) {
    const ch = src[i];
    if (inStr) {
      if (esc) {
        esc = false;
        continue;
      }
      if (ch === "\\") {
        esc = true;
        continue;
      }
      if (ch === quote) inStr = false;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === "`") {
      inStr = true;
      quote = ch;
      continue;
    }
    if (ch === "{") depth++;
    else if (ch === "}") {
      depth--;
      if (depth === 0) return src.slice(braceStart, i + 1);
    }
  }
  throw new Error("unbalanced object for " + marker);
}

const packs = Function(`"use strict"; return (${extractObjectLiteral(i18nSrc, "window.DocsPageI18n")});`)();

/** HTML data-di18n → fallback text */
const htmlMap = {};
for (const m of html.matchAll(/data-di18n="([^"]+)"(?:\s+data-di18n-attr="([^"]+)")?[^>]*>([^<]*)</g)) {
  const key = m[1];
  const text = m[3]
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .trim();
  if (text && !htmlMap[key]) htmlMap[key] = text;
}
for (const m of html.matchAll(/data-di18n="([^"]+)"\s+data-di18n-attr="placeholder"[^>]*placeholder="([^"]*)"/g)) {
  if (m[2].trim() && !htmlMap[m[1]]) htmlMap[m[1]] = m[2].trim();
}
for (const m of html.matchAll(/placeholder="([^"]*)"[^>]*data-di18n="([^"]+)"\s+data-di18n-attr="placeholder"/g)) {
  if (m[1].trim() && !htmlMap[m[2]]) htmlMap[m[2]] = m[1].trim();
}
for (const m of html.matchAll(/data-di18n="([^"]+)"\s+data-di18n-attr="aria-label"[^>]*aria-label="([^"]*)"/g)) {
  if (m[2].trim() && !htmlMap[m[1]]) htmlMap[m[1]] = m[2].trim();
}
for (const m of html.matchAll(/aria-label="([^"]*)"[^>]*data-di18n="([^"]+)"\s+data-di18n-attr="aria-label"/g)) {
  if (m[1].trim() && !htmlMap[m[2]]) htmlMap[m[2]] = m[1].trim();
}

/** dt("k") || "fallback" */
const dtFallback = {};
for (const m of app.matchAll(/\bdt\(\s*["']([^"']+)["']\s*(?:,\s*\{[^}]*\})?\s*\)\s*\|\|\s*["']([^"']+)["']/g)) {
  dtFallback[m[1]] = m[2];
}

function humanize(key) {
  return String(key)
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim();
}

/** Plain-language DE overrides (client-safe). */
const dePlain = {
  // Navigation / rail
  mobileOut: "Fertigstellen & senden",
  railKicker: "Fertigstellen",
  railTitle: "Dokument abschließen",
  deliver: "Versenden & drucken",
  deliverHint: "PDF, Druck und E-Mail nutzen das gespeicherte Dokument.",
  fineTune: "Seitenlayout (optional)",
  fillMerge: "Felder automatisch ausfüllen",
  checkPlaceholders: "Leere Felder prüfen",
  templatesHint: "Thema wählen, Vorlage einsetzen, Felder ausfüllen.",
  mergeModalTitle: "Felder ausfüllen",
  mergeModalHint: "Mitarbeiter wählen, offene Felder ergänzen, dann ausfüllen.",
  mergeApply: "Jetzt ausfüllen",
  mergeRefresh: "Vorschau aktualisieren",
  mergeWillFill: "Wird ausgefüllt",
  mergeStillOpen: "Noch offen",
  mergeManualTitle: "Offene Felder ausfüllen",
  mergeMenu: "Felder einfügen",
  placeholdersOpen: "{n} Felder noch nicht ausgefüllt",
  placeholdersClear: "Alle Felder sind ausgefüllt",
  printCleanWarn: "Noch {n} leere Felder — trotzdem drucken?",
  printPreviewCheck: "Leere Felder markieren",
  auto: "Auto",

  // Chips / fields
  chipBadge: "Ausweis-Nr.",
  chipManager: "Vorgesetzte/r",
  chipWorkerEmail: "E-Mail Mitarbeiter",
  chipWorkerRole: "Rolle",
  chipWorkerPhone: "Telefon Mitarbeiter",
  chipWorkerSite: "Standort Mitarbeiter",
  chipShiftSlot: "Schicht",
  chipShiftSite: "Schicht-Standort",
  chipSiteAddress: "Standortadresse",
  chipContact: "Kontakt",
  chipSector: "Branche",
  chipDateIso: "Datum (ISO)",
  snWorker: "Mitarbeiterzeile",

  // Actions
  wordPro: "Word-Editor (erweitert)",
  focus: "Vollbild schreiben",
  exitFocus: "Vollbild beenden",
  reset: "Zurücksetzen",
  shareLink: "Freigabe-Link",
  emailWithPdf: "E-Mail mit PDF",
  exportHtml: "Als Webseite",
  copyEditorLink: "Bearbeitungslink kopieren",
  cmdPalette: "Schnellaktionen",
  cmdPh: "Aktion suchen…",
  cmdHint: "Tipp: schreiben und Enter",
  lockNow: "Bearbeitung sperren",
  offlineSync: "Jetzt synchronisieren",
  applyAndReturn: "Übernehmen & zurück",
  returnContract: "Zurück zum Vertrag",
  contractBanner: "Vertragsmodus — speichern, dann zum Vertrag übernehmen.",
  publishArchiveHint: "Nach Freigabe liegt das PDF im Mitarbeiter-Archiv.",
  useLetterhead: "Briefkopf (Logo) auf dem Papier",
  brandHint: "Logo ist optional — Sie entscheiden.",
  header: "Kopfzeile",
  footer: "Fußzeile",

  // Sign / security (plain)
  signAesNote: "Die Unterschrift wird am Dokument gespeichert (einfache elektronische Signatur).",
  signLockLabel: "Danach Dokument sperren (nicht mehr bearbeitbar)",
  signPinLabel: "Sicherheitscode (mind. 4 Zeichen)",
  signQesStart: "Qualifizierte Signatur starten",
  signInsert: "Unterschrift einfügen",
  signAuditTitle: "Unterschriften-Protokoll",
  permDeniedSign: "Unterschreiben nur für Firmen-Administratoren.",
  qesStatusLoading: "Signatur-Status wird geprüft…",
  emailSmtpHint: "Wenn die E-Mail nicht ankommt: Versand in den Firmeneinstellungen prüfen.",
  emailModalHint: "PDF wird automatisch erstellt und mitgeschickt.",
  emailModalTitle: "Dokument per E-Mail senden",
  publishCompliance: "Als Nachweis für Behörden/Prüfung markieren",
  ooNeed: "Der erweiterte Word-Editor ist auf diesem Server nicht eingerichtet. Bitte Support kontaktieren.",
  ooSync: "Änderungen aus Word übernehmen",

  // Workflow
  workflowTitle: "Freigabe",
  workflowNext: "Zur Prüfung senden",
  workflowApprove: "Freigeben",
  workflowUnlock: "Weiter bearbeiten",
  workflowHintDraft: "Noch Entwurf — nach Prüfung freigeben.",
  unreadDocsTitle: "Noch nicht gelesen",
  expiringDocsTitle: "Läuft in 14 Tagen ab",

  // Common UI
  undo: "Rückgängig",
  redo: "Wiederholen",
  find: "Suchen",
  replace: "Ersetzen",
  replaceWith: "Ersetzen durch",
  replaceAll: "Alle ersetzen",
  replaceOne: "Ersetzen",
  findPh: "Im Dokument suchen…",
  replacePh: "Ersatztext…",
  duplicate: "Duplizieren",
  saveAsTemplate: "Als Vorlage speichern",
  tbEdit: "Bearbeiten",
  shortcuts: "Tastaturkürzel",
  ribbon: "Formatierung",
  spellLang: "Rechtschreibung",
  spellOff: "Aus",
  insertImage: "Bild",
  insertToc: "Inhaltsverzeichnis",
  importDocx: "Word importieren…",
  exportDocx: "Word (.docx)",
  printPreview: "Druckvorschau",
  printAsPdf: "Als PDF",
  printClean: "Sauber drucken",
  preflightTitle: "Vor dem Senden prüfen",
  preflightContinue: "Trotzdem fortfahren",
  shareModalTitle: "Freigabe-Link",
  shareCreate: "Link erzeugen",
  shareTtl: "Link gültig für (Stunden)",
  sharePassword: "Passwort (optional)",
  shareApprovedOnly: "Nur wenn freigegeben",
  shareRevokeAll: "Alle Links widerrufen",
  signModalTitle: "Unterschrift",
  signNamePrompt: "Name des Unterzeichners",
  signDrawHint: "Mit Maus oder Finger unterschreiben.",
  signClear: "Löschen",
  signLineOnly: "Nur Unterschriftszeile",
  signSaveMine: "Als meine speichern",
  signLoadMine: "Meine laden",
  signStampLabel: "Stempel «Unterschrieben» setzen",
  commentsPanel: "Kommentare",
  reviewModeBanner: "Prüfmodus — Text gesperrt; Vorschläge annehmen oder ablehnen.",
  suggestionsTitle: "Vorschläge",
  suggestionsEmpty: "Keine Vorschläge",
  addSuggestion: "Vorschlag",
  addReviewComment: "Kommentar",
  commentsOpen: "Offen",
  commentsDone: "Erledigt",
  commentsAll: "Alle",
  commentsEmpty: "Noch keine Kommentare",
  outline: "Gliederung",
  outlineEmpty: "Keine Überschriften",
  collabConflictText: "Dokument wurde von jemand anderem gespeichert.",
  collabReload: "Neu laden",
  collabKeep: "Weiter bearbeiten",
  liveFollow: "Mitbearbeiter folgen",
  tplEditHint: "Vorlage im Editor — nach Anpassung als eigene Vorlage speichern.",
  emptyTitle: "Neues Dokument",
  emptyHint: "Vorlage wählen oder leer starten.",
  emptyKicker: "Loslegen",
  emptyBlank: "Leeres Dokument",
  emptyPickTpl: "Vorlage wählen",
  watermark: "Wasserzeichen",
  wmNone: "Keins",
  wmDraft: "Entwurf",
  wmConfidential: "Vertraulich",
  wmCopy: "Kopie",
  brandLogoPick: "Firmenlogo wählen",
  brandLogoUpload: "Logo setzen",
  brandLogoClear: "Logo entfernen",
  brandLogoReadonly: "Logo nur durch Admin änderbar.",
  fpPageOnly: "Nur Seite X / Y",
  imgSize: "Bildgröße",
  imgSizeBar: "Bild anpassen",
  imgFull: "Volle Breite",
  selBubble: "Schnellformat",
  slashMenu: "Blöcke einfügen",
  translateUi: "Oberfläche übersetzen",
  aiFromExpiry: "Text wegen Ablaufdatum",
  aiFromAttendance: "Text wegen Verspätung",
  aiGroundedImprove: "Mit Firmendaten verbessern",
  aiDraftWarning: "KI-Entwurf — bitte prüfen und anpassen.",
  versionPreviewTitle: "Versionsvorschau",
  versionTabPreview: "Vorschau",
  versionTabDiff: "Änderungen",
  diffUnified: "Eine Ansicht",
  diffOnlyChanges: "Nur Änderungen",
  diffRestore: "Wiederherstellen",
  diffSaveCopy: "Kopie speichern",
  versionPreviewBtn: "Vorschau",
  offlineDiscard: "Verwerfen",
  offlineRestore: "Wiederherstellen",
  offlineReloadServer: "Server laden",
  emailTo: "An",
  emailToAddress: "E-Mail-Adresse",
  emailToManual: "Manuell / anderer Empfänger",
  emailSubject: "Betreff",
  emailMessage: "Nachricht",
  emailSend: "Senden",
  emailFallbackShare: "Lokal teilen…",
  emailTestSend: "Test-E-Mail senden",
  publishDocType: "Dokumenttyp",
  publishExpiry: "Ablaufdatum (optional)",
  publishNotify: "Mitarbeiter benachrichtigen",
  backContracts: "Zu den Verträgen",
  autosaved: "Automatisch gespeichert",
  clipboardFail: "Kopieren nicht möglich",
  findPrev: "Vorheriges",
  findNext: "Nächstes",
  fmtBold: "Fett",
  fmtItalic: "Kursiv",
  fmtUnderline: "Unterstrichen",
  fmtStrike: "Durchgestrichen",
  fmtLink: "Link",
  fmtQuote: "Zitat",
  fmtComment: "Kommentar",
  alignLeft: "Links",
  alignCenter: "Zentriert",
  alignRight: "Rechts",
  docTypeOther: "Sonstiges",
  docTypeMinWage: "Mindestlohnnachweis",
  docTypeWorkPermit: "Arbeitserlaubnis",
  docTypeResidence: "Aufenthaltserlaubnis",
  docTypeHealth: "Gesundheitszeugnis",
  docTypeRegistration: "Meldebescheinigung",
  tableAddRow: "Zeile +",
  tableDelRow: "Zeile −",
  tableAddCol: "Spalte +",
  tableDelCol: "Spalte −",
};

/** EN plain */
const enPlain = {
  mobileOut: "Finish & send",
  railKicker: "Finish",
  railTitle: "Complete document",
  deliver: "Send & print",
  deliverHint: "PDF, print and email use the saved document.",
  fineTune: "Page layout (optional)",
  fillMerge: "Fill fields automatically",
  checkPlaceholders: "Check empty fields",
  templatesHint: "Pick a topic, apply a template, fill the fields.",
  mergeModalTitle: "Fill fields",
  mergeModalHint: "Select an employee, complete open fields, then fill.",
  mergeApply: "Fill now",
  mergeRefresh: "Refresh preview",
  mergeWillFill: "Will be filled",
  mergeStillOpen: "Still open",
  mergeManualTitle: "Complete open fields",
  mergeMenu: "Insert fields",
  placeholdersOpen: "{n} fields still empty",
  placeholdersClear: "All fields are filled",
  printCleanWarn: "{n} empty fields remain — print anyway?",
  printPreviewCheck: "Highlight empty fields",
  auto: "Auto",
  chipBadge: "ID number",
  chipManager: "Manager",
  chipWorkerEmail: "Employee email",
  chipWorkerRole: "Role",
  wordPro: "Word editor (advanced)",
  focus: "Focus writing",
  exitFocus: "Exit focus",
  reset: "Reset",
  shareLink: "Share link",
  emailWithPdf: "Email with PDF",
  exportHtml: "Export as webpage",
  copyEditorLink: "Copy edit link",
  cmdPalette: "Quick actions",
  lockNow: "Lock editing",
  offlineSync: "Sync now",
  contractBanner: "Contract mode — save, then apply to the contract.",
  signAesNote: "The signature is stored on the document (simple electronic signature).",
  signLockLabel: "Then lock the document (no further edits)",
  signQesStart: "Start qualified signature",
  signInsert: "Insert signature",
  emailSmtpHint: "If email fails: check sending in company settings.",
  emailModalHint: "PDF is created automatically and attached.",
  publishCompliance: "Mark as official proof / compliance record",
  ooNeed: "The advanced Word editor is not set up on this server. Please contact support.",
  workflowTitle: "Approval",
  workflowNext: "Send for review",
  workflowApprove: "Approve",
  workflowUnlock: "Continue editing",
  unreadDocsTitle: "Unread releases",
  expiringDocsTitle: "Expiring within 14 days",
  undo: "Undo",
  redo: "Redo",
  find: "Find",
  replace: "Replace",
  duplicate: "Duplicate",
  saveAsTemplate: "Save as template",
  preflightTitle: "Check before sending",
  preflightContinue: "Continue anyway",
  commentsPanel: "Comments",
  outline: "Outline",
  watermark: "Watermark",
  wmNone: "None",
  wmDraft: "Draft",
  wmConfidential: "Confidential",
  wmCopy: "Copy",
  findPrev: "Previous",
  findNext: "Next",
  fmtBold: "Bold",
  fmtItalic: "Italic",
  fmtUnderline: "Underline",
  fmtStrike: "Strikethrough",
  fmtLink: "Link",
  fmtQuote: "Quote",
  fmtComment: "Comment",
  alignLeft: "Left",
  alignCenter: "Center",
  alignRight: "Right",
  docTypeOther: "Other",
  docTypeMinWage: "Minimum wage proof",
  docTypeWorkPermit: "Work permit",
  docTypeResidence: "Residence permit",
  docTypeHealth: "Health certificate",
  docTypeRegistration: "Registration certificate",
  tableAddRow: "Row +",
  tableDelRow: "Row −",
  tableAddCol: "Col +",
  tableDelCol: "Col −",
  collabConflictText: "Document was saved by someone else.",
  collabReload: "Reload",
  collabKeep: "Keep editing",
  liveFollow: "Follow collaborators",
  findPh: "Search in document…",
  replaceWith: "Replace with",
  replacePh: "Replacement text…",
  replaceAll: "Replace all",
  emptyTitle: "New document",
  emptyHint: "Pick a template or start blank.",
  emptyBlank: "Blank document",
  emptyPickTpl: "Choose template",
  outlineEmpty: "No headings yet",
  versionPreviewTitle: "Version preview",
  versionTabPreview: "Preview",
  versionTabDiff: "Changes",
  diffUnified: "Unified view",
  diffOnlyChanges: "Changes only",
  printAsPdf: "As PDF",
  printClean: "Clean print",
  cmdPh: "Search actions…",
  cmdHint: "Type and press Enter",
  slashMenu: "Insert blocks",
  reviewModeBanner: "Review mode — text locked; accept or reject suggestions.",
  suggestionsTitle: "Suggestions",
  addSuggestion: "Suggestion",
  addReviewComment: "Comment",
  commentsOpen: "Open",
  commentsDone: "Done",
  commentsAll: "All",
  commentsEmpty: "No comments yet",
  shareModalTitle: "Share link",
  emailModalTitle: "Send document by email",
  signDrawHint: "Sign with mouse or finger.",
  selBubble: "Quick format",
  imgSizeBar: "Adjust image",
  imgSize: "Image size",
  imgFull: "Full width",
  spellOff: "Off",
  offlineDiscard: "Discard",
  offlineRestore: "Restore",
  offlineReloadServer: "Load from server",
  brandLogoReadonly: "Only an admin can change the logo.",
  workflowHintDraft: "Still a draft — send for review, then approve.",
  publishArchiveHint: "After approval the PDF goes to the employee archive.",
  fpPageOnly: "Page X / Y only",
  aiFromExpiry: "Text for expiry date",
  aiFromAttendance: "Text for lateness",
  aiGroundedImprove: "Improve with company data",
  aiDraftWarning: "AI draft — please review and edit.",
  translateUi: "Translate UI",
  signAuditTitle: "Signature log",
  ooSync: "Apply changes from Word",
};

/** AR plain */
const arPlain = {
  mobileOut: "إنهاء وإرسال",
  railKicker: "إنهاء",
  railTitle: "إكمال المستند",
  deliver: "إرسال وطباعة",
  deliverHint: "يعتمد PDF والطباعة والبريد على المستند المحفوظ.",
  fineTune: "تنسيق الصفحة (اختياري)",
  fillMerge: "ملء الحقول تلقائياً",
  checkPlaceholders: "فحص الحقول الفارغة",
  templatesHint: "اختر موضوعاً، طبّق قالباً، ثم املأ الحقول.",
  mergeModalTitle: "ملء الحقول",
  mergeModalHint: "اختر موظفاً، أكمل الحقول المفتوحة، ثم املأ.",
  mergeApply: "املأ الآن",
  mergeRefresh: "تحديث المعاينة",
  mergeWillFill: "سيتم ملؤها",
  mergeStillOpen: "ما زال مفتوحاً",
  mergeManualTitle: "أكمل الحقول المفتوحة",
  mergeMenu: "إدراج حقول",
  placeholdersOpen: "{n} حقول لم تُملأ بعد",
  placeholdersClear: "كل الحقول ممتلئة",
  printCleanWarn: "ما زال هناك {n} حقول فارغة — هل تطبع على أي حال؟",
  printPreviewCheck: "إظهار الحقول الفارغة",
  auto: "تلقائي",
  chipBadge: "رقم البطاقة",
  chipManager: "المسؤول",
  chipWorkerEmail: "بريد الموظف",
  chipWorkerRole: "الدور",
  wordPro: "محرر Word (متقدم)",
  focus: "كتابة بملء الشاشة",
  exitFocus: "إنهاء ملء الشاشة",
  reset: "إعادة ضبط",
  shareLink: "رابط مشاركة",
  emailWithPdf: "بريد مع PDF",
  exportHtml: "تصدير كصفحة ويب",
  copyEditorLink: "نسخ رابط التحرير",
  cmdPalette: "إجراءات سريعة",
  lockNow: "قفل التحرير",
  offlineSync: "مزامنة الآن",
  contractBanner: "وضع العقد — احفظ ثم انقل إلى العقد.",
  signAesNote: "يُحفظ التوقيع على المستند (توقيع إلكتروني بسيط).",
  signLockLabel: "ثم اقفل المستند (لا مزيد من التعديل)",
  signQesStart: "بدء التوقيع المعتمد",
  signInsert: "إدراج التوقيع",
  emailSmtpHint: "إن لم تصل الرسالة: راجع إعدادات الإرسال في الشركة.",
  emailModalHint: "يُنشأ PDF تلقائياً ويُرفق بالرسالة.",
  publishCompliance: "تعليم كمستند إثبات رسمي",
  ooNeed: "محرر Word المتقدم غير متاح على هذا الخادم. تواصل مع الدعم.",
  workflowTitle: "الموافقة",
  workflowNext: "إرسال للمراجعة",
  workflowApprove: "اعتماد",
  workflowUnlock: "متابعة التحرير",
  unreadDocsTitle: "لم تُقرأ بعد",
  expiringDocsTitle: "تنتهي خلال 14 يوماً",
  undo: "تراجع",
  redo: "إعادة",
  find: "بحث",
  replace: "استبدال",
  duplicate: "نسخ",
  saveAsTemplate: "حفظ كقالب",
  importDocx: "استيراد Word…",
  insertToc: "جدول المحتويات",
  exportDocx: "تصدير Word",
  returnContract: "العودة إلى العقد",
  ribbon: "شريط التنسيق",
  shortcuts: "اختصارات لوحة المفاتيح",
  tbEdit: "تحرير",
  style: "نمط",
  spellLang: "التدقيق الإملائي",
  preflightTitle: "تحقق قبل الإرسال",
  preflightContinue: "المتابعة على أي حال",
  commentsPanel: "التعليقات",
  outline: "المخطط",
  watermark: "علامة مائية",
  wmNone: "بدون",
  wmDraft: "مسودة",
  wmConfidential: "سري",
  wmCopy: "نسخة",
  status: "الحالة",
  railLabel: "إنهاء وإرسال",
  publish: "إرسال للموظف",
  pdf: "إنشاء PDF",
  print: "طباعة",
  email: "بريد",
  save: "حفظ",
  delete: "حذف",
  close: "إغلاق",
  back: "التشغيل",
  newDoc: "جديد",
  tabTemplates: "قوالب",
  tabDocs: "مستندات",
  findPrev: "السابق",
  findNext: "التالي",
  fmtBold: "غامق",
  fmtItalic: "مائل",
  fmtUnderline: "تسطير",
  fmtStrike: "يتوسطه خط",
  fmtLink: "رابط",
  fmtQuote: "اقتباس",
  fmtComment: "تعليق",
  alignLeft: "يسار",
  alignCenter: "توسيط",
  alignRight: "يمين",
  docTypeOther: "أخرى",
  docTypeMinWage: "إثبات الحد الأدنى للأجور",
  docTypeWorkPermit: "تصريح عمل",
  docTypeResidence: "تصريح إقامة",
  docTypeHealth: "شهادة صحية",
  docTypeRegistration: "شهادة تسجيل",
  tableAddRow: "صف +",
  tableDelRow: "صف −",
  tableAddCol: "عمود +",
  tableDelCol: "عمود −",
  collabConflictText: "تم حفظ المستند من مستخدم آخر.",
  collabReload: "إعادة التحميل",
  collabKeep: "متابعة التحرير",
  liveFollow: "متابعة المتعاونين",
  findPh: "ابحث في المستند…",
  replaceWith: "استبدال بـ",
  replacePh: "نص الاستبدال…",
  replaceAll: "استبدال الكل",
  emptyTitle: "مستند جديد",
  emptyHint: "اختر قالباً أو ابدأ فارغاً.",
  emptyBlank: "مستند فارغ",
  emptyPickTpl: "اختر قالباً",
  outlineEmpty: "لا عناوين بعد",
  versionPreviewTitle: "معاينة الإصدار",
  versionTabPreview: "معاينة",
  versionTabDiff: "التغييرات",
  diffUnified: "عرض موحّد",
  diffOnlyChanges: "التغييرات فقط",
  printAsPdf: "كملف PDF",
  printClean: "طباعة نظيفة",
  cmdPh: "ابحث عن إجراء…",
  cmdHint: "اكتب ثم Enter",
  slashMenu: "إدراج كتل",
  reviewModeBanner: "وضع المراجعة — النص مقفل؛ اقبل الاقتراحات أو ارفضها.",
  suggestionsTitle: "الاقتراحات",
  addSuggestion: "اقتراح",
  addReviewComment: "تعليق",
  commentsOpen: "مفتوح",
  commentsDone: "منجز",
  commentsAll: "الكل",
  commentsEmpty: "لا تعليقات بعد",
  shareModalTitle: "رابط مشاركة",
  emailModalTitle: "إرسال المستند بالبريد",
  signDrawHint: "وقّع بالماوس أو بالإصبع.",
  selBubble: "تنسيق سريع",
  imgSizeBar: "ضبط الصورة",
  imgSize: "حجم الصورة",
  imgFull: "العرض الكامل",
  spellOff: "إيقاف",
  offlineDiscard: "تجاهل",
  offlineRestore: "استعادة",
  offlineReloadServer: "تحميل من الخادم",
  brandLogoReadonly: "يمكن للمشرف فقط تغيير الشعار.",
  workflowHintDraft: "ما زال مسودة — أرسل للمراجعة ثم اعتمد.",
  publishArchiveHint: "بعد الاعتماد يُحفظ PDF في أرشيف الموظف.",
  fpPageOnly: "الصفحة X / Y فقط",
  aiFromExpiry: "نص بسبب تاريخ الانتهاء",
  aiFromAttendance: "نص بسبب التأخير",
  aiGroundedImprove: "تحسين ببيانات الشركة",
  aiDraftWarning: "مسودة ذكاء اصطناعي — راجعها وعدّلها.",
  translateUi: "ترجمة الواجهة",
  signAuditTitle: "سجل التوقيعات",
  ooSync: "اعتماد التغييرات من Word",
  worker: "موظف",
  recipient: "المستلم",
};

const runtimeDe = JSON.parse(fs.readFileSync(path.join(root, "i18n-reports", "runtime-de.json"), "utf8"));
const runtimeEn = JSON.parse(fs.readFileSync(path.join(root, "i18n-reports", "runtime-en.json"), "utf8"));
const runtimeAr = JSON.parse(fs.readFileSync(path.join(root, "i18n-reports", "runtime-ar.json"), "utf8"));

function baseDe(key) {
  if (dePlain[key]) return dePlain[key];
  if (runtimeDe[key]) return runtimeDe[key];
  if (packs.de?.[key]) return packs.de[key];
  if (htmlMap[key]) return htmlMap[key];
  if (dtFallback[key]) return dtFallback[key];
  return humanize(key);
}

/** Lightweight EN from DE-ish / existing */
function baseEn(key, de) {
  if (enPlain[key]) return enPlain[key];
  if (runtimeEn[key]) return runtimeEn[key];
  if (packs.en?.[key]) return packs.en[key];
  if (!htmlMap[key] && !packs.de?.[key] && !runtimeDe[key]) return humanize(key);
  let t = de;
  const map = [
    [/Speichern/g, "Save"],
    [/Löschen/g, "Delete"],
    [/Schließen/g, "Close"],
    [/Drucken/g, "Print"],
    [/Senden/g, "Send"],
    [/Mitarbeiter/g, "Employee"],
    [/Dokument/g, "Document"],
    [/Vorlage/g, "Template"],
    [/Freigabe/g, "Approval"],
    [/Entwurf/g, "Draft"],
    [/Prüfung/g, "Review"],
    [/Firma/g, "Company"],
    [/Adresse/g, "Address"],
    [/Datum/g, "Date"],
    [/Unterschrift/g, "Signature"],
    [/Kopfzeile/g, "Header"],
    [/Fußzeile/g, "Footer"],
    [/Suchen/g, "Find"],
    [/Ersetzen/g, "Replace"],
    [/Kommentar/g, "Comment"],
    [/Version/g, "Version"],
    [/optional/g, "optional"],
  ];
  for (const [re, to] of map) t = t.replace(re, to);
  return t;
}

function baseAr(key, de, en) {
  if (arPlain[key]) return arPlain[key];
  if (runtimeAr[key]) return runtimeAr[key];
  if (packs.ar?.[key]) return packs.ar[key];
  return en;
}

const missing = report.missingFromAllPacks || [];
const deOnly = report.deOnlyKeys || [];
const usedKeys = [];
try {
  const htmlKeys = [...html.matchAll(/data-di18n="([^"]+)"/g)].map((m) => m[1]);
  const dtKeys = [...app.matchAll(/\bdt\(\s*["']([^"']+)["']/g)].map((m) => m[1]);
  usedKeys.push(...htmlKeys, ...dtKeys);
} catch {
  /* ignore */
}
const allNeeded = [
  ...new Set([
    ...missing,
    ...deOnly,
    ...usedKeys,
    ...Object.keys(dePlain),
    ...Object.keys(enPlain),
    ...Object.keys(arPlain),
    ...Object.keys(runtimeDe),
    ...Object.keys(runtimeEn),
    ...Object.keys(runtimeAr),
  ]),
];

const extra = { de: {}, en: {}, ar: {}, tr: {}, fr: {}, es: {}, it: {}, pl: {} };

for (const key of allNeeded) {
  const de = baseDe(key);
  const en = baseEn(key, de);
  const ar = baseAr(key, de, en);
  extra.de[key] = de;
  extra.en[key] = en;
  extra.ar[key] = ar;
  // UI chrome for other langs: start from EN (Phase 1 complete coverage; improve later)
  for (const lang of ["tr", "fr", "es", "it", "pl"]) {
    extra[lang][key] = packs[lang]?.[key] || en;
  }
}

// Also rewrite existing jargon keys in all packs via plain maps
for (const [key, val] of Object.entries(dePlain)) {
  extra.de[key] = val;
}
for (const [key, val] of Object.entries(enPlain)) {
  extra.en[key] = val;
}
for (const [key, val] of Object.entries(arPlain)) {
  extra.ar[key] = val;
  for (const lang of ["tr", "fr", "es", "it", "pl"]) {
    if (enPlain[key]) extra[lang][key] = enPlain[key];
  }
}

const outJs = `/** Auto-generated extras — plain-language + missing UI keys. Rebuild: node admin-v2/build-docs-i18n-extra.mjs
 * Merge policy: start from base docs-i18n.js; EXTRA fills missing keys.
 * Plain-language overrides apply only within their own language (dePlain→de, enPlain→en, arPlain→ar).
 */
(function () {
  const EXTRA = ${JSON.stringify(extra, null, 2)};
  const OVERRIDE_BY_LANG = ${JSON.stringify({
    de: Object.keys(dePlain),
    en: Object.keys(enPlain),
    ar: Object.keys(arPlain),
  })};
  const packs = window.DocsPageI18n || (window.DocsPageI18n = {});
  for (const lang of Object.keys(EXTRA)) {
    const next = Object.assign({}, packs[lang] || {});
    const overrideSet = new Set(OVERRIDE_BY_LANG[lang] || []);
    for (const [key, val] of Object.entries(EXTRA[lang] || {})) {
      if (overrideSet.has(key) || !next[key]) next[key] = val;
    }
    packs[lang] = next;
  }
})();
`;

fs.writeFileSync(path.join(root, "docs-i18n-extra.js"), outJs);

// Also patch main pack jargon keys in a small overlay report
const stillHumanized = Object.keys(extra.de).filter((k) => extra.de[k] === humanize(k));
fs.writeFileSync(path.join(root, "i18n-reports", "extra-key-count.json"), JSON.stringify({
  keys: Object.keys(extra.de).length,
  missingFilled: missing.length,
  stillHumanized: stillHumanized.length,
  stillHumanizedSample: stillHumanized.slice(0, 40),
}, null, 2));
console.log("wrote docs-i18n-extra.js keys=", Object.keys(extra.de).length, "humanizedLeft=", stillHumanized.length);
