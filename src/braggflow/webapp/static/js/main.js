// Ponto de entrada: ligações que atravessam as abas (barra lateral,
// atalhos de teclado) e a inicialização da página. Os demais módulos chegam
// pelas importações (tabs.js via series.js, analysis.js via spectra.js).

import { $, checkServerBuild, showError, syncCardStyles, toggleStep } from "./core.js";
import { applySetup, loadChannels, loadFileList, loadSetupList, processData, scheduleAutoProcess, syncTempChannels } from "./series.js";
import { previewSpectrum } from "./spectra.js";
import { drawPlotMarkers, generateFigure, loadFigureOptions, onVizChange, scheduleFigure, sortMarkerRows } from "./viz.js";
import { markProjectDirty, openProjectGate, redo, saveProject, undo } from "./projects.js";

// Marcações (abaixo do gráfico): não mudam o processamento, só a figura
$("card-markers").addEventListener("change", (e) => {
  if (!e.target.closest("#marker-list")) return;
  markProjectDirty();
  sortMarkerRows();
  drawPlotMarkers();
  scheduleFigure();
});

$("sidebar").addEventListener("change", async (e) => {
  const el = e.target;
  if (el.matches(".pick-series, .pick-spectrum, #auto-process, #file-upload, #spectra-upload")) return;
  markProjectDirty();
  if (el.closest("#tab-viz-sidebar")) {
    await onVizChange(el);  // aba de visualização: atualiza a figura, não o processamento
    return;
  }
  if (el.id === "file-upload" || el.id === "setup-name") return;
  if (el.id === "tempcomp-enabled" && el.checked) $("delta-enabled").checked = true;
  if (el.id === "delta-enabled" && !el.checked) $("tempcomp-enabled").checked = false;
  if (el.classList.contains("step-switch") && el.checked) toggleStep(el.closest(".step"), true);
  syncCardStyles();
  try {
    if (el.classList.contains("sensor-name")) syncTempChannels();
    if (el.id === "file-select") await loadChannels();
    if (el.id === "setup-select") await applySetup(el.value);
  } catch (err) {
    showError(err.message);
    return;
  }
  scheduleAutoProcess();
});

document.addEventListener("keydown", (e) => {
  // Desfazer do projeto, fora dos campos onde se digita (lá vale o do campo)
  const tecla = e.key.toLowerCase();
  if ((e.ctrlKey || e.metaKey) && (tecla === "z" || tecla === "y")) {
    const digitando = e.target.closest(
      "textarea, [contenteditable], input:not([type=checkbox]):not([type=radio]):not([type=button]):not([type=color])");
    if (digitando || !$("project-gate").classList.contains("hidden")) return;
    e.preventDefault();
    (tecla === "y" || e.shiftKey ? redo : undo)().catch((err) => showError(err.message));
    return;
  }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
    e.preventDefault();                 // salva o projeto, não a página
    saveProject();
    return;
  }
  if (!e.ctrlKey || e.key !== "Enter") return;
  if (!$("tab-series-sidebar").classList.contains("hidden")) processData();
  else if (!$("tab-spectra-sidebar").classList.contains("hidden")) previewSpectrum();
  else generateFigure();
});


syncCardStyles();
loadSetupList().catch((err) => showError(err.message));

(async function start() {
  await checkServerBuild();
  await loadFigureOptions().catch((err) => showError(err.message));
  await loadFileList();
  await openProjectGate().catch((err) => showError(err.message));
})();
