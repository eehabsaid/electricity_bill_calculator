"use strict";

const History = (() => {
  let requestId = 0;

  const LOCALE_MAP = { en: "en-US", ar: "ar-EG-u-nu-arab", fr: "fr-FR", de: "de-DE" };

  function formatDate(isoDate) {
    const d = new Date(isoDate + "T00:00:00");
    const locale = LOCALE_MAP[_lang] || "en-US";
    return d.toLocaleDateString(locale, { year: "numeric", month: "long" });
  }

  async function refresh() {
    const myRequestId = ++requestId;
    const container = document.getElementById("history-list");
    const emptyEl = document.getElementById("history-empty");

    let bills = [];
    try {
      const data = await Api.listBills();
      bills = data.bills || [];
    } catch (err) {
      if (myRequestId !== requestId) return; // a newer refresh() superseded this one
      container.innerHTML = `<div class="error-msg">${err.message}</div>`;
      return;
    }

    if (myRequestId !== requestId) return; // a newer refresh() superseded this one
    container.innerHTML = "";

    if (bills.length === 0) {
      emptyEl.style.display = "block";
      return;
    }
    emptyEl.style.display = "none";

    const table = document.createElement("table");
    table.className = "slices history-table";

    const thead = document.createElement("thead");
    thead.innerHTML = `
      <tr>
        <th>${t("history_col_date", "Bill date")}</th>
        <th>${t("history_col_consumption", "Consumption")}</th>
        <th>${t("row_energy_charge", "Energy charge")}</th>
        <th>${t("row_service_fee", "Customer service fee")}</th>
        <th>${t("row_other_fees", "Other fees")}</th>
        <th>${t("row_total", "Total")}</th>
        <th></th>
      </tr>
    `;
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    bills.forEach((bill) => {
      // Anything beyond energy + service fee (transition deductions, extra
      // fees, the unread-meter fee) is rolled into one "Other fees" figure,
      // so the visible columns still add up to the Total shown.
      const otherFees = (
        Number(bill.transition_deduction) +
        Number(bill.other_fees) +
        Number(bill.unread_meter_fee)
      );

      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${formatDate(bill.billing_month)}</td>
        <td>${fmt(bill.consumption_kwh)} kWh</td>
        <td>${fmt(bill.energy_charge)} EGP</td>
        <td>${fmt(bill.customer_service_fee)} EGP</td>
        <td>${fmt(otherFees)} EGP</td>
        <td class="history-total-cell">${fmt(bill.total)} EGP</td>
      `;

      const actionTd = document.createElement("td");
      const delBtn = document.createElement("button");
      delBtn.className = "icon-btn";
      delBtn.textContent = "✕";
      delBtn.title = t("history_delete", "Delete");
      delBtn.addEventListener("click", async () => {
        try {
          await Api.deleteBill(bill.id);
          await refresh();
        } catch (err) {
          container.insertAdjacentHTML("afterbegin", `<div class="error-msg">${err.message}</div>`);
        }
      });
      actionTd.appendChild(delBtn);
      tr.appendChild(actionTd);

      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    container.appendChild(table);
  }

  async function init() {
    await refresh();
    document.addEventListener("billSaved", refresh);
    document.addEventListener("languageChanged", refresh);
  }

  return { init, refresh };
})();
