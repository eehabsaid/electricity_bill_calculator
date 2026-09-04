const Settings = (() => {
  let tariff = null;

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  async function refresh() {
    tariff = await Api.getTariff();
    renderMeta();
    renderSlices();
    renderTransitionRules();
    renderFees();
    Calculator.reloadTariff();
  }

  function renderMeta() {
    document.getElementById("tariff-name").value = tariff.name;
    document.getElementById("unread-fee-input").value = tariff.unread_meter_fee;
    document.getElementById("service-fee-mode-select").value = tariff.service_fee_mode;
  }

  async function saveMeta() {
    const statusEl = document.getElementById("meta-status");
    try {
      await Api.updateTariff({
        name: document.getElementById("tariff-name").value,
        unread_meter_fee: document.getElementById("unread-fee-input").value,
        service_fee_mode: document.getElementById("service-fee-mode-select").value,
      });
      statusEl.textContent = t("saved_status", "Saved.");
      await refresh();
      setTimeout(() => (statusEl.textContent = ""), 1500);
    } catch (err) {
      statusEl.textContent = err.message;
    }
  }

  function renderSlices() {
    const tbody = document.getElementById("slices-body");
    tbody.innerHTML = "";
    const sorted = [...tariff.slices].sort((a, b) => a.order - b.order);

    sorted.forEach((slice, idx) => {
      const isLast = idx === sorted.length - 1;
      const tr = document.createElement("tr");

      const orderTd = document.createElement("td");
      const orderInput = document.createElement("input");
      orderInput.type = "number";
      orderInput.value = slice.order;
      orderInput.style.width = "3.5em";
      orderInput.addEventListener("change", () => commitField(slice.id, "order", parseInt(orderInput.value, 10)));
      orderTd.appendChild(orderInput);

      const minTd = document.createElement("td");
      const minInput = document.createElement("input");
      minInput.type = "number";
      minInput.step = "0.01";
      minInput.value = slice.min_kwh;
      minInput.disabled = true; // derived from previous slice's max to keep the ladder contiguous
      minTd.appendChild(minInput);

      const maxTd = document.createElement("td");
      const maxInput = document.createElement("input");
      maxInput.type = "number";
      maxInput.step = "0.01";
      maxInput.value = isLast ? "" : slice.max_kwh;
      maxInput.placeholder = isLast ? "open-ended" : "";
      maxInput.disabled = isLast;
      maxInput.addEventListener("change", () => onMaxChange(sorted, idx, maxInput.value));
      maxTd.appendChild(maxInput);

      const rateTd = document.createElement("td");
      const rateInput = document.createElement("input");
      rateInput.type = "number";
      rateInput.step = "0.01";
      rateInput.value = slice.rate_piastres;
      rateInput.addEventListener("change", () => commitField(slice.id, "rate_piastres", rateInput.value));
      rateTd.appendChild(rateInput);

      const feeTd = document.createElement("td");
      const feeInput = document.createElement("input");
      feeInput.type = "number";
      feeInput.step = "0.01";
      feeInput.value = slice.customer_service_fee;
      feeInput.addEventListener("change", () => commitField(slice.id, "customer_service_fee", feeInput.value));
      feeTd.appendChild(feeInput);

      const modeTd = document.createElement("td");
      const modeSelect = document.createElement("select");
      const marginalOpt = document.createElement("option");
      marginalOpt.value = "marginal";
      marginalOpt.textContent = t("mode_marginal", "Progressive");
      const flatOpt = document.createElement("option");
      flatOpt.value = "flat_full";
      flatOpt.textContent = t("mode_flat_full", "Flat (whole amount)");
      modeSelect.append(marginalOpt, flatOpt);
      modeSelect.value = slice.billing_mode;
      modeSelect.addEventListener("change", () => commitField(slice.id, "billing_mode", modeSelect.value));
      modeTd.appendChild(modeSelect);

      const actionTd = document.createElement("td");
      const delBtn = document.createElement("button");
      delBtn.className = "icon-btn";
      delBtn.textContent = "✕";
      delBtn.title = "Remove slice";
      delBtn.addEventListener("click", () => removeSlice(slice.id));
      actionTd.appendChild(delBtn);

      tr.append(orderTd, minTd, maxTd, rateTd, feeTd, modeTd, actionTd);
      tbody.appendChild(tr);
    });
  }

  async function onMaxChange(sorted, idx, newMax) {
    const statusEl = document.getElementById("slices-status");
    const slice = sorted[idx];
    const nextSlice = sorted[idx + 1];
    try {
      const maxVal = parseFloat(newMax);
      await Api.updateSlice(slice.id, { max_kwh: maxVal });
      if (nextSlice) {
        await Api.updateSlice(nextSlice.id, { min_kwh: (maxVal + 0.01).toFixed(2) });
      }
      await refresh();
    } catch (err) {
      statusEl.textContent = err.message;
    }
  }

  async function commitField(sliceId, field, value) {
    const statusEl = document.getElementById("slices-status");
    try {
      await Api.updateSlice(sliceId, { [field]: value });
      statusEl.textContent = "";
      await refresh();
    } catch (err) {
      statusEl.textContent = err.message;
    }
  }

  async function removeSlice(sliceId) {
    const statusEl = document.getElementById("slices-status");
    if (tariff.slices.length <= 1) {
      statusEl.textContent = t("min_one_slice", "A tariff needs at least one slice.");
      return;
    }
    try {
      await Api.deleteSlice(sliceId);
      await refresh();
    } catch (err) {
      statusEl.textContent = err.message;
    }
  }

  async function addSlice() {
    const statusEl = document.getElementById("slices-status");
    const sorted = [...tariff.slices].sort((a, b) => a.order - b.order);
    const last = sorted[sorted.length - 1];
    const lastMax = last.max_kwh === null ? Number(last.min_kwh) + 100 : Number(last.max_kwh);

    try {
      // Close off the previous open-ended slice, then append a new open-ended one.
      if (last.max_kwh === null) {
        await Api.updateSlice(last.id, { max_kwh: lastMax });
      }
      await Api.createSlice({
        order: last.order + 1,
        min_kwh: (lastMax + 0.01).toFixed(2),
        max_kwh: null,
        rate_piastres: last.rate_piastres,
        customer_service_fee: last.customer_service_fee,
      });
      await refresh();
    } catch (err) {
      statusEl.textContent = err.message;
    }
  }

  function renderTransitionRules() {
    const wrap = document.getElementById("transition-rules");
    wrap.innerHTML = "";
    const sorted = [...tariff.slices].sort((a, b) => a.order - b.order);

    tariff.transition_rules
      .sort((a, b) => a.order - b.order)
      .forEach((rule) => {
        const row = el("div", "field");
        row.style.display = "flex";
        row.style.alignItems = "center";
        row.style.gap = "0.6rem";
        row.style.marginBottom = "0.6rem";

        const check = document.createElement("input");
        check.type = "checkbox";
        check.checked = rule.is_active;
        check.addEventListener("change", async () => {
          await Api.updateTransitionRule(rule.id, { is_active: check.checked });
          await refresh();
        });

        const label = el("span", null, t("entering_slice", "Entering slice {order}").replace("{order}", rule.triggering_slice_order));
        label.style.flex = "1";
        label.style.fontSize = "0.85rem";
        label.style.color = "var(--text-dim)";

        const amountInput = document.createElement("input");
        amountInput.type = "number";
        amountInput.step = "0.01";
        amountInput.value = rule.deduction_amount;
        amountInput.style.width = "6em";
        amountInput.addEventListener("change", async () => {
          await Api.updateTransitionRule(rule.id, { deduction_amount: amountInput.value });
          await refresh();
        });

        const delBtn = document.createElement("button");
        delBtn.className = "icon-btn";
        delBtn.textContent = "✕";
        delBtn.addEventListener("click", async () => {
          await Api.deleteTransitionRule(rule.id);
          await refresh();
        });

        row.append(check, label, amountInput, delBtn);
        wrap.appendChild(row);
      });

    const addRow = document.createElement("div");
    addRow.style.display = "flex";
    addRow.style.gap = "0.5rem";
    addRow.style.marginTop = "0.75rem";

    const sliceSelect = document.createElement("select");
    sorted.forEach((s) => {
      const opt = document.createElement("option");
      opt.value = s.id;
      opt.textContent = t("slice_option_label", "Slice {order}").replace("{order}", s.order);
      sliceSelect.appendChild(opt);
    });

    const amountInput = document.createElement("input");
    amountInput.type = "number";
    amountInput.step = "0.01";
    amountInput.placeholder = t("amount_placeholder", "Amount (EGP)");
    amountInput.style.width = "8em";

    const addBtn = document.createElement("button");
    addBtn.className = "ghost";
    addBtn.textContent = t("add_rule_btn", "+ Add rule");
    addBtn.addEventListener("click", async () => {
      if (!amountInput.value) return;
      await Api.createTransitionRule({
        triggering_slice_id: parseInt(sliceSelect.value, 10),
        deduction_amount: amountInput.value,
        is_active: true,
        note: "",
      });
      await refresh();
    });

    addRow.append(sliceSelect, amountInput, addBtn);
    wrap.appendChild(addRow);
  }

  const FEE_TYPE_LABELS = () => ({
    fixed: t("fee_type_fixed", "Fixed (EGP)"),
    percentage: t("fee_type_percentage", "% of energy charge"),
    per_kwh: t("fee_type_per_kwh", "Per kWh (EGP)"),
  });

  function renderFees() {
    const wrap = document.getElementById("fees");
    wrap.innerHTML = "";
    const feeTypeLabels = FEE_TYPE_LABELS();

    tariff.fees.forEach((fee) => {
      const row = el("div", "field");
      row.style.display = "flex";
      row.style.alignItems = "center";
      row.style.gap = "0.6rem";
      row.style.marginBottom = "0.6rem";

      const check = document.createElement("input");
      check.type = "checkbox";
      check.checked = fee.is_active;
      check.title = "Active";
      check.addEventListener("change", async () => {
        await Api.updateFee(fee.id, { is_active: check.checked });
        await refresh();
      });

      const nameInput = document.createElement("input");
      nameInput.type = "text";
      nameInput.value = fee.name;
      nameInput.style.flex = "1";
      nameInput.addEventListener("change", async () => {
        await Api.updateFee(fee.id, { name: nameInput.value });
        await refresh();
      });

      const typeSelect = document.createElement("select");
      Object.entries(feeTypeLabels).forEach(([value, label]) => {
        const opt = document.createElement("option");
        opt.value = value;
        opt.textContent = label;
        if (value === fee.fee_type) opt.selected = true;
        typeSelect.appendChild(opt);
      });
      typeSelect.style.width = "12em";
      typeSelect.addEventListener("change", async () => {
        await Api.updateFee(fee.id, { fee_type: typeSelect.value });
        await refresh();
      });

      const amountInput = document.createElement("input");
      amountInput.type = "number";
      amountInput.step = "0.01";
      amountInput.value = fee.amount;
      amountInput.style.width = "6em";
      amountInput.addEventListener("change", async () => {
        await Api.updateFee(fee.id, { amount: amountInput.value });
        await refresh();
      });

      const delBtn = document.createElement("button");
      delBtn.className = "icon-btn";
      delBtn.textContent = "✕";
      delBtn.addEventListener("click", async () => {
        await Api.deleteFee(fee.id);
        await refresh();
      });

      row.append(check, nameInput, typeSelect, amountInput, delBtn);
      wrap.appendChild(row);
    });

    const addRow = document.createElement("div");
    addRow.style.display = "flex";
    addRow.style.gap = "0.5rem";
    addRow.style.marginTop = "0.75rem";

    const nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.placeholder = t("fee_name_placeholder", "Fee name");
    nameInput.style.flex = "1";

    const typeSelect = document.createElement("select");
    Object.entries(feeTypeLabels).forEach(([value, label]) => {
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = label;
      typeSelect.appendChild(opt);
    });
    typeSelect.style.width = "12em";

    const amountInput = document.createElement("input");
    amountInput.type = "number";
    amountInput.step = "0.01";
    amountInput.placeholder = t("amount_placeholder", "Amount (EGP)");
    amountInput.style.width = "6em";

    const addBtn = document.createElement("button");
    addBtn.className = "ghost";
    addBtn.textContent = t("add_fee_btn", "+ Add fee");
    addBtn.addEventListener("click", async () => {
      if (!nameInput.value || !amountInput.value) return;
      await Api.createFee({
        name: nameInput.value,
        fee_type: typeSelect.value,
        amount: amountInput.value,
        is_active: true,
      });
      await refresh();
    });

    addRow.append(nameInput, typeSelect, amountInput, addBtn);
    wrap.appendChild(addRow);
  }

  function bindEvents() {
    document.getElementById("save-meta-btn").addEventListener("click", saveMeta);
    document.getElementById("add-slice-btn").addEventListener("click", addSlice);
  }

  async function init() {
    bindEvents();
    await refresh();
  }

  return { init, refresh };
})();
