/**
 * SUPPIX AI Operator FAB — additive floating assistant for company admins.
 * Keeps existing Copilot / AI Command Center intact; this is a ubiquitous entry point.
 * Loaded on every HTML page via server inject (and optional page tags). Singleton-safe.
 */
(function (global) {
  "use strict";

  if (global.BaupassAiOperator && global.BaupassAiOperator.__boot) {
    return;
  }

  const VERSION = "20260725r";
  const VOICE_UI_VERSION = "20260725voice13";
  const HANDS_FREE_KEY = "baupass-ai-hands-free";
  const SESSION_STORE_KEY = "baupass-aio-session-id";
  const WELCOME_STORE_KEY = "baupass-aio-welcome";
  const AMBIENT_KEY = "baupass-aio-ambient";
  const COMPANY_ENABLED_KEY = "baupass-aio-company-enabled";
  const RECENT_PROMPTS_KEY = "baupass-aio-recent-prompts";
  const URGENCY_TOAST_KEY = "baupass-aio-urgency-toast";
  const FAB_POS_KEY = "baupass-aio-fab-pos-v1";
  let lastUserQuestion = "";
  /** Spoken-language override for this browser tab (Whisper / heuristic). */
  let sessionLangOverride = "";
  let confirmVoiceMode = false;
  /** Blocks overlapping listen/send cycles until one full turn finishes. */
  let voiceTurnLock = false;
  let lastVoiceSubmitAt = 0;
  let lastVoiceSubmitText = "";
  /** Company preference: when false, FAB is hidden everywhere for this company. */
  let companyOperatorEnabled = true;
  let companyVoiceEnabled = true;
  let companyWelcomeEnabled = true;
  let companySettingsLoaded = false;
  let _lastSettingsProbe = 0;
  /** Transcript waiting for operator to verify before send. */
  let pendingVerifyText = "";
  let pendingVerifyLang = "";
  let pendingVerifySpoken = false;
  const SKIP_PATHS = [
    /\/ai-command-center\.html$/i,
    /\/desktop\/splash\.html$/i,
    /\/desktop\/incoming-call\.html$/i,
    /\/contract-sign\.html$/i,
    /\/handover-sign\.html$/i,
  ];
  const WRITE_ACTIONS = new Set([
    "resolve_security_alert",
    "send_briefing_email",
    "send_briefing_webhook",
    "export_briefing_markdown",
    "approve_leave_request",
    "reject_leave_request",
    "notify_worker",
    "ack_system_alert",
    "prepare_deployment_month",
    "confirm_send_deployment_month",
    "remind_expired_documents",
    "remind_late_workers",
    "resolve_open_security_alerts",
    "ack_open_system_alerts",
    "broadcast_worker_message",
    "export_ops_snapshot",
    "resolve_inbox_item",
  ]);
  const ADMIN_ROLES = new Set(["company-admin", "superadmin", "admin"]);

  function isEmbeddedFrame() {
    try {
      return window.self !== window.top;
    } catch {
      return true;
    }
  }

  const STR = {
    de: {
      fabLabel: "KI-Assistent öffnen (Alt+A)",
      title: "Betriebs-Assistent",
      voiceBadgeOk: "Stimme bereit",
      voiceBadgeLimited: "Stimme eingeschränkt (Browser)",
      urgencyToast: "Achtung: offene Betriebsrisiken — Assistent tippen.",
      recentLabel: "Zuletzt",
      subtitle: "Fragen · planen · nach Ihrer Bestätigung ausführen",
      placeholder: "z. B. Wer ist heute vor Ort? Einsatzplan vorbereiten…",
      send: "Senden",
      thinking: "Denke nach…",
      idle: "Fragen Sie in Alltagssprache. Lesen ist sofort — Schreiben nur nach Bestätigung.",
      close: "Schließen",
      expand: "Volles KI-Center",
      confirmTitle: "Bestätigung erforderlich",
      confirmHint: "Diese Aktion ändert Daten oder benachrichtigt Personen. Bitte prüfen.",
      approve: "Bestätigen",
      reject: "Ablehnen",
      approved: "Ausgeführt.",
      rejected: "Abgelehnt.",
      open: "Öffnen",
      needAuth: "Bitte zuerst anmelden.",
      needCompany: "Bitte eine Firma wählen.",
      errGeneric: "Antwort fehlgeschlagen.",
      tools: "Tools",
      chipOnSite: "Wer ist vor Ort?",
      chipBriefing: "Tageslage",
      chipLate: "Wer kommt zu spät?",
      chipDocs: "Abgelaufene Dokumente?",
      chipPlan: "Einsatzplan vorbereiten",
      chipInbox: "Offene Aufgaben?",
      chipForecast: "Morgen-Prognose",
      chipSecurity: "Security prüfen",
      chipBroadcast: "An alle schreiben",
      chipSameReminder: "Gleiche Erinnerung wie gestern",
      welcomeSpeak: "Willkommen. Wie kann ich Ihnen heute helfen?",
      confirmAskVoice: "Ich habe das vorbereitet und zeige es Ihnen. Soll ich das wirklich ausführen?",
      ambientListening: "Zuhören… Satz zu Ende sprechen — nach ~5 Sek. Pause erscheint der Text zum Prüfen.",
      ambientReady: "Bereit. Sprechen → Text wächst → ~5 Sek. Pause → prüfen → Senden.",
      heardPrefix: "Ich habe verstanden:",
      briefingAskNext: "Was möchten Sie jetzt zuerst angehen?",
      stopListen: "Zuhören stoppen",
      langDetected: "Sprache erkannt",
      uiPilotDone: "Oberfläche bedient.",
      sensitiveAsk: "Sensible Details anzeigen?",
      sensitiveYes: "Ja, anzeigen",
      sensitiveNo: "Nein",
      voiceHint: "Mic tippen → in Ruhe sprechen → nach ~5 Sek. Pause wird der Text gesendet.",
      voiceListening: "Zuhören… sprechen Sie aus. Nach ~5 Sek. Stille: Text → Senden.",
      voiceTranscribing: "Sprache wird erkannt…",
      voiceNoSpeech: "Satz unvollständig — bitte weiter sprechen (mindestens zwei Wörter).",
      voiceWhisperMissing: "OPENAI_API_KEY fehlt — Arabisch funktioniert ohne Whisper nicht. DE/EN: voller Satz, dann ~5 Sek. Pause.",
      voiceVerifyHint: "Vollständigen Text prüfen — dann «Senden». Kein Auto-Send.",
      voiceVerifyTitle: "Bitte prüfen",
      voiceVerifySend: "Senden",
      voiceVerifyRetry: "Nochmal sprechen",
      voiceVerifyAsk: "Ich habe das verstanden. Bitte prüfen Sie den Text und tippen Sie Senden.",
      voiceUnavailable: "Spracheingabe hier nicht verfügbar — Text funktioniert weiterhin.",
      voicePrep: "Sprachmodus vorbereitet",
      handsFreeOn: "Hands-free an — nach Antwort wieder zuhören",
      handsFreeOff: "Hands-free aus",
      handsFreeBlocked: "Hands-free pausiert — bitte zuerst bestätigen oder ablehnen.",
      followupPlaceholder: "Nachfrage stellen…",
      followupHint: "Weiterfragen unter der Antwort — Mic tippen oder halten.",
      botLabel: "SUPPIX KI",
      msgCopy: "Kopieren",
      msgCopied: "Kopiert.",
      msgLike: "Hilfreich",
      msgDislike: "Nicht hilfreich",
      msgReadAloud: "Vorlesen",
      msgStopReading: "Vorlesen stoppen",
      msgRegenerate: "Erneut generieren",
      msgNoRegen: "Keine vorherige Frage zum erneuten Generieren.",
      msgShare: "Teilen",
      msgShareCopied: "Antwort in die Zwischenablage kopiert.",
      msgMore: "Mehr",
      newChat: "Neuer Chat",
      newChatDone: "Neuer Chat gestartet.",
      sources: "Quellen",
      companyLabel: "Firma",
      showChips: "Schnellwahl zeigen",
      hideChips: "Schnellwahl ausblenden",
    },
    en: {
      fabLabel: "Open AI assistant (Alt+A)",
      title: "Operations Assistant",
      voiceBadgeOk: "Voice ready",
      voiceBadgeLimited: "Voice limited (browser)",
      urgencyToast: "Attention: open operational risks — tap the assistant.",
      recentLabel: "Recent",
      subtitle: "Ask · plan · execute only after your confirmation",
      placeholder: "e.g. Who is on site today? Prepare deployment plan…",
      send: "Send",
      thinking: "Thinking…",
      idle: "Ask in plain language. Reads are instant — writes need your confirmation.",
      close: "Close",
      expand: "Full AI Center",
      confirmTitle: "Confirmation required",
      confirmHint: "This changes data or notifies people. Please review.",
      approve: "Confirm",
      reject: "Reject",
      approved: "Done.",
      rejected: "Rejected.",
      open: "Open",
      needAuth: "Please sign in first.",
      needCompany: "Please select a company.",
      errGeneric: "Request failed.",
      tools: "Tools",
      chipOnSite: "Who is on site?",
      chipBriefing: "Daily briefing",
      chipLate: "Who is late?",
      chipDocs: "Expired documents?",
      chipPlan: "Prepare deployment plan",
      chipInbox: "Open tasks?",
      chipForecast: "Tomorrow forecast",
      chipSecurity: "Check security",
      chipBroadcast: "Message everyone",
      chipSameReminder: "Same reminder as yesterday",
      welcomeSpeak: "Welcome. How can I help you today?",
      confirmAskVoice: "I prepared this and show it on screen. Should I really execute it?",
      ambientListening: "Listening… finish your sentence — after ~5s pause the full text appears to review.",
      ambientReady: "Ready. Speak → text grows → ~5s pause → review → Send.",
      heardPrefix: "I heard:",
      briefingAskNext: "What should we start with first?",
      stopListen: "Stop listening",
      langDetected: "Language detected",
      uiPilotDone: "UI action done.",
      sensitiveAsk: "Show sensitive details?",
      sensitiveYes: "Yes, show",
      sensitiveNo: "No",
      voiceHint: "Tap mic → speak calmly → after ~5s pause the text is sent.",
      voiceListening: "Listening… finish speaking. After ~5s silence: text → send.",
      voiceTranscribing: "Recognizing speech…",
      voiceNoSpeech: "Incomplete sentence — keep speaking (at least two words).",
      voiceWhisperMissing: "OPENAI_API_KEY missing — Arabic needs Whisper. DE/EN: full sentence, then ~5s pause.",
      voiceVerifyHint: "Review the full text — then tap Send. No auto-send.",
      voiceVerifyTitle: "Please review",
      voiceVerifySend: "Send",
      voiceVerifyRetry: "Speak again",
      voiceVerifyAsk: "I captured this. Please review the text and tap Send.",
      voiceUnavailable: "Voice input unavailable here — text still works.",
      voicePrep: "Voice mode ready",
      handsFreeOn: "Hands-free on — listen again after reply",
      handsFreeOff: "Hands-free off",
      handsFreeBlocked: "Hands-free paused — confirm or reject first.",
      followupPlaceholder: "Ask a follow-up…",
      followupHint: "Follow up under the answer — tap or hold the mic.",
      botLabel: "SUPPIX AI",
      msgCopy: "Copy",
      msgCopied: "Copied.",
      msgLike: "Helpful",
      msgDislike: "Not helpful",
      msgReadAloud: "Read aloud",
      msgStopReading: "Stop reading",
      msgRegenerate: "Regenerate",
      msgNoRegen: "No previous question to regenerate.",
      msgShare: "Share",
      msgShareCopied: "Answer copied to clipboard.",
      msgMore: "More",
      newChat: "New chat",
      newChatDone: "New chat started.",
      sources: "Sources",
      companyLabel: "Company",
      showChips: "Show quick prompts",
      hideChips: "Hide quick prompts",
    },
    ar: {
      fabLabel: "فتح المساعد (Alt+A)",
      title: "مساعد التشغيل",
      voiceBadgeOk: "الصوت جاهز",
      voiceBadgeLimited: "الصوت محدود (المتصفح)",
      urgencyToast: "تنبيه: مخاطر تشغيل مفتوحة — اضغط المساعد.",
      recentLabel: "الأخيرة",
      subtitle: "اسأل · خطّط · التنفيذ فقط بعد تأكيدك",
      placeholder: "مثال: من في الموقع اليوم؟ جهّز خطة الانتشار…",
      send: "إرسال",
      thinking: "جارٍ التفكير…",
      idle: "اسأل بلغة يومية. القراءة فورية — أي كتابة تحتاج تأكيدك.",
      close: "إغلاق",
      expand: "مركز الذكاء الكامل",
      confirmTitle: "يلزم التأكيد",
      confirmHint: "هذا يغيّر بيانات أو يُشعر أشخاصاً. راجع قبل الموافقة.",
      approve: "تأكيد",
      reject: "رفض",
      approved: "تم التنفيذ.",
      rejected: "تم الرفض.",
      open: "فتح",
      needAuth: "يرجى تسجيل الدخول أولاً.",
      needCompany: "يرجى اختيار شركة.",
      errGeneric: "فشل الطلب.",
      tools: "أدوات",
      chipOnSite: "من في الموقع؟",
      chipBriefing: "ملخص اليوم",
      chipLate: "من يتأخر؟",
      chipDocs: "وثائق منتهية؟",
      chipPlan: "تجهيز خطة الانتشار",
      chipInbox: "مهام مفتوحة؟",
      chipForecast: "توقع الغد",
      chipSecurity: "فحص الأمن",
      chipBroadcast: "رسالة للجميع",
      chipSameReminder: "Same reminder as yesterday",
      welcomeSpeak: "أهلاً وسهلاً. كيف أساعدك اليوم؟",
      confirmAskVoice: "جهّزت هذا وأعرضه على الشاشة. هل أنفّذه بالتأكيد؟",
      ambientListening: "أستمع… أكمل الجملة — بعد صمت ~5 ثوانٍ يظهر النص كاملاً للمراجعة.",
      ambientReady: "جاهز. تكلّم → يظهر النص → صمت ~5 ثوانٍ → راجع → أرسل بنفسك.",
      heardPrefix: "فهمت:",
      briefingAskNext: "ماذا نبدأ أولاً؟",
      stopListen: "إيقاف الاستماع",
      langDetected: "تم تمييز اللغة",
      uiPilotDone: "تم تشغيل الواجهة.",
      sensitiveAsk: "عرض التفاصيل الحساسة؟",
      sensitiveYes: "نعم، اعرض",
      sensitiveNo: "لا",
      voiceHint: "اضغط الميكروفون → تكلّم بهدوء → بعد صمت ~5 ثوانٍ يُرسل النص.",
      voiceListening: "أستمع… أكمل كلامك. بعد صمت ~5 ثوانٍ: النص ثم الإرسال.",
      voiceTranscribing: "جارٍ التعرف على الكلام…",
      voiceNoSpeech: "الجملة غير مكتملة — أكمل الحديث (كلمتان على الأقل).",
      voiceWhisperMissing: "لا يوجد OPENAI_API_KEY — العربية تحتاج Whisper على السيرفر. بدون المفتاح لن تُفهم العربية جيداً.",
      voiceVerifyHint: "راجع النص كاملاً في الحقل — ثم اضغط «إرسال» بيدك. لا إرسال تلقائي.",
      voiceVerifyTitle: "يرجى المراجعة",
      voiceVerifySend: "إرسال",
      voiceVerifyRetry: "تحدّث مجدداً",
      voiceVerifyAsk: "فهمت هذا. راجع النص ثم اضغط إرسال.",
      voiceUnavailable: "الإدخال الصوتي غير متاح هنا — النص يعمل كالمعتاد.",
      voicePrep: "وضع الصوت جاهز",
      handsFreeOn: "وضع حر اليدين يعمل — يستمع بعد الرد",
      handsFreeOff: "وضع حر اليدين متوقف",
      handsFreeBlocked: "إيقاف مؤقت — أكّد أو ارفض أولاً.",
      followupPlaceholder: "اطرح سؤالاً متابعة…",
      followupHint: "متابعة تحت الإجابة — اضغط أو اضغط مطوّلاً على الميكروفون.",
      botLabel: "SUPPIX AI",
      msgCopy: "نسخ",
      msgCopied: "تم النسخ.",
      msgLike: "مفيد",
      msgDislike: "غير مفيد",
      msgReadAloud: "قراءة بصوت",
      msgStopReading: "إيقاف القراءة",
      msgRegenerate: "إعادة التوليد",
      msgNoRegen: "لا يوجد سؤال سابق لإعادة التوليد.",
      msgShare: "مشاركة",
      msgShareCopied: "تم نسخ الرد.",
      msgMore: "المزيد",
      newChat: "محادثة جديدة",
      newChatDone: "بدأت محادثة جديدة.",
      sources: "المصادر",
      companyLabel: "الشركة",
      showChips: "إظهار الاختصارات",
      hideChips: "إخفاء الاختصارات",
    },
    tr: {
      fabLabel: "AI asistanını aç",
      title: "Operasyon Asistanı",
      subtitle: "Sor · planla · yalnızca onayından sonra çalıştır",
      placeholder: "örn. Bugün sahada kim var? Görev planını hazırla…",
      send: "Gönder",
      thinking: "Düşünüyorum…",
      idle: "Gündelik dilde sorun. Okuma anında — yazma yalnızca onayla.",
      close: "Kapat",
      expand: "Tam AI Merkezi",
      confirmTitle: "Onay gerekli",
      confirmHint: "Bu işlem veri değiştirir veya kişileri bilgilendirir. Lütfen kontrol edin.",
      approve: "Onayla",
      reject: "Reddet",
      approved: "Tamamlandı.",
      rejected: "Reddedildi.",
      open: "Aç",
      needAuth: "Önce oturum açın.",
      needCompany: "Lütfen bir şirket seçin.",
      errGeneric: "İstek başarısız.",
      tools: "Araçlar",
      chipOnSite: "Sahada kim var?",
      chipBriefing: "Günlük özet",
      chipLate: "Kim geç kalıyor?",
      chipDocs: "Süresi dolan belgeler?",
      chipPlan: "Görev planını hazırla",
      chipInbox: "Açık görevler?",
      chipForecast: "Yarın tahmini",
      chipSecurity: "Güvenliği kontrol et",
      chipBroadcast: "Herkese yaz",
      chipSameReminder: "Same reminder as yesterday",
      welcomeSpeak: "Buyurun. Bugün size nasıl yardımcı olabilirim?",
      confirmAskVoice: "Bunu hazırladım ve ekranda gösteriyorum. Gerçekten uygulayayım mı?",
      ambientListening: "Dinliyorum — ihtiyacınızı söylemeniz yeterli.",
      ambientReady: "Hazırım. İstediğiniz zaman konuşun.",
      heardPrefix: "Anladım:",
      sensitiveAsk: "Hassas ayrıntılar gösterilsin mi?",
      sensitiveYes: "Evet, göster",
      sensitiveNo: "Hayır",
      voiceHint: "Mike dokun veya basılı tut → konuş. Hoparlör = yanıtı dinle. ∞ = eller serbest.",
      voiceListening: "Dinliyorum… bırakın veya durdurmak için dokunun.",
      voiceTranscribing: "Konuşma tanınıyor…",
      voiceUnavailable: "Ses girişi burada yok — metin çalışmaya devam eder.",
      voicePrep: "Ses modu hazır",
      handsFreeOn: "Eller serbest açık — yanıttan sonra yeniden dinle",
      handsFreeOff: "Eller serbest kapalı",
      handsFreeBlocked: "Eller serbest duraklatıldı — önce onaylayın veya reddedin.",
      followupPlaceholder: "Takip sorusu…",
      followupHint: "Yanıtın altında devam edin — mike dokunun veya basılı tutun.",
      botLabel: "SUPPIX AI",
      msgCopy: "Kopyala",
      msgCopied: "Kopyalandı.",
      msgLike: "Faydalı",
      msgDislike: "Faydasız",
      msgReadAloud: "Sesli oku",
      msgStopReading: "Okumayı durdur",
      msgRegenerate: "Yeniden üret",
      msgNoRegen: "Yeniden üretilecek önceki soru yok.",
      msgShare: "Paylaş",
      msgShareCopied: "Yanıt panoya kopyalandı.",
      msgMore: "Daha fazla",
      newChat: "Yeni sohbet",
      newChatDone: "Yeni sohbet başladı.",
      sources: "Kaynaklar",
      companyLabel: "Şirket",
      showChips: "Hızlı seçimleri göster",
      hideChips: "Hızlı seçimleri gizle",
    },
    fr: {
      fabLabel: "Ouvrir l'assistant IA",
      title: "Assistant opérations",
      subtitle: "Demander · planifier · exécuter seulement après confirmation",
      placeholder: "ex. Qui est sur site aujourd'hui ? Préparer le plan…",
      send: "Envoyer",
      thinking: "Réflexion…",
      idle: "Parlez naturellement. Lecture immédiate — écriture uniquement après confirmation.",
      close: "Fermer",
      expand: "Centre IA complet",
      confirmTitle: "Confirmation requise",
      confirmHint: "Cette action modifie des données ou notifie des personnes. Vérifiez.",
      approve: "Confirmer",
      reject: "Refuser",
      approved: "Fait.",
      rejected: "Refusé.",
      open: "Ouvrir",
      needAuth: "Veuillez d'abord vous connecter.",
      needCompany: "Veuillez choisir une entreprise.",
      errGeneric: "Échec de la requête.",
      tools: "Outils",
      chipOnSite: "Qui est sur site ?",
      chipBriefing: "Briefing du jour",
      chipLate: "Qui est en retard ?",
      chipDocs: "Documents expirés ?",
      chipPlan: "Préparer le plan",
      chipInbox: "Tâches ouvertes ?",
      chipForecast: "Prévision demain",
      chipSecurity: "Vérifier la sécurité",
      chipBroadcast: "Écrire à tous",
      chipSameReminder: "Same reminder as yesterday",
      welcomeSpeak: "Bienvenue. Comment puis-je vous aider aujourd'hui ?",
      confirmAskVoice: "J'ai préparé cela et l'affiche. Dois-je vraiment l'exécuter ?",
      ambientListening: "J'écoute — dites simplement ce dont vous avez besoin.",
      ambientReady: "Prêt. Parlez quand vous voulez.",
      heardPrefix: "J'ai compris :",
      sensitiveAsk: "Afficher les détails sensibles ?",
      sensitiveYes: "Oui, afficher",
      sensitiveNo: "Non",
      voiceHint: "Appuyer ou maintenir le micro → parler. Haut-parleur = entendre. ∞ = mains libres.",
      voiceListening: "J'écoute… relâchez ou appuyez pour arrêter.",
      voiceTranscribing: "Reconnaissance vocale…",
      voiceUnavailable: "Voix indisponible ici — le texte fonctionne toujours.",
      voicePrep: "Mode vocal prêt",
      handsFreeOn: "Mains libres activé — réécoute après la réponse",
      handsFreeOff: "Mains libres désactivé",
      handsFreeBlocked: "Mains libres en pause — confirmez ou refusez d'abord.",
      followupPlaceholder: "Question de suivi…",
      followupHint: "Suivre sous la réponse — micro.",
      botLabel: "SUPPIX IA",
      msgCopy: "Copier",
      msgCopied: "Copié.",
      msgLike: "Utile",
      msgDislike: "Pas utile",
      msgReadAloud: "Lire à voix haute",
      msgStopReading: "Arrêter la lecture",
      msgRegenerate: "Régénérer",
      msgNoRegen: "Pas de question précédente à régénérer.",
      msgShare: "Partager",
      msgShareCopied: "Réponse copiée.",
      msgMore: "Plus",
      newChat: "Nouveau chat",
      newChatDone: "Nouveau chat démarré.",
      sources: "Sources",
      companyLabel: "Entreprise",
      showChips: "Afficher les raccourcis",
      hideChips: "Masquer les raccourcis",
    },
    es: {
      fabLabel: "Abrir asistente de IA",
      title: "Asistente de operaciones",
      subtitle: "Preguntar · planificar · ejecutar solo tras confirmación",
      placeholder: "p. ej. ¿Quién está en obra hoy? Preparar plan…",
      send: "Enviar",
      thinking: "Pensando…",
      idle: "Pregunte en lenguaje natural. Lectura al instante — escritura solo tras confirmación.",
      close: "Cerrar",
      expand: "Centro de IA completo",
      confirmTitle: "Confirmación necesaria",
      confirmHint: "Esta acción cambia datos o notifica a personas. Revise.",
      approve: "Confirmar",
      reject: "Rechazar",
      approved: "Hecho.",
      rejected: "Rechazado.",
      open: "Abrir",
      needAuth: "Inicie sesión primero.",
      needCompany: "Seleccione una empresa.",
      errGeneric: "Error en la solicitud.",
      tools: "Herramientas",
      chipOnSite: "¿Quién está en obra?",
      chipBriefing: "Resumen del día",
      chipLate: "¿Quién llega tarde?",
      chipDocs: "¿Documentos caducados?",
      chipPlan: "Preparar plan",
      chipInbox: "¿Tareas abiertas?",
      chipForecast: "Previsión de mañana",
      chipSecurity: "Revisar seguridad",
      chipBroadcast: "Escribir a todos",
      chipSameReminder: "Same reminder as yesterday",
      welcomeSpeak: "Bienvenido. ¿Cómo puedo ayudarle hoy?",
      confirmAskVoice: "Lo preparé y lo muestro en pantalla. ¿Lo ejecuto de verdad?",
      ambientListening: "Escucho — diga simplemente lo que necesita.",
      ambientReady: "Listo. Hable cuando quiera.",
      heardPrefix: "Entendí:",
      sensitiveAsk: "¿Mostrar detalles sensibles?",
      sensitiveYes: "Sí, mostrar",
      sensitiveNo: "No",
      voiceHint: "Toque o mantenga el mic → hable. Altavoz = oír. ∞ = manos libres.",
      voiceListening: "Escuchando… suelte o toque para parar.",
      voiceTranscribing: "Reconociendo voz…",
      voiceUnavailable: "Voz no disponible aquí — el texto sigue funcionando.",
      voicePrep: "Modo de voz listo",
      handsFreeOn: "Manos libres activado — escucha tras la respuesta",
      handsFreeOff: "Manos libres desactivado",
      handsFreeBlocked: "Manos libres en pausa — confirme o rechace primero.",
      followupPlaceholder: "Pregunta de seguimiento…",
      followupHint: "Continúe bajo la respuesta — mic.",
      botLabel: "SUPPIX IA",
      msgCopy: "Copiar",
      msgCopied: "Copiado.",
      msgLike: "Útil",
      msgDislike: "No útil",
      msgReadAloud: "Leer en voz alta",
      msgStopReading: "Detener lectura",
      msgRegenerate: "Regenerar",
      msgNoRegen: "No hay pregunta anterior para regenerar.",
      msgShare: "Compartir",
      msgShareCopied: "Respuesta copiada.",
      msgMore: "Más",
      newChat: "Nuevo chat",
      newChatDone: "Nuevo chat iniciado.",
      sources: "Fuentes",
      companyLabel: "Empresa",
      showChips: "Mostrar atajos",
      hideChips: "Ocultar atajos",
    },
    it: {
      fabLabel: "Apri assistente IA",
      title: "Assistente operazioni",
      subtitle: "Chiedi · pianifica · esegui solo dopo conferma",
      placeholder: "es. Chi è in cantiere oggi? Prepara il piano…",
      send: "Invia",
      thinking: "Sto pensando…",
      idle: "Chiedi in linguaggio naturale. Lettura immediata — scrittura solo dopo conferma.",
      close: "Chiudi",
      expand: "Centro IA completo",
      confirmTitle: "Conferma richiesta",
      confirmHint: "Questa azione modifica dati o notifica persone. Controlla.",
      approve: "Conferma",
      reject: "Rifiuta",
      approved: "Eseguito.",
      rejected: "Rifiutato.",
      open: "Apri",
      needAuth: "Accedi prima.",
      needCompany: "Seleziona un'azienda.",
      errGeneric: "Richiesta non riuscita.",
      tools: "Strumenti",
      chipOnSite: "Chi è in cantiere?",
      chipBriefing: "Briefing odierno",
      chipLate: "Chi è in ritardo?",
      chipDocs: "Documenti scaduti?",
      chipPlan: "Prepara piano",
      chipInbox: "Attività aperte?",
      chipForecast: "Previsione di domani",
      chipSecurity: "Controlla sicurezza",
      chipBroadcast: "Scrivi a tutti",
      chipSameReminder: "Same reminder as yesterday",
      welcomeSpeak: "Benvenuto. Come posso aiutarti oggi?",
      confirmAskVoice: "Ho preparato questo e lo mostro. Devo eseguirlo davvero?",
      ambientListening: "Ascolto — dica pure cosa le serve.",
      ambientReady: "Pronto. Parli quando vuole.",
      heardPrefix: "Ho capito:",
      sensitiveAsk: "Mostrare dettagli sensibili?",
      sensitiveYes: "Sì, mostra",
      sensitiveNo: "No",
      voiceHint: "Tocca o tieni premuto il microfono → parla. Altoparlante = ascolta. ∞ = mani libere.",
      voiceListening: "Ascolto… rilascia o tocca per fermare.",
      voiceTranscribing: "Riconoscimento vocale…",
      voiceUnavailable: "Voce non disponibile qui — il testo funziona ancora.",
      voicePrep: "Modalità vocale pronta",
      handsFreeOn: "Mani libere attivo — ascolta dopo la risposta",
      handsFreeOff: "Mani libere disattivo",
      handsFreeBlocked: "Mani libere in pausa — conferma o rifiuta prima.",
      followupPlaceholder: "Domanda di follow-up…",
      followupHint: "Continua sotto la risposta — microfono.",
      botLabel: "SUPPIX IA",
      msgCopy: "Copia",
      msgCopied: "Copiato.",
      msgLike: "Utile",
      msgDislike: "Non utile",
      msgReadAloud: "Leggi ad alta voce",
      msgStopReading: "Interrompi lettura",
      msgRegenerate: "Rigenera",
      msgNoRegen: "Nessuna domanda precedente da rigenerare.",
      msgShare: "Condividi",
      msgShareCopied: "Risposta copiata.",
      msgMore: "Altro",
      newChat: "Nuova chat",
      newChatDone: "Nuova chat avviata.",
      sources: "Fonti",
      companyLabel: "Azienda",
      showChips: "Mostra scorciatoie",
      hideChips: "Nascondi scorciatoie",
    },
    pl: {
      fabLabel: "Otwórz asystenta AI",
      title: "Asystent operacyjny",
      subtitle: "Pytaj · planuj · wykonuj dopiero po potwierdzeniu",
      placeholder: "np. Kto jest dziś na budowie? Przygotuj plan…",
      send: "Wyślij",
      thinking: "Myślę…",
      idle: "Pytaj potocznie. Odczyt od razu — zapis tylko po potwierdzeniu.",
      close: "Zamknij",
      expand: "Pełne centrum AI",
      confirmTitle: "Wymagane potwierdzenie",
      confirmHint: "Ta akcja zmienia dane lub powiadamia osoby. Sprawdź.",
      approve: "Potwierdź",
      reject: "Odrzuć",
      approved: "Wykonano.",
      rejected: "Odrzucono.",
      open: "Otwórz",
      needAuth: "Najpierw zaloguj się.",
      needCompany: "Wybierz firmę.",
      errGeneric: "Żądanie nie powiodło się.",
      tools: "Narzędzia",
      chipOnSite: "Kto jest na budowie?",
      chipBriefing: "Podsumowanie dnia",
      chipLate: "Kto się spóźnia?",
      chipDocs: "Wygasłe dokumenty?",
      chipPlan: "Przygotuj plan",
      chipInbox: "Otwarte zadania?",
      chipForecast: "Prognoza na jutro",
      chipSecurity: "Sprawdź bezpieczeństwo",
      chipBroadcast: "Napisz do wszystkich",
      chipSameReminder: "Same reminder as yesterday",
      welcomeSpeak: "Witam. Jak mogę dziś pomóc?",
      confirmAskVoice: "Przygotowałem to i pokazuję na ekranie. Czy naprawdę wykonać?",
      ambientListening: "Słucham — po prostu powiedz, czego potrzebujesz.",
      ambientReady: "Gotowy. Mów, kiedy chcesz.",
      heardPrefix: "Rozumiem:",
      sensitiveAsk: "Pokazać wrażliwe szczegóły?",
      sensitiveYes: "Tak, pokaż",
      sensitiveNo: "Nie",
      voiceHint: "Dotknij lub przytrzymaj mikrofon → mów. Głośnik = słuchaj. ∞ = hands-free.",
      voiceListening: "Słucham… puść lub dotknij, aby zatrzymać.",
      voiceTranscribing: "Rozpoznawanie mowy…",
      voiceUnavailable: "Głos niedostępny tutaj — tekst nadal działa.",
      voicePrep: "Tryb głosowy gotowy",
      handsFreeOn: "Hands-free włączony — słucha po odpowiedzi",
      handsFreeOff: "Hands-free wyłączony",
      handsFreeBlocked: "Hands-free wstrzymany — najpierw potwierdź lub odrzuć.",
      followupPlaceholder: "Pytanie dodatkowe…",
      followupHint: "Kontynuuj pod odpowiedzią — mikrofon.",
      botLabel: "SUPPIX AI",
      msgCopy: "Kopiuj",
      msgCopied: "Skopiowano.",
      msgLike: "Pomocne",
      msgDislike: "Niepomocne",
      msgReadAloud: "Czytaj na głos",
      msgStopReading: "Zatrzymaj czytanie",
      msgRegenerate: "Wygeneruj ponownie",
      msgNoRegen: "Brak poprzedniego pytania do regeneracji.",
      msgShare: "Udostępnij",
      msgShareCopied: "Odpowiedź skopiowana.",
      msgMore: "Więcej",
      newChat: "Nowy czat",
      newChatDone: "Nowy czat rozpoczęty.",
      sources: "Źródła",
      companyLabel: "Firma",
      showChips: "Pokaż skróty",
      hideChips: "Ukryj skróty",
    },
  };

  let chipsForcedOpen = false;

  let mounted = false;
  let open = false;
  let busy = false;
  let sessionId = "";
  let visibleForced = null;
  let els = {};
  let voiceBound = false;
  let voiceLibsPromise = null;
  let voiceReady = false;
  let handsFreeArmed = false;
  let handsFreeTimer = null;
  let ambientMode = false;
  let welcomeInFlight = false;
  /** Prevent re-greeting on every SPA section / 2s visibility poll. */
  let welcomeDoneThisLogin = false;
  let lastWelcomeTokenTip = "";
  let confirmVoiceAsked = false;
  let serverPromptChips = [];
  let opsUrgencyScore = 0;
  let sectorTerms = { termSite: "", termWorkers: "", sectorLabel: "" };
  let lastReminderPrompt = "";
  let _lastPulseProbe = 0;
  let suppressFabClickUntil = 0;

  function t(key) {
    const lang = detectLang();
    const pack = STR[lang] || STR.de;
    return pack[key] || STR.de[key] || key;
  }

  const SYSTEM_LANGS = ["de", "en", "ar", "tr", "fr", "es", "it", "pl"];

  function detectLang() {
    if (sessionLangOverride && SYSTEM_LANGS.includes(sessionLangOverride)) {
      return sessionLangOverride;
    }
    const WP = global.WorkPassStorage;
    const raw = String(
      WP?.getItem?.(WP?.KEYS?.ADMIN_LANG || "baupass-admin-v2-lang")
      || localStorage.getItem("baupass-admin-v2-lang")
      || localStorage.getItem("baupass-ui-lang")
      || localStorage.getItem("workpass-ui-lang")
      || localStorage.getItem("baupass-worker-lang")
      || document.documentElement.lang
      || "de"
    ).toLowerCase();
    const code = raw.slice(0, 2);
    return SYSTEM_LANGS.includes(code) ? code : "de";
  }

  function guessLangFromText(text) {
    const s = String(text || "").trim();
    if (!s) return "";
    // Arabic script (MSA + dialect orthography) always wins.
    if (/[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]/.test(s)) return "ar";
    if (/[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]/.test(s)) return "pl";
    if (/[ğüşıöçĞÜŞİÖÇ]/.test(s)) return "tr";
    if (/[àâçéèêëîïôùûüÿœæÀÂÇÉÈÊËÎÏÔÙÛÜŸŒÆ]/.test(s)
      && /\b(le|la|les|je|vous|bonjour|aujourd|qui|est)\b/i.test(s)) return "fr";
    if (/[áéíóúñü¿¡ÁÉÍÓÚÑÜ]/.test(s)
      && /\b(el|la|los|las|hola|gracias|quiero|quién)\b/i.test(s)) return "es";
    if (/[àèéìòùÀÈÉÌÒÙ]/.test(s)
      && /\b(il|lo|la|per|ciao|grazie|voglio|chi)\b/i.test(s)) return "it";
    if (/\b(ich|nicht|bitte|heute|mitarbeiter|urlaub|baustelle|wer|wie|was|und|oder|für)\b/i.test(s)) {
      return "de";
    }
    if (/\b(the|please|today|workers?|leave|site|who|what|how|are|is|show|open|late|documents?)\b/i.test(s)) {
      return "en";
    }
    return "";
  }

  function applyDetectedLang(code) {
    const lang = String(code || "").slice(0, 2).toLowerCase();
    if (!SYSTEM_LANGS.includes(lang)) return false;
    sessionLangOverride = lang;
    try {
      localStorage.setItem("baupass-admin-v2-lang", lang);
      localStorage.setItem("baupass-ui-lang", lang);
      const WP = global.WorkPassStorage;
      WP?.setItem?.(WP?.KEYS?.ADMIN_LANG || "baupass-admin-v2-lang", lang);
    } catch {
      /* ignore */
    }
    try {
      document.documentElement.lang = lang;
      document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    } catch {
      /* ignore */
    }
    global.dispatchEvent(new CustomEvent("baupass-lang-sync", { detail: { lang } }));
    refreshCopy();
    return true;
  }

  function matchVoiceConfirmDecision(text) {
    const s = String(text || "").trim().toLowerCase();
    if (!s) return null;
    // Short confirmations only — avoid treating full questions as yes/no.
    if (s.length > 48) return null;
    const yes = /^(yes|yeah|yep|yup|ok|okay|sure|confirm|execute|do it|go ahead|approve|ja|jawohl|genau|mach(?:en)?|ausführen|bestätig(?:en)?|oui|si|sí|evet|tamam|نعم|ايوه|أيوه|موافق|نفّذ|نفذ|tak|dobrze)\b/i;
    const no = /^(no|nope|nah|cancel|stop|reject|abort|nein|nicht|abbrechen|ablehnen|stopp|non|hayır|hayir|لا|لأ|الغِ|الغاء|الغاء|nie)\b/i;
    if (yes.test(s)) return "yes";
    if (no.test(s)) return "no";
    return null;
  }

  function clickPendingConfirm(decision) {
    const card = els.log?.querySelector(".aio-card");
    if (!card) return false;
    const sel = decision === "yes" ? '[data-act="ok"]' : '[data-act="no"]';
    const btn = card.querySelector(sel);
    if (!btn || btn.disabled) return false;
    confirmVoiceMode = false;
    btn.click();
    return true;
  }

  function isRtl() {
    return detectLang() === "ar"
      || document.documentElement.dir === "rtl"
      || document.body?.dir === "rtl";
  }

  function shouldSkipPage() {
    const path = String(location.pathname || "");
    if (SKIP_PATHS.some((re) => re.test(path))) return true;
    // Platform shell (index.html) already shows one FAB — skip inside embeds/iframes.
    if (isEmbeddedFrame()) return true;
    return false;
  }

  function destroyDuplicateRoots(keep) {
    document.querySelectorAll("#aioOperatorRoot, .aio-root").forEach((node) => {
      if (keep && node === keep) return;
      try {
        node.remove();
      } catch {
        /* ignore */
      }
    });
  }

  function readToken() {
    if (global.BaupassAuth?.getToken) {
      const tok = String(global.BaupassAuth.getToken() || "").trim();
      if (tok) return tok;
    }
    const WP = global.WorkPassStorage;
    return String(
      WP?.readSessionToken?.()
      || WP?.getItem?.(WP?.KEYS?.SESSION_TOKEN || "workpass-session-token")
      || WP?.getItem?.(WP?.KEYS?.ADMIN_TOKEN || "workpass-admin-token")
      || localStorage.getItem("workpass-session-token")
      || localStorage.getItem("workpass-admin-token")
      || ""
    ).trim();
  }

  function readCompanyId() {
    const qs = new URLSearchParams(location.search);
    const fromQs = (qs.get("company_id") || "").trim();
    if (fromQs) return fromQs;
    if (global.BaupassAuth?.readStoredCompanyId) {
      const c = String(global.BaupassAuth.readStoredCompanyId() || "").trim();
      if (c) return c;
    }
    const WP = global.WorkPassStorage;
    const stored = String(
      WP?.getItem?.(WP?.KEYS?.ADMIN_COMPANY || "workpass-admin-company")
      || WP?.getItem?.(WP?.KEYS?.PREVIEW_COMPANY_ID || "workpass-preview-company-id")
      || localStorage.getItem("workpass-admin-company")
      || localStorage.getItem("workpass-preview-company-id")
      || ""
    ).trim();
    if (stored) return stored;
    try {
      const raw = WP?.getItem?.(WP?.KEYS?.ADMIN_USER || "workpass-admin-user")
        || localStorage.getItem("workpass-admin-user")
        || "";
      if (!raw) return "";
      const u = JSON.parse(raw);
      return String(u?.company_id || u?.preview_company_id || "").trim();
    } catch {
      return "";
    }
  }

  function readUserRole() {
    try {
      const WP = global.WorkPassStorage;
      const keys = [
        WP?.KEYS?.ADMIN_USER || "workpass-admin-user",
        "workpass-admin-user",
        "baupass-admin-user",
        "workpass-user",
      ];
      for (const key of keys) {
        const raw = WP?.getItem?.(key) || localStorage.getItem(key) || sessionStorage.getItem(key) || "";
        if (!raw) continue;
        try {
          const u = JSON.parse(raw);
          const role = String(u?.role || u?.userRole || "").trim();
          if (role) return role;
        } catch {
          /* continue */
        }
      }
      return "";
    } catch {
      return "";
    }
  }

  function isLoginShellVisible() {
    const login = document.getElementById("loginView");
    if (login && !login.classList.contains("hidden")) return true;
    const boot = document.getElementById("sessionBootView");
    if (boot && !boot.classList.contains("hidden")) return true;
    const embedAuth = document.getElementById("embedAuthView");
    if (embedAuth && !embedAuth.classList.contains("hidden")) return true;
    // Legacy / root dashboard login panels
    if (document.body?.classList?.contains("logged-out")) return true;
    if (document.documentElement?.dataset?.auth === "required") return true;
    return false;
  }

  function authHeaders(extra) {
    if (global.BaupassAuth?.authHeaders) {
      return global.BaupassAuth.authHeaders(extra || {});
    }
    const headers = Object.assign({ Accept: "application/json" }, extra || {});
    const token = readToken();
    if (token && !headers.Authorization) headers.Authorization = `Bearer ${token}`;
    return headers;
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function isAdminSurfaceReady() {
    if (!readToken()) return false;
    if (isLoginShellVisible()) return false;
    const role = readUserRole();
    // Token without role yet: allow (session probe fills role shortly).
    if (role && !ADMIN_ROLES.has(role)) return false;
    const dash = document.getElementById("dashboardView");
    // admin-v2: wait until dashboard is visible
    if (dash && dash.classList.contains("hidden")) return false;
    return true;
  }

  function setFabVisible(show) {
    if (!els.fab) return;
    const on = visibleForced == null ? show : Boolean(visibleForced);
    els.fab.hidden = !on;
    if (!on) {
      setOpen(false);
      stopAllOperatorVoice({ clearAmbient: companyOperatorEnabled === false });
      if (els.root) els.root.hidden = true;
      return;
    }
    if (els.root) {
      els.root.hidden = false;
      els.root.style.visibility = "visible";
    }
    // Warm Whisper/TTS assets once the admin surface is ready (voice prep).
    if (voiceEnabled() && !voiceReady && !voiceLibsPromise) {
      ensureVoiceStack().catch(() => {});
    }
  }

  function readStoredFabPos() {
    try {
      const raw = String(global.localStorage?.getItem(FAB_POS_KEY) || "").trim();
      if (!raw) return null;
      const data = JSON.parse(raw);
      const x = Number(data?.x);
      const y = Number(data?.y);
      if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
      return { x, y };
    } catch {
      return null;
    }
  }

  function storeFabPos(x, y) {
    try {
      global.localStorage?.setItem(FAB_POS_KEY, JSON.stringify({ x: Number(x), y: Number(y) }));
    } catch {
      /* ignore */
    }
  }

  function clearFabPos() {
    try {
      global.localStorage?.removeItem(FAB_POS_KEY);
    } catch {
      /* ignore */
    }
  }

  function clampFabPos(x, y) {
    const root = els.root;
    if (!root) return { x: 0, y: 0 };
    const margin = 8;
    const vw = Math.max(320, Number(global.innerWidth) || 0);
    const vh = Math.max(320, Number(global.innerHeight) || 0);
    const w = Math.max(42, root.offsetWidth || 56);
    const h = Math.max(42, root.offsetHeight || 56);
    const minX = margin;
    const minY = margin;
    const maxX = Math.max(minX, vw - w - margin);
    const maxY = Math.max(minY, vh - h - margin);
    return {
      x: Math.min(maxX, Math.max(minX, Number(x) || 0)),
      y: Math.min(maxY, Math.max(minY, Number(y) || 0)),
    };
  }

  function applyFabPos(x, y, { persist = false } = {}) {
    if (!els.root) return;
    const p = clampFabPos(x, y);
    els.root.style.inset = "auto";
    els.root.style.left = `${p.x}px`;
    els.root.style.top = `${p.y}px`;
    els.root.style.right = "auto";
    els.root.style.bottom = "auto";
    els.root.dataset.aioFabPinned = "1";
    if (persist) storeFabPos(p.x, p.y);
  }

  function restoreFabPos() {
    if (!els.root) return;
    const p = readStoredFabPos();
    if (!p) return;
    applyFabPos(p.x, p.y, { persist: false });
  }

  function clampCurrentFabPos({ persist = true } = {}) {
    if (!els.root || els.root.dataset.aioFabPinned !== "1") return;
    const x = Number.parseFloat(els.root.style.left || "");
    const y = Number.parseFloat(els.root.style.top || "");
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      clearFabPos();
      delete els.root.dataset.aioFabPinned;
      els.root.style.left = "";
      els.root.style.top = "";
      els.root.style.right = "";
      els.root.style.bottom = "";
      els.root.style.inset = "";
      return;
    }
    applyFabPos(x, y, { persist });
  }

  function bindFabDragOnce(root) {
    if (!root || root.dataset.aioFabDragBound === "1") return;
    root.dataset.aioFabDragBound = "1";
    const fab = root.querySelector('[data-aio="fab"]');
    if (!fab) return;

    let pointerId = null;
    let startClientX = 0;
    let startClientY = 0;
    let startLeft = 0;
    let startTop = 0;
    let dragging = false;

    const finish = () => {
      if (pointerId == null) return;
      try {
        fab.releasePointerCapture(pointerId);
      } catch {
        /* ignore */
      }
      pointerId = null;
      root.classList.remove("is-dragging");
      if (dragging) {
        dragging = false;
        clampCurrentFabPos({ persist: true });
        suppressFabClickUntil = Date.now() + 350;
      }
      global.removeEventListener("pointermove", onMove);
      global.removeEventListener("pointerup", onUp);
      global.removeEventListener("pointercancel", onUp);
    };

    const onMove = (ev) => {
      if (pointerId == null || ev.pointerId !== pointerId) return;
      const dx = ev.clientX - startClientX;
      const dy = ev.clientY - startClientY;
      if (!dragging && Math.hypot(dx, dy) >= 6) {
        dragging = true;
        root.classList.add("is-dragging");
      }
      if (!dragging) return;
      ev.preventDefault();
      applyFabPos(startLeft + dx, startTop + dy, { persist: false });
    };

    const onUp = (ev) => {
      if (pointerId == null || ev.pointerId !== pointerId) return;
      finish();
    };

    fab.addEventListener("pointerdown", (ev) => {
      if (ev.button != null && ev.button !== 0) return;
      if (pointerId != null) return;

      const rect = root.getBoundingClientRect();
      applyFabPos(rect.left, rect.top, { persist: false });
      startLeft = Number.parseFloat(root.style.left || "0") || 0;
      startTop = Number.parseFloat(root.style.top || "0") || 0;
      startClientX = ev.clientX;
      startClientY = ev.clientY;
      dragging = false;
      pointerId = ev.pointerId;

      try {
        fab.setPointerCapture(pointerId);
      } catch {
        /* ignore */
      }
      global.addEventListener("pointermove", onMove, { passive: false });
      global.addEventListener("pointerup", onUp);
      global.addEventListener("pointercancel", onUp);
    });
  }

  function refreshVisibility() {
    const token = readToken() || "";
    const tip = token ? token.slice(-16) : "";
    if (tip !== lastWelcomeTokenTip) {
      lastWelcomeTokenTip = tip;
      welcomeDoneThisLogin = false;
    }
    if (!token) {
      welcomeDoneThisLogin = false;
    }
    const ready = isAdminSurfaceReady();
    const companyOn = companyOperatorEnabled !== false;
    setFabVisible(ready && companyOn);
    // Greeting only once after login — not on every Operations section / poll tick.
    if (ready && companyOn && !welcomeDoneThisLogin) {
      maybeSpeakWelcome().catch(() => {});
    }
    if (ready && companyOn) {
      void probeOpsPulse();
    } else if (els.fab) {
      els.fab.classList.remove("is-urgent");
    }
    // Keep company preference fresh (hide everywhere when company disables it).
    if (ready && token && readCompanyId()) {
      loadCompanyOperatorSettings().then((enabled) => {
        if (!enabled) setFabVisible(false);
        else if (isAdminSurfaceReady()) setFabVisible(true);
      }).catch(() => {});
    }
  }

  function setOpen(next) {
    open = Boolean(next);
    if (!els.drawer || !els.backdrop) return;
    els.drawer.hidden = !open;
    els.backdrop.hidden = !open;
    if (els.fab) els.fab.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) {
      refreshCopy();
      els.input?.focus?.();
      loadPendingProposals().catch(() => {});
      ensureVoiceStack()
        .then(() => bindOperatorVoice())
        .catch(() => markVoiceUnavailable());
    } else if (!ambientMode) {
      // Closing drawer must not kill ambient listen-after-welcome mode.
      handsFreeArmed = false;
      if (handsFreeTimer) {
        global.clearTimeout(handsFreeTimer);
        handsFreeTimer = null;
      }
      try {
        global.BaupassAiUi?.stopSpeaking?.();
        global.BaupassAiUi?.stopVoiceCapture?.("aioOperatorInput");
      } catch {
        /* ignore */
      }
      syncFabListeningState(false);
    }
  }

  function sessionStoreKey() {
    const cid = readCompanyId() || "none";
    return `${SESSION_STORE_KEY}:${cid}`;
  }

  function loadStoredSessionId() {
    try {
      return String(global.sessionStorage?.getItem(sessionStoreKey()) || "").trim();
    } catch {
      return "";
    }
  }

  function persistSessionId(id) {
    try {
      if (id) global.sessionStorage?.setItem(sessionStoreKey(), id);
      else global.sessionStorage?.removeItem(sessionStoreKey());
    } catch {
      /* ignore */
    }
  }

  function refreshCopy() {
    if (!els.root) return;
    els.root.dataset.rtl = isRtl() ? "1" : "0";
    if (els.title) els.title.textContent = t("title");
    if (els.subtitle) {
      const cid = readCompanyId();
      els.subtitle.textContent = cid
        ? `${t("subtitle")} · ${t("companyLabel")} ${cid.slice(0, 12)}${cid.length > 12 ? "…" : ""}`
        : t("subtitle");
    }
    if (els.input) els.input.placeholder = t("placeholder");
    if (els.sendBtn) {
      els.sendBtn.setAttribute("aria-label", t("send"));
      els.sendBtn.title = t("send");
      // Keep plane icon from BaupassAiUi.enhanceSendButton — never wipe with textContent.
      if (!els.sendBtn.querySelector(".bp-ai-send-icon") && !els.sendBtn.classList.contains("bp-ai-send")) {
        els.sendBtn.textContent = t("send");
      }
    }
    if (els.expandLink) els.expandLink.textContent = t("expand");
    if (els.newChatBtn) {
      els.newChatBtn.title = t("newChat");
      els.newChatBtn.setAttribute("aria-label", t("newChat"));
    }
    if (els.fab) els.fab.setAttribute("aria-label", t("fabLabel"));
    if (els.voiceHint && !pendingVerifyText) els.voiceHint.textContent = t("voiceHint");
    if (els.voiceHint && pendingVerifyText) els.voiceHint.textContent = t("voiceVerifyHint");
    if (els.verifyLabel) els.verifyLabel.textContent = t("voiceVerifyTitle");
    if (els.verifySendBtn) els.verifySendBtn.textContent = t("voiceVerifySend");
    if (els.verifyRetryBtn) els.verifyRetryBtn.textContent = t("voiceVerifyRetry");
    if (els.empty && !els.log?.querySelector(".aio-msg, .aio-turn")) {
      els.empty.textContent = t("idle");
    }
    syncHandsFreeBtn();
    renderChips();
    if (voiceBound && global.BaupassAiUi?.refreshComposerLabels) {
      global.BaupassAiUi.refreshComposerLabels(operatorVoiceOptions());
    }
  }

  function resetChatLog() {
    if (!els.log) return;
    els.log.innerHTML = "";
    const empty = document.createElement("div");
    empty.className = "aio-empty";
    empty.setAttribute("data-aio", "empty");
    empty.textContent = t("idle");
    els.log.appendChild(empty);
    els.empty = empty;
  }

  async function startNewChat() {
    if (busy) return;
    try {
      global.BaupassAiUi?.stopSpeaking?.();
      global.BaupassAiUi?.stopVoiceCapture?.("aioOperatorInput");
    } catch {
      /* ignore */
    }
    handsFreeArmed = false;
    lastUserQuestion = "";
    chipsForcedOpen = false;
    sessionId = "";
    persistSessionId("");
    resetChatLog();
    renderChips();
    syncConversationChrome();
    try {
      await ensureSession();
      showToast(t("newChatDone"));
    } catch (e) {
      showToast(e.message || t("errGeneric"));
    }
    els.input?.focus?.();
  }

  function isHandsFreeEnabled() {
    try {
      return global.localStorage?.getItem(HANDS_FREE_KEY) === "1";
    } catch {
      return false;
    }
  }

  function setHandsFreeEnabled(on) {
    try {
      global.localStorage?.setItem(HANDS_FREE_KEY, on ? "1" : "0");
    } catch {
      /* ignore */
    }
    syncHandsFreeBtn();
    if (!on) {
      handsFreeArmed = false;
      if (handsFreeTimer) {
        global.clearTimeout(handsFreeTimer);
        handsFreeTimer = null;
      }
    }
  }

  function syncHandsFreeBtn() {
    if (!els.handsFreeBtn) return;
    const on = isHandsFreeEnabled();
    els.handsFreeBtn.classList.toggle("is-on", on);
    els.handsFreeBtn.setAttribute("aria-pressed", on ? "true" : "false");
    els.handsFreeBtn.title = on ? t("handsFreeOn") : t("handsFreeOff");
    els.handsFreeBtn.setAttribute("aria-label", on ? t("handsFreeOn") : t("handsFreeOff"));
  }

  function hasPendingConfirmCard() {
    return Boolean(els.log?.querySelector(".aio-card"));
  }

  function isAmbientEnabled() {
    if (ambientMode) return true;
    try {
      return global.sessionStorage?.getItem(AMBIENT_KEY) === "1";
    } catch {
      return false;
    }
  }

  function setAmbientMode(on) {
    ambientMode = Boolean(on);
    try {
      if (on) global.sessionStorage?.setItem(AMBIENT_KEY, "1");
      else global.sessionStorage?.removeItem(AMBIENT_KEY);
    } catch {
      /* ignore */
    }
    if (on) setHandsFreeEnabled(true);
    syncFabListeningState(false);
  }

  function syncFabListeningState(listening) {
    if (!els.fab) return;
    els.fab.classList.toggle("is-listening", Boolean(listening));
    els.fab.classList.toggle("is-ambient", isAmbientEnabled());
    if (listening) {
      els.fab.title = t("ambientListening");
      els.fab.setAttribute("aria-label", t("ambientListening"));
    } else if (!open) {
      els.fab.setAttribute("aria-label", t("fabLabel"));
      els.fab.title = isAmbientEnabled() ? t("ambientReady") : t("fabLabel");
    }
  }

  function isVoiceTurnBlocked() {
    return Boolean(busy || voiceTurnLock || global.BaupassAiUi?.isSpeaking?.());
  }

  function releaseVoiceTurnLock() {
    voiceTurnLock = false;
  }

  function scheduleHandsFreeListen(opts) {
    const forConfirm = Boolean(opts?.forConfirm) || confirmVoiceMode;
    const delayMs = Math.max(0, Number(opts?.delayMs) || (forConfirm ? 600 : 1200));
    const allow = isAmbientEnabled() || (open && isHandsFreeEnabled()) || forConfirm;
    if (!allow || !voiceReady) return;
    if (isVoiceTurnBlocked() && !forConfirm) return;
    if (hasPendingConfirmCard() && !forConfirm) {
      if (els.voiceHint) els.voiceHint.textContent = t("handsFreeBlocked");
      syncFabListeningState(false);
      return;
    }
    handsFreeArmed = true;
    if (handsFreeTimer) global.clearTimeout(handsFreeTimer);
    handsFreeTimer = global.setTimeout(() => {
      handsFreeTimer = null;
      if (!handsFreeArmed) return;
      if (isVoiceTurnBlocked() && !forConfirm) return;
      if (!forConfirm && !isAmbientEnabled() && !(open && isHandsFreeEnabled())) return;
      if (hasPendingConfirmCard() && !confirmVoiceMode && !forConfirm) return;
      if (global.BaupassAiUi?.isSpeaking?.()) {
        // Retry after TTS finishes (speaking hook will also schedule).
        scheduleHandsFreeListen({ ...opts, delayMs: 900 });
        return;
      }
      // Ensure mic bindings exist even if drawer stayed closed.
      bindOperatorVoice();
      const latestMic = els.micBtn || els.log?.querySelector(".aio-turn:last-child [id$='Mic']");
      const latestInputId = latestMic?.id?.replace(/Mic$/, "Input") || "aioOperatorInput";
      if (global.BaupassAiUi?.isVoiceCaptureActive?.(latestInputId)) return;
      syncFabListeningState(true);
      if (els.voiceHint) {
        els.voiceHint.textContent = forConfirm || confirmVoiceMode
          ? t("confirmAskVoice")
          : t("ambientListening");
      }
      const start = latestMic?.bpStartVoiceCapture;
      if (typeof start === "function") {
        start().catch?.(() => syncFabListeningState(false));
      } else {
        latestMic?.click?.();
      }
    }, delayMs);
  }

  function isUsableVoiceUtterance(text) {
    const q = String(text || "").trim();
    if (!q || q.length < 2) return false;
    const arLetters = (q.match(/[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]/g) || []).length;
    // Arabic / dialect: need a short phrase, not one scrap letter cluster.
    if (arLetters >= 3) {
      const arWords = q.split(/\s+/).filter(Boolean);
      return arWords.length >= 2 || arLetters >= 8;
    }
    const words = q.split(/\s+/).filter(Boolean);
    // Never accept a single Latin token — that is the early-cut bug.
    if (words.length < 2) return false;
    return /[A-Za-zÀ-ÿ0-9\u00C0-\u024F\u0400-\u04FF]/.test(q);
  }

  function clearVoiceVerify() {
    pendingVerifyText = "";
    pendingVerifyLang = "";
    pendingVerifySpoken = false;
    if (els.verifyBar) els.verifyBar.hidden = true;
    if (els.form) els.form.classList.remove("aio-verify-pending");
    if (els.sendBtn) els.sendBtn.classList.remove("aio-send-pulse");
  }

  function showVoiceVerify(text, lang, meta) {
    const q = String(text || "").trim();
    if (!q) return;
    pendingVerifyText = q;
    pendingVerifyLang = lang || detectLang();
    pendingVerifySpoken = true;
    if (!open) setOpen(true);
    if (els.input) {
      els.input.value = q;
      try {
        els.input.dataset.bpVoiceInput = "1";
        if (pendingVerifyLang) els.input.dataset.bpDetectedLang = pendingVerifyLang;
        els.input.focus?.();
        // Do not select-all — easy accidental Enter/send; operator should read then Send.
        const len = q.length;
        els.input.setSelectionRange?.(len, len);
      } catch {
        /* ignore */
      }
    }
    if (els.verifyText) els.verifyText.textContent = q;
    if (els.verifyBar) els.verifyBar.hidden = false;
    if (els.form) els.form.classList.add("aio-verify-pending");
    if (els.sendBtn) els.sendBtn.classList.add("aio-send-pulse");
    if (els.voiceHint) els.voiceHint.textContent = t("voiceVerifyHint");
    syncFabListeningState(false);
    // Default: silent review (spoken prompt overlaps mic and cuts the next utterance).
    if (meta?.announce === true) {
      Promise.resolve(
        global.BaupassAiUi?.speakReply?.(t("voiceVerifyAsk"), pendingVerifyLang, {
          force: true,
          authHeaders: () => authHeaders(),
        })
      ).catch(() => {});
    }
  }

  function confirmVoiceVerifyAndSend() {
    const q = String(pendingVerifyText || els.input?.value || "").trim();
    if (!q || busy) return;
    const lang = pendingVerifyLang || detectLang();
    clearVoiceVerify();
    voiceTurnLock = true;
    handsFreeArmed = false;
    lastVoiceSubmitAt = Date.now();
    lastVoiceSubmitText = q;
    if (els.input) {
      els.input.value = q;
      try { els.input.dataset.bpVoiceInput = "1"; } catch { /* ignore */ }
    }
    void submitQuestion(q, els.input, { lang, spoken: true }).catch(() => {
      releaseVoiceTurnLock();
    });
  }

  function retryVoiceCapture() {
    clearVoiceVerify();
    if (els.input) els.input.value = "";
    if (els.voiceHint) els.voiceHint.textContent = t("ambientListening");
    scheduleHandsFreeListen({ delayMs: 400 });
  }

  function readCachedCompanyEnabled() {
    try {
      const cid = readCompanyId() || "none";
      const raw = global.localStorage?.getItem(`${COMPANY_ENABLED_KEY}:${cid}`);
      if (raw === "0") return false;
      if (raw === "1") return true;
    } catch {
      /* ignore */
    }
    return true;
  }

  function cacheCompanyEnabled(enabled) {
    companyOperatorEnabled = Boolean(enabled);
    companySettingsLoaded = true;
    try {
      const cid = readCompanyId() || "none";
      global.localStorage?.setItem(`${COMPANY_ENABLED_KEY}:${cid}`, enabled ? "1" : "0");
    } catch {
      /* ignore */
    }
  }

  function applyCompanyOperatorPrefs(data) {
    const settings = data?.settings || data || {};
    const planOk = data?.planAllowed !== false;
    const companyOn = data?.companyEnabled != null
      ? Boolean(data.companyEnabled)
      : settings.enabled !== false;
    const enabled = data?.enabled != null
      ? Boolean(data.enabled)
      : (companyOn && planOk);
    companyVoiceEnabled = settings.voiceEnabled !== false;
    companyWelcomeEnabled = settings.welcomeEnabled !== false;
    cacheCompanyEnabled(Boolean(enabled));
    return companyOperatorEnabled;
  }

  async function loadCompanyOperatorSettings() {
    const now = Date.now();
    if (now - _lastSettingsProbe < 8000 && companySettingsLoaded) return companyOperatorEnabled;
    _lastSettingsProbe = now;
    const companyId = readCompanyId();
    if (!companyId || !readToken()) {
      companyOperatorEnabled = readCachedCompanyEnabled();
      return companyOperatorEnabled;
    }
    try {
      const res = await fetch(
        `/api/ai/operator/settings?company_id=${encodeURIComponent(companyId)}`,
        { credentials: "include", headers: authHeaders() }
      );
      if (!res.ok) {
        // Older servers may not have this route yet — stay enabled, slow down probes.
        _lastSettingsProbe = now + 60000;
        companyOperatorEnabled = readCachedCompanyEnabled();
        return companyOperatorEnabled;
      }
      const data = await res.json();
      return applyCompanyOperatorPrefs(data);
    } catch {
      companyOperatorEnabled = readCachedCompanyEnabled();
      return companyOperatorEnabled;
    }
  }

  function stopAllOperatorVoice(opts) {
    handsFreeArmed = false;
    confirmVoiceMode = false;
    voiceTurnLock = false;
    if (handsFreeTimer) {
      global.clearTimeout(handsFreeTimer);
      handsFreeTimer = null;
    }
    try {
      global.BaupassAiUi?.stopSpeaking?.();
      global.BaupassAiUi?.stopVoiceCapture?.("aioOperatorInput");
    } catch {
      /* ignore */
    }
    if (opts?.clearAmbient) setAmbientMode(false);
    syncFabListeningState(false);
  }

  function voiceEnabled() {
    if (companyVoiceEnabled === false) return false;
    try {
      const flag = global.BAUPASS_AI_OPERATOR_VOICE;
      if (flag === 0 || flag === false || flag === "0" || flag === "off") return false;
    } catch {
      /* ignore */
    }
    return true;
  }

  /** Speak a short greeting once per login when admin surface is ready (default on). */
  function welcomeVoiceEnabled() {
    if (companyWelcomeEnabled === false) return false;
    try {
      const flag = global.BAUPASS_AI_OPERATOR_WELCOME;
      if (flag === 0 || flag === false || flag === "0" || flag === "off" || flag === "false") return false;
    } catch {
      /* ignore */
    }
    return true;
  }

  function welcomeStoreKey() {
    // Once per login (token tip) + company — survives SPA section changes, not new logins.
    const cid = readCompanyId() || "";
    const tok = readToken() || "";
    const tip = tok ? tok.slice(-16) : "guest";
    return `${WELCOME_STORE_KEY}:${cid || "none"}:${tip}`;
  }


  async function speakMorningBriefing() {
    const companyId = readCompanyId();
    if (!companyId || !readToken()) return;
    const lang = detectLang();
    try {
      const data = await apiJson(
        `/api/ai/briefing?company_id=${encodeURIComponent(companyId)}&lang=${encodeURIComponent(lang)}`,
        { method: "GET" }
      );
      let raw = String(data.answer || data.briefing || data.text || "").trim();
      if (!raw) return;
      const speakText = cleanSpeakText(raw, true).slice(0, 700);
      const full = `${speakText} ${t("briefingAskNext")}`.trim();
      await global.BaupassAiUi?.speakReply?.(full, lang, {
        force: true,
        authHeaders: () => authHeaders(),
      });
    } catch {
      /* optional */
    }
  }

  async function ensureAmbientVoiceReady() {
    await ensureVoiceStack();
    // Drawer can stay closed; mic/input nodes still exist in the mounted root.
    bindOperatorVoice();
    voiceReady = Boolean(global.BaupassAiUi?.bindVoiceInput);
  }

  async function maybeSpeakWelcome() {
    if (!welcomeVoiceEnabled() || !voiceEnabled()) return;
    if (!isAdminSurfaceReady()) return;
    // Wait for company context so we don't greet under ":none" then again under real company.
    if (!readCompanyId() || !readToken()) return;
    if (welcomeDoneThisLogin || welcomeInFlight) return;
    try {
      if (global.sessionStorage?.getItem(welcomeStoreKey())) {
        welcomeDoneThisLogin = true;
        return;
      }
      // Mark immediately so SPA section swaps / 2s polls never re-trigger.
      global.sessionStorage?.setItem(welcomeStoreKey(), "1");
      welcomeDoneThisLogin = true;
    } catch {
      welcomeDoneThisLogin = true;
    }
    welcomeInFlight = true;
    try {
      setAmbientMode(false);
      await ensureAmbientVoiceReady();
      if (!isAdminSurfaceReady()) return;
      const text = t("welcomeSpeak");
      syncFabListeningState(false);
      const spoken = global.BaupassAiUi?.speakReply?.(text, detectLang(), {
        streaming: false,
        force: true,
        authHeaders: () => authHeaders(),
      });
      try {
        await spoken;
      } catch {
        /* TTS best-effort */
      }
      if (!isAdminSurfaceReady()) return;
      if (hasPendingConfirmCard()) return;
      // One morning briefing after login welcome only — not when browsing sections.
      try {
        await speakMorningBriefing();
      } catch {
        /* briefing optional */
      }
      if (els.voiceHint) els.voiceHint.textContent = t("voiceHint");
      syncFabListeningState(false);
    } catch {
      /* voice optional */
    } finally {
      welcomeInFlight = false;
    }
  }

  function loadStylesheetOnce(href, id) {
    if (document.getElementById(id) || document.querySelector(`link[href^="${href.split("?")[0]}"]`)) {
      return Promise.resolve();
    }
    return new Promise((resolve) => {
      const link = document.createElement("link");
      link.id = id;
      link.rel = "stylesheet";
      link.href = href;
      link.onload = () => resolve();
      link.onerror = () => resolve();
      document.head.appendChild(link);
    });
  }

  function loadScriptOnce(src, id) {
    if (global.BaupassAiUi?.bindVoiceInput) return Promise.resolve();
    // Never inject a second ai-voice-ui.js — that replaces BaupassAiUi and kills bound mics.
    const existing = document.getElementById(id)
      || document.querySelector(`script[src*="ai-voice-ui.js"]`);
    if (existing) {
      return new Promise((resolve) => {
        let tries = 0;
        const tick = () => {
          if (global.BaupassAiUi?.bindVoiceInput || tries > 40) {
            resolve();
            return;
          }
          tries += 1;
          global.setTimeout(tick, 50);
        };
        existing.addEventListener("load", () => resolve(), { once: true });
        tick();
      });
    }
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.id = id;
      s.src = src;
      s.async = true;
      s.onload = () => resolve();
      s.onerror = () => reject(new Error("voice ui load failed"));
      document.head.appendChild(s);
    });
  }

  function ensureVoiceStack() {
    if (!voiceEnabled()) return Promise.reject(new Error("voice disabled"));
    if (global.BaupassAiUi?.bindVoiceInput) {
      voiceReady = true;
      return Promise.resolve();
    }
    if (voiceLibsPromise) return voiceLibsPromise;
    voiceLibsPromise = Promise.all([
      loadStylesheetOnce(`/ai-voice-ui.css?v=${VOICE_UI_VERSION}`, "aioVoiceCss"),
      loadScriptOnce(`/ai-voice-ui.js?v=${VOICE_UI_VERSION}`, "aioVoiceJs"),
    ]).then(() => {
      if (!global.BaupassAiUi?.bindVoiceInput) {
        throw new Error("BaupassAiUi missing");
      }
      voiceReady = true;
    });
    return voiceLibsPromise;
  }

  function operatorVoiceOptions() {
    return {
      inputId: "aioOperatorInput",
      buttonId: "aioOperatorMic",
      sendId: "aioOperatorSend",
      formId: "aioOperatorForm",
      hintId: "aioOperatorVoiceHint",
      replyButtonId: "aioOperatorVoiceReply",
      // ChatGPT-style: listen to full phrase → write text → auto-send after ~5s silence
      // (or user taps Send earlier). Whisper/auto-lang when server has it; else browser.
      chatgptDictation: true,
      dictationMode: "chatgpt",
      autoSubmit: false,
      multilingual: true,
      useWhisper: true,
      preferLiveDraft: false,
      autoStopOnSilence: true,
      silenceMs: 5000,
      minBeforeAutoStopMs: 1800,
      get arabicSpeech() { return detectLang() === "ar" || isRtl(); },
      fallbackToBrowser: true,
      liveSpeechDuringRecord: true,
      guessLanguage: (text) => guessLangFromText(text),
      maxRecordMs: 90000,
      get lang() { return detectLang(); },
      get speechLang() { return detectLang() === "ar" || isRtl() ? "ar" : detectLang(); },
      get hintText() {
        if (confirmVoiceMode && hasPendingConfirmCard()) return t("confirmAskVoice");
        return t("voiceHint");
      },
      authHeaders: () => authHeaders(),
      onTranscript: (text, meta) => {
        const q = String(text || "").trim();
        if (!q || busy || voiceTurnLock) return;

        if (hasPendingConfirmCard() && confirmVoiceMode) {
          const decision = matchVoiceConfirmDecision(q);
          syncFabListeningState(false);
          if (decision && clickPendingConfirm(decision)) return;
          return;
        }

        if (els.input) els.input.value = q;
        if (q === lastVoiceSubmitText && Date.now() - lastVoiceSubmitAt < 8000) return;

        // Prefer Whisper auto-detect, then script/heuristics — reply + TTS in that language.
        let detected = String(meta?.language || els.input?.dataset?.bpDetectedLang || "").slice(0, 2).toLowerCase();
        if (!SYSTEM_LANGS.includes(detected)) detected = guessLangFromText(q);
        if (/[\u0600-\u06FF]/.test(q)) detected = "ar";
        if (detected && SYSTEM_LANGS.includes(detected)) {
          applyDetectedLang(detected);
          if (els.input) els.input.dataset.bpDetectedLang = detected;
        }

        // Silence already waited ~5s → show text and send (ChatGPT-calm).
        handsFreeArmed = false;
        clearVoiceVerify();
        lastVoiceSubmitAt = Date.now();
        lastVoiceSubmitText = q;
        voiceTurnLock = true;
        void submitQuestion(q, els.input, { lang: detectLang(), spoken: true }).catch(() => {
          releaseVoiceTurnLock();
        });
      },
      onNoSpeech: () => {
        // Empty take — show hint, then listen again (no fake sends).
        syncFabListeningState(false);
        releaseVoiceTurnLock();
        if (els.voiceHint) {
          els.voiceHint.textContent = t("voiceNoSpeech") || t("ambientListening");
        }
        if (confirmVoiceMode && hasPendingConfirmCard()) {
          scheduleHandsFreeListen({ forConfirm: true, delayMs: 900 });
          return;
        }
        if (isAmbientEnabled() || isHandsFreeEnabled()) {
          scheduleHandsFreeListen({ delayMs: 1100 });
        }
      },
      onMicError: (err) => {
        syncFabListeningState(false);
        releaseVoiceTurnLock();
        if (confirmVoiceMode && hasPendingConfirmCard()) {
          scheduleHandsFreeListen({ forConfirm: true, delayMs: 1200 });
          return;
        }
        const code = String(err?.message || err?.payload?.error || "");
        if (code === "audio_too_short" || code === "no_speech_detected" || code === "no-speech") {
          if (isAmbientEnabled()) scheduleHandsFreeListen({ delayMs: 900 });
          return;
        }
        const msg = global.BaupassAiUi?.voiceErrorMessage?.(err, detectLang()) || t("voiceUnavailable");
        if (!open) setOpen(true);
        appendMsg("bot", msg);
        if (isAmbientEnabled()) scheduleHandsFreeListen({ delayMs: 2000 });
      },
      onTranscribeError: (err) => {
        syncFabListeningState(false);
        releaseVoiceTurnLock();
        if (confirmVoiceMode && hasPendingConfirmCard()) {
          scheduleHandsFreeListen({ forConfirm: true, delayMs: 1200 });
          return;
        }
        const code = String(err?.payload?.error || err?.message || "");
        const msg = global.BaupassAiUi?.voiceErrorMessage?.(err, detectLang())
          || err?.payload?.hint
          || String(err?.message || err);
        // Always surface failure — silent 400 loops looked like "nothing happens".
        if (!open) setOpen(true);
        if (els.voiceHint) els.voiceHint.textContent = msg;
        if (code !== "audio_too_short" && code !== "no_speech_detected" && code !== "no-speech") {
          appendStatusBot(msg);
        }
        if (isAmbientEnabled()) {
          scheduleHandsFreeListen({
            delayMs: (code === "audio_too_short" || code === "no_speech_detected") ? 1200 : 2500,
          });
        }
      },
      onListening: (active) => {
        // Barge-in: starting the mic interrupts TTS (ChatGPT-like).
        if (active) {
          try { global.BaupassAiUi?.stopSpeaking?.(); } catch { /* ignore */ }
        }
        syncFabListeningState(active);
        if (els.voiceHint) {
          els.voiceHint.textContent = active
            ? ((confirmVoiceMode && hasPendingConfirmCard())
              ? t("confirmAskVoice")
              : (t("voiceListening") || t("ambientListening")))
            : (pendingVerifyText
              ? t("voiceVerifyHint")
              : (isAmbientEnabled() ? t("ambientReady") : t("voiceHint")));
        }
      },
      onTranscribing: (active) => {
        // Do not lock here — lock is set only when a full utterance is accepted/sent.
        if (els.voiceHint) {
          els.voiceHint.textContent = active
            ? t("voiceTranscribing")
            : (isAmbientEnabled() ? t("ambientListening") : t("voiceHint"));
        }
      },
    };
  }

  function markVoiceUnavailable() {
    voiceReady = false;
    if (els.micBtn) {
      els.micBtn.disabled = true;
      els.micBtn.title = t("voiceUnavailable");
      els.micBtn.setAttribute("aria-label", t("voiceUnavailable"));
    }
    if (els.voiceHint) els.voiceHint.textContent = t("voiceUnavailable");
  }

  function bindOperatorVoice() {
    if (!els.input || !els.micBtn) return;
    if (!global.BaupassAiUi?.bindVoiceInput) {
      markVoiceUnavailable();
      return;
    }
    global.BaupassAiUi.bindVoiceInput(operatorVoiceOptions());
    voiceBound = true;
    if (els.voiceHint && !els.voiceHint.textContent) {
      els.voiceHint.textContent = t("voiceHint");
    }
    if (!global.__baupassAioSpeakingHook) {
      global.__baupassAioSpeakingHook = true;
      global.addEventListener("baupass-ai-speaking", (ev) => {
        if (ev.detail?.speaking) return;
        // TTS finished — reopen mic in ambient / hands-free mode.
        if (!isAmbientEnabled() && !(open && handsFreeArmed)) return;
        if (hasPendingConfirmCard()) {
          maybeSpeakConfirmPrompt();
          return;
        }
        scheduleHandsFreeListen();
      });
    }
  }

  function maybeSpeakConfirmPrompt() {
    if (!isAmbientEnabled() && !isHandsFreeEnabled()) return;
    if (!hasPendingConfirmCard()) return;
    confirmVoiceMode = true;
    if (confirmVoiceAsked) {
      // TTS already played — open mic for spoken yes/no.
      scheduleHandsFreeListen({ forConfirm: true });
      return;
    }
    confirmVoiceAsked = true;
    const text = t("confirmAskVoice");
    Promise.resolve(
      global.BaupassAiUi?.speakReply?.(text, detectLang(), {
        force: true,
        authHeaders: () => authHeaders(),
      })
    ).catch(() => {
      // If TTS fails, still listen for yes/no.
      if (hasPendingConfirmCard()) scheduleHandsFreeListen({ forConfirm: true });
    });
  }

  function conversationHasMessages() {
    return Boolean(els.log?.querySelector(".aio-turn, .aio-msg-user, .aio-msg-status-bot"));
  }

  function syncConversationChrome() {
    if (!els.root) return;
    const hasChat = conversationHasMessages();

    // Remove any legacy under-answer composers — only the icon toolbar belongs under answers.
    els.log?.querySelectorAll(".aio-followup").forEach((node) => node.remove());

    if (els.chips) {
      const showChips = !hasChat || chipsForcedOpen;
      els.chips.hidden = !showChips;
      els.chips.classList.toggle("is-collapsed", !showChips);
    }

    // Single composer always at the bottom of the drawer (answers scroll above it).
    if (els.form) {
      els.form.hidden = false;
      els.form.setAttribute("aria-hidden", "false");
    }

    let toggle = els.root.querySelector("[data-aio='chips-toggle']");
    if (hasChat) {
      if (!toggle && els.chips?.parentNode) {
        toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "aio-chips-toggle";
        toggle.setAttribute("data-aio", "chips-toggle");
        toggle.addEventListener("click", () => {
          chipsForcedOpen = !chipsForcedOpen;
          syncConversationChrome();
          if (chipsForcedOpen) renderChips();
        });
        els.chips.parentNode.insertBefore(toggle, els.chips);
      }
      if (toggle) {
        toggle.hidden = false;
        toggle.textContent = chipsForcedOpen ? t("hideChips") : t("showChips");
      }
    } else if (toggle) {
      toggle.hidden = true;
      chipsForcedOpen = false;
    }
  }

  function chipPrompts() {
    const lang = detectLang();
    const packs = {
      de: {
        chipBriefing: "Was ist heute wichtig? Tageslage",
        chipOnSite: "Wer ist heute vor Ort?",
        chipForecast: "Morgen-Prognose zeigen",
        chipLate: "Wer kommt zu spät? Erinnerung vorbereiten",
        chipDocs: "Abgelaufene Dokumente erinnern",
        chipPlan: "Einsatzplan vorbereiten",
        chipInbox: "Offene Urlaubsanträge genehmigen",
        chipSecurity: "Security-Alerts zeigen",
        chipBroadcast: "Mitteilung an alle: Bitte pünktlich erscheinen",
      },
      en: {
        chipBriefing: "What matters today? Daily briefing",
        chipOnSite: "Who is on site today?",
        chipForecast: "Show tomorrow forecast",
        chipLate: "Who is late? Prepare reminder",
        chipDocs: "Remind expired documents",
        chipPlan: "Prepare deployment plan",
        chipInbox: "Approve pending leave requests",
        chipSecurity: "Show security alerts",
        chipBroadcast: "Message everyone: please arrive on time",
      },
      ar: {
        chipBriefing: "ما المهم اليوم؟ ملخص اليوم",
        chipOnSite: "من في الموقع اليوم؟",
        chipForecast: "أظهر توقع الغد",
        chipLate: "من يتأخر؟ جهّز تذكيراً",
        chipDocs: "ذكّر بالوثائق المنتهية",
        chipPlan: "جهّز خطة الانتشار",
        chipInbox: "وافق على طلبات الإجازة المعلّقة",
        chipSecurity: "اعرض تنبيهات الأمن",
        chipBroadcast: "رسالة للجميع: يرجى الحضور في الوقت",
      },
      tr: {
        chipBriefing: "Bugün ne önemli? Günlük özet",
        chipOnSite: "Bugün sahada kim var?",
        chipForecast: "Yarın tahminini göster",
        chipLate: "Kim geç kalıyor? Hatırlatma hazırla",
        chipDocs: "Süresi dolan belgeleri hatırlat",
        chipPlan: "Görev planını hazırla",
        chipInbox: "Bekleyen izinleri onayla",
        chipSecurity: "Güvenlik uyarılarını göster",
        chipBroadcast: "Herkese yaz: lütfen zamanında gelin",
      },
      fr: {
        chipBriefing: "Qu'est-ce qui compte aujourd'hui ? Briefing",
        chipOnSite: "Qui est sur site aujourd'hui ?",
        chipForecast: "Afficher la prévision de demain",
        chipLate: "Qui est en retard ? Préparer un rappel",
        chipDocs: "Rappeler les documents expirés",
        chipPlan: "Préparer le plan de déploiement",
        chipInbox: "Approuver les congés en attente",
        chipSecurity: "Afficher les alertes sécurité",
        chipBroadcast: "Message à tous : merci d'arriver à l'heure",
      },
      es: {
        chipBriefing: "¿Qué importa hoy? Resumen diario",
        chipOnSite: "¿Quién está en obra hoy?",
        chipForecast: "Mostrar previsión de mañana",
        chipLate: "¿Quién llega tarde? Preparar recordatorio",
        chipDocs: "Recordar documentos caducados",
        chipPlan: "Preparar plan de despliegue",
        chipInbox: "Aprobar ausencias pendientes",
        chipSecurity: "Mostrar alertas de seguridad",
        chipBroadcast: "Mensaje a todos: lleguen a tiempo",
      },
      it: {
        chipBriefing: "Cosa conta oggi? Briefing giornaliero",
        chipOnSite: "Chi è in cantiere oggi?",
        chipForecast: "Mostra previsione di domani",
        chipLate: "Chi è in ritardo? Prepara promemoria",
        chipDocs: "Ricorda documenti scaduti",
        chipPlan: "Prepara piano di impiego",
        chipInbox: "Approva ferie in sospeso",
        chipSecurity: "Mostra avvisi di sicurezza",
        chipBroadcast: "Messaggio a tutti: arrivate in orario",
      },
      pl: {
        chipBriefing: "Co dziś ważne? Podsumowanie dnia",
        chipOnSite: "Kto jest dziś na budowie?",
        chipForecast: "Pokaż prognozę na jutro",
        chipLate: "Kto się spóźnia? Przygotuj przypomnienie",
        chipDocs: "Przypomnij o wygasłych dokumentach",
        chipPlan: "Przygotuj plan wdrożenia",
        chipInbox: "Zatwierdź oczekujące urlopy",
        chipSecurity: "Pokaż alerty bezpieczeństwa",
        chipBroadcast: "Wiadomość do wszystkich: proszę przyjść na czas",
      },
    };
    return packs[lang] || packs.en || packs.de;
  }

  function detectSurfaceContext() {
    const path = String(location.pathname || "").toLowerCase();
    const tab = String(
      document.querySelector(".tab.active, .tab[aria-selected='true']")?.getAttribute("data-tab")
      || new URLSearchParams(location.search).get("tab")
      || ""
    ).toLowerCase();
    if (path.includes("contracts")) return "contracts";
    if (path.includes("docs")) return "docs";
    if (path.includes("chat")) return "chat";
    if (path.includes("enterprise-hub")) return "hub";
    if (path.includes("ops-command")) return "ops";
    if (path.includes("ai-command")) return "ai";
    if (tab === "workers" || tab === "access") return "workers";
    if (tab === "operations") return "operations";
    if (tab === "inbox") return "inbox";
    if (tab === "billing") return "billing";
    return "general";
  }

  function chipKeysForContext(ctx) {
    const base = [
      "chipBriefing",
      "chipOnSite",
      "chipForecast",
      "chipLate",
      "chipDocs",
      "chipPlan",
      "chipInbox",
      "chipSecurity",
      "chipBroadcast",
    ];
    const priority = {
      contracts: ["chipDocs", "chipInbox", "chipBriefing", "chipOnSite"],
      docs: ["chipDocs", "chipBriefing", "chipInbox", "chipOnSite"],
      workers: ["chipOnSite", "chipLate", "chipDocs", "chipPlan", "chipBriefing"],
      operations: ["chipBriefing", "chipSecurity", "chipForecast", "chipBroadcast"],
      inbox: ["chipInbox", "chipBriefing", "chipLate", "chipDocs"],
      hub: ["chipSecurity", "chipBriefing", "chipForecast", "chipOnSite"],
      ops: ["chipSecurity", "chipBriefing", "chipOnSite", "chipForecast"],
      billing: ["chipBriefing", "chipInbox", "chipDocs"],
      chat: ["chipBroadcast", "chipInbox", "chipBriefing"],
      ai: ["chipBriefing", "chipForecast", "chipSecurity"],
      general: base,
    };
    const head = priority[ctx] || priority.general;
    const seen = new Set();
    const ordered = [];
    if (lastReminderPrompt) {
      ordered.push("chipSameReminder");
      seen.add("chipSameReminder");
    }
    head.concat(base).forEach((key) => {
      if (seen.has(key)) return;
      seen.add(key);
      ordered.push(key);
    });
    return ordered.slice(0, 6);
  }

  function readRecentPrompts() {
    try {
      const raw = global.localStorage?.getItem(RECENT_PROMPTS_KEY);
      const list = raw ? JSON.parse(raw) : [];
      return Array.isArray(list) ? list.map((x) => String(x || "").trim()).filter(Boolean).slice(0, 6) : [];
    } catch {
      return [];
    }
  }

  function pushRecentPrompt(q) {
    const text = String(q || "").trim();
    if (!text || text.length < 3) return;
    const next = [text].concat(readRecentPrompts().filter((x) => x !== text)).slice(0, 6);
    try {
      global.localStorage?.setItem(RECENT_PROMPTS_KEY, JSON.stringify(next));
    } catch {
      /* ignore */
    }
  }

  function rememberCompanyPrompt(companyId, q) {
    const text = String(q || "").trim();
    const cid = String(companyId || "").trim();
    if (!text || text.length < 3 || !cid || !readToken()) return;
    fetch("/api/ai/operator/memory", {
      method: "POST",
      credentials: "include",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        company_id: cid,
        rememberPrompt: text,
        preferredLang: detectLang(),
      }),
    }).catch(() => {});
  }

  function bindChipClicks(container) {
    container?.querySelectorAll("[data-prompt], [data-action], [data-nav-url], [data-nav-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (busy) return;
        const action = btn.getAttribute("data-action") || "";
        const navUrl = btn.getAttribute("data-nav-url") || "";
        const navTab = btn.getAttribute("data-nav-tab") || "";
        if (action) {
          let params = {};
          try {
            params = JSON.parse(btn.getAttribute("data-params") || "{}");
          } catch {
            params = {};
          }
          appendConfirmCard({
            title: t("confirmTitle"),
            body: `${t("confirmHint")}\n\n${btn.textContent || action}`,
            onApprove: () => runWriteAction({
              action,
              params,
              labelDe: btn.textContent || action,
              labelEn: btn.textContent || action,
              risk: "medium",
            }),
            onReject: () => appendStatusBot(t("rejected")),
          });
          if (!open) setOpen(true);
          return;
        }
        if (navUrl || navTab) {
          runNavigateAction({
            type: "navigate",
            url: navUrl || undefined,
            tab: navTab || undefined,
            labelDe: btn.textContent || "",
            labelEn: btn.textContent || "",
          });
          return;
        }
        if (els.input) els.input.value = btn.getAttribute("data-prompt") || "";
        submitQuestion();
      });
    });
  }

  function renderRecentStrip() {
    if (!els.chips) return;
    let strip = els.root?.querySelector('[data-aio="recent"]');
    const recent = readRecentPrompts();
    if (!recent.length) {
      if (strip) strip.hidden = true;
      return;
    }
    if (!strip && els.chips.parentNode) {
      strip = document.createElement("div");
      strip.className = "aio-recent";
      strip.setAttribute("data-aio", "recent");
      els.chips.parentNode.insertBefore(strip, els.chips);
    }
    if (!strip) return;
    strip.hidden = false;
    strip.innerHTML = `<span class="aio-recent-label">${escapeHtml(t("recentLabel"))}</span>`
      + recent.slice(0, 4).map((q) => (
        `<button type="button" class="aio-chip aio-chip-recent" data-prompt="${escapeHtml(q)}">${escapeHtml(q.length > 42 ? `${q.slice(0, 40)}…` : q)}</button>`
      )).join("");
    bindChipClicks(strip);
  }

  function applySectorLabel(text) {
    const site = String(sectorTerms?.termSite || "").trim();
    const workers = String(sectorTerms?.termWorkers || "").trim();
    let out = String(text || "");
    if (site) {
      out = out
        .replace(/Baustelle/g, site)
        .replace(/budowie/gi, site)
        .replace(/cantiere/gi, site)
        .replace(/\bobra\b/gi, site)
        .replace(/موقع بناء/g, site)
        .replace(/vor Ort/g, site)
        .replace(/on site/gi, site)
        .replace(/sur site/gi, site)
        .replace(/sahada/gi, site)
        .replace(/في الموقع/g, `في ${site}`);
    }
    if (workers) {
      out = out.replace(/Mitarbeiter/g, workers).replace(/\bworkers\b/gi, workers);
    }
    return out;
  }

  function renderChips() {
    if (!els.chips) return;
    const prompts = chipPrompts();
    const items = chipKeysForContext(detectSurfaceContext());
    const serverBits = (serverPromptChips || []).slice(0, 4).map((p) => {
      const label = applySectorLabel(String(p.label || p.prompt || "").trim());
      if (!label) return "";
      if (p.action) {
        const params = escapeHtml(JSON.stringify(p.params || {}));
        return `<button type="button" class="aio-chip aio-chip-live aio-chip-action" data-action="${escapeHtml(p.action)}" data-params="${params}" title="${escapeHtml(p.reason || label)}">${escapeHtml(label)}</button>`;
      }
      if (p.url || p.tab) {
        return `<button type="button" class="aio-chip aio-chip-live aio-chip-nav" data-nav-url="${escapeHtml(p.url || "")}" data-nav-tab="${escapeHtml(p.tab || "")}" title="${escapeHtml(p.reason || label)}">${escapeHtml(label)}</button>`;
      }
      const prompt = applySectorLabel(String(p.prompt || label).trim());
      if (!prompt) return "";
      return `<button type="button" class="aio-chip aio-chip-live" data-prompt="${escapeHtml(prompt)}" title="${escapeHtml(p.reason || label)}">${escapeHtml(label)}</button>`;
    }).filter(Boolean).join("");
    const staticBits = items.map((key) => {
      if (key === "chipSameReminder") {
        const prompt = String(lastReminderPrompt || "").trim();
        if (!prompt) return "";
        const label = t("chipSameReminder") || prompt;
        return `<button type="button" class="aio-chip aio-chip-memory" data-prompt="${escapeHtml(prompt)}" title="${escapeHtml(prompt)}">${escapeHtml(label)}</button>`;
      }
      const label = applySectorLabel(t(key));
      const prompt = applySectorLabel(prompts[key] || t(key));
      return `<button type="button" class="aio-chip" data-prompt="${escapeHtml(prompt)}">${escapeHtml(label)}</button>`;
    }).filter(Boolean).join("");
    els.chips.innerHTML = serverBits + staticBits;
    bindChipClicks(els.chips);
    renderRecentStrip();
    syncConversationChrome();
  }

  async function probeOpsPulse() {
    const now = Date.now();
    if (now - _lastPulseProbe < 45000) return;
    _lastPulseProbe = now;
    const companyId = readCompanyId();
    if (!companyId || !readToken() || !companyOperatorEnabled) return;
    try {
      const surface = detectSurfaceContext();
      const tab = String(
        document.querySelector(".tab.active, .tab[aria-selected='true']")?.getAttribute("data-tab")
        || new URLSearchParams(location.search).get("tab")
        || ""
      ).trim();
      const qs = new URLSearchParams({
        company_id: companyId,
        lang: detectLang(),
        surface,
        path: location.pathname || "",
      });
      if (tab) qs.set("tab", tab);
      const res = await fetch(
        `/api/ai/operator/pulse?${qs.toString()}`,
        { credentials: "include", headers: authHeaders() }
      );
      if (!res.ok) {
        // Fallback to classic prompts if pulse route missing on older servers.
        _lastPulseProbe = now + 60000;
        return;
      }
      const data = await res.json();
      if (data.sectorTerms && typeof data.sectorTerms === "object") {
        sectorTerms = {
          termSite: String(data.sectorTerms.termSite || ""),
          termWorkers: String(data.sectorTerms.termWorkers || ""),
          sectorLabel: String(data.sectorTerms.sectorLabel || ""),
        };
      }
      try {
        const memRes = await fetch(
          `/api/ai/operator/memory?company_id=${encodeURIComponent(companyId)}`,
          { credentials: "include", headers: authHeaders() }
        );
        if (memRes.ok) {
          const memData = await memRes.json();
          lastReminderPrompt = String(memData?.memory?.lastReminderPrompt || "").trim();
        }
      } catch {
        /* optional */
      }
      const list = Array.isArray(data.recommendations) ? data.recommendations : [];
      serverPromptChips = list.slice(0, 4).map((p) => {
        const label = String(p.label || p.prompt || p.id || "").trim();
        const prompt = String(p.prompt || p.label || "").trim();
        const action = String(p.action || "").trim();
        const navUrl = String(p.url || "").trim();
        const navTab = String(p.tab || "").trim();
        const params = p.params && typeof p.params === "object" ? { ...p.params } : {};
        if (action === "export_ops_snapshot" && !params.lang) {
          params.lang = detectLang();
        }
        const type = p.type || (action ? "execute" : (navUrl || navTab ? "navigate" : "prompt"));
        return {
          label,
          prompt: (action || navUrl || navTab) ? "" : prompt,
          action,
          params,
          url: navUrl,
          tab: navTab,
          reason: String(p.reason || "").trim(),
          type,
        };
      }).filter((p) => p.label && (p.prompt || p.action || p.url || p.tab));
      opsUrgencyScore = Number(data.urgency || 0);
      if (els.fab) {
        els.fab.classList.toggle("is-urgent", Boolean(data.urgent) || opsUrgencyScore > 0);
      }
      renderChips();
      if (opsUrgencyScore > 0) {
        const tip = (readToken() || "").slice(-16);
        const key = `${URGENCY_TOAST_KEY}:${companyId}:${tip}`;
        try {
          if (!global.sessionStorage?.getItem(key)) {
            global.sessionStorage?.setItem(key, "1");
            showToast(t("urgencyToast"));
          }
        } catch {
          /* ignore */
        }
      }
    } catch {
      /* optional */
    }
  }

  function ensureVerifyBar(root) {
    const form = root.querySelector('[data-aio="form"]');
    if (!form || form.querySelector('[data-aio="verify"]')) return;
    const bar = document.createElement("div");
    bar.className = "aio-verify";
    bar.setAttribute("data-aio", "verify");
    bar.hidden = true;
    bar.innerHTML = `
      <div class="aio-verify-label" data-aio="verify-label"></div>
      <p class="aio-verify-text" data-aio="verify-text"></p>
      <div class="aio-verify-actions">
        <button type="button" class="aio-btn aio-btn-primary" data-aio="verify-send"></button>
        <button type="button" class="aio-btn" data-aio="verify-retry"></button>
      </div>
    `;
    form.insertBefore(bar, form.firstChild);
  }

  function ensureHeadControls(root) {
    const actions = root.querySelector(".aio-head-actions");
    if (actions && !actions.querySelector("#aioOperatorVoiceReply")) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "aio-icon-btn";
      btn.id = "aioOperatorVoiceReply";
      btn.setAttribute("data-aio", "speaker");
      btn.setAttribute("aria-pressed", "true");
      btn.textContent = "🔊";
      actions.insertBefore(btn, actions.firstChild);
    }
    const fab = root.querySelector('[data-aio="fab"]');
    if (fab && !fab.querySelector('[data-aio="voice-badge"]')) {
      const badge = document.createElement("span");
      badge.className = "aio-fab-badge";
      badge.setAttribute("data-aio", "voice-badge");
      badge.hidden = true;
      badge.setAttribute("aria-hidden", "true");
      fab.appendChild(badge);
    }
  }

  function bindRootElements(root) {
    ensureVerifyBar(root);
    ensureHeadControls(root);
    els = {
      root,
      backdrop: root.querySelector('[data-aio="backdrop"]'),
      drawer: root.querySelector('[data-aio="drawer"]'),
      fab: root.querySelector('[data-aio="fab"]'),
      voiceBadge: root.querySelector('[data-aio="voice-badge"]'),
      title: root.querySelector('[data-aio="title"]'),
      subtitle: root.querySelector('[data-aio="subtitle"]'),
      chips: root.querySelector('[data-aio="chips"]'),
      log: root.querySelector('[data-aio="log"]'),
      empty: root.querySelector('[data-aio="empty"]'),
      form: root.querySelector('[data-aio="form"]'),
      input: root.querySelector('[data-aio="input"]'),
      micBtn: root.querySelector('[data-aio="mic"]'),
      speakerBtn: root.querySelector("#aioOperatorVoiceReply"),
      voiceHint: root.querySelector('[data-aio="voice-hint"]'),
      verifyBar: root.querySelector('[data-aio="verify"]'),
      verifyText: root.querySelector('[data-aio="verify-text"]'),
      verifyLabel: root.querySelector('[data-aio="verify-label"]'),
      verifySendBtn: root.querySelector('[data-aio="verify-send"]'),
      verifyRetryBtn: root.querySelector('[data-aio="verify-retry"]'),
      handsFreeBtn: root.querySelector('[data-aio="handsfree"]'),
      newChatBtn: root.querySelector('[data-aio="newchat"]'),
      sendBtn: root.querySelector('[data-aio="send"]'),
      expandLink: root.querySelector('[data-aio="expand"]'),
      closeBtn: root.querySelector('[data-aio="close"]'),
    };
  }

  async function probeVoiceReadiness() {
    if (!els.voiceBadge || !readToken()) return;
    try {
      const res = await fetch(`/api/ai/status?lang=${encodeURIComponent(detectLang())}`, {
        credentials: "include",
        headers: authHeaders(),
      });
      if (!res.ok) return;
      const data = await res.json();
      const speech = data.voiceSpeech || {};
      const whisper = data.voiceTranscription || {};
      const ttsOk = speech.configured === true;
      const whisperOk = whisper.configured === true;
      const ready = Boolean(ttsOk || whisperOk);
      els.voiceBadge.hidden = false;
      els.voiceBadge.classList.toggle("is-ok", ready);
      els.voiceBadge.classList.toggle("is-limited", !ready);
      els.voiceBadge.title = ready ? t("voiceBadgeOk") : t("voiceBadgeLimited");
      els.fab?.setAttribute("title", `${t("fabLabel")} · ${els.voiceBadge.title}`);
    } catch {
      /* optional */
    }
  }

  function bindGlobalShortcutsOnce() {
    if (global.__baupassAioKeys) return;
    global.__baupassAioKeys = true;
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && open) {
        setOpen(false);
        return;
      }
      const key = String(e.key || "").toLowerCase();
      if (!(e.altKey && !e.ctrlKey && !e.metaKey && key === "a")) return;
      if (!isAdminSurfaceReady() || companyOperatorEnabled === false) return;
      e.preventDefault();
      const willOpen = !open;
      setOpen(willOpen);
      if (willOpen) global.setTimeout(() => els.input?.focus?.(), 40);
    });
  }

  function bindRootEventsOnce(root) {
    if (root.dataset.aioBound === "1") return;
    root.dataset.aioBound = "1";
    els.fab?.addEventListener("click", () => {
      if (Date.now() < suppressFabClickUntil) return;
      try {
        if (global.BaupassAiUi?.isVoiceCaptureActive?.("aioOperatorInput")) {
          // Finish utterance → show full text for review (never abort mid-listen).
          if (typeof global.BaupassAiUi.finishVoiceCapture === "function") {
            global.BaupassAiUi.finishVoiceCapture("aioOperatorInput");
          } else {
            els.micBtn?.bpStopVoiceCapture?.();
          }
          syncFabListeningState(false);
          return;
        }
      } catch {
        /* ignore */
      }
      setOpen(!open);
    });
    els.backdrop?.addEventListener("click", () => setOpen(false));
    els.closeBtn?.addEventListener("click", () => setOpen(false));
    els.newChatBtn?.addEventListener("click", () => { void startNewChat(); });
    els.handsFreeBtn?.addEventListener("click", () => {
      setHandsFreeEnabled(!isHandsFreeEnabled());
      if (isHandsFreeEnabled() && els.voiceHint) {
        els.voiceHint.textContent = t("handsFreeOn");
      }
    });
    els.form?.addEventListener("submit", (e) => {
      e.preventDefault();
      if (pendingVerifyText) {
        // Prefer current textarea (operator may have edited before send).
        pendingVerifyText = String(els.input?.value || pendingVerifyText).trim();
        confirmVoiceVerifyAndSend();
        return;
      }
      submitQuestion();
    });
    els.input?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (pendingVerifyText) {
          pendingVerifyText = String(els.input?.value || pendingVerifyText).trim();
          confirmVoiceVerifyAndSend();
          return;
        }
        submitQuestion();
      }
    });
    els.verifySendBtn?.addEventListener("click", () => {
      pendingVerifyText = String(els.input?.value || pendingVerifyText).trim();
      confirmVoiceVerifyAndSend();
    });
    els.verifyRetryBtn?.addEventListener("click", () => {
      retryVoiceCapture();
    });
    els.input?.addEventListener("input", () => {
      if (!pendingVerifyText) return;
      pendingVerifyText = String(els.input.value || "").trim();
      if (els.verifyText) els.verifyText.textContent = pendingVerifyText;
    });
  }

  function mount() {
    if (shouldSkipPage()) {
      destroyDuplicateRoots(null);
      return;
    }
    const existing = document.getElementById("aioOperatorRoot");
    if (existing) {
      mounted = true;
      destroyDuplicateRoots(existing);
      bindRootElements(existing);
      bindFabDragOnce(existing);
      bindRootEventsOnce(existing);
      restoreFabPos();
      clampCurrentFabPos({ persist: false });
      refreshCopy();
      refreshVisibility();
      updateExpandHref();
      bindGlobalShortcutsOnce();
      void probeVoiceReadiness();
      return;
    }
    if (mounted) return;
    mounted = true;

    destroyDuplicateRoots(null);

    if (!document.getElementById("aioOperatorCss")) {
      const link = document.createElement("link");
      link.id = "aioOperatorCss";
      link.rel = "stylesheet";
      link.href = `/ai-operator-fab.css?v=${VERSION}`;
      document.head.appendChild(link);
    }

    const root = document.createElement("div");
    root.className = "aio-root";
    root.id = "aioOperatorRoot";
    root.innerHTML = `
      <div class="aio-backdrop" data-aio="backdrop" hidden></div>
      <section class="aio-drawer" data-aio="drawer" hidden aria-label="AI assistant">
        <header class="aio-head">
          <img class="aio-head-mark" src="/branding/suppix-ai-mark.svg" alt="" width="28" height="28" />
          <div>
            <h2 data-aio="title"></h2>
            <p data-aio="subtitle"></p>
          </div>
          <div class="aio-head-actions">
            <button type="button" class="aio-icon-btn" id="aioOperatorVoiceReply" data-aio="speaker" title="Voice replies" aria-label="Voice replies" aria-pressed="true">🔊</button>
            <button type="button" class="aio-icon-btn" data-aio="newchat" title="New chat" aria-label="New chat">+</button>
            <button type="button" class="aio-icon-btn aio-handsfree" data-aio="handsfree" aria-pressed="false" title="Hands-free">∞</button>
            <button type="button" class="aio-icon-btn" data-aio="close" title="Close" aria-label="Close">✕</button>
          </div>
        </header>
        <div class="aio-chips" data-aio="chips"></div>
        <div class="aio-log" data-aio="log">
          <div class="aio-empty" data-aio="empty"></div>
        </div>
        <form class="aio-form" data-aio="form" id="aioOperatorForm">
          <div class="aio-verify" data-aio="verify" hidden>
            <div class="aio-verify-label" data-aio="verify-label"></div>
            <p class="aio-verify-text" data-aio="verify-text"></p>
            <div class="aio-verify-actions">
              <button type="button" class="aio-btn aio-btn-primary" data-aio="verify-send"></button>
              <button type="button" class="aio-btn" data-aio="verify-retry"></button>
            </div>
          </div>
          <div class="ai-form-row aio-composer-row">
            <textarea id="aioOperatorInput" class="bp-ai-input" data-aio="input" rows="2" maxlength="4000"></textarea>
            <button type="button" class="aio-mic" id="aioOperatorMic" data-aio="mic" aria-label="Mic"></button>
            <button class="aio-send" type="submit" id="aioOperatorSend" data-aio="send"></button>
          </div>
          <p class="aio-voice-hint bp-ai-composer-hint" id="aioOperatorVoiceHint" data-aio="voice-hint"></p>
        </form>
        <div class="aio-footer-link">
          <a data-aio="expand" href="/ai-command-center.html" target="_blank" rel="noopener"></a>
        </div>
      </section>
      <button type="button" class="aio-fab" data-aio="fab" aria-expanded="false" hidden>
        <span class="aio-fab-pulse" aria-hidden="true"></span>
        <span class="aio-fab-badge" data-aio="voice-badge" hidden aria-hidden="true"></span>
        <svg class="aio-fab-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3z" stroke="currentColor" stroke-width="1.4" fill="currentColor" opacity="0.9"/>
          <path d="M18.5 14.5l.9 2.6 2.6.9-2.6.9-.9 2.6-.9-2.6-2.6-.9 2.6-.9.9-2.6z" fill="currentColor" opacity="0.7"/>
        </svg>
      </button>
    `;
    document.body.appendChild(root);
    bindRootElements(root);
    bindFabDragOnce(root);
    bindRootEventsOnce(root);
    restoreFabPos();
    clampCurrentFabPos({ persist: false });

    refreshCopy();
    refreshVisibility();
    updateExpandHref();
    bindGlobalShortcutsOnce();
    void probeVoiceReadiness();
    if (!global.__baupassAioSurfacePulse) {
      global.__baupassAioSurfacePulse = true;
      const refreshPulseSoon = () => {
        _lastPulseProbe = 0;
        void probeOpsPulse();
      };
      document.addEventListener("click", (ev) => {
        const tab = ev.target?.closest?.(".tab[data-tab], .ops-embed-tab[data-ops-page]");
        if (tab) global.setTimeout(refreshPulseSoon, 250);
      }, true);
      global.addEventListener("baupass-ai-navigate", () => global.setTimeout(refreshPulseSoon, 300));
      global.addEventListener("popstate", () => global.setTimeout(refreshPulseSoon, 200));
    }

    global.addEventListener("baupass-ai-operator-ready", () => {
      visibleForced = true;
      cacheCompanyEnabled(true);
      refreshVisibility();
    });
    global.addEventListener("baupass-ai-operator-hide", () => {
      cacheCompanyEnabled(false);
      visibleForced = false;
      refreshVisibility();
    });
    try {
      if (!global.__baupassAioBc && typeof BroadcastChannel !== "undefined") {
        global.__baupassAioBc = new BroadcastChannel("baupass-aio-visibility");
        global.__baupassAioBc.onmessage = (ev) => {
          const enabled = ev?.data?.enabled !== false;
          if (ev?.data?.voiceEnabled != null) companyVoiceEnabled = Boolean(ev.data.voiceEnabled);
          if (ev?.data?.welcomeEnabled != null) companyWelcomeEnabled = Boolean(ev.data.welcomeEnabled);
          cacheCompanyEnabled(enabled);
          visibleForced = enabled ? true : false;
          if (!companyVoiceEnabled) stopAllOperatorVoice({ clearAmbient: true });
          refreshVisibility();
        };
      }
    } catch {
      /* ignore */
    }
    global.addEventListener("storage", refreshVisibility);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) {
        refreshVisibility();
        clampCurrentFabPos({ persist: true });
      }
    });
    global.addEventListener("pageshow", refreshVisibility);
    global.addEventListener("resize", () => clampCurrentFabPos({ persist: true }));
    // Stable visibility: catch late logins / SPA-like view swaps on any page.
    if (!global.__baupassAioVisibilityTimer) {
      global.__baupassAioVisibilityTimer = setInterval(refreshVisibility, 2000);
    }
    probeSessionRole().catch(() => {});
  }

  let _lastProbe = 0;
  async function probeSessionRole() {
    const now = Date.now();
    if (now - _lastProbe < 15000) return;
    _lastProbe = now;
    if (!readToken()) {
      refreshVisibility();
      return;
    }
    try {
      const res = await fetch("/api/v2/auth/session", {
        credentials: "include",
        headers: authHeaders(),
      });
      if (!res.ok) {
        refreshVisibility();
        return;
      }
      const data = await res.json();
      const user = data.user || data;
      if (user && typeof user === "object") {
        const WP = global.WorkPassStorage;
        const key = WP?.KEYS?.ADMIN_USER || "workpass-admin-user";
        try {
          if (WP?.setItem) WP.setItem(key, JSON.stringify(user));
          else localStorage.setItem(key, JSON.stringify(user));
        } catch {
          /* ignore quota */
        }
        if (user.company_id && !readCompanyId()) {
          const ck = WP?.KEYS?.ADMIN_COMPANY || "workpass-admin-company";
          try {
            if (WP?.setItem) WP.setItem(ck, String(user.company_id));
            else localStorage.setItem(ck, String(user.company_id));
          } catch {
            /* ignore */
          }
        }
        const role = String(user.role || "").trim();
        if (ADMIN_ROLES.has(role)) {
          visibleForced = true;
        }
      }
    } catch {
      /* offline / public page */
    }
    refreshVisibility();
  }

  function updateExpandHref() {
    if (!els.expandLink) return;
    const cid = readCompanyId();
    const lang = detectLang();
    const qs = new URLSearchParams();
    if (cid) qs.set("company_id", cid);
    if (lang) qs.set("lang", lang);
    els.expandLink.href = `/ai-command-center.html${qs.toString() ? `?${qs}` : ""}`;
  }

  function clearEmpty() {
    els.empty?.remove?.();
    els.empty = null;
  }

  function appendMsg(role, text) {
    clearEmpty();
    if (role === "user") {
      const div = document.createElement("div");
      div.className = "aio-msg aio-msg-user";
      div.textContent = text || "";
      els.log.appendChild(div);
      els.log.scrollTop = els.log.scrollHeight;
      return div;
    }

    const turn = document.createElement("div");
    turn.className = "aio-turn";
    const div = document.createElement("div");
    div.className = "aio-msg aio-msg-bot";
    const label = document.createElement("div");
    label.className = "aio-msg-bot-label";
    label.textContent = t("botLabel");
    const body = document.createElement("div");
    body.className = "aio-msg-body";
    body.textContent = text || "";
    div.appendChild(label);
    div.appendChild(body);
    turn.appendChild(div);
    els.log.appendChild(turn);
    els.log.scrollTop = els.log.scrollHeight;
    div._aioBody = body;
    div._aioTurn = turn;
    return div;
  }

  function polishAnswerText(text) {
    let s = String(text || "");
    s = s.replace(/DECISION_JSON\s*=\s*\{[\s\S]*?\n\}\s*/gi, "");
    s = s.replace(/```(?:json)?\s*\{[\s\S]*?"recommendation"[\s\S]*?\}\s*```/gi, "");
    s = s.replace(/\n{3,}/g, "\n\n").trim();
    return s;
  }

  function formatAiAnswerHtml(text) {
    const raw = polishAnswerText(text);
    if (!raw) return "";
    const esc = (v) => escapeHtml(v);
    const inline = (line) => esc(line)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*\w])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
    const lines = raw.split(/\r?\n/);
    const parts = [];
    let listType = null;
    let listItems = [];
    const flushList = () => {
      if (!listType || !listItems.length) return;
      parts.push(`<${listType}>${listItems.map((li) => `<li>${li}</li>`).join("")}</${listType}>`);
      listType = null;
      listItems = [];
    };
    let para = [];
    const flushPara = () => {
      if (!para.length) return;
      parts.push(`<p>${para.join("<br>")}</p>`);
      para = [];
    };
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) {
        flushList();
        flushPara();
        continue;
      }
      const ul = trimmed.match(/^[-*•]\s+(.+)$/);
      const ol = trimmed.match(/^\d+[.)]\s+(.+)$/);
      if (ul || ol) {
        flushPara();
        const nextType = ul ? "ul" : "ol";
        if (listType && listType !== nextType) flushList();
        listType = nextType;
        listItems.push(inline(ul ? ul[1] : ol[1]));
        continue;
      }
      flushList();
      para.push(inline(trimmed));
    }
    flushList();
    flushPara();
    return parts.join("") || `<p>${inline(raw)}</p>`;
  }

  function setBotText(botEl, text) {
    if (!botEl) return;
    const body = botEl._aioBody || botEl.querySelector(".aio-msg-body");
    if (body) {
      body.textContent = text || "";
      return;
    }
    botEl.textContent = text || "";
  }

  function finalizeBotBody(botEl, text) {
    const body = botEl?._aioBody || botEl?.querySelector?.(".aio-msg-body");
    if (!body) {
      setBotText(botEl, text);
      return polishAnswerText(text);
    }
    const cleaned = polishAnswerText(text);
    body.innerHTML = formatAiAnswerHtml(cleaned);
    botEl.dataset.raw = cleaned;
    return cleaned;
  }

  function getBotPlainText(botEl) {
    if (botEl?.dataset?.raw) return String(botEl.dataset.raw).trim();
    const body = botEl?._aioBody || botEl?.querySelector?.(".aio-msg-body");
    return String(body?.textContent || botEl?.textContent || "").trim();
  }

  function showToast(msg) {
    if (!els.root || !msg) return;
    let toast = els.root.querySelector(".aio-toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.className = "aio-toast";
      els.root.appendChild(toast);
    }
    toast.textContent = msg;
    toast.classList.add("is-on");
    global.clearTimeout(showToast._t);
    showToast._t = global.setTimeout(() => toast.classList.remove("is-on"), 1800);
  }

  function iconSvg(name) {
    const icons = {
      copy: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>',
      like: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 11v10"/><path d="M15.5 21H9a2 2 0 0 1-2-2v-8l4-7a2 2 0 0 1 3.7 1.2L14 10h5.2a2 2 0 0 1 1.95 2.4l-1.4 7A2 2 0 0 1 17.8 21H15.5z"/></svg>',
      dislike: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M17 13V3"/><path d="M8.5 3H15a2 2 0 0 1 2 2v8l-4 7a2 2 0 0 1-3.7-1.2L10 14H4.8a2 2 0 0 1-1.95-2.4l1.4-7A2 2 0 0 1 6.2 3H8.5z"/></svg>',
      share: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12"/><path d="m8 7 4-4 4 4"/><path d="M5 13v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5"/></svg>',
      regen: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12a9 9 0 1 1-2.6-6.3"/><path d="M21 3v6h-6"/></svg>',
      more: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="19" cy="12" r="1.4" fill="currentColor" stroke="none"/></svg>',
      speak: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 10v4a2 2 0 0 0 2 2h2l5 4V4L7 8H5a2 2 0 0 0-2 2z"/><path d="M16.5 8.5a5 5 0 0 1 0 7"/><path d="M19 6a8.5 8.5 0 0 1 0 12"/></svg>',
    };
    return icons[name] || "";
  }

  function closeAnswerMoreMenus(except) {
    els.log?.querySelectorAll(".aio-msg-more-menu").forEach((menu) => {
      if (except && menu === except) return;
      menu.classList.add("is-hidden");
      menu.parentElement?.classList.remove("has-open-menu");
    });
  }

  function attachAnswerToolbar(botEl, rawText) {
    if (!botEl || botEl.querySelector(".aio-msg-actions")) return;
    const text = polishAnswerText(rawText || getBotPlainText(botEl));
    botEl.dataset.raw = text;
    const row = document.createElement("div");
    row.className = "aio-msg-actions";
    const mkBtn = (label, iconName) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "aio-msg-action-btn";
      b.title = label;
      b.setAttribute("aria-label", label);
      b.innerHTML = iconSvg(iconName);
      return b;
    };

    // Same order as AI Command Center: copy · like · dislike · share · regen · speak · more
    const copyBtn = mkBtn(t("msgCopy"), "copy");
    const likeBtn = mkBtn(t("msgLike"), "like");
    const dislikeBtn = mkBtn(t("msgDislike"), "dislike");
    const shareBtn = mkBtn(t("msgShare"), "share");
    const regenBtn = mkBtn(t("msgRegenerate"), "regen");
    const speakBtn = mkBtn(t("msgReadAloud"), "speak");
    const moreBtn = mkBtn(t("msgMore"), "more");

    const menu = document.createElement("div");
    menu.className = "aio-msg-more-menu is-hidden";
    menu.addEventListener("click", (ev) => ev.stopPropagation());
    const lang = detectLang();
    const timeLabel = new Date().toLocaleString(
      lang === "ar" ? "ar" : lang === "en" ? "en-GB" : "de-DE",
      { dateStyle: "medium", timeStyle: "short" },
    );
    menu.innerHTML = `<span class="aio-msg-more-time">${escapeHtml(timeLabel)}</span>`;
    const readBtn = document.createElement("button");
    readBtn.type = "button";
    readBtn.innerHTML = `<span class="aio-msg-more-ico">${iconSvg("speak")}</span><span data-read-label>${escapeHtml(t("msgReadAloud"))}</span>`;
    menu.appendChild(readBtn);
    row.append(copyBtn, likeBtn, dislikeBtn, shareBtn, regenBtn, speakBtn, moreBtn, menu);

    const setSpeakingUi = (on) => {
      speakBtn.classList.toggle("is-active", on);
      moreBtn.classList.toggle("is-speaking", on);
      speakBtn.title = on ? t("msgStopReading") : t("msgReadAloud");
      speakBtn.setAttribute("aria-label", speakBtn.title);
      const labelEl = readBtn.querySelector("[data-read-label]");
      if (labelEl) labelEl.textContent = on ? t("msgStopReading") : t("msgReadAloud");
    };

    const runReadAloud = async () => {
      closeAnswerMoreMenus();
      row.classList.remove("has-open-menu");
      if (global.BaupassAiUi?.isSpeaking?.()) {
        global.BaupassAiUi.stopSpeaking?.();
        setSpeakingUi(false);
        return;
      }
      setSpeakingUi(true);
      try {
        await ensureVoiceStack().catch(() => {});
        const speakText = cleanSpeakText(text, true);
        await global.BaupassAiUi?.speakReply?.(speakText, detectLang(), {
          spoken: true,
          force: true,
          authHeaders: () => authHeaders(),
        });
      } catch {
        /* ignore */
      } finally {
        setSpeakingUi(false);
      }
    };

    copyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(text);
      } catch {
        /* ignore */
      }
      showToast(t("msgCopied"));
    });
    likeBtn.addEventListener("click", () => {
      likeBtn.classList.add("is-active");
      dislikeBtn.classList.remove("is-active");
      showToast(t("msgLike"));
    });
    dislikeBtn.addEventListener("click", () => {
      dislikeBtn.classList.add("is-active");
      likeBtn.classList.remove("is-active");
      showToast(t("msgDislike"));
    });
    shareBtn.addEventListener("click", async () => {
      try {
        if (navigator.share) {
          await navigator.share({ text });
          return;
        }
      } catch {
        /* fall through */
      }
      try {
        await navigator.clipboard.writeText(text);
      } catch {
        /* ignore */
      }
      showToast(t("msgShareCopied"));
    });
    regenBtn.addEventListener("click", () => {
      const q = String(lastUserQuestion || "").trim();
      if (!q) {
        showToast(t("msgNoRegen"));
        return;
      }
      submitQuestion(q);
    });
    speakBtn.addEventListener("click", () => { void runReadAloud(); });
    readBtn.addEventListener("click", () => { void runReadAloud(); });
    moreBtn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const opening = menu.classList.contains("is-hidden");
      closeAnswerMoreMenus(opening ? menu : null);
      menu.classList.toggle("is-hidden", !opening);
      row.classList.toggle("has-open-menu", opening);
    });

    if (!global.__baupassAioMoreClose) {
      global.__baupassAioMoreClose = true;
      document.addEventListener("click", () => closeAnswerMoreMenus());
    }

    botEl.appendChild(row);
  }

  function appendStatus(text) {
    clearEmpty();
    let el = els.log.querySelector(".aio-msg-status");
    if (!el) {
      el = document.createElement("div");
      el.className = "aio-msg-status";
      els.log.appendChild(el);
    }
    el.textContent = text || "";
    els.log.scrollTop = els.log.scrollHeight;
    return el;
  }

  function removeStatus() {
    els.log?.querySelector(".aio-msg-status")?.remove?.();
  }

  function looksSensitiveQuestion(q) {
    return /gehalt|salary|راتب|iban|passport|passnummer|ausweis|ssn|steuer|sensitive|حسّاس|خاص/i.test(q || "");
  }

  async function ensureSession() {
    if (!sessionId) sessionId = loadStoredSessionId();
    if (sessionId) return sessionId;
    const companyId = readCompanyId();
    if (!companyId) throw new Error(t("needCompany"));
    const res = await fetch("/api/ai/sessions", {
      method: "POST",
      credentials: "include",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        company_id: companyId,
        agent_id: "operations",
        lang: detectLang(),
        title: "Operator FAB",
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.hint || err.error || t("errGeneric"));
    }
    const data = await res.json();
    sessionId = String(data.id || data.sessionId || data.session?.id || "").trim();
    persistSessionId(sessionId);
    return sessionId;
  }

  async function submitQuestion(raw, sourceInput, extraOpts) {
    if (busy) return;
    const inputEl = sourceInput || els.input;
    const fromVoice = Boolean(
      (extraOpts && extraOpts.spoken)
      || global.BaupassAiUi?.consumeVoiceInputFlag?.(inputEl)
    );
    const q = String(raw != null ? raw : inputEl?.value || "").trim();
    if (!q) {
      if (fromVoice) releaseVoiceTurnLock();
      return;
    }
    if (!readToken()) {
      appendStatusBot(t("needAuth"));
      if (fromVoice) releaseVoiceTurnLock();
      return;
    }
    const companyId = readCompanyId();
    if (!companyId) {
      appendStatusBot(t("needCompany"));
      if (fromVoice) releaseVoiceTurnLock();
      return;
    }
    pushRecentPrompt(q);
    rememberCompanyPrompt(companyId, q);

    const forcedLang = String(extraOpts?.lang || inputEl?.dataset?.bpDetectedLang || "").slice(0, 2).toLowerCase();
    if (forcedLang && SYSTEM_LANGS.includes(forcedLang)) {
      applyDetectedLang(forcedLang);
    } else if (fromVoice) {
      const guessed = guessLangFromText(q);
      if (guessed) applyDetectedLang(guessed);
    }
    const lang = detectLang();

    if (looksSensitiveQuestion(q)) {
      lastUserQuestion = q;
      appendConfirmCard({
        title: t("sensitiveAsk"),
        body: q,
        onApprove: () => askStream(q, { allowSensitive: true, spoken: fromVoice, lang }),
          onReject: () => appendStatusBot(t("rejected")),
        approveLabel: t("sensitiveYes"),
        rejectLabel: t("sensitiveNo"),
      });
      maybeSpeakConfirmPrompt();
      if (inputEl) inputEl.value = "";
      // Unlock so spoken yes/no can start; confirm mode owns the next listen.
      releaseVoiceTurnLock();
      return;
    }

    if (inputEl) inputEl.value = "";
    lastUserQuestion = q;
    await askStream(q, { spoken: fromVoice, lang });
  }

  function shouldSpeakTurn(spoken) {
    if (spoken) return true;
    return Boolean(global.BaupassAiUi?.isVoiceReplyEnabled?.());
  }

  function cleanSpeakText(text, spoken) {
    const raw = String(text || "").trim();
    if (!raw) return "";
    const ui = global.BaupassAiUi;
    if (ui?.cleanTextForSpeech) {
      return ui.cleanTextForSpeech(raw, { lang: detectLang(), spoken: Boolean(spoken) }) || raw;
    }
    if (ui?.cleanTextForDisplay) return ui.cleanTextForDisplay(raw) || raw;
    return raw.replace(/\s+/g, " ").trim();
  }

  async function askStream(q, opts) {
    busy = true;
    voiceTurnLock = true;
    handsFreeArmed = false;
    if (els.sendBtn) els.sendBtn.disabled = true;
    if (els.micBtn) els.micBtn.disabled = true;
    appendMsg("user", q);
    const bot = appendMsg("bot", "");
    setBotText(bot, t("thinking"));
    appendStatus(t("thinking"));
    updateExpandHref();

    const spoken = Boolean(opts.spoken);
    const wantSpeak = shouldSpeakTurn(spoken);
    let streamed = "";
    let meta = {};
    let pendingSpeech = null;
    let relistenAfter = false;
    let confirmAfter = false;
    const optLang = String(opts?.lang || "").slice(0, 2).toLowerCase();
    if (optLang && SYSTEM_LANGS.includes(optLang)) applyDetectedLang(optLang);
    const lang = detectLang();
    try {
      await ensureSession();
      const res = await fetch("/api/ai/query/stream", {
        method: "POST",
        credentials: "include",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          question: q,
          company_id: readCompanyId(),
          agent_id: "operations",
          session_id: sessionId || undefined,
          lang,
          use_agent: true,
          use_tools: true,
          spoken,
          allow_sensitive: Boolean(opts.allowSensitive),
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const msg = err.hint || err.error || t("errGeneric");
        finalizeBotBody(bot, msg);
        removeStatus();
        attachAnswerToolbar(bot, msg);
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() || "";
        for (const block of parts) {
          const line = block.split("\n").find((l) => l.startsWith("data:"));
          if (!line) continue;
          let payload;
          try {
            payload = JSON.parse(line.slice(5).trim());
          } catch {
            continue;
          }
          if (payload.type === "tool_start") {
            appendStatus(`${t("tools")}: ${payload.tool}…`);
          }
          if (payload.type === "tool_done") {
            appendStatus(`${payload.tool} ✓`);
          }
          if (payload.type === "status") {
            appendStatus(payload.text || "");
          }
          if (payload.type === "answer_start") {
            if (!streamed) setBotText(bot, "");
            if (wantSpeak) {
              try { global.BaupassAiUi?.markTtsPreparing?.(); } catch { /* ignore */ }
            }
          }
          if (payload.type === "answer_reset") {
            streamed = "";
            setBotText(bot, "");
          }
          if (payload.type === "chunk") {
            streamed += payload.text || "";
            setBotText(bot, streamed);
            els.log.scrollTop = els.log.scrollHeight;
            if (wantSpeak && streamed) {
              try {
                global.BaupassAiUi?.tryLockTtsPrefetch?.(streamed, lang, {
                  spoken: true,
                  authHeaders: () => authHeaders(),
                });
              } catch {
                /* ignore */
              }
            }
          }
          if (payload.type === "done") {
            meta = payload;
            if (payload.answer && !streamed) {
              streamed = payload.answer;
              setBotText(bot, streamed);
            }
            if (wantSpeak && streamed && !pendingSpeech && meta.ok !== false) {
              const speakText = cleanSpeakText(streamed, spoken);
              if (speakText) {
                pendingSpeech = global.BaupassAiUi?.speakReply?.(speakText, lang, {
                  spoken: true,
                  authHeaders: () => authHeaders(),
                }) || null;
              }
            }
          }
          if (payload.type === "error") {
            setBotText(bot, payload.hint || payload.error || t("errGeneric"));
          }
        }
      }
      removeStatus();
      if (!getBotPlainText(bot) && !streamed) streamed = "—";
      const answerPlain = finalizeBotBody(bot, streamed || getBotPlainText(bot) || "—");
      attachActionUi(bot, meta);
      attachAnswerMeta(bot, meta);
      attachAnswerToolbar(bot, answerPlain);
      await loadPendingProposals();

      if (wantSpeak && answerPlain && answerPlain !== "—" && meta.ok !== false) {
        handsFreeArmed = (isAmbientEnabled() || isHandsFreeEnabled()) && !hasPendingConfirmCard();
        if (!pendingSpeech) {
          const speakText = cleanSpeakText(answerPlain, spoken);
          pendingSpeech = global.BaupassAiUi?.speakReply?.(speakText, lang, {
            spoken: true,
            authHeaders: () => authHeaders(),
          }) || null;
        }
        try {
          await pendingSpeech;
        } catch {
          /* TTS best-effort */
        }
        if (hasPendingConfirmCard()) {
          confirmAfter = true;
        } else if (isAmbientEnabled() || isHandsFreeEnabled()) {
          relistenAfter = true;
        }
      } else if (hasPendingConfirmCard()) {
        confirmAfter = true;
      } else if (isAmbientEnabled() || isHandsFreeEnabled()) {
        relistenAfter = true;
      }
    } catch (e) {
      removeStatus();
      const msg = e.message || t("errGeneric");
      finalizeBotBody(bot, msg);
      attachAnswerToolbar(bot, msg);
      if (isAmbientEnabled() || isHandsFreeEnabled()) relistenAfter = true;
    } finally {
      busy = false;
      releaseVoiceTurnLock();
      if (els.sendBtn) els.sendBtn.disabled = false;
      if (els.micBtn && voiceReady) els.micBtn.disabled = false;
      syncConversationChrome();
      if (open) els.input?.focus?.();
      // Only after unlock: one listen for the next full utterance.
      if (confirmAfter) {
        maybeSpeakConfirmPrompt();
      } else if (relistenAfter && !hasPendingConfirmCard()) {
        scheduleHandsFreeListen({ delayMs: 900 });
      }
    }
  }

  function appendStatusBot(text) {
    // Compact system line — no follow-up composer / icon toolbar clutter.
    clearEmpty();
    const div = document.createElement("div");
    div.className = "aio-msg aio-msg-bot aio-msg-status-bot";
    const label = document.createElement("div");
    label.className = "aio-msg-bot-label";
    label.textContent = t("botLabel");
    const body = document.createElement("div");
    body.className = "aio-msg-body";
    body.textContent = text || "";
    div.appendChild(label);
    div.appendChild(body);
    els.log.appendChild(div);
    els.log.scrollTop = els.log.scrollHeight;
    syncConversationChrome();
    return div;
  }

  function actionLabel(a) {
    const lang = detectLang();
    const pack = a?.labels && typeof a.labels === "object" ? a.labels : null;
    if (pack && pack[lang]) return String(pack[lang]);
    const camel = `label${lang.charAt(0).toUpperCase()}${lang.slice(1)}`;
    if (a && a[camel]) return String(a[camel]);
    if (lang === "de") return a.labelDe || a.labelEn || a.label || a.action || a.id || t("open");
    if (lang === "ar") return a.labelAr || a.labelEn || a.labelDe || a.label || a.action || a.id || t("open");
    return a.labelEn || a.labelDe || a.label || a.action || a.id || t("open");
  }

  function uniqStrings(list) {
    const out = [];
    const seen = new Set();
    (list || []).forEach((item) => {
      const s = String(item || "").trim();
      if (!s || seen.has(s)) return;
      seen.add(s);
      out.push(s);
    });
    return out;
  }

  function actionDedupeKey(a) {
    if (!a || typeof a !== "object") return "";
    return [
      String(a.type || "").trim(),
      String(a.action || "").trim(),
      String(a.url || "").trim(),
      String(a.tab || "").trim(),
      String(a.prompt || a.promptDe || a.promptEn || a.promptAr || "").trim(),
      actionLabel(a),
    ].join("|");
  }

  function attachAnswerMeta(botEl, meta) {
    if (!botEl || !meta || typeof meta !== "object") return;
    if (botEl.querySelector(".aio-msg-meta")) return;
    const tools = uniqStrings(meta.toolsUsed);
    const sources = uniqStrings(meta.sources);
    // Avoid "Tools: X | Quellen: X" when both are the same list.
    const sourcesUnique = sources.filter((s) => !tools.includes(s));
    const parts = [];
    if (tools.length) parts.push(`${t("tools")}: ${tools.join(", ")}`);
    if (sourcesUnique.length) parts.push(`${t("sources")}: ${sourcesUnique.join(" · ")}`);
    if (!parts.length) return;
    const m = document.createElement("div");
    m.className = "aio-msg-meta";
    m.textContent = parts.join(" | ");
    botEl.appendChild(m);
  }

  function attachActionUi(botEl, meta) {
    const rawActions = [].concat(meta.suggestedActions || [], meta.actions || []);
    const actions = [];
    const seenNav = new Set();
    rawActions.forEach((a) => {
      const key = actionDedupeKey(a);
      if (!key || seenNav.has(key)) return;
      seenNav.add(key);
      actions.push(a);
    });
    const staged = meta.stagedProposals || [];
    const wrap = document.createElement("div");
    wrap.className = "aio-actions-row";
    const seenWrite = new Set();

    // Prefer staged proposals (already in DB) — show confirm cards immediately.
    staged.forEach((p) => {
      if (!p?.id) return;
      seenWrite.add(String(p.action || ""));
      appendConfirmCard({
        title: t("confirmTitle"),
        body: `${p.action || ""}\n${p.rationale || t("confirmHint")}`,
        proposalId: p.id,
        onApprove: async () => {
          maybeNavigateAfterAction(p.action, p.params || {});
        },
      });
    });

    actions.forEach((a) => {
      if (!a || typeof a !== "object") return;
      const type = String(a.type || "").trim();
      const prompt = String(a.prompt || a.promptDe || a.promptEn || a.promptAr || "").trim();
      const isWrite = type === "execute" || WRITE_ACTIONS.has(String(a.action || ""));
      if (isWrite) {
        const key = String(a.action || "");
        if (seenWrite.has(key)) return;
        seenWrite.add(key);
        // Real task: show confirmation card immediately (no extra click).
        appendConfirmCard({
          title: t("confirmTitle"),
          body: `${t("confirmHint")}\n\n${actionLabel(a)}`,
          onApprove: () => runWriteAction(a),
          onReject: () => appendStatusBot(t("rejected")),
        });
        return;
      }
      if (type === "ui_pilot") {
        // Auto-run allowlisted UI pilot (tab click / page open).
        runUiPilotAction(a);
        return;
      }
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "aio-btn";
      btn.textContent = actionLabel(a);
      if (type === "prompt" || (prompt && !a.url && !a.tab && !a.action)) {
        btn.addEventListener("click", () => {
          if (!prompt) return;
          submitQuestion(prompt);
        });
      } else {
        btn.addEventListener("click", () => runNavigateAction(a));
      }
      wrap.appendChild(btn);
    });

    if (wrap.childNodes.length) botEl.appendChild(wrap);
  }


  function runUiPilotAction(a) {
    const selector = String(a.selector || "").trim();
    const url = String(a.url || "").trim();
    const tab = String(a.tab || "").trim();
    let clicked = false;
    if (selector) {
      try {
        const el = document.querySelector(selector);
        if (el && typeof el.click === "function") {
          el.click();
          clicked = true;
        }
      } catch {
        /* ignore */
      }
    }
    global.dispatchEvent(new CustomEvent("baupass-ai-ui-pilot", {
      detail: {
        target: a.target || "",
        tab,
        url,
        selector,
        focus: a.focus || null,
        clicked,
      },
    }));
    if (!clicked) {
      runNavigateAction(a);
    }
    appendStatusBot(t("uiPilotDone") || actionLabel(a));
  }

  function runNavigateAction(a) {
    const url = String(a.url || "").trim();
    const tab = String(a.tab || "").trim();
    const detail = {
      tab: tab || inferTabFromUrl(url),
      url,
      focus: a.focus || null,
      einsatzplan: /einsatzplan=1|focus=deployment|deployment/i.test(url) || a.focus === "deployment",
      label: actionLabel(a),
    };
    global.dispatchEvent(new CustomEvent("baupass-ai-navigate", { detail }));
    if (detail.tab && /admin-v2/i.test(location.pathname)) {
      // local handler in admin-v2 will switch tabs
    } else if (url) {
      const abs = url.startsWith("http") ? url : url;
      if (/admin-v2|enterprise-hub|ops-command|contracts|docs/i.test(abs)) {
        location.href = abs;
      } else {
        global.open(abs, "_blank", "noopener");
      }
    }
  }

  function inferTabFromUrl(url) {
    if (!url) return "";
    try {
      const u = new URL(url, location.origin);
      return u.searchParams.get("tab") || "";
    } catch {
      return "";
    }
  }

  async function runWriteAction(a) {
    const companyId = readCompanyId();
    const action = String(a.action || "").trim();
    let params = a.params && typeof a.params === "object" ? { ...a.params } : {};
    if (!action) return;
    if (action === "confirm_send_deployment_month") {
      params.user_confirmed = true;
    }
    try {
      const proposed = await apiJson("/api/ai/actions/propose", {
        method: "POST",
        body: {
          company_id: companyId,
          action,
          params,
          rationale: actionLabel(a),
          risk: a.risk || (action.includes("deployment") ? "high" : "medium"),
        },
      });
      if (!proposed.ok || !proposed.proposal?.id) {
        // Fallback: execute only after explicit UI confirm already happened
        const exec = await apiJson("/api/ai/actions/execute", {
          method: "POST",
          body: {
            company_id: companyId,
            action,
            params,
            briefing_text: a.briefingText || params.text || "",
          },
        });
        if (exec.ok && action === "export_ops_snapshot" && exec.content) {
          downloadTextFile(exec.filename || "ops-snapshot.md", String(exec.content));
        }
        appendStatusBot(exec.ok ? t("approved") : (exec.hint || exec.error || t("errGeneric")));
        maybeNavigateAfterAction(action, params);
        return;
      }
      const approved = await apiJson("/api/ai/actions/approve", {
        method: "POST",
        body: {
          company_id: companyId,
          proposal_id: proposed.proposal.id,
        },
      });
      const exec = approved.execution || approved;
      const ok = approved.ok || approved.status === "executed" || exec.ok;
      let detail = "";
      if (ok && action === "prepare_deployment_month") {
        detail = ` ${exec.year || ""}/${exec.month || ""} · workers ${exec.workersTouched ?? "—"}`;
      }
      if (ok && action === "confirm_send_deployment_month") {
        detail = ` sent=${exec.sent ?? "—"} failed=${exec.failed ?? "—"}`;
      }
      if (ok && action === "notify_worker") {
        detail = ` push=${exec.pushSent ?? "—"}`;
      }
      if (ok && action === "export_ops_snapshot" && exec.content) {
        downloadTextFile(exec.filename || "ops-snapshot.md", String(exec.content));
        detail = " markdown";
      }
      appendStatusBot(ok ? `${t("approved")}${detail}` : (approved.hint || approved.error || exec.error || t("errGeneric")));
      maybeNavigateAfterAction(action, params);
    } catch (e) {
      appendStatusBot(e.message || t("errGeneric"));
    }
  }

  function downloadTextFile(filename, text) {
    try {
      const blob = new Blob([String(text || "")], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = String(filename || "ops-snapshot.md");
      document.body.appendChild(a);
      a.click();
      a.remove();
      global.setTimeout(() => URL.revokeObjectURL(url), 1500);
    } catch {
      /* ignore */
    }
  }

  function maybeNavigateAfterAction(action, params) {
    if (action === "notify_worker" && params.worker_id) {
      global.dispatchEvent(new CustomEvent("baupass-ai-navigate", {
        detail: { tab: "workers", workerId: params.worker_id },
      }));
    }
    if (/leave/i.test(action)) {
      global.dispatchEvent(new CustomEvent("baupass-ai-navigate", {
        detail: { tab: "inbox" },
      }));
    }
    if (/deployment/i.test(action)) {
      global.dispatchEvent(new CustomEvent("baupass-ai-navigate", {
        detail: { tab: "workers", einsatzplan: true, focus: "deployment" },
      }));
    }
    if (/remind_expired|document/i.test(action)) {
      global.dispatchEvent(new CustomEvent("baupass-ai-navigate", {
        detail: { tab: "workers" },
      }));
    }
    if (/security/i.test(action)) {
      global.dispatchEvent(new CustomEvent("baupass-ai-navigate", {
        detail: { tab: "overview" },
      }));
    }
    if (/late|broadcast/i.test(action)) {
      global.dispatchEvent(new CustomEvent("baupass-ai-navigate", {
        detail: { tab: "access" },
      }));
    }
  }

  function resumeAmbientAfterConfirm() {
    confirmVoiceAsked = false;
    confirmVoiceMode = false;
    syncFabListeningState(false);
    if (isAmbientEnabled() || isHandsFreeEnabled()) {
      scheduleHandsFreeListen();
    }
  }

  function appendConfirmCard(opts) {
    clearEmpty();
    if (!open) setOpen(true);
    // Never talk over a confirmation decision; pause hands-free until resolved.
    handsFreeArmed = false;
    syncFabListeningState(false);
    if (handsFreeTimer) {
      global.clearTimeout(handsFreeTimer);
      handsFreeTimer = null;
    }
    try {
      global.BaupassAiUi?.stopSpeaking?.();
      global.BaupassAiUi?.stopVoiceCapture?.("aioOperatorInput");
    } catch {
      /* ignore */
    }
    const card = document.createElement("div");
    card.className = "aio-card";
    card.innerHTML = `
      <h3>${escapeHtml(opts.title || t("confirmTitle"))}</h3>
      <p>${escapeHtml(opts.body || t("confirmHint"))}</p>
      <div class="aio-card-actions">
        <button type="button" class="aio-btn aio-btn-primary" data-act="ok">${escapeHtml(opts.approveLabel || t("approve"))}</button>
        <button type="button" class="aio-btn aio-btn-danger" data-act="no">${escapeHtml(opts.rejectLabel || t("reject"))}</button>
      </div>
    `;
    const ok = card.querySelector('[data-act="ok"]');
    const no = card.querySelector('[data-act="no"]');
    ok.addEventListener("click", async () => {
      ok.disabled = true;
      no.disabled = true;
      try {
        if (opts.proposalId) {
          const res = await apiJson("/api/ai/actions/approve", {
            method: "POST",
            body: { company_id: readCompanyId(), proposal_id: opts.proposalId },
          });
          const exec = res.execution || {};
          const ok = res.ok || res.status === "executed" || exec.ok;
          appendStatusBot(ok ? t("approved") : (res.hint || res.error || exec.error || t("errGeneric")));
          if (ok && typeof opts.onApprove === "function") await opts.onApprove(res);
        } else if (typeof opts.onApprove === "function") {
          await opts.onApprove();
        }
      } catch (e) {
        appendStatusBot(e.message || t("errGeneric"));
      } finally {
        card.remove();
        resumeAmbientAfterConfirm();
      }
    });
    no.addEventListener("click", async () => {
      ok.disabled = true;
      no.disabled = true;
      try {
        if (opts.proposalId) {
          await apiJson("/api/ai/actions/reject", {
            method: "POST",
            body: { company_id: readCompanyId(), proposal_id: opts.proposalId },
          });
        }
        if (typeof opts.onReject === "function") await opts.onReject();
        else appendStatusBot(t("rejected"));
      } catch (e) {
        appendStatusBot(e.message || t("errGeneric"));
      } finally {
        card.remove();
        resumeAmbientAfterConfirm();
      }
    });
    els.log.appendChild(card);
    els.log.scrollTop = els.log.scrollHeight;
    // Ask verbally whether to execute — after a short beat so the card is visible.
    global.setTimeout(() => maybeSpeakConfirmPrompt(), 350);
  }

  async function loadPendingProposals() {
    const companyId = readCompanyId();
    if (!companyId || !readToken()) return;
    try {
      const data = await apiJson(
        `/api/ai/actions/proposals?company_id=${encodeURIComponent(companyId)}&status=pending`,
        { method: "GET" }
      );
      const proposals = data.proposals || [];
      const existing = new Set(
        [...els.log.querySelectorAll("[data-proposal-id]")].map((n) => n.getAttribute("data-proposal-id"))
      );
      proposals.slice(0, 5).forEach((p) => {
        if (!p?.id || existing.has(p.id)) return;
        const cardHost = document.createElement("div");
        cardHost.dataset.proposalId = p.id;
        els.log.appendChild(cardHost);
        appendConfirmCard({
          title: t("confirmTitle"),
          body: `${p.action || ""}\n${p.rationale || t("confirmHint")}`,
          proposalId: p.id,
        });
        cardHost.remove();
      });
    } catch {
      /* optional */
    }
  }

  async function apiJson(path, opts) {
    const method = opts.method || "GET";
    const res = await fetch(path, {
      method,
      credentials: "include",
      headers: authHeaders(method === "GET" ? {} : { "Content-Type": "application/json" }),
      body: opts.body != null ? JSON.stringify(opts.body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = new Error(data.hint || data.error || t("errGeneric"));
      err.payload = data;
      throw err;
    }
    return data;
  }

  const api = {
    version: VERSION,
    __boot: true,
    init: mount,
    open: () => { mount(); setOpen(true); },
    close: () => setOpen(false),
    show: () => { visibleForced = true; mount(); refreshVisibility(); },
    hide: () => { visibleForced = false; refreshVisibility(); },
    ask: (q) => { mount(); setOpen(true); return submitQuestion(q); },
    refresh: () => { refreshVisibility(); probeSessionRole().catch(() => {}); },
    /** Prefetch Whisper/TTS stack without opening the drawer. */
    prepareVoice: () => ensureVoiceStack().then(() => { voiceReady = true; return true; }),
    isVoiceReady: () => Boolean(voiceReady && global.BaupassAiUi?.bindVoiceInput),
    /** Opt-in welcome TTS (requires BAUPASS_AI_OPERATOR_WELCOME=1). */
    welcome: () => maybeSpeakWelcome(),
  };

  global.BaupassAiOperator = api;

  global.addEventListener?.("baupass-lang-sync", () => {
    try {
      refreshCopy();
      if (voiceBound && global.BaupassAiUi?.refreshComposerLabels) {
        global.BaupassAiUi.refreshComposerLabels(operatorVoiceOptions());
      }
    } catch {
      /* ignore */
    }
  });
  global.addEventListener?.("storage", (event) => {
    const k = String(event?.key || "");
    if (!k || !/(lang|ui-lang)$/i.test(k)) return;
    try { refreshCopy(); } catch { /* ignore */ }
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})(typeof window !== "undefined" ? window : globalThis);
