"use strict";

function getNumberLocale() {
  const currentLang = localStorage.getItem("lang") || "en";
  // 'ar-EG-u-nu-arab' explicitly forces the localized Arabic-Indic digits (١, ٢, ٣).
  // Plain 'ar-EG' alone doesn't reliably do this across all browsers.
  return currentLang === "ar" ? "ar-EG-u-nu-arab" : "en-US";
}

function fmt(value) {
  if (value === null || value === undefined) return "-";
  return Number(value).toLocaleString(getNumberLocale(), {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function fmtInt(value) {
  if (value === null || value === undefined) return "-";
  return Number(value).toLocaleString(getNumberLocale());
}
