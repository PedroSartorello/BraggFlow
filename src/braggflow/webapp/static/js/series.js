// Aba Séries temporais: opções de processamento, sensores, setups, lista
// de arquivos, gráfico, processamento (um, em lote ou juntos) e concatenação.

import { $, fmtNum, fmtSig, setBusy, showError, syncCardStyles } from "./core.js";
import { baseName, fileKind, projectSeriesPaths, seriesOrder, seriesState, seriesStateFor, shared, shortName } from "./state.js";
import { renderSpectraFiles } from "./spectra.js";
import { collectMarkerTimes, markerLayout, moveMarker, onPlotClick } from "./viz.js";
import { numeroOuTraco, resetAnalysis, scheduleAnalysis } from "./analysis.js";
import { switchTab } from "./tabs.js";
import { addFileToProject, fileRow, markProjectDirty, renderEmptyFiles, renderFilePicker } from "./projects.js";

// ── Coleta das opções do formulário ─────────────────────────────────────────
export function collectSensors() {
  return Array.from(document.querySelectorAll(".sensor-row")).map((row) => ({
    channel: row.dataset.channel,
    name: row.querySelector(".sensor-name").value.trim(),
    nominal_wavelength: row.dataset.nominal || null,
    band_min: row.querySelector(".sensor-band-min").value,
    band_max: row.querySelector(".sensor-band-max").value,
    temp_sensitivity: row.querySelector(".sensor-kt").value,
    hidden: row.dataset.hidden === "1",
  }));
}

// ── Colunas ocultas: ficam num grupo recolhido no fim do cartão Sensores ────
const visibleSensorRows = () => [...document.querySelectorAll("#sensor-list > .sensor-row")];

function setSensorHidden(row, oculto) {
  row.dataset.hidden = oculto ? "1" : "0";
  row.classList.toggle("is-hidden", oculto);
  const botao = row.querySelector(".sensor-hide");
  botao.textContent = oculto ? "mostrar" : "ocultar";
  botao.title = oculto
    ? "Volta a usar esta coluna no processamento"
    : "Tira esta coluna de tudo (processamento, gráfico, CSV, figura), como se o arquivo não a tivesse";
  const destino = oculto ? $("hidden-sensor-list") : $("sensor-list");
  if (destino && row.parentElement !== destino) {
    if (oculto) destino.appendChild(row);
    else $("sensor-list").insertBefore(row, $("hidden-sensors"));
  }
  updateHiddenSummary();
}

function updateHiddenSummary() {
  const grupo = $("hidden-sensors");
  if (!grupo) return;
  const n = grupo.querySelectorAll(".sensor-row").length;
  grupo.classList.toggle("hidden", n === 0);
  grupo.querySelector("summary").textContent = n === 1 ? "1 coluna oculta" : `${n} colunas ocultas`;
}

export function collectProcessing() {
  const options = {};
  document.querySelectorAll("#tab-series-sidebar [data-opt]").forEach((el) => {
    const value = el.type === "checkbox" ? el.checked : el.value;
    const [section, key] = el.dataset.opt.split(".");
    if (key === undefined) options[section] = value;
    else (options[section] ??= {})[key] = value;
  });
  return options;
}

export function applyProcessing(processing) {
  if (!processing) return;
  document.querySelectorAll("#tab-series-sidebar [data-opt]").forEach((el) => {
    const [section, key] = el.dataset.opt.split(".");
    const value = key === undefined ? processing[section] : processing[section]?.[key];
    if (value === undefined) return;
    if (el.type === "checkbox") el.checked = Boolean(value);
    else el.value = value ?? "";
  });
  syncCardStyles();
}

function collectOptions() {
  return {
    project: $("project-name").value.trim(),   // pasta dos CSVs processados
    file: $("file-select").value,
    sensors: collectSensors(),
    setup_name: $("setup-select").value,
    ...collectProcessing(),
    include_raw: $("show-raw").checked,       // preferência de quem olha, não do projeto
  };
}

// ── Plot ─────────────────────────────────────────────────────────────────────
// Mesma fonte da interface (token --font do CSS)
export const plotFont = () =>
  getComputedStyle(document.documentElement).getPropertyValue("--font").trim() || "sans-serif";
// O "responsive" do Plotly só reage à janela. Quando o quadro do gráfico muda
// por outro motivo (tabela de picos, detalhes do status, cartões que abrem e
// fecham), o desenho ficava com a altura antiga e o eixo X era cortado.
const plotResizer = new ResizeObserver((entries) => {
  entries.forEach(({ target, contentRect }) => {
    if (!target.data || !contentRect.width || !contentRect.height) return;  // vazio ou escondido
    const layout = target._fullLayout;
    if (layout && Math.abs(layout.height - contentRect.height) < 1
        && Math.abs(layout.width - contentRect.width) < 1) return;
    Plotly.Plots.resize(target).catch(() => {});
  });
});
["plot", "spectra-plot"].forEach((id) => plotResizer.observe($(id)));
export const PALETTE = ["#000000", "#800000", "#003366", "#2E8B57", "#8B008B",
                 "#B8860B", "#4B0082", "#006400", "#8B0000", "#00008B"];

// ── Gráfico: disposição, valores relativos e medição de trechos ─────────────
const PLOT_VIEW_KEY = "braggflow.plotView";
let lastPlotData = null;      // último resultado mostrado (redesenha sem reprocessar)
let lastPlotOptions = null;   // opções que geraram esse resultado
let selection = null;         // {start, end} do trecho medido
let statsRequest = 0;
let lastStats = null;

const plotLayout = () => document.querySelector('input[name="plot-layout"]:checked')?.value || "separate";
export const plotTool = () => document.querySelector('input[name="plot-tool"]:checked')?.value || "zoom";
export const plotRelative = () => $("plot-relative").checked;
// Opções que geraram o gráfico atual (a medição e as estatísticas usam as mesmas)
export const currentPlotOptions = () => lastPlotOptions;

try {
  const salvo = JSON.parse(localStorage.getItem(PLOT_VIEW_KEY) || "{}");
  if (salvo.layout) document.querySelector(`input[name="plot-layout"][value="${salvo.layout}"]`)?.click();
  $("plot-relative").checked = Boolean(salvo.relative);
} catch { /* sem armazenamento */ }

function rememberPlotView() {
  try {
    localStorage.setItem(PLOT_VIEW_KEY, JSON.stringify({ layout: plotLayout(), relative: plotRelative() }));
  } catch { /* sem armazenamento */ }
}

// Primeiro valor válido de cada canal processado: a origem do "relativo ao início"
function channelOrigins(data) {
  const origem = {};
  data.channels.forEach((ch) => {
    origem[ch] = plotRelative() ? (data.signals[ch].find((v) => v !== null && Number.isFinite(v)) ?? 0) : 0;
  });
  return origem;
}

const shift = (values, offset) => (offset ? values.map((v) => (v === null ? null : v - offset)) : values);

// Escala y pelo processado: os picos do bruto (justamente o que o
// processamento tira) não podem achatar a curva que interessa
function yRange(series) {
  let lo = Infinity, hi = -Infinity;
  series.forEach((values) => values.forEach((v) => {
    if (v !== null && Number.isFinite(v)) { if (v < lo) lo = v; if (v > hi) hi = v; }
  }));
  if (!Number.isFinite(lo)) return undefined;
  const folga = (hi - lo) * 0.08 || Math.max(Math.abs(hi) * 1e-6, 1e-6);
  return [lo - folga, hi + folga];
}

// Faixa do trecho medido, junto com as marcações
export function plotDecorations() {
  const { shapes, annotations } = markerLayout();
  if (selection) {
    shapes.unshift({
      type: "rect", xref: "x", yref: "paper", x0: selection.start, x1: selection.end, y0: 0, y1: 1,
      fillcolor: "rgba(31, 111, 178, 0.10)", line: { width: 0 }, layer: "below",
    });
  }
  return { shapes, annotations };
}

function renderPlot(data) {
  lastPlotData = data;
  const unit = Object.values(data.units || {})[0] || "nm";
  const grandeza = data.quantity === "wavelength_shift" || plotRelative() ? "Δλ" : "λ";
  const separado = plotLayout() === "separate" && data.channels.length > 1;
  const origem = channelOrigins(data);
  const eixos = (i) => (separado ? { xaxis: `x${i + 1}`, yaxis: `y${i + 1}` } : {});
  const traces = [];

  if (data.raw) {
    data.channels.forEach((ch, i) => {
      traces.push({
        x: data.raw.time, y: shift(data.raw.signals[ch], origem[ch]),
        name: ch + " (bruto)", mode: "lines", legendgroup: ch, showlegend: !separado,
        line: { color: PALETTE[i % PALETTE.length], width: 1 },
        opacity: 0.3, ...eixos(i),
      });
    });
  }

  data.channels.forEach((ch, i) => {
    traces.push({
      x: data.time, y: shift(data.signals[ch], origem[ch]),
      name: ch, mode: "lines", legendgroup: ch, showlegend: !separado,
      line: { color: PALETTE[i % PALETTE.length], width: 1.5 },
      ...eixos(i),
    });
  });

  const eixo = { gridcolor: "#eceff3", zerolinecolor: "#e2e7ee", exponentformat: "e", automargin: true };
  const layout = {
    ...plotDecorations(),
    separators: ",.",                   // 1.551,45 como no resto do app
    margin: { l: 60, r: 20, t: separado ? 14 : 30, b: 45 },
    font: { family: plotFont(), size: 12.5, color: "#16212e" },
    hovermode: "x unified",
    legend: { orientation: "h", y: 1.08 },
    dragmode: { select: "select", mark: false }[plotTool()] ?? "zoom",
    selectdirection: "h",
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
  };
  if (separado) {
    const n = data.channels.length;
    layout.grid = { rows: n, columns: 1, pattern: "independent", roworder: "top to bottom", ygap: 0.12 };
    data.channels.forEach((ch, i) => {
      const sufixo = i ? String(i + 1) : "";
      layout[`xaxis${sufixo}`] = {
        ...eixo, matches: i ? "x" : undefined, showticklabels: i === n - 1,
        title: i === n - 1 ? "Tempo (s)" : undefined,
      };
      layout[`yaxis${sufixo}`] = {
        ...eixo, title: { text: `${ch}<br><span style="font-size:11px">${grandeza} (${unit})</span>`, font: { size: 12 } },
        range: yRange([shift(data.signals[ch], origem[ch])]),
      };
    });
  } else {
    layout.xaxis = { ...eixo, title: "Tempo (s)" };
    layout.yaxis = { ...eixo, title: `${grandeza} (${unit})`,
                     range: yRange(data.channels.map((ch) => shift(data.signals[ch], origem[ch]))) };
  }

  Plotly.react($("plot"), traces, layout, { responsive: true });

  const gd = $("plot");             // o purge de um projeto anterior tira os eventos
  ["plotly_click", "plotly_doubleclick", "plotly_selected"].forEach((ev) => gd.removeAllListeners?.(ev));
  // Só a ferramenta Marcar cria marcações: um clique ao dar zoom não marca nada
  // O instante vem da posição do clique, não do ponto do hover (que atrasa
  // quando o mouse anda rápido e marcava o lugar anterior)
  gd.on("plotly_click", (event) => {
    if (plotTool() !== "mark") return;
    const t = event?.event ? markerNear(event.event)?.t : undefined;
    onPlotClick(Number.isFinite(t) ? { points: [{ x: t }] } : event);
  });
  gd.on("plotly_doubleclick", () => clearTimeout(shared.markerClickTimer));
  gd.on("plotly_selected", onPlotSelected);
}

// ── Arrastar marcações (ferramenta Marcar) ───────────────────────────────────
// Feito aqui, e não com as "shapes editáveis" do Plotly: com um painel por
// canal, as áreas de arraste dos outros painéis ficam por cima da linha.
const MARKER_GRAB_PX = 6;
let markerDrag = null;   // {indice, forma, t}

// Instante (s) sob o ponteiro e a marcação mais perto dele, em pixels
function markerNear(event) {
  const gd = $("plot");
  const xa = gd._fullLayout?.xaxis;
  if (!xa) return null;
  const px = event.clientX - gd.getBoundingClientRect().left - xa._offset;
  if (px < 0 || px > xa._length) return null;
  const t = xa.p2l(px);
  let melhor = null;
  collectMarkerTimes().forEach((tm, indice) => {
    const dist = Math.abs(xa.l2p(tm) - px);
    if (dist <= MARKER_GRAB_PX && (!melhor || dist < melhor.dist)) melhor = { indice, dist };
  });
  return { t, alvo: melhor };
}

$("plot").addEventListener("mousedown", (event) => {
  if (plotTool() !== "mark" || event.button !== 0) return;
  const perto = markerNear(event);
  if (!perto?.alvo) return;
  event.stopPropagation();          // nem zoom, nem clique (que criaria outra marcação)
  event.preventDefault();
  markerDrag = { indice: perto.alvo.indice, forma: perto.alvo.indice + (selection ? 1 : 0), t: perto.t };
}, true);

window.addEventListener("mousemove", (event) => {
  const gd = $("plot");
  if (markerDrag) {
    const perto = markerNear(event);
    if (!perto) return;
    markerDrag.t = perto.t;
    Plotly.relayout(gd, { [`shapes[${markerDrag.forma}].x0`]: perto.t, [`shapes[${markerDrag.forma}].x1`]: perto.t });
    return;
  }
  if (plotTool() === "mark" && gd.contains(event.target)) {
    gd.classList.toggle("near-marker", Boolean(markerNear(event)?.alvo));
  }
});

window.addEventListener("mouseup", () => {
  if (!markerDrag) return;
  const { indice, t } = markerDrag;
  markerDrag = null;
  moveMarker(indice, t);
});

function onPlotSelected(event) {
  const chave = Object.keys(event?.range || {}).find((k) => k.startsWith("x"));
  if (!chave) return;                       // clique sem arrastar
  const [a, b] = event.range[chave];
  Plotly.relayout($("plot"), { selections: [] });   // a faixa própria substitui o retângulo do Plotly
  selectRange(Math.min(a, b), Math.max(a, b));
}

function selectRange(start, end) {
  selection = { start, end };
  Plotly.relayout($("plot"), plotDecorations());
  measureSelection();
}

// ``redraw: false`` quando o gráfico vai ser redesenhado ou apagado em seguida
// (outro arquivo, outro projeto): um relayout no meio disso quebra o Plotly
export function clearSelection({ redraw = true } = {}) {
  const tinha = selection !== null;
  selection = null;
  lastStats = null;
  statsRequest++;
  $("selection-panel").classList.add("hidden");
  if (tinha && redraw && $("plot").data) Plotly.relayout($("plot"), plotDecorations());
}

const fmtStat = fmtSig;

const STAT_COLUNAS = [
  ["Canal", (l) => l.channel],
  ["Média", (l) => fmtStat(l.mean)],
  ["σ", (l) => fmtStat(l.std)],
  ["Mín", (l) => fmtStat(l.min)],
  ["Máx", (l) => fmtStat(l.max)],
  ["Pico a pico", (l) => fmtStat(l.peak_to_peak)],
  ["Deriva (/s)", (l) => fmtStat(l.slope)],
  ["Início", (l) => fmtStat(l.value_start)],
  ["Fim", (l) => fmtStat(l.value_end)],
  ["Δ (fim − início)", (l) => fmtStat(l.delta)],
  ["n", (l) => numeroOuTraco(l.n, 0)],
];

async function measureSelection() {
  if (!selection || !lastPlotOptions) return;
  const request = ++statsRequest;
  $("selection-panel").classList.remove("hidden");
  $("selection-range").textContent =
    `${fmtNum(selection.start, 2)} – ${fmtNum(selection.end, 2)} s · Δt ${fmtNum(selection.end - selection.start, 2)} s`;
  $("selection-note").textContent = "Medindo…";
  try {
    const resp = await fetch("/api/series/stats", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ options: lastPlotOptions, start: selection.start, end: selection.end,
                             relative: plotRelative() }),
    });
    const data = await resp.json();
    if (request !== statsRequest) return;
    if (!resp.ok) throw new Error(data.error || "Erro ao medir o trecho.");
    lastStats = data;
    const unidade = data.channels[0]?.unit || "";
    $("selection-note").textContent =
      `Sinal processado inteiro, não o decimado da tela · ${unidade}${plotRelative() ? " · relativo ao início" : ""}`;
    renderSelectionTable(data);
  } catch (err) {
    if (request !== statsRequest) return;
    lastStats = null;
    $("selection-note").textContent = `Falha: ${err.message}`;
    $("selection-table").innerHTML = "";
  }
}

function renderSelectionTable(data) {
  const tabelaEl = $("selection-table");
  tabelaEl.innerHTML = "";
  const cabeca = tabelaEl.createTHead().insertRow();
  STAT_COLUNAS.forEach(([nome]) => {
    const th = document.createElement("th");
    th.textContent = nome;
    cabeca.appendChild(th);
  });
  const corpo = tabelaEl.createTBody();
  data.channels.forEach((linha) => {
    const tr = corpo.insertRow();
    STAT_COLUNAS.forEach(([, valor]) => { tr.insertCell().textContent = valor(linha); });
  });
}

function selectionText() {
  if (!lastStats) return "";
  const linhas = [STAT_COLUNAS.map(([nome]) => nome).join("\t"),
                  ...lastStats.channels.map((l) => STAT_COLUNAS.map(([, v]) => v(l).replace("—", "")).join("\t"))];
  return `Trecho ${fmtNum(lastStats.start, 2)}–${fmtNum(lastStats.end, 2)} s\n` + linhas.join("\n");
}

const TOOL_HINTS = {
  zoom: "arraste = zoom · duplo clique = ver tudo",
  select: "arraste = medir trecho · Esc limpa",
  mark: "clique = nova marcação · arraste uma marcação para mudar o instante",
};

function setPlotTool(tool) {
  document.querySelector(`input[name="plot-tool"][value="${tool}"]`).checked = true;
  $("plot-hint").textContent = TOOL_HINTS[tool];
  if ($("plot").data) {
    Plotly.relayout($("plot"), { dragmode: { select: "select", mark: false }[tool] ?? "zoom" });
  }
  if (tool !== "mark") $("plot").classList.remove("near-marker");
}

document.querySelectorAll('input[name="plot-layout"]').forEach((el) => el.addEventListener("change", () => {
  rememberPlotView();
  if (lastPlotData) renderPlot(lastPlotData);
}));
$("plot-relative").addEventListener("change", () => {
  rememberPlotView();
  if (lastPlotData) renderPlot(lastPlotData);
  if (selection) measureSelection();       // os níveis mudam com a origem
  scheduleAnalysis();
});
document.querySelectorAll('input[name="plot-tool"]').forEach((el) =>
  el.addEventListener("change", () => setPlotTool(el.value)));
$("btn-selection-clear").addEventListener("click", () => clearSelection());
$("btn-selection-copy").addEventListener("click", async () => {
  const texto = selectionText();
  if (!texto) return;
  try {
    await navigator.clipboard.writeText(texto);
    $("selection-note").textContent = "Tabela copiada: cole numa planilha.";
  } catch {
    showError("O navegador não deixou copiar; selecione a tabela e use Ctrl+C.");
  }
});

// Atalhos do gráfico (fora de campos de texto, só na aba Séries)
document.addEventListener("keydown", (e) => {
  // Campos onde se digita ficam com as teclas; caixas de marcar e botões não
  const digitando = e.target.closest(
    "textarea, select, [contenteditable], input:not([type=checkbox]):not([type=radio]):not([type=button])");
  if (e.ctrlKey || e.metaKey || e.altKey || digitando) return;
  if ($("tab-series-main").classList.contains("hidden") || !lastPlotData) return;
  const k = e.key.toLowerCase();
  if (k === "1" || k === "2") {
    document.querySelector(`input[name="plot-layout"][value="${k === "1" ? "separate" : "overlay"}"]`).click();
  } else if (k === "d") {
    $("plot-relative").click();
  } else if (k === "b") {
    $("show-raw").click();
  } else if (k === "m" || k === "z" || k === "a") {
    setPlotTool({ m: "select", z: "zoom", a: "mark" }[k]);
  } else if (k === "escape" && selection) {
    clearSelection();
  } else {
    return;
  }
  e.preventDefault();
});

function updateChannelDropdown(channels) {
  if (JSON.stringify(channels) === JSON.stringify(shared.lastChannels)) return;
  shared.lastChannels = channels;
  const sel = $("tempcomp-channel");
  const current = sel.value;
  sel.innerHTML = "";
  channels.forEach((ch) => {
    const opt = document.createElement("option");
    opt.value = ch; opt.textContent = ch;
    sel.appendChild(opt);
  });
  sel.value = channels.includes(current) ? current
            : (channels.includes("FBG") ? "FBG" : channels[0]);
}

// ── Ações ────────────────────────────────────────────────────────────────────
export async function processData({ save = true, files = null } = {}) {
  const opts = { ...collectOptions(), save };
  if (files) opts.files = files;        // vários arquivos viram um sinal contínuo
  if (!opts.file) { showError("Selecione um arquivo primeiro."); return; }

  setBusy(true);
  showError("");
  $("status-text").textContent = "Processando…";
  try {
    const resp = await fetch("/api/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(opts),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Erro no processamento.");

    updateChannelDropdown(data.channels);
    lastPlotOptions = opts;
    renderPlot(data);
    if (selection) measureSelection();       // o processamento mudou: a medição também
    scheduleAnalysis();                      // e as estatísticas por intervalo
    if (data.processed_file) shared.vizPendingFile = data.processed_file;
    if (data.existing_file) {
      (opts.files || [opts.file]).forEach((path) => {
        seriesStateFor(path).processed = data.existing_file;
      });
      renderSeriesFiles();
    }
    const csv = data.processed_file || data.existing_file;
    const estado = data.processed_file ? "CSV salvo ✓"
      : csv ? "pré-visualização · há um CSV salvo"
      : "pré-visualização · ainda sem CSV (Processar ▶ grava)";
    $("status-text").textContent =
      `${data.n_samples.toLocaleString("pt-BR")} amostras · ${data.channels.join(", ")} · ${estado}`;

    const detalhes = [];
    if (csv) detalhes.push({ texto: `CSV: ${shortName(csv)}` });
    if (data.plot_stride > 1) {
      detalhes.push({ texto: `Gráfico decimado 1:${data.plot_stride} só na tela; o CSV tem todas as amostras.` });
    }
    (data.report || []).forEach((texto) => detalhes.push({ texto }));
    (data.warnings || []).forEach((texto) => detalhes.push({ texto: `⚠ ${texto}`, aviso: true }));
    setStatusDetails(detalhes);
    statusCsv = csv;
    $("btn-open-viz").classList.toggle("hidden", !csv);
  } catch (err) {
    showError(err.message);
    $("status-text").textContent = "Falha no processamento.";
    setStatusDetails([]);
    $("btn-open-viz").classList.add("hidden");
  } finally {
    setBusy(false);
  }
}

// ── Detalhes do processamento (relatório e avisos) ──────────────────────────
let statusCsv = null;

function setStatusDetails(linhas) {
  const lista = $("status-details");
  lista.innerHTML = "";
  linhas.forEach(({ texto, aviso }) => {
    const li = document.createElement("li");
    li.textContent = texto;
    if (aviso) li.className = "warn";
    lista.appendChild(li);
  });
  const avisos = linhas.filter((l) => l.aviso).length;
  const botao = $("btn-status-details");
  botao.classList.toggle("hidden", !linhas.length);
  botao.classList.toggle("warn", avisos > 0);
  botao.textContent = avisos ? `⚠ ${avisos} aviso(s)` : "detalhes";
  showStatusDetails(avisos > 0);        // avisos aparecem sem precisar pedir
}

function showStatusDetails(mostrar) {
  $("status-details").classList.toggle("hidden", !mostrar || !$("status-details").children.length);
  $("btn-status-details").setAttribute("aria-expanded", String(mostrar));
}

$("btn-status-details").addEventListener("click", () =>
  showStatusDetails($("status-details").classList.contains("hidden")));
$("btn-open-viz").addEventListener("click", () => {
  if (!statusCsv) return;
  shared.vizPendingFile = statusCsv;           // já chega marcado na aba Visualização
  switchTab("viz");
});

async function downloadCsv() {
  const opts = collectOptions();
  if (!opts.file) { showError("Selecione um arquivo primeiro."); return; }
  showError("");
  try {
    const resp = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(opts),
    });
    if (!resp.ok) {
      const data = await resp.json();
      throw new Error(data.error || "Erro ao gerar CSV.");
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = opts.file.split("/").pop().replace(/\.[^.]+$/, "") + "_processado.csv";
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    showError(err.message);
  }
}

export function makeInput(type, className, value, placeholder) {
  const inp = document.createElement("input");
  inp.type = type; inp.className = className;
  if (type === "number") inp.step = "any";
  inp.value = value ?? ""; inp.placeholder = placeholder;
  return inp;
}

// Prioridade dos valores: edição atual na tela > setup carregado > padrão.
function sensorRow(ch, data, previous) {
  const fromSetup = shared.currentSetup?.sensors?.find((s) => s.channel === ch);
  const band = fromSetup?.band;
  const nominal = data.nominal[ch];

  const row = document.createElement("div");
  row.className = "sensor-row";
  row.dataset.channel = ch;
  if (nominal != null) row.dataset.nominal = nominal;

  const caption = document.createElement("span");
  caption.className = "sensor-caption";
  const texto = document.createElement("span");
  texto.textContent = nominal != null
    ? `${ch} · λ₀ ≈ ${fmtNum(nominal)} ${data.units[ch] || "nm"}`
    : `${ch} · sem leituras válidas`;
  const ocultar = document.createElement("button");
  ocultar.type = "button";
  ocultar.className = "btn-link sensor-hide";
  ocultar.addEventListener("click", () => {
    setSensorHidden(row, row.dataset.hidden !== "1");
    syncTempChannels();
    markProjectDirty();
    scheduleAutoProcess();
  });
  caption.append(texto, ocultar);

  row.append(
    caption,
    makeInput("text", "sensor-name",
      previous?.name ?? fromSetup?.name ?? data.defaults[ch] ?? ch, ch),
    makeInput("number", "sensor-band-min",
      previous?.min ?? (band ? band[0] : ""), "mín"),
    makeInput("number", "sensor-band-max",
      previous?.max ?? (band ? band[1] : ""), "máx"),
    makeInput("number", "sensor-kt",
      previous?.kt ?? fromSetup?.temp_sensitivity ?? "", "K_T"),
  );
  const kt = row.querySelector(".sensor-kt");
  kt.title = "Sensibilidade térmica K_T (pm/°C), da calibração em temperatura. " +
    "Usada pela compensação de temperatura: k = K_T do sensor / K_T da referência.";
  kt.min = "0";
  kt.step = "any";
  row.dataset.hidden = (previous?.hidden ?? fromSetup?.hidden) ? "1" : "0";
  return row;
}

export async function loadChannels() {
  const file = $("file-select").value;
  const list = $("sensor-list");
  if (!file) { list.innerHTML = '<span class="hint">Selecione um arquivo…</span>'; return; }
  try {
    const resp = await fetch("/api/channels?file=" + encodeURIComponent(file));
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Erro ao ler canais.");

    // Preserva o que já foi editado para canais de mesmo nome
    const previous = {};
    document.querySelectorAll(".sensor-row").forEach((row) => {
      previous[row.dataset.channel] = {
        name: row.querySelector(".sensor-name").value,
        min: row.querySelector(".sensor-band-min").value,
        max: row.querySelector(".sensor-band-max").value,
        kt: row.querySelector(".sensor-kt").value,
        hidden: row.dataset.hidden === "1",
      };
    });

    list.innerHTML = "";
    const cabecalho = document.createElement("div");
    cabecalho.className = "sensor-head";
    ["nome", "banda mín", "banda máx", "K_T pm/°C"].forEach((texto) => {
      const span = document.createElement("span");
      span.textContent = texto;
      cabecalho.appendChild(span);
    });
    cabecalho.lastChild.title = "Sensibilidade térmica de cada rede (calibração em temperatura)";
    list.appendChild(cabecalho);
    const grupo = document.createElement("details");
    grupo.className = "hidden-sensors hidden";
    grupo.id = "hidden-sensors";
    grupo.innerHTML = '<summary></summary><div id="hidden-sensor-list"></div>';
    list.appendChild(grupo);
    data.channels.forEach((ch) => {
      const row = sensorRow(ch, data, previous[ch]);
      list.insertBefore(row, grupo);
      setSensorHidden(row, row.dataset.hidden === "1");
    });

    const info = [`${data.n_samples.toLocaleString("pt-BR")} amostras`];
    if (data.fs) info.push(`≈ ${fmtNum(data.fs, 4)} Hz`);
    info.push(`${fmtNum(data.duration_s, 1)} s`);
    if (data.time_origin) info.push(`início ${data.time_origin.replace("T", " ")}`);
    $("file-info").textContent = info.join(" · ");
    syncTempChannels();
  } catch (err) {
    list.innerHTML = "";
    $("file-info").textContent = "";
    showError(err.message);
  }
}

export function syncTempChannels() {
  const names = visibleSensorRows()                 // coluna oculta não serve de referência
    .map((row) => row.querySelector(".sensor-name").value.trim() || row.dataset.channel);
  if (names.length) updateChannelDropdown(names);
}

export async function loadSetupList(selectValue) {
  const resp = await fetch("/api/setups");
  const data = await resp.json();
  const sel = $("setup-select");
  const current = selectValue ?? sel.value;
  sel.innerHTML = '<option value="">— nenhum —</option>';
  data.setups.forEach((name) => {
    const opt = document.createElement("option");
    opt.value = name; opt.textContent = name;
    sel.appendChild(opt);
  });
  sel.value = data.setups.includes(current) ? current : "";
}

// Aplica um setup salvo às linhas de sensor (sobrescreve nome e banda)
export async function applySetup(name) {
  if (!name) { shared.currentSetup = null; return; }
  const resp = await fetch("/api/setups/" + encodeURIComponent(name));
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || "Erro ao carregar setup.");
  shared.currentSetup = data;
  $("setup-name").value = data.name || name;
  document.querySelectorAll(".sensor-row").forEach((row) => {
    const sensor = data.sensors.find((s) => s.channel === row.dataset.channel);
    if (!sensor) return;
    row.querySelector(".sensor-name").value = sensor.name || row.dataset.channel;
    row.querySelector(".sensor-band-min").value = sensor.band ? sensor.band[0] : "";
    row.querySelector(".sensor-band-max").value = sensor.band ? sensor.band[1] : "";
    row.querySelector(".sensor-kt").value = sensor.temp_sensitivity ?? "";
    setSensorHidden(row, Boolean(sensor.hidden));
  });
  syncTempChannels();
}

async function saveSetup() {
  const name = $("setup-name").value.trim();
  if (!name) { showError("Informe um nome para o setup."); return; }
  showError("");
  try {
    const resp = await fetch("/api/setups", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ setup_name: name, sensors: collectSensors() }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Erro ao salvar setup.");
    await loadSetupList(data.name);
    await applySetup(data.name);
    $("status-text").textContent = `Setup "${data.name}" salvo em data/setups.`;
  } catch (err) {
    showError(err.message);
  }
}

// Banda = λ₀ ± maxHalfWidth, limitada à metade da distância até a grade
// vizinha para que bandas de grades próximas nunca se sobreponham.
function suggestBands(maxHalfWidth = 2.0) {
  const rows = visibleSensorRows();
  const nominals = rows.filter((r) => r.dataset.nominal).map((r) => Number(r.dataset.nominal));
  rows.forEach((row) => {
    const min = row.querySelector(".sensor-band-min");
    const max = row.querySelector(".sensor-band-max");
    if (!row.dataset.nominal || min.value || max.value) return;
    const nominal = Number(row.dataset.nominal);
    const gaps = nominals.map((n) => Math.abs(n - nominal)).filter((d) => d > 0);
    const halfWidth = Math.min(maxHalfWidth, ...gaps.map((d) => d / 2));
    min.value = (nominal - halfWidth).toFixed(3);
    max.value = (nominal + halfWidth).toFixed(3);
  });
  scheduleAutoProcess();
}

export async function loadFileList(selectValue) {
  const resp = await fetch("/api/files");
  const data = await resp.json();
  shared.rawFiles = data.files;

  // Só o catálogo do que existe em data/; o projeto escolhe o que usar
  const sel = $("file-select");
  const atual = sel.value;
  sel.innerHTML = "";
  projectSeriesPaths().forEach((path) => sel.add(new Option(shortName(path), path)));
  if (selectValue && projectSeriesPaths().includes(selectValue)) sel.value = selectValue;
  else if (projectSeriesPaths().includes(atual)) sel.value = atual;

  $("raw-kind-hint").textContent = "";
  renderSeriesFiles();
  renderSpectraFiles();
}

export async function uploadFiles(fileList) {
  const arquivos = [...(fileList || [])];
  if (!arquivos.length) return;
  showError("");
  const enviados = [];
  const erros = [];
  for (const [i, file] of arquivos.entries()) {
    $("status-text").textContent = $("spectra-status").textContent =
      `Enviando ${i + 1} de ${arquivos.length}: ${file.name}…`;
    const form = new FormData();
    form.append("file", file);
    try {
      const resp = await fetch("/api/upload", { method: "POST", body: form });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || "Erro no envio.");
      enviados.push(data.file);
    } catch (err) {
      erros.push(`${file.name}: ${err.message}`);
    }
  }

  await loadFileList();
  await addFilesAndShow(enviados);
  if (erros.length) showError(erros.join(" · "));
}

// Põe os arquivos no projeto e já mostra o último de cada tipo
export async function addFilesAndShow(paths) {
  if (!paths.length) return;
  for (const path of paths) await addFileToProject(path);
  markProjectDirty();

  const series = paths.filter((path) => fileKind(path) !== "spectrum");
  const espectros = paths.length - series.length;
  const naAbaSeries = !$("tab-series-sidebar").classList.contains("hidden");
  if (espectros && !series.length && naAbaSeries) switchTab("spectra");
  if (series.length) {
    await processData({ save: false });
    if (espectros) {
      $("status-text").textContent += ` · ${espectros} espectro(s) foram para a aba Espectros`;
    }
  }
}

// ── Wiring ───────────────────────────────────────────────────────────────────
$("btn-process").addEventListener("click", () => processData());
$("btn-download").addEventListener("click", downloadCsv);
$("btn-setup-save").addEventListener("click", saveSetup);
$("btn-suggest-bands").addEventListener("click", () => { suggestBands(); markProjectDirty(); });
$("file-upload").addEventListener("change", (e) =>
  uploadFiles(e.target.files).catch((err) => showError(err.message)).finally(() => { e.target.value = ""; }));

// Delegação: cobre também os inputs criados dinamicamente (sensores/marcações)
let debounceTimer = null;
export function scheduleAutoProcess() {
  if (!$("auto-process").checked) return;
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(processData, 400);
}

// ── Aba Séries temporais ─────────────────────────────────────────────────────
export function saveCurrentSeriesState() {
  const path = $("file-select").value;
  if (!path || !document.querySelectorAll(".sensor-row").length) return;
  const state = seriesStateFor(path);
  state.sensors = collectSensors();
  state.processing = collectProcessing();
}

export function applySensors(sensors) {
  (sensors || []).forEach((sensor) => {
    const row = document.querySelector(`.sensor-row[data-channel="${CSS.escape(sensor.channel)}"]`);
    if (!row) return;
    row.querySelector(".sensor-name").value = sensor.name || "";
    const [low, high] = sensor.band || [sensor.band_min ?? "", sensor.band_max ?? ""];
    row.querySelector(".sensor-band-min").value = low ?? "";
    row.querySelector(".sensor-band-max").value = high ?? "";
    row.querySelector(".sensor-kt").value = sensor.temp_sensitivity ?? "";
    setSensorHidden(row, Boolean(sensor.hidden));
  });
  syncTempChannels();
}

// O seletor escondido guarda o arquivo em edição; as opções vêm do projeto
function syncSeriesOptions() {
  const select = $("file-select");
  const current = select.value;
  select.innerHTML = "";
  projectSeriesPaths().forEach((path) => select.add(new Option(shortName(path), path)));
  if (projectSeriesPaths().includes(current)) select.value = current;
}

export function renderSeriesFiles() {
  syncSeriesOptions();
  const box = $("series-files");
  const current = $("file-select").value;
  box.innerHTML = "";
  projectSeriesPaths().forEach((path) => {
    const state = seriesStateFor(path);
    const include = document.createElement("input");
    include.type = "checkbox";
    include.className = "series-include";
    include.checked = state.include;
    include.title = "Incluir no processamento em lote";
    include.addEventListener("change", () => {
      state.include = include.checked;
      scheduleConcatPlan();
      markProjectDirty();
    });
    box.appendChild(fileRow(path, {
      selected: path === current, onSelect: showSeriesFile, checkbox: include,
      note: state.processed ? "processado" : "",
    }));
  });
  if (!box.children.length) {
    box.innerHTML = '<span class="hint">Nenhum arquivo neste projeto ainda.</span>';
  }
  document.body.classList.toggle("no-series", !projectSeriesPaths().length);
  $("card-concat").classList.toggle("hidden", projectSeriesPaths().length < 2);
  renderEmptyFiles("series");
  renderFilePicker("series");
  scheduleConcatPlan();
}

async function showSeriesFile(path) {
  await selectSeriesFile(path);
  await processData({ save: false });
}

export async function selectSeriesFile(path) {
  if (path !== $("file-select").value) {
    saveCurrentSeriesState();
    clearSelection({ redraw: false });
    resetAnalysis();
  }
  const novo = !(path in seriesState);
  seriesStateFor(path);          // entra no projeto, se ainda não estava
  syncSeriesOptions();
  $("file-select").value = path;
  renderSeriesFiles();
  await loadChannels();

  const state = seriesStateFor(path);
  if (state.processing) applyProcessing(state.processing);
  if (state.sensors) applySensors(state.sensors);
  if (novo) markProjectDirty();   // só olhar um arquivo não muda o projeto
}

function copySeriesOptions() {
  saveCurrentSeriesState();
  const current = $("file-select").value;
  const source = seriesState[current];
  if (!source) return;
  projectSeriesPaths().filter((path) => path !== current).forEach((path) => {
    const state = seriesStateFor(path);
    state.processing = structuredClone(source.processing);
    state.sensors = structuredClone(source.sensors);
  });
  markProjectDirty();
  $("status-text").textContent = "Opções e sensores copiados para os outros arquivos.";
}

async function processAll() {
  const files = concatFiles();
  if (!files.length) { showError("Marque pelo menos um arquivo para processar."); return; }
  showError("");

  for (const [i, path] of files.entries()) {
    $("status-text").textContent = `Processando ${i + 1} de ${files.length}: ${shortName(path)}…`;
    await selectSeriesFile(path);
    await processData();
  }
  $("status-text").textContent = `${files.length} arquivo(s) processados.`;
}


// ── Concatenação: quem entra, em que ordem e onde emenda ────────────────────
let concatPlan = null;
let concatTimer = null;

const concatFiles = () => projectSeriesPaths().filter((path) => seriesStateFor(path).include);

function moveSeriesFile(path, direcao) {
  const i = seriesOrder.indexOf(path);
  const j = i + direcao;
  if (i < 0 || j < 0 || j >= seriesOrder.length) return;
  [seriesOrder[i], seriesOrder[j]] = [seriesOrder[j], seriesOrder[i]];
  renderSeriesFiles();                 // a lista de arquivos segue a mesma ordem
  markProjectDirty();
}

function concatRow(path, posicao, total, parte) {
  const row = document.createElement("div");
  row.className = "concat-row";

  const numero = document.createElement("span");
  numero.className = "concat-index";
  numero.textContent = `${posicao + 1}.`;

  const nome = document.createElement("span");
  nome.className = "concat-name";
  nome.textContent = baseName(path);
  nome.title = path;

  const botao = (texto, titulo, direcao, desabilitado) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "concat-move";
    b.textContent = texto;
    b.title = titulo;
    b.disabled = desabilitado;
    b.addEventListener("click", () => moveSeriesFile(path, direcao));
    return b;
  };

  const faixa = document.createElement("span");
  faixa.className = "concat-range";
  if (parte) {
    const pausa = parte.source === "relógio"
      ? ` · pausa de ${fmtNum(parte.gap, 3)} s pelo relógio` : "";
    faixa.textContent = `${fmtNum(parte.start, 4)} s → ${fmtNum(parte.end, 4)} s · ` +
      `${parte.n_samples.toLocaleString("pt-BR")} amostras${pausa}`;
  } else {
    faixa.textContent = "—";
  }

  row.append(numero, nome,
             botao("↑", "Subir na ordem", -1, posicao === 0),
             botao("↓", "Descer na ordem", +1, posicao === total - 1),
             faixa);
  return row;
}

function renderConcatRows(arquivos, plano) {
  const lista = $("concat-list");
  lista.innerHTML = "";
  arquivos.forEach((path, i) => lista.appendChild(
    concatRow(path, i, arquivos.length, plano?.parts?.[i])));
  if (!arquivos.length) {
    lista.innerHTML = '<span class="hint">Nenhum arquivo marcado.</span>';
  }
}

async function refreshConcatPlan() {
  const arquivos = concatFiles();
  renderConcatRows(arquivos, null);         // a ordem aparece sem esperar o servidor
  $("btn-process-join").disabled = arquivos.length < 2;

  if (arquivos.length < 2) {
    concatPlan = null;
    $("concat-summary").textContent = "Marque dois ou mais arquivos para juntar.";
    return;
  }
  $("concat-summary").textContent = "Lendo os arquivos…";
  try {
    const resp = await fetch("/api/concat/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files: arquivos }),
    });
    const dados = await resp.json();
    if (!resp.ok) throw new Error(dados.error || "Erro na prévia da concatenação.");
    if (arquivos.join("|") !== concatFiles().join("|")) return;   // já mudou de novo
    concatPlan = dados;
    renderConcatRows(arquivos, dados);
    $("concat-summary").textContent =
      `${dados.parts.length} arquivos · ${dados.n_samples.toLocaleString("pt-BR")} amostras · ` +
      `0 s a ${fmtNum(dados.total_duration, 4)} s no total`;
    if (dados.warnings.length) showError(dados.warnings.join(" "));
  } catch (err) {
    concatPlan = null;
    $("concat-summary").textContent = `Sem prévia: ${err.message}`;
  }
}

function scheduleConcatPlan() {
  if (!$("card-concat").open) { concatPlan = null; return; }
  clearTimeout(concatTimer);
  concatTimer = setTimeout(() => refreshConcatPlan(), 200);
}

async function processJoined() {
  const arquivos = concatFiles();
  if (arquivos.length < 2) { showError("Marque dois ou mais arquivos para juntar."); return; }
  showError("");
  await selectSeriesFile(arquivos[0]);      // valem os sensores e as etapas do primeiro
  $("status-text").textContent = `Juntando ${arquivos.length} arquivos…`;
  await processData({ files: arquivos });
}

$("card-concat").addEventListener("toggle", () => {
  if ($("card-concat").open) refreshConcatPlan();
  markProjectDirty();
});
$("btn-process-join").addEventListener("click",
  () => processJoined().catch((err) => showError(err.message)));
$("btn-copy-series").addEventListener("click", copySeriesOptions);
const SHOW_RAW_KEY = "braggflow.showRaw";
try { $("show-raw").checked = localStorage.getItem(SHOW_RAW_KEY) !== "0"; } catch { /* sem armazenamento */ }
$("show-raw").addEventListener("change", () => {
  try { localStorage.setItem(SHOW_RAW_KEY, $("show-raw").checked ? "1" : "0"); } catch { /* sem armazenamento */ }
  processData({ save: false });
});
$("btn-process-all").addEventListener("click", () => processAll().catch((err) => showError(err.message)));
