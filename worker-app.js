const DEFAULT_RENDER_API_BASE = "https://baupass-backend.onrender.com";
const API_BASE_STORAGE_KEY = "baupass-api-base";
const WORKER_BUILD_TAG = "20260511b";

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

  if (window.location.protocol === "https:" && parsed.protocol === "http:") {
    const host = (parsed.hostname || "").toLowerCase();
    const localHosts = new Set(["localhost", "127.0.0.1", "::1"]);
    if (!localHosts.has(host)) {
      return "";
    }
  }

  return parsed.toString().replace(/\/+$/, "");
}

function resolveWorkerApiBase() {
  const params = new URL(window.location.href).searchParams;
  const queryValue = sanitizeApiBase(params.get("apiBase"));
  const storedValue = sanitizeApiBase(window.localStorage.getItem(API_BASE_STORAGE_KEY));
  const configuredValue = queryValue || storedValue;

  if (configuredValue) {
    window.localStorage.setItem(API_BASE_STORAGE_KEY, configuredValue);
    return `${configuredValue}/api/worker-app`;
  }

  if (!configuredValue && window.localStorage.getItem(API_BASE_STORAGE_KEY)) {
    window.localStorage.removeItem(API_BASE_STORAGE_KEY);
  }

  if (window.location.hostname.endsWith("github.io")) {
    return `${DEFAULT_RENDER_API_BASE}/api/worker-app`;
  }

  return "/api/worker-app";
}

const API_BASE = resolveWorkerApiBase();
const API_ROOT = resolveApiRoot(API_BASE);
const WORKER_TOKEN_KEY = "baupass-worker-token";
const WORKER_ACCESS_TOKEN_KEY = "baupass-worker-access-token";
const WORKER_BADGE_LOGIN_KEY = "baupass-worker-badge-login";
const LOCAL_LAST_PHOTO_KEY = "baupass-last-local-photo";
const OFFLINE_PHOTO_QUEUE_KEY = "baupass-offline-photo-queue";
const OFFLINE_EVENT_QUEUE_KEY = "baupass-offline-event-queue";
const WORKER_OFFLINE_LOGIN_PROFILE_KEY = "baupass-worker-offline-login-profile";
const QR_CACHE_PREFIX = "baupass-worker-qr-cache";
const QR_HIGH_CONTRAST_KEY = "baupass-qr-high-contrast";
const AUTO_OPEN_SCANNER_KEY = "baupass-auto-open-scanner";
const WORKER_SESSION_IP_KEY = "baupass-worker-session-ip";
const WORKER_CACHED_PAYLOAD_KEY = "baupass-worker-cached-payload";
const WORKER_LANG_KEY = "baupass-worker-lang";
const WORKER_INACTIVITY_TIMEOUT_MS = 60 * 1000;
const WORKER_PASS_LOCK_TIMEOUT_MS = 2 * 60 * 1000;
const WORKER_THEME_KEY = "baupass-worker-theme";
const PUSH_SUBSCRIPTIONS_KEY = "baupass-push-subscriptions";

// ── i18n ──────────────────────────────────────────────────────────────
const TRANSLATIONS = {
  de: {
    pageTitle: "Mitarbeiter-App",
    appTitle: "Control Pass Mobile",
    appEyebrow: "Mitarbeiter-App",
    appLead: "Dein Ausweis, dein Arbeitsweg und dein Einlass an einem Ort. Schnell, sauber und direkt auf dem Homescreen.",
    languageLabel: "Sprache",
    installBtn: "App installieren",
    installHint: "Für iPhone und Android optimiert. Installiere die App für schnellen Zugriff am Drehkreuz.",
    online: "Online",
    offline: "Offline",
    loginKicker: "Direkter Einstieg",
    loginTitle: "Digitalen Ausweis aktivieren",
    loginCopy: "Du kannst den Ausweis per Mitarbeiter-Link oder direkt mit deiner Badge-ID von der Karte aktivieren.",
    loginTokenLabel: "Link-Code oder Badge-ID",
    loginTokenPlaceholder: "Token aus Link oder BP-...",
    loginPinLabel: "Badge-PIN",
    loginPinPlaceholder: "4–8 stelliger PIN",
    loginBtn: "Ausweis laden",
    tipBadge: "Badge-ID plus PIN statt QR",
    tipHome: "Funktioniert als Homescreen-App",
    tipRoute: "Direkter Weg zum Standort",
    geolocationHint: "Standort wird für Badge-Login benötigt",
    logoutBtn: "Abmelden",
    refreshBtn: "Aktualisieren",
    fieldBadgeId: "Badge-ID",
    fieldValidUntil: "Gültig bis",
    fieldSite: "Standort",
    workerCardTitle: "Dein Ausweis für heute",
    visitorCardTitle: "Deine digitale Besucherkarte",
    workerPassSubLabel: "Mitarbeiterausweis",
    visitorPassSubLabel: "Besucherkarte",
    offlineBanner: "⚠️ Offline – zeige gespeicherte Daten",
    pinLockTitle: "PIN erforderlich",
    pinLockMessage: "Dieser Ausweis wurde gesperrt. Bitte gib deine Badge-PIN ein um fortzufahren.",
    pinLockBtn: "Ausweis entsperren",
    pinLockLogout: "Abmelden",
    pinLockEyebrow: "🔒 Ausweis gesperrt",
    enterBadgeId: "Bitte Badge-ID eingeben.",
    enterPin: "Bitte Badge-PIN eingeben.",
    loginFailed: "Anmeldung fehlgeschlagen",
    sessionExpired: "Digitale Besucherkarte abgelaufen. Bitte für heute neu anmelden.",
    connError: "Verbindungsfehler",
    lastSync: "Zuletzt synchronisiert",
    splashSub: "Mitarbeiter-App",
    splashLoading: "Laedt",
    routeTodayTitle: "Standort heute",
    cameraRotate: "Drehen",
    cameraDelete: "Löschen",
    cameraTakePhoto: "Foto aufnehmen",
    cameraConfirm: "Übernehmen",
    cameraRetake: "Neu aufnehmen",
    cameraCancel: "Abbrechen",
    gateEyebrow: "Digitale Firmenkarte",
    gateModeActive: "Drehkreuz-Modus aktiv - QR unter Scanner halten",
    gateBrightnessHint: "⚠ Bitte Display-Helligkeit auf Maximum stellen für schnellen Scan.",
    gateQrAlt: "Einlass QR",
    qrContrastOn: "High-Contrast QR: Ein",
    qrContrastOff: "High-Contrast QR: Aus",
    close: "Schliessen",
    workerDefaultName: "Mitarbeiter",
    companyFallback: "Baufirma",
    visitorRole: "Besucher",
    noQrAvailable: "Kein QR verfuegbar. Bitte Admin kontaktieren.",
    badgeUnset: "Badge nicht gesetzt",
    badgeValue: "Badge {value}",
    subcompanyPrefix: "✓ Sub: {name}",
    subcompanyTitle: "Subunternehmer: {name}",
    statusRevoked: "❌ Zugang entzogen",
    statusExpired: "⚠ Ausweis abgelaufen",
    statusActive: "✓ Aktiv und berechtigt",
    installAlreadyInstalled: "App ist bereits installiert.",
    installIosHowto: "iPhone: In Safari auf Teilen tippen und dann 'Zum Home-Bildschirm' wählen.",
    installAndroidChromeOnly: "Bitte in einem modernen Browser öffnen. Die Installation funktioniert über das Browser-Menü.",
    installAndroidHowto: "Android: Im Browser-Menü auf 'App installieren' oder 'Zum Startbildschirm' tippen.",
    installManual: "Installation manuell: Browser-Menü öffnen und 'Zum Startbildschirm' bzw. 'App installieren' wählen.",
    enterAccessCode: "Bitte Zugangscode eingeben.",
    installTip: "Tipp: App jetzt installieren, damit dein Ausweis direkt auf dem Handy verfuegbar ist.",
    visitorExpiredNeedLink: "Besucherkarte ist abgelaufen. Bitte neuen Link anfordern.",
    workerAppDisabled: "Mitarbeiter-App ist derzeit deaktiviert.",
    accessFailed: "Zugang fehlgeschlagen",
    inactiveReLogin: "Zu lange inaktiv. Bitte melde dich neu an.",
    wrongPinRetry: "Falsche PIN. Versuche erneut.",
    pinLockTooManyAttempts: "Zu viele Versuche – bitte warte 5 Minuten.",
    gateReadyScan: "📱 Bereit zum Scannen...",
    gateQrRefreshed: "QR aktualisiert. Bereit zum Scan.",
    gateScanSyncDelayed: "Verbindung langsam. Letzter QR bleibt aktiv.",
    gateScanAccessGrantedIn: "Zugang erkannt: Check-in bestaetigt.",
    gateScanAccessGrantedOut: "Zugang erkannt: Check-out bestaetigt.",
    gateScanAccessGrantedGeneric: "Zugang erkannt und gespeichert.",
    gateScanAccessDenied: "Zugang abgelehnt. Bitte beim Vorarbeiter melden.",
    lowLightDetected: "Dunkle Umgebung erkannt. High-Contrast QR empfohlen.",
    qrLoadFailedAlt: "QR-Code konnte nicht geladen werden",
    installHintStandalone: "App ist installiert. Am Drehkreuz einfach den QR-Code im Vollbild zeigen.",
    installHintIos: "iPhone: Safari > Teilen > Zum Home-Bildschirm. Danach startet die Firmenkarte direkt als App.",
    installHintAndroidChrome: "Android: Menü > App installieren. Danach wie eine normale Handy-App nutzbar.",
    installHintAndroidOther: "Android: Browser-Menü > App installieren oder Zum Startbildschirm hinzufügen.",
    cameraBlocked: "Safari blockiert hier die Browser-Kamera. Bitte Foto direkt aus Kamera oder Mediathek wählen.",
    cameraStartFailed: "Kamera konnte nicht gestartet werden.",
    cameraHttpsHint: "Safari erlaubt die Browser-Kamera meist nur über HTTPS. Bitte Foto direkt aus Kamera oder Mediathek wählen.",
    cameraWaitReady: "Bitte warte kurz, bis die Kamera bereit ist.",
    photoOfflineQueued: "Kein Internet: Foto wird spaeter synchronisiert.",
    dayCardValidToday: "Digitale Besucherkarte: gueltig bis heute 00:00 Uhr.",
    dayCardValidUntil: "Digitale Besucherkarte: gueltig bis {time} Uhr.",
    expiresUnknown: "Ablauf: --:--:--",
    expiresNow: "Ablauf: 00:00:00",
    expiresIn: "Ablauf in {time}",
    expiringSoonNotice: "Hinweis: Deine Besucherkarte laeuft in weniger als 5 Minuten ab.",
    scannerAutoOpened: "Scanner wurde automatisch geoeffnet, weil weniger als 2 Minuten verbleiben.",
    autoEndedAtMidnight: "Digitale Besucherkarte wurde um 00:00 automatisch beendet. Bitte neu anmelden.",
    updateAvailable: "Neue App-Version verfügbar – wird in wenigen Sekunden neu geladen …",
    siteLocationUnavailable: "Standort konnte nicht ermittelt werden – Login trotzdem erlaubt. Bitte Admin informieren.",
    gateBtn: "Drehkreuz-Modus öffnen",
    changePhotoBtn: "Foto ändern",
    autoOpenScannerLabel: "Scanner bei Ablauf automatisch öffnen",
    sessionKicker: "Session",
    sessionTitle: "Tagesausweis",
    actionsKicker: "Aktionen",
    actionsTitle: "Schnellzugriff",
    visitorMetaKicker: "Besuch",
    visitorMetaTitle: "Besuchsdetails",
    fieldVisitorCompany: "Gastfirma",
    fieldVisitPurpose: "Besuchsgrund",
    fieldHostName: "Ansprechpartner",
    fieldVisitEndAt: "Besuch bis",
    themeToggleBtn: "🌙 Theme",
    voiceCommandBtn: "🎤 Voice",
    notificationPermissionBtn: "Benachrichtigungen",
    leaveRequestKicker: "Abwesenheit",
    leaveRequestTitle: "Urlaubsantrag",
    leaveRequestTypeLabel: "Art",
    leaveTypeVacation: "Urlaub",
    leaveTypeSick: "Krank",
    leaveTypeOther: "Sonstiges",
    leaveRequestStartLabel: "Von",
    leaveRequestEndLabel: "Bis",
    leaveRequestNoteLabel: "Notiz",
    leaveRequestSubmitBtn: "Antrag einreichen",
    leaveRequestNewBtn: "+ Neuer Antrag",
    notificationBannerText: "Benachrichtigungen für Checkout-Erinnerungen aktivieren?",
    notificationEnableBtn: "Aktivieren",
    timesheetKicker: "Zeiterfassung",
    timesheetTitle: "Meine Stunden",
    timesheetCardTitle: "Eintritte & Zeiten",
    timesheetLoading: "Lade Einträge…",
    timesheetEmpty: "Noch keine Einträge vorhanden.",
    timesheetDirectionIn: "Einlass",
    timesheetDirectionOut: "Auslass",
    documentsKicker: "Dokumente",
    documentsTitle: "Meine Unterlagen",
    documentsLoading: "Lade Dokumente…",
    documentsEmpty: "Keine Dokumente hochgeladen.",
    documentsExpiry: "Ablauf",
    documentsStatusOk: "✓ Gültig",
    documentsStatusExpired: "⚠ Abgelaufen",
    documentsStatusNoExpiry: "Kein Ablaufdatum",
    menuKicker: "Menü",
    menuTitle: "Deine Bereiche",
    pageBackBtn: "← Übersicht",
    workerHubShowBtn: "Bereiche anzeigen",
    workerHubHideBtn: "Bereiche ausblenden",
    compactShowMore: "Mehr anzeigen",
    compactShowLess: "Weniger anzeigen",
    lateCheckInMessage: "Achtung: Du bist heute zu spät eingestempelt!",
    lateMinutesUnit: "Min.",
  },
  en: {
    pageTitle: "Worker App",
    appTitle: "Control Pass Mobile",
    appEyebrow: "Worker App",
    appLead: "Your ID, your route, and your site access in one place. Fast, clean, and right on your home screen.",
    languageLabel: "Language",
    installBtn: "Install App",
    installHint: "Optimized for iPhone and Android. Install the app for quick access at the turnstile.",
    online: "Online",
    offline: "Offline",
    loginKicker: "Quick Start",
    loginTitle: "Activate Your Digital ID",
    loginCopy: "You can activate your ID with the worker link or directly with your Badge ID from your card.",
    loginTokenLabel: "Link Code or Badge ID",
    loginTokenPlaceholder: "Token from link or BP-...",
    loginPinLabel: "Badge PIN",
    loginPinPlaceholder: "4–8 digit PIN",
    loginBtn: "Load ID",
    tipBadge: "Badge ID + PIN instead of QR",
    tipHome: "Works as a home screen app",
    tipRoute: "Direct route to your location",
    geolocationHint: "Location required for badge login",
    logoutBtn: "Logout",
    refreshBtn: "Refresh",
    fieldBadgeId: "Badge ID",
    fieldValidUntil: "Valid Until",
    fieldSite: "Location",
    workerCardTitle: "Your Pass for Today",
    visitorCardTitle: "Your Digital Visitor Pass",
    workerPassSubLabel: "Employee ID",
    visitorPassSubLabel: "Visitor Pass",
    offlineBanner: "⚠️ Offline – showing cached data",
    pinLockTitle: "PIN Required",
    pinLockMessage: "This ID has been locked. Please enter your Badge PIN to continue.",
    pinLockBtn: "Unlock ID",
    pinLockLogout: "Logout",
    pinLockEyebrow: "🔒 ID Locked",
    enterBadgeId: "Please enter your Badge ID.",
    enterPin: "Please enter your Badge PIN.",
    loginFailed: "Login failed",
    sessionExpired: "Your visitor pass has expired. Please log in again.",
    connError: "Connection error",
    lastSync: "Last synced",
    splashSub: "Worker App",
    splashLoading: "Loading",
    routeTodayTitle: "Today\'s Site",
    cameraRotate: "Rotate",
    cameraDelete: "Delete",
    cameraTakePhoto: "Take Photo",
    cameraConfirm: "Use Photo",
    cameraRetake: "Retake",
    cameraCancel: "Cancel",
    gateEyebrow: "Digital Company Card",
    gateModeActive: "Turnstile mode active - hold QR under scanner",
    gateBrightnessHint: "⚠ Set display brightness to maximum for fast scanning.",
    gateQrAlt: "Entry QR",
    qrContrastOn: "High-Contrast QR: On",
    qrContrastOff: "High-Contrast QR: Off",
    close: "Close",
    workerDefaultName: "Worker",
    companyFallback: "Construction Company",
    visitorRole: "Visitor",
    noQrAvailable: "No QR available. Please contact admin.",
    badgeUnset: "Badge not set",
    badgeValue: "Badge {value}",
    subcompanyPrefix: "✓ Sub: {name}",
    subcompanyTitle: "Subcontractor: {name}",
    statusRevoked: "❌ Access revoked",
    statusExpired: "⚠ ID expired",
    statusActive: "✓ Active and authorized",
    installAlreadyInstalled: "App is already installed.",
    installIosHowto: "iPhone: In Safari tap Share and choose 'Add to Home Screen'.",
    installAndroidChromeOnly: "Please open in a modern browser. Installation is available via the browser menu.",
    installAndroidHowto: "Android: Open browser menu and tap 'Install app' or 'Add to Home screen'.",
    installManual: "Manual install: Open browser menu and choose 'Add to Home screen' or 'Install app'.",
    enterAccessCode: "Please enter access code.",
    installTip: "Tip: Install the app now so your ID is directly available on your phone.",
    visitorExpiredNeedLink: "Visitor pass expired. Please request a new link.",
    workerAppDisabled: "Worker app is currently disabled.",
    accessFailed: "Access failed",
    inactiveReLogin: "Inactive for too long. Please log in again.",
    wrongPinRetry: "Wrong PIN. Try again.",
    pinLockTooManyAttempts: "Too many attempts - please wait 5 minutes.",
    gateReadyScan: "Ready to scan...",
    gateQrRefreshed: "QR refreshed. Ready to scan.",
    gateScanSyncDelayed: "Connection is slow. Last QR remains active.",
    gateScanAccessGrantedIn: "Access detected: check-in confirmed.",
    gateScanAccessGrantedOut: "Access detected: check-out confirmed.",
    gateScanAccessGrantedGeneric: "Access detected and saved.",
    gateScanAccessDenied: "Access denied. Please contact your supervisor.",
    lowLightDetected: "Low light detected. High-contrast QR recommended.",
    qrLoadFailedAlt: "QR code could not be loaded",
    installHintStandalone: "App is installed. At the turnstile, show the QR code in fullscreen.",
    installHintIos: "iPhone: Safari > Share > Add to Home Screen. Then your company card opens directly like an app.",
    installHintAndroidChrome: "Android: Menu > Install app. Then use it like a normal mobile app.",
    installHintAndroidOther: "Android: Browser menu > Install app or Add to Home screen.",
    cameraBlocked: "Safari blocks browser camera here. Please choose a photo from Camera or Library.",
    cameraStartFailed: "Camera could not be started.",
    cameraHttpsHint: "Safari usually allows browser camera only over HTTPS. Please choose a photo from Camera or Library.",
    cameraWaitReady: "Please wait until the camera is ready.",
    photoOfflineQueued: "No internet: photo will sync later.",
    dayCardValidToday: "Digital visitor pass: valid until today 00:00.",
    dayCardValidUntil: "Digital visitor pass: valid until {time}.",
    expiresUnknown: "Expires: --:--:--",
    expiresNow: "Expires: 00:00:00",
    expiresIn: "Expires in {time}",
    expiringSoonNotice: "Notice: Your visitor pass expires in less than 5 minutes.",
    scannerAutoOpened: "Scanner opened automatically because less than 2 minutes remain.",
    autoEndedAtMidnight: "Digital visitor pass ended automatically at 00:00. Please log in again.",
    updateAvailable: "New app version available – reloading in a few seconds …",
    siteLocationUnavailable: "Site location could not be determined – login still allowed. Please inform admin.",
    gateBtn: "Open Turnstile Mode",
    changePhotoBtn: "Change Photo",
    autoOpenScannerLabel: "Auto-open scanner before expiry",
    sessionKicker: "Session",
    sessionTitle: "Day Pass",
    actionsKicker: "Actions",
    actionsTitle: "Quick Access",
    visitorMetaKicker: "Visit",
    visitorMetaTitle: "Visit Details",
    fieldVisitorCompany: "Visitor Company",
    fieldVisitPurpose: "Visit Purpose",
    fieldHostName: "Contact Person",
    fieldVisitEndAt: "Visit Until",
    themeToggleBtn: "🌙 Theme",
    voiceCommandBtn: "🎤 Voice",
    notificationPermissionBtn: "Notifications",
    leaveRequestKicker: "Absence",
    leaveRequestTitle: "Leave Request",
    leaveRequestTypeLabel: "Type",
    leaveTypeVacation: "Vacation",
    leaveTypeSick: "Sick Leave",
    leaveTypeOther: "Other",
    leaveRequestStartLabel: "From",
    leaveRequestEndLabel: "To",
    leaveRequestNoteLabel: "Note",
    leaveRequestSubmitBtn: "Submit Request",
    leaveRequestNewBtn: "+ New Request",
    notificationBannerText: "Enable notifications for checkout reminders?",
    notificationEnableBtn: "Enable",
    timesheetKicker: "Time Tracking",
    timesheetTitle: "My Hours",
    timesheetCardTitle: "Check-ins & Times",
    timesheetLoading: "Loading entries…",
    timesheetEmpty: "No entries yet.",
    timesheetDirectionIn: "Check-In",
    timesheetDirectionOut: "Check-Out",
    documentsKicker: "Documents",
    documentsTitle: "My Documents",
    documentsLoading: "Loading documents…",
    documentsEmpty: "No documents uploaded.",
    documentsExpiry: "Expiry",
    documentsStatusOk: "✓ Valid",
    documentsStatusExpired: "⚠ Expired",
    documentsStatusNoExpiry: "No expiry date",
    menuKicker: "Menu",
    menuTitle: "Your Sections",
    pageBackBtn: "← Overview",
    workerHubShowBtn: "Show sections",
    workerHubHideBtn: "Hide sections",
    compactShowMore: "Show more",
    compactShowLess: "Show less",
    lateCheckInMessage: "Notice: You clocked in late today!",
    lateMinutesUnit: "min.",
  },
  tr: {
    pageTitle: "Çalışan Uygulaması",
    appTitle: "Control Pass Mobil",
    appEyebrow: "Çalışan Uygulaması",
    appLead: "Kimliğin, rotanın ve şantiye girişin tek bir yerde. Hızlı, temiz ve ana ekranında.",
    languageLabel: "Dil",
    installBtn: "Uygulamayı Kur",
    installHint: "iPhone ve Android için optimize edildi. Turnikede hızlı erişim için uygulamayı kur.",
    online: "Çevrimiçi",
    offline: "Çevrimdışı",
    loginKicker: "Hızlı Başlangıç",
    loginTitle: "Dijital Kimliği Etkinleştir",
    loginCopy: "Kimliğini çalışan bağlantısı veya kartındaki Rozet ID ile etkinleştirebilirsin.",
    loginTokenLabel: "Link Kodu veya Rozet ID",
    loginTokenPlaceholder: "Linkten token veya BP-...",
    loginPinLabel: "Rozet PIN",
    loginPinPlaceholder: "4–8 haneli PIN",
    loginBtn: "Kimliği Yükle",
    tipBadge: "Rozet ID + PIN QR yerine",
    tipHome: "Ana ekran uygulaması olarak çalışır",
    tipRoute: "Konuma doğrudan yol",
    geolocationHint: "Rozet girişi için konum gereklidir",
    logoutBtn: "Çıkış Yap",
    refreshBtn: "Yenile",
    fieldBadgeId: "Rozet ID",
    fieldValidUntil: "Geçerlilik Tarihi",
    fieldSite: "Konum",
    workerCardTitle: "Bugünkü Pasın",
    visitorCardTitle: "Dijital Ziyaretçi Kartın",
    workerPassSubLabel: "Çalışan Kimliği",
    visitorPassSubLabel: "Ziyaretçi Kartı",
    offlineBanner: "⚠️ Çevrimdışı – kayıtlı veriler gösteriliyor",
    pinLockTitle: "PIN Gerekli",
    pinLockMessage: "Bu kimlik kilitlendi. Devam etmek için Rozet PIN'ini gir.",
    pinLockBtn: "Kimliği Aç",
    pinLockLogout: "Çıkış Yap",
    pinLockEyebrow: "🔒 Kimlik Kilitli",
    enterBadgeId: "Lütfen Rozet ID'yi girin.",
    enterPin: "Lütfen Rozet PIN'ini girin.",
    loginFailed: "Giriş başarısız",
    sessionExpired: "Ziyaretçi kartı süresi doldu. Lütfen tekrar giriş yapın.",
    connError: "Bağlantı hatası",
    lastSync: "Son güncelleme",
    splashSub: "Çalışan Uygulaması",
    splashLoading: "Yükleniyor",
    routeTodayTitle: "Bugünkü Konum",
    cameraRotate: "Döndür",
    cameraDelete: "Sil",
    cameraTakePhoto: "Fotoğraf Çek",
    cameraConfirm: "Onayla",
    cameraRetake: "Tekrar Çek",
    cameraCancel: "İptal",
    gateEyebrow: "Dijital Kart",
    gateModeActive: "Turnike modu aktif. QR kodunu okuyucunun altında tut.",
    gateBrightnessHint: "⚠ Hızlı tarama için ekran parlaklığını maksimuma çıkar.",
    gateQrAlt: "Giriş QR",
    qrContrastOn: "Yüksek Kontrast QR: Açık",
    qrContrastOff: "Yüksek Kontrast QR: Kapalı",
    close: "Kapat",
    workerDefaultName: "Çalışan",
    companyFallback: "İnşaat Firması",
    visitorRole: "Ziyaretçi",
    noQrAvailable: "QR mevcut değil. Lütfen yöneticiye başvurun.",
    badgeUnset: "Rozet ayarlı değil",
    badgeValue: "Rozet {value}",
    subcompanyPrefix: "✓ Alt Yüklenici: {name}",
    subcompanyTitle: "Alt yüklenici: {name}",
    statusRevoked: "❌ Erişim kaldırıldı",
    statusExpired: "⚠ Kimlik süresi doldu",
    statusActive: "✓ Aktif ve yetkili",
    installAlreadyInstalled: "Uygulama zaten kurulu.",
    installIosHowto: "iPhone: Safari\'de Paylaş\'a dokun ve 'Ana Ekrana Ekle' seç.",
    installAndroidChromeOnly: "Lütfen modern bir tarayıcıda açın. Kurulum tarayıcı menüsünden yapılır.",
    installAndroidHowto: "Android: Tarayıcı menüsünden 'Uygulamayı yükle' veya 'Ana ekrana ekle' seç.",
    installManual: "Manuel kurulum: Tarayıcı menüsünü açıp 'Ana ekrana ekle' veya 'Uygulamayı yükle' seç.",
    enterAccessCode: "Lütfen erişim kodunu girin.",
    installTip: "İpucu: Kimliğin telefonda hazır olması için uygulamayı şimdi kur.",
    visitorExpiredNeedLink: "Ziyaretçi kartının süresi doldu. Lütfen yeni bağlantı isteyin.",
    workerAppDisabled: "Çalışan uygulaması şu anda devre dışı.",
    accessFailed: "Erişim başarısız",
    inactiveReLogin: "Çok uzun süre işlem yapılmadı. Lütfen yeniden giriş yapın.",
    wrongPinRetry: "PIN yanlış. Tekrar deneyin.",
    pinLockTooManyAttempts: "Çok fazla deneme – lütfen 5 dakika bekleyin.",
    gateReadyScan: "📱 Taramaya hazır...",
    gateQrRefreshed: "QR yenilendi. Tarama için hazır.",
    gateScanSyncDelayed: "Bağlantı yavaş. Son QR aktif kalıyor.",
    gateScanAccessGrantedIn: "Erisim algilandi: giris onaylandi.",
    gateScanAccessGrantedOut: "Erisim algilandi: cikis onaylandi.",
    gateScanAccessGrantedGeneric: "Erisim algilandi ve kaydedildi.",
    gateScanAccessDenied: "Erisim reddedildi. Lutfen sorumluya basvurun.",
    lowLightDetected: "Karanlık ortam algılandı. Yüksek kontrast QR önerilir.",
    qrLoadFailedAlt: "QR kodu yüklenemedi",
    installHintStandalone: "Uygulama kurulu. Turnikede QR kodunu tam ekranda göster.",
    installHintIos: "iPhone: Safari > Paylaş > Ana Ekrana Ekle. Sonra şirket kartı doğrudan uygulama gibi açılır.",
    installHintAndroidChrome: "Android: Menü > Uygulamayı yükle. Sonra normal mobil uygulama gibi kullan.",
    installHintAndroidOther: "Android: Tarayıcı menüsü > Uygulamayı yükle veya Ana ekrana ekle.",
    cameraBlocked: "Safari burada tarayıcı kamerasını engelliyor. Lütfen Kamera veya Galeri\'den fotoğraf seçin.",
    cameraStartFailed: "Kamera başlatılamadı.",
    cameraHttpsHint: "Safari genelde tarayıcı kamerasına sadece HTTPS üzerinde izin verir. Lütfen Kamera veya Galeri\'den fotoğraf seçin.",
    cameraWaitReady: "Lütfen kamera hazır olana kadar bekleyin.",
    photoOfflineQueued: "İnternet yok: fotoğraf daha sonra senkronize edilecek.",
    dayCardValidToday: "Dijital ziyaretçi kartı: bugün 00:00\'a kadar geçerli.",
    dayCardValidUntil: "Dijital ziyaretçi kartı: {time} saatine kadar geçerli.",
    expiresUnknown: "Bitiş: --:--:--",
    expiresNow: "Bitiş: 00:00:00",
    expiresIn: "Bitişe kalan {time}",
    expiringSoonNotice: "Bilgi: Ziyaretçi kartınızın süresi 5 dakikadan az kaldı.",
    scannerAutoOpened: "2 dakikadan az kaldığı için tarayıcı otomatik açıldı.",
    autoEndedAtMidnight: "Dijital ziyaretçi kartı 00:00\'da otomatik sona erdi. Lütfen yeniden giriş yapın.",
    gateBtn: "Turnike Modunu Aç",
    changePhotoBtn: "Fotoğrafı Değiştir",
    autoOpenScannerLabel: "Bitiş öncesi tarayıcıyı otomatik aç",
    sessionKicker: "Oturum",
    sessionTitle: "Günlük Kart",
    actionsKicker: "İşlemler",
    actionsTitle: "Hızlı Erişim",
    visitorMetaKicker: "Ziyaret",
    visitorMetaTitle: "Ziyaret Detayları",
    fieldVisitorCompany: "Ziyaretçi Firması",
    fieldVisitPurpose: "Ziyaret Amacı",
    fieldHostName: "İlgili Kişi",
    fieldVisitEndAt: "Ziyaret Bitiş",
    themeToggleBtn: "🌙 Tema",
    voiceCommandBtn: "🎤 Ses",
    notificationPermissionBtn: "Bildirimler",
    leaveRequestKicker: "İzin",
    leaveRequestTitle: "İzin Talebi",
    leaveRequestTypeLabel: "Tür",
    leaveTypeVacation: "Tatil",
    leaveTypeSick: "Hastalık İzni",
    leaveTypeOther: "Diğer",
    leaveRequestStartLabel: "Başlangıç",
    leaveRequestEndLabel: "Bitiş",
    leaveRequestNoteLabel: "Not",
    leaveRequestSubmitBtn: "Talebi Gönder",
    leaveRequestNewBtn: "+ Yeni Talep",
    notificationBannerText: "Çıkış hatırlatmaları için bildirimleri etkinleştir?",
    notificationEnableBtn: "Etkinleştir",
    timesheetKicker: "Zaman Takibi",
    timesheetTitle: "Saatlerim",
    timesheetLoading: "Girişler yükleniyor…",
    timesheetEmpty: "Henüz giriş yok.",
    timesheetDirectionIn: "Giriş",
    timesheetDirectionOut: "Çıkış",
    documentsKicker: "Belgeler",
    documentsTitle: "Belgelerim",
    documentsLoading: "Belgeler yükleniyor…",
    documentsEmpty: "Belge yüklenmedi.",
    documentsExpiry: "Son geçerlilik",
    documentsStatusOk: "✓ Geçerli",
    documentsStatusExpired: "⚠ Süresi doldu",
    documentsStatusNoExpiry: "Tarih yok",
    menuKicker: "Menü",
    menuTitle: "Bölümleriniz",
    pageBackBtn: "← Genel Bakış",
    lateCheckInMessage: "Dikkat: Bugün geç girdiniz!",
    lateMinutesUnit: "dk.",
    timesheetCardTitle: "Girişler & Saatler",
  },
  ar: {
    pageTitle: "تطبيق العمال",
    appTitle: "Control Pass موبايل",
    appEyebrow: "تطبيق العمال",
    appLead: "هويتك وطريقك ودخولك إلى الموقع في مكان واحد. سريع وسهل على الشاشة الرئيسية.",
    languageLabel: "اللغة",
    installBtn: "تثبيت التطبيق",
    installHint: "محسّن لـ iPhone وAndroid. ثبّت التطبيق للوصول السريع عند البوابة الدوارة.",
    online: "متصل",
    offline: "غير متصل",
    loginKicker: "بداية سريعة",
    loginTitle: "تفعيل الهوية الرقمية",
    loginCopy: "يمكنك تفعيل هويتك عبر رابط الموظف أو مباشرةً ببطاقة الهوية.",
    loginTokenLabel: "رمز الرابط أو رقم البطاقة",
    loginTokenPlaceholder: "رمز من الرابط أو BP-...",
    loginPinLabel: "رمز PIN للبطاقة",
    loginPinPlaceholder: "رمز PIN مكوّن من 4–8 أرقام",
    loginBtn: "تحميل الهوية",
    tipBadge: "رقم البطاقة + PIN بدلاً من QR",
    tipHome: "يعمل كتطبيق على الشاشة الرئيسية",
    tipRoute: "طريق مباشر إلى الموقع",
    geolocationHint: "الموقع مطلوب لتسجيل الدخول بالبطاقة",
    logoutBtn: "تسجيل الخروج",
    refreshBtn: "تحديث",
    fieldBadgeId: "رقم البطاقة",
    fieldValidUntil: "صالح حتى",
    fieldSite: "الموقع",
    workerCardTitle: "بطاقتك اليوم",
    visitorCardTitle: "بطاقة الزائر الرقمية",
    workerPassSubLabel: "هوية العامل",
    visitorPassSubLabel: "بطاقة الزائر",
    offlineBanner: "⚠️ غير متصل – عرض البيانات المحفوظة",
    pinLockTitle: "مطلوب رمز PIN",
    pinLockMessage: "تم قفل هذه الهوية. أدخل رمز PIN للمتابعة.",
    pinLockBtn: "فتح الهوية",
    pinLockLogout: "تسجيل الخروج",
    pinLockEyebrow: "🔒 الهوية مقفلة",
    enterBadgeId: "الرجاء إدخال رقم البطاقة.",
    enterPin: "الرجاء إدخال رمز PIN.",
    loginFailed: "فشل تسجيل الدخول",
    sessionExpired: "انتهت صلاحية بطاقة الزائر. يرجى تسجيل الدخول مجدداً.",
    connError: "خطأ في الاتصال",
    lastSync: "آخر تحديث",
    splashSub: "تطبيق العمال",
    splashLoading: "جارٍ التحميل",
    routeTodayTitle: "موقع اليوم",
    cameraRotate: "تدوير",
    cameraDelete: "حذف",
    cameraTakePhoto: "التقاط صورة",
    cameraConfirm: "استخدام الصورة",
    cameraRetake: "إعادة التقاط",
    cameraCancel: "إلغاء",
    gateEyebrow: "البطاقة الرقمية",
    gateModeActive: "وضع البوابة مفعل. ضع رمز QR تحت الماسح.",
    gateBrightnessHint: "⚠ ارفع سطوع الشاشة إلى الحد الأقصى لسرعة المسح.",
    gateQrAlt: "QR للدخول",
    qrContrastOn: "QR عالي التباين: تشغيل",
    qrContrastOff: "QR عالي التباين: إيقاف",
    close: "إغلاق",
    workerDefaultName: "عامل",
    companyFallback: "شركة البناء",
    visitorRole: "زائر",
    noQrAvailable: "لا يوجد رمز QR. يرجى التواصل مع المسؤول.",
    badgeUnset: "رقم البطاقة غير مضبوط",
    badgeValue: "البطاقة: {value}",
    subcompanyPrefix: "✓ المقاول الفرعي: {name}",
    subcompanyTitle: "المقاول الفرعي: {name}",
    statusRevoked: "❌ تم سحب الوصول",
    statusExpired: "⚠ انتهت صلاحية الهوية",
    statusActive: "✓ نشط ومصرح",
    installAlreadyInstalled: "التطبيق مثبت بالفعل.",
    installIosHowto: "iPhone: في Safari اضغط مشاركة ثم اختر 'إضافة إلى الشاشة الرئيسية'.",
    installAndroidChromeOnly: "يرجى الفتح في متصفح حديث. التثبيت متاح من قائمة المتصفح.",
    installAndroidHowto: "Android: افتح قائمة المتصفح واضغط 'تثبيت التطبيق' أو 'إضافة إلى الشاشة الرئيسية'.",
    installManual: "تثبيت يدوي: افتح قائمة المتصفح واختر 'إضافة إلى الشاشة الرئيسية' أو 'تثبيت التطبيق'.",
    enterAccessCode: "يرجى إدخال رمز الوصول.",
    installTip: "نصيحة: ثبّت التطبيق الآن ليكون معرّفك متاحاً مباشرة على الهاتف.",
    visitorExpiredNeedLink: "انتهت صلاحية بطاقة الزائر. يرجى طلب رابط جديد.",
    workerAppDisabled: "تطبيق العمال معطل حالياً.",
    accessFailed: "فشل الوصول",
    inactiveReLogin: "خمول لفترة طويلة. يرجى تسجيل الدخول مرة أخرى.",
    wrongPinRetry: "رمز PIN غير صحيح. حاول مرة أخرى.",
    pinLockTooManyAttempts: "محاولات كثيرة جداً – الرجاء الانتظار 5 دقائق.",
    gateReadyScan: "📱 جاهز للمسح...",
    gateQrRefreshed: "تم تحديث رمز QR. جاهز للمسح.",
    gateScanSyncDelayed: "الاتصال بطيء. آخر رمز QR لا يزال فعالاً.",
    gateScanAccessGrantedIn: "تم رصد العبور: تم تاكيد الدخول.",
    gateScanAccessGrantedOut: "تم رصد العبور: تم تاكيد الخروج.",
    gateScanAccessGrantedGeneric: "تم رصد العبور وحفظه.",
    gateScanAccessDenied: "تم رفض الوصول. يرجى التواصل مع المشرف.",
    lowLightDetected: "تم اكتشاف إضاءة منخفضة. يوصى برمز QR عالي التباين.",
    qrLoadFailedAlt: "تعذر تحميل رمز QR",
    installHintStandalone: "التطبيق مثبت. عند البوابة اعرض رمز QR بملء الشاشة.",
    installHintIos: "iPhone: Safari > مشاركة > إضافة إلى الشاشة الرئيسية. بعدها تفتح بطاقة الشركة مباشرة كتطبيق.",
    installHintAndroidChrome: "Android: القائمة > تثبيت التطبيق. ثم استخدمه كتطبيق جوال عادي.",
    installHintAndroidOther: "Android: قائمة المتصفح > تثبيت التطبيق أو إضافة إلى الشاشة الرئيسية.",
    cameraBlocked: "Safari يمنع كاميرا المتصفح هنا. يرجى اختيار صورة من الكاميرا أو المعرض.",
    cameraStartFailed: "تعذر تشغيل الكاميرا.",
    cameraHttpsHint: "Safari يسمح عادةً بكاميرا المتصفح عبر HTTPS فقط. يرجى اختيار صورة من الكاميرا أو المعرض.",
    cameraWaitReady: "يرجى الانتظار حتى تصبح الكاميرا جاهزة.",
    photoOfflineQueued: "لا يوجد إنترنت: ستتم مزامنة الصورة لاحقاً.",
    dayCardValidToday: "بطاقة الزائر الرقمية: صالحة حتى اليوم 00:00.",
    dayCardValidUntil: "بطاقة الزائر الرقمية: صالحة حتى {time}.",
    expiresUnknown: "الانتهاء: --:--:--",
    expiresNow: "الانتهاء: 00:00:00",
    expiresIn: "ينتهي خلال {time}",
    expiringSoonNotice: "تنبيه: ستنتهي صلاحية بطاقة الزائر خلال أقل من 5 دقائق.",
    scannerAutoOpened: "تم فتح الماسح تلقائياً لأن المتبقي أقل من دقيقتين.",
    autoEndedAtMidnight: "انتهت بطاقة الزائر الرقمية تلقائياً عند 00:00. يرجى تسجيل الدخول مجدداً.",
    gateBtn: "فتح وضع البوابة",
    changePhotoBtn: "تغيير الصورة",
    autoOpenScannerLabel: "فتح الماسح تلقائياً قبل الانتهاء",
    sessionKicker: "الجلسة",
    sessionTitle: "بطاقة اليوم",
    actionsKicker: "الإجراءات",
    actionsTitle: "وصول سريع",
    visitorMetaKicker: "الزيارة",
    visitorMetaTitle: "تفاصيل الزيارة",
    fieldVisitorCompany: "شركة الزائر",
    fieldVisitPurpose: "هدف الزيارة",
    fieldHostName: "جهة الاتصال",
    fieldVisitEndAt: "الزيارة حتى",
    themeToggleBtn: "🌙 المظهر",
    voiceCommandBtn: "🎤 صوت",
    notificationPermissionBtn: "إشعارات",
    leaveRequestKicker: "غياب",
    leaveRequestTitle: "طلب إجازة",
    leaveRequestTypeLabel: "النوع",
    leaveTypeVacation: "إجازة",
    leaveTypeSick: "إجازة مرضية",
    leaveTypeOther: "أخرى",
    leaveRequestStartLabel: "من",
    leaveRequestEndLabel: "إلى",
    leaveRequestNoteLabel: "ملاحظة",
    leaveRequestSubmitBtn: "إرسال الطلب",
    leaveRequestNewBtn: "+ طلب جديد",
    notificationBannerText: "تفعيل الإشعارات لتذكيرات الخروج؟",
    notificationEnableBtn: "تفعيل",
    timesheetKicker: "تتبع الوقت",
    timesheetTitle: "ساعاتي",
    timesheetCardTitle: "السجلات والأوقات",
    timesheetLoading: "جارٍ التحميل…",
    timesheetEmpty: "لا توجد سجلات بعد.",
    timesheetDirectionIn: "دخول",
    timesheetDirectionOut: "خروج",
    documentsKicker: "المستندات",
    documentsTitle: "مستنداتي",
    documentsLoading: "تحميل المستندات…",
    documentsEmpty: "لم يتم رفع أي مستند.",
    documentsExpiry: "انتهاء الصلاحية",
    documentsStatusOk: "✓ صالح",
    documentsStatusExpired: "⚠ منتهي",
    documentsStatusNoExpiry: "بدون تاريخ انتهاء",
    menuKicker: "القائمة",
    menuTitle: "أقسامك",
    pageBackBtn: "← نظرة عامة",
    lateCheckInMessage: "تنبيه: لقد تسجّلت اليوم متأخراً!",
    lateMinutesUnit: "د.",
  },
};
  TRANSLATIONS.fr = {
  ...TRANSLATIONS.en,
  pageTitle: "Application Employé",
  appEyebrow: "Application Employé",
  languageLabel: "Langue"
};
TRANSLATIONS.es = {
  ...TRANSLATIONS.en,
  pageTitle: "App Trabajador",
  appEyebrow: "App Trabajador",
  languageLabel: "Idioma"
};
TRANSLATIONS.it = {
  ...TRANSLATIONS.en,
  pageTitle: "App Lavoratore",
  appEyebrow: "App Lavoratore",
  languageLabel: "Lingua"
};
TRANSLATIONS.pl = {
  ...TRANSLATIONS.en,
  pageTitle: "Aplikacja Pracownika",
  appEyebrow: "Aplikacja Pracownika",
  languageLabel: "Język"
};

Object.assign(TRANSLATIONS.de, {
  visitorCountdownLabel: "Besuch endet in",
  visitorCountdownExpired: "Besuchszeit abgelaufen – Abmeldung",
  visitEndedLogout: "Ihre Besuchszeit ist abgelaufen. Bitte neu anmelden.",
  aiSuggestBtn: "✨ KI Vorschlag",
  bossEmailLabel: "An Chef senden (optional)",
  bossEmailPlaceholder: "chef@firma.de",
  leaveRequestNotePlaceholder: "Optional",
  quickMenuPass: "Pass",
  quickMenuActions: "Aktionen",
  quickMenuRequest: "Antrag",
  quickMenuHours: "Stunden",
  quickMenuDocs: "Docs",
  leaveBalanceDaysRemaining: "Tage verbleibend",
  topStatPass: "Pass",
  topStatDigital: "Digital",
  topStatSync: "Sync",
  topStatInstant: "Sofort",
  lastSyncInitial: "Zuletzt synchronisiert: -",
  statusActiveShort: "Aktiv",
  qrCodeAlt: "QR-Code",
  workerPhotoAlt: "Mitarbeiterfoto",
  workerDefaultRole: "Rolle",
  companyDefaultName: "Baufirma",
  workerPageDefault: "Bereich",
  workerPageOpened: "Geoeffnet: {page}",
  offlineLoginOnSiteOnly: "Offline-Login nur auf der Baustelle moeglich. Aktuell ca. {meters} m entfernt.",
  offlineLoginActiveWaitingSync: "Offline-Login aktiv. Wartet auf spaetere Synchronisierung.",
  browserPushNotSupported: "Push-Benachrichtigungen werden von Ihrem Browser nicht unterstützt.",
  notificationsAlreadyEnabled: "Benachrichtigungen sind bereits aktiviert.",
  notificationsEnabled: "Benachrichtigungen aktiviert!",
  quickMenuAria: "Schnellnavigation",
  languageSelectAria: "Sprache auswählen",
  qrLinkUsedEnterPin: "Dieser QR-Link wurde bereits benutzt. Bitte PIN eingeben.",
  qrLinkInvalidRescan: "QR-Link ungueltig oder bereits verbraucht. Bitte QR-Code neu scannen.",
  leaveDateRangeInvalid: "Startdatum muss vor dem Enddatum liegen.",
  leaveRequestSubmitted: "✓ Urlaubsantrag eingereicht",
  aiSuggestionInserted: "✓ KI-Vorschlag eingefügt",
  submitRequestFirst: "Bitte zuerst einen Antrag einreichen.",
  enterValidManagerEmail: "Bitte eine gültige Chef-E-Mail eingeben.",
  voiceNotSupported: "Sprachsteuerung wird von Ihrem Browser nicht unterstützt.",
  voiceNeedsSecureContext: "Sprachsteuerung benötigt HTTPS oder localhost.",
  voiceListening: "🎤 Zuhören...",
  microphoneAccessBlocked: "Mikrofonzugriff wurde blockiert. Bitte Browser-Berechtigung erlauben.",
  noSpeechDetected: "Keine Sprache erkannt. Bitte erneut versuchen.",
  sendToBossBtn: "Senden",
  sendToBossKicker: "Per E-Mail weiterleiten",
  sendToBossSuccess: "✓ Antrag wurde an den Chef gesendet.",
  sendToBossError: "Fehler beim Senden – E-Mail-Einstellungen prüfen.",
  visitorExpiredBadgeLogin: "Diese Besucherkarte ist abgelaufen und kann nicht mehr genutzt werden.",
  refreshBtn: "↻"
});

Object.assign(TRANSLATIONS.en, {
  visitorCountdownLabel: "Visit ends in",
  visitorCountdownExpired: "Visit time expired – logging out",
  visitEndedLogout: "Your visit time has expired. Please log in again.",
  aiSuggestBtn: "✨ AI Suggestion",
  bossEmailLabel: "Send to manager (optional)",
  bossEmailPlaceholder: "manager@company.com",
  leaveRequestNotePlaceholder: "Optional",
  quickMenuPass: "Pass",
  quickMenuActions: "Actions",
  quickMenuRequest: "Request",
  quickMenuHours: "Hours",
  quickMenuDocs: "Docs",
  leaveBalanceDaysRemaining: "days remaining",
  topStatPass: "Pass",
  topStatDigital: "Digital",
  topStatSync: "Sync",
  topStatInstant: "Instant",
  lastSyncInitial: "Last synced: -",
  statusActiveShort: "Active",
  qrCodeAlt: "QR code",
  workerPhotoAlt: "Worker photo",
  workerDefaultRole: "Role",
  companyDefaultName: "Company",
  workerPageDefault: "Section",
  workerPageOpened: "Opened: {page}",
  offlineLoginOnSiteOnly: "Offline login is only possible on site. Currently about {meters} m away.",
  offlineLoginActiveWaitingSync: "Offline login active. Waiting for later synchronization.",
  browserPushNotSupported: "Push notifications are not supported by your browser.",
  notificationsAlreadyEnabled: "Notifications are already enabled.",
  notificationsEnabled: "Notifications enabled!",
  quickMenuAria: "Quick navigation",
  languageSelectAria: "Select language",
  qrLinkUsedEnterPin: "This QR link has already been used. Please enter your PIN.",
  qrLinkInvalidRescan: "QR link invalid or already used. Please scan the QR code again.",
  leaveDateRangeInvalid: "Start date must be before end date.",
  leaveRequestSubmitted: "✓ Leave request submitted",
  aiSuggestionInserted: "✓ AI suggestion inserted",
  submitRequestFirst: "Please submit a request first.",
  enterValidManagerEmail: "Please enter a valid manager email.",
  voiceNotSupported: "Voice control is not supported by your browser.",
  voiceNeedsSecureContext: "Voice control requires HTTPS or localhost.",
  voiceListening: "🎤 Listening...",
  microphoneAccessBlocked: "Microphone access was blocked. Please allow browser permission.",
  noSpeechDetected: "No speech detected. Please try again.",
  sendToBossBtn: "Send",
  sendToBossKicker: "Forward by email",
  sendToBossSuccess: "✓ Request sent to manager.",
  sendToBossError: "Failed to send – check email settings.",
  visitorExpiredBadgeLogin: "This visitor card has expired and can no longer be used.",
  refreshBtn: "↻"
});

Object.assign(TRANSLATIONS.tr, {
  visitorCountdownLabel: "Ziyaret bitiyor",
  visitorCountdownExpired: "Ziyaret süresi doldu – çıkış yapılıyor",
  visitEndedLogout: "Ziyaret süreniz doldu. Lütfen yeniden giriş yapın.",
  aiSuggestBtn: "✨ Yapay Zeka Önerisi",
  bossEmailLabel: "Amire gönder (isteğe bağlı)",
  bossEmailPlaceholder: "amir@sirket.com",
  leaveRequestNotePlaceholder: "İsteğe bağlı",
  quickMenuPass: "Kart",
  quickMenuActions: "Aksiyonlar",
  quickMenuRequest: "Talep",
  quickMenuHours: "Saatler",
  quickMenuDocs: "Belgeler",
  leaveBalanceDaysRemaining: "gün kaldı",
  topStatPass: "Kart",
  topStatDigital: "Dijital",
  topStatSync: "Senk",
  topStatInstant: "Aninda",
  lastSyncInitial: "Son güncelleme: -",
  statusActiveShort: "Aktif",
  qrCodeAlt: "QR kodu",
  workerPhotoAlt: "Çalışan fotoğrafı",
  workerDefaultRole: "Rol",
  companyDefaultName: "Şirket",
  workerPageDefault: "Bölüm",
  workerPageOpened: "Açıldı: {page}",
  offlineLoginOnSiteOnly: "Çevrimdışı giriş yalnızca şantiyede mümkün. Şu anda yaklaşık {meters} m uzaktasınız.",
  offlineLoginActiveWaitingSync: "Çevrimdışı giriş aktif. Daha sonra senkronizasyon bekleniyor.",
  browserPushNotSupported: "Push bildirimleri tarayıcınız tarafından desteklenmiyor.",
  notificationsAlreadyEnabled: "Bildirimler zaten etkin.",
  notificationsEnabled: "Bildirimler etkinleştirildi!",
  quickMenuAria: "Hızlı gezinme",
  languageSelectAria: "Dil seç",
  qrLinkUsedEnterPin: "Bu QR bağlantısı zaten kullanıldı. Lütfen PIN girin.",
  qrLinkInvalidRescan: "QR bağlantısı geçersiz veya zaten kullanılmış. Lütfen QR kodunu tekrar tarayın.",
  leaveDateRangeInvalid: "Başlangıç tarihi bitiş tarihinden önce olmalıdır.",
  leaveRequestSubmitted: "✓ İzin talebi gönderildi",
  aiSuggestionInserted: "✓ Yapay zeka önerisi eklendi",
  submitRequestFirst: "Lütfen önce bir talep gönderin.",
  enterValidManagerEmail: "Lütfen geçerli bir yönetici e-postası girin.",
  voiceNotSupported: "Sesli kontrol tarayıcınız tarafından desteklenmiyor.",
  voiceNeedsSecureContext: "Sesli kontrol için HTTPS veya localhost gerekir.",
  voiceListening: "🎤 Dinleniyor...",
  microphoneAccessBlocked: "Mikrofon erişimi engellendi. Lütfen tarayıcı iznini verin.",
  noSpeechDetected: "Konuşma algılanmadı. Lütfen tekrar deneyin.",
  sendToBossBtn: "Gönder",
  sendToBossKicker: "E-posta ile ilet",
  sendToBossSuccess: "✓ Talep amire gönderildi.",
  sendToBossError: "Gönderim başarısız – e-posta ayarlarını kontrol edin.",
  visitorExpiredBadgeLogin: "Bu ziyaretçi kartının süresi doldu ve artık kullanılamaz.",
  refreshBtn: "↻",
  updateAvailable: "Yeni uygulama sürümü mevcut – birkaç saniye içinde yeniden yükleniyor …",
  siteLocationUnavailable: "Şantiye konumu belirlenemedi – giriş yine de izin veriliyor. Lütfen yöneticiyi bilgilendirin."
});

Object.assign(TRANSLATIONS.ar, {
  visitorCountdownLabel: "الزيارة تنتهي خلال",
  visitorCountdownExpired: "انتهت مدة الزيارة – جارٍ تسجيل الخروج",
  visitEndedLogout: "انتهت مدة زيارتك. يرجى تسجيل الدخول مرة أخرى.",
  aiSuggestBtn: "✨ اقتراح ذكاء اصطناعي",
  bossEmailLabel: "إرسال إلى المدير (اختياري)",
  bossEmailPlaceholder: "مدير@شركة.com",
  leaveRequestNotePlaceholder: "اختياري",
  quickMenuPass: "البطاقة",
  quickMenuActions: "الإجراءات",
  quickMenuRequest: "الطلب",
  quickMenuHours: "الساعات",
  quickMenuDocs: "المستندات",
  leaveBalanceDaysRemaining: "أيام متبقية",
  topStatPass: "البطاقة",
  topStatDigital: "رقمية",
  topStatSync: "مزامنة",
  topStatInstant: "فوري",
  lastSyncInitial: "آخر مزامنة: -",
  statusActiveShort: "نشط",
  qrCodeAlt: "رمز QR",
  workerPhotoAlt: "صورة العامل",
  workerDefaultRole: "الدور",
  companyDefaultName: "الشركة",
  workerPageDefault: "قسم",
  workerPageOpened: "مفتوح: {page}",
  offlineLoginOnSiteOnly: "تسجيل الدخول دون اتصال متاح فقط في موقع العمل. المسافة الحالية حوالي {meters} متر.",
  offlineLoginActiveWaitingSync: "تسجيل الدخول دون اتصال نشط. بانتظار المزامنة لاحقًا.",
  browserPushNotSupported: "إشعارات الدفع غير مدعومة في متصفحك.",
  notificationsAlreadyEnabled: "الإشعارات مفعلة بالفعل.",
  notificationsEnabled: "تم تفعيل الإشعارات!",
  quickMenuAria: "تنقل سريع",
  languageSelectAria: "اختر اللغة",
  qrLinkUsedEnterPin: "تم استخدام رابط QR هذا بالفعل. يرجى إدخال رمز PIN.",
  qrLinkInvalidRescan: "رابط QR غير صالح أو تم استخدامه بالفعل. يرجى مسح رمز QR مرة أخرى.",
  leaveDateRangeInvalid: "يجب أن يكون تاريخ البداية قبل تاريخ النهاية.",
  leaveRequestSubmitted: "✓ تم إرسال طلب الإجازة",
  aiSuggestionInserted: "✓ تمت إضافة اقتراح الذكاء الاصطناعي",
  submitRequestFirst: "يرجى إرسال طلب أولاً.",
  enterValidManagerEmail: "يرجى إدخال بريد إلكتروني صالح للمدير.",
  voiceNotSupported: "التحكم الصوتي غير مدعوم في متصفحك.",
  voiceNeedsSecureContext: "التحكم الصوتي يتطلب HTTPS أو localhost.",
  voiceListening: "🎤 جارٍ الاستماع...",
  microphoneAccessBlocked: "تم حظر الوصول إلى الميكروفون. يرجى السماح بإذن المتصفح.",
  noSpeechDetected: "لم يتم اكتشاف كلام. يرجى المحاولة مرة أخرى.",
  sendToBossBtn: "إرسال",
  sendToBossKicker: "إرسال بالبريد الإلكتروني",
  sendToBossSuccess: "✓ تم إرسال الطلب إلى المدير.",
  sendToBossError: "فشل الإرسال – تحقق من إعدادات البريد.",
  visitorExpiredBadgeLogin: "انتهت صلاحية هذه البطاقة ولا يمكن استخدامها.",
  refreshBtn: "↻",
  updateAvailable: "إصدار جديد من التطبيق متاح – إعادة التحميل خلال ثوانٍ …",
  siteLocationUnavailable: "تعذّر تحديد موقع الشانتيه – تسجيل الدخول مسموح به على أي حال. يرجى إبلاغ المسؤول."
});

Object.assign(TRANSLATIONS.fr, {
  visitorCountdownLabel: "La visite se termine dans",
  visitorCountdownExpired: "Temps de visite expiré – déconnexion",
  visitEndedLogout: "Votre temps de visite a expiré. Veuillez vous reconnecter.",
  aiSuggestBtn: "✨ Suggestion IA",
  bossEmailLabel: "Envoyer au responsable (optionnel)",
  bossEmailPlaceholder: "responsable@entreprise.fr",
  sendToBossBtn: "Envoyer",
  sendToBossKicker: "Transmettre par e-mail",
  sendToBossSuccess: "✓ Demande envoyée au responsable.",
  sendToBossError: "Échec de l'envoi – vérifiez les paramètres e-mail.",
  visitorExpiredBadgeLogin: "Cette carte visiteur a expiré et ne peut plus être utilisée.",
  refreshBtn: "↻",
  updateAvailable: "Nouvelle version disponible – rechargement dans quelques secondes …",
  siteLocationUnavailable: "Localisation du site indisponible – connexion tout de même autorisée. Informez l'administrateur."
});

Object.assign(TRANSLATIONS.es, {
  visitorCountdownLabel: "La visita termina en",
  visitorCountdownExpired: "Tiempo de visita expirado – cerrando sesión",
  visitEndedLogout: "Su tiempo de visita ha expirado. Por favor, inicie sesión de nuevo.",
  aiSuggestBtn: "✨ Sugerencia IA",
  bossEmailLabel: "Enviar al responsable (opcional)",
  bossEmailPlaceholder: "responsable@empresa.es",
  sendToBossBtn: "Enviar",
  sendToBossKicker: "Reenviar por correo",
  sendToBossSuccess: "✓ Solicitud enviada al responsable.",
  sendToBossError: "Error al enviar – compruebe la configuración de correo.",
  visitorExpiredBadgeLogin: "Esta tarjeta de visitante ha expirado y ya no puede usarse.",
  refreshBtn: "↻",
  updateAvailable: "Nueva versión disponible – recargando en unos segundos …",
  siteLocationUnavailable: "No se pudo determinar la ubicación del sitio – inicio de sesión permitido de todos modos. Informe al administrador."
});

Object.assign(TRANSLATIONS.it, {
  visitorCountdownLabel: "La visita termina tra",
  visitorCountdownExpired: "Tempo di visita scaduto – disconnessione",
  visitEndedLogout: "Il tuo tempo di visita è scaduto. Effettua di nuovo l'accesso.",
  aiSuggestBtn: "✨ Suggerimento IA",
  bossEmailLabel: "Invia al responsabile (opzionale)",
  bossEmailPlaceholder: "responsabile@azienda.it",
  sendToBossBtn: "Invia",
  sendToBossKicker: "Inoltra per e-mail",
  sendToBossSuccess: "✓ Richiesta inviata al responsabile.",
  sendToBossError: "Invio fallito – verificare le impostazioni e-mail.",
  visitorExpiredBadgeLogin: "Questo pass visitatore è scaduto e non può più essere utilizzato.",
  refreshBtn: "↻",
  updateAvailable: "Nuova versione disponibile – ricaricamento in pochi secondi …",
  siteLocationUnavailable: "Posizione del cantiere non disponibile – accesso comunque consentito. Informare l'amministratore."
});

Object.assign(TRANSLATIONS.pl, {
  visitorCountdownLabel: "Wizyta kończy się za",
  visitorCountdownExpired: "Czas wizyty minął – wylogowywanie",
  visitEndedLogout: "Twój czas wizyty minął. Zaloguj się ponownie.",
  aiSuggestBtn: "✨ Sugestia AI",
  bossEmailLabel: "Wyślij do przełożonego (opcjonalnie)",
  bossEmailPlaceholder: "przelozony@firma.pl",
  sendToBossBtn: "Wyślij",
  sendToBossKicker: "Przekaż e-mailem",
  sendToBossSuccess: "✓ Wniosek wysłany do przełożonego.",
  sendToBossError: "Błąd wysyłania – sprawdź ustawienia e-mail.",
  visitorExpiredBadgeLogin: "Ta karta odwiedzającego wygasła i nie może być już używana.",
  refreshBtn: "↻",
  updateAvailable: "Dostępna nowa wersja aplikacji – przeładowanie za kilka sekund …",
  siteLocationUnavailable: "Nie można określić lokalizacji budowy – logowanie jest i tak dozwolone. Poinformuj administratora."
});

Object.assign(TRANSLATIONS.fr, {
  appTitle: "Control Pass Mobile",
  appLead: "Votre badge, votre trajet et votre accès au chantier en un seul endroit.",
  installBtn: "Installer l'application",
  installHint: "Optimisée pour iPhone et Android. Installez l'application pour un accès rapide au tourniquet.",
  online: "En ligne",
  offline: "Hors ligne",
  loginKicker: "Accès direct",
  loginTitle: "Activer le badge numérique",
  loginCopy: "Vous pouvez activer le badge via le lien employé ou directement avec votre Badge-ID.",
  loginTokenLabel: "Code lien ou Badge-ID",
  loginTokenPlaceholder: "Token du lien ou BP-...",
  loginPinLabel: "Badge-PIN",
  loginPinPlaceholder: "PIN de 4 à 8 chiffres",
  loginBtn: "Charger le badge",
  tipBadge: "Badge-ID + PIN au lieu du QR",
  tipHome: "Fonctionne comme app écran d'accueil",
  tipRoute: "Itinéraire direct vers le chantier",
  workerPassSubLabel: "Badge employé",
  workerCardTitle: "Votre badge pour aujourd'hui",
  fieldBadgeId: "Badge-ID",
  fieldValidUntil: "Valide jusqu'au",
  fieldSite: "Chantier",
  routeTodayTitle: "Site du jour",
  menuKicker: "Menu",
  menuTitle: "Vos sections",
  sessionKicker: "Session",
  sessionTitle: "Badge du jour",
  actionsKicker: "Actions",
  actionsTitle: "Accès rapide",
  leaveRequestKicker: "Absence",
  leaveRequestTitle: "Demande de congé",
  leaveRequestTypeLabel: "Type",
  leaveTypeVacation: "Congé",
  leaveTypeSick: "Maladie",
  leaveTypeOther: "Autre",
  leaveRequestStartLabel: "Du",
  leaveRequestEndLabel: "Au",
  leaveRequestNoteLabel: "Note",
  leaveRequestNotePlaceholder: "Optionnel",
  leaveRequestSubmitBtn: "Envoyer la demande",
  leaveRequestNewBtn: "+ Nouvelle demande",
  notificationBannerText: "Activer les notifications pour les rappels de sortie ?",
  notificationEnableBtn: "Activer",
  timesheetKicker: "Temps de travail",
  timesheetTitle: "Mes heures",
  timesheetCardTitle: "Entrées et horaires",
  timesheetLoading: "Chargement des entrées...",
  documentsKicker: "Documents",
  documentsTitle: "Mes documents",
  documentsLoading: "Chargement des documents...",
  pageBackBtn: "← Aperçu",
  lateCheckInMessage: "Attention : vous vous êtes enregistré en retard aujourd'hui !",
  lateMinutesUnit: "min.",
  visitorMetaKicker: "Visite",
  visitorMetaTitle: "Détails de visite",
  fieldVisitorCompany: "Entreprise invitée",
  fieldVisitPurpose: "Motif de visite",
  fieldHostName: "Contact sur site",
  fieldVisitEndAt: "Visite jusqu'à",
  dayCardValidToday: "Valide aujourd'hui",
  autoOpenScannerLabel: "Ouvrir automatiquement le scanner à l'expiration",
  gateBtn: "Mode tourniquet",
  changePhotoBtn: "Changer la photo",
  logoutBtn: "Se déconnecter",
  cameraRotate: "Tourner",
  cameraDelete: "Supprimer",
  cameraTakePhoto: "Prendre une photo",
  cameraConfirm: "Utiliser",
  cameraRetake: "Reprendre",
  cameraCancel: "Annuler",
  gateModeActive: "Mode tourniquet actif - maintenir le QR sous le scanner",
  gateBrightnessHint: "⚠ Réglez la luminosité au maximum pour un scan rapide.",
  gateQrAlt: "QR d'accès",
  qrContrastOff: "QR haute contraste : désactivé",
  close: "Fermer",
  pinLockMessage: "Votre badge a été verrouillé. Veuillez saisir votre Badge-PIN pour continuer.",
  pinLockBtn: "Déverrouiller le badge",
  pinLockLogout: "Déconnexion",
  quickMenuPass: "Pass",
  quickMenuActions: "Actions",
  quickMenuRequest: "Demande",
  quickMenuHours: "Heures",
  quickMenuDocs: "Docs",
  leaveBalanceDaysRemaining: "jours restants",
  topStatPass: "Pass",
  topStatDigital: "Numérique",
  topStatSync: "Sync",
  topStatInstant: "Immédiat",
  lastSyncInitial: "Dernière synchronisation : -",
  statusActiveShort: "Actif",
  qrCodeAlt: "Code QR",
  workerPhotoAlt: "Photo du salarié",
  workerDefaultRole: "Rôle",
  companyDefaultName: "Entreprise",
  workerPageDefault: "Section",
  workerPageOpened: "Ouvert : {page}",
  offlineLoginOnSiteOnly: "Connexion hors ligne possible uniquement sur le chantier. Environ {meters} m de distance actuellement.",
  offlineLoginActiveWaitingSync: "Connexion hors ligne active. En attente de synchronisation ultérieure.",
  browserPushNotSupported: "Les notifications push ne sont pas prises en charge par votre navigateur.",
  notificationsAlreadyEnabled: "Les notifications sont déjà activées.",
  notificationsEnabled: "Notifications activées !",
  quickMenuAria: "Navigation rapide",
  languageSelectAria: "Choisir la langue",
  qrLinkUsedEnterPin: "Ce lien QR a déjà été utilisé. Veuillez saisir votre PIN.",
  qrLinkInvalidRescan: "Lien QR invalide ou déjà utilisé. Veuillez scanner à nouveau le QR code.",
  leaveDateRangeInvalid: "La date de début doit être antérieure à la date de fin.",
  leaveRequestSubmitted: "✓ Demande de congé envoyée",
  aiSuggestionInserted: "✓ Suggestion IA insérée",
  submitRequestFirst: "Veuillez d'abord envoyer une demande.",
  enterValidManagerEmail: "Veuillez saisir une adresse e-mail valide du responsable.",
  voiceNotSupported: "La commande vocale n'est pas prise en charge par votre navigateur.",
  voiceNeedsSecureContext: "La commande vocale nécessite HTTPS ou localhost.",
  voiceListening: "🎤 Écoute...",
  microphoneAccessBlocked: "L'accès au micro a été bloqué. Veuillez autoriser la permission du navigateur.",
  noSpeechDetected: "Aucune voix détectée. Veuillez réessayer."
});

Object.assign(TRANSLATIONS.es, {
  appTitle: "Control Pass Mobile",
  appLead: "Tu credencial, tu ruta y tu acceso a obra en un solo lugar.",
  installBtn: "Instalar aplicación",
  installHint: "Optimizada para iPhone y Android. Instala la app para acceso rápido al torniquete.",
  online: "En línea",
  offline: "Sin conexión",
  loginKicker: "Acceso directo",
  loginTitle: "Activar credencial digital",
  loginCopy: "Puedes activar la credencial con el enlace del trabajador o con tu Badge-ID.",
  loginTokenLabel: "Código de enlace o Badge-ID",
  loginTokenPlaceholder: "Token del enlace o BP-...",
  loginPinLabel: "Badge-PIN",
  loginPinPlaceholder: "PIN de 4 a 8 dígitos",
  loginBtn: "Cargar credencial",
  tipBadge: "Badge-ID + PIN en lugar de QR",
  tipHome: "Funciona como app de pantalla de inicio",
  tipRoute: "Ruta directa a la obra",
  workerPassSubLabel: "Credencial de trabajador",
  workerCardTitle: "Tu credencial de hoy",
  fieldBadgeId: "Badge-ID",
  fieldValidUntil: "Válido hasta",
  fieldSite: "Obra",
  routeTodayTitle: "Ubicación de hoy",
  menuKicker: "Menú",
  menuTitle: "Tus secciones",
  sessionKicker: "Sesión",
  sessionTitle: "Pase diario",
  actionsKicker: "Acciones",
  actionsTitle: "Acceso rápido",
  leaveRequestKicker: "Ausencia",
  leaveRequestTitle: "Solicitud de vacaciones",
  leaveRequestTypeLabel: "Tipo",
  leaveTypeVacation: "Vacaciones",
  leaveTypeSick: "Baja médica",
  leaveTypeOther: "Otro",
  leaveRequestStartLabel: "Desde",
  leaveRequestEndLabel: "Hasta",
  leaveRequestNoteLabel: "Nota",
  leaveRequestNotePlaceholder: "Opcional",
  leaveRequestSubmitBtn: "Enviar solicitud",
  leaveRequestNewBtn: "+ Nueva solicitud",
  notificationBannerText: "¿Activar notificaciones para recordatorios de salida?",
  notificationEnableBtn: "Activar",
  timesheetKicker: "Registro horario",
  timesheetTitle: "Mis horas",
  timesheetCardTitle: "Entradas y horarios",
  timesheetLoading: "Cargando registros...",
  documentsKicker: "Documentos",
  documentsTitle: "Mis documentos",
  documentsLoading: "Cargando documentos...",
  pageBackBtn: "← Resumen",
  lateCheckInMessage: "Aviso: ¡hoy has fichado tarde!",
  lateMinutesUnit: "min.",
  visitorMetaKicker: "Visita",
  visitorMetaTitle: "Detalles de visita",
  fieldVisitorCompany: "Empresa invitada",
  fieldVisitPurpose: "Motivo de visita",
  fieldHostName: "Contacto en obra",
  fieldVisitEndAt: "Visita hasta",
  dayCardValidToday: "Válido hoy",
  autoOpenScannerLabel: "Abrir escáner automáticamente al expirar",
  gateBtn: "Modo torniquete",
  changePhotoBtn: "Cambiar foto",
  logoutBtn: "Cerrar sesión",
  cameraRotate: "Girar",
  cameraDelete: "Eliminar",
  cameraTakePhoto: "Tomar foto",
  cameraConfirm: "Usar",
  cameraRetake: "Repetir",
  cameraCancel: "Cancelar",
  gateModeActive: "Modo torniquete activo - mantén el QR bajo el escáner",
  gateBrightnessHint: "⚠ Ajusta el brillo al máximo para un escaneo rápido.",
  gateQrAlt: "QR de acceso",
  qrContrastOff: "QR alto contraste: desactivado",
  close: "Cerrar",
  pinLockMessage: "Esta credencial fue bloqueada. Introduce tu Badge-PIN para continuar.",
  pinLockBtn: "Desbloquear credencial",
  pinLockLogout: "Cerrar sesión",
  quickMenuPass: "Pase",
  quickMenuActions: "Acciones",
  quickMenuRequest: "Solicitud",
  quickMenuHours: "Horas",
  quickMenuDocs: "Docs",
  leaveBalanceDaysRemaining: "días restantes",
  topStatPass: "Pase",
  topStatDigital: "Digital",
  topStatSync: "Sync",
  topStatInstant: "Al instante",
  lastSyncInitial: "Última sincronización: -",
  statusActiveShort: "Activo",
  qrCodeAlt: "Código QR",
  workerPhotoAlt: "Foto del trabajador",
  workerDefaultRole: "Rol",
  companyDefaultName: "Empresa",
  workerPageDefault: "Sección",
  workerPageOpened: "Abierto: {page}",
  offlineLoginOnSiteOnly: "El inicio de sesión sin conexión solo es posible en la obra. Actualmente estás a unos {meters} m.",
  offlineLoginActiveWaitingSync: "Inicio de sesión sin conexión activo. Esperando sincronización posterior.",
  browserPushNotSupported: "Tu navegador no admite notificaciones push.",
  notificationsAlreadyEnabled: "Las notificaciones ya están activadas.",
  notificationsEnabled: "¡Notificaciones activadas!",
  quickMenuAria: "Navegación rápida",
  languageSelectAria: "Seleccionar idioma",
  qrLinkUsedEnterPin: "Este enlace QR ya fue usado. Introduce tu PIN.",
  qrLinkInvalidRescan: "Enlace QR inválido o ya usado. Escanea de nuevo el código QR.",
  leaveDateRangeInvalid: "La fecha de inicio debe ser anterior a la fecha de fin.",
  leaveRequestSubmitted: "✓ Solicitud de vacaciones enviada",
  aiSuggestionInserted: "✓ Sugerencia IA insertada",
  submitRequestFirst: "Primero envía una solicitud.",
  enterValidManagerEmail: "Introduce un correo válido del responsable.",
  voiceNotSupported: "El control por voz no es compatible con tu navegador.",
  voiceNeedsSecureContext: "El control por voz requiere HTTPS o localhost.",
  voiceListening: "🎤 Escuchando...",
  microphoneAccessBlocked: "El acceso al micrófono fue bloqueado. Permite el permiso del navegador.",
  noSpeechDetected: "No se detectó voz. Inténtalo de nuevo."
});

Object.assign(TRANSLATIONS.it, {
  appTitle: "Control Pass Mobile",
  appLead: "Il tuo badge, il tuo percorso e l'accesso al cantiere in un unico posto.",
  installBtn: "Installa app",
  installHint: "Ottimizzata per iPhone e Android. Installa l'app per accesso rapido al tornello.",
  online: "Online",
  offline: "Offline",
  loginKicker: "Accesso rapido",
  loginTitle: "Attiva badge digitale",
  loginCopy: "Puoi attivare il badge con il link lavoratore o con il tuo Badge-ID.",
  loginTokenLabel: "Codice link o Badge-ID",
  loginTokenPlaceholder: "Token dal link o BP-...",
  loginPinLabel: "Badge-PIN",
  loginPinPlaceholder: "PIN da 4 a 8 cifre",
  loginBtn: "Carica badge",
  tipBadge: "Badge-ID + PIN invece del QR",
  tipHome: "Funziona come app home screen",
  tipRoute: "Percorso diretto al cantiere",
  workerPassSubLabel: "Badge lavoratore",
  workerCardTitle: "Il tuo badge di oggi",
  fieldBadgeId: "Badge-ID",
  fieldValidUntil: "Valido fino al",
  fieldSite: "Cantiere",
  routeTodayTitle: "Posizione di oggi",
  menuKicker: "Menu",
  menuTitle: "Le tue sezioni",
  sessionKicker: "Sessione",
  sessionTitle: "Pass giornaliero",
  actionsKicker: "Azioni",
  actionsTitle: "Accesso rapido",
  leaveRequestKicker: "Assenza",
  leaveRequestTitle: "Richiesta ferie",
  leaveRequestTypeLabel: "Tipo",
  leaveTypeVacation: "Ferie",
  leaveTypeSick: "Malattia",
  leaveTypeOther: "Altro",
  leaveRequestStartLabel: "Da",
  leaveRequestEndLabel: "A",
  leaveRequestNoteLabel: "Nota",
  leaveRequestNotePlaceholder: "Facoltativo",
  leaveRequestSubmitBtn: "Invia richiesta",
  leaveRequestNewBtn: "+ Nuova richiesta",
  notificationBannerText: "Attivare notifiche per promemoria checkout?",
  notificationEnableBtn: "Attiva",
  timesheetKicker: "Presenze",
  timesheetTitle: "Le mie ore",
  timesheetCardTitle: "Ingressi e orari",
  timesheetLoading: "Caricamento registrazioni...",
  documentsKicker: "Documenti",
  documentsTitle: "I miei documenti",
  documentsLoading: "Caricamento documenti...",
  pageBackBtn: "← Panoramica",
  lateCheckInMessage: "Avviso: oggi hai timbrato in ritardo!",
  lateMinutesUnit: "min.",
  visitorMetaKicker: "Visita",
  visitorMetaTitle: "Dettagli visita",
  fieldVisitorCompany: "Azienda ospite",
  fieldVisitPurpose: "Motivo visita",
  fieldHostName: "Contatto in cantiere",
  fieldVisitEndAt: "Visita fino a",
  dayCardValidToday: "Valido oggi",
  autoOpenScannerLabel: "Apri scanner automaticamente alla scadenza",
  gateBtn: "Modalità tornello",
  changePhotoBtn: "Cambia foto",
  logoutBtn: "Disconnetti",
  cameraRotate: "Ruota",
  cameraDelete: "Elimina",
  cameraTakePhoto: "Scatta foto",
  cameraConfirm: "Usa",
  cameraRetake: "Riscatta",
  cameraCancel: "Annulla",
  gateModeActive: "Modalità tornello attiva - tieni il QR sotto lo scanner",
  gateBrightnessHint: "⚠ Imposta la luminosità al massimo per una scansione rapida.",
  gateQrAlt: "QR di accesso",
  qrContrastOff: "QR alto contrasto: disattivato",
  close: "Chiudi",
  pinLockMessage: "Questo badge è stato bloccato. Inserisci il tuo Badge-PIN per continuare.",
  pinLockBtn: "Sblocca badge",
  pinLockLogout: "Disconnetti",
  quickMenuPass: "Pass",
  quickMenuActions: "Azioni",
  quickMenuRequest: "Richiesta",
  quickMenuHours: "Ore",
  quickMenuDocs: "Documenti",
  leaveBalanceDaysRemaining: "giorni rimanenti",
  topStatPass: "Pass",
  topStatDigital: "Digitale",
  topStatSync: "Sync",
  topStatInstant: "Immediato",
  lastSyncInitial: "Ultima sincronizzazione: -",
  statusActiveShort: "Attivo",
  qrCodeAlt: "Codice QR",
  workerPhotoAlt: "Foto lavoratore",
  workerDefaultRole: "Ruolo",
  companyDefaultName: "Azienda",
  workerPageDefault: "Sezione",
  workerPageOpened: "Aperto: {page}",
  offlineLoginOnSiteOnly: "Accesso offline possibile solo in cantiere. Attualmente sei a circa {meters} m.",
  offlineLoginActiveWaitingSync: "Accesso offline attivo. In attesa di sincronizzazione successiva.",
  browserPushNotSupported: "Le notifiche push non sono supportate dal tuo browser.",
  notificationsAlreadyEnabled: "Le notifiche sono già attive.",
  notificationsEnabled: "Notifiche attivate!",
  quickMenuAria: "Navigazione rapida",
  languageSelectAria: "Seleziona lingua",
  qrLinkUsedEnterPin: "Questo link QR è già stato usato. Inserisci il PIN.",
  qrLinkInvalidRescan: "Link QR non valido o già usato. Scansiona di nuovo il codice QR.",
  leaveDateRangeInvalid: "La data di inizio deve essere precedente alla data di fine.",
  leaveRequestSubmitted: "✓ Richiesta ferie inviata",
  aiSuggestionInserted: "✓ Suggerimento IA inserito",
  submitRequestFirst: "Invia prima una richiesta.",
  enterValidManagerEmail: "Inserisci un'e-mail valida del responsabile.",
  voiceNotSupported: "Il controllo vocale non è supportato dal tuo browser.",
  voiceNeedsSecureContext: "Il controllo vocale richiede HTTPS o localhost.",
  voiceListening: "🎤 In ascolto...",
  microphoneAccessBlocked: "L'accesso al microfono è stato bloccato. Consenti il permesso del browser.",
  noSpeechDetected: "Nessun parlato rilevato. Riprova."
});

Object.assign(TRANSLATIONS.pl, {
  appTitle: "Control Pass Mobile",
  appLead: "Twoja karta, trasa i dostęp do budowy w jednym miejscu.",
  installBtn: "Zainstaluj aplikację",
  installHint: "Zoptymalizowana dla iPhone i Android. Zainstaluj aplikację dla szybkiego dostępu do bramki.",
  online: "Online",
  offline: "Offline",
  loginKicker: "Szybki start",
  loginTitle: "Aktywuj cyfrową kartę",
  loginCopy: "Możesz aktywować kartę linkiem pracownika lub bezpośrednio przez Badge-ID.",
  loginTokenLabel: "Kod linku lub Badge-ID",
  loginTokenPlaceholder: "Token z linku lub BP-...",
  loginPinLabel: "Badge-PIN",
  loginPinPlaceholder: "PIN 4-8 cyfr",
  loginBtn: "Wczytaj kartę",
  tipBadge: "Badge-ID + PIN zamiast QR",
  tipHome: "Działa jako aplikacja ekranu głównego",
  tipRoute: "Bezpośrednia trasa na budowę",
  workerPassSubLabel: "Karta pracownika",
  workerCardTitle: "Twoja karta na dziś",
  fieldBadgeId: "Badge-ID",
  fieldValidUntil: "Ważna do",
  fieldSite: "Budowa",
  routeTodayTitle: "Lokalizacja dzisiaj",
  menuKicker: "Menu",
  menuTitle: "Twoje sekcje",
  sessionKicker: "Sesja",
  sessionTitle: "Przepustka dzienna",
  actionsKicker: "Akcje",
  actionsTitle: "Szybki dostęp",
  leaveRequestKicker: "Nieobecność",
  leaveRequestTitle: "Wniosek urlopowy",
  leaveRequestTypeLabel: "Typ",
  leaveTypeVacation: "Urlop",
  leaveTypeSick: "Chorobowe",
  leaveTypeOther: "Inne",
  leaveRequestStartLabel: "Od",
  leaveRequestEndLabel: "Do",
  leaveRequestNoteLabel: "Notatka",
  leaveRequestNotePlaceholder: "Opcjonalnie",
  leaveRequestSubmitBtn: "Wyślij wniosek",
  leaveRequestNewBtn: "+ Nowy wniosek",
  notificationBannerText: "Włączyć powiadomienia o przypomnieniach wyjścia?",
  notificationEnableBtn: "Włącz",
  timesheetKicker: "Ewidencja czasu",
  timesheetTitle: "Moje godziny",
  timesheetCardTitle: "Wejścia i czasy",
  timesheetLoading: "Ładowanie wpisów...",
  documentsKicker: "Dokumenty",
  documentsTitle: "Moje dokumenty",
  documentsLoading: "Ładowanie dokumentów...",
  pageBackBtn: "← Podgląd",
  lateCheckInMessage: "Uwaga: dzisiaj zalogowałeś się za późno!",
  lateMinutesUnit: "min.",
  visitorMetaKicker: "Wizyta",
  visitorMetaTitle: "Szczegóły wizyty",
  fieldVisitorCompany: "Firma gościa",
  fieldVisitPurpose: "Cel wizyty",
  fieldHostName: "Kontakt na budowie",
  fieldVisitEndAt: "Wizyta do",
  dayCardValidToday: "Ważna dzisiaj",
  autoOpenScannerLabel: "Automatycznie otwórz skaner przy wygaśnięciu",
  gateBtn: "Tryb bramki",
  changePhotoBtn: "Zmień zdjęcie",
  logoutBtn: "Wyloguj",
  cameraRotate: "Obróć",
  cameraDelete: "Usuń",
  cameraTakePhoto: "Zrób zdjęcie",
  cameraConfirm: "Użyj",
  cameraRetake: "Zrób ponownie",
  cameraCancel: "Anuluj",
  gateModeActive: "Tryb bramki aktywny - trzymaj QR pod skanerem",
  gateBrightnessHint: "⚠ Ustaw maksymalną jasność ekranu dla szybkiego skanowania.",
  gateQrAlt: "QR dostępu",
  qrContrastOff: "QR wysoki kontrast: wyłączony",
  close: "Zamknij",
  pinLockMessage: "Ta karta została zablokowana. Wpisz swój Badge-PIN, aby kontynuować.",
  pinLockBtn: "Odblokuj kartę",
  pinLockLogout: "Wyloguj",
  quickMenuPass: "Karta",
  quickMenuActions: "Akcje",
  quickMenuRequest: "Wniosek",
  quickMenuHours: "Godziny",
  quickMenuDocs: "Dokumenty",
  leaveBalanceDaysRemaining: "dni pozostało",
  topStatPass: "Przepustka",
  topStatDigital: "Cyfrowa",
  topStatSync: "Sync",
  topStatInstant: "Natychmiast",
  lastSyncInitial: "Ostatnia synchronizacja: -",
  statusActiveShort: "Aktywny",
  qrCodeAlt: "Kod QR",
  workerPhotoAlt: "Zdjęcie pracownika",
  workerDefaultRole: "Rola",
  companyDefaultName: "Firma",
  workerPageDefault: "Sekcja",
  workerPageOpened: "Otwarte: {page}",
  offlineLoginOnSiteOnly: "Logowanie offline możliwe tylko na budowie. Obecnie około {meters} m od miejsca.",
  offlineLoginActiveWaitingSync: "Logowanie offline aktywne. Oczekiwanie na późniejszą synchronizację.",
  browserPushNotSupported: "Powiadomienia push nie są obsługiwane przez Twoją przeglądarkę.",
  notificationsAlreadyEnabled: "Powiadomienia są już włączone.",
  notificationsEnabled: "Powiadomienia włączone!",
  quickMenuAria: "Szybka nawigacja",
  languageSelectAria: "Wybierz język",
  qrLinkUsedEnterPin: "Ten link QR został już użyty. Wpisz PIN.",
  qrLinkInvalidRescan: "Link QR jest nieprawidłowy lub już użyty. Zeskanuj kod QR ponownie.",
  leaveDateRangeInvalid: "Data rozpoczęcia musi być wcześniejsza niż data zakończenia.",
  leaveRequestSubmitted: "✓ Wniosek urlopowy wysłany",
  aiSuggestionInserted: "✓ Dodano sugestię AI",
  submitRequestFirst: "Najpierw złóż wniosek.",
  enterValidManagerEmail: "Wpisz poprawny e-mail przełożonego.",
  voiceNotSupported: "Sterowanie głosowe nie jest obsługiwane przez Twoją przeglądarkę.",
  voiceNeedsSecureContext: "Sterowanie głosowe wymaga HTTPS lub localhost.",
  voiceListening: "🎤 Nasłuchiwanie...",
  microphoneAccessBlocked: "Dostęp do mikrofonu został zablokowany. Zezwól na uprawnienie w przeglądarce.",
  noSpeechDetected: "Nie wykryto mowy. Spróbuj ponownie."
});

const LANG_META = {
  de: { label: "DE", flag: "🇩🇪", dir: "ltr" },
  en: { label: "EN", flag: "🇬🇧", dir: "ltr" },
  tr: { label: "TR", flag: "🇹🇷", dir: "ltr" },
  ar: { label: "AR", flag: "🇸🇦", dir: "rtl" },
  fr: { label: "FR", flag: "🇫🇷", dir: "ltr" },
  es: { label: "ES", flag: "🇪🇸", dir: "ltr" },
  it: { label: "IT", flag: "🇮🇹", dir: "ltr" },
  pl: { label: "PL", flag: "🇵🇱", dir: "ltr" },
};

let currentLang = localStorage.getItem(WORKER_LANG_KEY) || "de";
if (!TRANSLATIONS[currentLang]) {
  currentLang = "de";
}

function t(key) {
  return (TRANSLATIONS[currentLang] || TRANSLATIONS.de)[key] || TRANSLATIONS.de[key] || key;
}

function tf(key, vars = {}) {
  let out = t(key);
  Object.entries(vars).forEach(([name, value]) => {
    out = out.replace(new RegExp(`\\{${name}\\}`, "g"), String(value));
  });
  return out;
}

function getCurrentLocale() {
  if (currentLang === "ar") return "ar-SA";
  if (currentLang === "tr") return "tr-TR";
  if (currentLang === "en") return "en-GB";
  if (currentLang === "fr") return "fr-FR";
  if (currentLang === "es") return "es-ES";
  if (currentLang === "it") return "it-IT";
  if (currentLang === "pl") return "pl-PL";
  return "de-DE";
}

function normalizeCompanyBrandingPreset(value) {
  const preset = String(value || "").trim().toLowerCase();
  if (preset === "industry" || preset === "premium") {
    return preset;
  }
  return "construction";
}

function applyTranslations() {
  const lang = currentLang;
  const dir = LANG_META[lang]?.dir || "ltr";
  document.documentElement.lang = lang;
  document.documentElement.dir = dir;
  // Use company brand title (KontrolPass/BauPass) if already loaded, otherwise fallback to i18n key
  const brandPrefix = currentAppBrandTitle || "";
  document.title = brandPrefix ? brandPrefix + " – " + t("pageTitle") : t("pageTitle");

  const langSelect = document.querySelector("#workerLanguageSelect");
  if (langSelect && langSelect.value !== lang) {
    langSelect.value = lang;
  }

  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.dataset.i18n;
    const attr = el.dataset.i18nAttr;
    // Skip brand title elements – managed dynamically by renderWorker()
    if (!attr && el.id && ["workerAppTitle", "workerBrandChip", "workerSplashTitle", "workerBrandName"].includes(el.id)) {
      return;
    }
    if (attr) {
      el.setAttribute(attr, t(key));
    } else {
      el.textContent = t(key);
    }
  });
  // Re-apply company brand label after translations (preserves KontrolPass / BauPass)
  if (currentAppBrandTitle) {
    const appTitleEl = document.getElementById("workerAppTitle");
    if (appTitleEl) appTitleEl.textContent = currentAppBrandTitle;
    const brandChipEl = document.getElementById("workerBrandChip");
    if (brandChipEl) brandChipEl.textContent = currentAppBrandTitle;
    const splashTitleEl = document.getElementById("workerSplashTitle");
    if (splashTitleEl) splashTitleEl.textContent = currentAppBrandTitle;
    const brandNameEl = document.getElementById("workerBrandName");
    if (brandNameEl) brandNameEl.textContent = currentAppBrandTitle.toUpperCase();
  }
  updateWorkerHubToggleLabel();
}

function setLang(lang) {
  if (!TRANSLATIONS[lang]) return;
  currentLang = lang;
  localStorage.setItem(WORKER_LANG_KEY, lang);
  applyTranslations();
  updateConnectionState();
  updatePlatformInstallHint();
  applyQrContrastState();
  if (workerToken) {
    void loadWorkerData();
  }
}
// ─────────────────────────────────────────────────────────────────────

let workerToken = localStorage.getItem(WORKER_TOKEN_KEY) || "";
let deferredInstallPrompt = null;
let cameraStream = null;
let lastCameraPhotoDataUrl = null;
let lastCameraPhotoRotation = 0;
let wakeLockHandle = null;
let dynamicManifestUrl = "";
let currentAppBrandTitle = ""; // tracks the company-specific brand label (KontrolPass / BauPass)
let workerSessionExpiryTimeout = null;
let workerSessionCountdownInterval = null;
let visitorCountdownInterval = null;
let inactivityCheckInterval = null;
let qrHighContrastEnabled = localStorage.getItem(QR_HIGH_CONTRAST_KEY) === "1";
let sessionExpiringSoonNotified = false;
let ambientLightSensorHandle = null;
let ambientLowLightRecommended = false;
let gateAutoOpenTriggered = false;
let lastUserInteractionAt = Date.now();
let autoOpenScannerEnabled = localStorage.getItem(AUTO_OPEN_SCANNER_KEY) !== "0";
let offlineWorkerSessionActive = false;
let pinLockEnabled = false; // Wird vom Backend gesetzt
let isPassLocked = false; // Aktueller Status
let lastPassInteractionAt = Date.now();
let passLockTimer = null;
let lastSubmittedLeaveRequestId = "";
let leaveRefreshInterval = null;
let quickMenuObserver = null;
let activeWorkerPageTarget = "";
let iosWalletImmersive = false;
let workerHubExpanded = false;
let timesheetCompactExpanded = false;
let documentsCompactExpanded = false;
let leaveCompactExpanded = false;
// ── Dynamic QR state ─────────────────────────────────────────────────────────
let dqrInterval = null;          // setInterval handle for auto-refresh
let dqrCountdownInterval = null; // setInterval for per-second countdown
let dqrRemainingSeconds = 60;    // seconds until next QR refresh
let dqrCurrentToken = "";        // last fetched DQR token
let dqrWorkerBadgeId = "";       // fallback static badge id
let dqrWindowSeconds = 60;        // full token lifetime window from backend
let dqrRefreshTimeout = null;     // adaptive refresh timer
let gateFeedbackResetTimeout = null;
let gateEventPollTimeout = null;
let gateEventPollInFlight = false;
let gateLastSeenEventId = "";

const AUTO_OPEN_ACTIVITY_WINDOW_MS = 30 * 1000;

const elements = {
  loginCard: document.querySelector("#loginCard"),
  badgeCard: document.querySelector("#badgeCard"),
  workerNotice: document.querySelector("#workerNotice"),
  workerLoginForm: document.querySelector("#workerLoginForm"),
  workerAccessToken: document.querySelector("#workerAccessToken"),
  workerBadgePin: document.querySelector("#workerBadgePin"),
  companyName: document.querySelector("#companyName"),
    workerSubcompany: document.querySelector("#workerSubcompany"),
  workerName: document.querySelector("#workerName"),
  workerRole: document.querySelector("#workerRole"),
  workerPassTitle: document.querySelector("#workerPassTitle"),
  workerPassSubLabels: document.querySelectorAll("[data-pass-sub-label]"),
  walletCard: document.querySelector(".wallet-card"),
  workerStatus: document.querySelector("#workerStatus"),
  workerPhoto: document.querySelector("#workerPhoto"),
  workerBadgeId: document.querySelector("#workerBadgeId"),
  workerSite: document.querySelector("#workerSite"),
  workerSiteMapLink: document.querySelector("#workerSiteMapLink"),
  workerValidUntil: document.querySelector("#workerValidUntil"),
  workerDayCardValidity: document.querySelector("#workerDayCardValidity"),
  workerVisitorMeta: document.querySelector("#workerVisitorMeta"),
  workerVisitorCompany: document.querySelector("#workerVisitorCompany"),
  workerVisitPurpose: document.querySelector("#workerVisitPurpose"),
  workerHostName: document.querySelector("#workerHostName"),
  workerVisitEndAt: document.querySelector("#workerVisitEndAt"),
  workerQr: document.querySelector("#workerQr"),
  workerSessionCountdown: document.querySelector("#workerSessionCountdown"),
  autoOpenScannerToggle: document.querySelector("#autoOpenScannerToggle"),
  qrContrastToggle: document.querySelector("#qrContrastToggle"),
  qrFallbackText: document.querySelector("#qrFallbackText"),
  refreshButton: document.querySelector("#refreshButton"),
  logoutButton: document.querySelector("#logoutButton"),
  installButton: document.querySelector("#installButton"),
  installPlatformHint: document.querySelector("#installPlatformHint"),
  gateModeButton: document.querySelector("#gateModeButton"),
  quickGateModeButton: document.querySelector("#quickGateModeButton"),
  gateScannerOverlay: document.querySelector("#gateScannerOverlay"),
  gateQr: document.querySelector("#gateQr"),
  gateBadgeId: document.querySelector("#gateBadgeId"),
  gateWorkerName: document.querySelector("#gateWorkerName"),
  gateBrightnessHint: document.querySelector("#gateBrightnessHint"),
  closeGateModeButton: document.querySelector("#closeGateModeButton"),
  changePhotoButton: document.querySelector("#changePhotoButton"),
  photoInput: document.querySelector("#photoInput"),
  cameraOverlay: document.querySelector("#cameraOverlay"),
  cameraVideo: document.querySelector("#cameraVideo"),
  cameraCanvas: document.querySelector("#cameraCanvas"),
  takePhotoButton: document.querySelector("#takePhotoButton"),
  confirmPhotoButton: document.querySelector("#confirmPhotoButton"),
  retakePhotoButton: document.querySelector("#retakePhotoButton"),
  closeCameraButton: document.querySelector("#closeCameraButton"),
  photoPreviewWrap: document.querySelector("#photoPreviewWrap"),
  rotatePhotoButton: document.querySelector("#rotatePhotoButton"),
  deletePhotoButton: document.querySelector("#deletePhotoButton"),
  workerStatusBanner: document.querySelector("#workerStatusBanner"),
  workerStatusText: document.querySelector("#workerStatusText"),
  gateStatusFeedback: document.querySelector("#gateStatusFeedback"),
  gateContrastToggle: document.querySelector("#gateContrastToggle"),
  connectionBanner: document.querySelector("#connectionBanner"),
  lastSyncInfo: document.querySelector("#lastSyncInfo"),
  pinLockOverlay: document.querySelector("#pinLockOverlay"),
  pinLockForm: document.querySelector("#pinLockForm"),
  pinLockInput: document.querySelector("#pinLockInput"),
  pinLockError: document.querySelector("#pinLockError"),
  pinLockLogoutButton: document.querySelector("#pinLockLogoutButton"),
  geolocationHint: document.querySelector("#geolocationHint"),
  themeToggleBtn: document.querySelector("#themeToggleBtn"),
  voiceCommandBtn: document.querySelector("#voiceCommandBtn"),
  notificationPermissionBtn: document.querySelector("#notificationPermissionBtn"),
  enableNotificationsBtn: document.querySelector("#enableNotificationsBtn"),
  notificationBanner: document.querySelector("#notificationBanner"),
  leaveRequestCard: document.querySelector("#leaveRequestCard"),
  leaveRequestForm: document.querySelector("#leaveRequestForm"),
  leaveRequestFormWrapper: document.querySelector("#leaveRequestFormWrapper"),
  leaveRequestListWrapper: document.querySelector("#leaveRequestListWrapper"),
  leaveRequestList: document.querySelector("#leaveRequestList"),
  leaveRequestToggleBtn: document.querySelector("#leaveRequestToggleBtn"),
  leaveRequestType: document.querySelector("#leaveRequestType"),
  leaveRequestStart: document.querySelector("#leaveRequestStart"),
  leaveRequestEnd: document.querySelector("#leaveRequestEnd"),
  leaveRequestNote: document.querySelector("#leaveRequestNote"),
  leaveRequestAiBtn: document.querySelector("#leaveRequestAiBtn"),
  leaveRequestBossEmail: document.querySelector("#leaveRequestBossEmail"),
  workerHubToggle: document.querySelector("#workerHubToggle"),
  workerHubPanel: document.querySelector("#workerHubPanel"),
  workerQuickMenu: document.querySelector("#workerQuickMenu"),
  quickMenuButtons: document.querySelectorAll(".quick-menu-btn"),
  workerMenuButtons: document.querySelectorAll("[data-worker-page-target]"),
  workerPageNav: document.querySelector("#workerPageNav"),
  workerPageBackButton: document.querySelector("#workerPageBackButton"),
  workerPageLabel: document.querySelector("#workerPageLabel"),
  visitorCountdownBanner: document.querySelector("#visitorCountdownBanner"),
  visitorCountdownTime: document.querySelector("#visitorCountdownTime"),
  sendToBossPanel: document.querySelector("#sendToBossPanel"),
  bossEmailInput: document.querySelector("#bossEmailInput"),
  sendToBossBtn: document.querySelector("#sendToBossBtn"),
  timesheetCard: document.querySelector("#timesheetCard"),
  timesheetList: document.querySelector("#timesheetList"),
  timesheetRefreshBtn: document.querySelector("#timesheetRefreshBtn"),
  documentsCard: document.querySelector("#documentsCard"),
  documentsList: document.querySelector("#documentsList")
};

const splashStartedAt = performance.now();
const SPLASH_MIN_MS = 1050;

function dismissSplash() {
  const elapsed = performance.now() - splashStartedAt;
  const delay = Math.max(0, SPLASH_MIN_MS - elapsed);
  setTimeout(() => {
    document.body.classList.add("splash-released");
    const el = document.getElementById("splashScreen");
    if (!el) return;
    el.classList.add("splash-done");
    el.addEventListener("transitionend", () => el.remove(), { once: true });
    setTimeout(() => { if (el.parentNode) el.remove(); }, 800);
  }, delay);
}

// ── Globale User-Interaktions-Tracking-Funktion ──
function markUserInteraction() {
  lastUserInteractionAt = Date.now();
}

function isIosDevice() {
  const ua = navigator.userAgent || "";
  return /iPhone|iPad|iPod/i.test(ua);
}

function isStandaloneDisplay() {
  return Boolean(window.matchMedia?.("(display-mode: standalone)")?.matches) || Boolean(window.navigator.standalone);
}

function updateWalletImmersiveMode() {
  iosWalletImmersive = isIosDevice() && isStandaloneDisplay() && Boolean(workerToken);
  document.body.classList.toggle("wallet-immersive", iosWalletImmersive);
  if (iosWalletImmersive) {
    applyWorkerPageView("badgeCard");
  }
}

function setActiveQuickMenuTarget(targetId) {
  if (!elements.quickMenuButtons?.length) return;
  elements.quickMenuButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.getAttribute("data-scroll-target") === targetId);
  });
}

function updateWorkerHubToggleLabel() {
  if (!elements.workerHubToggle) return;
  elements.workerHubToggle.textContent = workerHubExpanded ? t("workerHubHideBtn") : t("workerHubShowBtn");
}

function setWorkerHubExpanded(expanded, options = {}) {
  const shouldExpand = Boolean(expanded);
  workerHubExpanded = shouldExpand;
  document.body.classList.toggle("wallet-immersive-sections-open", shouldExpand);
  if (elements.workerHubPanel) {
    elements.workerHubPanel.classList.toggle("hidden", !shouldExpand);
  }
  updateWorkerHubToggleLabel();
  if (options.scrollToPanel && shouldExpand && elements.workerHubPanel) {
    elements.workerHubPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function getWorkerPageTitle(targetId) {
  if (targetId === "routeCard") return t("routeTodayTitle");
  if (targetId === "sessionInfoCard") return t("sessionTitle");
  if (targetId === "actionsPanel") return t("actionsTitle");
  if (targetId === "leaveRequestCard") return t("leaveRequestTitle");
  if (targetId === "timesheetCard") return t("timesheetCardTitle");
  if (targetId === "documentsCard") return t("documentsTitle");
  if (targetId === "workerVisitorMeta") return t("visitorMetaTitle");
  return t("workerPageDefault");
}

function getWorkerPageSections() {
  return [
    document.querySelector("#routeCard"),
    elements.workerVisitorMeta,
    document.querySelector("#sessionInfoCard"),
    document.querySelector("#actionsPanel"),
    elements.leaveRequestCard,
    elements.timesheetCard,
    elements.documentsCard,
  ].filter(Boolean);
}

function applyWorkerPageView(targetId = "") {
  const sections = getWorkerPageSections();
  const useFocusMode = Boolean(targetId);
  const useTileOverview = document.body.classList.contains("worker-loaded");
  activeWorkerPageTarget = useFocusMode ? targetId : "";

  if (!useFocusMode) {
    if (useTileOverview) {
      document.body.classList.add("worker-tile-overview");
    }
    sections.forEach((section) => {
      if (useTileOverview) {
        section.classList.add("hidden");
        delete section.dataset.pageWasVisible;
      } else if (section.dataset.pageWasVisible !== undefined) {
        section.classList.toggle("hidden", section.dataset.pageWasVisible !== "1");
        delete section.dataset.pageWasVisible;
      }
      section.classList.remove("worker-page-active");
    });

    if (elements.workerPageNav) {
      elements.workerPageNav.classList.add("hidden");
    }
    if (elements.workerPageLabel) {
      elements.workerPageLabel.textContent = "";
    }
    return;
  }

  sections.forEach((section) => {
    if (section.dataset.pageWasVisible === undefined) {
      section.dataset.pageWasVisible = section.classList.contains("hidden") ? "0" : "1";
    }
    const shouldShow = section.id === targetId;
    section.classList.toggle("hidden", !shouldShow);
    section.classList.toggle("worker-page-active", shouldShow);
  });

  if (elements.workerPageNav) {
    elements.workerPageNav.classList.remove("hidden");
  }
  document.body.classList.remove("worker-tile-overview");
  if (elements.workerPageLabel) {
    elements.workerPageLabel.textContent = tf("workerPageOpened", { page: getWorkerPageTitle(targetId) });
  }
}

function initQuickMenuObserver() {
  if (!elements.quickMenuButtons?.length || typeof IntersectionObserver === "undefined") return;
  if (quickMenuObserver) {
    quickMenuObserver.disconnect();
  }
  const targets = ["badgeCard", "actionsPanel", "leaveRequestCard", "timesheetCard", "documentsCard"];
  quickMenuObserver = new IntersectionObserver((entries) => {
    const visible = entries
      .filter((entry) => entry.isIntersecting)
      .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
    if (visible.length > 0) {
      setActiveQuickMenuTarget(visible[0].target.id);
    }
  }, { threshold: [0.25, 0.5, 0.75], rootMargin: "-20% 0px -45% 0px" });

  targets.forEach((id) => {
    const el = document.getElementById(id);
    if (el) quickMenuObserver.observe(el);
  });
}

init().finally(dismissSplash);

async function init() {
  applyTranslations();
  bindEvents();
  updateWalletImmersiveMode();
  applyQrContrastState();
  applyAutoOpenScannerState();
  
  // Enable Dark Mode support
  if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
    document.documentElement.style.colorScheme = "dark";
  }
  
  const params = new URL(window.location.href).searchParams;
  const urlToken = (params.get("access") || "").trim();
  const viewParam = (params.get("view") || "").trim().toLowerCase();
  const urlBadgeParam = normalizeBadgeIdInput(params.get("badge") || "");
  const storedAccessToken = (window.localStorage.getItem(WORKER_ACCESS_TOKEN_KEY) || "").trim();
  const storedBadgeId = (window.localStorage.getItem(WORKER_BADGE_LOGIN_KEY) || "").trim();
  const bootstrapAccessToken = urlToken || storedAccessToken;

  if (bootstrapAccessToken) {
    window.localStorage.setItem(WORKER_ACCESS_TOKEN_KEY, bootstrapAccessToken);
    applyDynamicManifestStartUrl(bootstrapAccessToken);
  }

  registerWorkerSw();
  wireInstallPrompt();
  updateConnectionState();

  if (urlToken) {
    if (elements.workerAccessToken) {
      elements.workerAccessToken.value = urlToken;
    }
    // If already logged in with a valid session, just use it (token may be already used)
    if (workerToken) {
      const loaded = await loadWorkerData();
      if (loaded) {
        if (viewParam === "card") applyWorkerPageView("badgeCard");
        return;
      }
    }
    const locationPayload = await resolveLoginLocation();
    // keepUrlToken: false → URL wird sofort bereinigt, damit ein Seitenrefresh
    // nicht denselben (bereits verbrauchten) Einmalcode nochmals sendet.
    await loginWithAccessToken(urlToken, { keepUrlToken: false, silent: false, locationPayload });
    if (viewParam === "card" && workerToken) applyWorkerPageView("badgeCard");
    return;
  }

  if (workerToken) {
    const loaded = await loadWorkerData();
    if (loaded) {
      applyWorkerPageView("badgeCard");
      return;
    }
  }

  if (storedAccessToken) {
    if (elements.workerAccessToken) {
      elements.workerAccessToken.value = storedAccessToken;
    }
    const locationPayload = await resolveLoginLocation();
    await loginWithAccessToken(storedAccessToken, { keepUrlToken: false, silent: true, locationPayload });
    if (workerToken) {
      applyWorkerPageView("badgeCard");
      return;
    }
  }

  // ?badge=WRK-001 → permanent QR code that pre-fills badge ID and focuses PIN
  if (urlBadgeParam) {
    // If already logged in with a valid session, just go to card
    if (workerToken) {
      const loaded = await loadWorkerData();
      if (loaded) {
        if (viewParam === "card") applyWorkerPageView("badgeCard");
        return;
      }
    }
    // Pre-fill badge ID and let worker enter PIN
    localStorage.setItem(WORKER_BADGE_LOGIN_KEY, urlBadgeParam);
    if (elements.workerAccessToken) {
      elements.workerAccessToken.value = urlBadgeParam;
    }
    const pinWrapper = document.querySelector("#pinFieldWrapper");
    if (pinWrapper && !isVisitorBadgeId(urlBadgeParam)) {
      pinWrapper.classList.remove("hidden");
      const pinInput = document.querySelector("#workerBadgePin");
      if (pinInput) setTimeout(() => pinInput.focus(), 120);
    }
    return;
  }

  if (storedBadgeId) {
    if (elements.workerAccessToken) {
      elements.workerAccessToken.value = normalizeBadgeIdInput(storedBadgeId);
      const pinWrapper = document.querySelector("#pinFieldWrapper");
      if (pinWrapper && !isVisitorBadgeId(storedBadgeId)) pinWrapper.classList.remove("hidden");
    }
  }
}

function applyDynamicManifestStartUrl(accessToken, platformName) {
  const manifestLink = document.querySelector('link[rel="manifest"]');
  if (!manifestLink || !accessToken) {
    return;
  }

  fetch(`./worker-manifest.json?v=${WORKER_BUILD_TAG}`, { cache: "no-store" })
    .then((response) => response.json())
    .then((manifest) => {
      const params = new URLSearchParams();
      params.set("access", accessToken);

      const apiBaseParam = new URL(window.location.href).searchParams.get("apiBase");
      if (apiBaseParam) {
        params.set("apiBase", apiBaseParam);
      }

      manifest.start_url = `/worker.html?${params.toString()}`;
      // White-label: update manifest names dynamically
      if (platformName) {
        manifest.name = platformName + " – Mitarbeiter";
        manifest.short_name = platformName;
        if (manifest.shortcuts) {
          manifest.shortcuts.forEach((s) => { s.url = `/worker.html?view=card&${params.toString()}`; });
        }
      }

      const blob = new Blob([JSON.stringify(manifest)], { type: "application/manifest+json" });
      if (dynamicManifestUrl) {
        URL.revokeObjectURL(dynamicManifestUrl);
      }
      dynamicManifestUrl = URL.createObjectURL(blob);
      manifestLink.href = dynamicManifestUrl;
    })
    .catch(() => {
      // ignore manifest customization failures
    });
}

function bindEvents() {
  const langSelect = document.querySelector("#workerLanguageSelect");
  if (langSelect) {
    langSelect.value = currentLang;
    langSelect.addEventListener("change", () => setLang(langSelect.value));
  }

  window.addEventListener("online", () => {
    updateConnectionState();
    if (workerToken) {
      void syncOfflinePhotoQueue();
      void syncOfflineEventQueue();
    }
  });
  window.addEventListener("offline", updateConnectionState);
  window.addEventListener("pointerdown", markUserInteraction, { passive: true });
  window.addEventListener("touchstart", markUserInteraction, { passive: true });
  window.addEventListener("keydown", markUserInteraction, { passive: true });
  window.addEventListener("scroll", markUserInteraction, { passive: true });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      markUserInteraction();
      if (workerToken) {
        void requestWakeLock();
        void fetchAndDisplayDynamicQr();
      }
    } else {
      releaseWakeLock();
    }
  });
  window.addEventListener("pageshow", () => {
    updateWalletImmersiveMode();
    if (workerToken) {
      void requestWakeLock();
      void fetchAndDisplayDynamicQr();
    }
  });
  window.addEventListener("pagehide", () => {
    releaseWakeLock();
  });

  if (elements.workerAccessToken) {
    const pinWrapper = document.querySelector("#pinFieldWrapper");
    elements.workerAccessToken.addEventListener("input", () => {
      const rawValue = elements.workerAccessToken.value || "";
      const normalizedCandidate = normalizeBadgeIdInput(rawValue);
      const shouldNormalizeBadgeInput =
        looksLikeBadgeId(normalizedCandidate)
        || /^\s*(BP|VS)[\s\-‐‑–—‒_]/i.test(rawValue);

      if (shouldNormalizeBadgeInput && normalizedCandidate && rawValue !== normalizedCandidate) {
        elements.workerAccessToken.value = normalizedCandidate;
      }

      const val = (elements.workerAccessToken.value || "").trim();
      const needsPin = looksLikeBadgeId(val) && !isVisitorBadgeId(val);
      const isBadge = looksLikeBadgeId(val) && !isVisitorBadgeId(val);
      if (pinWrapper) {
        pinWrapper.classList.toggle("hidden", !needsPin);
        if (!needsPin && elements.workerBadgePin) {
          elements.workerBadgePin.value = "";
        }
      }
      if (elements.geolocationHint) {
        elements.geolocationHint.classList.toggle("hidden", !isBadge);
      }
    });
  }

  if (elements.workerLoginForm) {
    elements.workerLoginForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const credential = (elements.workerAccessToken?.value || "").trim();
      const locationPayload = await resolveLoginLocation();
      if (looksLikeBadgeId(credential)) {
        const badgePin = isVisitorBadgeId(credential) ? "" : (elements.workerBadgePin?.value || "").trim();
        await loginWithBadgeId(credential, badgePin, { locationPayload });
        return;
      }
      await loginWithAccessToken(credential, { locationPayload });
    });
  }

  if (elements.refreshButton) {
    elements.refreshButton.addEventListener("click", loadWorkerData);
  }

  if (elements.logoutButton) {
    elements.logoutButton.addEventListener("click", workerLogout);
  }

  if (elements.installButton) {
    elements.installButton.addEventListener("click", triggerInstall);
  }

  if (elements.gateModeButton) {
    elements.gateModeButton.addEventListener("click", openGateMode);
  }

  if (elements.quickGateModeButton) {
    elements.quickGateModeButton.addEventListener("click", openGateMode);
  }

  if (elements.closeGateModeButton) {
    elements.closeGateModeButton.addEventListener("click", closeGateMode);
  }

  if (elements.qrContrastToggle) {
    elements.qrContrastToggle.addEventListener("click", toggleQrContrastMode);
  }

  if (elements.gateContrastToggle) {
    elements.gateContrastToggle.addEventListener("click", toggleQrContrastMode);
  }

  if (elements.autoOpenScannerToggle) {
    elements.autoOpenScannerToggle.addEventListener("change", () => {
      autoOpenScannerEnabled = Boolean(elements.autoOpenScannerToggle?.checked);
      localStorage.setItem(AUTO_OPEN_SCANNER_KEY, autoOpenScannerEnabled ? "1" : "0");
      applyAutoOpenScannerState();
    });
  }

  if (elements.changePhotoButton) {
    elements.changePhotoButton.addEventListener("click", openCameraOverlay);
  }

  if (elements.photoInput) {
    elements.photoInput.addEventListener("change", handlePhotoSelected);
  }

  if (elements.takePhotoButton) {
    elements.takePhotoButton.addEventListener("click", takePhotoFromCamera);
  }
  if (elements.confirmPhotoButton) {
    elements.confirmPhotoButton.addEventListener("click", confirmCameraPhoto);
  }
  if (elements.retakePhotoButton) {
    elements.retakePhotoButton.addEventListener("click", retakeCameraPhoto);
  }
  if (elements.closeCameraButton) {
    elements.closeCameraButton.addEventListener("click", closeCameraOverlay);
  }
  if (elements.rotatePhotoButton) {
    elements.rotatePhotoButton.addEventListener("click", rotateCameraPhoto);
  }
  if (elements.deletePhotoButton) {
    elements.deletePhotoButton.addEventListener("click", deleteCameraPhoto);
  }

  // ── PIN-Lock Event-Listener ──
  if (elements.pinLockForm) {
    elements.pinLockForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const pin = elements.pinLockInput?.value || "";
      await handlePassLockUnlock(pin);
    });
  }

  if (elements.pinLockLogoutButton) {
    elements.pinLockLogoutButton.addEventListener("click", workerLogout);
  }

  // ── Tracking für Pass-Interaktionen ──
  if (elements.badgeCard) {
    elements.badgeCard.addEventListener("pointerdown", markPassInteraction, { passive: true });
    elements.badgeCard.addEventListener("touchstart", markPassInteraction, { passive: true });
    elements.badgeCard.addEventListener("scroll", markPassInteraction, { passive: true });
  }

  // ── NEW FEATURES EVENT LISTENERS ──
  if (elements.themeToggleBtn) {
    elements.themeToggleBtn.addEventListener("click", toggleTheme);
  }
  
  if (elements.voiceCommandBtn) {
    elements.voiceCommandBtn.addEventListener("click", initVoiceCommands);
  }
  
  if (elements.enableNotificationsBtn) {
    elements.enableNotificationsBtn.addEventListener("click", requestNotificationPermission);
  }
  
  if (elements.leaveRequestToggleBtn) {
    elements.leaveRequestToggleBtn.addEventListener("click", toggleLeaveRequestForm);
  }
  
  if (elements.leaveRequestForm) {
    elements.leaveRequestForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      await submitLeaveRequest();
    });
  }

  if (elements.workerHubToggle) {
    elements.workerHubToggle.addEventListener("click", () => {
      setWorkerHubExpanded(!workerHubExpanded, { scrollToPanel: true });
    });
  }

  if (elements.quickMenuButtons?.length) {
    elements.quickMenuButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const targetId = btn.getAttribute("data-scroll-target") || "";
        if (!targetId) return;
        setActiveQuickMenuTarget(targetId);
        const target = document.getElementById(targetId);
        if (target) {
          target.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    });
  }

  if (elements.workerMenuButtons?.length) {
    elements.workerMenuButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const targetId = btn.getAttribute("data-worker-page-target") || "";
        if (!targetId) return;
        applyWorkerPageView(targetId);
        const target = document.getElementById(targetId);
        if (target) {
          target.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    });
  }

  if (elements.workerPageBackButton) {
    elements.workerPageBackButton.addEventListener("click", () => {
      applyWorkerPageView("");
      const route = document.getElementById("routeCard");
      if (route) {
        route.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  }

  if (elements.leaveRequestAiBtn) {
    elements.leaveRequestAiBtn.addEventListener("click", applyAiLeaveSuggestion);
  }

  // Urlaubstage live berechnen
  const calcDays = () => {
    const start = elements.leaveRequestStart?.value;
    const end = elements.leaveRequestEnd?.value;
    const hint = document.getElementById("leaveDaysHint");
    if (!hint) return;
    if (start && end && end >= start) {
      const days = countWorkingDays(start, end);
      hint.textContent = `${days} Arbeitstag${days !== 1 ? "e" : ""}`;
      hint.className = "leave-days-hint";
    } else {
      hint.textContent = "";
    }
  };
  if (elements.leaveRequestStart) elements.leaveRequestStart.addEventListener("change", calcDays);
  if (elements.leaveRequestEnd) elements.leaveRequestEnd.addEventListener("change", calcDays);

  if (elements.sendToBossBtn) {
    elements.sendToBossBtn.addEventListener("click", async () => {
      await sendLastLeaveRequestToBoss();
    });
  }

  if (elements.timesheetRefreshBtn) {
    elements.timesheetRefreshBtn.addEventListener("click", () => void loadMyTimesheets());
  }

  window.addEventListener("beforeunload", stopCameraStream);
}

function savePhotoToOfflineQueue(dataUrl) {
  let queue = [];
  try {
    queue = JSON.parse(localStorage.getItem(OFFLINE_PHOTO_QUEUE_KEY) || "[]");
  } catch {
    queue = [];
  }
  queue.push({ dataUrl, timestamp: Date.now() });
  localStorage.setItem(OFFLINE_PHOTO_QUEUE_KEY, JSON.stringify(queue));
}

function readStoredJson(key, fallbackValue) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) {
      return fallbackValue;
    }
    return JSON.parse(raw);
  } catch {
    return fallbackValue;
  }
}

function writeStoredJson(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

function resolveExpiryTimestamp(value) {
  if (!value) {
    return Number.POSITIVE_INFINITY;
  }
  const normalized = /^\d{4}-\d{2}-\d{2}$/.test(String(value)) ? `${value}T23:59:59` : value;
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? Number.POSITIVE_INFINITY : parsed.getTime();
}

function isCachedWorkerPayloadUsable(payload) {
  const worker = payload?.worker;
  if (!worker || !worker.badgeId) {
    return false;
  }
  if (resolveExpiryTimestamp(worker.validUntil) < Date.now()) {
    return false;
  }
  if (worker.visitEndAt && resolveExpiryTimestamp(worker.visitEndAt) < Date.now()) {
    return false;
  }
  return true;
}

async function hashSensitiveValue(value) {
  const encoded = new TextEncoder().encode(String(value || ""));
  const digest = await crypto.subtle.digest("SHA-256", encoded);
  return Array.from(new Uint8Array(digest)).map((item) => item.toString(16).padStart(2, "0")).join("");
}

function calculateDistanceMeters(latitudeA, longitudeA, latitudeB, longitudeB) {
  const earthRadiusMeters = 6371000;
  const toRadians = (value) => value * (Math.PI / 180);
  const lat1 = toRadians(Number(latitudeA));
  const lon1 = toRadians(Number(longitudeA));
  const lat2 = toRadians(Number(latitudeB));
  const lon2 = toRadians(Number(longitudeB));
  const dLat = lat2 - lat1;
  const dLon = lon2 - lon1;
  const haversine = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * earthRadiusMeters * Math.asin(Math.sqrt(haversine));
}

async function resolveLoginLocation() {
  if (!navigator.geolocation) {
    return null;
  }

  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (position) => {
        resolve({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: position.coords.accuracy,
        });
      },
      () => {
        // Permission denied or unavailable – let the server decide if geolocation is required
        resolve(null);
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
    );
  });
}

async function persistOfflineBadgeProfile(badgeId, badgePin, payload) {
  if (!badgeId || !badgePin || !payload?.worker) {
    return;
  }
  const pinHash = await hashSensitiveValue(`${normalizeBadgeIdInput(badgeId)}:${normalizeBadgePinInput(badgePin)}`);
  writeStoredJson(WORKER_OFFLINE_LOGIN_PROFILE_KEY, {
    badgeId: normalizeBadgeIdInput(badgeId),
    pinHash,
    workerId: payload.worker.id,
    payload,
    savedAt: new Date().toISOString(),
  });
}

function queueOfflineEvent(eventPayload) {
  const queue = readStoredJson(OFFLINE_EVENT_QUEUE_KEY, []);
  queue.push(eventPayload);
  writeStoredJson(OFFLINE_EVENT_QUEUE_KEY, queue.slice(-50));
}

async function tryOfflineBadgeLogin(badgeId, badgePin, locationPayload) {
  const offlineProfile = readStoredJson(WORKER_OFFLINE_LOGIN_PROFILE_KEY, null);
  const cachedPayload = readStoredJson(WORKER_CACHED_PAYLOAD_KEY, null);
  const normalizedBadgeId = normalizeBadgeIdInput(badgeId);
  if (!offlineProfile || !cachedPayload || !isCachedWorkerPayloadUsable(cachedPayload)) {
    return false;
  }
  if (normalizeBadgeIdInput(offlineProfile.badgeId) !== normalizedBadgeId) {
    return false;
  }

  const expectedPinHash = await hashSensitiveValue(`${normalizedBadgeId}:${normalizeBadgePinInput(badgePin)}`);
  if (offlineProfile.pinHash !== expectedPinHash) {
    return false;
  }

  const siteLocation = cachedPayload?.worker?.siteLocation;
  const hasSiteGeo = siteLocation && typeof siteLocation.latitude === "number" && typeof siteLocation.longitude === "number";
  let distanceMeters = null;
  if (hasSiteGeo && locationPayload) {
    distanceMeters = Math.round(calculateDistanceMeters(siteLocation.latitude, siteLocation.longitude, locationPayload.latitude, locationPayload.longitude));
    if (distanceMeters > Number(siteLocation.radiusMeters || 100)) {
      showWorkerNotice(tf("offlineLoginOnSiteOnly", { meters: distanceMeters }));
      return true;
    }
  }
  // No GPS available or no site location configured → allow PIN-based offline login

  offlineWorkerSessionActive = true;
  workerToken = localStorage.getItem(WORKER_TOKEN_KEY) || "";
  localStorage.setItem(WORKER_BADGE_LOGIN_KEY, normalizedBadgeId);
  renderWorker(cachedPayload);
  updateConnectionState();
  if (elements.lastSyncInfo) {
    elements.lastSyncInfo.textContent = t("offlineLoginActiveWaitingSync");
  }
  queueOfflineEvent({
    type: "offline_login",
    occurredAt: new Date().toISOString(),
    distanceMeters,
  });
  initializeSessionInactivityProtection();
  return true;
}

async function syncOfflinePhotoQueue() {
  let queue = [];
  try {
    queue = JSON.parse(localStorage.getItem(OFFLINE_PHOTO_QUEUE_KEY) || "[]");
  } catch {
    queue = [];
  }

  if (!queue.length || !workerToken) {
    return;
  }

  const pending = [];
  for (const item of queue) {
    try {
      await fetchJson(`${API_BASE}/photo`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${workerToken}`
        },
        body: JSON.stringify({ photoData: item.dataUrl })
      });
    } catch {
      pending.push(item);
    }
  }

  localStorage.setItem(OFFLINE_PHOTO_QUEUE_KEY, JSON.stringify(pending));
}

async function syncOfflineEventQueue() {
  const queue = readStoredJson(OFFLINE_EVENT_QUEUE_KEY, []);
  if (!queue.length || !workerToken) {
    return;
  }

  try {
    await fetchJson(`${API_BASE}/offline-events`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${workerToken}`
      },
      body: JSON.stringify({ events: queue })
    });
    writeStoredJson(OFFLINE_EVENT_QUEUE_KEY, []);
  } catch {
    // keep queue for next sync attempt
  }
}

function registerWorkerSw() {
  if (!("serviceWorker" in navigator)) {
    return;
  }
  const swTimestamp = Math.floor(Date.now() / 1000);
  navigator.serviceWorker.register(`./worker-sw.js?v=${WORKER_BUILD_TAG}&t=${swTimestamp}`).then((registration) => {
    registration.update().catch(() => {});

    // When a new SW takes control, reload once to serve fresh assets.
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      window.location.reload();
    });

    // Force-activate waiting SW immediately without delay.
    function activateWaiting(sw) {
      if (!sw) return;
      sw.postMessage({ type: "SKIP_WAITING" });
    }

    if (registration.waiting) {
      // There's already a waiting SW — activate it now.
      activateWaiting(registration.waiting);
    }
    registration.addEventListener("updatefound", () => {
      const newSw = registration.installing;
      if (!newSw) return;
      newSw.addEventListener("statechange", () => {
        if (newSw.state === "installed") {
          // Activate immediately — no user confirmation needed.
          activateWaiting(newSw);
        }
      });
    });
  }).catch(() => {});
}

function wireInstallPrompt() {
  updatePlatformInstallHint();
  window.addEventListener("beforeinstallprompt", (event) => {
    deferredInstallPrompt = event;
    if (elements.installButton) {
      elements.installButton.hidden = false;
    }
  });
}

function isStandaloneMode() {
  return window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
}

async function triggerInstall() {
  if (deferredInstallPrompt) {
    deferredInstallPrompt.prompt();
    await deferredInstallPrompt.userChoice;
    deferredInstallPrompt = null;
    if (elements.installButton) {
      elements.installButton.hidden = true;
    }
    return;
  }

  if (isStandaloneMode()) {
    showWorkerNotice(t("installAlreadyInstalled"));
    return;
  }

  if (isIosDevice()) {
    showWorkerNotice(t("installIosHowto"));
    return;
  }

  if (isAndroidDevice()) {
    showWorkerNotice(t("installAndroidHowto"));
    return;
  }

  showWorkerNotice(t("installManual"));
}

async function loginWithAccessToken(accessToken, { keepUrlToken = false, silent = false, locationPayload = null } = {}) {
  if (!accessToken) {
    if (!silent) {
      showWorkerNotice(t("enterAccessCode"));
    }
    return;
  }

  if (!silent) {
    hideWorkerNotice();
  }

  try {
    const payload = await fetchJson(`${API_BASE}/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ accessToken, location: locationPayload })
    });

    offlineWorkerSessionActive = false;
    workerToken = payload.token;
    localStorage.setItem(WORKER_TOKEN_KEY, workerToken);
    localStorage.setItem(WORKER_ACCESS_TOKEN_KEY, accessToken);
    localStorage.removeItem(WORKER_BADGE_LOGIN_KEY);
    applyDynamicManifestStartUrl(accessToken);
    if (!keepUrlToken) {
      window.history.replaceState({}, document.title, "./worker.html");
    }
    await loadWorkerData();

    // Einmaltoken ist jetzt verbraucht – aus Storage löschen, damit beim nächsten
    // App-Start kein Fehler „Anmeldung fehlgeschlagen" wegen ungültigem Token entsteht.
    localStorage.removeItem(WORKER_ACCESS_TOKEN_KEY);
    // Badge-ID für nächste Session speichern (Feld wird beim nächsten Start vorausgefüllt).
    try {
      const cached = JSON.parse(localStorage.getItem(WORKER_CACHED_PAYLOAD_KEY) || "{}");
      const badgeId = cached.worker?.badgeId || cached.badgeId || "";
      if (badgeId) {
        localStorage.setItem(WORKER_BADGE_LOGIN_KEY, badgeId);
      }
    } catch {
      // Nicht kritisch
    }

    if (!isStandaloneMode() && elements.installButton) {
      elements.installButton.hidden = false;
      if (!silent) {
        showWorkerNotice(t("installTip"));
      }
    }

    // ── Schutzlogik: Session-Inaktivitäts-Monitor starten ──
    initializeSessionInactivityProtection();
  } catch (error) {
    if (error.code === "access_token_already_used") {
      localStorage.removeItem(WORKER_ACCESS_TOKEN_KEY);
      // If the worker already has an active session, just load that instead of showing the login screen
      const existingToken = localStorage.getItem(WORKER_TOKEN_KEY);
      if (existingToken) {
        workerToken = existingToken;
        const loaded = await loadWorkerData();
        if (loaded) {
          return;
        }
      }
      const fallbackBadgeId = normalizeBadgeIdInput(error?.payload?.badgeId || error?.payload?.badge_id || "");
      if (fallbackBadgeId) {
        localStorage.setItem(WORKER_BADGE_LOGIN_KEY, fallbackBadgeId);
        if (elements.workerAccessToken) {
          elements.workerAccessToken.value = fallbackBadgeId;
        }
        const pinWrapper = document.querySelector("#pinFieldWrapper");
        if (pinWrapper && !isVisitorBadgeId(fallbackBadgeId)) {
          pinWrapper.classList.remove("hidden");
          const pinInput = document.querySelector("#workerBadgePin");
          if (pinInput) setTimeout(() => pinInput.focus(), 120);
        }
        showWorkerNotice(t("qrLinkUsedEnterPin"));
        return;
      }
      showWorkerNotice(t("qrLinkInvalidRescan"));
      return;
    }
    if (["invalid_access_token", "access_token_revoked", "access_token_expired"].includes(error.code)) {
      localStorage.removeItem(WORKER_ACCESS_TOKEN_KEY);
      showWorkerNotice(t("qrLinkInvalidRescan"));
      return;
    }
    if (error.code === "visitor_visit_expired") {
      localStorage.removeItem(WORKER_ACCESS_TOKEN_KEY);
      showWorkerNotice(t("visitorExpiredNeedLink"));
      return;
    }
    if (silent) {
      showLogin();
      return;
    }
    if (error.code === "worker_app_disabled") {
      showWorkerNotice(t("workerAppDisabled"));
      return;
    }
    showWorkerNotice(`${t("accessFailed")}: ${error.message}`);
  }
}

async function loginWithBadgeId(badgeId, badgePin, { silent = false, locationPayload = null } = {}) {
  const normalizedBadgeId = normalizeBadgeIdInput(badgeId);
  const normalizedBadgePin = normalizeBadgePinInput(badgePin);
  if (!normalizedBadgeId) {
    if (!silent) {
      showWorkerNotice(t("enterBadgeId"));
    }
    return;
  }
  const visitorLogin = isVisitorBadgeId(normalizedBadgeId);
  if (!visitorLogin && !normalizedBadgePin) {
    if (!silent) {
      showWorkerNotice(t("enterPin"));
    }
    return;
  }

  if (!silent) {
    hideWorkerNotice();
  }

  try {
    const payload = await fetchJson(`${API_BASE}/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ badgeId: normalizedBadgeId, badgePin: normalizedBadgePin, location: locationPayload })
    });

    offlineWorkerSessionActive = false;
    workerToken = payload.token;
    localStorage.setItem(WORKER_TOKEN_KEY, workerToken);
    localStorage.setItem(WORKER_BADGE_LOGIN_KEY, normalizedBadgeId);
    localStorage.removeItem(WORKER_ACCESS_TOKEN_KEY);
    if (elements.workerAccessToken) {
      elements.workerAccessToken.value = normalizedBadgeId;
    }
    if (elements.workerBadgePin) {
      elements.workerBadgePin.value = "";
    }
    // Store PIN in sessionStorage for offline fallback (not persisted, not in DOM)
    if (normalizedBadgePin) {
      try { sessionStorage.setItem("_wpf", normalizedBadgePin); } catch (_) {}
    }
    await loadWorkerData();
    await persistOfflineBadgeProfile(normalizedBadgeId, normalizedBadgePin, payload);

    if (!isStandaloneMode() && elements.installButton) {
      elements.installButton.hidden = false;
      if (!silent) {
        showWorkerNotice(t("installTip"));
      }
    }

    // ── Schutzlogik: Session-Inaktivitäts-Monitor starten ──
    initializeSessionInactivityProtection();
  } catch (error) {
    if (!navigator.onLine || !error.code) {
      const restored = await tryOfflineBadgeLogin(normalizedBadgeId, normalizedBadgePin, locationPayload);
      if (restored) {
        return;
      }
    }
    if (silent) {
      showLogin();
      return;
    }
    if (error.code === "visitor_visit_expired") {
      localStorage.removeItem(WORKER_BADGE_LOGIN_KEY);
      showWorkerNotice(t("visitorExpiredBadgeLogin"));
      return;
    }
    if (error.code === "worker_app_disabled") {
      showWorkerNotice(t("workerAppDisabled"));
      return;
    }
    if (error.message === "site_location_unavailable") {
      showWorkerNotice(t("siteLocationUnavailable"));
      return;
    }
    showWorkerNotice(`${t("loginFailed")}: ${error.message}`);
  }
}

async function loadWorkerData() {
  if (!workerToken) {
    console.warn("[loadWorkerData] No worker token – showing login");
    showLogin();
    return false;
  }

  console.log("[loadWorkerData] Starting fetch for /me...");
  try {
    const payload = await fetchJson(`${API_BASE}/me`, {
      headers: { Authorization: `Bearer ${workerToken}` }
    });
    console.log("[loadWorkerData] Success:", payload);
    localStorage.setItem(WORKER_CACHED_PAYLOAD_KEY, JSON.stringify(payload));
    offlineWorkerSessionActive = false;
    renderWorker(payload);
    if (elements.lastSyncInfo) {
      elements.lastSyncInfo.textContent = `${t("lastSync")}: ${new Intl.DateTimeFormat(getCurrentLocale(), { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date())}`;
    }
    updateConnectionState();
    await syncOfflinePhotoQueue();
    await syncOfflineEventQueue();
    return true;
  } catch (error) {
    // Session expired or revoked — must re-login
    if (error?.code === "worker_session_expired" || error?.code === "invalid_worker_session") {
      localStorage.removeItem(WORKER_TOKEN_KEY);
      localStorage.removeItem(WORKER_CACHED_PAYLOAD_KEY);
      workerToken = "";
      clearWorkerSessionExpiryTimer();
      showWorkerNotice(t("sessionExpired"));
      showLogin();
      return false;
    }
    // Network error — show cached data if available
    console.warn("[loadWorkerData] Network error:", error.message);
    const cachedRaw = localStorage.getItem(WORKER_CACHED_PAYLOAD_KEY);
    if (cachedRaw) {
      try {
        const cachedPayload = JSON.parse(cachedRaw);
        console.log("[loadWorkerData] Rendering cached payload:", cachedPayload);
        offlineWorkerSessionActive = true;
        renderWorker(cachedPayload);
        if (elements.lastSyncInfo) {
          elements.lastSyncInfo.textContent = t("offlineBanner");
        }
        return true;
      } catch (cacheErr) {
        console.error("[loadWorkerData] Cache parse error:", cacheErr);
        // corrupt cache — fall through to logout
      }
    }
    console.warn("[loadWorkerData] No cache available – showing login");
    localStorage.removeItem(WORKER_TOKEN_KEY);
    workerToken = "";
    clearWorkerSessionExpiryTimer();
    showWorkerNotice(`${t("connError")}: ${error.message}`);
    showLogin();
    return false;
  }
}

function renderWorker(payload) {
  const worker = payload.worker || {};
  const company = payload.company || {};
  const subcompany = payload.subcompany || {};
  const workerBadgeId = String(worker.badgeId || worker.badge_id || "").trim();
  const companyPreset = normalizeCompanyBrandingPreset(company.brandingPreset || company.branding_preset);
  const normalizedStatus = String(worker.status || "").trim().toLowerCase();
  const workerType = String(worker.workerType || "worker").trim().toLowerCase();
  const isVisitor = workerType === "visitor";
  const sessionExpiresAt = String(payload.sessionExpiresAt || "").trim();

  // ── Pass-Lock aktivieren wenn Admin-Setting es erlaubt ──
  pinLockEnabled = payload.settings?.workerPassLockEnabled === 1 || payload.settings?.workerPassLockEnabled === "1";
  if (pinLockEnabled) {
    initializePassLockProtection();
  }

  // ── Dynamic platform branding ──
  const platformName = ((payload.settings?.platformName) || "Control Pass").trim() || "Control Pass";
  
  // Determine app title based on company branding preset
  const appTitleMap = {
    "industry": "Kontrollpass",
    "premium": "Kontrollpass",
    "construction": "BauPass"
  };
  const appBrandTitle = appTitleMap[companyPreset] || platformName;
  currentAppBrandTitle = appBrandTitle; // store globally so applyTranslations() can preserve it
  
  document.title = appBrandTitle + " – " + t("pageTitle");
  const brandEl = document.getElementById("workerBrandName");
  if (brandEl) brandEl.textContent = appBrandTitle.toUpperCase();
  const appTitleEl = document.getElementById("workerAppTitle");
  if (appTitleEl) appTitleEl.textContent = appBrandTitle;
  const splashTitleEl = document.getElementById("workerSplashTitle");
  if (splashTitleEl) splashTitleEl.textContent = appBrandTitle;
  // Brand chip in top panel
  const brandChipEl = document.getElementById("workerBrandChip");
  if (brandChipEl) brandChipEl.textContent = appBrandTitle;
  // Update iOS / Android meta tags dynamically
  const metaAppTitle = document.querySelector('meta[name="apple-mobile-web-app-title"]');
  if (metaAppTitle) metaAppTitle.setAttribute("content", appBrandTitle);
  const metaAppName = document.querySelector('meta[name="application-name"]');
  if (metaAppName) metaAppName.setAttribute("content", appBrandTitle + " Mitarbeiter-App");
  // Update manifest with white-label name
  const _storedToken = localStorage.getItem(WORKER_TOKEN_KEY) || "";
  if (_storedToken) applyDynamicManifestStartUrl(_storedToken, appBrandTitle);

  if (elements.workerPassTitle) {
    elements.workerPassTitle.textContent = isVisitor ? t("visitorCardTitle") : t("workerCardTitle");
  }
  if (elements.workerPassSubLabels && elements.workerPassSubLabels.length) {
    const passSubLabel = isVisitor ? t("visitorPassSubLabel") : t("workerPassSubLabel");
    elements.workerPassSubLabels.forEach((el) => {
      el.textContent = passSubLabel;
    });
  }

  if (elements.walletCard) {
    elements.walletCard.classList.remove("preset-construction", "preset-industry", "preset-premium");
    elements.walletCard.classList.add(`preset-${companyPreset}`);
  }

  if (elements.companyName) elements.companyName.textContent = company.name || t("companyFallback");
  if (elements.workerSubcompany) {
    const subcompanyName = String(subcompany.name || "").trim();
    if (subcompanyName) {
      elements.workerSubcompany.textContent = `Subunternehmen: ${subcompanyName}`;
      elements.workerSubcompany.title = `Subunternehmen: ${subcompanyName}`;
      elements.workerSubcompany.classList.remove("hidden");
    } else {
      elements.workerSubcompany.textContent = "";
      elements.workerSubcompany.title = "";
      elements.workerSubcompany.classList.add("hidden");
    }
  }
  if (elements.workerName) elements.workerName.textContent = `${worker.firstName || ""} ${worker.lastName || ""}`.trim();
  if (elements.workerRole) elements.workerRole.textContent = isVisitor ? t("visitorRole") : (worker.role || "-");
  if (elements.workerStatus) {
    elements.workerStatus.textContent = worker.status || "-";
    elements.workerStatus.dataset.status = normalizedStatus;
  }
  if (elements.workerBadgeId) elements.workerBadgeId.textContent = workerBadgeId || "-";
  if (elements.workerSite) elements.workerSite.textContent = worker.site || "-";
  updateSiteMapLink(worker.site || "");
  if (elements.workerValidUntil) elements.workerValidUntil.textContent = formatDate(worker.validUntil);
  renderDayCardValidity(sessionExpiresAt);
  scheduleWorkerSessionExpiry(sessionExpiresAt);
  if (elements.workerVisitorMeta) {
    elements.workerVisitorMeta.classList.toggle("hidden", !isVisitor);
  }
  if (elements.workerVisitorCompany) {
    elements.workerVisitorCompany.textContent = worker.visitorCompany || "-";
  }
  if (elements.workerVisitPurpose) {
    elements.workerVisitPurpose.textContent = worker.visitPurpose || "-";
  }
  if (elements.workerHostName) {
    elements.workerHostName.textContent = worker.hostName || "-";
  }
  if (elements.workerVisitEndAt) {
    elements.workerVisitEndAt.textContent = worker.visitEndAt ? formatDateTime(worker.visitEndAt) : "-";
  }

  if (isVisitor) {
    startVisitorCountdown(payload);
  } else {
    stopVisitorCountdown();
  }

  if (elements.workerPhoto) {
    if (worker.photoData && String(worker.photoData).startsWith("data:image")) {
      elements.workerPhoto.src = worker.photoData;
      localStorage.setItem(LOCAL_LAST_PHOTO_KEY, worker.photoData);
    } else {
      const localPhoto = localStorage.getItem(LOCAL_LAST_PHOTO_KEY);
      elements.workerPhoto.src = localPhoto && localPhoto.startsWith("data:image")
        ? localPhoto
        : createAvatar(worker.firstName, worker.lastName);
    }
  }

  dqrWorkerBadgeId = workerBadgeId;
  const qrPayload = buildQrPayload(worker);
  const isCompactViewport = window.matchMedia("(max-width: 520px)").matches;
  const workerQrSize = isCompactViewport ? 520 : 460;
  const gateQrSize = isCompactViewport ? 520 : 420;
  if (elements.workerQr) {
    if (!qrPayload) {
      elements.workerQr.removeAttribute("src");
      elements.workerQr.classList.add("hidden");
    } else {
      elements.workerQr.classList.remove("hidden");
      void setQrImage(elements.workerQr, qrPayload, workerQrSize);
    }
  }

  if (elements.qrFallbackText) {
    if (!qrPayload) {
      elements.qrFallbackText.textContent = t("noQrAvailable");
      elements.qrFallbackText.classList.remove("hidden");
    } else {
      elements.qrFallbackText.textContent = `Code: ${qrPayload}`;
      elements.qrFallbackText.classList.remove("hidden");
    }
  }

  if (elements.gateQr) {
    if (!qrPayload) {
      elements.gateQr.removeAttribute("src");
      elements.gateQr.classList.add("hidden");
    } else {
      elements.gateQr.classList.remove("hidden");
      void setQrImage(elements.gateQr, qrPayload, gateQrSize);
    }
  }

  if (elements.gateBadgeId) {
    elements.gateBadgeId.textContent = qrPayload ? tf("badgeValue", { value: qrPayload }) : t("badgeUnset");
  }

  if (elements.gateWorkerName) {
    elements.gateWorkerName.textContent = `${worker.firstName || ""} ${worker.lastName || ""}`.trim() || t("workerDefaultName");
  }

  // Update Status Banner
  if (elements.workerStatusBanner && elements.workerStatusText) {
    const banned = String(worker.banned || "false").trim().toLowerCase() === "true";
    const validUntilDate = new Date(worker.validUntil || "");
    const isExpired = validUntilDate < new Date();
    
    elements.workerStatusBanner.classList.remove("status-banner-hidden");
    
    if (banned) {
      elements.workerStatusBanner.className = "status-banner error";
      elements.workerStatusText.textContent = t("statusRevoked");
    } else if (isExpired) {
      elements.workerStatusBanner.className = "status-banner warning";
      elements.workerStatusText.textContent = t("statusExpired");
    } else {
      elements.workerStatusBanner.className = "status-banner active";
      elements.workerStatusText.textContent = t("statusActive");
    }
  }

  if (elements.loginCard) elements.loginCard.classList.add("hidden");
  if (elements.badgeCard) elements.badgeCard.classList.remove("hidden");
  document.body.classList.add("worker-loaded");
  window.scrollTo(0, 0);
  updateWalletImmersiveMode();
  setWorkerHubExpanded(true);
  haptic([18, 35, 22]);
  // Start dynamic QR lifecycle as soon as pass is visible.
  startDynamicQrRefresh();
  if (elements.workerQuickMenu) {
    elements.workerQuickMenu.classList.add("hidden");
  }
  if (quickMenuObserver) {
    quickMenuObserver.disconnect();
    quickMenuObserver = null;
  }
  
  // Show leave request card
  if (elements.leaveRequestCard) {
    elements.leaveRequestCard.classList.remove("hidden");
  }

  // Show leave balance badge
  const leaveStats = payload.leaveStats;
  const balanceBadge = document.getElementById("leaveBalanceBadge");
  const balanceRemaining = document.getElementById("leaveBalanceRemaining");
  if (leaveStats && balanceBadge && balanceRemaining && !isVisitor) {
    balanceRemaining.textContent = leaveStats.remaining;
    balanceBadge.classList.remove("hidden");
    balanceBadge.title = `Anspruch: ${leaveStats.balance} Tage · Genommen: ${leaveStats.taken} Tage`;
    const pct = leaveStats.balance > 0 ? leaveStats.remaining / leaveStats.balance : 1;
    balanceBadge.className = "leave-balance-badge" + (pct <= 0.1 ? " low" : pct <= 0.3 ? " medium" : "");
  }

  // Late check-in notification banner
  const lateInfo = payload.lateCheckIn;
  showLateCheckInBanner(lateInfo, isVisitor);

  // Plan-Feature-Gates
  const planFeatures = payload.planFeatures || {};
  const hasTimesheet    = !!planFeatures.worker_app;           // ab starter
  const hasLeave        = !!planFeatures.leave_management;     // ab starter
  const hasDocs         = !!planFeatures.document_upload;      // ab starter
  const hasLateAlert    = !!planFeatures.late_checkin_alert;   // ab professional

  // Re-show late banner only if plan allows it
  if (!hasLateAlert) {
    const lateBanner = document.getElementById("lateCheckInBanner");
    if (lateBanner) lateBanner.remove();
  }

  // Show timesheet only for regular workers (not visitors) and if plan allows
  if (elements.timesheetCard) {
    elements.timesheetCard.classList.toggle("hidden", isVisitor || !hasTimesheet);
  }
  // Also hide timesheet quick-menu and nav buttons for visitors or plan restriction
  document.querySelectorAll("[data-scroll-target='timesheetCard'], [data-worker-page-target='timesheetCard']").forEach((btn) => {
    btn.classList.toggle("hidden", isVisitor || !hasTimesheet);
  });
  if (elements.documentsCard) {
    elements.documentsCard.classList.toggle("hidden", !hasDocs);
  }
  // Hide leave section if plan doesn't support it
  const leaveCard = document.getElementById("leaveRequestCard");
  if (leaveCard) {
    leaveCard.classList.toggle("hidden", isVisitor || !hasLeave);
  }
  document.querySelectorAll("[data-scroll-target='leaveRequestCard'], [data-worker-page-target='leaveRequestCard']").forEach((btn) => {
    btn.classList.toggle("hidden", isVisitor || !hasLeave);
  });
  
  // Load leave requests after render
  if (hasLeave && !isVisitor) void loadLeaveRequests();
  if (leaveRefreshInterval) {
    clearInterval(leaveRefreshInterval);
  }
  if (hasLeave && !isVisitor) {
    leaveRefreshInterval = setInterval(() => {
      if (workerToken) {
        void loadLeaveRequests();
      }
    }, 60000);
  }
  if (hasTimesheet && !isVisitor) void loadMyTimesheets();
  if (hasDocs) void loadMyDocuments();
  void prefillCompanyAdminEmails();
}

function showLogin() {
  clearWorkerSessionExpiryTimer();
  clearWorkerSessionCountdown();
  stopVisitorCountdown();
  sessionExpiringSoonNotified = false;
  gateAutoOpenTriggered = false;
  stopAmbientLightRecommendation();
    stopDynamicQrRefresh();
  if (elements.badgeCard) elements.badgeCard.classList.add("hidden");
  if (elements.loginCard) elements.loginCard.classList.remove("hidden");
  setWorkerHubExpanded(false);
  if (elements.workerQuickMenu) elements.workerQuickMenu.classList.add("hidden");
  applyWorkerPageView("");
  if (quickMenuObserver) {
    quickMenuObserver.disconnect();
    quickMenuObserver = null;
  }
  document.body.classList.remove("worker-loaded");
  updateWalletImmersiveMode();

  // Prefill stored Badge-ID so the worker only needs to enter the PIN
  const savedBadgeId = (localStorage.getItem(WORKER_BADGE_LOGIN_KEY) || "").trim();
  if (savedBadgeId && elements.workerAccessToken) {
    elements.workerAccessToken.value = normalizeBadgeIdInput(savedBadgeId);
    const pinWrapper = document.querySelector("#pinFieldWrapper");
    if (pinWrapper && !isVisitorBadgeId(savedBadgeId)) {
      pinWrapper.classList.remove("hidden");
      // Focus the PIN field so the worker can type right away
      const pinInput = document.querySelector("#workerBadgePin");
      if (pinInput) setTimeout(() => pinInput.focus(), 120);
    }
  }
}

function updateConnectionState() {
  if (!elements.connectionBanner) {
    return;
  }
  if (navigator.onLine) {
    elements.connectionBanner.textContent = t("online");
    elements.connectionBanner.className = "connection-banner online";
  } else {
    elements.connectionBanner.textContent = t("offline");
    elements.connectionBanner.className = "connection-banner offline";
  }
}

function showWorkerNotice(message) {
  if (!elements.workerNotice) {
    return;
  }
  elements.workerNotice.textContent = message;
  elements.workerNotice.classList.remove("hidden");
}

function hideWorkerNotice() {
  if (!elements.workerNotice) {
    return;
  }
  elements.workerNotice.textContent = "";
  elements.workerNotice.classList.add("hidden");
}

// ═════════════════════════════════════════════════════════════════════
// ── SESSION PROTECTION: Aggressive Inactivity Timeout ──
// Schützt gegen Telefon-Weitergabe durch autom. Logout nach 60s ohne Interaktion
// ═════════════════════════════════════════════════════════════════════

function initializeSessionInactivityProtection() {
  // Stoppe jeden existierenden Timer
  if (inactivityCheckInterval) {
    clearInterval(inactivityCheckInterval);
  }

  lastUserInteractionAt = Date.now();

  // Prüfe alle 5 Sekunden auf Inaktivität, damit Logout nah an 60s erfolgt
  inactivityCheckInterval = setInterval(() => {
    const timeSinceLastInteraction = Date.now() - lastUserInteractionAt;
    if (timeSinceLastInteraction > WORKER_INACTIVITY_TIMEOUT_MS) {
      console.warn("🔐 Session timeout: Zu lange inaktiv, Auto-Logout für Sicherheit");
      showWorkerNotice(t("inactiveReLogin"));
      workerLogout();
    }
  }, 5 * 1000);

  console.log("✓ Session protection: 60s Inaktivitäts-Monitor gestartet");
}

// ═════════════════════════════════════════════════════════════════════
// ── PASS LOCK: 2min Inaktivitäts-Sperre zum Schutz vor Diebstahl ──
// ═════════════════════════════════════════════════════════════════════

function initializePassLockProtection() {
  if (!pinLockEnabled) {
    console.log("⚠️  Pass-Lock deaktiviert (Admin-Setting)");
    return;
  }

  // Stoppe existierenden Timer
  if (passLockTimer) clearTimeout(passLockTimer);

  lastPassInteractionAt = Date.now();
  isPassLocked = false;
  hidePassLockOverlay();

  // Überwache Inaktivität auf Ausweis-Seite
  const checkPassLock = () => {
    if (!elements.badgeCard || elements.badgeCard.classList.contains("hidden")) {
      // Nicht auf Ausweis-Seite, timer neustarten
      if (passLockTimer) clearTimeout(passLockTimer);
      passLockTimer = setTimeout(checkPassLock, 30 * 1000);
      return;
    }

    const timeSinceLastInteraction = Date.now() - lastPassInteractionAt;
    if (timeSinceLastInteraction > WORKER_PASS_LOCK_TIMEOUT_MS && !isPassLocked) {
      console.log("🔒 Pass-Lock: 2min Inaktivität → Ausweis sperren");
      isPassLocked = true;
      showPassLockOverlay();
    }

    passLockTimer = setTimeout(checkPassLock, 30 * 1000);
  };

  passLockTimer = setTimeout(checkPassLock, 30 * 1000);
  console.log("✓ Pass-Lock: 2min Inaktivitäts-Sperre gestartet");
}

function markPassInteraction() {
  if (isPassLocked) return; // Keine Interaktion möglich wenn gesperrt
  lastPassInteractionAt = Date.now();
  if (isPassLocked) {
    isPassLocked = false;
    hidePassLockOverlay();
    // Timer neustarten
    if (passLockTimer) clearTimeout(passLockTimer);
    initializePassLockProtection();
  }
}

function showPassLockOverlay() {
  if (elements.pinLockOverlay) {
    elements.pinLockOverlay.classList.remove("hidden");
    if (elements.pinLockInput) {
      elements.pinLockInput.focus();
    }
  }
}

function hidePassLockOverlay() {
  if (elements.pinLockOverlay) {
    elements.pinLockOverlay.classList.add("hidden");
  }
  if (elements.pinLockError) {
    elements.pinLockError.classList.add("hidden");
  }
  if (elements.pinLockInput) {
    elements.pinLockInput.value = "";
  }
}

async function handlePassLockUnlock(pin) {
  if (!pin || !workerToken) {
    showPassLockError(t("pinLockTitle"));
    return;
  }

  try {
    // Verifizierung gegen Backend (oder lokal wenn PIN im Token gespeichert)
    const payload = await fetchJson(`${API_BASE}/verify-pin`, {
      method: "POST",
      headers: { Authorization: `Bearer ${workerToken}`, "Content-Type": "application/json" },
      body: JSON.stringify({ pin: normalizeBadgePinInput(pin) })
    });

    if (payload.valid) {
      isPassLocked = false;
      hidePassLockOverlay();
      lastPassInteractionAt = Date.now();
      // Timer neustarten
      if (passLockTimer) clearTimeout(passLockTimer);
      initializePassLockProtection();
      console.log("✓ Pass entsperrt");
    } else if (payload.error === "too_many_attempts") {
      showPassLockError(t("pinLockTooManyAttempts") || "Zu viele Versuche – bitte warte kurz.");
    } else {
      showPassLockError(t("wrongPinRetry"));
    }
  } catch (error) {
    // Fallback: Locally verify using sessionStorage (used when backend unreachable)
    const storedPin = (() => { try { return sessionStorage.getItem("_wpf") || ""; } catch (_) { return ""; } })();
    if (storedPin && storedPin === normalizeBadgePinInput(pin)) {
      isPassLocked = false;
      hidePassLockOverlay();
      lastPassInteractionAt = Date.now();
      if (passLockTimer) clearTimeout(passLockTimer);
      initializePassLockProtection();
      console.log("✓ Pass entsperrt (lokal)");
    } else {
      showPassLockError(t("wrongPinRetry"));
    }
  }
}

function showPassLockError(message) {
  if (elements.pinLockError) {
    elements.pinLockError.textContent = message;
    elements.pinLockError.classList.remove("hidden");
  }
}

async function workerLogout() {
    stopDynamicQrRefresh();
  try {
    if (workerToken) {
      await fetchJson(`${API_BASE}/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${workerToken}` }
      });
    }
  } catch {
    // ignore logout call failures
  }

  localStorage.removeItem(WORKER_TOKEN_KEY);
  localStorage.removeItem(WORKER_ACCESS_TOKEN_KEY);
  localStorage.removeItem(WORKER_BADGE_LOGIN_KEY);
  localStorage.removeItem(WORKER_CACHED_PAYLOAD_KEY);
  localStorage.removeItem(WORKER_OFFLINE_LOGIN_PROFILE_KEY);
  localStorage.removeItem(OFFLINE_EVENT_QUEUE_KEY);
  try { sessionStorage.removeItem("_wpf"); } catch (_) {}
  offlineWorkerSessionActive = false;
  workerToken = "";
  clearWorkerSessionExpiryTimer();
  if (inactivityCheckInterval) {
    clearInterval(inactivityCheckInterval);
    inactivityCheckInterval = null;
  }
  if (leaveRefreshInterval) {
    clearInterval(leaveRefreshInterval);
    leaveRefreshInterval = null;
  }
  closeGateMode();
  showLogin();
}

async function openGateMode() {
  if (!elements.gateScannerOverlay) {
    return;
  }
  elements.gateScannerOverlay.classList.remove("hidden");
  setGateScannerFeedbackState("ready");
  haptic([14, 24, 14]);
  startGateEventFeedbackPolling();
  
  showBrightnessHintTemporarily();
  await requestWakeLock();
  await requestGateFullscreen();
  startAmbientLightRecommendation();
}

function closeGateMode() {
  if (gateFeedbackResetTimeout) {
    clearTimeout(gateFeedbackResetTimeout);
    gateFeedbackResetTimeout = null;
  }
  if (elements.gateScannerOverlay) {
    elements.gateScannerOverlay.classList.remove("is-ready", "is-refresh", "is-error");
    elements.gateScannerOverlay.classList.add("hidden");
  }
  if (elements.gateStatusFeedback) {
    elements.gateStatusFeedback.textContent = "";
  }
  stopGateEventFeedbackPolling();
  void exitGateFullscreen();
  stopAmbientLightRecommendation();
  releaseWakeLock();
}

function applyQrContrastState() {
  document.body.classList.toggle("qr-high-contrast", qrHighContrastEnabled);
  const label = qrHighContrastEnabled ? t("qrContrastOn") : t("qrContrastOff");
  if (elements.qrContrastToggle) {
    elements.qrContrastToggle.textContent = label;
  }
  if (elements.gateContrastToggle) {
    elements.gateContrastToggle.textContent = label;
  }
}

function toggleQrContrastMode() {
  qrHighContrastEnabled = !qrHighContrastEnabled;
  localStorage.setItem(QR_HIGH_CONTRAST_KEY, qrHighContrastEnabled ? "1" : "0");
  applyQrContrastState();
}

function applyAutoOpenScannerState() {
  if (elements.autoOpenScannerToggle) {
    elements.autoOpenScannerToggle.checked = autoOpenScannerEnabled;
  }
}

function showGateFeedback(message, color = "rgba(255, 255, 255, 0.78)") {
  if (!elements.gateStatusFeedback) {
    return;
  }
  elements.gateStatusFeedback.textContent = message;
  elements.gateStatusFeedback.style.color = color;
}

function setGateScannerFeedbackState(state, message = "") {
  if (!elements.gateScannerOverlay) {
    return;
  }
  elements.gateScannerOverlay.classList.remove("is-ready", "is-refresh", "is-error");
  if (state === "refresh") {
    elements.gateScannerOverlay.classList.add("is-refresh");
    showGateFeedback(message || t("gateQrRefreshed"), "#e8f6ff");
    return;
  }
  if (state === "error") {
    elements.gateScannerOverlay.classList.add("is-error");
    showGateFeedback(message || t("gateScanSyncDelayed"), "#ffd3d3");
    return;
  }
  elements.gateScannerOverlay.classList.add("is-ready");
  showGateFeedback(message || t("gateReadyScan"), "rgba(255, 255, 255, 0.7)");
}

function queueGateScannerReadyState(delayMs = 900) {
  if (gateFeedbackResetTimeout) {
    clearTimeout(gateFeedbackResetTimeout);
    gateFeedbackResetTimeout = null;
  }
  gateFeedbackResetTimeout = setTimeout(() => {
    setGateScannerFeedbackState("ready");
  }, Math.max(120, delayMs));
}

function stopGateEventFeedbackPolling() {
  if (gateEventPollTimeout) {
    clearTimeout(gateEventPollTimeout);
    gateEventPollTimeout = null;
  }
  gateEventPollInFlight = false;
  gateLastSeenEventId = "";
}

function scheduleGateEventFeedbackPolling(delayMs = 1200) {
  if (gateEventPollTimeout) {
    clearTimeout(gateEventPollTimeout);
    gateEventPollTimeout = null;
  }
  gateEventPollTimeout = setTimeout(() => {
    void pollLatestGateEvent();
  }, Math.max(500, delayMs));
}

function getGateEventFeedbackMessage(direction) {
  const normalized = String(direction || "").toLowerCase();
  if (normalized === "in") {
    return t("gateScanAccessGrantedIn");
  }
  if (normalized === "out") {
    return t("gateScanAccessGrantedOut");
  }
  return t("gateScanAccessGrantedGeneric");
}

function getGateDeniedFeedbackMessage(feedback) {
  const explicit = String(feedback?.message || "").trim();
  if (explicit) {
    return explicit;
  }
  return t("gateScanAccessDenied");
}

async function pollLatestGateEvent() {
  if (!workerToken || !elements.gateScannerOverlay || elements.gateScannerOverlay.classList.contains("hidden")) {
    stopGateEventFeedbackPolling();
    return;
  }
  if (gateEventPollInFlight) {
    scheduleGateEventFeedbackPolling(900);
    return;
  }

  gateEventPollInFlight = true;
  try {
    const payload = await fetchJson(`${API_BASE}/access-last`, {
      headers: { Authorization: `Bearer ${workerToken}` }
    });
    const feedback = payload?.gateFeedback || null;
    const feedbackId = String(feedback?.id || "").trim();
    const feedbackStatus = String(feedback?.status || "").trim().toLowerCase();
    const fallbackEventId = String(payload?.event?.id || "").trim();
    const currentId = feedbackId || fallbackEventId;
    if (currentId && gateLastSeenEventId && currentId !== gateLastSeenEventId) {
      if (feedbackStatus === "deny") {
        setGateScannerFeedbackState("error", getGateDeniedFeedbackMessage(feedback));
        queueGateScannerReadyState(2400);
        haptic([30, 40, 30]);
      } else {
        setGateScannerFeedbackState("refresh", getGateEventFeedbackMessage(feedback?.direction || payload?.event?.direction));
        queueGateScannerReadyState(1700);
        haptic([20, 28, 20]);
      }
    }
    if (currentId) {
      gateLastSeenEventId = currentId;
    }
  } catch {
    // Keep scanner usable even if backend ack polling is temporarily unavailable.
  } finally {
    gateEventPollInFlight = false;
    if (elements.gateScannerOverlay && !elements.gateScannerOverlay.classList.contains("hidden")) {
      scheduleGateEventFeedbackPolling(1200);
    }
  }
}

function startGateEventFeedbackPolling() {
  stopGateEventFeedbackPolling();
  void pollLatestGateEvent();
}

function startAmbientLightRecommendation() {
  ambientLowLightRecommended = false;
  if (typeof window.AmbientLightSensor !== "function") {
    return;
  }
  try {
    ambientLightSensorHandle = new window.AmbientLightSensor({ frequency: 0.5 });
    ambientLightSensorHandle.addEventListener("reading", () => {
      const lux = Number(ambientLightSensorHandle.illuminance || 0);
      if (lux > 0 && lux < 20 && !ambientLowLightRecommended) {
        ambientLowLightRecommended = true;
        showGateFeedback(t("lowLightDetected"), "#ffd5a3");
      }
    });
    ambientLightSensorHandle.addEventListener("error", () => {
      stopAmbientLightRecommendation();
    });
    ambientLightSensorHandle.start();
  } catch {
    stopAmbientLightRecommendation();
  }
}

function stopAmbientLightRecommendation() {
  ambientLowLightRecommended = false;
  if (!ambientLightSensorHandle) {
    return;
  }
  try {
    ambientLightSensorHandle.stop();
  } catch {
    // ignore sensor stop issues
  }
  ambientLightSensorHandle = null;
}

// ── Dynamic QR System ────────────────────────────────────────────────────────
function buildQrPayload(worker) {
  // Returns current DQR token if available, else falls back to static badge id.
  if (dqrCurrentToken) return dqrCurrentToken;
  const badge = String(worker?.badgeId || worker?.badge_id || "").trim();
  return badge || String(worker?.id || "").trim();
}

/** Vibrate the device (silent fail on unsupported devices) */
function haptic(pattern) {
  try { if (navigator.vibrate) navigator.vibrate(pattern); } catch {}
}

/** Update the QR countdown ring and text */
function _updateQrCountdownDisplay() {
  const el = document.getElementById("dqrCountdownRing");
  const textEl = document.getElementById("dqrCountdownText");
  if (!el && !textEl) return;
  const sec = Math.max(0, dqrRemainingSeconds);
  if (textEl) textEl.textContent = sec + "s";
  if (el) {
    const radius = 10;
    const circ = 2 * Math.PI * radius;
    const total = Math.max(20, Number(dqrWindowSeconds) || 60);
    const fraction = Math.min(1, Math.max(0, sec / total));
    el.style.strokeDashoffset = String(circ * (1 - fraction));
  }
}

function scheduleNextDynamicQrRefresh() {
  if (dqrRefreshTimeout) {
    clearTimeout(dqrRefreshTimeout);
    dqrRefreshTimeout = null;
  }
  const remaining = Math.max(8, Number(dqrRemainingSeconds) || 60);
  const nextInMs = Math.max(8_000, (remaining - 3) * 1000);
  dqrRefreshTimeout = setTimeout(() => {
    void fetchAndDisplayDynamicQr();
  }, nextInMs);
}

/** Fetch one dynamic QR token from the backend and update the QR image */
async function fetchAndDisplayDynamicQr() {
  if (!workerToken) return;
  try {
    const data = await fetchJson(`${API_BASE}/dynamic-qr`, {
      headers: { Authorization: `Bearer ${workerToken}` }
    });
    if (data?.qrToken) {
      dqrCurrentToken = data.qrToken;
      dqrRemainingSeconds = data.remainingSec ?? 60;
      dqrWindowSeconds = data.windowSec ?? Math.max(20, dqrRemainingSeconds || 60);
      // Re-render QR image
      const isCompact = window.matchMedia("(max-width: 520px)").matches;
      const sz = isCompact ? 520 : 460;
      if (elements.workerQr) {
        elements.workerQr.classList.remove("hidden");
        void setQrImage(elements.workerQr, dqrCurrentToken, sz);
        // Animate a quick flash on refresh
        elements.workerQr.style.opacity = "0.4";
        requestAnimationFrame(() => {
          elements.workerQr.style.transition = "opacity 0.35s ease";
          elements.workerQr.style.opacity = "1";
        });
      }
      // Also update gate QR if open
      if (elements.gateQr && !elements.gateQr.classList.contains("hidden")) {
        const gSz = isCompact ? 520 : 420;
        void setQrImage(elements.gateQr, dqrCurrentToken, gSz);
        setGateScannerFeedbackState("refresh", t("gateQrRefreshed"));
        queueGateScannerReadyState(1000);
      }
      // Update fallback text
      if (elements.qrFallbackText) elements.qrFallbackText.textContent = `Code: ${data.badgeId}`;
      haptic(30); // subtle pulse on QR refresh
      _updateQrCountdownDisplay();
      scheduleNextDynamicQrRefresh();
    }
  } catch {
    // offline or expired session — keep showing last token
    if (elements.gateScannerOverlay && !elements.gateScannerOverlay.classList.contains("hidden")) {
      setGateScannerFeedbackState("error", t("gateScanSyncDelayed"));
      queueGateScannerReadyState(2200);
      haptic([16, 34, 16]);
    }
    scheduleNextDynamicQrRefresh();
  }
}

/** Start polling for fresh dynamic QR tokens */
function startDynamicQrRefresh() {
  stopDynamicQrRefresh();
  // Fetch immediately
  void fetchAndDisplayDynamicQr();
  // Countdown every second
  dqrCountdownInterval = setInterval(() => {
    dqrRemainingSeconds = Math.max(0, dqrRemainingSeconds - 1);
    _updateQrCountdownDisplay();
  }, 1000);
}

/** Stop dynamic QR polling (e.g. on logout or when card is hidden) */
function stopDynamicQrRefresh() {
  if (dqrInterval) { clearInterval(dqrInterval); dqrInterval = null; }
  if (dqrRefreshTimeout) { clearTimeout(dqrRefreshTimeout); dqrRefreshTimeout = null; }
  if (dqrCountdownInterval) { clearInterval(dqrCountdownInterval); dqrCountdownInterval = null; }
  dqrCurrentToken = "";
  dqrRemainingSeconds = 60;
  dqrWindowSeconds = 60;
}

function normalizeBadgeIdInput(value) {
  return String(value || "")
    .trim()
    .toUpperCase()
    .replace(/[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]/g, "-")
    .replace(/\s+/g, "");
}

function normalizeBadgePinInput(value) {
  return String(value || "").replace(/\s+/g, "").trim();
}

function looksLikeBadgeId(value) {
  const normalized = normalizeBadgeIdInput(value);
  return normalized.length >= 6 && normalized.length <= 32 && /^[A-Z0-9-]+$/.test(normalized) && normalized.includes("-");
}

function isVisitorBadgeId(value) {
  return normalizeBadgeIdInput(value).startsWith("VS-") || normalizeBadgeIdInput(value).startsWith("VS");
}

function updateSiteMapLink(site) {
  if (!elements.workerSite) {
    return;
  }

  const normalizedSite = String(site || "").trim();
  if (!normalizedSite) {
    elements.workerSite.textContent = "-";
    elements.workerSite.setAttribute("href", "#");
    elements.workerSite.setAttribute("aria-disabled", "true");
    return;
  }

  const mapsUrl = new URL("https://www.google.com/maps/search/");
  mapsUrl.searchParams.set("api", "1");
  mapsUrl.searchParams.set("query", normalizedSite);
  elements.workerSite.textContent = normalizedSite;
  elements.workerSite.href = mapsUrl.toString();
  elements.workerSite.removeAttribute("aria-disabled");
}

function resolveApiRoot(workerApiBase) {
  return String(workerApiBase || "").replace(/\/api\/worker-app\/?$/, "");
}

function buildQrImageUrl(payload, size = 280) {
  const text = String(payload || "").trim();
  if (!text) {
    return "";
  }

  if (/^https?:\/\//i.test(API_ROOT)) {
    const url = new URL("/api/qr.png", API_ROOT);
    url.searchParams.set("data", text);
    url.searchParams.set("size", String(size));
    return url.toString();
  }

  const url = new URL("/api/qr.png", window.location.origin);
  url.searchParams.set("data", text);
  url.searchParams.set("size", String(size));
  return `${url.pathname}${url.search}`;
}

function getQrCacheKey(payload, size) {
  return `${QR_CACHE_PREFIX}:${size}:${payload}`;
}

function getCachedQr(payload, size) {
  const key = getQrCacheKey(payload, size);
  return localStorage.getItem(key) || "";
}

function setCachedQr(payload, size, dataUrl) {
  if (!dataUrl || !dataUrl.startsWith("data:image/png")) {
    return;
  }
  const key = getQrCacheKey(payload, size);
  localStorage.setItem(key, dataUrl);
}

async function fetchQrAsDataUrl(payload, size) {
  const url = buildQrImageUrl(payload, size);
  if (!url) {
    return "";
  }
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`qr_fetch_failed_${response.status}`);
  }
  const blob = await response.blob();
  return await blobToDataUrl(blob);
}

function blobToDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(typeof reader.result === "string" ? reader.result : "");
    reader.onerror = () => reject(new Error("blob_to_dataurl_failed"));
    reader.readAsDataURL(blob);
  });
}

async function setQrImage(imgElement, payload, size) {
  if (!imgElement || !payload) {
    return;
  }

  const cached = getCachedQr(payload, size);
  if (cached) {
    imgElement.src = cached;
  } else {
    const directUrl = buildQrImageUrl(payload, size);
    if (directUrl) {
      imgElement.src = directUrl;
    }
  }

  try {
    const freshDataUrl = await fetchQrAsDataUrl(payload, size);
    if (freshDataUrl) {
      setCachedQr(payload, size, freshDataUrl);
      imgElement.src = freshDataUrl;
    }
  } catch {
    if (!cached) {
      imgElement.alt = t("qrLoadFailedAlt");
    }
  }
}

function showBrightnessHintTemporarily() {
  if (!elements.gateBrightnessHint) {
    return;
  }
  elements.gateBrightnessHint.classList.remove("hidden");
  window.setTimeout(() => {
    if (elements.gateBrightnessHint) {
      elements.gateBrightnessHint.classList.add("hidden");
    }
  }, 6000);
}

async function requestGateFullscreen() {
  const panel = elements.gateScannerOverlay;
  if (!panel || document.fullscreenElement) {
    return;
  }
  const requestFullscreen = panel.requestFullscreen || panel.webkitRequestFullscreen;
  if (typeof requestFullscreen !== "function") {
    return;
  }
  try {
    await requestFullscreen.call(panel);
  } catch {
    // ignore fullscreen failures
  }
}

async function exitGateFullscreen() {
  const exitFullscreen = document.exitFullscreen || document.webkitExitFullscreen;
  if (typeof exitFullscreen !== "function" || !document.fullscreenElement) {
    return;
  }
  try {
    await exitFullscreen.call(document);
  } catch {
    // ignore fullscreen exit failures
  }
}

function isIosDevice() {
  const ua = navigator.userAgent || "";
  const platform = navigator.platform || "";
  const touchMac = platform === "MacIntel" && navigator.maxTouchPoints > 1;
  return /iPhone|iPad|iPod/i.test(ua) || touchMac;
}

function isAndroidDevice() {
  return /Android/i.test(navigator.userAgent || "");
}

  function isAndroidChrome() {
    const ua = navigator.userAgent || "";
    const isChrome = /Chrome\//i.test(ua) && !/EdgA\//i.test(ua) && !/OPR\//i.test(ua) && !/SamsungBrowser\//i.test(ua);
    return isAndroidDevice() && isChrome;
  }

function updatePlatformInstallHint() {
  if (!elements.installPlatformHint) {
    return;
  }

  if (isStandaloneMode()) {
    elements.installPlatformHint.textContent = t("installHintStandalone");
    return;
  }

  if (isIosDevice()) {
    elements.installPlatformHint.textContent = t("installHintIos");
    return;
  }

  if (isAndroidDevice()) {
      if (isAndroidChrome()) {
        elements.installPlatformHint.textContent = t("installHintAndroidChrome");
      } else {
        elements.installPlatformHint.textContent = t("installHintAndroidOther");
      }
    return;
  }

  elements.installPlatformHint.textContent = t("installHint");
}

async function requestWakeLock() {
  if (!navigator.wakeLock || wakeLockHandle) {
    return;
  }
  try {
    wakeLockHandle = await navigator.wakeLock.request("screen");
    wakeLockHandle.addEventListener("release", () => {
      wakeLockHandle = null;
    });
  } catch {
    wakeLockHandle = null;
  }
}

function releaseWakeLock() {
  if (!wakeLockHandle) {
    return;
  }
  wakeLockHandle.release().catch(() => {
    // ignore release failures
  });
  wakeLockHandle = null;
}

async function openCameraOverlay() {
  if (!elements.cameraOverlay || !elements.cameraVideo) {
    return;
  }

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
  const describeCameraError = (error) => {
    const name = String(error?.name || "").trim();
    const message = String(error?.message || "").trim();
    return [name, message].filter(Boolean).join(": ") || "unknown error";
  };
  const cameraDiagCodeForError = (error) => {
    const errorName = String(error?.name || "").trim();
    if (!window.isSecureContext) {
      return "CAM-HTTPS";
    }
    if (errorName === "NotAllowedError" || errorName === "SecurityError") {
      return "CAM-PERM";
    }
    if (errorName === "NotFoundError" || errorName === "DevicesNotFoundError") {
      return "CAM-NODEVICE";
    }
    if (errorName === "NotReadableError" || errorName === "TrackStartError") {
      return "CAM-INUSE";
    }
    if (errorName === "OverconstrainedError" || errorName === "ConstraintNotSatisfiedError") {
      return "CAM-CONSTRAINT";
    }
    if (errorName === "" && error?.message === "getUserMedia_not_supported") {
      return "CAM-API";
    }
    return "CAM-START";
  };
  const withCameraDiagCode = (message, code) => `${message} [${code}]`;

  if (!navigator.mediaDevices?.getUserMedia && !legacyGetUserMedia) {
    showWorkerNotice(withCameraDiagCode(t("cameraBlocked"), "CAM-API"));
    elements.photoInput?.click();
    return;
  }

  if (elements.photoPreviewWrap) elements.photoPreviewWrap.style.display = "none";
  if (elements.cameraCanvas) elements.cameraCanvas.style.display = "none";
  elements.cameraVideo.style.display = "block";
  if (elements.takePhotoButton) elements.takePhotoButton.style.display = "inline-block";
  if (elements.confirmPhotoButton) elements.confirmPhotoButton.style.display = "none";
  if (elements.retakePhotoButton) elements.retakePhotoButton.style.display = "none";

  elements.cameraOverlay.style.display = "flex";
  lastCameraPhotoDataUrl = null;
  lastCameraPhotoRotation = 0;

  const videoConstraintCandidates = [
    {
      facingMode: { ideal: "environment" },
      width: { ideal: 1280 },
      height: { ideal: 720 }
    },
    {
      facingMode: "environment"
    },
    {
      facingMode: { ideal: "user" },
      width: { ideal: 1280 },
      height: { ideal: 720 }
    },
    {
      facingMode: "user"
    },
    {
      width: { ideal: 1280 },
      height: { ideal: 720 }
    },
    {},
    true
  ];

  try {
    stopCameraStream();
    let stream = null;
    let lastError = null;

    for (const videoConstraint of videoConstraintCandidates) {
      try {
        stream = await requestUserMedia({
          video: videoConstraint,
          audio: false
        });
        if (stream) {
          break;
        }
      } catch (error) {
        lastError = error;
        // try next fallback constraint
      }
    }

    if (!stream && navigator.mediaDevices?.enumerateDevices) {
      const devices = await navigator.mediaDevices.enumerateDevices().catch(() => []);
      const videoInputs = devices.filter((device) => device.kind === "videoinput");
      for (const device of videoInputs) {
        try {
          stream = await requestUserMedia({
            video: { deviceId: { exact: device.deviceId } },
            audio: false
          });
          if (stream) {
            break;
          }
        } catch (error) {
          lastError = error;
        }
      }
    }

    if (!stream) {
      throw lastError || new Error("camera_unavailable");
    }

    cameraStream = stream;
    elements.cameraVideo.srcObject = stream;
    elements.cameraVideo.muted = true;
    elements.cameraVideo.autoplay = true;
    elements.cameraVideo.setAttribute("playsinline", "true");
    elements.cameraVideo.setAttribute("webkit-playsinline", "true");
    elements.cameraVideo.playsInline = true;
    await new Promise((resolve) => {
      const finalize = () => resolve();
      elements.cameraVideo.onloadedmetadata = finalize;
      window.setTimeout(finalize, 1200);
    });
    try {
      await elements.cameraVideo.play();
    } catch {
      // Keep stream active even if playback promise is blocked.
    }
  } catch (error) {
    const reason = describeCameraError(error);
    const diagCode = cameraDiagCodeForError(error);
    showWorkerNotice(
      window.isSecureContext
        ? withCameraDiagCode(`${t("cameraStartFailed")} (${reason})`, diagCode)
        : withCameraDiagCode(t("cameraHttpsHint"), "CAM-HTTPS")
    );
    closeCameraOverlay();
    elements.photoInput?.click();
  }
}

function stopCameraStream() {
  if (!cameraStream) {
    return;
  }
  cameraStream.getTracks().forEach((track) => track.stop());
  cameraStream = null;
}

function closeCameraOverlay() {
  if (elements.cameraOverlay) {
    elements.cameraOverlay.style.display = "none";
  }
  stopCameraStream();
  lastCameraPhotoDataUrl = null;
  lastCameraPhotoRotation = 0;
}

function takePhotoFromCamera() {
  if (!elements.cameraVideo || !elements.cameraCanvas) {
    return;
  }

  const video = elements.cameraVideo;
  if (!video.videoWidth || !video.videoHeight) {
    showWorkerNotice(t("cameraWaitReady"));
    return;
  }

  const canvas = elements.cameraCanvas;
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    return;
  }

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  lastCameraPhotoDataUrl = canvas.toDataURL("image/jpeg", 0.92);

  canvas.style.display = "block";
  video.style.display = "none";
  if (elements.photoPreviewWrap) elements.photoPreviewWrap.style.display = "flex";
  if (elements.takePhotoButton) elements.takePhotoButton.style.display = "none";
  if (elements.confirmPhotoButton) elements.confirmPhotoButton.style.display = "inline-block";
  if (elements.retakePhotoButton) elements.retakePhotoButton.style.display = "inline-block";
}

function retakeCameraPhoto() {
  if (!elements.cameraVideo || !elements.cameraCanvas) {
    return;
  }
  elements.cameraCanvas.style.display = "none";
  elements.cameraVideo.style.display = "block";
  if (elements.photoPreviewWrap) elements.photoPreviewWrap.style.display = "none";
  if (elements.takePhotoButton) elements.takePhotoButton.style.display = "inline-block";
  if (elements.confirmPhotoButton) elements.confirmPhotoButton.style.display = "none";
  if (elements.retakePhotoButton) elements.retakePhotoButton.style.display = "none";
  lastCameraPhotoDataUrl = null;
  lastCameraPhotoRotation = 0;
}

function rotateCameraPhoto() {
  if (!elements.cameraCanvas || !lastCameraPhotoDataUrl) {
    return;
  }
  lastCameraPhotoRotation = (lastCameraPhotoRotation + 90) % 360;

  const img = new window.Image();
  img.onload = () => {
    const canvas = elements.cameraCanvas;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      return;
    }

    if (lastCameraPhotoRotation % 180 === 0) {
      canvas.width = img.width;
      canvas.height = img.height;
    } else {
      canvas.width = img.height;
      canvas.height = img.width;
    }

    ctx.save();
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.translate(canvas.width / 2, canvas.height / 2);
    ctx.rotate((lastCameraPhotoRotation * Math.PI) / 180);
    ctx.drawImage(img, -img.width / 2, -img.height / 2);
    ctx.restore();

    lastCameraPhotoDataUrl = canvas.toDataURL("image/jpeg", 0.92);
  };
  img.src = lastCameraPhotoDataUrl;
}

function deleteCameraPhoto() {
  retakeCameraPhoto();
}

function confirmCameraPhoto() {
  if (!lastCameraPhotoDataUrl) {
    return;
  }

  closeCameraOverlay();

  if (elements.workerPhoto) {
    elements.workerPhoto.src = lastCameraPhotoDataUrl;
  }
  localStorage.setItem(LOCAL_LAST_PHOTO_KEY, lastCameraPhotoDataUrl);

  uploadPhotoToBackend(lastCameraPhotoDataUrl).catch(() => {
    savePhotoToOfflineQueue(lastCameraPhotoDataUrl);
    showWorkerNotice(t("photoOfflineQueued"));
  });
}

function handlePhotoSelected(event) {
  const file = event.target.files?.[0];
  if (!file) {
    return;
  }

  if (event.target) {
    event.target.value = "";
  }

  const reader = new FileReader();
  reader.onload = (loadEvent) => {
    const dataUrl = typeof loadEvent.target?.result === "string" ? loadEvent.target.result : "";
    if (!dataUrl) {
      return;
    }

    if (elements.workerPhoto) {
      elements.workerPhoto.src = dataUrl;
    }
    localStorage.setItem(LOCAL_LAST_PHOTO_KEY, dataUrl);

    uploadPhotoToBackend(dataUrl).catch(() => {
      savePhotoToOfflineQueue(dataUrl);
      showWorkerNotice(t("photoOfflineQueued"));
    });
  };
  reader.readAsDataURL(file);
}

async function uploadPhotoToBackend(dataUrl) {
  if (!workerToken) {
    throw new Error("missing_worker_token");
  }

  await fetchJson(`${API_BASE}/photo`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${workerToken}`
    },
    body: JSON.stringify({ photoData: dataUrl })
  });

  await loadWorkerData();
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    let code = "";
    let payload = null;
    try {
      payload = await response.json();
      code = payload?.error || "";
      message = payload?.message || payload?.error || message;
    } catch {
      // ignore parse errors
    }
    const error = new Error(message);
    error.code = code;
    error.payload = payload;
    throw error;
  }
  return response.json();
}

function formatDate(value) {
  if (!value) {
    return "-";
  }
  return new Intl.DateTimeFormat(getCurrentLocale(), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric"
  }).format(new Date(value));
}

function formatDateTime(value) {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return new Intl.DateTimeFormat(getCurrentLocale(), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(parsed);
}

function renderDayCardValidity(expiresAt) {
  if (!elements.workerDayCardValidity) {
    return;
  }
  if (!expiresAt) {
    elements.workerDayCardValidity.textContent = t("dayCardValidToday");
    return;
  }
  elements.workerDayCardValidity.textContent = tf("dayCardValidUntil", { time: formatDateTime(expiresAt) });
}

function clearWorkerSessionCountdown() {
  if (workerSessionCountdownInterval !== null) {
    window.clearInterval(workerSessionCountdownInterval);
    workerSessionCountdownInterval = null;
  }
}

function renderWorkerSessionCountdown(expiresAt) {
  // Worker cards (Mitarbeiter) don't show countdown timer - only visitors do
  // Mitarbeiter-Karten zeigen keinen Countdown - nur Besucher
  clearWorkerSessionCountdown();
  sessionExpiringSoonNotified = false;
  gateAutoOpenTriggered = false;
  if (!elements.workerSessionCountdown) {
    return;
  }
  // Hide worker session countdown for clean UI
  // Verstecke den Countdown für sauberes UI
  elements.workerSessionCountdown.textContent = "";
  elements.workerSessionCountdown.classList.remove("ok", "warn", "critical");
}

function clearWorkerSessionExpiryTimer() {
  if (workerSessionExpiryTimeout !== null) {
    window.clearTimeout(workerSessionExpiryTimeout);
    workerSessionExpiryTimeout = null;
  }
}

function stopVisitorCountdown() {
  if (visitorCountdownInterval !== null) {
    window.clearInterval(visitorCountdownInterval);
    visitorCountdownInterval = null;
  }
  if (elements.visitorCountdownBanner) {
    elements.visitorCountdownBanner.classList.add("hidden");
  }
}

function startVisitorCountdown(payload) {
  stopVisitorCountdown();
  if (!elements.visitorCountdownBanner || !elements.visitorCountdownTime) {
    return;
  }

  const worker = payload?.worker || {};
  const targetIso = String(worker.visitEndAt || payload?.sessionExpiresAt || "").trim();
  if (!targetIso) {
    return;
  }
  const targetMs = new Date(targetIso).getTime();
  if (!Number.isFinite(targetMs)) {
    return;
  }

  elements.visitorCountdownBanner.classList.remove("hidden");

  const update = () => {
    const remaining = targetMs - Date.now();
    if (remaining <= 0) {
      elements.visitorCountdownTime.textContent = "00:00:00";
      stopVisitorCountdown();
      showWorkerNotice(t("visitorCountdownExpired"));
      void workerLogout();
      return;
    }
    const totalSeconds = Math.floor(remaining / 1000);
    const h = String(Math.floor(totalSeconds / 3600)).padStart(2, "0");
    const m = String(Math.floor((totalSeconds % 3600) / 60)).padStart(2, "0");
    const s = String(totalSeconds % 60).padStart(2, "0");
    elements.visitorCountdownTime.textContent = `${h}:${m}:${s}`;
  };

  update();
  visitorCountdownInterval = window.setInterval(update, 1000);
}

function expireDailyCardInClient() {
  localStorage.removeItem(WORKER_TOKEN_KEY);
  workerToken = "";
  clearWorkerSessionExpiryTimer();
  closeGateMode();
  showLogin();
  showWorkerNotice(t("autoEndedAtMidnight"));
}

function scheduleWorkerSessionExpiry(expiresAt) {
  clearWorkerSessionExpiryTimer();
  renderWorkerSessionCountdown(expiresAt);
  if (!expiresAt) {
    return;
  }
  const parsed = new Date(expiresAt);
  if (Number.isNaN(parsed.getTime())) {
    return;
  }
  const msUntilExpiry = parsed.getTime() - Date.now();
  if (msUntilExpiry <= 0) {
    expireDailyCardInClient();
    return;
  }
  workerSessionExpiryTimeout = window.setTimeout(() => {
    expireDailyCardInClient();
  }, msUntilExpiry);
}

function createAvatar(firstName, lastName) {
  const initials = `${firstName?.[0] || ""}${lastName?.[0] || ""}`.toUpperCase();
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="280" height="340" viewBox="0 0 280 340">
      <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#d95d39"/><stop offset="100%" stop-color="#121417"/></linearGradient></defs>
      <rect width="280" height="340" rx="28" fill="url(#g)"/>
      <text x="50%" y="52%" text-anchor="middle" dominant-baseline="middle" font-family="Arial" font-size="84" fill="#fff7ef" font-weight="700">${initials}</text>
    </svg>
  `;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

// ═════════════════════════════════════════════════════════════════════
// ── FEATURE 1: DARK MODE TOGGLE ──
// ═════════════════════════════════════════════════════════════════════

function toggleTheme() {
  const current = localStorage.getItem(WORKER_THEME_KEY) || "auto";
  let next = "auto";
  if (current === "auto") next = "light";
  else if (current === "light") next = "dark";
  applyTheme(next);
  localStorage.setItem(WORKER_THEME_KEY, next);
}

function applyTheme(theme) {
  if (theme === "auto") {
    document.documentElement.removeAttribute("data-theme");
  } else {
    document.documentElement.setAttribute("data-theme", theme);
  }
}

// ═════════════════════════════════════════════════════════════════════
// ── FEATURE 2: PUSH NOTIFICATIONS (VAPID) ──
// ═════════════════════════════════════════════════════════════════════

async function requestNotificationPermission() {
  if (!("Notification" in window)) {
    showWorkerNotice(t("browserPushNotSupported"));
    return;
  }
  
  if (Notification.permission === "granted") {
    showWorkerNotice(t("notificationsAlreadyEnabled"));
    await subscribePushNotifications();
    return;
  }
  
  const permission = await Notification.requestPermission();
  if (permission === "granted") {
    showWorkerNotice(t("notificationsEnabled"));
    await subscribePushNotifications();
    if (elements.notificationBanner) {
      elements.notificationBanner.classList.add("hidden");
    }
  }
}

async function subscribePushNotifications() {
  try {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      return;
    }
    
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    
    if (subscription) {
      return;
    }
    
    const vapidKeyRes = await fetchJson(`${API_BASE}/push-vapid-key`);
    const vapidPublicKey = vapidKeyRes.vapidPublicKey;
    
    if (!vapidPublicKey) {
      console.warn("No VAPID public key from server");
      return;
    }
    
    const newSubscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(vapidPublicKey)
    });
    
    await fetchJson(`${API_BASE}/push-subscribe`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${workerToken}`
      },
      body: JSON.stringify({
        endpoint: newSubscription.endpoint,
        p256dh: arrayBufferToBase64(newSubscription.getKey("p256dh")),
        auth: arrayBufferToBase64(newSubscription.getKey("auth"))
      })
    });
    
    console.log("✓ Push subscription registered");
  } catch (error) {
    console.error("Push subscription failed:", error);
  }
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/\-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  return new Uint8Array([...rawData].map((char) => char.charCodeAt(0)));
}

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return window.btoa(binary);
}

// ═════════════════════════════════════════════════════════════════════
// ── FEATURE 3: LEAVE REQUESTS ──
// ═════════════════════════════════════════════════════════════════════

async function submitLeaveRequest() {
  if (!workerToken || !elements.leaveRequestForm) return;
  
  const type = elements.leaveRequestType?.value || "urlaub";
  const start = elements.leaveRequestStart?.value || "";
  const end = elements.leaveRequestEnd?.value || "";
  const note = elements.leaveRequestNote?.value || "";
  
  if (!start || !end) {
    showWorkerNotice(t("enterAccessCode")); // Reuse: please enter dates
    return;
  }
  if (start > end) {
    showWorkerNotice(t("leaveDateRangeInvalid"));
    return;
  }
  if (start > end) {
    showWorkerNotice(t("leaveDateRangeInvalid"));
    return;
  }
  
  try {
    const result = await fetchJson(`${API_BASE}/leave-requests`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${workerToken}`
      },
      body: JSON.stringify({ type, start_date: start, end_date: end, note })
    });
    lastSubmittedLeaveRequestId = String(result?.id || "");
    
    showWorkerNotice(t("leaveRequestSubmitted"));
    if (elements.sendToBossPanel) {
      elements.sendToBossPanel.classList.remove("hidden");
      if (elements.bossEmailInput && elements.leaveRequestBossEmail?.value) {
        elements.bossEmailInput.value = elements.leaveRequestBossEmail.value;
      }
    }
    elements.leaveRequestForm.reset();
    toggleLeaveRequestForm();
    await loadLeaveRequests();
  } catch (error) {
    showWorkerNotice(`Fehler: ${error.message}`);
  }
}

function applyAiLeaveSuggestion() {
  const type = elements.leaveRequestType?.value || "urlaub";
  const start = elements.leaveRequestStart?.value || "";
  const end = elements.leaveRequestEnd?.value || "";

  const typeLabel = type === "krank" ? "krankheitsbedingt" : type === "sonstiges" ? "aus persönlichem Grund" : "urlaubsbedingt";
  const dateRange = start && end ? `vom ${start} bis ${end}` : "im gewünschten Zeitraum";
  const suggestion = `Hiermit beantrage ich ${typeLabel} meine Abwesenheit ${dateRange}. Ich bitte um Genehmigung und danke für die Rückmeldung.`;

  if (elements.leaveRequestNote) {
    elements.leaveRequestNote.value = suggestion;
    showWorkerNotice(t("aiSuggestionInserted"));
  }
}

async function sendLastLeaveRequestToBoss() {
  if (!workerToken) return;
  if (!lastSubmittedLeaveRequestId) {
    showWorkerNotice(t("submitRequestFirst"));
    return;
  }
  const recipient = (elements.bossEmailInput?.value || "").trim();
  if (!recipient || !recipient.includes("@")) {
    showWorkerNotice(t("enterValidManagerEmail"));
    return;
  }

  try {
    await fetchJson(`${API_BASE}/leave-requests/${encodeURIComponent(lastSubmittedLeaveRequestId)}/send-email`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${workerToken}`
      },
      body: JSON.stringify({ recipient_email: recipient })
    });
    showWorkerNotice(t("sendToBossSuccess"));
  } catch (error) {
    showWorkerNotice(`${t("sendToBossError")}: ${error.message}`);
  }
}

async function prefillCompanyAdminEmails() {
  if (!workerToken) return;
  try {
    const admins = await fetchJson(`${API_BASE}/company-admins`, {
      headers: { Authorization: `Bearer ${workerToken}` }
    });
    if (!Array.isArray(admins) || admins.length === 0) return;

    const emailList = admins.map(a => a.email).filter(Boolean);
    const firstEmail = emailList[0] || "";

    const populateDatalist = (inputEl, listId) => {
      if (!inputEl) return;
      let dl = document.getElementById(listId);
      if (!dl) {
        dl = document.createElement("datalist");
        dl.id = listId;
        inputEl.parentNode.appendChild(dl);
      }
      dl.innerHTML = emailList.map(e => `<option value="${e}"></option>`).join("");
      inputEl.setAttribute("list", listId);
      if (!inputEl.value && firstEmail) inputEl.value = firstEmail;
    };

    populateDatalist(elements.leaveRequestBossEmail, "bossEmailDatalist1");
    populateDatalist(elements.bossEmailInput, "bossEmailDatalist2");
  } catch (_) {
    // Vorschlag ist optional – Fehler ignorieren
  }
}

function toggleLeaveRequestForm() {
  if (elements.leaveRequestToggleBtn) {
    elements.leaveRequestToggleBtn.textContent = isHidden ? t("leaveRequestNewBtn") : t("leaveRequestTitle");
  }
}

async function loadLeaveRequests() {
  if (!workerToken || !elements.leaveRequestList) return;
  
  try {
    const res = await fetchJson(`${API_BASE}/leave-requests`, {
      headers: { Authorization: `Bearer ${workerToken}` }
    });
    
    const requests = Array.isArray(res) ? res : res.requests || [];
    if (requests.length === 0) {
      elements.leaveRequestList.innerHTML = `<p class="muted-info">${t("leaveNoRequests") || "Keine Anträge vorhanden."}</p>`;
    } else {
      const sortedRequests = [...requests].sort((a, b) => {
        const aDate = String(a.start_date || a.created_at || "");
        const bDate = String(b.start_date || b.created_at || "");
        if (aDate === bDate) return 0;
        return aDate < bDate ? 1 : -1;
      });
      const visibleRequests = leaveCompactExpanded ? sortedRequests : sortedRequests.slice(0, 1);
      const hiddenCount = Math.max(0, sortedRequests.length - visibleRequests.length);

      const requestMarkup = visibleRequests.map((req) => {
        const typeMap = { urlaub: "Urlaub", krank: "Krank", sonderurlaub: "Sonderurlaub", unbezahlt: "Unbezahlt" };
        const typeLabel = typeMap[req.type] || req.type || "–";
        const statusCls = req.status === "genehmigt" ? "leave-status-ok" : req.status === "abgelehnt" ? "leave-status-no" : "leave-status-pending";
        const statusTxt = req.status === "genehmigt" ? "✓ Genehmigt" : req.status === "abgelehnt" ? "✗ Abgelehnt" : "⏳ Ausstehend";
        return `<div class="leave-request-item ${statusCls}">
          <div class="leave-req-row">
            <strong>${typeLabel}</strong>
            <span class="leave-req-badge ${statusCls}">${statusTxt}</span>
          </div>
          <div class="leave-req-dates">${req.start_date} → ${req.end_date}${req.days_count > 0 ? ` <span class="leave-req-days">${req.days_count} AT</span>` : ""}</div>
          ${req.note ? `<div class="leave-req-note">${req.note}</div>` : ""}
          ${req.review_note ? `<div class="leave-req-review">📋 ${req.review_note}</div>` : ""}
        </div>`;
      }).join("");

      const toggleMarkup = hiddenCount > 0 || leaveCompactExpanded
        ? `<button id="leaveRequestsCompactToggleBtn" class="ghost small-btn compact-list-toggle" type="button">${leaveCompactExpanded ? t("compactShowLess") : `${t("compactShowMore")} (+${hiddenCount})`}</button>`
        : "";

      elements.leaveRequestList.innerHTML = requestMarkup + toggleMarkup;

      const toggleBtn = document.querySelector("#leaveRequestsCompactToggleBtn");
      if (toggleBtn) {
        toggleBtn.addEventListener("click", () => {
          leaveCompactExpanded = !leaveCompactExpanded;
          void loadLeaveRequests();
        });
      }
    }
  } catch (error) {
    console.warn("Could not load leave requests:", error);
  }
}

// ═════════════════════════════════════════════════════════════════════
// ── FEATURE: TIMESHEETS (Stundennachweise) ──
// ═════════════════════════════════════════════════════════════════════

// ── Zu-spät-Banner ────────────────────────────────────────────────────────
function showLateCheckInBanner(lateInfo, isVisitor) {
  // Remove any existing banner
  const existing = document.getElementById("lateCheckInBanner");
  if (existing) existing.remove();
  if (isVisitor || !lateInfo || !lateInfo.today) return;

  const minutes = lateInfo.minutes || 0;
  const minutesText = minutes > 0 ? ` (${minutes} ${t("lateMinutesUnit") || "Min."})` : "";
  const msg = (t("lateCheckInMessage") || "Du bist heute zu spät eingestempelt").replace("{minutes}", minutesText) + minutesText;

  const banner = document.createElement("div");
  banner.id = "lateCheckInBanner";
  banner.className = "late-checkin-banner";
  banner.setAttribute("role", "alert");
  banner.innerHTML = `
    <span class="late-banner-icon">⚠️</span>
    <span class="late-banner-text">${msg}</span>
    <button class="late-banner-close" aria-label="Schließen" onclick="this.parentElement.remove()">×</button>
  `;

  // Insert after the wallet card or at top of main content
  const walletCard = document.querySelector(".wallet-card");
  if (walletCard && walletCard.parentElement) {
    walletCard.parentElement.insertBefore(banner, walletCard.nextSibling);
  } else {
    const main = document.querySelector("main") || document.querySelector(".worker-main") || document.body;
    main.prepend(banner);
  }
}

async function loadMyTimesheets() {
  if (!workerToken || !elements.timesheetList) return;
  elements.timesheetList.innerHTML = `<p class="muted-info">${t("timesheetLoading")}</p>`;
  try {
    const rows = await fetchJson(`${API_BASE}/my-timesheets`, {
      headers: { Authorization: `Bearer ${workerToken}` }
    });
    if (!Array.isArray(rows) || rows.length === 0) {
      elements.timesheetList.innerHTML = `<p class="muted-info">${t("timesheetEmpty")}</p>`;
      return;
    }
    // Group by date
    const byDate = {};
    for (const row of rows) {
      const date = (row.timestamp || "").slice(0, 10);
      if (!byDate[date]) byDate[date] = [];
      byDate[date].push(row);
    }
    const dayGroups = Object.entries(byDate).sort(([aDate], [bDate]) => {
      if (aDate === bDate) return 0;
      return aDate < bDate ? 1 : -1;
    });
    const visibleDayGroups = timesheetCompactExpanded ? dayGroups : dayGroups.slice(0, 2);
    const daysHiddenCount = Math.max(0, dayGroups.length - visibleDayGroups.length);

    const dayMarkup = visibleDayGroups.map(([date, entries]) => {
        // Pair IN/OUT entries to calculate total hours
        const ins = entries.filter(e => (e.direction || "").toLowerCase() === "in").sort((a,b) => a.timestamp > b.timestamp ? 1 : -1);
        const outs = entries.filter(e => (e.direction || "").toLowerCase() === "out").sort((a,b) => a.timestamp > b.timestamp ? 1 : -1);
        let totalMin = 0;
        const pairCount = Math.min(ins.length, outs.length);
        for (let i = 0; i < pairCount; i++) {
          const inTime = new Date(ins[i].timestamp);
          const outTime = new Date(outs[i].timestamp);
          if (outTime > inTime) totalMin += (outTime - inTime) / 60000;
        }
        const totalLabel = totalMin > 0 ? `${Math.floor(totalMin/60)}:${String(Math.round(totalMin%60)).padStart(2,"0")} h` : "";
        return `<div class="timesheet-day">
        <div class="timesheet-date-row">
          <span class="timesheet-date">${formatDate(date)}</span>
          ${totalLabel ? `<span class="timesheet-total">${totalLabel}</span>` : ""}
        </div>
        ${entries.map((e) => {
          const isIn = (e.direction || "").toLowerCase() === "in";
          return `<div class="timesheet-entry ${isIn ? "entry-in" : "entry-out"}">
            <span class="entry-direction">${isIn ? t("timesheetDirectionIn") : t("timesheetDirectionOut")}</span>
            <span class="entry-time">${(e.timestamp || "").slice(11, 16)}</span>
            ${e.gate ? `<span class="entry-gate">${e.gate}</span>` : ""}
          </div>`;
        }).join("")}
      </div>`;
      }).join("");

    const toggleMarkup = daysHiddenCount > 0 || timesheetCompactExpanded
      ? `<button id="timesheetCompactToggleBtn" class="ghost small-btn compact-list-toggle" type="button">${timesheetCompactExpanded ? t("compactShowLess") : `${t("compactShowMore")} (+${daysHiddenCount})`}</button>`
      : "";

    elements.timesheetList.innerHTML = dayMarkup + toggleMarkup;

    const toggleBtn = document.querySelector("#timesheetCompactToggleBtn");
    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => {
        timesheetCompactExpanded = !timesheetCompactExpanded;
        void loadMyTimesheets();
      });
    }
  } catch (error) {
    elements.timesheetList.innerHTML = `<p class="muted-info">${t("timesheetEmpty")}</p>`;
    console.warn("Could not load timesheets:", error);
  }
}

// ═════════════════════════════════════════════════════════════════════
// ── FEATURE: DOCUMENTS (Meine Dokumente) ──
// ═════════════════════════════════════════════════════════════════════

async function loadMyDocuments() {
  if (!workerToken || !elements.documentsList) return;
  elements.documentsList.innerHTML = `<p class="muted-info">${t("documentsLoading")}</p>`;
  try {
    const rows = await fetchJson(`${API_BASE}/my-documents`, {
      headers: { Authorization: `Bearer ${workerToken}` }
    });
    if (!Array.isArray(rows) || rows.length === 0) {
      elements.documentsList.innerHTML = `<p class="muted-info">${t("documentsEmpty")}</p>`;
      return;
    }
    const today = new Date().toISOString().slice(0, 10);
    const soon = new Date(); soon.setDate(soon.getDate() + 30);
    const soonStr = soon.toISOString().slice(0, 10);

    // Ablauf-Warnung Banner
    const expiringSoon = rows.filter(d => d.expiry_date && d.expiry_date > today && d.expiry_date <= soonStr);
    const expired = rows.filter(d => d.expiry_date && d.expiry_date <= today);
    let warningBanner = "";
    if (expired.length > 0) {
      warningBanner += `<div class="doc-warning-banner doc-warning-expired">⚠️ ${expired.length} Dokument${expired.length > 1 ? "e" : ""} abgelaufen</div>`;
    }
    if (expiringSoon.length > 0) {
      warningBanner += `<div class="doc-warning-banner doc-warning-soon">🕐 ${expiringSoon.length} Dokument${expiringSoon.length > 1 ? "e laufen" : " läuft"} bald ab</div>`;
    }

    const sortedRows = [...rows].sort((a, b) => {
      const aExpiry = String(a.expiry_date || "");
      const bExpiry = String(b.expiry_date || "");
      const aExpired = Boolean(aExpiry && aExpiry <= today);
      const bExpired = Boolean(bExpiry && bExpiry <= today);
      const aSoon = Boolean(aExpiry && aExpiry > today && aExpiry <= soonStr);
      const bSoon = Boolean(bExpiry && bExpiry > today && bExpiry <= soonStr);

      const aPriority = aExpired ? 0 : aSoon ? 1 : 2;
      const bPriority = bExpired ? 0 : bSoon ? 1 : 2;
      if (aPriority !== bPriority) return aPriority - bPriority;

      if (aExpiry && bExpiry && aExpiry !== bExpiry) {
        return aExpiry < bExpiry ? -1 : 1;
      }
      const aType = String(a.doc_type || "").toLowerCase();
      const bType = String(b.doc_type || "").toLowerCase();
      if (aType === bType) return 0;
      return aType < bType ? -1 : 1;
    });

    const visibleRows = documentsCompactExpanded ? sortedRows : sortedRows.slice(0, 2);
    const docsHiddenCount = Math.max(0, rows.length - visibleRows.length);
    const docsMarkup = visibleRows.map((doc) => {
      const isExpired = doc.expiry_date && doc.expiry_date < today;
      const statusLabel = doc.expiry_date
        ? (isExpired ? t("documentsStatusExpired") : t("documentsStatusOk"))
        : t("documentsStatusNoExpiry");
      const statusClass = doc.expiry_date
        ? (isExpired ? "doc-expired" : "doc-ok")
        : "doc-no-expiry";
      return `<div class="document-item ${statusClass}">
        <div class="doc-type">${escapeHtmlBasic(doc.doc_type?.replace(/_/g, " ") || "–")}</div>
        <div class="doc-meta">
          ${doc.expiry_date ? `<span>${t("documentsExpiry")}: ${formatDate(doc.expiry_date)}</span>` : ""}
          <span class="doc-status-badge ${statusClass}">${statusLabel}</span>
        </div>
      </div>`;
    }).join("");

    const toggleMarkup = docsHiddenCount > 0 || documentsCompactExpanded
      ? `<button id="documentsCompactToggleBtn" class="ghost small-btn compact-list-toggle" type="button">${documentsCompactExpanded ? t("compactShowLess") : `${t("compactShowMore")} (+${docsHiddenCount})`}</button>`
      : "";

    elements.documentsList.innerHTML = warningBanner + docsMarkup + toggleMarkup;

    const toggleBtn = document.querySelector("#documentsCompactToggleBtn");
    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => {
        documentsCompactExpanded = !documentsCompactExpanded;
        void loadMyDocuments();
      });
    }
  } catch (error) {
    elements.documentsList.innerHTML = `<p class="muted-info">${t("documentsEmpty")}</p>`;
    console.warn("Could not load documents:", error);
  }
}

function escapeHtmlBasic(str) {
  return String(str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** Zählt Arbeitstage (Mo–Fr) zwischen start und end (inkl.) */
function countWorkingDays(startStr, endStr) {
  const start = new Date(startStr);
  const end = new Date(endStr);
  let count = 0;
  const cur = new Date(start);
  while (cur <= end) {
    const dow = cur.getDay();
    if (dow !== 0 && dow !== 6) count++;
    cur.setDate(cur.getDate() + 1);
  }
  return count;
}

// ═════════════════════════════════════════════════════════════════════
// ── FEATURE 4: VOICE COMMANDS (Web Speech API) ──
// ═════════════════════════════════════════════════════════════════════

let voiceRecognition = null;
let isListening = false;

function initVoiceCommands() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    showWorkerNotice(t("voiceNotSupported"));
    return;
  }

  if (!window.isSecureContext) {
    showWorkerNotice(t("voiceNeedsSecureContext"));
    return;
  }
  
  if (!voiceRecognition) {
    voiceRecognition = new SpeechRecognition();
    const langMap = {
      de: "de-DE",
      en: "en-GB",
      tr: "tr-TR",
      ar: "ar-SA",
      fr: "fr-FR",
      es: "es-ES",
      it: "it-IT",
      pl: "pl-PL"
    };
    voiceRecognition.lang = langMap[currentLang] || "de-DE";
    voiceRecognition.continuous = false;
    voiceRecognition.interimResults = false;
    
    voiceRecognition.onstart = () => {
      isListening = true;
      if (elements.voiceCommandBtn) {
        elements.voiceCommandBtn.classList.add("listening");
      }
      showWorkerNotice(t("voiceListening"));
    };
    
    voiceRecognition.onend = () => {
      isListening = false;
      if (elements.voiceCommandBtn) {
        elements.voiceCommandBtn.classList.remove("listening");
      }
    };
    
    voiceRecognition.onerror = (event) => {
      const code = String(event.error || "");
      if (code === "not-allowed" || code === "service-not-allowed") {
        showWorkerNotice(t("microphoneAccessBlocked"));
        return;
      }
      if (code === "no-speech") {
        showWorkerNotice(t("noSpeechDetected"));
        return;
      }
      showWorkerNotice(`Fehler: ${code || "unknown"}`);
    };
    
    voiceRecognition.onresult = (event) => {
      let interimTranscript = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          processVoiceCommand(transcript);
        } else {
          interimTranscript += transcript;
        }
      }
      if (interimTranscript) {
        showWorkerNotice(`Hört: "${interimTranscript}"`);
      }
    };
  }
  
  if (isListening) {
    voiceRecognition.stop();
  } else {
    voiceRecognition.start();
  }
}

function processVoiceCommand(text) {
  const cmd = text.toLowerCase().trim();
  showWorkerNotice(`Befehl: "${text}"`);
  
  if (cmd.includes("ausbuchen") || cmd.includes("checkout")) {
    openGateMode();
  } else if (cmd.includes("antrag") || cmd.includes("urlaub")) {
    toggleLeaveRequestForm();
  } else if (cmd.includes("thema") || cmd.includes("theme")) {
    toggleTheme();
  } else if (cmd.includes("beenden") || cmd.includes("exit")) {
    if (!elements.gateScannerOverlay?.classList.contains("hidden")) {
      closeGateMode();
    }
  } else {
    showWorkerNotice(`"${text}" nicht erkannt. Versuchen Sie: Ausbuchen, Antrag, Thema`);
  }
}

// ═════════════════════════════════════════════════════════════════════
// ── FEATURE 5: OFFLINE QUEUE + IndexedDB ──
// ═════════════════════════════════════════════════════════════════════

async function initOfflineStorage() {
  // Already handled by existing offline queue in localStorage
  // IndexedDB can be added here for larger data persistence
  if (!("indexedDB" in window)) {
    console.warn("IndexedDB not supported");
    return;
  }
  
  try {
    const db = indexedDB.open("baupass-offline", 1);
    db.onupgradeneeded = (event) => {
      const idb = event.target.result;
      if (!idb.objectStoreNames.contains("events")) {
        idb.createObjectStore("events", { keyPath: "id", autoIncrement: true });
      }
    };
  } catch (error) {
    console.warn("Could not init IndexedDB:", error);
  }
}

// ═════════════════════════════════════════════════════════════════════
// ── INITIALIZATION ──
// ═════════════════════════════════════════════════════════════════════

// Apply stored theme on load
const storedTheme = localStorage.getItem(WORKER_THEME_KEY) || "auto";
applyTheme(storedTheme);

// Initialize offline storage
void initOfflineStorage();

// Show notification permission banner if not yet granted
if ("Notification" in window && Notification.permission === "default" && elements.notificationBanner) {
  elements.notificationBanner.classList.remove("hidden");
}

// Load leave requests on login
if (workerToken) {
  void loadLeaveRequests();
}

// ─────────────────────────────────────────────────────────────────────
// STARTUP: Force immediate card render if worker data exists
// ─────────────────────────────────────────────────────────────────────

console.log("[worker-app init] workerToken:", workerToken ? "present" : "missing");

if (workerToken) {
  const cachedPayloadRaw = localStorage.getItem(WORKER_CACHED_PAYLOAD_KEY);
  if (cachedPayloadRaw) {
    try {
      const cachedPayload = JSON.parse(cachedPayloadRaw);
      console.log("[worker-app init] Found cached payload, rendering immediately...");
      // Render cached data immediately without waiting for network
      renderWorker(cachedPayload);
      // Then refresh from network in background
      void loadWorkerData();
    } catch (err) {
      console.error("[worker-app init] Cache parse failed:", err);
      void loadWorkerData();
    }
  } else {
    console.log("[worker-app init] No cached payload, fetching fresh...");
    void loadWorkerData();
  }
} else {
  console.log("[worker-app init] No token, showing login");
  showLogin();
}
