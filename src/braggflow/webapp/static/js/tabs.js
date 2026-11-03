// Troca de abas.

import { $, showError } from "./core.js";
import { openSpectraTab } from "./spectra.js";
import { openVizTab } from "./viz.js";

export function switchTab(name) {
  document.querySelectorAll("#tabs .tab").forEach((b) => {
    const ativa = b.dataset.tab === name;
    b.classList.toggle("active", ativa);
    b.setAttribute("aria-selected", String(ativa));
    b.tabIndex = ativa ? 0 : -1;
  });
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

// Setas entre as abas, como em qualquer lista de abas
$("tabs").addEventListener("keydown", (e) => {
  const abas = [...document.querySelectorAll("#tabs .tab")];
  const i = abas.indexOf(document.activeElement);
  if (i < 0) return;
  const destino = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: abas.length - 1 }[e.key];
  if (destino === undefined) return;
  e.preventDefault();
  const aba = abas[(destino + abas.length) % abas.length];
  aba.focus();
  switchTab(aba.dataset.tab);
});
