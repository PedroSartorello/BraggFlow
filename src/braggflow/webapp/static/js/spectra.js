// Aba Espectros: preparo (o mesmo para todos ou um por arquivo), gráfico,
// picos e vales e a evolução do vale entre arquivos.

import { $, fmtNum, showError } from "./core.js";
import {
  baseName, commonSpectrumSettings, defaultSpectrumSettings, editedSpectrumSettings,
  projectSpectraPaths, referenceSpectra, shared, shortName, spectraCommon, spectraState,
  spectraStateFor, spectrumSettingsFor,
} from "./state.js";
import { PALETTE, plotFont, uploadFiles } from "./series.js";
import { numeroOuTraco } from "./analysis.js";
import { fileRow, markProjectDirty, renderEmptyFiles, renderFilePicker } from "./projects.js";

export async function openSpectraTab() {
  renderSpectraFiles();
  if (!shared.currentSpectrumFile && projectSpectraPaths().length) {
    await selectSpectrumFile(projectSpectraPaths()[0]);
  } else if (shared.currentSpectrumFile) {
    await previewSpectrum();
  }
  if ($("spectra-evolution").open && (!evolution || evolutionStale)) runEvolution();
}

// ── Preparo: o formulário da barra lateral ───────────────────────────────────
const COMUM = Symbol("preparo comum");
let formTarget = null;     // o que o formulário mostra: COMUM, um arquivo ou nada ainda

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
  $("card-transmission").open = syncTransmissionState();   // aberto só quando está em uso
}

// Põe no formulário o preparo que vale para `path` (o comum, no preparo comum)
function showSpectrumSettings(path) {
  fillSpectrumFileSelects();
  formTarget = spectraCommon.on ? COMUM : path || null;
  applySpectrumSettings(editedSpectrumSettings(path));
}

// Título do cartão: o que a conversão está usando (ou "não usada")
function syncTransmissionState() {
  const ref = document.querySelector('[data-spec="reference_file"]').value;
  const dark = document.querySelector('[data-spec="dark_file"]').value;
  $("transmission-state").textContent = ref && dark ? "fonte e fundo"
    : ref ? "só a fonte" : dark ? "só o fundo" : "não usada";
  return Boolean(ref || dark);
}

// Guarda o que está no formulário onde ele foi aberto (nunca num projeto
// que acabou de ser trocado, nem antes de o formulário ser preenchido)
export function saveCurrentSpectrumState() {
  if (formTarget === COMUM && spectraCommon.on) {
    spectraCommon.settings = collectSpectrumSettings();
  } else if (formTarget && formTarget !== COMUM && !spectraCommon.on && formTarget in spectraState) {
    spectraState[formTarget].settings = collectSpectrumSettings();
  }
}

// Fonte e fundo: qualquer espectro já enviado (no preparo por arquivo, menos o próprio)
function fillSpectrumFileSelects() {
  const disponiveis = shared.rawFiles.filter((f) => f.kind === "spectrum").map((f) => f.path);
  const proprio = spectraCommon.on ? null : shared.currentSpectrumFile;
  document.querySelectorAll(".spec-file-select").forEach((sel) => {
    const atual = sel.value;
    sel.innerHTML = "";
    sel.add(new Option("— nenhum —", ""));
    [...new Set([...projectSpectraPaths(), ...disponiveis])]
      .filter((path) => path !== proprio)
      .forEach((path) => sel.add(new Option(shortName(path), path)));
    if (atual && ![...sel.options].some((o) => o.value === atual)) {
      sel.add(new Option(`${baseName(atual)} (não encontrado)`, atual));   // escolhido antes, fora da lista
    }
    sel.value = atual;
  });
}

// ── Mesmo preparo para todos, ou um por arquivo ──────────────────────────────
function syncCommonMode() {
  $("spectra-common").checked = spectraCommon.on;
  $("spectra-prep-label").textContent = spectraCommon.on
    ? "Preparo de todos os espectros" : "Preparo do espectro selecionado";
  $("btn-copy-spectrum").classList.toggle("hidden", spectraCommon.on);
  $("spectra-common-hint").textContent = spectraCommon.on
    ? "Recorte, suavização e detecção valem para todos os arquivos do projeto. Desmarque para preparar cada arquivo de um jeito."
    : "Cada arquivo tem o seu próprio preparo; “Aplicar este preparo a todos” copia o do arquivo selecionado.";
}

// A fonte e o fundo não são convertidos com eles mesmos
const semAutoReferencia = (path, s) =>
  (path === s.reference_file || path === s.dark_file ? { ...s, reference_file: "", dark_file: "" } : s);

$("spectra-common").addEventListener("change", (e) => {
  saveCurrentSpectrumState();
  const atual = collectSpectrumSettings();
  spectraCommon.on = e.target.checked;
  if (spectraCommon.on) spectraCommon.settings = atual;
  else {
    projectSpectraPaths().forEach((path) => {
      spectraStateFor(path).settings = structuredClone(semAutoReferencia(path, atual));
    });
  }
  syncCommonMode();
  showSpectrumSettings(shared.currentSpectrumFile);
  renderSpectraFiles();
  markProjectDirty();
  scheduleSpectrumPreview();
  scheduleEvolution();
});

function copySpectrumSettings() {
  saveCurrentSpectrumState();
  const source = spectraState[shared.currentSpectrumFile];
  if (!source || spectraCommon.on) return;
  projectSpectraPaths().filter((path) => path !== shared.currentSpectrumFile).forEach((path) => {
    spectraStateFor(path).settings = structuredClone(semAutoReferencia(path, source.settings));
  });
  renderSpectraFiles();
  markProjectDirty();
  scheduleEvolution();
  $("spectra-status").textContent = "Preparo aplicado a todos os espectros.";
}

// Projeto trocado ou novo: preparo comum com os padrões, evolução padrão
export function resetSpectraProject() {
  spectraCommon.on = true;
  spectraCommon.settings = defaultSpectrumSettings();
  applyEvolutionOptions({});
  syncCommonMode();
  formTarget = null;
  showSpectrumSettings(null);
}

// Projeto aberto: preparo (comum ou por arquivo), arquivos fora da evolução
// e como acompanhar o vale
export function applySpectraProject(project) {
  const entradas = project.spectra_files || [];
  let comum = project.spectra_common;
  let preparo = project.spectra_settings;
  if (comum == null) {
    // Projeto de antes da opção: comum se os arquivos (menos fonte e fundo) têm o mesmo preparo
    const usados = new Set(entradas.flatMap((e) => [e.settings?.reference_file, e.settings?.dark_file]).filter(Boolean));
    const preparos = entradas.filter((e) => e.settings && !usados.has(e.file)).map((e) => JSON.stringify(e.settings));
    comum = new Set(preparos).size <= 1;
    preparo = preparo || (preparos.length ? JSON.parse(preparos[0]) : null);
  }
  spectraCommon.on = comum;
  spectraCommon.settings = { ...defaultSpectrumSettings(), ...(preparo || {}) };
  entradas.forEach((entrada) => {
    const st = spectraStateFor(entrada.file);
    st.settings = entrada.settings || structuredClone(semAutoReferencia(entrada.file, spectraCommon.settings));
    st.exclude = Boolean(entrada.exclude);
  });
  applyEvolutionOptions(project.evolution || {});
  syncCommonMode();
  formTarget = null;
  showSpectrumSettings(shared.currentSpectrumFile);
}

// ── Arquivos do projeto ──────────────────────────────────────────────────────
const FILTRO_A_PARTIR_DE = 8;   // com mais arquivos que isso, a lista ganha um filtro

function fileNote(path, usados) {
  const st = spectraState[path];
  if (usados.has(path)) return "fonte/fundo";
  if (st.exclude) return "fora da evolução";
  if (spectraCommon.on) return "";
  const s = st.settings || {};
  return s.reference_file ? "transmissão" : s.smooth_window ? "suavizado" : "";
}

export function renderSpectraFiles() {
  fillSpectrumFileSelects();
  const paths = projectSpectraPaths();
  const usados = referenceSpectra();
  const filtroEl = $("spectra-filter");
  filtroEl.classList.toggle("hidden", paths.length <= FILTRO_A_PARTIR_DE && !filtroEl.value);
  const filtro = filtroEl.value.trim().toLowerCase();

  const box = $("spectra-files");
  const fragment = document.createDocumentFragment();
  paths.filter((path) => !filtro || baseName(path).toLowerCase().includes(filtro)).forEach((path) => {
    const row = fileRow(path, {
      selected: path === shared.currentSpectrumFile, onSelect: selectSpectrumFile, note: fileNote(path, usados),
    });
    row.dataset.path = path;
    row.classList.toggle("excluded", Boolean(spectraState[path].exclude) && !usados.has(path));
    fragment.appendChild(row);
  });
  box.innerHTML = "";
  box.appendChild(fragment);
  if (!paths.length) box.innerHTML = '<span class="hint">Nenhum espectro neste projeto ainda.</span>';
  else if (!box.children.length) box.innerHTML = '<span class="hint">Nenhum espectro com esse nome.</span>';

  const fora = paths.filter((path) => spectraState[path].exclude && !usados.has(path)).length;
  const nRef = paths.filter((path) => usados.has(path)).length;
  const partes = [`${paths.length} espectro(s)`];
  if (nRef) partes.push(`${nRef} de fonte/fundo`);
  if (fora) partes.push(`${fora} fora da evolução`);
  $("spectra-files-summary").textContent = paths.length ? partes.join(" · ") : "";

  document.body.classList.toggle("no-spectra", !paths.length);
  renderEmptyFiles("spectrum");
  renderFilePicker("spectrum");
  if (evolutionSignature() !== evolutionFiles) scheduleEvolution();
}

function markSelectedRow(path) {
  document.querySelectorAll("#spectra-files .file-row").forEach((row) =>
    row.classList.toggle("selected", row.dataset.path === path));
}

export async function selectSpectrumFile(path) {
  if (!path) return;
  if (path !== shared.currentSpectrumFile) saveCurrentSpectrumState();
  const novo = !(path in spectraState);
  shared.currentSpectrumFile = path;
  spectraStateFor(path);
  showSpectrumSettings(path);
  if (novo) renderSpectraFiles();
  else markSelectedRow(path);
  renderEvolutionFocus();
  if (evolution) renderEvolution();          // o ponto em foco muda de lugar
  if (novo) markProjectDirty();
  await previewSpectrum();
}

// Vários arquivos de uma vez: a lista é desenhada uma vez e só um é aberto
export async function addSpectraToProject(paths) {
  const novos = paths.filter((path) => path && !(path in spectraState));
  novos.forEach((path) => spectraStateFor(path));
  if (!novos.length) return;
  renderSpectraFiles();
  const primeiro = projectSpectraPaths().find((path) => novos.includes(path));
  await selectSpectrumFile(shared.currentSpectrumFile && novos.length > 1 ? shared.currentSpectrumFile : primeiro);
}

function intensityTitle(unit) {
  if (unit === "%") return "Transmissão (%)";
  if (unit === "AU") return "Absorbância";
  if (unit === "") return "Transmissão";
  return unit && unit !== "a.u." ? `Intensidade (${unit})` : "Intensidade";
}

// ── Gráfico do espectro: extremos, λ de referência e o vale acompanhado ─────
let lastPreview = null;    // {file, data} da última prévia mostrada

function evoNumber(id) {
  const v = $(id).value.trim();
  return v === "" ? null : Number(v.replace(",", "."));
}

// Pontos da evolução no arquivo (um por trilha)
function trackedPoints(file) {
  const i = evolution ? evolution.files.findIndex((f) => f.file === file) : -1;
  return i < 0 ? [] : evolution.tracks.map((t) => t.points[i]).filter(Boolean);
}

// Onde a busca procurou neste arquivo: no λ de referência ou, seguindo a
// deriva, no vale encontrado no arquivo anterior
function searchCenter(file) {
  const ref = evoNumber("evo-ref");
  if (ref === null || !evolution || evolution.mode !== "reference" || !evolution.follow
      || evolution.reference !== ref) return ref;
  const i = evolution.files.findIndex((f) => f.file === file);
  let centro = ref;
  evolution.tracks[0].points.slice(0, Math.max(i, 0)).forEach((p) => { if (p) centro = p.vertex ?? p.wavelength; });
  return centro;
}

function renderSpectrumPlot() {
  if (!lastPreview || lastPreview.file !== shared.currentSpectrumFile) return;
  const { data } = lastPreview;
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

  const acompanhados = trackedPoints(lastPreview.file);
  if (acompanhados.length) {
    traces.push({
      x: acompanhados.map((p) => p.wavelength), y: acompanhados.map((p) => p.intensity),
      mode: "markers", name: "acompanhado", showlegend: false,
      marker: { symbol: "circle-open", size: 17, color: "#e67e22", line: { width: 2.5 } },
      hovertemplate: "vale acompanhado<br>λ = %{x:.3f} nm<extra></extra>",
    });
  }

  const shapes = [], annotations = [];
  const ref = evoNumber("evo-ref");
  if ($("evo-mode").value === "reference" && ref !== null && Number.isFinite(ref)) {
    const centro = searchCenter(lastPreview.file);
    const janela = evoNumber("evo-window");
    if (janela) {
      shapes.push({ type: "rect", xref: "x", yref: "paper", x0: centro - janela, x1: centro + janela,
                    y0: 0, y1: 1, fillcolor: "rgba(230, 126, 34, 0.08)", line: { width: 0 }, layer: "below" });
    }
    shapes.push({ type: "line", xref: "x", yref: "paper", x0: ref, x1: ref, y0: 0, y1: 1,
                  line: { color: "#e67e22", width: 1.5, dash: "dash" } });
    annotations.push({ x: ref, y: 1, xref: "x", yref: "paper", yanchor: "bottom", showarrow: false,
                       text: `λ ref ${fmtNum(ref, 2)}`, font: { size: 11, color: "#c0601a" } });
  }

  const gd = $("spectra-plot");
  Plotly.react(gd, traces, {
    separators: ",.",
    margin: { l: 60, r: 20, t: 30, b: 45 },
    font: { family: plotFont(), size: 12.5, color: "#16212e" },
    xaxis: { title: "Comprimento de onda (nm)", gridcolor: "#eceff3", zerolinecolor: "#e2e7ee" },
    yaxis: { title: intensityTitle(data.unit), gridcolor: "#eceff3", zerolinecolor: "#e2e7ee" },
    hovermode: "x unified",
    legend: { orientation: "h", y: 1.08 },
    shapes, annotations,
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
  }, { responsive: true });
  gd.removeAllListeners?.("plotly_click");
  gd.on("plotly_click", onSpectrumClick);
}

// ── Marcar o λ de referência clicando no vale ────────────────────────────────
let picking = false;

function setPicking(on) {
  picking = on;
  $("btn-evo-pick").classList.toggle("on", on);
  $("spectra-plot").classList.toggle("picking", on);
  $("spectra-status").textContent = on
    ? "Clique no vale que quer acompanhar · Esc cancela"
    : lastPreview?.status || $("spectra-status").textContent;
}

function onSpectrumClick(ev) {
  if (!picking) return;
  const gd = $("spectra-plot");
  const xa = gd._fullLayout?.xaxis;
  let lam = ev.points?.[0]?.x;
  if (xa && ev.event) {   // a posição do clique, não a do último hover
    const px = ev.event.clientX - gd.getBoundingClientRect().left - xa._offset;
    if (px >= 0 && px <= xa._length) lam = xa.p2l(px);
  }
  if (lam == null || !Number.isFinite(lam)) return;
  setReference(snapToExtremum(lam));
}

// O clique vai para o vale (ou pico) detectado mais próximo, a até 3% da
// faixa do espectro; sem nenhum, para o ponto mais baixo (ou mais alto) da
// curva por perto, se ele não estiver na borda dessa vizinhança
function snapToExtremum(lam) {
  const trace = lastPreview?.data?.traces?.[0];
  if (!trace) return lam;
  const kind = $("evo-kind").value;
  const xs = trace.wavelength;
  const raio = 0.03 * Math.abs(xs[xs.length - 1] - xs[0]);
  let melhor = null;
  (trace.extrema || []).filter((e) => e.type === kind).forEach((e) => {
    const d = Math.abs(e.wavelength - lam);
    if (d <= raio && (!melhor || d < melhor.d)) melhor = { d, lam: e.fit ?? e.wavelength };
  });
  if (melhor) return melhor.lam;

  let idx = -1, menor = Infinity, primeiro = -1, ultimo = -1;
  xs.forEach((x, i) => {
    const y = trace.intensity[i];
    if (x == null || y == null || Math.abs(x - lam) > raio) return;
    if (primeiro < 0) primeiro = i;
    ultimo = i;
    const v = kind === "min" ? y : -y;
    if (v < menor) { menor = v; idx = i; }
  });
  return idx > primeiro && idx < ultimo ? xs[idx] : lam;
}

function setReference(lam) {
  setPicking(false);
  $("evo-ref").value = Number(lam.toFixed(2));
  $("evo-mode").value = "reference";
  syncEvolutionFields();
  markProjectDirty();
  renderSpectrumPlot();
  if (!$("spectra-evolution").open) $("spectra-evolution").open = true;
  runEvolution();
}

$("btn-evo-pick").addEventListener("click", () => {
  if (!lastPreview) { showError("Abra um espectro para marcar o λ de referência no gráfico."); return; }
  setPicking(!picking);
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && picking) setPicking(false); });

// ── Picos e vales: tabela e resumo de cada traço ────────────────────────────
let spectraAnalysis = null;    // {file, traces} da última prévia

const SPECTRA_COLUNAS = (larguraNome) => [
  ["Traço", (t) => t.trace],
  ["Tipo", (e) => (e.type === "max" ? "máximo" : "mínimo")],
  ["λ (nm)", (e) => numeroOuTraco(e.wavelength, 4)],
  ["λ ajuste (nm)", (e) => numeroOuTraco(e.fit, 4)],
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

function renderSpectraResults(data, file) {
  const settings = spectrumSettingsFor(file);
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
  const db = spectrumSettingsFor(shared.currentSpectrumFile).intensity_scale === "db";
  const colunas = SPECTRA_COLUNAS(db ? "Banda 3 dB" : "FWHM");
  const linhas = spectraRows(spectraAnalysis);
  return [colunas.map(([nome]) => nome).join(";"),
          ...linhas.map((l) => colunas.map(([, valor]) => valor(l).replace(/—/, "")).join(";"))]
    .join("\n");
}

function baixarCsv(csv, nome) {
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nome;
  a.click();
  URL.revokeObjectURL(url);
}

$("btn-spectra-csv").addEventListener("click", () => {
  const csv = spectraCsv();
  if (!csv) { showError("Ligue a detecção de máximos ou mínimos antes de baixar."); return; }
  baixarCsv(csv, `${baseName(shared.currentSpectrumFile).replace(/\.[^.]+$/, "")}_picos_vales.csv`);
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
  const file = shared.currentSpectrumFile;
  if (!file) return;
  saveCurrentSpectrumState();
  const request = ++spectrumPreviewRequest;
  $("spectra-status").textContent = "Lendo espectro…";
  try {
    const resp = await fetch("/api/spectra/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file, settings: spectrumSettingsFor(file) }),
    });
    const data = await resp.json();
    // Outra prévia, outro arquivo ou outro projeto depois deste pedido: descarta
    if (request !== spectrumPreviewRequest || file !== shared.currentSpectrumFile) return;
    if (!resp.ok) throw new Error(data.error || "Erro ao ler o espectro.");
    showError("");
    const points = data.traces.reduce((total, trace) => total + trace.n_points, 0);
    const stride = data.traces[0]?.plot_stride > 1 ? ` (gráfico decimado 1:${data.traces[0].plot_stride})` : "";
    const quando = data.acquired
      ? ` · gravado ${data.acquired.replace("T", " ")}${data.acquired_from === "filename" ? " (hora do nome)" : ""}`
      : "";
    const papel = spectraCommon.on && referenceSpectra().has(file) ? " · fonte/fundo: mostrado sem conversão" : "";
    const status = `${shortName(file)} · ${data.traces.length} traço(s) · ` +
      `${points.toLocaleString("pt-BR")} pontos${stride}${quando}${papel}`;
    lastPreview = { file, data, status };
    renderSpectraResults(data, file);
    renderSpectrumPlot();
    $("spectra-status").textContent = picking ? "Clique no vale que quer acompanhar · Esc cancela" : status;
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
  if (e.target.matches("#spectra-upload, #spectra-upload-dir, .pick-spectrum, .list-filter, #spectra-common")) return;
  syncSpectrumFields();
  syncTransmissionState();
  saveCurrentSpectrumState();
  if (e.target.matches(".spec-file-select")) renderSpectraFiles();   // fonte e fundo saem da evolução
  markProjectDirty();
  scheduleSpectrumPreview();
  scheduleEvolution();     // o preparo mudou: a evolução também
});
$("btn-copy-spectrum").addEventListener("click", copySpectrumSettings);
$("spectra-filter").addEventListener("input", renderSpectraFiles);
$("spectrum-picker-filter").addEventListener("input", () => renderFilePicker("spectrum"));
["spectra-upload", "spectra-upload-dir"].forEach((id) => $(id).addEventListener("change", (e) =>
  uploadFiles(e.target.files).catch((err) => showError(err.message)).finally(() => { e.target.value = ""; })));

// ── Evolução entre arquivos ──────────────────────────────────────────────────
let evolution = null;      // última resposta de /api/spectra/evolution
let evolutionRequest = 0;  // descarta respostas de cálculos anteriores (ou de outro projeto)
let evolutionFiles = "";   // arquivos usados no cálculo atual
let evolutionStale = true; // algo mudou com o cartão fechado ou a aba escondida
let evolutionTimer = null;
const EVOLUTION_HINT = $("evolution-status").innerHTML;

export const currentEvolution = () => evolution;

// Projeto trocado ou fechado: nada do anterior fica na tela
export function resetSpectraAnalyses() {
  evolutionRequest++;
  spectrumPreviewRequest++;        // uma prévia ainda no caminho não volta para a tela
  clearTimeout(evolutionTimer);
  clearTimeout(spectrumTimer);
  evolution = null;
  evolutionStale = true;
  evolutionFiles = "";
  lastPreview = null;
  if (picking) setPicking(false);
  Plotly.purge($("evolution-plot"));
  $("evolution-table").innerHTML = "";
  $("evolution-table-summary").textContent = "Tabela";
  $("evolution-status").innerHTML = EVOLUTION_HINT;
  $("evolution-state").textContent = "";
  $("evolution-focus").classList.add("hidden");
  spectraAnalysis = null;
  $("spectra-summary").innerHTML = "";
  $("spectra-table").innerHTML = "";
  $("spectra-results").classList.add("hidden");
}

// Como acompanhar: os campos [data-evo] do cartão
export function evolutionOptions() {
  const opcoes = {};
  document.querySelectorAll("#spectra-evolution [data-evo]").forEach((el) => {
    opcoes[el.dataset.evo] = el.type === "checkbox" ? el.checked : el.value;
  });
  return opcoes;
}

export function applyEvolutionOptions(opcoes) {
  const padrao = shared.figureOptions?.evolution || {};
  document.querySelectorAll("#spectra-evolution [data-evo]").forEach((el) => {
    const valor = opcoes?.[el.dataset.evo] ?? padrao[el.dataset.evo];
    if (el.type === "checkbox") el.checked = valor ?? true;
    else el.value = valor ?? "";
    if (el.tagName === "SELECT" && el.selectedIndex < 0) el.selectedIndex = 0;
  });
  $("viz-evo-y").value = $("evo-y").value;
  syncEvolutionFields();
}

export function setEvolutionY(valor) {
  $("evo-y").value = valor;
  markProjectDirty();
  renderEvolution();
}

// Mostra só os campos do modo escolhido
function syncEvolutionFields() {
  const modo = $("evo-mode").value;
  document.querySelectorAll("#spectra-evolution .only-reference")
    .forEach((el) => el.classList.toggle("hidden", modo !== "reference"));
  document.querySelectorAll("#spectra-evolution .only-follow")
    .forEach((el) => el.classList.toggle("hidden", modo !== "follow"));
}

// Os espectros da evolução: os do projeto, menos fonte, fundo e os tirados
function evolutionItems() {
  const fora = referenceSpectra();
  return projectSpectraPaths()
    .filter((path) => !fora.has(path) && !spectraState[path]?.exclude)
    .map((path) => (spectraCommon.on ? { file: path } : { file: path, settings: spectraState[path].settings }));
}

const evolutionSignature = () => evolutionItems().map((i) => i.file).join("|");

export function evolutionPayload() {
  saveCurrentSpectrumState();
  return {
    items: evolutionItems(),
    ...(spectraCommon.on ? { settings: commonSpectrumSettings() } : {}),
    ...evolutionOptions(),
  };
}

// O que muda o cálculo (o eixo y e o x só mudam o gráfico)
const evolutionKey = (payload) => JSON.stringify({ ...payload, y: undefined, x: undefined });
let lastEvolutionKey = "";

function scheduleEvolution() {
  clearTimeout(evolutionTimer);
  evolutionStale = true;
  if (!$("spectra-evolution").open || $("tab-spectra-main").classList.contains("hidden")) return;
  evolutionTimer = setTimeout(() => runEvolution(), 500);
}

// A evolução atual, calculada de novo se algo mudou (para a figura)
export async function ensureEvolution() {
  if (!evolution || evolutionStale || evolutionKey(evolutionPayload()) !== lastEvolutionKey) await runEvolution();
  return evolution;
}

function clearEvolution(mensagem) {
  evolution = null;
  Plotly.purge($("evolution-plot"));
  $("evolution-table").innerHTML = "";
  $("evolution-table-summary").textContent = "Tabela";
  $("evolution-status").textContent = mensagem;
  $("evolution-state").textContent = "";
  renderEvolutionFocus();
  renderSpectrumPlot();
}

async function runEvolution() {
  clearTimeout(evolutionTimer);
  const request = ++evolutionRequest;
  const payload = evolutionPayload();
  evolutionFiles = payload.items.map((i) => i.file).join("|");
  evolutionStale = false;
  if (payload.items.length < 2) {
    clearEvolution(projectSpectraPaths().length
      ? "Adicione mais espectros ao projeto: a evolução precisa de dois ou mais (fonte, fundo e os tirados não contam)."
      : "Adicione dois ou mais espectros ao projeto para ver a evolução.");
    return;
  }
  if (payload.mode === "reference" && String(payload.reference).trim() === "") {
    clearEvolution("Marque o λ de referência: “Marcar no gráfico” e clique no vale do espectro acima, ou digite o valor.");
    return;
  }
  $("evolution-status").textContent = `Calculando ${payload.items.length} espectros…`;
  try {
    const resp = await fetch("/api/spectra/evolution", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (request !== evolutionRequest) return;      // outro cálculo (ou projeto) veio depois
    if (!resp.ok) throw new Error(data.error || "Erro ao calcular a evolução.");
    evolution = data;
    lastEvolutionKey = evolutionKey(payload);
    showError("");
    if (data.x === "order") $("evo-x").value = "order";
    renderEvolution();
    renderSpectrumPlot();
  } catch (err) {
    if (request !== evolutionRequest) return;
    clearEvolution(`Falha: ${err.message}`);
  }
}

const EVO_Y = {
  wavelength: ["λ (nm)", (p) => p.wavelength, 4],
  delta: ["Δλ (nm)", (p) => p.delta, 4],
  intensity: ["Intensidade", (p) => p.intensity, 4],
  prominence: ["Proeminência", (p) => p.prominence, 4],
  fwhm: ["Largura (nm)", (p) => p.fwhm, 4],
};

function evolutionX(file) {
  return $("evo-x").value === "time" && evolution.x === "time" ? file.elapsed_s / 60 : file.index;
}

function renderEvolution() {
  if (!evolution) return;
  const [rotulo, valor] = EVO_Y[$("evo-y").value];
  const porTempo = $("evo-x").value === "time" && evolution.x === "time";
  const n = evolution.files.length;
  const textos = evolution.files.map((f) => `${baseName(f.file)}${f.acquired ? " · " + f.acquired.replace("T", " ") : ""}`);
  const arquivos = evolution.files.map((f) => f.file);
  const traces = evolution.tracks.map((trilha, i) => ({
    x: evolution.files.map(evolutionX),
    y: trilha.points.map((p) => (p ? valor(p) : null)),
    name: trilha.name, mode: "lines+markers", connectgaps: false,
    line: { color: PALETTE[i % PALETTE.length], width: 1.5 },
    marker: { size: n > 150 ? 4 : 7 },
    text: textos, customdata: arquivos,
    hovertemplate: "%{text}<br>%{y:.4f}<extra>%{fullData.name}</extra>",
  }));
  // O espectro em foco (o do gráfico de cima), destacado
  const i = arquivos.indexOf(shared.currentSpectrumFile);
  if (i >= 0) {
    const pontos = evolution.tracks.map((t) => t.points[i]).filter(Boolean);
    traces.push({
      x: pontos.map(() => evolutionX(evolution.files[i])), y: pontos.map(valor),
      mode: "markers", name: "em foco", showlegend: false, hoverinfo: "skip",
      marker: { symbol: "circle-open", size: 15, color: "#e67e22", line: { width: 2.5 } },
    });
  }
  const gd = $("evolution-plot");
  Plotly.react(gd, traces, {
    separators: ",.",
    margin: { l: 60, r: 20, t: 30, b: 45 },
    font: { family: plotFont(), size: 12.5, color: "#16212e" },
    xaxis: { title: porTempo ? "Tempo desde o 1º arquivo (min)" : "Arquivo (ordem)",
             gridcolor: "#eceff3", dtick: porTempo || n > 30 ? undefined : 1 },
    yaxis: { title: $("evo-y").value === "intensity" && evolution.unit ? `${rotulo} (${evolution.unit})` : rotulo,
             gridcolor: "#eceff3" },
    legend: { orientation: "h", y: 1.1 },
    hovermode: "closest",
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
  }, { responsive: true });
  gd.removeAllListeners?.("plotly_click");
  gd.on("plotly_click", (ev) => {
    const arquivo = ev.points?.[0]?.customdata;
    if (arquivo && arquivo !== shared.currentSpectrumFile) selectSpectrumFile(arquivo).catch((err) => showError(err.message));
  });

  const nome = evolution.kind === "min" ? "vale" : "pico";
  const partes = [`${n} espectro(s)`, `${evolution.tracks.length} trilha(s)`];
  const principal = evolution.tracks[0]?.points.filter(Boolean) || [];
  if (evolution.tracks.length === 1 && principal.length > 1) {
    const total = principal[principal.length - 1].wavelength - principal[0].wavelength;
    partes.push(`Δλ do 1º ao último ${fmtNum(total, 3)} nm`);
  }
  if (evolution.tolerance != null) partes.push(`salto máximo ${fmtNum(evolution.tolerance, 3)} nm`);
  $("evolution-status").textContent = [partes.join(" · "), ...evolution.warnings].join(" — ");
  $("evolution-state").textContent = evolution.mode === "reference"
    ? `${nome} perto de ${fmtNum(evolution.reference, 2)} nm · ${n} espectros`
    : `${evolution.mode === "prominent" ? `${nome} mais proeminente` : `${evolution.tracks.length} trilhas`} · ${n} espectros`;
  renderEvolutionTable();
  renderEvolutionFocus();
}

function evolutionRows() {
  const comVertice = evolution.locate && evolution.locate !== "vertex";
  return evolution.files.map((f, i) => {
    const linha = { Arquivo: baseName(f.file), "Gravado": f.acquired ? f.acquired.replace("T", " ") : "—",
                    "t (min)": f.elapsed_s != null ? numeroOuTraco(f.elapsed_s / 60, 3) : "—" };
    evolution.tracks.forEach((trilha, j) => {
      const p = trilha.points[i];
      const sufixo = evolution.tracks.length > 1 ? ` · ${j + 1}` : "";
      linha[`λ (nm)${sufixo}`] = p ? numeroOuTraco(p.wavelength, 4) : "—";
      linha[`Δλ (nm)${sufixo}`] = p ? numeroOuTraco(p.delta, 4) : "—";
      linha[`Intensidade${sufixo}`] = p ? numeroOuTraco(p.intensity, 4) : "—";
      linha[`Proeminência${sufixo}`] = p ? numeroOuTraco(p.prominence, 4) : "—";
      linha[`Largura (nm)${sufixo}`] = p ? numeroOuTraco(p.fwhm, 4) : "—";
      if (comVertice) linha[`λ vértice (nm)${sufixo}`] = p ? numeroOuTraco(p.vertex, 4) : "—";
    });
    return linha;
  });
}

function renderEvolutionTable() {
  const linhas = evolutionRows();
  const tabelaEl = $("evolution-table");
  tabelaEl.innerHTML = "";
  $("evolution-table-summary").textContent = `Tabela (${linhas.length} linhas)`;
  if (!linhas.length) return;
  const colunas = Object.keys(linhas[0]);
  const cabeca = tabelaEl.createTHead().insertRow();
  colunas.forEach((nome) => {
    const th = document.createElement("th");
    th.textContent = nome;
    cabeca.appendChild(th);
  });
  const corpo = tabelaEl.createTBody();
  linhas.forEach((linha) => {
    const tr = corpo.insertRow();
    colunas.forEach((nome) => { tr.insertCell().textContent = linha[nome]; });
  });
}

// O espectro em foco: o que a evolução achou nele, tirar ou devolver
function renderEvolutionFocus() {
  const file = shared.currentSpectrumFile;
  const box = $("evolution-focus");
  if (!file || !(file in spectraState)) { box.classList.add("hidden"); return; }
  box.classList.remove("hidden");
  const usados = referenceSpectra();
  const st = spectraState[file];
  let texto = baseName(file);
  if (usados.has(file)) texto += " — fonte/fundo, fora da evolução";
  else if (st.exclude) texto += " — fora da evolução";
  else if (evolution) {
    const pontos = trackedPoints(file);
    texto += pontos.length === 1
      ? ` · λ ${fmtNum(pontos[0].wavelength, 3)} nm · Δλ ${fmtNum(pontos[0].delta, 3)} nm`
      : pontos.length ? ` · ${pontos.length} extremos acompanhados` : ` · sem ${evolution.kind === "min" ? "vale" : "pico"} acompanhado`;
  }
  $("evolution-focus-text").textContent = texto;
  const excluir = $("btn-evo-exclude");
  excluir.classList.toggle("hidden", usados.has(file));
  excluir.textContent = st.exclude ? "Devolver à evolução" : "Tirar da evolução";
  const fora = projectSpectraPaths().filter((path) => spectraState[path].exclude && !usados.has(path)).length;
  $("btn-evo-restore").classList.toggle("hidden", fora === 0 || (fora === 1 && st.exclude));
  $("btn-evo-restore").textContent = `Devolver todos (${fora} fora)`;
}

function stepSpectrum(passo) {
  const ordem = evolution ? evolution.files.map((f) => f.file) : projectSpectraPaths();
  const i = ordem.indexOf(shared.currentSpectrumFile);
  const alvo = ordem[i < 0 ? 0 : Math.min(ordem.length - 1, Math.max(0, i + passo))];
  if (alvo && alvo !== shared.currentSpectrumFile) selectSpectrumFile(alvo).catch((err) => showError(err.message));
}

function setExcluded(paths, fora) {
  paths.forEach((path) => { if (path in spectraState) spectraState[path].exclude = fora; });
  markProjectDirty();
  renderSpectraFiles();
  renderEvolutionFocus();
  runEvolution();
}

$("btn-evo-exclude").addEventListener("click", () => {
  const file = shared.currentSpectrumFile;
  if (file in spectraState) setExcluded([file], !spectraState[file].exclude);
});
$("btn-evo-restore").addEventListener("click", () => setExcluded(projectSpectraPaths(), false));
$("btn-evo-prev").addEventListener("click", () => stepSpectrum(-1));
$("btn-evo-next").addEventListener("click", () => stepSpectrum(1));

$("btn-evolution").addEventListener("click", () => runEvolution());
$("spectra-evolution").addEventListener("change", (e) => {
  const campo = e.target.dataset?.evo;
  if (!campo) return;
  if (campo === "reference" && e.target.value.trim() !== "") $("evo-mode").value = "reference";
  syncEvolutionFields();
  markProjectDirty();
  if (campo === "y" || campo === "x") {
    $("viz-evo-y").value = $("evo-y").value;
    renderEvolution();
    return;
  }
  if (["mode", "reference", "window"].includes(campo)) renderSpectrumPlot();
  scheduleEvolution();
});
$("spectra-evolution").addEventListener("toggle", () => {
  if ($("spectra-evolution").open && (!evolution || evolutionStale)) runEvolution();
});
$("btn-evolution-csv").addEventListener("click", () => {
  if (!evolution) { showError("Calcule a evolução antes de baixar."); return; }
  const linhas = evolutionRows();
  const colunas = Object.keys(linhas[0]);
  baixarCsv([colunas.join(";"),
             ...linhas.map((l) => colunas.map((c) => String(l[c]).replace(/—/, "")).join(";"))].join("\n"),
            "evolucao_espectros.csv");
});
