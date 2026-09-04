const Calculator = (() => {
  let currentTariff = null;

  function setTotal(total) {
    document.getElementById("total-number").textContent = fmt(total);
  }

  function renderBreakdown(result) {
    const el = document.getElementById("breakdown");
    el.innerHTML = "";

    const rows = [
      [t("row_energy_charge", "Energy charge"), result.energy_charge, ""],
      [t("row_service_fee", "Customer service fee"), result.customer_service_fee, ""],
      [t("row_transition", "Transition deduction"), result.transition_deduction, "fee"],
      [t("row_other_fees", "Other fees"), result.other_fees, "fee"],
      [t("row_unread_fee", "Unread meter fee"), result.unread_meter_fee, "fee"],
    ];

    rows.forEach(([label, value, cls]) => {
      if (Number(value) === 0 && cls === "fee") return;
      const row = document.createElement("div");
      row.className = `breakdown-row ${cls}`;
      row.innerHTML = `<span class="label">${label}</span><span class="value">${fmt(value)} EGP</span>`;
      el.appendChild(row);
    });

    const totalRow = document.createElement("div");
    totalRow.className = "breakdown-row total";
    totalRow.innerHTML = `<span class="label">${t("row_total", "Total")}</span><span class="value">${fmt(result.total)} EGP</span>`;
    el.appendChild(totalRow);

    const linesWrap = document.createElement("div");
    linesWrap.className = "energy-lines";
    result.details.energy_breakdown.forEach((line) => {
      const l = document.createElement("div");
      l.className = "line";
      l.innerHTML = `<span>${t("slice_option_label", "Slice {order}").replace("{order}", fmtInt(line.slice_order))} · ${fmt(line.kwh)} kWh @ ${fmt(line.rate_egp)}</span><span>${fmt(line.charge)} EGP</span>`;
      linesWrap.appendChild(l);
    });
    if (result.details.service_fee_breakdown && result.details.service_fee_breakdown.length > 1) {
      result.details.service_fee_breakdown.forEach((line) => {
        const l = document.createElement("div");
        l.className = "line";
        l.innerHTML = `<span>${t("service_fee_slice_line", "Slice {order} service fee").replace("{order}", fmtInt(line.slice_order))}</span><span>${fmt(line.fee)} EGP</span>`;
        linesWrap.appendChild(l);
      });
    }
    if (result.details.transition_breakdown.length) {
      result.details.transition_breakdown.forEach((rule) => {
        const l = document.createElement("div");
        l.className = "line";
        l.innerHTML = `<span>${rule.note || "Transition surcharge"}</span><span>${fmt(rule.deduction_amount)} EGP</span>`;
        linesWrap.appendChild(l);
      });
    }
    el.appendChild(linesWrap);
  }

  async function loadTariff() {
    currentTariff = await Api.getTariff();
    Ladder.render(
      document.getElementById("ladder"),
      document.getElementById("ladder-labels"),
      currentTariff.slices,
      0
    );
  }

  async function runCalculation() {
    const consumptionInput = document.getElementById("consumption-input");
    const rawValue = consumptionInput.value.trim();
    const unreadMeter = document.getElementById("unread-meter-check").checked;
    const errorEl = document.getElementById("calc-error");
    const statusEl = document.getElementById("calc-status");
    errorEl.textContent = "";
    statusEl.textContent = "";

    // Blank consumption is only acceptable when the meter couldn't be read -
    // the bill then defaults to just the unread-meter fee (0 kWh energy charge).
    let consumption = null;
    if (rawValue !== "") {
      consumption = parseFloat(rawValue);
      if (isNaN(consumption) || consumption < 0) {
        errorEl.textContent = t("error_invalid_consumption", "Enter a valid, non-negative consumption in kWh.");
        return;
      }
    } else if (!unreadMeter) {
      errorEl.textContent = t("error_invalid_consumption", "Enter a valid, non-negative consumption in kWh.");
      return;
    }

    const shouldSave = document.getElementById("save-bill-check").checked;
    const billingMonth = document.getElementById("billing-month-input").value;

    if (shouldSave && !billingMonth) {
      errorEl.textContent = t("error_billing_month_required", "Pick a billing month to save this bill.");
      return;
    }

    try {
      const payload = { unread_meter: unreadMeter };
      if (consumption !== null) payload.consumption_kwh = consumption;
      if (shouldSave) {
        payload.save = true;
        payload.billing_month = billingMonth;
      }
      const result = await Api.calculate(payload);
      setTotal(result.total);
      renderBreakdown(result);
      Ladder.render(
        document.getElementById("ladder"),
        document.getElementById("ladder-labels"),
        currentTariff.slices,
        consumption !== null ? consumption : 0
      );
      if (shouldSave) {
        statusEl.textContent = t("bill_saved", "Bill saved.");
        document.dispatchEvent(new CustomEvent("billSaved"));
      }
    } catch (err) {
      errorEl.textContent = err.message;
    }
  }

  const DATE_LOCALE_MAP = { en: "en-US", ar: "ar-EG-u-nu-arab", fr: "fr-FR", de: "de-DE" };

  function updateBillingMonthPreview() {
    const input = document.getElementById("billing-month-input");
    const preview = document.getElementById("billing-month-preview");
    if (!input.value) {
      preview.textContent = "";
      return;
    }
    const d = new Date(input.value + "T00:00:00");
    const locale = DATE_LOCALE_MAP[_lang] || "en-US";
    preview.textContent = d.toLocaleDateString(locale, { year: "numeric", month: "long" });
  }

  function bindEvents() {
    document.getElementById("calculate-btn").addEventListener("click", runCalculation);
    document.getElementById("consumption-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter") runCalculation();
    });
    document.getElementById("save-bill-check").addEventListener("change", (e) => {
      document.getElementById("billing-month-field").style.display = e.target.checked ? "block" : "none";
    });
    document.getElementById("billing-month-input").addEventListener("change", updateBillingMonthPreview);
    document.addEventListener("languageChanged", updateBillingMonthPreview);
  }

  async function init() {
    bindEvents();
    await loadTariff();
  }

  return { init, reloadTariff: loadTariff };
})();
