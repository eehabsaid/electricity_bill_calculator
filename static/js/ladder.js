const Ladder = (() => {
  function widthWeight(slice, slices) {
    if (slice.max_kwh === null) {
      // Open-ended last slice: give it a width similar to the slice before it,
      // unless the current reading pushes deep into it.
      const prev = slices[slices.length - 2];
      const fallback = prev ? Number(prev.max_kwh) - Number(prev.min_kwh) : 200;
      return Math.log1p(fallback);
    }
    return Math.log1p(Number(slice.max_kwh) - Number(slice.min_kwh));
  }

  function render(container, labelsContainer, slices, consumption) {
    container.innerHTML = "";
    labelsContainer.innerHTML = "";
    if (!slices.length) return;

    const weights = slices.map((s) => widthWeight(s, slices));
    const totalWeight = weights.reduce((a, b) => a + b, 0);

    slices.forEach((slice, i) => {
      const pct = (weights[i] / totalWeight) * 100;
      const band = document.createElement("div");
      band.className = "band";
      band.style.width = `${pct}%`;

      const min = Number(slice.min_kwh);
      const max = slice.max_kwh === null ? null : Number(slice.max_kwh);

      if (consumption > (max ?? Infinity)) {
        band.classList.add("filled");
      } else if (consumption >= min && (max === null || consumption <= max)) {
        band.classList.add("current");
        const span = max === null ? Math.max(consumption - min, 1) : max - min;
        const fillPct = span > 0 ? Math.min(100, ((consumption - min) / span) * 100) : 100;
        const fill = document.createElement("div");
        fill.className = "fill";
        fill.style.width = `${fillPct}%`;
        band.appendChild(fill);
      }
      band.title = `Slice ${slice.order}: ${min}–${max === null ? "∞" : max} kWh @ ${(slice.rate_piastres / 100).toFixed(2)} EGP/kWh`;
      container.appendChild(band);

      const label = document.createElement("span");
      label.style.width = `${pct}%`;
      label.textContent = max === null ? `${min}+` : `${min}–${max}`;
      labelsContainer.appendChild(label);
    });
  }

  return { render };
})();
