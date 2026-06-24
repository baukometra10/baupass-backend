import { STRINGS as BASE_STRINGS } from "./i18n-strings.js";
import { EXT_STRINGS } from "./i18n-strings-ext.js";
import { EXTRA_LANG_STRINGS } from "./i18n-strings-langs.js";
import { FEATURE_STRINGS } from "./i18n-features.js";

const LANGS_8 = ["de", "en", "ar", "tr", "fr", "es", "it", "pl"];

function buildLangPack(lang) {
  const base = BASE_STRINGS[lang] || BASE_STRINGS.en || {};
  const ext = EXT_STRINGS[lang] || EXT_STRINGS.en || {};
  const extra = EXTRA_LANG_STRINGS[lang] || {};
  const features = FEATURE_STRINGS[lang] || FEATURE_STRINGS.en || {};
  return { ...base, ...ext, ...extra, ...features };
}

const STRINGS = Object.fromEntries(LANGS_8.map((lang) => [lang, buildLangPack(lang)]));

/** Maps admin-v2 i18n keys → sector-config term keys from /api/platform/sector-config */
const SECTOR_I18N_MAP = {
  "overview.onSite": "overviewOnSite",
  "overview.onSiteKpi": "overviewOnSiteKpi",
  "tools.geofence": "toolsGeofence",
  "deployment.locationPh": "deploymentLocationPh",
  "tools.sitePlaceholder": "toolsSitePlaceholder",
  "deployment.colLocation": "deploymentColLocation",
};

export { STRINGS };

const LANG_KEY = window.WorkPassStorage?.KEYS?.ADMIN_LANG || "workpass-admin-lang";
const SHARED_LANG_KEY = window.WorkPassStorage?.KEYS?.UI_LANG || "workpass-ui-lang";

let sectorTermOverrides = {};

export function setSectorTermOverrides(apiTerms = {}) {
  const next = {};
  for (const [i18nKey, sectorKey] of Object.entries(SECTOR_I18N_MAP)) {
    const value = String(apiTerms[sectorKey] || "").trim();
    if (value) next[i18nKey] = value;
  }
  sectorTermOverrides = next;
}

export function clearSectorTermOverrides() {
  sectorTermOverrides = {};
}

export function getLang() {
  const code =
    localStorage.getItem(LANG_KEY) || localStorage.getItem(SHARED_LANG_KEY) || "de";
  return LANGS_8.includes(code) ? code : "de";
}

export function setLang(code) {
  if (!LANGS_8.includes(code)) return;
  localStorage.setItem(LANG_KEY, code);
  localStorage.setItem(SHARED_LANG_KEY, code);
  applyI18n();
  window.dispatchEvent(new CustomEvent("baupass-admin-lang", { detail: { lang: code } }));
}

/** Interpolate {name} placeholders in translated strings. */
export function t(key, vars = {}) {
  const lang = getLang();
  let text =
    sectorTermOverrides[key]
    || STRINGS[lang]?.[key]
    || (lang !== "de" && lang !== "ar" ? STRINGS.en?.[key] : undefined)
    || STRINGS.de[key]
    || STRINGS.en[key]
    || key;
  for (const [k, v] of Object.entries(vars)) {
    text = text.replaceAll(`{${k}}`, String(v ?? ""));
  }
  return text;
}

export function featureLabel(featureId, fallback = "") {
  const key = `feature.${String(featureId || "").trim()}`;
  const val = t(key);
  return val !== key ? val : (fallback || featureId || "");
}

export function widgetLabel(widget) {
  if (widget?.labelKey) return t(widget.labelKey);
  return widget?.label || widget?.id || "";
}

export function widgetValue(widget) {
  if (widget?.valueKey) return t(widget.valueKey);
  return widget?.value ?? "—";
}

export function widgetDetail(widget) {
  if (widget?.detailKey) return t(widget.detailKey, widget.detailVars || {});
  return widget?.detail || "";
}

export function moduleAlertMessage(alert) {
  const label = featureLabel(alert?.featureId, alert?.label);
  const days = alert?.daysSinceUse ?? 30;
  if (!alert?.lastUsedAt) return t("analytics.moduleUnusedDays", { label, days });
  return t("analytics.moduleLastUsedDays", { label, days });
}

export function formatForecastSummary(fc = {}) {
  const day = typeof fc.weekday === "number" ? t(`weekday.${fc.weekday}`) : (fc.weekdayLabel || "");
  return t("overview.forecastSummary", {
    day,
    date: fc.date || "",
    onSite: fc.expectedOnSite ?? 0,
    total: fc.totalActive ?? 0,
    absent: fc.expectedAbsent ?? 0,
  });
}

function applyAttr(el, attr, key) {
  const val = t(key);
  if (attr === "placeholder") el.placeholder = val;
  else if (attr === "title") el.title = val;
  else el.setAttribute(attr, val);
}

export function applyI18n() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (key) el.textContent = t(key);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    applyAttr(el, "placeholder", el.getAttribute("data-i18n-placeholder"));
  });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => {
    applyAttr(el, "title", el.getAttribute("data-i18n-title"));
  });
  document.querySelectorAll("select option[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (key) el.textContent = t(key);
  });
  document.querySelectorAll("[data-lang-select]").forEach((sel) => {
    if (sel.value !== getLang()) sel.value = getLang();
  });
  const lang = getLang();
  document.documentElement.lang = lang === "ar" ? "ar" : lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
}
