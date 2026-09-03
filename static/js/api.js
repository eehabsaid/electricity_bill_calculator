const Api = (() => {
  async function request(path, options = {}) {
    const res = await fetch(`/api${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    let body = null;
    try { body = await res.json(); } catch (e) { /* empty body */ }
    if (!res.ok) {
      const message = (body && body.error) || `Request failed (${res.status})`;
      throw new Error(message);
    }
    return body;
  }

  return {
    getTariff: () => request("/tariff/"),
    updateTariff: (patch) => request("/tariff/", { method: "PATCH", body: JSON.stringify(patch) }),

    createSlice: (data) => request("/tariff/slices/", { method: "POST", body: JSON.stringify(data) }),
    updateSlice: (id, patch) => request(`/tariff/slices/${id}/`, { method: "PATCH", body: JSON.stringify(patch) }),
    deleteSlice: (id) => request(`/tariff/slices/${id}/`, { method: "DELETE" }),

    createTransitionRule: (data) => request("/tariff/transition-rules/", { method: "POST", body: JSON.stringify(data) }),
    updateTransitionRule: (id, patch) => request(`/tariff/transition-rules/${id}/`, { method: "PATCH", body: JSON.stringify(patch) }),
    deleteTransitionRule: (id) => request(`/tariff/transition-rules/${id}/`, { method: "DELETE" }),

    createFee: (data) => request("/tariff/fees/", { method: "POST", body: JSON.stringify(data) }),
    updateFee: (id, patch) => request(`/tariff/fees/${id}/`, { method: "PATCH", body: JSON.stringify(patch) }),
    deleteFee: (id) => request(`/tariff/fees/${id}/`, { method: "DELETE" }),

    calculate: (payload) => request("/calculate/", { method: "POST", body: JSON.stringify(payload) }),
    listBills: () => request("/bills/"),
    deleteBill: (id) => request(`/bills/${id}/`, { method: "DELETE" }),
  };
})();
