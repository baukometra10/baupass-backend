// ALLE ELEMENTE OBEN DEFINIEREN!
const DEFAULT_RENDER_API_BASE = "https://baupass-backend.onrender.com";
const API_BASE_STORAGE_KEY = "baupass-api-base";

function normalizeApiBase(value) {
  return String(value || "").trim().replace(/\/+$/, "");
}

function sanitizeApiBase(value) {
  const normalized = normalizeApiBase(value);
  if (!normalized) {
    return "";
  }

  let parsed;
  try {
    parsed = new URL(normalized);
  } catch {
    return "";
  }

  // GitHub Pages laeuft ueber HTTPS; blockiere dort unsichere HTTP-Backends.
  if (window.location.protocol === "https:" && parsed.protocol === "http:") {
    const host = (parsed.hostname || "").toLowerCase();
    const localHosts = new Set(["localhost", "127.0.0.1", "::1"]);
    if (!localHosts.has(host)) {
      return "";
    }
  }

  return parsed.toString().replace(/\/+$/, "");
}

function resolveApiBase() {
  const params = new URL(window.location.href).searchParams;
  const queryValue = sanitizeApiBase(params.get("apiBase"));
  const storedValue = sanitizeApiBase(window.localStorage.getItem(API_BASE_STORAGE_KEY));
  const metaValue = sanitizeApiBase(document.querySelector('meta[name="baupass-api-base"]')?.content);
  const configuredValue = queryValue || metaValue || storedValue;

  if (configuredValue) {
    window.localStorage.setItem(API_BASE_STORAGE_KEY, configuredValue);
    return configuredValue;
  }

  // Entfernt veraltete/ungueltige API-Konfigurationen, damit der sichere Default greift.
  if (!configuredValue && window.localStorage.getItem(API_BASE_STORAGE_KEY)) {
    window.localStorage.removeItem(API_BASE_STORAGE_KEY);
  }

  if (window.location.hostname.endsWith("github.io")) {
    return DEFAULT_RENDER_API_BASE;
  }

  return "";
}

const API_BASE = resolveApiBase();
const SESSION_TOKEN_STORAGE_KEY = "baupass-control-token";
const SUPPORT_LOGIN_CONTEXT_KEY = "baupass-support-login-context";
const SUPPORT_PHONE_STORAGE_KEY = "baupass-support-phone";
const UI_LANG_STORAGE_KEY = "baupass-ui-lang";
const UI_FALLBACK_LANG = "de";

function loadStoredSessionToken() {
  try {
    const stored = (window.localStorage.getItem(SESSION_TOKEN_STORAGE_KEY) || "").trim();
    console.log("[Token] Loaded from storage:", stored ? `${stored.slice(0, 20)}...` : "NONE");
    return stored;
  } catch (err) {
    console.warn("[Token] Failed to load from storage:", err);
    return "";
  }
}

function persistSessionToken(value) {
  try {
    const next = String(value || "").trim();
    if (next) {
      window.localStorage.setItem(SESSION_TOKEN_STORAGE_KEY, next);
    } else {
      window.localStorage.removeItem(SESSION_TOKEN_STORAGE_KEY);
    }
  } catch {
    // ignore storage failures (private mode / quota)
  }
}

function loadSupportLoginContext() {
  try {
    const url = new URL(window.location.href);
    const companyId = String(url.searchParams.get("supportCompanyId") || "").trim();
    if (companyId) {
      return {
        companyId,
        companyName: String(url.searchParams.get("supportCompanyName") || "").trim(),
        actorName: String(url.searchParams.get("supportActorName") || "").trim(),
      };
    }
  } catch {
    // ignore URL parsing failures
  }
  try {
    const raw = window.sessionStorage.getItem(SUPPORT_LOGIN_CONTEXT_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    if (!parsed || !parsed.companyId) {
      return null;
    }
    return {
      companyId: String(parsed.companyId || "").trim(),
      companyName: String(parsed.companyName || "").trim(),
      actorName: String(parsed.actorName || "").trim(),
    };
  } catch {
    return null;
  }
}

function persistSupportLoginContext(context) {
  try {
    if (!context?.companyId) {
      window.sessionStorage.removeItem(SUPPORT_LOGIN_CONTEXT_KEY);
      return;
    }
    window.sessionStorage.setItem(SUPPORT_LOGIN_CONTEXT_KEY, JSON.stringify({
      companyId: String(context.companyId || "").trim(),
      companyName: String(context.companyName || "").trim(),
      actorName: String(context.actorName || "").trim(),
    }));
  } catch {
    // ignore storage failures
  }
}

function clearSupportLoginContext() {
  try {
    window.sessionStorage.removeItem(SUPPORT_LOGIN_CONTEXT_KEY);
  } catch {
    // ignore storage failures
  }
}
const UI_TRANSLATIONS = {
  de: {
    authEyebrow: "Melde-Seite",
    authTitle: "Sicher in BauPass Control anmelden",
    authCopy: "Super-Admin behält die Systemhoheit. Firmen-Admins sehen nur ihre Firma. Der Drehkreuz-Login bekommt einen schnellen Zutrittsmodus.",
    authPlatform: "Plattform",
    authOperator: "Betreiber",
    authTurnstile: "Drehkreuz-Endpunkt",
    loginUsernameLabel: "Benutzername",
    loginUsernamePlaceholder: "Benutzername",
    loginPasswordLabel: "Passwort",
    loginPasswordPlaceholder: "Passwort eingeben",
    loginOtpLabel: "OTP-Code (wenn 2FA aktiv)",
    loginOtpPlaceholder: "123456",
    uiLanguageLabel: "Sprache",
    loginScopeLabel: "Zugangstyp",
    loginScopeAuto: "Automatisch",
    loginScopeServerAdmin: "Server-Admin",
    loginScopeCompanyAdmin: "Firmen-Admin",
    loginScopeTurnstile: "Drehkreuz",
    supportReadOnlyAlert: "Dieser Support-Login ist nur lesend. Aenderungen sind in dieser Sitzung gesperrt.",
    supportReadOnlyTitle: "Support-Modus: nur lesen",
    supportLoginActive: "Support-Login aktiv:",
    supportCompanyFallback: "Firma",
    supportStartedBy: "gestartet von",
    supportReadOnlyNotice: "Nach der Anmeldung ist der Zugriff nur lesend.",
    supportModeLabel: "Support-Modus:",
    supportReadOnlyFor: "Nur lesen fuer",
    supportCompanyLoginConfirmPrefix: "Zum Firmen-Login fuer",
    supportCompanyLoginConfirmSuffix: "wechseln? Deine aktuelle Admin-Sitzung wird abgemeldet. Danach ist der Zugriff nur lesend.",
    supportCompanyLoginOpenedPrefix: "Login fuer",
    supportCompanyLoginOpenedSuffix: "geoeffnet. Bitte jetzt den Firmen-Admin anmelden. Diese Sitzung bleibt nur lesend.",
    supportModeReadOnlyLine: "Support-Modus aktiv: Nur lesen.",
    supportReadOnlyShort: "Support-Modus: nur lesen.",
    loginButton: "Anmelden",
    demoAccessTitle: "Demo-Zugänge",
    demoSuperAdmin: "Super-Admin: superadmin / 1234",
    demoCompanyAdmin: "Firmen-Admin: firma / 1234",
    demoTurnstile: "Drehkreuz: drehkreuz / 1234",
    desktopAppTitle: "Desktop-App",
    desktopInstallHint: "Dieses Portal kann auf dem Computer wie ein Programm installiert werden.",
    desktopInstallButton: "Auf diesem Computer installieren",
    appTitle: "BauPass Control",
    alertInstallUnavailable: "Die Installation ist in diesem Browser gerade nicht direkt verfuegbar. In Chrome oder Edge kannst du im Browser-Menue 'App installieren' waehlen.",
    alertSessionExpired: "Sitzung abgelaufen. Bitte neu anmelden.",
    // Shell
    sidebarEyebrow: "Firmenportal",
    sidebarCopy: "Mitarbeiter erfassen, Fotos aufnehmen, digitale Ausweise erzeugen und Zutritte am Drehkreuz steuern.",
    sidebarCardTitle: "Vermietungsmodus",
    sidebarCardStrong: "Multi-Firma f\u00e4hig",
    sidebarCardDesc: "Jede Baufirma verwaltet ihr Team getrennt. Super-Admin beh\u00e4lt Systemkontrolle.",
    navDashboard: "Dashboard",
    navWorkers: "Mitarbeiter",
    navBadge: "Ausweis",
    navAccess: "Zutritt",
    navInvoices: "Rechnungen",
    navAdmin: "Admin",
    topbarEyebrow: "Systemstatus",
    topbarHeading: "Baustellen-Ausweise und Zutritt",
    btnSeedData: "Demo-Daten einspielen",
    btnExport: "System exportieren",
    btnImport: "System importieren",
    btnLogout: "Sicher abmelden",
    dashEyebrow: "Verbesserter MVP",
    dashHeading: "Digitale Ausweise mit Foto, Badge-ID und Check-in am Drehkreuz",
    dashSubtext: "Der Prototyp ist bereits f\u00fcr Vermietung an Baufirmen gedacht: Firmenverwaltung, Mitarbeiter-Stammdaten, lokale Zutrittslogs, Export und Systemkonfiguration.",
    dashBadge1: "Fotoaufnahme",
    dashBadge2: "Zutrittslog",
    dashBadge3: "Mandantenf\u00e4hig",
    reportingEyebrow: "Reporting",
    reportingH3: "Zahlung und Sperrstatus",
    reportingPaid: "Bezahlt",
    reportingOpen: "Offen",
    reportingOverdue: "Ueberfaellig",
    reportingInvoicesLabel: "Rechnungen",
    reportingOverdueTotal: "Ueberfaellige Summe",
    reportingLockedCompanies: "Gesperrte Firmen",
    reportingAutoSuspensions30d: "Auto-Sperren (30d)",
    reportingGeneratedAt: "Stand",
    reportingNoOverdueCompanies: "Keine ueberfaelligen Firmen vorhanden.",
    reportingFallbackCompany: "Firma",
    reportingOverdueInvoicesLabel: "ueberfaellige Rechnungen",
    reportingNoAccessDataLast7Days: "Keine Zutrittsdaten fuer die letzten 7 Tage.",
    reportingCheckin: "Check-in",
    reportingCheckout: "Check-out",
    navDocuments: "Dokumente",
    docInboxEyebrow: "Posteingang",
    docInboxH3: "Eingehende Dokumente per Mail",
    btnDocInboxRefresh: "Aktualisieren",
    btnDocInboxSync: "System-Eingang abrufen",
    btnDocInboxPoll: "Postfach jetzt abrufen",
    docEmailInfoLabel: "Dokument-E-Mail (Mitarbeiter schicken Nachweise hierhin):",
    btnCopyEmail: "Kopieren",
    btnCopyEmailDone: "Kopiert!",
    docInboxHint: "Mitarbeiter schicken ihre Nachweise an die konfigurierte Dokuments-E-Mail. Der Pf\u00f6rtner ordnet die Anh\u00e4nge hier einem Mitarbeiter zu.",
    docAssignEyebrow: "Zuweisen",
    docAssignH3: "Anhang einem Mitarbeiter zuordnen",
    docInboxEmpty: "Kein unverarbeiteter Posteingang.",
    docInboxEmailFrom: "Von",
    docInboxEmailSubject: "Betreff",
    docInboxEmailDate: "Datum",
    docInboxAttachments: "Anh\u00e4nge",
    btnAssignDoc: "Zuweisen",
    btnDismissEmail: "Verwerfen",
    docAssignWorkerLabel: "Mitarbeiter w\u00e4hlen",
    docAssignTypeLabel: "Dokumenttyp",
    docAssignNotesLabel: "Anmerkungen (optional)",
    btnConfirmAssign: "Dokument zuweisen",
    docAssignSuccess: "Dokument erfolgreich zugewiesen.",
    docTypeMindestlohnnachweis: "Mindestlohnnachweis",
    docTypePersonalausweis: "Personalausweis / Reisepass",
    docTypeSozialversicherungsnachweis: "Sozialversicherungsnachweis",
    docTypeArbeitserlaubnis: "Arbeitserlaubnis",
    docTypeGesundheitszeugnis: "Gesundheitszeugnis",
    docTypeSonstiges: "Sonstiges",
    workerDocsHeading: "Gespeicherte Dokumente",
    workerDocsEmpty: "Keine Dokumente hinterlegt.",
    workerAkteLabel: "Mitarbeiter-Akte",
    btnUploadWorkerDoc: "Dokument hochladen",
    btnConfirmUpload: "Hochladen",
    docUploadSuccess: "Dokument erfolgreich hochgeladen.",
    confirmDeleteDoc: "Dokument wirklich l\u00f6schen?",
    btnDownloadDoc: "Download",
    btnDeleteDoc: "L\u00f6schen",
    imapSectionEyebrow: "Dokument-Eingang",
    imapSectionH4: "IMAP-Postfach f\u00fcr Nachweise",
    labelImapHint: "Mitarbeiter schicken Nachweise an diese Adresse. Das System ruft das Postfach alle paar Minuten ab.",
    labelImapHost: "IMAP Host",
    labelImapPort: "IMAP Port",
    labelImapUser: "IMAP Benutzername",
    labelImapPass: "IMAP Passwort",
    labelImapFolder: "IMAP Ordner",
    labelImapSsl: "SSL/TLS",
    btnImapTest: "IMAP-Verbindung testen",
    imapTestOk: "Verbindung erfolgreich!",
    imapTestFail: "Verbindung fehlgeschlagen",
    accessWeekEyebrow: "7 Tage",
    accessWeekH3: "Zutritte pro Tag",
    recentEyebrow: "Letzte Aktivit\u00e4ten",
    recentH3: "Zutrittsprotokoll",
    porterLiveEmpty: "Letzter Zutritt wird angezeigt, sobald eine An- oder Abmeldung vorliegt.",
    workersFormEyebrow: "Stammdaten",
    workersFormH3: "Mitarbeiter oder Besucher erfassen",
    labelType: "Typ",
    optWorker: "Mitarbeiter",
    optVisitor: "Besucher",
    labelFirm: "Firma",
    labelSubcompany: "Subunternehmen",
    optNoSubcompany: "Kein Subunternehmen",
    labelNewSubcompany: "Neues Subunternehmen",
    btnAddSubcompany: "Subunternehmen anlegen",
    labelFirstName: "Vorname",
    labelLastName: "Nachname",
    labelInsuranceNumber: "Rentenversicherungsnummer",
    labelRoleField: "Funktion",
    labelSite: "Baustelle",
    siteFieldHint: "Vollständige Adresse eingeben – wird für GPS-Prüfung beim Login benötigt",
    labelPhysicalCard: "Physische Karten-ID (NFC/RFID)",
    labelValidUntil: "G\u00fcltig bis",
    labelVisitorCompany: "Besucherfirma",
    labelVisitPurpose: "Besuchszweck",
    labelHostName: "Ansprechpartner vor Ort",
    labelVisitEndAt: "Besuchsende",
    visitorHint: "Besucher sind f\u00fcr ein paar Stunden oder bis Tagesende g\u00fcltig. Offene Zutritte werden sp\u00e4testens um 00:00 automatisch abgemeldet, die Karte bleibt aber f\u00fcr Auswertungen erhalten.",
    labelWorkerStatus: "Status",
    optStatusActive: "Aktiv",
    optStatusLocked: "Gesperrt",
    optStatusExpired: "Abgelaufen",
    labelBadgePin: "Badge-PIN f\u00fcr App-Login",
    btnStartCamera: "Kamera starten",
    btnCapturePhoto: "Foto aufnehmen",
    btnUploadPhoto: "Foto hochladen",
    btnPhotoUp: "\u2191 Hoch",
    btnPhotoLeft: "\u2190 Links",
    btnPhotoRight: "Rechts \u2192",
    btnPhotoDown: "Runter \u2193",
    btnPhotoReset: "Position zur\u00fccksetzen",
    btnWorkerSubmit: "Mitarbeiter speichern und Ausweis erzeugen",
    btnWorkerCancelEdit: "Bearbeiten abbrechen",
    workersListEyebrow: "Datenbestand",
    workersListH3: "Registrierte Mitarbeiter",
    btnWorkerCsv: "Mitarbeiterliste als PDF herunterladen",
    btnBulkDelete: "Ausgew\u00e4hlte l\u00f6schen",
    btnBulkActive: "Status: aktiv",
    btnBulkInactive: "Status: inaktiv",
    btnBulkCancel: "Abbrechen",
    badgeEyebrow: "Digitaler Ausweis",
    badgeH3: "Badge-Vorschau",
    badgeEmptyState: "Bitte zuerst einen Mitarbeiter anlegen oder aus der Liste ausw\u00e4hlen.",
    badgeScanEyebrow: "Scan-Hilfe",
    badgeScanH3: "Badge-Code",
    badgeScanEmpty: "Kein Badge ausgew\u00e4hlt.",
    badgeTitleVisitor: "Digitale Besucherkarte",
    badgeTitleDayPass: "Digitaler Baustellen-Tagesausweis",
    badgeTitleRegular: "Digitaler Baustellen-Ausweis",
    badgeUnknownCompany: "Unbekannte Firma",
    badgeQrHint: "QR scannen, App installieren und Ausweis direkt oeffnen.",
    badgeLabelBadgeId: "Badge-ID",
    badgeMetaQrFunc: "QR-Funktion",
    badgeMetaQrFuncVal: "Mitarbeiter-App Installation",
    badgeMetaRoleLabel: "Rolle im System",
    badgePhotoUploadHint: "Foto aufnehmen oder hochladen",
    appPinLabel: "App-PIN",
    pinNotRequired: "nicht noetig",
    pinSet: "gesetzt",
    pinMissing: "fehlt",
    cardLabel: "Karte",
    cardUnassigned: "nicht zugewiesen",
    btnEdit: "Bearbeiten",
    btnDelete: "Loeschen",
    btnRestore: "Wiederherstellen",
    btnAppLink: "App-Link",
    btnResetPin: "PIN zuruecksetzen",
    confirmDeleteWorker: "Mitarbeiter wirklich loeschen?",
    alertDeleteWorkerFailed: "Mitarbeiter konnte nicht geloescht werden: {error}",
    alertRestoreWorkerFailed: "Mitarbeiter konnte nicht wiederhergestellt werden: {error}",
    alertAppLinkCreateFailed: "App-Link konnte nicht erzeugt werden: {error}",
    promptResetPinFor: "Neue Badge-PIN fuer {name} (4-8 Ziffern):",
    alertPinMustDigits: "PIN muss aus 4 bis 8 Ziffern bestehen.",
    alertPinResetSuccessFor: "PIN fuer {name} wurde erfolgreich zurueckgesetzt.",
    alertPinResetFailed: "PIN konnte nicht zurueckgesetzt werden: {error}",
    alertPhotoOverrideApproved: "Foto-Override freigegeben. Mitarbeiterdaten wurden gespeichert.",
    alertPhotoOverrideApproveFailed: "Freigabe fehlgeschlagen: {error}",
    alertPhotoOverrideRejectReasonRequired: "Ablehnungsgrund ist erforderlich.",
    alertPhotoOverrideRejected: "Foto-Override abgelehnt.",
    alertPhotoOverrideRejectFailed: "Ablehnung fehlgeschlagen: {error}",
    alertDocEmailSaveFailed: "Dokument-E-Mail konnte nicht gespeichert werden: {error}",
    alertCompanyDeleted: "Firma {name} wurde geloescht.",
    alertCompanyDeleteFailed: "Firma {name} konnte nicht geloescht werden: {error}",
    alertCompanyLocked: "Firma {name} wurde gesperrt.",
    alertCompanyUnlocked: "Sperre fuer {name} wurde aufgehoben.",
    alertCompanyStatusChangeFailed: "Statuswechsel fuer {name} fehlgeschlagen: {error}",
    alertBrandingPresetSaveFailed: "Design-Preset konnte nicht gespeichert werden: {error}",
    alertPasswordMinLength: "Passwort muss mindestens 4 Zeichen haben.",
    alertTurnstileCreateFailed: "Drehkreuz konnte nicht angelegt werden: {error}",
    alertTurnstilePasswordUpdated: "Drehkreuz-Passwort wurde aktualisiert.",
    alertTurnstilePasswordResetFailed: "Passwort-Reset fehlgeschlagen: {error}",
    alertApiKeyRotationFailed: "API-Key-Rotation fehlgeschlagen: {error}",
    alertTurnstileToggleFailed: "Drehkreuz konnte nicht umgeschaltet werden: {error}",
    alertWorkerDeletedCannotEdit: "Geloeschte Mitarbeiter koennen nicht bearbeitet werden.",
    alertDataCopied: "Daten kopiert.",
    alertPrintWindowFailed: "Druckfenster konnte nicht geoeffnet werden.",
    alertAppLinkCopied: "App-Link kopiert.",
    alertQrNotReadyYet: "QR-Code wird noch erzeugt. Bitte kurz erneut versuchen.",
    alertAccessBookingFailed: "Zutritt konnte nicht gebucht werden: {error}",
    alertWorkerSaveFailed: "Mitarbeiter konnte nicht gespeichert werden: {error}",
    alertPhotoMatchFailed: "Fotovergleich fehlgeschlagen ({score}%). Speichern ist gesperrt. Bitte erneut fotografieren oder Superadmin kontaktieren.",
    alertOverrideReasonTooShort: "Override-Grund zu kurz. Bitte mindestens 8 Zeichen eingeben.",
    alertPhotoOverrideRequested: "Foto-Override beantragt (Freigabe-ID: {id}).\nEin zweiter Superadmin muss die Aenderung freigeben, bevor sie gespeichert wird.",
    alertBadgePinInvalid: "Badge-PIN muss aus 4 bis 8 Ziffern bestehen.",
    alertDuplicatePhysicalCardId: "Diese physische Karten-ID ist bereits einem anderen Mitarbeiter zugeordnet.",
    alertPhotoOverrideSuperadminOnly: "Foto-Override ist nur fuer Superadmin erlaubt.",
    alertPhotoOverrideReasonRequired: "Bitte einen ausreichenden Grund fuer den Foto-Override angeben.",
    alertInvoiceSavedSendFailed: "Rechnung gespeichert, Versand fehlgeschlagen: {error}",
    alertInvoiceNumberDuplicate: "Rechnungsnummer {number} ist bereits vergeben. Bitte eine andere Nummer verwenden.",
    alertInvoiceSendFailed: "Rechnung konnte nicht versendet werden: {error}",
    alertInvoiceNumberLength: "Rechnungsnummer muss zwischen 3 und 64 Zeichen haben.",
    alertInvoiceDateInvalid: "Rechnungsdatum oder Faelligkeitsdatum ist ungueltig.",
    alertInvoiceDueDateBeforeIssue: "Faelligkeitsdatum darf nicht vor dem Rechnungsdatum liegen.",
    alertInvoiceVatRange: "MwSt. muss zwischen 0 und 100 liegen.",
    alertApprovalRejectReasonRequired: "Ablehnung ohne Begruendung ist nicht erlaubt.",
    alertApprovalConfirmed: "Freigabe bestaetigt und Aktion ausgefuehrt.",
    alertApprovalRejected: "Freigabe wurde abgelehnt.",
    alertApprovalUpdated: "Freigabe aktualisiert.",
    alertApprovalActionFailed: "Freigabe-Aktion fehlgeschlagen: {error}",
    alertInvoiceRetrySentDeadLetter: "Rechnung wurde erfolgreich erneut versendet und aus Dead-Letter entfernt.",
    alertInvoiceRetrySent: "Rechnung wurde erfolgreich erneut versendet.",
    alertInvoiceRetryFailed: "Erneuter Versand fehlgeschlagen: {error}",
    alertDeadLetterResolveApprovalRequested: "Freigabe angefordert ({id}). Ein zweiter Superadmin muss bestaetigen.",
    alertDeadLetterResolveFailed: "Dead-Letter-Fall konnte nicht erledigt werden: {error}",
    alertGenericError: "Fehler: {error}",
    alertCollectionsStatusChangeFailed: "Statuswechsel fehlgeschlagen: {error}",
    alertActionFailed: "Aktion fehlgeschlagen: {error}",
    alertInvoiceHistoryLoadFailed: "Historie konnte nicht geladen werden: {error}",
    alertAccessExportFailed: "Zutrittsjournal-Export fehlgeschlagen: {error}",
    alertWorkerExportFailed: "Mitarbeiterlisten-Export fehlgeschlagen: {error}",
    alertSettingsSaveFailed: "Einstellungen konnten nicht gespeichert werden: {error}",
    alertSystemRepairDone: "System-Reparatur wurde ausgefuehrt.",
    alertSystemRepairFailed: "System-Reparatur fehlgeschlagen: {error}",
    alertBrandingLoaded: "BauKometra Branding geladen. Jetzt nur noch auf Admin-Einstellungen speichern klicken.",
    alertBrandingLoadFailed: "Branding konnte nicht geladen werden: {error}",
    alertBrandingAltLoaded: "Alternative BauKometra Branding-Variante geladen. Jetzt nur noch auf Admin-Einstellungen speichern klicken.",
    alertBrandingAltLoadFailed: "Alternative Branding-Variante konnte nicht geladen werden: {error}",
    alertDayCloseAckFailed: "Tagesabschluss konnte nicht quittiert werden: {error}",
    alertOtpRequired: "Fuer dieses Konto ist 2FA aktiv. Bitte OTP-Code eingeben.",
    alertOtpInvalid: "OTP-Code ist ungueltig oder abgelaufen. Bitte neuen Code eingeben.",
    alertTooManyAttempts: "Zu viele Fehlversuche. Bitte 10 Minuten warten und erneut versuchen.",
    loginSecurityTitle: "Sicherheitswarnung",
    loginSecurityHint: "Es wurden 3 fehlgeschlagene Login-Versuche erkannt.",
    loginSecurityCallPrefix: "Bitte Admin sofort anrufen unter:",
    loginSecurityFooter: "Nach Ruecksprache kann das Passwort zurueckgesetzt werden.",
    alertForbiddenTenantHost: "Dieser Zugang ist nur ueber die freigegebene Firmen-Domain erlaubt.",
    alertSupportCompanyMismatch: "Dieser Login passt nicht zur ausgewaehlten Firma. Bitte den Firmen-Admin der markierten Firma verwenden.",
    alertLoginCompanyLocked: "Diese Firma ist gesperrt. Bitte zuerst offene Rechnungen begleichen oder die Sperre im Superadmin aufheben.",
    alertInvalidCredentials: "Benutzername oder Passwort ist falsch. Bitte Daten pruefen und erneut versuchen.",
    alertAdminIpNotAllowed: "Admin-Zugriff von dieser IP ist nicht erlaubt.",
    alertLoginScopeMismatch: "Zugangstyp passt nicht zum Konto. Bitte Server-Admin/Firmen-Admin korrekt auswaehlen.",
    alertLoginHttp405: "Login fehlgeschlagen: 405. Der Login-Request landet aktuell auf {target}. Fuer GitHub Pages muss das Frontend dein Render-Backend nutzen.",
    alertLoginFailed: "Login fehlgeschlagen: {error}",
    alertPasswordResetEnterUsername: "Bitte zuerst Benutzername oder E-Mail eintragen.",
    alertPasswordResetSent: "Wenn ein passender Account gefunden wurde, wurde eine Reset-E-Mail versendet.",
    alertPasswordResetFailed: "Passwort-Reset konnte nicht gestartet werden: {error}",
    alertPasswordSetSuccess: "Passwort wurde erfolgreich gesetzt. Du kannst dich jetzt anmelden.",
    alertPasswordResetLinkFailed: "Reset-Link konnte nicht verwendet werden: {error}",
    alertPasswordChanged: "Passwort geaendert. Bitte neu anmelden.",
    alertPasswordChangeFailed: "Passwortwechsel fehlgeschlagen: {error}",
    alert2faSetupFailed: "2FA Setup fehlgeschlagen: {error}",
    alert2faEnableFailed: "2FA konnte nicht aktiviert werden: {error}",
    alertDeviceDeleteFailed: "Fehler beim Loeschen: {error}",
    alertCompanyCreateFailed: "Firma konnte nicht angelegt werden: {error}",
    alert2faDisableFailed: "2FA konnte nicht deaktiviert werden: {error}",
    alertExportFailed: "Export fehlgeschlagen: {error}",
    alertNoDemoCompany: "Keine aktive Firma fuer Demo-Daten gefunden.",
    alertDemoModeInvalid: "Ungueltiger Modus. Bitte replace oder append verwenden.",
    alertDemoLoadFailed: "Demo-Daten konnten nicht geladen werden: {error}",
    alertImportSuccess: "Import erfolgreich angewendet.",
    alertImportFailed: "Import fehlgeschlagen: {error}",
    alertCsvExportFailed: "CSV-Export fehlgeschlagen: {error}",
    alertIncidentExportFailed: "Incident-Export fehlgeschlagen: {error}",
    alertSelectInvoiceForRetry: "Bitte mindestens eine Rechnung in der Warteschlange auswaehlen.",
    alertBulkRetryDone: "Bulk-Retry abgeschlossen. Erfolgreich: {sent}, Fehlgeschlagen: {failed}, Uebersprungen: {skipped}",
    alertBulkRetryFailed: "Bulk-Retry fehlgeschlagen: {error}",
    alertNoCriticalCases: "Aktuell gibt es keine kritischen Faelle (Score >= 70).",
    alertCriticalBulkRetryDone: "Kritischer Bulk-Retry abgeschlossen. Erfolgreich: {sent}, Fehlgeschlagen: {failed}, Uebersprungen: {skipped}",
    alertCriticalBulkRetryFailed: "Kritischer Bulk-Retry fehlgeschlagen: {error}",
    alertDesktopInstallFailed: "Desktop-Installation konnte nicht gestartet werden.",
    alertSubcompanyCreateFailed: "Subunternehmen konnte nicht angelegt werden: {error}",
    alertDeleteFailed: "Fehler beim Loeschen: {error}",
    alertStatusChangeFailed: "Fehler beim Status-Aendern: {error}",
    alertReassignmentDone: "Neu-Zuordnung abgeschlossen. Treffer: {count}",
    alertReassignmentFailed: "Neu-Zuordnung fehlgeschlagen: {error}",
    detailCloseTitle: "Schliessen",
    detailPhotoAlt: "Mitarbeiterfoto",
    detailCheckinBtn: "Anmelden (Check-in)",
    detailCheckoutBtn: "Abmelden (Check-out)",
    accessFormEyebrow: "Drehkreuz",
    accessFormH3: "Check-in und Check-out",
    labelAccessBadge: "Badge-ID oder Mitarbeiter",
    labelAccessDir: "Richtung",
    labelAccessGate: "Punkt",
    labelAccessNote: "Notiz",
    optCheckin: "Check-in",
    optCheckout: "Check-out",
    btnAccessSubmit: "Zutritt buchen",
    porterEmpty: "Pf\u00f6rtner-Live-Ansicht: Mitarbeiter w\u00e4hlen und Zutritt buchen.",
    accessLogEyebrow: "Zutrittsjournal",
    accessLogH3: "Eintritt und Austritt mit Zeitstempel",
    labelFrom: "Von",
    labelTo: "Bis",
    labelFilterDir: "Richtung",
    labelFilterGate: "Drehkreuz",
    optAllDir: "Alle",
    btnApplyFilter: "Filter anwenden",
    btnResetFilter: "Filter zur\u00fccksetzen",
    btnAccessCsv: "Zutritts-CSV exportieren",
    dailyReportEyebrow: "Tagesbericht",
    dailyReportH3: "Pro Drehkreuz",
    btnPrintDaily: "Tagesreport drucken",
    btnPrintVisitorWeekly: "Besucher-Wochenliste drucken",
    hourlyEyebrow: "Stundenanalyse",
    hourlyH3: "Eintritt/Austritt je Stunde",
    warningsEyebrow: "Warnungen",
    warningsH3: "Eintritt ohne Austritt",
    invListEyebrow: "Fakturierung",
    invListH3: "Rechnungen und Zahlungsstatus",
    optAllStatus: "Alle Status",
    optDraft: "Entwurf",
    optSent: "Versendet",
    optOverdue: "\u00dcberf\u00e4llig",
    optPaid: "Bezahlt",
    optFailed: "Fehler",
    btnRefreshList: "Aktualisieren",
    inkassoEyebrow: "Inkasso",
    inkassoH3: "\u00dcberf\u00e4llig, vor Sperre, gesperrt",
    optAllPositions: "Alle offenen Positionen",
    optPrelock: "Vor Sperre",
    optLocked: "Bereits gesperrt",
    adminEyebrow: "Admin-Zentrale",
    adminH3: "System & Konfiguration",
    sysStatusEyebrow: "Systemstatus",
    sysStatusH3: "Notfallzugriff & Reparatur",
    btnRefreshStatus: "Status neu laden",
    btnRepairSessions: "Sitzungen reparieren",
    superAdminEyebrow: "Systemhoheit",
    superAdminH3: "Super-Admin Einstellungen",
    labelPlatformName: "Plattformname",
    labelOperatorName: "Betreiber",
    labelTurnstileEp: "Drehkreuz-API Endpoint",
    labelSmtpHost: "SMTP Host",
    labelSmtpPort: "SMTP Port",
    labelSmtpUser: "SMTP Benutzer",
    labelSmtpPass: "SMTP Passwort",
    labelSenderEmail: "Absender E-Mail",
    labelSenderName: "Absender Name",
    labelTls: "TLS aktiv",
    optTlsYes: "Ja",
    optTlsNo: "Nein",
    btnTestSmtp: "Test-Mail senden",
    optYes: "Ja",
    optNo: "Nein",
    labelIpWhitelist: "Admin IP-Whitelist (Komma getrennt, optional CIDR)",
    labelEnforceDomain: "Firmen-Domain erzwingen",
    btnSaveAdmin: "Admin-Einstellungen speichern",
    companyNewEyebrow: "Mandanten",
    companyNewH3: "Neue Baufirma anlegen",
    labelCompanyName: "Firmenname",
    labelCompanyContact: "Ansprechpartner",
    labelBillingEmail: "Rechnungs-E-Mail",
    labelAccessHost: "Firmen-Zugangsdomain",
    labelPlan: "Tarif",
    labelCompanyStatus: "Status",
    optCompanyActive: "Aktiv",
    optCompanyTest: "Testphase",
    optCompanyPaused: "Pausiert",
    optCompanyLocked: "Gesperrt wegen Zahlungsverzug",
    labelCompanyAdminPassword: "Admin-Startpasswort",
    companyAdminPasswordPlaceholder: "z.B. Sicher!2025",
    btnCreateCompany: "Baufirma anlegen",
    accountEyebrow: "Konto",
    accountH3: "Passwort \u00e4ndern",
    labelCurrentPassword: "Aktuelles Passwort",
    labelNewPassword: "Neues Passwort",
    btnChangePassword: "Passwort \u00e4ndern",
    tfaEyebrow: "Zwei-Faktor",
    tfaH3: "2FA Verwaltung",
    companiesListEyebrow: "Mandanten",
    companiesListH3: "Baufirmen und Pl\u00e4ne",
    invFormEyebrow: "Rechnungen",
    invFormH3: "Mit Logo und Design versenden",
    labelInvFirm: "Firma",
    labelInvNumber: "Rechnungsnummer",
    labelInvRecipient: "Empf\u00e4nger E-Mail",
    labelInvDate: "Rechnungsdatum",
    labelInvDueDate: "F\u00e4lligkeitsdatum",
    labelInvPeriod: "Leistungszeitraum",
    labelInvDescription: "Leistungsbeschreibung",
    labelInvNet: "Nettobetrag (EUR)",
    labelInvVat: "MwSt. (%)",
    btnPrintInvoice: "Rechnung drucken / als PDF speichern",
    btnSendInvoice: "Rechnung per E-Mail senden",
    btnUpdatePreview: "Vorschau aktualisieren",
    auditEyebrow: "Sicherheitsprotokoll",
    auditH3: "Audit-Log",
    labelAuditEvent: "Event-Typ",
    labelAuditRole: "Rolle",
    btnAuditCsv: "Audit-CSV exportieren",
    loginForgotPassword: "Passwort vergessen",
    legalImpressum: "Impressum",
    legalPrivacy: "Datenschutz",
    legalCloseTitle: "Schliessen",
    legalFallbackEmpty: "Kein Text hinterlegt.",
    invoiceMgmtTitle: "Rechnungs-Management",
    invoiceMgmtCopy: "Zeige offene und bezahlte Rechnungen an. Markiere Rechnungen als bezahlt um Firmensperrungen automatisch aufzuheben. Alle Aktivitäten werden im Audit-Log protokolliert.",
    invoiceOpsEyebrow: "Operations",
    invoiceOpsH3: "Versand-SLA und Fehlerlage",
    invoiceSendEyebrow: "Versand",
    invoiceSendH3: "Warteschlange fuer fehlgeschlagene Mails",
    optRetryAll: "Alle Fehlversaende",
    optRetryPriority: "Prioritaet zuerst",
    optRetryMaxed: "Max Retries erreicht",
    optRetryTodayFailed: "Heute fehlgeschlagen",
    invoiceRetryTopIssuesOnly: "Nur meine Top-Probleme",
    btnRetryCriticalSend: "Nur kritische jetzt senden",
    btnRetryExportCsv: "Queue CSV",
    btnIncidentExportCsv: "Incident CSV",
    btnRetryBulkSend: "Ausgewaehlte erneut senden",
    invoiceApprovalsEyebrow: "Freigaben",
    invoiceApprovalsH3: "4-Augen-Pruefung fuer kritische Aktionen",
    optApprovalAllActions: "Alle Aktionstypen",
    optApprovalBulkRetry: "Bulk-Retry",
    optApprovalDeadLetterResolve: "Dead-Letter-Resolve",
    legalSectionEyebrow: "Rechtliches",
    legalSectionTitle: "Impressum & Datenschutz",
    labelImpressumText: "Impressum-Text",
    labelPrivacyText: "Datenschutzerklaerung",
    legalTextsHint: "Diese Texte erscheinen auf der Anmeldeseite unter 'Impressum' und 'Datenschutz'.",
    labelCompanyDocumentEmail: "Dokument-E-Mail",
    labelBrandingPreset: "Branding-Preset",
    optBrandingConstruction: "Bau",
    optBrandingIndustry: "Industrie",
    optBrandingPremium: "Premium",
    optPlanStarter: "Starter (49 EUR)",
    optPlanProfessional: "Professional (99 EUR)",
    optPlanEnterprise: "Enterprise (199 EUR)",
    navDevices: "Geräte",
    devicesEyebrow: "Hardware",
    devicesH3: "Smart-Boxen und OSDP-Geräte",
    devicesHint: "Jede Smart-Box sendet alle 30–60 s einen Heartbeat. Kein Signal >90 s = offline.",
    btnAddDevice: "Gerät hinzufügen",
    addDeviceEyebrow: "Neues Gerät",
    addDeviceH3: "Gerät registrieren",
    labelDeviceName: "Name",
    labelDeviceLocation: "Standort",
    labelDeviceType: "Typ / Protokoll",
    btnDeviceRegister: "Gerät registrieren und API-Schlüssel erzeugen",
    deviceOnline: "Online",
    deviceOffline: "Offline",
    deviceNeverSeen: "Noch kein Heartbeat",
    btnPrintBadge: "Ausweis drucken",
    greetingMorning: "Guten Morgen",
    greetingDay: "Guten Tag",
    greetingEvening: "Guten Abend",
    greetingNight: "Gute Nacht",
    greetingSuffix: "Angenehmen Dienst!",
    adminWorkerAppSectionTitle: "Mitarbeiter-App",
    adminWorkerAppSectionCopy: "Steuert die komplette Mitarbeiter-App: Login, digitaler Ausweis und QR-Nutzung auf dem Handy.",
    adminWorkerAppPinLockHint: "Nach 2 Minuten ohne Interaktion muss der Mitarbeiter seine Badge-PIN erneut eingeben, um den Ausweis zu sehen.",
    optPlanDayPassRecommended: "Besucherkarte (empfohlen)",
    optPlanMonthlySite: "Monatlich pro Baustelle",
    optPlanPerWorker: "Pro Mitarbeiter",
    optPlanFlatCompany: "Pauschal pro Firma",
    optPlanDayPassPrice: "Besucherkarte (19 EUR/Tag)",
    btnDocInboxRematch: "Neu zuordnen",
    accessFeedbackCheckin: "Zutritt gebucht",
    badgePinHint: "Badge-Login in der Mitarbeiter-App funktioniert nur noch mit Badge-ID und dieser PIN. Beim Bearbeiten kannst du hier eine neue PIN setzen.",
    badgePinPlaceholder: "4 bis 8 Ziffern",
    bulkSelectAll: "Alle auswählen",
    btnDayCloseAcknowledge: "Tagesabschluss quittieren",
    btnExportCompanyDocEmails: "Dokument-Mails exportieren",
    btnLoadAltBrand: "Alternative laden",
    btnLoadDefaultBrand: "BauKometra Branding laden",
    cameraNotStarted: "Kamera noch nicht gestartet.",
    complianceEyebrow: "Compliance",
    complianceH3: "Dokumentenstatus",
    dayCloseCommentLabel: "Kommentar zur Tagesabschluss-Quittierung",
    dayCloseCommentPlaceholder: "z. B. Schichtleiter informiert, Austritt wird nachgetragen",
    deadLetterEyebrow: "Dead-Letter",
    deadLetterH3: "Manuell zu klärende Rechnungen",
    filterByCompanyPlaceholder: "Nach Firma filtern…",
    filterQueueByCompanyPlaceholder: "Firma in Warteschlange filtern…",
    formSectionAppFeaturesEyebrow: "App-Features",
    formSectionBrandingEyebrow: "Rechnungsdesign",
    formSectionBrandingH4: "Farben & Branding",
    formSectionEmailEyebrow: "E-Mail",
    formSectionPlatformEyebrow: "Plattform",
    formSectionPlatformH4: "Identität & Betreiber",
    formSectionSecurityH4: "Zugang & Isolation",
    formSectionSmtpH4: "SMTP Versand",
    invoiceLogoHint: "Das Rechnungslogo wird auch als System-Icon und Mitarbeiter-App-Icon verwendet.",
    invoicePreviewEyebrow: "Vorschau",
    invoicePreviewH3: "Rechnung vor Versand prüfen",
    maxAgeFilterPlaceholder: "Max Alter in Minuten (0 = alle)",
    optDeviceOsdp: "OSDP (RS-485)",
    optDeviceTcp: "TCP/IP Smart-Box",
    optDeviceWiegand: "Wiegand-Reader",
    optPinLockActive: "Aktiv – PIN-Lock schützt vor Telefon-Weitergabe",
    optPinLockDisabled: "Deaktiviert – Ausweis jederzeit frei zugänglich",
    optRoleCompanyAdmin: "Firmen-Admin",
    optRoleSuperAdmin: "Super-Admin",
    optWorkerAppActive: "Aktiv – Ausweis, QR und Badge-Login sind freigegeben",
    optWorkerAppLocked: "Gesperrt – Mobile-App ist deaktiviert",
    photoAdjustHelp: "Foto nach Aufnahme verschieben, damit es rechts im Ausweis sauber passt.",
    photoOverrideH3: "Ausstehende Foto-Override-Freigaben",
    photoRequiredHint: "Pflicht: Ohne Foto kann der Ausweis nicht gespeichert werden.",
    photoSharpenLabel: "Schärfe:",
    photoWhiteBgLabel: "Hintergrund komplett weiß (aktiv)",
    photoZoomCropLabel: "Zoom / Zuschneiden",
    recentAuditEyebrow: "Audit",
    recentAuditH3: "Letzte Systemereignisse",
    rentalModelLabel: "Vermietungsmodell",
    sectionSecurityEyebrow: "Sicherheit",
    statusLoading: "Status wird geladen…",
    sysAlertActionBtn: "Zu Rechnungen",
    sysAlertDefaultText: "Aktuell liegen kritische Rechnungs-Fehlversände vor.",
    sysAlertHeading: "Kritische Versandlage",
    turnstileCountLabel: "Anzahl Drehkreuze",
    turnstilePasswordLabel: "Drehkreuz-Startpasswort",
    workerAppEnabledLabel: "Mobile-Ausweis-App (digitaler Ausweis + QR)",
    workerPassLockLabel: "Ausweis mit PIN-Sperre sichern (nach 2min Inaktivität)",
    workerSearchPlaceholder: "Suchen: Name, Badge-ID, Baustelle …",
    confirmDeleteCompanyText: "Firma {name} und alle zugeh\u00f6rigen Datens\u00e4tze l\u00f6schen?\n\nOK = komplette L\u00f6schung (inkl. Mitarbeiter, Subunternehmen und Logs)\nAbbrechen = nicht l\u00f6schen",
    confirmLockCompany: "Firma {name} jetzt sperren? Firmen-Admin, Drehkreuz und Mitarbeiter-App dieser Firma werden blockiert.",
    confirmUnlockCompany: "Sperre f\u00fcr {name} jetzt aufheben? Die Firma kann sich danach wieder anmelden.",
    confirmDeleteWorkerBulk: "{count} Mitarbeiter wirklich l\u00f6schen?",
    confirmApiKeyRotate: "API-Key f\u00fcr dieses Drehkreuz jetzt neu erzeugen? Der bisherige Key verliert sofort seine G\u00fcltigkeit.",
    confirmSystemRepair: "System-Reparatur ausf\u00fchren? Abgelaufene Sitzungen und Login-Sperren werden bereinigt.",
    confirmApprovalDecision: "Freigabe {id} wirklich {decision}?",
    confirmDeadLetterRetry: "Dead-Letter-Rechnung jetzt erneut senden?",
    confirmDeadLetterResolve: "Dead-Letter-Fall als erledigt markieren?",
    confirmInvoicePaid: "Diese Rechnung als bezahlt markieren? Firmensperrung wird ggf. aufgehoben.",
    confirmInvoiceRetry: "Rechnung jetzt erneut senden?",
    confirmInvoicePaidSimple: "Rechnung jetzt als bezahlt markieren?",
    confirmDemoInvoices: "Sollen Demo-Rechnungen mit erzeugt werden?",
    confirmDemoAccessLogs: "Sollen Demo-Zutrittslogs erzeugt werden?",
    confirmDemoReplace: "Demo-Daten jetzt f\u00fcr {name} im Modus REPLACE laden? Vorhandene Mitarbeiter, Subunternehmen und Logs werden ersetzt.",
    confirmDemoAppend: "Demo-Daten jetzt f\u00fcr {name} im Modus APPEND zus\u00e4tzlich laden?",
    confirmExportAudit: "Audit-Log im Export einschlie\u00dfen?",
    confirmExportDayClose: "Tagesabschluss-Quittierungen im Export einschlie\u00dfen?",
    confirmExportDeleted: "Gel\u00f6schte Eintr\u00e4ge im Export einschlie\u00dfen?",
    confirmExportAll: "Als Superadmin: Gesamtsystem exportieren? (Nein = nur aktuelle Firma)",
    confirmExportDownload: "System-Export{scope} jetzt herunterladen?",
    confirmLogout: "Wirklich abmelden?",
    confirmImportChangesOnly: "Nur \u00c4nderungen importieren? (Empfohlen)",
    confirmBulkRetrySelected: "{count} ausgew\u00e4hlte Rechnung(en) jetzt erneut senden?",
    confirmBulkRetryCritical: "{count} kritische Rechnung(en) jetzt erneut senden?",
    confirmPhotoMatchFailed: "Fotovergleich fehlgeschlagen ({score}%). Nur Superadmin darf mit Risiko speichern. Trotzdem speichern?",
    promptDocEmail: "Dokument-E-Mail f\u00fcr {name} festlegen",
    promptTurnstilePassword: "Drehkreuz-Passwort f\u00fcr {name} festlegen (min. 4 Zeichen):",
    promptTurnstilePasswordNew: "Neues Drehkreuz-Passwort festlegen (min. 4 Zeichen):",
    promptCopyData: "Daten zum Kopieren:",
    promptAppLink: "App-Link f\u00fcr den Mitarbeiter:",
    promptPhotoOverrideReason: "Bitte Grund f\u00fcr den Foto-Override eingeben (mindestens 8 Zeichen):",
    promptNewPassword: "Neues Passwort eingeben (mindestens 8 Zeichen):",
    promptTfaCode: "Bitte 6-stelligen Code aus deiner Authenticator-App eingeben:",
    promptTfaDisableCode: "Bitte aktuellen 2FA-Code zum Deaktivieren eingeben:",
    promptDemoMode: "Demo-Daten f\u00fcr {name}: Modus eingeben (replace oder append)",
    promptRejectionReason: "Ablehnungsgrund (Pflicht):",
    promptRejectApproval: "Bitte Ablehnungsgrund eingeben:",
    invoiceTitle: "Rechnung",
    invoiceAltLogo: "Firmenlogo",
    invoiceLabelNumber: "Rechnungsnummer:",
    invoiceLabelDate: "Rechnungsdatum:",
    invoiceLabelDue: "F\u00e4lligkeitsdatum:",
    invoiceLabelCustomer: "Kunde:",
    invoiceLabelContact: "Ansprechpartner:",
    invoiceLabelPeriod: "Leistungszeitraum:",
    invoiceColService: "Leistung / Mitarbeiter",
    invoiceColAccess: "Zug\u00e4nge",
    invoiceColNet: "Nettobetrag",
    invoiceRowUnknown: "Unbekannt",
    invoiceRowPlan: "Tarif: {label}",
    invoiceTotalNet: "Zwischensumme netto",
    invoiceTotalVat: "MwSt. ({rate} %)",
    invoiceTotalGross: "Gesamtbetrag",
    invoiceFooter: "Vielen Dank f\u00fcr die Zusammenarbeit. Diese Rechnung wurde digital erstellt und kann direkt versendet werden.",
    invoiceHistoryEmpty: "Noch keine versendeten oder gespeicherten Rechnungen.",
    invoiceHistoryRecipient: "Empf\u00e4nger:",
    invoiceHistoryTotal: "Gesamt:",
    invoiceHistoryCreated: "Erstellt:",
    invoiceHistorySent: "Versendet:",
    invoiceHistoryError: "Fehler:",
    tfaStatusActive: "2FA ist aktiv",
    tfaStatusInactive: "2FA ist nicht aktiv",
    tfaBtnSetup: "2FA einrichten",
    tfaBtnEnable: "2FA aktivieren",
    tfaBtnDisable: "2FA deaktivieren",
    tfaQrHint: "Geheimnis mit Authenticator-App einrichten:",
    tfaSecretLabel: "Manueller Code:",
    tfaCodeLabel: "Code aus App:",
    tfaCodePlaceholder: "6-stelliger Code",
    tfaEnableHint: "Gib den 6-stelligen Code aus deiner Authenticator-App ein und klicke 'Aktivieren'.",
    tfaEmailLabel: "E-Mail-Adresse für OTP-Codes",
    tfaEmailPlaceholder: "admin@example.com",
    tfaActivateOneClickHint: "Gib deine E-Mail-Adresse ein und klicke auf Aktivieren. Bei jedem Login wird ein Code an deine E-Mail gesendet.",
    alertTfaActivated: "2FA wurde aktiviert.",
    alertTfaEmailRequired: "Bitte E-Mail-Adresse eingeben, bevor 2FA aktiviert wird.",
    alertOtpSent: "Ein Sicherheitscode wurde an Ihre E-Mail gesendet. Bitte prüfen Sie Ihr Postfach.",
    loginOtpSentNotice: "Code per E-Mail gesendet – Postfach prüfen",
    loginOtpBackBtn: "← Zurück",
  },
  en: {
    authEyebrow: "Login Page",
    authTitle: "Secure Sign-in to BauPass Control",
    authCopy: "Super admin keeps full system control. Company admins only see their own company. Turnstile login gets a fast access mode.",
    authPlatform: "Platform",
    authOperator: "Operator",
    authTurnstile: "Turnstile Endpoint",
    loginUsernameLabel: "Username",
    loginUsernamePlaceholder: "Username",
    loginPasswordLabel: "Password",
    loginPasswordPlaceholder: "Enter password",
    loginOtpLabel: "OTP code (if 2FA is enabled)",
    loginOtpPlaceholder: "123456",
    uiLanguageLabel: "Language",
    loginScopeLabel: "Access type",
    loginScopeAuto: "Automatic",
    loginScopeServerAdmin: "Server Admin",
    loginScopeCompanyAdmin: "Company Admin",
    loginScopeTurnstile: "Turnstile",
    supportReadOnlyAlert: "This support login is read-only. Changes are blocked in this session.",
    supportReadOnlyTitle: "Support mode: read-only",
    supportLoginActive: "Support login active:",
    supportCompanyFallback: "Company",
    supportStartedBy: "started by",
    supportReadOnlyNotice: "After sign-in, access is read-only.",
    supportModeLabel: "Support mode:",
    supportReadOnlyFor: "Read-only for",
    supportCompanyLoginConfirmPrefix: "Switch to company login for",
    supportCompanyLoginConfirmSuffix: "? Your current admin session will be logged out. Access will then be read-only.",
    supportCompanyLoginOpenedPrefix: "Login for",
    supportCompanyLoginOpenedSuffix: "opened. Please sign in with the company admin now. This session remains read-only.",
    supportModeReadOnlyLine: "Support mode active: Read-only.",
    supportReadOnlyShort: "Support mode: read-only.",
    loginButton: "Sign in",
    demoAccessTitle: "Demo Accounts",
    demoSuperAdmin: "Super Admin: superadmin / 1234",
    demoCompanyAdmin: "Company Admin: firma / 1234",
    demoTurnstile: "Turnstile: drehkreuz / 1234",
    desktopAppTitle: "Desktop App",
    desktopInstallHint: "This portal can be installed on your computer like a native app.",
    desktopInstallButton: "Install on this computer",
    appTitle: "BauPass Control",
    alertInstallUnavailable: "Installation is not directly available in this browser right now. In Chrome or Edge, choose 'Install app' from the browser menu.",
    alertSessionExpired: "Session expired. Please sign in again.",
    // Shell
    sidebarEyebrow: "Company Portal",
    sidebarCopy: "Register workers, take photos, generate digital ID cards and control access at turnstiles.",
    sidebarCardTitle: "Rental Mode",
    sidebarCardStrong: "Multi-Company Ready",
    sidebarCardDesc: "Each construction company manages its team separately. Super admin retains system control.",
    navDashboard: "Dashboard",
    navWorkers: "Workers",
    navBadge: "Badge",
    navAccess: "Access",
    navInvoices: "Invoices",
    navAdmin: "Admin",
    topbarEyebrow: "System Status",
    topbarHeading: "Construction Badges & Access Control",
    btnSeedData: "Insert demo data",
    btnExport: "Export system",
    btnImport: "Import system",
    btnLogout: "Sign out securely",
    dashEyebrow: "Enhanced MVP",
    dashHeading: "Digital badges with photo, badge ID and check-in at turnstile",
    dashSubtext: "The prototype is already designed for renting to construction companies: company management, worker records, local access logs, export and system configuration.",
    dashBadge1: "Photo capture",
    dashBadge2: "Access log",
    dashBadge3: "Multi-tenant",
    reportingEyebrow: "Reporting",
    reportingH3: "Payment & Block Status",
    reportingPaid: "Paid",
    reportingOpen: "Open",
    reportingOverdue: "Overdue",
    reportingInvoicesLabel: "invoices",
    reportingOverdueTotal: "Overdue total",
    reportingLockedCompanies: "Blocked companies",
    reportingAutoSuspensions30d: "Auto suspensions (30d)",
    reportingGeneratedAt: "Generated",
    reportingNoOverdueCompanies: "No overdue companies found.",
    reportingFallbackCompany: "Company",
    reportingOverdueInvoicesLabel: "overdue invoices",
    reportingNoAccessDataLast7Days: "No access data for the last 7 days.",
    reportingCheckin: "Check-in",
    reportingCheckout: "Check-out",
    navDocuments: "Documents",
    docInboxEyebrow: "Inbox",
    docInboxH3: "Incoming Documents by Email",
    btnDocInboxRefresh: "Refresh",
    btnDocInboxSync: "Sync system inbox",
    btnDocInboxPoll: "Fetch mailbox now",
    docEmailInfoLabel: "Document email (workers send proofs here):",
    btnCopyEmail: "Copy",
    btnCopyEmailDone: "Copied!",
    docInboxHint: "Workers send their proof documents to the configured document email. The porter assigns attachments to a worker here.",
    docAssignEyebrow: "Assign",
    docAssignH3: "Assign attachment to a worker",
    docInboxEmpty: "No unprocessed emails in inbox.",
    docInboxEmailFrom: "From",
    docInboxEmailSubject: "Subject",
    docInboxEmailDate: "Date",
    docInboxAttachments: "Attachments",
    btnAssignDoc: "Assign",
    btnDismissEmail: "Dismiss",
    docAssignWorkerLabel: "Select worker",
    docAssignTypeLabel: "Document type",
    docAssignNotesLabel: "Notes (optional)",
    btnConfirmAssign: "Assign document",
    docAssignSuccess: "Document assigned successfully.",
    docTypeMindestlohnnachweis: "Minimum wage proof",
    docTypePersonalausweis: "ID / Passport",
    docTypeSozialversicherungsnachweis: "Social security certificate",
    docTypeArbeitserlaubnis: "Work permit",
    docTypeGesundheitszeugnis: "Health certificate",
    docTypeSonstiges: "Other",
    workerDocsHeading: "Stored Documents",
    workerDocsEmpty: "No documents on file.",
    workerAkteLabel: "Worker File",
    btnUploadWorkerDoc: "Upload document",
    btnConfirmUpload: "Upload",
    docUploadSuccess: "Document uploaded successfully.",
    confirmDeleteDoc: "Really delete this document?",
    btnDownloadDoc: "Download",
    btnDeleteDoc: "Delete",
    imapSectionEyebrow: "Document Inbox",
    imapSectionH4: "IMAP mailbox for proof documents",
    labelImapHint: "Workers send their proof documents to this address. The system polls the mailbox every few minutes.",
    labelImapHost: "IMAP Host",
    labelImapPort: "IMAP Port",
    labelImapUser: "IMAP Username",
    labelImapPass: "IMAP Password",
    labelImapFolder: "IMAP Folder",
    labelImapSsl: "SSL/TLS",
    btnImapTest: "Test IMAP connection",
    imapTestOk: "Connection successful!",
    imapTestFail: "Connection failed",
    accessWeekEyebrow: "7 Days",
    accessWeekH3: "Access per Day",
    recentEyebrow: "Recent Activity",
    recentH3: "Access Log",
    porterLiveEmpty: "Last access entry will be shown once a check-in or check-out occurs.",
    workersFormEyebrow: "Master Data",
    workersFormH3: "Register Worker or Visitor",
    labelType: "Type",
    optWorker: "Worker",
    optVisitor: "Visitor",
    labelFirm: "Company",
    labelSubcompany: "Subcompany",
    optNoSubcompany: "No subcompany",
    labelNewSubcompany: "New Subcompany",
    btnAddSubcompany: "Create subcompany",
    labelFirstName: "First name",
    labelLastName: "Last name",
    labelInsuranceNumber: "Social security number",
    labelRoleField: "Job title",
    labelSite: "Construction site",
    siteFieldHint: "Enter full address – required for GPS check on login",
    labelPhysicalCard: "Physical card ID (NFC/RFID)",
    labelValidUntil: "Valid until",
    labelVisitorCompany: "Visitor company",
    labelVisitPurpose: "Visit purpose",
    labelHostName: "On-site contact person",
    labelVisitEndAt: "Visit end",
    visitorHint: "Visitors are valid for a few hours or until end of day. Open check-ins are automatically checked out at 00:00 at the latest, but the card is retained for reporting.",
    labelWorkerStatus: "Status",
    optStatusActive: "Active",
    optStatusLocked: "Blocked",
    optStatusExpired: "Expired",
    labelBadgePin: "Badge PIN for app login",
    btnStartCamera: "Start camera",
    btnCapturePhoto: "Take photo",
    btnUploadPhoto: "Upload photo",
    btnPhotoUp: "\u2191 Up",
    btnPhotoLeft: "\u2190 Left",
    btnPhotoRight: "Right \u2192",
    btnPhotoDown: "Down \u2193",
    btnPhotoReset: "Reset position",
    btnWorkerSubmit: "Save worker and generate badge",
    btnWorkerCancelEdit: "Cancel editing",
    workersListEyebrow: "Records",
    workersListH3: "Registered Workers",
    btnWorkerCsv: "Download worker list as PDF",
    btnBulkDelete: "Delete selected",
    btnBulkActive: "Set active",
    btnBulkInactive: "Set inactive",
    btnBulkCancel: "Cancel",
    badgeEyebrow: "Digital Badge",
    badgeH3: "Badge Preview",
    badgeEmptyState: "Please create or select a worker first.",
    badgeScanEyebrow: "Scan Help",
    badgeScanH3: "Badge Code",
    badgeScanEmpty: "No badge selected.",
    badgeTitleVisitor: "Digital Visitor Card",
    badgeTitleDayPass: "Digital Site Day Pass",
    badgeTitleRegular: "Digital Site Badge",
    badgeUnknownCompany: "Unknown Company",
    badgeQrHint: "Scan QR, install app and open badge directly.",
    badgeLabelBadgeId: "Badge-ID",
    badgeMetaQrFunc: "QR Function",
    badgeMetaQrFuncVal: "Worker App Installation",
    badgeMetaRoleLabel: "Role in System",
    badgePhotoUploadHint: "Take or upload photo",
    appPinLabel: "App PIN",
    pinNotRequired: "not required",
    pinSet: "set",
    pinMissing: "missing",
    cardLabel: "Card",
    navDevices: "Devices",
    devicesEyebrow: "Hardware",
    devicesH3: "Smart Boxes & OSDP Devices",
    devicesHint: "Each smart box sends a heartbeat every 30–60 s. No signal >90 s = offline.",
    btnAddDevice: "Add Device",
    addDeviceEyebrow: "New Device",
    addDeviceH3: "Register Device",
    labelDeviceName: "Name",
    labelDeviceLocation: "Location",
    labelDeviceType: "Type / Protocol",
    btnDeviceRegister: "Register device and generate API key",
    deviceOnline: "Online",
    deviceOffline: "Offline",
    deviceNeverSeen: "No heartbeat yet",
    btnPrintBadge: "Print Badge",
    greetingMorning: "Good morning",
    greetingDay: "Good day",
    greetingEvening: "Good evening",
    greetingNight: "Good night",
    greetingSuffix: "Have a great shift!",
    adminWorkerAppSectionTitle: "Worker App",
    adminWorkerAppSectionCopy: "Controls the complete worker app: login, digital badge and QR usage on mobile.",
    adminWorkerAppPinLockHint: "After 2 minutes of inactivity the worker must re-enter their badge PIN to see the badge.",
    optPlanDayPassRecommended: "Visitor card (recommended)",
    optPlanMonthlySite: "Monthly per site",
    optPlanPerWorker: "Per worker",
    optPlanFlatCompany: "Flat rate per company",
    optPlanDayPassPrice: "Visitor card (19 EUR/day)",
    btnDocInboxRematch: "Re-assign",
    cardUnassigned: "not assigned",
    btnEdit: "Edit",
    btnDelete: "Delete",
    btnRestore: "Restore",
    btnAppLink: "App link",
    btnResetPin: "Reset PIN",
    confirmDeleteWorker: "Delete worker now?",
    alertDeleteWorkerFailed: "Worker could not be deleted: {error}",
    alertRestoreWorkerFailed: "Worker could not be restored: {error}",
    alertAppLinkCreateFailed: "App link could not be created: {error}",
    promptResetPinFor: "New badge PIN for {name} (4-8 digits):",
    alertPinMustDigits: "PIN must contain 4 to 8 digits.",
    alertPinResetSuccessFor: "PIN for {name} was reset successfully.",
    alertPinResetFailed: "PIN could not be reset: {error}",
    alertPhotoOverrideApproved: "Photo override approved. Worker data has been saved.",
    alertPhotoOverrideApproveFailed: "Approval failed: {error}",
    alertPhotoOverrideRejectReasonRequired: "A rejection reason is required.",
    alertPhotoOverrideRejected: "Photo override rejected.",
    alertPhotoOverrideRejectFailed: "Rejection failed: {error}",
    alertDocEmailSaveFailed: "Document email could not be saved: {error}",
    alertCompanyDeleted: "Company {name} has been deleted.",
    alertCompanyDeleteFailed: "Company {name} could not be deleted: {error}",
    alertCompanyLocked: "Company {name} has been locked.",
    alertCompanyUnlocked: "Lock for {name} has been lifted.",
    alertCompanyStatusChangeFailed: "Status change for {name} failed: {error}",
    alertBrandingPresetSaveFailed: "Design preset could not be saved: {error}",
    alertPasswordMinLength: "Password must be at least 4 characters.",
    alertTurnstileCreateFailed: "Turnstile could not be created: {error}",
    alertTurnstilePasswordUpdated: "Turnstile password has been updated.",
    alertTurnstilePasswordResetFailed: "Password reset failed: {error}",
    alertApiKeyRotationFailed: "API key rotation failed: {error}",
    alertTurnstileToggleFailed: "Turnstile could not be toggled: {error}",
    alertWorkerDeletedCannotEdit: "Deleted workers cannot be edited.",
    alertDataCopied: "Data copied.",
    alertPrintWindowFailed: "Print window could not be opened.",
    alertAppLinkCopied: "App link copied.",
    alertQrNotReadyYet: "QR code is still being generated. Please try again shortly.",
    alertAccessBookingFailed: "Access could not be booked: {error}",
    alertWorkerSaveFailed: "Worker could not be saved: {error}",
    alertPhotoMatchFailed: "Photo comparison failed ({score}%). Saving is blocked. Please retake the photo or contact a superadmin.",
    alertOverrideReasonTooShort: "Override reason too short. Please enter at least 8 characters.",
    alertPhotoOverrideRequested: "Photo override requested (Approval ID: {id}).\nA second superadmin must approve the change before it is saved.",
    alertBadgePinInvalid: "Badge PIN must contain 4 to 8 digits.",
    alertDuplicatePhysicalCardId: "This physical card ID is already assigned to another worker.",
    alertPhotoOverrideSuperadminOnly: "Photo override is only allowed for superadmins.",
    alertPhotoOverrideReasonRequired: "Please provide a sufficient reason for the photo override.",
    alertInvoiceSavedSendFailed: "Invoice saved, sending failed: {error}",
    alertInvoiceNumberDuplicate: "Invoice number {number} is already taken. Please use a different number.",
    alertInvoiceSendFailed: "Invoice could not be sent: {error}",
    alertInvoiceNumberLength: "Invoice number must be between 3 and 64 characters.",
    alertInvoiceDateInvalid: "Invoice date or due date is invalid.",
    alertInvoiceDueDateBeforeIssue: "Due date cannot be before invoice date.",
    alertInvoiceVatRange: "VAT must be between 0 and 100.",
    alertApprovalRejectReasonRequired: "Rejection without a reason is not allowed.",
    alertApprovalConfirmed: "Approval confirmed and action executed.",
    alertApprovalRejected: "Approval was rejected.",
    alertApprovalUpdated: "Approval updated.",
    alertApprovalActionFailed: "Approval action failed: {error}",
    alertInvoiceRetrySentDeadLetter: "Invoice was successfully resent and removed from dead-letter queue.",
    alertInvoiceRetrySent: "Invoice was successfully resent.",
    alertInvoiceRetryFailed: "Resend failed: {error}",
    alertDeadLetterResolveApprovalRequested: "Approval requested ({id}). A second superadmin must confirm.",
    alertDeadLetterResolveFailed: "Dead-letter case could not be resolved: {error}",
    alertGenericError: "Error: {error}",
    alertCollectionsStatusChangeFailed: "Status change failed: {error}",
    alertActionFailed: "Action failed: {error}",
    alertInvoiceHistoryLoadFailed: "History could not be loaded: {error}",
    alertAccessExportFailed: "Access log export failed: {error}",
    alertWorkerExportFailed: "Worker list export failed: {error}",
    alertSettingsSaveFailed: "Settings could not be saved: {error}",
    alertSystemRepairDone: "System repair has been executed.",
    alertSystemRepairFailed: "System repair failed: {error}",
    alertBrandingLoaded: "BauKometra branding loaded. Just click Save in Admin Settings.",
    alertBrandingLoadFailed: "Branding could not be loaded: {error}",
    alertBrandingAltLoaded: "Alternative BauKometra branding loaded. Just click Save in Admin Settings.",
    alertBrandingAltLoadFailed: "Alternative branding could not be loaded: {error}",
    alertDayCloseAckFailed: "Day close could not be acknowledged: {error}",
    alertOtpRequired: "2FA is active for this account. Please enter the OTP code.",
    alertOtpInvalid: "OTP code is invalid or expired. Please enter a new code.",
    alertTooManyAttempts: "Too many failed attempts. Please wait 10 minutes and try again.",
    loginSecurityTitle: "Security Alert",
    loginSecurityHint: "3 failed sign-in attempts were detected.",
    loginSecurityCallPrefix: "Please call admin immediately at:",
    loginSecurityFooter: "After verification, the password can be reset.",
    alertForbiddenTenantHost: "This access is only allowed via the approved company domain.",
    alertSupportCompanyMismatch: "This login does not match the selected company. Please use the company admin of the marked company.",
    alertLoginCompanyLocked: "This company is locked. Please settle outstanding invoices or lift the lock in superadmin.",
    alertInvalidCredentials: "Username or password is incorrect. Please check your details and try again.",
    alertAdminIpNotAllowed: "Admin access from this IP is not allowed.",
    alertLoginScopeMismatch: "Access type does not match the account. Please select server admin / company admin correctly.",
    alertLoginHttp405: "Login failed: 405. The login request is currently landing on {target}. For GitHub Pages, the frontend must use your Render backend.",
    alertLoginFailed: "Login failed: {error}",
    alertPasswordResetEnterUsername: "Please enter a username or email first.",
    alertPasswordResetSent: "If a matching account was found, a reset email has been sent.",
    alertPasswordResetFailed: "Password reset could not be started: {error}",
    alertPasswordSetSuccess: "Password has been set successfully. You can now sign in.",
    alertPasswordResetLinkFailed: "Reset link could not be used: {error}",
    alertPasswordChanged: "Password changed. Please sign in again.",
    alertPasswordChangeFailed: "Password change failed: {error}",
    alert2faSetupFailed: "2FA setup failed: {error}",
    alert2faEnableFailed: "2FA could not be activated: {error}",
    alertDeviceDeleteFailed: "Error deleting: {error}",
    alertCompanyCreateFailed: "Company could not be created: {error}",
    alert2faDisableFailed: "2FA could not be deactivated: {error}",
    alertExportFailed: "Export failed: {error}",
    alertNoDemoCompany: "No active company found for demo data.",
    alertDemoModeInvalid: "Invalid mode. Please use replace or append.",
    alertDemoLoadFailed: "Demo data could not be loaded: {error}",
    alertImportSuccess: "Import applied successfully.",
    alertImportFailed: "Import failed: {error}",
    alertCsvExportFailed: "CSV export failed: {error}",
    alertIncidentExportFailed: "Incident export failed: {error}",
    alertSelectInvoiceForRetry: "Please select at least one invoice in the queue.",
    alertBulkRetryDone: "Bulk retry completed. Sent: {sent}, Failed: {failed}, Skipped: {skipped}",
    alertBulkRetryFailed: "Bulk retry failed: {error}",
    alertNoCriticalCases: "There are currently no critical cases (score >= 70).",
    alertCriticalBulkRetryDone: "Critical bulk retry completed. Sent: {sent}, Failed: {failed}, Skipped: {skipped}",
    alertCriticalBulkRetryFailed: "Critical bulk retry failed: {error}",
    alertDesktopInstallFailed: "Desktop installation could not be started.",
    alertSubcompanyCreateFailed: "Subcontractor could not be created: {error}",
    alertDeleteFailed: "Error deleting: {error}",
    alertStatusChangeFailed: "Error changing status: {error}",
    alertReassignmentDone: "Reassignment completed. Matches: {count}",
    alertReassignmentFailed: "Reassignment failed: {error}",
    detailCloseTitle: "Close",
    detailPhotoAlt: "Worker photo",
    detailCheckinBtn: "Check in",
    detailCheckoutBtn: "Check out",
    accessFormEyebrow: "Turnstile",
    accessFormH3: "Check-in and Check-out",
    labelAccessBadge: "Badge ID or Worker",
    labelAccessDir: "Direction",
    labelAccessGate: "Gate",
    labelAccessNote: "Note",
    optCheckin: "Check-in",
    optCheckout: "Check-out",
    btnAccessSubmit: "Book access",
    porterEmpty: "Porter live view: Select worker and book access.",
    accessLogEyebrow: "Access Journal",
    accessLogH3: "Entry and exit with timestamp",
    labelFrom: "From",
    labelTo: "To",
    labelFilterDir: "Direction",
    labelFilterGate: "Gate",
    optAllDir: "All",
    btnApplyFilter: "Apply filter",
    btnResetFilter: "Reset filter",
    btnAccessCsv: "Export access CSV",
    dailyReportEyebrow: "Daily Report",
    dailyReportH3: "Per gate",
    btnPrintDaily: "Print daily report",
    btnPrintVisitorWeekly: "Print visitor weekly list",
    hourlyEyebrow: "Hourly Analysis",
    hourlyH3: "Entry/Exit per hour",
    warningsEyebrow: "Warnings",
    warningsH3: "Entry without exit",
    invListEyebrow: "Billing",
    invListH3: "Invoices & Payment Status",
    optAllStatus: "All statuses",
    optDraft: "Draft",
    optSent: "Sent",
    optOverdue: "Overdue",
    optPaid: "Paid",
    optFailed: "Error",
    btnRefreshList: "Refresh",
    inkassoEyebrow: "Collections",
    inkassoH3: "Overdue, pre-block, blocked",
    optAllPositions: "All open items",
    optPrelock: "Pre-block",
    optLocked: "Already blocked",
    adminEyebrow: "Admin Center",
    adminH3: "System & Configuration",
    sysStatusEyebrow: "System Status",
    sysStatusH3: "Emergency Access & Repair",
    btnRefreshStatus: "Reload status",
    btnRepairSessions: "Repair sessions",
    superAdminEyebrow: "System Control",
    superAdminH3: "Super Admin Settings",
    labelPlatformName: "Platform name",
    labelOperatorName: "Operator",
    labelTurnstileEp: "Turnstile API endpoint",
    labelSmtpHost: "SMTP host",
    labelSmtpPort: "SMTP port",
    labelSmtpUser: "SMTP user",
    labelSmtpPass: "SMTP password",
    labelSenderEmail: "Sender email",
    labelSenderName: "Sender name",
    labelTls: "TLS active",
    optTlsYes: "Yes",
    optTlsNo: "No",
    btnTestSmtp: "Send test mail",
    optYes: "Yes",
    optNo: "No",
    labelIpWhitelist: "Admin IP whitelist (comma separated, optional CIDR)",
    labelEnforceDomain: "Enforce company domain",
    btnSaveAdmin: "Save admin settings",
    companyNewEyebrow: "Tenants",
    companyNewH3: "Create New Construction Company",
    labelCompanyName: "Company name",
    labelCompanyContact: "Contact person",
    labelBillingEmail: "Billing email",
    labelAccessHost: "Company access domain",
    labelPlan: "Plan",
    labelCompanyStatus: "Status",
    optCompanyActive: "Active",
    optCompanyTest: "Trial",
    optCompanyPaused: "Paused",
    optCompanyLocked: "Blocked due to overdue payment",
    labelCompanyAdminPassword: "Admin start password",
    companyAdminPasswordPlaceholder: "e.g. Secure!2025",
    btnCreateCompany: "Create company",
    accountEyebrow: "Account",
    accountH3: "Change Password",
    labelCurrentPassword: "Current password",
    labelNewPassword: "New password",
    btnChangePassword: "Change password",
    tfaEyebrow: "Two-Factor",
    tfaH3: "2FA Management",
    companiesListEyebrow: "Tenants",
    companiesListH3: "Companies & Plans",
    invFormEyebrow: "Invoices",
    invFormH3: "Send with logo and branding",
    labelInvFirm: "Company",
    labelInvNumber: "Invoice number",
    labelInvRecipient: "Recipient email",
    labelInvDate: "Invoice date",
    labelInvDueDate: "Due date",
    labelInvPeriod: "Service period",
    labelInvDescription: "Service description",
    labelInvNet: "Net amount (EUR)",
    labelInvVat: "VAT (%)",
    btnPrintInvoice: "Print invoice / save as PDF",
    btnSendInvoice: "Send invoice by email",
    btnUpdatePreview: "Update preview",
    auditEyebrow: "Security Log",
    auditH3: "Audit Log",
    labelAuditEvent: "Event type",
    labelAuditRole: "Role",
    btnAuditCsv: "Export audit CSV",
    loginForgotPassword: "Forgot password",
    legalImpressum: "Legal notice",
    legalPrivacy: "Privacy",
    legalCloseTitle: "Close",
    legalFallbackEmpty: "No text available.",
    invoiceMgmtTitle: "Invoice management",
    invoiceMgmtCopy: "View open and paid invoices. Mark invoices as paid to automatically lift company locks. All activities are logged in the audit log.",
    invoiceOpsEyebrow: "Operations",
    invoiceOpsH3: "Delivery SLA and error status",
    invoiceSendEyebrow: "Delivery",
    invoiceSendH3: "Queue for failed emails",
    optRetryAll: "All failed deliveries",
    optRetryPriority: "Priority first",
    optRetryMaxed: "Max retries reached",
    optRetryTodayFailed: "Failed today",
    invoiceRetryTopIssuesOnly: "Only my top issues",
    btnRetryCriticalSend: "Send critical only now",
    btnRetryExportCsv: "Queue CSV",
    btnIncidentExportCsv: "Incident CSV",
    btnRetryBulkSend: "Resend selected",
    invoiceApprovalsEyebrow: "Approvals",
    invoiceApprovalsH3: "Four-eyes check for critical actions",
    optApprovalAllActions: "All action types",
    optApprovalBulkRetry: "Bulk retry",
    optApprovalDeadLetterResolve: "Dead-letter resolve",
    legalSectionEyebrow: "Legal",
    legalSectionTitle: "Legal notice & privacy",
    labelImpressumText: "Legal notice text",
    labelPrivacyText: "Privacy policy",
    legalTextsHint: "These texts appear on the login page under 'Legal notice' and 'Privacy'.",
    labelCompanyDocumentEmail: "Document email",
    labelBrandingPreset: "Branding preset",
    optBrandingConstruction: "Construction",
    optBrandingIndustry: "Industry",
    optBrandingPremium: "Premium",
    optPlanStarter: "Starter (49 EUR)",
    optPlanProfessional: "Professional (99 EUR)",
    optPlanEnterprise: "Enterprise (199 EUR)",
    accessFeedbackCheckin: "Access granted",
    badgePinHint: "Badge login in the worker app only works with Badge-ID and this PIN. When editing you can set a new PIN here.",
    badgePinPlaceholder: "4 to 8 digits",
    bulkSelectAll: "Select all",
    btnDayCloseAcknowledge: "Acknowledge day close",
    btnExportCompanyDocEmails: "Export document emails",
    btnLoadAltBrand: "Load alternative",
    btnLoadDefaultBrand: "Load default branding",
    cameraNotStarted: "Camera not started yet.",
    complianceEyebrow: "Compliance",
    complianceH3: "Document status",
    dayCloseCommentLabel: "Day close comment",
    dayCloseCommentPlaceholder: "e.g. Shift leader notified, exit to be added later",
    deadLetterEyebrow: "Dead-Letter",
    deadLetterH3: "Invoices requiring manual resolution",
    filterByCompanyPlaceholder: "Filter by company…",
    filterQueueByCompanyPlaceholder: "Filter queue by company…",
    formSectionAppFeaturesEyebrow: "App Features",
    formSectionBrandingEyebrow: "Invoice design",
    formSectionBrandingH4: "Colors & Branding",
    formSectionEmailEyebrow: "E-Mail",
    formSectionPlatformEyebrow: "Platform",
    formSectionPlatformH4: "Identity & Operator",
    formSectionSecurityH4: "Access & Isolation",
    formSectionSmtpH4: "SMTP Sending",
    invoiceLogoHint: "The invoice logo is also used as the system icon and worker app icon.",
    invoicePreviewEyebrow: "Preview",
    invoicePreviewH3: "Check invoice before sending",
    maxAgeFilterPlaceholder: "Max age in minutes (0 = all)",
    optDeviceOsdp: "OSDP (RS-485)",
    optDeviceTcp: "TCP/IP Smart-Box",
    optDeviceWiegand: "Wiegand Reader",
    optPinLockActive: "Active – PIN lock prevents phone sharing",
    optPinLockDisabled: "Disabled – Badge always accessible",
    optRoleCompanyAdmin: "Company Admin",
    optRoleSuperAdmin: "Super Admin",
    optWorkerAppActive: "Active – Badge, QR and badge login enabled",
    optWorkerAppLocked: "Locked – Mobile app disabled",
    photoAdjustHelp: "Move the photo after capture so it fits neatly on the right side of the badge.",
    photoOverrideH3: "Pending photo override approvals",
    photoRequiredHint: "Required: Without a photo the badge cannot be saved.",
    photoSharpenLabel: "Sharpness:",
    photoWhiteBgLabel: "Background completely white (active)",
    photoZoomCropLabel: "Zoom / Crop",
    recentAuditEyebrow: "Audit",
    recentAuditH3: "Recent system events",
    rentalModelLabel: "Rental model",
    sectionSecurityEyebrow: "Security",
    statusLoading: "Loading status…",
    sysAlertActionBtn: "Go to invoices",
    sysAlertDefaultText: "There are critical invoice sending failures.",
    sysAlertHeading: "Critical sending issue",
    turnstileCountLabel: "Number of turnstiles",
    turnstilePasswordLabel: "Turnstile start password",
    workerAppEnabledLabel: "Mobile badge app (digital badge + QR)",
    workerPassLockLabel: "Secure badge with PIN lock",
    workerSearchPlaceholder: "Search: Name, Badge-ID, Site …",
    confirmDeleteCompanyText: "Delete company {name} and all associated records?\n\nOK = complete deletion (incl. employees, subcontractors and logs)\nCancel = do not delete",
    confirmLockCompany: "Lock company {name} now? The company admin, turnstile and employee app of this company will be blocked.",
    confirmUnlockCompany: "Lift lock for {name} now? The company can log in again afterwards.",
    confirmDeleteWorkerBulk: "Really delete {count} employees?",
    confirmApiKeyRotate: "Regenerate the API key for this turnstile now? The existing key will immediately lose its validity.",
    confirmSystemRepair: "Run system repair? Expired sessions and login lockouts will be cleaned up.",
    confirmApprovalDecision: "Really {decision} approval {id}?",
    confirmDeadLetterRetry: "Resend dead-letter invoice now?",
    confirmDeadLetterResolve: "Mark dead-letter case as resolved?",
    confirmInvoicePaid: "Mark this invoice as paid? Any company lock will be lifted.",
    confirmInvoiceRetry: "Resend invoice now?",
    confirmInvoicePaidSimple: "Mark invoice as paid now?",
    confirmDemoInvoices: "Should demo invoices also be generated?",
    confirmDemoAccessLogs: "Should demo access logs be generated?",
    confirmDemoReplace: "Load demo data now for {name} in REPLACE mode? Existing employees, subcontractors and logs will be replaced.",
    confirmDemoAppend: "Load demo data additionally for {name} in APPEND mode?",
    confirmExportAudit: "Include audit log in export?",
    confirmExportDayClose: "Include day-close acknowledgements in export?",
    confirmExportDeleted: "Include deleted entries in export?",
    confirmExportAll: "As superadmin: export entire system? (No = current company only)",
    confirmExportDownload: "Download system export{scope} now?",
    confirmLogout: "Really log out?",
    confirmImportChangesOnly: "Import changes only? (Recommended)",
    confirmBulkRetrySelected: "Resend {count} selected invoice(s) now?",
    confirmBulkRetryCritical: "Resend {count} critical invoice(s) now?",
    confirmPhotoMatchFailed: "Photo comparison failed ({score}%). Only superadmin may save with risk. Save anyway?",
    promptDocEmail: "Set document email for {name}",
    promptTurnstilePassword: "Set turnstile password for {name} (min. 4 characters):",
    promptTurnstilePasswordNew: "Set new turnstile password (min. 4 characters):",
    promptCopyData: "Data to copy:",
    promptAppLink: "App link for employee:",
    promptPhotoOverrideReason: "Please enter reason for photo override (at least 8 characters):",
    promptNewPassword: "Enter new password (at least 8 characters):",
    promptTfaCode: "Please enter 6-digit code from your authenticator app:",
    promptTfaDisableCode: "Please enter current 2FA code to disable:",
    promptDemoMode: "Demo data for {name}: enter mode (replace or append)",
    promptRejectionReason: "Rejection reason (required):",
    promptRejectApproval: "Please enter rejection reason:",
    invoiceTitle: "Invoice",
    invoiceAltLogo: "Company logo",
    invoiceLabelNumber: "Invoice number:",
    invoiceLabelDate: "Invoice date:",
    invoiceLabelDue: "Due date:",
    invoiceLabelCustomer: "Customer:",
    invoiceLabelContact: "Contact person:",
    invoiceLabelPeriod: "Service period:",
    invoiceColService: "Service / Employee",
    invoiceColAccess: "Accesses",
    invoiceColNet: "Net amount",
    invoiceRowUnknown: "Unknown",
    invoiceRowPlan: "Plan: {label}",
    invoiceTotalNet: "Subtotal net",
    invoiceTotalVat: "VAT ({rate} %)",
    invoiceTotalGross: "Total amount",
    invoiceFooter: "Thank you for the partnership. This invoice was created digitally and can be sent directly.",
    invoiceHistoryEmpty: "No invoices sent or saved yet.",
    invoiceHistoryRecipient: "Recipient:",
    invoiceHistoryTotal: "Total:",
    invoiceHistoryCreated: "Created:",
    invoiceHistorySent: "Sent:",
    invoiceHistoryError: "Error:",
    tfaStatusActive: "2FA is active",
    tfaStatusInactive: "2FA is not active",
    tfaBtnSetup: "Set up 2FA",
    tfaBtnEnable: "Enable 2FA",
    tfaBtnDisable: "Disable 2FA",
    tfaQrHint: "Set up secret with authenticator app:",
    tfaSecretLabel: "Manual code:",
    tfaCodeLabel: "Code from app:",
    tfaCodePlaceholder: "6-digit code",
    tfaEnableHint: "Enter the 6-digit code from your authenticator app and click 'Enable'.",
    tfaEmailLabel: "Email address for OTP codes",
    tfaEmailPlaceholder: "admin@example.com",
    tfaActivateOneClickHint: "Enter your email address and click Activate. A code will be sent to your email at each login.",
    alertTfaActivated: "2FA has been activated.",
    alertTfaEmailRequired: "Please enter an email address before activating 2FA.",
    alertOtpSent: "A security code has been sent to your email. Please check your inbox.",
    loginOtpSentNotice: "Code sent by email – check your inbox",
    loginOtpBackBtn: "← Back",
  },
  tr: {
    authEyebrow: "Giriş Sayfası",
    authTitle: "BauPass Control'a Güvenli Giriş",
    authCopy: "Süper admin tüm sistem kontrolünü elinde tutar. Firma adminleri yalnızca kendi firmalarını görür. Turnike girişi hızlı geçiş moduna sahiptir.",
    authPlatform: "Platform",
    authOperator: "İşletmeci",
    authTurnstile: "Turnike Uç Noktası",
    loginUsernameLabel: "Kullanıcı adı",
    loginUsernamePlaceholder: "Kullanici adi",
    loginPasswordLabel: "Şifre",
    loginPasswordPlaceholder: "Parola girin",
    loginOtpLabel: "OTP kodu (2FA aktifse)",
    loginOtpPlaceholder: "123456",
    uiLanguageLabel: "Dil",
    loginScopeLabel: "Erişim tipi",
    loginScopeAuto: "Otomatik",
    loginScopeServerAdmin: "Sunucu Yöneticisi",
    loginScopeCompanyAdmin: "Firma Yöneticisi",
    loginScopeTurnstile: "Turnike",
    supportReadOnlyAlert: "Bu destek oturumu salt okunur. Bu oturumda değişiklik yapamazsınız.",
    supportReadOnlyTitle: "Destek modu: salt okunur",
    supportLoginActive: "Destek oturumu aktif:",
    supportCompanyFallback: "Firma",
    supportStartedBy: "başlatan:",
    supportReadOnlyNotice: "Girişten sonra erişim salt okunur olur.",
    supportModeLabel: "Destek modu:",
    supportReadOnlyFor: "Şu firma için salt okunur:",
    supportCompanyLoginConfirmPrefix: "Şu firma için girişe geçilsin",
    supportCompanyLoginConfirmSuffix: "? Mevcut admin oturumun kapatılacak. Sonrasında erişim salt okunur olacak.",
    supportCompanyLoginOpenedPrefix: "Şu firma için giriş ekranı",
    supportCompanyLoginOpenedSuffix: "açıldı. Şimdi firma yöneticisi ile giriş yapın. Bu oturum salt okunur kalacaktır.",
    supportModeReadOnlyLine: "Destek modu aktif: Salt okunur erişim.",
    supportReadOnlyShort: "Destek modu: salt okunur erişim.",
    loginButton: "Giriş yap",
    demoAccessTitle: "Demo Hesaplar",
    demoSuperAdmin: "Süper Admin: superadmin / 1234",
    demoCompanyAdmin: "Firma Yöneticisi: firma / 1234",
    demoTurnstile: "Turnike: drehkreuz / 1234",
    desktopAppTitle: "Masaüstü Uygulaması",
    desktopInstallHint: "Bu portal bilgisayarınıza yerel uygulama gibi kurulabilir.",
    desktopInstallButton: "Bu bilgisayara yükle",
    // Shell (nav + buttons + headings)
    sidebarEyebrow: "Firma Portali",
    sidebarCopy: "\u00c7al\u0131\u015fanlar\u0131 kaydet, foto\u011fraf \u00e7ek, dijital kimlik kart\u0131 olu\u015ftur ve turnike giri\u015fini y\u00f6net.",
    sidebarCardTitle: "Kiralama Modu",
    sidebarCardStrong: "\u00c7ok Firmaya Uygun",
    sidebarCardDesc: "Her in\u015faat firmas\u0131 kendi ekibini ayr\u0131 y\u00f6netir. S\u00fcper admin sistem kontroln\u00fc elinde tutar.",
    navDashboard: "Kontrol Paneli",
    navWorkers: "\u00c7al\u0131\u015fanlar",
    navBadge: "Rozet",
    navAccess: "Giri\u015f",
    navInvoices: "Faturalar",
    navAdmin: "Y\u00f6netim",
    topbarEyebrow: "Sistem Durumu",
    topbarHeading: "\u0130n\u015faat Rozetleri ve Giri\u015f Kontrol",
    btnSeedData: "Demo veri ekle",
    btnExport: "Sistemi d\u0131\u015fa aktar",
    btnImport: "Sistemi i\u00e7e aktar",
    btnLogout: "G\u00fcvenli \u00e7\u0131k\u0131\u015f",
    dashEyebrow: "Geli\u015ftirilmi\u015f MVP",
    dashHeading: "Foto\u011frafl\u0131, Badge ID\u2019li dijital kimlikler ve turnike check-in",
    dashSubtext: "Prototip, in\u015faat firmalar\u0131na kiralama i\u00e7in tasarlanm\u0131\u015ft\u0131r.",
    dashBadge1: "Foto\u011fraf \u00c7ekimi",
    dashBadge2: "Giri\u015f Kayd\u0131",
    dashBadge3: "\u00c7ok Kirac\u0131l\u0131",
    reportingEyebrow: "Raporlama",
    reportingH3: "\u00d6deme ve Engelleme Durumu",
    accessWeekEyebrow: "7 G\u00fcn",
    accessWeekH3: "G\u00fcnl\u00fck Giri\u015f",
    recentEyebrow: "Son Aktiviteler",
    recentH3: "Giri\u015f Kayd\u0131",
    porterLiveEmpty: "Bir check-in veya check-out oldu\u011funda son giri\u015f burada g\u00f6r\u00fcnt\u00fclenecek.",
    workersFormEyebrow: "Ana Veriler",
    workersFormH3: "\u00c7al\u0131\u015fan veya Ziyaret\u00e7i Kaydet",
    labelType: "Tip",
    optWorker: "\u00c7al\u0131\u015fan",
    optVisitor: "Ziyaret\u00e7i",
    labelFirm: "Firma",
    labelSubcompany: "Alt Firma",
    optNoSubcompany: "Alt firma yok",
    labelNewSubcompany: "Yeni Alt Firma",
    btnAddSubcompany: "Alt firma olu\u015ftur",
    labelFirstName: "Ad",
    labelLastName: "Soyad",
    labelInsuranceNumber: "Sigorta numaras\u0131",
    labelRoleField: "G\u00f6rev",
    labelSite: "\u015eantiye",
    siteFieldHint: "Tam adres girin - giris icin GPS kontrolu gereklidir",
    labelPhysicalCard: "Fiziksel Kart ID (NFC/RFID)",
    labelValidUntil: "Ge\u00e7erlilik tarihi",
    labelVisitorCompany: "Ziyaret\u00e7i firmas\u0131",
    labelVisitPurpose: "Ziyaret amac\u0131",
    labelHostName: "Sahada ileti\u015fim ki\u015fisi",
    labelVisitEndAt: "Ziyaret biti\u015fi",
    visitorHint: "Ziyaretçiler birkaç saat veya gün sonuna kadar geçerlidir. Açık girişler en geç 00:00'da otomatik olarak çıkış yapar, kart raporlama için saklanır.",
    labelWorkerStatus: "Durum",
    optStatusActive: "Aktif",
    optStatusLocked: "Engelli",
    optStatusExpired: "S\u00fcresi doldu",
    labelBadgePin: "Uygulama giri\u015fi i\u00e7in Badge PIN",
    btnStartCamera: "Kameray\u0131 ba\u015flat",
    btnCapturePhoto: "Foto\u011fraf \u00e7ek",
    btnUploadPhoto: "Foto\u011fraf y\u00fckle",
    btnPhotoUp: "\u2191 Yukar\u0131",
    btnPhotoLeft: "\u2190 Sol",
    btnPhotoRight: "Sa\u011f \u2192",
    btnPhotoDown: "A\u015fa\u011f\u0131 \u2193",
    btnPhotoReset: "Konumu s\u0131f\u0131rla",
    btnWorkerSubmit: "\u00c7al\u0131\u015fan\u0131 kaydet ve rozet olu\u015ftur",
    btnWorkerCancelEdit: "D\u00fczenli\u015f i\u00e7in iptal",
    workersListEyebrow: "Kay\u0131tlar",
    workersListH3: "Kay\u0131tl\u0131 \u00c7al\u0131\u015fanlar",
    btnWorkerCsv: "\u00c7al\u0131\u015fan listesini PDF olarak indir",
    btnBulkDelete: "Se\u00e7ilenleri sil",
    btnBulkActive: "Durumu: aktif",
    btnBulkInactive: "Durumu: pasif",
    btnBulkCancel: "\u0130ptal",
    badgeEyebrow: "Dijital Kimlik",
    badgeH3: "Rozet \u00d6nizleme",
    badgeEmptyState: "L\u00fctfen \u00f6nce bir \u00e7al\u0131\u015fan olu\u015fturun veya listeden se\u00e7in.",
    badgeScanEyebrow: "Tarama Yard\u0131m\u0131",
    badgeScanH3: "Rozet Kodu",
    badgeScanEmpty: "Rozet se\u00e7ilmedi.",
    accessFormEyebrow: "Turnike",
    accessFormH3: "Check-in ve Check-out",
    labelAccessBadge: "Badge ID veya \u00c7al\u0131\u015fan",
    labelAccessDir: "Y\u00f6n",
    labelAccessGate: "Kap\u0131",
    labelAccessNote: "Not",
    optCheckin: "Check-in",
    optCheckout: "Check-out",
    btnAccessSubmit: "Giri\u015f kaydet",
    porterEmpty: "Kap\u0131c\u0131 canl\u0131 g\u00f6r\u00fcn\u00fcm\u00fc: \u00c7al\u0131\u015fan se\u00e7 ve giri\u015fi kaydet.",
    accessLogEyebrow: "Giri\u015f G\u00fcnl\u00fc\u011f\u00fc",
    accessLogH3: "Zaman damgal\u0131 giri\u015f ve \u00e7\u0131k\u0131\u015f",
    labelFrom: "Ba\u015flang\u0131\u00e7",
    labelTo: "Biti\u015f",
    labelFilterDir: "Y\u00f6n",
    labelFilterGate: "Turnike",
    optAllDir: "T\u00fcm\u00fc",
    btnApplyFilter: "Filtre uygula",
    btnResetFilter: "Filtreyi s\u0131f\u0131rla",
    btnAccessCsv: "Giri\u015f CSV disa aktar",
    dailyReportEyebrow: "G\u00fcnl\u00fck Rapor",
    dailyReportH3: "Kapiya g\u00f6re",
    btnPrintDaily: "G\u00fcnl\u00fck rapor yazd\u0131r",
    btnPrintVisitorWeekly: "Haftal\u0131k ziyaret\u00e7i listesi yazd\u0131r",
    hourlyEyebrow: "Saatlik Analiz",
    hourlyH3: "Saate g\u00f6re giri\u015f/\u00e7\u0131k\u0131\u015f",
    warningsEyebrow: "Uyar\u0131lar",
    warningsH3: "\u00c7\u0131k\u0131\u015fs\u0131z giri\u015f",
    invListEyebrow: "Faturaland\u0131rma",
    invListH3: "Faturalar ve \u00d6deme Durumu",
    optAllStatus: "T\u00fcm durumlar",
    optDraft: "Taslak",
    optSent: "G\u00f6nderildi",
    optOverdue: "Vadesi ge\u00e7mi\u015f",
    optPaid: "\u00d6dendi",
    optFailed: "Hata",
    btnRefreshList: "Yenile",
    inkassoEyebrow: "Tahsilat",
    inkassoH3: "Vadesi ge\u00e7mi\u015f, \u00f6n engel, engellendi",
    optAllPositions: "T\u00fcm a\u00e7\u0131k kalemler",
    optPrelock: "\u00d6n engel",
    optLocked: "Zaten engellendi",
    adminEyebrow: "Y\u00f6netim Merkezi",
    adminH3: "Sistem & Yap\u0131land\u0131rma",
    sysStatusEyebrow: "Sistem Durumu",
    sysStatusH3: "Acil Eri\u015fim & Onar\u0131m",
    btnRefreshStatus: "Durumu yenile",
    btnRepairSessions: "Oturumlar\u0131 onar",
    superAdminEyebrow: "Sistem Kontrolu",
    superAdminH3: "S\u00fcper Admin Ayarlar\u0131",
    labelPlatformName: "Platform ad\u0131",
    labelOperatorName: "\u0130\u015flet",
    labelTurnstileEp: "Turnike API endpoint",
    labelSmtpHost: "SMTP Host",
    labelSmtpPort: "SMTP Port",
    labelSmtpUser: "SMTP Kullan\u0131c\u0131s\u0131",
    labelSmtpPass: "SMTP \u015eifre",
    labelSenderEmail: "G\u00f6nderen E-Posta",
    labelSenderName: "G\u00f6nderen Ad\u0131",
    labelTls: "TLS aktif",
    optTlsYes: "Evet",
    optTlsNo: "Hayır",
    btnTestSmtp: "Test maili gönder",
    optYes: "Evet",
    optNo: "Hayır",
    labelIpWhitelist: "Admin IP beyaz listesi",
    labelEnforceDomain: "Firma domain zorla",
    btnSaveAdmin: "Admin ayarlar\u0131n\u0131 kaydet",
    companyNewEyebrow: "Kirac\u0131lar",
    companyNewH3: "Yeni \u0130n\u015faat Firmas\u0131 Ekle",
    labelCompanyName: "Firma ad\u0131",
    labelCompanyContact: "\u0130leti\u015fim ki\u015fisi",
    labelBillingEmail: "Fatura e-postas\u0131",
    labelAccessHost: "Firma eri\u015fim alan\u0131",
    labelPlan: "Plan",
    labelCompanyStatus: "Durum",
    optCompanyActive: "Aktif",
    optCompanyTest: "Deneme",
    optCompanyPaused: "Askıya alındı",
    optCompanyLocked: "\u00d6deme gecikmi\u015f, engellendi",
    labelCompanyAdminPassword: "Yönetici başlangıç şifresi",
    companyAdminPasswordPlaceholder: "Örn. Güvenli!2025",
    btnCreateCompany: "Firma olu\u015ftur",
    accountEyebrow: "Hesap",
    accountH3: "\u015eifreyi De\u011fi\u015ftir",
    labelCurrentPassword: "Mevcut \u015fifre",
    labelNewPassword: "Yeni \u015fifre",
    btnChangePassword: "\u015eifreyi de\u011fi\u015ftir",
    tfaEyebrow: "\u0130ki Fakt\u00f6r",
    tfaH3: "2FA Y\u00f6netimi",
    companiesListEyebrow: "Kirac\u0131lar",
    companiesListH3: "Firmalar ve Planlar",
    invFormEyebrow: "Faturalar",
    invFormH3: "Logo ve tasar\u0131mla g\u00f6nder",
    labelInvFirm: "Firma",
    labelInvNumber: "Fatura numaras\u0131",
    labelInvRecipient: "Al\u0131c\u0131 e-postas\u0131",
    labelInvDate: "Fatura tarihi",
    labelInvDueDate: "Son \u00f6deme tarihi",
    labelInvPeriod: "Hizmet d\u00f6nemi",
    labelInvDescription: "Hizmet a\u00e7\u0131klamas\u0131",
    labelInvNet: "Net tutar (EUR)",
    labelInvVat: "KDV (%)",
    btnPrintInvoice: "Faturay\u0131 yazd\u0131r / PDF kaydet",
    btnSendInvoice: "Faturay\u0131 e-postayla g\u00f6nder",
    btnUpdatePreview: "\u00d6nizlemeyi g\u00fcncelle",
    auditEyebrow: "G\u00fcvenlik Kayd\u0131",
    auditH3: "Denetim Kayd\u0131",
    labelAuditEvent: "Olay tipi",
    labelAuditRole: "Rol",
    btnAuditCsv: "Denetim CSV disa aktar",
    reportingPaid: "Ödendi",
    reportingOpen: "Açık",
    reportingOverdue: "Gecikmiş",
    reportingInvoicesLabel: "Faturalar",
    reportingOverdueTotal: "Gecikmiş toplam",
    reportingLockedCompanies: "Engelli firmalar",
    reportingAutoSuspensions30d: "Otomatik askı (30g)",
    reportingGeneratedAt: "Oluşturuldu",
    reportingNoOverdueCompanies: "Gecikmiş firma yok.",
    reportingFallbackCompany: "Firma",
    reportingOverdueInvoicesLabel: "gecikmiş fatura",
    reportingNoAccessDataLast7Days: "Son 7 gün için erişim verisi yok.",
    reportingCheckin: "Check-in",
    reportingCheckout: "Check-out",
    navDocuments: "Belgeler",
    docInboxEyebrow: "Gelen Kutusu",
    docInboxH3: "E-posta ile Gelen Belgeler",
    btnDocInboxRefresh: "Yenile",
    btnDocInboxSync: "Sistem kutusunu al",
    btnDocInboxPoll: "Posta kutusunu şimdi getir",
    btnDocInboxRematch: "Yeniden eşleştir",
    docEmailInfoLabel: "Belge e-postası (çalışanlar kanıtlarını buraya gönderir):",
    btnCopyEmail: "Kopyala",
    btnCopyEmailDone: "Kopyalandı!",
    docInboxHint: "Çalışanlar kanıtlarını yapılandırılmış belge e-postasına gönderir. Görevli ekleri bir çalışana burada atar.",
    docAssignEyebrow: "Ata",
    docAssignH3: "Eki bir çalışana ata",
    docInboxEmpty: "İşlenmemiş posta yok.",
    docInboxEmailFrom: "Kimden",
    docInboxEmailSubject: "Konu",
    docInboxEmailDate: "Tarih",
    docInboxAttachments: "Ekler",
    btnAssignDoc: "Ata",
    btnDismissEmail: "Kapat",
    docAssignWorkerLabel: "Çalışan seç",
    docAssignTypeLabel: "Belge türü",
    docAssignNotesLabel: "Notlar (isteğe bağlı)",
    btnConfirmAssign: "Belgeyi ata",
    docAssignSuccess: "Belge başarıyla atandı.",
    docTypeMindestlohnnachweis: "Asgari ücret kanıtı",
    docTypePersonalausweis: "Kimlik / Pasaport",
    docTypeSozialversicherungsnachweis: "Sosyal güvenlik belgesi",
    docTypeArbeitserlaubnis: "Çalışma izni",
    docTypeGesundheitszeugnis: "Sağlık sertifikası",
    docTypeSonstiges: "Diğer",
    workerDocsHeading: "Kayıtlı Belgeler",
    workerDocsEmpty: "Belge kayıtlı değil.",
    workerAkteLabel: "Çalışan Dosyası",
    btnUploadWorkerDoc: "Belge yükle",
    btnConfirmUpload: "Yükle",
    docUploadSuccess: "Belge başarıyla yüklendi.",
    confirmDeleteDoc: "Bu belge gerçekten silinsin mi?",
    btnDownloadDoc: "İndir",
    btnDeleteDoc: "Sil",
    imapSectionEyebrow: "Belge Gelen Kutusu",
    imapSectionH4: "Kanıt belgeler için IMAP posta kutusu",
    labelImapHint: "Çalışanlar kanıtlarını bu adrese gönderir. Sistem posta kutusunu birkaç dakikada bir kontrol eder.",
    labelImapHost: "IMAP Host",
    labelImapPort: "IMAP Port",
    labelImapUser: "IMAP Kullanıcı Adı",
    labelImapPass: "IMAP Şifre",
    labelImapFolder: "IMAP Klasör",
    labelImapSsl: "SSL/TLS",
    btnImapTest: "IMAP bağlantısını test et",
    imapTestOk: "Bağlantı başarılı!",
    imapTestFail: "Bağlantı başarısız",
    navDevices: "Cihazlar",
    devicesEyebrow: "Donanım",
    devicesH3: "Akıllı Kutular ve OSDP Cihazlar",
    devicesHint: "Her akıllı kutu her 30–60 s'de bir sinyal gönderir. >90 s sinyal yok = çevrimdışı.",
    btnAddDevice: "Cihaz ekle",
    addDeviceEyebrow: "Yeni Cihaz",
    addDeviceH3: "Cihaz kaydet",
    labelDeviceName: "Ad",
    labelDeviceLocation: "Konum",
    labelDeviceType: "Tip / Protokol",
    btnDeviceRegister: "Cihazı kaydet ve API anahtarı oluştur",
    deviceOnline: "Çevrimiçi",
    deviceOffline: "Çevrimdışı",
    deviceNeverSeen: "Henüz sinyal yok",
    alertInstallUnavailable: "Kurulum bu tarayıcıda şu an mevcut değil. Chrome veya Edge'de tarayıcı menüsünden 'Uygulamayı kur' seçin.",
    alertSessionExpired: "Oturum süresi doldu. Lütfen tekrar giriş yapın.",
    alertDeleteWorkerFailed: "Calisan silinemedi: {error}",
    alertRestoreWorkerFailed: "Calisan geri yuklenemedi: {error}",
    alertAppLinkCreateFailed: "Uygulama baglantisi olusturulamadi: {error}",
    promptResetPinFor: "{name} icin yeni rozet PIN (4-8 rakam):",
    alertPinMustDigits: "PIN 4 ila 8 rakamdan olusmalıdır.",
    alertPinResetSuccessFor: "{name} icin PIN basariyla sifirlandi.",
    alertPinResetFailed: "PIN sifirlanamazdi: {error}",
    alertPhotoOverrideApproved: "Fotograf gecersiz kilma onaylandi. Calisan verileri kaydedildi.",
    alertPhotoOverrideApproveFailed: "Onay basarisiz oldu: {error}",
    alertPhotoOverrideRejectReasonRequired: "Reddetme nedeni gereklidir.",
    alertPhotoOverrideRejected: "Fotograf gecersiz kilma reddedildi.",
    alertPhotoOverrideRejectFailed: "Reddetme basarisiz oldu: {error}",
    alertDocEmailSaveFailed: "Belge e-postası kaydedilemedi: {error}",
    alertCompanyDeleted: "{name} firmasi silindi.",
    alertCompanyDeleteFailed: "{name} firmasi silinemedi: {error}",
    alertCompanyLocked: "{name} firmasi kilitlendi.",
    alertCompanyUnlocked: "{name} icin kilit kaldirildi.",
    alertCompanyStatusChangeFailed: "{name} icin durum degisikligi basarisiz oldu: {error}",
    alertBrandingPresetSaveFailed: "Tasarim on ayari kaydedilemedi: {error}",
    alertPasswordMinLength: "Sifre en az 4 karakter olmalidir.",
    alertTurnstileCreateFailed: "Turnike olusturulamadi: {error}",
    alertTurnstilePasswordUpdated: "Turnike sifresi guncellendi.",
    alertTurnstilePasswordResetFailed: "Sifre sifirlama basarisiz oldu: {error}",
    alertApiKeyRotationFailed: "API anahtar rotasyonu basarisiz oldu: {error}",
    alertTurnstileToggleFailed: "Turnike degistirilemedi: {error}",
    alertWorkerDeletedCannotEdit: "Silinen calisanlar duzenlenemez.",
    alertDataCopied: "Veriler kopyalandi.",
    alertPrintWindowFailed: "Yazdir penceresi acilamadi.",
    alertAppLinkCopied: "Uygulama baglantisi kopyalandi.",
    alertQrNotReadyYet: "QR kodu olusturuluyor. Lutfen kisa sure sonra tekrar deneyin.",
    alertAccessBookingFailed: "Erisim kaydedilemedi: {error}",
    alertWorkerSaveFailed: "Calisan kaydedilemedi: {error}",
    alertPhotoMatchFailed: "Fotograf karsilastirmasi basarisiz ({score}%). Kaydetme engellendi. Lutfen fotografi yeniden cekin veya bir superadmin ile iletisime gecin.",
    alertOverrideReasonTooShort: "Gecersiz kilma nedeni cok kisa. Lutfen en az 8 karakter girin.",
    alertPhotoOverrideRequested: "Fotograf gecersiz kilma talebinde bulunuldu (Onay ID: {id}).\nDegisiklik kaydedilmeden once ikinci bir superadmin onaylamalidir.",
    alertBadgePinInvalid: "Rozet PIN 4 ila 8 rakamdan olusmalıdır.",
    alertDuplicatePhysicalCardId: "Bu fiziksel kart kimligini baska bir calisana atanmistir.",
    alertPhotoOverrideSuperadminOnly: "Fotograf gecersiz kilma yalnizca superadminler icin izinlidir.",
    alertPhotoOverrideReasonRequired: "Lutfen fotograf gecersiz kilma icin yeterli bir neden belirtin.",
    alertInvoiceSavedSendFailed: "Fatura kaydedildi, gonderim basarisiz oldu: {error}",
    alertInvoiceNumberDuplicate: "{number} fatura numarasi zaten kullaniliyor. Lutfen baska bir numara kullanin.",
    alertInvoiceSendFailed: "Fatura gonderilemedi: {error}",
    alertInvoiceNumberLength: "Fatura numarasi 3 ila 64 karakter arasinda olmalidir.",
    alertInvoiceDateInvalid: "Fatura tarihi veya vade tarihi gecersiz.",
    alertInvoiceDueDateBeforeIssue: "Vade tarihi fatura tarihinden once olamaz.",
    alertInvoiceVatRange: "KDV 0 ile 100 arasinda olmalidir.",
    alertApprovalRejectReasonRequired: "Gerekcesiz reddetmeye izin verilmiyor.",
    alertApprovalConfirmed: "Onay dogrulandi ve islem gerceklestirildi.",
    alertApprovalRejected: "Onay reddedildi.",
    alertApprovalUpdated: "Onay guncellendi.",
    alertApprovalActionFailed: "Onay islemi basarisiz oldu: {error}",
    alertInvoiceRetrySentDeadLetter: "Fatura basariyla yeniden gonderildi ve dead-letter kuyrugundan kaldirildi.",
    alertInvoiceRetrySent: "Fatura basariyla yeniden gonderildi.",
    alertInvoiceRetryFailed: "Yeniden gonderim basarisiz oldu: {error}",
    alertDeadLetterResolveApprovalRequested: "Onay talep edildi ({id}). Ikinci bir superadmin onaylamalidir.",
    alertDeadLetterResolveFailed: "Dead-letter davasi cozulemedi: {error}",
    alertGenericError: "Hata: {error}",
    alertCollectionsStatusChangeFailed: "Durum degisikligi basarisiz oldu: {error}",
    alertActionFailed: "Islem basarisiz oldu: {error}",
    alertInvoiceHistoryLoadFailed: "Gecmis yuklenemedi: {error}",
    alertAccessExportFailed: "Erisim gunlugu disa aktarimi basarisiz oldu: {error}",
    alertWorkerExportFailed: "Calisan listesi disa aktarimi basarisiz oldu: {error}",
    alertSettingsSaveFailed: "Ayarlar kaydedilemedi: {error}",
    alertSystemRepairDone: "Sistem onarimi gerceklestirildi.",
    alertSystemRepairFailed: "Sistem onarimi basarisiz oldu: {error}",
    alertBrandingLoaded: "BauKometra markasi yuklendi. Simdi Admin Ayarlari'nda kaydet dugmesine tiklayin.",
    alertBrandingLoadFailed: "Marka yuklenemedi: {error}",
    alertBrandingAltLoaded: "Alternatif BauKometra markasi yuklendi. Simdi Admin Ayarlari'nda kaydet dugmesine tiklayin.",
    alertBrandingAltLoadFailed: "Alternatif marka yuklenemedi: {error}",
    alertDayCloseAckFailed: "Gun sonu onaylanamadi: {error}",
    alertOtpRequired: "Bu hesap icin 2FA aktif. Lutfen OTP kodunu girin.",
    alertOtpInvalid: "OTP kodu gecersiz veya suresi dolmus. Lutfen yeni kod girin.",
    alertTooManyAttempts: "Cok fazla basarisiz deneme. Lutfen 10 dakika bekleyin ve tekrar deneyin.",
    alertForbiddenTenantHost: "Bu erisim yalnizca onaylanan sirket domaini uzerinden izinlidir.",
    alertSupportCompanyMismatch: "Bu giris secilen sirketle eslesmiyor. Lutfen isaretlenen sirketin sirket admini kullanin.",
    alertLoginCompanyLocked: "Bu sirket kilitli. Lutfen once acik faturalari odeyin veya superadminde kilidi kaldiriniz.",
    alertInvalidCredentials: "Kullanici adi veya sifre yanlis. Lutfen bilgileri kontrol edin ve tekrar deneyin.",
    alertAdminIpNotAllowed: "Bu IP'den admin erisimi izin verilmiyor.",
    alertLoginScopeMismatch: "Erisim turu hesapla uyusmuyor. Lutfen sunucu-admin / sirket-admini dogru secin.",
    alertLoginHttp405: "Giris basarisiz: 405. Giris istegi su anda {target} adresine dusuyor. GitHub Pages icin on yuz Render backend'inizi kullanmalidir.",
    alertLoginFailed: "Giris basarisiz oldu: {error}",
    alertPasswordResetEnterUsername: "Lutfen once kullanici adi veya e-posta girin.",
    alertPasswordResetSent: "Eslesen bir hesap bulunursa, bir sifirlama e-postasi gonderildi.",
    alertPasswordResetFailed: "Sifre sifirlama baslatılamadı: {error}",
    alertPasswordSetSuccess: "Sifre basariyla ayarlandi. Artik giris yapabilirsiniz.",
    alertPasswordResetLinkFailed: "Sifirlama baglantisi kullanılamadi: {error}",
    alertPasswordChanged: "Sifre degistirildi. Lutfen yeniden giris yapin.",
    alertPasswordChangeFailed: "Sifre degisikligi basarisiz oldu: {error}",
    alert2faSetupFailed: "2FA kurulumu basarisiz oldu: {error}",
    alert2faEnableFailed: "2FA etkinlestirilemedi: {error}",
    alertDeviceDeleteFailed: "Silme hatasi: {error}",
    alertCompanyCreateFailed: "Firma olusturulamadi: {error}",
    alert2faDisableFailed: "2FA devre disi birakilamadi: {error}",
    alertExportFailed: "Disa aktarma basarisiz: {error}",
    alertNoDemoCompany: "Demo verileri icin aktif firma bulunamadi.",
    alertDemoModeInvalid: "Gecersiz mod. Lutfen replace veya append kullanin.",
    alertDemoLoadFailed: "Demo verileri yuklenemedi: {error}",
    alertImportSuccess: "Iceri aktarma basariyla uygulanmadi.",
    alertImportFailed: "Iceri aktarma basarisiz: {error}",
    alertCsvExportFailed: "CSV disa aktarma basarisiz: {error}",
    alertIncidentExportFailed: "Olay disa aktarma basarisiz: {error}",
    alertSelectInvoiceForRetry: "Lutfen kuyrukta en az bir fatura secin.",
    alertBulkRetryDone: "Toplu yeniden deneme tamamlandi. Gonderilen: {sent}, Basarisiz: {failed}, Atlanan: {skipped}",
    alertBulkRetryFailed: "Toplu yeniden deneme basarisiz oldu: {error}",
    alertNoCriticalCases: "Simdilik kritik durum yok (Skor >= 70).",
    alertCriticalBulkRetryDone: "Kritik toplu yeniden deneme tamamlandi. Gonderilen: {sent}, Basarisiz: {failed}, Atlanan: {skipped}",
    alertCriticalBulkRetryFailed: "Kritik toplu yeniden deneme basarisiz oldu: {error}",
    alertDesktopInstallFailed: "Masa ustu kurulumu baslatılamadi.",
    alertSubcompanyCreateFailed: "Taeron olusturulamadi: {error}",
    alertDeleteFailed: "Silme hatasi: {error}",
    alertStatusChangeFailed: "Durum degistirme hatasi: {error}",
    alertReassignmentDone: "Yeniden atama tamamlandi. Eslesmeler: {count}",
    alertReassignmentFailed: "Yeniden atama basarisiz oldu: {error}",
    btnPrintBadge: "Rozet yazdır",
    greetingMorning: "Günaydın",
    greetingDay: "İyi günler",
    greetingEvening: "İyi akşamlar",
    greetingNight: "İyi geceler",
    greetingSuffix: "İyi çalışmalar!",
    adminWorkerAppSectionTitle: "Çalışan Uygulaması",
    adminWorkerAppSectionCopy: "Çalışan uygulamasının tamamını kontrol eder: giriş, dijital kimlik ve telefonda QR kullanımı.",
    adminWorkerAppPinLockHint: "2 dakika etkisizlikten sonra çalışanın kimliği görmek için rozet PIN'ini yeniden girmesi gerekir.",
    optPlanDayPassRecommended: "Ziyaretçi kartı (önerilen)",
    optPlanMonthlySite: "Aylık şantiye başına",
    optPlanPerWorker: "Çalışan başına",
    optPlanFlatCompany: "Firma başına sabit",
    optPlanDayPassPrice: "Ziyaretçi kartı (19 EUR/gün)",
    loginForgotPassword: "Sifremi unuttum",
    legalImpressum: "Yasal bilgilendirme",
    legalPrivacy: "Gizlilik",
    legalCloseTitle: "Kapat",
    legalFallbackEmpty: "Metin bulunamadi.",
    invoiceMgmtTitle: "Fatura yonetimi",
    invoiceMgmtCopy: "Acik ve odenmis faturalari goruntuleyin. Firma kilitlerini otomatik kaldirmak icin faturayi odendi olarak isaretleyin. Tum islemler denetim kaydina yazilir.",
    invoiceOpsEyebrow: "Operasyon",
    invoiceOpsH3: "Gonderim SLA ve hata durumu",
    invoiceSendEyebrow: "Gonderim",
    invoiceSendH3: "Basarisiz e-postalar kuyrugu",
    optRetryAll: "Tum basarisiz gonderimler",
    optRetryPriority: "Once oncelik",
    optRetryMaxed: "Maksimum deneme siniri",
    optRetryTodayFailed: "Bugun basarisiz",
    invoiceRetryTopIssuesOnly: "Sadece en onemli sorunlarim",
    btnRetryCriticalSend: "Sadece kritikleri hemen gonder",
    btnRetryExportCsv: "Kuyruk CSV",
    btnIncidentExportCsv: "Olay CSV",
    btnRetryBulkSend: "Secilenleri yeniden gonder",
    invoiceApprovalsEyebrow: "Onaylar",
    invoiceApprovalsH3: "Kritik islemler icin dort goz onayi",
    optApprovalAllActions: "Tum islem tipleri",
    optApprovalBulkRetry: "Toplu tekrar deneme",
    optApprovalDeadLetterResolve: "Dead-letter cozum",
    legalSectionEyebrow: "Hukuki",
    legalSectionTitle: "Yasal bilgilendirme ve gizlilik",
    labelImpressumText: "Yasal bilgilendirme metni",
    labelPrivacyText: "Gizlilik metni",
    legalTextsHint: "Bu metinler giris sayfasinda 'Yasal bilgilendirme' ve 'Gizlilik' altinda gorunur.",
    labelCompanyDocumentEmail: "Dokuman e-postasi",
    labelBrandingPreset: "Marka on ayari",
    optBrandingConstruction: "Insaat",
    optBrandingIndustry: "Sanayi",
    optBrandingPremium: "Premium",
    optPlanStarter: "Starter (49 EUR)",
    optPlanProfessional: "Professional (99 EUR)",
    optPlanEnterprise: "Enterprise (199 EUR)",
    accessFeedbackCheckin: "Giriş onaylandı",
    badgePinHint: "Mitarbeiter uygulamasında rozet girişi yalnızca Badge-ID ve bu PIN ile çalışır. Düzenlerken buradan yeni bir PIN ayarlayabilirsiniz.",
    badgePinPlaceholder: "4 ila 8 rakam",
    bulkSelectAll: "Tümünü seç",
    btnDayCloseAcknowledge: "Gün sonunu onayla",
    btnExportCompanyDocEmails: "Belge e-postalarını dışa aktar",
    btnLoadAltBrand: "Alternatifi yükle",
    btnLoadDefaultBrand: "Varsayılan markayı yükle",
    cameraNotStarted: "Kamera henüz başlatılmadı.",
    complianceEyebrow: "Uyumluluk",
    complianceH3: "Belge durumu",
    dayCloseCommentLabel: "Gün sonu yorumu",
    dayCloseCommentPlaceholder: "Örn. Vardiya amiri bilgilendirildi",
    deadLetterEyebrow: "Dead-Letter",
    deadLetterH3: "Manuel çözüm gerektiren faturalar",
    filterByCompanyPlaceholder: "Firmaya göre filtrele…",
    filterQueueByCompanyPlaceholder: "Kuyruğu firmaya göre filtrele…",
    formSectionAppFeaturesEyebrow: "Uygulama Özellikleri",
    formSectionBrandingEyebrow: "Fatura Tasarımı",
    formSectionBrandingH4: "Renkler & Marka",
    formSectionEmailEyebrow: "E-Posta",
    formSectionPlatformEyebrow: "Platform",
    formSectionPlatformH4: "Kimlik & İşletici",
    formSectionSecurityH4: "Erişim & İzolasyon",
    formSectionSmtpH4: "SMTP Gönderim",
    invoiceLogoHint: "Fatura logosu aynı zamanda sistem ikonu ve çalışan uygulaması ikonu olarak kullanılır.",
    invoicePreviewEyebrow: "Önizleme",
    invoicePreviewH3: "Göndermeden önce faturayı kontrol et",
    maxAgeFilterPlaceholder: "Maks yaş dakika cinsinden (0 = hepsi)",
    optDeviceOsdp: "OSDP (RS-485)",
    optDeviceTcp: "TCP/IP Akıllı Kutu",
    optDeviceWiegand: "Wiegand Okuyucu",
    optPinLockActive: "Aktif – PIN kilidi telefon paylaşımını önler",
    optPinLockDisabled: "Devre dışı – Rozet her zaman erişilebilir",
    optRoleCompanyAdmin: "Firma Admini",
    optRoleSuperAdmin: "Süper Admin",
    optWorkerAppActive: "Aktif – Rozet, QR ve rozet girişi etkin",
    optWorkerAppLocked: "Kilitli – Mobil uygulama devre dışı",
    photoAdjustHelp: "Fotoğrafı kaydırarak rozetin sağ tarafına düzgün oturtun.",
    photoOverrideH3: "Bekleyen fotoğraf geçersiz kılma onayları",
    photoRequiredHint: "Zorunlu: Fotoğraf olmadan rozet kaydedilemez.",
    photoSharpenLabel: "Keskinlik:",
    photoWhiteBgLabel: "Arka plan tamamen beyaz (aktif)",
    photoZoomCropLabel: "Yakınlaştır / Kırp",
    recentAuditEyebrow: "Denetim",
    recentAuditH3: "Son sistem olayları",
    rentalModelLabel: "Kiralama modeli",
    sectionSecurityEyebrow: "Güvenlik",
    statusLoading: "Durum yükleniyor…",
    sysAlertActionBtn: "Faturalara git",
    sysAlertDefaultText: "Kritik fatura gönderim hataları mevcut.",
    sysAlertHeading: "Kritik Gönderim Sorunu",
    turnstileCountLabel: "Turnike sayısı",
    turnstilePasswordLabel: "Turnike başlangıç şifresi",
    workerAppEnabledLabel: "Mobil rozet uygulaması (dijital rozet + QR)",
    workerPassLockLabel: "Rozeti PIN kilidiyle güvenli hale getir",
    workerSearchPlaceholder: "Ara: İsim, Badge-ID, Şantiye …",
    confirmDeleteCompanyText: "{name} firmasını ve tüm ilişkili kayıtları sil?\n\nTamam = tam silme (çalışanlar, alt yükleniciler ve loglar dahil)\nİptal = silme",
    confirmLockCompany: "{name} firmasını şimdi kilitle? Bu firmanın firma yöneticisi, turnike ve çalışan uygulaması engellenir.",
    confirmUnlockCompany: "{name} için kilidi kaldır? Firma daha sonra tekrar giriş yapabilir.",
    confirmDeleteWorkerBulk: "{count} çalışan gerçekten silinsin mi?",
    confirmApiKeyRotate: "Bu turnike için API anahtarı şimdi yeniden oluşturulsun mu? Mevcut anahtar hemen geçerliliğini yitirir.",
    confirmSystemRepair: "Sistem tamiri yapılsın mı? Süresi dolan oturumlar ve giriş kilitleri temizlenir.",
    confirmApprovalDecision: "Onay {id} gerçekten {decision} edilsin mi?",
    confirmDeadLetterRetry: "Ölü mektup faturası şimdi yeniden gönderilsin mi?",
    confirmDeadLetterResolve: "Ölü mektup durumu çözüldü olarak işaretlensin mi?",
    confirmInvoicePaid: "Bu fatura ödendi olarak işaretlensin mi? Firma kilidi kaldırılabilir.",
    confirmInvoiceRetry: "Fatura şimdi yeniden gönderilsin mi?",
    confirmInvoicePaidSimple: "Fatura şimdi ödendi olarak işaretlensin mi?",
    confirmDemoInvoices: "Demo faturaları da oluşturulsun mu?",
    confirmDemoAccessLogs: "Demo giriş logları oluşturulsun mu?",
    confirmDemoReplace: "Demo verileri {name} için şimdi REPLACE modunda yüklensin mi? Mevcut çalışanlar, alt yükleniciler ve loglar değiştirilir.",
    confirmDemoAppend: "Demo verileri {name} için şimdi APPEND modunda ek olarak yüklensin mi?",
    confirmExportAudit: "Denetim logu dışa aktarmaya eklensin mi?",
    confirmExportDayClose: "Gün kapanış onayları dışa aktarmaya eklensin mi?",
    confirmExportDeleted: "Silinen girişler dışa aktarmaya eklensin mi?",
    confirmExportAll: "Süper admin olarak: tüm sistemi dışa aktar? (Hayır = yalnızca mevcut firma)",
    confirmExportDownload: "Sistem dışa aktarması{scope} şimdi indirilsin mi?",
    confirmLogout: "Gerçekten çıkış yapılsın mı?",
    confirmImportChangesOnly: "Yalnızca değişiklikler içe aktarılsın mı? (Önerilen)",
    confirmBulkRetrySelected: "{count} seçili fatura şimdi yeniden gönderilsin mi?",
    confirmBulkRetryCritical: "{count} kritik fatura şimdi yeniden gönderilsin mi?",
    confirmPhotoMatchFailed: "Fotoğraf karşılaştırması başarısız ({score}%). Yalnızca süper admin riskle kayıt yapabilir. Yine de kaydedilsin mi?",
    promptDocEmail: "{name} için belge e-postası belirle",
    promptTurnstilePassword: "{name} için turnike şifresi belirle (en az 4 karakter):",
    promptTurnstilePasswordNew: "Yeni turnike şifresi belirle (en az 4 karakter):",
    promptCopyData: "Kopyalanacak veriler:",
    promptAppLink: "Çalışan için uygulama bağlantısı:",
    promptPhotoOverrideReason: "Foto geçersiz kılma nedeni girin (en az 8 karakter):",
    promptNewPassword: "Yeni şifre girin (en az 8 karakter):",
    promptTfaCode: "Lütfen kimlik doğrulayıcı uygulamanızdan 6 haneli kodu girin:",
    promptTfaDisableCode: "Devre dışı bırakmak için mevcut 2FA kodunu girin:",
    promptDemoMode: "{name} için demo verileri: modu girin (replace veya append)",
    promptRejectionReason: "Red gerekçesi (zorunlu):",
    promptRejectApproval: "Lütfen red gerekçesini girin:",
    invoiceTitle: "Fatura",
    invoiceAltLogo: "Firma logosu",
    invoiceLabelNumber: "Fatura numarası:",
    invoiceLabelDate: "Fatura tarihi:",
    invoiceLabelDue: "Son ödeme tarihi:",
    invoiceLabelCustomer: "Müşteri:",
    invoiceLabelContact: "İlgili kişi:",
    invoiceLabelPeriod: "Hizmet dönemi:",
    invoiceColService: "Hizmet / Çalışan",
    invoiceColAccess: "Girişler",
    invoiceColNet: "Net tutar",
    invoiceRowUnknown: "Bilinmiyor",
    invoiceRowPlan: "Plan: {label}",
    invoiceTotalNet: "Net ara toplam",
    invoiceTotalVat: "KDV ({rate} %)",
    invoiceTotalGross: "Toplam tutar",
    invoiceFooter: "İşbirliğiniz için teşekkür ederiz. Bu fatura dijital olarak oluşturulmuş ve doğrudan gönderilebilir.",
    invoiceHistoryEmpty: "Henüz gönderilmiş veya kaydedilmiş fatura yok.",
    invoiceHistoryRecipient: "Alıcı:",
    invoiceHistoryTotal: "Toplam:",
    invoiceHistoryCreated: "Oluşturuldu:",
    invoiceHistorySent: "Gönderildi:",
    invoiceHistoryError: "Hata:",
    tfaStatusActive: "2FA etkin",
    tfaStatusInactive: "2FA etkin değil",
    tfaBtnSetup: "2FA kur",
    tfaBtnEnable: "2FA etkinleştir",
    tfaBtnDisable: "2FA devre dışı bırak",
    tfaQrHint: "Kimlik doğrulama uygulamasıyla sırrı kur:",
    tfaSecretLabel: "Manuel kod:",
    tfaCodeLabel: "Uygulamadan kod:",
    tfaCodePlaceholder: "6 haneli kod",
    tfaEnableHint: "Kimlik doğrulama uygulamanızdan 6 haneli kodu girin ve 'Etkinleştir' düğmesine tıklayın.",
    tfaEmailLabel: "OTP kodları için e-posta adresi",
    tfaEmailPlaceholder: "admin@example.com",
    tfaActivateOneClickHint: "E-posta adresinizi girin ve Etkinleştir'e tıklayın. Her girişte e-postasınıza bir kod gönderilecektir.",
    alertTfaActivated: "2FA etkinleştirildi.",
    alertTfaEmailRequired: "2FA'yı etkinleştirmeden önce lütfen bir e-posta adresi girin.",
    alertOtpSent: "Güvenlik kodu e-postasınıza gönderildi. Lütfen gelen kutunuzu kontrol edin.",
    loginOtpSentNotice: "Kod e-posta ile gönderildi – gelen kutunuzu kontrol edin",
    loginOtpBackBtn: "← Geri",
  },
  ar: {
    authEyebrow: "صفحة تسجيل الدخول",
    authTitle: "تسجيل دخول آمن إلى BauPass Control",
    authCopy: "يمتلك المشرف العام التحكم الكامل بالنظام. مديرو الشركات يرون شركتهم فقط. تسجيل دخول البوابة الدوّارة يوفر وضع وصول سريع.",
    authPlatform: "المنصة",
    authOperator: "المشغّل",
    authTurnstile: "نقطة نهاية البوابة",
    loginUsernameLabel: "اسم المستخدم",
    loginUsernamePlaceholder: "اسم المستخدم",
    loginPasswordLabel: "كلمة المرور",
    loginPasswordPlaceholder: "أدخل كلمة المرور",
    loginOtpLabel: "رمز OTP (إذا كانت 2FA مفعلة)",
    loginOtpPlaceholder: "123456",
    uiLanguageLabel: "اللغة",
    loginScopeLabel: "نوع الوصول",
    loginScopeAuto: "تلقائي",
    loginScopeServerAdmin: "مدير الخادم",
    loginScopeCompanyAdmin: "مدير الشركة",
    loginScopeTurnstile: "البوابة الدوارة",
    supportReadOnlyAlert: "تسجيل الدعم هذا للقراءة فقط. التغييرات محظورة في هذه الجلسة.",
    supportReadOnlyTitle: "وضع الدعم: قراءة فقط",
    supportLoginActive: "جلسة الدعم نشطة:",
    supportCompanyFallback: "الشركة",
    supportStartedBy: "بدأه",
    supportReadOnlyNotice: "بعد تسجيل الدخول سيكون الوصول للقراءة فقط.",
    supportModeLabel: "وضع الدعم:",
    supportReadOnlyFor: "قراءة فقط لشركة",
    supportCompanyLoginConfirmPrefix: "الانتقال إلى تسجيل الدخول للشركة",
    supportCompanyLoginConfirmSuffix: "؟ سيتم تسجيل خروج جلسة المشرف الحالية. بعد ذلك سيكون الوصول للقراءة فقط.",
    supportCompanyLoginOpenedPrefix: "تم فتح تسجيل الدخول للشركة",
    supportCompanyLoginOpenedSuffix: "يرجى الآن تسجيل الدخول بمدير الشركة. ستبقى هذه الجلسة للقراءة فقط.",
    supportModeReadOnlyLine: "وضع الدعم نشط: قراءة فقط.",
    supportReadOnlyShort: "وضع الدعم: قراءة فقط.",
    loginButton: "تسجيل الدخول",
    demoAccessTitle: "حسابات تجريبية",
    demoSuperAdmin: "مشرف عام: superadmin / 1234",
    demoCompanyAdmin: "مدير شركة: firma / 1234",
    demoTurnstile: "البوابة: drehkreuz / 1234",
    desktopAppTitle: "تطبيق سطح المكتب",
    desktopInstallHint: "يمكن تثبيت هذه البوابة على الكمبيوتر كتطبيق محلي.",
    desktopInstallButton: "ثبّت على هذا الكمبيوتر",
    // Shell nav+buttons (full, AR - RTL)
    sidebarEyebrow: "بوابة الشركة",
    sidebarCopy: "تسجيل العمال، التقاط الصور، إنشاء بطاقات هوية رقمية وإدارة البوابات الدوارة.",
    sidebarCardTitle: "وضع التأجير",
    sidebarCardStrong: "دعم متعدد الشركات",
    sidebarCardDesc: "تدير كل شركة بناء فريقها بشكل مستقل. يحتفظ المشرف العام بالتحكم في النظام.",
    navDashboard: "لوحة التحكم",
    navWorkers: "العمال",
    navBadge: "بطاقة الهوية",
    navAccess: "الدخول",
    navInvoices: "الفواتير",
    navAdmin: "الإدارة",
    topbarEyebrow: "حالة النظام",
    topbarHeading: "بطاقات البناء والتحكم في الدخول",
    btnSeedData: "إدخال بيانات تجريبية",
    btnExport: "تصدير النظام",
    btnImport: "استيراد النظام",
    btnLogout: "تسجيل خروج آمن",
    dashEyebrow: "نموذج محسّن",
    dashHeading: "بطاقات رقمية مع صورة و Badge ID وتسجيل الدخول عند البوابة",
    dashSubtext: "مصمّم لتأجير شركات البناء.",
    dashBadge1: "التقاط الصور",
    dashBadge2: "سجل الدخول",
    dashBadge3: "تعدد المستأجرين",
    reportingEyebrow: "التقارير",
    reportingH3: "حالة الدفع والتجميد",
    accessWeekEyebrow: "7 أيام",
    accessWeekH3: "الدخول يومياً",
    recentEyebrow: "النشاط الأخير",
    recentH3: "سجل الدخول",
    porterLiveEmpty: "سيظهر آخر دخول عند أول تسجيل.",
    workersFormEyebrow: "البيانات الرئيسية",
    workersFormH3: "تسجيل عامل أو زائر",
    labelType: "النوع",
    optWorker: "عامل",
    optVisitor: "زائر",
    labelFirm: "الشركة",
    labelSubcompany: "شركة فرعية",
    optNoSubcompany: "بدون شركة فرعية",
    labelNewSubcompany: "شركة فرعية جديدة",
    btnAddSubcompany: "إنشاء شركة فرعية",
    labelFirstName: "الاسم الأول",
    labelLastName: "اسم العائلة",
    labelInsuranceNumber: "رقم التأمين",
    labelRoleField: "المنصب",
    labelSite: "موقع البناء",
    siteFieldHint: "أدخل العنوان الكامل – مطلوب للتحقق من الموقع عند تسجيل الدخول",
    labelPhysicalCard: "معرّف البطاقة المادية (NFC/RFID)",
    labelValidUntil: "صالح حتى",
    labelVisitorCompany: "شركة الزائر",
    labelVisitPurpose: "غرض الزيارة",
    labelHostName: "جهة الاتصال في الموقع",
    labelVisitEndAt: "نهاية الزيارة",
    visitorHint: "الزوار صالحون لبضع ساعات أو حتى نهاية اليوم. يتم تسجيل خروج الدخلات المفتوحة تلقائيًا في منتصف الليل على أبعد تقدير، لكن البطاقة تُحفظ لأغراض التقارير.",
    labelWorkerStatus: "الحالة",
    optStatusActive: "نشط",
    optStatusLocked: "محظور",
    optStatusExpired: "منتهي الصلاحية",
    labelBadgePin: "Badge PIN لتسجيل الدخول",
    btnStartCamera: "تشغيل الكاميرا",
    btnCapturePhoto: "التقاط صورة",
    btnUploadPhoto: "رفع صورة",
    btnPhotoUp: "↑ للأعلى",
    btnPhotoLeft: "← يسار",
    btnPhotoRight: "يمين →",
    btnPhotoDown: "للأسفل ↓",
    btnPhotoReset: "إعادة ضبط الموضع",
    btnWorkerSubmit: "حفظ العامل وإنشاء البطاقة",
    btnWorkerCancelEdit: "إلغاء التحرير",
    workersListEyebrow: "السجلات",
    workersListH3: "العمال المسجلون",
    btnWorkerCsv: "تنزيل قائمة العمال PDF",
    btnBulkDelete: "حذف المحددة",
    btnBulkActive: "نشط",
    btnBulkInactive: "غير نشط",
    btnBulkCancel: "إلغاء",
    badgeEyebrow: "بطاقة رقمية",
    badgeH3: "معاينة البطاقة",
    badgeEmptyState: "يرجى إنشاء أو اختيار عامل أولاً.",
    badgeScanEyebrow: "مساعدة المسح",
    badgeScanH3: "رمز البطاقة",
    badgeScanEmpty: "لم يتم اختيار بطاقة.",
    badgeTitleVisitor: "بطاقة زائر رقمية",
    badgeTitleDayPass: "تصريح يومي رقمي للموقع",
    badgeTitleRegular: "بطاقة هوية رقمية للموقع",
    badgeUnknownCompany: "شركة غير معروفة",
    badgeQrHint: "امسح الرمز، ثبّت التطبيق وافتح البطاقة مباشرةً.",
    badgeLabelBadgeId: "Badge-ID",
    badgeMetaQrFunc: "وظيفة QR",
    badgeMetaQrFuncVal: "تثبيت تطبيق العمال",
    badgeMetaRoleLabel: "الدور في النظام",
    badgePhotoUploadHint: "التقط أو ارفع صورة",
    appPinLabel: "PIN التطبيق",
    pinNotRequired: "غير مطلوب",
    pinSet: "مضبوط",
    pinMissing: "مفقود",
    cardLabel: "البطاقة",
    cardUnassigned: "غير مخصصة",
    btnEdit: "تعديل",
    btnDelete: "حذف",
    btnRestore: "استعادة",
    btnAppLink: "رابط التطبيق",
    btnResetPin: "إعادة تعيين PIN",
    confirmDeleteWorker: "حذف العامل الآن؟",
    alertDeleteWorkerFailed: "تعذر حذف العامل: {error}",
    alertRestoreWorkerFailed: "تعذر استعادة العامل: {error}",
    alertAppLinkCreateFailed: "تعذر إنشاء رابط التطبيق: {error}",
    promptResetPinFor: "PIN جديد للشارة لـ {name} (4-8 أرقام):",
    alertPinMustDigits: "يجب أن يكون PIN من 4 إلى 8 أرقام.",
    alertPinResetSuccessFor: "تمت إعادة تعيين PIN لـ {name} بنجاح.",
    alertPinResetFailed: "تعذر إعادة تعيين PIN: {error}",
    alertPhotoOverrideApproved: "تمت الموافقة على تجاوز الصورة. تم حفظ بيانات العامل.",
    alertPhotoOverrideApproveFailed: "فشل الموافقة: {error}",
    alertPhotoOverrideRejectReasonRequired: "سبب الرفض مطلوب.",
    alertPhotoOverrideRejected: "تم رفض تجاوز الصورة.",
    alertPhotoOverrideRejectFailed: "فشل الرفض: {error}",
    alertDocEmailSaveFailed: "تعذر حفظ بريد المستندات: {error}",
    alertCompanyDeleted: "تم حذف الشركة {name}.",
    alertCompanyDeleteFailed: "تعذر حذف الشركة {name}: {error}",
    alertCompanyLocked: "تم قفل الشركة {name}.",
    alertCompanyUnlocked: "تم رفع القفل عن {name}.",
    alertCompanyStatusChangeFailed: "فشل تغيير حالة {name}: {error}",
    alertBrandingPresetSaveFailed: "تعذر حفظ إعداد التصميم: {error}",
    alertPasswordMinLength: "يجب أن تتكون كلمة المرور من 4 أحرف على الأقل.",
    alertTurnstileCreateFailed: "تعذر إنشاء البوابة: {error}",
    alertTurnstilePasswordUpdated: "تم تحديث كلمة مرور البوابة.",
    alertTurnstilePasswordResetFailed: "فشل إعادة تعيين كلمة المرور: {error}",
    alertApiKeyRotationFailed: "فشل تدوير مفتاح API: {error}",
    alertTurnstileToggleFailed: "تعذر تبديل البوابة: {error}",
    alertWorkerDeletedCannotEdit: "لا يمكن تعديل العمال المحذوفين.",
    alertDataCopied: "تم نسخ البيانات.",
    alertPrintWindowFailed: "تعذر فتح نافذة الطباعة.",
    alertAppLinkCopied: "تم نسخ رابط التطبيق.",
    alertQrNotReadyYet: "رمز QR لا يزال قيد الإنشاء. يرجى المحاولة مرة أخرى بعد لحظة.",
    alertAccessBookingFailed: "تعذر حجز الدخول: {error}",
    alertWorkerSaveFailed: "تعذر حفظ بيانات العامل: {error}",
    alertPhotoMatchFailed: "فشلت مقارنة الصور ({score}٪). تم حظر الحفظ. يرجى التقاط صورة جديدة أو الاتصال بمسؤول النظام.",
    alertOverrideReasonTooShort: "سبب التجاوز قصير جداً. يرجى إدخال 8 أحرف على الأقل.",
    alertPhotoOverrideRequested: "تم طلب تجاوز الصورة (معرف الموافقة: {id}).\nيجب على مسؤول نظام ثانٍ الموافقة قبل حفظ التغيير.",
    alertBadgePinInvalid: "يجب أن يتكون رمز PIN للبطاقة من 4 إلى 8 أرقام.",
    alertDuplicatePhysicalCardId: "معرف البطاقة الفعلية هذا مخصص لعامل آخر بالفعل.",
    alertPhotoOverrideSuperadminOnly: "تجاوز الصورة مسموح فقط للمسؤولين العامين.",
    alertPhotoOverrideReasonRequired: "يرجى تقديم سبب كافٍ لتجاوز الصورة.",
    alertInvoiceSavedSendFailed: "تم حفظ الفاتورة، فشل الإرسال: {error}",
    alertInvoiceNumberDuplicate: "رقم الفاتورة {number} مستخدم بالفعل. يرجى استخدام رقم آخر.",
    alertInvoiceSendFailed: "تعذر إرسال الفاتورة: {error}",
    alertInvoiceNumberLength: "يجب أن يكون رقم الفاتورة بين 3 و64 حرفاً.",
    alertInvoiceDateInvalid: "تاريخ الفاتورة أو تاريخ الاستحقاق غير صالح.",
    alertInvoiceDueDateBeforeIssue: "لا يمكن أن يسبق تاريخ الاستحقاق تاريخ الفاتورة.",
    alertInvoiceVatRange: "يجب أن تكون نسبة الضريبة بين 0 و100.",
    alertApprovalRejectReasonRequired: "الرفض بدون سبب غير مسموح به.",
    alertApprovalConfirmed: "تمت الموافقة وتنفيذ الإجراء.",
    alertApprovalRejected: "تم رفض الموافقة.",
    alertApprovalUpdated: "تم تحديث الموافقة.",
    alertApprovalActionFailed: "فشل إجراء الموافقة: {error}",
    alertInvoiceRetrySentDeadLetter: "تم إعادة إرسال الفاتورة بنجاح وإزالتها من قائمة الانتظار.",
    alertInvoiceRetrySent: "تم إعادة إرسال الفاتورة بنجاح.",
    alertInvoiceRetryFailed: "فشلت إعادة الإرسال: {error}",
    alertDeadLetterResolveApprovalRequested: "تم طلب الموافقة ({id}). يجب على مسؤول نظام ثانٍ التأكيد.",
    alertDeadLetterResolveFailed: "تعذر حل حالة القائمة الميتة: {error}",
    alertGenericError: "خطأ: {error}",
    alertCollectionsStatusChangeFailed: "فشل تغيير الحالة: {error}",
    alertActionFailed: "فشل الإجراء: {error}",
    alertInvoiceHistoryLoadFailed: "تعذر تحميل السجل: {error}",
    alertAccessExportFailed: "فشل تصدير سجل الدخول: {error}",
    alertWorkerExportFailed: "فشل تصدير قائمة العمال: {error}",
    alertSettingsSaveFailed: "تعذر حفظ الإعدادات: {error}",
    alertSystemRepairDone: "تم تنفيذ إصلاح النظام.",
    alertSystemRepairFailed: "فشل إصلاح النظام: {error}",
    alertBrandingLoaded: "تم تحميل علامة BauKometra التجارية. الآن انقر فوق حفظ في إعدادات الإدارة.",
    alertBrandingLoadFailed: "تعذر تحميل العلامة التجارية: {error}",
    alertBrandingAltLoaded: "تم تحميل البديل لعلامة BauKometra التجارية. الآن انقر فوق حفظ في إعدادات الإدارة.",
    alertBrandingAltLoadFailed: "تعذر تحميل العلامة التجارية البديلة: {error}",
    alertDayCloseAckFailed: "تعذر تأكيد إغلاق اليوم: {error}",
    alertOtpRequired: "المصادقة الثنائية مفعلة لهذا الحساب. يرجى إدخال رمز OTP.",
    alertOtpInvalid: "رمز OTP غير صالح أو منتهي الصلاحية. يرجى إدخال رمز جديد.",
    alertTooManyAttempts: "محاولات فاشلة كثيرة جداً. يرجى الانتظار 10 دقائق والمحاولة مرة أخرى.",
    alertForbiddenTenantHost: "هذا الوصول مسموح فقط عبر نطاق الشركة المعتمد.",
    alertSupportCompanyMismatch: "هذا تسجيل الدخول لا يطابق الشركة المحددة. يرجى استخدام مسؤول الشركة للشركة المحددة.",
    alertLoginCompanyLocked: "هذه الشركة مقفلة. يرجى تسديد الفواتير المعلقة أو رفع القفل في لوحة المسؤول العام.",
    alertInvalidCredentials: "اسم المستخدم أو كلمة المرور غير صحيحة. يرجى التحقق من البيانات والمحاولة مرة أخرى.",
    alertAdminIpNotAllowed: "الوصول كمسؤول من هذا العنوان IP غير مسموح.",
    alertLoginScopeMismatch: "نوع الوصول لا يطابق الحساب. يرجى اختيار مسؤول الخادم / مسؤول الشركة بشكل صحيح.",
    alertLoginHttp405: "فشل تسجيل الدخول: 405. طلب تسجيل الدخول يصل حالياً إلى {target}. بالنسبة لـ GitHub Pages، يجب أن يستخدم الواجهة الأمامية خلفيتك على Render.",
    alertLoginFailed: "فشل تسجيل الدخول: {error}",
    alertPasswordResetEnterUsername: "يرجى إدخال اسم المستخدم أو البريد الإلكتروني أولاً.",
    alertPasswordResetSent: "إذا تم العثور على حساب مطابق، فقد تم إرسال بريد إلكتروني لإعادة التعيين.",
    alertPasswordResetFailed: "تعذر بدء إعادة تعيين كلمة المرور: {error}",
    alertPasswordSetSuccess: "تم تعيين كلمة المرور بنجاح. يمكنك الآن تسجيل الدخول.",
    alertPasswordResetLinkFailed: "تعذر استخدام رابط إعادة التعيين: {error}",
    alertPasswordChanged: "تم تغيير كلمة المرور. يرجى تسجيل الدخول مجدداً.",
    alertPasswordChangeFailed: "فشل تغيير كلمة المرور: {error}",
    alert2faSetupFailed: "فشل إعداد المصادقة الثنائية: {error}",
    alert2faEnableFailed: "تعذر تفعيل المصادقة الثنائية: {error}",
    alertDeviceDeleteFailed: "خطأ في الحذف: {error}",
    alertCompanyCreateFailed: "تعذر إنشاء الشركة: {error}",
    alert2faDisableFailed: "تعذر إلغاء تفعيل المصادقة الثنائية: {error}",
    alertExportFailed: "فشل التصدير: {error}",
    alertNoDemoCompany: "لم يتم العثور على شركة نشطة لبيانات العرض التوضيحي.",
    alertDemoModeInvalid: "وضع غير صالح. يرجى استخدام replace أو append.",
    alertDemoLoadFailed: "تعذر تحميل بيانات العرض التوضيحي: {error}",
    alertImportSuccess: "تم تطبيق الاستيراد بنجاح.",
    alertImportFailed: "فشل الاستيراد: {error}",
    alertCsvExportFailed: "فشل تصدير CSV: {error}",
    alertIncidentExportFailed: "فشل تصدير الحوادث: {error}",
    alertSelectInvoiceForRetry: "يرجى تحديد فاتورة واحدة على الأقل في قائمة الانتظار.",
    alertBulkRetryDone: "اكتمال إعادة المحاولة الجماعية. تم الإرسال: {sent}، فشل: {failed}، تم التخطي: {skipped}",
    alertBulkRetryFailed: "فشلت إعادة المحاولة الجماعية: {error}",
    alertNoCriticalCases: "لا توجد حالات حرجة حالياً (النتيجة >= 70).",
    alertCriticalBulkRetryDone: "اكتمال إعادة المحاولة الجماعية الحرجة. تم الإرسال: {sent}، فشل: {failed}، تم التخطي: {skipped}",
    alertCriticalBulkRetryFailed: "فشلت إعادة المحاولة الجماعية الحرجة: {error}",
    alertDesktopInstallFailed: "تعذر بدء تثبيت سطح المكتب.",
    alertSubcompanyCreateFailed: "تعذر إنشاء المقاول الفرعي: {error}",
    alertDeleteFailed: "خطأ في الحذف: {error}",
    alertStatusChangeFailed: "خطأ في تغيير الحالة: {error}",
    alertReassignmentDone: "اكتمل إعادة التعيين. المطابقات: {count}",
    alertReassignmentFailed: "فشل إعادة التعيين: {error}",
    detailCloseTitle: "إغلاق",
    detailPhotoAlt: "صورة العامل",
    detailCheckinBtn: "تسجيل دخول",
    detailCheckoutBtn: "تسجيل خروج",
    accessFormEyebrow: "البوابة الدوارة",
    accessFormH3: "تسجيل دخول وخروج",
    labelAccessBadge: "Badge ID أو عامل",
    labelAccessDir: "الاتجاه",
    labelAccessGate: "البوابة",
    labelAccessNote: "ملاحظة",
    optCheckin: "دخول",
    optCheckout: "خروج",
    btnAccessSubmit: "تسجيل الدخول",
    porterEmpty: "مشهد الحارس المباشر: اختر عاملاً وسجّل الدخول.",
    accessLogEyebrow: "سجل الدخول",
    accessLogH3: "دخول وخروج بتوقيت زمني",
    labelFrom: "من",
    labelTo: "إلى",
    labelFilterDir: "الاتجاه",
    labelFilterGate: "البوابة",
    optAllDir: "الكل",
    btnApplyFilter: "تطبيق الفلتر",
    btnResetFilter: "إعادة ضبط الفلتر",
    btnAccessCsv: "تصدير CSV الدخول",
    dailyReportEyebrow: "التقرير اليومي",
    dailyReportH3: "لكل بوابة",
    btnPrintDaily: "طباعة التقرير اليومي",
    btnPrintVisitorWeekly: "طباعة قائمة الزيار الأسبوعية",
    hourlyEyebrow: "التحليل بالساعة",
    hourlyH3: "دخول/خروج لكل ساعة",
    warningsEyebrow: "تحذيرات",
    warningsH3: "دخول بدون خروج",
    invListEyebrow: "الفواتير",
    invListH3: "الفواتير وحالة الدفع",
    optAllStatus: "جميع الحالات",
    optDraft: "مسودة",
    optSent: "مرسلة",
    optOverdue: "متأخرة",
    optPaid: "مدفوعة",
    optFailed: "خطأ",
    btnRefreshList: "تحديث",
    inkassoEyebrow: "التحصيل",
    inkassoH3: "متأخرة، مسبق الحظر، محظورة",
    optAllPositions: "جميع العناصر المفتوحة",
    optPrelock: "مسبق الحظر",
    optLocked: "محظور بالفعل",
    adminEyebrow: "مركز الإدارة",
    adminH3: "النظام والتكوين",
    sysStatusEyebrow: "حالة النظام",
    sysStatusH3: "وصول طارئ وإصلاح",
    btnRefreshStatus: "تحديث الحالة",
    btnRepairSessions: "إصلاح الجلسات",
    superAdminEyebrow: "التحكم الكامل",
    superAdminH3: "إعدادات المشرف العام",
    labelPlatformName: "اسم المنصة",
    labelOperatorName: "المشغّل",
    labelTurnstileEp: "نقطة نهاية API للبوابة",
    labelSmtpHost: "SMTP Host",
    labelSmtpPort: "SMTP Port",
    labelSmtpUser: "مستخدم SMTP",
    labelSmtpPass: "كلمة مرور SMTP",
    labelSenderEmail: "بريد المرسل",
    labelSenderName: "اسم المرسل",
    labelTls: "TLS نشط",
    optTlsYes: "نعم",
    optTlsNo: "لا",
    btnTestSmtp: "إرسال بريد اختبار",
    optYes: "نعم",
    optNo: "لا",
    labelIpWhitelist: "قائمة بيضاء IP للمشرف",
    labelEnforceDomain: "فرض دومين الشركة",
    btnSaveAdmin: "حفظ إعدادات المشرف",
    companyNewEyebrow: "المستأجرون",
    companyNewH3: "إضافة شركة بناء جديدة",
    labelCompanyName: "اسم الشركة",
    labelCompanyContact: "جهة الاتصال",
    labelBillingEmail: "بريد الفواتير",
    labelAccessHost: "نطاق وصول الشركة",
    labelPlan: "الخطة",
    labelCompanyStatus: "الحالة",
    optCompanyActive: "نشط",
    optCompanyTest: "تجريبي",
    optCompanyPaused: "موقوف مؤقتاً",
    optCompanyLocked: "محظور بسبب تأخر الدفع",
    labelCompanyAdminPassword: "كلمة مرور المشرف الأولية",
    companyAdminPasswordPlaceholder: "مثال: آمن!2025",
    btnCreateCompany: "إنشاء شركة",
    accountEyebrow: "الحساب",
    accountH3: "تغيير كلمة المرور",
    labelCurrentPassword: "كلمة المرور الحالية",
    labelNewPassword: "كلمة مرور جديدة",
    btnChangePassword: "تغيير كلمة المرور",
    tfaEyebrow: "عاملان",
    tfaH3: "إدارة 2FA",
    companiesListEyebrow: "المستأجرون",
    companiesListH3: "الشركات والخطط",
    invFormEyebrow: "الفواتير",
    invFormH3: "إرسال بشعار وتصميم",
    labelInvFirm: "الشركة",
    labelInvNumber: "رقم الفاتورة",
    labelInvRecipient: "بريد المستلم",
    labelInvDate: "تاريخ الفاتورة",
    labelInvDueDate: "تاريخ الاستحقاق",
    labelInvPeriod: "فترة الخدمة",
    labelInvDescription: "وصف الخدمة",
    labelInvNet: "المبلغ الصافي (EUR)",
    labelInvVat: "ضريبة القيمة المضافة (%)",
    btnPrintInvoice: "طباعة الفاتورة / حفظ PDF",
    btnSendInvoice: "إرسال الفاتورة بالبريد الإلكتروني",
    btnUpdatePreview: "تحديث المعاينة",
    auditEyebrow: "سجل الأمان",
    auditH3: "سجل المراجعة",
    labelAuditEvent: "نوع الحدث",
    labelAuditRole: "الدور",
    btnAuditCsv: "تصدير CSV المراجعة",
    reportingPaid: "مدفوعة",
    reportingOpen: "مفتوحة",
    reportingOverdue: "متأخرة",
    reportingInvoicesLabel: "فواتير",
    reportingOverdueTotal: "إجمالي المتأخرات",
    reportingLockedCompanies: "شركات محظورة",
    reportingAutoSuspensions30d: "تعليق تلقائي (30 يوم)",
    reportingGeneratedAt: "تم الإنشاء",
    reportingNoOverdueCompanies: "لا توجد شركات متأخرة.",
    reportingFallbackCompany: "الشركة",
    reportingOverdueInvoicesLabel: "فاتورة متأخرة",
    reportingNoAccessDataLast7Days: "لا توجد بيانات دخول للأيام السبعة الأخيرة.",
    reportingCheckin: "دخول",
    reportingCheckout: "خروج",
    navDocuments: "المستندات",
    docInboxEyebrow: "البريد الوارد",
    docInboxH3: "المستندات الواردة بالبريد",
    btnDocInboxRefresh: "تحديث",
    btnDocInboxSync: "مزامنة البريد",
    btnDocInboxPoll: "جلب البريد الآن",
    btnDocInboxRematch: "إعادة تعيين",
    docEmailInfoLabel: "بريد المستندات (يرسل العمال وثائقهم هنا):",
    btnCopyEmail: "نسخ",
    btnCopyEmailDone: "تم النسخ!",
    docInboxHint: "يرسل العمال وثائقهم إلى عنوان البريد المخصص. يقوم الحارس بتعيين المرفقات للعامل هنا.",
    docAssignEyebrow: "تعيين",
    docAssignH3: "تعيين مرفق لعامل",
    docInboxEmpty: "لا يوجد بريد غير معالج.",
    docInboxEmailFrom: "من",
    docInboxEmailSubject: "الموضوع",
    docInboxEmailDate: "التاريخ",
    docInboxAttachments: "المرفقات",
    btnAssignDoc: "تعيين",
    btnDismissEmail: "رفض",
    docAssignWorkerLabel: "اختر عاملاً",
    docAssignTypeLabel: "نوع المستند",
    docAssignNotesLabel: "ملاحظات (اختياري)",
    btnConfirmAssign: "تعيين المستند",
    docAssignSuccess: "تم تعيين المستند بنجاح.",
    docTypeMindestlohnnachweis: "إثبات الحد الأدنى للأجر",
    docTypePersonalausweis: "هوية / جواز سفر",
    docTypeSozialversicherungsnachweis: "شهادة الضمان الاجتماعي",
    docTypeArbeitserlaubnis: "تصريح عمل",
    docTypeGesundheitszeugnis: "شهادة صحية",
    docTypeSonstiges: "أخرى",
    workerDocsHeading: "المستندات المحفوظة",
    workerDocsEmpty: "لا توجد مستندات.",
    workerAkteLabel: "ملف العامل",
    btnUploadWorkerDoc: "رفع مستند",
    btnConfirmUpload: "رفع",
    docUploadSuccess: "تم رفع المستند بنجاح.",
    confirmDeleteDoc: "هل تريد حذف هذا المستند؟",
    btnDownloadDoc: "تنزيل",
    btnDeleteDoc: "حذف",
    imapSectionEyebrow: "بريد المستندات",
    imapSectionH4: "صندوق IMAP للوثائق",
    labelImapHint: "يرسل العمال وثائقهم إلى هذا العنوان. يفحص النظام البريد كل بضع دقائق.",
    labelImapHost: "IMAP Host",
    labelImapPort: "IMAP Port",
    labelImapUser: "مستخدم IMAP",
    labelImapPass: "كلمة مرور IMAP",
    labelImapFolder: "مجلد IMAP",
    labelImapSsl: "SSL/TLS",
    btnImapTest: "اختبار اتصال IMAP",
    imapTestOk: "الاتصال ناجح!",
    imapTestFail: "فشل الاتصال",
    navDevices: "الأجهزة",
    devicesEyebrow: "الأجهزة",
    devicesH3: "الصناديق الذكية وأجهزة OSDP",
    devicesHint: "يرسل كل صندوق ذكي نبضة كل 30-60 ثانية. لا إشارة >90 ثانية = غير متصل.",
    btnAddDevice: "إضافة جهاز",
    addDeviceEyebrow: "جهاز جديد",
    addDeviceH3: "تسجيل جهاز",
    labelDeviceName: "الاسم",
    labelDeviceLocation: "الموقع",
    labelDeviceType: "النوع / البروتوكول",
    btnDeviceRegister: "تسجيل الجهاز وإنشاء مفتاح API",
    deviceOnline: "متصل",
    deviceOffline: "غير متصل",
    deviceNeverSeen: "لا نبضة بعد",
    alertInstallUnavailable: "التثبيت غير متاح في هذا المتصفح الآن. في Chrome أو Edge اختر 'تثبيت التطبيق' من قائمة المتصفح.",
    alertSessionExpired: "انتهت الجلسة. يرجى تسجيل الدخول مجدداً.",
    btnPrintBadge: "طباعة البطاقة",
    greetingMorning: "صباح الخير",
    greetingDay: "مرحباً",
    greetingEvening: "مساء الخير",
    greetingNight: "تصبح على خير",
    greetingSuffix: "وردية طيبة!",
    adminWorkerAppSectionTitle: "تطبيق العمال",
    adminWorkerAppSectionCopy: "يتحكم في تطبيق العمال بالكامل: تسجيل الدخول والهوية الرقمية واستخدام QR.",
    adminWorkerAppPinLockHint: "بعد دقيقتين من عدم النشاط يجب على العامل إدخال رمز PIN لرؤية بطاقته.",
    optPlanDayPassRecommended: "بطاقة زائر (موصى به)",
    optPlanMonthlySite: "شهرياً لكل موقع",
    optPlanPerWorker: "لكل عامل",
    optPlanFlatCompany: "ثابت لكل شركة",
    optPlanDayPassPrice: "بطاقة زائر (19 EUR/يوم)",
    loginForgotPassword: "نسيت كلمة المرور",
    legalImpressum: "البيانات القانونية",
    legalPrivacy: "الخصوصية",
    legalCloseTitle: "إغلاق",
    legalFallbackEmpty: "لا يوجد نص متاح.",
    invoiceMgmtTitle: "إدارة الفواتير",
    invoiceMgmtCopy: "اعرض الفواتير المفتوحة والمدفوعة. ضع علامة مدفوعة لرفع حظر الشركة تلقائياً. يتم تسجيل كل الأنشطة في سجل التدقيق.",
    invoiceOpsEyebrow: "العمليات",
    invoiceOpsH3: "SLA الإرسال وحالة الأخطاء",
    invoiceSendEyebrow: "الإرسال",
    invoiceSendH3: "قائمة انتظار الرسائل الفاشلة",
    optRetryAll: "كل الإرسالات الفاشلة",
    optRetryPriority: "الأولوية أولاً",
    optRetryMaxed: "تم الوصول للحد الأقصى",
    optRetryTodayFailed: "فشل اليوم",
    invoiceRetryTopIssuesOnly: "فقط أهم مشاكلي",
    btnRetryCriticalSend: "إرسال الحرجة الآن فقط",
    btnRetryExportCsv: "CSV قائمة الانتظار",
    btnIncidentExportCsv: "CSV الحوادث",
    btnRetryBulkSend: "إعادة إرسال المحدد",
    invoiceApprovalsEyebrow: "الموافقات",
    invoiceApprovalsH3: "مراجعة الأربعة أعين للإجراءات الحرجة",
    optApprovalAllActions: "كل أنواع الإجراءات",
    optApprovalBulkRetry: "إعادة محاولة جماعية",
    optApprovalDeadLetterResolve: "حل الرسائل المتعثرة",
    legalSectionEyebrow: "قانوني",
    legalSectionTitle: "البيانات القانونية والخصوصية",
    labelImpressumText: "نص البيانات القانونية",
    labelPrivacyText: "سياسة الخصوصية",
    legalTextsHint: "تظهر هذه النصوص في صفحة تسجيل الدخول تحت 'البيانات القانونية' و'الخصوصية'.",
    labelCompanyDocumentEmail: "بريد المستندات",
    labelBrandingPreset: "إعداد الهوية",
    optBrandingConstruction: "إنشاءات",
    optBrandingIndustry: "صناعة",
    optBrandingPremium: "مميز",
    optPlanStarter: "Starter (49 EUR)",
    optPlanProfessional: "Professional (99 EUR)",
    optPlanEnterprise: "Enterprise (199 EUR)",
    accessFeedbackCheckin: "تم تسجيل الدخول",
    badgePinHint: "تسجيل الدخول بالبطاقة في تطبيق العمال يعمل فقط بـ Badge-ID وهذا الرمز السري. عند التعديل يمكنك تعيين رمز سري جديد هنا.",
    badgePinPlaceholder: "4 إلى 8 أرقام",
    bulkSelectAll: "تحديد الكل",
    btnDayCloseAcknowledge: "تأكيد إغلاق اليوم",
    btnExportCompanyDocEmails: "تصدير بريد المستندات",
    btnLoadAltBrand: "تحميل البديل",
    btnLoadDefaultBrand: "تحميل العلامة الافتراضية",
    cameraNotStarted: "الكاميرا لم تبدأ بعد.",
    complianceEyebrow: "الامتثال",
    complianceH3: "حالة المستندات",
    dayCloseCommentLabel: "تعليق إغلاق اليوم",
    dayCloseCommentPlaceholder: "مثال: تم إبلاغ مشرف الوردية",
    deadLetterEyebrow: "Dead-Letter",
    deadLetterH3: "فواتير تحتاج حلًا يدويًا",
    filterByCompanyPlaceholder: "تصفية حسب الشركة…",
    filterQueueByCompanyPlaceholder: "تصفية قائمة الانتظار حسب الشركة…",
    formSectionAppFeaturesEyebrow: "ميزات التطبيق",
    formSectionBrandingEyebrow: "تصميم الفاتورة",
    formSectionBrandingH4: "الألوان والعلامة التجارية",
    formSectionEmailEyebrow: "البريد الإلكتروني",
    formSectionPlatformEyebrow: "المنصة",
    formSectionPlatformH4: "الهوية والمشغّل",
    formSectionSecurityH4: "الوصول والعزل",
    formSectionSmtpH4: "إرسال SMTP",
    invoiceLogoHint: "يُستخدم شعار الفاتورة أيضًا كأيقونة النظام وأيقونة تطبيق العمال.",
    invoicePreviewEyebrow: "معاينة",
    invoicePreviewH3: "مراجعة الفاتورة قبل الإرسال",
    maxAgeFilterPlaceholder: "الحد الأقصى للعمر بالدقائق (0 = الكل)",
    optDeviceOsdp: "OSDP (RS-485)",
    optDeviceTcp: "TCP/IP Smart-Box",
    optDeviceWiegand: "قارئ Wiegand",
    optPinLockActive: "نشط – قفل PIN يمنع مشاركة الهاتف",
    optPinLockDisabled: "معطّل – البطاقة متاحة دائمًا",
    optRoleCompanyAdmin: "مدير شركة",
    optRoleSuperAdmin: "مشرف عام",
    optWorkerAppActive: "نشط – البطاقة وQR وتسجيل الدخول مفعّلة",
    optWorkerAppLocked: "مقفل – التطبيق المحمول معطّل",
    photoAdjustHelp: "حرك الصورة بعد الالتقاط لتناسب الجانب الأيمن من البطاقة.",
    photoOverrideH3: "طلبات تجاوز الصورة المعلقة",
    photoRequiredHint: "مطلوب: لا يمكن حفظ البطاقة بدون صورة.",
    photoSharpenLabel: "الحدة:",
    photoWhiteBgLabel: "الخلفية بيضاء بالكامل (نشط)",
    photoZoomCropLabel: "تكبير / قص",
    recentAuditEyebrow: "المراجعة",
    recentAuditH3: "أحدث أحداث النظام",
    rentalModelLabel: "نموذج الإيجار",
    sectionSecurityEyebrow: "الأمان",
    statusLoading: "جارٍ تحميل الحالة…",
    sysAlertActionBtn: "الذهاب إلى الفواتير",
    sysAlertDefaultText: "توجد أخطاء حرجة في إرسال الفواتير.",
    sysAlertHeading: "مشكلة إرسال حرجة",
    turnstileCountLabel: "عدد البوابات",
    turnstilePasswordLabel: "كلمة مرور البوابة الأولية",
    workerAppEnabledLabel: "تطبيق البطاقة المحمولة (بطاقة رقمية + QR)",
    workerPassLockLabel: "تأمين البطاقة بقفل PIN",
    workerSearchPlaceholder: "بحث: الاسم، Badge-ID، الموقع …",
    confirmDeleteCompanyText: "حذف الشركة {name} وجميع السجلات المرتبطة؟\n\nموافق = حذف كامل (بما في ذلك الموظفون والمقاولون الفرعيون والسجلات)\nإلغاء = لا تحذف",
    confirmLockCompany: "قفل الشركة {name} الآن؟ سيتم حظر مسؤول الشركة والدوار وتطبيق الموظف.",
    confirmUnlockCompany: "رفع قفل {name} الآن؟ يمكن للشركة تسجيل الدخول مجدداً بعد ذلك.",
    confirmDeleteWorkerBulk: "هل تريد فعلاً حذف {count} موظف؟",
    confirmApiKeyRotate: "إعادة إنشاء مفتاح API لهذا الدوار الآن؟ سيفقد المفتاح الحالي صلاحيته فوراً.",
    confirmSystemRepair: "تشغيل إصلاح النظام؟ سيتم تنظيف الجلسات المنتهية وأقفال تسجيل الدخول.",
    confirmApprovalDecision: "هل تريد فعلاً {decision} الموافقة {id}؟",
    confirmDeadLetterRetry: "إعادة إرسال فاتورة Dead-Letter الآن؟",
    confirmDeadLetterResolve: "وضع علامة حل على حالة Dead-Letter؟",
    confirmInvoicePaid: "وضع علامة مدفوعة على هذه الفاتورة؟ سيتم رفع أي قفل عن الشركة.",
    confirmInvoiceRetry: "إعادة إرسال الفاتورة الآن؟",
    confirmInvoicePaidSimple: "وضع علامة مدفوعة على الفاتورة الآن؟",
    confirmDemoInvoices: "هل يجب أيضاً إنشاء فواتير تجريبية؟",
    confirmDemoAccessLogs: "هل يجب إنشاء سجلات دخول تجريبية؟",
    confirmDemoReplace: "تحميل البيانات التجريبية لـ {name} الآن في وضع REPLACE؟ سيتم استبدال الموظفين والمقاولين الفرعيين والسجلات الموجودة.",
    confirmDemoAppend: "تحميل البيانات التجريبية لـ {name} الآن في وضع APPEND إضافياً؟",
    confirmExportAudit: "تضمين سجل التدقيق في التصدير؟",
    confirmExportDayClose: "تضمين إيصالات إغلاق اليوم في التصدير؟",
    confirmExportDeleted: "تضمين الإدخالات المحذوفة في التصدير؟",
    confirmExportAll: "كمشرف عام: تصدير النظام بأكمله؟ (لا = الشركة الحالية فقط)",
    confirmExportDownload: "تنزيل تصدير النظام{scope} الآن؟",
    confirmLogout: "هل تريد فعلاً تسجيل الخروج؟",
    confirmImportChangesOnly: "استيراد التغييرات فقط؟ (موصى به)",
    confirmBulkRetrySelected: "إعادة إرسال {count} فاتورة محددة الآن؟",
    confirmBulkRetryCritical: "إعادة إرسال {count} فاتورة حرجة الآن؟",
    confirmPhotoMatchFailed: "فشل مقارنة الصور ({score}%). المشرف العام فقط يمكنه الحفظ مع المخاطر. الحفظ على أي حال؟",
    promptDocEmail: "تحديد بريد المستندات لـ {name}",
    promptTurnstilePassword: "تحديد كلمة مرور الدوار لـ {name} (4 أحرف على الأقل):",
    promptTurnstilePasswordNew: "تحديد كلمة مرور دوار جديدة (4 أحرف على الأقل):",
    promptCopyData: "البيانات للنسخ:",
    promptAppLink: "رابط التطبيق للموظف:",
    promptPhotoOverrideReason: "يرجى إدخال سبب تجاوز الصورة (8 أحرف على الأقل):",
    promptNewPassword: "أدخل كلمة مرور جديدة (8 أحرف على الأقل):",
    promptTfaCode: "يرجى إدخال رمز 6 أرقام من تطبيق المصادقة:",
    promptTfaDisableCode: "يرجى إدخال رمز 2FA الحالي للتعطيل:",
    promptDemoMode: "بيانات تجريبية لـ {name}: أدخل الوضع (replace أو append)",
    promptRejectionReason: "سبب الرفض (مطلوب):",
    promptRejectApproval: "يرجى إدخال سبب الرفض:",
    invoiceTitle: "فاتورة",
    invoiceAltLogo: "شعار الشركة",
    invoiceLabelNumber: "رقم الفاتورة:",
    invoiceLabelDate: "تاريخ الفاتورة:",
    invoiceLabelDue: "تاريخ الاستحقاق:",
    invoiceLabelCustomer: "العميل:",
    invoiceLabelContact: "جهة الاتصال:",
    invoiceLabelPeriod: "فترة الخدمة:",
    invoiceColService: "الخدمة / الموظف",
    invoiceColAccess: "الدخولات",
    invoiceColNet: "المبلغ الصافي",
    invoiceRowUnknown: "غير معروف",
    invoiceRowPlan: "الخطة: {label}",
    invoiceTotalNet: "المجموع الجزئي الصافي",
    invoiceTotalVat: "ضريبة القيمة المضافة ({rate} %)",
    invoiceTotalGross: "المبلغ الإجمالي",
    invoiceFooter: "شكراً للتعاون. تم إنشاء هذه الفاتورة رقمياً ويمكن إرسالها مباشرة.",
    invoiceHistoryEmpty: "لا توجد فواتير مرسلة أو محفوظة بعد.",
    invoiceHistoryRecipient: "المستلم:",
    invoiceHistoryTotal: "الإجمالي:",
    invoiceHistoryCreated: "تم الإنشاء:",
    invoiceHistorySent: "تم الإرسال:",
    invoiceHistoryError: "خطأ:",
    tfaStatusActive: "المصادقة الثنائية مفعلة",
    tfaStatusInactive: "المصادقة الثنائية غير مفعلة",
    tfaBtnSetup: "إعداد المصادقة الثنائية",
    tfaBtnEnable: "تفعيل المصادقة الثنائية",
    tfaBtnDisable: "تعطيل المصادقة الثنائية",
    tfaQrHint: "إعداد السر باستخدام تطبيق المصادقة:",
    tfaSecretLabel: "الرمز اليدوي:",
    tfaCodeLabel: "الرمز من التطبيق:",
    tfaCodePlaceholder: "رمز 6 أرقام",
    tfaEnableHint: "أدخل الرمز المكون من 6 أرقام من تطبيق المصادقة وانقر 'تفعيل'.",
    tfaEmailLabel: "عنوان البريد الإلكتروني لرموز OTP",
    tfaEmailPlaceholder: "admin@example.com",
    tfaActivateOneClickHint: "أدخل عنوان بريدك واضغط على تفعيل. سيتم إرسال رمز إلى بريدك عند كل تسجيل دخول.",
    alertTfaActivated: "تم تفعيل التحقق الثنائي.",
    alertTfaEmailRequired: "يرجى إدخال عنوان بريد إلكتروني قبل تفعيل التحقق الثنائي.",
    alertOtpSent: "تم إرسال رمز الأمان إلى بريدك الإلكتروني. يرجى التحقق من صندوق الوارد.",
    loginOtpSentNotice: "تم إرسال الرمز عبر البريد – تحقق من صندوق الوارد",
    loginOtpBackBtn: "← رجوع",
  },
  fr: {
    authEyebrow: "Page de connexion",
    authTitle: "Connexion sécurisée à BauPass Control",
    authCopy: "Le super admin garde le contrôle total du système. Les admins d'entreprise ne voient que leur entreprise. Le login tourniquet offre un mode d'accès rapide.",
    authPlatform: "Plateforme",
    authOperator: "Opérateur",
    authTurnstile: "Point d'accès tourniquet",
    loginUsernameLabel: "Nom d'utilisateur",
    loginUsernamePlaceholder: "Nom d'utilisateur",
    loginPasswordLabel: "Mot de passe",
    loginPasswordPlaceholder: "Saisir le mot de passe",
    loginOtpLabel: "Code OTP (si 2FA activée)",
    loginOtpPlaceholder: "123456",
    uiLanguageLabel: "Langue",
    loginScopeLabel: "Type d'accès",
    loginScopeAuto: "Automatique",
    loginScopeServerAdmin: "Admin serveur",
    loginScopeCompanyAdmin: "Admin entreprise",
    loginScopeTurnstile: "Tourniquet",
    supportReadOnlyAlert: "Cette connexion support est en lecture seule. Les modifications sont bloquées dans cette session.",
    supportReadOnlyTitle: "Mode support : lecture seule",
    supportLoginActive: "Connexion support active :",
    supportCompanyFallback: "Entreprise",
    supportStartedBy: "démarré par",
    supportReadOnlyNotice: "Après la connexion, l'accès est en lecture seule.",
    supportModeLabel: "Mode support :",
    supportReadOnlyFor: "Lecture seule pour",
    supportCompanyLoginConfirmPrefix: "Basculer vers la connexion entreprise pour",
    supportCompanyLoginConfirmSuffix: "? Votre session admin actuelle sera déconnectée. L'accès sera ensuite en lecture seule.",
    supportCompanyLoginOpenedPrefix: "Connexion pour",
    supportCompanyLoginOpenedSuffix: "ouverte. Connectez-vous maintenant avec le compte admin entreprise. Cette session reste en lecture seule.",
    supportModeReadOnlyLine: "Mode support actif : lecture seule.",
    supportReadOnlyShort: "Mode support : lecture seule.",
    loginButton: "Se connecter",
    demoAccessTitle: "Comptes de démonstration",
    demoSuperAdmin: "Super Admin: superadmin / 1234",
    demoCompanyAdmin: "Admin entreprise: firma / 1234",
    demoTurnstile: "Tourniquet: drehkreuz / 1234",
    desktopAppTitle: "Application bureau",
    desktopInstallHint: "Ce portail peut être installé sur votre ordinateur comme une application native.",
    desktopInstallButton: "Installer sur cet ordinateur",
    // Shell
    sidebarEyebrow: "Portail entreprise",
    sidebarCopy: "Enregistrez les travailleurs, prenez des photos, créez des badges numériques et gérez le contrôle d'accès.",
    sidebarCardTitle: "Mode location",
    sidebarCardStrong: "Multi-entreprises",
    sidebarCardDesc: "Chaque entreprise de construction gère son équipe séparément. Le super admin garde le contrôle du système.",
    navDashboard: "Tableau de bord",
    navWorkers: "Travailleurs",
    navBadge: "Badge",
    navAccess: "Accès",
    navInvoices: "Factures",
    navAdmin: "Administration",
    topbarEyebrow: "État du système",
    topbarHeading: "Badges chantier et contrôle d'accès",
    btnSeedData: "Données de démo",
    btnExport: "Exporter le système",
    btnImport: "Importer le système",
    btnLogout: "Déconnexion sécurisée",
    dashEyebrow: "MVP amélioré",
    dashHeading: "Badges numériques avec photo, Badge ID et check-in tourniquet",
    dashSubtext: "Conçu pour la location aux entreprises de construction.",
    dashBadge1: "Prise de photo",
    dashBadge2: "Journal d'accès",
    dashBadge3: "Multi-locataires",
    reportingEyebrow: "Rapports",
    reportingH3: "État de paiement et blocage",
    accessWeekEyebrow: "7 jours",
    accessWeekH3: "Accès quotidien",
    recentEyebrow: "Activité récente",
    recentH3: "Journal d'accès",
    porterLiveEmpty: "Le dernier accès s'affichera ici lors du premier enregistrement.",
    workersFormEyebrow: "Données maîtres",
    workersFormH3: "Enregistrer un travailleur ou visiteur",
    labelType: "Type",
    optWorker: "Travailleur",
    optVisitor: "Visiteur",
    labelFirm: "Entreprise",
    labelSubcompany: "Sous-entreprise",
    optNoSubcompany: "Pas de sous-entreprise",
    labelNewSubcompany: "Nouvelle sous-entreprise",
    btnAddSubcompany: "Créer sous-entreprise",
    labelFirstName: "Prénom",
    labelLastName: "Nom",
    labelInsuranceNumber: "Numéro d'assurance",
    labelRoleField: "Fonction",
    labelSite: "Chantier",
    siteFieldHint: "Saisir l'adresse complète – nécessaire pour la vérification GPS à la connexion",
    labelPhysicalCard: "ID carte physique (NFC/RFID)",
    labelValidUntil: "Valide jusqu'au",
    labelVisitorCompany: "Entreprise du visiteur",
    labelVisitPurpose: "Objet de la visite",
    labelHostName: "Contact sur site",
    labelVisitEndAt: "Fin de visite",
    visitorHint: "Les visiteurs sont valides quelques heures ou jusqu'\u00e0 la fin de la journ\u00e9e. Les entr\u00e9es ouvertes sont automatiquement cl\u00f4tur\u00e9es \u00e0 00h00 au plus tard, la carte est conserv\u00e9e pour les rapports.",
    labelWorkerStatus: "Statut",
    optStatusActive: "Actif",
    optStatusLocked: "Bloqué",
    optStatusExpired: "Expiré",
    labelBadgePin: "Badge PIN pour connexion app",
    btnStartCamera: "Démarrer caméra",
    btnCapturePhoto: "Prendre photo",
    btnUploadPhoto: "Uploader photo",
    btnPhotoUp: "↑ Haut",
    btnPhotoLeft: "← Gauche",
    btnPhotoRight: "Droite →",
    btnPhotoDown: "Bas ↓",
    btnPhotoReset: "Réinitialiser position",
    btnWorkerSubmit: "Sauvegarder travailleur et créer badge",
    btnWorkerCancelEdit: "Annuler l'édition",
    workersListEyebrow: "Enregistrements",
    workersListH3: "Travailleurs enregistrés",
    btnWorkerCsv: "Télécharger liste PDF",
    btnBulkDelete: "Supprimer sélection",
    btnBulkActive: "Statut : actif",
    btnBulkInactive: "Statut : inactif",
    btnBulkCancel: "Annuler",
    badgeEyebrow: "Identité numérique",
    badgeH3: "Aperçu du badge",
    badgeEmptyState: "Veuillez créer ou sélectionner un travailleur d'abord.",
    badgeScanEyebrow: "Aide scan",
    badgeScanH3: "Code badge",
    badgeScanEmpty: "Aucun badge sélectionné.",
    badgeTitleVisitor: "Carte visiteur numérique",
    badgeTitleDayPass: "Laissez-passer journalier numérique chantier",
    badgeTitleRegular: "Badge numérique chantier",
    badgeUnknownCompany: "Entreprise inconnue",
    badgeQrHint: "Scanner le QR, installer l'app et ouvrir le badge directement.",
    badgeLabelBadgeId: "Badge-ID",
    badgeMetaQrFunc: "Fonction QR",
    badgeMetaQrFuncVal: "Installation app travailleurs",
    badgeMetaRoleLabel: "Rôle dans le système",
    badgePhotoUploadHint: "Prendre ou télécharger une photo",
    appPinLabel: "PIN app",
    pinNotRequired: "non requis",
    pinSet: "defini",
    pinMissing: "manquant",
    cardLabel: "Carte",
    cardUnassigned: "non attribuee",
    btnEdit: "Modifier",
    btnDelete: "Supprimer",
    btnRestore: "Restaurer",
    btnAppLink: "Lien app",
    btnResetPin: "Reinitialiser PIN",
    confirmDeleteWorker: "Supprimer ce travailleur ?",
    alertDeleteWorkerFailed: "Le travailleur n'a pas pu etre supprime: {error}",
    alertRestoreWorkerFailed: "Le travailleur n'a pas pu etre restaure: {error}",
    alertAppLinkCreateFailed: "Le lien app n'a pas pu etre cree: {error}",
    promptResetPinFor: "Nouveau PIN badge pour {name} (4-8 chiffres):",
    alertPinMustDigits: "Le PIN doit contenir 4 a 8 chiffres.",
    alertPinResetSuccessFor: "Le PIN pour {name} a ete reinitialise.",
    alertPinResetFailed: "Le PIN n'a pas pu etre reinitialise: {error}",
    alertPhotoOverrideApproved: "Remplacement de photo approuvé. Les données du travailleur ont été sauvegardées.",
    alertPhotoOverrideApproveFailed: "Approbation échouée : {error}",
    alertPhotoOverrideRejectReasonRequired: "Une raison de refus est requise.",
    alertPhotoOverrideRejected: "Remplacement de photo refusé.",
    alertPhotoOverrideRejectFailed: "Refus échoué : {error}",
    alertDocEmailSaveFailed: "L'e-mail de document n'a pas pu etre sauvegardé : {error}",
    alertCompanyDeleted: "La société {name} a été supprimée.",
    alertCompanyDeleteFailed: "La société {name} n'a pas pu etre supprimée : {error}",
    alertCompanyLocked: "La société {name} a été verrouillée.",
    alertCompanyUnlocked: "Le verrouillage de {name} a été levé.",
    alertCompanyStatusChangeFailed: "Le changement de statut de {name} a échoué : {error}",
    alertBrandingPresetSaveFailed: "Le preset de design n'a pas pu etre sauvegardé : {error}",
    alertPasswordMinLength: "Le mot de passe doit contenir au moins 4 caractères.",
    alertTurnstileCreateFailed: "Le tourniquet n'a pas pu etre créé : {error}",
    alertTurnstilePasswordUpdated: "Le mot de passe du tourniquet a été mis à jour.",
    alertTurnstilePasswordResetFailed: "La réinitialisation du mot de passe a échoué : {error}",
    alertApiKeyRotationFailed: "La rotation de la clé API a échoué : {error}",
    alertTurnstileToggleFailed: "Le tourniquet n'a pas pu etre basculé : {error}",
    alertWorkerDeletedCannotEdit: "Les travailleurs supprimés ne peuvent pas etre modifiés.",
    alertDataCopied: "Données copiées.",
    alertPrintWindowFailed: "La fenetre d'impression n'a pas pu etre ouverte.",
    alertAppLinkCopied: "Lien de l'application copié.",
    alertQrNotReadyYet: "Le code QR est encore en cours de génération. Veuillez réessayer dans un moment.",
    alertAccessBookingFailed: "L'accès n'a pas pu etre réservé : {error}",
    alertWorkerSaveFailed: "Le travailleur n'a pas pu etre sauvegardé : {error}",
    alertPhotoMatchFailed: "La comparaison de photos a échoué ({score}%). La sauvegarde est bloquée. Veuillez reprendre la photo ou contacter un superadmin.",
    alertOverrideReasonTooShort: "La raison de remplacement est trop courte. Veuillez saisir au moins 8 caractères.",
    alertPhotoOverrideRequested: "Remplacement de photo demandé (ID d'approbation : {id}).\nUn second superadmin doit approuver le changement avant qu'il soit sauvegardé.",
    alertBadgePinInvalid: "Le PIN du badge doit contenir de 4 à 8 chiffres.",
    alertDuplicatePhysicalCardId: "Cet identifiant de carte physique est déjà attribué à un autre travailleur.",
    alertPhotoOverrideSuperadminOnly: "Le remplacement de photo est uniquement autorisé pour les superadmins.",
    alertPhotoOverrideReasonRequired: "Veuillez fournir une raison suffisante pour le remplacement de photo.",
    alertInvoiceSavedSendFailed: "Facture sauvegardée, envoi échoué : {error}",
    alertInvoiceNumberDuplicate: "Le numéro de facture {number} est déjà utilisé. Veuillez utiliser un autre numéro.",
    alertInvoiceSendFailed: "La facture n'a pas pu etre envoyée : {error}",
    alertInvoiceNumberLength: "Le numéro de facture doit contenir entre 3 et 64 caractères.",
    alertInvoiceDateInvalid: "La date de facture ou la date d'échéance est invalide.",
    alertInvoiceDueDateBeforeIssue: "La date d'échéance ne peut pas etre antérieure à la date de facture.",
    alertInvoiceVatRange: "La TVA doit etre comprise entre 0 et 100.",
    alertApprovalRejectReasonRequired: "Le refus sans raison n'est pas autorisé.",
    alertApprovalConfirmed: "Approbation confirmée et action exécutée.",
    alertApprovalRejected: "L'approbation a été refusée.",
    alertApprovalUpdated: "Approbation mise à jour.",
    alertApprovalActionFailed: "L'action d'approbation a échoué : {error}",
    alertInvoiceRetrySentDeadLetter: "La facture a été renvoyée avec succès et retirée de la file d'attente morte.",
    alertInvoiceRetrySent: "La facture a été renvoyée avec succès.",
    alertInvoiceRetryFailed: "Le renvoi a échoué : {error}",
    alertDeadLetterResolveApprovalRequested: "Approbation demandée ({id}). Un second superadmin doit confirmer.",
    alertDeadLetterResolveFailed: "Le cas de lettre morte n'a pas pu etre résolu : {error}",
    alertGenericError: "Erreur : {error}",
    alertCollectionsStatusChangeFailed: "Le changement de statut a échoué : {error}",
    alertActionFailed: "L'action a échoué : {error}",
    alertInvoiceHistoryLoadFailed: "L'historique n'a pas pu etre chargé : {error}",
    alertAccessExportFailed: "L'exportation du journal d'accès a échoué : {error}",
    alertWorkerExportFailed: "L'exportation de la liste des travailleurs a échoué : {error}",
    alertSettingsSaveFailed: "Les paramètres n'ont pas pu etre sauvegardés : {error}",
    alertSystemRepairDone: "La réparation du système a été exécutée.",
    alertSystemRepairFailed: "La réparation du système a échoué : {error}",
    alertBrandingLoaded: "Marque BauKometra chargée. Cliquez maintenant sur Enregistrer dans les paramètres admin.",
    alertBrandingLoadFailed: "La marque n'a pas pu etre chargée : {error}",
    alertBrandingAltLoaded: "Variante alternative de la marque BauKometra chargée. Cliquez maintenant sur Enregistrer dans les paramètres admin.",
    alertBrandingAltLoadFailed: "La variante de marque alternative n'a pas pu etre chargée : {error}",
    alertDayCloseAckFailed: "La cloture journalière n'a pas pu etre accusée : {error}",
    alertOtpRequired: "La 2FA est active pour ce compte. Veuillez saisir le code OTP.",
    alertOtpInvalid: "Le code OTP est invalide ou expiré. Veuillez saisir un nouveau code.",
    alertTooManyAttempts: "Trop de tentatives échouées. Veuillez attendre 10 minutes et réessayer.",
    alertForbiddenTenantHost: "Cet accès n'est autorisé que via le domaine approuvé de l'entreprise.",
    alertSupportCompanyMismatch: "Cette connexion ne correspond pas à l'entreprise sélectionnée. Veuillez utiliser l'admin de l'entreprise marquée.",
    alertLoginCompanyLocked: "Cette entreprise est verrouillée. Veuillez d'abord régler les factures ouvertes ou lever le verrou dans superadmin.",
    alertInvalidCredentials: "Nom d'utilisateur ou mot de passe incorrect. Veuillez vérifier vos informations et réessayer.",
    alertAdminIpNotAllowed: "L'accès admin depuis cette adresse IP n'est pas autorisé.",
    alertLoginScopeMismatch: "Le type d'accès ne correspond pas au compte. Veuillez sélectionner correctement admin serveur / admin entreprise.",
    alertLoginHttp405: "Connexion échouée : 405. La requete de connexion arrive actuellement sur {target}. Pour GitHub Pages, le frontend doit utiliser votre backend Render.",
    alertLoginFailed: "Connexion échouée : {error}",
    alertPasswordResetEnterUsername: "Veuillez d'abord saisir un nom d'utilisateur ou un e-mail.",
    alertPasswordResetSent: "Si un compte correspondant a été trouvé, un e-mail de réinitialisation a été envoyé.",
    alertPasswordResetFailed: "La réinitialisation du mot de passe n'a pas pu etre démarrée : {error}",
    alertPasswordSetSuccess: "Le mot de passe a été défini avec succès. Vous pouvez maintenant vous connecter.",
    alertPasswordResetLinkFailed: "Le lien de réinitialisation n'a pas pu etre utilisé : {error}",
    alertPasswordChanged: "Mot de passe modifié. Veuillez vous reconnecter.",
    alertPasswordChangeFailed: "Le changement de mot de passe a échoué : {error}",
    alert2faSetupFailed: "La configuration 2FA a échoué : {error}",
    alert2faEnableFailed: "La 2FA n'a pas pu etre activée : {error}",
    alertDeviceDeleteFailed: "Erreur lors de la suppression : {error}",
    alertCompanyCreateFailed: "La société n'a pas pu etre créée : {error}",
    alert2faDisableFailed: "La 2FA n'a pas pu etre desactivée : {error}",
    alertExportFailed: "L'exportation a échoué : {error}",
    alertNoDemoCompany: "Aucune société active trouvée pour les données de démonstration.",
    alertDemoModeInvalid: "Mode invalide. Veuillez utiliser replace ou append.",
    alertDemoLoadFailed: "Les données de démonstration n'ont pas pu etre chargées : {error}",
    alertImportSuccess: "L'importation a été appliquée avec succès.",
    alertImportFailed: "L'importation a échoué : {error}",
    alertCsvExportFailed: "L'exportation CSV a échoué : {error}",
    alertIncidentExportFailed: "L'exportation des incidents a échoué : {error}",
    alertSelectInvoiceForRetry: "Veuillez sélectionner au moins une facture dans la file d'attente.",
    alertBulkRetryDone: "Réessai en masse terminé. Envoyés : {sent}, Échoués : {failed}, Ignorés : {skipped}",
    alertBulkRetryFailed: "Le réessai en masse a échoué : {error}",
    alertNoCriticalCases: "Il n'y a actuellement aucun cas critique (score >= 70).",
    alertCriticalBulkRetryDone: "Réessai en masse critique terminé. Envoyés : {sent}, Échoués : {failed}, Ignorés : {skipped}",
    alertCriticalBulkRetryFailed: "Le réessai en masse critique a échoué : {error}",
    alertDesktopInstallFailed: "L'installation de bureau n'a pas pu etre démarrée.",
    alertSubcompanyCreateFailed: "Le sous-traitant n'a pas pu etre créé : {error}",
    alertDeleteFailed: "Erreur lors de la suppression : {error}",
    alertStatusChangeFailed: "Erreur lors du changement de statut : {error}",
    alertReassignmentDone: "Réaffectation terminée. Correspondances : {count}",
    alertReassignmentFailed: "La réaffectation a échoué : {error}",
    detailCloseTitle: "Fermer",
    detailPhotoAlt: "Photo du travailleur",
    detailCheckinBtn: "Entree (Check-in)",
    detailCheckoutBtn: "Sortie (Check-out)",
    accessFormEyebrow: "Tourniquet",
    accessFormH3: "Check-in et check-out",
    labelAccessBadge: "Badge ID ou travailleur",
    labelAccessDir: "Direction",
    labelAccessGate: "Porte",
    labelAccessNote: "Note",
    optCheckin: "Entrée",
    optCheckout: "Sortie",
    btnAccessSubmit: "Enregistrer accès",
    porterEmpty: "Vue portier : sélectionnez un travailleur et enregistrez l'accès.",
    accessLogEyebrow: "Journal d'accès",
    accessLogH3: "Entrées et sorties horodatées",
    labelFrom: "De",
    labelTo: "À",
    labelFilterDir: "Direction",
    labelFilterGate: "Tourniquet",
    optAllDir: "Tous",
    btnApplyFilter: "Appliquer filtre",
    btnResetFilter: "Réinitialiser filtre",
    btnAccessCsv: "Exporter accès CSV",
    dailyReportEyebrow: "Rapport journalier",
    dailyReportH3: "Par porte",
    btnPrintDaily: "Imprimer rapport journalier",
    btnPrintVisitorWeekly: "Imprimer liste visiteurs semaine",
    hourlyEyebrow: "Analyse horaire",
    hourlyH3: "Entrées/sorties par heure",
    warningsEyebrow: "Avertissements",
    warningsH3: "Entrée sans sortie",
    invListEyebrow: "Facturation",
    invListH3: "Factures et état de paiement",
    optAllStatus: "Tous les statuts",
    optDraft: "Brouillon",
    optSent: "Envoyée",
    optOverdue: "En retard",
    optPaid: "Payée",
    optFailed: "Erreur",
    btnRefreshList: "Actualiser",
    inkassoEyebrow: "Recouvrement",
    inkassoH3: "En retard, pré-blocage, bloqué",
    optAllPositions: "Tous les postes ouverts",
    optPrelock: "Pré-blocage",
    optLocked: "Déjà bloqué",
    adminEyebrow: "Centre d'administration",
    adminH3: "Système et configuration",
    sysStatusEyebrow: "État du système",
    sysStatusH3: "Accès d'urgence et réparation",
    btnRefreshStatus: "Actualiser état",
    btnRepairSessions: "Réparer sessions",
    superAdminEyebrow: "Contrôle système",
    superAdminH3: "Paramètres super admin",
    labelPlatformName: "Nom de la plateforme",
    labelOperatorName: "Opérateur",
    labelTurnstileEp: "Endpoint API tourniquet",
    labelSmtpHost: "SMTP Host",
    labelSmtpPort: "SMTP Port",
    labelSmtpUser: "Utilisateur SMTP",
    labelSmtpPass: "Mot de passe SMTP",
    labelSenderEmail: "E-mail expéditeur",
    labelSenderName: "Nom expéditeur",
    labelTls: "TLS actif",
    optTlsYes: "Oui",
    optTlsNo: "Non",
    btnTestSmtp: "Envoyer un e-mail test",
    optYes: "Oui",
    optNo: "Non",
    labelIpWhitelist: "Liste blanche IP admin",
    labelEnforceDomain: "Forcer domaine entreprise",
    btnSaveAdmin: "Sauvegarder paramètres admin",
    companyNewEyebrow: "Locataires",
    companyNewH3: "Ajouter une entreprise de construction",
    labelCompanyName: "Nom de l'entreprise",
    labelCompanyContact: "Personne de contact",
    labelBillingEmail: "E-mail facturation",
    labelAccessHost: "Domaine d'accès entreprise",
    labelPlan: "Plan",
    labelCompanyStatus: "Statut",
    optCompanyActive: "Actif",
    optCompanyTest: "Test",
    optCompanyPaused: "Suspendu",
    optCompanyLocked: "Bloqué (paiement en retard)",
    labelCompanyAdminPassword: "Mot de passe admin initial",
    companyAdminPasswordPlaceholder: "ex. Sécurisé!2025",
    btnCreateCompany: "Créer entreprise",
    accountEyebrow: "Compte",
    accountH3: "Changer le mot de passe",
    labelCurrentPassword: "Mot de passe actuel",
    labelNewPassword: "Nouveau mot de passe",
    btnChangePassword: "Changer mot de passe",
    tfaEyebrow: "Double facteur",
    tfaH3: "Gestion 2FA",
    companiesListEyebrow: "Locataires",
    companiesListH3: "Entreprises et plans",
    invFormEyebrow: "Factures",
    invFormH3: "Envoyer avec logo et design",
    labelInvFirm: "Entreprise",
    labelInvNumber: "Numéro de facture",
    labelInvRecipient: "E-mail destinataire",
    labelInvDate: "Date de facture",
    labelInvDueDate: "Date d'échéance",
    labelInvPeriod: "Période de service",
    labelInvDescription: "Description du service",
    labelInvNet: "Montant net (EUR)",
    labelInvVat: "TVA (%)",
    btnPrintInvoice: "Imprimer facture / Enregistrer PDF",
    btnSendInvoice: "Envoyer facture par e-mail",
    btnUpdatePreview: "Mettre à jour l'aperçu",
    auditEyebrow: "Journal sécurité",
    auditH3: "Journal d'audit",
    labelAuditEvent: "Type d'événement",
    labelAuditRole: "Rôle",
    btnAuditCsv: "Exporter audit CSV",
    reportingPaid: "Payée",
    reportingOpen: "Ouverte",
    reportingOverdue: "En retard",
    reportingInvoicesLabel: "factures",
    reportingOverdueTotal: "Total en retard",
    reportingLockedCompanies: "Entreprises bloquées",
    reportingAutoSuspensions30d: "Suspensions auto (30j)",
    reportingGeneratedAt: "Généré le",
    reportingNoOverdueCompanies: "Aucune entreprise en retard.",
    reportingFallbackCompany: "Entreprise",
    reportingOverdueInvoicesLabel: "factures en retard",
    reportingNoAccessDataLast7Days: "Aucune donnée d'accès pour les 7 derniers jours.",
    reportingCheckin: "Entrée",
    reportingCheckout: "Sortie",
    navDocuments: "Documents",
    docInboxEyebrow: "Boîte de réception",
    docInboxH3: "Documents reçus par e-mail",
    btnDocInboxRefresh: "Actualiser",
    btnDocInboxSync: "Synchroniser la boîte",
    btnDocInboxPoll: "Récupérer la boîte maintenant",
    btnDocInboxRematch: "Réassocier",
    docEmailInfoLabel: "E-mail documents (les travailleurs envoient leurs preuves ici) :",
    btnCopyEmail: "Copier",
    btnCopyEmailDone: "Copié !",
    docInboxHint: "Les travailleurs envoient leurs preuves à l'adresse e-mail documents configurée. Le portier associe les pièces jointes à un travailleur ici.",
    docAssignEyebrow: "Attribuer",
    docAssignH3: "Attribuer une pièce jointe à un travailleur",
    docInboxEmpty: "Aucun e-mail non traité.",
    docInboxEmailFrom: "De",
    docInboxEmailSubject: "Objet",
    docInboxEmailDate: "Date",
    docInboxAttachments: "Pièces jointes",
    btnAssignDoc: "Attribuer",
    btnDismissEmail: "Ignorer",
    docAssignWorkerLabel: "Sélectionner travailleur",
    docAssignTypeLabel: "Type de document",
    docAssignNotesLabel: "Notes (optionnel)",
    btnConfirmAssign: "Attribuer le document",
    docAssignSuccess: "Document attribué avec succès.",
    docTypeMindestlohnnachweis: "Preuve de salaire minimum",
    docTypePersonalausweis: "Carte d'identité / Passeport",
    docTypeSozialversicherungsnachweis: "Attestation sécurité sociale",
    docTypeArbeitserlaubnis: "Permis de travail",
    docTypeGesundheitszeugnis: "Certificat de santé",
    docTypeSonstiges: "Autre",
    workerDocsHeading: "Documents enregistrés",
    workerDocsEmpty: "Aucun document enregistré.",
    workerAkteLabel: "Dossier travailleur",
    btnUploadWorkerDoc: "Téléverser document",
    btnConfirmUpload: "Téléverser",
    docUploadSuccess: "Document téléversé avec succès.",
    confirmDeleteDoc: "Supprimer ce document ?",
    btnDownloadDoc: "Télécharger",
    btnDeleteDoc: "Supprimer",
    imapSectionEyebrow: "Boîte documents",
    imapSectionH4: "Boîte IMAP pour les preuves",
    labelImapHint: "Les travailleurs envoient leurs preuves à cette adresse. Le système interroge la boîte toutes les quelques minutes.",
    labelImapHost: "IMAP Host",
    labelImapPort: "IMAP Port",
    labelImapUser: "Utilisateur IMAP",
    labelImapPass: "Mot de passe IMAP",
    labelImapFolder: "Dossier IMAP",
    labelImapSsl: "SSL/TLS",
    btnImapTest: "Tester la connexion IMAP",
    imapTestOk: "Connexion réussie !",
    imapTestFail: "Échec de connexion",
    navDevices: "Appareils",
    devicesEyebrow: "Matériel",
    devicesH3: "Boîtes intelligentes et appareils OSDP",
    devicesHint: "Chaque boîte intelligente envoie un signal toutes les 30–60 s. Pas de signal >90 s = hors ligne.",
    btnAddDevice: "Ajouter un appareil",
    addDeviceEyebrow: "Nouvel appareil",
    addDeviceH3: "Enregistrer un appareil",
    labelDeviceName: "Nom",
    labelDeviceLocation: "Emplacement",
    labelDeviceType: "Type / Protocole",
    btnDeviceRegister: "Enregistrer l'appareil et générer la clé API",
    deviceOnline: "En ligne",
    deviceOffline: "Hors ligne",
    deviceNeverSeen: "Pas encore de signal",
    alertInstallUnavailable: "L'installation n'est pas directement disponible dans ce navigateur. Dans Chrome ou Edge, choisissez 'Installer l'appli' dans le menu.",
    alertSessionExpired: "Session expirée. Veuillez vous reconnecter.",
    btnPrintBadge: "Imprimer le badge",
    greetingMorning: "Bonjour",
    greetingDay: "Bonjour",
    greetingEvening: "Bonsoir",
    greetingNight: "Bonne nuit",
    greetingSuffix: "Bonne prise de service !",
    adminWorkerAppSectionTitle: "Application travailleurs",
    adminWorkerAppSectionCopy: "Contrôle l'application travailleurs complète : connexion, badge numérique et utilisation QR.",
    adminWorkerAppPinLockHint: "Après 2 minutes d'inactivité, le travailleur doit saisir à nouveau son badge PIN pour voir son badge.",
    optPlanDayPassRecommended: "Carte visiteur (recommandé)",
    optPlanMonthlySite: "Mensuel par chantier",
    optPlanPerWorker: "Par travailleur",
    optPlanFlatCompany: "Forfait par entreprise",
    optPlanDayPassPrice: "Carte visiteur (19 EUR/jour)",
    loginForgotPassword: "Mot de passe oublié",
    legalImpressum: "Mentions légales",
    legalPrivacy: "Confidentialité",
    legalCloseTitle: "Fermer",
    legalFallbackEmpty: "Aucun texte disponible.",
    invoiceMgmtTitle: "Gestion des factures",
    invoiceMgmtCopy: "Affichez les factures ouvertes et payées. Marquez une facture comme payée pour lever automatiquement les blocages d'entreprise. Toutes les activités sont consignées dans l'audit.",
    invoiceOpsEyebrow: "Opérations",
    invoiceOpsH3: "SLA d'envoi et état des erreurs",
    invoiceSendEyebrow: "Envoi",
    invoiceSendH3: "File d'attente des e-mails échoués",
    optRetryAll: "Tous les envois échoués",
    optRetryPriority: "Priorité d'abord",
    optRetryMaxed: "Nombre max d'essais atteint",
    optRetryTodayFailed: "Échoués aujourd'hui",
    invoiceRetryTopIssuesOnly: "Seulement mes problèmes prioritaires",
    btnRetryCriticalSend: "Envoyer seulement les critiques",
    btnRetryExportCsv: "CSV file",
    btnIncidentExportCsv: "CSV incidents",
    btnRetryBulkSend: "Renvoyer la sélection",
    invoiceApprovalsEyebrow: "Approbations",
    invoiceApprovalsH3: "Contrôle à quatre yeux pour actions critiques",
    optApprovalAllActions: "Tous les types d'action",
    optApprovalBulkRetry: "Bulk retry",
    optApprovalDeadLetterResolve: "Résolution dead-letter",
    legalSectionEyebrow: "Légal",
    legalSectionTitle: "Mentions légales et confidentialité",
    labelImpressumText: "Texte des mentions légales",
    labelPrivacyText: "Déclaration de confidentialité",
    legalTextsHint: "Ces textes apparaissent sur la page de connexion sous 'Mentions légales' et 'Confidentialité'.",
    labelCompanyDocumentEmail: "E-mail documents",
    labelBrandingPreset: "Préréglage branding",
    optBrandingConstruction: "Construction",
    optBrandingIndustry: "Industrie",
    optBrandingPremium: "Premium",
    optPlanStarter: "Starter (49 EUR)",
    optPlanProfessional: "Professional (99 EUR)",
    optPlanEnterprise: "Enterprise (199 EUR)",
    accessFeedbackCheckin: "Accès accordé",
    badgePinHint: "La connexion par badge dans l'application travailleur ne fonctionne qu'avec le Badge-ID et ce code PIN. En modifiant, vous pouvez définir un nouveau code PIN ici.",
    badgePinPlaceholder: "4 à 8 chiffres",
    bulkSelectAll: "Tout sélectionner",
    btnDayCloseAcknowledge: "Valider la clôture journalière",
    btnExportCompanyDocEmails: "Exporter les e-mails de documents",
    btnLoadAltBrand: "Charger l'alternative",
    btnLoadDefaultBrand: "Charger le branding par défaut",
    cameraNotStarted: "Caméra non démarrée.",
    complianceEyebrow: "Conformité",
    complianceH3: "Statut des documents",
    dayCloseCommentLabel: "Commentaire de clôture journalière",
    dayCloseCommentPlaceholder: "ex. Chef d'équipe informé, sortie à compléter",
    deadLetterEyebrow: "Dead-Letter",
    deadLetterH3: "Factures à résoudre manuellement",
    filterByCompanyPlaceholder: "Filtrer par entreprise…",
    filterQueueByCompanyPlaceholder: "Filtrer la file par entreprise…",
    formSectionAppFeaturesEyebrow: "Fonctionnalités app",
    formSectionBrandingEyebrow: "Design de facture",
    formSectionBrandingH4: "Couleurs & Identité visuelle",
    formSectionEmailEyebrow: "E-Mail",
    formSectionPlatformEyebrow: "Plateforme",
    formSectionPlatformH4: "Identité & Opérateur",
    formSectionSecurityH4: "Accès & Isolation",
    formSectionSmtpH4: "Envoi SMTP",
    invoiceLogoHint: "Le logo de facture est également utilisé comme icône système et icône de l'application travailleur.",
    invoicePreviewEyebrow: "Aperçu",
    invoicePreviewH3: "Vérifier la facture avant envoi",
    maxAgeFilterPlaceholder: "Âge max en minutes (0 = tous)",
    optDeviceOsdp: "OSDP (RS-485)",
    optDeviceTcp: "TCP/IP Smart-Box",
    optDeviceWiegand: "Lecteur Wiegand",
    optPinLockActive: "Actif – Le verrou PIN empêche le partage du téléphone",
    optPinLockDisabled: "Désactivé – Badge toujours accessible",
    optRoleCompanyAdmin: "Admin entreprise",
    optRoleSuperAdmin: "Super Admin",
    optWorkerAppActive: "Actif – Badge, QR et connexion badge activés",
    optWorkerAppLocked: "Verrouillé – Application mobile désactivée",
    photoAdjustHelp: "Déplacez la photo après la capture pour qu'elle s'ajuste correctement sur le côté droit du badge.",
    photoOverrideH3: "Approbations de remplacement photo en attente",
    photoRequiredHint: "Obligatoire : Sans photo, le badge ne peut pas être sauvegardé.",
    photoSharpenLabel: "Netteté :",
    photoWhiteBgLabel: "Arrière-plan entièrement blanc (actif)",
    photoZoomCropLabel: "Zoom / Recadrer",
    recentAuditEyebrow: "Audit",
    recentAuditH3: "Événements récents du système",
    rentalModelLabel: "Modèle de location",
    sectionSecurityEyebrow: "Sécurité",
    statusLoading: "Chargement du statut…",
    sysAlertActionBtn: "Aller aux factures",
    sysAlertDefaultText: "Des erreurs d'envoi critiques de factures sont en cours.",
    sysAlertHeading: "Problème d'envoi critique",
    turnstileCountLabel: "Nombre de tourniquets",
    turnstilePasswordLabel: "Mot de passe initial du tourniquet",
    workerAppEnabledLabel: "Application badge mobile (badge numérique + QR)",
    workerPassLockLabel: "Sécuriser le badge avec un verrou PIN",
    workerSearchPlaceholder: "Rechercher : Nom, Badge-ID, Chantier …",
    confirmDeleteCompanyText: "Supprimer la société {name} et tous les enregistrements associés ?\n\nOK = suppression complète (incl. employés, sous-traitants et journaux)\nAnnuler = ne pas supprimer",
    confirmLockCompany: "Bloquer la société {name} maintenant ? L'admin, le tourniquet et l'app employé de cette société seront bloqués.",
    confirmUnlockCompany: "Lever le blocage de {name} maintenant ? La société pourra ensuite se reconnecter.",
    confirmDeleteWorkerBulk: "Vraiment supprimer {count} employés ?",
    confirmApiKeyRotate: "Régénérer la clé API pour ce tourniquet maintenant ? La clé existante perdra immédiatement sa validité.",
    confirmSystemRepair: "Effectuer la réparation système ? Les sessions expirées et les verrouillages de connexion seront nettoyés.",
    confirmApprovalDecision: "Vraiment {decision} l'approbation {id} ?",
    confirmDeadLetterRetry: "Renvoyer la facture Dead-Letter maintenant ?",
    confirmDeadLetterResolve: "Marquer le cas Dead-Letter comme résolu ?",
    confirmInvoicePaid: "Marquer cette facture comme payée ? Le blocage éventuel de la société sera levé.",
    confirmInvoiceRetry: "Renvoyer la facture maintenant ?",
    confirmInvoicePaidSimple: "Marquer la facture comme payée maintenant ?",
    confirmDemoInvoices: "Des factures de démonstration doivent-elles également être créées ?",
    confirmDemoAccessLogs: "Des journaux d'accès de démonstration doivent-ils être créés ?",
    confirmDemoReplace: "Charger les données de démonstration pour {name} en mode REPLACE maintenant ? Les employés, sous-traitants et journaux existants seront remplacés.",
    confirmDemoAppend: "Charger les données de démonstration pour {name} en mode APPEND en plus ?",
    confirmExportAudit: "Inclure le journal d'audit dans l'export ?",
    confirmExportDayClose: "Inclure les acquittements de clôture journalière dans l'export ?",
    confirmExportDeleted: "Inclure les entrées supprimées dans l'export ?",
    confirmExportAll: "En tant que superadmin : exporter tout le système ? (Non = société actuelle uniquement)",
    confirmExportDownload: "Télécharger l'export système{scope} maintenant ?",
    confirmLogout: "Vraiment se déconnecter ?",
    confirmImportChangesOnly: "Importer uniquement les modifications ? (Recommandé)",
    confirmBulkRetrySelected: "Renvoyer {count} facture(s) sélectionnée(s) maintenant ?",
    confirmBulkRetryCritical: "Renvoyer {count} facture(s) critique(s) maintenant ?",
    confirmPhotoMatchFailed: "Comparaison de photos échouée ({score}%). Seul le superadmin peut sauvegarder avec risque. Sauvegarder quand même ?",
    promptDocEmail: "Définir l'e-mail document pour {name}",
    promptTurnstilePassword: "Définir le mot de passe tourniquet pour {name} (min. 4 caractères) :",
    promptTurnstilePasswordNew: "Définir un nouveau mot de passe tourniquet (min. 4 caractères) :",
    promptCopyData: "Données à copier :",
    promptAppLink: "Lien de l'application pour l'employé :",
    promptPhotoOverrideReason: "Veuillez saisir la raison du remplacement photo (au moins 8 caractères) :",
    promptNewPassword: "Saisir un nouveau mot de passe (au moins 8 caractères) :",
    promptTfaCode: "Veuillez saisir le code à 6 chiffres de votre application d'authentification :",
    promptTfaDisableCode: "Veuillez saisir le code 2FA actuel pour désactiver :",
    promptDemoMode: "Données de démonstration pour {name} : saisir le mode (replace ou append)",
    promptRejectionReason: "Raison du rejet (obligatoire) :",
    promptRejectApproval: "Veuillez saisir la raison du rejet :",
    invoiceTitle: "Facture",
    invoiceAltLogo: "Logo société",
    invoiceLabelNumber: "Numéro de facture :",
    invoiceLabelDate: "Date de facture :",
    invoiceLabelDue: "Date d'échéance :",
    invoiceLabelCustomer: "Client :",
    invoiceLabelContact: "Interlocuteur :",
    invoiceLabelPeriod: "Période de prestation :",
    invoiceColService: "Prestation / Employé",
    invoiceColAccess: "Accès",
    invoiceColNet: "Montant net",
    invoiceRowUnknown: "Inconnu",
    invoiceRowPlan: "Forfait : {label}",
    invoiceTotalNet: "Sous-total net",
    invoiceTotalVat: "TVA ({rate} %)",
    invoiceTotalGross: "Montant total",
    invoiceFooter: "Merci pour votre collaboration. Cette facture a été créée numériquement et peut être envoyée directement.",
    invoiceHistoryEmpty: "Aucune facture envoyée ou sauvegardée pour l'instant.",
    invoiceHistoryRecipient: "Destinataire :",
    invoiceHistoryTotal: "Total :",
    invoiceHistoryCreated: "Créé :",
    invoiceHistorySent: "Envoyé :",
    invoiceHistoryError: "Erreur :",
    tfaStatusActive: "La 2FA est active",
    tfaStatusInactive: "La 2FA n'est pas active",
    tfaBtnSetup: "Configurer la 2FA",
    tfaBtnEnable: "Activer la 2FA",
    tfaBtnDisable: "Désactiver la 2FA",
    tfaQrHint: "Configurer le secret avec l'application d'authentification :",
    tfaSecretLabel: "Code manuel :",
    tfaCodeLabel: "Code depuis l'app :",
    tfaCodePlaceholder: "Code à 6 chiffres",
    tfaEnableHint: "Entrez le code à 6 chiffres de votre application d'authentification et cliquez sur 'Activer'.",
    tfaEmailLabel: "Adresse e-mail pour les codes OTP",
    tfaEmailPlaceholder: "admin@example.com",
    tfaActivateOneClickHint: "Entrez votre adresse e-mail et cliquez sur Activer. Un code sera envoyé à votre e-mail à chaque connexion.",
    alertTfaActivated: "La 2FA a été activée.",
    alertTfaEmailRequired: "Veuillez saisir une adresse e-mail avant d'activer la 2FA.",
    alertOtpSent: "Un code de sécurité a été envoyé à votre e-mail. Vérifiez votre boîte de réception.",
    loginOtpSentNotice: "Code envoyé par e-mail – vérifiez votre boîte",
    loginOtpBackBtn: "← Retour",
  },
  es: {
    authEyebrow: "Página de acceso",
    authTitle: "Inicio de sesión seguro en BauPass Control",
    authCopy: "El super admin mantiene el control completo del sistema. Los admins de empresa solo ven su empresa. El acceso de torniquete ofrece un modo rápido.",
    authPlatform: "Plataforma",
    authOperator: "Operador",
    authTurnstile: "Endpoint de torniquete",
    loginUsernameLabel: "Usuario",
    loginUsernamePlaceholder: "Usuario",
    loginPasswordLabel: "Contraseña",
    loginPasswordPlaceholder: "Introduce la contraseña",
    loginOtpLabel: "Código OTP (si 2FA está activa)",
    loginOtpPlaceholder: "123456",
    uiLanguageLabel: "Idioma",
    loginScopeLabel: "Tipo de acceso",
    loginScopeAuto: "Automático",
    loginScopeServerAdmin: "Admin del servidor",
    loginScopeCompanyAdmin: "Admin de empresa",
    loginScopeTurnstile: "Torniquete",
    supportReadOnlyAlert: "Este acceso de soporte es de solo lectura. Los cambios están bloqueados en esta sesión.",
    supportReadOnlyTitle: "Modo soporte: solo lectura",
    supportLoginActive: "Acceso de soporte activo:",
    supportCompanyFallback: "Empresa",
    supportStartedBy: "iniciado por",
    supportReadOnlyNotice: "Después de iniciar sesión, el acceso es de solo lectura.",
    supportModeLabel: "Modo soporte:",
    supportReadOnlyFor: "Solo lectura para",
    supportCompanyLoginConfirmPrefix: "Cambiar al acceso de empresa para",
    supportCompanyLoginConfirmSuffix: "? Tu sesión de admin actual se cerrará. Después, el acceso será de solo lectura.",
    supportCompanyLoginOpenedPrefix: "Acceso para",
    supportCompanyLoginOpenedSuffix: "abierto. Inicia sesión ahora con el administrador de empresa. Esta sesión seguirá en solo lectura.",
    supportModeReadOnlyLine: "Modo soporte activo: Solo lectura.",
    supportReadOnlyShort: "Modo soporte: solo lectura.",
    loginButton: "Iniciar sesión",
    demoAccessTitle: "Cuentas demo",
    demoSuperAdmin: "Super Admin: superadmin / 1234",
    demoCompanyAdmin: "Admin empresa: firma / 1234",
    demoTurnstile: "Torniquete: drehkreuz / 1234",
    desktopAppTitle: "App de escritorio",
    desktopInstallHint: "Este portal puede instalarse en tu ordenador como una app local.",
    desktopInstallButton: "Instalar en este ordenador",
    // Shell
    sidebarEyebrow: "Portal de empresa",
    sidebarCopy: "Registra trabajadores, toma fotos, crea credenciales digitales y gestiona el control de acceso.",
    sidebarCardTitle: "Modo alquiler",
    sidebarCardStrong: "Multi-empresa",
    sidebarCardDesc: "Cada empresa de construcción gestiona su equipo por separado. El super admin controla el sistema.",
    navDashboard: "Panel de control",
    navWorkers: "Trabajadores",
    navBadge: "Credencial",
    navAccess: "Acceso",
    navInvoices: "Facturas",
    navAdmin: "Administración",
    topbarEyebrow: "Estado del sistema",
    topbarHeading: "Credenciales de obra y control de acceso",
    btnSeedData: "Datos de demo",
    btnExport: "Exportar sistema",
    btnImport: "Importar sistema",
    btnLogout: "Cerrar sesión segura",
    dashEyebrow: "MVP mejorado",
    dashHeading: "Credenciales digitales con foto, Badge ID y check-in de torniquete",
    dashSubtext: "Diseñado para alquiler a empresas de construcción.",
    dashBadge1: "Captura de foto",
    dashBadge2: "Registro de acceso",
    dashBadge3: "Multi-inquilino",
    reportingEyebrow: "Informes",
    reportingH3: "Estado de pago y bloqueo",
    accessWeekEyebrow: "7 días",
    accessWeekH3: "Acceso diario",
    recentEyebrow: "Actividad reciente",
    recentH3: "Registro de acceso",
    porterLiveEmpty: "El último acceso se mostrará aquí en el primer registro.",
    workersFormEyebrow: "Datos maestros",
    workersFormH3: "Registrar trabajador o visitante",
    labelType: "Tipo",
    optWorker: "Trabajador",
    optVisitor: "Visitante",
    labelFirm: "Empresa",
    labelSubcompany: "Subempresa",
    optNoSubcompany: "Sin subempresa",
    labelNewSubcompany: "Nueva subempresa",
    btnAddSubcompany: "Crear subempresa",
    labelFirstName: "Nombre",
    labelLastName: "Apellido",
    labelInsuranceNumber: "Número de seguro",
    labelRoleField: "Función",
    labelSite: "Obra",
    siteFieldHint: "Introduzca la dirección completa – necesaria para la verificación GPS al iniciar sesión",
    labelPhysicalCard: "ID tarjeta física (NFC/RFID)",
    labelValidUntil: "Válido hasta",
    labelVisitorCompany: "Empresa del visitante",
    labelVisitPurpose: "Propósito de la visita",
    labelHostName: "Contacto en obra",
    labelVisitEndAt: "Fin de visita",
    visitorHint: "Los visitantes son válidos por unas horas o hasta el final del día. Los registros abiertos se cierran automáticamente a las 00:00 como máximo, la tarjeta se conserva para informes.",
    labelWorkerStatus: "Estado",
    optStatusActive: "Activo",
    optStatusLocked: "Bloqueado",
    optStatusExpired: "Expirado",
    labelBadgePin: "Badge PIN para inicio de sesión",
    btnStartCamera: "Iniciar cámara",
    btnCapturePhoto: "Tomar foto",
    btnUploadPhoto: "Subir foto",
    btnPhotoUp: "↑ Arriba",
    btnPhotoLeft: "← Izquierda",
    btnPhotoRight: "Derecha →",
    btnPhotoDown: "Abajo ↓",
    btnPhotoReset: "Restablecer posición",
    btnWorkerSubmit: "Guardar trabajador y crear credencial",
    btnWorkerCancelEdit: "Cancelar edición",
    workersListEyebrow: "Registros",
    workersListH3: "Trabajadores registrados",
    btnWorkerCsv: "Descargar lista PDF",
    btnBulkDelete: "Eliminar selección",
    btnBulkActive: "Estado: activo",
    btnBulkInactive: "Estado: inactivo",
    btnBulkCancel: "Cancelar",
    badgeEyebrow: "Identidad digital",
    badgeH3: "Vista previa de credencial",
    badgeEmptyState: "Por favor crea o selecciona un trabajador primero.",
    badgeScanEyebrow: "Ayuda escaneo",
    badgeScanH3: "Código de credencial",
    badgeScanEmpty: "Ninguna credencial seleccionada.",
    badgeTitleVisitor: "Tarjeta de visitante digital",
    badgeTitleDayPass: "Pase diario de obra digital",
    badgeTitleRegular: "Insignia de obra digital",
    badgeUnknownCompany: "Empresa desconocida",
    badgeQrHint: "Escanear QR, instalar la app y abrir la insignia directamente.",
    badgeLabelBadgeId: "Badge-ID",
    badgeMetaQrFunc: "Funci\u00f3n QR",
    badgeMetaQrFuncVal: "Instalaci\u00f3n de app de trabajadores",
    badgeMetaRoleLabel: "Rol en el sistema",
    badgePhotoUploadHint: "Tomar o subir foto",
    appPinLabel: "PIN de app",
    pinNotRequired: "no necesario",
    pinSet: "configurado",
    pinMissing: "faltante",
    cardLabel: "Tarjeta",
    cardUnassigned: "no asignada",
    btnEdit: "Editar",
    btnDelete: "Eliminar",
    btnRestore: "Restaurar",
    btnAppLink: "Enlace app",
    btnResetPin: "Restablecer PIN",
    confirmDeleteWorker: "\u00bfEliminar al trabajador ahora?",
    alertDeleteWorkerFailed: "No se pudo eliminar al trabajador: {error}",
    alertRestoreWorkerFailed: "No se pudo restaurar al trabajador: {error}",
    alertAppLinkCreateFailed: "No se pudo crear el enlace de la app: {error}",
    promptResetPinFor: "Nuevo PIN de badge para {name} (4-8 digitos):",
    alertPinMustDigits: "El PIN debe tener de 4 a 8 digitos.",
    alertPinResetSuccessFor: "El PIN de {name} se restablecio correctamente.",
    alertPinResetFailed: "No se pudo restablecer el PIN: {error}",
    alertPhotoOverrideApproved: "Reemplazo de foto aprobado. Los datos del trabajador han sido guardados.",
    alertPhotoOverrideApproveFailed: "Aprobacion fallida: {error}",
    alertPhotoOverrideRejectReasonRequired: "Se requiere una razon de rechazo.",
    alertPhotoOverrideRejected: "Reemplazo de foto rechazado.",
    alertPhotoOverrideRejectFailed: "Rechazo fallido: {error}",
    alertDocEmailSaveFailed: "El correo de documentos no pudo guardarse: {error}",
    alertCompanyDeleted: "La empresa {name} ha sido eliminada.",
    alertCompanyDeleteFailed: "La empresa {name} no pudo eliminarse: {error}",
    alertCompanyLocked: "La empresa {name} ha sido bloqueada.",
    alertCompanyUnlocked: "El bloqueo de {name} ha sido levantado.",
    alertCompanyStatusChangeFailed: "El cambio de estado de {name} fallo: {error}",
    alertBrandingPresetSaveFailed: "El preset de diseno no pudo guardarse: {error}",
    alertPasswordMinLength: "La contrasena debe tener al menos 4 caracteres.",
    alertTurnstileCreateFailed: "El torniquete no pudo crearse: {error}",
    alertTurnstilePasswordUpdated: "La contrasena del torniquete ha sido actualizada.",
    alertTurnstilePasswordResetFailed: "El restablecimiento de contrasena fallo: {error}",
    alertApiKeyRotationFailed: "La rotacion de clave API fallo: {error}",
    alertTurnstileToggleFailed: "El torniquete no pudo cambiarse: {error}",
    alertWorkerDeletedCannotEdit: "Los trabajadores eliminados no pueden editarse.",
    alertDataCopied: "Datos copiados.",
    alertPrintWindowFailed: "La ventana de impresion no pudo abrirse.",
    alertAppLinkCopied: "Enlace de la aplicacion copiado.",
    alertQrNotReadyYet: "El codigo QR todavia se esta generando. Por favor intentelo de nuevo en un momento.",
    alertAccessBookingFailed: "El acceso no pudo reservarse: {error}",
    alertWorkerSaveFailed: "El trabajador no pudo guardarse: {error}",
    alertPhotoMatchFailed: "Comparacion de fotos fallida ({score}%). El guardado esta bloqueado. Por favor vuelva a tomar la foto o contacte a un superadmin.",
    alertOverrideReasonTooShort: "La razon de reemplazo es demasiado corta. Por favor ingrese al menos 8 caracteres.",
    alertPhotoOverrideRequested: "Reemplazo de foto solicitado (ID de aprobacion: {id}).\nUn segundo superadmin debe aprobar el cambio antes de que se guarde.",
    alertBadgePinInvalid: "El PIN de la insignia debe contener de 4 a 8 digitos.",
    alertDuplicatePhysicalCardId: "Este ID de tarjeta fisica ya esta asignado a otro trabajador.",
    alertPhotoOverrideSuperadminOnly: "El reemplazo de foto solo esta permitido para superadmins.",
    alertPhotoOverrideReasonRequired: "Por favor proporcione una razon suficiente para el reemplazo de foto.",
    alertInvoiceSavedSendFailed: "Factura guardada, envio fallido: {error}",
    alertInvoiceNumberDuplicate: "El numero de factura {number} ya esta en uso. Por favor use un numero diferente.",
    alertInvoiceSendFailed: "La factura no pudo enviarse: {error}",
    alertInvoiceNumberLength: "El numero de factura debe tener entre 3 y 64 caracteres.",
    alertInvoiceDateInvalid: "La fecha de factura o la fecha de vencimiento es invalida.",
    alertInvoiceDueDateBeforeIssue: "La fecha de vencimiento no puede ser anterior a la fecha de factura.",
    alertInvoiceVatRange: "El IVA debe estar entre 0 y 100.",
    alertApprovalRejectReasonRequired: "El rechazo sin razon no esta permitido.",
    alertApprovalConfirmed: "Aprobacion confirmada y accion ejecutada.",
    alertApprovalRejected: "La aprobacion fue rechazada.",
    alertApprovalUpdated: "Aprobacion actualizada.",
    alertApprovalActionFailed: "La accion de aprobacion fallo: {error}",
    alertInvoiceRetrySentDeadLetter: "La factura fue reenviada con exito y eliminada de la cola muerta.",
    alertInvoiceRetrySent: "La factura fue reenviada con exito.",
    alertInvoiceRetryFailed: "El reenvio fallo: {error}",
    alertDeadLetterResolveApprovalRequested: "Aprobacion solicitada ({id}). Un segundo superadmin debe confirmar.",
    alertDeadLetterResolveFailed: "El caso de letra muerta no pudo resolverse: {error}",
    alertGenericError: "Error: {error}",
    alertCollectionsStatusChangeFailed: "El cambio de estado fallo: {error}",
    alertActionFailed: "La accion fallo: {error}",
    alertInvoiceHistoryLoadFailed: "El historial no pudo cargarse: {error}",
    alertAccessExportFailed: "La exportacion del registro de acceso fallo: {error}",
    alertWorkerExportFailed: "La exportacion de la lista de trabajadores fallo: {error}",
    alertSettingsSaveFailed: "La configuracion no pudo guardarse: {error}",
    alertSystemRepairDone: "La reparacion del sistema ha sido ejecutada.",
    alertSystemRepairFailed: "La reparacion del sistema fallo: {error}",
    alertBrandingLoaded: "Marca BauKometra cargada. Ahora haga clic en Guardar en la configuracion de admin.",
    alertBrandingLoadFailed: "La marca no pudo cargarse: {error}",
    alertBrandingAltLoaded: "Variante alternativa de la marca BauKometra cargada. Ahora haga clic en Guardar en la configuracion de admin.",
    alertBrandingAltLoadFailed: "La variante de marca alternativa no pudo cargarse: {error}",
    alertDayCloseAckFailed: "El cierre de dia no pudo confirmarse: {error}",
    alertOtpRequired: "La 2FA esta activa para esta cuenta. Por favor ingrese el codigo OTP.",
    alertOtpInvalid: "El codigo OTP es invalido o ha expirado. Por favor ingrese un nuevo codigo.",
    alertTooManyAttempts: "Demasiados intentos fallidos. Por favor espere 10 minutos e intentelo de nuevo.",
    alertForbiddenTenantHost: "Este acceso solo esta permitido a traves del dominio de empresa aprobado.",
    alertSupportCompanyMismatch: "Este inicio de sesion no coincide con la empresa seleccionada. Por favor use el admin de la empresa marcada.",
    alertLoginCompanyLocked: "Esta empresa esta bloqueada. Por favor liquide las facturas pendientes o levante el bloqueo en superadmin.",
    alertInvalidCredentials: "Nombre de usuario o contrasena incorrectos. Por favor verifique sus datos e intentelo de nuevo.",
    alertAdminIpNotAllowed: "El acceso de admin desde esta IP no esta permitido.",
    alertLoginScopeMismatch: "El tipo de acceso no coincide con la cuenta. Por favor seleccione correctamente admin de servidor / admin de empresa.",
    alertLoginHttp405: "Inicio de sesion fallido: 405. La solicitud de inicio de sesion esta llegando actualmente a {target}. Para GitHub Pages, el frontend debe usar su backend de Render.",
    alertLoginFailed: "Inicio de sesion fallido: {error}",
    alertPasswordResetEnterUsername: "Por favor ingrese primero un nombre de usuario o correo electronico.",
    alertPasswordResetSent: "Si se encontro una cuenta coincidente, se ha enviado un correo de restablecimiento.",
    alertPasswordResetFailed: "El restablecimiento de contrasena no pudo iniciarse: {error}",
    alertPasswordSetSuccess: "La contrasena se ha establecido correctamente. Ahora puede iniciar sesion.",
    alertPasswordResetLinkFailed: "El enlace de restablecimiento no pudo usarse: {error}",
    alertPasswordChanged: "Contrasena cambiada. Por favor inicie sesion de nuevo.",
    alertPasswordChangeFailed: "El cambio de contrasena fallo: {error}",
    alert2faSetupFailed: "La configuracion de 2FA fallo: {error}",
    alert2faEnableFailed: "La 2FA no pudo activarse: {error}",
    alertDeviceDeleteFailed: "Error al eliminar: {error}",
    alertCompanyCreateFailed: "La empresa no pudo crearse: {error}",
    alert2faDisableFailed: "La 2FA no pudo desactivarse: {error}",
    alertExportFailed: "La exportacion fallo: {error}",
    alertNoDemoCompany: "No se encontro ninguna empresa activa para los datos de demostracion.",
    alertDemoModeInvalid: "Modo invalido. Por favor use replace o append.",
    alertDemoLoadFailed: "Los datos de demostracion no pudieron cargarse: {error}",
    alertImportSuccess: "Importacion aplicada con exito.",
    alertImportFailed: "La importacion fallo: {error}",
    alertCsvExportFailed: "La exportacion CSV fallo: {error}",
    alertIncidentExportFailed: "La exportacion de incidentes fallo: {error}",
    alertSelectInvoiceForRetry: "Por favor seleccione al menos una factura en la cola.",
    alertBulkRetryDone: "Reintento masivo completado. Enviados: {sent}, Fallidos: {failed}, Omitidos: {skipped}",
    alertBulkRetryFailed: "El reintento masivo fallo: {error}",
    alertNoCriticalCases: "Actualmente no hay casos criticos (puntuacion >= 70).",
    alertCriticalBulkRetryDone: "Reintento masivo critico completado. Enviados: {sent}, Fallidos: {failed}, Omitidos: {skipped}",
    alertCriticalBulkRetryFailed: "El reintento masivo critico fallo: {error}",
    alertDesktopInstallFailed: "La instalacion de escritorio no pudo iniciarse.",
    alertSubcompanyCreateFailed: "El subcontratista no pudo crearse: {error}",
    alertDeleteFailed: "Error al eliminar: {error}",
    alertStatusChangeFailed: "Error al cambiar el estado: {error}",
    alertReassignmentDone: "Reasignacion completada. Coincidencias: {count}",
    alertReassignmentFailed: "La reasignacion fallo: {error}",
    detailCloseTitle: "Cerrar",
    detailPhotoAlt: "Foto del trabajador",
    detailCheckinBtn: "Entrada (Check-in)",
    detailCheckoutBtn: "Salida (Check-out)",
    accessFormEyebrow: "Torniquete",
    accessFormH3: "Check-in y check-out",
    labelAccessBadge: "Badge ID o trabajador",
    labelAccessDir: "Dirección",
    labelAccessGate: "Puerta",
    labelAccessNote: "Nota",
    optCheckin: "Entrada",
    optCheckout: "Salida",
    btnAccessSubmit: "Registrar acceso",
    porterEmpty: "Vista portero: selecciona un trabajador y registra el acceso.",
    accessLogEyebrow: "Registro de acceso",
    accessLogH3: "Entradas y salidas con marca de tiempo",
    labelFrom: "Desde",
    labelTo: "Hasta",
    labelFilterDir: "Dirección",
    labelFilterGate: "Torniquete",
    optAllDir: "Todos",
    btnApplyFilter: "Aplicar filtro",
    btnResetFilter: "Restablecer filtro",
    btnAccessCsv: "Exportar acceso CSV",
    dailyReportEyebrow: "Informe diario",
    dailyReportH3: "Por puerta",
    btnPrintDaily: "Imprimir informe diario",
    btnPrintVisitorWeekly: "Imprimir lista visitantes semanal",
    hourlyEyebrow: "Análisis horario",
    hourlyH3: "Entradas/salidas por hora",
    warningsEyebrow: "Advertencias",
    warningsH3: "Entrada sin salida",
    invListEyebrow: "Facturación",
    invListH3: "Facturas y estado de pago",
    optAllStatus: "Todos los estados",
    optDraft: "Borrador",
    optSent: "Enviada",
    optOverdue: "Vencida",
    optPaid: "Pagada",
    optFailed: "Error",
    btnRefreshList: "Actualizar",
    inkassoEyebrow: "Cobro",
    inkassoH3: "Vencida, pre-bloqueo, bloqueada",
    optAllPositions: "Todas las posiciones abiertas",
    optPrelock: "Pre-bloqueo",
    optLocked: "Ya bloqueado",
    adminEyebrow: "Centro de administración",
    adminH3: "Sistema y configuración",
    sysStatusEyebrow: "Estado del sistema",
    sysStatusH3: "Acceso de emergencia y reparación",
    btnRefreshStatus: "Actualizar estado",
    btnRepairSessions: "Reparar sesiones",
    superAdminEyebrow: "Control del sistema",
    superAdminH3: "Ajustes del super admin",
    labelPlatformName: "Nombre de la plataforma",
    labelOperatorName: "Operador",
    labelTurnstileEp: "Endpoint API torniquete",
    labelSmtpHost: "SMTP Host",
    labelSmtpPort: "SMTP Port",
    labelSmtpUser: "Usuario SMTP",
    labelSmtpPass: "Contraseña SMTP",
    labelSenderEmail: "E-mail remitente",
    labelSenderName: "Nombre remitente",
    labelTls: "TLS activo",
    optTlsYes: "Sí",
    optTlsNo: "No",
    btnTestSmtp: "Enviar correo de prueba",
    optYes: "Sí",
    optNo: "No",
    labelIpWhitelist: "Lista blanca IP admin",
    labelEnforceDomain: "Forzar dominio empresa",
    btnSaveAdmin: "Guardar ajustes admin",
    companyNewEyebrow: "Inquilinos",
    companyNewH3: "Añadir empresa de construcción",
    labelCompanyName: "Nombre de empresa",
    labelCompanyContact: "Persona de contacto",
    labelBillingEmail: "E-mail de facturación",
    labelAccessHost: "Dominio de acceso empresa",
    labelPlan: "Plan",
    labelCompanyStatus: "Estado",
    optCompanyActive: "Activo",
    optCompanyTest: "Prueba",
    optCompanyPaused: "Pausado",
    optCompanyLocked: "Bloqueado (pago pendiente)",
    labelCompanyAdminPassword: "Contraseña inicial del admin",
    companyAdminPasswordPlaceholder: "ej. Seguro!2025",
    btnCreateCompany: "Crear empresa",
    accountEyebrow: "Cuenta",
    accountH3: "Cambiar contraseña",
    labelCurrentPassword: "Contraseña actual",
    labelNewPassword: "Nueva contraseña",
    btnChangePassword: "Cambiar contraseña",
    tfaEyebrow: "Doble factor",
    tfaH3: "Gestión 2FA",
    companiesListEyebrow: "Inquilinos",
    companiesListH3: "Empresas y planes",
    invFormEyebrow: "Facturas",
    invFormH3: "Enviar con logo y diseño",
    labelInvFirm: "Empresa",
    labelInvNumber: "Número de factura",
    labelInvRecipient: "E-mail destinatario",
    labelInvDate: "Fecha de factura",
    labelInvDueDate: "Fecha de vencimiento",
    labelInvPeriod: "Período de servicio",
    labelInvDescription: "Descripción del servicio",
    labelInvNet: "Importe neto (EUR)",
    labelInvVat: "IVA (%)",
    btnPrintInvoice: "Imprimir factura / Guardar PDF",
    btnSendInvoice: "Enviar factura por e-mail",
    btnUpdatePreview: "Actualizar vista previa",
    auditEyebrow: "Registro de seguridad",
    auditH3: "Registro de auditoría",
    labelAuditEvent: "Tipo de evento",
    labelAuditRole: "Rol",
    btnAuditCsv: "Exportar auditoría CSV",
    reportingPaid: "Pagada",
    reportingOpen: "Abierta",
    reportingOverdue: "Vencida",
    reportingInvoicesLabel: "facturas",
    reportingOverdueTotal: "Total vencido",
    reportingLockedCompanies: "Empresas bloqueadas",
    reportingAutoSuspensions30d: "Suspensiones auto (30d)",
    reportingGeneratedAt: "Generado",
    reportingNoOverdueCompanies: "No hay empresas con facturas vencidas.",
    reportingFallbackCompany: "Empresa",
    reportingOverdueInvoicesLabel: "facturas vencidas",
    reportingNoAccessDataLast7Days: "No hay datos de acceso para los últimos 7 días.",
    reportingCheckin: "Entrada",
    reportingCheckout: "Salida",
    navDocuments: "Documentos",
    docInboxEyebrow: "Bandeja de entrada",
    docInboxH3: "Documentos entrantes por correo",
    btnDocInboxRefresh: "Actualizar",
    btnDocInboxSync: "Sincronizar bandeja",
    btnDocInboxPoll: "Obtener buzón ahora",
    btnDocInboxRematch: "Reasignar",
    docEmailInfoLabel: "Correo de documentos (los trabajadores envían sus pruebas aquí):",
    btnCopyEmail: "Copiar",
    btnCopyEmailDone: "¡Copiado!",
    docInboxHint: "Los trabajadores envían sus pruebas al correo de documentos configurado. El portero asigna los archivos adjuntos a un trabajador aquí.",
    docAssignEyebrow: "Asignar",
    docAssignH3: "Asignar archivo adjunto a un trabajador",
    docInboxEmpty: "No hay correos sin procesar.",
    docInboxEmailFrom: "De",
    docInboxEmailSubject: "Asunto",
    docInboxEmailDate: "Fecha",
    docInboxAttachments: "Archivos adjuntos",
    btnAssignDoc: "Asignar",
    btnDismissEmail: "Descartar",
    docAssignWorkerLabel: "Seleccionar trabajador",
    docAssignTypeLabel: "Tipo de documento",
    docAssignNotesLabel: "Notas (opcional)",
    btnConfirmAssign: "Asignar documento",
    docAssignSuccess: "Documento asignado correctamente.",
    docTypeMindestlohnnachweis: "Prueba de salario mínimo",
    docTypePersonalausweis: "DNI / Pasaporte",
    docTypeSozialversicherungsnachweis: "Certificado de seguridad social",
    docTypeArbeitserlaubnis: "Permiso de trabajo",
    docTypeGesundheitszeugnis: "Certificado de salud",
    docTypeSonstiges: "Otros",
    workerDocsHeading: "Documentos guardados",
    workerDocsEmpty: "No hay documentos registrados.",
    workerAkteLabel: "Expediente del trabajador",
    btnUploadWorkerDoc: "Subir documento",
    btnConfirmUpload: "Subir",
    docUploadSuccess: "Documento subido correctamente.",
    confirmDeleteDoc: "¿Eliminar este documento?",
    btnDownloadDoc: "Descargar",
    btnDeleteDoc: "Eliminar",
    imapSectionEyebrow: "Buzón de documentos",
    imapSectionH4: "Buzón IMAP para pruebas",
    labelImapHint: "Los trabajadores envían sus pruebas a esta dirección. El sistema consulta el buzón cada pocos minutos.",
    labelImapHost: "IMAP Host",
    labelImapPort: "IMAP Puerto",
    labelImapUser: "Usuario IMAP",
    labelImapPass: "Contraseña IMAP",
    labelImapFolder: "Carpeta IMAP",
    labelImapSsl: "SSL/TLS",
    btnImapTest: "Probar conexión IMAP",
    imapTestOk: "¡Conexión exitosa!",
    imapTestFail: "Error de conexión",
    navDevices: "Dispositivos",
    devicesEyebrow: "Hardware",
    devicesH3: "Cajas inteligentes y dispositivos OSDP",
    devicesHint: "Cada caja inteligente envía una señal cada 30–60 s. Sin señal >90 s = desconectado.",
    btnAddDevice: "Añadir dispositivo",
    addDeviceEyebrow: "Nuevo dispositivo",
    addDeviceH3: "Registrar dispositivo",
    labelDeviceName: "Nombre",
    labelDeviceLocation: "Ubicación",
    labelDeviceType: "Tipo / Protocolo",
    btnDeviceRegister: "Registrar dispositivo y generar clave API",
    deviceOnline: "En línea",
    deviceOffline: "Desconectado",
    deviceNeverSeen: "Sin señal todavía",
    alertInstallUnavailable: "La instalación no está disponible directamente en este navegador. En Chrome o Edge elige 'Instalar aplicación' en el menú.",
    alertSessionExpired: "Sesión expirada. Por favor, inicia sesión de nuevo.",
    btnPrintBadge: "Imprimir credencial",
    greetingMorning: "Buenos días",
    greetingDay: "Buenas tardes",
    greetingEvening: "Buenas tardes",
    greetingNight: "Buenas noches",
    greetingSuffix: "¡Buen turno!",
    adminWorkerAppSectionTitle: "App de trabajadores",
    adminWorkerAppSectionCopy: "Controla toda la app de trabajadores: acceso, credencial digital y uso de QR.",
    adminWorkerAppPinLockHint: "Después de 2 minutos sin interacción el trabajador debe volver a introducir su PIN de credencial.",
    optPlanDayPassRecommended: "Tarjeta de visitante (recomendado)",
    optPlanMonthlySite: "Mensual por obra",
    optPlanPerWorker: "Por trabajador",
    optPlanFlatCompany: "Tarifa plana por empresa",
    optPlanDayPassPrice: "Tarjeta de visitante (19 EUR/día)",
    loginForgotPassword: "Olvidé la contraseña",
    legalImpressum: "Aviso legal",
    legalPrivacy: "Privacidad",
    legalCloseTitle: "Cerrar",
    legalFallbackEmpty: "No hay texto disponible.",
    invoiceMgmtTitle: "Gestión de facturas",
    invoiceMgmtCopy: "Muestra facturas abiertas y pagadas. Marque facturas como pagadas para levantar bloqueos de empresa automáticamente. Todas las actividades se registran en el log de auditoría.",
    invoiceOpsEyebrow: "Operaciones",
    invoiceOpsH3: "SLA de envío y estado de errores",
    invoiceSendEyebrow: "Envío",
    invoiceSendH3: "Cola de correos fallidos",
    optRetryAll: "Todos los envíos fallidos",
    optRetryPriority: "Primero prioridad",
    optRetryMaxed: "Máximo de reintentos alcanzado",
    optRetryTodayFailed: "Fallados hoy",
    invoiceRetryTopIssuesOnly: "Solo mis problemas principales",
    btnRetryCriticalSend: "Enviar solo críticos ahora",
    btnRetryExportCsv: "CSV cola",
    btnIncidentExportCsv: "CSV incidentes",
    btnRetryBulkSend: "Reenviar seleccionados",
    invoiceApprovalsEyebrow: "Aprobaciones",
    invoiceApprovalsH3: "Revisión de cuatro ojos para acciones críticas",
    optApprovalAllActions: "Todos los tipos de acción",
    optApprovalBulkRetry: "Reintento masivo",
    optApprovalDeadLetterResolve: "Resolver dead-letter",
    legalSectionEyebrow: "Legal",
    legalSectionTitle: "Aviso legal y privacidad",
    labelImpressumText: "Texto de aviso legal",
    labelPrivacyText: "Política de privacidad",
    legalTextsHint: "Estos textos aparecen en la página de acceso bajo 'Aviso legal' y 'Privacidad'.",
    labelCompanyDocumentEmail: "Correo de documentos",
    labelBrandingPreset: "Preset de marca",
    optBrandingConstruction: "Construcción",
    optBrandingIndustry: "Industria",
    optBrandingPremium: "Premium",
    optPlanStarter: "Starter (49 EUR)",
    optPlanProfessional: "Professional (99 EUR)",
    optPlanEnterprise: "Enterprise (199 EUR)",
    accessFeedbackCheckin: "Acceso registrado",
    badgePinHint: "El inicio de sesión por badge en la app del trabajador solo funciona con el Badge-ID y este PIN. Al editar puedes establecer un nuevo PIN aquí.",
    badgePinPlaceholder: "4 a 8 dígitos",
    bulkSelectAll: "Seleccionar todo",
    btnDayCloseAcknowledge: "Confirmar cierre del día",
    btnExportCompanyDocEmails: "Exportar e-mails de documentos",
    btnLoadAltBrand: "Cargar alternativa",
    btnLoadDefaultBrand: "Cargar marca predeterminada",
    cameraNotStarted: "Cámara no iniciada.",
    complianceEyebrow: "Cumplimiento",
    complianceH3: "Estado de documentos",
    dayCloseCommentLabel: "Comentario de cierre del día",
    dayCloseCommentPlaceholder: "ej. Jefe de turno informado, salida a registrar después",
    deadLetterEyebrow: "Dead-Letter",
    deadLetterH3: "Facturas que requieren resolución manual",
    filterByCompanyPlaceholder: "Filtrar por empresa…",
    filterQueueByCompanyPlaceholder: "Filtrar cola por empresa…",
    formSectionAppFeaturesEyebrow: "Funciones de la app",
    formSectionBrandingEyebrow: "Diseño de factura",
    formSectionBrandingH4: "Colores & Marca",
    formSectionEmailEyebrow: "E-Mail",
    formSectionPlatformEyebrow: "Plataforma",
    formSectionPlatformH4: "Identidad y Operador",
    formSectionSecurityH4: "Acceso y aislamiento",
    formSectionSmtpH4: "Envío SMTP",
    invoiceLogoHint: "El logo de factura también se usa como icono del sistema e icono de la app del trabajador.",
    invoicePreviewEyebrow: "Vista previa",
    invoicePreviewH3: "Revisar factura antes de enviar",
    maxAgeFilterPlaceholder: "Edad máx en minutos (0 = todos)",
    optDeviceOsdp: "OSDP (RS-485)",
    optDeviceTcp: "TCP/IP Smart-Box",
    optDeviceWiegand: "Lector Wiegand",
    optPinLockActive: "Activo – Bloqueo PIN evita compartir el teléfono",
    optPinLockDisabled: "Desactivado – Credencial siempre accesible",
    optRoleCompanyAdmin: "Admin empresa",
    optRoleSuperAdmin: "Super Admin",
    optWorkerAppActive: "Activo – Badge, QR e inicio de sesión habilitados",
    optWorkerAppLocked: "Bloqueado – App móvil desactivada",
    photoAdjustHelp: "Mueve la foto tras la captura para que encaje correctamente en el lado derecho del credencial.",
    photoOverrideH3: "Aprobaciones de anulación de foto pendientes",
    photoRequiredHint: "Obligatorio: Sin foto no se puede guardar el credencial.",
    photoSharpenLabel: "Nitidez:",
    photoWhiteBgLabel: "Fondo completamente blanco (activo)",
    photoZoomCropLabel: "Zoom / Recortar",
    recentAuditEyebrow: "Auditoría",
    recentAuditH3: "Eventos recientes del sistema",
    rentalModelLabel: "Modelo de alquiler",
    sectionSecurityEyebrow: "Seguridad",
    statusLoading: "Cargando estado…",
    sysAlertActionBtn: "Ir a facturas",
    sysAlertDefaultText: "Hay errores críticos de envío de facturas.",
    sysAlertHeading: "Problema crítico de envío",
    turnstileCountLabel: "Número de torniquetes",
    turnstilePasswordLabel: "Contraseña inicial del torniquete",
    workerAppEnabledLabel: "App de badge móvil (badge digital + QR)",
    workerPassLockLabel: "Proteger el credencial con bloqueo PIN",
    workerSearchPlaceholder: "Buscar: Nombre, Badge-ID, Obra …",
    confirmDeleteCompanyText: "\u00bfEliminar la empresa {name} y todos los registros asociados?\n\nAceptar = eliminaci\u00f3n completa (incl. empleados, subcontratistas y registros)\nCancelar = no eliminar",
    confirmLockCompany: "\u00bfBloquear la empresa {name} ahora? El administrador, el torniquete y la app de empleados de esta empresa ser\u00e1n bloqueados.",
    confirmUnlockCompany: "\u00bfLevantar el bloqueo de {name} ahora? La empresa podr\u00e1 volver a iniciar sesi\u00f3n.",
    confirmDeleteWorkerBulk: "\u00bfRealmente eliminar {count} empleados?",
    confirmApiKeyRotate: "\u00bfRegenarar la clave API para este torniquete ahora? La clave existente perder\u00e1 su validez inmediatamente.",
    confirmSystemRepair: "\u00bfEjecutar reparaci\u00f3n del sistema? Se limpiar\u00e1n las sesiones expiradas y los bloqueos de inicio de sesi\u00f3n.",
    confirmApprovalDecision: "\u00bfRealmente {decision} la aprobaci\u00f3n {id}?",
    confirmDeadLetterRetry: "\u00bfReenviar la factura Dead-Letter ahora?",
    confirmDeadLetterResolve: "\u00bfMarcar el caso Dead-Letter como resuelto?",
    confirmInvoicePaid: "\u00bfMarcar esta factura como pagada? Se levantar\u00e1 cualquier bloqueo de la empresa.",
    confirmInvoiceRetry: "\u00bfReenviar la factura ahora?",
    confirmInvoicePaidSimple: "\u00bfMarcar la factura como pagada ahora?",
    confirmDemoInvoices: "\u00bfTambi\u00e9n se deben crear facturas de demostraci\u00f3n?",
    confirmDemoAccessLogs: "\u00bfSe deben crear registros de acceso de demostraci\u00f3n?",
    confirmDemoReplace: "\u00bfCargar datos de demostraci\u00f3n para {name} en modo REPLACE ahora? Los empleados, subcontratistas y registros existentes ser\u00e1n reemplazados.",
    confirmDemoAppend: "\u00bfCargar datos de demostraci\u00f3n para {name} en modo APPEND adicionalmente?",
    confirmExportAudit: "\u00bfIncluir registro de auditor\u00eda en la exportaci\u00f3n?",
    confirmExportDayClose: "\u00bfIncluir acuses de cierre de d\u00eda en la exportaci\u00f3n?",
    confirmExportDeleted: "\u00bfIncluir entradas eliminadas en la exportaci\u00f3n?",
    confirmExportAll: "Como superadmin: \u00bfexportar todo el sistema? (No = solo empresa actual)",
    confirmExportDownload: "\u00bfDescargar exportaci\u00f3n del sistema{scope} ahora?",
    confirmLogout: "\u00bfRealmente cerrar sesi\u00f3n?",
    confirmImportChangesOnly: "\u00bfImportar solo cambios? (Recomendado)",
    confirmBulkRetrySelected: "\u00bfReenviar {count} factura(s) seleccionada(s) ahora?",
    confirmBulkRetryCritical: "\u00bfReenviar {count} factura(s) cr\u00edtica(s) ahora?",
    confirmPhotoMatchFailed: "Comparaci\u00f3n de fotos fallida ({score}%). Solo el superadmin puede guardar con riesgo. \u00bfGuardar de todas formas?",
    promptDocEmail: "Establecer correo de documentos para {name}",
    promptTurnstilePassword: "Establecer contrase\u00f1a de torniquete para {name} (m\u00edn. 4 caracteres):",
    promptTurnstilePasswordNew: "Establecer nueva contrase\u00f1a de torniquete (m\u00edn. 4 caracteres):",
    promptCopyData: "Datos para copiar:",
    promptAppLink: "Enlace de la app para el empleado:",
    promptPhotoOverrideReason: "Por favor, ingrese el motivo de la anulaci\u00f3n de foto (al menos 8 caracteres):",
    promptNewPassword: "Ingrese la nueva contrase\u00f1a (al menos 8 caracteres):",
    promptTfaCode: "Por favor, ingrese el c\u00f3digo de 6 d\u00edgitos de su app de autenticaci\u00f3n:",
    promptTfaDisableCode: "Por favor, ingrese el c\u00f3digo 2FA actual para desactivar:",
    promptDemoMode: "Datos de demostraci\u00f3n para {name}: ingresar modo (replace o append)",
    promptRejectionReason: "Motivo de rechazo (obligatorio):",
    promptRejectApproval: "Por favor, ingrese el motivo del rechazo:",
    invoiceTitle: "Factura",
    invoiceAltLogo: "Logo de empresa",
    invoiceLabelNumber: "N\u00famero de factura:",
    invoiceLabelDate: "Fecha de factura:",
    invoiceLabelDue: "Fecha de vencimiento:",
    invoiceLabelCustomer: "Cliente:",
    invoiceLabelContact: "Persona de contacto:",
    invoiceLabelPeriod: "Per\u00edodo de servicio:",
    invoiceColService: "Servicio / Empleado",
    invoiceColAccess: "Accesos",
    invoiceColNet: "Importe neto",
    invoiceRowUnknown: "Desconocido",
    invoiceRowPlan: "Plan: {label}",
    invoiceTotalNet: "Subtotal neto",
    invoiceTotalVat: "IVA ({rate} %)",
    invoiceTotalGross: "Importe total",
    invoiceFooter: "Gracias por la colaboraci\u00f3n. Esta factura fue creada digitalmente y puede enviarse directamente.",
    invoiceHistoryEmpty: "A\u00fan no hay facturas enviadas ni guardadas.",
    invoiceHistoryRecipient: "Destinatario:",
    invoiceHistoryTotal: "Total:",
    invoiceHistoryCreated: "Creado:",
    invoiceHistorySent: "Enviado:",
    invoiceHistoryError: "Error:",
    tfaStatusActive: "La 2FA est\u00e1 activa",
    tfaStatusInactive: "La 2FA no est\u00e1 activa",
    tfaBtnSetup: "Configurar 2FA",
    tfaBtnEnable: "Activar 2FA",
    tfaBtnDisable: "Desactivar 2FA",
    tfaQrHint: "Configurar secreto con app de autenticaci\u00f3n:",
    tfaSecretLabel: "C\u00f3digo manual:",
    tfaCodeLabel: "C\u00f3digo de la app:",
    tfaCodePlaceholder: "C\u00f3digo de 6 d\u00edgitos",
    tfaEnableHint: "Ingresa el c\u00f3digo de 6 d\u00edgitos de tu app de autenticaci\u00f3n y haz clic en 'Activar'.",
  },
  it: {
    authEyebrow: "Pagina di accesso",
    authTitle: "Accesso sicuro a BauPass Control",
    authCopy: "Il super admin mantiene il controllo completo del sistema. Gli admin aziendali vedono solo la propria azienda. L'accesso tornello ha una modalità rapida.",
    authPlatform: "Piattaforma",
    authOperator: "Operatore",
    authTurnstile: "Endpoint tornello",
    loginUsernameLabel: "Nome utente",
    loginUsernamePlaceholder: "Nome utente",
    loginPasswordLabel: "Password",
    loginPasswordPlaceholder: "Inserisci la password",
    loginOtpLabel: "Codice OTP (se 2FA è attiva)",
    loginOtpPlaceholder: "123456",
    uiLanguageLabel: "Lingua",
    loginScopeLabel: "Tipo di accesso",
    loginScopeAuto: "Automatico",
    loginScopeServerAdmin: "Admin server",
    loginScopeCompanyAdmin: "Admin azienda",
    loginScopeTurnstile: "Tornello",
    supportReadOnlyAlert: "Questo accesso di supporto è in sola lettura. Le modifiche sono bloccate in questa sessione.",
    supportReadOnlyTitle: "Modalità supporto: sola lettura",
    supportLoginActive: "Accesso supporto attivo:",
    supportCompanyFallback: "Azienda",
    supportStartedBy: "avviato da",
    supportReadOnlyNotice: "Dopo l'accesso, l'operatività è in sola lettura.",
    supportModeLabel: "Modalità supporto:",
    supportReadOnlyFor: "Sola lettura per",
    supportCompanyLoginConfirmPrefix: "Passare al login aziendale per",
    supportCompanyLoginConfirmSuffix: "? La sessione admin corrente verrà disconnessa. Dopo, l'accesso sarà in sola lettura.",
    supportCompanyLoginOpenedPrefix: "Login per",
    supportCompanyLoginOpenedSuffix: "aperto. Accedi ora con l'admin aziendale. Questa sessione resta in sola lettura.",
    supportModeReadOnlyLine: "Modalità supporto attiva: sola lettura.",
    supportReadOnlyShort: "Modalità supporto: sola lettura.",
    loginButton: "Accedi",
    demoAccessTitle: "Account demo",
    demoSuperAdmin: "Super Admin: superadmin / 1234",
    demoCompanyAdmin: "Admin azienda: firma / 1234",
    demoTurnstile: "Tornello: drehkreuz / 1234",
    desktopAppTitle: "App desktop",
    desktopInstallHint: "Questo portale può essere installato sul computer come app locale.",
    desktopInstallButton: "Installa su questo computer",
    // Shell
    sidebarEyebrow: "Portale aziendale",
    sidebarCopy: "Registra i lavoratori, scatta foto, crea badge digitali e gestisci il controllo accessi.",
    sidebarCardTitle: "Modalità noleggio",
    sidebarCardStrong: "Multi-azienda",
    sidebarCardDesc: "Ogni impresa edile gestisce il proprio team separatamente. Il super admin mantiene il controllo del sistema.",
    navDashboard: "Pannello di controllo",
    navWorkers: "Lavoratori",
    navBadge: "Badge",
    navAccess: "Accesso",
    navInvoices: "Fatture",
    navAdmin: "Amministrazione",
    topbarEyebrow: "Stato del sistema",
    topbarHeading: "Badge cantiere e controllo accessi",
    btnSeedData: "Dati demo",
    btnExport: "Esporta sistema",
    btnImport: "Importa sistema",
    btnLogout: "Disconnessione sicura",
    dashEyebrow: "MVP migliorato",
    dashHeading: "Badge digitali con foto, Badge ID e check-in tornello",
    dashSubtext: "Progettato per il noleggio alle imprese edili.",
    dashBadge1: "Scatto foto",
    dashBadge2: "Registro accessi",
    dashBadge3: "Multi-tenant",
    reportingEyebrow: "Report",
    reportingH3: "Stato pagamento e blocco",
    accessWeekEyebrow: "7 giorni",
    accessWeekH3: "Accesso giornaliero",
    recentEyebrow: "Attività recente",
    recentH3: "Registro accessi",
    porterLiveEmpty: "L'ultimo accesso verrà mostrato qui al primo ingresso.",
    workersFormEyebrow: "Dati anagrafici",
    workersFormH3: "Registra lavoratore o visitatore",
    labelType: "Tipo",
    optWorker: "Lavoratore",
    optVisitor: "Visitatore",
    labelFirm: "Azienda",
    labelSubcompany: "Sub-azienda",
    optNoSubcompany: "Nessuna sub-azienda",
    labelNewSubcompany: "Nuova sub-azienda",
    btnAddSubcompany: "Crea sub-azienda",
    labelFirstName: "Nome",
    labelLastName: "Cognome",
    labelInsuranceNumber: "Numero assicurazione",
    labelRoleField: "Mansione",
    labelSite: "Cantiere",
    siteFieldHint: "Inserire l'indirizzo completo – necessario per il controllo GPS al login",
    labelPhysicalCard: "ID tessera fisica (NFC/RFID)",
    labelValidUntil: "Valido fino al",
    labelVisitorCompany: "Azienda del visitatore",
    labelVisitPurpose: "Scopo della visita",
    labelHostName: "Contatto in cantiere",
    labelVisitEndAt: "Fine visita",
    visitorHint: "I visitatori sono validi per alcune ore o fino a fine giornata. Gli accessi aperti vengono chiusi automaticamente alle 00:00 al pi\u00f9 tardi, la tessera rimane conservata per i report.",
    labelWorkerStatus: "Stato",
    optStatusActive: "Attivo",
    optStatusLocked: "Bloccato",
    optStatusExpired: "Scaduto",
    labelBadgePin: "Badge PIN per login app",
    btnStartCamera: "Avvia fotocamera",
    btnCapturePhoto: "Scatta foto",
    btnUploadPhoto: "Carica foto",
    btnPhotoUp: "↑ Su",
    btnPhotoLeft: "← Sinistra",
    btnPhotoRight: "Destra →",
    btnPhotoDown: "Giù ↓",
    btnPhotoReset: "Reimposta posizione",
    btnWorkerSubmit: "Salva lavoratore e crea badge",
    btnWorkerCancelEdit: "Annulla modifica",
    workersListEyebrow: "Registrazioni",
    workersListH3: "Lavoratori registrati",
    btnWorkerCsv: "Scarica lista PDF",
    btnBulkDelete: "Elimina selezionati",
    btnBulkActive: "Stato: attivo",
    btnBulkInactive: "Stato: inattivo",
    btnBulkCancel: "Annulla",
    badgeEyebrow: "Identità digitale",
    badgeH3: "Anteprima badge",
    badgeEmptyState: "Crea o seleziona prima un lavoratore.",
    badgeScanEyebrow: "Aiuto scansione",
    badgeScanH3: "Codice badge",
    badgeScanEmpty: "Nessun badge selezionato.",
    badgeTitleVisitor: "Tessera visitatore digitale",
    badgeTitleDayPass: "Pass giornaliero cantiere digitale",
    badgeTitleRegular: "Badge cantiere digitale",
    badgeUnknownCompany: "Azienda sconosciuta",
    badgeQrHint: "Scansiona il QR, installa l'app e apri il badge direttamente.",
    badgeLabelBadgeId: "Badge-ID",
    badgeMetaQrFunc: "Funzione QR",
    badgeMetaQrFuncVal: "Installazione app lavoratori",
    badgeMetaRoleLabel: "Ruolo nel sistema",
    badgePhotoUploadHint: "Scatta o carica una foto",
    appPinLabel: "PIN app",
    pinNotRequired: "non necessario",
    pinSet: "impostato",
    pinMissing: "mancante",
    cardLabel: "Carta",
    cardUnassigned: "non assegnata",
    btnEdit: "Modifica",
    btnDelete: "Elimina",
    btnRestore: "Ripristina",
    btnAppLink: "Link app",
    btnResetPin: "Reimposta PIN",
    confirmDeleteWorker: "Eliminare il lavoratore ora?",
    alertDeleteWorkerFailed: "Impossibile eliminare il lavoratore: {error}",
    alertRestoreWorkerFailed: "Impossibile ripristinare il lavoratore: {error}",
    alertAppLinkCreateFailed: "Impossibile creare il link app: {error}",
    promptResetPinFor: "Nuovo PIN badge per {name} (4-8 cifre):",
    alertPinMustDigits: "Il PIN deve contenere da 4 a 8 cifre.",
    alertPinResetSuccessFor: "PIN di {name} reimpostato con successo.",
    alertPinResetFailed: "Impossibile reimpostare il PIN: {error}",
    alertPhotoOverrideApproved: "Sostituzione foto approvata. I dati del lavoratore sono stati salvati.",
    alertPhotoOverrideApproveFailed: "Approvazione fallita: {error}",
    alertPhotoOverrideRejectReasonRequired: "E necessario un motivo di rifiuto.",
    alertPhotoOverrideRejected: "Sostituzione foto rifiutata.",
    alertPhotoOverrideRejectFailed: "Rifiuto fallito: {error}",
    alertDocEmailSaveFailed: "L'e-mail documento non ha potuto essere salvata: {error}",
    alertCompanyDeleted: "L'azienda {name} e stata eliminata.",
    alertCompanyDeleteFailed: "L'azienda {name} non ha potuto essere eliminata: {error}",
    alertCompanyLocked: "L'azienda {name} e stata bloccata.",
    alertCompanyUnlocked: "Il blocco di {name} e stato rimosso.",
    alertCompanyStatusChangeFailed: "Il cambio di stato di {name} e fallito: {error}",
    alertBrandingPresetSaveFailed: "Il preset di design non ha potuto essere salvato: {error}",
    alertPasswordMinLength: "La password deve contenere almeno 4 caratteri.",
    alertTurnstileCreateFailed: "Il tornello non ha potuto essere creato: {error}",
    alertTurnstilePasswordUpdated: "La password del tornello e stata aggiornata.",
    alertTurnstilePasswordResetFailed: "Il reset della password e fallito: {error}",
    alertApiKeyRotationFailed: "La rotazione della chiave API e fallita: {error}",
    alertTurnstileToggleFailed: "Il tornello non ha potuto essere commutato: {error}",
    alertWorkerDeletedCannotEdit: "I lavoratori eliminati non possono essere modificati.",
    alertDataCopied: "Dati copiati.",
    alertPrintWindowFailed: "La finestra di stampa non ha potuto essere aperta.",
    alertAppLinkCopied: "Link dell'app copiato.",
    alertQrNotReadyYet: "Il codice QR e ancora in generazione. Riprovare tra poco.",
    alertAccessBookingFailed: "L'accesso non ha potuto essere prenotato: {error}",
    alertWorkerSaveFailed: "Il lavoratore non ha potuto essere salvato: {error}",
    alertPhotoMatchFailed: "Confronto foto fallito ({score}%). Il salvataggio e bloccato. Riprendere la foto o contattare un superamministratore.",
    alertOverrideReasonTooShort: "Il motivo della sostituzione e troppo breve. Inserire almeno 8 caratteri.",
    alertPhotoOverrideRequested: "Sostituzione foto richiesta (ID approvazione: {id}).\nUn secondo superamministratore deve approvare la modifica prima che venga salvata.",
    alertBadgePinInvalid: "Il PIN del badge deve contenere da 4 a 8 cifre.",
    alertDuplicatePhysicalCardId: "Questo ID carta fisica e gia assegnato a un altro lavoratore.",
    alertPhotoOverrideSuperadminOnly: "La sostituzione foto e consentita solo ai superamministratori.",
    alertPhotoOverrideReasonRequired: "Fornire un motivo sufficiente per la sostituzione della foto.",
    alertInvoiceSavedSendFailed: "Fattura salvata, invio fallito: {error}",
    alertInvoiceNumberDuplicate: "Il numero di fattura {number} e gia in uso. Usare un numero diverso.",
    alertInvoiceSendFailed: "La fattura non ha potuto essere inviata: {error}",
    alertInvoiceNumberLength: "Il numero di fattura deve contenere tra 3 e 64 caratteri.",
    alertInvoiceDateInvalid: "La data della fattura o la data di scadenza non e valida.",
    alertInvoiceDueDateBeforeIssue: "La data di scadenza non puo essere anteriore alla data della fattura.",
    alertInvoiceVatRange: "L'IVA deve essere compresa tra 0 e 100.",
    alertApprovalRejectReasonRequired: "Il rifiuto senza motivo non e consentito.",
    alertApprovalConfirmed: "Approvazione confermata e azione eseguita.",
    alertApprovalRejected: "L'approvazione e stata rifiutata.",
    alertApprovalUpdated: "Approvazione aggiornata.",
    alertApprovalActionFailed: "L'azione di approvazione e fallita: {error}",
    alertInvoiceRetrySentDeadLetter: "La fattura e stata reinviata con successo e rimossa dalla coda morta.",
    alertInvoiceRetrySent: "La fattura e stata reinviata con successo.",
    alertInvoiceRetryFailed: "Il reinvio e fallito: {error}",
    alertDeadLetterResolveApprovalRequested: "Approvazione richiesta ({id}). Un secondo superamministratore deve confermare.",
    alertDeadLetterResolveFailed: "Il caso di lettera morta non ha potuto essere risolto: {error}",
    alertGenericError: "Errore: {error}",
    alertCollectionsStatusChangeFailed: "Il cambio di stato e fallito: {error}",
    alertActionFailed: "Azione fallita: {error}",
    alertInvoiceHistoryLoadFailed: "La cronologia non ha potuto essere caricata: {error}",
    alertAccessExportFailed: "L'esportazione del registro accessi e fallita: {error}",
    alertWorkerExportFailed: "L'esportazione dell'elenco lavoratori e fallita: {error}",
    alertSettingsSaveFailed: "Le impostazioni non hanno potuto essere salvate: {error}",
    alertSystemRepairDone: "La riparazione del sistema e stata eseguita.",
    alertSystemRepairFailed: "La riparazione del sistema e fallita: {error}",
    alertBrandingLoaded: "Marchio BauKometra caricato. Ora fare clic su Salva nelle impostazioni admin.",
    alertBrandingLoadFailed: "Il marchio non ha potuto essere caricato: {error}",
    alertBrandingAltLoaded: "Variante alternativa del marchio BauKometra caricata. Ora fare clic su Salva nelle impostazioni admin.",
    alertBrandingAltLoadFailed: "La variante di marchio alternativa non ha potuto essere caricata: {error}",
    alertDayCloseAckFailed: "La chiusura giornaliera non ha potuto essere confermata: {error}",
    alertOtpRequired: "La 2FA e attiva per questo account. Inserire il codice OTP.",
    alertOtpInvalid: "Il codice OTP non e valido o e scaduto. Inserire un nuovo codice.",
    alertTooManyAttempts: "Troppi tentativi falliti. Attendere 10 minuti e riprovare.",
    alertForbiddenTenantHost: "Questo accesso e consentito solo tramite il dominio aziendale approvato.",
    alertSupportCompanyMismatch: "Questo accesso non corrisponde all'azienda selezionata. Usare l'admin dell'azienda contrassegnata.",
    alertLoginCompanyLocked: "Questa azienda e bloccata. Saldare prima le fatture in sospeso o rimuovere il blocco nel superamministratore.",
    alertInvalidCredentials: "Nome utente o password non corretti. Verificare i dati e riprovare.",
    alertAdminIpNotAllowed: "L'accesso admin da questo IP non e consentito.",
    alertLoginScopeMismatch: "Il tipo di accesso non corrisponde all'account. Selezionare correttamente admin server / admin azienda.",
    alertLoginHttp405: "Accesso fallito: 405. La richiesta di accesso sta arrivando attualmente su {target}. Per GitHub Pages, il frontend deve usare il backend Render.",
    alertLoginFailed: "Accesso fallito: {error}",
    alertPasswordResetEnterUsername: "Inserire prima un nome utente o un'e-mail.",
    alertPasswordResetSent: "Se e stato trovato un account corrispondente, e stata inviata un'e-mail di ripristino.",
    alertPasswordResetFailed: "Il ripristino della password non ha potuto essere avviato: {error}",
    alertPasswordSetSuccess: "La password e stata impostata con successo. Ora e possibile effettuare l'accesso.",
    alertPasswordResetLinkFailed: "Il link di ripristino non ha potuto essere utilizzato: {error}",
    alertPasswordChanged: "Password modificata. Effettuare nuovamente l'accesso.",
    alertPasswordChangeFailed: "Il cambio password e fallito: {error}",
    alert2faSetupFailed: "Configurazione 2FA fallita: {error}",
    alert2faEnableFailed: "La 2FA non ha potuto essere attivata: {error}",
    alertDeviceDeleteFailed: "Errore nell'eliminazione: {error}",
    alertCompanyCreateFailed: "L'azienda non ha potuto essere creata: {error}",
    alert2faDisableFailed: "La 2FA non ha potuto essere disattivata: {error}",
    alertExportFailed: "L'esportazione e fallita: {error}",
    alertNoDemoCompany: "Nessuna azienda attiva trovata per i dati demo.",
    alertDemoModeInvalid: "Modalita non valida. Utilizzare replace o append.",
    alertDemoLoadFailed: "I dati demo non hanno potuto essere caricati: {error}",
    alertImportSuccess: "Importazione applicata con successo.",
    alertImportFailed: "L'importazione e fallita: {error}",
    alertCsvExportFailed: "L'esportazione CSV e fallita: {error}",
    alertIncidentExportFailed: "L'esportazione degli incidenti e fallita: {error}",
    alertSelectInvoiceForRetry: "Selezionare almeno una fattura nella coda.",
    alertBulkRetryDone: "Ripetizione massiva completata. Inviati: {sent}, Falliti: {failed}, Saltati: {skipped}",
    alertBulkRetryFailed: "La ripetizione massiva e fallita: {error}",
    alertNoCriticalCases: "Attualmente non ci sono casi critici (punteggio >= 70).",
    alertCriticalBulkRetryDone: "Ripetizione massiva critica completata. Inviati: {sent}, Falliti: {failed}, Saltati: {skipped}",
    alertCriticalBulkRetryFailed: "La ripetizione massiva critica e fallita: {error}",
    alertDesktopInstallFailed: "L'installazione desktop non ha potuto essere avviata.",
    alertSubcompanyCreateFailed: "Il subappaltatore non ha potuto essere creato: {error}",
    alertDeleteFailed: "Errore nell'eliminazione: {error}",
    alertStatusChangeFailed: "Errore nel cambio di stato: {error}",
    alertReassignmentDone: "Riassegnazione completata. Corrispondenze: {count}",
    alertReassignmentFailed: "La riassegnazione e fallita: {error}",
    detailCloseTitle: "Chiudi",
    detailPhotoAlt: "Foto lavoratore",
    detailCheckinBtn: "Entrata (Check-in)",
    detailCheckoutBtn: "Uscita (Check-out)",
    accessFormEyebrow: "Tornello",
    accessFormH3: "Check-in e check-out",
    labelAccessBadge: "Badge ID o lavoratore",
    labelAccessDir: "Direzione",
    labelAccessGate: "Cancello",
    labelAccessNote: "Nota",
    optCheckin: "Entrata",
    optCheckout: "Uscita",
    btnAccessSubmit: "Registra accesso",
    porterEmpty: "Vista portiere: seleziona un lavoratore e registra l'accesso.",
    accessLogEyebrow: "Registro accessi",
    accessLogH3: "Ingressi e uscite con timestamp",
    labelFrom: "Da",
    labelTo: "A",
    labelFilterDir: "Direzione",
    labelFilterGate: "Tornello",
    optAllDir: "Tutti",
    btnApplyFilter: "Applica filtro",
    btnResetFilter: "Reimposta filtro",
    btnAccessCsv: "Esporta accessi CSV",
    dailyReportEyebrow: "Report giornaliero",
    dailyReportH3: "Per cancello",
    btnPrintDaily: "Stampa report giornaliero",
    btnPrintVisitorWeekly: "Stampa lista visitatori settimanale",
    hourlyEyebrow: "Analisi oraria",
    hourlyH3: "Ingressi/uscite per ora",
    warningsEyebrow: "Avvisi",
    warningsH3: "Entrata senza uscita",
    invListEyebrow: "Fatturazione",
    invListH3: "Fatture e stato pagamento",
    optAllStatus: "Tutti gli stati",
    optDraft: "Bozza",
    optSent: "Inviata",
    optOverdue: "Scaduta",
    optPaid: "Pagata",
    optFailed: "Errore",
    btnRefreshList: "Aggiorna",
    inkassoEyebrow: "Recupero crediti",
    inkassoH3: "Scaduta, pre-blocco, bloccata",
    optAllPositions: "Tutte le posizioni aperte",
    optPrelock: "Pre-blocco",
    optLocked: "Già bloccato",
    adminEyebrow: "Centro amministrativo",
    adminH3: "Sistema e configurazione",
    sysStatusEyebrow: "Stato del sistema",
    sysStatusH3: "Accesso emergenza e riparazione",
    btnRefreshStatus: "Aggiorna stato",
    btnRepairSessions: "Ripara sessioni",
    superAdminEyebrow: "Controllo sistema",
    superAdminH3: "Impostazioni super admin",
    labelPlatformName: "Nome della piattaforma",
    labelOperatorName: "Operatore",
    labelTurnstileEp: "Endpoint API tornello",
    labelSmtpHost: "SMTP Host",
    labelSmtpPort: "SMTP Port",
    labelSmtpUser: "Utente SMTP",
    labelSmtpPass: "Password SMTP",
    labelSenderEmail: "E-mail mittente",
    labelSenderName: "Nome mittente",
    labelTls: "TLS attivo",
    optTlsYes: "Sì",
    optTlsNo: "No",
    btnTestSmtp: "Invia email di prova",
    optYes: "Sì",
    optNo: "No",
    labelIpWhitelist: "Whitelist IP admin",
    labelEnforceDomain: "Imponi dominio aziendale",
    btnSaveAdmin: "Salva impostazioni admin",
    companyNewEyebrow: "Tenant",
    companyNewH3: "Aggiungi impresa edile",
    labelCompanyName: "Nome azienda",
    labelCompanyContact: "Persona di contatto",
    labelBillingEmail: "E-mail fatturazione",
    labelAccessHost: "Dominio accesso azienda",
    labelPlan: "Piano",
    labelCompanyStatus: "Stato",
    optCompanyActive: "Attivo",
    optCompanyTest: "Test",
    optCompanyPaused: "In pausa",
    optCompanyLocked: "Bloccato (pagamento in ritardo)",
    labelCompanyAdminPassword: "Password admin iniziale",
    companyAdminPasswordPlaceholder: "es. Sicuro!2025",
    btnCreateCompany: "Crea azienda",
    accountEyebrow: "Account",
    accountH3: "Cambia password",
    labelCurrentPassword: "Password attuale",
    labelNewPassword: "Nuova password",
    btnChangePassword: "Cambia password",
    tfaEyebrow: "Doppio fattore",
    tfaH3: "Gestione 2FA",
    companiesListEyebrow: "Tenant",
    companiesListH3: "Aziende e piani",
    invFormEyebrow: "Fatture",
    invFormH3: "Invia con logo e design",
    labelInvFirm: "Azienda",
    labelInvNumber: "Numero fattura",
    labelInvRecipient: "E-mail destinatario",
    labelInvDate: "Data fattura",
    labelInvDueDate: "Data scadenza",
    labelInvPeriod: "Periodo di servizio",
    labelInvDescription: "Descrizione servizio",
    labelInvNet: "Importo netto (EUR)",
    labelInvVat: "IVA (%)",
    btnPrintInvoice: "Stampa fattura / Salva PDF",
    btnSendInvoice: "Invia fattura per e-mail",
    btnUpdatePreview: "Aggiorna anteprima",
    auditEyebrow: "Registro sicurezza",
    auditH3: "Registro audit",
    labelAuditEvent: "Tipo evento",
    labelAuditRole: "Ruolo",
    btnAuditCsv: "Esporta audit CSV",
    reportingPaid: "Pagata",
    reportingOpen: "Aperta",
    reportingOverdue: "Scaduta",
    reportingInvoicesLabel: "fatture",
    reportingOverdueTotal: "Totale scaduto",
    reportingLockedCompanies: "Aziende bloccate",
    reportingAutoSuspensions30d: "Sospensioni auto (30g)",
    reportingGeneratedAt: "Generato il",
    reportingNoOverdueCompanies: "Nessuna azienda in ritardo.",
    reportingFallbackCompany: "Azienda",
    reportingOverdueInvoicesLabel: "fatture scadute",
    reportingNoAccessDataLast7Days: "Nessun dato di accesso per gli ultimi 7 giorni.",
    reportingCheckin: "Entrata",
    reportingCheckout: "Uscita",
    navDocuments: "Documenti",
    docInboxEyebrow: "Posta in arrivo",
    docInboxH3: "Documenti in entrata per e-mail",
    btnDocInboxRefresh: "Aggiorna",
    btnDocInboxSync: "Sincronizza casella",
    btnDocInboxPoll: "Recupera casella ora",
    btnDocInboxRematch: "Riassegna",
    docEmailInfoLabel: "E-mail documenti (i lavoratori inviano le prove qui):",
    btnCopyEmail: "Copia",
    btnCopyEmailDone: "Copiato!",
    docInboxHint: "I lavoratori inviano le loro prove all'indirizzo e-mail documenti configurato. Il portiere assegna gli allegati a un lavoratore qui.",
    docAssignEyebrow: "Assegna",
    docAssignH3: "Assegna allegato a un lavoratore",
    docInboxEmpty: "Nessuna e-mail non elaborata.",
    docInboxEmailFrom: "Da",
    docInboxEmailSubject: "Oggetto",
    docInboxEmailDate: "Data",
    docInboxAttachments: "Allegati",
    btnAssignDoc: "Assegna",
    btnDismissEmail: "Ignora",
    docAssignWorkerLabel: "Seleziona lavoratore",
    docAssignTypeLabel: "Tipo documento",
    docAssignNotesLabel: "Note (facoltativo)",
    btnConfirmAssign: "Assegna documento",
    docAssignSuccess: "Documento assegnato con successo.",
    docTypeMindestlohnnachweis: "Prova salario minimo",
    docTypePersonalausweis: "Carta d'identità / Passaporto",
    docTypeSozialversicherungsnachweis: "Attestato previdenza sociale",
    docTypeArbeitserlaubnis: "Permesso di lavoro",
    docTypeGesundheitszeugnis: "Certificato sanitario",
    docTypeSonstiges: "Altro",
    workerDocsHeading: "Documenti salvati",
    workerDocsEmpty: "Nessun documento registrato.",
    workerAkteLabel: "Fascicolo lavoratore",
    btnUploadWorkerDoc: "Carica documento",
    btnConfirmUpload: "Carica",
    docUploadSuccess: "Documento caricato con successo.",
    confirmDeleteDoc: "Eliminare questo documento?",
    btnDownloadDoc: "Scarica",
    btnDeleteDoc: "Elimina",
    imapSectionEyebrow: "Casella documenti",
    imapSectionH4: "Casella IMAP per le prove",
    labelImapHint: "I lavoratori inviano le prove a questo indirizzo. Il sistema controlla la casella ogni pochi minuti.",
    labelImapHost: "IMAP Host",
    labelImapPort: "IMAP Porta",
    labelImapUser: "Utente IMAP",
    labelImapPass: "Password IMAP",
    labelImapFolder: "Cartella IMAP",
    labelImapSsl: "SSL/TLS",
    btnImapTest: "Testa connessione IMAP",
    imapTestOk: "Connessione riuscita!",
    imapTestFail: "Connessione fallita",
    navDevices: "Dispositivi",
    devicesEyebrow: "Hardware",
    devicesH3: "Box intelligenti e dispositivi OSDP",
    devicesHint: "Ogni box invia un segnale ogni 30–60 s. Nessun segnale >90 s = offline.",
    btnAddDevice: "Aggiungi dispositivo",
    addDeviceEyebrow: "Nuovo dispositivo",
    addDeviceH3: "Registra dispositivo",
    labelDeviceName: "Nome",
    labelDeviceLocation: "Posizione",
    labelDeviceType: "Tipo / Protocollo",
    btnDeviceRegister: "Registra dispositivo e genera chiave API",
    deviceOnline: "Online",
    deviceOffline: "Offline",
    deviceNeverSeen: "Nessun segnale ancora",
    alertInstallUnavailable: "L'installazione non è direttamente disponibile in questo browser. In Chrome o Edge scegli 'Installa app' dal menu.",
    alertSessionExpired: "Sessione scaduta. Accedi di nuovo.",
    btnPrintBadge: "Stampa badge",
    greetingMorning: "Buongiorno",
    greetingDay: "Buon pomeriggio",
    greetingEvening: "Buonasera",
    greetingNight: "Buonanotte",
    greetingSuffix: "Buon turno!",
    adminWorkerAppSectionTitle: "App lavoratori",
    adminWorkerAppSectionCopy: "Controlla l'intera app lavoratori: accesso, badge digitale e utilizzo QR.",
    adminWorkerAppPinLockHint: "Dopo 2 minuti di inattività il lavoratore deve inserire di nuovo il badge PIN per vedere il badge.",
    optPlanDayPassRecommended: "Tessera visitatore (consigliato)",
    optPlanMonthlySite: "Mensile per cantiere",
    optPlanPerWorker: "Per lavoratore",
    optPlanFlatCompany: "Forfait per azienda",
    optPlanDayPassPrice: "Tessera visitatore (19 EUR/giorno)",
    loginForgotPassword: "Password dimenticata",
    legalImpressum: "Note legali",
    legalPrivacy: "Privacy",
    legalCloseTitle: "Chiudi",
    legalFallbackEmpty: "Nessun testo disponibile.",
    invoiceMgmtTitle: "Gestione fatture",
    invoiceMgmtCopy: "Visualizza fatture aperte e pagate. Segna le fatture come pagate per sbloccare automaticamente le aziende. Tutte le attività sono registrate nell'audit log.",
    invoiceOpsEyebrow: "Operazioni",
    invoiceOpsH3: "SLA invio e stato errori",
    invoiceSendEyebrow: "Invio",
    invoiceSendH3: "Coda email non riuscite",
    optRetryAll: "Tutti gli invii non riusciti",
    optRetryPriority: "Priorità prima",
    optRetryMaxed: "Max tentativi raggiunti",
    optRetryTodayFailed: "Falliti oggi",
    invoiceRetryTopIssuesOnly: "Solo i miei problemi principali",
    btnRetryCriticalSend: "Invia ora solo i critici",
    btnRetryExportCsv: "CSV coda",
    btnIncidentExportCsv: "CSV incidenti",
    btnRetryBulkSend: "Rinvia selezionati",
    invoiceApprovalsEyebrow: "Approvazioni",
    invoiceApprovalsH3: "Controllo a quattro occhi per azioni critiche",
    optApprovalAllActions: "Tutti i tipi di azione",
    optApprovalBulkRetry: "Riprova massiva",
    optApprovalDeadLetterResolve: "Risolvi dead-letter",
    legalSectionEyebrow: "Legale",
    legalSectionTitle: "Note legali e privacy",
    labelImpressumText: "Testo note legali",
    labelPrivacyText: "Informativa privacy",
    legalTextsHint: "Questi testi appaiono nella pagina di accesso sotto 'Note legali' e 'Privacy'.",
    labelCompanyDocumentEmail: "Email documenti",
    labelBrandingPreset: "Preset branding",
    optBrandingConstruction: "Costruzioni",
    optBrandingIndustry: "Industria",
    optBrandingPremium: "Premium",
    optPlanStarter: "Starter (49 EUR)",
    optPlanProfessional: "Professional (99 EUR)",
    optPlanEnterprise: "Enterprise (199 EUR)",
    accessFeedbackCheckin: "Accesso registrato",
    badgePinHint: "Il login con badge nell'app lavoratori funziona solo con Badge-ID e questo PIN. In modifica puoi impostare un nuovo PIN qui.",
    badgePinPlaceholder: "da 4 a 8 cifre",
    bulkSelectAll: "Seleziona tutto",
    btnDayCloseAcknowledge: "Conferma chiusura giornata",
    btnExportCompanyDocEmails: "Esporta e-mail documenti",
    btnLoadAltBrand: "Carica alternativo",
    btnLoadDefaultBrand: "Carica branding predefinito",
    cameraNotStarted: "Fotocamera non avviata.",
    complianceEyebrow: "Conformità",
    complianceH3: "Stato documenti",
    dayCloseCommentLabel: "Commento chiusura giornata",
    dayCloseCommentPlaceholder: "es. Capo turno informato, uscita da registrare",
    deadLetterEyebrow: "Dead-Letter",
    deadLetterH3: "Fatture da risolvere manualmente",
    filterByCompanyPlaceholder: "Filtra per azienda…",
    filterQueueByCompanyPlaceholder: "Filtra coda per azienda…",
    formSectionAppFeaturesEyebrow: "Funzionalità app",
    formSectionBrandingEyebrow: "Design fattura",
    formSectionBrandingH4: "Colori & Brand",
    formSectionEmailEyebrow: "E-Mail",
    formSectionPlatformEyebrow: "Piattaforma",
    formSectionPlatformH4: "Identità & Operatore",
    formSectionSecurityH4: "Accesso e isolamento",
    formSectionSmtpH4: "Invio SMTP",
    invoiceLogoHint: "Il logo della fattura viene usato anche come icona di sistema e icona dell'app lavoratori.",
    invoicePreviewEyebrow: "Anteprima",
    invoicePreviewH3: "Verifica fattura prima dell'invio",
    maxAgeFilterPlaceholder: "Età max in minuti (0 = tutti)",
    optDeviceOsdp: "OSDP (RS-485)",
    optDeviceTcp: "TCP/IP Smart-Box",
    optDeviceWiegand: "Lettore Wiegand",
    optPinLockActive: "Attivo – Blocco PIN impedisce la condivisione del telefono",
    optPinLockDisabled: "Disabilitato – Badge sempre accessibile",
    optRoleCompanyAdmin: "Admin aziendale",
    optRoleSuperAdmin: "Super Admin",
    optWorkerAppActive: "Attivo – Badge, QR e login badge abilitati",
    optWorkerAppLocked: "Bloccato – App mobile disabilitata",
    photoAdjustHelp: "Sposta la foto dopo la cattura per farla rientrare correttamente nel lato destro del badge.",
    photoOverrideH3: "Approvazioni di override foto in attesa",
    photoRequiredHint: "Obbligatorio: Senza foto il badge non può essere salvato.",
    photoSharpenLabel: "Nitidezza:",
    photoWhiteBgLabel: "Sfondo completamente bianco (attivo)",
    photoZoomCropLabel: "Zoom / Ritaglia",
    recentAuditEyebrow: "Audit",
    recentAuditH3: "Eventi recenti del sistema",
    rentalModelLabel: "Modello di noleggio",
    sectionSecurityEyebrow: "Sicurezza",
    statusLoading: "Caricamento stato…",
    sysAlertActionBtn: "Vai alle fatture",
    sysAlertDefaultText: "Si sono verificati errori critici nell'invio delle fatture.",
    sysAlertHeading: "Problema critico di invio",
    turnstileCountLabel: "Numero di tornelli",
    turnstilePasswordLabel: "Password iniziale tornello",
    workerAppEnabledLabel: "App badge mobile (badge digitale + QR)",
    workerPassLockLabel: "Proteggere il badge con blocco PIN",
    workerSearchPlaceholder: "Cerca: Nome, Badge-ID, Cantiere …",
    confirmDeleteCompanyText: "Eliminare la societ\u00e0 {name} e tutti i record associati?\n\nOK = eliminazione completa (incl. dipendenti, subappaltatori e log)\nAnnulla = non eliminare",
    confirmLockCompany: "Bloccare la societ\u00e0 {name} ora? L'admin, il tornello e l'app dipendenti di questa societ\u00e0 verranno bloccati.",
    confirmUnlockCompany: "Rimuovere il blocco di {name} ora? La societ\u00e0 potr\u00e0 accedere di nuovo.",
    confirmDeleteWorkerBulk: "Eliminare davvero {count} dipendenti?",
    confirmApiKeyRotate: "Rigenerare la chiave API per questo tornello ora? La chiave esistente perder\u00e0 immediatamente validit\u00e0.",
    confirmSystemRepair: "Eseguire la riparazione del sistema? Le sessioni scadute e i blocchi di accesso verranno puliti.",
    confirmApprovalDecision: "Davvero {decision} l'approvazione {id}?",
    confirmDeadLetterRetry: "Reinviare la fattura Dead-Letter ora?",
    confirmDeadLetterResolve: "Contrassegnare il caso Dead-Letter come risolto?",
    confirmInvoicePaid: "Contrassegnare questa fattura come pagata? L'eventuale blocco della societ\u00e0 sar\u00e0 rimosso.",
    confirmInvoiceRetry: "Reinviare la fattura ora?",
    confirmInvoicePaidSimple: "Contrassegnare la fattura come pagata ora?",
    confirmDemoInvoices: "Devono essere create anche fatture dimostrative?",
    confirmDemoAccessLogs: "Devono essere creati log di accesso dimostrativi?",
    confirmDemoReplace: "Caricare i dati dimostrativi per {name} in modalit\u00e0 REPLACE ora? Dipendenti, subappaltatori e log esistenti verranno sostituiti.",
    confirmDemoAppend: "Caricare i dati dimostrativi per {name} in modalit\u00e0 APPEND in aggiunta?",
    confirmExportAudit: "Includere il log di audit nell'esportazione?",
    confirmExportDayClose: "Includere le conferme di chiusura giornaliera nell'esportazione?",
    confirmExportDeleted: "Includere le voci eliminate nell'esportazione?",
    confirmExportAll: "Come superadmin: esportare l'intero sistema? (No = solo societ\u00e0 corrente)",
    confirmExportDownload: "Scaricare l'esportazione del sistema{scope} ora?",
    confirmLogout: "Vuoi davvero disconnetterti?",
    confirmImportChangesOnly: "Importare solo le modifiche? (Consigliato)",
    confirmBulkRetrySelected: "Reinviare {count} fattura/e selezionata/e ora?",
    confirmBulkRetryCritical: "Reinviare {count} fattura/e critica/e ora?",
    confirmPhotoMatchFailed: "Confronto foto fallito ({score}%). Solo il superadmin pu\u00f2 salvare con rischio. Salvare comunque?",
    promptDocEmail: "Impostare l'e-mail documenti per {name}",
    promptTurnstilePassword: "Impostare la password del tornello per {name} (min. 4 caratteri):",
    promptTurnstilePasswordNew: "Impostare una nuova password tornello (min. 4 caratteri):",
    promptCopyData: "Dati da copiare:",
    promptAppLink: "Link app per il dipendente:",
    promptPhotoOverrideReason: "Inserire il motivo dell'override foto (almeno 8 caratteri):",
    promptNewPassword: "Inserire la nuova password (almeno 8 caratteri):",
    promptTfaCode: "Inserire il codice a 6 cifre dall'app di autenticazione:",
    promptTfaDisableCode: "Inserire il codice 2FA attuale per disabilitare:",
    promptDemoMode: "Dati dimostrativi per {name}: inserire la modalit\u00e0 (replace o append)",
    promptRejectionReason: "Motivo del rifiuto (obbligatorio):",
    promptRejectApproval: "Inserire il motivo del rifiuto:",
    invoiceTitle: "Fattura",
    invoiceAltLogo: "Logo aziendale",
    invoiceLabelNumber: "Numero fattura:",
    invoiceLabelDate: "Data fattura:",
    invoiceLabelDue: "Data scadenza:",
    invoiceLabelCustomer: "Cliente:",
    invoiceLabelContact: "Referente:",
    invoiceLabelPeriod: "Periodo di servizio:",
    invoiceColService: "Servizio / Dipendente",
    invoiceColAccess: "Accessi",
    invoiceColNet: "Importo netto",
    invoiceRowUnknown: "Sconosciuto",
    invoiceRowPlan: "Piano: {label}",
    invoiceTotalNet: "Subtotale netto",
    invoiceTotalVat: "IVA ({rate} %)",
    invoiceTotalGross: "Importo totale",
    invoiceFooter: "Grazie per la collaborazione. Questa fattura e stata creata digitalmente e puo essere inviata direttamente.",
    invoiceHistoryEmpty: "Nessuna fattura inviata o salvata finora.",
    invoiceHistoryRecipient: "Destinatario:",
    invoiceHistoryTotal: "Totale:",
    invoiceHistoryCreated: "Creato:",
    invoiceHistorySent: "Inviato:",
    invoiceHistoryError: "Errore:",
    tfaStatusActive: "La 2FA e attiva",
    tfaStatusInactive: "La 2FA non e attiva",
    tfaBtnSetup: "Configura 2FA",
    tfaBtnEnable: "Abilita 2FA",
    tfaBtnDisable: "Disabilita 2FA",
    tfaQrHint: "Configura il segreto con l'app di autenticazione:",
    tfaSecretLabel: "Codice manuale:",
    tfaCodeLabel: "Codice dall'app:",
    tfaCodePlaceholder: "Codice a 6 cifre",
    tfaEnableHint: "Inserisci il codice a 6 cifre dalla tua app di autenticazione e clicca 'Abilita'.",
    tfaEmailLabel: "Indirizzo email per i codici OTP",
    tfaEmailPlaceholder: "admin@example.com",
    tfaActivateOneClickHint: "Inserisci il tuo indirizzo email e fai clic su Attiva. Un codice verrà inviato alla tua email ad ogni accesso.",
    alertTfaActivated: "Il 2FA è stato attivato.",
    alertTfaEmailRequired: "Inserisci un indirizzo email prima di attivare il 2FA.",
    alertOtpSent: "Un codice di sicurezza è stato inviato alla tua email. Controlla la tua casella di posta.",
    loginOtpSentNotice: "Codice inviato per email – controlla la casella",
    loginOtpBackBtn: "← Indietro",
  },
  pl: {
    authEyebrow: "Strona logowania",
    authTitle: "Bezpieczne logowanie do BauPass Control",
    authCopy: "Super administrator zachowuje pełną kontrolę nad systemem. Administratorzy firm widzą tylko swoją firmę. Logowanie bramki ma szybki tryb dostępu.",
    authPlatform: "Platforma",
    authOperator: "Operator",
    authTurnstile: "Endpoint bramki",
    loginUsernameLabel: "Nazwa użytkownika",
    loginUsernamePlaceholder: "Nazwa uzytkownika",
    loginPasswordLabel: "Hasło",
    loginPasswordPlaceholder: "Wpisz haslo",
    loginOtpLabel: "Kod OTP (jeśli 2FA jest aktywne)",
    loginOtpPlaceholder: "123456",
    uiLanguageLabel: "Język",
    loginScopeLabel: "Typ dostępu",
    loginScopeAuto: "Automatycznie",
    loginScopeServerAdmin: "Admin serwera",
    loginScopeCompanyAdmin: "Admin firmy",
    loginScopeTurnstile: "Bramka",
    supportReadOnlyAlert: "To logowanie wsparcia jest tylko do odczytu. Zmiany są zablokowane w tej sesji.",
    supportReadOnlyTitle: "Tryb wsparcia: tylko odczyt",
    supportLoginActive: "Aktywna sesja wsparcia:",
    supportCompanyFallback: "Firma",
    supportStartedBy: "uruchomione przez",
    supportReadOnlyNotice: "Po zalogowaniu dostęp będzie tylko do odczytu.",
    supportModeLabel: "Tryb wsparcia:",
    supportReadOnlyFor: "Tylko odczyt dla firmy",
    supportCompanyLoginConfirmPrefix: "Przejść do logowania firmy",
    supportCompanyLoginConfirmSuffix: "? Twoja bieżąca sesja admina zostanie wylogowana. Potem dostęp będzie tylko do odczytu.",
    supportCompanyLoginOpenedPrefix: "Logowanie dla",
    supportCompanyLoginOpenedSuffix: "otwarte. Zaloguj się teraz kontem administratora firmy. Ta sesja pozostaje tylko do odczytu.",
    supportModeReadOnlyLine: "Tryb wsparcia aktywny: tylko odczyt.",
    supportReadOnlyShort: "Tryb wsparcia: tylko odczyt.",
    loginButton: "Zaloguj się",
    demoAccessTitle: "Konta demo",
    demoSuperAdmin: "Super Admin: superadmin / 1234",
    demoCompanyAdmin: "Admin firmy: firma / 1234",
    demoTurnstile: "Bramka: drehkreuz / 1234",
    desktopAppTitle: "Aplikacja desktopowa",
    desktopInstallHint: "Ten portal można zainstalować na komputerze jak aplikację lokalną.",
    desktopInstallButton: "Zainstaluj na tym komputerze",
    // Shell
    sidebarEyebrow: "Portal firmowy",
    sidebarCopy: "Rejestruj pracowników, rób zdjęcia, twórz cyfrowe identyfikatory i zarządzaj kontrolą dostępu.",
    sidebarCardTitle: "Tryb wynajmu",
    sidebarCardStrong: "Obsługa wielu firm",
    sidebarCardDesc: "Każda firma budowlana zarządza swoim zespołem osobno. Super admin zachowuje kontrolę nad systemem.",
    navDashboard: "Pulpit",
    navWorkers: "Pracownicy",
    navBadge: "Identyfikator",
    navAccess: "Dostęp",
    navInvoices: "Faktury",
    navAdmin: "Administracja",
    topbarEyebrow: "Stan systemu",
    topbarHeading: "Identyfikatory budowlane i kontrola dostępu",
    btnSeedData: "Dane demo",
    btnExport: "Eksportuj system",
    btnImport: "Importuj system",
    btnLogout: "Bezpieczne wylogowanie",
    dashEyebrow: "Ulepszony MVP",
    dashHeading: "Cyfrowe identyfikatory ze zdjęciem, Badge ID i check-in bramki",
    dashSubtext: "Zaprojektowany do wynajmu firmom budowlanym.",
    dashBadge1: "Zdjęcie",
    dashBadge2: "Rejestr wejść",
    dashBadge3: "Multi-najemca",
    reportingEyebrow: "Raporty",
    reportingH3: "Status płatności i blokady",
    accessWeekEyebrow: "7 dni",
    accessWeekH3: "Codzienne wejścia",
    recentEyebrow: "Ostatnia aktywność",
    recentH3: "Rejestr wejść",
    porterLiveEmpty: "Ostatnie wejście pojawi się tutaj przy pierwszym zapisie.",
    workersFormEyebrow: "Dane podstawowe",
    workersFormH3: "Rejestracja pracownika lub gościa",
    labelType: "Typ",
    optWorker: "Pracownik",
    optVisitor: "Gość",
    labelFirm: "Firma",
    labelSubcompany: "Podwykonawca",
    optNoSubcompany: "Brak podwykonawcy",
    labelNewSubcompany: "Nowy podwykonawca",
    btnAddSubcompany: "Utwórz podwykonawcę",
    labelFirstName: "Imię",
    labelLastName: "Nazwisko",
    labelInsuranceNumber: "Numer ubezpieczenia",
    labelRoleField: "Stanowisko",
    labelSite: "Plac budowy",
    siteFieldHint: "Wpisz pełny adres – wymagany do weryfikacji GPS przy logowaniu",
    labelPhysicalCard: "ID karty fizycznej (NFC/RFID)",
    labelValidUntil: "Ważny do",
    labelVisitorCompany: "Firma gościa",
    labelVisitPurpose: "Cel wizyty",
    labelHostName: "Kontakt na budowie",
    labelVisitEndAt: "Koniec wizyty",
    visitorHint: "Goście są ważni przez kilka godzin lub do końca dnia. Otwarte wejścia są automatycznie wyrejestrowane najpóźniej o 00:00, karta jest zachowana do celów raportowania.",
    labelWorkerStatus: "Status",
    optStatusActive: "Aktywny",
    optStatusLocked: "Zablokowany",
    optStatusExpired: "Wygasły",
    labelBadgePin: "Badge PIN do logowania",
    btnStartCamera: "Uruchom kamerę",
    btnCapturePhoto: "Zrób zdjęcie",
    btnUploadPhoto: "Prześlij zdjęcie",
    btnPhotoUp: "↑ Góra",
    btnPhotoLeft: "← Lewo",
    btnPhotoRight: "Prawo →",
    btnPhotoDown: "Dół ↓",
    btnPhotoReset: "Resetuj pozycję",
    btnWorkerSubmit: "Zapisz pracownika i utwórz identyfikator",
    btnWorkerCancelEdit: "Anuluj edycję",
    workersListEyebrow: "Rekordy",
    workersListH3: "Zarejestrowani pracownicy",
    btnWorkerCsv: "Pobierz listę PDF",
    btnBulkDelete: "Usuń zaznaczone",
    btnBulkActive: "Status: aktywny",
    btnBulkInactive: "Status: nieaktywny",
    btnBulkCancel: "Anuluj",
    badgeEyebrow: "Tożsamość cyfrowa",
    badgeH3: "Podgląd identyfikatora",
    badgeEmptyState: "Najpierw utwórz lub wybierz pracownika.",
    badgeScanEyebrow: "Pomoc skanowania",
    badgeScanH3: "Kod identyfikatora",
    badgeScanEmpty: "Nie wybrano identyfikatora.",
    badgeTitleVisitor: "Cyfrowa karta go\u015bcia",
    badgeTitleDayPass: "Cyfrowa dzienna przepustka budowy",
    badgeTitleRegular: "Cyfrowa odznaka budowy",
    badgeUnknownCompany: "Nieznana firma",
    badgeQrHint: "Zeskanuj QR, zainstaluj aplikacj\u0119 i otw\u00f3rz odznak\u0119 bezpo\u015brednio.",
    badgeLabelBadgeId: "Badge-ID",
    badgeMetaQrFunc: "Funkcja QR",
    badgeMetaQrFuncVal: "Instalacja aplikacji pracownika",
    badgeMetaRoleLabel: "Rola w systemie",
    badgePhotoUploadHint: "Zr\u00f3b lub prze\u015blij zdj\u0119cie",
    appPinLabel: "PIN aplikacji",
    pinNotRequired: "nie wymagany",
    pinSet: "ustawiony",
    pinMissing: "brak",
    cardLabel: "Karta",
    cardUnassigned: "nieprzypisana",
    btnEdit: "Edytuj",
    btnDelete: "Usun",
    btnRestore: "Przywroc",
    btnAppLink: "Link aplikacji",
    btnResetPin: "Resetuj PIN",
    confirmDeleteWorker: "Usunac pracownika teraz?",
    alertDeleteWorkerFailed: "Nie udalo sie usunac pracownika: {error}",
    alertRestoreWorkerFailed: "Nie udalo sie przywrocic pracownika: {error}",
    alertAppLinkCreateFailed: "Nie udalo sie utworzyc linku aplikacji: {error}",
    promptResetPinFor: "Nowy PIN odznaki dla {name} (4-8 cyfr):",
    alertPinMustDigits: "PIN musi zawierac od 4 do 8 cyfr.",
    alertPinResetSuccessFor: "PIN dla {name} zostal pomyslnie zresetowany.",
    alertPinResetFailed: "Nie udalo sie zresetowac PIN: {error}",
    alertPhotoOverrideApproved: "Zastapienie zdjecia zatwierdzone. Dane pracownika zostaly zapisane.",
    alertPhotoOverrideApproveFailed: "Zatwierdzenie nieudane: {error}",
    alertPhotoOverrideRejectReasonRequired: "Wymagany jest powod odrzucenia.",
    alertPhotoOverrideRejected: "Zastapienie zdjecia odrzucone.",
    alertPhotoOverrideRejectFailed: "Odrzucenie nieudane: {error}",
    alertDocEmailSaveFailed: "Nie udalo sie zapisac e-maila dokumentow: {error}",
    alertCompanyDeleted: "Firma {name} zostala usunieta.",
    alertCompanyDeleteFailed: "Firma {name} nie mogla zostac usunieta: {error}",
    alertCompanyLocked: "Firma {name} zostala zablokowana.",
    alertCompanyUnlocked: "Blokada dla {name} zostala usunieta.",
    alertCompanyStatusChangeFailed: "Zmiana statusu dla {name} nie powiodla sie: {error}",
    alertBrandingPresetSaveFailed: "Nie udalo sie zapisac presetu projektu: {error}",
    alertPasswordMinLength: "Haslo musi miec co najmniej 4 znaki.",
    alertTurnstileCreateFailed: "Nie udalo sie utworzyc kolowrotka: {error}",
    alertTurnstilePasswordUpdated: "Haslo kolowrotka zostalo zaktualizowane.",
    alertTurnstilePasswordResetFailed: "Resetowanie hasla nie powiodlo sie: {error}",
    alertApiKeyRotationFailed: "Rotacja klucza API nie powiodla sie: {error}",
    alertTurnstileToggleFailed: "Nie udalo sie przelaczye kolowrotka: {error}",
    alertWorkerDeletedCannotEdit: "Usunieci pracownicy nie moga byc edytowani.",
    alertDataCopied: "Dane skopiowane.",
    alertPrintWindowFailed: "Nie udalo sie otworzyc okna drukowania.",
    alertAppLinkCopied: "Link aplikacji skopiowany.",
    alertQrNotReadyYet: "Kod QR jest jeszcze generowany. Prosze sprobowac ponownie za chwile.",
    alertAccessBookingFailed: "Nie udalo sie zarejestrowac dostepu: {error}",
    alertWorkerSaveFailed: "Nie udalo sie zapisac danych pracownika: {error}",
    alertPhotoMatchFailed: "Porownanie zdjec nie powiodlo sie ({score}%). Zapisywanie jest zablokowane. Prosze ponownie zrobic zdjecie lub skontaktowac sie z superadminem.",
    alertOverrideReasonTooShort: "Powod zastapienia jest zbyt krotki. Prosze wprowadzic co najmniej 8 znakow.",
    alertPhotoOverrideRequested: "Zadanie zastapienia zdjecia (ID zatwierdzenia: {id}).\nDrugi superadmin musi zatwierdzic zmiane przed jej zapisaniem.",
    alertBadgePinInvalid: "PIN odznaki musi zawierac od 4 do 8 cyfr.",
    alertDuplicatePhysicalCardId: "Ten identyfikator karty fizycznej jest juz przypisany do innego pracownika.",
    alertPhotoOverrideSuperadminOnly: "Zastapienie zdjecia jest dozwolone tylko dla superadminow.",
    alertPhotoOverrideReasonRequired: "Prosze podac wystarczajacy powod zastapienia zdjecia.",
    alertInvoiceSavedSendFailed: "Faktura zapisana, wysylanie nieudane: {error}",
    alertInvoiceNumberDuplicate: "Numer faktury {number} jest juz zajety. Prosze uzyc innego numeru.",
    alertInvoiceSendFailed: "Faktura nie mogla zostac wyslana: {error}",
    alertInvoiceNumberLength: "Numer faktury musi miec od 3 do 64 znakow.",
    alertInvoiceDateInvalid: "Data faktury lub termin platnosci jest nieprawidlowy.",
    alertInvoiceDueDateBeforeIssue: "Termin platnosci nie moze byc wczesniejszy niz data faktury.",
    alertInvoiceVatRange: "Podatek VAT musi byc pomiedzy 0 a 100.",
    alertApprovalRejectReasonRequired: "Odrzucenie bez powodu jest niedozwolone.",
    alertApprovalConfirmed: "Zatwierdzenie potwierdzone i akcja wykonana.",
    alertApprovalRejected: "Zatwierdzenie zostalo odrzucone.",
    alertApprovalUpdated: "Zatwierdzenie zaktualizowane.",
    alertApprovalActionFailed: "Akcja zatwierdzenia nie powiodla sie: {error}",
    alertInvoiceRetrySentDeadLetter: "Faktura zostala pomyslnie wyslana ponownie i usunieta z kolejki martwych liter.",
    alertInvoiceRetrySent: "Faktura zostala pomyslnie wyslana ponownie.",
    alertInvoiceRetryFailed: "Ponowne wysylanie nie powiodlo sie: {error}",
    alertDeadLetterResolveApprovalRequested: "Zatwierdzenie zadane ({id}). Drugi superadmin musi potwierdzic.",
    alertDeadLetterResolveFailed: "Sprawa martwej litery nie mogla zostac rozwiazana: {error}",
    alertGenericError: "Blad: {error}",
    alertCollectionsStatusChangeFailed: "Zmiana statusu nie powiodla sie: {error}",
    alertActionFailed: "Akcja nie powiodla sie: {error}",
    alertInvoiceHistoryLoadFailed: "Historia nie mogla zostac zaladowana: {error}",
    alertAccessExportFailed: "Eksport dziennika dostepu nie powiodl sie: {error}",
    alertWorkerExportFailed: "Eksport listy pracownikow nie powiodl sie: {error}",
    alertSettingsSaveFailed: "Nie udalo sie zapisac ustawien: {error}",
    alertSystemRepairDone: "Naprawa systemu zostala wykonana.",
    alertSystemRepairFailed: "Naprawa systemu nie powiodla sie: {error}",
    alertBrandingLoaded: "Marka BauKometra zaladowana. Teraz kliknij Zapisz w ustawieniach administratora.",
    alertBrandingLoadFailed: "Nie udalo sie zaladowac marki: {error}",
    alertBrandingAltLoaded: "Alternatywny wariant marki BauKometra zaladowany. Teraz kliknij Zapisz w ustawieniach administratora.",
    alertBrandingAltLoadFailed: "Nie udalo sie zaladowac alternatywnego wariantu marki: {error}",
    alertDayCloseAckFailed: "Zamkniecie dnia nie moglo zostac potwierdzone: {error}",
    alertOtpRequired: "2FA jest aktywne dla tego konta. Prosze wprowadzic kod OTP.",
    alertOtpInvalid: "Kod OTP jest nieprawidlowy lub wygasl. Prosze wprowadzic nowy kod.",
    alertTooManyAttempts: "Zbyt wiele nieudanych prob. Prosze poczekac 10 minut i sprobowac ponownie.",
    alertForbiddenTenantHost: "Ten dostep jest dozwolony tylko przez zatwierdzony domen firmy.",
    alertSupportCompanyMismatch: "To logowanie nie pasuje do wybranej firmy. Prosze uzyc admina firmy oznaczonej firmy.",
    alertLoginCompanyLocked: "Ta firma jest zablokowana. Prosze najpierw uregulowac otwarte faktury lub zniesc blokade w superadminie.",
    alertInvalidCredentials: "Nazwa uzytkownika lub haslo sa nieprawidlowe. Prosze sprawdzic dane i sprobowac ponownie.",
    alertAdminIpNotAllowed: "Dostep admina z tego IP jest niedozwolony.",
    alertLoginScopeMismatch: "Typ dostepu nie pasuje do konta. Prosze poprawnie wybrac admin serwera / admin firmy.",
    alertLoginHttp405: "Logowanie nieudane: 405. Zadanie logowania trafia aktualnie na {target}. W przypadku GitHub Pages, frontend musi uzywac backendu Render.",
    alertLoginFailed: "Logowanie nieudane: {error}",
    alertPasswordResetEnterUsername: "Prosze najpierw wprowadzic nazwe uzytkownika lub e-mail.",
    alertPasswordResetSent: "Jesli znaleziono pasujace konto, zostal wyslany e-mail resetujacy.",
    alertPasswordResetFailed: "Nie udalo sie uruchomic resetowania hasla: {error}",
    alertPasswordSetSuccess: "Haslo zostalo pomyslnie ustawione. Mozesz sie teraz zalogowac.",
    alertPasswordResetLinkFailed: "Link resetujacy nie mogl zostac uzyty: {error}",
    alertPasswordChanged: "Haslo zmienione. Prosze zalogowac sie ponownie.",
    alertPasswordChangeFailed: "Zmiana hasla nie powiodla sie: {error}",
    alert2faSetupFailed: "Konfiguracja 2FA nie powiodla sie: {error}",
    alert2faEnableFailed: "Nie udalo sie aktywowac 2FA: {error}",
    alertDeviceDeleteFailed: "Blad podczas usuwania: {error}",
    alertCompanyCreateFailed: "Firma nie mogla zostac utworzona: {error}",
    alert2faDisableFailed: "Nie udalo sie dezaktywowac 2FA: {error}",
    alertExportFailed: "Eksport nie powiodl sie: {error}",
    alertNoDemoCompany: "Nie znaleziono aktywnej firmy dla danych demonstracyjnych.",
    alertDemoModeInvalid: "Nieprawidlowy tryb. Prosze uzyc replace lub append.",
    alertDemoLoadFailed: "Nie udalo sie zaladowac danych demonstracyjnych: {error}",
    alertImportSuccess: "Import zostal pomyslnie zastosowany.",
    alertImportFailed: "Import nie powiodl sie: {error}",
    alertCsvExportFailed: "Eksport CSV nie powiodl sie: {error}",
    alertIncidentExportFailed: "Eksport zdarzen nie powiodl sie: {error}",
    alertSelectInvoiceForRetry: "Prosze wybrac co najmniej jedna fakture z kolejki.",
    alertBulkRetryDone: "Ponowna proba masowa zakonczona. Wyslane: {sent}, Nieudane: {failed}, Pominiete: {skipped}",
    alertBulkRetryFailed: "Ponowna proba masowa nie powiodla sie: {error}",
    alertNoCriticalCases: "Aktualnie nie ma krytycznych przypadkow (wynik >= 70).",
    alertCriticalBulkRetryDone: "Krytyczna ponowna proba masowa zakonczona. Wyslane: {sent}, Nieudane: {failed}, Pominiete: {skipped}",
    alertCriticalBulkRetryFailed: "Krytyczna ponowna proba masowa nie powiodla sie: {error}",
    alertDesktopInstallFailed: "Nie udalo sie uruchomic instalacji desktopowej.",
    alertSubcompanyCreateFailed: "Nie udalo sie utworzyc podwykonawcy: {error}",
    alertDeleteFailed: "Blad podczas usuwania: {error}",
    alertStatusChangeFailed: "Blad przy zmianie statusu: {error}",
    alertReassignmentDone: "Przypisanie ponowne zakonczone. Dopasowania: {count}",
    alertReassignmentFailed: "Przypisanie ponowne nie powiodlo sie: {error}",
    detailCloseTitle: "Zamknij",
    detailPhotoAlt: "Zdjecie pracownika",
    detailCheckinBtn: "Wejscie (Check-in)",
    detailCheckoutBtn: "Wyjscie (Check-out)",
    accessFormEyebrow: "Bramka",
    accessFormH3: "Check-in i check-out",
    labelAccessBadge: "Badge ID lub pracownik",
    labelAccessDir: "Kierunek",
    labelAccessGate: "Brama",
    labelAccessNote: "Uwaga",
    optCheckin: "Wejście",
    optCheckout: "Wyjście",
    btnAccessSubmit: "Zapisz wejście",
    porterEmpty: "Widok portiera: wybierz pracownika i zapisz wejście.",
    accessLogEyebrow: "Rejestr wejść",
    accessLogH3: "Wejścia i wyjścia ze znacznikiem czasu",
    labelFrom: "Od",
    labelTo: "Do",
    labelFilterDir: "Kierunek",
    labelFilterGate: "Bramka",
    optAllDir: "Wszystkie",
    btnApplyFilter: "Zastosuj filtr",
    btnResetFilter: "Resetuj filtr",
    btnAccessCsv: "Eksportuj wejścia CSV",
    dailyReportEyebrow: "Raport dzienny",
    dailyReportH3: "Według bramy",
    btnPrintDaily: "Drukuj raport dzienny",
    btnPrintVisitorWeekly: "Drukuj tygodniową listę gości",
    hourlyEyebrow: "Analiza godzinowa",
    hourlyH3: "Wejścia/wyjścia na godzinę",
    warningsEyebrow: "Ostrzeżenia",
    warningsH3: "Wejście bez wyjścia",
    invListEyebrow: "Fakturowanie",
    invListH3: "Faktury i status płatności",
    optAllStatus: "Wszystkie statusy",
    optDraft: "Szkic",
    optSent: "Wysłana",
    optOverdue: "Zaległa",
    optPaid: "Opłacona",
    optFailed: "Błąd",
    btnRefreshList: "Odśwież",
    inkassoEyebrow: "Windykacja",
    inkassoH3: "Zaległa, pre-blokada, zablokowana",
    optAllPositions: "Wszystkie otwarte pozycje",
    optPrelock: "Pre-blokada",
    optLocked: "Już zablokowana",
    adminEyebrow: "Centrum administracji",
    adminH3: "System i konfiguracja",
    sysStatusEyebrow: "Stan systemu",
    sysStatusH3: "Dostęp awaryjny i naprawa",
    btnRefreshStatus: "Odśwież stan",
    btnRepairSessions: "Napraw sesje",
    superAdminEyebrow: "Kontrola systemu",
    superAdminH3: "Ustawienia super admina",
    labelPlatformName: "Nazwa platformy",
    labelOperatorName: "Operator",
    labelTurnstileEp: "Endpoint API bramki",
    labelSmtpHost: "SMTP Host",
    labelSmtpPort: "SMTP Port",
    labelSmtpUser: "Użytkownik SMTP",
    labelSmtpPass: "Hasło SMTP",
    labelSenderEmail: "E-mail nadawcy",
    labelSenderName: "Nazwa nadawcy",
    labelTls: "TLS aktywne",
    optTlsYes: "Tak",
    optTlsNo: "Nie",
    btnTestSmtp: "Wyślij testowy e-mail",
    optYes: "Tak",
    optNo: "Nie",
    labelIpWhitelist: "Biała lista IP admina",
    labelEnforceDomain: "Wymuś domenę firmy",
    btnSaveAdmin: "Zapisz ustawienia admina",
    companyNewEyebrow: "Najemcy",
    companyNewH3: "Dodaj firmę budowlaną",
    labelCompanyName: "Nazwa firmy",
    labelCompanyContact: "Osoba kontaktowa",
    labelBillingEmail: "E-mail do faktur",
    labelAccessHost: "Domena dostępu firmy",
    labelPlan: "Plan",
    labelCompanyStatus: "Status",
    optCompanyActive: "Aktywna",
    optCompanyTest: "Testowa",
    optCompanyPaused: "Wstrzymana",
    optCompanyLocked: "Zablokowana (zaległa płatność)",
    labelCompanyAdminPassword: "Startowe hasło admina",
    companyAdminPasswordPlaceholder: "np. Bezpieczne!2025",
    btnCreateCompany: "Utwórz firmę",
    accountEyebrow: "Konto",
    accountH3: "Zmień hasło",
    labelCurrentPassword: "Aktualne hasło",
    labelNewPassword: "Nowe hasło",
    btnChangePassword: "Zmień hasło",
    tfaEyebrow: "Drugi czynnik",
    tfaH3: "Zarządzanie 2FA",
    companiesListEyebrow: "Najemcy",
    companiesListH3: "Firmy i plany",
    invFormEyebrow: "Faktury",
    invFormH3: "Wyślij z logo i projektem",
    labelInvFirm: "Firma",
    labelInvNumber: "Numer faktury",
    labelInvRecipient: "E-mail odbiorcy",
    labelInvDate: "Data faktury",
    labelInvDueDate: "Termin płatności",
    labelInvPeriod: "Okres usługi",
    labelInvDescription: "Opis usługi",
    labelInvNet: "Kwota netto (EUR)",
    labelInvVat: "VAT (%)",
    btnPrintInvoice: "Drukuj fakturę / Zapisz PDF",
    btnSendInvoice: "Wyślij fakturę e-mailem",
    btnUpdatePreview: "Aktualizuj podgląd",
    auditEyebrow: "Rejestr bezpieczeństwa",
    auditH3: "Rejestr audytu",
    labelAuditEvent: "Typ zdarzenia",
    labelAuditRole: "Rola",
    btnAuditCsv: "Eksportuj audyt CSV",
    reportingPaid: "Opłacona",
    reportingOpen: "Otwarta",
    reportingOverdue: "Zaległa",
    reportingInvoicesLabel: "faktury",
    reportingOverdueTotal: "Suma zaległości",
    reportingLockedCompanies: "Zablokowane firmy",
    reportingAutoSuspensions30d: "Auto-blokady (30d)",
    reportingGeneratedAt: "Wygenerowano",
    reportingNoOverdueCompanies: "Brak firm z zaległościami.",
    reportingFallbackCompany: "Firma",
    reportingOverdueInvoicesLabel: "zaległe faktury",
    reportingNoAccessDataLast7Days: "Brak danych dostępu za ostatnie 7 dni.",
    reportingCheckin: "Wejście",
    reportingCheckout: "Wyjście",
    navDocuments: "Dokumenty",
    docInboxEyebrow: "Skrzynka odbiorcza",
    docInboxH3: "Dokumenty przychodzące e-mailem",
    btnDocInboxRefresh: "Odśwież",
    btnDocInboxSync: "Pobierz skrzynkę",
    btnDocInboxPoll: "Pobierz skrzynkę teraz",
    btnDocInboxRematch: "Przypisz ponownie",
    docEmailInfoLabel: "E-mail dokumentów (pracownicy wysyłają tu swoje dokumenty):",
    btnCopyEmail: "Kopiuj",
    btnCopyEmailDone: "Skopiowano!",
    docInboxHint: "Pracownicy wysyłają swoje dokumenty na skonfigurowany adres e-mail. Portier przypisuje załączniki do pracownika tutaj.",
    docAssignEyebrow: "Przypisz",
    docAssignH3: "Przypisz załącznik do pracownika",
    docInboxEmpty: "Brak nieprzetworzonych wiadomości.",
    docInboxEmailFrom: "Od",
    docInboxEmailSubject: "Temat",
    docInboxEmailDate: "Data",
    docInboxAttachments: "Załączniki",
    btnAssignDoc: "Przypisz",
    btnDismissEmail: "Odrzuć",
    docAssignWorkerLabel: "Wybierz pracownika",
    docAssignTypeLabel: "Typ dokumentu",
    docAssignNotesLabel: "Uwagi (opcjonalnie)",
    btnConfirmAssign: "Przypisz dokument",
    docAssignSuccess: "Dokument przypisany pomyślnie.",
    docTypeMindestlohnnachweis: "Dowód minimalnego wynagrodzenia",
    docTypePersonalausweis: "Dowód osobisty / Paszport",
    docTypeSozialversicherungsnachweis: "Zaświadczenie ZUS",
    docTypeArbeitserlaubnis: "Pozwolenie na pracę",
    docTypeGesundheitszeugnis: "Świadectwo zdrowia",
    docTypeSonstiges: "Inne",
    workerDocsHeading: "Zapisane dokumenty",
    workerDocsEmpty: "Brak zarejestrowanych dokumentów.",
    workerAkteLabel: "Teczka pracownika",
    btnUploadWorkerDoc: "Prześlij dokument",
    btnConfirmUpload: "Prześlij",
    docUploadSuccess: "Dokument przesłany pomyślnie.",
    confirmDeleteDoc: "Usunąć ten dokument?",
    btnDownloadDoc: "Pobierz",
    btnDeleteDoc: "Usuń",
    imapSectionEyebrow: "Skrzynka dokumentów",
    imapSectionH4: "Skrzynka IMAP na dokumenty",
    labelImapHint: "Pracownicy wysyłają dokumenty na ten adres. System sprawdza skrzynkę co kilka minut.",
    labelImapHost: "IMAP Host",
    labelImapPort: "IMAP Port",
    labelImapUser: "Użytkownik IMAP",
    labelImapPass: "Hasło IMAP",
    labelImapFolder: "Folder IMAP",
    labelImapSsl: "SSL/TLS",
    btnImapTest: "Testuj połączenie IMAP",
    imapTestOk: "Połączenie udane!",
    imapTestFail: "Błąd połączenia",
    navDevices: "Urządzenia",
    devicesEyebrow: "Sprzęt",
    devicesH3: "Inteligentne skrzynki i urządzenia OSDP",
    devicesHint: "Każda skrzynka wysyła sygnał co 30–60 s. Brak sygnału >90 s = offline.",
    btnAddDevice: "Dodaj urządzenie",
    addDeviceEyebrow: "Nowe urządzenie",
    addDeviceH3: "Zarejestruj urządzenie",
    labelDeviceName: "Nazwa",
    labelDeviceLocation: "Lokalizacja",
    labelDeviceType: "Typ / Protokół",
    btnDeviceRegister: "Zarejestruj urządzenie i wygeneruj klucz API",
    deviceOnline: "Online",
    deviceOffline: "Offline",
    deviceNeverSeen: "Brak sygnału",
    alertInstallUnavailable: "Instalacja nie jest dostępna bezpośrednio w tej przeglądarce. W Chrome lub Edge wybierz 'Zainstaluj aplikację' z menu.",
    alertSessionExpired: "Sesja wygasła. Zaloguj się ponownie.",
    btnPrintBadge: "Drukuj identyfikator",
    greetingMorning: "Dzień dobry",
    greetingDay: "Miłego dnia",
    greetingEvening: "Dobry wieczór",
    greetingNight: "Dobranoc",
    greetingSuffix: "Miłej zmiany!",
    adminWorkerAppSectionTitle: "Aplikacja pracowników",
    adminWorkerAppSectionCopy: "Kontroluje całą aplikację pracowników: logowanie, cyfrowy identyfikator i użycie QR.",
    adminWorkerAppPinLockHint: "Po 2 minutach braku aktywności pracownik musi ponownie wpisać PIN identyfikatora.",
    optPlanDayPassRecommended: "Karta gościa (zalecane)",
    optPlanMonthlySite: "Miesięcznie za budowę",
    optPlanPerWorker: "Na pracownika",
    optPlanFlatCompany: "Ryczałt za firmę",
    optPlanDayPassPrice: "Karta gościa (19 EUR/dzień)",
    loginForgotPassword: "Nie pamietam hasla",
    legalImpressum: "Informacje prawne",
    legalPrivacy: "Prywatnosc",
    legalCloseTitle: "Zamknij",
    legalFallbackEmpty: "Brak dostepnego tekstu.",
    invoiceMgmtTitle: "Zarzadzanie fakturami",
    invoiceMgmtCopy: "Pokaz otwarte i oplacone faktury. Oznacz fakture jako oplacona, aby automatycznie zdjac blokade firmy. Wszystkie dzialania sa zapisywane w dzienniku audytu.",
    invoiceOpsEyebrow: "Operacje",
    invoiceOpsH3: "SLA wysylki i status bledow",
    invoiceSendEyebrow: "Wysylka",
    invoiceSendH3: "Kolejka nieudanych e-maili",
    optRetryAll: "Wszystkie nieudane wysylki",
    optRetryPriority: "Najpierw priorytet",
    optRetryMaxed: "Osiagnieto maks. liczbe prob",
    optRetryTodayFailed: "Nieudane dzisiaj",
    invoiceRetryTopIssuesOnly: "Tylko moje najwazniejsze problemy",
    btnRetryCriticalSend: "Wyslij teraz tylko krytyczne",
    btnRetryExportCsv: "CSV kolejki",
    btnIncidentExportCsv: "CSV incydentow",
    btnRetryBulkSend: "Wyslij ponownie zaznaczone",
    invoiceApprovalsEyebrow: "Akceptacje",
    invoiceApprovalsH3: "Kontrola czterech oczu dla krytycznych akcji",
    optApprovalAllActions: "Wszystkie typy akcji",
    optApprovalBulkRetry: "Bulk retry",
    optApprovalDeadLetterResolve: "Dead-letter resolve",
    legalSectionEyebrow: "Prawne",
    legalSectionTitle: "Informacje prawne i prywatnosc",
    labelImpressumText: "Tekst informacji prawnych",
    labelPrivacyText: "Polityka prywatnosci",
    legalTextsHint: "Te teksty pojawiaja sie na stronie logowania pod 'Informacje prawne' i 'Prywatnosc'.",
    labelCompanyDocumentEmail: "E-mail dokumentow",
    labelBrandingPreset: "Preset brandingu",
    optBrandingConstruction: "Budownictwo",
    optBrandingIndustry: "Przemysl",
    optBrandingPremium: "Premium",
    optPlanStarter: "Starter (49 EUR)",
    optPlanProfessional: "Professional (99 EUR)",
    optPlanEnterprise: "Enterprise (199 EUR)",
    accessFeedbackCheckin: "Wejście zarejestrowane",
    badgePinHint: "Logowanie przez badge w aplikacji pracowników działa tylko z Badge-ID i tym kodem PIN. Podczas edycji możesz tu ustawić nowy PIN.",
    badgePinPlaceholder: "4 do 8 cyfr",
    bulkSelectAll: "Zaznacz wszystkie",
    btnDayCloseAcknowledge: "Potwierdź zamknięcie dnia",
    btnExportCompanyDocEmails: "Eksportuj e-maile dokumentów",
    btnLoadAltBrand: "Załaduj alternatywę",
    btnLoadDefaultBrand: "Załaduj domyślny branding",
    cameraNotStarted: "Kamera nie uruchomiona.",
    complianceEyebrow: "Compliance",
    complianceH3: "Status dokumentów",
    dayCloseCommentLabel: "Komentarz zamknięcia dnia",
    dayCloseCommentPlaceholder: "np. Kierownik zmiany powiadomiony",
    deadLetterEyebrow: "Dead-Letter",
    deadLetterH3: "Faktury wymagające ręcznego rozwiązania",
    filterByCompanyPlaceholder: "Filtruj według firmy…",
    filterQueueByCompanyPlaceholder: "Filtruj kolejkę według firmy…",
    formSectionAppFeaturesEyebrow: "Funkcje aplikacji",
    formSectionBrandingEyebrow: "Design faktury",
    formSectionBrandingH4: "Kolory & Branding",
    formSectionEmailEyebrow: "E-Mail",
    formSectionPlatformEyebrow: "Platforma",
    formSectionPlatformH4: "Tożsamość & Operator",
    formSectionSecurityH4: "Dostęp & Izolacja",
    formSectionSmtpH4: "Wysyłka SMTP",
    invoiceLogoHint: "Logo faktury jest również używane jako ikona systemu i ikona aplikacji pracowników.",
    invoicePreviewEyebrow: "Podgląd",
    invoicePreviewH3: "Sprawdź fakturę przed wysłaniem",
    maxAgeFilterPlaceholder: "Maks wiek w minutach (0 = wszystkie)",
    optDeviceOsdp: "OSDP (RS-485)",
    optDeviceTcp: "TCP/IP Smart-Box",
    optDeviceWiegand: "Czytnik Wiegand",
    optPinLockActive: "Aktywna – Blokada PIN chroni przed przekazywaniem telefonu",
    optPinLockDisabled: "Wyłączona – Identyfikator zawsze dostępny",
    optRoleCompanyAdmin: "Admin firmy",
    optRoleSuperAdmin: "Super Admin",
    optWorkerAppActive: "Aktywna – Badge, QR i logowanie badge włączone",
    optWorkerAppLocked: "Zablokowana – Aplikacja mobilna wyłączona",
    photoAdjustHelp: "Przesuń zdjęcie po wykonaniu, aby pasowało do prawej strony identyfikatora.",
    photoOverrideH3: "Oczekujące zatwierdzenia nadpisania zdjęcia",
    photoRequiredHint: "Wymagane: Bez zdjęcia nie można zapisać identyfikatora.",
    photoSharpenLabel: "Ostrość:",
    photoWhiteBgLabel: "Tło całkowicie białe (aktywne)",
    photoZoomCropLabel: "Zoom / Przytnij",
    recentAuditEyebrow: "Audyt",
    recentAuditH3: "Ostatnie zdarzenia systemowe",
    rentalModelLabel: "Model wynajmu",
    sectionSecurityEyebrow: "Bezpieczeństwo",
    statusLoading: "Ładowanie stanu…",
    sysAlertActionBtn: "Przejdź do faktur",
    sysAlertDefaultText: "Wystąpiły krytyczne błędy wysyłki faktur.",
    sysAlertHeading: "Krytyczny problem wysyłki",
    turnstileCountLabel: "Liczba bramek",
    turnstilePasswordLabel: "Hasło startowe bramki",
    workerAppEnabledLabel: "Mobilna aplikacja badge (cyfrowy identyfikator + QR)",
    workerPassLockLabel: "Zabezpiecz identyfikator blokadą PIN",
    workerSearchPlaceholder: "Szukaj: Imię, Badge-ID, Budowa …",
    confirmDeleteCompanyText: "Usunąć firmę {name} i wszystkie powiązane rekordy?\n\nOK = pełne usunięcie (w tym pracownicy, podwykonawcy i logi)\nAnuluj = nie usuwaj",
    confirmLockCompany: "Zablokować firmę {name} teraz? Administrator firmy, kołowrót i aplikacja pracownika zostaną zablokowane.",
    confirmUnlockCompany: "Zdjąć blokadę z {name} teraz? Firma będzie mogła się ponownie zalogować.",
    confirmDeleteWorkerBulk: "Czy naprawdę usunąć {count} pracowników?",
    confirmApiKeyRotate: "Wygenerować nowy klucz API dla tego kołowrotu teraz? Obecny klucz straci ważność natychmiast.",
    confirmSystemRepair: "Uruchomić naprawę systemu? Wygasłe sesje i blokady logowania zostaną wyczyszczone.",
    confirmApprovalDecision: "Czy naprawdę {decision} zatwierdzenie {id}?",
    confirmDeadLetterRetry: "Ponownie wysłać fakturę Dead-Letter teraz?",
    confirmDeadLetterResolve: "Oznaczyć sprawę Dead-Letter jako rozwiązaną?",
    confirmInvoicePaid: "Oznaczyć tę fakturę jako opłaconą? Ewentualna blokada firmy zostanie zniesiona.",
    confirmInvoiceRetry: "Ponownie wysłać fakturę teraz?",
    confirmInvoicePaidSimple: "Oznaczyć fakturę jako opłaconą teraz?",
    confirmDemoInvoices: "Czy mają być również tworzone faktury demonstracyjne?",
    confirmDemoAccessLogs: "Czy mają być tworzone dzienniki dostępu demonstracyjnego?",
    confirmDemoReplace: "Załadować dane demonstracyjne dla {name} w trybie REPLACE teraz? Istniejący pracownicy, podwykonawcy i logi zostaną zastąpieni.",
    confirmDemoAppend: "Załadować dane demonstracyjne dla {name} w trybie APPEND dodatkowo?",
    confirmExportAudit: "Uwzględnić dziennik audytu w eksporcie?",
    confirmExportDayClose: "Uwzględnić potwierdzenia zamknięcia dnia w eksporcie?",
    confirmExportDeleted: "Uwzględnić usunięte wpisy w eksporcie?",
    confirmExportAll: "Jako superadmin: eksportować cały system? (Nie = tylko bieżąca firma)",
    confirmExportDownload: "Pobrać eksport systemu{scope} teraz?",
    confirmLogout: "Czy naprawdę się wylogować?",
    confirmImportChangesOnly: "Importować tylko zmiany? (Zalecane)",
    confirmBulkRetrySelected: "Ponownie wysłać {count} wybraną/e fakturę/faktury teraz?",
    confirmBulkRetryCritical: "Ponownie wysłać {count} krytyczną/e fakturę/faktury teraz?",
    confirmPhotoMatchFailed: "Porównanie zdjęć nie powiodło się ({score}%). Tylko superadmin może zapisać z ryzykiem. Czy zapisać mimo to?",
    promptDocEmail: "Ustaw e-mail dokumentów dla {name}",
    promptTurnstilePassword: "Ustaw hasło kołowrotu dla {name} (min. 4 znaki):",
    promptTurnstilePasswordNew: "Ustaw nowe hasło kołowrotu (min. 4 znaki):",
    promptCopyData: "Dane do skopiowania:",
    promptAppLink: "Link do aplikacji dla pracownika:",
    promptPhotoOverrideReason: "Podaj powód nadpisania zdjęcia (co najmniej 8 znaków):",
    promptNewPassword: "Podaj nowe hasło (co najmniej 8 znaków):",
    promptTfaCode: "Podaj 6-cyfrowy kod z aplikacji uwierzytelniającej:",
    promptTfaDisableCode: "Podaj aktualny kod 2FA, aby wyłączyć:",
    promptDemoMode: "Dane demonstracyjne dla {name}: wpisz tryb (replace lub append)",
    promptRejectionReason: "Powód odrzucenia (wymagane):",
    promptRejectApproval: "Podaj powód odrzucenia:",
    invoiceTitle: "Faktura",
    invoiceAltLogo: "Logo firmy",
    invoiceLabelNumber: "Numer faktury:",
    invoiceLabelDate: "Data faktury:",
    invoiceLabelDue: "Termin płatności:",
    invoiceLabelCustomer: "Klient:",
    invoiceLabelContact: "Osoba kontaktowa:",
    invoiceLabelPeriod: "Okres świadczenia usług:",
    invoiceColService: "Usługa / Pracownik",
    invoiceColAccess: "Wejścia",
    invoiceColNet: "Kwota netto",
    invoiceRowUnknown: "Nieznany",
    invoiceRowPlan: "Plan: {label}",
    invoiceTotalNet: "Suma częściowa netto",
    invoiceTotalVat: "VAT ({rate} %)",
    invoiceTotalGross: "Kwota całkowita",
    invoiceFooter: "Dziękujemy za współpracę. Faktura została stworzona cyfrowo i może być wysłana bezpośrednio.",
    invoiceHistoryEmpty: "Brak wysłanych lub zapisanych faktur.",
    invoiceHistoryRecipient: "Odbiorca:",
    invoiceHistoryTotal: "Razem:",
    invoiceHistoryCreated: "Utworzono:",
    invoiceHistorySent: "Wysłano:",
    invoiceHistoryError: "Błąd:",
    tfaStatusActive: "2FA jest aktywna",
    tfaStatusInactive: "2FA nie jest aktywna",
    tfaBtnSetup: "Skonfiguruj 2FA",
    tfaBtnEnable: "Włącz 2FA",
    tfaBtnDisable: "Wyłącz 2FA",
    tfaQrHint: "Skonfiguruj sekret z aplikacją uwierzytelniającą:",
    tfaSecretLabel: "Ręczny kod:",
    tfaCodeLabel: "Kod z aplikacji:",
    tfaCodePlaceholder: "6-cyfrowy kod",
    tfaEnableHint: "Wprowadź 6-cyfrowy kod z aplikacji uwierzytelniającej i kliknij 'Włącz'.",
    tfaEmailLabel: "Adres e-mail dla kodów OTP",
    tfaEmailPlaceholder: "admin@example.com",
    tfaActivateOneClickHint: "Wprowadź swój adres e-mail i kliknij Aktywuj. Przy każdym logowaniu kod zostanie wysłany na Twój e-mail.",
    alertTfaActivated: "2FA zostało aktywowane.",
    alertTfaEmailRequired: "Proszę wprowadzić adres e-mail przed aktywacją 2FA.",
    alertOtpSent: "Kod bezpieczeństwa został wysłany na Twój e-mail. Sprawdź swoją skrzynkę odbiorzą.",
    loginOtpSentNotice: "Kod wysłany e-mailem – sprawdź skrzynkę",
    loginOtpBackBtn: "← Powrót",
  },
};

function normalizeUiLang(value) {
  const candidate = String(value || "").trim().toLowerCase();
  return Object.prototype.hasOwnProperty.call(UI_TRANSLATIONS, candidate) ? candidate : UI_FALLBACK_LANG;
}

function getStoredUiLang() {
  return normalizeUiLang(window.localStorage.getItem(UI_LANG_STORAGE_KEY));
}

function uiT(key) {
  const lang = getStoredUiLang();
  return UI_TRANSLATIONS[lang]?.[key] || UI_TRANSLATIONS[UI_FALLBACK_LANG]?.[key] || key;
}

const UI_PLACEHOLDER_TEXTS = {
  subcompanyName: {
    de: "z. B. Elektro Yilmaz GmbH",
    en: "e.g. Elektro Yilmaz Ltd",
    tr: "örn. Elektro Yilmaz Ltd. Şti.",
    ar: "مثال: شركة يلماز للكهرباء",
    fr: "ex. Électro Yilmaz Sarl",
    es: "ej. Electro Yilmaz SL",
    it: "es. Elektro Yilmaz Srl",
    pl: "np. Elektro Yilmaz Sp. z o.o.",
  },
  firstName: {
    de: "Max",
    en: "John",
    tr: "Mehmet",
    ar: "محمد",
    fr: "Jean",
    es: "Juan",
    it: "Mario",
    pl: "Jan",
  },
  lastName: {
    de: "Mustermann",
    en: "Smith",
    tr: "Yılmaz",
    ar: "الأحمدي",
    fr: "Dupont",
    es: "García",
    it: "Rossi",
    pl: "Kowalski",
  },
  insuranceNumber: {
    de: "12 345678 A 123",
    en: "12 345678 A 123",
    tr: "12 345678 A 123",
    ar: "12 345678 A 123",
    fr: "12 345678 A 123",
    es: "12 345678 A 123",
    it: "12 345678 A 123",
    pl: "12 345678 A 123",
  },
  role: {
    de: "Polier, Kranführer, Monteur",
    en: "Foreman, Crane operator, Installer",
    tr: "Ustabaşı, Vinç operatörü, Montajcı",
    ar: "مشرف، مشغل رافعة، فني تركيب",
    fr: "Chef d'équipe, Grutier, Monteur",
    es: "Capataz, Gruista, Montador",
    it: "Caposquadra, Gruista, Montatore",
    pl: "Brygadzista, Operator dźwigu, Monter",
  },
  site: {
    de: "z. B. Musterstr. 12, 80333 München",
    en: "e.g. Sample St 12, Munich",
    tr: "örn. Örnek Cad. 12, İstanbul",
    ar: "مثال: شارع النماذج 12، برلين",
    fr: "ex. Rue Exemple 12, Paris",
    es: "ej. Calle Ejemplo 12, Madrid",
    it: "es. Via Esempio 12, Milano",
    pl: "np. ul. Przykładowa 12, Warszawa",
  },
  physicalCardId: {
    de: "UID oder Kartenkennung",
    en: "UID or card identifier",
    tr: "UID veya kart kimliği",
    ar: "UID أو رقم البطاقة",
    fr: "UID ou identifiant de carte",
    es: "UID o identificador de tarjeta",
    it: "UID o identificatore carta",
    pl: "UID lub identyfikator karty",
  },
  visitorCompany: {
    de: "z. B. Lieferant, Kunde, externe Firma",
    en: "e.g. Supplier, Customer, External company",
    tr: "örn. Tedarikçi, Müşteri, Dış firma",
    ar: "مثال: مورد، عميل، شركة خارجية",
    fr: "ex. Fournisseur, Client, Société externe",
    es: "ej. Proveedor, Cliente, Empresa externa",
    it: "es. Fornitore, Cliente, Azienda esterna",
    pl: "np. Dostawca, Klient, Firma zewnętrzna",
  },
  visitPurpose: {
    de: "z. B. Besprechung, Lieferung, Abnahme",
    en: "e.g. Meeting, Delivery, Inspection",
    tr: "örn. Toplantı, Teslimat, Denetim",
    ar: "مثال: اجتماع، تسليم، فحص",
    fr: "ex. Réunion, Livraison, Inspection",
    es: "ej. Reunión, Entrega, Inspección",
    it: "es. Riunione, Consegna, Ispezione",
    pl: "np. Spotkanie, Dostawa, Odbiór",
  },
  hostName: {
    de: "z. B. Bauleiter Mustafa Yilmaz",
    en: "e.g. Site manager Michael Miller",
    tr: "örn. Şef Mühendis Mehmet Yılmaz",
    ar: "مثال: مدير الموقع محمد أحمد",
    fr: "ex. Chef de chantier Michel Dupont",
    es: "ej. Jefe de obra Miguel García",
    it: "es. Direttore lavori Mario Rossi",
    pl: "np. Kierownik budowy Jan Kowalski",
  },
  accessWorkerSearch: {
    de: "Name oder Badge-ID suchen",
    en: "Search name or Badge ID",
    tr: "İsim veya Badge-ID ara",
    ar: "البحث بالاسم أو رقم Badge",
    fr: "Rechercher nom ou Badge-ID",
    es: "Buscar nombre o Badge-ID",
    it: "Cerca nome o Badge-ID",
    pl: "Szukaj nazwy lub Badge-ID",
  },
  accessNote: {
    de: "Optional",
    en: "Optional",
    tr: "İsteğe bağlı",
    ar: "اختياري",
    fr: "Optionnel",
    es: "Opcional",
    it: "Facoltativo",
    pl: "Opcjonalnie",
  },
  accessFilterGate: {
    de: "z. B. Drehkreuz Nord",
    en: "e.g. Gate North",
    tr: "örn. Kuzey Geçidi",
    ar: "مثال: بوابة الشمال",
    fr: "ex. Portique Nord",
    es: "ej. Puerta Norte",
    it: "es. Cancello Nord",
    pl: "np. Bramka Północna",
  },
  platformName: {
    de: "BauPass Control",
    en: "BauPass Control",
    tr: "BauPass Control",
    ar: "BauPass Control",
    fr: "BauPass Control",
    es: "BauPass Control",
    it: "BauPass Control",
    pl: "BauPass Control",
  },
  operatorName: {
    de: "Deine Firma",
    en: "Your company",
    tr: "Firmanız",
    ar: "شركتك",
    fr: "Votre entreprise",
    es: "Tu empresa",
    it: "La tua azienda",
    pl: "Twoja firma",
  },
  companyTurnstileEndpoint: {
    de: "https://api.dein-gateway.de/access",
    en: "https://api.your-gateway.com/access",
    tr: "https://api.your-gateway.com/access",
    ar: "https://api.your-gateway.com/access",
    fr: "https://api.votre-gateway.fr/access",
    es: "https://api.your-gateway.com/access",
    it: "https://api.your-gateway.com/access",
    pl: "https://api.your-gateway.com/access",
  },
  smtpHost: {
    de: "smtp.dein-provider.de",
    en: "smtp.your-provider.com",
    tr: "smtp.your-provider.com",
    ar: "smtp.your-provider.com",
    fr: "smtp.votre-fournisseur.fr",
    es: "smtp.your-provider.com",
    it: "smtp.your-provider.com",
    pl: "smtp.your-provider.com",
  },
  smtpUsername: {
    de: "mailer@deinefirma.de",
    en: "mailer@yourcompany.com",
    tr: "mailer@firmaniz.com",
    ar: "mailer@yourcompany.com",
    fr: "mailer@votreentreprise.fr",
    es: "mailer@tuempresa.com",
    it: "mailer@tuaazienda.com",
    pl: "mailer@twojafirma.com",
  },
  smtpPassword: {
    de: "App-Passwort",
    en: "App password",
    tr: "Uygulama şifresi",
    ar: "كلمة مرور التطبيق",
    fr: "Mot de passe d'application",
    es: "Contraseña de aplicación",
    it: "Password applicazione",
    pl: "Hasło aplikacji",
  },
  smtpSenderEmail: {
    de: "rechnung@deinefirma.de",
    en: "billing@yourcompany.com",
    tr: "fatura@firmaniz.com",
    ar: "billing@yourcompany.com",
    fr: "facturation@votreentreprise.fr",
    es: "factura@tuempresa.com",
    it: "fattura@tuaazienda.com",
    pl: "faktura@twojafirma.com",
  },
  smtpSenderName: {
    de: "Deine Firma",
    en: "Your company",
    tr: "Firmanız",
    ar: "شركتك",
    fr: "Votre entreprise",
    es: "Tu empresa",
    it: "La tua azienda",
    pl: "Twoja firma",
  },
  adminIpWhitelist: {
    de: "203.0.113.10, 203.0.113.0/24",
    en: "203.0.113.10, 203.0.113.0/24",
    tr: "203.0.113.10, 203.0.113.0/24",
    ar: "203.0.113.10, 203.0.113.0/24",
    fr: "203.0.113.10, 203.0.113.0/24",
    es: "203.0.113.10, 203.0.113.0/24",
    it: "203.0.113.10, 203.0.113.0/24",
    pl: "203.0.113.10, 203.0.113.0/24",
  },
  imapHost: {
    de: "imap.dein-provider.de",
    en: "imap.your-provider.com",
    tr: "imap.your-provider.com",
    ar: "imap.your-provider.com",
    fr: "imap.votre-fournisseur.fr",
    es: "imap.your-provider.com",
    it: "imap.your-provider.com",
    pl: "imap.your-provider.com",
  },
  imapPort: {
    de: "993",
    en: "993",
    tr: "993",
    ar: "993",
    fr: "993",
    es: "993",
    it: "993",
    pl: "993",
  },
  imapUsername: {
    de: "dokumente@deinefirma.de",
    en: "documents@yourcompany.com",
    tr: "belgeler@firmaniz.com",
    ar: "documents@yourcompany.com",
    fr: "documents@votreentreprise.fr",
    es: "documentos@tuempresa.com",
    it: "documenti@tuaazienda.com",
    pl: "dokumenty@twojafirma.com",
  },
  imapPassword: {
    de: "App-Passwort",
    en: "App password",
    tr: "Uygulama şifresi",
    ar: "كلمة مرور التطبيق",
    fr: "Mot de passe d'application",
    es: "Contraseña de aplicación",
    it: "Password applicazione",
    pl: "Hasło aplikacji",
  },
  imapFolder: {
    de: "INBOX",
    en: "INBOX",
    tr: "INBOX",
    ar: "INBOX",
    fr: "INBOX",
    es: "INBOX",
    it: "INBOX",
    pl: "INBOX",
  },
  companyName: {
    de: "Muster Bau GmbH",
    en: "Example Construction Ltd",
    tr: "Örnek İnşaat Ltd. Şti.",
    ar: "شركة البناء النموذجية",
    fr: "Exemple Construction Sarl",
    es: "Construcción Ejemplo SL",
    it: "Costruzioni Esempio Srl",
    pl: "Przykładowe Budownictwo Sp. z o.o.",
  },
  companyContact: {
    de: "Sabine Keller",
    en: "Sarah Keller",
    tr: "Ayşe Kaya",
    ar: "سارة أحمد",
    fr: "Sophie Martin",
    es: "Sara García",
    it: "Sara Rossi",
    pl: "Sara Kowalska",
  },
  companyBillingEmail: {
    de: "buchhaltung@firma.de",
    en: "billing@company.com",
    tr: "muhasebe@firma.com",
    ar: "billing@company.com",
    fr: "comptabilite@entreprise.fr",
    es: "contabilidad@empresa.com",
    it: "contabilita@azienda.com",
    pl: "ksiegowosc@firma.com",
  },
  companyDocumentEmail: {
    de: "dokumente+firma@deinedomain.de",
    en: "documents+company@yourdomain.com",
    tr: "belgeler+firma@yourdomain.com",
    ar: "documents+company@yourdomain.com",
    fr: "documents+entreprise@votredomaine.fr",
    es: "documentos+empresa@yourdomain.com",
    it: "documenti+azienda@yourdomain.com",
    pl: "dokumenty+firma@yourdomain.com",
  },
  companyAccessHost: {
    de: "firma-a.deine-domain.de",
    en: "company-a.your-domain.com",
    tr: "firma-a.your-domain.com",
    ar: "company-a.your-domain.com",
    fr: "entreprise-a.votre-domaine.fr",
    es: "empresa-a.your-domain.com",
    it: "azienda-a.your-domain.com",
    pl: "firma-a.your-domain.com",
  },
  companyTurnstilePassword: {
    de: "z.B. Gate!2025",
    en: "e.g. Gate!2025",
    tr: "örn. Gate!2025",
    ar: "مثال: Gate!2025",
    fr: "ex. Portail!2025",
    es: "ej. Puerta!2025",
    it: "es. Cancello!2025",
    pl: "np. Brama!2025",
  },
  deviceName: {
    de: "z.B. Drehkreuz Nord",
    en: "e.g. Gate North",
    tr: "örn. Kuzey Geçidi",
    ar: "مثال: بوابة الشمال",
    fr: "ex. Portique Nord",
    es: "ej. Puerta Norte",
    it: "es. Cancello Nord",
    pl: "np. Bramka Północna",
  },
  deviceLocation: {
    de: "z.B. Eingang West, Baustelle A",
    en: "e.g. West entrance, Site A",
    tr: "örn. Batı Girişi, Şantiye A",
    ar: "مثال: مدخل الغرب، موقع A",
    fr: "ex. Entrée Ouest, Chantier A",
    es: "ej. Entrada Oeste, Obra A",
    it: "es. Ingresso Ovest, Cantiere A",
    pl: "np. Wejście Zachodnie, Budowa A",
  },
  invoiceNumber: {
    de: "RE-2026-0001",
    en: "INV-2026-0001",
    tr: "FAT-2026-0001",
    ar: "INV-2026-0001",
    fr: "FAC-2026-0001",
    es: "FAC-2026-0001",
    it: "FAT-2026-0001",
    pl: "FV-2026-0001",
  },
  invoiceRecipientEmail: {
    de: "buchhaltung@firma.de",
    en: "billing@company.com",
    tr: "muhasebe@firma.com",
    ar: "billing@company.com",
    fr: "comptabilite@entreprise.fr",
    es: "contabilidad@empresa.com",
    it: "contabilita@azienda.com",
    pl: "ksiegowosc@firma.com",
  },
  invoicePeriod: {
    de: "01.04.2026 - 30.04.2026",
    en: "2026-04-01 - 2026-04-30",
    tr: "01.04.2026 - 30.04.2026",
    ar: "01.04.2026 - 30.04.2026",
    fr: "01.04.2026 - 30.04.2026",
    es: "01.04.2026 - 30.04.2026",
    it: "01.04.2026 - 30.04.2026",
    pl: "01.04.2026 - 30.04.2026",
  },
  invoiceDescription: {
    de: "Digitale Baustellen-Ausweise + Zutrittskontrolle",
    en: "Digital site IDs + access control",
    tr: "Dijital şantiye kimlikleri + erişim kontrolü",
    ar: "هويات الموقع الرقمية + التحكم في الوصول",
    fr: "Badges de chantier numériques + contrôle d'accès",
    es: "Credenciales de obra digitales + control de acceso",
    it: "Badge cantiere digitali + controllo accessi",
    pl: "Cyfrowe identyfikatory budowy + kontrola dostępu",
  },
  auditEventType: {
    de: "z. B. worker.deleted",
    en: "e.g. worker.deleted",
    tr: "örn. worker.deleted",
    ar: "مثال: worker.deleted",
    fr: "ex. worker.deleted",
    es: "ej. worker.deleted",
    it: "es. worker.deleted",
    pl: "np. worker.deleted",
  },
  impressumText: {
    de: "Angaben gemäß § 5 TMG\n\nFirmenname GmbH\nMusterstraße 1\n12345 Musterstadt\n\nVertreten durch: Max Mustermann\nE-Mail: info@firma.de",
    en: "Legal notice\n\nCompany Ltd\nSample Street 1\n12345 Sample City\n\nRepresented by: John Smith\nE-mail: info@company.com",
    tr: "Yasal Bildirim\n\nŞirket Ltd.\nÖrnek Caddesi 1\n12345 Örnek Şehir\n\nTemsil eden: Mehmet Yılmaz\nE-posta: info@company.com",
    ar: "إشعار قانوني\n\nشركة المثال\nشارع 1\n12345 مدينة المثال\n\nيمثلها: محمد أحمد\nالبريد: info@company.com",
    fr: "Mentions légales\n\nEntreprise Sarl\n1 Rue Exemple\n75000 Paris\n\nReprésentée par : Jean Dupont\nE-mail : info@enterprise.fr",
    es: "Aviso legal\n\nEmpresa SL\nCalle Ejemplo 1\n28001 Madrid\n\nRepresentada por: Juan García\nE-mail: info@empresa.com",
    it: "Note legali\n\nAzienda Srl\nVia Esempio 1\n20100 Milano\n\nRappresentata da: Mario Rossi\nE-mail: info@azienda.com",
    pl: "Nota prawna\n\nFirma Sp. z o.o.\nul. Przykładowa 1\n00-001 Warszawa\n\nReprezentowana przez: Jan Kowalski\nE-mail: info@firma.com",
  },
  datenschutzText: {
    de: "Datenschutzerklärung gemäß DSGVO\n\nVerantwortlicher: ...\n\n1. Allgemeines\n...",
    en: "Privacy policy\n\nController: ...\n\n1. General\n...",
    tr: "Gizlilik politikası\n\nSorumlu: ...\n\n1. Genel\n...",
    ar: "سياسة الخصوصية\n\nالمسؤول: ...\n\n1. عام\n...",
    fr: "Politique de confidentialité\n\nResponsable : ...\n\n1. Général\n...",
    es: "Política de privacidad\n\nResponsable: ...\n\n1. General\n...",
    it: "Informativa sulla privacy\n\nResponsabile: ...\n\n1. Generale\n...",
    pl: "Polityka prywatności\n\nAdministrator: ...\n\n1. Ogólne\n...",
  },
};

function applyUiPlaceholders() {
  const lang = getStoredUiLang();
  const useGerman = lang === "de";
  Object.entries(UI_PLACEHOLDER_TEXTS).forEach(([elementId, texts]) => {
    const element = document.querySelector(`#${elementId}`);
    if (!element) {
      return;
    }
    const nextPlaceholder = useGerman
      ? (texts.de || "")
      : (texts[lang] || texts.intl || texts.de || "");
    if (nextPlaceholder) {
      element.setAttribute("placeholder", nextPlaceholder);
    }
  });
}

const UI_LANGUAGE_META = {
  de: { code: "DE", flag: "de" },
  en: { code: "EN", flag: "en" },
  tr: { code: "TR", flag: "tr" },
  ar: { code: "AR", flag: "ar" },
  fr: { code: "FR", flag: "fr" },
  es: { code: "ES", flag: "es" },
  it: { code: "IT", flag: "it" },
  pl: { code: "PL", flag: "pl" },
};

function updateAuthLanguageControl(lang) {
  const normalized = normalizeUiLang(lang);
  const meta = UI_LANGUAGE_META[normalized] || UI_LANGUAGE_META[UI_FALLBACK_LANG];
  const authSelect = document.querySelector("#uiLangAuthSelect");
  if (authSelect) {
    authSelect.value = normalized;
  }

  const triggerFlag = document.querySelector("#uiLangAuthTriggerFlag");
  const triggerCode = document.querySelector("#uiLangAuthTriggerCode");
  if (triggerFlag) triggerFlag.setAttribute("data-flag", meta.flag);
  if (triggerCode) triggerCode.textContent = meta.code;

  document.querySelectorAll(".auth-lang-option[data-ui-lang-option]").forEach((button) => {
    const isActive = button.getAttribute("data-ui-lang-option") === normalized;
    button.setAttribute("aria-selected", isActive ? "true" : "false");
  });
}

function closeAuthLanguageMenu() {
  const shell = document.querySelector("#uiLangAuthShell");
  const trigger = document.querySelector("#uiLangAuthTrigger");
  if (shell) shell.classList.remove("is-open");
  if (trigger) trigger.setAttribute("aria-expanded", "false");
}

function toggleAuthLanguageMenu() {
  const shell = document.querySelector("#uiLangAuthShell");
  const trigger = document.querySelector("#uiLangAuthTrigger");
  if (!shell || !trigger) return;
  const nextOpen = !shell.classList.contains("is-open");
  shell.classList.toggle("is-open", nextOpen);
  trigger.setAttribute("aria-expanded", nextOpen ? "true" : "false");
}

function applyUiTranslations() {
  const lang = getStoredUiLang();
  const isRtl = lang === "ar";
  document.documentElement.lang = lang;
  const authPanel = document.querySelector(".auth-panel");
  if (authPanel) {
    authPanel.setAttribute("dir", isRtl ? "rtl" : "ltr");
  }

  document.querySelectorAll("[data-ui-i18n]").forEach((el) => {
    const key = el.getAttribute("data-ui-i18n");
    const attr = el.getAttribute("data-ui-i18n-attr");
    if (!key) return;
    const value = uiT(key);
    if (attr) {
      el.setAttribute(attr, value);
    } else {
      el.textContent = value;
    }
  });

  applyUiPlaceholders();
  applyRuntimeUiTexts();

  updateAuthLanguageControl(lang);
  const topbarSelect = document.querySelector("#uiLangTopbarSelect");
  if (topbarSelect) topbarSelect.value = lang;
}

function setUiLang(lang) {
  const normalized = normalizeUiLang(lang);
  window.localStorage.setItem(UI_LANG_STORAGE_KEY, normalized);
  applyUiTranslations();
  applySystemTheme(getStoredSystemTheme(), { persist: false });
  updateDesktopInstallHint();
}

function initUiLanguageControl() {
  const initial = getStoredUiLang();
  window.localStorage.setItem(UI_LANG_STORAGE_KEY, initial);
  const authSelect = document.querySelector("#uiLangAuthSelect");
  const authShell = document.querySelector("#uiLangAuthShell");
  const authTrigger = document.querySelector("#uiLangAuthTrigger");
  if (authSelect) {
    authSelect.value = initial;
    authSelect.addEventListener("change", () => setUiLang(authSelect.value || UI_FALLBACK_LANG));
  }
  if (authTrigger) {
    authTrigger.addEventListener("click", () => toggleAuthLanguageMenu());
  }
  document.querySelectorAll(".auth-lang-option[data-ui-lang-option]").forEach((button) => {
    button.addEventListener("click", () => {
      const nextLang = button.getAttribute("data-ui-lang-option") || UI_FALLBACK_LANG;
      closeAuthLanguageMenu();
      setUiLang(nextLang);
    });
  });
  document.addEventListener("click", (event) => {
    if (!authShell || !authShell.contains(event.target)) {
      closeAuthLanguageMenu();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeAuthLanguageMenu();
    }
  });
  const topbarSelect = document.querySelector("#uiLangTopbarSelect");
  if (topbarSelect) {
    topbarSelect.value = initial;
    topbarSelect.addEventListener("change", () => setUiLang(topbarSelect.value));
  }
  applyUiTranslations();
}

const SYSTEM_THEME_STORAGE_KEY = "baupass-system-theme";
const SYSTEM_THEME_WHITE = "white";
const SYSTEM_THEME_BLACK = "black";

function normalizeSystemTheme(value) {
  if (value === SYSTEM_THEME_BLACK) return SYSTEM_THEME_BLACK;
  return SYSTEM_THEME_WHITE;
}

function getStoredSystemTheme() {
  try {
    return normalizeSystemTheme(window.localStorage.getItem(SYSTEM_THEME_STORAGE_KEY));
  } catch {
    return SYSTEM_THEME_WHITE;
  }
}

function getSystemThemeTexts() {
  const lang = getStoredUiLang();
  const map = {
    de: {
      labelPrefix: "Fensterfarbe",
      white: "Weiss",
      dark: "Dunkel",
      titleWhenDark: "Aktuell Dunkel. Klicken fuer Weiss.",
      titleWhenWhite: "Aktuell Weiss. Klicken fuer Dunkel."
    },
    en: {
      labelPrefix: "Window color",
      white: "Light",
      dark: "Dark",
      titleWhenDark: "Currently dark. Click for light.",
      titleWhenWhite: "Currently light. Click for dark."
    },
    tr: {
      labelPrefix: "Pencere rengi",
      white: "Aydinlik",
      dark: "Koyu",
      titleWhenDark: "Su an koyu. Aydinlik icin tiklayin.",
      titleWhenWhite: "Su an aydinlik. Koyu icin tiklayin."
    },
    ar: {
      labelPrefix: "لون النافذة",
      white: "فاتح",
      dark: "داكن",
      titleWhenDark: "الوضع الحالي داكن. انقر للوضع الفاتح.",
      titleWhenWhite: "الوضع الحالي فاتح. انقر للوضع الداكن."
    },
    fr: {
      labelPrefix: "Couleur de fenetre",
      white: "Clair",
      dark: "Sombre",
      titleWhenDark: "Mode sombre actif. Cliquer pour clair.",
      titleWhenWhite: "Mode clair actif. Cliquer pour sombre."
    },
    es: {
      labelPrefix: "Color de ventana",
      white: "Claro",
      dark: "Oscuro",
      titleWhenDark: "Modo oscuro activo. Haz clic para claro.",
      titleWhenWhite: "Modo claro activo. Haz clic para oscuro."
    },
    it: {
      labelPrefix: "Colore finestra",
      white: "Chiaro",
      dark: "Scuro",
      titleWhenDark: "Modalita scura attiva. Clicca per chiaro.",
      titleWhenWhite: "Modalita chiara attiva. Clicca per scuro."
    },
    pl: {
      labelPrefix: "Kolor okna",
      white: "Jasny",
      dark: "Ciemny",
      titleWhenDark: "Aktualnie ciemny. Kliknij, aby ustawic jasny.",
      titleWhenWhite: "Aktualnie jasny. Kliknij, aby ustawic ciemny."
    }
  };
  return map[lang] || map.de;
}

function getThemeModeLabel(mode) {
  const texts = getSystemThemeTexts();
  return mode === SYSTEM_THEME_BLACK ? texts.dark : texts.white;
}

function applySystemTheme(mode, { persist = true } = {}) {
  const selectedMode = normalizeSystemTheme(mode);
  document.body.classList.remove("theme-black", "theme-white");
  document.body.classList.add(selectedMode === SYSTEM_THEME_BLACK ? "theme-black" : "theme-white");
  document.body.style.setProperty("--window-color", selectedMode === SYSTEM_THEME_BLACK ? "#000000" : "#ffffff");
  if (persist) {
    try {
      window.localStorage.setItem(SYSTEM_THEME_STORAGE_KEY, selectedMode);
    } catch {
      // ignore storage errors (private mode / blocked storage)
    }
  }
  try {
    window.localStorage.removeItem("baupass-system-theme-color");
  } catch {
    // ignore storage errors (private mode / blocked storage)
  }

  const button = document.querySelector("#systemThemeToggleButton");
  if (button) {
    const texts = getSystemThemeTexts();
    button.textContent = `${texts.labelPrefix}: ${getThemeModeLabel(selectedMode)}`;
    button.title = selectedMode === SYSTEM_THEME_BLACK
      ? texts.titleWhenDark
      : texts.titleWhenWhite;
  }
}

function toggleSystemTheme() {
  const currentMode = getStoredSystemTheme();
  applySystemTheme(currentMode === SYSTEM_THEME_BLACK ? SYSTEM_THEME_WHITE : SYSTEM_THEME_BLACK);
}

function initSystemThemeControl() {
  applySystemTheme(getStoredSystemTheme(), { persist: false });
}

let deferredDesktopInstallPrompt = null;
const elements = {
  body: document.body,
  desktopTitlebar: document.querySelector("#desktopTitlebar"),
  desktopMinimizeBtn: document.querySelector("#desktopMinimizeBtn"),
  desktopMaximizeBtn: document.querySelector("#desktopMaximizeBtn"),
  desktopCloseBtn: document.querySelector("#desktopCloseBtn"),
  authOverlay: document.querySelector("#authOverlay"),
  authPanel: document.querySelector("#authOverlay .auth-panel"),
  mainShell: document.querySelector("#mainShell"),
  loginForm: document.querySelector("#loginForm"),
  loginUsername: document.querySelector("#loginUsername"),
  loginPassword: document.querySelector("#loginPassword"),
  loginOtpCode: document.querySelector("#loginOtpCode"),
  loginScope: document.querySelector("#loginScope"),
  loginSupportNotice: document.querySelector("#loginSupportNotice"),
  loginResetPasswordButton: document.querySelector("#loginResetPasswordButton"),
  systemThemeToggleButton: document.querySelector("#systemThemeToggleButton"),
  desktopInstallButton: document.querySelector("#desktopInstallButton"),
  desktopInstallHint: document.querySelector("#desktopInstallHint"),
  logoutButton: document.querySelector("#logoutButton"),
  systemAlertBanner: document.querySelector("#systemAlertBanner"),
  systemAlertText: document.querySelector("#systemAlertText"),
  systemAlertActionBtn: document.querySelector("#systemAlertActionBtn"),
  seedDataButton: document.querySelector("#seedDataButton"),
  exportButton: document.querySelector("#exportButton"),
  importButton: document.querySelector("#importButton"),
  sessionCard: document.querySelector("#sessionCard"),
  views: Array.from(document.querySelectorAll(".view")),
  navLinks: Array.from(document.querySelectorAll(".nav-link")),
  statsGrid: document.querySelector("#statsGrid"),
  reportingSummaryGrid: document.querySelector("#reportingSummaryGrid"),
  reportingTopOverdueList: document.querySelector("#reportingTopOverdueList"),
  reportingAccessDaily: document.querySelector("#reportingAccessDaily"),
  recentAccessList: document.querySelector("#recentAccessList"),
  dashboardPorterLivePanel: document.querySelector("#dashboardPorterLivePanel"),
  workerList: document.querySelector("#workerList"),
  workerSearchInput: document.querySelector("#workerSearchInput"),
  bulkSelectAll: document.querySelector("#bulkSelectAll"),
  bulkActionBar: document.querySelector("#bulkActionBar"),
  bulkSelectionCount: document.querySelector("#bulkSelectionCount"),
  bulkDeleteButton: document.querySelector("#bulkDeleteButton"),
  bulkSetActiveButton: document.querySelector("#bulkSetActiveButton"),
  bulkSetInactiveButton: document.querySelector("#bulkSetInactiveButton"),
  bulkCancelButton: document.querySelector("#bulkCancelButton"),
  badgePreview: document.querySelector("#badgePreview"),
  badgeMeta: document.querySelector("#badgeMeta"),
  badgeActionRow: document.querySelector("#badgeActionRow"),
  printBadgeButton: document.querySelector("#printBadgeButton"),
  appLinkBadgeButton: document.querySelector("#appLinkBadgeButton"),
  loginGreetingToast: document.querySelector("#loginGreetingToast"),
  deviceStatusList: document.querySelector("#deviceStatusList"),
  deviceApiKeyResult: document.querySelector("#deviceApiKeyResult"),
  deviceForm: document.querySelector("#deviceForm"),
  deviceName: document.querySelector("#deviceName"),
  deviceLocation: document.querySelector("#deviceLocation"),
  deviceType: document.querySelector("#deviceType"),
  accessLogList: document.querySelector("#accessLogList"),
  accessSummaryGrid: document.querySelector("#accessSummaryGrid"),
  accessHourlyGrid: document.querySelector("#accessHourlyGrid"),
  accessOpenWarnings: document.querySelector("#accessOpenWarnings"),
  dayCloseBanner: document.querySelector("#dayCloseBanner"),
  porterLivePanel: document.querySelector("#porterLivePanel"),
  accessDuplicateError: document.querySelector("#accessDuplicateError"),
  accessFeedbackOverlay: document.querySelector("#accessFeedbackOverlay"),
  accessFeedbackTitle: document.querySelector("#accessFeedbackTitle"),
  accessFeedbackMeta: document.querySelector("#accessFeedbackMeta"),
  accessFeedbackPhoto: document.querySelector("#accessFeedbackPhoto"),
  accessWorkerSelect: document.querySelector("#accessWorkerSelect"),
  turnstileQuickPanel: document.querySelector("#turnstileQuickPanel"),
  companySelect: document.querySelector("#companySelect"),
  workerType: document.querySelector("#workerType"),
  visitorFields: document.querySelector("#visitorFields"),
  visitorCompany: document.querySelector("#visitorCompany"),
  visitPurpose: document.querySelector("#visitPurpose"),
  hostName: document.querySelector("#hostName"),
  visitEndAt: document.querySelector("#visitEndAt"),
  badgePinHint: document.querySelector("#badgePinHint"),
  invoiceCompanySelect: document.querySelector("#invoiceCompanySelect"),
  companyList: document.querySelector("#companyList"),
  compliancePanel: document.querySelector("#compliancePanel"),
  auditLogPanel: document.querySelector("#auditLogPanel"),
  dayCloseAcknowledgeForm: document.querySelector("#dayCloseAcknowledgeForm"),
  dayCloseComment: document.querySelector("#dayCloseComment"),
  dayCloseAcknowledgeButton: document.querySelector("#dayCloseAcknowledgeButton"),
  cameraPlaceholder: document.querySelector("#cameraPlaceholder"),
  cameraPreview: document.querySelector("#cameraPreview"),
  capturedPhoto: document.querySelector("#capturedPhoto"),
  companyForm: document.querySelector("#companyForm"),
  invoiceHistoryList: document.querySelector("#invoiceHistoryList"),
  invoiceLogoData: document.querySelector("#invoiceLogoData"),
  invoiceLogoPreview: document.querySelector("#invoiceLogoPreview"),
  invoiceRecipientEmail: document.querySelector("#invoiceRecipientEmail"),
  invoicePreviewFrame: document.querySelector("#invoicePreviewFrame"),
  photoAdjustStatus: document.querySelector("#photoAdjustStatus"),
  photoRequiredHint: document.querySelector("#photoRequiredHint"),
  photoCanvas: document.querySelector("#photoCanvas"),
  photoData: document.querySelector("#photoData"),
  photoFileInput: document.querySelector("#photoFileInput"),
  photoDebugText: document.querySelector("#photoDebugText"),
  photoMoveButtons: Array.from(document.querySelectorAll(".photo-move-btn")),
  photoResetButton: document.querySelector("#photoResetButton"),
  photoSharpen: document.querySelector("#photoSharpen"),
  photoSharpenValue: document.querySelector("#photoSharpenValue"),
  photoZoom: document.querySelector("#photoZoom"),
  photoZoomValue: document.querySelector("#photoZoomValue"),
  // ...weitere Elemente nach Bedarf...
};

let token = loadStoredSessionToken();
let qrLibraryLoadPromise = null;
let accessFeedbackTimer = null;
let accessAudioContext = null;
let cameraStream = null;
let backendStatusTimer = null;
let heartbeatTimer = null;
let selfieSegmenter = null;
let sessionExpiryNoticeShown = false;
let sessionExpiryNoticeAt = 0;
let invoicePaidHighlightTimer = null;
let invoiceAutoRefreshTimer = null;
let invoiceApprovalRefreshTimer = null;
let turnstileTapInFlight = false;
let turnstileTapLiveResetTimer = null;
let lastLoginFocusAt = 0;
let loginLockOverlayTimer = null;
let companyBrandingPreviewOverride = "";
let superadminUiPreviewCompanyId = "";
const LOGIN_HARD_LOCK_MS = 10 * 60 * 1000;
const LOGIN_SUPPORT_PHONE_FALLBACK = "+49 176 31676589";

const PLAN_LABELS = {
  tageskarte: "Besucherkarte",
  starter: "Starter",
  professional: "Professional",
  enterprise: "Enterprise"
};

const PLAN_NET_PRICE_EUR = {
  tageskarte: 19,
  starter: 49,
  professional: 99,
  enterprise: 199,
};

const state = {
  currentUser: null,
  supportLoginContext: loadSupportLoginContext(),
  settings: {
    platformName: "BauPass Control",
    operatorName: "Deine Betriebsfirma",
    turnstileEndpoint: ""
  },
  companies: [],
  subcompanies: [],
  workers: [],
  accessLogs: [],
  accessInsights: { hourly: [], openEntries: [] },
  reporting: { kpis: {}, accessDaily: [], topOverdueCompanies: [] },
  invoices: [],
  devices: [],
  invoiceOpsMetrics: {
    avgFirstSuccessMinutes: 0,
    criticalOver24h: 0,
    retryVolume7d: [],
    topErrorReasons: [],
  },
  invoiceDeadLetters: [],
  invoiceApprovalRequests: [],
  companyRepairHistory: {},
  companyRepairBusy: {},
  companyRepairStatus: {},
  companyLockBusy: {},
  companyTurnstiles: {},
  companyAdminSecurity: {},
  complianceOverview: [],
  auditLogs: [],
  repairHistoryWindowDays: 30,
  onlyCompaniesWithRepairs: false,
  dayClose: null,
  editingWorkerId: null,
  selectedWorkerId: null,
  accessFilter: { from: "", to: "", direction: "", gate: "" },
  porterLive: { workerId: null, lastEvent: null },
  twofa: { enabled: false, secret: "", otpauthUri: "" },
  loginOtpPending: false,
  loginSecurity: {
    failCount: 0,
    blockedUntil: 0,
  },
  invoiceJustPaidId: "",
  invoiceSeenIds: {},
  invoiceNewIds: {},
  invoiceRetrySelectedIds: [],
  invoiceAttemptHistoryById: {},
  invoiceAttemptHistoryLoadingById: {},
  invoiceHistoryExpandedById: {}
};

const PHOTO_EDITOR_ZOOM_DEFAULT = 1.18;
const PHOTO_EDITOR_ZOOM_MIN = 1;
const PHOTO_EDITOR_ZOOM_MAX = 1.8;
const PHOTO_EDITOR_STEP = 10;
const PHOTO_TARGET_WIDTH = 480;
const PHOTO_TARGET_HEIGHT = 360;
const PHOTO_JPEG_QUALITY = 0.92;

let photoEditorSourceData = "";
let photoEditorImage = null;
let photoEditorOffset = { x: 0, y: 0 };
let photoEditorZoom = PHOTO_EDITOR_ZOOM_DEFAULT;
let photoSharpenAmount = 0.28;
let photoDragState = {
  active: false,
  pointerId: null,
  startX: 0,
  startY: 0,
  baseOffsetX: 0,
  baseOffsetY: 0
};

function normalizeLog(entry) {
  return {
    id: entry?.id || "",
    workerId: entry?.workerId || entry?.worker_id || "",
    direction: entry?.direction || "",
    gate: entry?.gate || "",
    note: entry?.note || "",
    timestamp: entry?.timestamp || ""
  };
}

function getRuntimeUiTexts() {
  const lang = getStoredUiLang();
  const base = {
    sessionLoggedIn: "Signed in",
    sessionRole: "Role",
    roleUnknown: "Unknown",
    roleSuperadmin: "Superadmin",
    roleCompanyAdmin: "Company admin",
    roleTurnstile: "Turnstile",
    statsWorkersTotal: "Workers total",
    statsWorkersActive: "Active workers",
    statsVisitorsTotal: "Visitors total",
    statsCompanies: "Companies",
    statsAccessToday: "Currently on-site",
    badgePinHintVisitor: "Visitors use the one-time link/QR. A badge PIN is not required for visitors.",
    badgePinHintWorker: "Badge login in the worker app now works only with badge ID and this PIN. While editing, you can set a new PIN here.",
    workerListEmpty: "No workers created yet.",
    workerListNoResults: "No results for \"{term}\".",
    recentAccessEmpty: "No access bookings yet.",
    badgeEmptyStateShort: "Please create a worker first.",
    badgeNoneSelected: "No badge selected.",
    dayReportEmpty: "No data available for the daily report yet.",
    hourlyEmpty: "No hourly values available.",
    summaryEntries: "Entries",
    summaryExits: "Exits",
    summaryTotal: "Total",
    summaryLastBooking: "Latest booking",
    summaryPeople: "Visitors / Workers",
    hourlyIn: "In",
    hourlyOut: "Out",
    cameraNotStarted: "Camera not started.",
    cameraUnavailableWithHint: "Browser camera unavailable.{hint}",
    cameraHintSecureContext: " HTTPS or localhost is required.",
    cameraActiveCanCapture: "Camera active. You can now take a photo.",
    cameraNeedsHttps: "Browser camera requires HTTPS or localhost.",
    cameraAccessBlocked: "Camera access was blocked. Please allow camera permission in the browser.",
    cameraNotFound: "No camera found.",
    cameraInUse: "Camera is already in use by another app or browser tab.",
    cameraConstraintFailed: "Camera could not be started with the requested settings.",
    cameraApiMissing: "This browser does not provide a live camera API.",
    cameraStartFailed: "Camera could not be started: {reason}",
    photoCaptured: "Photo captured ({preview})",
    photoPosition: "Position: X {x} | Y {y}",
    photoSharpenNormal: "Normal",
    photoSharpenSoft: "Soft",
    photoSharpenVerySharp: "Very sharp",
    photoRequiredOk: "Photo captured. Badge can be saved.",
    photoRequiredMissing: "Required: Without a photo, the badge cannot be saved.",
    bulkSelectedCount: "{count} selected",
    photoWhiteBgActive: "Background fully white (active)",
    photoAdjustHelp: "Move the photo after capture so it fits cleanly on the right side of the badge.",
    photoZoomCropLabel: "Zoom / Crop",
    photoSharpenLabel: "Sharpness:",
    bulkSelectAllLabel: "Select all",
    noSubcompanyOption: "No subcompany",
    selectPersonOption: "Please select a person",
    visitorTagShort: "Visitor",
    dashboardLastAccessPlaceholder: "Latest access is shown once a check-in or check-out exists.",
    dashboardLastAccessHeading: "Latest access",
    dashboardDirectionCheckin: "Check-in",
    dashboardDirectionCheckout: "Check-out",
    unknownPerson: "Unknown",
    unknownCompany: "Unknown company",
    unknownTurnstile: "Unknown turnstile",
    accessFilterEmpty: "No access bookings for the selected filter.",
    dayCloseAutoClosedAfterMidnight: "Automatically checked out after 00:00:",
    dayCloseAckTitle: "Day-close already acknowledged",
    dayCloseAckByOn: "By {user} on {when}",
    dayCloseCommentLabel: "Comment: {comment}",
    dayCloseCheckActive: "Day-close check active",
    dayCloseOpenEntriesNoExit: "{count} open check-ins without check-out.",
    dayCloseNoOpenEntries: "No open check-ins.",
    dayCloseAlertAt18: "Day-close 18:00: {count} open check-ins without check-out found.",
    dayCloseCommentMin: "Please enter a meaningful comment with at least 4 characters.",
    dayCloseAckSuccess: "Day-close acknowledged successfully.",
    turnstileSelectWorkerFirst: "Please select a worker first.",
    workerPhotoRequired: "Please take a photo first. The badge can only be saved with photo.",
    subcompanyNameRequired: "Please select company and subcompany name first.",
    cameraPermissionRetry: "Camera access was blocked. Please allow camera access in the browser and click Start camera again.",
    photoReadFailed: "Photo could not be read.",
    photoLoadFailed: "Photo could not be loaded.",
    cameraStartFirst: "Please start the camera first.",
    photoProcessingUnavailable: "Photo processing unavailable.",
    workerBadgePinMissing: "Please set a badge PIN for the worker.",
    visitorPurposeMissing: "Please provide a visit purpose.",
    visitorCompanyMissing: "Please provide the visitor company.",
    visitorHostMissing: "Please provide an on-site contact person.",
    visitorEndMissing: "Please provide a visit end date and time.",
    popupBlockedAllow: "Popup blocked. Please allow popups.",
    logoImageFileRequired: "Please select an image file for the logo.",
    invoiceSentEmail: "Invoice sent by email.",
    invoiceSavedEmailNotConfigured: "Invoice saved, but email is not configured. Please configure SMTP in Admin settings.",
    invoiceSelectCompany: "Please select a company.",
    invoiceRecipientInvalid: "Please enter a valid recipient email.",
    invoiceFormRequiredFields: "Please fill in invoice date, due date, service period, and service description.",
    invoiceMarkedPaid: "Invoice marked as paid.",
    backendUnreachableReload: "Backend unreachable. Please check server/network and reload.",
    loginResponseIncomplete: "Login response from server is incomplete. Please reload and try again.",
    demoAdminOnly: "Only admin roles can load demo data.",
    loginFirst: "Please sign in first.",
    porterOnSiteByCompanyHeading: "On-site by company",
    porterOnSiteHeading: "Currently on site",
    porterNoActiveCheckins: "No active check-ins yet.",
    porterTotal: "Total",
    porterPersonSingular: "person",
    porterPersonPlural: "persons",
  };
  const map = {
    de: {
      sessionLoggedIn: "Angemeldet",
      sessionRole: "Rolle",
      roleUnknown: "Unbekannt",
      roleSuperadmin: "Superadmin",
      roleCompanyAdmin: "Firmen-Admin",
      roleTurnstile: "Drehkreuz",
      statsWorkersTotal: "Mitarbeiter gesamt",
      statsWorkersActive: "Aktive Mitarbeiter",
      statsVisitorsTotal: "Besucher gesamt",
      statsCompanies: "Firmen",
      statsAccessToday: "Aktiv auf Baustelle",
      badgePinHintVisitor: "Besucher nutzen den Einmal-Link/QR. Eine Badge-PIN ist fuer Besucher nicht erforderlich.",
      badgePinHintWorker: "Badge-Login in der Mitarbeiter-App funktioniert nur noch mit Badge-ID und dieser PIN. Beim Bearbeiten kannst du hier eine neue PIN setzen.",
      workerListEmpty: "Noch keine Mitarbeiter angelegt.",
      workerListNoResults: "Keine Treffer fuer \"{term}\".",
      recentAccessEmpty: "Noch keine Zutrittsbuchungen vorhanden.",
      badgeEmptyStateShort: "Bitte zuerst einen Mitarbeiter anlegen.",
      badgeNoneSelected: "Kein Badge ausgewaehlt.",
      dayReportEmpty: "Noch keine Daten fuer den Tagesbericht.",
      hourlyEmpty: "Keine Stundenwerte verfuegbar.",
      summaryEntries: "Eintritte",
      summaryExits: "Austritte",
      summaryTotal: "Gesamt",
      summaryLastBooking: "Letzte Buchung",
      summaryPeople: "Besucher / Mitarbeiter",
      hourlyIn: "In",
      hourlyOut: "Out",
      cameraNotStarted: "Kamera noch nicht gestartet.",
      cameraUnavailableWithHint: "Browser-Kamera nicht verfuegbar.{hint}",
      cameraHintSecureContext: " HTTPS oder localhost ist erforderlich.",
      cameraActiveCanCapture: "Kamera aktiv. Du kannst jetzt ein Foto aufnehmen.",
      cameraNeedsHttps: "Browser-Kamera benoetigt HTTPS oder localhost.",
      cameraAccessBlocked: "Kamera-Zugriff wurde blockiert. Bitte Browser-Berechtigung fuer Kamera erlauben.",
      cameraNotFound: "Keine Kamera gefunden.",
      cameraInUse: "Kamera ist bereits von einer anderen App oder Browser-Registerkarte belegt.",
      cameraConstraintFailed: "Kamera konnte mit den angeforderten Einstellungen nicht gestartet werden.",
      cameraApiMissing: "Dieser Browser stellt keine Live-Kamera-API bereit.",
      cameraStartFailed: "Kamera konnte nicht gestartet werden: {reason}",
      photoCaptured: "Foto erfasst ({preview})",
      photoPosition: "Position: X {x} | Y {y}",
      photoSharpenNormal: "Normal",
      photoSharpenSoft: "Weich",
      photoSharpenVerySharp: "Sehr scharf",
      photoRequiredOk: "Foto erfasst. Ausweis kann gespeichert werden.",
      photoRequiredMissing: "Pflicht: Ohne Foto kann der Ausweis nicht gespeichert werden.",
      bulkSelectedCount: "{count} ausgewaehlt",
      photoWhiteBgActive: "Hintergrund komplett weiss (aktiv)",
      photoAdjustHelp: "Foto nach Aufnahme verschieben, damit es rechts im Ausweis sauber passt.",
      photoZoomCropLabel: "Zoom / Zuschneiden",
      photoSharpenLabel: "Schaerfe:",
      bulkSelectAllLabel: "Alle auswaehlen",
      noSubcompanyOption: "Kein Subunternehmen",
      selectPersonOption: "Bitte Person waehlen",
      visitorTagShort: "Besucher",
      dashboardLastAccessPlaceholder: "Letzter Zutritt wird angezeigt, sobald eine An- oder Abmeldung vorliegt.",
      dashboardLastAccessHeading: "Letzter Zutritt",
      dashboardDirectionCheckin: "Anmeldung",
      dashboardDirectionCheckout: "Abmeldung",
      unknownPerson: "Unbekannt",
      unknownCompany: "Unbekannte Firma",
      unknownTurnstile: "Unbekanntes Drehkreuz",
      accessFilterEmpty: "Keine Zutrittsbuchungen fuer den gewaelten Filter.",
      dayCloseAutoClosedAfterMidnight: "Nach 00:00 automatisch abgemeldet:",
      dayCloseAckTitle: "Tagesabschluss bereits quittiert",
      dayCloseAckByOn: "Von {user} am {when}",
      dayCloseCommentLabel: "Kommentar: {comment}",
      dayCloseCheckActive: "Tagesabschluss-Pruefung aktiv",
      dayCloseOpenEntriesNoExit: "{count} offene Eintritte ohne Austritt.",
      dayCloseNoOpenEntries: "Keine offenen Eintritte.",
      dayCloseAlertAt18: "Tagesabschluss 18:00: {count} offene Eintritte ohne Austritt gefunden.",
      dayCloseCommentMin: "Bitte einen aussagekraeftigen Kommentar mit mindestens 4 Zeichen eingeben.",
      dayCloseAckSuccess: "Tagesabschluss wurde erfolgreich quittiert.",
      turnstileSelectWorkerFirst: "Bitte zuerst einen Mitarbeiter auswaehlen.",
      workerPhotoRequired: "Bitte zuerst ein Foto aufnehmen. Der Ausweis wird nur mit Foto gespeichert.",
      subcompanyNameRequired: "Bitte zuerst Firma und Subunternehmensname angeben.",
      cameraPermissionRetry: "Kamera-Zugriff wurde blockiert. Bitte Browser-Zugriff auf die Kamera erlauben und erneut auf Kamera starten klicken.",
      photoReadFailed: "Foto konnte nicht gelesen werden.",
      photoLoadFailed: "Foto konnte nicht geladen werden.",
      cameraStartFirst: "Bitte zuerst die Kamera starten.",
      photoProcessingUnavailable: "Fotoverarbeitung nicht verfuegbar.",
      workerBadgePinMissing: "Bitte eine Badge-PIN fuer den Mitarbeiter setzen.",
      visitorPurposeMissing: "Bitte einen Besuchszweck angeben.",
      visitorCompanyMissing: "Bitte die Besucherfirma angeben.",
      visitorHostMissing: "Bitte einen Ansprechpartner vor Ort angeben.",
      visitorEndMissing: "Bitte ein Besuchsende mit Datum und Uhrzeit angeben.",
      popupBlockedAllow: "Popup blockiert. Bitte Popups erlauben.",
      logoImageFileRequired: "Bitte eine Bilddatei fuer das Logo auswaehlen.",
      invoiceSentEmail: "Rechnung wurde per E-Mail versendet.",
      invoiceSavedEmailNotConfigured: "Rechnung wurde gespeichert, aber E-Mail ist nicht eingerichtet. Bitte SMTP im Superadmin-Bereich unter Admin-Einstellungen konfigurieren.",
      invoiceSelectCompany: "Bitte eine Firma auswaehlen.",
      invoiceRecipientInvalid: "Bitte eine gueltige Empfaenger-E-Mail eingeben.",
      invoiceFormRequiredFields: "Bitte Rechnungsdatum, Faelligkeitsdatum, Leistungszeitraum und Leistungsbeschreibung ausfuellen.",
      invoiceMarkedPaid: "Rechnung als bezahlt markiert",
      backendUnreachableReload: "Backend nicht erreichbar. Bitte pruefe, ob der Server laeuft und lade die Seite neu.",
      loginResponseIncomplete: "Login-Antwort vom Server ist unvollstaendig. Bitte Seite neu laden und erneut versuchen.",
      demoAdminOnly: "Nur Admin-Rollen duerfen Demo-Daten laden.",
      loginFirst: "Bitte zuerst anmelden.",
      porterOnSiteByCompanyHeading: "Aktuell auf der Baustelle je Firma",
      porterOnSiteHeading: "Aktuell auf der Baustelle",
      porterNoActiveCheckins: "Noch keine aktiven Anmeldungen vorhanden.",
      porterTotal: "Gesamt",
      porterPersonSingular: "Person",
      porterPersonPlural: "Personen",
    },
    tr: {
      sessionLoggedIn: "Giris yapan",
      sessionRole: "Rol",
      roleUnknown: "Bilinmiyor",
      roleSuperadmin: "Superadmin",
      roleCompanyAdmin: "Firma Y\u00f6neticisi",
      roleTurnstile: "Turnike",
      statsWorkersTotal: "Toplam \u00e7al\u0131\u015fan",
      statsWorkersActive: "Aktif \u00e7al\u0131\u015fan",
      statsVisitorsTotal: "Toplam ziyaret\u00e7i",
      statsCompanies: "Firmalar",
      statsAccessToday: "Şu an sahada",
      badgePinHintVisitor: "Ziyaret\u00e7iler tek kullan\u0131ml\u0131k link/QR kullan\u0131r. Ziyaret\u00e7iler i\u00e7in Badge PIN gerekli de\u011fildir.",
      badgePinHintWorker: "\u00c7al\u0131\u015fan uygulamas\u0131nda rozet giri\u015fi yaln\u0131zca Badge ID ve PIN ile \u00e7al\u0131\u015f\u0131r. D\u00fczenleme s\u0131ras\u0131nda burada yeni PIN ayarlayabilirsiniz.",
      workerListEmpty: "Hen\u00fcz \u00e7al\u0131\u015fan eklenmemi\u015f.",
      workerListNoResults: "\"{term}\" i\u00e7in sonu\u00e7 bulunamad\u0131.",
      recentAccessEmpty: "Hen\u00fcz eri\u015fim kayd\u0131 yok.",
      badgeEmptyStateShort: "L\u00fctfen \u00f6nce bir \u00e7al\u0131\u015fan olu\u015fturun.",
      badgeNoneSelected: "Rozet se\u00e7ilmedi.",
      dayReportEmpty: "G\u00fcnl\u00fck rapor i\u00e7in hen\u00fcz veri yok.",
      hourlyEmpty: "Saatlik de\u011fer mevcut de\u011fil.",
      summaryEntries: "Giri\u015fler",
      summaryExits: "\u00c7\u0131k\u0131\u015flar",
      summaryTotal: "Toplam",
      summaryLastBooking: "Son kay\u0131t",
      summaryPeople: "Ziyaret\u00e7i / \u00c7al\u0131\u015fan",
      hourlyIn: "Giri\u015f",
      hourlyOut: "\u00c7\u0131k\u0131\u015f",
      cameraNotStarted: "Kamera hen\u00fcz ba\u015flat\u0131lmad\u0131.",
      cameraUnavailableWithHint: "Taray\u0131c\u0131 kameras\u0131 mevcut de\u011fil.{hint}",
      cameraHintSecureContext: " HTTPS veya localhost gereklidir.",
      cameraActiveCanCapture: "Kamera aktif. Art\u0131k foto\u011fraf \u00e7ekebilirsiniz.",
      cameraNeedsHttps: "Taray\u0131c\u0131 kameras\u0131 HTTPS veya localhost gerektirir.",
      cameraAccessBlocked: "Kamera eri\u015fimi engellendi. L\u00fctfen taray\u0131c\u0131da kamera iznini etkinle\u015ftirin.",
      cameraNotFound: "Kamera bulunamad\u0131.",
      cameraInUse: "Kamera ba\u015fka bir uygulama veya taray\u0131c\u0131 sekmesi taraf\u0131ndan kullan\u0131l\u0131yor.",
      cameraConstraintFailed: "Kamera istenen ayarlarla ba\u015flat\u0131lamad\u0131.",
      cameraApiMissing: "Bu taray\u0131c\u0131 canl\u0131 kamera API\u2019sini desteklemiyor.",
      cameraStartFailed: "Kamera ba\u015flat\u0131lamad\u0131: {reason}",
      photoCaptured: "Foto\u011fraf \u00e7ekildi ({preview})",
      photoPosition: "Konum: X {x} | Y {y}",
      photoSharpenNormal: "Normal",
      photoSharpenSoft: "Yumu\u015fak",
      photoSharpenVerySharp: "\u00c7ok keskin",
      photoRequiredOk: "Foto\u011fraf \u00e7ekildi. Rozet kaydedilebilir.",
      photoRequiredMissing: "Zorunlu: Foto\u011frafs\u0131z rozet kaydedilemez.",
      bulkSelectedCount: "{count} se\u00e7ildi",
      photoWhiteBgActive: "Arka plan tamamen beyaz (aktif)",
      photoAdjustHelp: "Foto\u011fraf\u0131 \u00e7ektikten sonra rozette sa\u011f tarafa d\u00fczg\u00fcn oturmas\u0131 i\u00e7in kayd\u0131r\u0131n.",
      photoZoomCropLabel: "Zoom / K\u0131rpma",
      photoSharpenLabel: "Keskinlik:",
      bulkSelectAllLabel: "T\u00fcm\u00fcn\u00fc se\u00e7",
      noSubcompanyOption: "Alt firma yok",
      selectPersonOption: "L\u00fctfen bir ki\u015fi se\u00e7in",
      visitorTagShort: "Ziyaret\u00e7i",
      dashboardLastAccessPlaceholder: "\u0130lk giri\u015f veya \u00e7\u0131k\u0131\u015f kaydedildi\u011finde burada g\u00f6r\u00fcn\u00fcr.",
      dashboardLastAccessHeading: "Son giri\u015f",
      dashboardDirectionCheckin: "Giri\u015f",
      dashboardDirectionCheckout: "\u00c7\u0131k\u0131\u015f",
      unknownPerson: "Bilinmiyor",
      unknownCompany: "Bilinmeyen firma",
      unknownTurnstile: "Bilinmeyen turnike",
      accessFilterEmpty: "Se\u00e7ilen filtre i\u00e7in giri\u015f kayd\u0131 yok.",
      dayCloseAutoClosedAfterMidnight: "00:00\u2019dan sonra otomatik \u00e7\u0131k\u0131\u015f:",
      dayCloseAckTitle: "G\u00fcn kapan\u0131\u015f\u0131 zaten onayland\u0131",
      dayCloseAckByOn: "{user} taraf\u0131ndan {when} tarihinde",
      dayCloseCommentLabel: "Yorum: {comment}",
      dayCloseCheckActive: "G\u00fcn kapan\u0131\u015f\u0131 kontrol\u00fc aktif",
      dayCloseOpenEntriesNoExit: "{count} \u00e7\u0131k\u0131\u015fs\u0131z a\u00e7\u0131k giri\u015f.",
      dayCloseNoOpenEntries: "A\u00e7\u0131k giri\u015f yok.",
      dayCloseAlertAt18: "G\u00fcn kapan\u0131\u015f\u0131 18:00: {count} \u00e7\u0131k\u0131\u015fs\u0131z a\u00e7\u0131k giri\u015f bulundu.",
      dayCloseCommentMin: "L\u00fctfen en az 4 karakter i\u00e7eren anlaml\u0131 bir yorum girin.",
      dayCloseAckSuccess: "G\u00fcn kapan\u0131\u015f\u0131 ba\u015far\u0131yla onaylan\u0131 ",
      turnstileSelectWorkerFirst: "L\u00fctfen \u00f6nce bir \u00e7al\u0131\u015fan se\u00e7in.",
      workerPhotoRequired: "L\u00fctfen \u00f6nce bir foto\u011fraf \u00e7ekin. Rozet yaln\u0131zca foto\u011frafla kaydedilebilir.",
      subcompanyNameRequired: "L\u00fctfen \u00f6nce firma ve alt firma ad\u0131n\u0131 girin.",
      cameraPermissionRetry: "Kamera eri\u015fimi engellendi. L\u00fctfen taray\u0131c\u0131da kamera eri\u015fimine izin verin ve Kameray\u0131 ba\u015flat\u2019a tekrar t\u0131klay\u0131n.",
      photoReadFailed: "Foto\u011fraf okunamad\u0131.",
      photoLoadFailed: "Foto\u011fraf y\u00fcklenemedi.",
      cameraStartFirst: "L\u00fctfen \u00f6nce kameray\u0131 ba\u015flat\u0131n.",
      photoProcessingUnavailable: "Foto\u011fraf i\u015fleme kullan\u0131lam\u0131yor.",
      workerBadgePinMissing: "L\u00fctfen \u00e7al\u0131\u015fan i\u00e7in bir Badge PIN ayarlay\u0131n.",
      visitorPurposeMissing: "L\u00fctfen ziyaret amac\u0131n\u0131 belirtin.",
      visitorCompanyMissing: "L\u00fctfen ziyaret\u00e7i firmas\u0131n\u0131 belirtin.",
      visitorHostMissing: "L\u00fctfen saha ileti\u015fim ki\u015fisini belirtin.",
      visitorEndMissing: "L\u00fctfen ziyaret biti\u015f tarihi ve saatini belirtin.",
      popupBlockedAllow: "A\u00e7\u0131l\u0131r pencere engellendi. L\u00fctfen a\u00e7\u0131l\u0131r pencerelere izin verin.",
      logoImageFileRequired: "L\u00fctfen logo i\u00e7in bir resim dosyas\u0131 se\u00e7in.",
      invoiceSentEmail: "Fatura e-postayla g\u00f6nderildi.",
      invoiceSavedEmailNotConfigured: "Fatura kaydedildi ancak e-posta yap\u0131land\u0131r\u0131lmam\u0131\u015f. L\u00fctfen Admin ayarlar\u0131nda SMTP\u2019yi yap\u0131land\u0131r\u0131n.",
      invoiceSelectCompany: "L\u00fctfen bir firma se\u00e7in.",
      invoiceRecipientInvalid: "L\u00fctfen ge\u00e7erli bir al\u0131c\u0131 e-postas\u0131 girin.",
      invoiceFormRequiredFields: "L\u00fctfen fatura tarihi, son \u00f6deme tarihi, hizmet d\u00f6nemi ve hizmet a\u00e7\u0131klamas\u0131n\u0131 doldurun.",
      invoiceMarkedPaid: "Fatura \u00f6dendi olarak i\u015faretlendi.",
      backendUnreachableReload: "Sunucuya eri\u015filemiyor. L\u00fctfen sunucuyu/a\u011f\u0131 kontrol edin ve sayfay\u0131 yenileyin.",
      loginResponseIncomplete: "Sunucudan gelen giri\u015f yan\u0131t\u0131 eksik. L\u00fctfen sayfay\u0131 yenileyin ve tekrar deneyin.",
      demoAdminOnly: "Yaln\u0131zca admin rolleri demo verileri y\u00fckleyebilir.",
      loginFirst: "L\u00fctfen \u00f6nce giri\u015f yap\u0131n.",
      porterOnSiteByCompanyHeading: "Firmaya g\u00f6re \u015fantiyedekiler",
      porterOnSiteHeading: "\u015eu anda \u015fantiyede",
      porterNoActiveCheckins: "Hen\u00fcz aktif giri\u015f yok.",
      porterTotal: "Toplam",
      porterPersonSingular: "ki\u015fi",
      porterPersonPlural: "ki\u015fi",
    },
    ar: {
      sessionLoggedIn: "تسجيل الدخول",
      sessionRole: "الدور",
      roleUnknown: "غير معروف",
      roleSuperadmin: "مشرف عام",
      roleCompanyAdmin: "مسؤول الشركة",
      roleTurnstile: "البوابة",
      statsWorkersTotal: "إجمالي الموظفين",
      statsWorkersActive: "الموظفون النشطون",
      statsVisitorsTotal: "إجمالي الزوار",
      statsCompanies: "الشركات",
      statsAccessToday: "في الموقع الآن",
      badgePinHintVisitor: "يستخدم الزوار الرابط/QR لمرة واحدة. لا يلزم وجود Badge PIN للزوار.",
      badgePinHintWorker: "يعمل تسجيل الدخول برمز الشارة في تطبيق العمال فقط مع Badge ID وهذا PIN. يمكنك تعيين PIN جديد هنا عند التحرير.",
      workerListEmpty: "لم يتم إضافة أي عمال بعد.",
      workerListNoResults: "لا توجد نتائج لـ \"{term}\".",
      recentAccessEmpty: "لا توجد حجوزات وصول بعد.",
      badgeEmptyStateShort: "يرجى إنشاء عامل أولاً.",
      badgeNoneSelected: "لم يتم اختيار بطاقة.",
      dayReportEmpty: "لا توجد بيانات للتقرير اليومي بعد.",
      hourlyEmpty: "لا توجد قيم بالساعة.",
      summaryEntries: "دخول",
      summaryExits: "خروج",
      summaryTotal: "المجموع",
      summaryLastBooking: "آخر حجز",
      summaryPeople: "زوار / عمال",
      hourlyIn: "دخول",
      hourlyOut: "خروج",
      cameraNotStarted: "لم يتم تشغيل الكاميرا بعد.",
      cameraUnavailableWithHint: "كاميرا المتصفح غير متاحة.{hint}",
      cameraHintSecureContext: " HTTPS أو localhost مطلوب.",
      cameraActiveCanCapture: "الكاميرا نشطة. يمكنك الآن التقاط صورة.",
      cameraNeedsHttps: "كاميرا المتصفح تتطلب HTTPS أو localhost.",
      cameraAccessBlocked: "تم حظر الوصول إلى الكاميرا. يرجى السماح بإذن الكاميرا في المتصفح.",
      cameraNotFound: "لم يتم العثور على كاميرا.",
      cameraInUse: "الكاميرا مستخدمة من قِبَل تطبيق أو علامة تبويب أخرى.",
      cameraConstraintFailed: "تعذّر تشغيل الكاميرا بالإعدادات المطلوبة.",
      cameraApiMissing: "هذا المتصفح لا يوفر واجهة برمجة كاميرا مباشرة.",
      cameraStartFailed: "تعذّر تشغيل الكاميرا: {reason}",
      photoCaptured: "تم التقاط الصورة ({preview})",
      photoPosition: "الموقع: X {x} | Y {y}",
      photoSharpenNormal: "عادي",
      photoSharpenSoft: "ناعم",
      photoSharpenVerySharp: "حاد جداً",
      photoRequiredOk: "تم التقاط الصورة. يمكن حفظ البطاقة.",
      photoRequiredMissing: "مطلوب: لا يمكن حفظ البطاقة بدون صورة.",
      bulkSelectedCount: "{count} محدد",
      photoWhiteBgActive: "الخلفية بيضاء كاملاً (نشط)",
      photoAdjustHelp: "بعد الالتقاط، حرّك الصورة لتناسب الجانب الأيمن من البطاقة.",
      photoZoomCropLabel: "تكبير / قطع",
      photoSharpenLabel: "الحدة:",
      bulkSelectAllLabel: "تحديد الكل",
      noSubcompanyOption: "بدون شركة فرعية",
      selectPersonOption: "يرجى اختيار شخص",
      visitorTagShort: "زائر",
      dashboardLastAccessPlaceholder: "سيظهر آخر دخول عند أول تسجيل.",
      dashboardLastAccessHeading: "آخر دخول",
      dashboardDirectionCheckin: "دخول",
      dashboardDirectionCheckout: "خروج",
      unknownPerson: "غير معروف",
      unknownCompany: "شركة غير معروفة",
      unknownTurnstile: "بوابة غير معروفة",
      accessFilterEmpty: "لا توجد حجوزات للفلتر المحدد.",
      dayCloseAutoClosedAfterMidnight: "تم الخروج تلقائياً بعد 00:00:",
      dayCloseAckTitle: "تم تأكيد إغلاق اليوم مسبقاً",
      dayCloseAckByOn: "بواسطة {user} في {when}",
      dayCloseCommentLabel: "تعليق: {comment}",
      dayCloseCheckActive: "فحص إغلاق اليوم نشط",
      dayCloseOpenEntriesNoExit: "{count} دخول مفتوح بدون خروج.",
      dayCloseNoOpenEntries: "لا توجد دخولات مفتوحة.",
      dayCloseAlertAt18: "إغلاق اليوم 18:00: تم العثور على {count} دخول مفتوح بدون خروج.",
      dayCloseCommentMin: "يرجى إدخال تعليق ذي معنى لا يقل عن 4 أحرف.",
      dayCloseAckSuccess: "تم تأكيد إغلاق اليوم بنجاح.",
      turnstileSelectWorkerFirst: "يرجى اختيار عامل أولاً.",
      workerPhotoRequired: "يرجى التقاط صورة أولاً. لا يمكن حفظ البطاقة بدون صورة.",
      subcompanyNameRequired: "يرجى تحديد الشركة واسم الشركة الفرعية أولاً.",
      cameraPermissionRetry: "تم حظر الوصول إلى الكاميرا. يرجى السماح بالوصول في المتصفح والنقر مجدداً على تشغيل الكاميرا.",
      photoReadFailed: "تعذّر قراءة الصورة.",
      photoLoadFailed: "تعذّر تحميل الصورة.",
      cameraStartFirst: "يرجى تشغيل الكاميرا أولاً.",
      photoProcessingUnavailable: "معالجة الصورة غير متاحة.",
      workerBadgePinMissing: "يرجى تعيين Badge PIN للعامل.",
      visitorPurposeMissing: "يرجى تحديد غرض الزيارة.",
      visitorCompanyMissing: "يرجى تحديد شركة الزائر.",
      visitorHostMissing: "يرجى تحديد جهة الاتصال في الموقع.",
      visitorEndMissing: "يرجى تحديد تاريخ ووقت نهاية الزيارة.",
      popupBlockedAllow: "النوافذ المنبثقة محظورة. يرجى السماح بالنوافذ المنبثقة.",
      logoImageFileRequired: "يرجى اختيار ملف صورة للشعار.",
      invoiceSentEmail: "تم إرسال الفاتورة بالبريد الإلكتروني.",
      invoiceSavedEmailNotConfigured: "تم حفظ الفاتورة لكن البريد الإلكتروني غير مكوّن. يرجى تكوين SMTP في إعدادات الإدارة.",
      invoiceSelectCompany: "يرجى اختيار شركة.",
      invoiceRecipientInvalid: "يرجى إدخال بريد إلكتروني صحيح للمستلم.",
      invoiceFormRequiredFields: "يرجى ملء تاريخ الفاتورة، تاريخ الاستحقاق، فترة الخدمة، وتوصيف الخدمة.",
      invoiceMarkedPaid: "تم تحديد الفاتورة كمدفوعة.",
      backendUnreachableReload: "تعذّر الوصول إلى الخادم. يرجى التحقق من الخادم/الشبكة وإعادة التحميل.",
      loginResponseIncomplete: "استجابة تسجيل الدخول من الخادم غير مكتملة. يرجى إعادة التحميل والمحاولة مجدداً.",
      demoAdminOnly: "يمكن لأدوار المشرف فقط تحميل البيانات التجريبية.",
      loginFirst: "يرجى تسجيل الدخول أولاً.",
      porterOnSiteByCompanyHeading: "على الموقع حسب الشركة",
      porterOnSiteHeading: "حاليًا في الموقع",
      porterNoActiveCheckins: "لا تسجيلات نشطة بعد.",
      porterTotal: "الإجمالي",
      porterPersonSingular: "شخص",
      porterPersonPlural: "أشخاص",
    },
    fr: {
      sessionLoggedIn: "Connecté",
      sessionRole: "Rôle",
      roleUnknown: "Inconnu",
      roleSuperadmin: "Superadmin",
      roleCompanyAdmin: "Admin entreprise",
      roleTurnstile: "Tourniquet",
      statsWorkersTotal: "Employés total",
      statsWorkersActive: "Employés actifs",
      statsVisitorsTotal: "Visiteurs total",
      statsCompanies: "Entreprises",
      statsAccessToday: "Actifs sur site",
      badgePinHintVisitor: "Les visiteurs utilisent le lien/QR à usage unique. Un Badge PIN n'est pas nécessaire pour les visiteurs.",
      badgePinHintWorker: "La connexion via badge dans l'app travailleurs fonctionne uniquement avec Badge ID et ce PIN. Vous pouvez définir un nouveau PIN ici lors de la modification.",
      workerListEmpty: "Aucun travailleur créé.",
      workerListNoResults: "Aucun résultat pour \"{term}\".",
      recentAccessEmpty: "Aucune réservation d'accès encore.",
      badgeEmptyStateShort: "Veuillez d'abord créer un travailleur.",
      badgeNoneSelected: "Aucun badge sélectionné.",
      dayReportEmpty: "Aucune donnée disponible pour le rapport journalier.",
      hourlyEmpty: "Aucune valeur horaire disponible.",
      summaryEntries: "Entrées",
      summaryExits: "Sorties",
      summaryTotal: "Total",
      summaryLastBooking: "Dernier enregistrement",
      summaryPeople: "Visiteurs / Travailleurs",
      hourlyIn: "Entrée",
      hourlyOut: "Sortie",
      cameraNotStarted: "Caméra non démarrée.",
      cameraUnavailableWithHint: "Caméra du navigateur indisponible.{hint}",
      cameraHintSecureContext: " HTTPS ou localhost requis.",
      cameraActiveCanCapture: "Caméra active. Vous pouvez prendre une photo.",
      cameraNeedsHttps: "La caméra du navigateur nécessite HTTPS ou localhost.",
      cameraAccessBlocked: "Accès caméra bloqué. Veuillez autoriser la caméra dans le navigateur.",
      cameraNotFound: "Aucune caméra trouvée.",
      cameraInUse: "La caméra est utilisée par une autre application ou onglet.",
      cameraConstraintFailed: "La caméra n'a pas pu démarrer avec les paramètres demandés.",
      cameraApiMissing: "Ce navigateur ne fournit pas d'API caméra en direct.",
      cameraStartFailed: "La caméra n'a pas pu démarrer : {reason}",
      photoCaptured: "Photo capturée ({preview})",
      photoPosition: "Position : X {x} | Y {y}",
      photoSharpenNormal: "Normal",
      photoSharpenSoft: "Doux",
      photoSharpenVerySharp: "Très net",
      photoRequiredOk: "Photo capturée. Le badge peut être sauvegardé.",
      photoRequiredMissing: "Requis : Sans photo, le badge ne peut pas être sauvegardé.",
      bulkSelectedCount: "{count} sélectionné(s)",
      photoWhiteBgActive: "Fond entièrement blanc (actif)",
      photoAdjustHelp: "Déplacez la photo après la capture pour qu'elle s'intègre proprement dans le badge.",
      photoZoomCropLabel: "Zoom / Recadrer",
      photoSharpenLabel: "Netteté :",
      bulkSelectAllLabel: "Tout sélectionner",
      noSubcompanyOption: "Pas de sous-entreprise",
      selectPersonOption: "Veuillez sélectionner une personne",
      visitorTagShort: "Visiteur",
      dashboardLastAccessPlaceholder: "Le dernier accès s'affichera ici lors du premier enregistrement.",
      dashboardLastAccessHeading: "Dernier accès",
      dashboardDirectionCheckin: "Entrée",
      dashboardDirectionCheckout: "Sortie",
      unknownPerson: "Inconnu",
      unknownCompany: "Entreprise inconnue",
      unknownTurnstile: "Tourniquet inconnu",
      accessFilterEmpty: "Aucune réservation d'accès pour le filtre sélectionné.",
      dayCloseAutoClosedAfterMidnight: "Clôturé automatiquement après 00:00 :",
      dayCloseAckTitle: "Clôture journalière déjà confirmée",
      dayCloseAckByOn: "Par {user} le {when}",
      dayCloseCommentLabel: "Commentaire : {comment}",
      dayCloseCheckActive: "Vérification de clôture journalière active",
      dayCloseOpenEntriesNoExit: "{count} entrée(s) ouverte(s) sans sortie.",
      dayCloseNoOpenEntries: "Aucune entrée ouverte.",
      dayCloseAlertAt18: "Clôture journalière 18h00 : {count} entrée(s) ouverte(s) sans sortie.",
      dayCloseCommentMin: "Veuillez saisir un commentaire significatif d'au moins 4 caractères.",
      dayCloseAckSuccess: "Clôture journalière confirmée avec succès.",
      turnstileSelectWorkerFirst: "Veuillez d'abord sélectionner un travailleur.",
      workerPhotoRequired: "Veuillez d'abord prendre une photo. Le badge ne peut être sauvegardé qu'avec une photo.",
      subcompanyNameRequired: "Veuillez d'abord sélectionner l'entreprise et le nom de la sous-entreprise.",
      cameraPermissionRetry: "Accès caméra bloqué. Veuillez autoriser l'accès dans le navigateur et cliquer à nouveau sur Démarrer caméra.",
      photoReadFailed: "La photo n'a pas pu être lue.",
      photoLoadFailed: "La photo n'a pas pu être chargée.",
      cameraStartFirst: "Veuillez d'abord démarrer la caméra.",
      photoProcessingUnavailable: "Traitement photo indisponible.",
      workerBadgePinMissing: "Veuillez définir un Badge PIN pour le travailleur.",
      visitorPurposeMissing: "Veuillez indiquer l'objet de la visite.",
      visitorCompanyMissing: "Veuillez indiquer l'entreprise du visiteur.",
      visitorHostMissing: "Veuillez indiquer le contact sur site.",
      visitorEndMissing: "Veuillez indiquer la date et l'heure de fin de visite.",
      popupBlockedAllow: "Fenêtre contextuelle bloquée. Veuillez autoriser les popups.",
      logoImageFileRequired: "Veuillez sélectionner un fichier image pour le logo.",
      invoiceSentEmail: "Facture envoyée par e-mail.",
      invoiceSavedEmailNotConfigured: "Facture sauvegardée, mais l'e-mail n'est pas configuré. Veuillez configurer SMTP dans les paramètres Admin.",
      invoiceSelectCompany: "Veuillez sélectionner une entreprise.",
      invoiceRecipientInvalid: "Veuillez saisir un e-mail destinataire valide.",
      invoiceFormRequiredFields: "Veuillez remplir la date de facture, l'échéance, la période de service et la description.",
      invoiceMarkedPaid: "Facture marquée comme payée.",
      backendUnreachableReload: "Serveur inaccessible. Veuillez vérifier le serveur/réseau et recharger.",
      loginResponseIncomplete: "La réponse de connexion du serveur est incomplète. Veuillez recharger et réessayer.",
      demoAdminOnly: "Seuls les rôles admin peuvent charger les données de démo.",
      loginFirst: "Veuillez d'abord vous connecter.",
      porterOnSiteByCompanyHeading: "Sur site par entreprise",
      porterOnSiteHeading: "Actuellement sur site",
      porterNoActiveCheckins: "Aucune entr\u00e9e active pour l'instant.",
      porterTotal: "Total",
      porterPersonSingular: "personne",
      porterPersonPlural: "personnes",
    },
    es: {
      sessionLoggedIn: "Conectado",
      sessionRole: "Rol",
      roleUnknown: "Desconocido",
      roleSuperadmin: "Superadmin",
      roleCompanyAdmin: "Admin de empresa",
      roleTurnstile: "Torno",
      statsWorkersTotal: "Trabajadores total",
      statsWorkersActive: "Trabajadores activos",
      statsVisitorsTotal: "Visitantes total",
      statsCompanies: "Empresas",
      statsAccessToday: "Activos en obra",
      badgePinHintVisitor: "Los visitantes usan el enlace/QR de un solo uso. No se requiere Badge PIN para visitantes.",
      badgePinHintWorker: "El inicio de sesión en la app de trabajadores solo funciona con Badge ID y este PIN. Puede establecer un nuevo PIN aquí al editar.",
      workerListEmpty: "No hay trabajadores creados aún.",
      workerListNoResults: "Sin resultados para \"{term}\".",
      recentAccessEmpty: "Aún no hay registros de acceso.",
      badgeEmptyStateShort: "Por favor cree un trabajador primero.",
      badgeNoneSelected: "Ningún badge seleccionado.",
      dayReportEmpty: "Sin datos para el informe diario aún.",
      hourlyEmpty: "Sin valores por hora disponibles.",
      summaryEntries: "Entradas",
      summaryExits: "Salidas",
      summaryTotal: "Total",
      summaryLastBooking: "Última reserva",
      summaryPeople: "Visitantes / Trabajadores",
      hourlyIn: "Entrada",
      hourlyOut: "Salida",
      cameraNotStarted: "Cámara no iniciada.",
      cameraUnavailableWithHint: "Cámara del navegador no disponible.{hint}",
      cameraHintSecureContext: " Se requiere HTTPS o localhost.",
      cameraActiveCanCapture: "Cámara activa. Puede tomar una foto ahora.",
      cameraNeedsHttps: "La cámara del navegador requiere HTTPS o localhost.",
      cameraAccessBlocked: "Acceso a cámara bloqueado. Por favor permita el acceso en el navegador.",
      cameraNotFound: "No se encontró cámara.",
      cameraInUse: "La cámara está en uso por otra aplicación o pestaña.",
      cameraConstraintFailed: "La cámara no pudo iniciarse con la configuración solicitada.",
      cameraApiMissing: "Este navegador no proporciona API de cámara en vivo.",
      cameraStartFailed: "La cámara no pudo iniciarse: {reason}",
      photoCaptured: "Foto capturada ({preview})",
      photoPosition: "Posición: X {x} | Y {y}",
      photoSharpenNormal: "Normal",
      photoSharpenSoft: "Suave",
      photoSharpenVerySharp: "Muy nítido",
      photoRequiredOk: "Foto capturada. El badge puede guardarse.",
      photoRequiredMissing: "Obligatorio: Sin foto no se puede guardar el badge.",
      bulkSelectedCount: "{count} seleccionado(s)",
      photoWhiteBgActive: "Fondo completamente blanco (activo)",
      photoAdjustHelp: "Mueva la foto después de capturarla para que encaje bien en el badge.",
      photoZoomCropLabel: "Zoom / Recortar",
      photoSharpenLabel: "Nitidez:",
      bulkSelectAllLabel: "Seleccionar todo",
      noSubcompanyOption: "Sin subempresa",
      selectPersonOption: "Por favor seleccione una persona",
      visitorTagShort: "Visitante",
      dashboardLastAccessPlaceholder: "El último acceso se mostrará con el primer registro.",
      dashboardLastAccessHeading: "Último acceso",
      dashboardDirectionCheckin: "Entrada",
      dashboardDirectionCheckout: "Salida",
      unknownPerson: "Desconocido",
      unknownCompany: "Empresa desconocida",
      unknownTurnstile: "Torno desconocido",
      accessFilterEmpty: "No hay reservas de acceso para el filtro seleccionado.",
      dayCloseAutoClosedAfterMidnight: "Cerrado automáticamente después de las 00:00:",
      dayCloseAckTitle: "Cierre diario ya confirmado",
      dayCloseAckByOn: "Por {user} el {when}",
      dayCloseCommentLabel: "Comentario: {comment}",
      dayCloseCheckActive: "Verificación de cierre diario activa",
      dayCloseOpenEntriesNoExit: "{count} entrada(s) abierta(s) sin salida.",
      dayCloseNoOpenEntries: "Sin entradas abiertas.",
      dayCloseAlertAt18: "Cierre diario 18:00: {count} entrada(s) abierta(s) sin salida encontrada(s).",
      dayCloseCommentMin: "Por favor ingrese un comentario significativo de al menos 4 caracteres.",
      dayCloseAckSuccess: "Cierre diario confirmado exitosamente.",
      turnstileSelectWorkerFirst: "Por favor seleccione un trabajador primero.",
      workerPhotoRequired: "Por favor tome una foto primero. El badge solo puede guardarse con foto.",
      subcompanyNameRequired: "Por favor seleccione empresa y nombre de subempresa primero.",
      cameraPermissionRetry: "Acceso a cámara bloqueado. Permita el acceso en el navegador y haga clic en Iniciar cámara nuevamente.",
      photoReadFailed: "No se pudo leer la foto.",
      photoLoadFailed: "No se pudo cargar la foto.",
      cameraStartFirst: "Por favor inicie la cámara primero.",
      photoProcessingUnavailable: "Procesamiento de fotos no disponible.",
      workerBadgePinMissing: "Por favor establezca un Badge PIN para el trabajador.",
      visitorPurposeMissing: "Por favor indique el propósito de la visita.",
      visitorCompanyMissing: "Por favor indique la empresa del visitante.",
      visitorHostMissing: "Por favor indique el contacto en sitio.",
      visitorEndMissing: "Por favor indique la fecha y hora de fin de visita.",
      popupBlockedAllow: "Ventana emergente bloqueada. Por favor permita las ventanas emergentes.",
      logoImageFileRequired: "Por favor seleccione un archivo de imagen para el logo.",
      invoiceSentEmail: "Factura enviada por correo electrónico.",
      invoiceSavedEmailNotConfigured: "Factura guardada, pero el correo no está configurado. Configure SMTP en los ajustes de Admin.",
      invoiceSelectCompany: "Por favor seleccione una empresa.",
      invoiceRecipientInvalid: "Por favor ingrese un correo de destinatario válido.",
      invoiceFormRequiredFields: "Complete la fecha de factura, vencimiento, período de servicio y descripción.",
      invoiceMarkedPaid: "Factura marcada como pagada.",
      backendUnreachableReload: "Backend inaccesible. Verifique el servidor/red y recargue.",
      loginResponseIncomplete: "La respuesta de inicio de sesión del servidor está incompleta. Recargue e intente de nuevo.",
      demoAdminOnly: "Solo los roles de admin pueden cargar datos de demo.",
      loginFirst: "Por favor inicie sesión primero.",
      porterOnSiteByCompanyHeading: "En obra por empresa",
      porterOnSiteHeading: "Actualmente en obra",
      porterNoActiveCheckins: "Aún no hay entradas activas.",
      porterTotal: "Total",
      porterPersonSingular: "persona",
      porterPersonPlural: "personas",
    },
    it: {
      sessionLoggedIn: "Accesso effettuato",
      sessionRole: "Ruolo",
      roleUnknown: "Sconosciuto",
      roleSuperadmin: "Superadmin",
      roleCompanyAdmin: "Admin azienda",
      roleTurnstile: "Tornello",
      statsWorkersTotal: "Lavoratori totali",
      statsWorkersActive: "Lavoratori attivi",
      statsVisitorsTotal: "Visitatori totali",
      statsCompanies: "Aziende",
      statsAccessToday: "Attivi in cantiere",
      badgePinHintVisitor: "I visitatori utilizzano il link/QR monouso. Un Badge PIN non è necessario per i visitatori.",
      badgePinHintWorker: "L'accesso tramite badge nell'app lavoratori funziona solo con Badge ID e questo PIN. È possibile impostare un nuovo PIN qui durante la modifica.",
      workerListEmpty: "Nessun lavoratore creato.",
      workerListNoResults: "Nessun risultato per \"{term}\".",
      recentAccessEmpty: "Nessuna prenotazione di accesso ancora.",
      badgeEmptyStateShort: "Creare prima un lavoratore.",
      badgeNoneSelected: "Nessun badge selezionato.",
      dayReportEmpty: "Nessun dato disponibile per il rapporto giornaliero.",
      hourlyEmpty: "Nessun valore orario disponibile.",
      summaryEntries: "Ingressi",
      summaryExits: "Uscite",
      summaryTotal: "Totale",
      summaryLastBooking: "Ultima prenotazione",
      summaryPeople: "Visitatori / Lavoratori",
      hourlyIn: "Ingresso",
      hourlyOut: "Uscita",
      cameraNotStarted: "Telecamera non avviata.",
      cameraUnavailableWithHint: "Telecamera del browser non disponibile.{hint}",
      cameraHintSecureContext: " HTTPS o localhost richiesto.",
      cameraActiveCanCapture: "Telecamera attiva. Ora puoi scattare una foto.",
      cameraNeedsHttps: "La telecamera del browser richiede HTTPS o localhost.",
      cameraAccessBlocked: "Accesso telecamera bloccato. Consentire l'accesso nel browser.",
      cameraNotFound: "Nessuna telecamera trovata.",
      cameraInUse: "La telecamera è già in uso da un'altra app o scheda.",
      cameraConstraintFailed: "La telecamera non ha potuto avviarsi con le impostazioni richieste.",
      cameraApiMissing: "Questo browser non fornisce un'API telecamera live.",
      cameraStartFailed: "La telecamera non ha potuto avviarsi: {reason}",
      photoCaptured: "Foto acquisita ({preview})",
      photoPosition: "Posizione: X {x} | Y {y}",
      photoSharpenNormal: "Normale",
      photoSharpenSoft: "Morbido",
      photoSharpenVerySharp: "Molto nitido",
      photoRequiredOk: "Foto acquisita. Il badge può essere salvato.",
      photoRequiredMissing: "Obbligatorio: Senza foto il badge non può essere salvato.",
      bulkSelectedCount: "{count} selezionato/i",
      photoWhiteBgActive: "Sfondo completamente bianco (attivo)",
      photoAdjustHelp: "Sposta la foto dopo l'acquisizione per adattarla al lato destro del badge.",
      photoZoomCropLabel: "Zoom / Ritaglia",
      photoSharpenLabel: "Nitidezza:",
      bulkSelectAllLabel: "Seleziona tutto",
      noSubcompanyOption: "Nessuna sottosocietà",
      selectPersonOption: "Selezionare una persona",
      visitorTagShort: "Visitatore",
      dashboardLastAccessPlaceholder: "L'ultimo accesso sarà mostrato al primo check-in o check-out.",
      dashboardLastAccessHeading: "Ultimo accesso",
      dashboardDirectionCheckin: "Ingresso",
      dashboardDirectionCheckout: "Uscita",
      unknownPerson: "Sconosciuto",
      unknownCompany: "Azienda sconosciuta",
      unknownTurnstile: "Tornello sconosciuto",
      accessFilterEmpty: "Nessuna prenotazione di accesso per il filtro selezionato.",
      dayCloseAutoClosedAfterMidnight: "Uscita automatica dopo le 00:00:",
      dayCloseAckTitle: "Chiusura giornaliera già confermata",
      dayCloseAckByOn: "Da {user} il {when}",
      dayCloseCommentLabel: "Commento: {comment}",
      dayCloseCheckActive: "Verifica chiusura giornaliera attiva",
      dayCloseOpenEntriesNoExit: "{count} ingresso/i aperto/i senza uscita.",
      dayCloseNoOpenEntries: "Nessun ingresso aperto.",
      dayCloseAlertAt18: "Chiusura giornaliera 18:00: {count} ingresso/i aperto/i senza uscita.",
      dayCloseCommentMin: "Inserire un commento significativo di almeno 4 caratteri.",
      dayCloseAckSuccess: "Chiusura giornaliera confermata con successo.",
      turnstileSelectWorkerFirst: "Selezionare prima un lavoratore.",
      workerPhotoRequired: "Scattare prima una foto. Il badge può essere salvato solo con foto.",
      subcompanyNameRequired: "Selezionare prima azienda e nome sottosocietà.",
      cameraPermissionRetry: "Accesso telecamera bloccato. Consentire l'accesso nel browser e fare clic su Avvia telecamera.",
      photoReadFailed: "Impossibile leggere la foto.",
      photoLoadFailed: "Impossibile caricare la foto.",
      cameraStartFirst: "Avviare prima la telecamera.",
      photoProcessingUnavailable: "Elaborazione foto non disponibile.",
      workerBadgePinMissing: "Impostare un Badge PIN per il lavoratore.",
      visitorPurposeMissing: "Indicare lo scopo della visita.",
      visitorCompanyMissing: "Indicare l'azienda del visitatore.",
      visitorHostMissing: "Indicare il contatto in loco.",
      visitorEndMissing: "Indicare la data e l'ora di fine visita.",
      popupBlockedAllow: "Popup bloccato. Consentire i popup.",
      logoImageFileRequired: "Selezionare un file immagine per il logo.",
      invoiceSentEmail: "Fattura inviata via email.",
      invoiceSavedEmailNotConfigured: "Fattura salvata, ma l'email non è configurata. Configurare SMTP nelle impostazioni Admin.",
      invoiceSelectCompany: "Selezionare un'azienda.",
      invoiceRecipientInvalid: "Inserire un'email destinatario valida.",
      invoiceFormRequiredFields: "Compilare data fattura, scadenza, periodo di servizio e descrizione.",
      invoiceMarkedPaid: "Fattura contrassegnata come pagata.",
      backendUnreachableReload: "Backend irraggiungibile. Verificare il server/rete e ricaricare.",
      loginResponseIncomplete: "La risposta di accesso dal server è incompleta. Ricaricare e riprovare.",
      demoAdminOnly: "Solo i ruoli admin possono caricare i dati demo.",
      loginFirst: "Accedere prima.",
      porterOnSiteByCompanyHeading: "In cantiere per azienda",
      porterOnSiteHeading: "Attualmente in cantiere",
      porterNoActiveCheckins: "Nessun ingresso attivo al momento.",
      porterTotal: "Totale",
      porterPersonSingular: "persona",
      porterPersonPlural: "persone",
    },
    pl: {
      sessionLoggedIn: "Zalogowany",
      sessionRole: "Rola",
      roleUnknown: "Nieznana",
      roleSuperadmin: "Superadmin",
      roleCompanyAdmin: "Admin firmy",
      roleTurnstile: "Bramka",
      statsWorkersTotal: "Pracownicy łącznie",
      statsWorkersActive: "Aktywni pracownicy",
      statsVisitorsTotal: "Goście łącznie",
      statsCompanies: "Firmy",
      statsAccessToday: "Aktywni na budowie",
      badgePinHintVisitor: "Odwiedzający używają jednorazowego linku/QR. PIN Badge nie jest wymagany dla odwiedzających.",
      badgePinHintWorker: "Logowanie przez badge w aplikacji pracownika działa tylko z Badge ID i tym PIN. Możesz ustawić nowy PIN tutaj podczas edycji.",
      workerListEmpty: "Nie dodano jeszcze pracowników.",
      workerListNoResults: "Brak wyników dla \"{term}\".",
      recentAccessEmpty: "Brak jeszcze rezerwacji dostępu.",
      badgeEmptyStateShort: "Najpierw utwórz pracownika.",
      badgeNoneSelected: "Nie wybrano odznaki.",
      dayReportEmpty: "Brak danych do raportu dziennego.",
      hourlyEmpty: "Brak wartości godzinowych.",
      summaryEntries: "Wejścia",
      summaryExits: "Wyjścia",
      summaryTotal: "Suma",
      summaryLastBooking: "Ostatnia rezerwacja",
      summaryPeople: "Odwiedzający / Pracownicy",
      hourlyIn: "Wejście",
      hourlyOut: "Wyjście",
      cameraNotStarted: "Kamera nie została uruchomiona.",
      cameraUnavailableWithHint: "Kamera przeglądarki niedostępna.{hint}",
      cameraHintSecureContext: " Wymagany HTTPS lub localhost.",
      cameraActiveCanCapture: "Kamera aktywna. Możesz teraz zrobić zdjęcie.",
      cameraNeedsHttps: "Kamera przeglądarki wymaga HTTPS lub localhost.",
      cameraAccessBlocked: "Dostęp do kamery zablokowany. Zezwól na uprawnienia kamery w przeglądarce.",
      cameraNotFound: "Nie znaleziono kamery.",
      cameraInUse: "Kamera jest już używana przez inną aplikację lub zakładkę.",
      cameraConstraintFailed: "Kamera nie mogła uruchomić się z żądanymi ustawieniami.",
      cameraApiMissing: "Ta przeglądarka nie udostępnia API kamery na żywo.",
      cameraStartFailed: "Kamera nie mogła się uruchomić: {reason}",
      photoCaptured: "Zdjęcie zrobione ({preview})",
      photoPosition: "Pozycja: X {x} | Y {y}",
      photoSharpenNormal: "Normalny",
      photoSharpenSoft: "Miękki",
      photoSharpenVerySharp: "Bardzo ostry",
      photoRequiredOk: "Zdjęcie zrobione. Odznaka może być zapisana.",
      photoRequiredMissing: "Wymagane: Bez zdjęcia odznaka nie może być zapisana.",
      bulkSelectedCount: "{count} wybranych",
      photoWhiteBgActive: "Tło całkowicie białe (aktywne)",
      photoAdjustHelp: "Po zrobieniu zdjęcia przesuń je tak, aby pasowało do prawej strony odznaki.",
      photoZoomCropLabel: "Zoom / Kadrowanie",
      photoSharpenLabel: "Ostrość:",
      bulkSelectAllLabel: "Wybierz wszystko",
      noSubcompanyOption: "Brak podmiotu",
      selectPersonOption: "Wybierz osobę",
      visitorTagShort: "Odwiedzający",
      dashboardLastAccessPlaceholder: "Ostatni dostęp pojawi się po pierwszym logowaniu.",
      dashboardLastAccessHeading: "Ostatni dostęp",
      dashboardDirectionCheckin: "Wejście",
      dashboardDirectionCheckout: "Wyjście",
      unknownPerson: "Nieznany",
      unknownCompany: "Nieznana firma",
      unknownTurnstile: "Nieznana bramka",
      accessFilterEmpty: "Brak rezerwacji dostępu dla wybranego filtra.",
      dayCloseAutoClosedAfterMidnight: "Automatycznie wylogowano po 00:00:",
      dayCloseAckTitle: "Zamknięcie dnia już potwierdzone",
      dayCloseAckByOn: "Przez {user} dnia {when}",
      dayCloseCommentLabel: "Komentarz: {comment}",
      dayCloseCheckActive: "Kontrola zamknięcia dnia aktywna",
      dayCloseOpenEntriesNoExit: "{count} otwarte wejścia bez wyjścia.",
      dayCloseNoOpenEntries: "Brak otwartych wejść.",
      dayCloseAlertAt18: "Zamknięcie dnia 18:00: znaleziono {count} otwarte wejścia bez wyjścia.",
      dayCloseCommentMin: "Wprowadź istotny komentarz z co najmniej 4 znakami.",
      dayCloseAckSuccess: "Zamknięcie dnia zostało pomyślnie potwierdzone.",
      turnstileSelectWorkerFirst: "Najpierw wybierz pracownika.",
      workerPhotoRequired: "Najpierw zrób zdjęcie. Odznaka może być zapisana tylko ze zdjęciem.",
      subcompanyNameRequired: "Najpierw wybierz firmę i nazwę podmiotu.",
      cameraPermissionRetry: "Dostęp do kamery zablokowany. Zezwól na dostęp w przeglądarce i kliknij Uruchom kamerę ponownie.",
      photoReadFailed: "Nie można było odczytać zdjęcia.",
      photoLoadFailed: "Nie można było załadować zdjęcia.",
      cameraStartFirst: "Najpierw uruchom kamerę.",
      photoProcessingUnavailable: "Przetwarzanie zdjęć niedostępne.",
      workerBadgePinMissing: "Ustaw PIN Badge dla pracownika.",
      visitorPurposeMissing: "Podaj cel wizyty.",
      visitorCompanyMissing: "Podaj firmę odwiedzającego.",
      visitorHostMissing: "Podaj osobę kontaktową na miejscu.",
      visitorEndMissing: "Podaj datę i godzinę końca wizyty.",
      popupBlockedAllow: "Popup zablokowany. Zezwól na popupy.",
      logoImageFileRequired: "Wybierz plik obrazu dla logo.",
      invoiceSentEmail: "Faktura wysłana emailem.",
      invoiceSavedEmailNotConfigured: "Faktura zapisana, ale email nie jest skonfigurowany. Skonfiguruj SMTP w ustawieniach administratora.",
      invoiceSelectCompany: "Wybierz firmę.",
      invoiceRecipientInvalid: "Wprowadź prawidłowy email odbiorcy.",
      invoiceFormRequiredFields: "Wypełnij datę faktury, termin płatności, okres usługi i opis usługi.",
      invoiceMarkedPaid: "Faktura oznaczona jako zapłacona.",
      backendUnreachableReload: "Backend niedostępny. Sprawdź serwer/sieć i odśwież stronę.",
      loginResponseIncomplete: "Odpowiedź logowania z serwera jest niepełna. Odśwież stronę i spróbuj ponownie.",
      demoAdminOnly: "Tylko role adminów mogą ładować dane demo.",
      loginFirst: "Najpierw się zaloguj.",
      porterOnSiteByCompanyHeading: "Na budowie według firmy",
      porterOnSiteHeading: "Aktualnie na budowie",
      porterNoActiveCheckins: "Brak aktywnych wejść.",
      porterTotal: "Łącznie",
      porterPersonSingular: "osoba",
      porterPersonPlural: "osoby",
    },
  };
  return {
    ...base,
    ...(map[lang] || map.de),
  };
}

function runtimeText(key) {
  const texts = getRuntimeUiTexts();
  return texts[key] || "";
}

function runtimeTextTemplate(key, values = {}) {
  let template = runtimeText(key);
  Object.entries(values).forEach(([token, value]) => {
    template = template.replace(new RegExp(`\\{${token}\\}`, "g"), String(value));
  });
  return template;
}

function applyRuntimeUiTexts() {
  const cameraPlaceholder = document.querySelector("#cameraPlaceholder");
  const photoDebugText = document.querySelector("#photoDebugText");
  const photoWhiteBgLabel = document.querySelector("#photoWhiteBgLabel");
  const photoAdjustHelp = document.querySelector("#photoAdjustHelp");
  const photoZoomCropLabel = document.querySelector("#photoZoomCropLabel");
  const photoSharpenLabel = document.querySelector("#photoSharpenLabel");
  const photoRequiredHint = document.querySelector("#photoRequiredHint");
  const photoAdjustStatus = document.querySelector("#photoAdjustStatus");
  const badgePinHint = document.querySelector("#badgePinHint");
  const bulkSelectAllText = document.querySelector("#bulkSelectAllText");

  if (cameraPlaceholder && !cameraPlaceholder.hidden) {
    cameraPlaceholder.textContent = runtimeText("cameraNotStarted");
  }
  if (photoDebugText) {
    const current = (photoDebugText.textContent || "").trim();
    const defaultDe = "Kamera noch nicht gestartet.";
    const defaultEn = "Camera not started.";
    if (!current || current === defaultDe || current === defaultEn) {
      photoDebugText.textContent = runtimeText("cameraNotStarted");
    }
  }
  if (photoWhiteBgLabel) photoWhiteBgLabel.textContent = runtimeText("photoWhiteBgActive");
  if (photoAdjustHelp) photoAdjustHelp.textContent = runtimeText("photoAdjustHelp");
  if (photoZoomCropLabel) photoZoomCropLabel.textContent = runtimeText("photoZoomCropLabel");
  if (photoSharpenLabel) photoSharpenLabel.textContent = runtimeText("photoSharpenLabel");
  if (photoRequiredHint && photoRequiredHint.classList.contains("helper-text-warning")) {
    photoRequiredHint.textContent = runtimeText("photoRequiredMissing");
  }
  if (photoAdjustStatus) {
    const current = (photoAdjustStatus.textContent || "").trim();
    if (!current || current.startsWith("Position:")) {
      photoAdjustStatus.textContent = runtimeTextTemplate("photoPosition", { x: 0, y: 0 });
    }
  }
  if (badgePinHint) {
    const workerType = document.querySelector("#workerType")?.value || "worker";
    badgePinHint.textContent = workerType === "visitor"
      ? runtimeText("badgePinHintVisitor")
      : runtimeText("badgePinHintWorker");
  }
  if (bulkSelectAllText) bulkSelectAllText.textContent = runtimeText("bulkSelectAllLabel");
}

function getRoleLabel(role) {
  const texts = getRuntimeUiTexts();
  const normalized = String(role || "").toLowerCase();
  if (normalized === "superadmin") return texts.roleSuperadmin;
  if (normalized === "company-admin") return texts.roleCompanyAdmin;
  if (normalized === "turnstile") return texts.roleTurnstile;
  return normalized || texts.roleUnknown;
}

function isSupportReadOnlyMode() {
  return Boolean(state.currentUser?.support_read_only);
}

function showSupportReadOnlyAlert() {
  window.alert(uiT("supportReadOnlyAlert"));
}

function updateLoginOtpVisibility() {
  const otpLabel = elements.loginOtpCode?.closest("label");
  if (!otpLabel) {
    return;
  }
  const scope = String(elements.loginScope?.value || "auto").trim().toLowerCase();
  const hideForTurnstile = scope === "turnstile";
  // Show OTP field only after credentials were verified and OTP was sent (2-step)
  const showOtp = !hideForTurnstile && state.loginOtpPending;
  otpLabel.style.display = showOtp ? "" : "none";
  if (!showOtp && elements.loginOtpCode) {
    elements.loginOtpCode.value = "";
  }
}

function syncSupportLoginUi() {
  const context = state.supportLoginContext || loadSupportLoginContext();
  state.supportLoginContext = context;
  updateLoginOtpVisibility();
  if (context?.companyId) {
    persistSupportLoginContext(context);
    try {
      const url = new URL(window.location.href);
      if (url.searchParams.has("supportCompanyId")) {
        url.searchParams.delete("supportCompanyId");
        url.searchParams.delete("supportCompanyName");
        url.searchParams.delete("supportActorName");
        window.history.replaceState({}, document.title, url.toString());
      }
    } catch {
      // ignore history update failures
    }
  }
  if (elements.loginSupportNotice) {
    if (context?.companyId) {
      const actorText = context.actorName ? ` ${escapeHtml(uiT("supportStartedBy"))} ${escapeHtml(context.actorName)}` : "";
      elements.loginSupportNotice.innerHTML = `<strong>${escapeHtml(uiT("supportLoginActive"))}</strong> ${escapeHtml(context.companyName || uiT("supportCompanyFallback"))}${actorText}. ${escapeHtml(uiT("supportReadOnlyNotice"))}`;
      elements.loginSupportNotice.style.display = "block";
    } else {
      elements.loginSupportNotice.innerHTML = "";
      elements.loginSupportNotice.style.display = "none";
    }
  }
  if (!token && context?.companyId && elements.loginScope) {
    elements.loginScope.value = "company-admin";
  }
}

function focusLoginInput({ force = false } = {}) {
  if (!elements.authOverlay || !elements.loginUsername || !elements.loginPassword) {
    return;
  }
  if (elements.authOverlay.getAttribute("aria-hidden") === "true") {
    return;
  }

  const now = Date.now();
  if (!force && now - lastLoginFocusAt < 350) {
    return;
  }
  lastLoginFocusAt = now;

  window.requestAnimationFrame(() => {
    const hasUsername = Boolean(String(elements.loginUsername.value || "").trim());
    const target = hasUsername ? elements.loginPassword : elements.loginUsername;
    target.classList.remove("login-focus-pulse");
    // Reflow ensures the pulse animation can restart on repeated focus actions.
    void target.offsetWidth;
    target.classList.add("login-focus-pulse");
    target.focus({ preventScroll: true });
    target.select?.();
    window.setTimeout(() => {
      target.classList.remove("login-focus-pulse");
    }, 850);
  });
}

function applySupportReadOnlyUiState() {
  const readOnly = isSupportReadOnlyMode();
  const selectors = [
    "#workerForm input, #workerForm select, #workerForm textarea, #workerForm button",
    "#companyForm input, #companyForm select, #companyForm textarea, #companyForm button",
    "#settingsForm input, #settingsForm select, #settingsForm textarea, #settingsForm button",
    "#invoiceForm input, #invoiceForm select, #invoiceForm textarea, #invoiceForm button",
    "#accessForm input, #accessForm select, #accessForm textarea, #accessForm button",
    "#workerCsvButton, #accessCsvButton, #auditCsvButton",
    "#docInboxSyncBtn, #docInboxRematchBtn, #imapTestBtn",
    "[data-assign-btn], [data-dismiss-email-id], [data-manual-company-match], [data-delete-doc-id]",
    ".worker-doc-upload-form input, .worker-doc-upload-form select, .worker-doc-upload-form textarea, .worker-doc-upload-form button",
    "#docAssignForm input, #docAssignForm select, #docAssignForm textarea, #docAssignForm button",
    "#docCompanyMatchForm input, #docCompanyMatchForm select, #docCompanyMatchForm textarea, #docCompanyMatchForm button",
    "[data-worker-edit], [data-worker-delete], [data-worker-restore], [data-worker-app-link], [data-worker-reset-pin]",
    "[data-company-doc-email], [data-company-otp-setup], [data-company-add-turnstile], [data-company-repair], [data-company-toggle-lock], [data-company-delete]",
    "[data-collections-mark-paid], [data-collections-toggle-lock]"
  ];

  selectors.forEach((selector) => {
    document.querySelectorAll(selector).forEach((element) => {
      if (!(element instanceof HTMLButtonElement || element instanceof HTMLInputElement || element instanceof HTMLSelectElement || element instanceof HTMLTextAreaElement)) {
        return;
      }
      if (readOnly) {
        if (!element.dataset.supportReadOnlyOriginalTitle) {
          element.dataset.supportReadOnlyOriginalTitle = element.getAttribute("title") || "";
        }
        if (element.dataset.supportReadOnlyOriginalDisabled === undefined) {
          element.dataset.supportReadOnlyOriginalDisabled = element.disabled ? "1" : "0";
        }
        element.disabled = true;
        element.setAttribute("title", uiT("supportReadOnlyTitle"));
      } else if (element.dataset.supportReadOnlyOriginalTitle !== undefined) {
        element.disabled = element.dataset.supportReadOnlyOriginalDisabled === "1";
        element.setAttribute("title", element.dataset.supportReadOnlyOriginalTitle);
        delete element.dataset.supportReadOnlyOriginalTitle;
        delete element.dataset.supportReadOnlyOriginalDisabled;
      }
    });
  });
}

function userCanManageSystem() {
  const role = getEffectiveUiRole();
  return role === "superadmin" && !isSupportReadOnlyMode() && !isSuperadminCompanyPreviewMode();
}

function userCanManageWorkers() {
  const role = getEffectiveUiRole();
  return (role === "superadmin" || role === "company-admin") && !isSupportReadOnlyMode() && !isSuperadminCompanyPreviewMode();
}

function userCanManageAccess() {
  const role = getEffectiveUiRole();
  return (role === "superadmin" || role === "company-admin" || role === "turnstile") && !isSupportReadOnlyMode() && !isSuperadminCompanyPreviewMode();
}

function canRepairCompany(company) {
  const effectiveRole = getEffectiveUiRole();
  const effectiveCompanyId = getEffectiveUiCompanyId();
  if (!effectiveRole || !company?.id) {
    return false;
  }
  if (isSupportReadOnlyMode() || isSuperadminCompanyPreviewMode()) {
    return false;
  }
  if (effectiveRole === "superadmin") {
    return true;
  }
  return effectiveRole === "company-admin" && effectiveCompanyId === company.id;
}

function mapCompanyRepairError(error) {
  const message = String(error?.message || error || "");
  if (message === "forbidden") {
    return "Du darfst nur deine eigene Firma reparieren.";
  }
  if (message === "backend_unreachable") {
    return "Backend nicht erreichbar. Bitte Server und Netzwerk prüfen.";
  }
  if (message === "company_not_found") {
    return "Die Firma wurde nicht gefunden oder wurde inzwischen gelöscht.";
  }
  if (message === "company_locked") {
    return "Diese Firma ist aktuell gesperrt.";
  }
  if (message === "company_has_workers") {
    return "Die Firma hat noch aktive Mitarbeiter. Bitte komplette Löschung als Superadmin verwenden.";
  }
  return message || "unbekannter_fehler";
}

function getCompanyStatusMeta(status) {
  const normalized = String(status || "aktiv").trim().toLowerCase();
  if (normalized === "gesperrt") {
    return { label: "Gesperrt", className: "helper-text helper-text-warning" };
  }
  if (normalized === "pausiert") {
    return { label: "Pausiert", className: "helper-text helper-text-info" };
  }
  if (normalized === "test") {
    return { label: "Testphase", className: "helper-text helper-text-info" };
  }
  return { label: "Aktiv", className: "helper-text helper-text-ok" };
}

function isStandaloneDesktopApp() {
  return window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
}

function updateDesktopInstallHint() {
  if (!elements.desktopInstallHint) {
    return;
  }

  const lang = getStoredUiLang();
  const installHintInstalledByLang = {
    de: "BauPass Control ist auf diesem Geraet bereits als Desktop-App installiert.",
    en: "BauPass Control is already installed as a desktop app on this device.",
    tr: "BauPass Control bu cihazda zaten masaustu uygulamasi olarak kurulu.",
    ar: "BauPass Control مثبت بالفعل كتطبيق سطح مكتب على هذا الجهاز.",
    fr: "BauPass Control est deja installe comme application de bureau sur cet appareil.",
    es: "BauPass Control ya esta instalado como aplicacion de escritorio en este dispositivo.",
    it: "BauPass Control e gia installato come app desktop su questo dispositivo.",
    pl: "BauPass Control jest juz zainstalowany na tym urzadzeniu jako aplikacja desktopowa.",
  };
  const installHintDefaultByLang = {
    de: "Dieses Portal kann auf Windows, macOS und Linux wie ein lokales Programm installiert werden.",
    en: "This portal can be installed on Windows, macOS, and Linux like a local app.",
    tr: "Bu portal Windows, macOS ve Linux'a yerel uygulama gibi kurulabilir.",
    ar: "يمكن تثبيت هذه البوابة على Windows وmacOS وLinux كتطبيق محلي.",
    fr: "Ce portail peut etre installe sur Windows, macOS et Linux comme une application locale.",
    es: "Este portal puede instalarse en Windows, macOS y Linux como una app local.",
    it: "Questo portale puo essere installato su Windows, macOS e Linux come app locale.",
    pl: "Ten portal mozna zainstalowac w systemach Windows, macOS i Linux jako aplikacje lokalna.",
  };

  if (isStandaloneDesktopApp()) {
    elements.desktopInstallHint.textContent = installHintInstalledByLang[lang] || installHintInstalledByLang.de;
    return;
  }
  elements.desktopInstallHint.textContent = installHintDefaultByLang[lang] || installHintDefaultByLang.de;
}

function registerControlServiceWorker() {
  if (!("serviceWorker" in navigator)) {
    return;
  }
  // Hard-disable SW to prevent stale cached app bundles from breaking runtime behavior.
  navigator.serviceWorker.getRegistrations().then((registrations) => {
    return Promise.all(registrations.map((registration) => registration.unregister()));
  }).catch(() => {
    // ignore SW access failures
  });

  if (window.caches && typeof window.caches.keys === "function") {
    window.caches.keys().then((cacheKeys) => {
      return Promise.all(cacheKeys.map((key) => window.caches.delete(key)));
    }).catch(() => {
      // ignore cache delete failures
    });
  }
}

function wireDesktopInstallPrompt() {
  updateDesktopInstallHint();
  window.addEventListener("beforeinstallprompt", (event) => {
    deferredDesktopInstallPrompt = event;
    if (elements.desktopInstallButton) {
      elements.desktopInstallButton.hidden = false;
    }
  });
  window.addEventListener("appinstalled", () => {
    deferredDesktopInstallPrompt = null;
    if (elements.desktopInstallButton) {
      elements.desktopInstallButton.hidden = true;
    }
    updateDesktopInstallHint();
  });
}

async function triggerDesktopInstall() {
  if (isStandaloneDesktopApp()) {
    updateDesktopInstallHint();
    return;
  }
  if (!deferredDesktopInstallPrompt) {
    window.alert(uiT("alertInstallUnavailable"));
    return;
  }
  deferredDesktopInstallPrompt.prompt();
  await deferredDesktopInstallPrompt.userChoice;
  deferredDesktopInstallPrompt = null;
  if (elements.desktopInstallButton) {
    elements.desktopInstallButton.hidden = true;
  }
  updateDesktopInstallHint();
}

function initNativeDesktopShell() {
  const desktopApi = window.baupassDesktop;
  const isDesktop = Boolean(desktopApi && desktopApi.isDesktop);
  if (!isDesktop) {
    return;
  }

  if (elements.body) {
    elements.body.classList.add("desktop-app");
  }
  if (elements.desktopTitlebar) {
    elements.desktopTitlebar.classList.remove("hidden");
    elements.desktopTitlebar.setAttribute("aria-hidden", "false");
    // Doppelklick auf die Titelleiste → Maximieren/Wiederherstellen
    elements.desktopTitlebar.addEventListener("dblclick", (ev) => {
      if (ev.target.closest(".desktop-titlebar-actions")) return; // Buttons ausschließen
      desktopApi.toggleMaximize();
    });
  }

  if (elements.desktopInstallButton) {
    elements.desktopInstallButton.hidden = true;
  }
  if (elements.desktopInstallHint) {
    elements.desktopInstallHint.textContent = "Desktop-Modus aktiv - ohne Browser-Titelleiste.";
  }

  if (elements.desktopMinimizeBtn) {
    elements.desktopMinimizeBtn.addEventListener("click", () => {
      desktopApi.minimize();
    });
  }
  if (elements.desktopMaximizeBtn) {
    const updateMaximizeState = (state) => {
      const isMaximized = Boolean(state?.isMaximized);
      elements.desktopMaximizeBtn.title = isMaximized ? "Wiederherstellen" : "Maximieren";
      elements.desktopMaximizeBtn.setAttribute("aria-label", isMaximized ? "Wiederherstellen" : "Maximieren");
      elements.desktopMaximizeBtn.classList.toggle("is-maximized", isMaximized);
    };
    elements.desktopMaximizeBtn.addEventListener("click", () => {
      desktopApi.toggleMaximize();
    });
    desktopApi.getWindowState().then(updateMaximizeState).catch(() => {});
    if (typeof desktopApi.onWindowState === "function") {
      desktopApi.onWindowState(updateMaximizeState);
    }
  }
  if (elements.desktopCloseBtn) {
    elements.desktopCloseBtn.addEventListener("click", () => {
      desktopApi.close();
    });
  }
}

function getSubcompanyLabel(worker) {
  if (!worker?.subcompanyId) return "";
  const sub = state.subcompanies.find((entry) => entry.id === worker.subcompanyId);
  return sub?.name || "";
}

function isVisitorWorker(worker) {
  return String(worker?.workerType || worker?.worker_type || "worker").toLowerCase() === "visitor";
}

function toDateInputValue(date) {
  const parsed = date instanceof Date ? date : new Date(date);
  if (Number.isNaN(parsed.getTime())) {
    return "";
  }
  const year = parsed.getFullYear();
  const month = String(parsed.getMonth() + 1).padStart(2, "0");
  const day = String(parsed.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function toDateTimeLocalValue(date) {
  const parsed = date instanceof Date ? date : new Date(date);
  if (Number.isNaN(parsed.getTime())) {
    return "";
  }
  const year = parsed.getFullYear();
  const month = String(parsed.getMonth() + 1).padStart(2, "0");
  const day = String(parsed.getDate()).padStart(2, "0");
  const hour = String(parsed.getHours()).padStart(2, "0");
  const minute = String(parsed.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hour}:${minute}`;
}

function syncWorkerTypeUi() {
  const workerType = elements.workerType?.value || "worker";
  const isVisitor = workerType === "visitor";
  if (elements.visitorFields) {
    elements.visitorFields.classList.toggle("hidden", !isVisitor);
  }
  const insuranceField = document.querySelector("#insuranceNumber");
  const roleField = document.querySelector("#role");
  const badgePinField = document.querySelector("#badgePin");
  if (insuranceField) {
    insuranceField.required = !isVisitor;
    insuranceField.placeholder = isVisitor ? "Optional für Besucher" : "12 345678 A 123";
  }
  if (roleField) {
    roleField.required = !isVisitor;
    roleField.placeholder = isVisitor ? "Besucher" : "Polier, Kranfuehrer, Monteur";
    if (isVisitor && !roleField.value.trim()) {
      roleField.value = "Besucher";
    }
  }
  if (badgePinField) {
    badgePinField.required = !isVisitor;
    badgePinField.placeholder = isVisitor ? "Für Besucher nicht nötig" : "4 bis 8 Ziffern";
  }
  if (elements.badgePinHint) {
    elements.badgePinHint.textContent = isVisitor
      ? runtimeText("badgePinHintVisitor")
      : runtimeText("badgePinHintWorker");
  }
  if (isVisitor && elements.visitEndAt && !elements.visitEndAt.value) {
    const defaultEnd = new Date(Date.now() + (8 * 60 * 60 * 1000));
    elements.visitEndAt.value = toDateTimeLocalValue(defaultEnd);
  }
  if (isVisitor && document.querySelector("#validUntil") && elements.visitEndAt?.value) {
    document.querySelector("#validUntil").value = elements.visitEndAt.value.slice(0, 10);
  }
}

function populateSubcompanySelects() {
  const select = document.querySelector("#subcompanySelect");
  const companyId = document.querySelector("#companySelect")?.value || "";
  if (!select) return;
  const normalizedCompanyId = String(companyId).trim();

  const options = state.subcompanies
    .filter((entry) => {
      const isDeleted = Boolean(entry?.deletedAt || entry?.deleted_at);
      const entryCompanyId = String(entry?.companyId || entry?.company_id || "").trim();
      return !isDeleted && (!normalizedCompanyId || entryCompanyId === normalizedCompanyId);
    })
    .map((entry) => `<option value="${escapeHtml(entry.id)}">${escapeHtml(entry.name)}</option>`)
    .join("");

  const current = select.value || "";
  select.innerHTML = `<option value="">${uiT("optNoSubcompany")}</option>${options}`;
  if (current && Array.from(select.options).some((opt) => opt.value === current)) {
    select.value = current;
  }
}

function setPhotoEditorSource(source, { resetOffset = false } = {}) {
  photoEditorSourceData = source || "";
  if (resetOffset) {
    photoEditorOffset = { x: 0, y: 0 };
  }
  if (elements.photoData) {
    elements.photoData.value = photoEditorSourceData;
  }
  if (elements.capturedPhoto) {
    elements.capturedPhoto.src = photoEditorSourceData;
    elements.capturedPhoto.style.display = photoEditorSourceData ? "inline-block" : "none";
    elements.capturedPhoto.style.transform = "translate(0px, 0px)";
    elements.capturedPhoto.setAttribute("data-x", "0");
    elements.capturedPhoto.setAttribute("data-y", "0");
  }
  if (typeof updatePhotoAdjustControlsState === "function") {
    updatePhotoAdjustControlsState();
  }
}

function loadImageFromDataUrl(dataUrl) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("image_load_failed"));
    img.src = dataUrl;
  });
}

async function computePhotoDHash(dataUrl, width = 9, height = 8) {
  if (!dataUrl) {
    return "";
  }
  const img = await loadImageFromDataUrl(dataUrl);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(img, 0, 0, width, height);
  const pixels = ctx.getImageData(0, 0, width, height).data;

  let bits = "";
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < (width - 1); x += 1) {
      const left = ((y * width) + x) * 4;
      const right = ((y * width) + x + 1) * 4;
      const leftLuma = (pixels[left] * 299 + pixels[left + 1] * 587 + pixels[left + 2] * 114) / 1000;
      const rightLuma = (pixels[right] * 299 + pixels[right + 1] * 587 + pixels[right + 2] * 114) / 1000;
      bits += leftLuma > rightLuma ? "1" : "0";
    }
  }
  return bits;
}

async function computePhotoAHash(dataUrl, size = 8) {
  if (!dataUrl) {
    return "";
  }
  const img = await loadImageFromDataUrl(dataUrl);
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(img, 0, 0, size, size);
  const pixels = ctx.getImageData(0, 0, size, size).data;

  const lumaValues = [];
  for (let i = 0; i < pixels.length; i += 4) {
    const luma = (pixels[i] * 299 + pixels[i + 1] * 587 + pixels[i + 2] * 114) / 1000;
    lumaValues.push(luma);
  }
  const avg = lumaValues.reduce((sum, val) => sum + val, 0) / Math.max(1, lumaValues.length);
  return lumaValues.map((val) => (val >= avg ? "1" : "0")).join("");
}

async function computePhotoDHashCenterCrop(dataUrl, width = 9, height = 8) {
  if (!dataUrl) {
    return "";
  }
  const img = await loadImageFromDataUrl(dataUrl);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });

  const srcW = img.naturalWidth || img.width;
  const srcH = img.naturalHeight || img.height;
  const cropW = Math.max(1, Math.floor(srcW * 0.7));
  const cropH = Math.max(1, Math.floor(srcH * 0.7));
  const sx = Math.max(0, Math.floor((srcW - cropW) / 2));
  const sy = Math.max(0, Math.floor((srcH - cropH) / 2));
  ctx.drawImage(img, sx, sy, cropW, cropH, 0, 0, width, height);

  const pixels = ctx.getImageData(0, 0, width, height).data;
  let bits = "";
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < (width - 1); x += 1) {
      const left = ((y * width) + x) * 4;
      const right = ((y * width) + x + 1) * 4;
      const leftLuma = (pixels[left] * 299 + pixels[left + 1] * 587 + pixels[left + 2] * 114) / 1000;
      const rightLuma = (pixels[right] * 299 + pixels[right + 1] * 587 + pixels[right + 2] * 114) / 1000;
      bits += leftLuma > rightLuma ? "1" : "0";
    }
  }
  return bits;
}

function hammingDistanceBits(a, b) {
  const minLen = Math.min(a.length, b.length);
  let dist = 0;
  for (let i = 0; i < minLen; i += 1) {
    if (a[i] !== b[i]) {
      dist += 1;
    }
  }
  return dist + Math.abs(a.length - b.length);
}

async function compareWorkerPhotoSimilarity(referenceDataUrl, candidateDataUrl) {
  if (!referenceDataUrl || !candidateDataUrl) {
    return { comparable: false, similarity: 0 };
  }
  try {
    const [refDHash, candDHash, refAHash, candAHash, refCenterHash, candCenterHash] = await Promise.all([
      computePhotoDHash(referenceDataUrl),
      computePhotoDHash(candidateDataUrl),
      computePhotoAHash(referenceDataUrl),
      computePhotoAHash(candidateDataUrl),
      computePhotoDHashCenterCrop(referenceDataUrl),
      computePhotoDHashCenterCrop(candidateDataUrl)
    ]);

    if (!refDHash || !candDHash || !refAHash || !candAHash || !refCenterHash || !candCenterHash) {
      return { comparable: false, similarity: 0 };
    }

    const dDistance = hammingDistanceBits(refDHash, candDHash);
    const dMax = Math.max(refDHash.length, candDHash.length) || 1;
    const dSimilarity = 1 - (dDistance / dMax);

    const aDistance = hammingDistanceBits(refAHash, candAHash);
    const aMax = Math.max(refAHash.length, candAHash.length) || 1;
    const aSimilarity = 1 - (aDistance / aMax);

    const cDistance = hammingDistanceBits(refCenterHash, candCenterHash);
    const cMax = Math.max(refCenterHash.length, candCenterHash.length) || 1;
    const cSimilarity = 1 - (cDistance / cMax);

    const similarity = (dSimilarity * 0.45) + (aSimilarity * 0.2) + (cSimilarity * 0.35);
    return { comparable: true, similarity: Math.max(0, Math.min(1, similarity)) };
  } catch {
    return { comparable: false, similarity: 0 };
  }
}

function syncWorkerEditorUi() {
  const submitButton = document.querySelector("#workerSubmitButton");
  const cancelButton = document.querySelector("#workerCancelEditButton");
  const editing = Boolean(state.editingWorkerId);
  if (submitButton) {
    submitButton.textContent = editing ? "Mitarbeiter aktualisieren" : "Mitarbeiter speichern und Ausweis erzeugen";
  }
  if (cancelButton) {
    cancelButton.classList.toggle("hidden", !editing);
  }
}

function clearWorkerEditor() {
  const form = document.querySelector("#workerForm");
  if (form) {
    form.reset();
  }
  const badgePinInput = document.querySelector("#badgePin");
  if (badgePinInput) {
    badgePinInput.value = "";
  }
  state.editingWorkerId = null;
  setPhotoEditorSource("", { resetOffset: true });
  if (elements.workerType) {
    elements.workerType.value = "worker";
  }
  syncWorkerTypeUi();
  syncWorkerEditorUi();
}

function applyWebsiteLogo(dataUrl) {
  const fixedBpIconPath = "./worker-icon-192.png?v=20260421bp";
  const hasLogo = Boolean(dataUrl);
  document.querySelectorAll(".website-logo-sync").forEach((img) => {
    if (hasLogo) {
      img.src = dataUrl;
    }
    img.classList.toggle("hidden", !hasLogo && img.classList.contains("website-logo-sidebar"));
  });

  const appFavicon = document.querySelector("#appFavicon");
  if (appFavicon) {
    appFavicon.href = fixedBpIconPath;
  }
  document.querySelectorAll('link[rel="apple-touch-icon"]').forEach((link) => {
    link.href = fixedBpIconPath;
  });
}

function getCurrentUser() {
  return state.currentUser;
}

function isSuperadminCompanyPreviewMode() {
  const role = String(getCurrentUser()?.role || "").toLowerCase();
  return role === "superadmin" && Boolean(String(superadminUiPreviewCompanyId || "").trim());
}

function getEffectiveUiRole() {
  if (isSuperadminCompanyPreviewMode()) {
    return "company-admin";
  }
  return String(getCurrentUser()?.role || "").toLowerCase();
}

function getEffectiveUiCompanyId() {
  if (isSuperadminCompanyPreviewMode()) {
    return String(superadminUiPreviewCompanyId || "").trim();
  }
  return String(getCurrentUser()?.company_id || getCurrentUser()?.companyId || "").trim();
}

function getUiVisibleWorkers() {
  const companyId = getEffectiveUiCompanyId();
  if (!companyId) {
    return [...state.workers];
  }
  return state.workers.filter((entry) => String(entry?.companyId || entry?.company_id || "").trim() === companyId);
}

function getUiVisibleAccessLogs() {
  const workers = getUiVisibleWorkers();
  const allowedWorkerIds = new Set(workers.map((entry) => entry.id));
  return state.accessLogs.filter((entry) => allowedWorkerIds.has(entry.workerId));
}

function getDefaultViewForRole(role) {
  const normalized = String(role || "").toLowerCase();
  if (normalized === "turnstile") {
    return "access";
  }
  return "dashboard";
}

function getAllowedViewsForRole(role) {
  const normalized = String(role || "").toLowerCase();
  if (normalized === "superadmin") {
    return ["dashboard", "workers", "badge", "access", "documents", "invoices", "admin", "devices"];
  }
  if (normalized === "company-admin") {
    return ["dashboard", "workers", "badge", "access", "documents", "devices", "admin"];
  }
  if (normalized === "turnstile") {
    return ["access", "documents", "dashboard"];
  }
  return ["dashboard"];
}

function getCurrentViewName() {
  const activeView = elements.views.find((view) => view.classList.contains("active"));
  return activeView?.dataset?.view || "dashboard";
}

function enforceRoleViewAccess() {
  const role = getEffectiveUiRole();
  const allowedViews = getAllowedViewsForRole(role);
  const currentView = getCurrentViewName();

  elements.navLinks.forEach((link) => {
    const viewName = link.dataset.view || "";
    const allowed = allowedViews.includes(viewName);
    link.style.display = allowed ? "" : "none";
  });

  // Hide sections that are only for superadmin
  const isSuperadmin = role === "superadmin";
  document.querySelectorAll("[data-superadmin-only]").forEach((el) => {
    el.style.display = isSuperadmin ? "" : "none";
  });

  if (!allowedViews.includes(currentView)) {
    setView(getDefaultViewForRole(role));
  }
}

function setView(viewName) {
  const role = getEffectiveUiRole();
  const allowedViews = getAllowedViewsForRole(role);
  const targetView = allowedViews.includes(viewName) ? viewName : getDefaultViewForRole(role);

  elements.views.forEach((view) => {
    view.classList.toggle("active", view.dataset.view === targetView);
  });
  elements.navLinks.forEach((link) => {
    link.classList.toggle("active", link.dataset.view === targetView);
  });

  if (targetView === "invoices") {
    markCurrentInvoicesAsSeen();
    startInvoiceAutoRefresh();
    startInvoiceApprovalAutoRefresh();
  } else {
    stopInvoiceAutoRefresh();
    stopInvoiceApprovalAutoRefresh();
  }

  if (targetView === "devices") {
    loadDevices();
  }
}

function stopInvoiceAutoRefresh() {
  if (invoiceAutoRefreshTimer) {
    window.clearInterval(invoiceAutoRefreshTimer);
    invoiceAutoRefreshTimer = null;
  }
}

function stopInvoiceApprovalAutoRefresh() {
  if (invoiceApprovalRefreshTimer) {
    window.clearInterval(invoiceApprovalRefreshTimer);
    invoiceApprovalRefreshTimer = null;
  }
}

function markCurrentInvoicesAsSeen() {
  const seen = { ...(state.invoiceSeenIds || {}) };
  (state.invoices || []).forEach((invoice) => {
    if (invoice?.id) {
      seen[invoice.id] = true;
    }
  });
  state.invoiceSeenIds = seen;
  state.invoiceNewIds = {};
}

function startInvoiceAutoRefresh() {
  if (invoiceAutoRefreshTimer || getCurrentViewName() !== "invoices") {
    return;
  }
  invoiceAutoRefreshTimer = window.setInterval(async () => {
    if (!token || getCurrentViewName() !== "invoices") {
      stopInvoiceAutoRefresh();
      return;
    }
    await loadAndRenderInvoices({ silent: true });
  }, 25000);
}

async function loadInvoiceApprovalsOnly(options = {}) {
  const { silent = true } = options;
  try {
    const approvalResponse = await apiRequest(API_BASE + "/api/invoices/approvals/pending");
    state.invoiceApprovalRequests = Array.isArray(approvalResponse) ? approvalResponse : [];
    renderInvoiceApprovalQueue();
  } catch (error) {
    if (!silent) {
      console.error("Failed to load invoice approvals:", error);
    }
  }
}

function startInvoiceApprovalAutoRefresh() {
  if (invoiceApprovalRefreshTimer || getCurrentViewName() !== "invoices") {
    return;
  }
  invoiceApprovalRefreshTimer = window.setInterval(async () => {
    if (!token || getCurrentViewName() !== "invoices") {
      stopInvoiceApprovalAutoRefresh();
      return;
    }
    await loadInvoiceApprovalsOnly({ silent: true });
  }, 20000);
}

function clearSession() {
  token = "";
  persistSessionToken("");
  state.currentUser = null;
  state.loginOtpPending = false;
  // Greeting darf beim nächsten Login wieder erscheinen
  localStorage.removeItem(GREETING_SHOWN_KEY);
}

function handleExpiredControlSession() {
  clearSession();
  refreshAll();
  const now = Date.now();
  if (sessionExpiryNoticeShown && (now - sessionExpiryNoticeAt) < 2500) {
    return;
  }
  sessionExpiryNoticeShown = true;
  sessionExpiryNoticeAt = now;
  window.alert(uiT("alertSessionExpired"));
}

function startHeartbeat() {
  if (heartbeatTimer) {
    window.clearInterval(heartbeatTimer);
  }
  heartbeatTimer = window.setInterval(async () => {
    if (!token) return;
    try {
      const response = await fetch(`${API_BASE}/api/me/heartbeat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        credentials: "include",
        body: JSON.stringify({}),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload?.active === false) {
        clearSession();
        refreshAll();
      }
    } catch {
      // heartbeat failures should not hard-crash UI
    }
  }, 4 * 60 * 1000);
}

function startBackendStatusMonitor() {
  if (backendStatusTimer) {
    window.clearInterval(backendStatusTimer);
  }
  backendStatusTimer = window.setInterval(async () => {
    try {
      await fetch(`${API_BASE}/api/health`, { credentials: "include" });
    } catch {
      // ignore transient offline checks
    }
  }, 30 * 1000);
}

async function apiRequest(url, options = {}) {
  const { method = "GET", body, auth = true, retries = 1 } = options;
  if (auth && !token) {
    handleExpiredControlSession();
    throw new Error("session_expired");
  }
  const normalizedMethod = String(method || "GET").toUpperCase();
  if (
    auth
    && isSupportReadOnlyMode()
    && !["GET", "HEAD", "OPTIONS"].includes(normalizedMethod)
    && !String(url || "").includes("/api/logout")
    && !String(url || "").includes("/api/me/heartbeat")
  ) {
    throw new Error("support_session_read_only");
  }
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (auth && token) {
    headers.Authorization = `Bearer ${token}`;
  }

  let response;
  try {
    response = await fetch(url, {
      method,
      headers,
      credentials: "include",
      body: body === undefined ? undefined : JSON.stringify(body)
    });
  } catch {
    throw new Error("backend_unreachable");
  }

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    // ── Retry bei 401 mit neuer Session ──
    if (auth && response.status === 401 && retries > 0) {
      console.warn("⚠️  401 erhalten, versuche neue Session zu laden...");
      try {
        await loadAllData();
        if (token) {
          console.log("✓ Session erneuert, wiederhole Request");
          return apiRequest(url, { ...options, retries: retries - 1 });
        }
      } catch {
        // Fallback zu Session-Ablauf
        handleExpiredControlSession();
        throw new Error("session_expired");
      }
    }
    if (auth && ["invalid_session", "unauthorized"].includes(String(payload?.error || ""))) {
      handleExpiredControlSession();
      throw new Error("session_expired");
    }
    const requestError = new Error(payload?.error || `http_${response.status}`);
    requestError.code = payload?.error || `http_${response.status}`;
    requestError.payload = payload;
    requestError.status = response.status;
    throw requestError;
  }
  return payload;
}

function normalizeWorkerAppLink(rawLink) {
  const candidate = String(rawLink || "").trim();
  if (!candidate) {
    return "";
  }

  try {
    return new URL(candidate, window.location.origin).toString();
  } catch {
    return candidate;
  }
}

async function loadAllData() {
  // Ohne gespeicherten Token gibt es keine Session zum Bootstrappen.
  // So vermeiden wir unnoetige 401-Requests im ausgeloggten Zustand.
  if (!token) {
    sessionExpiryNoticeShown = false;
    return;
  }

  // Bootstrap nur dann nutzen, wenn ein Token existiert, aber der User noch
  // nicht in den lokalen State geladen wurde.
  if (!state.currentUser) {
    let bootstrap;
    try {
      console.log("[Bootstrap] Attempting with token:", token ? `${token.slice(0, 20)}...` : "NONE");
      bootstrap = await apiRequest(`${API_BASE}/api/session/bootstrap`, {
        auth: false,
        // Bei Cross-Site-Cookies (z. B. Railway) kann der Cookie fehlen.
        // Wenn bereits ein Token im Speicher ist, sende es explizit mit.
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });
      console.log("[Bootstrap] Success:", { hasUser: !!bootstrap?.user, username: bootstrap?.user?.username });
    } catch (error) {
      const msg = String(error?.message || "");
      console.warn("[Bootstrap] Failed:", msg);
      // Nicht eingeloggt ist beim ersten Laden ein normaler Zustand.
      if (["unauthorized", "invalid_session", "session_expired"].includes(msg)) {
        clearSession();
        sessionExpiryNoticeShown = false;
        return;
      }
      throw error;
    }
    if (bootstrap?.token) {
      token = bootstrap.token;
      persistSessionToken(token);
    }
    if (bootstrap?.user) {
      state.currentUser = bootstrap.user;
      // Serverseitig gespeicherte Vorschau-Session wiederherstellen
      if (bootstrap.user.role === "superadmin" && bootstrap.user.preview_company_id) {
        superadminUiPreviewCompanyId = bootstrap.user.preview_company_id;
        const previewCompany = (state.companies || []).find((c) => c.id === superadminUiPreviewCompanyId);
        companyBrandingPreviewOverride = previewCompany ? getCompanyBrandingPreset(previewCompany) : "";
      }
    }
  }

  sessionExpiryNoticeShown = false;

  const reportUrl = `${API_BASE}/api/reporting/summary`;
  const requests = await Promise.allSettled([
    apiRequest(`${API_BASE}/api/settings`),
    apiRequest(`${API_BASE}/api/companies`),
    apiRequest(`${API_BASE}/api/subcompanies`),
    apiRequest(`${API_BASE}/api/workers`),
    apiRequest(`${API_BASE}/api/access-logs`),
    apiRequest(`${API_BASE}/api/invoices`),
    apiRequest(`${API_BASE}/api/access-logs/summary`),
    apiRequest(`${API_BASE}/api/access-logs/day-close-check`),
    apiRequest(`${API_BASE}/api/audit-logs?eventType=company.repair&targetType=company&limit=120`),
    apiRequest(reportUrl),
    apiRequest(`${API_BASE}/api/compliance/overview`),
    apiRequest(`${API_BASE}/api/audit-logs?limit=50`)
  ]);

  const [settings, companies, subcompanies, workers, accessLogs, invoices, summary, dayClose, repairAudit, reporting, complianceOverview, auditLogs] = requests;
  if (settings.status === "fulfilled") {
    state.settings = settings.value || state.settings;
    document.dispatchEvent(new CustomEvent("baupass:settingsLoaded"));
  }
  if (companies.status === "fulfilled") {
    state.companies = companies.value || [];
    // Branding-Override nach Laden der Unternehmen auflösen (bei wiederhergestellter Vorschau-Session)
    if (superadminUiPreviewCompanyId && !companyBrandingPreviewOverride) {
      const previewCompany = state.companies.find((c) => c.id === superadminUiPreviewCompanyId);
      if (previewCompany) {
        companyBrandingPreviewOverride = getCompanyBrandingPreset(previewCompany);
      }
    }
  }
  if (subcompanies.status === "fulfilled") state.subcompanies = subcompanies.value || [];
  if (workers.status === "fulfilled") state.workers = workers.value || [];
  if (accessLogs.status === "fulfilled") state.accessLogs = (accessLogs.value || []).map(normalizeLog);
  if (invoices.status === "fulfilled") state.invoices = invoices.value || [];
  if (invoices.status !== "fulfilled") state.invoices = [];
  if (summary.status === "fulfilled") state.accessInsights = summary.value || state.accessInsights;
  if (reporting.status === "fulfilled") state.reporting = reporting.value || state.reporting;
  if (dayClose.status === "fulfilled") state.dayClose = dayClose.value || null;
  if (repairAudit.status === "fulfilled") {
    const grouped = {};
    ((repairAudit.value && Array.isArray(repairAudit.value.logs) ? repairAudit.value.logs : repairAudit.value) || []).forEach((entry) => {
      const companyId = entry?.target_id || "";
      if (!companyId) {
        return;
      }
      if (!grouped[companyId]) {
        grouped[companyId] = [];
      }
      grouped[companyId].push(entry);
    });
    Object.keys(grouped).forEach((companyId) => {
      grouped[companyId] = grouped[companyId].slice(0, 5);
    });
    state.companyRepairHistory = grouped;
  } else {
    state.companyRepairHistory = {};
  }

  if (complianceOverview.status === "fulfilled") {
    state.complianceOverview = Array.isArray(complianceOverview.value) ? complianceOverview.value : [];
  } else {
    state.complianceOverview = [];
  }

  if (auditLogs.status === "fulfilled") {
    state.auditLogs = Array.isArray(auditLogs.value?.logs) ? auditLogs.value.logs : [];
  } else {
    state.auditLogs = [];
  }

  state.companyTurnstiles = {};
  state.companyAdminSecurity = {};
  if (companies.status === "fulfilled" && ["superadmin", "company-admin"].includes(String(state.currentUser?.role || ""))) {
    const visibleCompanies = (companies.value || []).filter((company) => !company.deleted_at);
    const [turnstileRequests, securityRequests] = await Promise.all([
      Promise.allSettled(
        visibleCompanies.map((company) => apiRequest(`${API_BASE}/api/companies/${company.id}/turnstiles`))
      ),
      state.currentUser?.role === "superadmin"
        ? Promise.allSettled(
            visibleCompanies.map((company) => apiRequest(`${API_BASE}/api/companies/${company.id}/admin-security`))
          )
        : Promise.resolve(visibleCompanies.map(() => ({ status: "skipped" }))),
    ]);
    visibleCompanies.forEach((company, index) => {
      const result = turnstileRequests[index];
      state.companyTurnstiles[company.id] = result?.status === "fulfilled" && Array.isArray(result.value)
        ? result.value
        : [];
      if (state.currentUser?.role === "superadmin") {
        const sec = securityRequests[index];
        state.companyAdminSecurity[company.id] = sec?.status === "fulfilled" ? sec.value : null;
      }
    });
  }
}

function refreshAll() {
  const loggedIn = Boolean(token && state.currentUser);
  syncSupportLoginUi();
  if (elements.authOverlay) {
    const activeElement = document.activeElement;
    if (loggedIn && activeElement && elements.authOverlay.contains(activeElement) && typeof activeElement.blur === "function") {
      activeElement.blur();
    }
    elements.authOverlay.style.display = loggedIn ? "none" : "grid";
    elements.authOverlay.setAttribute("aria-hidden", loggedIn ? "true" : "false");
    elements.authOverlay.toggleAttribute("inert", loggedIn);
  }
  if (elements.mainShell) {
    elements.mainShell.style.display = loggedIn ? "grid" : "none";
    elements.mainShell.classList.toggle("locked", !loggedIn);
    elements.mainShell.hidden = !loggedIn;
    elements.mainShell.setAttribute("aria-hidden", loggedIn ? "false" : "true");
    elements.mainShell.toggleAttribute("inert", !loggedIn);
  }
  if (elements.body) {
    elements.body.classList.toggle("auth-locked", !loggedIn);
    if (!loggedIn) {
      companyBrandingPreviewOverride = "";
      superadminUiPreviewCompanyId = "";
      elements.body.setAttribute("data-branding-preset", "construction");
    }
  }

  if (!loggedIn) {
    focusLoginInput();
  }

  updateTopbarActionsState(loggedIn);
  renderSuperadminPreviewTopbar(loggedIn);
  renderSuperadminSimulationBar(loggedIn);
  renderSuperadminPreviewSidebarStatus(loggedIn);
  renderSystemAlertBanner(loggedIn);

  if (loggedIn && elements.sessionCard) {
    const texts = getRuntimeUiTexts();
    const role = getRoleLabel(state.currentUser?.role || "");
    const user = state.currentUser?.username || "-";
    const supportModeMarkup = isSupportReadOnlyMode()
      ? `<br /><strong>${escapeHtml(uiT("supportModeLabel"))}</strong> ${escapeHtml(uiT("supportReadOnlyFor"))} ${escapeHtml(state.currentUser?.support_company_name || uiT("supportCompanyFallback"))}${state.currentUser?.support_actor_name ? ` | ${escapeHtml(uiT("supportStartedBy"))} ${escapeHtml(state.currentUser.support_actor_name)}` : ""}`
      : "";
    const previewCompany = state.companies.find((entry) => String(entry?.id || "") === String(superadminUiPreviewCompanyId || ""));
    const previewMarkup = isSuperadminCompanyPreviewMode() && previewCompany
      ? `<br /><strong>Vorschau:</strong> Firmenansicht ${escapeHtml(previewCompany.name || "Firma")}`
      : "";
    elements.sessionCard.innerHTML = `<strong>${escapeHtml(texts.sessionLoggedIn)}:</strong> ${escapeHtml(user)} | <strong>${escapeHtml(texts.sessionRole)}:</strong> ${escapeHtml(role)}${supportModeMarkup}${previewMarkup}`;
  }

  if (!loggedIn) {
    stopInvoiceAutoRefresh();
    stopInvoiceApprovalAutoRefresh();
    return;
  }

  enforceRoleViewAccess();
  applyActiveCompanyBrandingPreset();

  renderStats();
  renderReportingPanels();
  renderWorkerList();
  renderPhotoOverrideApprovalPanel();
  renderCompanyList();
  renderCompliancePanel();
  renderAuditLogPanel();
  populateWorkerSelectOptions();
  populateCompanySelectOptions();
  renderSystemIdentity();
  renderAdminSettingsForm();
  renderDashboardPorterLivePanel();
  renderRecentAccess();
  renderAccessLog();
  renderAccessSummary();
  renderAccessHourly();
  renderAccessWarnings();
  renderDayCloseBanner();
  renderTurnstileQuickPanel();
  renderPorterLivePanel();
  renderBadge();
  loadDevices();
  showLoginGreeting();
  renderTwofaPanel();
  renderInvoiceHistory();
  renderInvoiceManagementList();
  if (getCurrentViewName() === "invoices") {
    startInvoiceAutoRefresh();
  }
  ensureInvoiceDefaults();
  refreshInvoicePreview({ silent: true });
  applySupportReadOnlyUiState();
}

// ── Login Greeting ──────────────────────────────────────────────────────────
const GREETING_SHOWN_KEY = "baupass-greeting-date";
const GREET_DISPLAY_MS = 4200;

function getGreetingMeta(lang) {
  const normalized = normalizeUiLang(lang);
  const map = {
    de: {
      ttsLang: "de-DE",
      morning: "Guten Morgen",
      noon: "Guten Mittag",
      day: "Guten Tag",
      evening: "Guten Abend",
      night: "Gute Nacht",
      subMorning: "Ein produktiver Tag liegt vor Ihnen.",
      subNoon: "Zeit fuer eine kurze Pause!",
      subDay: "Schoen, dass Sie da sind.",
      subEvening: "Danke fuer Ihren Einsatz heute.",
      subNight: "Bitte denken Sie an die Uebergabe.",
    },
    en: {
      ttsLang: "en-GB",
      morning: "Good morning",
      noon: "Good afternoon",
      day: "Good afternoon",
      evening: "Good evening",
      night: "Good night",
      subMorning: "A productive day is ahead of you.",
      subNoon: "Time for a short break!",
      subDay: "Great to have you here.",
      subEvening: "Thank you for your effort today.",
      subNight: "Please remember the handover.",
    },
    tr: {
      ttsLang: "tr-TR",
      morning: "Gunaydin",
      noon: "Iyi oglenler",
      day: "Iyi gunler",
      evening: "Iyi aksamlar",
      night: "Iyi geceler",
      subMorning: "Verimli bir gun sizi bekliyor.",
      subNoon: "Kisa bir mola zamani!",
      subDay: "Burada olmaniza sevindik.",
      subEvening: "Bugunku emeginiz icin tesekkurler.",
      subNight: "Lutfen deviri unutmayin.",
    },
    ar: {
      ttsLang: "ar-SA",
      morning: "صباح الخير",
      noon: "نهارك سعيد",
      day: "مرحباً",
      evening: "مساء الخير",
      night: "تصبح على خير",
      subMorning: "يوم منتج ينتظرك.",
      subNoon: "وقت استراحة قصيرة!",
      subDay: "سعداء بوجودك.",
      subEvening: "شكراً على جهودك اليوم.",
      subNight: "يرجى تذكر تسليم المهام.",
    },
    fr: {
      ttsLang: "fr-FR",
      morning: "Bonjour",
      noon: "Bon apres-midi",
      day: "Bonjour",
      evening: "Bonsoir",
      night: "Bonne nuit",
      subMorning: "Une journee productive vous attend.",
      subNoon: "Temps pour une courte pause !",
      subDay: "Ravis de vous voir.",
      subEvening: "Merci pour votre engagement aujourd'hui.",
      subNight: "Pensez a la passation, s'il vous plait.",
    },
    es: {
      ttsLang: "es-ES",
      morning: "Buenos dias",
      noon: "Buenas tardes",
      day: "Buenas tardes",
      evening: "Buenas tardes",
      night: "Buenas noches",
      subMorning: "Le espera un dia productivo.",
      subNoon: "Hora de una pausa corta!",
      subDay: "Nos alegra verle aqui.",
      subEvening: "Gracias por su esfuerzo de hoy.",
      subNight: "Recuerde el relevo, por favor.",
    },
    it: {
      ttsLang: "it-IT",
      morning: "Buongiorno",
      noon: "Buon pomeriggio",
      day: "Buon pomeriggio",
      evening: "Buonasera",
      night: "Buonanotte",
      subMorning: "Ti aspetta una giornata produttiva.",
      subNoon: "Tempo per una breve pausa!",
      subDay: "Felici di averti qui.",
      subEvening: "Grazie per il tuo impegno di oggi.",
      subNight: "Ricorda il passaggio consegne.",
    },
    pl: {
      ttsLang: "pl-PL",
      morning: "Dzien dobry",
      noon: "Dobrego poludnia",
      day: "Milego dnia",
      evening: "Dobry wieczor",
      night: "Dobranoc",
      subMorning: "Przed Toba produktywny dzien.",
      subNoon: "Czas na krotka przerwe!",
      subDay: "Milo Cie widziec.",
      subEvening: "Dziekujemy za Twoj dzisiejszy wysilek.",
      subNight: "Pamietaj o przekazaniu zmiany.",
    },
  };

  return map[normalized] || map.de;
}

function loadTtsVoiceList() {
  const panel = document.getElementById("ttsVoiceListPanel");
  if (!panel) return;

  if (!window.speechSynthesis) {
    panel.innerHTML = `
      <p style="color:#dc2626;font-size:0.88rem">⚠️ Sprachausgabe (Web Speech API) wird von diesem Browser nicht unterstützt.</p>
      <p style="color:#555;font-size:0.83rem;margin-top:6px">Bitte verwende <strong>Google Chrome</strong> oder <strong>Microsoft Edge</strong> für Sprachausgabe.</p>`;
    return;
  }

  function renderVoices() {
    const voices = window.speechSynthesis.getVoices();
    if (!voices.length) {
      panel.innerHTML = `
        <div style="background:#fff8e1;border:1px solid #f59e0b;border-radius:6px;padding:12px;font-size:0.85rem">
          <p style="margin:0 0 8px;font-weight:600;color:#92400e">⚠️ Keine Sprachstimmen gefunden</p>
          <p style="margin:0 0 6px;color:#555">Mögliche Ursachen und Lösungen:</p>
          <ul style="margin:0 0 10px;padding-left:18px;color:#555;line-height:1.7">
            <li><strong>Windows:</strong> Einstellungen → Zeit &amp; Sprache → Sprache → Sprache hinzufügen (z.B. Arabisch, Türkisch)</li>
            <li><strong>Chrome:</strong> Öffne <code>chrome://settings/languages</code> und füge Sprachen hinzu</li>
            <li><strong>Firefox:</strong> Unterstützt Web Speech API eingeschränkt – besser Chrome/Edge nutzen</li>
            <li><strong>Server/Linux:</strong> <code>apt install speech-dispatcher espeak-ng</code></li>
          </ul>
          <p style="margin:0;color:#555">Die Begrüßung spielt trotzdem einen <strong>Jingle</strong> ab, wenn keine Stimme verfügbar ist.</p>
          <button type="button" class="ghost-button" style="margin-top:10px" onclick="loadTtsVoiceList()">🔄 Erneut versuchen</button>
        </div>`;
      return;
    }

    const byLang = {};
    for (const v of voices) {
      const lang = v.lang || "unbekannt";
      if (!byLang[lang]) byLang[lang] = [];
      byLang[lang].push(v);
    }

    const langKeys = Object.keys(byLang).sort();
    const highlighted = ["de", "ar", "tr", "en", "fr", "es", "it", "pl"];

    let html = `<p style="font-size:0.82rem;color:#555;margin:0 0 10px">${voices.length} Stimmen verfügbar</p>`;

    // Warnung wenn wichtige Sprachen fehlen
    const missingLangs = [];
    const availPrefixes = new Set(Object.keys(byLang).map((l) => l.split("-")[0].toLowerCase()));
    const needed = { ar: "Arabisch", tr: "Türkisch", de: "Deutsch", en: "Englisch", fr: "Französisch", es: "Spanisch", it: "Italienisch", pl: "Polnisch" };
    for (const [code, label] of Object.entries(needed)) {
      if (!availPrefixes.has(code)) missingLangs.push({ code, label });
    }
    if (missingLangs.length) {
      html += `<div style="background:#fff8e1;border:1px solid #f59e0b;border-radius:6px;padding:10px 12px;margin-bottom:10px;font-size:0.83rem">`;
      html += `<p style="margin:0 0 4px;font-weight:600;color:#92400e">⚠️ Fehlende Sprachen: ${missingLangs.map((l) => l.label).join(", ")}</p>`;
      html += `<p style="margin:0 0 6px;color:#555">So installieren (Windows):</p>`;
      html += `<ol style="margin:0 0 6px;padding-left:18px;color:#555;line-height:1.75">`;
      html += `<li>Öffne <strong>Einstellungen → Zeit &amp; Sprache → Sprache</strong></li>`;
      html += `<li>Klicke auf <strong>„Sprache hinzufügen"</strong></li>`;
      html += `<li>Suche nach der fehlenden Sprache (z.B. <strong>العربية</strong> für Arabisch) und installiere sie</li>`;
      html += `<li>Stelle sicher dass bei der installierten Sprache <strong>„Sprachausgabe"</strong> aktiviert ist</li>`;
      html += `<li>Browser neu starten und <strong>„Stimmen laden"</strong> erneut klicken</li>`;
      html += `</ol>`;
      html += `<p style="margin:0;color:#555">Bis zur Installation spricht die Begrüßung auf <strong>Englisch</strong> als Fallback.</p>`;
      html += `</div>`;
    }
    html += `<div style="max-height:400px;overflow-y:auto;font-size:0.83rem">`;
    for (const lang of langKeys) {
      const prefix = lang.split("-")[0].toLowerCase();
      const isHighlighted = highlighted.includes(prefix);
      const color = isHighlighted ? "#0f4c5c" : "#555";
      const weight = isHighlighted ? "600" : "400";
      html += `<div style="margin-bottom:6px">`;
      html += `<span style="font-weight:${weight};color:${color}">${escapeHtml(lang)}</span>`;
      html += `<span style="color:#999;margin-left:6px">(${byLang[lang].length} Stimme${byLang[lang].length !== 1 ? "n" : ""})</span>`;
      html += `<div style="margin-left:12px;display:flex;flex-wrap:wrap;gap:4px;margin-top:3px">`;
      for (const v of byLang[lang]) {
        const label = v.name + (v.localService ? " 🖥️" : " ☁️");
        const voiceIdx = voices.indexOf(v);
        html += `<button type="button" class="ghost-button" style="font-size:0.78rem;padding:2px 7px"
          onclick="testTtsVoice(${voiceIdx})">${escapeHtml(label)}</button>`;
      }
      html += `</div></div>`;
    }
    html += `</div>`;
    html += `<p style="font-size:0.78rem;color:#888;margin-top:8px">🖥️ = lokale Stimme &nbsp; ☁️ = Cloud-Stimme &nbsp; <strong>Fett</strong> = in BauPass genutzte Sprachen</p>`;
    panel.innerHTML = html;
  }

  panel.innerHTML = `<p style="color:#888;font-size:0.88rem">Lade Stimmen…</p>`;
  const voices = window.speechSynthesis.getVoices();
  if (voices.length > 0) {
    renderVoices();
  } else {
    window.speechSynthesis.addEventListener("voiceschanged", function once() {
      window.speechSynthesis.removeEventListener("voiceschanged", once);
      renderVoices();
    });
    setTimeout(renderVoices, 1200);
  }
}

function testTtsVoice(voiceIndex) {
  if (!window.speechSynthesis) return;
  const voices = window.speechSynthesis.getVoices();
  const voice = voices[voiceIndex];
  if (!voice) return;
  window.speechSynthesis.cancel();
  const lang = getStoredUiLang ? getStoredUiLang() : "de";
  const greetingMeta = getGreetingMeta(lang);
  const h = new Date().getHours();
  const text = h < 12 ? greetingMeta.morning : h < 18 ? greetingMeta.day : greetingMeta.evening;
  const utter = new SpeechSynthesisUtterance(text + "!");
  utter.voice  = voice;
  utter.lang   = voice.lang;
  utter.volume = 0.8;
  utter.rate   = 0.92;
  utter.pitch  = 1.15;
  window.speechSynthesis.speak(utter);
}

function playGreetingJingle() {
  // Freundlicher 3-Ton Jingle über Web Audio API – kein TTS nötig
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const notes = [523.25, 659.25, 783.99]; // C5, E5, G5 (Dur-Dreiklang)
    let startTime = ctx.currentTime + 0.05;
    for (const freq of notes) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = "sine";
      osc.frequency.setValueAtTime(freq, startTime);
      gain.gain.setValueAtTime(0, startTime);
      gain.gain.linearRampToValueAtTime(0.18, startTime + 0.04);
      gain.gain.exponentialRampToValueAtTime(0.001, startTime + 0.45);
      osc.start(startTime);
      osc.stop(startTime + 0.5);
      startTime += 0.22;
    }
    // Kontext nach Ende schließen
    setTimeout(() => { try { ctx.close(); } catch {} }, 2000);
  } catch {
    // AudioContext nicht verfügbar – ignorieren
  }
}

function showLoginGreeting() {
  const user = state.currentUser;
  const el = document.getElementById("loginGreetingToast");
  if (!el || !user) return;

  // Nur einmal pro Tag anzeigen
  const today = new Date().toISOString().slice(0, 10); // "2026-04-21"
  const lastShown = localStorage.getItem(GREETING_SHOWN_KEY);
  if (lastShown === today) return;
  localStorage.setItem(GREETING_SHOWN_KEY, today);

  const lang = getStoredUiLang();
  const greetingMeta = getGreetingMeta(lang);
  const h = new Date().getHours();
  let salutation, icon, sub;
  if      (h >= 5  && h < 12) { salutation = greetingMeta.morning; icon = "☀️";  sub = greetingMeta.subMorning; }
  else if (h >= 12 && h < 14) { salutation = greetingMeta.noon;    icon = "🌤️"; sub = greetingMeta.subNoon; }
  else if (h >= 14 && h < 18) { salutation = greetingMeta.day;     icon = "🌤️"; sub = greetingMeta.subDay; }
  else if (h >= 18 && h < 22) { salutation = greetingMeta.evening; icon = "🌆";  sub = greetingMeta.subEvening; }
  else                         { salutation = greetingMeta.night;   icon = "🌙";  sub = greetingMeta.subNight; }

  const firstName = (user.name || user.username || "").split(" ")[0];
  const fullSalutation = firstName ? `${salutation}, ${firstName}!` : `${salutation}!`;

  // Laufleiste Dauer setzen
  el.style.setProperty("--greet-duration", `${GREET_DISPLAY_MS / 1000}s`);

  const iconEl = document.getElementById("greetIcon");
  const salEl  = document.getElementById("greetSalutation");
  const subEl  = document.getElementById("greetSub");
  if (iconEl)  iconEl.textContent  = icon;
  if (salEl)   salEl.textContent   = fullSalutation;
  if (subEl)   subEl.textContent   = sub;

  el.classList.remove("hidden", "fade-out");

  // Text-to-Speech (Web Speech API) – spricht in der jeweiligen UI-Sprache
  try {
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
      const ttsText = `${salutation}${firstName ? ", " + firstName : ""}!`;
      const ttsLang = greetingMeta.ttsLang;

      function speakWithVoice() {
        const utter = new SpeechSynthesisUtterance(ttsText);
        utter.lang   = ttsLang;
        utter.volume = 0.7;
        utter.rate   = 0.92;
        utter.pitch  = 1.15;
        const voices = window.speechSynthesis.getVoices();
        const prefix = ttsLang.split("-")[0].toLowerCase();

        const femaleKeywords = /female|frau|woman|féminin|feminine|zira|sabina|anna|lekha|helena|susan|karen|victoria|moira|samantha|ava|alice|amelie|céline|celine|hazel|heera|nora|laura|lucia|mia|paulina|kendra|joana|microsoft.*zira|google.*female/i;
        function isFemale(v) { return femaleKeywords.test(v.name); }

        // Prüfen ob für die gewünschte Sprache überhaupt eine Stimme existiert
        const langAvailable = voices.some((v) => v.lang.toLowerCase().startsWith(prefix));

        let preferred;
        if (langAvailable) {
          // Normale Auswahl: weiblich > lokal > beliebig in der Zielsprache
          preferred =
            voices.find((v) => isFemale(v) && v.lang.toLowerCase() === ttsLang.toLowerCase() && v.localService) ||
            voices.find((v) => isFemale(v) && v.lang.toLowerCase().startsWith(prefix) && v.localService) ||
            voices.find((v) => isFemale(v) && v.lang.toLowerCase() === ttsLang.toLowerCase()) ||
            voices.find((v) => isFemale(v) && v.lang.toLowerCase().startsWith(prefix)) ||
            voices.find((v) => v.lang.toLowerCase() === ttsLang.toLowerCase() && v.localService) ||
            voices.find((v) => v.lang.toLowerCase().startsWith(prefix) && v.localService) ||
            voices.find((v) => v.lang.toLowerCase().startsWith(prefix));
        } else {
          // Zielsprache nicht verfügbar → Fallback: weibliche Englisch-Stimme
          utter.lang = "en-GB";
          preferred =
            voices.find((v) => isFemale(v) && v.lang.toLowerCase().startsWith("en") && v.localService) ||
            voices.find((v) => isFemale(v) && v.lang.toLowerCase().startsWith("en")) ||
            voices.find((v) => v.lang.toLowerCase().startsWith("en") && v.localService) ||
            voices.find((v) => v.lang.toLowerCase().startsWith("en")) ||
            voices.find((v) => isFemale(v) && v.localService) ||
            voices.find((v) => isFemale(v));
        }
        if (preferred) utter.voice = preferred;
        window.speechSynthesis.speak(utter);
      }

      const voices = window.speechSynthesis.getVoices();
      if (voices.length > 0) {
        speakWithVoice();
      } else {
        window.speechSynthesis.addEventListener("voiceschanged", function onVoicesReady() {
          window.speechSynthesis.removeEventListener("voiceschanged", onVoicesReady);
          speakWithVoice();
        });
        // Fallback: nach 1s prüfen ob Stimmen jetzt da sind, sonst Jingle
        setTimeout(() => {
          if (!window.speechSynthesis.speaking) {
            if (window.speechSynthesis.getVoices().length > 0) {
              speakWithVoice();
            } else {
              // Keine Stimmen verfügbar → kurzen Jingle über AudioContext abspielen
              playGreetingJingle();
            }
          }
        }, 1000);
      }
    }
  } catch {
    // Kein TTS verfügbar – Jingle als Fallback
    try { playGreetingJingle(); } catch { /* ignore */ }
  }

  // Nach GREET_DISPLAY_MS ausblenden
  setTimeout(() => {
    el.classList.add("fade-out");
    setTimeout(() => el.classList.add("hidden"), 600);
  }, GREET_DISPLAY_MS);
}

// ── Device Management ────────────────────────────────────────────────────────
const _deviceRefreshTimers = {};

async function loadDevices() {
  const user = state.currentUser;
  if (!user || !["superadmin", "company-admin"].includes(user.role)) return;
  try {
    const data = await apiRequest(`${API_BASE}/api/admin/devices`);
    state.devices = Array.isArray(data) ? data : (data.devices || []);
    renderDevices();
  } catch (e) {
    console.warn("loadDevices failed", e);
  }
}

function renderDevices() {
  const list = elements.deviceStatusList;
  if (!list) return;
  const devices = state.devices || [];
  if (!devices.length) {
    list.innerHTML = `<p class="empty-state" style="padding:1rem;">${escapeHtml("Noch keine Geräte registriert.")}</p>`;
    return;
  }
  list.innerHTML = devices.map(d => {
    const ago = d.lastSeenAt ? Math.round((Date.now() - new Date(d.lastSeenAt).getTime()) / 1000) : null;
    const statusLabel = d.online
      ? (uiT("deviceOnline") || "Online")
      : ago === null ? (uiT("deviceNeverSeen") || "Noch kein Heartbeat") : (uiT("deviceOffline") || "Offline");
    const dotClass = d.online ? "device-dot online" : "device-dot offline";
    const agoText = ago !== null ? ` · ${ago < 60 ? ago + "s" : Math.round(ago/60) + "min"} ago` : "";
    return `<div class="device-status-item" data-device-id="${escapeHtml(d.id)}">
      <span class="${dotClass}"></span>
      <span class="device-name">${escapeHtml(d.name)}</span>
      <span class="device-meta">${escapeHtml(d.location)}${agoText}</span>
      <span class="device-badge">${escapeHtml(statusLabel)}</span>
      <button class="ghost-button" style="margin-left:auto;color:#dc2626;font-size:.8rem;" onclick="deleteDevice('${escapeHtml(d.id)}')">✕</button>
    </div>`;
  }).join("");
}

async function deleteDevice(id) {
  if (!confirm("Gerät wirklich löschen?")) return;
  try {
    await apiRequest(`${API_BASE}/api/admin/devices/${encodeURIComponent(id)}`, { method: "DELETE" });
    state.devices = (state.devices || []).filter(d => d.id !== id);
    renderDevices();
  } catch (e) {
    alert(uiT("alertDeviceDeleteFailed").replace("{error}", e.message || e));
  }
}

// Wire device form (delegated, called once on page load)
(function wireDeviceForm() {
  const form = document.getElementById("deviceForm");
  const keyResult = document.getElementById("deviceApiKeyResult");
  if (!form) return;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = (document.getElementById("deviceName")?.value || "").trim();
    const location = (document.getElementById("deviceLocation")?.value || "").trim();
    const deviceType = document.getElementById("deviceType")?.value || "osdp";
    if (!name) return;
    try {
      const res = await apiRequest(`${API_BASE}/api/admin/devices`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, location, deviceType }),
      });
      if (keyResult) {
        const createdKey = res?.apiKey || res?.device?.apiKey || "";
        keyResult.classList.remove("hidden");
        keyResult.innerHTML = `<strong>API-Schlüssel (nur einmal sichtbar):</strong><br><code style="word-break:break-all;">${escapeHtml(createdKey || "-")}</code>`;
      }
      form.reset();
      await loadDevices();
    } catch (err) {
      alert(uiT("alertGenericError").replace("{error}", err.message || err));
    }
  });
})();

// Auto-refresh devices every 30s when devices view is active
setInterval(() => {
  if (getCurrentViewName && getCurrentViewName() === "devices") {
    loadDevices();
  }
}, 30000);

// ── Print Badge ──────────────────────────────────────────────────────────────
function printBadge(worker, company) {
  // Vorherige Druck-Container entfernen
  document.querySelectorAll(".print-badge-root").forEach((el) => el.remove());

  const preview = document.getElementById("badgePreview");
  if (!preview) return;

  // Badge-Inhalt in Druck-Overlay klonen (nutzt dieselben Styles wie die App)
  const root = document.createElement("div");
  root.className = "print-badge-root";
  root.innerHTML = `<div class="badge-shell">${preview.innerHTML}</div>`;
  document.body.appendChild(root);

  // Auf alle Bilder (insbesondere QR-Code) warten bevor gedruckt wird
  const images = Array.from(root.querySelectorAll("img"));
  const loadPromises = images.map((img) => {
    if (img.complete && img.naturalWidth > 0) return Promise.resolve();
    return new Promise((resolve) => {
      img.onload = resolve;
      img.onerror = resolve;
      setTimeout(resolve, 5000); // Fallback nach 5s
    });
  });

  Promise.all(loadPromises).then(() => {
    window.print();
    // Nach dem Drucken (oder Abbrechen) aufräumen
    setTimeout(() => root.remove(), 2500);
  });
}

function normalizeWorkerCardStatus(status) {
  const normalized = String(status || "aktiv").trim().toLowerCase();
  if (!normalized) {
    return "aktiv";
  }
  return normalized;
}

function getWorkerCardRoleLabel(worker) {
  if (isVisitorWorker(worker)) {
    return uiT("optVisitor");
  }
  return worker.role || "Mitarbeiter";
}

function getWorkerCardPassSubLabel(worker) {
  return isVisitorWorker(worker) ? "Besucherkarte" : "Mitarbeiterausweis";
}

function buildPrintableWorkerCardMarkup(worker, company) {
  const safeBadgePhoto = sanitizeImageSrc(worker.photoData, createAvatar(worker));
  const normalizedStatus = normalizeWorkerCardStatus(worker.status);
  const subcompanyLabel = getSubcompanyLabel(worker);
  const validUntilLabel = formatDate(worker.validUntil);
  const passSubLabel = getWorkerCardPassSubLabel(worker);
  const roleLabel = getWorkerCardRoleLabel(worker);
  const companyName = company?.name || uiT("badgeUnknownCompany");

  return `
    <article class="wallet-card" data-status="${escapeHtml(normalizedStatus)}">
      <div class="wc-shimmer"></div>
      <div class="wc-grid"></div>

      <!-- Top: Marke + NFC -->
      <div class="wc-top">
        <div class="wc-brand">
          <div class="wc-brand-mark">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M3 17L12 4l9 13H3z" fill="#fff" fill-opacity=".9"/>
              <rect x="7" y="17" width="10" height="4" rx="1" fill="#fff" fill-opacity=".7"/>
              <rect x="10" y="13" width="4" height="4" fill="#fff" fill-opacity=".5"/>
            </svg>
          </div>
          <div class="wc-brand-text">
            <span class="wc-brand-name">BAUPASS</span>
            <span class="wc-brand-sub">${escapeHtml(passSubLabel)}</span>
          </div>
        </div>

        <svg class="wc-nfc" width="26" height="26" viewBox="0 0 26 26" fill="none" aria-hidden="true">
          <path d="M4 13a9 9 0 019-9" stroke="rgba(255,255,255,.75)" stroke-width="2.2" stroke-linecap="round"/>
          <path d="M7.5 13a5.5 5.5 0 015.5-5.5" stroke="rgba(255,255,255,.55)" stroke-width="2.2" stroke-linecap="round"/>
          <path d="M11 13a2 2 0 012-2" stroke="rgba(255,255,255,.4)" stroke-width="2.2" stroke-linecap="round"/>
          <circle cx="13" cy="13" r="1.2" fill="rgba(255,255,255,.6)"/>
        </svg>
      </div>

      <!-- Mitte: QR-Chip + Foto -->
      <div class="wc-middle">
        <div class="wc-qr-holder">
          <div class="wc-qr-frame" aria-hidden="true"></div>
          <img id="badge-card-qr-${escapeHtml(worker.id)}" class="badge-wallet-qr" alt="QR Code" />
        </div>
        <img class="wc-photo" src="${safeBadgePhoto}" alt="${escapeHtml(worker.firstName)} ${escapeHtml(worker.lastName)}" />
      </div>

      <!-- Unten: Name + Felder -->
      <div class="wc-bottom">
        <p class="wc-name">${escapeHtml(`${worker.firstName || ""} ${worker.lastName || ""}`.trim())}</p>
        <p class="wc-role-text">${escapeHtml(roleLabel)}</p>
        <div class="wc-footer">
          <div class="wc-fields">
            <div class="wc-field">
              <span class="wc-field-label">Badge-ID</span>
              <span class="wc-field-value">${escapeHtml(worker.badgeId || "-")}</span>
            </div>
            <div class="wc-field">
              <span class="wc-field-label">Gueltig bis</span>
              <span class="wc-field-value">${escapeHtml(validUntilLabel || "-")}</span>
            </div>
          </div>
          <div class="wc-right">
            <div class="wc-status" data-status="${escapeHtml(normalizedStatus)}">${escapeHtml(worker.status || "aktiv")}</div>
            <p class="wc-company">${escapeHtml(companyName)}</p>
            ${subcompanyLabel ? `<p class="wc-subcompany">${escapeHtml(subcompanyLabel)}</p>` : ""}
          </div>
        </div>
      </div>
    </article>
  `;
}

function renderSystemAlertBanner(loggedIn) {
  if (!elements.systemAlertBanner || !elements.systemAlertText || !elements.systemAlertActionBtn) {
    return;
  }

  if (!loggedIn) {
    elements.systemAlertBanner.style.display = "none";
    return;
  }

  const role = String(getCurrentUser()?.role || "").toLowerCase();
  if (role !== "superadmin") {
    elements.systemAlertBanner.style.display = "none";
    return;
  }

  const criticalIds = getCriticalRetryInvoiceIds(state.invoices, 50);
  const criticalCount = criticalIds.length;
  if (criticalCount < 10) {
    elements.systemAlertBanner.style.display = "none";
    return;
  }

  elements.systemAlertText.textContent = `${criticalCount} kritische Rechnungs-Fehlversände (Score >= 70) erfordern Aufmerksamkeit.`;
  elements.systemAlertActionBtn.textContent = `Rechnungen öffnen (${criticalCount})`;
  elements.systemAlertBanner.style.display = "flex";
  elements.systemAlertBanner.classList.remove("system-alert-banner-warn", "system-alert-banner-alert");
  if (criticalCount >= 20) {
    elements.systemAlertBanner.classList.add("system-alert-banner-alert");
  } else {
    elements.systemAlertBanner.classList.add("system-alert-banner-warn");
  }
}

function renderCompliancePanel() {
  if (!elements.compliancePanel) return;
  const items = Array.isArray(state.complianceOverview) ? state.complianceOverview : [];
  if (!items.length) {
    elements.compliancePanel.innerHTML = '<div class="card-item"><p class="muted">Keine Compliance-Daten geladen.</p></div>';
    return;
  }
  elements.compliancePanel.innerHTML = items.map((company) => {
    const criticalWorkers = (company.workers || []).filter((worker) => worker.overall === "red").slice(0, 6);
    return `
      <article class="card-item">
        <div style="display:flex; justify-content:space-between; gap:12px; align-items:flex-start;">
          <div>
            <strong>${escapeHtml(company.companyName || "Firma")}</strong>
            <p class="helper-text">Gruen ${Number(company.greenCount || 0)} | Gelb ${Number(company.yellowCount || 0)} | Rot ${Number(company.redCount || 0)}</p>
          </div>
        </div>
        ${criticalWorkers.length ? `<div class="meta-box">${criticalWorkers.map((worker) => `<span>• ${escapeHtml(worker.name || "Mitarbeiter")}: ${Object.entries(worker.docs || {}).filter(([, value]) => value !== "ok").map(([key, value]) => `${escapeHtml(key)}=${escapeHtml(value)}`).join(", ")}</span>`).join("")}</div>` : '<p class="helper-text helper-text-ok">Keine kritischen Dokumentluecken.</p>'}
      </article>
    `;
  }).join("");
}

function renderAuditLogPanel() {
  if (!elements.auditLogPanel) return;
  const logs = Array.isArray(state.auditLogs) ? state.auditLogs : [];
  if (!logs.length) {
    elements.auditLogPanel.innerHTML = '<div class="card-item"><p class="muted">Keine Audit-Eintraege vorhanden.</p></div>';
    return;
  }
  elements.auditLogPanel.innerHTML = `
    <article class="card-item">
      ${logs.slice(0, 20).map((entry) => `<div style="padding:8px 0; border-bottom:1px solid rgba(0,0,0,0.08);">
        <strong>${escapeHtml(entry.event_type || "event")}</strong>
        <span class="muted" style="display:block; font-size:0.84em;">${escapeHtml(formatTimestamp(entry.created_at || ""))}</span>
        <span>${escapeHtml(entry.message || "")}</span>
      </div>`).join("")}
    </article>
  `;
}

function ensureInvoiceDefaults() {
  const invoiceDateField = document.querySelector("#invoiceDate");
  const invoiceDueDateField = document.querySelector("#invoiceDueDate");
  const invoicePeriodField = document.querySelector("#invoicePeriod");
  if (invoiceDateField && !invoiceDateField.value) {
    invoiceDateField.value = new Date().toISOString().slice(0, 10);
  }
  if (invoiceDueDateField && !invoiceDueDateField.value) {
    const base = invoiceDateField?.value ? new Date(`${invoiceDateField.value}T00:00:00`) : new Date();
    const due = new Date(base.getTime() + (14 * 24 * 60 * 60 * 1000));
    invoiceDueDateField.value = due.toISOString().slice(0, 10);
  }
  if (invoicePeriodField && !invoicePeriodField.value) {
    const now = new Date();
    const first = new Date(now.getFullYear(), now.getMonth(), 1);
    const last = new Date(now.getFullYear(), now.getMonth() + 1, 0);
    const format = (d) => `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}.${d.getFullYear()}`;
    invoicePeriodField.value = `${format(first)} - ${format(last)}`;
  }
}

function updateTopbarActionsState(loggedIn) {
  const role = getCurrentUser()?.role || "";
  const canWrite = !isSupportReadOnlyMode();
  const canSeed = (role === "superadmin" || role === "company-admin") && canWrite;

  if (elements.seedDataButton) {
    elements.seedDataButton.style.display = loggedIn ? "inline-flex" : "none";
    elements.seedDataButton.disabled = !canSeed;
    elements.seedDataButton.title = canSeed ? "" : "Nur für Admin-Rollen";
  }

  if (elements.exportButton) {
    const canExport = (role === "superadmin" || role === "company-admin") && canWrite;
    elements.exportButton.style.display = loggedIn && canExport ? "inline-flex" : "none";
    elements.exportButton.disabled = !canExport;
    elements.exportButton.title = canExport ? "" : "Nur für Admin-Rollen";
  }

  if (elements.importButton) {
    const canImport = (role === "superadmin" || role === "company-admin") && canWrite;
    elements.importButton.style.display = loggedIn && canImport ? "inline-flex" : "none";
    elements.importButton.disabled = !canImport;
    elements.importButton.title = canImport ? "" : "Nur für Admin-Rollen";
  }

  if (elements.logoutButton) {
    elements.logoutButton.style.display = loggedIn ? "inline-flex" : "none";
    elements.logoutButton.disabled = false;
  }
}

async function clearSuperadminPreviewMode({ refresh = true } = {}) {
  superadminUiPreviewCompanyId = "";
  companyBrandingPreviewOverride = "";
  try {
    await apiRequest(API_BASE + "/api/superadmin/preview-session", { method: "POST", body: { company_id: null } });
  } catch (e) {
    console.warn("[preview] Fehler beim Beenden der Vorschau-Session:", e);
  }
  if (refresh) {
    refreshAll();
  }
}

async function setSuperadminPreviewCompany(companyId, { refresh = true } = {}) {
  const selectedCompanyId = String(companyId || "").trim();
  superadminUiPreviewCompanyId = selectedCompanyId;
  companyBrandingPreviewOverride = "";
  const company = state.companies.find((entry) => String(entry?.id || "") === selectedCompanyId);
  if (company) {
    companyBrandingPreviewOverride = getCompanyBrandingPreset(company);
  }
  try {
    await apiRequest(API_BASE + "/api/superadmin/preview-session", { method: "POST", body: { company_id: selectedCompanyId || null } });
  } catch (e) {
    console.warn("[preview] Fehler beim Setzen der Vorschau-Session:", e);
  }
  if (refresh) {
    refreshAll();
  }
}

function renderSuperadminPreviewTopbar(loggedIn) {
  const topbarActions = document.querySelector(".topbar-actions");
  if (!topbarActions) {
    return;
  }

  let previewPill = document.querySelector("#superadminPreviewTopbarPill");
  const previewActive = loggedIn && isSuperadminCompanyPreviewMode();
  if (!previewActive) {
    if (previewPill) {
      previewPill.remove();
    }
    return;
  }

  if (!previewPill) {
    previewPill = document.createElement("div");
    previewPill.id = "superadminPreviewTopbarPill";
    previewPill.className = "superadmin-preview-pill";

    const label = document.createElement("span");
    label.id = "superadminPreviewTopbarLabel";
    label.className = "superadmin-preview-pill-label";
    previewPill.appendChild(label);

    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.className = "ghost-button small-button superadmin-preview-pill-close";
    closeButton.textContent = "Vorschau beenden";
    closeButton.addEventListener("click", () => clearSuperadminPreviewMode());
    previewPill.appendChild(closeButton);

    const logoutButton = elements.logoutButton && topbarActions.contains(elements.logoutButton)
      ? elements.logoutButton
      : null;
    if (logoutButton) {
      topbarActions.insertBefore(previewPill, logoutButton);
    } else {
      topbarActions.appendChild(previewPill);
    }
  }

  const previewCompany = state.companies.find((entry) => String(entry?.id || "") === String(superadminUiPreviewCompanyId || ""));
  const labelText = previewCompany?.name
    ? `Vorschau aktiv: ${previewCompany.name}`
    : "Vorschau aktiv";
  const labelNode = document.querySelector("#superadminPreviewTopbarLabel");
  if (labelNode) {
    labelNode.textContent = labelText;
  }
}

function renderSuperadminSimulationBar(loggedIn) {
  const content = document.querySelector(".content");
  if (!content) {
    return;
  }

  let simulationBar = document.querySelector("#superadminSimulationBar");
  const previewActive = loggedIn && isSuperadminCompanyPreviewMode();
  if (!previewActive) {
    if (simulationBar) {
      simulationBar.remove();
    }
    return;
  }

  const previewCompany = state.companies.find((entry) => String(entry?.id || "") === String(superadminUiPreviewCompanyId || ""));
  const previewCompanyName = String(previewCompany?.name || "Firma");
  const previewPreset = getCompanyBrandingPreset(previewCompany);
  const previewPresetLabel = getCompanyBrandingPresetLabel(previewPreset);

  if (!simulationBar) {
    simulationBar = document.createElement("div");
    simulationBar.id = "superadminSimulationBar";
    simulationBar.className = "superadmin-simulation-bar";
    simulationBar.setAttribute("role", "status");
    simulationBar.setAttribute("aria-live", "polite");

    const main = document.createElement("div");
    main.className = "superadmin-simulation-main";
    main.innerHTML = `
      <strong id="superadminSimulationBarTitle">Simulation aktiv</strong>
      <span id="superadminSimulationBarMeta">Firmenansicht</span>
    `;
    simulationBar.appendChild(main);

    const actions = document.createElement("div");
    actions.className = "superadmin-simulation-actions";

    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.className = "ghost-button small-button superadmin-simulation-close";
    closeButton.textContent = "Vorschau beenden";
    closeButton.addEventListener("click", () => clearSuperadminPreviewMode());
    actions.appendChild(closeButton);

    simulationBar.appendChild(actions);

    const insertBeforeTarget = elements.systemAlertBanner && content.contains(elements.systemAlertBanner)
      ? elements.systemAlertBanner
      : content.querySelector(".view");
    if (insertBeforeTarget) {
      content.insertBefore(simulationBar, insertBeforeTarget);
    } else {
      content.appendChild(simulationBar);
    }
  }

  simulationBar.classList.remove("simulation-construction", "simulation-industry", "simulation-premium");
  simulationBar.classList.add(`simulation-${previewPreset}`);

  const titleNode = document.querySelector("#superadminSimulationBarTitle");
  const metaNode = document.querySelector("#superadminSimulationBarMeta");
  if (titleNode) {
    titleNode.textContent = "Simulation aktiv";
  }
  if (metaNode) {
    metaNode.textContent = `Firmenansicht: ${previewCompanyName} (${previewPresetLabel})`;
  }
}

function renderSuperadminPreviewSidebarStatus(loggedIn) {
  const sidebarCard = document.querySelector(".sidebar-card");
  if (!sidebarCard) {
    return;
  }

  let sidebarStatus = document.querySelector("#superadminSidebarPreviewStatus");
  const previewActive = loggedIn && isSuperadminCompanyPreviewMode();
  if (!previewActive) {
    if (sidebarStatus) {
      sidebarStatus.remove();
    }
    return;
  }

  const previewCompany = state.companies.find((entry) => String(entry?.id || "") === String(superadminUiPreviewCompanyId || ""));
  const previewCompanyName = String(previewCompany?.name || "Firma");
  const previewPreset = getCompanyBrandingPreset(previewCompany);

  if (!sidebarStatus) {
    sidebarStatus = document.createElement("div");
    sidebarStatus.id = "superadminSidebarPreviewStatus";
    sidebarStatus.className = "superadmin-sidebar-preview-status";
    sidebarStatus.innerHTML = `
      <span class="superadmin-sidebar-preview-dot" aria-hidden="true"></span>
      <div class="superadmin-sidebar-preview-main">
        <strong id="superadminSidebarPreviewTitle">Simulation laeuft</strong>
        <span id="superadminSidebarPreviewMeta">Firmenansicht</span>
      </div>
      <button type="button" class="ghost-button small-button superadmin-sidebar-preview-close" id="superadminSidebarPreviewClose">Beenden</button>
    `;
    sidebarCard.appendChild(sidebarStatus);

    const closeButton = document.querySelector("#superadminSidebarPreviewClose");
    if (closeButton) {
      closeButton.addEventListener("click", () => clearSuperadminPreviewMode());
    }
  }

  sidebarStatus.classList.remove("sidebar-simulation-construction", "sidebar-simulation-industry", "sidebar-simulation-premium");
  sidebarStatus.classList.add(`sidebar-simulation-${previewPreset}`);

  const titleNode = document.querySelector("#superadminSidebarPreviewTitle");
  const metaNode = document.querySelector("#superadminSidebarPreviewMeta");
  if (titleNode) {
    titleNode.textContent = "Simulation laeuft";
  }
  if (metaNode) {
    metaNode.textContent = previewCompanyName;
  }
}

function renderStats() {
  if (!elements.statsGrid) return;
  const texts = getRuntimeUiTexts();
  const visibleWorkers = getUiVisibleWorkers();
  const visibleLogs = getUiVisibleAccessLogs();
  const scopedCompanyId = getEffectiveUiCompanyId();

  const totalWorkers = visibleWorkers.filter((w) => !w.deletedAt).length;
  const activeWorkers = visibleWorkers.filter((w) => !w.deletedAt && w.status === "aktiv").length;
  const totalVisitors = visibleWorkers.filter((w) => !w.deletedAt && isVisitorWorker(w)).length;
  const totalCompanies = scopedCompanyId ? 1 : state.companies.filter((c) => !c.deleted_at).length;
  const today = new Date().toISOString().slice(0, 10);
  const todayLogs = visibleLogs.filter((log) => String(log.timestamp || "").slice(0, 10) === today);
  // Nur Mitarbeiter zählen, die aktuell noch auf der Baustelle sind:
  // letzter Eintrag des Tages muss "check-in" sein (nicht check-out).
  const lastLogByWorker = {};
  for (const log of todayLogs) {
    const wid = log.workerId || log.worker_id || "";
    if (!wid) continue;
    if (!lastLogByWorker[wid] || log.timestamp > lastLogByWorker[wid].timestamp) {
      lastLogByWorker[wid] = log;
    }
  }
  const accessToday = Object.values(lastLogByWorker).filter((log) => log.direction === "check-in").length;

  const cards = [
    [texts.statsWorkersTotal, totalWorkers],
    [texts.statsWorkersActive, activeWorkers],
    [texts.statsVisitorsTotal, totalVisitors],
    [texts.statsCompanies, totalCompanies],
    [texts.statsAccessToday, accessToday]
  ];

  elements.statsGrid.innerHTML = cards
    .map(([label, value]) => `<article class="stat-card"><p>${escapeHtml(label)}</p><strong>${escapeHtml(String(value))}</strong></article>`)
    .join("");
}

function formatCurrencyEur(value) {
  const numeric = Number(value || 0);
  return new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(Number.isFinite(numeric) ? numeric : 0);
}

function renderReportingPanels() {
  const summaryGrid = elements.reportingSummaryGrid;
  const topOverdueList = elements.reportingTopOverdueList;
  const accessDailyList = elements.reportingAccessDaily;
  const reportingPanels = document.querySelector("#reportingPanels");
  if (!summaryGrid || !topOverdueList || !accessDailyList) {
    return;
  }

  const role = String(getEffectiveUiRole() || "").toLowerCase();
  if (role !== "superadmin") {
    if (reportingPanels) {
      reportingPanels.style.display = "none";
    }
    summaryGrid.innerHTML = "";
    topOverdueList.innerHTML = "";
    accessDailyList.innerHTML = "";
    return;
  }

  if (reportingPanels) {
    reportingPanels.style.display = "grid";
  }

  const kpis = state.reporting?.kpis || {};
  const generatedAt = state.reporting?.generatedAt || "";
  const summaryCards = [
    [uiT("reportingPaid"), formatCurrencyEur(kpis.paidTotal)],
    [uiT("reportingOpen"), formatCurrencyEur(kpis.openTotal)],
    [uiT("reportingOverdue"), `${Number(kpis.overdueInvoiceCount || 0)} ${uiT("reportingInvoicesLabel")}`],
    [uiT("reportingOverdueTotal"), formatCurrencyEur(kpis.overdueTotal)],
    [uiT("reportingLockedCompanies"), String(Number(kpis.lockedCompanies || 0))],
    [uiT("reportingAutoSuspensions30d"), String(Number(kpis.suspensionsLast30d || 0))]
  ];

  summaryGrid.innerHTML = summaryCards
    .map(([label, value]) => `
      <article class="card-item">
        <p class="helper-text">${escapeHtml(label)}</p>
        <strong>${escapeHtml(String(value))}</strong>
      </article>
    `)
    .join("") + (generatedAt ? `<p class="helper-text">${escapeHtml(uiT("reportingGeneratedAt"))}: ${escapeHtml(formatTimestamp(generatedAt))}</p>` : "");

  const topCompanies = state.reporting?.topOverdueCompanies || [];
  if (!topCompanies.length) {
    topOverdueList.innerHTML = `<div class="empty-state">${escapeHtml(uiT("reportingNoOverdueCompanies"))}</div>`;
  } else {
    topOverdueList.innerHTML = topCompanies
      .map((entry) => `
        <article class="card-item">
          <strong>${escapeHtml(entry.companyName || uiT("reportingFallbackCompany"))}</strong>
          <p class="helper-text">${Number(entry.overdueCount || 0)} ${escapeHtml(uiT("reportingOverdueInvoicesLabel"))}</p>
          <p>${escapeHtml(formatCurrencyEur(entry.overdueTotal))}</p>
        </article>
      `)
      .join("");
  }

  const dailyRows = state.reporting?.accessDaily || [];
  if (!dailyRows.length) {
    accessDailyList.innerHTML = `<div class="empty-state">${escapeHtml(uiT("reportingNoAccessDataLast7Days"))}</div>`;
  } else {
    const maxDaily = Math.max(
      ...dailyRows.map((entry) => Number(entry.checkIn || 0) + Number(entry.checkOut || 0)),
      1
    );

    accessDailyList.innerHTML = dailyRows
      .map((entry) => {
        const checkIn = Number(entry.checkIn || 0);
        const checkOut = Number(entry.checkOut || 0);
        const inWidth = Math.max(3, Math.round((checkIn / maxDaily) * 100));
        const outWidth = Math.max(3, Math.round((checkOut / maxDaily) * 100));
        return `
        <article class="card-item">
          <strong>${escapeHtml(formatDate(entry.day))}</strong>
          <p class="helper-text">${escapeHtml(uiT("reportingCheckin"))}: ${escapeHtml(String(checkIn))}</p>
          <div style="height:8px; background:#e6edf2; border-radius:6px; overflow:hidden; margin:4px 0 8px;">
            <div style="height:100%; width:${inWidth}%; background:#0f7a5a;"></div>
          </div>
          <p class="helper-text">${escapeHtml(uiT("reportingCheckout"))}: ${escapeHtml(String(checkOut))}</p>
          <div style="height:8px; background:#e6edf2; border-radius:6px; overflow:hidden; margin:4px 0 0;">
            <div style="height:100%; width:${outWidth}%; background:#4c6faf;"></div>
          </div>
        </article>
      `;
      })
      .join("");
  }
}

function renderWorkerList() {
  if (!elements.workerList) return;
  const searchTerm = ((elements.workerSearchInput?.value) || "").trim().toLowerCase();
  const workers = getUiVisibleWorkers()
    .filter((w) => {
      if (!searchTerm) return true;
      const hay = [w.firstName, w.lastName, w.badgeId, w.site, w.role, w.status, w.visitorCompany].join(" ").toLowerCase();
      return hay.includes(searchTerm);
    })
    .sort((a, b) => `${a.lastName} ${a.firstName}`.localeCompare(`${b.lastName} ${b.firstName}`));

  if (!workers.length) {
    const emptyText = searchTerm
      ? runtimeTextTemplate("workerListNoResults", { term: escapeHtml(searchTerm) })
      : runtimeText("workerListEmpty");
    elements.workerList.innerHTML = `<div class="empty-state">${emptyText}</div>`;
    return;
  }

  elements.workerList.innerHTML = workers
    .map((worker) => {
      const deleted = Boolean(worker.deletedAt);
      const sub = getSubcompanyLabel(worker);
      const visitor = isVisitorWorker(worker);
      const lockReason = String(worker.lockReason || "").trim();
      const visitorMeta = visitor
        ? `<p>${uiT("labelVisitorCompany")}: <strong>${escapeHtml(worker.visitorCompany || "-")}</strong> | ${uiT("labelVisitPurpose")}: <strong>${escapeHtml(worker.visitPurpose || "-")}</strong></p>
          <p>${uiT("labelHostName")}: <strong>${escapeHtml(worker.hostName || "-")}</strong> | ${uiT("labelVisitEndAt")}: <strong>${escapeHtml(worker.visitEndAt ? formatTimestamp(worker.visitEndAt) : "-")}</strong></p>`
        : "";
      return `
        <article class="card-item ${deleted ? "is-deleted" : ""}">
          <header>
            <div>
              <input type="checkbox" class="bulk-checkbox" data-bulk-id="${escapeHtml(worker.id)}" />
              <strong>${escapeHtml(worker.firstName)} ${escapeHtml(worker.lastName)}</strong>
              <span>${escapeHtml(worker.badgeId || "-")}</span>
            </div>
            <span class="status-pill">${escapeHtml(worker.status || "-")}</span>
          </header>
          <p>${escapeHtml(visitor ? uiT("optVisitor") : (worker.role || "-"))} | ${escapeHtml(worker.site || "-")}</p>
          <p>${uiT("appPinLabel")}: <strong>${visitor ? uiT("pinNotRequired") : (worker.badgePinConfigured ? uiT("pinSet") : uiT("pinMissing"))}</strong> | ${uiT("cardLabel")}: <strong>${escapeHtml(worker.physicalCardId || uiT("cardUnassigned"))}</strong></p>
          ${sub ? `<p>Subunternehmen: ${escapeHtml(sub)}</p>` : ""}
          ${lockReason ? `<p class="helper-text helper-text-warning"><strong>Sperrgrund:</strong> ${escapeHtml(lockReason)}</p>` : ""}
          ${visitorMeta}
          <div class="button-row">
            <button type="button" class="ghost-button" data-worker-edit="${escapeHtml(worker.id)}" ${deleted ? "disabled" : ""}>${uiT("btnEdit")}</button>
            <button type="button" class="ghost-button" data-worker-delete="${escapeHtml(worker.id)}" ${deleted ? "disabled" : ""}>${uiT("btnDelete")}</button>
            <button type="button" class="ghost-button" data-worker-restore="${escapeHtml(worker.id)}" ${deleted ? "" : "disabled"}>${uiT("btnRestore")}</button>
            <button type="button" class="ghost-button" data-worker-app-link="${escapeHtml(worker.id)}" ${deleted ? "disabled" : ""}>${uiT("btnAppLink")}</button>
            ${!visitor && !deleted ? `<button type="button" class="ghost-button" data-worker-reset-pin="${escapeHtml(worker.id)}">${uiT("btnResetPin")}</button>` : ""}
          </div>
        </article>
      `;
    })
    .join("");

  bindWorkerRowActions();
}

function bindWorkerRowActions() {

  // Delegate checkbox changes to update bulk bar
  elements.workerList.addEventListener("change", (e) => {
    if (e.target.classList.contains("bulk-checkbox")) {
      updateBulkActionBar();
      // Sync "select all" state
      const all = elements.workerList.querySelectorAll(".bulk-checkbox");
      const checked = elements.workerList.querySelectorAll(".bulk-checkbox:checked");
      if (elements.bulkSelectAll) {
        elements.bulkSelectAll.indeterminate = checked.length > 0 && checked.length < all.length;
        elements.bulkSelectAll.checked = checked.length === all.length && all.length > 0;
      }
    }
  });
  elements.workerList.querySelectorAll("[data-worker-edit]").forEach((button) => {
    button.onclick = () => {
      const worker = state.workers.find((entry) => entry.id === button.dataset.workerEdit);
      if (!worker || worker.deletedAt) return;
      state.editingWorkerId = worker.id;
      if (elements.companySelect) elements.companySelect.value = worker.companyId;
      populateSubcompanySelects();
      document.querySelector("#subcompanySelect").value = worker.subcompanyId || "";
      document.querySelector("#firstName").value = worker.firstName || "";
      document.querySelector("#lastName").value = worker.lastName || "";
      document.querySelector("#insuranceNumber").value = worker.insuranceNumber || "";
      if (elements.workerType) elements.workerType.value = isVisitorWorker(worker) ? "visitor" : "worker";
      document.querySelector("#role").value = worker.role || "";
      document.querySelector("#site").value = worker.site || "";
      document.querySelector("#physicalCardId").value = worker.physicalCardId || "";
      document.querySelector("#validUntil").value = worker.validUntil || "";
      if (elements.visitorCompany) elements.visitorCompany.value = worker.visitorCompany || "";
      if (elements.visitPurpose) elements.visitPurpose.value = worker.visitPurpose || "";
      if (elements.hostName) elements.hostName.value = worker.hostName || "";
      if (elements.visitEndAt) elements.visitEndAt.value = worker.visitEndAt ? toDateTimeLocalValue(worker.visitEndAt) : "";
      document.querySelector("#workerStatus").value = worker.status || "aktiv";
      document.querySelector("#badgePin").value = "";
      setPhotoEditorSource(worker.photoData || "", { resetOffset: true });
      syncWorkerTypeUi();
      syncWorkerEditorUi();
      setView("workers");
    };
  });

  elements.workerList.querySelectorAll("[data-worker-delete]").forEach((button) => {
    button.onclick = async () => {
      if (!window.confirm(uiT("confirmDeleteWorker"))) return;
      try {
        await apiRequest(`${API_BASE}/api/workers/${button.dataset.workerDelete}`, { method: "DELETE" });
        await loadAllData();
        refreshAll();
      } catch (error) {
        window.alert(uiT("alertDeleteWorkerFailed").replace("{error}", error.message));
      }
    };
  });

  elements.workerList.querySelectorAll("[data-worker-restore]").forEach((button) => {
    button.onclick = async () => {
      try {
        await apiRequest(`${API_BASE}/api/workers/${button.dataset.workerRestore}/restore`, { method: "POST" });
        await loadAllData();
        refreshAll();
      } catch (error) {
        window.alert(uiT("alertRestoreWorkerFailed").replace("{error}", error.message));
      }
    };
  });

  elements.workerList.querySelectorAll("[data-worker-app-link]").forEach((button) => {
    button.onclick = async () => {
      try {
        const payload = await apiRequest(`${API_BASE}/api/workers/${button.dataset.workerAppLink}/app-access`, { method: "POST" });
        const absoluteLink = normalizeWorkerAppLink(payload.link);
        const worker = state.workers.find((entry) => entry.id === button.dataset.workerAppLink) || null;
        showWorkerAppQrDialog(worker, absoluteLink, payload);
      } catch (error) {
        window.alert(uiT("alertAppLinkCreateFailed").replace("{error}", error.message));
      }
    };
  });

  elements.workerList.querySelectorAll("[data-worker-reset-pin]").forEach((button) => {
    button.onclick = async () => {
      const workerId = button.dataset.workerResetPin;
      const worker = state.workers.find((w) => w.id === workerId);
      const name = worker ? `${worker.firstName} ${worker.lastName}` : workerId;
      const newPin = window.prompt(uiT("promptResetPinFor").replace("{name}", name));
      if (newPin === null) return; // abgebrochen
      if (!/^\d{4,8}$/.test(newPin.trim())) {
        window.alert(uiT("alertPinMustDigits"));
        return;
      }
      try {
        await apiRequest(`${API_BASE}/api/workers/${workerId}/reset-pin`, { method: "POST", body: { newPin: newPin.trim() } });
        window.alert(uiT("alertPinResetSuccessFor").replace("{name}", name));
      } catch (error) {
        window.alert(uiT("alertPinResetFailed").replace("{error}", error.message));
      }
    };
  });
}

async function renderPhotoOverrideApprovalPanel() {
  const panel = document.getElementById("photoOverrideApprovalPanel");
  const list = document.getElementById("photoOverrideApprovalList");
  if (!panel || !list) return;

  const role = String(getCurrentUser()?.role || "").toLowerCase();
  if (role !== "superadmin") {
    panel.classList.add("hidden");
    return;
  }

  let approvals = [];
  try {
    approvals = await apiRequest(API_BASE + "/api/workers/photo-override-approvals/pending");
  } catch {
    panel.classList.add("hidden");
    return;
  }

  if (!Array.isArray(approvals) || approvals.length === 0) {
    panel.classList.add("hidden");
    return;
  }

  panel.classList.remove("hidden");
  const currentUserId = getCurrentUser()?.id || "";
  list.innerHTML = approvals.map((a) => {
    const canDecide = a.requestedByUserId !== currentUserId;
    const photoHtml = a.photoData
      ? `<img src="${escapeHtml(a.photoData)}" alt="Neues Foto" style="max-width:80px;max-height:100px;border-radius:8px;border:1px solid #ccc;margin-bottom:8px;" />`
      : "";
    const similarityText = a.similarity != null ? `${a.similarity}%` : "k.A.";
    const notSelfHint = canDecide ? "" : `<p class="helper-text helper-text-warning">Du bist der Antragsteller – ein anderer Superadmin muss freigeben.</p>`;
    return `
      <div class="card" data-approval-id="${escapeHtml(a.approvalId)}">
        ${photoHtml}
        <p><strong>${escapeHtml(a.workerName || a.workerId || "?")}</strong></p>
        <p class="helper-text">Fotovergleich: ${escapeHtml(similarityText)} | Grund: ${escapeHtml(a.overrideReason || "–")}</p>
        <p class="helper-text">Beantragt: ${escapeHtml(a.requestedAt || "")} | Gültig bis: ${escapeHtml(a.expiresAt || "")}</p>
        ${notSelfHint}
        ${canDecide ? `
        <div style="display:flex;gap:8px;margin-top:10px;">
          <button class="primary-button approval-approve-btn" data-approval-id="${escapeHtml(a.approvalId)}">Freigeben</button>
          <button class="danger-button approval-reject-btn" data-approval-id="${escapeHtml(a.approvalId)}">Ablehnen</button>
        </div>` : ""}
      </div>`;
  }).join("");

  list.querySelectorAll(".approval-approve-btn").forEach((btn) => {
    btn.onclick = async () => {
      try {
        await apiRequest(API_BASE + `/api/workers/photo-override-approvals/${btn.dataset.approvalId}/decision`, {
          method: "POST",
          body: { decision: "approve", note: "" },
        });
        await loadAllData();
        await renderPhotoOverrideApprovalPanel();
        refreshAll();
        window.alert(uiT("alertPhotoOverrideApproved"));
      } catch (error) {
        window.alert(uiT("alertPhotoOverrideApproveFailed").replace("{error}", error.message));
      }
    };
  });

  list.querySelectorAll(".approval-reject-btn").forEach((btn) => {
    btn.onclick = async () => {
      const reason = window.prompt(uiT("promptRejectApproval")) || "";
      if (!reason.trim()) {
        window.alert(uiT("alertPhotoOverrideRejectReasonRequired"));
        return;
      }
      try {
        await apiRequest(API_BASE + `/api/workers/photo-override-approvals/${btn.dataset.approvalId}/decision`, {
          method: "POST",
          body: { decision: "reject", note: reason.trim() },
        });
        await renderPhotoOverrideApprovalPanel();
        window.alert(uiT("alertPhotoOverrideRejected"));
      } catch (error) {
        window.alert(uiT("alertPhotoOverrideRejectFailed").replace("{error}", error.message));
      }
    };
  });
}

function renderCompanyList() {
  if (!elements.companyList) return;
  if (!state.companies.length) {
    elements.companyList.innerHTML = '<div class="empty-state">Noch keine Firmen vorhanden.</div>';
    return;
  }
  const userRole = getEffectiveUiRole();
  const userCompanyId = getEffectiveUiCompanyId();
  const superadminPreviewEnabled = String(getCurrentUser()?.role || "").toLowerCase() === "superadmin";
  const previewCompanyId = String(superadminUiPreviewCompanyId || "").trim();
  const previewCompanyOptions = state.companies
    .filter((entry) => !entry.deleted_at)
    .map((entry) => `<option value="${escapeHtml(entry.id)}" ${entry.id === previewCompanyId ? "selected" : ""}>${escapeHtml(entry.name || entry.id)}</option>`)
    .join("");
  const canRepairAny = userRole === "superadmin";
  const canDeleteAny = userRole === "superadmin";
  const canRepairOwn = userRole === "company-admin";
  const historyWindowValue = String(state.repairHistoryWindowDays || 0);
  const onlyProblemsChecked = Boolean(state.onlyCompaniesWithRepairs);

  const companiesToRender = state.companies.filter((company) => {
    if (!onlyProblemsChecked) {
      return true;
    }
    const companyId = company.id || "";
    const repairHistory = filterRepairHistoryByWindow(state.companyRepairHistory?.[companyId] || []);
    return repairHistory.length > 0;
  });
  const shownCount = companiesToRender.length;
  const totalCount = state.companies.length;

  const cardsMarkup = companiesToRender
    .map((company) => {
      const companyId = company.id || "";
      const deleted = Boolean(company.deleted_at || company.deletedAt);
      const statusMeta = getCompanyStatusMeta(company.status);
      const canRepair = canRepairCompany(company);
      const canToggleLock = userRole === "superadmin";
      const isRepairing = Boolean(state.companyRepairBusy?.[companyId]);
      const isLockBusy = Boolean(state.companyLockBusy?.[companyId]);
      const repairStatus = state.companyRepairStatus?.[companyId] || null;
      const repairStatusClass = repairStatus?.kind === "error"
        ? "helper-text helper-text-warning"
        : repairStatus?.kind === "success"
          ? "helper-text helper-text-ok"
          : "helper-text helper-text-info";
      const documentEmail = getCompanyDocumentEmail(company);
      const brandingPreset = getCompanyBrandingPreset(company);
      const turnstiles = Array.isArray(state.companyTurnstiles?.[companyId]) ? state.companyTurnstiles[companyId] : [];
      const repairHistory = filterRepairHistoryByWindow(state.companyRepairHistory?.[companyId] || []);
      const historyMarkup = repairHistory.length
        ? repairHistory
            .map((entry) => `<span>• ${escapeHtml(formatTimestamp(entry.created_at))}: ${escapeHtml(entry.message || "Reparatur ausgefuehrt")}</span>`)
            .join("")
        : "<span>Keine Reparaturen im gewaelten Zeitraum.</span>";
      const turnstileMarkup = turnstiles.length
        ? `<div class="meta-box"><p><strong>Drehkreuz-Accounts</strong></p>${turnstiles.map((entry) => `<span>• ${escapeHtml(entry.username || entry.name || "Drehkreuz")} | ${entry.isActive ? "aktiv" : "deaktiviert"} | ${entry.hasApiKey ? "API-Key aktiv" : "kein API-Key"} <button type="button" class="ghost-button small-button" data-turnstile-reset="${escapeHtml(entry.id)}" data-turnstile-company="${escapeHtml(companyId)}">Passwort neu</button>${userRole === "superadmin" ? ` <button type="button" class="ghost-button small-button" data-turnstile-rotate-key="${escapeHtml(entry.id)}" data-turnstile-company="${escapeHtml(companyId)}">API-Key neu</button>` : ""} <button type="button" class="ghost-button small-button" data-turnstile-toggle="${escapeHtml(entry.id)}" data-turnstile-company="${escapeHtml(companyId)}">${entry.isActive ? "Deaktivieren" : "Aktivieren"}</button></span>`).join("")}</div>`
        : '<div class="meta-box"><span>Keine Drehkreuz-Accounts vorhanden.</span></div>';
      return `
        <article class="card-item ${deleted ? "is-deleted" : ""}">
          <strong>${escapeHtml(company.name || "Firma")}</strong>
          <span>${escapeHtml(company.plan || "-")}</span>
          <p class="${statusMeta.className}">Status: ${escapeHtml(statusMeta.label)}</p>
          <p><strong>Design:</strong> ${escapeHtml(getCompanyBrandingPresetLabel(brandingPreset))}</p>
          <p><strong>Dokument-E-Mail:</strong> ${escapeHtml(documentEmail || "Nicht gesetzt")}</p>
          ${(() => {
            const sec = state.companyAdminSecurity?.[companyId];
            if (!sec) return "";
            const otpIcon = sec.twofa_enabled ? "🔐" : "🔓";
            const otpLabel = sec.twofa_enabled
              ? `OTP aktiv · ${escapeHtml(sec.email || "keine E-Mail")}`
              : sec.email
                ? `OTP deaktiviert · ${escapeHtml(sec.email)}`
                : "OTP nicht konfiguriert";
            return `<p>${otpIcon} <strong>Admin-OTP:</strong> ${otpLabel}</p>`;
          })()}
          <div class="button-row" style="align-items:center; margin-top:2px;">
            <select data-company-branding-select="${escapeHtml(companyId)}" ${canDeleteAny && !deleted ? "" : "disabled"}>
              <option value="construction" ${brandingPreset === "construction" ? "selected" : ""}>Bau</option>
              <option value="industry" ${brandingPreset === "industry" ? "selected" : ""}>Industrie</option>
              <option value="premium" ${brandingPreset === "premium" ? "selected" : ""}>Premium</option>
            </select>
            <button type="button" class="ghost-button small-button" data-company-branding-save="${escapeHtml(companyId)}" ${canDeleteAny && !deleted ? "" : "disabled"}>Design speichern</button>
            <button type="button" class="ghost-button small-button" data-company-branding-reset="${escapeHtml(companyId)}" ${canDeleteAny && !deleted ? "" : "disabled"}>Zuruecksetzen</button>
          </div>
          <div class="button-row" style="align-items:center; margin-top:2px;">
            <span class="company-branding-preview preview-${escapeHtml(brandingPreset)}" data-company-branding-preview="${escapeHtml(companyId)}" aria-hidden="true"></span>
            <span class="helper-text" data-company-branding-preview-label="${escapeHtml(companyId)}">Vorschau: ${escapeHtml(getCompanyBrandingPresetLabel(brandingPreset))}</span>
            <span class="helper-text" data-company-branding-dirty="${escapeHtml(companyId)}"></span>
          </div>
          ${turnstileMarkup}
          <div class="meta-box">
            <p><strong>Letzte Reparaturen</strong></p>
            ${historyMarkup}
          </div>
          ${repairStatus ? `<p class="${repairStatusClass}">${escapeHtml(repairStatus.message || "")}</p>` : ""}
          <div class="button-row">
            <button type="button" class="ghost-button" data-company-doc-email="${escapeHtml(companyId)}" ${canDeleteAny && !deleted ? "" : "disabled"}>Dokument-Mail setzen</button>
            <button type="button" class="ghost-button" data-company-otp-setup="${escapeHtml(companyId)}" ${canDeleteAny && !deleted ? "" : "disabled"}>🔐 Admin-OTP</button>
            <button type="button" class="ghost-button" data-company-add-turnstile="${escapeHtml(companyId)}" ${canDeleteAny && !deleted ? "" : "disabled"}>Drehkreuz hinzufügen</button>
            <button type="button" class="ghost-button" data-company-repair="${escapeHtml(companyId)}" ${canRepair && !deleted && !isRepairing ? "" : "disabled"}>${isRepairing ? "Login wird vorbereitet..." : "Firmen-Login"}</button>
            <button type="button" class="ghost-button" data-company-toggle-lock="${escapeHtml(companyId)}" ${canToggleLock && !deleted && !isLockBusy ? "" : "disabled"}>${isLockBusy ? "Speichert..." : String(company.status || "aktiv").toLowerCase() === "gesperrt" ? "Sperre aufheben" : "Firma sperren"}</button>
            <button type="button" class="ghost-button" data-company-delete="${escapeHtml(companyId)}" ${canDeleteAny && !deleted ? "" : "disabled"}>Firma löschen</button>
          </div>
        </article>
      `;
    })
    .join("");

  elements.companyList.innerHTML = `
    <article class="card-item">
      <div class="button-row" style="justify-content:space-between; align-items:center;">
        <div>
          <strong>Reparatur-Verlauf filtern</strong>
          <p class="helper-text">${shownCount} von ${totalCount} Firmen angezeigt</p>
        </div>
        <div class="button-row" style="gap:10px;">
          <label>
            Zeitraum
            <select id="companyRepairHistoryWindow" style="margin-left:8px;">
              <option value="7" ${historyWindowValue === "7" ? "selected" : ""}>Letzte 7 Tage</option>
              <option value="30" ${historyWindowValue === "30" ? "selected" : ""}>Letzte 30 Tage</option>
              <option value="90" ${historyWindowValue === "90" ? "selected" : ""}>Letzte 90 Tage</option>
              <option value="0" ${historyWindowValue === "0" ? "selected" : ""}>Alle</option>
            </select>
          </label>
          <label>
            <input id="companyOnlyProblems" type="checkbox" ${onlyProblemsChecked ? "checked" : ""} />
            Nur Probleme anzeigen
          </label>
        </div>
      </div>
      ${superadminPreviewEnabled ? `
      <div class="button-row" style="margin-top:10px; align-items:center; gap:10px;">
        <strong>Firmenvorschau:</strong>
        <select id="superadminCompanyPreviewSelect">
          <option value="">Keine Vorschau (Superadmin-Sicht)</option>
          ${previewCompanyOptions}
        </select>
        <button type="button" class="ghost-button small-button" id="superadminCompanyPreviewReset">Vorschau beenden</button>
      </div>
      ` : ""}
    </article>
    ${cardsMarkup || '<div class="empty-state">Keine Firmen mit Reparaturen im ausgewaehlten Zeitraum.</div>'}
  `;

  bindCompanyHistoryControls();
  bindCompanyRowActions();
}

function filterRepairHistoryByWindow(entries) {
  const days = Number(state.repairHistoryWindowDays || 0);
  if (!days || days <= 0) {
    return entries;
  }
  const cutoffMs = Date.now() - (days * 24 * 60 * 60 * 1000);
  return (entries || []).filter((entry) => {
    const ts = Date.parse(entry?.created_at || "");
    return Number.isFinite(ts) && ts >= cutoffMs;
  });
}

function bindCompanyHistoryControls() {
  const filterSelect = document.querySelector("#companyRepairHistoryWindow");
  const onlyProblemsToggle = document.querySelector("#companyOnlyProblems");
  const previewSelect = document.querySelector("#superadminCompanyPreviewSelect");
  const previewResetButton = document.querySelector("#superadminCompanyPreviewReset");
  if (!filterSelect) {
    return;
  }

  filterSelect.addEventListener("change", () => {
    const value = Number(filterSelect.value || 30);
    state.repairHistoryWindowDays = Number.isFinite(value) ? value : 30;
    renderCompanyList();
  });

  if (onlyProblemsToggle) {
    onlyProblemsToggle.addEventListener("change", () => {
      state.onlyCompaniesWithRepairs = Boolean(onlyProblemsToggle.checked);
      renderCompanyList();
    });
  }

  if (previewSelect) {
    previewSelect.addEventListener("change", () => {
      setSuperadminPreviewCompany(previewSelect.value);
    });
  }

  if (previewResetButton) {
    previewResetButton.addEventListener("click", () => clearSuperadminPreviewMode());
  }
}

function bindCompanyRowActions() {
  if (!elements.companyList || elements.companyList.dataset.repairBound === "1") return;

  elements.companyList.dataset.repairBound = "1";
  elements.companyList.addEventListener("change", (event) => {
    const presetSelect = event.target.closest("[data-company-branding-select]");
    if (!presetSelect || !elements.companyList.contains(presetSelect)) {
      return;
    }
    const companyId = String(presetSelect.dataset.companyBrandingSelect || "").trim();
    const selectedPreset = normalizeCompanyBrandingPresetValue(presetSelect.value);
    const previewDot = elements.companyList.querySelector(`[data-company-branding-preview="${companyId}"]`);
    const previewLabel = elements.companyList.querySelector(`[data-company-branding-preview-label="${companyId}"]`);
    const dirtyLabel = elements.companyList.querySelector(`[data-company-branding-dirty="${companyId}"]`);
    if (previewDot) {
      previewDot.classList.remove("preview-construction", "preview-industry", "preview-premium");
      previewDot.classList.add(`preview-${selectedPreset}`);
    }
    if (previewLabel) {
      previewLabel.textContent = `Vorschau: ${getCompanyBrandingPresetLabel(selectedPreset)}`;
    }
    if (dirtyLabel) {
      dirtyLabel.textContent = "Noch nicht gespeichert";
    }
    companyBrandingPreviewOverride = selectedPreset;
    applyActiveCompanyBrandingPreset();
  });

  elements.companyList.addEventListener("click", async (event) => {
    // ── Admin-OTP einrichten ──
    const otpSetupButton = event.target.closest("[data-company-otp-setup]");
    if (otpSetupButton && !otpSetupButton.disabled && elements.companyList.contains(otpSetupButton)) {
      const companyId = otpSetupButton.dataset.companyOtpSetup;
      const company = state.companies.find((c) => c.id === companyId);
      if (!companyId || !company) return;
      const sec = state.companyAdminSecurity?.[companyId];
      const currentEmail = sec?.email || "";
      const newEmail = window.prompt(
        `OTP-E-Mail für Admin der Firma „${company.name}":\n(Leer lassen = OTP deaktivieren)`,
        currentEmail
      );
      if (newEmail === null) return;
      const enable = newEmail.trim().length > 0;
      try {
        await apiRequest(`${API_BASE}/api/companies/${companyId}/admin-security`, {
          method: "PUT",
          body: { email: newEmail.trim(), enable2fa: enable }
        });
        await loadAllData();
        refreshAll();
        window.alert(enable
          ? `✅ OTP aktiviert!\nE-Mail: ${newEmail.trim()}\n\nDer Admin erhält beim nächsten Login einen Code an diese Adresse.`
          : `🔓 OTP deaktiviert für Admin der Firma „${company.name}".`
        );
      } catch (err) {
        window.alert(`Fehler: ${err.message}`);
      }
      return;
    }

    const docEmailButton = event.target.closest("[data-company-doc-email]");
    if (docEmailButton && !docEmailButton.disabled && elements.companyList.contains(docEmailButton)) {
      const companyId = docEmailButton.dataset.companyDocEmail;
      const company = state.companies.find((entry) => entry.id === companyId);
      if (!companyId || !company) {
        return;
      }

      const currentValue = getCompanyDocumentEmail(company);
      const nextValue = window.prompt(uiT("promptDocEmail").replace("{name}", company.name), currentValue || suggestCompanyDocumentEmail(company.name));
      if (nextValue === null) {
        return;
      }

      try {
        await apiRequest(`${API_BASE}/api/companies/${companyId}`, {
          method: "PUT",
          body: {
            name: company.name,
            contact: company.contact,
            billingEmail: getCompanyBillingEmail(company),
            documentEmail: nextValue.trim(),
            accessHost: company.accessHost || company.access_host || "",
            plan: company.plan,
            status: company.status,
          }
        });
        await loadAllData();
        refreshAll();
      } catch (error) {
        window.alert(uiT("alertDocEmailSaveFailed").replace("{error}", error.message));
      }
      return;
    }

    const deleteButton = event.target.closest("[data-company-delete]");
    if (deleteButton && !deleteButton.disabled && elements.companyList.contains(deleteButton)) {
      const companyId = deleteButton.dataset.companyDelete;
      if (!companyId) {
        return;
      }
      const company = state.companies.find((entry) => entry.id === companyId);
      const companyName = company?.name || "diese Firma";
      const forceDelete = window.confirm(
        uiT("confirmDeleteCompanyText").replace("{name}", companyName)
      );
      if (!forceDelete) {
        return;
      }

      try {
        await apiRequest(`${API_BASE}/api/companies/${companyId}?force=1`, { method: "DELETE" });
        await loadAllData();
        refreshAll();
        window.alert(uiT("alertCompanyDeleted").replace("{name}", companyName));
      } catch (error) {
        const repairMessage = mapCompanyRepairError(error);
        window.alert(uiT("alertCompanyDeleteFailed").replace("{name}", companyName).replace("{error}", repairMessage));
      }
      return;
    }

    const lockButton = event.target.closest("[data-company-toggle-lock]");
    if (lockButton && !lockButton.disabled && elements.companyList.contains(lockButton)) {
      const companyId = lockButton.dataset.companyToggleLock;
      if (!companyId) {
        return;
      }
      const company = state.companies.find((entry) => entry.id === companyId);
      const companyName = company?.name || "diese Firma";
      const currentStatus = String(company?.status || "aktiv").toLowerCase();
      const nextStatus = currentStatus === "gesperrt" ? "aktiv" : "gesperrt";
      const promptText = nextStatus === "gesperrt"
        ? uiT("confirmLockCompany").replace("{name}", companyName)
        : uiT("confirmUnlockCompany").replace("{name}", companyName);
      if (!window.confirm(promptText)) {
        return;
      }

      state.companyLockBusy[companyId] = true;
      state.companyRepairStatus[companyId] = {
        kind: "info",
        message: nextStatus === "gesperrt" ? "Firma wird gesperrt..." : "Sperre wird aufgehoben..."
      };
      renderCompanyList();

      try {
        await apiRequest(`${API_BASE}/api/companies/${companyId}`, { method: "PUT", body: { status: nextStatus } });
        state.companyRepairStatus[companyId] = {
          kind: nextStatus === "gesperrt" ? "error" : "success",
          message: nextStatus === "gesperrt" ? "Firma ist jetzt gesperrt." : "Firma ist wieder aktiv."
        };
        await loadAllData();
        refreshAll();
        window.alert(nextStatus === "gesperrt"
          ? uiT("alertCompanyLocked").replace("{name}", companyName)
          : uiT("alertCompanyUnlocked").replace("{name}", companyName));
      } catch (error) {
        const repairMessage = mapCompanyRepairError(error);
        state.companyRepairStatus[companyId] = {
          kind: "error",
          message: repairMessage
        };
        renderCompanyList();
        window.alert(uiT("alertCompanyStatusChangeFailed").replace("{name}", companyName).replace("{error}", repairMessage));
      } finally {
        delete state.companyLockBusy[companyId];
        renderCompanyList();
      }
      return;
    }

    const brandingResetButton = event.target.closest("[data-company-branding-reset]");
    if (brandingResetButton && !brandingResetButton.disabled && elements.companyList.contains(brandingResetButton)) {
      const companyId = brandingResetButton.dataset.companyBrandingReset;
      const company = state.companies.find((entry) => entry.id === companyId);
      if (!companyId || !company) {
        return;
      }

      const savedPreset = getCompanyBrandingPreset(company);
      const presetSelect = elements.companyList.querySelector(`[data-company-branding-select="${companyId}"]`);
      const previewDot = elements.companyList.querySelector(`[data-company-branding-preview="${companyId}"]`);
      const previewLabel = elements.companyList.querySelector(`[data-company-branding-preview-label="${companyId}"]`);
      const dirtyLabel = elements.companyList.querySelector(`[data-company-branding-dirty="${companyId}"]`);

      if (presetSelect) {
        presetSelect.value = savedPreset;
      }
      if (previewDot) {
        previewDot.classList.remove("preview-construction", "preview-industry", "preview-premium");
        previewDot.classList.add(`preview-${savedPreset}`);
      }
      if (previewLabel) {
        previewLabel.textContent = `Vorschau: ${getCompanyBrandingPresetLabel(savedPreset)}`;
      }
      if (dirtyLabel) {
        dirtyLabel.textContent = "";
      }

      companyBrandingPreviewOverride = savedPreset;
      applyActiveCompanyBrandingPreset();
      return;
    }

    const brandingSaveButton = event.target.closest("[data-company-branding-save]");
    if (brandingSaveButton && !brandingSaveButton.disabled && elements.companyList.contains(brandingSaveButton)) {
      const companyId = brandingSaveButton.dataset.companyBrandingSave;
      const company = state.companies.find((entry) => entry.id === companyId);
      if (!companyId || !company) {
        return;
      }
      const presetSelect = elements.companyList.querySelector(`[data-company-branding-select="${companyId}"]`);
      const brandingPreset = normalizeCompanyBrandingPresetValue(presetSelect?.value || "construction");
      try {
        await apiRequest(`${API_BASE}/api/companies/${companyId}`, {
          method: "PUT",
          body: {
            name: company.name,
            contact: company.contact,
            billingEmail: getCompanyBillingEmail(company),
            documentEmail: getCompanyDocumentEmail(company),
            accessHost: company.accessHost || company.access_host || "",
            brandingPreset,
            plan: company.plan,
            status: company.status,
          }
        });
        companyBrandingPreviewOverride = brandingPreset;
        await loadAllData();
        refreshAll();
      } catch (error) {
        window.alert(uiT("alertBrandingPresetSaveFailed").replace("{error}", error.message));
      }
      return;
    }

    const addTurnstileButton = event.target.closest("[data-company-add-turnstile]");
    if (addTurnstileButton && !addTurnstileButton.disabled && elements.companyList.contains(addTurnstileButton)) {
      const companyId = addTurnstileButton.dataset.companyAddTurnstile;
      const company = state.companies.find((entry) => entry.id === companyId);
      if (!companyId || !company) return;

      const password = window.prompt(uiT("promptTurnstilePassword").replace("{name}", company.name), "");
      if (password === null) return;
      if (password.trim().length < 4) {
        window.alert(uiT("alertPasswordMinLength"));
        return;
      }

      try {
        const result = await apiRequest(`${API_BASE}/api/companies/${companyId}/add-turnstile`, {
          method: "POST",
          body: { password: password.trim() },
        });
        await loadAllData();
        refreshAll();
        showSecretDialog(
          "Drehkreuz-Zugang angelegt",
          [
            `Benutzername: ${result.username}`,
            `Passwort: ${result.password}`,
            `API-Key: ${result.apiKey || "nicht verfuegbar"}`,
          ],
          {
            copyLabel: "API-Key kopieren",
            copyValue: result.apiKey || `Benutzername: ${result.username}\nPasswort: ${result.password}`,
          }
        );
      } catch (error) {
        window.alert(uiT("alertTurnstileCreateFailed").replace("{error}", error.message));
      }
      return;
    }

    const resetTurnstileButton = event.target.closest("[data-turnstile-reset]");
    if (resetTurnstileButton && elements.companyList.contains(resetTurnstileButton)) {
      const companyId = resetTurnstileButton.dataset.turnstileCompany;
      const userId = resetTurnstileButton.dataset.turnstileReset;
      const password = window.prompt(uiT("promptTurnstilePasswordNew"), "");
      if (password === null) return;
      if (password.trim().length < 4) {
        window.alert(uiT("alertPasswordMinLength"));
        return;
      }
      try {
        await apiRequest(`${API_BASE}/api/companies/${companyId}/turnstiles/${userId}/reset-password`, {
          method: "POST",
          body: { password: password.trim() }
        });
        window.alert(uiT("alertTurnstilePasswordUpdated"));
      } catch (error) {
        window.alert(uiT("alertTurnstilePasswordResetFailed").replace("{error}", error.message));
      }
      return;
    }

    const rotateTurnstileKeyButton = event.target.closest("[data-turnstile-rotate-key]");
    if (rotateTurnstileKeyButton && elements.companyList.contains(rotateTurnstileKeyButton)) {
      const companyId = rotateTurnstileKeyButton.dataset.turnstileCompany;
      const userId = rotateTurnstileKeyButton.dataset.turnstileRotateKey;
      if (!window.confirm(uiT("confirmApiKeyRotate"))) {
        return;
      }
      try {
        const result = await apiRequest(`${API_BASE}/api/companies/${companyId}/turnstiles/${userId}/rotate-api-key`, {
          method: "POST"
        });
        await loadAllData();
        refreshAll();
        showSecretDialog(
          "Neuer Drehkreuz-API-Key",
          [result.apiKey || "Kein API-Key erhalten"],
          {
            copyLabel: "API-Key kopieren",
            copyValue: result.apiKey || "",
          }
        );
      } catch (error) {
        window.alert(uiT("alertApiKeyRotationFailed").replace("{error}", error.message));
      }
      return;
    }

    const toggleTurnstileButton = event.target.closest("[data-turnstile-toggle]");
    if (toggleTurnstileButton && elements.companyList.contains(toggleTurnstileButton)) {
      const companyId = toggleTurnstileButton.dataset.turnstileCompany;
      const userId = toggleTurnstileButton.dataset.turnstileToggle;
      try {
        await apiRequest(`${API_BASE}/api/companies/${companyId}/turnstiles/${userId}/toggle-active`, { method: "POST" });
        await loadAllData();
        refreshAll();
      } catch (error) {
        window.alert(uiT("alertTurnstileToggleFailed").replace("{error}", error.message));
      }
      return;
    }

    const button = event.target.closest("[data-company-repair]");
    if (!button || button.disabled || !elements.companyList.contains(button)) {
      return;
    }

    const companyId = button.dataset.companyRepair;
    if (!companyId) {
      return;
    }

    const company = state.companies.find((entry) => entry.id === companyId);
    const companyName = company?.name || "diese Firma";
    if (!window.confirm(`${uiT("supportCompanyLoginConfirmPrefix")} ${companyName} ${uiT("supportCompanyLoginConfirmSuffix")}`)) {
      return;
    }

    const actorName = getCurrentUser()?.name || getCurrentUser()?.username || "Admin";
    state.supportLoginContext = { companyId, companyName, actorName };
    persistSupportLoginContext(state.supportLoginContext);
    const companyAccessHost = String(company?.accessHost || company?.access_host || "").trim().toLowerCase();
    const currentHost = String(window.location.host || "").trim().toLowerCase();
    if (companyAccessHost && companyAccessHost !== currentHost) {
      await handleLogout({ preserveSupportContext: true });
      const targetUrl = new URL(window.location.href);
      targetUrl.protocol = window.location.protocol;
      targetUrl.host = companyAccessHost;
      targetUrl.pathname = "/";
      targetUrl.search = "";
      if (API_BASE) {
        targetUrl.searchParams.set("apiBase", API_BASE);
      }
      targetUrl.searchParams.set("supportCompanyId", companyId);
      targetUrl.searchParams.set("supportCompanyName", companyName);
      targetUrl.searchParams.set("supportActorName", actorName);
      targetUrl.searchParams.set("loginScope", "company-admin");
      window.location.assign(targetUrl.toString());
      return;
    }
    await handleLogout({ preserveSupportContext: true });
    syncSupportLoginUi();
    window.scrollTo({ top: 0, behavior: "smooth" });
    // Use a short delay instead of window.alert() to avoid Electron losing
    // keyboard focus after a native dialog dismissal.
    window.setTimeout(() => {
      focusLoginInput({ force: true });
    }, 80);
  });
}

function populateWorkerSelectOptions() {
  const select = elements.accessWorkerSelect;
  if (!select) return;
  const current = select.value;
  const options = getUiVisibleWorkers()
    .filter((w) => !w.deletedAt)
    .map((w) => `<option value="${escapeHtml(w.id)}">${escapeHtml(`${w.firstName} ${w.lastName}`)}${isVisitorWorker(w) ? ` [${runtimeText("visitorTagShort")}]` : ""} (${escapeHtml(w.badgeId || "-")})</option>`)
    .join("");
  select.innerHTML = `<option value="">${runtimeText("selectPersonOption")}</option>${options}`;
  if (current && Array.from(select.options).some((o) => o.value === current)) {
    select.value = current;
  }
}

function populateCompanySelectOptions() {
  const scopedCompanyId = getEffectiveUiCompanyId();
  const companies = scopedCompanyId
    ? state.companies.filter((c) => !c.deleted_at && String(c.id || "") === scopedCompanyId)
    : state.companies.filter((c) => !c.deleted_at);
  const syncSelect = (select) => {
    if (!select) return;
    const current = select.value;
    select.innerHTML = companies.map((company) => `<option value="${escapeHtml(company.id)}">${escapeHtml(company.name)}</option>`).join("");
    if (current && Array.from(select.options).some((o) => o.value === current)) {
      select.value = current;
    }
  };
  syncSelect(elements.companySelect);
  syncSelect(elements.invoiceCompanySelect);
  syncInvoiceRecipientFromCompany();
}

function getCompanyBillingEmail(company) {
  return (company?.billingEmail || company?.billing_email || "").trim();
}

function getCompanyDocumentEmail(company) {
  return (company?.documentEmail || company?.document_email || "").trim();
}

function getCompanyBrandingPreset(company) {
  const preset = String(company?.brandingPreset || company?.branding_preset || "").trim().toLowerCase();
  return ["construction", "industry", "premium"].includes(preset) ? preset : "construction";
}

function normalizeCompanyBrandingPresetValue(value) {
  const preset = String(value || "").trim().toLowerCase();
  return ["construction", "industry", "premium"].includes(preset) ? preset : "construction";
}

function getCompanyBrandingPresetLabel(preset) {
  if (preset === "industry") {
    return "Industrie";
  }
  if (preset === "premium") {
    return "Premium";
  }
  return "Bau";
}

function applyActiveCompanyBrandingPreset() {
  if (!document.body) {
    return;
  }
  const role = String(getCurrentUser()?.role || "").toLowerCase();
  if (role === "superadmin" && companyBrandingPreviewOverride) {
    document.body.setAttribute("data-branding-preset", normalizeCompanyBrandingPresetValue(companyBrandingPreviewOverride));
    return;
  }
  if (role === "superadmin" && isSuperadminCompanyPreviewMode()) {
    const previewCompany = state.companies.find((entry) => String(entry?.id || "") === String(superadminUiPreviewCompanyId || ""));
    document.body.setAttribute("data-branding-preset", getCompanyBrandingPreset(previewCompany));
    return;
  }
  const companyId = String(getCurrentUser()?.company_id || getCurrentUser()?.companyId || "").trim();
  const activeCompany = companyId ? state.companies.find((entry) => String(entry?.id || "") === companyId) : null;
  const activePreset = role === "superadmin" ? "construction" : getCompanyBrandingPreset(activeCompany);
  document.body.setAttribute("data-branding-preset", activePreset);
}

function suggestCompanyDocumentEmail(companyName) {
  const imapUsername = String(state.settings?.imapUsername || "").trim().toLowerCase();
  if (!companyName || !imapUsername.includes("@")) {
    return "";
  }
  const slug = String(companyName)
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48) || "firma";
  const [localPart, domain] = imapUsername.split("@", 2);
  const aliasBase = (localPart.split("+", 1)[0] || "dokumente").trim() || "dokumente";
  return `${aliasBase}+${slug}@${domain}`;
}

function syncInvoiceRecipientFromCompany() {
  if (!elements.invoiceCompanySelect || !elements.invoiceRecipientEmail) {
    return;
  }
  const companyId = elements.invoiceCompanySelect.value;
  const company = state.companies.find((entry) => entry.id === companyId);
  const billingEmail = getCompanyBillingEmail(company);
  if (billingEmail) {
    elements.invoiceRecipientEmail.value = billingEmail;
  }
}

function renderSystemIdentity() {
  const platform = document.querySelector("#loginPlatformName");
  const operator = document.querySelector("#loginOperatorName");
  const endpoint = document.querySelector("#loginTurnstileEndpoint");
  if (platform) platform.textContent = state.settings.platformName || "BauPass Control";
  if (operator) operator.textContent = state.settings.operatorName || "Deine Betriebsfirma";
  if (endpoint) endpoint.textContent = state.settings.turnstileEndpoint || "Noch nicht gesetzt";
}

function renderAdminSettingsForm() {
  const platformName = document.querySelector("#platformName");
  const operatorName = document.querySelector("#operatorName");
  const turnstileEndpoint = document.querySelector("#companyTurnstileEndpoint");
  const rentalModel = document.querySelector("#rentalModel");
  const invoicePrimaryColor = document.querySelector("#invoicePrimaryColor");
  const invoiceAccentColor = document.querySelector("#invoiceAccentColor");
  const smtpHost = document.querySelector("#smtpHost");
  const smtpPort = document.querySelector("#smtpPort");
  const smtpUsername = document.querySelector("#smtpUsername");
  const smtpPassword = document.querySelector("#smtpPassword");
  const smtpSenderEmail = document.querySelector("#smtpSenderEmail");
  const smtpSenderName = document.querySelector("#smtpSenderName");
  const smtpUseTls = document.querySelector("#smtpUseTls");
  const adminIpWhitelist = document.querySelector("#adminIpWhitelist");
  const enforceTenantDomain = document.querySelector("#enforceTenantDomain");
  const supportPhone = document.querySelector("#supportPhone");
  const workerAppEnabled = document.querySelector("#workerAppEnabled");

  if (platformName) platformName.value = state.settings.platformName || "BauPass Control";
  if (operatorName) operatorName.value = state.settings.operatorName || "Deine Betriebsfirma";
  if (turnstileEndpoint) turnstileEndpoint.value = state.settings.turnstileEndpoint || "";
  if (rentalModel) rentalModel.value = state.settings.rentalModel || "tageskarte";
  if (invoicePrimaryColor) invoicePrimaryColor.value = state.settings.invoicePrimaryColor || "#0f4c5c";
  if (invoiceAccentColor) invoiceAccentColor.value = state.settings.invoiceAccentColor || "#e36414";
  if (smtpHost) smtpHost.value = state.settings.smtpHost || "";
  if (smtpPort) smtpPort.value = String(state.settings.smtpPort || 587);
  if (smtpUsername) smtpUsername.value = state.settings.smtpUsername || "";
  if (smtpPassword) smtpPassword.value = "";
  if (smtpSenderEmail) smtpSenderEmail.value = state.settings.smtpSenderEmail || "";
  if (smtpSenderName) smtpSenderName.value = state.settings.smtpSenderName || "";
  if (smtpUseTls) smtpUseTls.value = state.settings.smtpUseTls === false ? "0" : "1";
  if (adminIpWhitelist) adminIpWhitelist.value = state.settings.adminIpWhitelist || "";
  if (enforceTenantDomain) enforceTenantDomain.value = state.settings.enforceTenantDomain ? "1" : "0";
  if (supportPhone) supportPhone.value = getSupportPhoneForLockScreen();
  if (workerAppEnabled) workerAppEnabled.value = state.settings.workerAppEnabled === false ? "0" : "1";
  // Brevo-Felder
  const brevoApiKeyEl = document.querySelector("#brevoApiKey");
  const brevoFromEmailEl = document.querySelector("#brevoFromEmail");
  if (brevoApiKeyEl) brevoApiKeyEl.value = "";
  if (brevoFromEmailEl) brevoFromEmailEl.value = state.settings.brevoFromEmail || "";
  const brevoKeyHint = document.querySelector("#brevoKeyStoredHint");
  if (brevoKeyHint) {
    const hasBrevoKey = !!(state.settings.brevoApiKey);
    brevoKeyHint.textContent = hasBrevoKey ? "✓ API-Key gespeichert" : "Kein Key gespeichert";
    brevoKeyHint.style.color = hasBrevoKey ? "#16a34a" : "#9ca3af";
  }
  if (elements.invoiceLogoData) {
    elements.invoiceLogoData.value = state.settings.invoiceLogoData || "";
  }
  if (elements.invoiceLogoPreview) {
    const logoSrc = state.settings.invoiceLogoData || "";
    elements.invoiceLogoPreview.src = logoSrc;
    elements.invoiceLogoPreview.classList.toggle("hidden", !logoSrc);
  }
  applyWebsiteLogo(state.settings.invoiceLogoData || "");
  // IMAP-Felder
  const imapHost = document.querySelector("#imapHost");
  const imapPort = document.querySelector("#imapPort");
  const imapUsername = document.querySelector("#imapUsername");
  const imapPassword = document.querySelector("#imapPassword");
  const imapFolder = document.querySelector("#imapFolder");
  const imapUseSsl = document.querySelector("#imapUseSsl");
  if (imapHost) imapHost.value = state.settings.imapHost || "";
  if (imapPort) imapPort.value = String(state.settings.imapPort || 993);
  if (imapUsername) imapUsername.value = state.settings.imapUsername || "";
  if (imapPassword) imapPassword.value = "";
  if (imapFolder) imapFolder.value = state.settings.imapFolder || "INBOX";
  if (imapUseSsl) imapUseSsl.value = state.settings.imapUseSsl === false ? "0" : "1";
  const impressumText = document.querySelector("#impressumText");
  const datenschutzText = document.querySelector("#datenschutzText");
  if (impressumText) impressumText.value = state.settings.impressumText || "";
  if (datenschutzText) datenschutzText.value = state.settings.datenschutzText || "";
  // Invoice bank/address/tax fields
  const invoiceFields = ["invoiceOperatorStreet", "invoiceOperatorZipCity", "invoiceOperatorPhone",
    "invoiceOperatorWebsite", "invoiceOperatorEmail", "invoiceIban", "invoiceBic", "invoiceBankName", "invoiceTaxId", "invoiceVatId",
    "invoiceEmailSubject", "invoiceEmailIntro"];
  for (const fid of invoiceFields) {
    const el = document.querySelector(`#${fid}`);
    if (el) el.value = state.settings[fid] || "";
  }
}

function showWorkerDetailOverlay(worker) {
  const overlay = document.getElementById("workerDetailOverlay");
  if (!overlay) return;
  const company = state.companies.find((entry) => entry.id === worker.companyId);
  const subcompanyLabel = getSubcompanyLabel(worker);
  const role = String(getCurrentUser()?.role || "").toLowerCase();
  const readOnly = isSupportReadOnlyMode();
  const canResetPin = !readOnly && !isVisitorWorker(worker) && ["superadmin", "company-admin", "turnstile"].includes(role);
  const safePhoto = sanitizeImageSrc(worker.photoData, createAvatar(worker));
  overlay.innerHTML = `
    <div class="worker-detail-card">
      <button class="close-btn" title="${uiT("detailCloseTitle")}">&times;</button>
      <img src="${safePhoto}" alt="${uiT("detailPhotoAlt")}" />
      <h2>${escapeHtml(worker.firstName)} ${escapeHtml(worker.lastName)}</h2>
      <p><strong>${uiT("labelType")}:</strong> ${escapeHtml(isVisitorWorker(worker) ? uiT("optVisitor") : uiT("optWorker"))}</p>
      <p><strong>${uiT("labelFirm")}:</strong> ${escapeHtml(company?.name || "-")}</p>
      ${subcompanyLabel ? `<p><strong>${uiT("labelSubcompany")}:</strong> ${escapeHtml(subcompanyLabel)}</p>` : ""}
      <p><strong>${uiT("badgeLabelBadgeId")}:</strong> ${escapeHtml(worker.badgeId)}</p>
      ${isVisitorWorker(worker) ? `<p><strong>${uiT("labelVisitorCompany")}:</strong> ${escapeHtml(worker.visitorCompany || "-")}</p><p><strong>${uiT("labelVisitPurpose")}:</strong> ${escapeHtml(worker.visitPurpose || "-")}</p><p><strong>${uiT("labelHostName")}:</strong> ${escapeHtml(worker.hostName || "-")}</p><p><strong>${uiT("labelVisitEndAt")}:</strong> ${escapeHtml(worker.visitEndAt ? formatTimestamp(worker.visitEndAt) : "-")}</p>` : `<p><strong>${uiT("labelInsuranceNumber")}:</strong> ${escapeHtml(worker.insuranceNumber)}</p><p><strong>${uiT("labelRoleField")}:</strong> ${escapeHtml(worker.role)}</p>`}
      <p><strong>${uiT("labelSite")}:</strong> ${escapeHtml(worker.site)}</p>
      <p><strong>${uiT("labelValidUntil")}:</strong> ${formatDate(worker.validUntil)}</p>
      <p><strong>${uiT("labelWorkerStatus")}:</strong> ${escapeHtml(worker.status)}</p>
      <p><strong>${uiT("appPinLabel")}:</strong> ${isVisitorWorker(worker) ? uiT("pinNotRequired") : (worker.badgePinConfigured ? uiT("pinSet") : uiT("pinMissing"))}</p>
      <p><strong>${uiT("labelPhysicalCard")}:</strong> ${escapeHtml(worker.physicalCardId || uiT("cardUnassigned"))}</p>
      ${readOnly ? `<p class="helper-text helper-text-info">${escapeHtml(uiT("supportModeReadOnlyLine"))}</p>` : ""}
      <div class="button-row">
        <button type="button" class="primary-button" id="workerCheckInBtn" ${readOnly ? "disabled" : ""}>${uiT("detailCheckinBtn")}</button>
        <button type="button" class="ghost-button" id="workerCheckOutBtn" ${readOnly ? "disabled" : ""}>${uiT("detailCheckoutBtn")}</button>
        ${canResetPin ? `<button type="button" class="ghost-button" id="workerResetPinBtn">${uiT("btnResetPin")}</button>` : ""}
      </div>
      ${!isVisitorWorker(worker) ? `
      <hr style="margin:16px 0; border:none; border-top:1px solid #e5e7eb;" />
      <div class="worker-docs-section">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <h4 style="margin:0;">${escapeHtml(uiT("workerDocsHeading"))}</h4>
          <span class="muted" style="font-size:0.82em;">${escapeHtml(uiT("workerAkteLabel"))}</span>
        </div>
        <div id="workerDocsList"><p class="muted">…</p></div>
      </div>` : ""}
    </div>
  `;
  overlay.classList.remove("hidden");
  overlay.querySelector(".close-btn").onclick = () => overlay.classList.add("hidden");
  overlay.onclick = (e) => { if (e.target === overlay) overlay.classList.add("hidden"); };
  overlay.querySelector("#workerCheckInBtn").onclick = () => {
    triggerWorkerAccess(worker, "check-in");
    overlay.classList.add("hidden");
  };
  overlay.querySelector("#workerCheckOutBtn").onclick = () => {
    triggerWorkerAccess(worker, "check-out");
    overlay.classList.add("hidden");
  };

  const resetButton = overlay.querySelector("#workerResetPinBtn");
  if (resetButton) {
    resetButton.onclick = async () => {
      const name = `${worker.firstName} ${worker.lastName}`.trim() || worker.id;
      const newPin = window.prompt(uiT("promptResetPinFor").replace("{name}", name));
      if (newPin === null) return;
      if (!/^\d{4,8}$/.test(String(newPin).trim())) {
        window.alert(uiT("alertPinMustDigits"));
        return;
      }
      try {
        await apiRequest(`${API_BASE}/api/workers/${worker.id}/reset-pin`, {
          method: "POST",
          body: { newPin: String(newPin).trim() }
        });
        window.alert(uiT("alertPinResetSuccessFor").replace("{name}", name));
        await loadAllData();
        refreshAll();
      } catch (error) {
        window.alert(uiT("alertPinResetFailed").replace("{error}", error.message));
      }
    };
  }

  // Worker-Dokumente laden und rendern
  if (!isVisitorWorker(worker)) {
    const docsContainer = overlay.querySelector("#workerDocsList");
    if (docsContainer) {
      loadWorkerDocuments(worker.id).then((docs) => {
        renderWorkerDocuments(docs, worker.id, docsContainer);
      });
    }
  }
}

async function triggerWorkerAccess(worker, direction) {
  try {
    await apiRequest(API_BASE + "/api/access-logs", {
      method: "POST",
      body: {
        workerId: worker.id,
        direction,
        gate: "Dashboard",
        note: "Dashboard Schnellbuchung"
      }
    });
    await loadAllData();
    refreshAll();
    showAccessFeedback(worker.id, direction, "Dashboard", new Date().toISOString());
  } catch (error) {
    window.alert(uiT("alertAccessBookingFailed").replace("{error}", error.message));
  }
}

window.triggerWorkerAccess = triggerWorkerAccess;

  elements.workerList.querySelectorAll("[data-worker-edit]").forEach((button) => {
    button.addEventListener("click", () => {
      const worker = state.workers.find((entry) => entry.id === button.dataset.workerEdit);
      if (!worker) {
        return;
      }
      if (worker.deletedAt) {
        window.alert(uiT("alertWorkerDeletedCannotEdit"));
        return;
      }

      state.editingWorkerId = worker.id;
      document.querySelector("#companySelect").value = worker.companyId;
      populateSubcompanySelects();
      document.querySelector("#subcompanySelect").value = worker.subcompanyId || "";
      document.querySelector("#firstName").value = worker.firstName;
      document.querySelector("#lastName").value = worker.lastName;
      document.querySelector("#insuranceNumber").value = worker.insuranceNumber;
      document.querySelector("#role").value = worker.role;
      document.querySelector("#site").value = worker.site;
      document.querySelector("#physicalCardId").value = worker.physicalCardId || "";
      document.querySelector("#validUntil").value = worker.validUntil;
      document.querySelector("#workerStatus").value = worker.status;
      document.querySelector("#badgePin").value = "";
      setPhotoEditorSource(worker.photoData || "", { resetOffset: true });
      syncWorkerEditorUi();
      setView("workers");
    });
  });

  elements.workerList.querySelectorAll("[data-worker-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!window.confirm(uiT("confirmDeleteWorker"))) {
        return;
      }

      try {
        await apiRequest(API_BASE + `/api/workers/${button.dataset.workerDelete}`, { method: "DELETE" });
        if (state.editingWorkerId === button.dataset.workerDelete) {
          clearWorkerEditor();
        }
        await loadAllData();
        refreshAll();
      } catch (error) {
        window.alert(uiT("alertDeleteWorkerFailed").replace("{error}", error.message));
      }
    });
  });

  elements.workerList.querySelectorAll("[data-worker-restore]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await apiRequest(API_BASE + `/api/workers/${button.dataset.workerRestore}/restore`, { method: "POST" });
        await loadAllData();
        refreshAll();
      } catch (error) {
        window.alert(uiT("alertRestoreWorkerFailed").replace("{error}", error.message));
      }
    });
  });

  elements.workerList.querySelectorAll("[data-worker-app-link]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const payload = await apiRequest(API_BASE + `/api/workers/${button.dataset.workerAppLink}/app-access`, { method: "POST" });
        const absoluteLink = normalizeWorkerAppLink(payload.link);
        const worker = state.workers.find((entry) => entry.id === button.dataset.workerAppLink) || null;
        showWorkerAppQrDialog(worker, absoluteLink, payload);
      } catch (error) {
        window.alert(uiT("alertAppLinkCreateFailed").replace("{error}", error.message));
      }
    });
  });

function closeWorkerAppQrDialog() {
  const existing = document.querySelector(".worker-app-qr-overlay");
  if (existing) {
    existing.remove();
  }
}

function closeSecretDialog() {
  const existing = document.querySelector(".turnstile-secret-overlay");
  if (existing) {
    existing.remove();
  }
}

function showSecretDialog(title, lines, options = {}) {
  closeSecretDialog();

  const intro = options.intro || "Diese Daten werden nur jetzt angezeigt.";
  const copyLabel = options.copyLabel || "Daten kopieren";
  const copyValue = options.copyValue || lines.join("\n");
  const dialog = document.createElement("div");
  dialog.className = "worker-app-qr-overlay turnstile-secret-overlay";
  dialog.innerHTML = `
    <div class="worker-app-qr-card turnstile-secret-card">
      <h3>${escapeHtml(title || "Geheimer Schluessel")}</h3>
      <p>${escapeHtml(intro)}</p>
      <div class="turnstile-secret-copy">${lines.map((line) => `<span>${escapeHtml(line)}</span>`).join("")}</div>
      <div class="button-row">
        <button type="button" class="primary-button" data-secret-copy>${escapeHtml(copyLabel)}</button>
        <button type="button" class="ghost-button" data-secret-close>Schliessen</button>
      </div>
    </div>
  `;

  document.body.appendChild(dialog);

  dialog.querySelector("[data-secret-close]")?.addEventListener("click", () => {
    closeSecretDialog();
  });

  dialog.querySelector("[data-secret-copy]")?.addEventListener("click", async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(copyValue);
        window.alert(uiT("alertDataCopied"));
      } else {
        window.prompt(uiT("promptCopyData"), copyValue);
      }
    } catch {
      window.prompt(uiT("promptCopyData"), copyValue);
    }
  });

  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) {
      closeSecretDialog();
    }
  });
}

function printWorkerAppQr(workerName, qrSrc) {
  const w = window.open("", "_blank", "width=720,height=840");
  if (!w) {
    window.alert(uiT("alertPrintWindowFailed"));
    return;
  }

  const safeName = escapeHtml(workerName || "Mitarbeiter");
  w.document.write(`
    <!DOCTYPE html>
    <html lang="de" translate="no">
    <head>
      <meta charset="UTF-8" />
      <meta name="google" content="notranslate" />
      <meta http-equiv="Content-Language" content="de" />
      <title>Mitarbeiter-App QR</title>
      <style>
        body { font-family: Arial, sans-serif; margin: 24px; text-align: center; }
        .sheet { border: 1px solid #ddd; border-radius: 16px; padding: 24px; }
        img { width: 320px; height: 320px; object-fit: contain; }
        h1 { margin: 0 0 8px; font-size: 1.4rem; }
        p { margin: 6px 0; color: #444; }
      </style>
    </head>
    <body>
      <div class="sheet">
        <h1>Mitarbeiter-App installieren</h1>
        <p><strong>${safeName}</strong></p>
        <p>QR-Code mit der Kamera scannen und App starten.</p>
        <img src="${qrSrc}" alt="Mitarbeiter App QR" />
      </div>
      <script>window.onload = () => window.print();</script>
    </body>
    </html>
  `);
  w.document.close();
}

function showWorkerAppQrDialog(worker, absoluteLink, payload = null) {
  closeWorkerAppQrDialog();

  const workerName = worker ? `${worker.firstName} ${worker.lastName}` : "Mitarbeiter";
  const isVisitorCard = worker ? isVisitorWorker(worker) : true;
  const linkExpiresAt = payload?.accessExpiresAt ? formatDateTime(payload.accessExpiresAt) : "-";
  const oneTimeHint = payload?.oneTime ? "Einmal-Link: Nach erstem Login ungueltig." : "";
  const dialog = document.createElement("div");
  dialog.className = "worker-app-qr-overlay";

  const qrId = `workerAppQr-${Date.now()}`;
  dialog.innerHTML = `
    <div class="worker-app-qr-card">
      <h3>Besucherkarte QR</h3>
      <p>Fuer: <strong>${escapeHtml(workerName)}</strong></p>
      <p>Code mit der Kamera scannen, um die Besucherkarte digital in der App zu oeffnen.</p>
      <p class="helper-text">Gueltig bis: ${escapeHtml(linkExpiresAt)} Uhr</p>
      ${oneTimeHint ? `<p class="helper-text">${escapeHtml(oneTimeHint)}</p>` : ""}
      <img id="${qrId}" alt="Mitarbeiter App QR" />
      <div class="button-row">
        ${isVisitorCard ? "" : `<button type="button" class="primary-button" data-worker-app-print>QR drucken</button>`}
        <button type="button" class="ghost-button" data-worker-app-copy>Link kopieren</button>
        <button type="button" class="ghost-button" data-worker-app-close>Schliessen</button>
      </div>
    </div>
  `;

  document.body.appendChild(dialog);
  renderRealQr(qrId, absoluteLink);

  dialog.querySelector("[data-worker-app-close]")?.addEventListener("click", () => {
    closeWorkerAppQrDialog();
  });

  dialog.querySelector("[data-worker-app-copy]")?.addEventListener("click", async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(absoluteLink);
        window.alert(uiT("alertAppLinkCopied"));
      } else {
        window.prompt(uiT("promptAppLink"), absoluteLink);
      }
    } catch {
      window.prompt(uiT("promptAppLink"), absoluteLink);
    }
  });

  dialog.querySelector("[data-worker-app-print]")?.addEventListener("click", () => {
    const qrImage = dialog.querySelector(`#${qrId}`);
    if (!qrImage?.src) {
      window.alert(uiT("alertQrNotReadyYet"));
      return;
    }
    printWorkerAppQr(workerName, qrImage.src);
  });

  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) {
      closeWorkerAppQrDialog();
    }
  });
}

function renderBadge() {
  const worker = state.workers.find((entry) => entry.id === state.selectedWorkerId) || state.workers[0] || null;

  if (!worker) {
    elements.badgePreview.innerHTML = runtimeText("badgeEmptyStateShort");
    elements.badgePreview.className = "badge-shell empty-state";
    elements.badgeMeta.innerHTML = runtimeText("badgeNoneSelected");
    elements.badgeMeta.className = "badge-meta empty-state";
    if (elements.badgeActionRow) elements.badgeActionRow.style.display = "none";
    return;
  }

  state.selectedWorkerId = worker.id;
  const company = state.companies.find((entry) => entry.id === worker.companyId);
  const subcompanyLabel = getSubcompanyLabel(worker);
  const qrId = `badge-card-qr-${worker.id}`;
  const visitor = isVisitorWorker(worker);

  elements.badgePreview.className = "badge-shell";
  const siteMapHref = worker.site ? `https://www.google.com/maps/search/${encodeURIComponent(worker.site)}` : "#";
  const validUntilLabel = formatDate(worker.validUntil);
  elements.badgePreview.innerHTML = `
    <div class="badge-card-stage">
      ${buildPrintableWorkerCardMarkup(worker, company)}
      <div class="badge-card-note">
        <div class="badge-info-row">
          <span class="badge-info-icon">📍</span>
          <span class="badge-info-label">${uiT("labelSite") || "Baustelle"}</span>
          <a class="badge-info-value badge-info-link" href="${escapeHtml(siteMapHref)}" target="_blank" rel="noopener noreferrer">${escapeHtml(worker.site || "–")}</a>
        </div>
        <div class="badge-info-row">
          <span class="badge-info-icon">📅</span>
          <span class="badge-info-label">${uiT("labelValidUntil") || "Gültig bis"}</span>
          <span class="badge-info-value">${escapeHtml(validUntilLabel || "–")}</span>
        </div>
        ${subcompanyLabel ? `
        <div class="badge-info-row">
          <span class="badge-info-icon">🏢</span>
          <span class="badge-info-label">${uiT("labelSubcompany") || "Subunternehmer"}</span>
          <span class="badge-info-value">${escapeHtml(subcompanyLabel)}</span>
        </div>` : ""}
        ${visitor ? `
        <div class="badge-info-row">
          <span class="badge-info-icon">👤</span>
          <span class="badge-info-label">${uiT("labelVisitorCompany") || "Firma"}</span>
          <span class="badge-info-value">${escapeHtml(worker.visitorCompany || "–")}</span>
        </div>
        <div class="badge-info-row">
          <span class="badge-info-icon">📝</span>
          <span class="badge-info-label">${uiT("labelVisitPurpose") || "Zweck"}</span>
          <span class="badge-info-value">${escapeHtml(worker.visitPurpose || "–")}</span>
        </div>` : ""}
      </div>
    </div>
  `;

  // Make badge photo placeholder clickable if no photo is present
  setTimeout(() => {
    const badgePhoto = elements.badgePreview.querySelector('.badge-photo-placeholder');
    if (badgePhoto) {
      badgePhoto.title = uiT('badgePhotoUploadHint');
      badgePhoto.addEventListener('click', () => {
        setView('workers');
        state.editingWorkerId = worker.id;
        if (elements.companySelect) elements.companySelect.value = worker.companyId;
        populateSubcompanySelects();
        document.querySelector("#subcompanySelect").value = worker.subcompanyId || "";
        document.querySelector("#firstName").value = worker.firstName || "";
        document.querySelector("#lastName").value = worker.lastName || "";
        document.querySelector("#insuranceNumber").value = worker.insuranceNumber || "";
        document.querySelector("#role").value = worker.role || "";
        document.querySelector("#site").value = worker.site || "";
        document.querySelector("#physicalCardId").value = worker.physicalCardId || "";
        document.querySelector("#validUntil").value = worker.validUntil || "";
        document.querySelector("#workerStatus").value = worker.status || "aktiv";
        document.querySelector("#badgePin").value = "";
        syncWorkerEditorUi();
        setTimeout(() => {
          if (typeof setPhotoEditorSource === 'function') {
            setPhotoEditorSource(worker.photoData || "", { resetOffset: true });
          }
          const cameraBlock = document.querySelector('.camera-block');
          if (cameraBlock) cameraBlock.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }, 200);
      });
    }
  }, 0);

  elements.badgeMeta.className = "badge-meta";
  elements.badgeMeta.innerHTML = `
    <div class="meta-box">
      <p>${uiT("badgeLabelBadgeId")}</p>
      <code>${escapeHtml(worker.badgeId)}</code>
    </div>
    <div class="meta-box">
      <p>Druckformat</p>
      <code>ID-1 Karte 85.6 × 54 mm</code>
    </div>
    <div class="meta-box">
      <p>Ausgabe-Optionen</p>
      <p>Physische Karte drucken <strong>oder</strong> App-Link auf Smartphone senden</p>
    </div>
  `;

  // Show action row with both options
  if (elements.badgeActionRow) elements.badgeActionRow.style.display = "";

  if (elements.printBadgeButton) {
    elements.printBadgeButton.onclick = () => printBadge(worker, state.companies.find(c => c.id === worker.companyId));
  }

  if (elements.appLinkBadgeButton) {
    elements.appLinkBadgeButton.onclick = async () => {
      elements.appLinkBadgeButton.disabled = true;
      elements.appLinkBadgeButton.textContent = "Wird erstellt …";
      try {
        const payload = await apiRequest(`${API_BASE}/api/workers/${worker.id}/app-access`, { method: "POST" });
        const absoluteLink = normalizeWorkerAppLink(payload.link);
        showWorkerAppQrDialog(worker, absoluteLink, payload);
      } catch (error) {
        window.alert(uiT("alertAppLinkCreateFailed").replace("{error}", error.message));
      } finally {
        elements.appLinkBadgeButton.disabled = false;
        elements.appLinkBadgeButton.textContent = "📱 App auf Smartphone";
      }
    };
  }

  renderRealQr(qrId, worker.badgeId || worker.id);
}

async function renderWorkerBadgeAppQr(workerId, qrId, fallbackBadgeId) {
  try {
    const payload = await apiRequest(`${API_BASE}/api/workers/${workerId}/app-access`);
    const appLink = normalizeWorkerAppLink(payload?.link || "");
    if (!appLink) {
      throw new Error("missing_app_link");
    }
    const stillSelected = state.selectedWorkerId === workerId;
    if (!stillSelected) {
      return;
    }
    renderRealQr(qrId, appLink);
  } catch {
    const installFallback = normalizeWorkerAppLink(`${window.location.origin}/worker.html`);
    renderRealQr(qrId, installFallback || fallbackBadgeId);
  }
}

function ensureQrLibrary() {
  return Promise.resolve(false);
}

async function renderRealQr(elementId, payload) {
  const target = document.getElementById(elementId);
  if (!target) {
    return;
  }

  await ensureQrLibrary();
  try {
    const qrUrl = `${API_BASE}/api/qr.png?size=280&data=${encodeURIComponent(payload)}`;
    target.src = qrUrl;
    target.alt = "QR Code";
  } catch {
    target.alt = "QR Code konnte nicht erzeugt werden";
  }
}

function renderRecentAccess() {
  // Nur den jeweils letzten Eintrag pro Mitarbeiter anzeigen (keine Duplikate)
  const sortedAll = [...state.accessLogs].sort((left, right) => right.timestamp.localeCompare(left.timestamp));
  const seenWorkers = new Set();
  const deduplicated = [];
  for (const entry of sortedAll) {
    const key = entry.workerId || entry.id;
    if (!seenWorkers.has(key)) {
      seenWorkers.add(key);
      deduplicated.push(entry);
    }
    if (deduplicated.length >= 5) break;
  }
  const recent = deduplicated;

  if (!recent.length) {
    elements.recentAccessList.innerHTML = `<div class="empty-state">${runtimeText("recentAccessEmpty")}</div>`;
    return;
  }

  elements.recentAccessList.innerHTML = recent
    .map((entry, index) => renderAccessItem(entry, { featured: index === 0 }))
    .join("");

  // Klick-Handler für Einträge
  elements.recentAccessList.querySelectorAll(".recent-access-item").forEach((item) => {
    item.addEventListener("click", () => {
      const worker = state.workers.find((entry) => String(entry.id) === String(item.dataset.workerId));
      if (worker) renderDashboardWorkerDetail(worker);
    });
  });
}

function getPorterOnSiteByCompany() {
  const visibleLogs = [...getUiVisibleAccessLogs()].sort((left, right) => left.timestamp.localeCompare(right.timestamp));
  const workerById = new Map(getUiVisibleWorkers().map((worker) => [worker.id, worker]));
  const lastDirectionByWorker = new Map();

  for (const entry of visibleLogs) {
    if (!entry?.workerId) {
      continue;
    }
    lastDirectionByWorker.set(entry.workerId, entry.direction);
  }

  const companyCounts = new Map();
  for (const [workerId, direction] of lastDirectionByWorker.entries()) {
    if (direction !== "check-in") {
      continue;
    }
    const worker = workerById.get(workerId);
    if (!worker) {
      continue;
    }
    const companyId = worker.companyId || worker.company_id || "";
    const companyName = state.companies.find((entry) => entry.id === companyId)?.name || runtimeText("unknownCompany");
    const currentCount = Number(companyCounts.get(companyName) || 0);
    companyCounts.set(companyName, currentCount + 1);
  }

  return [...companyCounts.entries()]
    .map(([companyName, count]) => ({ companyName, count }))
    .sort((left, right) => right.count - left.count || left.companyName.localeCompare(right.companyName, "de"));
}

function renderDashboardPorterLivePanel() {
  const panel = elements.dashboardPorterLivePanel;
  if (!panel) {
    return;
  }

  const onSiteByCompany = getPorterOnSiteByCompany();
  const companySummaryHtml = onSiteByCompany.length
    ? `
      <div class="porter-company-summary">
        <strong>${runtimeText("porterOnSiteByCompanyHeading")}</strong>
        <div class="porter-company-list">
          ${onSiteByCompany.map((entry) => `<div class="porter-company-item"><span>${escapeHtml(entry.companyName)}</span><span class="porter-company-count">${entry.count}</span></div>`).join("")}
        </div>
      </div>
    `
    : `
      <div class="porter-company-summary empty">
        <strong>${runtimeText("porterOnSiteByCompanyHeading")}</strong>
        <div class="helper-text">${runtimeText("porterNoActiveCheckins")}</div>
      </div>
    `;

  const latest = [...state.accessLogs].sort((left, right) => right.timestamp.localeCompare(left.timestamp))[0] || null;
  if (!latest) {
    panel.className = "porter-live-card empty-state";
    panel.innerHTML = `${runtimeText("dashboardLastAccessPlaceholder")}${companySummaryHtml}`;
    return;
  }

  const worker = state.workers.find((entry) => entry.id === latest.workerId) || null;
  const company = worker ? state.companies.find((entry) => entry.id === worker.companyId) : null;
  const subcompanyLabel = getSubcompanyLabel(worker);
  const directionLabel = latest.direction === "check-in"
    ? runtimeText("dashboardDirectionCheckin")
    : runtimeText("dashboardDirectionCheckout");
  const photoSrc = worker
    ? sanitizeImageSrc(worker.photoData, createAvatar(worker))
    : createAvatar({ firstName: "?", lastName: "?" });
  const workerName = worker ? `${worker.firstName} ${worker.lastName}` : runtimeText("unknownPerson");
  const eventClass = latest.direction === "check-in" ? "porter-event" : "porter-event muted";

  panel.className = "porter-live-card";
  panel.innerHTML = `
    <div class="porter-live-topline">
      <strong>${runtimeText("dashboardLastAccessHeading")}</strong>
      <span>${escapeHtml(formatTimestamp(latest.timestamp))}</span>
    </div>
    <div class="porter-head">
      <img class="porter-photo" src="${photoSrc}" alt="${escapeHtml(workerName)}" />
      <div>
        <strong>${escapeHtml(workerName)}</strong>
        <span>${escapeHtml(company?.name || runtimeText("unknownCompany"))}</span>
        ${subcompanyLabel ? `<span>${escapeHtml(subcompanyLabel)}</span>` : ""}
        <span>${escapeHtml(latest.gate || runtimeText("unknownTurnstile"))}</span>
      </div>
    </div>
    <div class="${eventClass}">${escapeHtml(directionLabel)}${latest.note ? ` | ${escapeHtml(latest.note)}` : ""}</div>
    ${companySummaryHtml}
  `;
}

// Pförtner-View (Zutritts-Ansicht): Firmenzählung aktuell auf der Baustelle
function renderPorterLivePanel() {
  const panel = elements.porterLivePanel;
  if (!panel) {
    return;
  }

  const onSiteByCompany = getPorterOnSiteByCompany();
  if (!onSiteByCompany.length) {
    panel.className = "porter-live-card empty-state";
    panel.innerHTML = `<strong>${runtimeText("porterOnSiteByCompanyHeading")}</strong><p class="helper-text">${runtimeText("porterNoActiveCheckins")}</p>`;
    return;
  }

  const totalOnSite = onSiteByCompany.reduce((sum, entry) => sum + entry.count, 0);
  panel.className = "porter-live-card";
  panel.innerHTML = `
    <div class="porter-company-summary">
      <strong>${runtimeText("porterOnSiteHeading")}</strong>
      <div class="porter-company-total">
        <span>${runtimeText("porterTotal")}</span>
        <span class="porter-company-count">${totalOnSite} ${totalOnSite === 1 ? runtimeText("porterPersonSingular") : runtimeText("porterPersonPlural")}</span>
      </div>
      <div class="porter-company-list">
        ${onSiteByCompany.map((entry) => `
          <div class="porter-company-item">
            <span>${escapeHtml(entry.companyName)}</span>
            <span class="porter-company-count">${entry.count} ${entry.count === 1 ? runtimeText("porterPersonSingular") : runtimeText("porterPersonPlural")}</span>
          </div>`).join("")}
      </div>
    </div>
  `;
}

// Zeige Mitarbeiterdetails direkt im Dashboard-Bereich
function renderDashboardWorkerDetail(worker) {
  // Overlay und Detail-Elemente holen
  const overlay = document.getElementById("dashboardDetailOverlay");
  const detail = document.getElementById("dashboardWorkerDetail");
  if (!overlay || !detail) return;
  const company = state.companies.find((entry) => entry.id === worker.companyId);
  const subcompanyLabel = getSubcompanyLabel(worker);
  const safePhoto = sanitizeImageSrc(worker.photoData, createAvatar(worker));
  detail.innerHTML = `
    <button class="close-btn" title="Schließen">&times;</button>
    <div class="worker-detail-card">
      <img src="${safePhoto}" alt="Mitarbeiterfoto" />
      <h2>${escapeHtml(worker.firstName)} ${escapeHtml(worker.lastName)}</h2>
      <p><strong>Firma:</strong> ${escapeHtml(company?.name || "-")}</p>
      ${subcompanyLabel ? `<p><strong>Subunternehmen:</strong> ${escapeHtml(subcompanyLabel)}</p>` : ""}
      <p><strong>Badge-ID:</strong> ${escapeHtml(worker.badgeId)}</p>
      <p><strong>Rentenversicherung:</strong> ${escapeHtml(worker.insuranceNumber)}</p>
      <p><strong>Funktion:</strong> ${escapeHtml(worker.role)}</p>
      <p><strong>Baustelle:</strong> ${escapeHtml(worker.site)}</p>
      <p><strong>Gültig bis:</strong> ${formatDate(worker.validUntil)}</p>
      <p><strong>Status:</strong> ${escapeHtml(worker.status)}</p>
      <p><strong>Badge-PIN:</strong> ${worker.badgePinConfigured ? "gesetzt" : "nicht gesetzt"}</p>
      <p><strong>Karten-ID:</strong> ${escapeHtml(worker.physicalCardId || "nicht zugewiesen")}</p>
      <div class="button-row">
        <button type="button" class="primary-button" data-worker-id="${escapeHtml(worker.id)}" data-direction="check-in">Anmelden (Check-in)</button>
        <button type="button" class="ghost-button" data-worker-id="${escapeHtml(worker.id)}" data-direction="check-out">Abmelden (Check-out)</button>
      </div>
    </div>
  `;
  overlay.classList.remove("hidden");
  detail.querySelector(".close-btn").onclick = () => overlay.classList.add("hidden");
  overlay.onclick = (e) => { if (e.target === overlay) overlay.classList.add("hidden"); };
  detail.querySelectorAll("[data-worker-id][data-direction]").forEach((button) => {
    button.addEventListener("click", () => {
      const targetWorker = state.workers.find((item) => item.id === button.dataset.workerId);
      if (!targetWorker) {
        return;
      }
      triggerWorkerAccess(targetWorker, button.dataset.direction);
    });
  });
}

function renderAccessLog() {
  document.querySelector("#accessFrom").value = state.accessFilter.from;
  document.querySelector("#accessTo").value = state.accessFilter.to;
  document.querySelector("#accessFilterDirection").value = state.accessFilter.direction;
  document.querySelector("#accessFilterGate").value = state.accessFilter.gate;

  const entries = getUiVisibleAccessLogs().sort((left, right) => right.timestamp.localeCompare(left.timestamp));

  if (!entries.length) {
    elements.accessLogList.innerHTML = `<div class="empty-state">${runtimeText("accessFilterEmpty")}</div>`;
    return;
  }

  elements.accessLogList.innerHTML = entries.map(renderAccessItem).join("");
}

function renderAccessSummary() {
  const entries = getUiVisibleAccessLogs();
  if (!entries.length) {
    elements.accessSummaryGrid.innerHTML = `<div class="empty-state">${runtimeText("dayReportEmpty")}</div>`;
    return;
  }

  const grouped = new Map();
  entries.forEach((entry) => {
    const gateKey = (entry.gate || "Unbekanntes Drehkreuz").trim() || "Unbekanntes Drehkreuz";
    const current = grouped.get(gateKey) || {
      gate: gateKey,
      total: 0,
      checkIn: 0,
      checkOut: 0,
      latest: "",
      visitors: []
    };

    const worker = state.workers.find((item) => item.id === entry.workerId);
    const visitorName = worker ? `${worker.firstName} ${worker.lastName}` : `Mitarbeiter ${entry.workerId}`;
    const visitorMeta = worker && isVisitorWorker(worker)
      ? `${worker.visitorCompany || "Besucherfirma"} | ${worker.visitPurpose || "Besuch"}`
      : "";

    current.total += 1;
    if (entry.direction === "check-in") {
      current.checkIn += 1;
    }
    if (entry.direction === "check-out") {
      current.checkOut += 1;
    }
    if (!current.latest || entry.timestamp > current.latest) {
      current.latest = entry.timestamp;
    }
    const visitorLabel = visitorMeta ? `${visitorName} (${visitorMeta})` : visitorName;
    if (!current.visitors.includes(visitorLabel)) {
      current.visitors.push(visitorLabel);
    }

    grouped.set(gateKey, current);
  });

  const cards = Array.from(grouped.values()).sort((a, b) => a.gate.localeCompare(b.gate));
  elements.accessSummaryGrid.innerHTML = cards
    .map(
      (item) => `
        <article class="summary-card">
          <strong>${escapeHtml(item.gate)}</strong>
          <span>${runtimeText("summaryEntries")}: ${item.checkIn}</span>
          <span>${runtimeText("summaryExits")}: ${item.checkOut}</span>
          <span>${runtimeText("summaryTotal")}: ${item.total}</span>
          <span>${runtimeText("summaryLastBooking")}: ${formatTimestamp(item.latest)}</span>
          <div class="summary-visitor-block">
            <span class="summary-visitor-title">${runtimeText("summaryPeople")}:</span>
            <div class="summary-visitor-list">${item.visitors.map((name) => `<span class="summary-visitor-pill">${escapeHtml(name)}</span>`).join("")}</div>
          </div>
        </article>
      `
    )
    .join("");
}

function renderAccessHourly() {
  const rows = state.accessInsights.hourly || [];
  if (!rows.length) {
    elements.accessHourlyGrid.innerHTML = `<div class="empty-state">${runtimeText("hourlyEmpty")}</div>`;
    return;
  }

  elements.accessHourlyGrid.innerHTML = rows
    .map(
      (row) => `
        <article class="hour-row">
          <strong>${escapeHtml(row.hour)}</strong>
          <span>${runtimeText("hourlyIn")}: ${Number(row.checkIn) || 0}</span>
          <span>${runtimeText("hourlyOut")}: ${Number(row.checkOut) || 0}</span>
        </article>
      `
    )
    .join("");
}

function renderAccessWarnings() {
  const warnings = state.accessInsights.openEntries || [];
  if (!warnings.length) {
    elements.accessOpenWarnings.innerHTML = '<div class="empty-state">Keine offenen Eintritte gefunden.</div>';
    return;
  }

  elements.accessOpenWarnings.innerHTML = warnings
    .slice(0, 40)
    .map(
      (entry) => `
        <article class="list-item warning-item severity-${escapeHtml(getSeverity(entry))}">
          <header>
            <div>
              <strong>${escapeHtml(entry.name)}</strong>
              <span>${escapeHtml(entry.badgeId)}</span>
            </div>
            <span class="status-pill status-check-in">${escapeHtml(getSeverityLabel(getSeverity(entry)))}</span>
          </header>
          <span>Drehkreuz: ${escapeHtml(entry.gate || "Unbekannt")}</span>
          <span>Letzter Eintritt: ${formatTimestamp(entry.timestamp)}</span>
          <span>Offen seit: ${escapeHtml(formatDurationMinutes(getOpenMinutes(entry)))}</span>
        </article>
      `
    )
    .join("");
}

function renderDayCloseBanner() {
  const due = state.dayClose?.due;
  const count = state.dayClose?.openCount || 0;
  const autoClosedCount = state.dayClose?.autoClosedCount || 0;
  const autoClosedEntries = state.dayClose?.autoClosedEntries || [];
  const acknowledgement = state.dayClose?.acknowledgement || null;
  const canAcknowledge = ["superadmin", "company-admin"].includes(getCurrentUser()?.role);

  if (!due) {
    elements.dayCloseBanner.classList.add("hidden");
    elements.dayCloseBanner.textContent = "";
    elements.dayCloseAcknowledgeForm.classList.add("hidden");
    return;
  }

  elements.dayCloseBanner.classList.remove("hidden");
  const isWarning = count > 0 && !acknowledgement;
  const isOk = count === 0 || Boolean(acknowledgement);
  elements.dayCloseBanner.classList.toggle("is-warning", isWarning);
  elements.dayCloseBanner.classList.toggle("is-ok", isOk);

  const autoClosedMarkup = autoClosedCount > 0
    ? `
      <div class="summary-visitor-block">
        <span class="summary-visitor-title">${runtimeText("dayCloseAutoClosedAfterMidnight")}</span>
        <div class="summary-visitor-list">${autoClosedEntries.map((entry) => `<span class="summary-visitor-pill">${escapeHtml(entry.name)}</span>`).join("")}</div>
      </div>
    `
    : "";

  if (acknowledgement) {
    const when = formatTimestamp(acknowledgement.createdAt);
    elements.dayCloseBanner.innerHTML = `<strong>${runtimeText("dayCloseAckTitle")}</strong><span>${runtimeTextTemplate("dayCloseAckByOn", { user: escapeHtml(acknowledgement.acknowledgedBy), when: escapeHtml(when) })}</span><span>${runtimeTextTemplate("dayCloseCommentLabel", { comment: escapeHtml(acknowledgement.comment) })}</span>${autoClosedMarkup}`;
  } else if (count > 0) {
    elements.dayCloseBanner.innerHTML = `<strong>${runtimeText("dayCloseCheckActive")}</strong><span>${runtimeTextTemplate("dayCloseOpenEntriesNoExit", { count })}</span>${autoClosedMarkup}`;
  } else {
    elements.dayCloseBanner.innerHTML = `<strong>${runtimeText("dayCloseCheckActive")}</strong><span>${runtimeText("dayCloseNoOpenEntries")}</span>${autoClosedMarkup}`;
  }

  const showForm = canAcknowledge && count > 0 && !acknowledgement;
  elements.dayCloseAcknowledgeForm.classList.toggle("hidden", !showForm);
  if (!showForm) {
    elements.dayCloseComment.value = "";
  }
}

function triggerAutoDayCloseAlert() {
  const due = state.dayClose?.due;
  const count = state.dayClose?.openCount || 0;
  const acknowledgement = state.dayClose?.acknowledgement || null;
  const date = state.dayClose?.date || new Date().toISOString().slice(0, 10);
  if (!due || count <= 0 || acknowledgement) {
    return;
  }

  const companyScope = getCurrentUser()?.companyId || "system";
  const key = `baupass-day-close-alert-${companyScope}-${date}`;
  if (localStorage.getItem(key) === "1") {
    return;
  }

  localStorage.setItem(key, "1");
  window.alert(runtimeTextTemplate("dayCloseAlertAt18", { count }));
}

async function handleDayCloseAcknowledge(event) {
  event.preventDefault();
  const comment = elements.dayCloseComment.value.trim();
  if (comment.length < 4) {
    window.alert(runtimeText("dayCloseCommentMin"));
    return;
  }

  elements.dayCloseAcknowledgeButton.disabled = true;
  try {
    await apiRequest(API_BASE + "/api/access-logs/day-close-ack", {
      method: "POST",
      body: {
        date: state.dayClose?.date || new Date().toISOString().slice(0, 10),
        comment
      }
    });
    elements.dayCloseComment.value = "";
    await loadAllData();
    refreshAll();
    window.alert(runtimeText("dayCloseAckSuccess"));
  } catch (error) {
    window.alert(uiT("alertDayCloseAckFailed").replace("{error}", error.message));
  } finally {
    elements.dayCloseAcknowledgeButton.disabled = false;
  }
}

function getOpenMinutes(entry) {
  if (typeof entry.openMinutes === "number") {
    return entry.openMinutes;
  }
  const at = new Date(entry.timestamp).getTime();
  if (!Number.isFinite(at)) {
    return 0;
  }
  return Math.max(Math.floor((Date.now() - at) / 60000), 0);
}

function getSeverity(entry) {
  if (entry.severity) {
    return entry.severity;
  }
  const minutes = getOpenMinutes(entry);
  if (minutes >= 240) {
    return "red";
  }
  if (minutes >= 120) {
    return "yellow";
  }
  return "green";
}

function getSeverityLabel(severity) {
  if (severity === "red") {
    return "Kritisch";
  }
  if (severity === "yellow") {
    return "Warnung";
  }
  return "OK";
}

function formatDurationMinutes(minutes) {
  const safeMinutes = Math.max(Number(minutes) || 0, 0);
  const hours = Math.floor(safeMinutes / 60);
  const rest = safeMinutes % 60;
  return `${hours}h ${String(rest).padStart(2, "0")}m`;
}

function renderAccessItem(log, options = {}) {
  const { featured = false } = options;
  const worker = state.workers.find((entry) => entry.id === log.workerId);
  const subcompanyLabel = getSubcompanyLabel(worker);
  const photoSrc = worker
    ? sanitizeImageSrc(worker.photoData, createAvatar(worker))
    : createAvatar({ firstName: "?", lastName: "?" });
  const workerName = worker ? `${worker.firstName} ${worker.lastName}` : "Unbekannt";
  const itemClass = featured ? "list-item recent-access-item clickable access-entry-featured" : "list-item recent-access-item clickable";
  return `
    <article class="${itemClass}" data-worker-id="${worker ? escapeHtml(worker.id) : ""}">
      <div class="access-entry-layout">
        <img class="access-entry-photo" src="${photoSrc}" alt="${escapeHtml(workerName)}" />
        <div class="access-entry-copy">
          <header>
            <div>
              <strong>${escapeHtml(workerName)}</strong>
              <span>${escapeHtml(log.gate)}${subcompanyLabel ? ` | ${escapeHtml(subcompanyLabel)}` : ""}</span>
            </div>
            <span class="status-pill status-${escapeHtml(log.direction)}">${escapeHtml(log.direction)}</span>
          </header>
          <span>${formatTimestamp(log.timestamp)}</span>
          <span>${escapeHtml(log.note || "Keine Notiz")}</span>
        </div>
      </div>
    </article>
  `;
}

function renderTurnstileQuickPanel() {
  if (getCurrentUser()?.role !== "turnstile") {
    elements.turnstileQuickPanel.innerHTML = "";
    return;
  }

  elements.turnstileQuickPanel.innerHTML = `
    <div class="quick-panel-card">
      <strong>Drehkreuz-Schnellmodus</strong>
      <p class="helper-text">Karte auflegen, Enter senden, fertig. Die Richtung wird automatisch gewechselt.</p>
      <div id="turnstileTapLive" class="turnstile-tap-live is-idle" role="status" aria-live="polite">
        <span class="turnstile-tap-dot" aria-hidden="true"></span>
        <strong id="turnstileTapLiveText">Bereit fuer Tap</strong>
      </div>
      <input type="search" id="turnstileCardTapInput" class="turnstile-card-input" placeholder="Karten-ID (NFC/RFID)" autocomplete="off" autocapitalize="off" spellcheck="false" />
      <div class="button-row">
        <button type="button" class="ghost-button" id="turnstileCardTapSubmit">Tap buchen</button>
      </div>
      <p id="turnstileCardTapHint" class="helper-text">Bereit fuer den naechsten Tap.</p>
      <hr style="width:100%; border:none; border-top:1px solid rgba(23,23,23,0.08); margin:8px 0;" />
      <p class="helper-text">Fallback: Mitarbeiter manuell waehlen und Richtung buchen.</p>
      <input type="search" id="turnstileQuickSearch" placeholder="Mitarbeiter suchen" />
      <div id="turnstileQuickPreview" class="meta-box" style="display:flex; gap:12px; align-items:center; margin:10px 0;"></div>
      <div class="button-row">
        <button type="button" class="ghost-button" data-quick-direction="check-in">Schnell Check-in</button>
        <button type="button" class="ghost-button" data-quick-direction="check-out">Schnell Check-out</button>
      </div>
    </div>
  `;

  const searchInput = document.querySelector("#turnstileQuickSearch");
  const preview = document.querySelector("#turnstileQuickPreview");
  const cardTapInput = document.querySelector("#turnstileCardTapInput");
  const cardTapSubmit = document.querySelector("#turnstileCardTapSubmit");
  const cardTapHint = document.querySelector("#turnstileCardTapHint");
  const cardTapLive = document.querySelector("#turnstileTapLive");
  const cardTapLiveText = document.querySelector("#turnstileTapLiveText");
  const normalizeCardId = (value) => String(value || "").trim().toUpperCase();

  const setTapHint = (text) => {
    if (cardTapHint) {
      cardTapHint.textContent = text;
    }
  };

  const setTapLiveState = (stateName, text) => {
    if (!cardTapLive) {
      return;
    }
    cardTapLive.classList.remove("is-idle", "is-pending", "is-success", "is-error");
    cardTapLive.classList.add(stateName);
    if (cardTapLiveText && text) {
      cardTapLiveText.textContent = text;
    }
  };

  const scheduleTapLiveIdleReset = (delayMs = 2200) => {
    if (turnstileTapLiveResetTimer) {
      window.clearTimeout(turnstileTapLiveResetTimer);
    }
    turnstileTapLiveResetTimer = window.setTimeout(() => {
      setTapLiveState("is-idle", "Bereit fuer Tap");
      turnstileTapLiveResetTimer = null;
    }, delayMs);
  };

  const findWorkerByCardId = (cardId) => {
    const normalized = normalizeCardId(cardId);
    if (!normalized) {
      return null;
    }
    return state.workers.find(
      (entry) => normalizeCardId(entry.physicalCardId) === normalized && !entry.deletedAt
    );
  };

  const resolveNextDirection = (workerId) => {
    const latest = [...state.accessLogs]
      .filter((log) => log.workerId === workerId)
      .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))[0];
    return latest?.direction === "check-in" ? "check-out" : "check-in";
  };

  const submitCardTap = async () => {
    if (turnstileTapInFlight) {
      return;
    }
    const normalizedCardId = normalizeCardId(cardTapInput?.value);
    if (!normalizedCardId) {
      setTapHint("Keine Karten-ID gelesen. Bitte erneut auflegen.");
      setTapLiveState("is-error", "Keine Karte erkannt");
      scheduleTapLiveIdleReset();
      showAccessFeedback(null, "check-in", "Drehkreuz Scanner", new Date().toISOString(), {
        isError: true,
        title: "KARTE NICHT ERKANNT",
        message: "Keine Karten-ID gelesen.",
        tone: "error"
      });
      cardTapInput?.focus();
      return;
    }

    const worker = findWorkerByCardId(normalizedCardId);
    if (!worker) {
      setTapHint(`Unbekannte Karte: ${normalizedCardId}`);
      setTapLiveState("is-error", `Unbekannte Karte ${normalizedCardId}`);
      scheduleTapLiveIdleReset();
      showAccessFeedback(null, "check-in", "Drehkreuz Scanner", new Date().toISOString(), {
        isError: true,
        title: "ZUTRITT ABGELEHNT",
        message: `Karte ${normalizedCardId} ist keinem Mitarbeiter zugewiesen.`,
        tone: "error"
      });
      if (cardTapInput) {
        cardTapInput.value = "";
        cardTapInput.focus();
      }
      return;
    }

    const nextDirection = resolveNextDirection(worker.id);
    turnstileTapInFlight = true;
    setTapHint(`Verarbeite ${normalizedCardId} ...`);
    if (turnstileTapLiveResetTimer) {
      window.clearTimeout(turnstileTapLiveResetTimer);
      turnstileTapLiveResetTimer = null;
    }
    setTapLiveState("is-pending", `Pruefe Karte ${normalizedCardId}`);

    try {
      if (elements.accessWorkerSelect) {
        elements.accessWorkerSelect.value = worker.id;
      }
      renderPreview();
      const booking = await bookAccess(worker.id, nextDirection, "Drehkreuz Scanner", "NFC/RFID Tap");
      if (booking?.ok) {
        setTapHint(`Letzter Tap: ${normalizedCardId} (${nextDirection === "check-in" ? "Anmeldung" : "Abmeldung"})`);
        setTapLiveState("is-success", `${worker.firstName || ""} ${worker.lastName || ""}`.trim() || "Zutritt OK");
        scheduleTapLiveIdleReset();
      } else {
        setTapHint(`Tap abgelehnt: ${booking?.message || "Unbekannter Grund"}`);
        setTapLiveState("is-error", "Zutritt abgelehnt");
        scheduleTapLiveIdleReset();
      }
    } finally {
      turnstileTapInFlight = false;
      if (cardTapInput) {
        cardTapInput.value = "";
        window.setTimeout(() => cardTapInput.focus(), 20);
      }
    }
  };

  const renderPreview = () => {
    const worker = state.workers.find((entry) => entry.id === elements.accessWorkerSelect.value);
    if (!preview) return;
    if (!worker) {
      preview.innerHTML = '<span class="helper-text">Noch kein Mitarbeiter ausgewaehlt.</span>';
      return;
    }
    const photoSrc = sanitizeImageSrc(worker.photoData, createAvatar(worker));
    preview.innerHTML = `
      <img src="${photoSrc}" alt="${escapeHtml(`${worker.firstName || ""} ${worker.lastName || ""}`.trim())}" style="width:58px; height:58px; border-radius:14px; object-fit:cover;" />
      <div>
        <strong>${escapeHtml(`${worker.firstName || ""} ${worker.lastName || ""}`.trim())}</strong>
        <span class="muted" style="display:block; font-size:0.84em;">${escapeHtml(worker.badgeId || "-")}</span>
      </div>
    `;
  };

  if (searchInput && elements.accessWorkerSelect) {
    searchInput.addEventListener("input", () => {
      const needle = searchInput.value.trim().toLowerCase();
      Array.from(elements.accessWorkerSelect.options).forEach((option, index) => {
        if (index === 0) return;
        option.hidden = needle ? !option.textContent.toLowerCase().includes(needle) : false;
      });
    });
    elements.accessWorkerSelect.addEventListener("change", renderPreview);
  }
  renderPreview();

  if (cardTapInput) {
    window.setTimeout(() => cardTapInput.focus(), 0);
    cardTapInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        submitCardTap();
      }
    });
    cardTapInput.addEventListener("blur", () => {
      if (getCurrentViewName() === "access" && getCurrentUser()?.role === "turnstile") {
        window.setTimeout(() => cardTapInput.focus(), 60);
      }
    });
  }
  if (cardTapSubmit) {
    cardTapSubmit.addEventListener("click", () => {
      submitCardTap();
    });
  }

  elements.turnstileQuickPanel.querySelectorAll("[data-quick-direction]").forEach((button) => {
    button.addEventListener("click", () => {
      const workerId = elements.accessWorkerSelect.value;
      if (!workerId) {
        window.alert(runtimeText("turnstileSelectWorkerFirst"));
        return;
      }
      bookAccess(workerId, button.dataset.quickDirection, "Drehkreuz Schnellmodus", "Terminalbuchung");
    });
  });
}

async function handleWorkerSubmit(event) {
  event.preventDefault();
  if (!userCanManageWorkers()) {
    return;
  }

  const firstName = document.querySelector("#firstName").value.trim();
  const lastName = document.querySelector("#lastName").value.trim();

  const photoDataValue = document.querySelector("#photoData").value;
  if (!photoDataValue) {
    window.alert(runtimeText("workerPhotoRequired"));
    setView("workers");
    const cameraBlock = document.querySelector(".camera-block");
    if (cameraBlock) {
      cameraBlock.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    return;
  }
  const payload = {
    companyId: document.querySelector("#companySelect").value,
    subcompanyId: document.querySelector("#subcompanySelect").value || null,
    workerType: elements.workerType?.value || "worker",
    firstName,
    lastName,
    insuranceNumber: document.querySelector("#insuranceNumber").value.trim(),
    role: document.querySelector("#role").value.trim(),
    site: document.querySelector("#site").value.trim(),
    physicalCardId: document.querySelector("#physicalCardId").value.trim(),
    validUntil: document.querySelector("#validUntil").value,
    visitorCompany: elements.visitorCompany?.value.trim() || "",
    visitPurpose: elements.visitPurpose?.value.trim() || "",
    hostName: elements.hostName?.value.trim() || "",
    visitEndAt: elements.visitEndAt?.value || "",
    status: document.querySelector("#workerStatus").value,
    photoData: photoDataValue,
    badgeId: buildBadgeId(firstName, lastName, elements.workerType?.value || "worker"),
    badgePin: document.querySelector("#badgePin").value.trim()
  };

  try {
    let targetWorkerId = state.editingWorkerId || null;

    if (state.editingWorkerId) {
      const existingWorker = state.workers.find((entry) => entry.id === state.editingWorkerId) || null;
      const existingPhoto = existingWorker?.photoData || "";
      const newPhoto = payload.photoData || "";
      if (existingPhoto && newPhoto && existingPhoto !== newPhoto) {
        const compare = await compareWorkerPhotoSimilarity(existingPhoto, newPhoto);
        if (compare.comparable && compare.similarity < 0.62) {
          const scorePct = Math.round(compare.similarity * 100);
          const role = String(getCurrentUser()?.role || "").toLowerCase();
          const canOverride = role === "superadmin";
          if (!canOverride) {
            window.alert(uiT("alertPhotoMatchFailed").replace("{score}", scorePct));
            return;
          }
          const proceed = window.confirm(
            uiT("confirmPhotoMatchFailed").replace("{score}", scorePct)
          );
          if (!proceed) {
            return;
          }
          const overrideReason = window.prompt(uiT("promptPhotoOverrideReason"), "") || "";
          if (overrideReason.trim().length < 8) {
            window.alert(uiT("alertOverrideReasonTooShort"));
            return;
          }
          payload.photoMatchOverride = true;
          payload.photoMatchSimilarity = Number(compare.similarity.toFixed(4));
          payload.photoMatchOverrideReason = overrideReason.trim();
        }
      }
    }

    if (state.editingWorkerId) {
      const result = await apiRequest(API_BASE + `/api/workers/${state.editingWorkerId}`, { method: "PUT", body: payload });
      if (result?.approvalRequested) {
        window.alert(uiT("alertPhotoOverrideRequested").replace("{id}", result.approvalId || "?"));
        clearWorkerEditor();
        stopCamera();
        await loadAllData();
        refreshAll();
        setView("workers");
        return;
      }
    } else {
      const createdWorker = await apiRequest(API_BASE + "/api/workers", { method: "POST", body: payload });
      targetWorkerId = createdWorker?.id || null;
    }
    clearWorkerEditor();
    stopCamera();
    await loadAllData();
    if (targetWorkerId && state.workers.some((worker) => worker.id === targetWorkerId)) {
      state.selectedWorkerId = targetWorkerId;
    }
    refreshAll();
    setView("badge");
  } catch (error) {
    if (error.message === "invalid_badge_pin") {
      window.alert(uiT("alertBadgePinInvalid"));
      return;
    }
    if (error.message === "badge_pin_required") {
      window.alert(runtimeText("workerBadgePinMissing"));
      return;
    }
    if (error.message === "duplicate_physical_card_id") {
      window.alert(uiT("alertDuplicatePhysicalCardId"));
      return;
    }
    if (error.message === "photo_override_forbidden") {
      window.alert(uiT("alertPhotoOverrideSuperadminOnly"));
      return;
    }
    if (error.message === "photo_override_reason_required") {
      window.alert(uiT("alertPhotoOverrideReasonRequired"));
      return;
    }
    if (error.message === "visit_purpose_required") {
      window.alert(runtimeText("visitorPurposeMissing"));
      return;
    }
    if (error.message === "visitor_company_required") {
      window.alert(runtimeText("visitorCompanyMissing"));
      return;
    }
    if (error.message === "host_name_required") {
      window.alert(runtimeText("visitorHostMissing"));
      return;
    }
    if (error.message === "visit_end_required") {
      window.alert(runtimeText("visitorEndMissing"));
      return;
    }
    window.alert(uiT("alertWorkerSaveFailed").replace("{error}", error.message));
  }
}

async function handleAccessSubmit(event) {
  event.preventDefault();
  await bookAccess(
    document.querySelector("#accessWorkerSelect").value,
    document.querySelector("#accessDirection").value,
    document.querySelector("#accessGate").value.trim(),
    document.querySelector("#accessNote").value.trim()
  );
}

async function bookAccess(workerId, direction, gate, note) {
  if (isSupportReadOnlyMode()) {
    showSupportReadOnlyAlert();
    return;
  }
  if (!workerId) {
    return;
  }

  // Prevent multiple consecutive check-ins or check-outs
  const lastEvent = [...state.accessLogs]
    .filter((log) => log.workerId === workerId)
    .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))[0];
  if (lastEvent && lastEvent.direction === direction) {
    const duplicateMessage =
      direction === "check-in"
        ? "Diese Karte ist bereits angemeldet. Erst abmelden, dann erneut anmelden."
        : "Diese Karte ist bereits abgemeldet. Erst anmelden, dann erneut abmelden.";
    if (getCurrentUser()?.role === "turnstile") {
      showAccessFeedback(workerId, direction, gate, new Date().toISOString(), {
        isError: true,
        title: "ZUTRITT ABGELEHNT",
        message: duplicateMessage,
        tone: "error"
      });
    } else {
      // Roten Banner im Formular anzeigen statt window.alert
      const banner = elements.accessDuplicateError;
      if (banner) {
        banner.textContent = duplicateMessage;
        banner.classList.remove("hidden");
        // Nach 5 Sekunden automatisch ausblenden
        clearTimeout(banner._hideTimer);
        banner._hideTimer = setTimeout(() => banner.classList.add("hidden"), 5000);
      }
    }
    return { ok: false, reason: "duplicate_direction", message: duplicateMessage };
  }

  try {
    const createdLog = await apiRequest(API_BASE + "/api/access-logs", {
      method: "POST",
      body: {
        workerId,
        direction,
        gate,
        note,
        timestamp: new Date().toISOString()
      }
    });
    state.porterLive.workerId = workerId;
    state.porterLive.lastEvent = normalizeLog(createdLog);
    showAccessFeedback(workerId, direction, gate, createdLog.timestamp, {
      title: direction === "check-in" ? "ANMELDUNG ERFOLGREICH" : "ABMELDUNG ERFOLGREICH",
      message: direction === "check-in" ? "Du bist jetzt angemeldet." : "Du bist jetzt abgemeldet.",
      tone: direction === "check-in" ? "success_in" : "success_out"
    });
    await loadAllData();
    refreshAll();
    return { ok: true, direction, timestamp: createdLog.timestamp };
  } catch (error) {
    const denyMessage = error?.message ? String(error.message) : "Unbekannter Fehler";
    if (getCurrentUser()?.role === "turnstile") {
      showAccessFeedback(workerId, direction, gate, new Date().toISOString(), {
        isError: true,
        title: "ZUTRITT ABGELEHNT",
        message: `Buchung fehlgeschlagen: ${denyMessage}`,
        tone: "error"
      });
      return { ok: false, reason: denyMessage, message: denyMessage };
    }
    window.alert(uiT("alertAccessBookingFailed").replace("{error}", denyMessage));
    return { ok: false, reason: denyMessage, message: denyMessage };
  }
}

function showAccessFeedback(workerId, direction, gate, timestamp, options = {}) {
  const worker = state.workers.find((entry) => entry.id === workerId);
  const company = worker ? state.companies.find((entry) => entry.id === worker.companyId) : null;
  const subcompanyLabel = getSubcompanyLabel(worker);
  const isError = Boolean(options.isError);
  const title = options.title || (direction === "check-in" ? "ANMELDUNG ERFOLGREICH" : "ABMELDUNG ERFOLGREICH");
  const primaryMessage =
    options.message || (direction === "check-in" ? "Du bist jetzt angemeldet." : "Du bist jetzt abgemeldet.");
  const dirLabel = direction === "check-in" ? "Anmeldung" : "Abmeldung";
  const who = worker ? `${worker.firstName} ${worker.lastName}` : "Mitarbeiter";
  const companyLabel = company?.name || "Unbekannte Firma";
  const subLabel = subcompanyLabel ? ` | ${subcompanyLabel}` : "";
  const when = formatTimestamp(timestamp || new Date().toISOString());

  elements.accessFeedbackTitle.textContent = title;
  elements.accessFeedbackMeta.textContent = `${primaryMessage} | ${who} | ${companyLabel}${subLabel} | ${dirLabel} | ${gate} | ${when}`;
  elements.accessFeedbackPhoto.src = worker
    ? sanitizeImageSrc(worker.photoData, createAvatar(worker))
    : createAvatar({ firstName: "?", lastName: "?" });
  elements.accessFeedbackPhoto.alt = worker ? `${worker.firstName} ${worker.lastName}` : "Mitarbeiterfoto";
  elements.accessFeedbackOverlay.classList.remove("hidden", "feedback-in", "feedback-out", "feedback-error");
  if (isError) {
    elements.accessFeedbackOverlay.classList.add("feedback-error");
  } else {
    elements.accessFeedbackOverlay.classList.add(direction === "check-in" ? "feedback-in" : "feedback-out");
  }

  // Zeige auch den Baustellen-Ausweis mit Foto
  if (worker && !isError) {
    state.selectedWorkerId = worker.id;
    renderBadge();
    // Schalte zur Badge-Ansicht um
    const badgeTab = document.querySelector('a[href="#badge"]') || document.querySelector('[data-view="badge"]');
    if (badgeTab) badgeTab.click();
  }

  playAccessTone(options.tone || (isError ? "error" : direction));

  if (accessFeedbackTimer) {
    window.clearTimeout(accessFeedbackTimer);
  }
  accessFeedbackTimer = window.setTimeout(() => {
    elements.accessFeedbackOverlay.classList.add("hidden");
    elements.accessFeedbackOverlay.classList.remove("feedback-in", "feedback-out", "feedback-error");
  }, 3500);
}

function playAccessTone(tone) {
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) {
      return;
    }
    if (!accessAudioContext) {
      accessAudioContext = new AudioCtx();
    }

    const baseTime = accessAudioContext.currentTime;
    let sequence = [660, 880];
    if (tone === "check-out" || tone === "success_out") {
      sequence = [440, 330];
    }
    if (tone === "error") {
      sequence = [220, 165, 120];
    }
    sequence.forEach((freq, index) => {
      const osc = accessAudioContext.createOscillator();
      const gain = accessAudioContext.createGain();
      osc.type = tone === "error" ? "triangle" : "sine";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, baseTime + index * 0.12);
      gain.gain.exponentialRampToValueAtTime(tone === "error" ? 0.22 : 0.18, baseTime + index * 0.12 + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, baseTime + index * 0.12 + 0.1);
      osc.connect(gain);
      gain.connect(accessAudioContext.destination);
      osc.start(baseTime + index * 0.12);
      osc.stop(baseTime + index * 0.12 + 0.11);
    });
  } catch {
    // ignore audio errors
  }
}

async function handleAccessFilterSubmit(event) {
  event.preventDefault();
  state.accessFilter.from = document.querySelector("#accessFrom").value;
  state.accessFilter.to = document.querySelector("#accessTo").value;
  state.accessFilter.direction = document.querySelector("#accessFilterDirection").value;
  state.accessFilter.gate = document.querySelector("#accessFilterGate").value.trim();
  await loadAllData();
  refreshAll();
}

async function resetAccessFilter() {
  state.accessFilter = { from: "", to: "", direction: "", gate: "" };
  await loadAllData();
  refreshAll();
}

async function exportAccessCsv() {
  try {
    const query = new URLSearchParams();
    if (state.accessFilter.from) {
      query.set("from", state.accessFilter.from);
    }
    if (state.accessFilter.to) {
      query.set("to", state.accessFilter.to);
    }
    if (state.accessFilter.direction) {
      query.set("direction", state.accessFilter.direction);
    }
    if (state.accessFilter.gate) {
      query.set("gate", state.accessFilter.gate);
    }
    const suffix = query.toString() ? `?${query.toString()}` : "";

    const response = await fetch(`${API_BASE}/api/access-logs/export.csv${suffix}`, {
      headers: {
        Authorization: `Bearer ${token}`
      }
    });

    if (!response.ok) {
      throw new Error(`API Fehler ${response.status}`);
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `zutrittsjournal-${new Date().toISOString().slice(0, 10)}.pdf`;
    link.click();
    URL.revokeObjectURL(url);
  } catch (error) {
    window.alert(uiT("alertAccessExportFailed").replace("{error}", error.message));
  }
}

function exportWorkersPdf() {
  const today = new Date().toISOString().slice(0, 10);
  const overlay = document.createElement("div");
  overlay.className = "turnstile-secret-overlay";
  overlay.innerHTML = `
    <div class="turnstile-secret-card" style="max-width:420px">
      <p class="eyebrow">Mitarbeiterliste</p>
      <h3 style="margin:0 0 18px">PDF-Export Optionen</h3>
      <div style="display:grid;gap:14px;margin-bottom:20px">
        <label style="display:flex;align-items:center;gap:10px;cursor:pointer">
          <input type="checkbox" id="wlIncludePhotos" style="width:18px;height:18px" />
          <span>Mit Fotos (Passfoto je Mitarbeiter)</span>
        </label>
        <label style="display:flex;flex-direction:column;gap:6px">
          <span style="font-weight:600">Zeitraum</span>
          <select id="wlPeriod" style="padding:8px 12px;border-radius:8px;border:1.5px solid #ddd;font-size:14px">
            <option value="all">Alle aktiven Mitarbeiter</option>
            <option value="today">Heute</option>
            <option value="week">Diese Woche</option>
            <option value="day">Bestimmter Tag</option>
          </select>
        </label>
        <label id="wlCustomDateWrap" style="display:none;flex-direction:column;gap:6px">
          <span style="font-weight:600">Datum</span>
          <input type="date" id="wlCustomDate" value="${today}" style="padding:8px 12px;border-radius:8px;border:1.5px solid #ddd;font-size:14px" />
        </label>
      </div>
      <div style="display:flex;gap:12px;justify-content:flex-end">
        <button type="button" class="ghost-button" id="wlCancelBtn">Abbrechen</button>
        <button type="button" class="primary-button" id="wlDownloadBtn">PDF herunterladen</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  const periodSel = overlay.querySelector("#wlPeriod");
  const customWrap = overlay.querySelector("#wlCustomDateWrap");
  periodSel.addEventListener("change", () => {
    customWrap.style.display = periodSel.value === "day" ? "flex" : "none";
  });
  overlay.querySelector("#wlCancelBtn").addEventListener("click", () => overlay.remove());
  overlay.addEventListener("click", (ev) => { if (ev.target === overlay) overlay.remove(); });

  overlay.querySelector("#wlDownloadBtn").addEventListener("click", async () => {
    const includePhotos = overlay.querySelector("#wlIncludePhotos").checked;
    const periodVal = periodSel.value;
    const customDate = overlay.querySelector("#wlCustomDate").value || today;
    overlay.remove();

    const query = new URLSearchParams();
    if (includePhotos) query.set("includePhotos", "1");
    if (periodVal === "today") { query.set("period", "day"); query.set("date", today); }
    else if (periodVal === "week") { query.set("period", "week"); query.set("date", today); }
    else if (periodVal === "day") { query.set("period", "day"); query.set("date", customDate); }
    const suffix = query.toString() ? `?${query.toString()}` : "";

    try {
      const response = await fetch(`${API_BASE}/api/workers/export.pdf${suffix}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!response.ok) throw new Error(`API Fehler ${response.status}`);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `mitarbeiterliste-${today}.pdf`;
      link.style.display = "none";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (error) {
      window.alert(uiT("alertWorkerExportFailed").replace("{error}", error.message));
    }
  });
}

function printDailyReport() {
  const now = new Date();
  const fromLabel = state.accessFilter.from || now.toISOString().slice(0, 10);
  const toLabel = state.accessFilter.to || fromLabel;
  const role = getRoleLabel(getCurrentUser()?.role || "unbekannt");
  const summaryItems = Array.from(document.querySelectorAll("#accessSummaryGrid .summary-card")).map((card) => card.outerHTML).join("");
  const warningItems = Array.from(document.querySelectorAll("#accessOpenWarnings .warning-item")).map((card) => card.outerHTML).join("");
  const visitorRows = getVisitorReportRows(fromLabel, toLabel)
    .map((entry) => `<tr><td>${escapeHtml(entry.name)}</td><td>${escapeHtml(entry.visitorCompany || "-")}</td><td>${escapeHtml(entry.purpose || "-")}</td><td>${escapeHtml(entry.hostName || "-")}</td><td>${escapeHtml(entry.site || "-")}</td><td>${escapeHtml(entry.lastSeen || "-")}</td></tr>`)
    .join("");

  const html = `
    <!DOCTYPE html>
    <html lang="de" translate="no">
    <head>
      <meta charset="UTF-8" />
      <meta name="google" content="notranslate" />
      <meta http-equiv="Content-Language" content="de" />
      <title>Zutrittsreport</title>
      <style>
        body { font-family: Arial, sans-serif; padding: 24px; color: #222; }
        h1, h2 { margin: 0 0 10px; }
        .muted { color: #555; margin-bottom: 18px; }
        .grid { display: grid; gap: 10px; }
        .summary-card, .warning-item { border: 1px solid #ddd; border-radius: 10px; padding: 10px; margin-bottom: 8px; }
        table { width: 100%; border-collapse: collapse; margin-top: 12px; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; font-size: 12px; }
        th { background: #f3f6f8; }
        .summary-visitor-block { margin-top: 8px; }
        .summary-visitor-title { display: block; font-weight: 700; color: #333; margin-bottom: 6px; }
        .summary-visitor-list { display: flex; gap: 6px; flex-wrap: wrap; }
        .summary-visitor-pill { display: inline-block; padding: 4px 8px; border-radius: 999px; background: #eef2f6; color: #334; font-size: 12px; }
      </style>
    </head>
    <body>
      <h1>Zutrittsreport</h1>
      <p class="muted">Zeitraum: ${fromLabel} bis ${toLabel} | Rolle: ${escapeHtml(role)}</p>
      <h2>Drehkreuz-Uebersicht</h2>
      <div class="grid">${summaryItems || "<p>Keine Daten.</p>"}</div>
      <h2>Offene Eintritte</h2>
      <div class="grid">${warningItems || "<p>Keine offenen Eintritte.</p>"}</div>
      <h2>Besucher im Zeitraum</h2>
      ${visitorRows ? `<table><thead><tr><th>Name</th><th>Firma</th><th>Zweck</th><th>Ansprechpartner</th><th>Baustelle</th><th>Letzte Aktivität</th></tr></thead><tbody>${visitorRows}</tbody></table>` : "<p>Keine Besucher im Zeitraum.</p>"}
    </body>
    </html>
  `;

  const reportWindow = window.open("", "_blank", "width=960,height=800");
  if (!reportWindow) {
    window.alert(runtimeText("popupBlockedAllow"));
    return;
  }
  reportWindow.document.open();
  reportWindow.document.write(html);
  reportWindow.document.close();
  reportWindow.focus();
  reportWindow.print();
}

function getVisitorReportRows(fromDate, toDate) {
  const fromTs = fromDate ? new Date(`${fromDate}T00:00:00`).getTime() : Date.now() - (7 * 24 * 60 * 60 * 1000);
  const toTs = toDate ? new Date(`${toDate}T23:59:59`).getTime() : Date.now();
  return state.workers
    .filter((worker) => !worker.deletedAt && isVisitorWorker(worker))
    .map((worker) => {
      const lastLog = [...state.accessLogs]
        .filter((log) => log.workerId === worker.id)
        .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))[0];
      const lastSeenTs = lastLog ? new Date(lastLog.timestamp).getTime() : 0;
      return {
        id: worker.id,
        name: `${worker.firstName} ${worker.lastName}`.trim(),
        visitorCompany: worker.visitorCompany || "",
        purpose: worker.visitPurpose || "",
        hostName: worker.hostName || "",
        site: worker.site || "",
        lastSeenTs,
        lastSeen: lastLog ? formatTimestamp(lastLog.timestamp) : (worker.visitEndAt ? formatTimestamp(worker.visitEndAt) : "-")
      };
    })
    .filter((entry) => entry.lastSeenTs === 0 || (entry.lastSeenTs >= fromTs && entry.lastSeenTs <= toTs))
    .sort((a, b) => b.lastSeenTs - a.lastSeenTs);
}

function printVisitorWeeklyReport() {
  const end = new Date();
  const start = new Date(Date.now() - (6 * 24 * 60 * 60 * 1000));
  const rows = getVisitorReportRows(toDateInputValue(start), toDateInputValue(end));
  const htmlRows = rows.map((entry) => `<tr><td>${escapeHtml(entry.name)}</td><td>${escapeHtml(entry.visitorCompany || "-")}</td><td>${escapeHtml(entry.purpose || "-")}</td><td>${escapeHtml(entry.hostName || "-")}</td><td>${escapeHtml(entry.site || "-")}</td><td>${escapeHtml(entry.lastSeen || "-")}</td></tr>`).join("");
  const reportWindow = window.open("", "_blank", "width=1100,height=800");
  if (!reportWindow) {
    window.alert(runtimeText("popupBlockedAllow"));
    return;
  }
  reportWindow.document.open();
  reportWindow.document.write(`<!DOCTYPE html><html lang="de" translate="no"><head><meta charset="UTF-8" /><meta name="google" content="notranslate" /><meta http-equiv="Content-Language" content="de" /><title>Besucher-Wochenliste</title><style>body{font-family:Arial,sans-serif;padding:24px;color:#222}table{width:100%;border-collapse:collapse;margin-top:12px}th,td{border:1px solid #ddd;padding:8px;text-align:left;font-size:12px}th{background:#f3f6f8}h1{margin:0 0 8px}.muted{color:#555}</style></head><body><h1>Besucher-Wochenliste</h1><p class="muted">Zeitraum: ${escapeHtml(toDateInputValue(start))} bis ${escapeHtml(toDateInputValue(end))}</p>${htmlRows ? `<table><thead><tr><th>Name</th><th>Firma</th><th>Zweck</th><th>Ansprechpartner</th><th>Baustelle</th><th>Letzte Aktivität</th></tr></thead><tbody>${htmlRows}</tbody></table>` : "<p>Keine Besucher in dieser Woche.</p>"}</body></html>`);
  reportWindow.document.close();
  reportWindow.focus();
  reportWindow.print();
}

async function handleSettingsSubmit(event) {
  event.preventDefault();
  if (!userCanManageSystem()) {
    return;
  }

  try {
    const settingsBody = {
      platformName: document.querySelector("#platformName").value.trim(),
      operatorName: document.querySelector("#operatorName").value.trim(),
      turnstileEndpoint: (document.querySelector("#companyTurnstileEndpoint")?.value || "").trim(),
      rentalModel: document.querySelector("#rentalModel").value,
      invoiceLogoData: elements.invoiceLogoData.value,
      invoicePrimaryColor: document.querySelector("#invoicePrimaryColor").value,
      invoiceAccentColor: document.querySelector("#invoiceAccentColor").value,
      smtpHost: document.querySelector("#smtpHost").value.trim(),
      smtpPort: Number(document.querySelector("#smtpPort").value || 587),
      smtpUsername: document.querySelector("#smtpUsername").value.trim(),
      smtpSenderEmail: document.querySelector("#smtpSenderEmail").value.trim(),
      smtpSenderName: document.querySelector("#smtpSenderName").value.trim(),
      smtpUseTls: document.querySelector("#smtpUseTls").value === "1",
      adminIpWhitelist: document.querySelector("#adminIpWhitelist").value.trim(),
      enforceTenantDomain: document.querySelector("#enforceTenantDomain").value === "1",
      workerAppEnabled: document.querySelector("#workerAppEnabled").value !== "0",
      imapHost: (document.querySelector("#imapHost")?.value || "").trim(),
      imapPort: Number(document.querySelector("#imapPort")?.value || 993),
      imapUsername: (document.querySelector("#imapUsername")?.value || "").trim(),
      imapFolder: (document.querySelector("#imapFolder")?.value || "INBOX").trim() || "INBOX",
      imapUseSsl: document.querySelector("#imapUseSsl")?.value !== "0",
      impressumText: (document.querySelector("#impressumText")?.value || ""),
      datenschutzText: (document.querySelector("#datenschutzText")?.value || ""),
      brevoApiKey: (document.querySelector("#brevoApiKey")?.value || ""),
      brevoFromEmail: (document.querySelector("#brevoFromEmail")?.value || "").trim(),
      invoiceOperatorStreet: (document.querySelector("#invoiceOperatorStreet")?.value || "").trim(),
      invoiceOperatorZipCity: (document.querySelector("#invoiceOperatorZipCity")?.value || "").trim(),
      invoiceOperatorPhone: (document.querySelector("#invoiceOperatorPhone")?.value || "").trim(),
      invoiceOperatorWebsite: (document.querySelector("#invoiceOperatorWebsite")?.value || "").trim(),
      invoiceOperatorEmail: (document.querySelector("#invoiceOperatorEmail")?.value || "").trim(),
      invoiceIban: (document.querySelector("#invoiceIban")?.value || "").trim(),
      invoiceBic: (document.querySelector("#invoiceBic")?.value || "").trim(),
      invoiceBankName: (document.querySelector("#invoiceBankName")?.value || "").trim(),
      invoiceTaxId: (document.querySelector("#invoiceTaxId")?.value || "").trim(),
      invoiceVatId: (document.querySelector("#invoiceVatId")?.value || "").trim(),
      invoiceEmailSubject: (document.querySelector("#invoiceEmailSubject")?.value || "").trim(),
      invoiceEmailIntro: (document.querySelector("#invoiceEmailIntro")?.value || "").trim(),
    };
    const smtpPasswordValue = document.querySelector("#smtpPassword")?.value || "";
    if (smtpPasswordValue.trim()) {
      settingsBody.smtpPassword = smtpPasswordValue;
    }
    const imapPasswordValue = document.querySelector("#imapPassword")?.value || "";
    if (imapPasswordValue.trim()) {
      settingsBody.imapPassword = imapPasswordValue;
    }

    const updated = await apiRequest(API_BASE + "/api/settings", {
      method: "PUT",
      body: settingsBody
    });

    const supportPhoneInput = String(document.querySelector("#supportPhone")?.value || "").trim();
    try {
      if (supportPhoneInput) {
        window.localStorage.setItem(SUPPORT_PHONE_STORAGE_KEY, supportPhoneInput);
      } else {
        window.localStorage.removeItem(SUPPORT_PHONE_STORAGE_KEY);
      }
    } catch {
      // ignore storage failures (private mode / quota)
    }

    state.settings = updated;
    document.dispatchEvent(new CustomEvent("baupass:settingsLoaded"));
    refreshAll();
  } catch (error) {
    window.alert(uiT("alertSettingsSaveFailed").replace("{error}", error.message));
  }
}

function getCurrentSmtpSettingsFromForm() {
  const settings = {
    platformName: document.querySelector("#platformName")?.value.trim() || "",
    operatorName: document.querySelector("#operatorName")?.value.trim() || "",
    invoicePrimaryColor: document.querySelector("#invoicePrimaryColor")?.value || "#0f4c5c",
    invoiceAccentColor: document.querySelector("#invoiceAccentColor")?.value || "#e36414",
    smtpHost: document.querySelector("#smtpHost")?.value.trim() || "",
    smtpPort: Number(document.querySelector("#smtpPort")?.value || 587),
    smtpUsername: document.querySelector("#smtpUsername")?.value.trim() || "",
    smtpSenderEmail: document.querySelector("#smtpSenderEmail")?.value.trim() || "",
    smtpSenderName: document.querySelector("#smtpSenderName")?.value.trim() || "",
    smtpUseTls: document.querySelector("#smtpUseTls")?.value === "1",
    brevoApiKey: document.querySelector("#brevoApiKey")?.value || "",
    brevoFromEmail: document.querySelector("#brevoFromEmail")?.value.trim() || "",
  };
  const smtpPassword = document.querySelector("#smtpPassword")?.value || "";
  if (smtpPassword.trim()) {
    settings.smtpPassword = smtpPassword;
  }
  return settings;
}

function formatResendEnvState(payload) {
  const known = Array.isArray(payload?.resendEnv?.known) ? payload.resendEnv.known : [];
  if (!known.length) return "";
  const keyNames = [
    "RESEND_API_KEY",
    "RESEND_KEY",
    "RESEND_API_TOKEN",
    "BAUPASS_RESEND_API_KEY",
    "RESEND_APIKEY",
    "RESEND_TOKEN"
  ];
  const states = keyNames
    .map((name) => {
      const row = known.find((item) => item?.name === name);
      if (!row) return "";
      return `${name}: ${row.set ? "gesetzt" : "leer"}`;
    })
    .filter(Boolean);
  return states.length ? `Env-Check: ${states.join(", ")}` : "";
}

function formatApiFallbackState(payload) {
  const hasResend = payload?.resendConfigured === true;
  const hasBrevo = payload?.brevoConfigured === true;
  if (!hasResend && !hasBrevo) return "API-Fallback nicht erkannt";
  if (hasResend && hasBrevo) return "API-Fallback erkannt (Resend + Brevo)";
  if (hasBrevo) return "API-Fallback erkannt (Brevo)";
  return `API-Fallback erkannt (Resend${payload?.resendKeySource ? `: ${payload.resendKeySource}` : ""})`;
}

function formatSmtpTestError(err) {
  if (err?.code === "smtp_not_configured") {
    const missingFields = Array.isArray(err?.payload?.missingFields) ? err.payload.missingFields : [];
    if (!missingFields.length) {
      return "SMTP ist nicht vollständig konfiguriert.";
    }
    const labels = {
      smtpHost: "SMTP Host",
      smtpSenderEmail: "Absender E-Mail"
    };
    return `Fehlende Felder: ${missingFields.map((field) => labels[field] || field).join(", ")}`;
  }
  if (err?.code === "smtp_send_failed" || err?.code === "otp_send_failed") {
    const base = err?.payload?.detail || err?.message || "SMTP-Versand fehlgeschlagen.";
    const diag = formatSmtpDiagnosticsPayload(err?.payload?.diagnostics);
    const fallbackError = String(err?.payload?.fallbackError || "");
    const fallbackHint = fallbackError.startsWith("resend_not_configured")
      ? "API-Fallback ist nicht aktiv. Setze Brevo in den Einstellungen (empfohlen) oder RESEND_API_KEY in Railway."
      : "";
    const apiState = formatApiFallbackState(err?.payload || {});
    const resendEnvState = err?.payload?.resendConfigured ? formatResendEnvState(err?.payload) : "";
    const parts = [base];
    if (diag) parts.push(diag);
    if (fallbackHint && !base.includes(fallbackHint) && !diag.includes(fallbackHint)) parts.push(fallbackHint);
    const diagHasApiState = diag.includes("API-Fallback erkannt") || diag.includes("API-Fallback nicht erkannt");
    if (apiState && !diagHasApiState && !base.includes(apiState)) parts.push(apiState);
    if (resendEnvState) parts.push(resendEnvState);
    return parts.join(" | ");
  }
  return err?.message || "Unbekannter Fehler";
}

function formatSmtpDiagnosticsPayload(payload) {
  if (!payload) return "";
  if (payload.ok) {
    const apiState = formatApiFallbackState(payload);
    return `Diagnose OK: Host ${payload.host}:${payload.port}, TLS ${payload.useTls ? "an" : "aus"}, Auth ${payload.hasUsername ? "gesetzt" : "ohne Login"}${apiState ? `, ${apiState}` : ""}`;
  }
  const stage = payload.stage ? `Stufe ${payload.stage}` : "Diagnose fehlgeschlagen";
  const type = payload.errorType ? `${payload.errorType}: ` : "";
  const message = payload.error || "Unbekannter Fehler";
  const apiState = formatApiFallbackState(payload);
  const resendEnvState = payload?.resendConfigured ? formatResendEnvState(payload) : "";
  return `${stage} - ${type}${message}${apiState ? ` | ${apiState}` : ""}${resendEnvState ? ` | ${resendEnvState}` : ""}`;
}

async function runSmtpDiagnostics() {
  return apiRequest(API_BASE + "/api/settings/smtp-diagnose", {
    method: "POST",
    body: getCurrentSmtpSettingsFromForm()
  });
}

async function runResendDirectTest(recipient = "", provider = "") {
  const payload = recipient ? { recipient } : {};
  if (provider) {
    payload.provider = provider;
  }
  try {
    return await apiRequest(API_BASE + "/api/settings/resend-test", {
      method: "POST",
      body: payload
    });
  } catch (err) {
    return err?.payload || { ok: false, error: err?.code || "resend_test_failed" };
  }
}

async function saveAndTestBrevo() {
  const keyEl = document.querySelector("#brevoApiKey");
  const fromEl = document.querySelector("#brevoFromEmail");
  const resultEl = document.querySelector("#brevoTestResult");
  const hintEl = document.querySelector("#brevoKeyStoredHint");
  const key = keyEl?.value?.trim() || "";
  const fromEmail = fromEl?.value?.trim() || "";
  const hasStoredKey = Boolean(state?.settings?.brevoApiKey) || Boolean((hintEl?.textContent || "").includes("gespeichert"));
  if (!key && !hasStoredKey) {
    if (resultEl) { resultEl.textContent = "Bitte Brevo API-Key eingeben"; resultEl.style.color = "#dc2626"; }
    return;
  }

  if (key || fromEmail) {
    if (resultEl) { resultEl.textContent = "⏳ Speichern…"; resultEl.style.color = "#6b7280"; }
    try {
      await apiRequest(API_BASE + "/api/settings", {
        method: "PUT",
        body: { ...getCurrentSmtpSettingsFromForm(), brevoApiKey: key, brevoFromEmail: fromEmail }
      });
      if (state?.settings) {
        state.settings.brevoApiKey = state.settings.brevoApiKey || "stored";
        if (fromEmail) state.settings.brevoFromEmail = fromEmail;
      }
    } catch (e) {
      if (resultEl) { resultEl.textContent = `✗ Speichern fehlgeschlagen: ${e?.code || e}`; resultEl.style.color = "#dc2626"; }
      return;
    }
  }

  if (hintEl) { hintEl.textContent = "✓ API-Key gespeichert"; hintEl.style.color = "#16a34a"; }
  if (keyEl) keyEl.value = "";
  if (resultEl) { resultEl.textContent = "⏳ Teste…"; resultEl.style.color = "#6b7280"; }
  // Test via resend-test endpoint (uses API fallback: Resend/Brevo)
  let data = await runResendDirectTest("", "brevo");
  if (data?.error === "missing_recipient") {
    const addr = window.prompt("Brevo-Test: An welche E-Mail senden? (Keine Empfaenger-E-Mail gefunden)");
    if (!addr || !addr.includes("@")) {
      if (resultEl) { resultEl.textContent = "Abgebrochen"; resultEl.style.color = "#9ca3af"; }
      return;
    }
    data = await runResendDirectTest(addr, "brevo");
  }
  if (!resultEl) return;
  if (data?.ok) {
    resultEl.textContent = "✓ Brevo: Mail gesendet!";
    resultEl.style.color = "#16a34a";
  } else {
    const detail = data?.detail ? ` → ${data.detail}` : "";
    resultEl.textContent = `✗ ${data?.error || "Fehler"}${detail}`;
    resultEl.style.color = "#dc2626";
  }
}

async function sendOtpTestMail() {
  const btn = document.querySelector("#otpTestBtn");
  const result = document.querySelector("#otpTestResult");
  const email = window.prompt("OTP-Test: An welche E-Mail-Adresse soll der Code gesendet werden?");
  if (!email || !email.includes("@")) return;
  if (btn) btn.disabled = true;
  if (result) result.textContent = "⏳ …";
  try {
    const res = await apiRequest(API_BASE + "/api/settings/otp-test", {
      method: "POST",
      body: { ...getCurrentSmtpSettingsFromForm(), email }
    });
    if (result) {
      result.style.color = "#16a34a";
      result.textContent = `✅ OTP-Code gesendet an ${res.recipient} (Code: 123456)`;
    }
  } catch (err) {
    if (result) {
      result.style.color = "#dc2626";
      let message = formatSmtpTestError(err);
      const hasInlineDiag = Boolean(err?.payload?.diagnostics);
      if (!hasInlineDiag) {
        try {
          const diag = await runSmtpDiagnostics();
          const diagText = formatSmtpDiagnosticsPayload(diag);
          if (diagText) message += ` | ${diagText}`;
        } catch (diagErr) {
          const diagText = formatSmtpDiagnosticsPayload(diagErr?.payload);
          if (diagText) message += ` | ${diagText}`;
        }
      }
      result.textContent = `❌ Fehler: ${message}`;
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function sendSmtpTestMail() {
  const btn = document.querySelector("#smtpTestBtn");
  const result = document.querySelector("#smtpTestResult");
  if (btn) btn.disabled = true;
  if (result) result.textContent = "⏳ …";
  try {
    const res = await apiRequest(API_BASE + "/api/settings/smtp-test", {
      method: "POST",
      body: getCurrentSmtpSettingsFromForm()
    });
    if (result) {
      result.style.color = "#16a34a";
      if (res?.delivery && res.delivery !== "smtp") {
        result.textContent = `✅ Mail gesendet an ${res.recipient} (Fallback via HTTPS-API)`;
      } else {
        result.textContent = `✅ Mail gesendet an ${res.recipient}`;
      }
    }
  } catch (err) {
    if (result) {
      result.style.color = "#dc2626";
      let message = formatSmtpTestError(err);
      const hasInlineDiag = Boolean(err?.payload?.diagnostics);
      if (!hasInlineDiag) {
        try {
          const diag = await runSmtpDiagnostics();
          const diagText = formatSmtpDiagnosticsPayload(diag);
          if (diagText) message += ` | ${diagText}`;
        } catch (diagErr) {
          const diagText = formatSmtpDiagnosticsPayload(diagErr?.payload);
          if (diagText) message += ` | ${diagText}`;
        }
      }
      const isConnectFailure = String(err?.payload?.diagnostics?.stage || "") === "connect";
      if (isConnectFailure) {
        const fallbackRecipient = document.querySelector("#smtpSenderEmail")?.value.trim() || "";
        const apiCheck = await runResendDirectTest(fallbackRecipient);
        if (apiCheck?.ok) {
          message += " | API Direkt-Test: OK";
        } else if (apiCheck?.error) {
          const apiSource = apiCheck?.resendKeySource ? ` (${apiCheck.resendKeySource})` : "";
          message += ` | API Direkt-Test: ${apiCheck.error}${apiSource}`;
        }
      }
      result.textContent = `❌ Fehler: ${message}`;
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

function renderSystemStatusPanel(statusPayload) {
  const panel = document.querySelector("#systemStatusPanel");
  if (!panel) return;

  if (!statusPayload) {
    panel.innerHTML = "<p>Status konnte nicht geladen werden.</p>";
    return;
  }

  const activeSessions = Number(statusPayload.activeSessions || 0);
  const activeWorkerSessions = Number(statusPayload.activeWorkerSessions || 0);
  const openEntries = Number(statusPayload.openEntries || 0);
  const loginLocks = Array.isArray(statusPayload.loginLocks) ? statusPayload.loginLocks.length : 0;
  const recentIssues = Array.isArray(statusPayload.recentIssues) ? statusPayload.recentIssues.length : 0;
  const serverTime = formatTimestamp(statusPayload.serverTime || new Date().toISOString());

  panel.innerHTML = `
    <p><strong>Serverzeit:</strong> ${escapeHtml(serverTime)}</p>
    <p><strong>Aktive Admin-Sitzungen:</strong> ${activeSessions}</p>
    <p><strong>Aktive Mitarbeiter-App-Sitzungen:</strong> ${activeWorkerSessions}</p>
    <p><strong>Offene Eintritte:</strong> ${openEntries}</p>
    <p><strong>Login-Sperren:</strong> ${loginLocks}</p>
    <p><strong>Letzte Probleme:</strong> ${recentIssues}</p>
  `;
}

async function refreshSystemStatus() {
  const panel = document.querySelector("#systemStatusPanel");
  if (panel) {
    panel.innerHTML = "<p>Status wird geladen...</p>";
  }

  try {
    const status = await apiRequest(`${API_BASE}/api/system/status`, { method: "GET" });
    renderSystemStatusPanel(status);
  } catch (error) {
    if (panel) {
      panel.innerHTML = `<p>Status konnte nicht geladen werden: ${escapeHtml(error.message)}</p>`;
    }
  }
}

async function handleSystemRepair() {
  if (!window.confirm(uiT("confirmSystemRepair"))) {
    return;
  }

  try {
    await apiRequest(`${API_BASE}/api/system/repair`, { method: "POST", body: {} });
    await refreshSystemStatus();
    window.alert(uiT("alertSystemRepairDone"));
  } catch (error) {
    window.alert(uiT("alertSystemRepairFailed").replace("{error}", error.message));
  }
}

async function handleInvoiceLogoUpload(event) {
  const file = event.target.files?.[0];
  if (!file) {
    return;
  }

  if (!file.type.startsWith("image/")) {
    window.alert(runtimeText("logoImageFileRequired"));
    return;
  }

  const reader = new FileReader();
  reader.onload = () => {
    const dataUrl = typeof reader.result === "string" ? reader.result : "";
    elements.invoiceLogoData.value = dataUrl;
    elements.invoiceLogoPreview.src = dataUrl;
    elements.invoiceLogoPreview.classList.toggle("hidden", !dataUrl);
    applyWebsiteLogo(dataUrl);
  };
  reader.readAsDataURL(file);
}

async function loadCustomBrandingPreset() {
  try {
    const response = await fetch(API_BASE + "/branding/baukometra-logo.svg");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const svg = await response.text();
    const logoDataUrl = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;

    document.querySelector("#platformName").value = "BauKometra Control";
    document.querySelector("#operatorName").value = "BauKometra";
    document.querySelector("#invoicePrimaryColor").value = "#0f4c5c";
    document.querySelector("#invoiceAccentColor").value = "#e36414";

    elements.invoiceLogoData.value = logoDataUrl;
    elements.invoiceLogoPreview.src = logoDataUrl;
    elements.invoiceLogoPreview.classList.remove("hidden");
    applyWebsiteLogo(logoDataUrl);

    window.alert(uiT("alertBrandingLoaded"));
  } catch (error) {
    window.alert(uiT("alertBrandingLoadFailed").replace("{error}", error.message));
  }
}

async function loadCustomBrandingPresetAlt() {
  try {
    const response = await fetch(API_BASE + "/branding/baukometra-alt-logo.svg");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const svg = await response.text();
    const logoDataUrl = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;

    document.querySelector("#platformName").value = "BauKometra Control";
    document.querySelector("#operatorName").value = "BauKometra";
    document.querySelector("#invoicePrimaryColor").value = "#24324a";
    document.querySelector("#invoiceAccentColor").value = "#c65a2e";

    elements.invoiceLogoData.value = logoDataUrl;
    elements.invoiceLogoPreview.src = logoDataUrl;
    elements.invoiceLogoPreview.classList.remove("hidden");
    applyWebsiteLogo(logoDataUrl);

    window.alert(uiT("alertBrandingAltLoaded"));
  } catch (error) {
    window.alert(uiT("alertBrandingAltLoadFailed").replace("{error}", error.message));
  }
}

async function handleInvoicePrint(event) {
  event.preventDefault();
  const invoice = buildInvoiceDraft({ silent: false });
  if (!invoice) {
    return;
  }
  const html = renderInvoiceHtml(invoice);

  const invoiceWindow = window.open("", "_blank", "width=980,height=860");
  if (!invoiceWindow) {
    window.alert(runtimeText("popupBlockedAllow"));
    return;
  }
  invoiceWindow.document.open();
  invoiceWindow.document.write(html);
  invoiceWindow.document.close();
  invoiceWindow.focus();
  invoiceWindow.print();
}

async function handleInvoiceSend() {
  const invoice = buildInvoiceDraft({ silent: false });
  if (!invoice) {
    return;
  }

  const sendBtn = document.querySelector("#invoiceSendButton");
  if (sendBtn) {
    if (sendBtn.disabled) return;  // prevent double-click
    sendBtn.disabled = true;
  }

  const html = renderInvoiceHtml(invoice);
  try {
    const payload = await apiRequest(API_BASE + "/api/invoices/send", {
      method: "POST",
      body: {
        companyId: invoice.company.id,
        recipientEmail: invoice.recipientEmail,
        invoiceNumber: invoice.invoiceNumber,
        invoiceDate: invoice.invoiceDate,
        dueDate: invoice.dueDate,
        invoicePeriod: invoice.invoicePeriod,
        description: invoice.invoiceDescription,
        netAmount: invoice.netAmount,
        vatRate: invoice.vatRate,
        discountAmount: invoice.discountAmount || 0,
        items: invoice.items || [],
        renderedHtml: html
      }
    });

    await loadAllData();
    refreshAll();
    if (payload.sent) {
      window.alert(runtimeText("invoiceSentEmail"));
    } else {
      const errorText = String(payload.error || "");
      if (errorText.toLowerCase().includes("smtp ist nicht konfiguriert")) {
        window.alert(runtimeText("invoiceSavedEmailNotConfigured"));
      } else {
        window.alert(uiT("alertInvoiceSavedSendFailed").replace("{error}", payload.error));
      }
    }
  } catch (error) {
    if (String(error.message || "") === "duplicate_invoice_number") {
      window.alert(uiT("alertInvoiceNumberDuplicate").replace("{number}", invoice.invoiceNumber));
      return;
    }
    window.alert(uiT("alertInvoiceSendFailed").replace("{error}", error.message));
  } finally {
    if (sendBtn) sendBtn.disabled = false;
  }
}

function buildInvoiceDraft(options = {}) {
  const { silent = false } = options;
  const companyId = document.querySelector("#invoiceCompanySelect").value;
  const company = state.companies.find((entry) => entry.id === companyId);
  if (!company) {
    if (!silent) {
      window.alert(runtimeText("invoiceSelectCompany"));
    }
    return null;
  }

  const recipientEmail = elements.invoiceRecipientEmail.value.trim();
  const isValidRecipientEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(recipientEmail);
  if (!isValidRecipientEmail) {
    if (!silent) {
      window.alert(runtimeText("invoiceRecipientInvalid"));
    }
    return null;
  }

  const invoiceDate = document.querySelector("#invoiceDate").value;
  const invoiceDueDate = document.querySelector("#invoiceDueDate")?.value || "";
  const invoicePeriod = document.querySelector("#invoicePeriod").value.trim();
  const invoiceDescription = document.querySelector("#invoiceDescription").value.trim();
  const requestedNetAmount = Number(document.querySelector("#invoiceNetAmount").value || "0");
  const invoiceNumberRaw = document.querySelector("#invoiceNumber").value.trim();
  const invoiceNumber = invoiceNumberRaw || `RE-${new Date().getFullYear()}-${String(Date.now()).slice(-5)}`;

  if (invoiceNumber.length < 3 || invoiceNumber.length > 64) {
    if (!silent) {
      window.alert(uiT("alertInvoiceNumberLength"));
    }
    return null;
  }

  const duplicateInvoice = (state.invoices || []).some((entry) => {
    const sameCompany = String(entry.company_id || entry.companyId || "") === String(company.id || "");
    const sameNumber = String(entry.invoice_number || entry.invoiceNumber || "").trim().toLowerCase() === invoiceNumber.trim().toLowerCase();
    return sameCompany && sameNumber;
  });
  if (duplicateInvoice) {
    if (!silent) {
      window.alert(uiT("alertInvoiceNumberDuplicate").replace("{number}", invoiceNumber));
    }
    return null;
  }

  if (!invoiceDate || !invoiceDueDate || !invoicePeriod || !invoiceDescription) {
    if (!silent) {
      window.alert(runtimeText("invoiceFormRequiredFields"));
    }
    return null;
  }

  const invoiceDateObj = new Date(`${invoiceDate}T00:00:00`);
  const dueDateObj = new Date(`${invoiceDueDate}T00:00:00`);
  if (Number.isNaN(invoiceDateObj.getTime()) || Number.isNaN(dueDateObj.getTime())) {
    if (!silent) {
      window.alert(uiT("alertInvoiceDateInvalid"));
    }
    return null;
  }

  if (dueDateObj < invoiceDateObj) {
    if (!silent) {
      window.alert(uiT("alertInvoiceDueDateBeforeIssue"));
    }
    return null;
  }

  // Extrahiere Datumsbereich aus invoicePeriod (z. B. "01.04.2026 - 30.04.2026")
  const accessLineItems = extractAccessLineItems(company.id, invoicePeriod);

  // Multi-position items
  const positionItems = getInvoicePositions ? getInvoicePositions() : [];
  const positionsNetAmount = positionItems.reduce((sum, item) => sum + (item.total || 0), 0);

  const lineItemsNet = accessLineItems.reduce((sum, item) => sum + Number(item.amount || 0), 0);
  const fallbackNetAmount = getPlanNetPrice(company.plan);
  const netAmount = positionsNetAmount > 0
    ? Math.round(positionsNetAmount * 100) / 100
    : requestedNetAmount > 0
    ? requestedNetAmount
    : (lineItemsNet > 0 ? Math.round(lineItemsNet * 100) / 100 : fallbackNetAmount);

  // Discount / Skonto
  const discountToggle = document.querySelector("#invoiceDiscountToggle");
  const discountAmount = (discountToggle?.checked)
    ? Math.round((parseFloat(document.querySelector("#invoiceDiscountAmount")?.value || "0") || 0) * 100) / 100
    : 0;
  const netAfterDiscount = Math.max(0, Math.round((netAmount - discountAmount) * 100) / 100);

  const vatRate = Number(document.querySelector("#invoiceVatRate").value || "0");
  if (!Number.isFinite(vatRate) || vatRate < 0 || vatRate > 100) {
    if (!silent) {
      window.alert(uiT("alertInvoiceVatRange"));
    }
    return null;
  }
  const vatAmount = Math.round(netAfterDiscount * (vatRate / 100) * 100) / 100;
  const totalAmount = Math.round((netAfterDiscount + vatAmount) * 100) / 100;

  return {
    company,
    recipientEmail,
    invoiceNumber,
    invoiceDate,
    dueDate: invoiceDueDate,
    invoicePeriod,
    invoiceDescription,
    planLabel: getPlanLabel(company.plan),
    netAmount,
    vatRate,
    vatAmount,
    totalAmount,
    discountAmount,
    items: positionItems.length > 0 ? positionItems : undefined,
    accessLineItems,
    primaryColor: normalizeHexColor(state.settings.invoicePrimaryColor, "#0f4c5c"),
    accentColor: normalizeHexColor(state.settings.invoiceAccentColor, "#e36414"),
    logo: sanitizeInvoiceLogoSrc(state.settings.invoiceLogoData)
      || sanitizeInvoiceLogoSrc(elements.invoiceLogoData.value)
      || DEFAULT_BRAND_LOGO
  };
}

function parseInvoicePeriodRange(invoicePeriod) {
  const normalized = String(invoicePeriod || "").trim();
  const parts = normalized.split(/\s+-\s+|\s+bis\s+|\s+to\s+/i).map((part) => part.trim()).filter(Boolean);
  if (parts.length < 2) {
    return null;
  }

  const parseDate = (input) => {
    const value = String(input || "").trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
      const date = new Date(`${value}T00:00:00`);
      return Number.isNaN(date.getTime()) ? null : date;
    }
    if (/^\d{2}\.\d{2}\.\d{4}$/.test(value)) {
      const [day, month, year] = value.split(".").map(Number);
      const date = new Date(year, month - 1, day, 0, 0, 0);
      return Number.isNaN(date.getTime()) ? null : date;
    }
    return null;
  };

  const from = parseDate(parts[0]);
  const to = parseDate(parts[1]);
  if (!from || !to) {
    return null;
  }
  to.setHours(23, 59, 59, 999);
  return { from, to };
}

function extractAccessLineItems(companyId, invoicePeriod) {
  const range = parseInvoicePeriodRange(invoicePeriod);
  if (!range) {
    return [];
  }
  const { from, to } = range;
  
  // Filter access logs for this company and period
  const companyWorkerIds = state.workers
    .filter(w => w.companyId === companyId)
    .map(w => w.id);
  
  const relevantLogs = state.accessLogs.filter(log => {
    if (!companyWorkerIds.includes(log.workerId)) return false;
    const logTime = new Date(log.timestamp);
    return logTime >= from && logTime <= to;
  });
  
  // Group by worker
  const workerCounts = {};
  relevantLogs.forEach(log => {
    if (!workerCounts[log.workerId]) {
      workerCounts[log.workerId] = 0;
    }
    workerCounts[log.workerId]++;
  });
  
  // Build line items
  return Object.keys(workerCounts)
    .map(workerId => {
      const worker = state.workers.find(w => w.id === workerId);
      const accessCount = workerCounts[workerId];
      // Berechne Betrag: vereinfacht als (count * tariff_per_access)
      const pricePerAccess = 2.0; // Beispiel: 2 EUR pro Zugang
      const amount = accessCount * pricePerAccess;
      return {
        workerId,
        workerName: worker ? `${worker.firstName} ${worker.lastName}` : "Unbekannt",
        accessCount,
        amount: Math.round(amount * 100) / 100
      };
    })
    .sort((a, b) => a.workerName.localeCompare(b.workerName));
}

function renderInvoiceHtml(invoice) {
  return `
    <!DOCTYPE html>
    <html lang="de" translate="no">
    <head>
      <meta charset="UTF-8" />
      <meta name="google" content="notranslate" />
      <meta http-equiv="Content-Language" content="de" />
      <title>${escapeHtml(uiT("invoiceTitle"))} ${escapeHtml(invoice.invoiceNumber)}</title>
      <style>
        body { margin: 0; font-family: Arial, sans-serif; color: #1b1b1b; }
        .sheet { padding: 28px; }
        .head { display: flex; justify-content: space-between; align-items: flex-start; gap: 18px; margin-bottom: 18px; }
        .brand h1 { margin: 0; color: ${invoice.primaryColor}; }
        .brand p { margin: 6px 0 0; color: #555; }
        .logo { max-width: 180px; max-height: 84px; object-fit: contain; }
        .bar { height: 5px; background: linear-gradient(90deg, ${invoice.primaryColor}, ${invoice.accentColor}); border-radius: 4px; margin: 12px 0 20px; }
        .meta, .totals { width: 100%; border-collapse: collapse; }
        .meta td { padding: 6px 4px; vertical-align: top; }
        .service { margin: 14px 0 16px; border: 1px solid #ddd; border-radius: 10px; overflow: hidden; }
        .service table { width: 100%; border-collapse: collapse; }
        .service th { text-align: left; background: #f8f8f8; padding: 10px; }
        .service td { padding: 10px; border-top: 1px solid #eee; }
        .totals td { padding: 6px 4px; }
        .totals tr:last-child td { font-size: 1.1rem; font-weight: 700; color: ${invoice.primaryColor}; }
        .footer { margin-top: 22px; font-size: 0.9rem; color: #666; }
      </style>
    </head>
    <body>
      <div class="sheet">
        <div class="head">
          <div class="brand">
            <h1>${escapeHtml(uiT("invoiceTitle"))}</h1>
            <p>${escapeHtml(state.settings.operatorName)}</p>
            <p>${escapeHtml(state.settings.platformName)}</p>
          </div>
          ${invoice.logo ? `<img class="logo" src="${invoice.logo}" alt="${escapeHtml(uiT('invoiceAltLogo'))}" />` : ""}
        </div>

        <div class="bar"></div>

        <table class="meta">
          <tr>
            <td><strong>${escapeHtml(uiT("invoiceLabelNumber"))}</strong> ${escapeHtml(invoice.invoiceNumber)}</td>
            <td><strong>${escapeHtml(uiT("invoiceLabelDate"))}</strong> ${escapeHtml(formatDate(invoice.invoiceDate))}</td>
          </tr>
          <tr>
            <td><strong>${escapeHtml(uiT("invoiceLabelDue"))}</strong> ${escapeHtml(formatDate(invoice.dueDate))}</td>
            <td></td>
          </tr>
          <tr>
            <td><strong>${escapeHtml(uiT("invoiceLabelCustomer"))}</strong> ${escapeHtml(invoice.company.name)}</td>
            <td><strong>${escapeHtml(uiT("invoiceLabelContact"))}</strong> ${escapeHtml(invoice.company.contact || "-")}</td>
          </tr>
          <tr>
            <td colspan="2"><strong>${escapeHtml(uiT("invoiceLabelPeriod"))}</strong> ${escapeHtml(invoice.invoicePeriod)}</td>
          </tr>
        </table>

        <div class="service">
          <table>
            <thead>
              <tr>
                <th>${escapeHtml(uiT("invoiceColService"))}</th>
                <th style="text-align:center">${escapeHtml(uiT("invoiceColAccess"))}</th>
                <th style="text-align:right">${escapeHtml(uiT("invoiceColNet"))}</th>
              </tr>
            </thead>
            <tbody>
              ${invoice.accessLineItems && invoice.accessLineItems.length > 0 ? 
                invoice.accessLineItems.map(item => `
                  <tr>
                    <td>${escapeHtml(item.workerName || uiT('invoiceRowUnknown'))}</td>
                    <td style="text-align:center">${item.accessCount}</td>
                    <td style="text-align:right">${formatCurrency(item.amount)}</td>
                  </tr>
                `).join('') :
                `
                  <tr>
                    <td>${escapeHtml(uiT("invoiceRowPlan").replace("{label}", invoice.planLabel))}</td>
                    <td style="text-align:center">-</td>
                    <td style="text-align:right">${formatCurrency(invoice.netAmount)}</td>
                  </tr>
                  <tr>
                    <td>${escapeHtml(invoice.invoiceDescription)}</td>
                    <td style="text-align:center">-</td>
                    <td style="text-align:right">${formatCurrency(invoice.netAmount)}</td>
                  </tr>
                `
              }
            </tbody>
          </table>
        </div>

        <table class="totals">
          <tr><td>${escapeHtml(uiT("invoiceTotalNet"))}</td><td>${formatCurrency(invoice.netAmount)}</td></tr>
          <tr><td>${escapeHtml(uiT("invoiceTotalVat").replace("{rate}", invoice.vatRate.toFixed(1)))}</td><td>${formatCurrency(invoice.vatAmount)}</td></tr>
          <tr><td>${escapeHtml(uiT("invoiceTotalGross"))}</td><td>${formatCurrency(invoice.totalAmount)}</td></tr>
        </table>

        <p class="footer">${escapeHtml(uiT("invoiceFooter"))}</p>
      </div>
    </body>
    </html>
  `;
}

function refreshInvoicePreview(options = {}) {
  const { silent = true } = options;
  if (!elements.invoicePreviewFrame) {
    return;
  }

  const invoice = buildInvoiceDraft({ silent });
  if (!invoice) {
    elements.invoicePreviewFrame.srcdoc = "";
    return;
  }
  elements.invoicePreviewFrame.srcdoc = renderInvoiceHtml(invoice);
}

function renderInvoiceHistory() {
  if (!state.invoices.length) {
    elements.invoiceHistoryList.innerHTML = `<div class="empty-state">${escapeHtml(uiT("invoiceHistoryEmpty"))}</div>`;
    return;
  }

  elements.invoiceHistoryList.innerHTML = state.invoices
    .slice(0, 20)
    .map(
      (invoice) => `
        <article class="list-item">
          <header>
            <div>
              <strong>${escapeHtml(invoice.invoice_number)}</strong>
              <span>${escapeHtml(invoice.company_name || "Firma")}</span>
            </div>
            <span class="status-pill status-${escapeHtml(invoice.status || "test")}">${escapeHtml(invoice.status || "-")}</span>
          </header>
          <span>${escapeHtml(uiT("invoiceHistoryRecipient"))} ${escapeHtml(invoice.recipient_email)}</span>
          <span>${escapeHtml(uiT("invoiceHistoryTotal"))} ${formatCurrency(invoice.total_amount)}</span>
          <span>${escapeHtml(uiT("invoiceHistoryCreated"))} ${formatTimestamp(invoice.created_at)}</span>
          ${invoice.sent_at ? `<span>${escapeHtml(uiT("invoiceHistorySent"))} ${formatTimestamp(invoice.sent_at)}</span>` : ""}
          ${invoice.error_message ? `<span>${escapeHtml(uiT("invoiceHistoryError"))} ${escapeHtml(invoice.error_message)}</span>` : ""}
        </article>
      `
    )
    .join("");
}

function formatCurrency(value) {
  return new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "EUR"
  }).format(Number(value) || 0);
}

function normalizeHexColor(value, fallback) {
  const candidate = String(value || "").trim();
  if (/^#[0-9a-fA-F]{6}$/.test(candidate)) {
    return candidate;
  }
  return fallback;
}

function sanitizeInvoiceLogoSrc(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return "";
  }
  if (raw.startsWith("data:image/")) {
    return raw;
  }

  try {
    const parsed = new URL(raw, window.location.origin);
    if (parsed.protocol === "https:" || parsed.protocol === "blob:") {
      return parsed.toString();
    }
  } catch {
    return "";
  }

  return "";
}

async function handleCompanySubmit(event) {
  event.preventDefault();
  if (!userCanManageSystem()) {
    return;
  }

  const companyTurnstileEndpointInput = document.querySelector("#companyTurnstileEndpoint");
  const companyTurnstileEndpoint = (companyTurnstileEndpointInput?.value || "").trim();

  try {
    const response = await apiRequest(API_BASE + "/api/companies", {
      method: "POST",
      body: {
        turnstileEndpoint: companyTurnstileEndpoint || undefined,
        name: document.querySelector("#companyName").value.trim(),
        contact: document.querySelector("#companyContact").value.trim(),
        billingEmail: document.querySelector("#companyBillingEmail").value.trim(),
        documentEmail: document.querySelector("#companyDocumentEmail").value.trim(),
        accessHost: document.querySelector("#companyAccessHost").value.trim().toLowerCase(),
        brandingPreset: (document.querySelector("#companyBrandingPreset")?.value || "construction").trim(),
        plan: document.querySelector("#companyPlan").value,
        status: document.querySelector("#companyStatus").value,
        adminPassword: document.querySelector("#companyAdminPassword").value.trim() || undefined,
        turnstilePassword: (document.querySelector("#companyTurnstilePassword")?.value || "").trim() || undefined,
        turnstileCount: Number(document.querySelector("#companyTurnstileCount")?.value || 1),
      }
    });

    elements.companyForm.reset();
    const brandingPresetInput = document.querySelector("#companyBrandingPreset");
    if (brandingPresetInput) {
      brandingPresetInput.value = "construction";
    }
    document.querySelector("#companyPlan").value = "tageskarte";
    document.querySelector("#companyStatus").value = "aktiv";
    const turnstileCountInput = document.querySelector("#companyTurnstileCount");
    if (turnstileCountInput) {
      turnstileCountInput.value = "1";
    }
    if (companyTurnstileEndpointInput) {
      companyTurnstileEndpointInput.value = companyTurnstileEndpoint || state.settings.turnstileEndpoint || "";
    }

    await loadAllData();
    refreshAll();

    if (response.adminCredentials) {
      const accessLines = [
        `Admin-Zugang: ${response.adminCredentials.username} / ${response.adminCredentials.password}`,
      ];

      const turnstileCredentials = Array.isArray(response.turnstileCredentialsList)
        ? response.turnstileCredentialsList
        : response.turnstileCredentials?.username
          ? [response.turnstileCredentials]
          : [];

      turnstileCredentials.forEach((credential, index) => {
        accessLines.push(`Drehkreuz-Zugang ${index + 1}: ${credential.username} / ${credential.password}`);
        if (credential.apiKey) {
          accessLines.push(`Drehkreuz-API-Key ${index + 1}: ${credential.apiKey}`);
        }
      });

      if (!turnstileCredentials.length && response.turnstileCredentials?.username) {
        accessLines.push(`Drehkreuz-Zugang: ${response.turnstileCredentials.username} / ${response.turnstileCredentials.password}`);
        if (response.turnstileCredentials.apiKey) {
          accessLines.push(`Drehkreuz-API-Key: ${response.turnstileCredentials.apiKey}`);
        }
      }

      showSecretDialog(
        "Firma angelegt",
        accessLines,
        {
          intro: "Zugangsdaten und API-Keys werden nur jetzt vollstaendig angezeigt.",
          copyLabel: "Zugangsdaten kopieren",
          copyValue: accessLines.join("\n"),
        }
      );
    }
  } catch (error) {
    window.alert(uiT("alertCompanyCreateFailed").replace("{error}", error.message));
  }
}

async function loadAndRenderInvoices(options = {}) {
  const { silent = false } = options;
  try {
    const hadSeenInvoices = Object.keys(state.invoiceSeenIds || {}).length > 0;
    const previousSeen = { ...(state.invoiceSeenIds || {}) };
    const [invoiceResponse, opsResponse, deadLetterResponse, approvalResponse] = await Promise.all([
      apiRequest(API_BASE + "/api/invoices"),
      apiRequest(API_BASE + "/api/invoices/ops-metrics"),
      apiRequest(API_BASE + "/api/invoices/dead-letters"),
      apiRequest(API_BASE + "/api/invoices/approvals/pending"),
    ]);
    state.invoices = invoiceResponse || [];
    state.invoiceOpsMetrics = opsResponse || {
      avgFirstSuccessMinutes: 0,
      criticalOver24h: 0,
      retryVolume7d: [],
      topErrorReasons: [],
    };
    state.invoiceDeadLetters = Array.isArray(deadLetterResponse) ? deadLetterResponse : [];
    state.invoiceApprovalRequests = Array.isArray(approvalResponse) ? approvalResponse : [];

    const nextSeen = { ...previousSeen };
    const nextNew = {};
    state.invoices.forEach((invoice) => {
      if (!invoice?.id) {
        return;
      }
      if (hadSeenInvoices && !previousSeen[invoice.id]) {
        nextNew[invoice.id] = true;
      }
      nextSeen[invoice.id] = true;
    });
    state.invoiceSeenIds = nextSeen;
    state.invoiceNewIds = nextNew;

    const validIds = new Set(state.invoices.map((invoice) => String(invoice?.id || "")).filter(Boolean));
    state.invoiceRetrySelectedIds = (state.invoiceRetrySelectedIds || []).filter((id) => validIds.has(id));
    Object.keys(state.invoiceHistoryExpandedById || {}).forEach((id) => {
      if (!validIds.has(id)) {
        delete state.invoiceHistoryExpandedById[id];
      }
    });

    renderInvoiceManagementList();
  } catch (error) {
    if (!silent) {
      console.error("Failed to load invoices:", error);
    }
    state.invoices = [];
    state.invoiceOpsMetrics = {
      avgFirstSuccessMinutes: 0,
      criticalOver24h: 0,
      retryVolume7d: [],
      topErrorReasons: [],
    };
    state.invoiceDeadLetters = [];
    state.invoiceApprovalRequests = [];
    renderInvoiceManagementList();
  }
}

function renderInvoiceApprovalQueue() {
  const container = document.querySelector("#invoiceApprovalList");
  if (!container) {
    return;
  }

  const filterAction = String(document.querySelector("#invoiceApprovalFilterAction")?.value || "all").trim();
  const maxAgeMinutesValue = Number(document.querySelector("#invoiceApprovalMaxAgeMinutes")?.value || 0);
  const maxAgeMinutes = Number.isFinite(maxAgeMinutesValue) ? Math.max(0, Math.floor(maxAgeMinutesValue)) : 0;
  const nowMs = Date.now();

  const rows = (Array.isArray(state.invoiceApprovalRequests) ? state.invoiceApprovalRequests : []).filter((item) => {
    if (filterAction !== "all" && String(item?.action_type || "") !== filterAction) {
      return false;
    }
    if (maxAgeMinutes <= 0) {
      return true;
    }
    const requestedMs = Date.parse(String(item?.requested_at || ""));
    if (!Number.isFinite(requestedMs)) {
      return true;
    }
    return ((nowMs - requestedMs) / 60000) <= maxAgeMinutes;
  });

  if (!rows.length) {
    container.innerHTML = '<div class="empty-state">Keine offenen Freigaben.</div>';
    container.onclick = null;
    return;
  }

  const actionLabels = {
    "invoice.retry_send_bulk": "Bulk-Retry Rechnungsversand",
    "invoice.dead_letter_resolve": "Dead-Letter auflösen",
  };

  container.innerHTML = rows.map((item) => {
    const payload = item?.payload || {};
    const invoiceCount = Array.isArray(payload.invoiceIds) ? payload.invoiceIds.length : 0;
    const expiresAt = String(item?.expires_at || "").trim();
    const expiresMs = Date.parse(expiresAt);
    const minutesLeft = Number.isFinite(expiresMs) ? Math.max(0, Math.ceil((expiresMs - nowMs) / 60000)) : null;
    const urgencyClass = minutesLeft !== null && minutesLeft <= 1
      ? " invoice-approval-item-alert"
      : (minutesLeft !== null && minutesLeft <= 5 ? " invoice-approval-item-warn" : "");
    const urgencyChipClass = minutesLeft !== null && minutesLeft <= 1
      ? "invoice-priority-kritisch"
      : (minutesLeft !== null && minutesLeft <= 5 ? "invoice-priority-hoch" : "invoice-priority-niedrig");
    const urgencyChipText = minutesLeft === null
      ? "offen"
      : (minutesLeft <= 1 ? "kritisch" : (minutesLeft <= 5 ? "dringend" : "offen"));
    const expiryLabel = minutesLeft === null
      ? "Ablauf: -"
      : (minutesLeft <= 0 ? "Ablauf: abgelaufen" : `Ablauf in: ${minutesLeft} min`);
    const payloadHint = invoiceCount
      ? `${invoiceCount} Rechnung(en)`
      : (payload.invoiceId ? `Rechnung ${escapeHtml(payload.invoiceId)}` : "-");
    return `
      <article class="card-item invoice-approval-item${urgencyClass}">
        <div class="retry-queue-head">
          <div>
            <strong>${escapeHtml(actionLabels[item.action_type] || item.action_type || "Freigabe")}</strong>
            <p class="helper-text">Anfrage: ${escapeHtml(item.id || "-")}</p>
          </div>
          <span class="invoice-priority-chip ${urgencyChipClass}">${urgencyChipText}</span>
        </div>
        <p class="helper-text">Angefordert von: ${escapeHtml(item.requested_by_name || item.requested_by_username || "Unbekannt")}</p>
        <p class="helper-text">Zeitpunkt: ${formatTimestamp(item.requested_at || "")}</p>
        <p class="helper-text">${expiryLabel}</p>
        <p class="helper-text">Umfang: ${payloadHint}</p>
        <div class="button-row invoice-management-actions">
          <button type="button" class="ghost-button" data-approval-decision="approve" data-approval-id="${escapeHtml(item.id || "")}">Freigeben</button>
          <button type="button" class="ghost-button" data-approval-decision="reject" data-approval-id="${escapeHtml(item.id || "")}">Ablehnen</button>
        </div>
      </article>
    `;
  }).join("");

  container.onclick = async (event) => {
    const decisionButton = event.target.closest("[data-approval-id][data-approval-decision]");
    if (!decisionButton || !container.contains(decisionButton)) {
      return;
    }

    const approvalId = String(decisionButton.dataset.approvalId || "").trim();
    const decision = String(decisionButton.dataset.approvalDecision || "").trim();
    if (!approvalId || !decision) {
      return;
    }

    const decisionText = decision === "approve" ? "freigeben" : "ablehnen";
    if (!window.confirm(uiT("confirmApprovalDecision").replace("{id}", approvalId).replace("{decision}", decisionText))) {
      return;
    }

    let note = "";
    if (decision === "reject") {
      note = String(window.prompt(uiT("promptRejectionReason"), "") || "").trim();
      if (!note) {
        window.alert(uiT("alertApprovalRejectReasonRequired"));
        return;
      }
    }

    try {
      const payload = await apiRequest(`${API_BASE}/api/invoices/approvals/${approvalId}/decision`, {
        method: "POST",
        body: { decision, note },
      });
      if (payload?.status === "approved") {
        window.alert(uiT("alertApprovalConfirmed"));
      } else if (payload?.status === "rejected") {
        window.alert(uiT("alertApprovalRejected"));
      } else {
        window.alert(uiT("alertApprovalUpdated"));
      }
      state.invoiceRetrySelectedIds = [];
      await loadAndRenderInvoices();
      await loadAllData();
      refreshAll();
    } catch (error) {
      window.alert(uiT("alertApprovalActionFailed").replace("{error}", error.message));
    }
  };
}

function renderInvoiceDeadLetters() {
  const container = document.querySelector("#invoiceDeadLetterList");
  if (!container) {
    return;
  }

  const rows = Array.isArray(state.invoiceDeadLetters) ? state.invoiceDeadLetters : [];
  if (!rows.length) {
    container.innerHTML = '<div class="empty-state">Keine offenen Dead-Letter-Fälle.</div>';
    container.onclick = null;
    return;
  }

  container.innerHTML = rows.map((item) => `
    <article class="card-item invoice-dead-letter-item">
      <div class="retry-queue-head">
        <div>
          <strong>${escapeHtml(item.invoice_number || "RE-???")}</strong>
          <p class="helper-text">${escapeHtml(item.company_name || "Firma")}</p>
        </div>
        <span class="invoice-priority-chip invoice-priority-hoch">${escapeHtml(item.reason || "manual_review")}</span>
      </div>
      <p class="helper-text">Betrag: ${formatCurrency(item.total_amount)} • Versuche: ${Number(item.send_attempt_count || 0)}</p>
      <p class="helper-text">Erstellt: ${formatTimestamp(item.created_at || "")} ${item.last_send_attempt_at ? `• Letzter Versuch: ${formatTimestamp(item.last_send_attempt_at)}` : ""}</p>
      <p class="helper-text invoice-management-error">${item.last_error ? `Letzter Fehler: ${escapeHtml(item.last_error)}` : "Letzter Fehler nicht vorhanden."}</p>
      <div class="button-row invoice-management-actions">
        <button type="button" class="ghost-button" data-dead-letter-retry-id="${escapeHtml(item.invoice_id || "")}">Jetzt erneut senden</button>
        <button type="button" class="ghost-button" data-dead-letter-resolve-id="${escapeHtml(item.invoice_id || "")}">Als erledigt markieren</button>
      </div>
    </article>
  `).join("");

  container.onclick = async (event) => {
    const retryButton = event.target.closest("[data-dead-letter-retry-id]");
    if (retryButton && container.contains(retryButton)) {
      const invoiceId = String(retryButton.dataset.deadLetterRetryId || "").trim();
      if (!invoiceId || !window.confirm(uiT("confirmDeadLetterRetry"))) {
        return;
      }
      try {
        const payload = await apiRequest(`${API_BASE}/api/invoices/${invoiceId}/retry-send`, {
          method: "POST",
          body: {}
        });
        if (payload?.sent) {
          window.alert(uiT("alertInvoiceRetrySentDeadLetter"));
        } else {
          window.alert(uiT("alertInvoiceRetryFailed").replace("{error}", payload?.error || "Unbekannter Fehler"));
        }
        await loadAndRenderInvoices();
        await loadAllData();
        refreshAll();
      } catch (error) {
        window.alert(uiT("alertInvoiceRetryFailed").replace("{error}", error.message));
      }
      return;
    }

    const resolveButton = event.target.closest("[data-dead-letter-resolve-id]");
    if (resolveButton && container.contains(resolveButton)) {
      const invoiceId = String(resolveButton.dataset.deadLetterResolveId || "").trim();
      if (!invoiceId || !window.confirm(uiT("confirmDeadLetterResolve"))) {
        return;
      }
      try {
        const payload = await apiRequest(`${API_BASE}/api/invoices/${invoiceId}/dead-letter/resolve`, {
          method: "PUT",
          body: {}
        });
        if (payload?.approvalRequested) {
          window.alert(uiT("alertDeadLetterResolveApprovalRequested").replace("{id}", payload.approvalId));
        }
        await loadAndRenderInvoices();
        refreshAll();
      } catch (error) {
        window.alert(uiT("alertDeadLetterResolveFailed").replace("{error}", error.message));
      }
    }
  };
}

function renderInvoiceOpsMetrics() {
  const kpiContainer = document.querySelector("#invoiceOpsKpiGrid");
  const trendContainer = document.querySelector("#invoiceOpsTrendList");
  if (!kpiContainer || !trendContainer) {
    return;
  }

  const metrics = state.invoiceOpsMetrics || {};
  const avgMinutes = Number(metrics.avgFirstSuccessMinutes || 0);
  const criticalOver24h = Number(metrics.criticalOver24h || 0);
  const trend = Array.isArray(metrics.retryVolume7d) ? metrics.retryVolume7d : [];
  const topErrors = Array.isArray(metrics.topErrorReasons) ? metrics.topErrorReasons : [];

  kpiContainer.innerHTML = `
    <article class="summary-block invoice-kpi-card invoice-kpi-open">
      <p class="eyebrow">Zeit bis erster Erfolg</p>
      <strong>${avgMinutes ? `${avgMinutes} min` : "-"}</strong>
      <p class="meta-text">Durchschnitt über erfolgreiche Sendungen</p>
    </article>
    <article class="summary-block invoice-kpi-card invoice-kpi-overdue">
      <p class="eyebrow">Kritische Fälle >24h</p>
      <strong>${criticalOver24h}</strong>
      <p class="meta-text">Score >= 70 und älter als 24h</p>
    </article>
    <article class="summary-block invoice-kpi-card invoice-kpi-failed">
      <p class="eyebrow">Top Fehlergrund</p>
      <strong>${escapeHtml(topErrors[0]?.label || "-")}</strong>
      <p class="meta-text">${topErrors[0]?.count || 0} Vorkommen</p>
    </article>
  `;

  const trendBars = trend.map((entry) => {
    const count = Number(entry?.count || 0);
    const day = String(entry?.day || "").slice(5);
    return `
      <article class="card-item invoice-ops-trend-item">
        <div class="invoice-ops-trend-head">
          <strong>${escapeHtml(day || "-")}</strong>
          <span class="meta-text">${count} Retry(s)</span>
        </div>
        <div class="invoice-ops-bar-track">
          <div class="invoice-ops-bar-fill" style="width:${Math.min(100, count * 12)}%"></div>
        </div>
      </article>
    `;
  }).join("");

  const errorRows = topErrors.length
    ? topErrors.map((item) => `<span class="invoice-ops-error-chip">${escapeHtml(item.label || "-")}: ${Number(item.count || 0)}</span>`).join("")
    : '<span class="helper-text">Noch keine dominanten Fehlergründe.</span>';

  trendContainer.innerHTML = `
    <div class="invoice-ops-trend-grid">${trendBars}</div>
    <div class="invoice-ops-error-row">${errorRows}</div>
  `;
}

async function loadInvoiceAttemptHistory(invoiceId, options = {}) {
  const id = String(invoiceId || "").trim();
  if (!id) {
    return [];
  }
  const force = Boolean(options.force);
  const cached = state.invoiceAttemptHistoryById?.[id];
  if (!force && Array.isArray(cached)) {
    return cached;
  }

  state.invoiceAttemptHistoryLoadingById[id] = true;
  try {
    const payload = await apiRequest(`${API_BASE}/api/invoices/${id}/attempts`);
    const attempts = Array.isArray(payload?.attempts) ? payload.attempts : [];
    state.invoiceAttemptHistoryById[id] = attempts;
    return attempts;
  } finally {
    delete state.invoiceAttemptHistoryLoadingById[id];
  }
}

function renderInvoiceAttemptTimelineHtml(invoiceId) {
  const id = String(invoiceId || "");
  if (!id || !state.invoiceHistoryExpandedById?.[id]) {
    return "";
  }

  if (state.invoiceAttemptHistoryLoadingById?.[id]) {
    return '<div class="invoice-attempt-timeline"><p class="helper-text">Historie wird geladen...</p></div>';
  }

  const attempts = Array.isArray(state.invoiceAttemptHistoryById?.[id]) ? state.invoiceAttemptHistoryById[id] : [];
  if (!attempts.length) {
    return '<div class="invoice-attempt-timeline"><p class="helper-text">Noch keine Versandversuche protokolliert.</p></div>';
  }

  const rows = attempts
    .map((attempt) => {
      const failed = String(attempt?.outcome || "").toLowerCase() !== "sent";
      const statusText = failed ? "Fehlgeschlagen" : "Erfolgreich";
      const statusClass = failed ? "invoice-attempt-status-failed" : "invoice-attempt-status-sent";
      return `
        <li class="invoice-attempt-item">
          <div class="invoice-attempt-row">
            <p class="helper-text">Versuch ${escapeHtml(String(attempt?.attempt_number || "-"))}</p>
            <span class="invoice-attempt-status ${statusClass}">${statusText}</span>
          </div>
          <p class="meta-text">${escapeHtml(formatTimestamp(attempt?.created_at || ""))} • ${escapeHtml(String(attempt?.actor_label || "system"))}</p>
          ${attempt?.next_retry_at ? `<p class="helper-text">Nächster Retry: ${escapeHtml(formatTimestamp(attempt.next_retry_at))}</p>` : ""}
          ${attempt?.error_message ? `<p class="helper-text invoice-management-error">Fehler: ${escapeHtml(String(attempt.error_message || ""))}</p>` : ""}
        </li>
      `;
    })
    .join("");

  return `
    <div class="invoice-attempt-timeline">
      <ul class="invoice-attempt-list">
        ${rows}
      </ul>
    </div>
  `;
}

function renderInvoiceManagementList() {
  const container = document.querySelector("#invoiceManagementList");
  const kpiContainer = document.querySelector("#invoiceStatusKpiGrid");
  const retryQueueContainer = document.querySelector("#invoiceRetryQueue");
  if (!container) return;

  renderInvoiceOpsMetrics();

  const filterCompany = (document.querySelector("#invoiceFilterCompany")?.value || "").toLowerCase();
  const filterStatus = (document.querySelector("#invoiceFilterStatus")?.value || "");

  const allInvoices = state.invoices || [];
  let invoices = [...allInvoices];

  if (kpiContainer) {
    const totals = {
      openCount: 0,
      openAmount: 0,
      overdueCount: 0,
      overdueAmount: 0,
      paidCount: 0,
      paidAmount: 0,
      failedCount: 0,
      failedAmount: 0
    };

    allInvoices.forEach((inv) => {
      const amount = Number(inv.total_amount || 0);
      const status = String(inv.status || "").toLowerCase();
      if (status === "bezahlt") {
        totals.paidCount += 1;
        totals.paidAmount += amount;
        return;
      }
      if (status === "overdue") {
        totals.overdueCount += 1;
        totals.overdueAmount += amount;
      }
      if (status === "send_failed") {
        totals.failedCount += 1;
        totals.failedAmount += amount;
      }
      if (["draft", "sent", "overdue", "send_failed"].includes(status)) {
        totals.openCount += 1;
        totals.openAmount += amount;
      }
    });

    kpiContainer.innerHTML = `
      <article class="summary-block invoice-kpi-card invoice-kpi-open">
        <p class="eyebrow">Offen</p>
        <strong>${totals.openCount}</strong>
        <p class="meta-text">${formatCurrency(totals.openAmount)}</p>
      </article>
      <article class="summary-block invoice-kpi-card invoice-kpi-overdue">
        <p class="eyebrow">Überfällig</p>
        <strong>${totals.overdueCount}</strong>
        <p class="meta-text">${formatCurrency(totals.overdueAmount)}</p>
      </article>
      <article class="summary-block invoice-kpi-card invoice-kpi-paid">
        <p class="eyebrow">Bezahlt</p>
        <strong>${totals.paidCount}</strong>
        <p class="meta-text">${formatCurrency(totals.paidAmount)}</p>
      </article>
      <article class="summary-block invoice-kpi-card invoice-kpi-failed">
        <p class="eyebrow">Fehler</p>
        <strong>${totals.failedCount}</strong>
        <p class="meta-text">${formatCurrency(totals.failedAmount)}</p>
      </article>
    `;
  }
  
  // Apply filters
  if (filterCompany) {
    invoices = invoices.filter(inv => {
      const companyName = (inv.company_name || "").toLowerCase();
      return companyName.includes(filterCompany);
    });
  }
  
  if (filterStatus) {
    invoices = invoices.filter(inv => inv.status === filterStatus);
  }

  if (!invoices.length) {
    container.innerHTML = '<div class="empty-state">Keine Rechnungen vorhanden oder keine Treffer.</div>';
    renderInvoiceRetryQueue(retryQueueContainer, allInvoices);
    renderInvoiceApprovalQueue();
    renderInvoiceDeadLetters();
    renderCollectionsList();
    return;
  }

  const rows = invoices
    .map((inv) => {
      const statusLabel = {
        draft: "Entwurf",
        sent: "Versendet",
        overdue: "Überfällig",
        bezahlt: "Bezahlt",
        send_failed: "Fehler"
      }[inv.status] || inv.status;

      const statusKey = String(inv.status || "draft").toLowerCase();
      const statusIcon = {
        draft: "&#9679;",
        sent: "&#10148;",
        overdue: "&#9888;",
        bezahlt: "&#10003;",
        send_failed: "&#10005;"
      }[statusKey] || "&#9679;";

      const statusClass = {
        draft: "",
        sent: "helper-text-info",
        overdue: "helper-text-warning",
        bezahlt: "helper-text-ok",
        send_failed: "helper-text-warning"
      }[inv.status] || "";

      const isPaid = inv.status === "bezahlt" || Boolean(inv.paid_at);
      const canMarkPaid = !isPaid && (getCurrentUser()?.role === "superadmin" || inv.company_id === getCurrentUser()?.company_id);
      const canRetrySend = !isPaid && statusKey === "send_failed" && (getCurrentUser()?.role === "superadmin");
      const canViewHistory = getCurrentUser()?.role === "superadmin";
      const justPaidClass = state.invoiceJustPaidId && state.invoiceJustPaidId === inv.id ? " invoice-status-just-paid" : "";
      const newBadge = state.invoiceNewIds?.[inv.id] ? '<span class="invoice-new-badge">Neu</span>' : "";
      const maxRetryAttempts = 5;
      const retryAttemptCount = Number(inv.send_attempt_count || 0);
      const retryInfo = canRetrySend
        ? `<p class="helper-text invoice-retry-meta">Versuch ${Math.max(1, retryAttemptCount)}/${maxRetryAttempts}${inv.next_retry_at ? ` • Nächster Retry: ${formatTimestamp(inv.next_retry_at)}` : ""}</p>`
        : "";
      const historyExpanded = Boolean(state.invoiceHistoryExpandedById?.[inv.id]);
      const historyLabel = historyExpanded ? "Historie ausblenden" : "Versand-Historie";
      const historyTimeline = canViewHistory ? renderInvoiceAttemptTimelineHtml(inv.id) : "";

      return `
        <article class="card-item invoice-management-item invoice-status-${escapeHtml(statusKey)}${justPaidClass}">
          <div class="invoice-management-head">
            <div class="invoice-management-main">
              <strong>${escapeHtml(inv.invoice_number || "RE-???")} ${newBadge}</strong>
              <p class="helper-text">${escapeHtml(inv.company_name || "Firma")}</p>
              <p class="meta-text">
                ${inv.invoice_date ? formatTimestamp(inv.invoice_date) : "-"} 
                ${inv.paid_at ? ` • Bezahlt: ${formatTimestamp(inv.paid_at)}` : ""}
              </p>
            </div>
            <div class="invoice-management-side">
              <p class="meta-text">${inv.total_amount ? inv.total_amount.toFixed(2) : "0.00"} EUR</p>
              <p class="helper-text ${statusClass}">Status: <span class="invoice-status-badge invoice-status-badge-${escapeHtml(statusKey)}"><span class="invoice-status-icon" aria-hidden="true">${statusIcon}</span><span>${statusLabel}</span></span></p>
            </div>
          </div>

          ${inv.due_date ? `<p class="helper-text">Fälligkeitsdatum: ${formatTimestamp(inv.due_date)}</p>` : ""}
          ${inv.auto_suspend_triggered_at ? `<p class="helper-text helper-text-warning">Auto-Sperrung ausgelöst: ${formatTimestamp(inv.auto_suspend_triggered_at)}</p>` : ""}

          <div class="button-row invoice-management-actions">
            ${canMarkPaid ? `<button type="button" class="ghost-button invoice-mark-paid" data-invoice-id="${escapeHtml(inv.id)}">Als bezahlt markieren</button>` : ""}
            ${canRetrySend ? `<button type="button" class="ghost-button" data-invoice-retry-id="${escapeHtml(inv.id)}">Erneut senden</button>` : ""}
            ${canViewHistory ? `<button type="button" class="ghost-button" data-invoice-history-toggle-id="${escapeHtml(inv.id)}">${historyLabel}</button>` : ""}
            <span class="helper-text invoice-management-error">${inv.error_message ? `Fehler: ${escapeHtml(inv.error_message)}` : ""}</span>
          </div>
          ${retryInfo}
          ${historyTimeline}
        </article>
      `;
    })
    .join("");

  container.innerHTML = rows;

  // Bind mark-paid buttons
  container.querySelectorAll("[data-invoice-id]").forEach(button => {
    button.addEventListener("click", async (e) => {
      const invId = e.target.dataset.invoiceId;
      if (!invId || !window.confirm(uiT("confirmInvoicePaid"))) return;
      
      try {
        await apiRequest(API_BASE + `/api/invoices/${invId}/pay`, {
          method: "PUT",
          body: { paymentDate: new Date().toISOString().split("T")[0] }
        });
        state.invoiceJustPaidId = invId;
        if (invoicePaidHighlightTimer) {
          clearTimeout(invoicePaidHighlightTimer);
        }
        invoicePaidHighlightTimer = setTimeout(() => {
          state.invoiceJustPaidId = "";
          renderInvoiceManagementList();
        }, 2200);
        window.alert(runtimeText("invoiceMarkedPaid"));
        await loadAndRenderInvoices();
        await loadAllData();
        refreshAll();
      } catch (error) {
        window.alert(uiT("alertGenericError").replace("{error}", error.message));
      }
    });
  });

  container.querySelectorAll("[data-invoice-retry-id]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      const retryId = event.target.dataset.invoiceRetryId;
      if (!retryId) return;
      if (!window.confirm(uiT("confirmInvoiceRetry"))) return;

      try {
        const payload = await apiRequest(API_BASE + `/api/invoices/${retryId}/retry-send`, {
          method: "POST",
          body: {}
        });
        if (payload?.sent) {
          window.alert(uiT("alertInvoiceRetrySent"));
        } else {
          window.alert(uiT("alertInvoiceRetryFailed").replace("{error}", payload?.error || "Unbekannter Fehler"));
        }
        await loadAndRenderInvoices();
        await loadAllData();
        refreshAll();
      } catch (error) {
        window.alert(uiT("alertInvoiceRetryFailed").replace("{error}", error.message));
      }
    });
  });

  container.querySelectorAll("[data-invoice-history-toggle-id]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      const invoiceId = String(event.target.dataset.invoiceHistoryToggleId || "").trim();
      if (!invoiceId) {
        return;
      }

      const isExpanded = Boolean(state.invoiceHistoryExpandedById?.[invoiceId]);
      if (isExpanded) {
        delete state.invoiceHistoryExpandedById[invoiceId];
        renderInvoiceManagementList();
        return;
      }

      state.invoiceHistoryExpandedById[invoiceId] = true;
      renderInvoiceManagementList();
      try {
        await loadInvoiceAttemptHistory(invoiceId, { force: true });
      } catch (error) {
        window.alert(uiT("alertInvoiceHistoryLoadFailed").replace("{error}", error.message));
      }
      renderInvoiceManagementList();
    });
  });

  renderInvoiceRetryQueue(retryQueueContainer, allInvoices);
  renderInvoiceApprovalQueue();
  renderInvoiceDeadLetters();

  renderCollectionsList();
}

function renderInvoiceRetryQueue(container, sourceInvoices) {
  if (!container) return;
  const kpiContainer = document.querySelector("#invoiceRetryKpiGrid");
  const criticalSendButton = document.querySelector("#invoiceRetryCriticalSendBtn");
  const maxRetryAttempts = 5;
  const retryFilterMode = String(document.querySelector("#invoiceRetryFilterMode")?.value || "all");
  const retryFilterCompany = String(document.querySelector("#invoiceRetryFilterCompany")?.value || "").trim().toLowerCase();
  const topIssuesOnly = Boolean(document.querySelector("#invoiceRetryTopIssuesOnly")?.checked);
  const allInvoices = Array.isArray(sourceInvoices) ? sourceInvoices : [];
  const selectedIds = state.invoiceRetrySelectedIds || [];
  const criticalIds = getCriticalRetryInvoiceIds(sourceInvoices, 50);
  if (criticalSendButton) {
    criticalSendButton.textContent = `Nur kritische jetzt senden (${criticalIds.length})`;
    criticalSendButton.disabled = criticalIds.length === 0;
    criticalSendButton.classList.remove("invoice-critical-btn-warn", "invoice-critical-btn-alert");
    if (criticalIds.length >= 20) {
      criticalSendButton.classList.add("invoice-critical-btn-alert");
    } else if (criticalIds.length >= 10) {
      criticalSendButton.classList.add("invoice-critical-btn-warn");
    }
  }
  const failed = (Array.isArray(sourceInvoices) ? sourceInvoices : [])
    .filter((inv) => String(inv?.status || "").toLowerCase() === "send_failed" && !inv?.paid_at)
    .sort((a, b) => {
      const aRetry = String(a?.next_retry_at || "");
      const bRetry = String(b?.next_retry_at || "");
      return aRetry.localeCompare(bRetry);
    });

  const companyFailureCounts = failed.reduce((acc, inv) => {
    const key = String(inv?.company_id || "").trim();
    if (!key) {
      return acc;
    }
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});

  const buildRetryPriority = (inv) => calculateRetryPriority(inv, companyFailureCounts);

  if (kpiContainer) {
    const today = new Date().toISOString().slice(0, 10);
    const retriedSentToday = allInvoices.filter((inv) => {
      const isSent = String(inv?.status || "").toLowerCase() === "sent";
      const hasRetry = Number(inv?.send_attempt_count || 0) > 1;
      const sentToday = String(inv?.sent_at || "").slice(0, 10) === today;
      return isSent && hasRetry && sentToday;
    }).length;
    const maxedOut = failed.filter((inv) => Number(inv?.send_attempt_count || 0) >= maxRetryAttempts).length;
    const highPriority = failed.filter((inv) => buildRetryPriority(inv).score >= 70).length;

    kpiContainer.innerHTML = `
      <article class="summary-block invoice-kpi-card invoice-kpi-failed">
        <p class="eyebrow">Offen fehlgeschlagen</p>
        <strong>${failed.length}</strong>
        <p class="meta-text">In Warteschlange</p>
      </article>
      <article class="summary-block invoice-kpi-card invoice-kpi-paid">
        <p class="eyebrow">Heute nach Retry ok</p>
        <strong>${retriedSentToday}</strong>
        <p class="meta-text">Erneut zugestellt</p>
      </article>
      <article class="summary-block invoice-kpi-card invoice-kpi-overdue">
        <p class="eyebrow">Max Retries erreicht</p>
        <strong>${maxedOut}</strong>
        <p class="meta-text">Manuelle Prüfung nötig</p>
      </article>
      <article class="summary-block invoice-kpi-card invoice-kpi-overdue">
        <p class="eyebrow">Kritische Priorität</p>
        <strong>${highPriority}</strong>
        <p class="meta-text">Score >= 70</p>
      </article>
    `;
  }

  const today = new Date().toISOString().slice(0, 10);
  let filteredFailed = [...failed];

  if (topIssuesOnly) {
    filteredFailed = filteredFailed
      .filter((inv) => Number(inv?.send_attempt_count || 0) >= maxRetryAttempts)
      .sort((a, b) => {
        const aPriority = buildRetryPriority(a);
        const bPriority = buildRetryPriority(b);
        if (bPriority.score !== aPriority.score) {
          return bPriority.score - aPriority.score;
        }
        const aCreated = String(a?.created_at || "");
        const bCreated = String(b?.created_at || "");
        return aCreated.localeCompare(bCreated);
      });
  } else {
    if (retryFilterMode === "priority") {
      filteredFailed = filteredFailed.sort((a, b) => {
        const aPriority = buildRetryPriority(a);
        const bPriority = buildRetryPriority(b);
        if (bPriority.score !== aPriority.score) {
          return bPriority.score - aPriority.score;
        }
        const aCreated = String(a?.created_at || "");
        const bCreated = String(b?.created_at || "");
        return aCreated.localeCompare(bCreated);
      });
    } else if (retryFilterMode === "maxed") {
      filteredFailed = filteredFailed.filter((inv) => Number(inv?.send_attempt_count || 0) >= maxRetryAttempts);
    } else if (retryFilterMode === "today_failed") {
      filteredFailed = filteredFailed.filter((inv) => String(inv?.last_send_attempt_at || "").slice(0, 10) === today);
    }
  }

  if (retryFilterCompany) {
    filteredFailed = filteredFailed.filter((inv) => String(inv?.company_name || "").toLowerCase().includes(retryFilterCompany));
  }

  if (!filteredFailed.length) {
    container.innerHTML = '<div class="empty-state">Keine offenen Versand-Fehler in der Warteschlange.</div>';
    container.onclick = null;
    return;
  }

  container.innerHTML = filteredFailed
    .slice(0, 25)
    .map((inv) => {
      const attempts = Number(inv?.send_attempt_count || 0);
      const checked = selectedIds.includes(inv.id) ? "checked" : "";
      const priority = buildRetryPriority(inv);
      const priorityClass = `invoice-priority-${priority.tier}`;
      return `
        <article class="card-item retry-queue-item">
          <div class="retry-queue-head">
            <div>
              <label class="invoice-retry-select">
                <input type="checkbox" data-retry-queue-select="${escapeHtml(inv.id || "")}" ${checked} />
                <span>Auswählen</span>
              </label>
              <strong>${escapeHtml(inv.invoice_number || "RE-???")}</strong>
              <p class="helper-text">${escapeHtml(inv.company_name || "Firma")}</p>
            </div>
            <p class="meta-text">${formatCurrency(inv.total_amount)}</p>
          </div>
          <p class="helper-text">
            <span class="invoice-priority-chip ${priorityClass}">Prio ${priority.score} (${escapeHtml(priority.tier)})</span>
            • Alter: ${priority.ageDays} Tage
            • Firma: ${priority.companyIssueCount} offen
          </p>
          <p class="helper-text">Versuch ${Math.max(1, attempts)}/${maxRetryAttempts}${inv?.next_retry_at ? ` • Nächster Retry: ${formatTimestamp(inv.next_retry_at)}` : ""}</p>
          <p class="helper-text invoice-management-error">${inv?.error_message ? `Letzter Fehler: ${escapeHtml(inv.error_message)}` : ""}</p>
          <div class="button-row invoice-management-actions">
            <button type="button" class="ghost-button" data-retry-queue-send="${escapeHtml(inv.id || "")}">Jetzt erneut senden</button>
          </div>
        </article>
      `;
    })
    .join("");

  container.onclick = async (event) => {
    const selectInput = event.target.closest("[data-retry-queue-select]");
    if (selectInput && container.contains(selectInput)) {
      const retryId = selectInput.dataset.retryQueueSelect;
      if (!retryId) return;
      const set = new Set(state.invoiceRetrySelectedIds || []);
      if (selectInput.checked) {
        set.add(retryId);
      } else {
        set.delete(retryId);
      }
      state.invoiceRetrySelectedIds = Array.from(set);
      return;
    }

    const retryButton = event.target.closest("[data-retry-queue-send]");
    if (!retryButton || !container.contains(retryButton)) return;
    const retryId = retryButton.dataset.retryQueueSend;
    if (!retryId) return;
    if (!window.confirm(uiT("confirmInvoiceRetry"))) return;

    try {
      const payload = await apiRequest(API_BASE + `/api/invoices/${retryId}/retry-send`, {
        method: "POST",
        body: {}
      });
      if (payload?.sent) {
        window.alert(uiT("alertInvoiceRetrySent"));
      } else {
        window.alert(uiT("alertInvoiceRetryFailed").replace("{error}", payload?.error || "Unbekannter Fehler"));
      }
      await loadAndRenderInvoices();
      await loadAllData();
      refreshAll();
    } catch (error) {
      window.alert(uiT("alertInvoiceRetryFailed").replace("{error}", error.message));
    }
  };
}

function calculateRetryPriority(inv, companyFailureCounts = {}) {
  const attemptCount = Number(inv?.send_attempt_count || 0);
  const amount = Number(inv?.total_amount || 0);
  const createdAt = String(inv?.created_at || "");
  const createdMs = Date.parse(createdAt);
  const ageDays = Number.isFinite(createdMs)
    ? Math.max(0, Math.floor((Date.now() - createdMs) / (24 * 60 * 60 * 1000)))
    : 0;
  const companyIssueCount = Number(companyFailureCounts[String(inv?.company_id || "")] || 1);

  const attemptsScore = Math.min(36, Math.max(1, attemptCount) * 8);
  const ageScore = Math.min(26, ageDays * 1.5);
  const amountScore = Math.min(22, amount / 220);
  const companyScore = Math.min(16, companyIssueCount * 4);
  const score = Math.round(attemptsScore + ageScore + amountScore + companyScore);

  let tier = "niedrig";
  if (score >= 70) {
    tier = "kritisch";
  } else if (score >= 45) {
    tier = "hoch";
  }

  return { score, tier, ageDays, companyIssueCount };
}

function getCriticalRetryInvoiceIds(sourceInvoices, maxItems = 50) {
  const failed = (Array.isArray(sourceInvoices) ? sourceInvoices : [])
    .filter((inv) => String(inv?.status || "").toLowerCase() === "send_failed" && !inv?.paid_at);
  const companyFailureCounts = failed.reduce((acc, inv) => {
    const key = String(inv?.company_id || "").trim();
    if (!key) {
      return acc;
    }
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});

  return failed
    .filter((inv) => calculateRetryPriority(inv, companyFailureCounts).score >= 70)
    .map((inv) => String(inv?.id || ""))
    .filter(Boolean)
    .slice(0, maxItems);
}

function toDateOnly(value) {
  const raw = String(value || "").slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
    return null;
  }
  const parsed = new Date(`${raw}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function getInvoiceCollectionsMeta(invoice) {
  const today = toDateOnly(new Date().toISOString().slice(0, 10));
  const due = toDateOnly(invoice?.due_date);
  const isPaid = String(invoice?.status || "") === "bezahlt" || Boolean(invoice?.paid_at);
  const company = state.companies.find((entry) => entry.id === invoice?.company_id);
  const companyLocked = String(company?.status || "aktiv").toLowerCase() === "gesperrt";

  if (isPaid || !due || !today) {
    return { open: false, overdue: false, prelock: false, locked: false, daysOverdue: 0, companyLocked };
  }

  const msPerDay = 24 * 60 * 60 * 1000;
  const daysOverdue = Math.floor((today.getTime() - due.getTime()) / msPerDay);
  const overdue = daysOverdue > 0;
  const prelock = daysOverdue >= 0 && daysOverdue <= 3 && !companyLocked;
  const locked = companyLocked;

  return {
    open: true,
    overdue,
    prelock,
    locked,
    daysOverdue,
    companyLocked,
  };
}

function renderCollectionsKpis(allOpenRows) {
  const kpiContainer = document.querySelector("#collectionsKpiGrid");
  if (!kpiContainer) {
    return;
  }

  const rows = Array.isArray(allOpenRows) ? allOpenRows : [];
  const totals = {
    all: { count: 0, amount: 0 },
    overdue: { count: 0, amount: 0 },
    prelock: { count: 0, amount: 0 },
    locked: { count: 0, amount: 0 },
  };

  rows.forEach(({ invoice, meta }) => {
    const amount = Number(invoice?.total_amount || 0);
    totals.all.count += 1;
    totals.all.amount += amount;
    if (meta?.overdue) {
      totals.overdue.count += 1;
      totals.overdue.amount += amount;
    }
    if (meta?.prelock) {
      totals.prelock.count += 1;
      totals.prelock.amount += amount;
    }
    if (meta?.locked) {
      totals.locked.count += 1;
      totals.locked.amount += amount;
    }
  });

  const cards = [
    ["Offen gesamt", totals.all],
    ["Ueberfaellig", totals.overdue],
    ["Vor Sperre", totals.prelock],
    ["Gesperrte Firmen", totals.locked],
  ];

  kpiContainer.innerHTML = cards
    .map(([label, data]) => `
      <article class="card-item" style="display:inline-block; min-width:220px; margin:0 8px 8px 0;">
        <p class="helper-text">${escapeHtml(label)}</p>
        <strong>${escapeHtml(String(data.count))}</strong>
        <p class="helper-text">${escapeHtml(formatCurrency(data.amount))}</p>
      </article>
    `)
    .join("");
}

function renderCollectionsList() {
  const container = document.querySelector("#collectionsList");
  if (!container) {
    return;
  }

  const filter = String(document.querySelector("#collectionsFilter")?.value || "all");
  const role = String(getCurrentUser()?.role || "").toLowerCase();
  const canToggleLock = role === "superadmin";

  const allOpenRows = (state.invoices || [])
    .map((invoice) => ({ invoice, meta: getInvoiceCollectionsMeta(invoice) }))
    .filter((entry) => entry.meta.open);

  renderCollectionsKpis(allOpenRows);

  let rows = [...allOpenRows];

  if (filter === "overdue") {
    rows = rows.filter((entry) => entry.meta.overdue);
  } else if (filter === "prelock") {
    rows = rows.filter((entry) => entry.meta.prelock);
  } else if (filter === "locked") {
    rows = rows.filter((entry) => entry.meta.locked);
  }

  if (!rows.length) {
    container.innerHTML = '<div class="empty-state">Keine Inkasso-Faelle fuer den gewaehlten Filter.</div>';
    return;
  }

  container.innerHTML = rows
    .sort((a, b) => {
      const aDue = String(a.invoice?.due_date || "");
      const bDue = String(b.invoice?.due_date || "");
      return aDue.localeCompare(bDue);
    })
    .map(({ invoice, meta }) => {
      const stage = Number(invoice?.reminder_stage || 0);
      const dueText = invoice?.due_date ? formatDate(invoice.due_date) : "-";
      const overdueText = meta.daysOverdue > 0 ? `${meta.daysOverdue} Tag(e) ueberfaellig` : "noch nicht ueberfaellig";
      const badge = meta.locked
        ? '<span class="helper-text helper-text-warning">Firma gesperrt</span>'
        : meta.prelock
          ? '<span class="helper-text helper-text-warning">Vor Sperre</span>'
          : meta.overdue
            ? '<span class="helper-text helper-text-warning">Ueberfaellig</span>'
            : '<span class="helper-text helper-text-info">Offen</span>';
      return `
        <article class="card-item">
          <div style="display:flex; justify-content:space-between; gap:12px; align-items:flex-start;">
            <div style="flex:1;">
              <strong>${escapeHtml(invoice.invoice_number || "RE-???")}</strong>
              <p class="helper-text">${escapeHtml(invoice.company_name || "Firma")}</p>
              <p class="helper-text">Faellig: ${escapeHtml(dueText)} | ${escapeHtml(overdueText)}</p>
              <p class="helper-text">Mahnstufe: ${escapeHtml(String(stage))}</p>
            </div>
            <div style="text-align:right; min-width:160px;">
              <p class="meta-text">${formatCurrency(invoice.total_amount)}</p>
              ${badge}
            </div>
          </div>
          <div class="button-row" style="margin-top:8px;">
            <button type="button" class="ghost-button" data-collections-mark-paid="${escapeHtml(invoice.id || "")}">Als bezahlt markieren</button>
            ${canToggleLock ? `<button type="button" class="ghost-button" data-collections-toggle-lock="${escapeHtml(invoice.company_id || "")}">${meta.companyLocked ? "Sperre aufheben" : "Firma sperren"}</button>` : ""}
          </div>
        </article>
      `;
    })
    .join("");

  container.onclick = async (event) => {
    const paidButton = event.target.closest("[data-collections-mark-paid]");
    if (paidButton && container.contains(paidButton)) {
      const invoiceId = paidButton.dataset.collectionsMarkPaid;
      if (!invoiceId || !window.confirm(uiT("confirmInvoicePaidSimple"))) {
        return;
      }
      try {
        await apiRequest(`${API_BASE}/api/invoices/${invoiceId}/pay`, {
          method: "PUT",
          body: { paymentDate: new Date().toISOString().slice(0, 10) }
        });
        await loadAllData();
        refreshAll();
      } catch (error) {
        window.alert(uiT("alertActionFailed").replace("{error}", error.message));
      }
      return;
    }

    const lockButton = event.target.closest("[data-collections-toggle-lock]");
    if (lockButton && container.contains(lockButton)) {
      const companyId = lockButton.dataset.collectionsToggleLock;
      const company = state.companies.find((entry) => entry.id === companyId);
      if (!companyId || !company) {
        return;
      }
      const currentStatus = String(company.status || "aktiv").toLowerCase();
      const nextStatus = currentStatus === "gesperrt" ? "aktiv" : "gesperrt";
      const ok = window.confirm(nextStatus === "gesperrt"
        ? uiT("confirmLockCompany").replace("{name}", company.name)
        : uiT("confirmUnlockCompany").replace("{name}", company.name)
      );
      if (!ok) {
        return;
      }

      try {
        await apiRequest(`${API_BASE}/api/companies/${companyId}`, {
          method: "PUT",
          body: { status: nextStatus }
        });
        await loadAllData();
        refreshAll();
      } catch (error) {
        window.alert(uiT("alertCollectionsStatusChangeFailed").replace("{error}", error.message));
      }
    }
  };
}

function getSupportPhoneForLockScreen() {
  const fromStorage = String(window.localStorage.getItem(SUPPORT_PHONE_STORAGE_KEY) || "").trim();
  return fromStorage || LOGIN_SUPPORT_PHONE_FALLBACK;
}

function clearLoginSecurityLockScreen() {
  const overlay = document.getElementById("loginSecurityLockOverlay");
  if (overlay) {
    overlay.remove();
  }
  if (loginLockOverlayTimer) {
    window.clearInterval(loginLockOverlayTimer);
    loginLockOverlayTimer = null;
  }
}

function updateLoginLockScreenCountdown() {
  const countdown = document.getElementById("loginSecurityCountdown");
  if (!countdown) {
    return;
  }
  const remainingMs = Math.max(0, Number(state.loginSecurity?.blockedUntil || 0) - Date.now());
  const remainingMinutes = Math.ceil(remainingMs / 60000);
  if (remainingMs <= 0) {
    countdown.textContent = "";
    clearLoginSecurityLockScreen();
    return;
  }
  countdown.textContent = `${remainingMinutes} min`;
}

function showLoginSecurityLockScreen() {
  clearLoginSecurityLockScreen();
  const supportPhone = getSupportPhoneForLockScreen();
  const safePhone = escapeHtml(supportPhone);
  const telPhone = encodeURIComponent(supportPhone.replace(/\s+/g, ""));

  const overlay = document.createElement("div");
  overlay.id = "loginSecurityLockOverlay";
  overlay.style.position = "fixed";
  overlay.style.inset = "0";
  overlay.style.zIndex = "99999";
  overlay.style.display = "grid";
  overlay.style.placeItems = "center";
  overlay.style.background = "radial-gradient(circle at 20% 20%, #ff7878 0%, #b30000 45%, #5a0000 100%)";
  overlay.style.color = "#fff";

  overlay.innerHTML = `
    <div style="text-align:center;max-width:720px;padding:24px;">
      <div style="font-size:1rem;letter-spacing:0.18em;text-transform:uppercase;opacity:0.92;">AI Security Screen</div>
      <h2 style="margin:10px 0 8px;font-size:clamp(1.8rem,4vw,3rem);line-height:1.1;">${escapeHtml(uiT("loginSecurityTitle"))}</h2>
      <p style="margin:0 0 12px;font-size:1.1rem;line-height:1.5;">${escapeHtml(uiT("loginSecurityHint"))}</p>
      <p style="margin:0 0 8px;font-size:1rem;opacity:0.95;">${escapeHtml(uiT("loginSecurityCallPrefix"))}</p>
      <a href="tel:${telPhone}" style="display:inline-block;margin:4px 0 14px;padding:12px 18px;border-radius:10px;background:#fff;color:#900;text-decoration:none;font-weight:800;font-size:1.2rem;">${safePhone}</a>
      <p style="margin:0 0 8px;font-size:0.95rem;opacity:0.95;">${escapeHtml(uiT("alertTooManyAttempts"))}</p>
      <p style="margin:0 0 4px;font-size:0.95rem;opacity:0.95;">${escapeHtml(uiT("loginSecurityFooter"))}</p>
      <p style="margin:8px 0 0;font-size:0.9rem;opacity:0.8;">Lock aktiv: <span id="loginSecurityCountdown"></span></p>
    </div>
  `;

  document.body.appendChild(overlay);
  updateLoginLockScreenCountdown();
  loginLockOverlayTimer = window.setInterval(updateLoginLockScreenCountdown, 1000);
}

function registerLoginFailure(errorCode) {
  // Count failures for wrong credentials AND wrong OTP, for ALL login scopes
  if (!["invalid_credentials", "otp_invalid"].includes(errorCode)) {
    return;
  }
  state.loginSecurity.failCount = Number(state.loginSecurity.failCount || 0) + 1;
  if (state.loginSecurity.failCount >= 3) {
    state.loginSecurity.blockedUntil = Date.now() + LOGIN_HARD_LOCK_MS;
    showLoginSecurityLockScreen();
  }
}

function resetLoginFailureCounter() {
  state.loginSecurity.failCount = 0;
  state.loginSecurity.blockedUntil = 0;
  clearLoginSecurityLockScreen();
}

function isLoginBlockedLocally() {
  return Number(state.loginSecurity.blockedUntil || 0) > Date.now();
}

async function tryAutofillOtpFromClipboard() {
  if (!navigator?.clipboard?.readText) {
    return;
  }
  try {
    const text = String(await navigator.clipboard.readText() || "").trim();
    if (/^\d{6}$/.test(text) && !elements.loginOtpCode.value.trim()) {
      elements.loginOtpCode.value = text;
    }
  } catch {
    // Clipboard read is optional and may be blocked by browser permissions.
  }
}

async function handleLoginSubmit(event) {
  event.preventDefault();

  // Lockout check applies to ALL login scopes
  if (isLoginBlockedLocally()) {
    showLoginSecurityLockScreen();
    return;
  }

  const supportContext = state.supportLoginContext || loadSupportLoginContext();
  const loginScope = elements.loginScope?.value || "auto";

  try {
    const payload = await apiRequest(API_BASE + "/api/login", {
      auth: false,
      method: "POST",
      body: {
        username: elements.loginUsername.value.trim(),
        password: elements.loginPassword.value,
        // Only send OTP in step 2
        otpCode: state.loginOtpPending ? elements.loginOtpCode.value.trim() : "",
        loginScope,
        supportCompanyId: loginScope === "company-admin" ? (supportContext?.companyId || "") : "",
        supportActorName: loginScope === "company-admin" ? (supportContext?.actorName || "") : ""
      }
    });

    if (payload?.ok === false || payload?.error) {
      throw new Error(payload?.error || "login_failed");
    }
    if (!payload?.token || !payload?.user) {
      throw new Error("invalid_login_response");
    }

    resetLoginFailureCounter();
    state.loginOtpPending = false;
    token = payload.token;
    console.log("[Login] Token received:", token ? `${token.slice(0, 20)}...` : "NONE");
    persistSessionToken(token);
    console.log("[Login] Token persisted to storage");
    state.currentUser = payload.user;
    clearSupportLoginContext();
    state.supportLoginContext = null;
    elements.loginForm.reset();
    updateLoginOtpVisibility();
    startHeartbeat();
    startBackendStatusMonitor();
    setView(getDefaultViewForRole(payload.user?.role));
    refreshAll();

    try {
      await loadAllData();
      refreshAll();
    } catch (loadError) {
      console.warn("Post-login data load failed (session stays active):", loadError);
    }
  } catch (error) {
    if (error.message === "backend_unreachable") {
      window.alert(runtimeText("backendUnreachableReload"));
      return;
    }
    if (error.message === "otp_sent") {
      // Credentials verified – OTP was emailed. Show OTP field.
      resetLoginFailureCounter();
      state.loginOtpPending = true;
      updateLoginOtpVisibility();
      await tryAutofillOtpFromClipboard();
      elements.loginOtpCode?.focus();
      window.alert(uiT("alertOtpSent"));
      return;
    }
    if (error.message === "otp_required") {
      // Fallback: no email on user, show OTP field for TOTP entry
      state.loginOtpPending = true;
      updateLoginOtpVisibility();
      await tryAutofillOtpFromClipboard();
      elements.loginOtpCode?.focus();
      window.alert(uiT("alertOtpRequired"));
      return;
    }
    if (error.message === "otp_invalid") {
      registerLoginFailure(error.message);
      if (!isLoginBlockedLocally()) {
        elements.loginOtpCode?.focus();
        window.alert(uiT("alertOtpInvalid"));
      }
      return;
    }
    if (error.message === "too_many_attempts") {
      state.loginSecurity.blockedUntil = Date.now() + LOGIN_HARD_LOCK_MS;
      showLoginSecurityLockScreen();
      return;
    }
    if (error.message === "forbidden_tenant_host") {
      window.alert(uiT("alertForbiddenTenantHost"));
      return;
    }
    if (error.message === "support_session_read_only") {
      showSupportReadOnlyAlert();
      return;
    }
    if (error.message === "support_company_mismatch") {
      window.alert(uiT("alertSupportCompanyMismatch"));
      return;
    }
    if (error.message === "company_locked") {
      window.alert(uiT("alertLoginCompanyLocked"));
      return;
    }
    if (error.message === "invalid_credentials") {
      registerLoginFailure(error.message);
      if (!isLoginBlockedLocally()) {
        window.alert(uiT("alertInvalidCredentials"));
      }
      return;
    }
    if (error.message === "admin_ip_not_allowed") {
      window.alert(uiT("alertAdminIpNotAllowed"));
      return;
    }
    if (error.message === "login_scope_mismatch") {
      window.alert(uiT("alertLoginScopeMismatch"));
      return;
    }
    if (error.message === "http_405") {
      const targetInfo = API_BASE || window.location.origin;
      window.alert(uiT("alertLoginHttp405").replace("{target}", targetInfo));
      return;
    }
    if (error.message === "invalid_login_response") {
      window.alert(runtimeText("loginResponseIncomplete"));
      return;
    }
    window.alert(uiT("alertLoginFailed").replace("{error}", error.message));
  }
}

async function requestPasswordResetFromLogin() {
  const username = String(elements.loginUsername?.value || "").trim();
  if (!username) {
    window.alert(uiT("alertPasswordResetEnterUsername"));
    return;
  }
  try {
    await apiRequest(API_BASE + "/api/auth/request-password-reset", {
      auth: false,
      method: "POST",
      body: { username }
    });
    window.alert(uiT("alertPasswordResetSent"));
  } catch (error) {
    window.alert(uiT("alertPasswordResetFailed").replace("{error}", error.message));
  }
}

async function maybeHandlePasswordResetToken() {
  const url = new URL(window.location.href);
  const rawToken = url.searchParams.get("resetToken");
  if (!rawToken) {
    return;
  }
  const newPassword = window.prompt(uiT("promptNewPassword"), "");
  if (!newPassword) {
    return;
  }
  try {
    await apiRequest(`${API_BASE}/api/auth/reset-password/${encodeURIComponent(rawToken)}`, {
      auth: false,
      method: "POST",
      body: { password: newPassword }
    });
    url.searchParams.delete("resetToken");
    window.history.replaceState({}, document.title, url.toString());
    window.alert(uiT("alertPasswordSetSuccess"));
  } catch (error) {
    window.alert(uiT("alertPasswordResetLinkFailed").replace("{error}", error.message));
  }
}

async function handleLogout(options = {}) {
  const { preserveSupportContext = false } = options;
  try {
    if (token) {
      await apiRequest(API_BASE + "/api/logout", { method: "POST" });
    }
  } catch {
    // ignore logout call failures
  }

  if (!preserveSupportContext) {
    clearSupportLoginContext();
    state.supportLoginContext = null;
  }
  clearSession();
  setView("dashboard");
  stopCamera();
  refreshAll();
}

async function handlePasswordChange(event) {
  event.preventDefault();
  if (isSupportReadOnlyMode()) {
    showSupportReadOnlyAlert();
    return;
  }
  const currentPassword = document.querySelector("#currentPassword").value;
  const newPassword = document.querySelector("#newPassword").value;

  try {
    await apiRequest(API_BASE + "/api/me/password", {
      method: "POST",
      body: { currentPassword, newPassword }
    });
    window.alert(uiT("alertPasswordChanged"));
    await handleLogout();
  } catch (error) {
    window.alert(uiT("alertPasswordChangeFailed").replace("{error}", error.message));
  }
}


// ── 2FA Panel ──────────────────────────────────────────────────────────────
function renderTwofaPanel() {
  const panel = document.getElementById("twofaPanel");
  if (!panel) {
    return;
  }

  const enabled = Boolean(state.twofa.enabled || state.currentUser?.twofa_enabled);
  const currentEmail = state.currentUser?.email || "";

  if (enabled) {
    panel.innerHTML = `
      <div style="margin-bottom:10px">
        <span class="status-pill status-ok">${escapeHtml(uiT("tfaStatusActive"))}</span>
      </div>
      <p style="margin:0 0 8px;font-size:0.88rem;color:#555">${escapeHtml(currentEmail || "–")}</p>
      <div class="button-row">
        <button type="button" class="danger-button" onclick="disableTwofa()">${escapeHtml(uiT("tfaBtnDisable"))}</button>
      </div>
    `;
    return;
  }

  panel.innerHTML = `
    <div style="margin-bottom:10px">
      <span class="status-pill status-test">${escapeHtml(uiT("tfaStatusInactive"))}</span>
    </div>
    <p style="margin:0 0 6px;font-size:0.88rem">${escapeHtml(uiT("tfaActivateOneClickHint"))}</p>
    <label style="display:block;margin-bottom:10px;font-size:0.88rem">
      <span>${escapeHtml(uiT("tfaEmailLabel"))}</span><br>
      <input id="tfaEmailInput" type="email" placeholder="${escapeHtml(uiT("tfaEmailPlaceholder"))}"
        value="${escapeHtml(currentEmail)}"
        style="width:100%;max-width:300px;margin-top:4px;padding:6px 8px;border:1px solid #ccc;border-radius:4px;font-size:0.9rem">
    </label>
    <div class="button-row">
      <button type="button" class="primary-button" onclick="activateTwofa()">${escapeHtml(uiT("tfaBtnEnable"))}</button>
    </div>
  `;
}

async function activateTwofa() {
  const emailInput = document.getElementById("tfaEmailInput");
  const email = (emailInput?.value || "").trim();
  if (!email) {
    window.alert(uiT("alertTfaEmailRequired"));
    return;
  }
  try {
    // Save email first
    await apiRequest(API_BASE + "/api/me/email", { method: "PUT", body: { email } });
    // Then activate 2FA
    await apiRequest(API_BASE + "/api/me/2fa/activate", { method: "POST", body: {} });
    state.twofa.enabled = true;
    if (state.currentUser) {
      state.currentUser.twofa_enabled = 1;
      state.currentUser.email = email;
    }
    window.alert(uiT("alertTfaActivated"));
    refreshAll();
  } catch (error) {
    if (error.message === "email_required") {
      window.alert(uiT("alertTfaEmailRequired"));
    } else {
      window.alert(uiT("alert2faSetupFailed").replace("{error}", error.message));
    }
  }
}

async function disableTwofa() {
  if (!window.confirm(uiT("tfaBtnDisable") + "?")) {
    return;
  }
  try {
    await apiRequest(API_BASE + "/api/me/2fa/disable", { method: "POST", body: {} });
    state.twofa.enabled = false;
    if (state.currentUser) {
      state.currentUser.twofa_enabled = 0;
    }
    refreshAll();
  } catch (error) {
    window.alert(uiT("alert2faDisableFailed").replace("{error}", error.message));
  }
}

async function setupTwofa() {
  // Kept for backward compat – redirect to activateTwofa
  await activateTwofa();
}

async function enableTwofa() {
  // Kept for backward compat – redirect to activateTwofa
  await activateTwofa();
}

async function startCamera() {
  if (!userCanManageWorkers()) {
    return;
  }

  const ua = (navigator.userAgent || "").toLowerCase();
  const isMobile = /android|iphone|ipad|ipod|mobile/.test(ua);
  const legacyGetUserMedia = navigator.getUserMedia || navigator.webkitGetUserMedia || navigator.mozGetUserMedia || navigator.msGetUserMedia;
  const requestUserMedia = async (constraints) => {
    if (navigator.mediaDevices?.getUserMedia) {
      return navigator.mediaDevices.getUserMedia(constraints);
    }
    if (legacyGetUserMedia) {
      return new Promise((resolve, reject) => {
        legacyGetUserMedia.call(navigator, constraints, resolve, reject);
      });
    }
    throw new Error("getUserMedia_not_supported");
  };

  const buildCameraErrorMessage = (error) => {
    const errorName = String(error?.name || "").trim();
    if (!window.isSecureContext) {
      return runtimeText("cameraNeedsHttps");
    }
    if (errorName === "NotAllowedError" || errorName === "SecurityError") {
      return runtimeText("cameraAccessBlocked");
    }
    if (errorName === "NotFoundError" || errorName === "DevicesNotFoundError") {
      return runtimeText("cameraNotFound");
    }
    if (errorName === "NotReadableError" || errorName === "TrackStartError") {
      return runtimeText("cameraInUse");
    }
    if (errorName === "OverconstrainedError" || errorName === "ConstraintNotSatisfiedError") {
      return runtimeText("cameraConstraintFailed");
    }
    if (errorName === "" && error?.message === "getUserMedia_not_supported") {
      return runtimeText("cameraApiMissing");
    }
    return runtimeTextTemplate("cameraStartFailed", { reason: error?.message || errorName || "unknown error" });
  };

  if (!navigator.mediaDevices?.getUserMedia && !legacyGetUserMedia) {
    if (elements.photoDebugText) {
      const secureHint = window.isSecureContext ? "" : runtimeText("cameraHintSecureContext");
      elements.photoDebugText.textContent = runtimeTextTemplate("cameraUnavailableWithHint", { hint: secureHint });
      elements.photoDebugText.style.color = "#8a5a00";
    }
    return;
  }

  const videoConstraintCandidates = [
    {
      facingMode: { ideal: "user" },
      width: { ideal: 1280 },
      height: { ideal: 720 },
      frameRate: { ideal: 24, max: 30 }
    },
    {
      facingMode: { ideal: "environment" },
      width: { ideal: 1280 },
      height: { ideal: 720 }
    },
    true
  ];

  try {
    stopCamera();
    let lastError = null;

    for (const videoConstraint of videoConstraintCandidates) {
      try {
        cameraStream = await requestUserMedia({
          video: videoConstraint,
          audio: false
        });
        if (cameraStream) {
          break;
        }
      } catch (error) {
        lastError = error;
      }
    }

    if (!cameraStream && navigator.mediaDevices?.enumerateDevices) {
      const devices = await navigator.mediaDevices.enumerateDevices().catch(() => []);
      const videoInputs = devices.filter((device) => device.kind === "videoinput");
      for (const device of videoInputs) {
        try {
          cameraStream = await requestUserMedia({
            video: { deviceId: { exact: device.deviceId } },
            audio: false
          });
          if (cameraStream) {
            break;
          }
        } catch (error) {
          lastError = error;
        }
      }
    }

    if (!cameraStream) {
      throw lastError || new Error("camera_unavailable");
    }

    elements.cameraPreview.srcObject = cameraStream;
    await new Promise((resolve) => {
      const finalize = () => resolve();
      elements.cameraPreview.onloadedmetadata = finalize;
      window.setTimeout(finalize, 1200);
    });
    await elements.cameraPreview.play();
    elements.cameraPreview.style.visibility = "visible";
    elements.cameraPlaceholder.hidden = true;
    if (elements.photoDebugText) {
      elements.photoDebugText.textContent = runtimeText("cameraActiveCanCapture");
      elements.photoDebugText.style.color = "#0b7a3b";
    }
  } catch (error) {
    const reason = buildCameraErrorMessage(error);
    if (elements.photoDebugText) {
      elements.photoDebugText.textContent = reason;
      elements.photoDebugText.style.color = "#8a5a00";
    }
    if (isMobile && (error?.name === "NotAllowedError" || error?.name === "SecurityError")) {
      window.alert(runtimeText("cameraPermissionRetry"));
      return;
    }
  }
}

function openPhotoFilePicker(options = {}) {
  const { preferCamera = false } = options;
  if (!elements.photoFileInput) {
    return;
  }
  if (preferCamera) {
    elements.photoFileInput.setAttribute("capture", "user");
  }
  elements.photoFileInput.value = "";
  elements.photoFileInput.click();
}

function handlePhotoFileSelected(event) {
  const file = event.target.files?.[0];
  if (!file) {
    return;
  }

  const reader = new FileReader();
  reader.onload = async (loadEvent) => {
    const dataUrl = typeof loadEvent.target?.result === "string" ? loadEvent.target.result : "";
    if (!dataUrl) {
      window.alert(runtimeText("photoReadFailed"));
      return;
    }
    const cleaned = await processStillImageBackground(dataUrl);
    setPhotoEditorSource(cleaned || dataUrl, { resetOffset: true });
  };
  reader.onerror = () => {
    window.alert(runtimeText("photoLoadFailed"));
  };
  reader.readAsDataURL(file);
}

async function capturePhoto() {
  const context = elements.photoCanvas.getContext("2d", { willReadFrequently: true });
  const video = elements.cameraPreview;

  if (!video.videoWidth || !video.videoHeight) {
    window.alert(runtimeText("cameraStartFirst"));
    return;
  }

  if (!context) {
    window.alert(runtimeText("photoProcessingUnavailable"));
    return;
  }

  const targetWidth = PHOTO_TARGET_WIDTH;
  const targetHeight = PHOTO_TARGET_HEIGHT;
  elements.photoCanvas.width = targetWidth;
  elements.photoCanvas.height = targetHeight;

  // Keep transparent canvas so removed background stays truly transparent.
  context.clearRect(0, 0, targetWidth, targetHeight);
  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = "high";

  // Passfoto framing: crop to portrait ratio with a slight top bias for face/headroom.
  const sourceWidth = video.videoWidth;
  const sourceHeight = video.videoHeight;
  const sourceAspect = sourceWidth / sourceHeight;
  const targetAspect = targetWidth / targetHeight;

  let cropX = 0;
  let cropY = 0;
  let cropWidth = sourceWidth;
  let cropHeight = sourceHeight;

  if (sourceAspect > targetAspect) {
    cropWidth = Math.round(sourceHeight * targetAspect);
    cropX = Math.round((sourceWidth - cropWidth) / 2);
  } else {
    cropHeight = Math.round(sourceWidth / targetAspect);
    const centered = Math.round((sourceHeight - cropHeight) / 2);
    cropY = Math.max(Math.round(centered * 0.55), 0);
  }

  context.drawImage(video, cropX, cropY, cropWidth, cropHeight, 0, 0, targetWidth, targetHeight);

  const imageData = context.getImageData(0, 0, targetWidth, targetHeight);
  const data = imageData.data;
  const brightness = 8;
  const contrast = 1.05;
  for (let i = 0; i < data.length; i += 4) {
    data[i] = Math.max(0, Math.min(255, (data[i] - 128) * contrast + 128 + brightness));
    data[i + 1] = Math.max(0, Math.min(255, (data[i + 1] - 128) * contrast + 128 + brightness));
    data[i + 2] = Math.max(0, Math.min(255, (data[i + 2] - 128) * contrast + 128 + brightness));
  }
  context.putImageData(imageData, 0, 0);

  // Background removal disabled: keep original camera background as requested.

  const photo = elements.photoCanvas.toDataURL("image/png");
  setPhotoEditorSource(photo, { resetOffset: true });
  applyPhotoEditorTransform();

  if (elements.photoDebugText) {
    elements.photoDebugText.textContent = runtimeTextTemplate("photoCaptured", {
      preview: photo ? photo.slice(0, 30) : "empty",
    });
    elements.photoDebugText.style.color = "#0b7a3b";
  }

  // Setze Bild auch im digitalen Ausweis (Badge-Vorschau)
  if (elements.badgePreview) {
    let badgeImg = elements.badgePreview.querySelector('img');
    if (!badgeImg) {
      badgeImg = document.createElement('img');
      badgeImg.alt = "Mitarbeiterfoto";
      badgeImg.style.maxWidth = "120px";
      badgeImg.style.maxHeight = "150px";
      badgeImg.style.borderRadius = "14px";
      badgeImg.style.border = "1px solid #ccc";
      elements.badgePreview.innerHTML = "";
      elements.badgePreview.appendChild(badgeImg);
    }
    badgeImg.src = photo;
    badgeImg.style.display = 'inline-block';
  }
}

async function processStillImageBackground(dataUrl) {
  try {
    const img = await new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = reject;
      image.src = dataUrl;
    });

    const context = elements.photoCanvas.getContext("2d", { willReadFrequently: true });
    if (!context) {
      return dataUrl;
    }

    const targetWidth = PHOTO_TARGET_WIDTH;
    const targetHeight = PHOTO_TARGET_HEIGHT;
    elements.photoCanvas.width = targetWidth;
    elements.photoCanvas.height = targetHeight;

    context.clearRect(0, 0, targetWidth, targetHeight);
    context.imageSmoothingEnabled = true;
    context.imageSmoothingQuality = "high";

    const sourceWidth = img.naturalWidth || img.width;
    const sourceHeight = img.naturalHeight || img.height;
    const sourceAspect = sourceWidth / sourceHeight;
    const targetAspect = targetWidth / targetHeight;

    let cropX = 0;
    let cropY = 0;
    let cropWidth = sourceWidth;
    let cropHeight = sourceHeight;

    if (sourceAspect > targetAspect) {
      cropWidth = Math.round(sourceHeight * targetAspect);
      cropX = Math.round((sourceWidth - cropWidth) / 2);
    } else {
      cropHeight = Math.round(sourceWidth / targetAspect);
      const centered = Math.round((sourceHeight - cropHeight) / 2);
      cropY = Math.max(Math.round(centered * 0.55), 0);
    }

    context.drawImage(img, cropX, cropY, cropWidth, cropHeight, 0, 0, targetWidth, targetHeight);
    return elements.photoCanvas.toDataURL("image/png");
  } catch {
    return dataUrl;
  }
}

function initSelfieSegmenter() {
  if (selfieSegmenter) {
    return Promise.resolve(selfieSegmenter);
  }
  return new Promise((resolve, reject) => {
    const seg = new SelfieSegmentation({
      locateFile: (file) =>
        `https://cdn.jsdelivr.net/npm/@mediapipe/selfie_segmentation@0.1.1675465747/${file}`
    });
    // Model 0 gives cleaner edges than the fast landscape model.
    seg.setOptions({ modelSelection: 0 });
    seg.onResults(() => {});
    seg.initialize().then(() => {
      selfieSegmenter = seg;
      resolve(selfieSegmenter);
    }).catch(reject);
  });
}

async function removeBackgroundML(canvas, context) {
  try {
    const segmenter = await initSelfieSegmenter();
    const width = canvas.width;
    const height = canvas.height;

    const result = await new Promise((resolve) => {
      segmenter.onResults((r) => resolve(r));
      segmenter.send({ image: canvas });
    });

    // Draw segmentation mask to a temp canvas and smooth it to reduce jagged edges.
    const maskCanvas = document.createElement("canvas");
    maskCanvas.width = width;
    maskCanvas.height = height;
    const maskCtx = maskCanvas.getContext("2d", { willReadFrequently: true });
    if (!maskCtx) {
      boostWhiteBackground(context, canvas.width, canvas.height);
      return;
    }
    maskCtx.imageSmoothingEnabled = true;
    maskCtx.imageSmoothingQuality = "high";
    maskCtx.drawImage(result.segmentationMask, 0, 0, width, height);

    const smoothMaskCanvas = document.createElement("canvas");
    smoothMaskCanvas.width = width;
    smoothMaskCanvas.height = height;
    const smoothMaskCtx = smoothMaskCanvas.getContext("2d", { willReadFrequently: true });
    if (!smoothMaskCtx) {
      boostWhiteBackground(context, canvas.width, canvas.height);
      return;
    }
    smoothMaskCtx.imageSmoothingEnabled = true;
    smoothMaskCtx.imageSmoothingQuality = "high";
    smoothMaskCtx.filter = "blur(1.1px)";
    smoothMaskCtx.drawImage(maskCanvas, 0, 0, width, height);
    smoothMaskCtx.filter = "none";
    const maskData = smoothMaskCtx.getImageData(0, 0, width, height).data;

    const imageData = context.getImageData(0, 0, width, height);
    const data = imageData.data;

    for (let i = 0; i < data.length; i += 4) {
      const personConfidence = maskData[i] / 255;
      if (personConfidence < 0.56) {
        data[i + 3] = 0;
      } else if (personConfidence < 0.84) {
        const alpha = Math.round(((personConfidence - 0.56) / 0.28) * 255);
        data[i + 3] = Math.max(0, Math.min(255, alpha));
      } else {
        data[i + 3] = 255;
      }
    }
    context.putImageData(imageData, 0, 0);
    enhancePhotoClarity(context, width, height, maskData);
    knockOutWhitePixelsToAlpha(context, width, height);
  } catch {
    // ML not available — keep original image without forced white background.
    enhancePhotoClarity(context, canvas.width, canvas.height);
    knockOutWhitePixelsToAlpha(context, canvas.width, canvas.height);
  }
}

function knockOutWhitePixelsToAlpha(context, width, height) {
  const imageData = context.getImageData(0, 0, width, height);
  const data = imageData.data;

  for (let i = 0; i < data.length; i += 4) {
    const r = data[i];
    const g = data[i + 1];
    const b = data[i + 2];
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const nearNeutral = (max - min) <= 22;
    const veryBright = r >= 236 && g >= 236 && b >= 236;
    const brightNeutral = nearNeutral && r >= 224 && g >= 224 && b >= 224;

    if (veryBright || brightNeutral) {
      data[i + 3] = 0;
    }
  }

  context.putImageData(imageData, 0, 0);
}

function finalizeWhiteBackdrop(context, width, height, maskData = null) {
  const imageData = context.getImageData(0, 0, width, height);
  const data = imageData.data;

  for (let i = 0; i < data.length; i += 4) {
    const confidence = maskData ? (maskData[i] / 255) : 0;
    const r = data[i];
    const g = data[i + 1];
    const b = data[i + 2];
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const avg = (r + g + b) / 3;
    const nearNeutral = (max - min) <= 34;

    if (maskData && confidence < 0.9) {
      data[i] = 255;
      data[i + 1] = 255;
      data[i + 2] = 255;
      continue;
    }

    if (nearNeutral && avg >= 170 && (!maskData || confidence < 0.96)) {
      data[i] = 255;
      data[i + 1] = 255;
      data[i + 2] = 255;
    }
  }

  if (!maskData) {
    // Last-resort portrait matte: aggressively whiten outside the central portrait zone.
    const cx = width * 0.5;
    const cy = height * 0.56;
    const rx = width * 0.31;
    const ry = height * 0.44;
    const feather = Math.max(8, Math.round(Math.min(width, height) * 0.04));

    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const nx = (x - cx) / rx;
        const ny = (y - cy) / ry;
        const d = nx * nx + ny * ny;
        if (d <= 1) {
          continue;
        }
        const p = (y * width + x) * 4;
        const edge = Math.min(1, Math.max(0, (d - 1) * (feather / 6)));
        const blend = Math.max(0.7, edge);
        data[p] = Math.round(data[p] + (255 - data[p]) * blend);
        data[p + 1] = Math.round(data[p + 1] + (255 - data[p + 1]) * blend);
        data[p + 2] = Math.round(data[p + 2] + (255 - data[p + 2]) * blend);
      }
    }
  }

  context.putImageData(imageData, 0, 0);
}

function forceFullWhiteBackground(context, maskData, width, height) {
  if (!maskData) {
    return;
  }
  const imageData = context.getImageData(0, 0, width, height);
  const data = imageData.data;
  for (let i = 0; i < data.length; i += 4) {
    const personConfidence = maskData[i] / 255;
    if (personConfidence < 0.85) {
      data[i] = 255;
      data[i + 1] = 255;
      data[i + 2] = 255;
    }
  }
  context.putImageData(imageData, 0, 0);
}

function enhancePhotoClarity(context, width, height, maskData = null) {
  const imageData = context.getImageData(0, 0, width, height);
  const src = imageData.data;
  const original = new Uint8ClampedArray(src);

  const sharpenAmount = photoSharpenAmount;
  if (sharpenAmount < 0.01) return; // No sharpening
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const i = (y * width + x) * 4;
      if (maskData) {
        const confidence = maskData[i] / 255;
        if (confidence < 0.6) {
          continue;
        }
      }
      for (let channel = 0; channel < 3; channel += 1) {
        const c = original[i + channel];
        const up = original[i - width * 4 + channel];
        const down = original[i + width * 4 + channel];
        const left = original[i - 4 + channel];
        const right = original[i + 4 + channel];
        const sharpened = 5 * c - up - down - left - right;
        const mixed = c * (1 - sharpenAmount) + sharpened * sharpenAmount;
        src[i + channel] = Math.max(0, Math.min(255, Math.round(mixed)));
      }
    }
  }
  context.putImageData(imageData, 0, 0);
}

function resetPhotoEditor() {
  photoEditorSourceData = "";
  photoEditorImage = null;
  photoEditorOffset = { x: 0, y: 0 };
  photoEditorZoom = PHOTO_EDITOR_ZOOM_DEFAULT;
  photoDragState = {
    active: false,
    pointerId: null,
    startX: 0,
    startY: 0,
    baseOffsetX: 0,
    baseOffsetY: 0
  };
  elements.photoData.value = "";
  elements.capturedPhoto.src = "";
  elements.capturedPhoto.classList.remove("has-image", "dragging");
  updatePhotoAdjustControlsState();
}

function updatePhotoAdjustControlsState() {
  const hasPhoto = Boolean(
    elements.capturedPhoto &&
    elements.capturedPhoto.src &&
    elements.capturedPhoto.src.startsWith("data:image")
  );

  elements.photoMoveButtons.forEach((button) => {
    button.disabled = !hasPhoto;
  });

  if (elements.photoResetButton) {
    elements.photoResetButton.disabled = !hasPhoto;
  }

  if (elements.photoAdjustStatus) {
    elements.photoAdjustStatus.textContent = runtimeTextTemplate("photoPosition", {
      x: photoEditorOffset.x,
      y: photoEditorOffset.y,
    });
  }

  if (elements.photoZoom) {
    elements.photoZoom.disabled = !hasPhoto;
    elements.photoZoom.value = String(photoEditorZoom);
  }

  if (elements.photoZoomValue) {
    elements.photoZoomValue.textContent = `${photoEditorZoom.toFixed(2)}x`;
  }

  if (elements.photoSharpen) {
    elements.photoSharpen.disabled = !hasPhoto;
    elements.photoSharpen.value = String(photoSharpenAmount);
  }

  if (elements.photoSharpenValue) {
    let label = runtimeText("photoSharpenNormal");
    if (photoSharpenAmount < 0.13) label = runtimeText("photoSharpenSoft");
    else if (photoSharpenAmount > 0.45) label = runtimeText("photoSharpenVerySharp");
    elements.photoSharpenValue.textContent = label;
  }

  if (elements.photoRequiredHint) {
    if (hasPhoto) {
      elements.photoRequiredHint.textContent = runtimeText("photoRequiredOk");
      elements.photoRequiredHint.classList.remove("helper-text-warning");
      elements.photoRequiredHint.classList.add("helper-text-ok");
    } else {
      elements.photoRequiredHint.textContent = runtimeText("photoRequiredMissing");
      elements.photoRequiredHint.classList.remove("helper-text-ok");
      elements.photoRequiredHint.classList.add("helper-text-warning");
    }
  }
}

function updatePhotoAdjustControlsState() {
  // Aktiviere die Bearbeitungsbuttons immer, wenn ein Foto vorhanden ist
  const hasPhoto = Boolean(elements.capturedPhoto && elements.capturedPhoto.src && elements.capturedPhoto.src.startsWith("data:image"));
  elements.photoMoveButtons.forEach((button) => {
    button.disabled = !hasPhoto;
  });
  if (elements.photoResetButton) {
    elements.photoResetButton.disabled = !hasPhoto;
  }
  if (elements.photoAdjustStatus) {
    elements.photoAdjustStatus.textContent = runtimeTextTemplate("photoPosition", {
      x: photoEditorOffset.x,
      y: photoEditorOffset.y,
    });
  }
  if (elements.photoZoom) {
    elements.photoZoom.disabled = !hasPhoto;
    elements.photoZoom.value = String(photoEditorZoom);
  }
  if (elements.photoZoomValue) {
    elements.photoZoomValue.textContent = `${photoEditorZoom.toFixed(2)}x`;
  }
  if (elements.photoSharpen) {
    elements.photoSharpen.disabled = !hasPhoto;
    elements.photoSharpen.value = String(photoSharpenAmount);
  }
  if (elements.photoSharpenValue) {
    let label = runtimeText("photoSharpenNormal");
    if (photoSharpenAmount < 0.13) label = runtimeText("photoSharpenSoft");
    else if (photoSharpenAmount > 0.45) label = runtimeText("photoSharpenVerySharp");
    elements.photoSharpenValue.textContent = label;
  }
}

// Bearbeitungsfunktionen für Foto-Verschiebung
elements.photoMoveButtons.forEach((button) => {
  button.onclick = () => {
    if (!elements.capturedPhoto || !elements.capturedPhoto.src.startsWith("data:image")) return;
    const direction = button.dataset.photoMove;
    // Hole aktuelle Position aus Style oder setze Standard
    let x = parseInt(elements.capturedPhoto.getAttribute('data-x') || '0', 10);
    let y = parseInt(elements.capturedPhoto.getAttribute('data-y') || '0', 10);
    if (direction === "left") x -= 10;
    if (direction === "right") x += 10;
    if (direction === "up") y -= 10;
    if (direction === "down") y += 10;
    elements.capturedPhoto.style.transform = `translate(${x}px, ${y}px)`;
    elements.capturedPhoto.setAttribute('data-x', x);
    elements.capturedPhoto.setAttribute('data-y', y);
    if (elements.photoAdjustStatus) {
      elements.photoAdjustStatus.textContent = runtimeTextTemplate("photoPosition", { x, y });
    }
  };
});

function handlePhotoZoomInput(event) {
  const rawValue = Number(event.target.value || PHOTO_EDITOR_ZOOM_DEFAULT);
  photoEditorZoom = Math.min(PHOTO_EDITOR_ZOOM_MAX, Math.max(PHOTO_EDITOR_ZOOM_MIN, rawValue));
  if (photoEditorSourceData) {
    applyPhotoEditorTransform();
  } else {
    updatePhotoAdjustControlsState();
  }
}

function handlePhotoSharpenInput(event) {
  const rawValue = Number(event.target.value || 0.28);
  photoSharpenAmount = Math.max(0, Math.min(2, rawValue));
  if (photoEditorSourceData) {
    applyPhotoEditorTransform();
  } else {
    updatePhotoAdjustControlsState();
  }
}

function resetCapturedPhotoPosition() {
  if (!photoEditorSourceData) {
    return;
  }
  photoEditorOffset = { x: 0, y: 0 };
  applyPhotoEditorTransform();
}

function moveCapturedPhoto(direction) {
  if (!photoEditorSourceData) {
    return;
  }

  if (direction === "left") {
    photoEditorOffset.x -= PHOTO_EDITOR_STEP;
  } else if (direction === "right") {
    photoEditorOffset.x += PHOTO_EDITOR_STEP;
  } else if (direction === "up") {
    photoEditorOffset.y -= PHOTO_EDITOR_STEP;
  } else if (direction === "down") {
    photoEditorOffset.y += PHOTO_EDITOR_STEP;
  }

  applyPhotoEditorTransform();
}

function clampPhotoEditorOffset(offset, maxX, maxY) {
  return {
    x: Math.max(-maxX, Math.min(maxX, offset.x)),
    y: Math.max(-maxY, Math.min(maxY, offset.y)),
  };
}

function applyPhotoEditorTransform() {
  if (!photoEditorSourceData) {
    updatePhotoAdjustControlsState();
    return;
  }

  if (photoEditorImage?.src === photoEditorSourceData) {
    renderPhotoEditorImage(photoEditorImage);
    return;
  }

  const image = new Image();
  image.onload = () => {
    photoEditorImage = image;
    renderPhotoEditorImage(image);
  };
  image.onerror = () => {
    window.alert(runtimeText("photoLoadFailed"));
    resetPhotoEditor();
  };
  image.src = photoEditorSourceData;
}

function renderPhotoEditorImage(image) {
  const context = elements.photoCanvas.getContext("2d", { willReadFrequently: true });
  if (!context) {
    return;
  }

  const width = PHOTO_TARGET_WIDTH;
  const height = PHOTO_TARGET_HEIGHT;
  elements.photoCanvas.width = width;
  elements.photoCanvas.height = height;

  const drawWidth = Math.round(width * photoEditorZoom);
  const drawHeight = Math.round(height * photoEditorZoom);
  const maxOffsetX = Math.max(Math.floor((drawWidth - width) / 2), 0);
  const maxOffsetY = Math.max(Math.floor((drawHeight - height) / 2), 0);
  photoEditorOffset = clampPhotoEditorOffset(photoEditorOffset, maxOffsetX, maxOffsetY);

  const drawX = Math.round((width - drawWidth) / 2 + photoEditorOffset.x);
  const drawY = Math.round((height - drawHeight) / 2 + photoEditorOffset.y);

  context.clearRect(0, 0, width, height);
  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = "high";
  context.drawImage(image, drawX, drawY, drawWidth, drawHeight);
  // Keep natural background in preview.

  const adjusted = elements.photoCanvas.toDataURL("image/png");
  elements.photoData.value = adjusted;
  elements.capturedPhoto.src = adjusted;
  elements.capturedPhoto.style.display = "inline-block";
  elements.capturedPhoto.classList.add("has-image");
  updatePhotoAdjustControlsState();
}

function startPhotoDrag(event) {
  if (!photoEditorSourceData) {
    return;
  }
  photoDragState = {
    active: true,
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    baseOffsetX: photoEditorOffset.x,
    baseOffsetY: photoEditorOffset.y
  };
  elements.capturedPhoto.classList.add("dragging");
  elements.capturedPhoto.setPointerCapture(event.pointerId);
  event.preventDefault();
}

function movePhotoDrag(event) {
  if (!photoDragState.active || event.pointerId !== photoDragState.pointerId) {
    return;
  }
  const deltaX = Math.round(event.clientX - photoDragState.startX);
  const deltaY = Math.round(event.clientY - photoDragState.startY);
  photoEditorOffset = {
    x: photoDragState.baseOffsetX + deltaX,
    y: photoDragState.baseOffsetY + deltaY
  };
  applyPhotoEditorTransform();
}

function endPhotoDrag(event) {
  if (!photoDragState.active || event.pointerId !== photoDragState.pointerId) {
    return;
  }
  photoDragState.active = false;
  photoDragState.pointerId = null;
  elements.capturedPhoto.classList.remove("dragging");
  if (elements.capturedPhoto.hasPointerCapture(event.pointerId)) {
    elements.capturedPhoto.releasePointerCapture(event.pointerId);
  }
}

function boostWhiteBackground(context, width, height) {
  const imageData = context.getImageData(0, 0, width, height);
  const data = imageData.data;

  // Sample full perimeter with median for robust background color detection
  const rs = [];
  const gs = [];
  const bs = [];
  const borderThickness = 10;
  const stepX = Math.max(1, Math.floor(width / 80));
  const stepY = Math.max(1, Math.floor(height / 80));

  for (let bRow = 0; bRow < borderThickness; bRow++) {
    for (let x = 0; x < width; x += stepX) {
      const topIdx = (bRow * width + x) * 4;
      rs.push(data[topIdx]); gs.push(data[topIdx + 1]); bs.push(data[topIdx + 2]);
      const botIdx = ((height - 1 - bRow) * width + x) * 4;
      rs.push(data[botIdx]); gs.push(data[botIdx + 1]); bs.push(data[botIdx + 2]);
    }
  }
  for (let bCol = 0; bCol < borderThickness; bCol++) {
    for (let y = borderThickness; y < height - borderThickness; y += stepY) {
      const leftIdx = (y * width + bCol) * 4;
      rs.push(data[leftIdx]); gs.push(data[leftIdx + 1]); bs.push(data[leftIdx + 2]);
      const rightIdx = (y * width + (width - 1 - bCol)) * 4;
      rs.push(data[rightIdx]); gs.push(data[rightIdx + 1]); bs.push(data[rightIdx + 2]);
    }
  }

  rs.sort((a, b) => a - b);
  gs.sort((a, b) => a - b);
  bs.sort((a, b) => a - b);
  const mid = Math.floor(rs.length / 2);
  const bg = [rs[mid], gs[mid], bs[mid]];

  // Flood-fill from all border pixels inward.
  // Only pixels CONNECTED TO THE BORDER and similar to bg get removed.
  // Face/hair in the center is never touched — even if color is similar to background.
  // High threshold is safe here because flood-fill can never jump over the person.
  const threshold = 95;
  const blendZone = 45;

  const getDistance = (pixIdx) => {
    const dr = data[pixIdx] - bg[0];
    const dg = data[pixIdx + 1] - bg[1];
    const db = data[pixIdx + 2] - bg[2];
    return Math.sqrt(dr * dr + dg * dg + db * db);
  };

  const visited = new Uint8Array(width * height);
  const queue = [];

  // Seed queue with all border pixels
  for (let x = 0; x < width; x++) {
    queue.push(x);
    queue.push((height - 1) * width + x);
  }
  for (let y = 1; y < height - 1; y++) {
    queue.push(y * width);
    queue.push(y * width + (width - 1));
  }

  let head = 0;
  while (head < queue.length) {
    const pos = queue[head++];
    if (visited[pos]) {
      continue;
    }
    visited[pos] = 1;
    const pixIdx = pos * 4;
    const d = getDistance(pixIdx);

    if (d < threshold + blendZone) {
      if (d < threshold) {
        data[pixIdx] = 255;
        data[pixIdx + 1] = 255;
        data[pixIdx + 2] = 255;
      } else {
        // Soft blend toward white at edges
        const t = 1 - (d - threshold) / blendZone;
        data[pixIdx] = Math.round(data[pixIdx] + (255 - data[pixIdx]) * t * 0.65);
        data[pixIdx + 1] = Math.round(data[pixIdx + 1] + (255 - data[pixIdx + 1]) * t * 0.65);
        data[pixIdx + 2] = Math.round(data[pixIdx + 2] + (255 - data[pixIdx + 2]) * t * 0.65);
      }

      // Expand to 4-connected neighbors
      const px = pos % width;
      const py = Math.floor(pos / width);
      if (px > 0 && !visited[pos - 1]) queue.push(pos - 1);
      if (px < width - 1 && !visited[pos + 1]) queue.push(pos + 1);
      if (py > 0 && !visited[pos - width]) queue.push(pos - width);
      if (py < height - 1 && !visited[pos + width]) queue.push(pos + width);
    }
  }

  context.putImageData(imageData, 0, 0);
}

function stopCamera() {
  if (!cameraStream) {
    return;
  }

  cameraStream.getTracks().forEach((track) => track.stop());
  cameraStream = null;
  elements.cameraPreview.srcObject = null;
  elements.cameraPreview.style.visibility = "hidden";
  elements.cameraPlaceholder.hidden = false;
}

async function exportState(options = {}) {
  try {
    const includeAudit = Boolean(options.includeAudit);
    const includeDayClose = Boolean(options.includeDayClose);
    const includeDeleted = Boolean(options.includeDeleted);
    const companyId = String(options.companyId || "").trim();

    const query = new URLSearchParams();
    if (includeAudit) query.set("includeAudit", "1");
    if (includeDayClose) query.set("includeDayClose", "1");
    if (includeDeleted) query.set("includeDeleted", "1");
    if (companyId) query.set("companyId", companyId);

    const exportPayload = await apiRequest(`${API_BASE}/api/export${query.toString() ? `?${query.toString()}` : ""}`);
    const currentUser = getCurrentUser();
    const exportCompanyId = currentUser?.company_id || currentUser?.companyId || "";
    const exportCompany = state.companies.find((entry) => entry.id === exportCompanyId);
    const exportScopeLabel = exportCompany ? ` fuer ${exportCompany.name}` : "";
    const fileScope = exportPayload?.meta?.scope || (companyId ? "company" : "system");
    const blob = new Blob([JSON.stringify(exportPayload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `baupass-export-${fileScope}-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    if (elements.photoDebugText) {
      const counts = exportPayload?.meta?.counts || {};
      elements.photoDebugText.textContent = `System-Export${exportScopeLabel} wurde heruntergeladen (Firmen: ${counts.companies || 0}, Mitarbeiter: ${counts.workers || 0}, Logs: ${counts.accessLogs || 0}).`;
      elements.photoDebugText.style.color = "#0b7a3b";
    }
  } catch (error) {
    window.alert(uiT("alertExportFailed").replace("{error}", error.message));
  }
}

async function loadDemoData() {
  if (!userCanManageWorkers()) {
    window.alert(runtimeText("demoAdminOnly"));
    return;
  }

  const currentUser = getCurrentUser();
  let companyId = currentUser?.company_id || currentUser?.companyId || "";

  if (!companyId) {
    companyId = state.companies.find((entry) => !entry.deleted_at && !entry.deletedAt)?.id || "";
  }

  if (!companyId) {
    window.alert(uiT("alertNoDemoCompany"));
    return;
  }

  const company = state.companies.find((entry) => entry.id === companyId);
  const companyName = company?.name || "die ausgewaehlte Firma";
  const modeRaw = window.prompt(
    uiT("promptDemoMode").replace("{name}", companyName),
    "replace"
  );
  if (modeRaw === null) {
    return;
  }
  const mode = String(modeRaw || "replace").trim().toLowerCase();
  if (!["replace", "append"].includes(mode)) {
    window.alert(uiT("alertDemoModeInvalid"));
    return;
  }

  const includeInvoices = window.confirm(uiT("confirmDemoInvoices"));
  const includeAccessLogs = window.confirm(uiT("confirmDemoAccessLogs"));

  const proceed = window.confirm(
    mode === "replace"
      ? uiT("confirmDemoReplace").replace("{name}", companyName)
      : uiT("confirmDemoAppend").replace("{name}", companyName)
  );
  if (!proceed) {
    return;
  }

  try {
    const result = await apiRequest(API_BASE + "/api/demo-seed", {
      method: "POST",
      body: {
        companyId,
        mode,
        includeInvoices: includeInvoices ? 1 : 0,
        includeAccessLogs: includeAccessLogs ? 1 : 0,
        includeOverdueExample: 1,
      }
    });
    await loadAllData();
    refreshAll();
    window.alert(
      `Demo-Daten fuer ${companyName} wurden geladen (Modus: ${result.mode}, Mitarbeiter: ${result.workersCreated}, Logs: ${result.accessLogsCreated}, Rechnungen: ${result.invoicesCreated}).`
    );
  } catch (error) {
    window.alert(uiT("alertDemoLoadFailed").replace("{error}", error.message));
  }
}

async function handleTopbarExport() {
  if (!token || !state.currentUser) {
    window.alert(runtimeText("loginFirst"));
    return;
  }
  const exportCompanyId = state.currentUser?.company_id || state.currentUser?.companyId || "";
  const exportCompany = state.companies.find((entry) => entry.id === exportCompanyId);
  const exportScopeLabel = exportCompany ? ` fuer ${exportCompany.name}` : "";
  const includeAudit = window.confirm(uiT("confirmExportAudit"));
  const includeDayClose = window.confirm(uiT("confirmExportDayClose"));
  const includeDeleted = window.confirm(uiT("confirmExportDeleted"));

  let exportCompanyTarget = "";
  if (state.currentUser?.role === "superadmin") {
    const exportAll = window.confirm(uiT("confirmExportAll"));
    if (!exportAll) {
      exportCompanyTarget = exportCompanyId;
    }
  }

  const proceed = window.confirm(uiT("confirmExportDownload").replace("{scope}", exportScopeLabel));
  if (!proceed) {
    return;
  }
  await exportState({
    includeAudit,
    includeDayClose,
    includeDeleted,
    companyId: exportCompanyTarget,
  });
}

async function handleTopbarLogout() {
  const proceed = window.confirm(uiT("confirmLogout"));
  if (!proceed) {
    return;
  }
  await handleLogout();
}

function showImportDryRunDialog(summary) {
  return new Promise((resolve) => {
    const accepted = summary?.accepted || {};
    const conflicts = summary?.conflicts || {};
    const skipped = summary?.skipped || {};
    const unchanged = summary?.unchanged || {};
    const importOnlyChanges = Boolean(summary?.importOnlyChanges);

    const formatBadge = (value, mode) => {
      const numeric = Number(value || 0);
      const text = escapeHtml(String(numeric));
      let bg = "#eef2f7";
      let color = "#1f2937";

      if (mode === "accepted") {
        if (numeric > 0) {
          bg = "#dcfce7";
          color = "#166534";
        }
      } else if (mode === "conflict") {
        if (numeric > 5) {
          bg = "#fee2e2";
          color = "#991b1b";
        } else if (numeric > 0) {
          bg = "#fef3c7";
          color = "#92400e";
        } else {
          bg = "#dcfce7";
          color = "#166534";
        }
      } else if (mode === "skip") {
        if (numeric > 0) {
          bg = "#fef3c7";
          color = "#92400e";
        } else {
          bg = "#dcfce7";
          color = "#166534";
        }
      }

      return `<span style="display:inline-flex; min-width:38px; justify-content:center; padding:2px 8px; border-radius:999px; background:${bg}; color:${color}; font-weight:700;">${text}</span>`;
    };

    const overlay = document.createElement("div");
    overlay.style.position = "fixed";
    overlay.style.inset = "0";
    overlay.style.background = "rgba(10, 16, 26, 0.52)";
    overlay.style.display = "grid";
    overlay.style.placeItems = "center";
    overlay.style.zIndex = "9999";

    const panel = document.createElement("div");
    panel.style.width = "min(860px, 94vw)";
    panel.style.maxHeight = "80vh";
    panel.style.overflow = "auto";
    panel.style.background = "#ffffff";
    panel.style.borderRadius = "14px";
    panel.style.padding = "18px";
    panel.style.boxShadow = "0 12px 38px rgba(0,0,0,0.22)";

    panel.innerHTML = `
      <h3 style="margin:0 0 8px;">Import Vorschau (Dry-Run)</h3>
      <p class="helper-text" style="margin:0 0 12px;">Bitte Zahlen prüfen, bevor der Import angewendet wird.</p>
      <p class="helper-text" style="margin:0 0 12px; color:#475569;">Modus: <strong>${importOnlyChanges ? "Nur Änderungen" : "Alle Datensätze"}</strong> · Unverändert erkannt: ${Number(unchanged.companies || 0) + Number(unchanged.subcompanies || 0) + Number(unchanged.workers || 0) + Number(unchanged.accessLogs || 0) + Number(unchanged.invoices || 0)}</p>
      
      <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:8px; margin-bottom:14px; padding:10px; background:#f9fafb; border-radius:8px; border:1px solid #e5e7eb;">
        <div style="display:flex; align-items:center; gap:6px; font-size:0.85rem;">
          <span style="display:inline-flex; min-width:24px; height:24px; justify-content:center; align-items:center; padding:2px 6px; border-radius:999px; background:#dcfce7; color:#166534; font-weight:700; font-size:0.8rem;">✓</span>
          <span style="color:#16a34a;"><strong>Grün:</strong> OK / keine Konflikte</span>
        </div>
        <div style="display:flex; align-items:center; gap:6px; font-size:0.85rem;">
          <span style="display:inline-flex; min-width:24px; height:24px; justify-content:center; align-items:center; padding:2px 6px; border-radius:999px; background:#fef3c7; color:#92400e; font-weight:700; font-size:0.8rem;">⚠</span>
          <span style="color:#b45309;"><strong>Gelb:</strong> 1-5 Konflikte</span>
        </div>
        <div style="display:flex; align-items:center; gap:6px; font-size:0.85rem;">
          <span style="display:inline-flex; min-width:24px; height:24px; justify-content:center; align-items:center; padding:2px 6px; border-radius:999px; background:#fee2e2; color:#991b1b; font-weight:700; font-size:0.8rem;">✕</span>
          <span style="color:#dc2626;"><strong>Rot:</strong> >5 Konflikte</span>
        </div>
      </div>

      <table style="width:100%; border-collapse:collapse; font-size:0.95rem; margin-bottom:12px;">
        <thead>
          <tr style="background:#f5f7fa; text-align:left;">
            <th style="padding:8px; border:1px solid #d8dee8;">Bereich</th>
            <th style="padding:8px; border:1px solid #d8dee8;">Accepted</th>
            <th style="padding:8px; border:1px solid #d8dee8;">Conflicts</th>
          </tr>
        </thead>
        <tbody>
          <tr><td style="padding:8px; border:1px solid #d8dee8;">Companies</td><td style="padding:8px; border:1px solid #d8dee8;">${formatBadge(accepted.companies, "accepted")}</td><td style="padding:8px; border:1px solid #d8dee8;">${formatBadge(conflicts.companies, "conflict")}</td></tr>
          <tr><td style="padding:8px; border:1px solid #d8dee8;">Subcompanies</td><td style="padding:8px; border:1px solid #d8dee8;">${formatBadge(accepted.subcompanies, "accepted")}</td><td style="padding:8px; border:1px solid #d8dee8;">${formatBadge(conflicts.subcompanies, "conflict")}</td></tr>
          <tr><td style="padding:8px; border:1px solid #d8dee8;">Workers</td><td style="padding:8px; border:1px solid #d8dee8;">${formatBadge(accepted.workers, "accepted")}</td><td style="padding:8px; border:1px solid #d8dee8;">${formatBadge(conflicts.workers, "conflict")}</td></tr>
          <tr><td style="padding:8px; border:1px solid #d8dee8;">Access Logs</td><td style="padding:8px; border:1px solid #d8dee8;">${formatBadge(accepted.accessLogs, "accepted")}</td><td style="padding:8px; border:1px solid #d8dee8;">${formatBadge(conflicts.accessLogs, "conflict")}</td></tr>
          <tr><td style="padding:8px; border:1px solid #d8dee8;">Invoices</td><td style="padding:8px; border:1px solid #d8dee8;">${formatBadge(accepted.invoices, "accepted")}</td><td style="padding:8px; border:1px solid #d8dee8;">${formatBadge(conflicts.invoices, "conflict")}</td></tr>
        </tbody>
      </table>

      <div style="padding:8px 10px; background:#fef3c7; border-radius:6px; border-left:4px solid #b45309; margin-bottom:14px;">
        <p style="margin:0 0 6px; font-weight:600; color:#92400e; font-size:0.9rem;">⚠ Übersprungene Einträge:</p>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; font-size:0.85rem; color:#78350f;">
          <div><strong>Verboten (Berechtigung):</strong> ${formatBadge(skipped.forbidden, "skip")}</div>
          <div><strong>Ungültig (Format):</strong> ${formatBadge(skipped.invalid, "skip")}</div>
        </div>
      </div>

      <div style="display:flex; gap:10px; justify-content:flex-end;">
        <button type="button" class="ghost-button" data-import-preview="cancel">Abbrechen</button>
        <button type="button" class="primary-button" data-import-preview="apply">Import anwenden</button>
      </div>
    `;

    overlay.appendChild(panel);
    document.body.appendChild(overlay);

    const cleanup = (result) => {
      overlay.remove();
      resolve(result);
    };

    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) {
        cleanup(false);
      }
    });

    panel.querySelector('[data-import-preview="cancel"]')?.addEventListener("click", () => cleanup(false));
    panel.querySelector('[data-import-preview="apply"]')?.addEventListener("click", () => cleanup(true));
  });
}

async function handleTopbarImport() {
  if (!token || !state.currentUser) {
    window.alert(runtimeText("loginFirst"));
    return;
  }

  const input = document.createElement("input");
  input.type = "file";
  input.accept = "application/json,.json";

  input.onchange = async () => {
    const file = input.files?.[0];
    if (!file) {
      return;
    }

    try {
      const text = await file.text();
      const parsed = JSON.parse(text);
      const payloadData = parsed?.data && typeof parsed.data === "object" ? parsed.data : parsed;

      const importOnlyChanges = window.confirm(uiT("confirmImportChangesOnly"));

      const dryRunResult = await apiRequest(`${API_BASE}/api/import`, {
        method: "POST",
        body: {
          data: payloadData,
          dryRun: 1,
          importOnlyChanges: importOnlyChanges ? 1 : 0,
        }
      });

      const summary = dryRunResult?.summary || {};
      const proceed = await showImportDryRunDialog(summary);

      if (!proceed) {
        return;
      }

      await apiRequest(`${API_BASE}/api/import`, {
        method: "POST",
        body: {
          data: payloadData,
          dryRun: 0,
          importOnlyChanges: importOnlyChanges ? 1 : 0,
        }
      });

      await loadAllData();
      refreshAll();
      window.alert(uiT("alertImportSuccess"));
    } catch (error) {
      window.alert(uiT("alertImportFailed").replace("{error}", error.message));
    }
  };

  input.click();
}

function buildBadgeId(firstName, lastName, workerType = "worker") {
  const stamp = Date.now().toString(36).slice(-5).toUpperCase();
  const initials = `${firstName[0] || "X"}${lastName[0] || "X"}`.toUpperCase();
  const prefix = workerType === "visitor" ? "VS" : "BP";
  return `${prefix}-${initials}-${stamp}`;
}

function createAvatar(worker) {
  const first = String(worker?.firstName || "");
  const last = String(worker?.lastName || "");
  const rawInitials = `${first[0] || ""}${last[0] || ""}`.toUpperCase();
  const initials = rawInitials.replace(/[^A-Z0-9]/g, "").slice(0, 2) || "BP";
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="320" height="420" viewBox="0 0 320 420">
      <defs>
        <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stop-color="#d95d39" />
          <stop offset="100%" stop-color="#121417" />
        </linearGradient>
      </defs>
      <rect width="320" height="420" rx="36" fill="url(#bg)" />
      <circle cx="160" cy="136" r="68" fill="rgba(255,255,255,0.22)" />
      <path d="M76 338c22-58 64-86 84-86s62 28 84 86" fill="rgba(255,255,255,0.22)" />
      <text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" font-family="Space Grotesk, Arial" font-size="64" font-weight="700" fill="#fff7ef">${initials}</text>
    </svg>
  `;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

function sanitizeImageSrc(value, fallback = "") {
  const raw = String(value || "").trim();
  if (!raw) {
    return fallback;
  }
  const normalized = raw.toLowerCase();
  if (normalized.startsWith("data:image/")) {
    return raw;
  }
  if (normalized.startsWith("blob:")) {
    return raw;
  }
  if (normalized.startsWith("https://") || normalized.startsWith("http://")) {
    return raw;
  }
  if (raw.startsWith("/")) {
    return raw;
  }
  return fallback;
}

function getPlanNetPrice(plan) {
  const normalized = String(plan || "").trim().toLowerCase();
  return PLAN_NET_PRICE_EUR[normalized] || PLAN_NET_PRICE_EUR.tageskarte;
}

function getPlanLabel(plan) {
  const normalized = String(plan || "").trim().toLowerCase();
  return PLAN_LABELS[normalized] || PLAN_LABELS.tageskarte;
}

function formatDate(value) {
  if (!value) {
    return "-";
  }

  return new Intl.DateTimeFormat("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric"
  }).format(new Date(value));
}

function formatTimestamp(value) {
  return new Intl.DateTimeFormat("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

function formatDateTime(value) {
  if (!value) {
    return "-";
  }

  return new Intl.DateTimeFormat("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

window.addEventListener("beforeunload", stopCamera);

if (elements.navLinks.length) {
  elements.navLinks.forEach((link) => {
    link.addEventListener("click", () => {
      if (!token) return;
      setView(link.dataset.view || "dashboard");
    });
  });
}

if (elements.loginForm) {
  elements.loginForm.addEventListener("submit", handleLoginSubmit);
}

if (elements.authOverlay) {
  elements.authOverlay.addEventListener("click", (event) => {
    const interactive = event.target.closest(".auth-panel,input,select,textarea,button,a,label");
    if (interactive) {
      return;
    }
    focusLoginInput({ force: true });
  });
}

if (elements.loginScope) {
  elements.loginScope.addEventListener("change", () => {
    state.loginOtpPending = false;
    updateLoginOtpVisibility();
    if (!token) {
      focusLoginInput({ force: true });
    }
  });
}

updateLoginOtpVisibility();

if (elements.logoutButton) {
  elements.logoutButton.addEventListener("click", handleTopbarLogout);
}

if (elements.seedDataButton) {
  elements.seedDataButton.addEventListener("click", loadDemoData);
}

if (elements.exportButton) {
  elements.exportButton.addEventListener("click", handleTopbarExport);
}

if (elements.importButton) {
  elements.importButton.addEventListener("click", handleTopbarImport);
}

if (elements.systemThemeToggleButton) {
  elements.systemThemeToggleButton.addEventListener("click", toggleSystemTheme);
}

if (elements.systemAlertActionBtn) {
  elements.systemAlertActionBtn.addEventListener("click", () => {
    if (!token) {
      return;
    }
    setView("invoices");
    const invoicesPanel = document.querySelector(".view[data-view='invoices']");
    if (invoicesPanel) {
      invoicesPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
}

const workerCsvButton = document.querySelector("#workerCsvButton");
if (workerCsvButton) {
  workerCsvButton.addEventListener("click", exportWorkersPdf);
}

const workerForm = document.querySelector("#workerForm");
if (workerForm) {
  workerForm.addEventListener("submit", handleWorkerSubmit);
}

const workerCancelEditButton = document.querySelector("#workerCancelEditButton");
if (workerCancelEditButton) {
  workerCancelEditButton.addEventListener("click", () => {
    clearWorkerEditor();
    stopCamera();
  });
}

if (elements.workerType) {
  elements.workerType.addEventListener("change", () => syncWorkerTypeUi());
}

const validUntilInput = document.querySelector("#validUntil");
if (validUntilInput) {
  validUntilInput.addEventListener("change", () => {
    if ((elements.workerType?.value || "worker") === "visitor" && elements.visitEndAt && validUntilInput.value && !elements.visitEndAt.value) {
      elements.visitEndAt.value = `${validUntilInput.value}T23:00`;
    }
  });
}

if (elements.visitEndAt) {
  elements.visitEndAt.addEventListener("change", () => {
    if ((elements.workerType?.value || "worker") === "visitor" && validUntilInput && elements.visitEndAt.value) {
      validUntilInput.value = elements.visitEndAt.value.slice(0, 10);
    }
  });
}

syncWorkerTypeUi();

const accessForm = document.querySelector("#accessForm");
if (accessForm) {
  accessForm.addEventListener("submit", handleAccessSubmit);
}

const accessFilterForm = document.querySelector("#accessFilterForm");
if (accessFilterForm) {
  accessFilterForm.addEventListener("submit", handleAccessFilterSubmit);
}

const accessResetButton = document.querySelector("#accessResetButton");
if (accessResetButton) {
  accessResetButton.addEventListener("click", resetAccessFilter);
}

const accessCsvButton = document.querySelector("#accessCsvButton");
if (accessCsvButton) {
  accessCsvButton.addEventListener("click", exportAccessCsv);
}

const invoiceRefreshButton = document.querySelector("#invoiceRefreshButton");
if (invoiceRefreshButton) {
  invoiceRefreshButton.addEventListener("click", async () => {
    await loadAndRenderInvoices();
    markCurrentInvoicesAsSeen();
    renderInvoiceManagementList();
  });
}

const invoiceFilterCompany = document.querySelector("#invoiceFilterCompany");
if (invoiceFilterCompany) {
  invoiceFilterCompany.addEventListener("input", () => renderInvoiceManagementList());
}

const invoiceFilterStatus = document.querySelector("#invoiceFilterStatus");
if (invoiceFilterStatus) {
  invoiceFilterStatus.addEventListener("change", () => renderInvoiceManagementList());
}

const invoiceRetryFilterMode = document.querySelector("#invoiceRetryFilterMode");
if (invoiceRetryFilterMode) {
  invoiceRetryFilterMode.addEventListener("change", () => renderInvoiceManagementList());
}

const invoiceRetryFilterCompany = document.querySelector("#invoiceRetryFilterCompany");
if (invoiceRetryFilterCompany) {
  invoiceRetryFilterCompany.addEventListener("input", () => renderInvoiceManagementList());
}

const invoiceRetryTopIssuesOnly = document.querySelector("#invoiceRetryTopIssuesOnly");
if (invoiceRetryTopIssuesOnly) {
  invoiceRetryTopIssuesOnly.addEventListener("change", () => renderInvoiceManagementList());
}

const invoiceApprovalFilterAction = document.querySelector("#invoiceApprovalFilterAction");
if (invoiceApprovalFilterAction) {
  invoiceApprovalFilterAction.addEventListener("change", () => renderInvoiceManagementList());
}

const invoiceApprovalMaxAgeMinutes = document.querySelector("#invoiceApprovalMaxAgeMinutes");
if (invoiceApprovalMaxAgeMinutes) {
  invoiceApprovalMaxAgeMinutes.addEventListener("input", () => renderInvoiceManagementList());
}

async function downloadAuthorizedCsv(url, downloadName) {
  const response = await fetch(url, {
    method: "GET",
    headers: { Authorization: `Bearer ${token}` },
    credentials: "include",
  });
  if (!response.ok) {
    let payload = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
    throw new Error(payload?.error || `http_${response.status}`);
  }
  const blob = await response.blob();
  const objectUrl = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = downloadName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(objectUrl);
}

const invoiceRetryExportBtn = document.querySelector("#invoiceRetryExportBtn");
if (invoiceRetryExportBtn) {
  invoiceRetryExportBtn.addEventListener("click", async () => {
    if (!token) {
      handleExpiredControlSession();
      return;
    }
    try {
      await downloadAuthorizedCsv(
        `${API_BASE}/api/invoices/retry-queue/export.csv`,
        `invoice-retry-queue-${new Date().toISOString().slice(0, 10)}.pdf`
      );
    } catch (error) {
      window.alert(uiT("alertCsvExportFailed").replace("{error}", error.message));
    }
  });
}

const invoiceIncidentExportBtn = document.querySelector("#invoiceIncidentExportBtn");
if (invoiceIncidentExportBtn) {
  invoiceIncidentExportBtn.addEventListener("click", async () => {
    if (!token) {
      handleExpiredControlSession();
      return;
    }
    try {
      await downloadAuthorizedCsv(
        `${API_BASE}/api/invoices/incidents/export.csv`,
        `invoice-incidents-${new Date().toISOString().slice(0, 10)}.pdf`
      );
    } catch (error) {
      window.alert(uiT("alertIncidentExportFailed").replace("{error}", error.message));
    }
  });
}

const invoiceRetryBulkSendBtn = document.querySelector("#invoiceRetryBulkSendBtn");
if (invoiceRetryBulkSendBtn) {
  invoiceRetryBulkSendBtn.addEventListener("click", async () => {
    const selectedIds = Array.isArray(state.invoiceRetrySelectedIds) ? state.invoiceRetrySelectedIds : [];
    if (!selectedIds.length) {
      window.alert(uiT("alertSelectInvoiceForRetry"));
      return;
    }
    if (!window.confirm(uiT("confirmBulkRetrySelected").replace("{count}", selectedIds.length))) {
      return;
    }
    try {
      const payload = await apiRequest(`${API_BASE}/api/invoices/retry-send-bulk`, {
        method: "POST",
        body: { invoiceIds: selectedIds }
      });
      if (payload?.approvalRequested) {
        window.alert(uiT("alertDeadLetterResolveApprovalRequested").replace("{id}", payload.approvalId));
      } else {
        const summary = payload?.summary || {};
        window.alert(uiT("alertBulkRetryDone").replace("{sent}", summary.sent || 0).replace("{failed}", summary.failed || 0).replace("{skipped}", summary.skipped || 0));
      }
      state.invoiceRetrySelectedIds = [];
      await loadAndRenderInvoices();
      await loadAllData();
      refreshAll();
    } catch (error) {
      window.alert(uiT("alertBulkRetryFailed").replace("{error}", error.message));
    }
  });
}

const invoiceRetryCriticalSendBtn = document.querySelector("#invoiceRetryCriticalSendBtn");
if (invoiceRetryCriticalSendBtn) {
  invoiceRetryCriticalSendBtn.addEventListener("click", async () => {
    const criticalIds = getCriticalRetryInvoiceIds(state.invoices, 50);

    if (!criticalIds.length) {
      window.alert(uiT("alertNoCriticalCases"));
      return;
    }

    if (!window.confirm(uiT("confirmBulkRetryCritical").replace("{count}", criticalIds.length))) {
      return;
    }

    try {
      const payload = await apiRequest(`${API_BASE}/api/invoices/retry-send-bulk`, {
        method: "POST",
        body: { invoiceIds: criticalIds }
      });
      if (payload?.approvalRequested) {
        window.alert(uiT("alertDeadLetterResolveApprovalRequested").replace("{id}", payload.approvalId));
      } else {
        const summary = payload?.summary || {};
        window.alert(uiT("alertCriticalBulkRetryDone").replace("{sent}", summary.sent || 0).replace("{failed}", summary.failed || 0).replace("{skipped}", summary.skipped || 0));
      }
      state.invoiceRetrySelectedIds = [];
      await loadAndRenderInvoices();
      await loadAllData();
      refreshAll();
    } catch (error) {
      window.alert(uiT("alertCriticalBulkRetryFailed").replace("{error}", error.message));
    }
  });
}

const exportCompanyDocEmailsBtn = document.querySelector("#exportCompanyDocEmailsBtn");
if (exportCompanyDocEmailsBtn) {
  exportCompanyDocEmailsBtn.addEventListener("click", async () => {
    if (!token) {
      handleExpiredControlSession();
      return;
    }
    try {
      const response = await fetch(`${API_BASE}/api/companies/document-emails/export`, {
        method: "GET",
        headers: { Authorization: `Bearer ${token}` },
        credentials: "include",
      });
      if (!response.ok) {
        let payload = {};
        try {
          payload = await response.json();
        } catch {
          payload = {};
        }
        throw new Error(payload?.error || `http_${response.status}`);
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `company-document-emails-${new Date().toISOString().slice(0, 10)}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      window.alert(uiT("alertExportFailed").replace("{error}", error.message));
    }
  });
}

const collectionsFilter = document.querySelector("#collectionsFilter");
if (collectionsFilter) {
  collectionsFilter.addEventListener("change", () => renderCollectionsList());
}

const printDailyReportButton = document.querySelector("#printDailyReportButton");
if (printDailyReportButton) {
  printDailyReportButton.addEventListener("click", printDailyReport);
}

const printVisitorWeeklyReportButton = document.querySelector("#printVisitorWeeklyReportButton");
if (printVisitorWeeklyReportButton) {
  printVisitorWeeklyReportButton.addEventListener("click", printVisitorWeeklyReport);
}

const refreshSystemStatusButton = document.querySelector("#refreshSystemStatusButton");
if (refreshSystemStatusButton) {
  refreshSystemStatusButton.addEventListener("click", refreshSystemStatus);
}

const repairSystemButton = document.querySelector("#repairSystemButton");
if (repairSystemButton) {
  repairSystemButton.addEventListener("click", handleSystemRepair);
}

if (elements.dayCloseAcknowledgeForm) {
  elements.dayCloseAcknowledgeForm.addEventListener("submit", handleDayCloseAcknowledge);
}

const settingsForm = document.querySelector("#settingsForm");
if (settingsForm) {
  settingsForm.addEventListener("submit", handleSettingsSubmit);
}

const companyForm = document.querySelector("#companyForm");
if (companyForm) {
  companyForm.addEventListener("submit", handleCompanySubmit);

  const companyNameInput = document.querySelector("#companyName");
  const companyDocumentEmailInput = document.querySelector("#companyDocumentEmail");
  if (companyNameInput && companyDocumentEmailInput) {
    let lastSuggestedValue = "";
    companyNameInput.addEventListener("input", () => {
      const nextSuggestion = suggestCompanyDocumentEmail(companyNameInput.value);
      const currentValue = companyDocumentEmailInput.value.trim();
      if (!currentValue || currentValue === lastSuggestedValue) {
        companyDocumentEmailInput.value = nextSuggestion;
        lastSuggestedValue = nextSuggestion;
      }
    });
  }
}

if (elements.desktopInstallButton) {
  elements.desktopInstallButton.addEventListener("click", () => {
    triggerDesktopInstall().catch(() => {
      window.alert(uiT("alertDesktopInstallFailed"));
    });
  });
}

const passwordForm = document.querySelector("#passwordForm");
if (passwordForm) {
  passwordForm.addEventListener("submit", handlePasswordChange);
}

const invoiceForm = document.querySelector("#invoiceForm");
if (invoiceForm) {
  invoiceForm.addEventListener("submit", handleInvoicePrint);
}

const invoiceSendButton = document.querySelector("#invoiceSendButton");
if (invoiceSendButton) {
  invoiceSendButton.addEventListener("click", handleInvoiceSend);
}

const invoicePreviewButton = document.querySelector("#invoicePreviewButton");
if (invoicePreviewButton) {
  invoicePreviewButton.addEventListener("click", () => refreshInvoicePreview({ silent: false }));
}

const invoiceCompanySelect = document.querySelector("#invoiceCompanySelect");
if (invoiceCompanySelect) {
  invoiceCompanySelect.addEventListener("change", () => {
    syncInvoiceRecipientFromCompany();
    refreshInvoicePreview({ silent: true });
  });
}

// ── Auto-fill invoice number ──────────────────────────────────────────────
const invoiceNumberAutoBtn = document.querySelector("#invoiceNumberAutoBtn");
if (invoiceNumberAutoBtn) {
  invoiceNumberAutoBtn.addEventListener("click", async () => {
    try {
      const data = await apiRequest(API_BASE + "/api/invoices/next-number");
      const field = document.querySelector("#invoiceNumber");
      if (field) field.value = data.nextNumber || "";
    } catch (e) {
      window.alert("Konnte nächste Rechnungsnummer nicht laden: " + e.message);
    }
  });
}

// ── Dynamic invoice positions ─────────────────────────────────────────────
function createPositionRow(pos = {}) {
  const row = document.createElement("div");
  row.className = "invoice-position-row";
  row.style.cssText = "display:grid;grid-template-columns:1fr 70px 90px 90px 34px;gap:4px;margin-bottom:4px;align-items:center;";
  const desc = pos.description || "";
  const qty = pos.qty != null ? pos.qty : 1;
  const unit = pos.unit || "Pauschal";
  const unitPrice = pos.unitPrice != null ? pos.unitPrice : 0;
  row.innerHTML = `
    <input type="text" class="pos-desc" placeholder="Beschreibung" value="${escapeAttr(desc)}" style="padding:5px 7px;border:1px solid #cbd5e0;border-radius:4px;font-size:13px;" required />
    <input type="number" class="pos-qty" placeholder="Menge" value="${qty}" min="0" step="any" style="padding:5px 7px;border:1px solid #cbd5e0;border-radius:4px;font-size:13px;text-align:right;" />
    <select class="pos-unit" style="padding:5px 4px;border:1px solid #cbd5e0;border-radius:4px;font-size:13px;">
      <option${unit==="Pauschal"?" selected":""}>Pauschal</option>
      <option${unit==="Stunden"?" selected":""}>Stunden</option>
      <option${unit==="Stück"?" selected":""}>Stück</option>
      <option${unit==="Monat"?" selected":""}>Monat</option>
      <option${unit==="Tag"?" selected":""}>Tag</option>
    </select>
    <input type="number" class="pos-unit-price" placeholder="Einzelpreis" value="${unitPrice}" min="0" step="0.01" style="padding:5px 7px;border:1px solid #cbd5e0;border-radius:4px;font-size:13px;text-align:right;" />
    <button type="button" class="remove-pos-btn" style="background:none;border:none;cursor:pointer;color:#e53e3e;font-size:18px;line-height:1;padding:2px;">×</button>
  `;
  row.querySelector(".remove-pos-btn").addEventListener("click", () => {
    row.remove();
    updatePositionNetTotal();
  });
  ["pos-qty", "pos-unit-price"].forEach((cls) => {
    row.querySelector("." + cls).addEventListener("input", updatePositionNetTotal);
  });
  return row;
}

function escapeAttr(str) {
  return String(str || "").replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

function updatePositionNetTotal() {
  const rows = document.querySelectorAll("#invoicePositionRows .invoice-position-row");
  let total = 0;
  rows.forEach((r) => {
    const qty = parseFloat(r.querySelector(".pos-qty")?.value || "1") || 0;
    const price = parseFloat(r.querySelector(".pos-unit-price")?.value || "0") || 0;
    total += qty * price;
  });
  total = Math.round(total * 100) / 100;
  const el = document.querySelector("#invoicePositionNetTotal");
  if (el) el.textContent = total.toLocaleString("de-DE", {minimumFractionDigits: 2}) + " EUR";
  refreshInvoicePreview({ silent: true });
}

function getInvoicePositions() {
  const rows = document.querySelectorAll("#invoicePositionRows .invoice-position-row");
  if (!rows.length) return [];
  return Array.from(rows).map((r) => {
    const qty = parseFloat(r.querySelector(".pos-qty")?.value || "1") || 1;
    const unitPrice = parseFloat(r.querySelector(".pos-unit-price")?.value || "0") || 0;
    return {
      description: (r.querySelector(".pos-desc")?.value || "").trim(),
      qty,
      unit: r.querySelector(".pos-unit")?.value || "Pauschal",
      unitPrice,
      total: Math.round(qty * unitPrice * 100) / 100,
    };
  });
}

function initInvoicePositions() {
  const container = document.querySelector("#invoicePositionRows");
  const addBtn = document.querySelector("#addInvoicePositionBtn");
  if (!container || !addBtn) return;
  if (!container.children.length) {
    container.appendChild(createPositionRow({ description: "", qty: 1, unit: "Pauschal", unitPrice: 0 }));
  }
  addBtn.addEventListener("click", () => {
    container.appendChild(createPositionRow());
    updatePositionNetTotal();
  });
  const discountToggle = document.querySelector("#invoiceDiscountToggle");
  const discountRow = document.querySelector("#invoiceDiscountRow");
  if (discountToggle && discountRow) {
    discountToggle.addEventListener("change", () => {
      discountRow.style.display = discountToggle.checked ? "block" : "none";
    });
    const discountInput = document.querySelector("#invoiceDiscountAmount");
    if (discountInput) discountInput.addEventListener("input", updatePositionNetTotal);
  }
}
initInvoicePositions();

// ── CSV Worker Import ─────────────────────────────────────────────────────
const workerCsvImportButton = document.querySelector("#workerCsvImportButton");
const workerCsvImportInput = document.querySelector("#workerCsvImportInput");
if (workerCsvImportButton && workerCsvImportInput) {
  workerCsvImportButton.addEventListener("click", () => workerCsvImportInput.click());
  workerCsvImportInput.addEventListener("change", async () => {
    const file = workerCsvImportInput.files?.[0];
    if (!file) return;
    const resultEl = document.querySelector("#workerCsvImportResult");
    if (resultEl) { resultEl.style.display = "block"; resultEl.textContent = "Importiere…"; resultEl.style.background = "#ebf4ff"; }
    try {
      const formData = new FormData();
      formData.append("file", file);
      const resp = await fetch(API_BASE + "/api/workers/import-csv", {
        method: "POST",
        credentials: "include",
        body: formData,
      });
      if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.message || resp.statusText); }
      const data = await resp.json();
      if (resultEl) {
        resultEl.style.background = data.errors === 0 ? "#f0fff4" : "#fffbeb";
        resultEl.innerHTML = `<strong>Import abgeschlossen:</strong> ${data.created} erstellt, ${data.skipped} übersprungen, ${data.errors} Fehler.` +
          (data.details?.errors?.length ? `<br><small style="color:#c05621">${data.details.errors.map(e => `Zeile ${e.row}: ${e.reason}`).join("; ")}</small>` : "");
      }
      workerCsvImportInput.value = "";
      refreshAll();
    } catch (err) {
      if (resultEl) { resultEl.style.background = "#fff5f5"; resultEl.textContent = "Fehler: " + err.message; }
    }
  });
}

["#invoiceNumber", "#invoiceRecipientEmail", "#invoiceDate", "#invoiceDueDate", "#invoicePeriod", "#invoiceDescription", "#invoiceNetAmount", "#invoiceVatRate"].forEach((selector) => {
  const field = document.querySelector(selector);
  if (field) {
    field.addEventListener("input", () => refreshInvoicePreview({ silent: true }));
  }
});

const invoiceLogoFile = document.querySelector("#invoiceLogoFile");
if (invoiceLogoFile) {
  invoiceLogoFile.addEventListener("change", handleInvoiceLogoUpload);
}

const loadCustomBrandButton = document.querySelector("#loadCustomBrandButton");
if (loadCustomBrandButton) {
  loadCustomBrandButton.addEventListener("click", loadCustomBrandingPreset);
}

const loadCustomBrandAltButton = document.querySelector("#loadCustomBrandAltButton");
if (loadCustomBrandAltButton) {
  loadCustomBrandAltButton.addEventListener("click", loadCustomBrandingPresetAlt);
}

const startCameraButton = document.querySelector("#startCameraButton");
if (startCameraButton) {
  startCameraButton.addEventListener("click", startCamera);
}

const capturePhotoButton = document.querySelector("#capturePhotoButton");
if (capturePhotoButton) {
  capturePhotoButton.addEventListener("click", capturePhoto);
}

const uploadPhotoButton = document.querySelector("#uploadPhotoButton");
if (uploadPhotoButton) {
  uploadPhotoButton.addEventListener("click", openPhotoFilePicker);
}

if (elements.photoFileInput) {
  elements.photoFileInput.addEventListener("change", handlePhotoFileSelected);
}

if (elements.photoZoom) {
  elements.photoZoom.addEventListener("input", handlePhotoZoomInput);
}

if (elements.photoSharpen) {
  elements.photoSharpen.addEventListener("input", handlePhotoSharpenInput);
}

if (elements.photoResetButton) {
  elements.photoResetButton.addEventListener("click", resetCapturedPhotoPosition);
}

const companySelect = document.querySelector("#companySelect");
if (companySelect) {
  companySelect.addEventListener("change", populateSubcompanySelects);
}

const addSubcompanyButton = document.querySelector("#addSubcompanyButton");
if (addSubcompanyButton) {
  addSubcompanyButton.addEventListener("click", async () => {
    const companyId = document.querySelector("#companySelect")?.value || "";
    const name = (document.querySelector("#subcompanyName")?.value || "").trim();
    if (!companyId || !name) {
      window.alert(runtimeText("subcompanyNameRequired"));
      return;
    }
    try {
      await apiRequest(`${API_BASE}/api/subcompanies`, { method: "POST", body: { companyId, name } });
      const input = document.querySelector("#subcompanyName");
      if (input) input.value = "";
      await loadAllData();
      populateSubcompanySelects();
      refreshAll();
    } catch (error) {
      if (error.message === "session_expired") {
        return;
      }
      window.alert(uiT("alertSubcompanyCreateFailed").replace("{error}", error.message));
    }
  });
}

registerControlServiceWorker();
initUiLanguageControl();
initNativeDesktopShell();
wireDesktopInstallPrompt();

(function initWorkerListControls() {
  // ── Search ──
  if (elements.workerSearchInput) {
    elements.workerSearchInput.addEventListener("input", () => renderWorkerList());
  }

  // ── Bulk select all ──
  if (elements.bulkSelectAll) {
    elements.bulkSelectAll.addEventListener("change", () => {
      const checked = elements.bulkSelectAll.checked;
      elements.workerList?.querySelectorAll(".bulk-checkbox").forEach((cb) => { cb.checked = checked; });
      updateBulkActionBar();
    });
  }

  // ── Bulk action buttons ──
  if (elements.bulkCancelButton) {
    elements.bulkCancelButton.addEventListener("click", () => {
      elements.workerList?.querySelectorAll(".bulk-checkbox").forEach((cb) => { cb.checked = false; });
      if (elements.bulkSelectAll) elements.bulkSelectAll.checked = false;
      updateBulkActionBar();
    });
  }

  if (elements.bulkDeleteButton) {
    elements.bulkDeleteButton.addEventListener("click", async () => {
      const ids = getSelectedWorkerIds();
      if (!ids.length) return;
      if (!window.confirm(uiT("confirmDeleteWorkerBulk").replace("{count}", ids.length))) return;
      try {
        await Promise.all(ids.map((id) => apiRequest(`${API_BASE}/api/workers/${id}`, { method: "DELETE" })));
        await loadAllData();
        if (elements.bulkSelectAll) elements.bulkSelectAll.checked = false;
        refreshAll();
      } catch (error) {
        window.alert(uiT("alertDeleteFailed").replace("{error}", error.message));
      }
    });
  }

  if (elements.bulkSetActiveButton) {
    elements.bulkSetActiveButton.addEventListener("click", () => bulkSetStatus("aktiv"));
  }
  if (elements.bulkSetInactiveButton) {
    elements.bulkSetInactiveButton.addEventListener("click", () => bulkSetStatus("inaktiv"));
  }
})();

// Robuster Fallback: delegierte Handler fuer Dokument-Aktionen.
// So funktionieren die Buttons auch dann, wenn ein direkter Listener nicht gebunden wurde.
(function wireDocumentActionFallbacks() {
  if (window.__baupassDocActionFallbackBound) {
    return;
  }
  window.__baupassDocActionFallbackBound = true;

  document.addEventListener("click", (event) => {
    const actionEl = event.target.closest("#docInboxRefreshBtn, #docInboxSyncBtn, .nav-link[data-view='documents']");
    if (!actionEl) {
      return;
    }

    const ensureSession = () => {
      if (!token) {
        handleExpiredControlSession();
        return false;
      }
      return true;
    };

    if (actionEl.matches(".nav-link[data-view='documents']")) {
      if (!ensureSession()) {
        return;
      }
      // setView laeuft ueber den normalen Nav-Handler; danach Inbox nachladen.
      window.setTimeout(() => {
        loadDocumentInbox().catch((e) => {
          window.alert(e.message);
        });
      }, 0);
      return;
    }

    if (actionEl.id === "docInboxRefreshBtn") {
      event.preventDefault();
      if (!ensureSession()) {
        return;
      }
      loadDocumentInbox().catch((e) => {
        window.alert(e.message);
      });
      return;
    }

    if (actionEl.id === "docInboxSyncBtn") {
      event.preventDefault();
      if (!ensureSession()) {
        return;
      }
      (async () => {
        actionEl.disabled = true;
        try {
          await apiRequest(API_BASE + "/api/documents/imap/trigger", { method: "POST" });
          await loadDocumentInbox();
        } catch (e) {
          window.alert(e.message);
        } finally {
          actionEl.disabled = false;
        }
      })();
      return;
    }
  });
})();

function getSelectedWorkerIds() {
  return [...(elements.workerList?.querySelectorAll(".bulk-checkbox:checked") || [])].map((cb) => cb.dataset.bulkId);
}

function updateBulkActionBar() {
  const count = getSelectedWorkerIds().length;
  if (elements.bulkActionBar) elements.bulkActionBar.classList.toggle("hidden", count === 0);
  if (elements.bulkSelectionCount) {
    elements.bulkSelectionCount.textContent = runtimeTextTemplate("bulkSelectedCount", { count });
  }
}

async function bulkSetStatus(status) {
  const ids = getSelectedWorkerIds();
  if (!ids.length) return;
  try {
    await Promise.all(ids.map((id) => {
      const worker = state.workers.find((w) => w.id === id);
      if (!worker) return Promise.resolve();
      return apiRequest(`${API_BASE}/api/workers/${id}`, {
        method: "PUT",
        body: { ...worker, status, companyId: worker.companyId }
      });
    }));
    await loadAllData();
    if (elements.bulkSelectAll) elements.bulkSelectAll.checked = false;
    refreshAll();
  } catch (error) {
    window.alert(uiT("alertStatusChangeFailed").replace("{error}", error.message));
  }
}

(async () => {
  initSystemThemeControl();
  setView("dashboard");
  
  // Try to restore session from storage before showing UI
  try {
    console.log("[App Init] Starting bootstrap with token:", token ? "present" : "missing");
    await loadAllData();
    console.log("[App Init] Bootstrap complete. CurrentUser:", state.currentUser?.username || "none");
    
    if (token && state.currentUser) {
      console.log("[App Init] Session restored successfully");
      startHeartbeat();
      startBackendStatusMonitor();
      setView(getDefaultViewForRole(state.currentUser.role));
    } else {
      console.log("[App Init] No session after bootstrap");
    }
  } catch (error) {
    if (error.message !== "session_expired" && error.message !== "backend_unreachable") {
      console.warn("Initial session bootstrap failed:", error);
    }
    clearSession();
  }

  // Show appropriate UI after session is loaded
  refreshAll();
})();

// ─────────────────────────────────────────────────────────────────────
// Dokument-Inbox (IMAP) & Worker-Dokumente
// ─────────────────────────────────────────────────────────────────────

// Dokumenttypen für die Auswahlfelder
const DOC_TYPES = [
  { value: "mindestlohnnachweis", key: "docTypeMindestlohnnachweis" },
  { value: "personalausweis", key: "docTypePersonalausweis" },
  { value: "sozialversicherungsnachweis", key: "docTypeSozialversicherungsnachweis" },
  { value: "arbeitserlaubnis", key: "docTypeArbeitserlaubnis" },
  { value: "gesundheitszeugnis", key: "docTypeGesundheitszeugnis" },
  { value: "sonstiges", key: "docTypeSonstiges" },
];

function docTypeLabelForValue(value) {
  const found = DOC_TYPES.find((d) => d.value === value);
  return found ? uiT(found.key) : value;
}

async function loadDocumentInbox() {
  const listEl = document.querySelector("#docInboxList");
  if (!listEl) return;
  const rematchBtn = document.querySelector("#docInboxRematchBtn");
  if (rematchBtn) {
    rematchBtn.style.display = String(getCurrentUser()?.role || "").toLowerCase() === "superadmin" ? "" : "none";
  }
  try {
    const data = await apiRequest(API_BASE + "/api/documents/inbox");
    renderDocumentInbox(Array.isArray(data) ? data : (data.emails || []));
  } catch (e) {
    if (listEl) listEl.innerHTML = `<div class="empty-state">${escapeHtml(e.message)}</div>`;
  }
}

function renderDocumentInbox(emails) {
  const listEl = document.querySelector("#docInboxList");
  if (!listEl) return;
  const isSuperadmin = String(getCurrentUser()?.role || "").toLowerCase() === "superadmin";
  if (!emails.length) {
    listEl.innerHTML = `<div class="empty-state">${escapeHtml(uiT("docInboxEmpty"))}</div>`;
    return;
  }
  const statusChip = (email) => {
    const attachments = Array.isArray(email.attachments) ? email.attachments : [];
    const assignedCount = attachments.filter((att) => att.assigned_worker_id).length;
    if (!email.matched_company_id) {
      return '<span style="display:inline-block; padding:2px 8px; border-radius:999px; background:#ffe8e8; color:#9f1d1d; font-size:0.75em; font-weight:700;">Nicht erkannt</span>';
    }
    if (!attachments.length || assignedCount === 0) {
      return '<span style="display:inline-block; padding:2px 8px; border-radius:999px; background:#fff3d1; color:#8a5b00; font-size:0.75em; font-weight:700;">Neu</span>';
    }
    if (assignedCount < attachments.length) {
      return '<span style="display:inline-block; padding:2px 8px; border-radius:999px; background:#e7f0ff; color:#114b9f; font-size:0.75em; font-weight:700;">Teilweise</span>';
    }
    return '<span style="display:inline-block; padding:2px 8px; border-radius:999px; background:#e7ffe9; color:#1f7a35; font-size:0.75em; font-weight:700;">Zugeordnet</span>';
  };

  const renderEmailCard = (email) => {
    const previewText = String(email.body_text || "").trim();
    const previewShort = previewText.length > 220 ? `${previewText.slice(0, 220)}…` : previewText;
    const recipientLine = String(email.to_addr || "").trim();
    const matchedCompanyName = String(email.matched_company_name || "").trim();
    const attachments = (email.attachments || []).map((att) => `
      <span class="attachment-chip">
        📎 ${escapeHtml(att.filename)}
        <button class="link-button" data-inbox-id="${escapeHtml(String(email.id))}" data-attachment-id="${escapeHtml(String(att.id))}" data-filename="${escapeHtml(att.filename)}" data-matched-company-id="${escapeHtml(String(email.matched_company_id || ""))}" data-assign-btn>
          ${escapeHtml(uiT("btnAssignDoc"))}
        </button>
      </span>`).join("");
    return `
      <div class="list-item" data-email-id="${escapeHtml(String(email.id))}">
        <div class="list-item-meta">
          <strong>${escapeHtml(email.from_addr || "-")}</strong> ${statusChip(email)}
          <span class="muted">${escapeHtml(email.received_at ? formatTimestamp(email.received_at) : "")}</span>
        </div>
        ${recipientLine ? `<div class="muted" style="margin-top:4px; font-size:0.85em;"><strong>An:</strong> ${escapeHtml(recipientLine)}</div>` : ""}
        ${matchedCompanyName ? `<div class="muted" style="margin-top:2px; font-size:0.85em;"><strong>Firma:</strong> ${escapeHtml(matchedCompanyName)}</div>` : ""}
        <div class="list-item-subject">${escapeHtml(email.subject || "(kein Betreff)")}</div>
        ${previewShort ? `
          <div class="muted" style="margin-top:6px; font-size:0.9em; white-space:pre-wrap;">${escapeHtml(previewShort)}</div>
          <button class="link-button" type="button" data-toggle-mail-details="${escapeHtml(String(email.id))}" style="margin-top:4px;">
            ${escapeHtml("Details")}
          </button>
          <div class="muted" data-mail-details="${escapeHtml(String(email.id))}" style="display:none; margin-top:6px; white-space:pre-wrap; line-height:1.4; border-left:3px solid var(--color-border, #ddd); padding-left:10px;">
            ${escapeHtml(previewText)}
          </div>
        ` : ""}
        ${isSuperadmin && !email.matched_company_id ? `
          <div class="button-row" style="margin-top:6px;">
            <button class="ghost-button small-button" data-manual-company-match="${escapeHtml(String(email.id))}">Firma manuell zuweisen</button>
          </div>
        ` : ""}
        ${attachments ? `<div class="attachment-list">${attachments}</div>` : ""}
        <div class="button-row" style="margin-top:8px">
          <button class="ghost-button small-button" data-dismiss-email-id="${escapeHtml(String(email.id))}">
            ${escapeHtml(uiT("btnDismissEmail"))}
          </button>
        </div>
      </div>`;
  };

  const recognized = emails.filter((entry) => Boolean(entry.matched_company_id));
  const unrecognized = emails.filter((entry) => !entry.matched_company_id);

  listEl.innerHTML = `
    <div class="meta-box" style="margin-bottom:8px;">
      <p style="margin:0;"><strong>Erkannt:</strong> ${recognized.length} | <strong>Prüfkorb:</strong> ${unrecognized.length}</p>
    </div>
    ${recognized.length ? recognized.map(renderEmailCard).join("") : '<div class="empty-state">Keine erkannten Mails.</div>'}
    <div class="meta-box" style="margin-top:12px;">
      <p style="margin:0;"><strong>Prüfkorb</strong> (Empfängeradresse konnte keiner Firma zugeordnet werden)</p>
    </div>
    ${unrecognized.length ? unrecognized.map(renderEmailCard).join("") : '<div class="empty-state">Keine ungeklärten Mails.</div>'}
  `;

  // Assign-Buttons
  listEl.querySelectorAll("[data-assign-btn]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (isSupportReadOnlyMode()) {
        showSupportReadOnlyAlert();
        return;
      }
      openDocAssignPanel(btn.dataset.inboxId, btn.dataset.attachmentId, btn.dataset.filename, btn.dataset.matchedCompanyId || "");
    });
  });

  // Dismiss-Buttons
  listEl.querySelectorAll("[data-dismiss-email-id]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (isSupportReadOnlyMode()) {
        showSupportReadOnlyAlert();
        return;
      }
      const emailId = btn.dataset.dismissEmailId;
      try {
        await apiRequest(API_BASE + `/api/documents/inbox/${emailId}/dismiss`, { method: "POST" });
        loadDocumentInbox();
      } catch (e) {
        window.alert(e.message);
      }
    });
  });

  // Manueller Firmen-Match für Prüfkorb
  listEl.querySelectorAll("[data-manual-company-match]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (isSupportReadOnlyMode()) {
        showSupportReadOnlyAlert();
        return;
      }
      const inboxId = btn.dataset.manualCompanyMatch;
      if (!inboxId) return;
      openManualCompanyMatchPanel(inboxId);
    });
  });

  // Mail-Details ein-/ausblenden
  listEl.querySelectorAll("[data-toggle-mail-details]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const emailId = btn.dataset.toggleMailDetails;
      const detailsEl = listEl.querySelector(`[data-mail-details="${CSS.escape(emailId || "")}"]`);
      if (!detailsEl) return;
      const isHidden = detailsEl.style.display === "none" || !detailsEl.style.display;
      detailsEl.style.display = isHidden ? "" : "none";
      btn.textContent = isHidden ? "Weniger" : "Details";
    });
  });

  applySupportReadOnlyUiState();
}

function openDocAssignPanel(inboxId, attachmentId, filename, matchedCompanyId = "") {
  if (isSupportReadOnlyMode()) {
    showSupportReadOnlyAlert();
    return;
  }
  const panel = document.querySelector("#docAssignPanel");
  const content = document.querySelector("#docAssignContent");
  if (!panel || !content) return;
  panel.style.display = "";

  // Mitarbeiter-Liste aus state.workers (aktive Nicht-Besucher)
  const workers = (state.workers || []).filter((w) => {
    if (isVisitorWorker(w) || w.status === "inaktiv") {
      return false;
    }
    if (matchedCompanyId && String(w.companyId || w.company_id || "") !== String(matchedCompanyId)) {
      return false;
    }
    return true;
  });
  const workerOptions = workers.map((w) =>
    `<option value="${escapeHtml(String(w.id))}">${escapeHtml(w.firstName + " " + w.lastName)} — ${escapeHtml(w.badgeId)}</option>`
  ).join("");

  const docTypeOptions = DOC_TYPES.map((d) =>
    `<option value="${escapeHtml(d.value)}">${escapeHtml(uiT(d.key))}</option>`
  ).join("");

  content.innerHTML = `
    <form id="docAssignForm" class="settings-form">
      <p class="muted">📎 ${escapeHtml(filename)}</p>
      ${matchedCompanyId ? `<p class="muted">Vorauswahl auf erkannte Firma eingeschränkt.</p>` : ""}
      <label>
        <span>${escapeHtml(uiT("docAssignWorkerLabel"))}</span>
        <select id="docAssignWorkerId" required>
          <option value="">— bitte wählen —</option>
          ${workerOptions}
        </select>
      </label>
      <label>
        <span>${escapeHtml(uiT("docAssignTypeLabel"))}</span>
        <select id="docAssignType" required>
          ${docTypeOptions}
        </select>
      </label>
      <label>
        <span>${escapeHtml(uiT("docAssignNotesLabel"))}</span>
        <input id="docAssignNotes" type="text" />
      </label>
      <div class="button-row">
        <button type="submit" class="primary-button">${escapeHtml(uiT("btnConfirmAssign"))}</button>
        <button type="button" class="ghost-button" id="docAssignCancelBtn">Abbrechen</button>
      </div>
      <p id="docAssignMsg" class="helper-text"></p>
    </form>`;

  document.querySelector("#docAssignCancelBtn").addEventListener("click", () => {
    panel.style.display = "none";
  });

  document.querySelector("#docAssignForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (isSupportReadOnlyMode()) {
      showSupportReadOnlyAlert();
      return;
    }
    const workerId = document.querySelector("#docAssignWorkerId").value;
    const docType = document.querySelector("#docAssignType").value;
    const notes = document.querySelector("#docAssignNotes").value.trim();
    const msgEl = document.querySelector("#docAssignMsg");
    if (!workerId) return;
    try {
      await apiRequest(API_BASE + `/api/documents/inbox/${inboxId}/attachments/${attachmentId}/assign`, {
        method: "POST",
        body: { workerId: Number(workerId), docType, notes },
      });
      msgEl.textContent = uiT("docAssignSuccess");
      msgEl.style.color = "var(--color-success, green)";
      panel.style.display = "none";
      loadDocumentInbox();
    } catch (err) {
      msgEl.textContent = err.message;
      msgEl.style.color = "var(--color-danger, red)";
    }
  });
}

function openManualCompanyMatchPanel(inboxId) {
  if (isSupportReadOnlyMode()) {
    showSupportReadOnlyAlert();
    return;
  }
  const panel = document.querySelector("#docAssignPanel");
  const content = document.querySelector("#docAssignContent");
  if (!panel || !content) return;
  panel.style.display = "";

  const closePanel = () => {
    panel.style.display = "none";
  };

  const activeCompanies = (state.companies || [])
    .filter((company) => !company.deleted_at)
    .sort((a, b) => String(a.name || "").localeCompare(String(b.name || ""), "de"));

  if (!activeCompanies.length) {
    content.innerHTML = `
      <div class="settings-form">
        <p class="helper-text" style="color:var(--color-danger, red);">Keine aktiven Firmen vorhanden.</p>
        <div class="button-row">
          <button type="button" class="ghost-button" id="docAssignCancelBtn">Schließen</button>
        </div>
      </div>`;
    const closeBtn = document.querySelector("#docAssignCancelBtn");
    if (closeBtn) closeBtn.addEventListener("click", closePanel);
    return;
  }

  content.innerHTML = `
    <form id="docCompanyMatchForm" class="settings-form">
      <p class="muted">Mail aus Prüfkorb manuell einer Firma zuordnen.</p>
      <label>
        <span>Firma suchen</span>
        <input id="docCompanyMatchFilter" type="text" placeholder="Name oder Mail eingeben" />
      </label>
      <label>
        <span>Firma</span>
        <select id="docCompanyMatchSelect" required>
          <option value="">— bitte wählen —</option>
        </select>
      </label>
      <div class="button-row">
        <button type="submit" class="primary-button">Zuordnen</button>
        <button type="button" class="ghost-button" id="docAssignCancelBtn">Abbrechen</button>
      </div>
      <p id="docCompanyMatchMsg" class="helper-text"></p>
    </form>`;

  const filterInput = document.querySelector("#docCompanyMatchFilter");
  const selectEl = document.querySelector("#docCompanyMatchSelect");
  const renderCompanyOptions = (filterValue = "") => {
    if (!selectEl) return;
    const prev = String(selectEl.value || "");
    const needle = String(filterValue || "").trim().toLowerCase();
    const options = activeCompanies
      .filter((company) => {
        if (!needle) return true;
        const name = String(company.name || "").toLowerCase();
        const mail = String(getCompanyDocumentEmail(company) || "").toLowerCase();
        return name.includes(needle) || mail.includes(needle);
      })
      .map((company) => `<option value="${escapeHtml(String(company.id))}">${escapeHtml(String(company.name || "Firma"))} (${escapeHtml(getCompanyDocumentEmail(company) || "keine Dokument-Mail")})</option>`)
      .join("");

    selectEl.innerHTML = `<option value="">— bitte wählen —</option>${options}`;
    if (prev && Array.from(selectEl.options).some((opt) => opt.value === prev)) {
      selectEl.value = prev;
    }
  };

  renderCompanyOptions("");
  if (filterInput) {
    filterInput.addEventListener("input", () => {
      renderCompanyOptions(filterInput.value);
    });
  }

  const closeBtn = document.querySelector("#docAssignCancelBtn");
  if (closeBtn) {
    closeBtn.addEventListener("click", closePanel);
  }

  const form = document.querySelector("#docCompanyMatchForm");
  if (!form) return;

  if (filterInput) {
    // UX: sofort Suchfeld fokussieren, damit direkt getippt werden kann.
    window.setTimeout(() => {
      filterInput.focus();
      filterInput.select();
    }, 0);

    filterInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        if (!selectEl) return;
        if (selectEl.value) {
          return;
        }
        const firstRealOption = Array.from(selectEl.options).find((opt) => opt.value);
        if (firstRealOption) {
          selectEl.value = firstRealOption.value;
        }
      }
      if (event.key === "Escape") {
        event.preventDefault();
        closePanel();
      }
    });
  }

  form.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closePanel();
    }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (isSupportReadOnlyMode()) {
      showSupportReadOnlyAlert();
      return;
    }
    const companyId = String(document.querySelector("#docCompanyMatchSelect")?.value || "").trim();
    const msgEl = document.querySelector("#docCompanyMatchMsg");
    if (!companyId) {
      if (msgEl) {
        msgEl.textContent = "Bitte eine Firma wählen.";
        msgEl.style.color = "var(--color-danger, red)";
      }
      return;
    }

    try {
      await apiRequest(`${API_BASE}/api/documents/inbox/${inboxId}/match-company`, {
        method: "POST",
        body: { companyId },
      });
      closePanel();
      await loadDocumentInbox();
    } catch (error) {
      if (msgEl) {
        msgEl.textContent = `Zuordnung fehlgeschlagen: ${error.message}`;
        msgEl.style.color = "var(--color-danger, red)";
      }
    }
  });
}

async function loadWorkerDocuments(workerId) {
  try {
    const data = await apiRequest(API_BASE + `/api/workers/${workerId}/documents`);
    return Array.isArray(data) ? data : (data.documents || []);
  } catch {
    return [];
  }
}

async function uploadWorkerDocument(workerId, file, docType, notes, expiryDate) {
  if (isSupportReadOnlyMode()) {
    throw new Error("support_session_read_only");
  }
  const fd = new FormData();
  fd.append("file", file);
  fd.append("docType", docType);
  fd.append("notes", notes);
  if (expiryDate) {
    fd.append("expiryDate", expiryDate);
  }
  const response = await fetch(API_BASE + `/api/workers/${workerId}/documents/upload`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: fd
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.error || `http_${response.status}`);
  return payload;
}

function renderWorkerDocuments(docs, workerId, containerEl) {
  if (!containerEl) return;
  const role = String(getCurrentUser()?.role || "").toLowerCase();
  const canDelete = ["superadmin", "company-admin"].includes(role);
  const canUpload = ["superadmin", "company-admin", "turnstile"].includes(role);

  const docTypeOptions = DOC_TYPES.map((d) =>
    `<option value="${escapeHtml(d.value)}">${escapeHtml(uiT(d.key))}</option>`
  ).join("");

  const uploadForm = canUpload ? `
    <details style="margin-top:12px;">
      <summary style="cursor:pointer; font-weight:600; padding:6px 0;">${escapeHtml(uiT("btnUploadWorkerDoc"))}</summary>
      <form class="worker-doc-upload-form" style="margin-top:8px; display:flex; flex-direction:column; gap:8px;">
        <input type="file" class="doc-upload-file" accept=".pdf,.jpg,.jpeg,.png,.gif,.webp,.doc,.docx" required />
        <select class="doc-upload-type" required>${docTypeOptions}</select>
        <input type="text" class="doc-upload-notes" placeholder="${escapeHtml(uiT("docAssignNotesLabel"))}" />
        <label style="display:flex; flex-direction:column; gap:4px;">
          <span class="helper-text">Ablaufdatum (optional)</span>
          <input type="date" class="doc-upload-expiry" />
        </label>
        <div class="button-row">
          <button type="submit" class="primary-button small-button">${escapeHtml(uiT("btnConfirmUpload"))}</button>
        </div>
        <p class="doc-upload-msg helper-text" style="display:none;"></p>
      </form>
    </details>` : "";

  const listHtml = docs.length
    ? `<ul class="document-list">` + docs.map((doc) => `
      <li class="document-list-item">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px;">
          <div>
            <span style="font-weight:600;">📄 ${escapeHtml(docTypeLabelForValue(doc.doc_type))}</span>
            <span class="muted" style="display:block; font-size:0.8em;">${escapeHtml(doc.filename)}</span>
            ${doc.notes ? `<span class="muted" style="display:block; font-size:0.8em;">${escapeHtml(doc.notes)}</span>` : ""}
            ${doc.expiry_date ? `<span class="muted" style="display:block; font-size:0.8em; color:${doc.expiry_date < new Date().toISOString().slice(0, 10) ? "var(--color-danger, #b42318)" : "inherit"};">Ablaufdatum: ${escapeHtml(doc.expiry_date)}</span>` : ""}
            <span class="muted" style="display:block; font-size:0.8em;">${escapeHtml(doc.created_at ? formatTimestamp(doc.created_at) : "")}</span>
          </div>
          <div class="button-row" style="flex-shrink:0;">
            <a class="ghost-button small-button" href="${API_BASE}/api/workers/${workerId}/documents/${doc.id}/download" target="_blank" rel="noopener noreferrer">${escapeHtml(uiT("btnDownloadDoc"))}</a>
            ${canDelete ? `<button class="ghost-button small-button danger" data-delete-doc-id="${escapeHtml(String(doc.id))}">${escapeHtml(uiT("btnDeleteDoc"))}</button>` : ""}
          </div>
        </div>
      </li>`).join("") + `</ul>`
    : `<p class="muted">${escapeHtml(uiT("workerDocsEmpty"))}</p>`;

  containerEl.innerHTML = listHtml + uploadForm;

  containerEl.querySelectorAll("[data-delete-doc-id]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (isSupportReadOnlyMode()) {
        showSupportReadOnlyAlert();
        return;
      }
      if (!window.confirm(uiT("confirmDeleteDoc"))) return;
      try {
        await apiRequest(API_BASE + `/api/workers/${workerId}/documents/${btn.dataset.deleteDocId}`, { method: "DELETE" });
        const updatedDocs = await loadWorkerDocuments(workerId);
        renderWorkerDocuments(updatedDocs, workerId, containerEl);
      } catch (e) {
        window.alert(e.message);
      }
    });
  });

  const uploadFormEl = containerEl.querySelector(".worker-doc-upload-form");
  if (uploadFormEl) {
    uploadFormEl.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (isSupportReadOnlyMode()) {
        showSupportReadOnlyAlert();
        return;
      }
      const fileInput = uploadFormEl.querySelector(".doc-upload-file");
      const typeSelect = uploadFormEl.querySelector(".doc-upload-type");
      const notesInput = uploadFormEl.querySelector(".doc-upload-notes");
      const expiryInput = uploadFormEl.querySelector(".doc-upload-expiry");
      const msgEl = uploadFormEl.querySelector(".doc-upload-msg");
      const submitBtn = uploadFormEl.querySelector("[type='submit']");
      const file = fileInput?.files?.[0];
      if (!file) return;
      submitBtn.disabled = true;
      msgEl.style.display = "none";
      try {
        await uploadWorkerDocument(workerId, file, typeSelect.value, notesInput.value.trim(), expiryInput?.value || "");
        msgEl.textContent = uiT("docUploadSuccess");
        msgEl.style.color = "var(--color-success, green)";
        msgEl.style.display = "";
        uploadFormEl.reset();
        const updatedDocs = await loadWorkerDocuments(workerId);
        renderWorkerDocuments(updatedDocs, workerId, containerEl);
      } catch (err) {
        msgEl.textContent = err.message === "support_session_read_only" ? uiT("supportReadOnlyShort") : err.message;
        msgEl.style.color = "var(--color-danger, red)";
        msgEl.style.display = "";
        submitBtn.disabled = false;
      }
    });
  }

  applySupportReadOnlyUiState();
}

// Dokument-Inbox beim Wechsel zur documents-View laden
// DOM ist bereits bereit wenn app.js am Ende von <body> läuft.
// Führe sofort aus, statt auf DOMContentLoaded zu warten (wird sonst nie gefeuert).
(function initDocumentSection() {
  // Documents Nav-Link
  const docNavLink = document.querySelector("[data-view='documents']");
  if (docNavLink) {
    docNavLink.addEventListener("click", () => {
      if (!token) {
        handleExpiredControlSession();
        return;
      }
      loadDocumentInbox();
    });
  }

  const refreshBtn = document.querySelector("#docInboxRefreshBtn");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      if (!token) {
        handleExpiredControlSession();
        return;
      }
      loadDocumentInbox();
    });
  }

  // Zeige die konfigurierte Dokument-E-Mail-Adresse für den Pförtner
  function updateDocEmailInfoBar() {
    const bar = document.querySelector("#docEmailInfoBar");
    const addrEl = document.querySelector("#docEmailInfoAddr");
    const copyBtn = document.querySelector("#docEmailCopyBtn");
    if (!bar || !addrEl) return;
    const currentUser = getCurrentUser();
    const role = String(currentUser?.role || "").toLowerCase();
    const currentCompanyId = currentUser?.company_id || currentUser?.companyId || "";
    const currentCompany = (state.companies || []).find((company) => company.id === currentCompanyId);
    const companyEmail = getCompanyDocumentEmail(currentCompany);
    const globalEmail = (state.settings?.imapUsername || "").trim();
    const email = companyEmail || (role === "superadmin" ? globalEmail : "");
    if (email) {
      addrEl.textContent = email;
      bar.style.display = "";
    } else {
      bar.style.display = "none";
    }
    if (copyBtn) {
      copyBtn.onclick = async () => {
        try {
          if (navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(email);
          } else {
            window.prompt(uiT("docEmailInfoLabel"), email);
          }
          const orig = copyBtn.textContent;
          copyBtn.textContent = uiT("btnCopyEmailDone");
          window.setTimeout(() => { copyBtn.textContent = orig; }, 1800);
        } catch {
          window.prompt(uiT("docEmailInfoLabel"), email);
        }
      };
    }
  }

  updateDocEmailInfoBar();
  // Auch aktualisieren wenn Einstellungen neu geladen werden
  document.addEventListener("baupass:settingsLoaded", updateDocEmailInfoBar);

  const runDocumentInboxSync = async (buttonEl) => {
    if (isSupportReadOnlyMode()) {
      showSupportReadOnlyAlert();
      return;
    }
    if (buttonEl) buttonEl.disabled = true;
    try {
      await apiRequest(API_BASE + "/api/documents/imap/trigger", { method: "POST" });
      await loadDocumentInbox();
    } catch (e) {
      window.alert(e.message);
    } finally {
      if (buttonEl) buttonEl.disabled = false;
    }
  };

  const syncBtn = document.querySelector("#docInboxSyncBtn");
  if (syncBtn) {
    syncBtn.addEventListener("click", async () => {
      if (!token) {
        handleExpiredControlSession();
        return;
      }
      await runDocumentInboxSync(syncBtn);
    });
  }

  const rematchBtn = document.querySelector("#docInboxRematchBtn");
  if (rematchBtn) {
    rematchBtn.style.display = String(getCurrentUser()?.role || "").toLowerCase() === "superadmin" ? "" : "none";
    rematchBtn.addEventListener("click", async () => {
      if (isSupportReadOnlyMode()) {
        showSupportReadOnlyAlert();
        return;
      }
      if (!token) {
        handleExpiredControlSession();
        return;
      }
      rematchBtn.disabled = true;
      try {
        const res = await apiRequest(API_BASE + "/api/documents/inbox/rematch-company-links", { method: "POST", body: {} });
        await loadDocumentInbox();
        window.alert(uiT("alertReassignmentDone").replace("{count}", Number(res?.matchedCount || 0)));
      } catch (error) {
        window.alert(uiT("alertReassignmentFailed").replace("{error}", error.message));
      } finally {
        rematchBtn.disabled = false;
      }
    });
  }

  // IMAP-Test-Button
  const imapTestBtn = document.querySelector("#imapTestBtn");
  if (imapTestBtn) {
    imapTestBtn.addEventListener("click", async () => {
      if (isSupportReadOnlyMode()) {
        showSupportReadOnlyAlert();
        return;
      }
      const resultEl = document.querySelector("#imapTestResult");
      const imapHost = (document.querySelector("#imapHost")?.value || "").trim();
      const imapUsername = (document.querySelector("#imapUsername")?.value || "").trim();
      const imapPassword = document.querySelector("#imapPassword")?.value || "";
      if (!imapHost || !imapUsername || !imapPassword) {
        if (resultEl) {
          resultEl.textContent = "Bitte IMAP Host, Benutzername und Passwort ausfüllen und speichern.";
          resultEl.style.color = "var(--color-danger, red)";
        }
        return;
      }
      imapTestBtn.disabled = true;
      if (resultEl) resultEl.textContent = "…";
      try {
        const res = await apiRequest(API_BASE + "/api/settings/imap/test", {
          method: "POST",
          body: {
            imapHost,
            imapPort: Number(document.querySelector("#imapPort")?.value || 993),
            imapUsername,
            imapPassword,
            imapFolder: (document.querySelector("#imapFolder")?.value || "INBOX").trim() || "INBOX",
            imapUseSsl: document.querySelector("#imapUseSsl")?.value !== "0",
          },
        });
        if (resultEl) {
          resultEl.textContent = uiT("imapTestOk") + (res.message ? ` (${res.message})` : "");
          resultEl.style.color = "var(--color-success, green)";
        }
      } catch (e) {
        if (resultEl) {
          resultEl.textContent = `${uiT("imapTestFail")}: ${e.message}`;
          resultEl.style.color = "var(--color-danger, red)";
        }
      } finally {
        imapTestBtn.disabled = false;
      }
    });
  }

  if (elements.loginResetPasswordButton) {
    elements.loginResetPasswordButton.addEventListener("click", requestPasswordResetFromLogin);
  }

  // ── Impressum / Datenschutz Modal ─────────────────────────────────────────
  const legalModal = document.getElementById("legalModal");
  const legalModalTitle = document.getElementById("legalModalTitle");
  const legalModalBody = document.getElementById("legalModalBody");
  const legalModalClose = document.getElementById("legalModalClose");

  function openLegalModal(title, text) {
    if (!legalModal) return;
    if (legalModalTitle) legalModalTitle.textContent = title;
    if (legalModalBody) legalModalBody.textContent = text || uiT("legalFallbackEmpty");
    legalModal.classList.remove("hidden");
    legalModal.focus?.();
  }

  if (legalModalClose) {
    legalModalClose.addEventListener("click", () => legalModal?.classList.add("hidden"));
  }
  if (legalModal) {
    legalModal.addEventListener("click", (event) => {
      if (event.target === legalModal) legalModal.classList.add("hidden");
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !legalModal.classList.contains("hidden")) {
        legalModal.classList.add("hidden");
      }
    });
  }

  const showImpressumBtn = document.getElementById("showImpressumBtn");
  const showDatenschutzBtn = document.getElementById("showDatenschutzBtn");
  if (showImpressumBtn) {
    showImpressumBtn.addEventListener("click", () => {
      openLegalModal(uiT("legalImpressum"), state.settings?.impressumText || "");
    });
  }
  if (showDatenschutzBtn) {
    showDatenschutzBtn.addEventListener("click", () => {
      openLegalModal(uiT("legalPrivacy"), state.settings?.datenschutzText || "");
    });
  }

  maybeHandlePasswordResetToken();
})();
