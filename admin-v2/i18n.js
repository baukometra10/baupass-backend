import { STRINGS as BASE_STRINGS } from "./i18n-strings.js";
import { EXT_STRINGS } from "./i18n-strings-ext.js";

const STRINGS = Object.fromEntries(
  ["de", "en", "ar"].map((lang) => [lang, { ...BASE_STRINGS[lang], ...EXT_STRINGS[lang] }]),
);

export { STRINGS };

const LANG_KEY = "baupass-admin-v2-lang";
const SHARED_LANG_KEY = "baupass-ui-lang";

export function getLang() {
  const code =
    localStorage.getItem(LANG_KEY) || localStorage.getItem(SHARED_LANG_KEY) || "de";
  return STRINGS[code] ? code : "de";
}

export function setLang(code) {
  if (!STRINGS[code]) return;
  localStorage.setItem(LANG_KEY, code);
  localStorage.setItem(SHARED_LANG_KEY, code);
  applyI18n();
  window.dispatchEvent(new CustomEvent("baupass-admin-lang", { detail: { lang: code } }));
}

/** Interpolate {name} placeholders in translated strings. */
export function t(key, vars = {}) {
  const lang = getLang();
  let text = STRINGS[lang]?.[key] || STRINGS.de[key] || STRINGS.en[key] || key;
  for (const [k, v] of Object.entries(vars)) {
    text = text.replaceAll(`{${k}}`, String(v ?? ""));
  }
  return text;
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
