// Troca de abas.

import { $, showError } from "./core.js";
import { openSpectraTab } from "./spectra.js";
import { openVizTab } from "./viz.js";

export function switchTab(name) {
  document.querySelectorAll("#tabs .tab").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === name));
  ["series", "spectra", "viz"].forEach((tab) => {
    $(`tab-${tab}-sidebar`).classList.toggle("hidden", tab !== name);
    $(`tab-${tab}-main`).classList.toggle("hidden", tab !== name);
  });
  showError("");
  if (name === "viz") openVizTab();
  if (name === "spectra") openSpectraTab();
}

// ── Wiring ───────────────────────────────────────────────────────────────────
document.querySelectorAll("#tabs .tab").forEach((b) =>
  b.addEventListener("click", () => switchTab(b.dataset.tab)));
