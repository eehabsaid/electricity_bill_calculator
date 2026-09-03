document.addEventListener("DOMContentLoaded", () => {
  const switchButtons = document.querySelectorAll("nav.view-switch button");
  const views = document.querySelectorAll("section.view");

  switchButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      switchButtons.forEach((b) => b.classList.remove("active"));
      views.forEach((v) => v.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(btn.dataset.view).classList.add("active");
    });
  });

  document.getElementById("theme-toggle").addEventListener("click", toggleTheme);

  Calculator.init();
  Settings.init();

  document.addEventListener("languageChanged", () => {
    Settings.refresh();
  });
});
