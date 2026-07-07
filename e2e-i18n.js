/**
 * E2E security panel i18n (admin + worker).
 */
(function (global) {
  const STRINGS = {
    de: {
      e2eSecurityEyebrow: "Verschlüsselung",
      e2eSecurityTitle: "E2E-Sicherheit",
      e2eSecuritySubtitle: "Private Schlüssel werden nur in dieser App erzeugt und verbleiben auf diesem Gerät. Der Server speichert ausschließlich Public Keys.",
      e2eSecurityBadgeLocal: "Private Key: nur dieses Gerät",
      e2eSecurityBadgeAlgo: "AES-256-GCM + X25519",
      e2eSecurityBadgeServer: "Server: nur Public Key",
      e2eSecurityBtnRecovery: "Recovery-Phrase",
      e2eSecurityBtnRotate: "Schlüssel rotieren",
      e2eSecurityBtnQrExport: "QR-Transfer export",
      e2eSecurityBtnQrImport: "QR-Transfer import",
      e2eSecurityBtnPinSet: "Geräte-PIN setzen",
      e2eSecurityBtnPinUnlock: "PIN entsperren",
      e2eSecurityPinPlaceholder: "Geräte-PIN (mind. 6 Zeichen)",
      e2eSecurityPinHint: "Optional: Zusätzliche Sperre — ohne PIN kann selbst bei Gerätezugriff nicht entschlüsselt werden.",
      e2eSecurityLockLocked: "Gerätesperre aktiv — bitte PIN eingeben und entsperren.",
      e2eSecurityLockUnlocked: "Gerätesperre entsperrt für diese Sitzung.",
      e2eSecurityQrPlaceholder: "Transfer-JSON einfügen…",
      e2eSecurityStatusRotated: "Schlüssel rotiert und Public Key registriert.",
      e2eSecurityStatusImported: "Identität importiert.",
      e2eSecurityStatusPinSet: "Geräte-PIN gesetzt. Bitte entsperren.",
      e2eSecurityStatusPinOk: "PIN korrekt — Schlüssel für diese Sitzung freigegeben.",
      e2eSecurityStatusPinBad: "PIN falsch.",
      e2eSecurityStatusPinShort: "PIN muss mindestens 6 Zeichen haben.",
    },
    en: {
      e2eSecurityEyebrow: "Encryption",
      e2eSecurityTitle: "E2E Security",
      e2eSecuritySubtitle: "Private keys are generated in this app only and stay on this device. The server stores public keys only.",
      e2eSecurityBadgeLocal: "Private key: this device only",
      e2eSecurityBadgeAlgo: "AES-256-GCM + X25519",
      e2eSecurityBadgeServer: "Server: public key only",
      e2eSecurityBtnRecovery: "Recovery phrase",
      e2eSecurityBtnRotate: "Rotate keys",
      e2eSecurityBtnQrExport: "Export QR transfer",
      e2eSecurityBtnQrImport: "Import QR transfer",
      e2eSecurityBtnPinSet: "Set device PIN",
      e2eSecurityBtnPinUnlock: "Unlock PIN",
      e2eSecurityPinPlaceholder: "Device PIN (min. 6 chars)",
      e2eSecurityPinHint: "Optional extra lock — without the PIN, data cannot be decrypted even with device access.",
      e2eSecurityLockLocked: "Device lock active — enter PIN and unlock.",
      e2eSecurityLockUnlocked: "Device lock unlocked for this session.",
      e2eSecurityQrPlaceholder: "Paste transfer JSON…",
      e2eSecurityStatusRotated: "Keys rotated and public key registered.",
      e2eSecurityStatusImported: "Identity imported.",
      e2eSecurityStatusPinSet: "Device PIN set. Please unlock.",
      e2eSecurityStatusPinOk: "PIN correct — keys unlocked for this session.",
      e2eSecurityStatusPinBad: "Incorrect PIN.",
      e2eSecurityStatusPinShort: "PIN must be at least 6 characters.",
    },
    ar: {
      e2eSecurityEyebrow: "التشفير",
      e2eSecurityTitle: "أمان E2E",
      e2eSecuritySubtitle: "يتم إنشاء المفاتيح الخاصة في هذا التطبيق فقط وتبقى على هذا الجهاز. الخادم يخزن المفاتيح العامة فقط.",
      e2eSecurityBadgeLocal: "المفتاح الخاص: هذا الجهاز فقط",
      e2eSecurityBadgeAlgo: "AES-256-GCM + X25519",
      e2eSecurityBadgeServer: "الخادم: مفتاح عام فقط",
      e2eSecurityBtnRecovery: "عبارة الاسترداد",
      e2eSecurityBtnRotate: "تدوير المفاتيح",
      e2eSecurityBtnQrExport: "تصدير QR",
      e2eSecurityBtnQrImport: "استيراد QR",
      e2eSecurityBtnPinSet: "تعيين PIN",
      e2eSecurityBtnPinUnlock: "فتح PIN",
      e2eSecurityPinPlaceholder: "PIN الجهاز (6+ أحرف)",
      e2eSecurityPinHint: "قفل إضافي اختياري — بدون PIN لا يمكن فك التشفير حتى مع الوصول للجهاز.",
      e2eSecurityLockLocked: "قفل الجهاز نشط — أدخل PIN.",
      e2eSecurityLockUnlocked: "تم فتح القفل لهذه الجلسة.",
      e2eSecurityQrPlaceholder: "الصق JSON النقل…",
      e2eSecurityStatusRotated: "تم تدوير المفاتيح وتسجيل المفتاح العام.",
      e2eSecurityStatusImported: "تم استيراد الهوية.",
      e2eSecurityStatusPinSet: "تم تعيين PIN. يرجى الفتح.",
      e2eSecurityStatusPinOk: "PIN صحيح — تم فتح المفاتيح.",
      e2eSecurityStatusPinBad: "PIN غير صحيح.",
      e2eSecurityStatusPinShort: "يجب أن يكون PIN 6 أحرف على الأقل.",
    },
    tr: {
      e2eSecurityEyebrow: "Sifreleme",
      e2eSecurityTitle: "Uctan uca guvenlik",
      e2eSecuritySubtitle: "Ozel anahtarlar yalnizca bu uygulamada uretilir ve bu cihazda kalir. Sunucu yalnizca acik anahtarlari saklar.",
      e2eSecurityBadgeLocal: "Ozel anahtar: yalnizca bu cihaz",
      e2eSecurityBadgeAlgo: "AES-256-GCM + X25519",
      e2eSecurityBadgeServer: "Sunucu: yalnizca acik anahtar",
      e2eSecurityBtnRecovery: "Kurtarma ifadesi",
      e2eSecurityBtnRotate: "Anahtarlari yenile",
      e2eSecurityBtnQrExport: "QR aktar (disa)",
      e2eSecurityBtnQrImport: "QR aktar (ice)",
      e2eSecurityBtnPinSet: "Cihaz PIN ayarla",
      e2eSecurityBtnPinUnlock: "PIN ac",
      e2eSecurityPinPlaceholder: "Cihaz PIN (en az 6)",
      e2eSecurityPinHint: "Istege bagli ek kilit — PIN olmadan cihaz erisimi bile sifre cozemez.",
      e2eSecurityLockLocked: "Cihaz kilidi aktif — PIN girin.",
      e2eSecurityLockUnlocked: "Bu oturum icin kilit acildi.",
      e2eSecurityQrPlaceholder: "Transfer JSON yapistir…",
      e2eSecurityStatusRotated: "Anahtarlar yenilendi ve acik anahtar kaydedildi.",
      e2eSecurityStatusImported: "Kimlik ice aktarildi.",
      e2eSecurityStatusPinSet: "PIN ayarlandi. Lutfen acin.",
      e2eSecurityStatusPinOk: "PIN dogru — anahtarlar acildi.",
      e2eSecurityStatusPinBad: "PIN yanlis.",
      e2eSecurityStatusPinShort: "PIN en az 6 karakter olmali.",
    },
    fr: {
      e2eSecurityEyebrow: "Chiffrement",
      e2eSecurityTitle: "Securite E2E",
      e2eSecuritySubtitle: "Les cles privees sont generees uniquement dans cette app et restent sur cet appareil. Le serveur ne stocke que les cles publiques.",
      e2eSecurityBadgeLocal: "Cle privee : cet appareil seulement",
      e2eSecurityBadgeAlgo: "AES-256-GCM + X25519",
      e2eSecurityBadgeServer: "Serveur : cle publique seulement",
      e2eSecurityBtnRecovery: "Phrase de recuperation",
      e2eSecurityBtnRotate: "Rotation des cles",
      e2eSecurityBtnQrExport: "Exporter QR",
      e2eSecurityBtnQrImport: "Importer QR",
      e2eSecurityBtnPinSet: "Definir PIN appareil",
      e2eSecurityBtnPinUnlock: "Deverrouiller PIN",
      e2eSecurityPinPlaceholder: "PIN appareil (6+ caracteres)",
      e2eSecurityPinHint: "Verrou supplementaire — sans PIN, impossible de dechiffrer meme avec acces a l'appareil.",
      e2eSecurityLockLocked: "Verrou actif — saisissez le PIN.",
      e2eSecurityLockUnlocked: "Verrou ouvert pour cette session.",
      e2eSecurityQrPlaceholder: "Coller le JSON de transfert…",
      e2eSecurityStatusRotated: "Cles rotatees et cle publique enregistree.",
      e2eSecurityStatusImported: "Identite importee.",
      e2eSecurityStatusPinSet: "PIN defini. Veuillez deverrouiller.",
      e2eSecurityStatusPinOk: "PIN correct — cles deverrouillees.",
      e2eSecurityStatusPinBad: "PIN incorrect.",
      e2eSecurityStatusPinShort: "Le PIN doit contenir au moins 6 caracteres.",
    },
    es: {
      e2eSecurityEyebrow: "Cifrado",
      e2eSecurityTitle: "Seguridad E2E",
      e2eSecuritySubtitle: "Las claves privadas se generan solo en esta app y permanecen en este dispositivo. El servidor solo guarda claves publicas.",
      e2eSecurityBadgeLocal: "Clave privada: solo este dispositivo",
      e2eSecurityBadgeAlgo: "AES-256-GCM + X25519",
      e2eSecurityBadgeServer: "Servidor: solo clave publica",
      e2eSecurityBtnRecovery: "Frase de recuperacion",
      e2eSecurityBtnRotate: "Rotar claves",
      e2eSecurityBtnQrExport: "Exportar QR",
      e2eSecurityBtnQrImport: "Importar QR",
      e2eSecurityBtnPinSet: "Definir PIN",
      e2eSecurityBtnPinUnlock: "Desbloquear PIN",
      e2eSecurityPinPlaceholder: "PIN del dispositivo (6+)",
      e2eSecurityPinHint: "Bloqueo extra opcional — sin PIN no se puede descifrar aunque accedan al dispositivo.",
      e2eSecurityLockLocked: "Bloqueo activo — introduzca el PIN.",
      e2eSecurityLockUnlocked: "Desbloqueado para esta sesion.",
      e2eSecurityQrPlaceholder: "Pegar JSON de transferencia…",
      e2eSecurityStatusRotated: "Claves rotadas y clave publica registrada.",
      e2eSecurityStatusImported: "Identidad importada.",
      e2eSecurityStatusPinSet: "PIN definido. Desbloquee.",
      e2eSecurityStatusPinOk: "PIN correcto — claves desbloqueadas.",
      e2eSecurityStatusPinBad: "PIN incorrecto.",
      e2eSecurityStatusPinShort: "El PIN debe tener al menos 6 caracteres.",
    },
    it: {
      e2eSecurityEyebrow: "Crittografia",
      e2eSecurityTitle: "Sicurezza E2E",
      e2eSecuritySubtitle: "Le chiavi private sono generate solo in questa app e restano su questo dispositivo. Il server memorizza solo chiavi pubbliche.",
      e2eSecurityBadgeLocal: "Chiave privata: solo questo dispositivo",
      e2eSecurityBadgeAlgo: "AES-256-GCM + X25519",
      e2eSecurityBadgeServer: "Server: solo chiave pubblica",
      e2eSecurityBtnRecovery: "Frase di recupero",
      e2eSecurityBtnRotate: "Ruota chiavi",
      e2eSecurityBtnQrExport: "Esporta QR",
      e2eSecurityBtnQrImport: "Importa QR",
      e2eSecurityBtnPinSet: "Imposta PIN",
      e2eSecurityBtnPinUnlock: "Sblocca PIN",
      e2eSecurityPinPlaceholder: "PIN dispositivo (6+ caratteri)",
      e2eSecurityPinHint: "Blocco extra opzionale — senza PIN non si puo decifrare neanche con accesso al dispositivo.",
      e2eSecurityLockLocked: "Blocco attivo — inserire PIN.",
      e2eSecurityLockUnlocked: "Sbloccato per questa sessione.",
      e2eSecurityQrPlaceholder: "Incolla JSON trasferimento…",
      e2eSecurityStatusRotated: "Chiavi ruotate e chiave pubblica registrata.",
      e2eSecurityStatusImported: "Identita importata.",
      e2eSecurityStatusPinSet: "PIN impostato. Sbloccare.",
      e2eSecurityStatusPinOk: "PIN corretto — chiavi sbloccate.",
      e2eSecurityStatusPinBad: "PIN errato.",
      e2eSecurityStatusPinShort: "Il PIN deve avere almeno 6 caratteri.",
    },
    pl: {
      e2eSecurityEyebrow: "Szyfrowanie",
      e2eSecurityTitle: "Bezpieczenstwo E2E",
      e2eSecuritySubtitle: "Klucze prywatne sa tworzone tylko w tej aplikacji i pozostaja na tym urzadzeniu. Serwer przechowuje tylko klucze publiczne.",
      e2eSecurityBadgeLocal: "Klucz prywatny: tylko to urzadzenie",
      e2eSecurityBadgeAlgo: "AES-256-GCM + X25519",
      e2eSecurityBadgeServer: "Serwer: tylko klucz publiczny",
      e2eSecurityBtnRecovery: "Fraza odzyskiwania",
      e2eSecurityBtnRotate: "Rotacja kluczy",
      e2eSecurityBtnQrExport: "Eksport QR",
      e2eSecurityBtnQrImport: "Import QR",
      e2eSecurityBtnPinSet: "Ustaw PIN",
      e2eSecurityBtnPinUnlock: "Odblokuj PIN",
      e2eSecurityPinPlaceholder: "PIN urzadzenia (6+ znakow)",
      e2eSecurityPinHint: "Opcjonalna blokada — bez PIN nie da sie odszyfrowac nawet przy dostepie do urzadzenia.",
      e2eSecurityLockLocked: "Blokada aktywna — wpisz PIN.",
      e2eSecurityLockUnlocked: "Odblokowano na te sesje.",
      e2eSecurityQrPlaceholder: "Wklej JSON transferu…",
      e2eSecurityStatusRotated: "Klucze zrotowane i klucz publiczny zapisany.",
      e2eSecurityStatusImported: "Tozsamosc zaimportowana.",
      e2eSecurityStatusPinSet: "PIN ustawiony. Odblokuj.",
      e2eSecurityStatusPinOk: "PIN poprawny — klucze odblokowane.",
      e2eSecurityStatusPinBad: "Niepoprawny PIN.",
      e2eSecurityStatusPinShort: "PIN musi miec co najmniej 6 znakow.",
    },
  };

  function resolveLang(lang) {
    const code = String(
      lang
      || (typeof global.getCurrentLang === "function" && global.getCurrentLang())
      || global.WorkerI18N?.getCurrentLang?.()
      || "de",
    ).slice(0, 2).toLowerCase();
    return Object.prototype.hasOwnProperty.call(STRINGS, code) ? code : "de";
  }

  function t(key, lang) {
    const code = resolveLang(lang);
    return STRINGS[code]?.[key] || STRINGS.de[key] || STRINGS.en[key] || key;
  }

  function applyDom(root, lang) {
    const scope = root || document;
    scope.querySelectorAll("[data-e2e-i18n]").forEach((el) => {
      const key = el.getAttribute("data-e2e-i18n");
      if (!key) return;
      const attr = el.getAttribute("data-e2e-i18n-attr");
      const value = t(key, lang);
      if (attr) {
        attr.split(",").map((part) => part.trim()).filter(Boolean).forEach((name) => {
          el.setAttribute(name, value);
        });
      } else {
        el.textContent = value;
      }
    });
    scope.querySelectorAll("[data-e2e-i18n-placeholder]").forEach((el) => {
      const key = el.getAttribute("data-e2e-i18n-placeholder");
      if (key) el.placeholder = t(key, lang);
    });
  }

  global.E2EI18n = Object.freeze({ t, applyDom, resolveLang, STRINGS });
})(typeof window !== "undefined" ? window : globalThis);
