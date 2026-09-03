"use strict";

let _t = {};
let _lang = localStorage.getItem("lang") || "en";

async function loadLanguage(code) {
  try {
    const res = await fetch(`/static/i18n/${code}.json?v=${Date.now()}`);
    if (!res.ok) throw new Error("Not found");
    const data = await res.json();
    _t = data;
    _lang = code;
    localStorage.setItem("lang", code);

    const isRTL = String(data.__rtl || "").toLowerCase() === "true";
    document.documentElement.setAttribute("dir", isRTL ? "rtl" : "ltr");
    document.documentElement.lang = code;

    applyTranslations();
    document.dispatchEvent(new CustomEvent("languageChanged", { detail: { code } }));
  } catch (e) {
    // Fall back silently to whatever translations are already loaded.
  }
}

function t(key, fallback) {
  return _t[key] || fallback || key;
}

function applyTranslations(container = document) {
  if (!_t) return;
  const root = container || document;

  root.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (!_t[key]) return;
    el.textContent = _t[key];
  });

  root.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.getAttribute("data-i18n-placeholder");
    if (_t[key]) el.setAttribute("placeholder", _t[key]);
  });
}

async function populateLanguageSwitcher() {
  const select = document.getElementById("lang-select");
  if (!select) return;
  try {
    const res = await fetch("/api/languages/");
    const data = await res.json();
    select.innerHTML = "";
    data.languages.forEach((lang) => {
      const opt = document.createElement("option");
      opt.value = lang.code;
      opt.textContent = lang.name;
      if (lang.code === _lang) opt.selected = true;
      select.appendChild(opt);
    });
  } catch (e) {
    // If discovery fails, the select just stays empty; language stays at default.
  }
  select.addEventListener("change", () => loadLanguage(select.value));
}

document.addEventListener("DOMContentLoaded", async () => {
  await populateLanguageSwitcher();
  await loadLanguage(_lang);
});
