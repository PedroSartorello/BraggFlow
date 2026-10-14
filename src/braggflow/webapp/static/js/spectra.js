// Aba Espectros: preparo de cada espectro, gráfico, picos e vales.

import { $, fmtNum, showError } from "./core.js";
import { baseName, projectSpectraPaths, shared, shortName, spectraState, spectraStateFor } from "./state.js";
import { PALETTE, plotFont, uploadFiles } from "./series.js";
import { numeroOuTraco, tabela } from "./analysis.js";
import { fileRow, markProjectDirty, renderEmptyFiles, renderFilePicker } from "./projects.js";

export async function openSpectraTab() {
  renderSpectraFiles();
  if (!shared.currentSpectrumFile && projectSpectraPaths().length) {
    await selectSpectrumFile(projectSpectraPaths()[0]);
  } else if (shared.currentSpectrumFile) {
    await previewSpectrum();
  }
}

// ── Aba Espectros ────────────────────────────────────────────────────────────
function collectSpectrumSettings() {
  const settings = {};
  document.querySelectorAll("#tab-spectra-sidebar [data-spec]").forEach((el) => {
    settings[el.dataset.spec] = el.type === "checkbox" ? el.checked : el.value;
  });
  return settings;
}

function applySpectrumSettings(settings) {
  document.querySelectorAll("#tab-spectra-sidebar [data-spec]").forEach((el) => {
    const value = settings?.[el.dataset.spec];
    if (el.type === "checkbox") el.checked = Boolean(value);
    else el.value = value ?? "";
  });
  syncSpectrumFields();
}

export function saveCurrentSpectrumState() {
  if (shared.currentSpectrumFile) spectraStateFor(shared.currentSpectrumFile).settings = collectSpectrumSettings();
}

export function renderSpectraFiles() {
  const box = $("spectra-files");
  box.innerHTML = "";
  projectSpectraPaths().forEach((path) => {
    box.appendChild(fileRow(path, {
      selected: path === shared.currentSpectrumFile, onSelect: selectSpectrumFile,
      note: spectraState[path]?.settings?.smooth_window ? "suavizado" : "",
    }));
  });
  if (!box.children.length) {
    box.innerHTML = '<span class="hint">Nenhum espectro neste projeto ainda.</span>';
  }
  document.body.classList.toggle("no-spectra", !projectSpectraPaths().length);
  renderEmptyFiles("spectrum");
  renderFilePicker("spectrum");
}

export async function selectSpectrumFile(path) {
  if (path !== shared.currentSpectrumFile) saveCurrentSpectrumState();
  const novo = !(path in spectraState);
  shared.currentSpectrumFile = path;
  renderSpectraFiles();
  applySpectrumSettings(spectraStateFor(path).settings);
  if (novo) markProjectDirty();   // só olhar um espectro não muda o projeto
  await previewSpectrum();
}

function copySpectrumSettings() {
  saveCurrentSpectrumState();
  const source = spectraState[shared.currentSpectrumFile];
  if (!source) return;
  projectSpectraPaths().filter((path) => path !== shared.currentSpectrumFile).forEach((path) => {
    spectraStateFor(path).settings = structuredClone(source.settings);
  });
  renderSpectraFiles();
  markProjectDirty();
  $("spectra-status").textContent = "Preparo aplicado a todos os espectros.";
}

function renderSpectrumPlot(data) {
  const traces = data.traces.map((trace, i) => ({
    x: trace.wavelength, y: trace.intensity, name: trace.name, mode: "lines",
    line: { color: PALETTE[i % PALETTE.length], width: 1.2 },
  }));
  data.traces.forEach((trace, i) => {
    const cor = PALETTE[i % PALETTE.length];
    const extremos = trace.extrema || [];
    if (!extremos.length) return;
    traces.push({
      x: extremos.map((e) => e.wavelength), y: extremos.map((e) => e.intensity),
      mode: "markers", name: `${trace.name} · extremos`, showlegend: false,
      marker: {
        color: extremos.map((e) => (e.type === "max" ? "#c0392b" : "#1f6fb2")),
        symbol: extremos.map((e) => (e.type === "max" ? "triangle-up" : "triangle-down")),
        size: 9, line: { color: "#fff", width: 1 },
      },
      text: extremos.map((e) => `${e.type === "max" ? "máximo" : "mínimo"}` +
        (e.fwhm ? ` · largura ${fmtNum(e.fwhm, 4)} nm · Q ${fmtNum(e.q, 0)}` : "")),
      hovertemplate: "%{text}<br>λ = %{x:.4f} nm<br>I = %{y}<extra></extra>",
    });
    const xs = [], ys = [];
    extremos.filter((e) => e.fwhm).forEach((e) => {
      xs.push(e.left, e.right, null);
      ys.push(e.level, e.level, null);
    });
    if (xs.length) {
      traces.push({
        x: xs, y: ys, mode: "lines", name: `${trace.name} · largura`, showlegend: false,
        line: { color: cor, width: 1.5, dash: "dash" }, hoverinfo: "skip",
      });
    }
  });
  Plotly.react($("spectra-plot"), traces, {
    separators: ",.",
    margin: { l: 60, r: 20, t: 30, b: 45 },
    font: { family: plotFont(), size: 12.5, color: "#16212e" },
    xaxis: { title: "Comprimento de onda (nm)", gridcolor: "#eceff3", zerolinecolor: "#e2e7ee" },
    yaxis: { title: "Intensidade", gridcolor: "#eceff3", zerolinecolor: "#e2e7ee" },
    hovermode: "x unified",
    legend: { orientation: "h", y: 1.08 },
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
  }, { responsive: true });
}

// ── Picos e vales: tabela e resumo de cada traço ────────────────────────────
let spectraAnalysis = null;    // {file, traces} da última prévia

const SPECTRA_COLUNAS = (larguraNome) => [
  ["Traço", (t) => t.trace],
  ["Tipo", (e) => (e.type === "max" ? "máximo" : "mínimo")],
  ["λ (nm)", (e) => numeroOuTraco(e.wavelength, 4)],
  ["Intensidade", (e) => numeroOuTraco(e.intensity, 4)],
  ["Proeminência", (e) => numeroOuTraco(e.prominence, 4)],
  [`${larguraNome} (nm)`, (e) => numeroOuTraco(e.fwhm, 4)],
  ["Q", (e) => numeroOuTraco(e.q, 0)],
  ["Centroide (nm)", (e) => numeroOuTraco(e.centroid, 4)],
  ["Δλ anterior (nm)", (e) => numeroOuTraco(e.spacing, 4)],
];

function spectraRows(data) {
  return data.traces.flatMap((t) => (t.extrema || []).map((e) => ({ ...e, trace: t.name })));
}

function renderSpectraResults(data) {
  const settings = spectraStateFor(shared.currentSpectrumFile).settings || {};
  const ligado = Boolean(settings.find_max || settings.find_min);
  $("spectra-results").classList.toggle("hidden", !ligado);
  spectraAnalysis = ligado ? data : null;
  if (!ligado) return;

  const db = settings.intensity_scale === "db";
  const unidade = db ? " dB" : "";
  const colunas = SPECTRA_COLUNAS(db ? "Banda 3 dB" : "FWHM");

  // Resumo: uma linha por traço
  const resumo = $("spectra-summary");
  resumo.innerHTML = "";
  data.traces.forEach((t) => {
    const r = t.summary || {};
    const partes = [];
    if (r.global_max) partes.push(`máx. global ${fmtNum(r.global_max.intensity, 4)} em ${fmtNum(r.global_max.wavelength, 4)} nm`);
    if (r.global_min) partes.push(`mín. global ${fmtNum(r.global_min.intensity, 4)} em ${fmtNum(r.global_min.wavelength, 4)} nm`);
    if (r.side_lobe_suppression != null) partes.push(`lóbulo lateral −${fmtNum(r.side_lobe_suppression, 3)}${unidade}`);
    if (r.fsr_max != null) partes.push(`FSR picos ${fmtNum(r.fsr_max, 4)} nm`);
    if (r.fsr_min != null) partes.push(`FSR vales ${fmtNum(r.fsr_min, 4)} nm`);
    if (r.resolution != null) partes.push(`resolução ${fmtNum(r.resolution * 1000, 2)} pm`);
    if (r.prominence != null) partes.push(`proeminência ≥ ${fmtNum(r.prominence, 4)}`);
    const linha = document.createElement("span");
    const nome = document.createElement("b");
    nome.textContent = `${t.name}: ${r.n_max || 0} pico(s), ${r.n_min || 0} vale(s)`;
    linha.append(nome, document.createTextNode(partes.length ? " · " + partes.join(" · ") : ""));
    resumo.appendChild(linha);
  });

  // Tabela: um extremo por linha
  const tabela = $("spectra-table");
  tabela.innerHTML = "";
  const linhas = spectraRows(data);
  if (!linhas.length) {
    tabela.innerHTML = '<tr><td style="text-align:left">Nenhum extremo com essa proeminência. ' +
      "Diminua a proeminência mínima ou confira a escala.</td></tr>";
    return;
  }
  const cabeca = tabela.createTHead().insertRow();
  colunas.forEach(([nome]) => {
    const th = document.createElement("th");
    th.textContent = nome;
    cabeca.appendChild(th);
  });
  const corpo = tabela.createTBody();
  linhas.forEach((linha) => {
    const tr = corpo.insertRow();
    colunas.forEach(([, valor]) => { tr.insertCell().textContent = valor(linha); });
  });
}

function spectraCsv() {
  if (!spectraAnalysis) return "";
  const db = spectraStateFor(shared.currentSpectrumFile)?.settings?.intensity_scale === "db";
  const colunas = SPECTRA_COLUNAS(db ? "Banda 3 dB" : "FWHM");
  const linhas = spectraRows(spectraAnalysis);
  return [colunas.map(([nome]) => nome).join(";"),
          ...linhas.map((l) => colunas.map(([, valor]) => valor(l).replace(/—/, "")).join(";"))]
    .join("\n");
}

$("btn-spectra-csv").addEventListener("click", () => {
  const csv = spectraCsv();
  if (!csv) { showError("Ligue a detecção de máximos ou mínimos antes de baixar."); return; }
  const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${baseName(shared.currentSpectrumFile).replace(/\.[^.]+$/, "")}_picos_vales.csv`;
  a.click();
  URL.revokeObjectURL(url);
});

// O "?" vive dentro do <summary>, então não pode abrir e fechar o cartão
$("btn-spectra-help").addEventListener("click", (e) => {
  e.preventDefault();
  e.stopPropagation();
  const fechado = $("spectra-help").classList.toggle("hidden");
  $("btn-spectra-help").classList.toggle("on", !fechado);
  if (!$("spectra-results").open) $("spectra-results").open = true;
});

// A ordem do ajuste só vale para o Savitzky-Golay
function syncSpectrumFields() {
  const sg = document.querySelector('[data-spec="smooth_method"]').value === "savgol";
  const ordem = document.querySelector('[data-spec="smooth_order"]');
  ordem.disabled = !sg;
  $("spec-order-field").title = sg ? "" : "Só o Savitzky-Golay usa a ordem do ajuste";
}

let spectrumPreviewRequest = 0;
export async function previewSpectrum() {
  if (!shared.currentSpectrumFile) return;
  saveCurrentSpectrumState();
  const request = ++spectrumPreviewRequest;
  $("spectra-status").textContent = "Lendo espectro…";
  try {
    const resp = await fetch("/api/spectra/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file: shared.currentSpectrumFile,
                             settings: spectraStateFor(shared.currentSpectrumFile).settings }),
    });
    const data = await resp.json();
    if (request !== spectrumPreviewRequest) return;
    if (!resp.ok) throw new Error(data.error || "Erro ao ler o espectro.");
    showError("");
    renderSpectraResults(data);
    renderSpectrumPlot(data);
    const points = data.traces.reduce((total, trace) => total + trace.n_points, 0);
    const stride = data.traces[0]?.plot_stride > 1 ? ` (gráfico decimado 1:${data.traces[0].plot_stride})` : "";
    $("spectra-status").textContent =
      `${shortName(shared.currentSpectrumFile)} · ${data.traces.length} traço(s) · ` +
      `${points.toLocaleString("pt-BR")} pontos${stride}`;
  } catch (err) {
    if (request !== spectrumPreviewRequest) return;
    showError(err.message);
    $("spectra-status").textContent = `Falha: ${err.message}`;
  }
}

let spectrumTimer = null;
function scheduleSpectrumPreview() {
  clearTimeout(spectrumTimer);
  spectrumTimer = setTimeout(() => previewSpectrum(), 400);
}

$("tab-spectra-sidebar").addEventListener("change", (e) => {
  if (e.target.matches("#spectra-upload, .pick-spectrum")) return;
  syncSpectrumFields();
  markProjectDirty();
  scheduleSpectrumPreview();
});
$("btn-copy-spectrum").addEventListener("click", copySpectrumSettings);
$("spectra-upload").addEventListener("change", (e) =>
  uploadFiles(e.target.files).catch((err) => showError(err.message)).finally(() => { e.target.value = ""; }));
