// Aba Figura: fontes de dados, estilo por canal, estilos salvos,
// marcações, geração e download da figura.

import { $, fmtNum, showError } from "./core.js";
import { baseName, projectSeriesPaths, projectSpectraPaths, shared, shortName, spectraStateFor } from "./state.js";
import { makeInput, plotDecorations } from "./series.js";
import { saveCurrentSpectrumState } from "./spectra.js";
import { scheduleAnalysis } from "./analysis.js";
import { applyVizChannelSelection, markProjectDirty } from "./projects.js";

// ── Aba Figura ─────────────────────────────────────────────────────────
let lastFigureInfo = null;       // tamanho da última figura gerada
let figureRequest = 0;           // descarta respostas de edições anteriores
export const channelStyleMemory = {};   // estilo por canal, preservado entre CSVs

const STYLE_STORAGE_KEY = "braggflow.figureStyle";
const FIGURE_PRESETS = {
  ieee1: { unit: "cm", width: 8.89, height: "", font_size: 8 },
  ieee2: { unit: "cm", width: 18.19, height: "", font_size: 9 },
  els1: { unit: "cm", width: 9, height: "", font_size: 8 },
  els2: { unit: "cm", width: 19, height: "", font_size: 9 },
  a4: { unit: "cm", width: 16, height: "", font_size: 11 },
  slide: { unit: "cm", width: 25.4, height: 14.29, font_size: 16 },
};
const LINESTYLE_LABELS = { "": "auto", "-": "——", "--": "– –", "-.": "–·–", ":": "···", none: "sem" };
const MARKER_LABELS = {
  "": "auto", none: "sem", o: "●", s: "■", "^": "▲", v: "▼", D: "◆",
  x: "✕", "+": "+", "*": "★", P: "✚", X: "✖", h: "⬢", ".": "·",
};

const styleInput = (path) => document.querySelector(`[data-style="${path}"]`);
export const vizSource = () => $("viz-source").value;

// Mostra só os campos que fazem sentido para a fonte escolhida
export function applySourceMode() {
  const spectra = vizSource() === "spectra";
  document.querySelectorAll("#tab-viz-sidebar .only-timeseries")
    .forEach((el) => el.classList.toggle("hidden", spectra));
  document.querySelectorAll("#tab-viz-sidebar .only-spectra")
    .forEach((el) => el.classList.toggle("hidden", !spectra));
  $("marker-hint").textContent = spectra
    ? "λ (nm) · legenda · cor"
    : "t (s, na escala do CSV) · legenda · cor";
  $("viz-data-hint").textContent = spectra
    ? "Cada traço do arquivo vira uma curva. Limites de X em nm; recorte, suavização e normalização vêm da aba Espectros."
    : "Marque os CSVs processados e escolha as curvas no cartão Curvas. Limites de X na unidade escolhida.";
  document.querySelectorAll(".marker-time").forEach((el) => {
    el.placeholder = spectra ? "λ (nm)" : "t (s)";
  });
}

// Uma curva por traço de cada arquivo marcado
let spectrumRequest = 0;
async function loadSpectrumCurves() {
  const box = $("viz-channels");
  const files = [...document.querySelectorAll(".viz-spectrum-source:checked")].map((c) => c.value);
  const request = ++spectrumRequest;   // marcar vários arquivos dispara várias chamadas
  rememberChannelStyles();

  if (!files.length) {
    shared.spectrumCurves = {};
    box.innerHTML = '<span class="hint">Marque um ou mais arquivos de espectro.</span>';
    return;
  }

  const curves = {};
  const fragment = document.createDocumentFragment();
  let index = 0;
  for (const file of files) {
    const resp = await fetch("/api/spectra/traces?file=" + encodeURIComponent(file));
    const data = await resp.json();
    if (request !== spectrumRequest) return;   // já houve outra mudança
    if (!resp.ok) { showError(data.error || "Erro ao ler o espectro."); continue; }
    data.traces.forEach((trace) => {
      curves[trace.key] = { file, trace: trace.name };
      fragment.appendChild(channelRow(
        trace.key, index++,
        `${trace.n_points.toLocaleString("pt-BR")} pts · ${trace.range[0]}–${trace.range[1]} nm`));
    });
  }
  shared.spectrumCurves = curves;
  box.innerHTML = "";
  box.appendChild(fragment);
  applyVizChannelSelection();
}

export async function refreshVizCurves() {
  if (vizSource() === "spectra") await loadSpectrumCurves();
  else await loadSeriesCurves();
  refreshStyleState();
}

// Recarrega a lista a cada entrada na aba; se houve processamento novo,
// seleciona o CSV gerado e já desenha a figura.
export async function openVizTab() {
  const pending = shared.vizPendingFile;
  shared.vizPendingFile = null;
  await loadVizSources(pending);
  await refreshVizCurves();
  if (document.querySelectorAll(".viz-channel:checked").length) generateFigure();
}

function sourceRow(className, path, checked) {
  const label = document.createElement("label");
  label.className = "check-row";
  const cb = document.createElement("input");
  cb.type = "checkbox"; cb.className = className; cb.value = path; cb.checked = checked;
  label.append(cb, document.createTextNode(baseName(path)));
  label.title = path;
  return label;
}

// Lista os CSVs processados e os arquivos de espectro que podem virar curvas
export async function loadVizSources(pending) {
  const marked = (className) =>
    new Set([...document.querySelectorAll(`.${className}:checked`)].map((c) => c.value));

  try {
    const projeto = $("project-name").value.trim();
    const resp = await fetch("/api/processed?project=" + encodeURIComponent(projeto));
    const data = await resp.json();
    const checked = marked("viz-series-source");
    if (pending) checked.add(pending);
    // Só os CSVs dos arquivos que estão no projeto, inclusive o de uma junção
    const doProjeto = new Set();
    projectSeriesPaths().forEach((path) => {
      const stem = shortName(path).split("/").pop().replace(/\.[^.]+$/, "");
      doProjeto.add(`${data.folder}/${stem}_processado.csv`);
      doProjeto.add(`${data.folder}/${stem}_juntos_processado.csv`);
    });
    const arquivos = data.files.filter((f) => doProjeto.has(f));
    const box = $("viz-series-sources");
    box.innerHTML = "";
    arquivos.forEach((f) => box.appendChild(sourceRow("viz-series-source", f, checked.has(f))));
    if (!arquivos.length) {
      box.innerHTML = '<span class="hint">Processe os arquivos na aba Séries temporais.</span>';
    }
  } catch (err) {
    showError(err.message);
  }

  const checkedSpectra = marked("viz-spectrum-source");
  const box = $("viz-spectra-sources");
  box.innerHTML = "";
  projectSpectraPaths().forEach((path) =>
    box.appendChild(sourceRow("viz-spectrum-source", path, checkedSpectra.has(path))));
  if (!box.children.length) {
    box.innerHTML = '<span class="hint">Adicione espectros ao projeto na aba Espectros.</span>';
  }
}

// ── Estilo por canal ─────────────────────────────────────────────────────────
function makeSelect(className, labels, value) {
  const sel = document.createElement("select");
  sel.className = className;
  Object.entries(labels).forEach(([v, text]) => sel.add(new Option(text, v)));
  sel.value = value ?? "";
  return sel;
}

function currentPalette() {
  return shared.figureOptions?.palettes?.[$("viz-palette").value] || ["#000000"];
}

function channelRow(ch, index, note, defaultVisible = true) {
  const saved = channelStyleMemory[ch] || {};
  const palette = currentPalette();

  const row = document.createElement("div");
  row.className = "viz-ch-row";
  row.dataset.channel = ch;

  const head = document.createElement("label");
  head.className = "viz-ch-head";
  const visible = document.createElement("input");
  visible.type = "checkbox"; visible.className = "viz-channel"; visible.value = ch;
  visible.checked = saved.visible ?? defaultVisible;
  const name = document.createElement("span");
  name.textContent = ch;
  const unitSpan = document.createElement("span");
  unitSpan.className = "unit";
  unitSpan.textContent = note || "";
  head.append(visible, name, unitSpan);

  const color = document.createElement("input");
  color.type = "color"; color.className = "color-input ch-color";
  color.value = saved.color || palette[index % palette.length];
  color.title = "Cor da curva";

  const label = makeInput("text", "ch-label", saved.label ?? "", ch);
  label.title = "Texto na legenda";
  const linestyle = makeSelect("ch-linestyle", LINESTYLE_LABELS, saved.linestyle);
  linestyle.title = "Estilo da linha";
  const marker = makeSelect("ch-marker", MARKER_LABELS, saved.marker);
  marker.title = "Marcador";

  row.append(head, label, linestyle, marker, color);
  return row;
}

export function rememberChannelStyles() {
  document.querySelectorAll(".viz-ch-row").forEach((row) => {
    channelStyleMemory[row.dataset.channel] = {
      visible: row.querySelector(".viz-channel").checked,
      label: row.querySelector(".ch-label").value,
      linestyle: row.querySelector(".ch-linestyle").value,
      marker: row.querySelector(".ch-marker").value,
      color: row.querySelector(".ch-color").value,
    };
  });
}

function applyPalette() {
  const palette = currentPalette();
  document.querySelectorAll(".viz-ch-row").forEach((row, i) => {
    row.querySelector(".ch-color").value = palette[i % palette.length];
  });
  rememberChannelStyles();
}

let curvesRequest = 0;
async function loadSeriesCurves() {
  const box = $("viz-channels");
  const files = [...document.querySelectorAll(".viz-series-source:checked")].map((c) => c.value);
  const request = ++curvesRequest;
  rememberChannelStyles();

  if (!files.length) {
    shared.seriesCurves = {};
    box.innerHTML = '<span class="hint">Marque um ou mais CSVs processados.</span>';
    return;
  }

  const curves = {};
  const fragment = document.createDocumentFragment();
  const allUnits = [];
  const allQuantities = [];
  let index = 0;
  for (const [position, file] of files.entries()) {
    const resp = await fetch("/api/processed-channels?file=" + encodeURIComponent(file));
    const data = await resp.json();
    if (request !== curvesRequest) return;
    if (!resp.ok) { showError(data.error || "Erro ao ler canais do CSV."); continue; }

    // A chave precisa ser a mesma que o servidor monta ao desenhar
    const stem = shortName(file).split("/").pop().replace(/\.csv$/, "").replace(/_processado$/, "");
    data.channels.forEach((ch) => {
      const key = files.length > 1 ? `${stem} · ${ch}` : ch;
      curves[key] = { file, channel: ch };
      const unit = data.units?.[ch];
      allUnits.push(unit || "nm");
      allQuantities.push(data.quantities?.[ch]);
      // Com vários arquivos, só o primeiro já vem marcado
      fragment.appendChild(channelRow(key, index++, unit ? `[${unit}]` : "", position === 0));
    });
  }

  // nm → pm só para canais em nm; dados já em Δλ não precisam de referência
  const allNm = allUnits.every((u) => u === "nm");
  styleInput("data.to_pm").disabled = !allNm;
  if (!allNm) styleInput("data.to_pm").checked = false;
  if (allQuantities.length && allQuantities.every((q) => q === "wavelength_shift")) {
    styleInput("data.relative_first").checked = false;
  }

  shared.seriesCurves = curves;
  box.innerHTML = "";
  box.appendChild(fragment);
  applyVizChannelSelection();
}

// ── Coleta e aplicação do estilo ─────────────────────────────────────────────
export function collectStyle() {
  const style = {};
  document.querySelectorAll("[data-style]").forEach((el) => {
    const [section, key] = el.dataset.style.split(".");
    (style[section] ??= {})[key] = el.type === "checkbox" ? el.checked : el.value;
  });
  rememberChannelStyles();
  style.channels = {};
  Object.entries(channelStyleMemory).forEach(([ch, s]) => {
    style.channels[ch] = { label: s.label, color: s.color, linestyle: s.linestyle, marker: s.marker };
  });
  return style;
}

export function applyStyle(style) {
  if (!style) return;
  document.querySelectorAll("[data-style]").forEach((el) => {
    const [section, key] = el.dataset.style.split(".");
    const value = style[section]?.[key];
    if (value === undefined) return;
    if (el.type === "checkbox") el.checked = Boolean(value);
    else el.value = value ?? "";
  });

  Object.entries(style.channels || {}).forEach(([ch, s]) => {
    const previous = channelStyleMemory[ch] || {};
    channelStyleMemory[ch] = {
      visible: previous.visible ?? true,
      label: s.label ?? "",
      linestyle: s.linestyle ?? "",
      marker: s.marker ?? "",
      color: s.color || previous.color || "",
    };
  });
  document.querySelectorAll(".viz-ch-row").forEach((row) => {
    const s = channelStyleMemory[row.dataset.channel];
    if (!s) return;
    row.querySelector(".ch-label").value = s.label;
    row.querySelector(".ch-linestyle").value = s.linestyle;
    row.querySelector(".ch-marker").value = s.marker;
    if (s.color) row.querySelector(".ch-color").value = s.color;
  });
  refreshStyleState();
}

function applyPreset(key) {
  const preset = FIGURE_PRESETS[key];
  if (!preset) return;
  Object.entries(preset).forEach(([field, value]) => {
    styleInput(`figure.${field}`).value = value;
  });
}

function persistStyle() {
  try {
    localStorage.setItem(STYLE_STORAGE_KEY, JSON.stringify(collectStyle()));
  } catch { /* armazenamento local indisponível: segue sem lembrar */ }
}

function fillFontSelect(fonts) {
  const sel = $("viz-font");
  sel.innerHTML = "";
  [["serif", "Serifada (Times New Roman)"], ["sans-serif", "Sem serifa (Arial)"],
   ["monospace", "Monoespaçada"]].forEach(([value, text]) => sel.add(new Option(text, value)));
  const group = document.createElement("optgroup");
  group.label = "Fontes instaladas";
  fonts.forEach((font) => group.appendChild(new Option(font, font)));
  sel.appendChild(group);
}

export async function loadFigureOptions() {
  const resp = await fetch("/api/figure/options");
  shared.figureOptions = await resp.json();
  styleBaseline = shared.figureOptions.style;
  fillFontSelect(shared.figureOptions.fonts);
  applyStyle(shared.figureOptions.style);
  applySourceMode();
  try {
    const saved = JSON.parse(localStorage.getItem(STYLE_STORAGE_KEY) || "null");
    if (saved) applyStyle(saved);
  } catch { /* estilo salvo ilegível ou armazenamento indisponível */ }
  await loadStyleList();
}

// ── O que mudou, resumo dos cartões e busca ──────────────────────────────────
let styleBaseline = null;        // estilo de referência: o padrão ou o estilo salvo carregado

function baselineValue(el) {
  const [section, key] = el.dataset.style.split(".");
  return styleBaseline?.[section]?.[key];
}

// Igual ao que applyStyle mostraria? Números comparados como números, cores sem caixa
function differsFromBaseline(el) {
  if (!styleBaseline) return false;
  const base = baselineValue(el);
  if (base === undefined) return false;
  if (el.type === "checkbox") return el.checked !== Boolean(base);
  const atual = String(el.value ?? "").trim().toLowerCase();
  const ref = String(base ?? "").trim().toLowerCase();
  const na = Number(atual), nb = Number(ref);
  if (atual !== "" && ref !== "" && Number.isFinite(na) && Number.isFinite(nb)) return na !== nb;
  return atual !== ref;
}

const PLURAL = (n, um, varios) => `${n} ${n === 1 ? um : varios}`;
const opcaoEscolhida = (sel) => sel?.selectedOptions?.[0]?.textContent.split("(")[0].trim() || "";

// Resumo que aparece no título de cada cartão (para não precisar abrir)
const CARD_SUMMARIES = {
  dados: () => {
    if (vizSource() === "spectra") {
      return PLURAL(document.querySelectorAll(".viz-spectrum-source:checked").length, "espectro", "espectros");
    }
    const partes = [PLURAL(document.querySelectorAll(".viz-series-source:checked").length, "CSV", "CSVs"),
                    `x em ${styleInput("data.time_unit")?.value || "s"}`];
    if (styleInput("data.relative_first")?.checked) partes.push("Δ");
    if (styleInput("data.to_pm")?.checked) partes.push("pm");
    return partes.join(" · ");
  },
  curvas: () => {
    const partes = [PLURAL(document.querySelectorAll(".viz-channel:checked").length, "curva", "curvas")];
    partes.push(styleInput("legend.show")?.checked ? `legenda ${opcaoEscolhida(styleInput("legend.position")).toLowerCase()}` : "sem legenda");
    return partes.join(" · ");
  },
  figura: () => {
    const unidade = styleInput("figure.unit")?.value || "cm";
    const largura = fmtNum(styleInput("figure.width")?.value || 0, 2);
    const altura = styleInput("figure.height")?.value ? fmtNum(styleInput("figure.height").value, 2) : "auto";
    return `${largura} × ${altura} ${unidade} · ${opcaoEscolhida(styleInput("figure.layout")).toLowerCase()}`;
  },
  marcacoes: () => {
    const partes = [PLURAL(collectMarkers().filter((m) => String(m.time).trim() !== "").length, "marcação", "marcações")];
    if (styleInput("markers.shade")?.checked) partes.push("faixas");
    if (styleInput("axes.grid")?.checked) partes.push("grade");
    return partes.join(" · ");
  },
};

export function refreshStyleState() {
  document.querySelectorAll("#tab-viz-sidebar [data-style]").forEach((el) => {
    el.closest(".field, .check-row")?.classList.toggle("changed", differsFromBaseline(el));
  });
  document.querySelectorAll("#tab-viz-sidebar details[data-card]").forEach((card) => {
    const alvo = card.querySelector(":scope > summary [data-summary]");
    if (!alvo) return;
    const resumo = CARD_SUMMARIES[card.dataset.card]?.() || "";
    const alteradas = card.querySelectorAll(".changed").length;
    alvo.innerHTML = "";
    alvo.append(resumo);
    if (alteradas) {
      const marca = document.createElement("span");
      marca.className = "alteradas";
      marca.textContent = ` · ${PLURAL(alteradas, "alterada", "alteradas")}`;
      alvo.appendChild(marca);
    }
  });
}

// "Restaurar este cartão": volta os campos dele ao estilo de referência
document.querySelectorAll("#tab-viz-sidebar .card-reset").forEach((botao) => {
  botao.addEventListener("click", () => {
    const card = botao.closest("details[data-card]");
    card.querySelectorAll("[data-style]").forEach((el) => {
      const base = baselineValue(el);
      if (base === undefined) return;
      if (el.type === "checkbox") el.checked = Boolean(base);
      else el.value = base ?? "";
    });
    if (card.dataset.card === "figura") $("viz-preset").value = "";
    refreshStyleState();
    markProjectDirty();
    scheduleFigure(true);
  });
});

// Busca: mostra só as opções cujo rótulo (ou as escolhas) tem o texto digitado
const semAcento = (t) => t.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
let abertosAntesDaBusca = null;

// Nome da seção (sub-rótulo "Ticks", "Legenda"…) e do cartão de um campo: buscar
// "tick" acha também "Direção" e "Comprimento", que ficam na seção Ticks
function secaoDe(el) {
  let secao = "";
  for (let irmao = el.previousElementSibling; irmao; irmao = irmao.previousElementSibling) {
    if (irmao.classList.contains("sub-label")) { secao = irmao.textContent; break; }
  }
  const cartao = el.closest("details[data-card]")?.querySelector(":scope > summary > span")?.textContent || "";
  return `${secao} ${cartao}`;
}

function filterVizOptions(texto) {
  const q = semAcento(texto.trim());
  const sidebar = $("tab-viz-sidebar");
  const itens = [...sidebar.querySelectorAll(".field, .check-row, .inline-row")]
    .filter((el) => !el.closest(".viz-search") && !el.parentElement.closest(".field, .check-row, .inline-row"));
  const cartoes = [...sidebar.querySelectorAll("details[data-card]")];
  const extras = sidebar.querySelectorAll(".hint:not(#viz-search-empty), .sub-label, .card-reset, #viz-channels, .advanced > summary");
  if (!q) {
    itens.forEach((el) => el.classList.remove("search-hidden"));
    cartoes.forEach((c) => c.classList.remove("search-hidden"));
    extras.forEach((el) => el.classList.remove("search-hidden"));
    if (abertosAntesDaBusca) {
      sidebar.querySelectorAll("details").forEach((d) => { d.open = abertosAntesDaBusca.has(d); });
      abertosAntesDaBusca = null;
    }
    $("viz-search-empty").classList.add("hidden");
    return;
  }
  if (!abertosAntesDaBusca) abertosAntesDaBusca = new Set([...sidebar.querySelectorAll("details")].filter((d) => d.open));
  extras.forEach((el) => el.classList.add("search-hidden"));
  let achados = 0;
  itens.forEach((el) => {
    const texto = semAcento(`${secaoDe(el)} ${el.textContent} ` +
                            [...el.querySelectorAll("input")].map((i) => i.placeholder).join(" "));
    const casa = texto.includes(q);
    el.classList.toggle("search-hidden", !casa);
    if (casa) {
      achados++;
      for (let d = el.closest("details"); d; d = d.parentElement.closest("details")) d.open = true;
    }
  });
  cartoes.forEach((c) => c.classList.toggle("search-hidden", !c.querySelector(".field:not(.search-hidden), .check-row:not(.search-hidden), .inline-row:not(.search-hidden)")));
  $("viz-search-empty").classList.toggle("hidden", achados > 0);
}

$("viz-search").addEventListener("input", (e) => filterVizOptions(e.target.value));
$("viz-search").addEventListener("keydown", (e) => {
  if (e.key === "Escape") { e.target.value = ""; filterVizOptions(""); }
  if (e.key === "Enter") {      // vai para o primeiro campo encontrado
    e.preventDefault();
    $("tab-viz-sidebar").querySelector(".field:not(.search-hidden) :is(input, select), .check-row:not(.search-hidden) input")?.focus();
  }
});

// ── Estilos salvos ───────────────────────────────────────────────────────────
async function loadStyleList(selectValue) {
  const resp = await fetch("/api/styles");
  const data = await resp.json();
  const sel = $("style-select");
  const current = selectValue ?? sel.value;
  sel.innerHTML = '<option value="">— nenhum —</option>';
  data.styles.forEach((name) => sel.add(new Option(name, name)));
  sel.value = data.styles.includes(current) ? current : "";
}

async function loadStyle(name) {
  if (!name) return;
  const resp = await fetch("/api/styles/" + encodeURIComponent(name));
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || "Erro ao carregar estilo.");
  styleBaseline = data.style;
  applyStyle(data.style);
  $("style-name").value = data.name;
  $("viz-preset").value = "";
}

async function saveStyle() {
  const name = $("style-name").value.trim();
  if (!name) { showError("Informe um nome para o estilo."); return; }
  showError("");
  try {
    const resp = await fetch("/api/styles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, style: collectStyle() }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Erro ao salvar estilo.");
    await loadStyleList(data.name);
    $("viz-status").textContent = `Estilo "${data.name}" salvo em data/styles.`;
  } catch (err) {
    showError(err.message);
  }
}

function resetStyle() {
  if (!shared.figureOptions) return;
  Object.keys(channelStyleMemory).forEach((ch) => delete channelStyleMemory[ch]);
  document.querySelectorAll(".viz-ch-row").forEach((row) => {
    row.querySelector(".ch-label").value = "";
    row.querySelector(".ch-linestyle").value = "";
    row.querySelector(".ch-marker").value = "";
  });
  $("viz-palette").value = "publicacao";
  applyPalette();
  styleBaseline = shared.figureOptions.style;
  applyStyle(shared.figureOptions.style);
  $("style-select").value = "";
  $("viz-preset").value = "";
  scheduleFigure(true);
}

// ── Marcações ────────────────────────────────────────────────────────────────
export function addMarkerRow(time = "", label = "", color = "#4682B4") {
  const row = document.createElement("div");
  row.className = "marker-row";

  const tIn = makeInput("number", "marker-time", time, "t (s)");
  const lIn = makeInput("text", "marker-label", label, "legenda");
  const cIn = document.createElement("input");
  cIn.type = "color"; cIn.className = "marker-color"; cIn.value = color;

  const del = document.createElement("button");
  del.type = "button"; del.className = "marker-del"; del.textContent = "×";
  del.title = "Remover marcação";
  del.addEventListener("click", () => {
    row.remove();
    markProjectDirty();
    drawPlotMarkers();
    scheduleFigure();
  });

  row.append(tIn, lIn, cIn, del);
  $("marker-list").appendChild(row);
  return row;
}

export function sortMarkerRows() {
  const list = $("marker-list");
  const chave = (row) => {
    const t = parseFloat(row.querySelector(".marker-time").value);
    return Number.isFinite(t) ? t : Infinity;
  };
  [...list.children].sort((a, b) => chave(a) - chave(b) || 0).forEach((row) => list.appendChild(row));
}

export function markerLayout() {
  const markers = collectMarkers()
    .map((m) => ({ ...m, time: Number(m.time) }))
    .filter((m) => Number.isFinite(m.time));
  return {
    shapes: markers.map((m) => ({
      type: "line", xref: "x", yref: "paper", x0: m.time, x1: m.time, y0: 0, y1: 1,
      line: { color: m.color, width: 1.5, dash: "dash" },
    })),
    annotations: markers.filter((m) => m.label).map((m) => ({
      x: m.time, xref: "x", y: 1, yref: "paper", text: m.label, showarrow: false,
      xanchor: "left", yanchor: "top", xshift: 3, font: { size: 11, color: m.color },
      bgcolor: "rgba(255, 255, 255, 0.85)", borderpad: 2,           // legível por cima da curva
    })),
  };
}

// Instantes das marcações válidas, na ordem em que são desenhadas
export function collectMarkerTimes() {
  return collectMarkers().map((m) => Number(m.time)).filter(Number.isFinite);
}

// Uma marcação arrastada no gráfico (índice na ordem do desenho)
export function moveMarker(indice, x) {
  const linhas = [...document.querySelectorAll(".marker-row")]
    .filter((row) => Number.isFinite(parseFloat(row.querySelector(".marker-time").value)));
  const row = linhas[indice];
  if (!row || !Number.isFinite(Number(x))) return;
  row.querySelector(".marker-time").value = Math.round(Number(x) * 100) / 100;
  sortMarkerRows();
  markProjectDirty();
  drawPlotMarkers();
  scheduleFigure();
}

export function drawPlotMarkers() {
  scheduleAnalysis();
  const n = collectMarkers().length;
  $("marker-count").textContent = n ? `(${n})` : "";
  $("viz-marker-count").textContent = n
    ? `${n} marcação(ões), feitas na aba Séries temporais.`
    : "Nenhuma marcação: clique no gráfico da aba Séries temporais para criar.";
  if ($("plot").data) Plotly.relayout($("plot"), plotDecorations());
  refreshStyleState();
}

// Um clique marca; o duplo clique (que reajusta o zoom) não
export function onPlotClick(event) {
  const x = event?.points?.[0]?.x;
  if (typeof x !== "number") return;
  clearTimeout(shared.markerClickTimer);
  shared.markerClickTimer = setTimeout(() => addMarkerAt(x), 280);
}

function addMarkerAt(x) {
  const row = addMarkerRow(Math.round(x * 100) / 100);
  sortMarkerRows();
  markProjectDirty();
  drawPlotMarkers();
  scheduleFigure();
  $("card-markers").open = true;
  row.querySelector(".marker-label").focus();
}

export function collectMarkers() {
  return Array.from(document.querySelectorAll(".marker-row"))
    .map((r) => ({
      time: r.querySelector(".marker-time").value,
      label: r.querySelector(".marker-label").value,
      color: r.querySelector(".marker-color").value,
    }))
    .filter((m) => m.time !== "");
}

export function collectVizOptions() {
  const selected = Array.from(document.querySelectorAll(".viz-channel:checked")).map((c) => c.value);
  if (vizSource() === "spectra") {
    saveCurrentSpectrumState();
    return {
      source: "spectra",
      // cada espectro leva o preparo definido na aba Espectros
      spectra: selected.map((key) => shared.spectrumCurves[key]).filter(Boolean)
        .map((curve) => ({ ...curve, settings: spectraStateFor(curve.file).settings })),
      markers: collectMarkers(),
      style: collectStyle(),
    };
  }
  return {
    source: "series",
    series: selected.map((key) => shared.seriesCurves[key]).filter(Boolean),
    markers: collectMarkers(),
    style: collectStyle(),
  };
}

// ── Geração, zoom e download ─────────────────────────────────────────────────
function applyZoom() {
  const img = $("viz-img");
  const zoom = $("viz-zoom").value;
  img.classList.toggle("zoom-fit", zoom === "fit");
  // "Tamanho real": 96 px CSS por polegada
  img.style.width = zoom === "fit" || !lastFigureInfo
    ? "" : `${lastFigureInfo.width_in * 96 * Number(zoom)}px`;
}

export async function generateFigure() {
  const opts = collectVizOptions();
  const curves = opts.source === "spectra" ? opts.spectra : opts.series;
  if (!curves.length) {
    showError(opts.source === "spectra"
      ? "Marque pelo menos um traço de espectro."
      : "Marque pelo menos um canal de um CSV processado.");
    return;
  }
  const request = ++figureRequest;
  const curveCount = curves.length;
  showError("");
  $("viz-status").textContent = "Gerando figura…";
  try {
    const resp = await fetch("/api/figure", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(opts),
    });
    const data = await resp.json();
    if (request !== figureRequest) return;
    if (!resp.ok) throw new Error(data.error || "Erro ao gerar figura.");

    const img = $("viz-img");
    img.src = "data:image/png;base64," + data.image;
    img.classList.remove("hidden");
    document.querySelector("#viz-figure .placeholder").classList.add("hidden");
    lastFigureInfo = data.info;
    applyZoom();

    const info = data.info;
    const format = opts.style.export.format;
    const size = ["png", "tiff"].includes(format)
      ? ` → ${info.width_px} × ${info.height_px} px a ${info.dpi} dpi` : " (vetorial)";
    $("viz-status").textContent =
      `${fmtNum(info.width_cm, 2)} × ${fmtNum(info.height_cm, 2)} cm · ${format.toUpperCase()}${size}` +
      ` · ${curveCount} curva(s) · ${opts.markers.length} marcação(ões)`;
    persistStyle();
  } catch (err) {
    if (request !== figureRequest) return;
    showError(err.message);
    $("viz-status").textContent = `Falha ao gerar figura: ${err.message}`;
  }
}

let figureTimer = null;
export function scheduleFigure(force = false) {
  if (!force && !$("viz-auto").checked) return;
  if (!document.querySelectorAll(".viz-channel:checked").length) return;
  clearTimeout(figureTimer);
  figureTimer = setTimeout(generateFigure, 500);
}

export async function onVizChange(el) {
  try {
    if (el.id === "style-name" || el.id === "viz-palette") return;
    if (el.id === "viz-source") { applySourceMode(); await refreshVizCurves(); }
    if (el.classList.contains("viz-series-source")) await loadSeriesCurves();
    if (el.classList.contains("viz-spectrum-source")) await loadSpectrumCurves();
    if (el.id === "style-select") await loadStyle(el.value);
    if (el.id === "viz-preset") applyPreset(el.value);
  } catch (err) {
    showError(err.message);
    return;
  }
  // Editar o tamanho à mão desfaz a predefinição
  if (["figure.unit", "figure.width", "figure.height", "figure.font_size"].includes(el.dataset.style)) {
    $("viz-preset").value = "";
  }
  refreshStyleState();
  scheduleFigure();
}

async function copyFigure() {
  const opts = collectVizOptions();
  const curvas = opts.source === "spectra" ? opts.spectra : opts.series;
  if (!curvas.length) { showError("Marque pelo menos uma curva."); return; }
  const dpi = Math.min(Number(opts.style.export?.dpi) || 300, 300);
  opts.style.export = { ...opts.style.export, preview_dpi: dpi };
  $("viz-status").textContent = "Copiando figura…";
  try {
    const resp = await fetch("/api/figure", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(opts),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Erro ao gerar a figura.");
    const bytes = Uint8Array.from(atob(data.image), (c) => c.charCodeAt(0));
    await navigator.clipboard.write([new ClipboardItem({ "image/png": new Blob([bytes], { type: "image/png" }) })]);
    $("viz-status").textContent = `Figura copiada (PNG, ${dpi} dpi): cole num slide ou documento.`;
  } catch (err) {
    showError(`Não foi possível copiar a figura: ${err.message}. Use "Baixar figura".`);
    $("viz-status").textContent = "Falha ao copiar a figura.";
  }
}

async function downloadFigure() {
  const opts = collectVizOptions();
  if (!(opts.source === "spectra" ? opts.spectra : opts.series).length) {
    showError("Marque as curvas da figura primeiro."); return;
  }
  const format = opts.style.export.format;
  showError("");
  $("viz-status").textContent = `Exportando ${format.toUpperCase()}…`;
  try {
    const resp = await fetch("/api/figure/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(opts),
    });
    if (!resp.ok) {
      const data = await resp.json();
      throw new Error(data.error || "Erro ao gerar figura.");
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const first = (opts.spectra || opts.series)[0].file;
    const base = first.split("/").pop().replace(/\.[^.]+$/, "").replace(/_processado$/, "");
    a.download = `${base}_figura.${format}`;
    a.click();
    URL.revokeObjectURL(url);
    $("viz-status").textContent = `${format.toUpperCase()} exportado.`;
  } catch (err) {
    showError(err.message);
    $("viz-status").textContent = `Falha ao exportar: ${err.message}`;
  }
}
$("btn-add-marker").addEventListener("click", () => {
  addMarkerRow().querySelector(".marker-time").focus();
  markProjectDirty();
});
$("btn-figure").addEventListener("click", generateFigure);
$("btn-fig-download").addEventListener("click", downloadFigure);
$("btn-fig-copy").addEventListener("click", copyFigure);
$("btn-apply-palette").addEventListener("click", () => { applyPalette(); markProjectDirty(); scheduleFigure(); });
$("btn-style-save").addEventListener("click", saveStyle);
$("btn-style-reset").addEventListener("click", resetStyle);
$("viz-zoom").addEventListener("change", applyZoom);
$("status-viz").addEventListener("change", (e) => {
  if (e.target.dataset.style) { markProjectDirty(); scheduleFigure(); }
});
