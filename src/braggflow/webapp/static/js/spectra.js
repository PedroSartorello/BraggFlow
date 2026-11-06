// Aba Espectros: preparo (o mesmo para todos ou um por arquivo), gráfico,
// picos e vales e a evolução do vale entre arquivos.

import {
  $, checkFields, fmtNum, hintHtml, icon, markStale, plotSeparators, setHtml, setPlain, setReadout, setText,
  showError, showFixField, toCsv,
} from "./core.js";
import { onLanguageChange, t } from "./i18n.js";
import {
  baseName, commonSpectrumSettings, defaultSpectrumSettings, editedSpectrumSettings,
  projectSpectraPaths, referenceSpectra, shared, shortName, spectraCommon, spectraState,
  spectraStateFor, spectrumSettingsFor,
} from "./state.js";
import { PALETTE, plotFont, uploadFiles } from "./series.js";
import { numeroOuTraco } from "./analysis.js";
import { fileRow, markProjectDirty, renderEmptyFiles, renderFilePicker } from "./projects.js";
import { scheduleFigure, vizSource } from "./viz.js";

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
  setText($("transmission-state"), ref && dark ? "transmission.both"
    : ref ? "transmission.sourceOnly" : dark ? "transmission.darkOnly" : "transmission.unused");
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
    sel.add(new Option(t("common.none"), ""));
    [...new Set([...projectSpectraPaths(), ...disponiveis])]
      .filter((path) => path !== proprio)
      .forEach((path) => sel.add(new Option(shortName(path), path)));
    if (atual && ![...sel.options].some((o) => o.value === atual)) {
      sel.add(new Option(t("transmission.notFound", { name: baseName(atual) }), atual));   // escolhido antes, fora da lista
    }
    sel.value = atual;
  });
}

// ── Mesmo preparo para todos, ou um por arquivo ──────────────────────────────
function syncCommonMode() {
  $("spectra-common").checked = spectraCommon.on;
  setText($("spectra-prep-label"), spectraCommon.on ? "spectra.prepAll" : "spectra.prepSelected");
  $("btn-copy-spectrum").classList.toggle("hidden", spectraCommon.on);
  setText($("spectra-common-hint"), spectraCommon.on ? "spectra.commonHintOn" : "spectra.commonHintOff");
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
  setText($("spectra-status"), "spectra.prepApplied");
}

// Projeto trocado ou novo: preparo comum com os padrões, evolução padrão
export function resetSpectraProject() {
  spectraCommon.on = true;
  spectraCommon.settings = defaultSpectrumSettings();
  applyEvolutionOptions({});
  evolutionEvents = [];
  renderEventLists();
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
  evolutionEvents = (project.evolution_events || []).map((e) => ({ ...e }));
  renderEventLists();
  syncCommonMode();
  formTarget = null;
  showSpectrumSettings(shared.currentSpectrumFile);
}

// ── Arquivos do projeto ──────────────────────────────────────────────────────
const FILTRO_A_PARTIR_DE = 8;   // com mais arquivos que isso, a lista ganha um filtro

function fileNote(path, usados) {
  const st = spectraState[path];
  if (usados.has(path)) return t("spectra.noteReference");
  if (st.exclude) return t("spectra.noteExcluded");
  if (spectraCommon.on) return "";
  const s = st.settings || {};
  return s.reference_file ? t("spectra.noteTransmission") : s.smooth_window ? t("spectra.noteSmoothed") : "";
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
  if (!paths.length) box.innerHTML = hintHtml("spectra.noFiles");
  else if (!box.children.length) box.innerHTML = hintHtml("spectra.noMatch");

  const fora = paths.filter((path) => spectraState[path].exclude && !usados.has(path)).length;
  const nRef = paths.filter((path) => usados.has(path)).length;
  const partes = [t("spectra.count", { n: paths.length })];
  if (nRef) partes.push(t("spectra.countReference", { n: nRef }));
  if (fora) partes.push(t("spectra.countExcluded", { n: fora }));
  setPlain($("spectra-files-summary"), paths.length ? partes.join(" · ") : "");

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
  if (unit === "%") return t("transmission.percent");
  if (unit === "AU") return t("plot.absorbance");
  if (unit === "") return t("plot.transmission");
  return unit && unit !== "a.u." ? t("plot.intensityUnit", { unit }) : t("plot.intensity");
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
    x: trace.wavelength, y: trace.intensity, name: trace.label ?? trace.name, mode: "lines",
    line: { color: PALETTE[i % PALETTE.length], width: 1.2 },
  }));
  data.traces.forEach((trace, i) => {
    const cor = PALETTE[i % PALETTE.length];
    const extremos = trace.extrema || [];
    if (!extremos.length) return;
    traces.push({
      x: extremos.map((e) => e.wavelength), y: extremos.map((e) => e.intensity),
      mode: "markers", name: t("spectra.extremaTrace", { name: trace.label ?? trace.name }), showlegend: false,
      marker: {
        color: extremos.map((e) => (e.type === "max" ? "#c0392b" : "#1f6fb2")),
        symbol: extremos.map((e) => (e.type === "max" ? "triangle-up" : "triangle-down")),
        size: 9, line: { color: "#fff", width: 1 },
      },
      text: extremos.map((e) => t(e.type === "max" ? "spectra.maximum" : "spectra.minimum") +
        (e.fwhm ? ` · ${t("spectra.widthQ", { width: fmtNum(e.fwhm, 4), q: fmtNum(e.q, 0) })}` : "")),
      hovertemplate: "%{text}<br>λ = %{x:.4f} nm<br>I = %{y}<extra></extra>",
    });
    const xs = [], ys = [];
    extremos.filter((e) => e.fwhm).forEach((e) => {
      xs.push(e.left, e.right, null);
      ys.push(e.level, e.level, null);
    });
    if (xs.length) {
      traces.push({
        x: xs, y: ys, mode: "lines", name: t("spectra.widthTrace", { name: trace.label ?? trace.name }), showlegend: false,
        line: { color: cor, width: 1.5, dash: "dash" }, hoverinfo: "skip",
      });
    }
  });

  const acompanhados = trackedPoints(lastPreview.file);
  if (acompanhados.length) {
    traces.push({
      x: acompanhados.map((p) => p.wavelength), y: acompanhados.map((p) => p.intensity),
      mode: "markers", name: t("spectra.trackedName"), showlegend: false,
      marker: { symbol: "circle-open", size: 17, color: "#e67e22", line: { width: 2.5 } },
      hovertemplate: `${t("spectra.trackedHover")}<br>λ = %{x:.3f} nm<extra></extra>`,
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
    separators: plotSeparators(),
    margin: { l: 60, r: 20, t: 30, b: 45 },
    font: { family: plotFont(), size: 12.5, color: "#16212e" },
    xaxis: { title: t("plot.wavelengthAxis"), gridcolor: "#eceff3", zerolinecolor: "#e2e7ee" },
    yaxis: { title: intensityTitle(data.unit), gridcolor: "#eceff3", zerolinecolor: "#e2e7ee" },
    hovermode: "x unified",
    legend: { orientation: "h", y: 1.08 },
    showlegend: data.traces.length > 1,       // um traço só: a legenda não diz nada
    shapes, annotations,
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
  }, { responsive: true, displayModeBar: false });
  gd.removeAllListeners?.("plotly_click");
  gd.on("plotly_click", onSpectrumClick);
}

// ── Marcar o λ de referência clicando no vale ────────────────────────────────
let picking = false;

function setPicking(on) {
  picking = on;
  $("btn-evo-pick").classList.toggle("on", on);
  $("spectra-plot").classList.toggle("picking", on);
  if (on) setText($("spectra-status"), "spectra.pickHint");
  else if (lastPreview?.status) setReadout($("spectra-status"), lastPreview.status);
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
  if (!lastPreview) { showError(t("spectra.openToPick")); return; }
  setPicking(!picking);
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (picking) setPicking(false);
    if (markingEvents) setMarkingEvents(false);
    return;
  }
  // ← → percorrem os espectros (na ordem da evolução), fora dos campos de texto
  if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && !e.ctrlKey && !e.altKey && !e.metaKey
      && !$("tab-spectra-main").classList.contains("hidden")
      && !e.target.closest("input, select, textarea, [role=tab], [contenteditable]")) {
    e.preventDefault();
    stepSpectrum(e.key === "ArrowLeft" ? -1 : 1);
  }
});

// ── Picos e vales: tabela e resumo de cada traço ────────────────────────────
let spectraAnalysis = null;    // {file, traces} da última prévia

// Títulos no idioma de quando a tabela (ou o CSV) é montada
const SPECTRA_COLUNAS = (db) => [
  [t("peaks.col.trace"), (e) => e.trace],
  [t("peaks.col.type"), (e) => t(e.type === "max" ? "spectra.maximum" : "spectra.minimum")],
  ["λ (nm)", (e) => numeroOuTraco(e.wavelength, 4)],
  [t("peaks.col.fit"), (e) => numeroOuTraco(e.fit, 4)],
  [t("peaks.col.intensity"), (e) => numeroOuTraco(e.intensity, 4)],
  [t("peaks.col.prominence"), (e) => numeroOuTraco(e.prominence, 4)],
  [`${db ? t("peaks.band3db") : "FWHM"} (nm)`, (e) => numeroOuTraco(e.fwhm, 4)],
  ["Q", (e) => numeroOuTraco(e.q, 0)],
  [t("peaks.col.centroid"), (e) => numeroOuTraco(e.centroid, 4)],
  [t("peaks.col.spacing"), (e) => numeroOuTraco(e.spacing, 4)],
];

function spectraRows(data) {
  return data.traces.flatMap((traco) => (traco.extrema || []).map((e) => ({ ...e, trace: traco.label ?? traco.name })));
}

function renderSpectraResults(data, file) {
  const settings = spectrumSettingsFor(file);
  const ligado = Boolean(settings.find_max || settings.find_min);
  $("spectra-results").classList.toggle("hidden", !ligado);
  spectraAnalysis = ligado ? data : null;
  if (!ligado) return;

  const db = settings.intensity_scale === "db";
  const unidade = db ? " dB" : "";
  const colunas = SPECTRA_COLUNAS(db);

  // Resumo: uma linha por traço
  const resumo = $("spectra-summary");
  resumo.innerHTML = "";
  data.traces.forEach((traco) => {
    const r = traco.summary || {};
    const partes = [];
    if (r.global_max) partes.push(t("spectra.globalMax", { value: fmtNum(r.global_max.intensity, 4), wl: fmtNum(r.global_max.wavelength, 4) }));
    if (r.global_min) partes.push(t("spectra.globalMin", { value: fmtNum(r.global_min.intensity, 4), wl: fmtNum(r.global_min.wavelength, 4) }));
    if (r.side_lobe_suppression != null) partes.push(t("spectra.sideLobe", { value: fmtNum(r.side_lobe_suppression, 3), unit: unidade }));
    if (r.fsr_max != null) partes.push(t("spectra.fsrPeaks", { value: fmtNum(r.fsr_max, 4) }));
    if (r.fsr_min != null) partes.push(t("spectra.fsrValleys", { value: fmtNum(r.fsr_min, 4) }));
    if (r.resolution != null) partes.push(t("spectra.resolution", { value: fmtNum(r.resolution * 1000, 2) }));
    if (r.prominence != null) partes.push(t("spectra.prominenceAtLeast", { value: fmtNum(r.prominence, 4) }));
    const linha = document.createElement("span");
    const nome = document.createElement("b");
    nome.textContent = `${traco.label ?? traco.name}: ${t("spectra.peakCount", { n: r.n_max || 0 })}, ${t("spectra.valleyCount", { n: r.n_min || 0 })}`;
    linha.append(nome, document.createTextNode(partes.length ? " · " + partes.join(" · ") : ""));
    resumo.appendChild(linha);
  });

  // Tabela: um extremo por linha
  const tabela = $("spectra-table");
  tabela.innerHTML = "";
  const linhas = spectraRows(data);
  if (!linhas.length) {
    tabela.innerHTML = `<tr><td style="text-align:left">${t("spectra.noExtrema")}</td></tr>`;
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
  const colunas = SPECTRA_COLUNAS(db);
  const linhas = spectraRows(spectraAnalysis);
  return toCsv([colunas.map(([nome]) => nome), ...linhas.map((l) => colunas.map(([, valor]) => valor(l)))]);
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
  if (!csv) { showError(t("spectra.enableDetection")); return; }
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
  $("spec-order-field").title = sg ? "" : t("spectra.orderOnlySavgol");
}

let spectrumPreviewRequest = 0;
export async function previewSpectrum() {
  const file = shared.currentSpectrumFile;
  if (!file) return;
  saveCurrentSpectrumState();
  const request = ++spectrumPreviewRequest;
  setText($("spectra-status"), "spectra.reading");
  try {
    const resp = await fetch("/api/spectra/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file, settings: spectrumSettingsFor(file) }),
    });
    const data = await resp.json();
    // Outra prévia, outro arquivo ou outro projeto depois deste pedido: descarta
    if (request !== spectrumPreviewRequest || file !== shared.currentSpectrumFile) return;
    if (!resp.ok) throw new Error(data.error || t("spectra.readError"));
    showError("");
    const points = data.traces.reduce((total, trace) => total + trace.n_points, 0);
    const passo = data.traces[0]?.plot_stride;
    const quando = data.acquired?.replace("T", " ");
    // Montada de novo quando o idioma muda
    const status = () => ({
      partes: [
        [baseName(file), ""],
        [fmtNum(points, 0), t("spectra.points", { n: points })],
        data.traces.length > 1 ? [String(data.traces.length), t("spectra.traces")] : null,
        quando ? t(data.acquired_from === "filename" ? "spectra.recordedFromName" : "spectra.recorded", { when: quando }) : null,
        passo > 1 ? t("spectra.decimated", { stride: passo }) : null,
        spectraCommon.on && referenceSpectra().has(file) ? t("spectra.referenceAsIs") : null,
      ],
      estado: null,
    });
    lastPreview = { file, data, status };
    renderSpectraResults(data, file);
    renderSpectrumPlot();
    if (picking) setText($("spectra-status"), "spectra.pickHint");
    else setReadout($("spectra-status"), status);
  } catch (err) {
    if (request !== spectrumPreviewRequest) return;
    showError(err.message);
    setText($("spectra-status"), "common.failed", { msg: err.message });
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

// Janela da suavização pelos dados: validação cruzada no espectro aberto
async function chooseSmoothingFromData() {
  const file = shared.currentSpectrumFile;
  const nota = $("spec-smooth-auto-note");
  nota.classList.remove("hidden");
  if (!file) { setText(nota, "spectra.smoothAutoNoFile"); return; }
  saveCurrentSpectrumState();          // o que está no formulário vale, mesmo antes de virar prévia
  const botao = $("btn-spec-smooth-auto");
  botao.disabled = true;
  setText(nota, "savgol.autoBusy");
  try {
    const resp = await fetch("/api/spectra/smoothing-auto", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file, settings: spectrumSettingsFor(file) }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || t("savgol.autoError"));
    const campo = (nome) => document.querySelector(`#tab-spectra-sidebar [data-spec="${nome}"]`);
    campo("smooth_window").value = data.window;
    if (data.method === "savgol") campo("smooth_order").value = data.order;
    setText(nota, data.method === "savgol" ? "spectra.smoothAutoResultSg" : "spectra.smoothAutoResultMa",
            { window: data.window, order: data.order, nm: fmtNum(data.window_nm, 3) });
    ["input", "change"].forEach((tipo) => campo("smooth_window").dispatchEvent(new Event(tipo, { bubbles: true })));
  } catch (err) {
    setPlain(nota, err.message);
  } finally {
    botao.disabled = false;
  }
}
$("btn-spec-smooth-auto").addEventListener("click", () => chooseSmoothingFromData().catch((err) => showError(err.message)));
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
  if (markingEvents) setMarkingEvents(false);
  Plotly.purge($("evolution-plot"));
  $("evolution-table").innerHTML = "";
  setText($("evolution-table-summary"), "evo.table");
  setHtml($("evolution-status"), "evo.intro");
  setPlain($("evolution-state"), "");
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
    events: evolutionEventsList(),
  };
}

// O que muda o cálculo (os eixos e os eventos só mudam o gráfico)
const evolutionKey = (payload) => JSON.stringify({ ...payload, y: undefined, x: undefined, events: undefined });
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

function clearEvolution(key, vars) {
  evolution = null;
  syncEventTool();
  markStale("evolution-plot");
  $("evolution-status").classList.remove("status-error");
  Plotly.purge($("evolution-plot"));
  $("evolution-table").innerHTML = "";
  setText($("evolution-table-summary"), "evo.table");
  setText($("evolution-status"), key, vars);
  setPlain($("evolution-state"), "");
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
    clearEvolution(projectSpectraPaths().length ? "evo.needMore" : "evo.needTwo");
    return;
  }
  const invalido = checkFields($("spectra-evolution"));
  if (invalido) {        // nem vai ao servidor: o campo diz o que corrigir
    showFixField($("evolution-status"), invalido);
    if (evolution) markStale("evolution-plot", "stale.fixField");
    return;
  }
  if (payload.mode === "reference" && String(payload.reference).trim() === "") {
    clearEvolution("evo.markReference");
    return;
  }
  setText($("evolution-status"), "evo.calculating", { n: payload.items.length });
  try {
    const resp = await fetch("/api/spectra/evolution", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (request !== evolutionRequest) return;      // outro cálculo (ou projeto) veio depois
    if (!resp.ok) throw new Error(data.error || t("evo.error"));
    evolution = data;
    lastEvolutionKey = evolutionKey(payload);
    markStale("evolution-plot");
    $("evolution-status").classList.remove("status-error");
    showError("");
    if (data.x === "order") $("evo-x").value = "order";
    renderEvolution();
    renderSpectrumPlot();
  } catch (err) {
    if (request !== evolutionRequest) return;
    if (!evolution) { clearEvolution("common.failed", { msg: err.message }); return; }
    // O último resultado bom continua na tela, marcado como desatualizado
    setText($("evolution-status"), "common.failed", { msg: err.message });
    $("evolution-status").classList.add("status-error");
    markStale("evolution-plot", "stale.calculationFailed");
  }
}

// [chave do título do eixo, valor, casas]
const EVO_Y = {
  wavelength: ["evo.col.wavelength", (p) => p.wavelength, 4],
  delta: ["evo.col.delta", (p) => p.delta, 4],
  intensity: ["peaks.col.intensity", (p) => p.intensity, 4],
  prominence: ["peaks.col.prominence", (p) => p.prominence, 4],
  fwhm: ["evo.col.width", (p) => p.fwhm, 4],
};

function evolutionX(file) {
  return $("evo-x").value === "time" && evolution.x === "time" ? file.elapsed_s / 60 : file.index;
}

function renderEvolution() {
  if (!evolution) return;
  const [chaveRotulo, valor] = EVO_Y[$("evo-y").value];
  const rotulo = t(chaveRotulo);
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
      mode: "markers", name: t("evo.inFocus"), showlegend: false, hoverinfo: "skip",
      marker: { symbol: "circle-open", size: 15, color: "#e67e22", line: { width: 2.5 } },
    });
  }
  const eventos = eventPositions();
  const gd = $("evolution-plot");
  Plotly.react(gd, traces, {
    separators: plotSeparators(),
    margin: { l: 60, r: 20, t: eventos.length ? 44 : 30, b: 45 },
    // Um evento = uma linha e a sua legenda, nos mesmos índices (o arraste usa isso)
    shapes: eventos.map(({ x, e }) => ({
      type: "line", xref: "x", yref: "paper", x0: x, x1: x, y0: 0, y1: 1,
      line: { color: e.color, width: 1.5, dash: "dash" },
    })),
    annotations: eventos.map(({ x, e }) => ({
      x, y: 1, xref: "x", yref: "paper", yanchor: "bottom", showarrow: false,
      text: textoPlotly(e.label), font: { size: 11, color: e.color },
    })),
    font: { family: plotFont(), size: 12.5, color: "#16212e" },
    xaxis: { title: t(porTempo ? "evo.axisTime" : "evo.axisOrder"),
             gridcolor: "#eceff3", dtick: porTempo || n > 30 ? undefined : 1 },
    yaxis: { title: $("evo-y").value === "intensity" && evolution.unit ? `${rotulo} (${evolution.unit})` : rotulo,
             gridcolor: "#eceff3" },
    legend: { orientation: "h", y: eventos.length ? 1.16 : 1.1 },
    hovermode: "closest",
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
  }, { responsive: true, displayModeBar: false });
  gd.removeAllListeners?.("plotly_click");
  gd.on("plotly_click", (ev) => {
    const arquivo = ev.points?.[0]?.customdata;
    if (arquivo && arquivo !== shared.currentSpectrumFile) selectSpectrumFile(arquivo).catch((err) => showError(err.message));
  });

  const nome = t(evolution.kind === "min" ? "evo.valley" : "evo.peak");
  const partes = [t("evo.spectraCount", { n }), t("evo.trackCount", { n: evolution.tracks.length })];
  const principal = evolution.tracks[0]?.points.filter(Boolean) || [];
  if (evolution.tracks.length === 1 && principal.length > 1) {
    const total = principal[principal.length - 1].wavelength - principal[0].wavelength;
    partes.push(t("evo.totalShift", { value: fmtNum(total, 3) }));
  }
  if (evolution.tolerance != null) partes.push(t("evo.maxJump", { value: fmtNum(evolution.tolerance, 3) }));
  // Os avisos vêm do servidor, no idioma do pedido
  setPlain($("evolution-status"), [partes.join(" · "), ...evolution.warnings].join(" — "));
  setPlain($("evolution-state"), evolution.mode === "reference"
    ? t("evo.stateReference", { kind: nome, ref: fmtNum(evolution.reference, 2), n })
    : evolution.mode === "prominent" ? t("evo.stateProminent", { kind: nome, n })
    : t("evo.stateFollow", { tracks: evolution.tracks.length, n }));
  renderEvolutionTable();
  renderEvolutionFocus();
  renderEventLists();
  syncEventTool();
}

function evolutionRows() {
  const comVertice = evolution.locate && evolution.locate !== "vertex";
  return evolution.files.map((f, i) => {
    const linha = { [t("evo.col.file")]: baseName(f.file),
                    [t("evo.col.recorded")]: f.acquired ? f.acquired.replace("T", " ") : "—",
                    "t (min)": f.elapsed_s != null ? numeroOuTraco(f.elapsed_s / 60, 3) : "—" };
    evolution.tracks.forEach((trilha, j) => {
      const p = trilha.points[i];
      const sufixo = evolution.tracks.length > 1 ? ` · ${j + 1}` : "";
      linha[`${t("evo.col.wavelength")}${sufixo}`] = p ? numeroOuTraco(p.wavelength, 4) : "—";
      linha[`${t("evo.col.delta")}${sufixo}`] = p ? numeroOuTraco(p.delta, 4) : "—";
      linha[`${t("peaks.col.intensity")}${sufixo}`] = p ? numeroOuTraco(p.intensity, 4) : "—";
      linha[`${t("peaks.col.prominence")}${sufixo}`] = p ? numeroOuTraco(p.prominence, 4) : "—";
      linha[`${t("evo.col.width")}${sufixo}`] = p ? numeroOuTraco(p.fwhm, 4) : "—";
      if (comVertice) linha[`${t("evo.col.vertex")}${sufixo}`] = p ? numeroOuTraco(p.vertex, 4) : "—";
    });
    if (evolutionEvents.length && evolution.start) {
      // O último evento antes do espectro: em que meio (ou condição) ele foi gravado
      const antes = evolutionEvents.filter((e) => elapsedOf(e) <= f.elapsed_s);
      linha[t("evo.col.event")] = antes.length ? antes[antes.length - 1].label || t("evo.noLabel") : "—";
    }
    return linha;
  });
}

function renderEvolutionTable() {
  const linhas = evolutionRows();
  const tabelaEl = $("evolution-table");
  tabelaEl.innerHTML = "";
  setText($("evolution-table-summary"), "evo.tableRows", { n: linhas.length });
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
  if (usados.has(file)) texto += ` — ${t("evo.focusReference")}`;
  else if (st.exclude) texto += ` — ${t("spectra.noteExcluded")}`;
  else if (evolution) {
    const pontos = trackedPoints(file);
    texto += " · " + (pontos.length === 1
      ? `λ ${fmtNum(pontos[0].wavelength, 3)} nm · Δλ ${fmtNum(pontos[0].delta, 3)} nm`
      : pontos.length ? t("evo.focusTracked", { n: pontos.length })
      : t("evo.focusNone", { kind: t(evolution.kind === "min" ? "evo.valley" : "evo.peak") }));
  }
  $("evolution-focus-text").textContent = texto;
  const excluir = $("btn-evo-exclude");
  excluir.classList.toggle("hidden", usados.has(file));
  excluir.textContent = t(st.exclude ? "evo.restore" : "evo.exclude");
  const fora = projectSpectraPaths().filter((path) => spectraState[path].exclude && !usados.has(path)).length;
  $("btn-evo-restore").classList.toggle("hidden", fora === 0 || (fora === 1 && st.exclude));
  $("btn-evo-restore").textContent = t("evo.restoreAll", { n: fora });
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
  if (!evolution) { showError(t("evo.calculateFirst")); return; }
  const linhas = evolutionRows();
  const colunas = Object.keys(linhas[0]);
  baixarCsv(toCsv([colunas, ...linhas.map((l) => colunas.map((c) => l[c]))]), "evolucao_espectros.csv");
});

// ── Eventos da evolução: trocas de meio, injeções… ───────────────────────────
// Guardados pelo instante da aquisição (ISO, como os arquivos), não pelo tempo
// desde o 1º espectro: tirar o 1º da evolução não os faz andar. As contas são
// em UTC para não depender do fuso nem do horário de verão.
const EVENT_COLORS = ["#4682B4", "#2E8B57", "#8B008B", "#C0392B", "#D35400", "#7F8C8D"];
const EVENT_GRAB_PX = 6;
let evolutionEvents = [];   // [{at, label, color}], em ordem de tempo
let markingEvents = false;
let eventDrag = null;       // {indice, x}

export const evolutionEventsList = () => evolutionEvents.map((e) => ({ ...e }));

const textoPlotly = (t) => (t || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const instante = (iso) => Date.parse(`${iso}Z`);

function isoUtc(ms) {
  const d = new Date(ms);
  const p = (n, k = 2) => String(n).padStart(k, "0");
  return `${p(d.getUTCFullYear(), 4)}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())}T` +
    `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}.${p(d.getUTCMilliseconds(), 3)}`;
}

// Segundos desde o 1º espectro da evolução atual
const elapsedOf = (e) => (instante(e.at) - instante(evolution.start)) / 1000;
const isoOfElapsed = (s) => isoUtc(instante(evolution.start) + Math.round(s * 1000));

// Interpolação linear com as pontas presas (como np.interp)
function interp(v, xs, ys) {
  if (v <= xs[0]) return ys[0];
  if (v >= xs[xs.length - 1]) return ys[ys.length - 1];
  const i = xs.findIndex((x) => x >= v);
  const f = (v - xs[i - 1]) / (xs[i] - xs[i - 1] || 1);
  return ys[i - 1] + f * (ys[i] - ys[i - 1]);
}

// Eixo x do gráfico: minutos, ou o número do espectro (o evento fica entre o
// espectro de antes e o de depois)
const porMinuto = () => $("evo-x").value === "time";
function xOfElapsed(s) {
  if (porMinuto()) return s / 60;
  return interp(s, evolution.files.map((f) => f.elapsed_s), evolution.files.map((f) => f.index));
}
function elapsedOfX(x) {
  if (porMinuto()) return x * 60;
  return interp(x, evolution.files.map((f) => f.index), evolution.files.map((f) => f.elapsed_s));
}

function eventPositions() {
  if (!evolution?.start) return [];
  return evolutionEvents.map((e, i) => ({ e, i, x: xOfElapsed(elapsedOf(e)) }));
}

// Sem o instante de cada arquivo, não há onde pôr um evento
function syncEventTool() {
  const pode = Boolean(evolution?.start);
  $("btn-evo-event").disabled = !pode;
  document.querySelectorAll(".evo-event-add").forEach((b) => { b.disabled = !pode; });
  if (!pode && markingEvents) setMarkingEvents(false);
}

function setMarkingEvents(on) {
  markingEvents = on && Boolean(evolution?.start);
  $("btn-evo-event").classList.toggle("on", markingEvents);
  $("evolution-plot").classList.toggle("marking", markingEvents);
  setText($("evolution-events-hint"), markingEvents ? "evo.eventsHintMarking" : "evo.eventsHint");
}

// Posição do ponteiro no eixo x e o evento cuja linha está a até EVENT_GRAB_PX
function eventNear(ev) {
  const gd = $("evolution-plot");
  const xa = gd._fullLayout?.xaxis, ya = gd._fullLayout?.yaxis;
  if (!xa || !ya || !evolution?.start) return null;
  const r = gd.getBoundingClientRect();
  const px = ev.clientX - r.left - xa._offset, py = ev.clientY - r.top - ya._offset;
  if (px < 0 || px > xa._length || py < 0 || py > ya._length) return null;
  let alvo = null, menor = EVENT_GRAB_PX;
  eventPositions().forEach(({ x, i }) => {
    const d = Math.abs(xa.l2p(x) - px);
    if (d <= menor) { menor = d; alvo = i; }
  });
  return { x: xa.p2l(px), alvo };
}

function sortEvents() {
  evolutionEvents.sort((a, b) => instante(a.at) - instante(b.at));
}

// Algo mudou nos eventos: gráfico, tabela, as duas listas, projeto e figura
function eventsChanged({ listas = true } = {}) {
  sortEvents();
  markProjectDirty();
  if (evolution) renderEvolution();
  else if (listas) renderEventLists();
  if (vizSource() === "evolution") scheduleFigure();
}

function addEvent(elapsed) {
  const evento = { at: isoOfElapsed(elapsed), label: "",
                   color: EVENT_COLORS[evolutionEvents.length % EVENT_COLORS.length] };
  evolutionEvents.push(evento);
  eventsChanged();
  // A legenda é o que falta: o cursor já vai para ela
  const i = evolutionEvents.indexOf(evento);
  $("evolution-events").querySelectorAll(".event-label")[i]?.focus();
}

// "+ adicionar": no instante do espectro em foco (ou no fim da evolução)
document.querySelectorAll(".evo-event-add").forEach((botao) => botao.addEventListener("click", () => {
  if (!evolution?.start) { showError(t("evo.needAcquisitionTime")); return; }
  const foco = evolution.files.find((f) => f.file === shared.currentSpectrumFile);
  addEvent((foco || evolution.files[evolution.files.length - 1]).elapsed_s);
}));

$("btn-evo-event").addEventListener("click", () => setMarkingEvents(!markingEvents));

$("evolution-plot").addEventListener("mousedown", (ev) => {
  if (!markingEvents || ev.button !== 0) return;
  const perto = eventNear(ev);
  if (!perto) return;                 // fora da área dos eixos (legenda, título)
  ev.stopPropagation();               // nem zoom, nem abrir o espectro do ponto
  ev.preventDefault();                // (e o foco não sai do campo sozinho:)
  document.activeElement?.blur?.();   // a legenda recém-digitada é gravada antes
  if (perto.alvo !== null) eventDrag = { indice: perto.alvo, x: perto.x };
  else addEvent(elapsedOfX(perto.x));
}, true);

window.addEventListener("mousemove", (ev) => {
  const gd = $("evolution-plot");
  if (eventDrag) {
    const perto = eventNear(ev);
    if (!perto) return;
    eventDrag.x = perto.x;
    const i = eventDrag.indice;
    Plotly.relayout(gd, { [`shapes[${i}].x0`]: perto.x, [`shapes[${i}].x1`]: perto.x, [`annotations[${i}].x`]: perto.x });
    return;
  }
  if (markingEvents && gd.contains(ev.target)) gd.classList.toggle("near-event", eventNear(ev)?.alvo != null);
});

window.addEventListener("mouseup", () => {
  if (!eventDrag) return;
  const { indice, x } = eventDrag;
  eventDrag = null;
  evolutionEvents[indice].at = isoOfElapsed(elapsedOfX(x));
  eventsChanged();
});

// Hora digitada (HH:MM:SS): no dia do evento, ou no vizinho se cair mais
// perto da evolução (ensaio que passa da meia-noite)
function setEventClock(evento, valor) {
  const [h, m, s = "0"] = valor.split(":").map(Number);
  if (![h, m, s].every(Number.isFinite)) return;
  const d = new Date(instante(evento.at));
  let novo = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), h, m, Math.floor(s));
  if (evolution?.start) {
    const ini = instante(evolution.start);
    const fim = ini + 1000 * Math.max(...evolution.files.map((f) => f.elapsed_s ?? 0));
    const fora = (t) => (t < ini ? ini - t : t > fim ? t - fim : 0);
    const DIA = 864e5;
    [-DIA, DIA].forEach((passo) => { if (fora(novo + passo) < fora(novo)) novo += passo; });
  }
  evento.at = isoUtc(novo);
}

function eventRow(evento) {
  const row = document.createElement("div");
  row.className = "event-row";
  const hora = document.createElement("input");
  hora.type = "time"; hora.step = 1; hora.className = "event-time";
  hora.value = evento.at.slice(11, 19);
  hora.title = t("evo.eventTime");
  const legenda = document.createElement("input");
  legenda.type = "text"; legenda.className = "event-label"; legenda.value = evento.label;
  legenda.placeholder = t("evo.eventLabelPlaceholder");
  const cor = document.createElement("input");
  cor.type = "color"; cor.className = "color-input event-color"; cor.value = evento.color;
  cor.title = t("evo.eventColor");
  const quando = document.createElement("span");
  quando.className = "event-when";
  if (evolution?.start) quando.textContent = `${fmtNum(elapsedOf(evento) / 60, 2)} min`;
  const del = document.createElement("button");
  del.type = "button"; del.className = "marker-del"; del.append(icon("x"));
  del.title = t("evo.eventDelete");

  hora.addEventListener("change", () => { setEventClock(evento, hora.value); eventsChanged(); });
  hora.addEventListener("blur", () => setTimeout(renderEventLists));    // volta à ordem de tempo
  // Legenda e cor não mudam a ordem: a lista onde se digita fica como está
  legenda.addEventListener("change", () => { evento.label = legenda.value.trim(); eventsChanged({ listas: false }); });
  cor.addEventListener("change", () => { evento.color = cor.value; eventsChanged({ listas: false }); });
  del.addEventListener("click", () => {
    evolutionEvents.splice(evolutionEvents.indexOf(evento), 1);
    eventsChanged();
  });
  row.append(hora, legenda, cor, quando, del);
  return row;
}

// As duas listas (aba Espectros e cartão Dados da Figura), menos a que tem o
// foco: refazê-la tiraria o cursor do campo onde se está digitando
function renderEventLists() {
  ["evolution-events", "viz-evo-events"].forEach((id) => {
    const box = $(id);
    if (box.contains(document.activeElement) && box.children.length === evolutionEvents.length) return;
    box.innerHTML = "";
    evolutionEvents.forEach((evento) => box.appendChild(eventRow(evento)));
    if (!evolutionEvents.length) box.innerHTML = hintHtml("evo.noEvents");
  });
}

// ── Idioma trocado: o que esta aba desenha fora do HTML ─────────────────────
onLanguageChange(() => {
  renderSpectraFiles();                   // notas da lista, fonte e fundo
  syncSpectrumFields();
  renderEvolutionFocus();
  // Os nomes dos traços, os avisos e os nomes das trilhas vêm do servidor: pede de novo
  if (shared.currentSpectrumFile) previewSpectrum();
  if (evolution) runEvolution();
  else renderEventLists();
});
