"use strict";

const History = (() => {
  function fmt(value) {
    return Number(value).toLocaleString("en-EG", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  const LOCALE_MAP = { en: "en-US", ar: "ar-EG", fr: "fr-FR", de: "de-DE" };

  function formatMonth(isoDate) {
    const d = new Date(isoDate + "T00:00:00");
    const locale = LOCALE_MAP[_lang] || "en-US";
    return d.toLocaleDateString(locale, { year: "numeric", month: "long" });
  }

  async function refresh() {
    const listEl = document.getElementById("history-list");
    const emptyEl = document.getElementById("history-empty");
    listEl.innerHTML = "";

    let bills = [];
    try {
      const data = await Api.listBills();
      bills = data.bills || [];
    } catch (err) {
      listEl.innerHTML = `<div class="error-msg">${err.message}</div>`;
      return;
    }

    if (bills.length === 0) {
      emptyEl.style.display = "block";
      return;
    }
    emptyEl.style.display = "none";

    bills.forEach((bill) => {
      const row = document.createElement("div");
      row.className = "history-row";

      const info = document.createElement("div");
      info.className = "history-info";
      info.innerHTML = `
        <div class="history-month">${formatMonth(bill.billing_month)}</div>
        <div class="history-meta">${fmt(bill.consumption_kwh)} kWh</div>
      `;

      const total = document.createElement("div");
      total.className = "history-total";
      total.textContent = `${fmt(bill.total)} EGP`;

      const delBtn = document.createElement("button");
      delBtn.className = "icon-btn";
      delBtn.textContent = "✕";
      delBtn.title = t("history_delete", "Delete");
      delBtn.addEventListener("click", async () => {
        try {
          await Api.deleteBill(bill.id);
          await refresh();
        } catch (err) {
          listEl.insertAdjacentHTML("afterbegin", `<div class="error-msg">${err.message}</div>`);
        }
      });

      row.append(info, total, delBtn);
      listEl.appendChild(row);
    });
  }

  async function init() {
    await refresh();
    document.addEventListener("billSaved", refresh);
    document.addEventListener("languageChanged", refresh);
  }

  return { init, refresh };
})();
