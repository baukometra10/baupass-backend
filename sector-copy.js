/**
 * Client rewriter for operating-sector vocabulary.
 * Mirrors backend/app/platform/ai/sector_copy.py — skip construction (source dialect).
 */
(function initBaupassSectorCopy(global) {
  function titleCase(value) {
    const text = String(value || "");
    if (!text) return text;
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  function applySectorText(text, opts) {
    if (!text) return text;
    const options = opts && typeof opts === "object" ? opts : {};
    let out = String(text);
    const lang = String(options.lang || "de").slice(0, 2);
    const workers = String(options.workers || "").trim();
    const site = String(options.site || "").trim();
    const gate = String(options.gate || "").trim();
    const singular = String(options.workerSingular || workers).trim() || workers;
    const company = String(options.company || "").trim();
    const sites = String(options.sites || site).trim() || site;
    if (!site && !workers && !company) return out;

    if (lang === "de") {
      out = out.replaceAll("Baustellenkontrolle", site + "-Kontrolle");
      out = out.replaceAll("Baustellen-Ausweis", site + "-Ausweis");
      out = out.replaceAll("Baustellenordnung", site + "ordnung");
      out = out.replaceAll("Auf allen Baustellen", "In allen " + sites);
      out = out.replaceAll("auf allen Baustellen", "in allen " + sites);
      out = out.replaceAll("Auf der Baustelle", "Am " + site);
      out = out.replaceAll("auf der Baustelle", "am " + site);
      out = out.replaceAll("Auf Baustelle", "Am " + site);
      out = out.replaceAll("auf Baustelle", "am " + site);
      if (company) {
        out = out.replaceAll("Bauunternehmen", company);
        out = out.replaceAll("Baufirma", company);
        out = out.replaceAll("Baubetrieb", company);
      }
      out = out.replaceAll("Bauleitung", "Einsatzleitung");
      out = out.replaceAll("Baustellen", sites).replaceAll("Baustelle", site);
      if (singular) out = out.replaceAll("Mitarbeiter-App", singular + "-App");
      if (workers) out = out.replaceAll("Mitarbeiter", workers);
      out = out.replaceAll("vor Ort", "am " + site);
      if (gate) {
        out = out.replaceAll("Drehkreuz / Tor", gate).replaceAll("Drehkreuz", gate);
        out = out.replaceAll("am Tor", "am " + gate).replaceAll("Am Tor", "Am " + gate);
      }
    } else if (lang === "en") {
      if (company) {
        const plural = company.endsWith("s") ? company : company + "s";
        out = out.replaceAll("construction companies", plural);
        out = out.replaceAll("Construction companies", titleCase(plural));
        out = out.replaceAll("construction company", company);
        out = out.replaceAll("Construction company", titleCase(company));
      }
      out = out.replaceAll("construction sites", sites);
      out = out.replaceAll("Construction sites", titleCase(sites));
      out = out.replaceAll("construction site", site).replaceAll("Construction site", titleCase(site));
      out = out.replaceAll("on site", "at " + site).replaceAll("On site", "At " + site);
      if (workers) {
        out = out.replaceAll("Workers", titleCase(workers));
        out = out.replaceAll("workers", workers);
      }
      if (singular) {
        out = out.replaceAll("Worker", titleCase(singular));
        out = out.replaceAll("worker", singular);
      }
    } else if (lang === "ar") {
      if (company) {
        out = out.replaceAll("شركة إنشاءات باوشتلا", company);
        out = out.replaceAll("شركات البناء", company);
        out = out.replaceAll("شركة إنشاءات", company);
        out = out.replaceAll("شركة بناء", company);
      }
      out = out.replaceAll("مواقع البناء", sites);
      out = out.replaceAll("موقع البناء", site);
      out = out.replaceAll("باوشتلا", site);
      out = out.replaceAll("في الموقع", "في " + site).replaceAll("الموقع", site);
      if (workers) out = out.replaceAll("العمال", workers).replaceAll("عمال", workers);
    } else if (lang === "tr") {
      if (company) {
        out = out.replaceAll("inşaat firmaları", company);
        out = out.replaceAll("inşaat firması", company);
        out = out.replaceAll("İnşaat Firması", titleCase(company));
      }
      out = out.replaceAll("sahada", site + " üzerinde").replaceAll("Sahada", site + " üzerinde");
      out = out.replaceAll("şantiyede", site + " üzerinde");
      out = out.replaceAll("şantiye", site);
      if (workers) out = out.replaceAll("çalışanlar", workers);
    } else if (lang === "pl") {
      if (company) {
        out = out.replaceAll("firmom budowlanym", company);
        out = out.replaceAll("firma budowlana", company);
        out = out.replaceAll("firmę budowlaną", company);
      }
      out = out.replaceAll("na budowie", "na " + site).replaceAll("placu budowy", site);
      out = out.replaceAll("budowie", site);
      if (workers) out = out.replaceAll("pracownicy", workers);
    } else if (lang === "es") {
      if (company) {
        out = out.replaceAll("empresas de construcción", company);
        out = out.replaceAll("empresa de construcción", company);
      }
      out = out.replaceAll("en la obra", "en " + site).replaceAll("en obra", "en " + site);
      out = out.replaceAll("obra", site);
      if (workers) out = out.replaceAll("trabajadores", workers);
    } else if (lang === "it") {
      if (company) {
        out = out.replaceAll("imprese edili", company);
        out = out.replaceAll("impresa edile", company);
      }
      out = out.replaceAll("in cantiere", "in " + site).replaceAll("cantiere", site);
      if (workers) out = out.replaceAll("lavoratori", workers);
    } else if (lang === "fr") {
      if (company) {
        out = out.replaceAll("entreprises de construction", company);
        out = out.replaceAll("entreprise de construction", company);
      }
      out = out.replaceAll("sur chantier", "sur " + site).replaceAll("Sur chantier", "Sur " + site);
      out = out.replaceAll("chantier", site);
      out = out.replaceAll("sur site", "sur " + site).replaceAll("Sur site", "Sur " + site);
      if (workers) out = out.replaceAll("collaborateurs", workers);
    }
    return out;
  }

  function resolveContext() {
    if (global.__baupassSector && global.__baupassSector.sector) {
      return {
        sector: String(global.__baupassSector.sector || "construction"),
        terms: global.__baupassSector.terms || {},
      };
    }
    if (global.__adminV2Sector) {
      return {
        sector: String(global.__adminV2Sector || "construction"),
        terms: global.__adminV2SectorTerms || {},
      };
    }
    if (global.__workerOperatingSector || global.__workerSectorTerms) {
      return {
        sector: String(global.__workerOperatingSector || "construction"),
        terms: global.__workerSectorTerms || {},
      };
    }
    return { sector: "construction", terms: {} };
  }

  function applyFromWindow(text, lang) {
    if (!text) return text;
    const ctx = resolveContext();
    if (!ctx.sector || ctx.sector === "construction") return text;
    const terms = ctx.terms || {};
    return applySectorText(text, {
      lang: lang || "de",
      workers: terms.termWorkers || "",
      site: terms.termSite || "",
      gate: terms.termGate || "",
      workerSingular: terms.termWorker || "",
      company: terms.termCompany || "",
      sites: terms.termSites || "",
    });
  }

  function loadConfig(options) {
    if (global.WorkPassStorage?.isSupportAssistQuietMode?.()) return Promise.resolve(null);
    const opts = options && typeof options === "object" ? options : {};
    const lang = String(opts.lang || "de").slice(0, 2);
    const companyId = String(opts.companyId || "").trim();
    let url = "/api/platform/sector-config?lang=" + encodeURIComponent(lang);
    if (companyId) url += "&company_id=" + encodeURIComponent(companyId);
    const request = typeof opts.fetchJson === "function"
      ? Promise.resolve(opts.fetchJson(url))
      : fetch(url, { credentials: "include" }).then((res) => (res.ok ? res.json() : null));
    return Promise.resolve(request)
      .then((data) => {
        if (data && data.sector) {
          global.__baupassSector = {
            sector: data.sector,
            terms: data.terms || {},
            label: data.label || "",
          };
        }
        return data || null;
      })
      .catch(() => null);
  }

  global.BaupassSectorCopy = {
    applySectorText,
    applyFromWindow,
    resolveContext,
    loadConfig,
  };
})(typeof window !== "undefined" ? window : globalThis);
