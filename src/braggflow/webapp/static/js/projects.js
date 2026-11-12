// Projetos: tela inicial, adicionar e tirar arquivos, salvar, abrir,
// excluir e o aviso de alterações não salvas.

import { $, fmtBytes, fmtWhen, hintHtml, icon, setPlain, setText, showError } from "./core.js";
import { numberLocale, onLanguageChange, t } from "./i18n.js";
import { baseName, commonSpectrumSettings, fileKind, folderOf, porNome, projectSeriesPaths, projectSpectraPaths, seriesOrder, seriesState, seriesStateFor, shared, shortName, spectraCommon, spectraState } from "./state.js";
import { clearSelection, addFilesAndShow, applyProcessing, applySensors, resetProcessing, collectProcessing, collectSensors, loadChannels, processData, renderSeriesFiles, saveCurrentSeriesState, selectSeriesFile, uploadFiles } from "./series.js";
import { addSpectraToProject, applySpectraProject, evolutionEventsList, evolutionOptions, renderSpectraFiles, resetSpectraAnalyses, resetSpectraProject, saveCurrentSpectrumState, selectSpectrumFile } from "./spectra.js";
import { addMarkerRow, applySourceMode, applyStyle, channelStyleMemory, collectMarkers, collectStyle, drawPlotMarkers, loadVizSources, refreshVizCurves, rememberChannelStyles, vizSource } from "./viz.js";
import { switchTab } from "./tabs.js";
import { resetAnalysis } from "./analysis.js";

export function fileRow(path, { selected, onSelect, checkbox, note }) {
  const row = document.createElement("div");
  row.className = "file-row" + (selected ? " selected" : "");
  const name = document.createElement("button");
  name.type = "button";
  name.className = "file-name";
  name.textContent = baseName(path);
  name.title = path;
  name.addEventListener("click", () => onSelect(path).catch((err) => showError(err.message)));
  const state = document.createElement("span");
  state.className = "file-state";
  state.textContent = note || "";
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "file-remove";
  remove.append(icon("x"));
  remove.setAttribute("aria-label", t("files.removeLabel", { name: baseName(path) }));
  remove.title = t("files.removeTitle");
  remove.addEventListener("click", (e) => { e.stopPropagation(); removeFileFromProject(path); });
  row.append(checkbox || document.createElement("span"), name, state, remove);
  return row;
}

function clearProjectState() {
  $("card-concat").open = false;
  $("card-markers").open = false;
  Object.keys(seriesState).forEach((path) => delete seriesState[path]);
  seriesOrder.length = 0;
  Object.keys(spectraState).forEach((path) => delete spectraState[path]);
  Object.keys(channelStyleMemory).forEach((key) => delete channelStyleMemory[key]);
  shared.currentSpectrumFile = null;
  shared.spectrumCurves = {};
  shared.seriesCurves = {};
  shared.evolutionCurves = {};
  $("file-select").innerHTML = "";
  $("marker-list").innerHTML = "";
  $("sensor-list").innerHTML = hintHtml("sensors.addFile");
  $("viz-channels").innerHTML = hintHtml("viz.pickSource");
  setPlain($("file-info"), "");
  $("spectra-filter").value = "";
  if (shared.figureOptions) applyStyle(shared.figureOptions.style);
  resetSpectraAnalyses();
  resetSpectraProject();
  renderSeriesFiles();
  renderSpectraFiles();
  clearSelection({ redraw: false });
  resetAnalysis();
  Plotly.purge($("plot"));
  Plotly.purge($("spectra-plot"));
  setText($("status-text"), "project.addSeries");
  setText($("spectra-status"), "project.addSpectra");
}

function projectRow(project, isLast) {
  const item = document.createElement("div");
  item.className = "gate-item";
  const row = document.createElement("button");
  row.type = "button";
  row.className = "gate-row";
  const title = document.createElement("strong");
  title.textContent = project.name;
  const detail = document.createElement("span");
  detail.textContent = [
    t("gate.seriesCount", { n: project.n_series }), t("gate.spectraCount", { n: project.n_spectra }),
    t("gate.markerCount", { n: project.n_markers }), project.updated.replace("T", " "),
    ...(isLast ? [t("gate.lastOpened")] : []),
  ].join(" · ");
  row.append(title, detail);
  row.addEventListener("click", async () => {
    closeProjectGate();
    try {
      await openProject(project.name);
    } catch (err) {
      showError(err.message);
      openProjectGate();
    }
  });

  const excluir = document.createElement("button");
  excluir.type = "button";
  excluir.className = "gate-delete";
  excluir.textContent = t("gate.delete");
  excluir.title = t("gate.deleteTitle", { name: project.name });
  excluir.addEventListener("click", () => deleteProject(project.name, excluir).catch((err) => {
    setPlain($("gate-error"), err.message);
    $("gate-error").classList.remove("hidden");
  }));

  item.append(row, excluir);
  return item;
}

// A lista mostrada no diálogo (desenhada de novo quando o idioma muda)
let gateList = null;   // {projects, last}

function renderProjectList() {
  const box = $("gate-projects");
  const { projects, last } = gateList;
  box.innerHTML = "";
  const ordered = [...projects].sort((a, b) => (b.name === last) - (a.name === last));
  ordered.forEach((project) => box.appendChild(projectRow(project, project.name === last)));
  if (!projects.length) box.innerHTML = hintHtml("gate.noProjects");
}

export async function openProjectGate({ canReturn = false } = {}) {
  const box = $("gate-projects");
  gateList = null;
  box.innerHTML = hintHtml("common.loading");
  $("btn-gate-back").classList.toggle("hidden", !canReturn);
  $("gate-error").classList.add("hidden");
  $("project-gate").classList.remove("hidden");
  $("project-gate").dataset.canReturn = canReturn ? "1" : "";
  $("gate-name").value = "";         // antes de esperar a lista: não apaga o que for digitado
  let last = null;
  try { last = localStorage.getItem(LAST_PROJECT_KEY); } catch { /* sem armazenamento */ }

  const projects = await loadProjectList().catch(() => []);
  gateList = { projects, last };
  renderProjectList();
  // O foco entra no diálogo: o último projeto aberto, ou o nome do novo
  if (!$("project-gate").classList.contains("hidden") && !$("project-gate").contains(document.activeElement)) {
    ($("gate-projects").querySelector(".gate-row") || $("gate-name")).focus();
  }
}

// Diálogo de projetos: Tab circula dentro dele; Esc volta ao projeto atual
$("project-gate").addEventListener("keydown", (e) => {
  if (e.key === "Escape" && $("project-gate").dataset.canReturn) { closeProjectGate(); return; }
  if (e.key !== "Tab") return;
  const focaveis = [...$("project-gate").querySelectorAll("button, input")].filter((el) => el.offsetParent && !el.disabled);
  if (!focaveis.length) return;
  const [primeiro, ultimo] = [focaveis[0], focaveis[focaveis.length - 1]];
  if (e.shiftKey && document.activeElement === primeiro) { e.preventDefault(); ultimo.focus(); }
  else if (!e.shiftKey && document.activeElement === ultimo) { e.preventDefault(); primeiro.focus(); }
});
$("gate-name").addEventListener("input", () => $("gate-error").classList.add("hidden"));

function closeProjectGate() {
  $("project-gate").classList.add("hidden");
}

// O nome de arquivo que o servidor dá ao projeto (_safe_name em app.py); no
// Windows, maiúsculas e minúsculas dão o mesmo arquivo
const projectFileName = (nome) => nome.replace(/[^\p{L}\p{N}._ -]/gu, "").replace(/^[. ]+|[. ]+$/g, "").toLowerCase();

function startNewProject() {
  const name = $("gate-name").value.trim();
  const existente = gateList?.projects.find((p) => projectFileName(p.name) === projectFileName(name));
  if (!name || existente) {          // o nome dá a pasta dos resultados
    setText($("gate-error"), existente ? "gate.nameTaken" : "gate.nameRequired", { name: existente?.name });
    $("gate-error").classList.remove("hidden");
    $("gate-name").focus();
    return;
  }
  clearProjectState();
  newProject();
  $("project-name").value = name;
  resetHistory();
  closeProjectGate();
  switchTab("series");
  setText($("status-text"), "project.startNamed", { name });
}

// ── Adicionar arquivos ao projeto ────────────────────────────────────────────
// Arquivos enviados ficam na raiz de data/raw e data/uploads ou em subpastas
// (uma por ensaio, ou uma pasta enviada inteira): as subpastas viram grupos.
const RAIZES = new Set(["data/raw", "data/uploads"]);
const MAX_SOLTOS = 12;    // na tela vazia, os arquivos soltos que aparecem um a um

function availableFiles(kind) {
  const espectro = kind === "spectrum";
  const dentro = new Set(espectro ? projectSpectraPaths() : projectSeriesPaths());
  return shared.rawFiles.filter((f) => (f.kind === "spectrum") === espectro && !dentro.has(f.path));
}

// [[pasta ou "" para os soltos, arquivos]]: soltos primeiro, do mais recente;
// pastas pelo nome, e dentro delas os arquivos pelo nome (01, 02… 10)
function byFolder(files) {
  const grupos = new Map();
  files.forEach((f) => {
    const pasta = RAIZES.has(folderOf(f.path)) ? "" : folderOf(f.path);
    if (!grupos.has(pasta)) grupos.set(pasta, []);
    grupos.get(pasta).push(f);
  });
  return [...grupos.entries()]
    .sort(([a], [b]) => (a === "" ? -1 : b === "" ? 1 : porNome(a, b)))
    .map(([pasta, lista]) => [pasta, lista.sort(pasta === ""
      ? (a, b) => (b.modified || "").localeCompare(a.modified || "")
      : (a, b) => porNome(a.path, b.path))]);
}

function addAll(paths) {
  showError("");
  addFilesAndShow(paths).catch((err) => showError(err.message));
}

export function renderFilePicker(kind) {
  const espectro = kind === "spectrum";
  const box = $(espectro ? "spectra-picker" : "series-picker");
  const filtro = (espectro ? $("spectrum-picker-filter").value : "").trim().toLowerCase();
  const disponiveis = availableFiles(kind)
    .filter((f) => !filtro || shortName(f.path).toLowerCase().includes(filtro));

  box.innerHTML = "";
  if (!disponiveis.length) {
    box.innerHTML = hintHtml(filtro ? "files.noMatch" : "files.noneAvailable");
    return;
  }
  const fragment = document.createDocumentFragment();
  byFolder(disponiveis).forEach(([pasta, arquivos]) => {
    if (pasta) {
      const head = document.createElement("div");
      head.className = "picker-group";
      const nome = document.createElement("span");
      nome.textContent = `${shortName(pasta)}/ (${arquivos.length})`;
      nome.title = pasta;
      const todos = document.createElement("button");
      todos.type = "button";
      todos.className = "btn-link";
      todos.textContent = t(arquivos.length > 1 ? (filtro ? "files.addThese" : "files.addAll") : "files.addOne");
      todos.addEventListener("click", () => addAll(arquivos.map((f) => f.path)));
      head.append(nome, todos);
      fragment.appendChild(head);
    }
    arquivos.forEach((f) => {
      const label = document.createElement("label");
      label.className = "check-row";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.className = espectro ? "pick-spectrum" : "pick-series";
      cb.value = f.path;
      const meta = document.createElement("span");
      meta.className = "file-meta";
      meta.textContent = `${fmtWhen(f.modified)} · ${fmtBytes(f.size || 0)}`;
      label.append(cb, document.createTextNode(baseName(f.path)), meta);
      label.title = f.path;
      fragment.appendChild(label);
    });
  });
  box.appendChild(fragment);
}

async function addPickedFiles(kind) {
  const picked = [...document.querySelectorAll(kind === "spectrum" ? ".pick-spectrum:checked" : ".pick-series:checked")]
    .map((c) => c.value);
  if (!picked.length) { showError(t("files.checkToAdd")); return; }
  showError("");
  await addFilesAndShow(picked);
  renderFilePicker(kind);
}

function emptyButton(textos, title, onClick) {
  const botao = document.createElement("button");
  botao.type = "button";
  botao.className = "empty-file";
  botao.title = title;
  textos.forEach((texto) => {
    const span = document.createElement("span");
    span.textContent = texto;
    botao.appendChild(span);
  });
  botao.addEventListener("click", onClick);
  return botao;
}

export function renderEmptyFiles(kind) {
  const espectro = kind === "spectrum";
  const box = $(espectro ? "spectra-empty-files" : "series-empty-files");
  const lista = availableFiles(kind);

  box.innerHTML = "";
  if (!lista.length) return;
  const titulo = document.createElement("div");
  titulo.className = "sub-label";
  titulo.textContent = t("files.orUseUploaded");
  box.appendChild(titulo);
  byFolder(lista).forEach(([pasta, arquivos]) => {
    if (pasta) {     // uma pasta inteira de uma vez
      const botao = emptyButton(
        [`${baseName(pasta)}/`, t("files.folderAddAll", { n: arquivos.length })], pasta,
        () => addAll(arquivos.map((f) => f.path)));
      botao.classList.add("empty-folder");
      box.appendChild(botao);
      return;
    }
    arquivos.slice(0, MAX_SOLTOS).forEach((f) => box.appendChild(emptyButton(
      [baseName(f.path), fmtWhen(f.modified), fmtBytes(f.size || 0)], f.path, () => addAll([f.path]))));
    if (arquivos.length > MAX_SOLTOS) {
      const mais = document.createElement("span");
      mais.className = "hint";
      mais.textContent = t("files.moreInSidebar", { n: arquivos.length - MAX_SOLTOS });
      box.appendChild(mais);
    }
  });
}

// Itens soltos na área: arquivos e pastas inteiras, lidas com as subpastas.
// As entradas precisam ser pegas antes do primeiro await (o navegador as
// esvazia quando o evento termina).
async function droppedFiles(dataTransfer) {
  const entradas = [...(dataTransfer.items || [])].map((item) => item.webkitGetAsEntry?.()).filter(Boolean);
  if (!entradas.length) return [...dataTransfer.files];
  const arquivos = [];
  async function visitar(entrada, pasta) {
    const caminho = pasta ? `${pasta}/${entrada.name}` : entrada.name;
    if (entrada.isFile) {
      const file = await new Promise((ok, erro) => entrada.file(ok, erro));
      arquivos.push({ file, path: caminho });
    } else if (entrada.isDirectory) {
      const leitor = entrada.createReader();
      for (;;) {       // readEntries devolve em lotes, até um lote vazio
        const lote = await new Promise((ok, erro) => leitor.readEntries(ok, erro));
        if (!lote.length) break;
        for (const filho of lote) await visitar(filho, caminho);
      }
    }
  }
  for (const entrada of entradas) await visitar(entrada, "");
  return arquivos;
}

// Soltar arquivos fora da área certa não pode abrir o arquivo no navegador
// (o que fecharia a página e perderia o que não foi salvo)
["dragover", "drop"].forEach((tipo) => window.addEventListener(tipo, (e) => e.preventDefault()));
document.querySelectorAll(".dropzone").forEach((zona) => {
  zona.addEventListener("dragover", (e) => { e.preventDefault(); zona.classList.add("over"); });
  zona.addEventListener("dragleave", () => zona.classList.remove("over"));
  zona.addEventListener("drop", (e) => {
    e.preventDefault();
    zona.classList.remove("over");
    droppedFiles(e.dataTransfer).then(uploadFiles).catch((err) => showError(err.message));
  });
  zona.querySelector(".dropzone-input").addEventListener("change", (e) =>
    uploadFiles(e.target.files).catch((err) => showError(err.message)).finally(() => { e.target.value = ""; }));
});

export async function addFileToProject(path) {
  if (fileKind(path) === "spectrum") {
    await addSpectraToProject([path]);
  } else {
    seriesStateFor(path);
    renderSeriesFiles();
    await selectSeriesFile(path);
  }
}

function removeFileFromProject(path) {
  if (fileKind(path) === "spectrum") {
    delete spectraState[path];
    if (shared.currentSpectrumFile === path) shared.currentSpectrumFile = projectSpectraPaths()[0] || null;
    renderSpectraFiles();
    renderFilePicker("spectrum");
    if (shared.currentSpectrumFile) selectSpectrumFile(shared.currentSpectrumFile);
    else Plotly.purge($("spectra-plot"));
  } else {
    delete seriesState[path];
    seriesOrder.splice(seriesOrder.indexOf(path), 1);
    const select = $("file-select");
    [...select.options].filter((o) => o.value === path).forEach((o) => o.remove());
    renderSeriesFiles();
    renderFilePicker("series");
    const next = projectSeriesPaths()[0];
    if (next) selectSeriesFile(next);
    else { select.value = ""; Plotly.purge($("plot")); }
  }
  markProjectDirty();
}

$("btn-gate-new").addEventListener("click", startNewProject);
$("gate-name").addEventListener("keydown", (e) => { if (e.key === "Enter") startNewProject(); });
$("btn-projects").addEventListener("click", async () => {
  if (!(await confirmLeaveProject())) return;
  openProjectGate({ canReturn: true }).catch((err) => showError(err.message));
});
$("btn-gate-back").addEventListener("click", closeProjectGate);
$("btn-add-series").addEventListener("click", () => addPickedFiles("series").catch((err) => showError(err.message)));
$("btn-add-spectra").addEventListener("click", () => addPickedFiles("spectrum").catch((err) => showError(err.message)));


// ── Projetos ─────────────────────────────────────────────────────────────────
// Um projeto guarda arquivo, sensores, etapas, marcações, canais e estilo.
const LAST_PROJECT_KEY = "braggflow.lastProject";
let projectDirty = false;
let pendingVizChannels = null;   // canais do projeto, aplicados quando carregarem

// ── Salvar sozinho e desfazer ────────────────────────────────────────────────
const AUTOSAVE_KEY = "braggflow.autosave";
const AUTOSAVE_MS = 2000;
const HISTORY_MAX = 50;
let autosaveTimer = null;
let snapshotTimer = null;
let changeSeq = 0;               // conta mudanças: um save só limpa o "não salvo" se nada mudou durante ele
let saving = Promise.resolve();  // saves em fila, um de cada vez
// Data de criação do projeto na tela: o servidor só substitui o arquivo que
// tem a mesma (um projeto novo com o nome de outro não o apaga)
let projectCreated = "";
let restoring = false;           // aplicando um estado (abrir, desfazer): não é mudança do usuário
const historico = { states: [], index: -1 };   // estados para desfazer/refazer

const autosaveOn = () => $("autosave").checked;
try { $("autosave").checked = localStorage.getItem(AUTOSAVE_KEY) !== "0"; } catch { /* sem armazenamento */ }

// Indicador do cabeçalho: guarda a chave (e o motivo, no erro) para trocar de idioma
let saveState = { key: "", vars: {}, erro: false };

function setSaveState(key, vars = {}, erro = false) {
  saveState = { key, vars, erro };
  drawSaveState();
}

function drawSaveState() {
  const { key, vars, erro } = saveState;
  const el = $("save-state");
  const hora = vars.at?.toLocaleTimeString(numberLocale(), { hour: "2-digit", minute: "2-digit" });
  el.textContent = key ? t(key, { ...vars, time: hora }) : "";
  el.classList.toggle("erro", erro);
  el.title = erro ? t("project.saveRetryTitle", { msg: vars.msg }) : "";
}

// ``history: false`` para o nome do projeto (não entra no desfazer);
// ``autosave: false`` para o projeto que acabou de ser excluído (não recriar)
export function markProjectDirty(dirty = true, { history: comHistorico = true, autosave = true } = {}) {
  projectDirty = dirty;
  $("project-dirty").classList.toggle("hidden", !dirty || autosaveOn());
  if (!dirty || restoring) return;
  changeSeq++;
  if (comHistorico) scheduleSnapshot();
  if (autosave) scheduleAutosave();
}

function scheduleAutosave() {
  clearTimeout(autosaveTimer);
  if (!autosaveOn()) { setSaveState(""); return; }
  setSaveState("project.saveChanges");
  autosaveTimer = setTimeout(autosaveNow, AUTOSAVE_MS);
}

async function autosaveNow() {
  if (restoring || !projectDirty || !autosaveOn()) return;   // tela pela metade: nada de salvar
  if (document.activeElement === $("project-name")) return;   // salva quando sair do campo
  if (!$("project-name").value.trim()) { setSaveState("project.saveNeedsName"); return; }
  await saveProject({ silent: true });
}

// Salva o que estiver pendente (trocar de projeto, fechar a página)
async function flushAutosave() {
  clearTimeout(autosaveTimer);
  if (projectDirty && autosaveOn() && $("project-name").value.trim()) await saveProject({ silent: true });
  return !projectDirty;
}

// O estado do projeto, sem o nome (renomear não se desfaz: criaria cópias) e
// sem a data de criação (desfazer até antes do 1º salvamento não a apaga)
function snapshot() {
  const projeto = collectProject();
  delete projeto.name;
  delete projeto.created;
  return JSON.stringify(projeto);
}

function updateUndoButtons() {
  $("btn-undo").disabled = historico.index <= 0;
  $("btn-redo").disabled = historico.index >= historico.states.length - 1;
}

function resetHistory() {
  clearTimeout(snapshotTimer);
  historico.states = [snapshot()];
  historico.index = 0;
  updateUndoButtons();
}

function cancelPendingTimers() {
  clearTimeout(autosaveTimer);
  clearTimeout(snapshotTimer);
  snapshotTimer = null;
}

function scheduleSnapshot() {
  clearTimeout(snapshotTimer);
  snapshotTimer = setTimeout(pushSnapshot, 450);
}

function pushSnapshot() {
  snapshotTimer = null;
  if (restoring || historico.index < 0) return;
  const estado = snapshot();
  if (estado === historico.states[historico.index]) return;
  historico.states = historico.states.slice(0, historico.index + 1);
  historico.states.push(estado);
  if (historico.states.length > HISTORY_MAX) historico.states.shift();
  historico.index = historico.states.length - 1;
  updateUndoButtons();
}

async function restoreState(indice) {
  if (snapshotTimer) { clearTimeout(snapshotTimer); pushSnapshot(); }   // a última mudança entra antes
  if (indice < 0 || indice >= historico.states.length || indice === historico.index) return;
  historico.index = indice;
  updateUndoButtons();
  const projeto = JSON.parse(historico.states[indice]);
  projeto.name = $("project-name").value.trim();
  // Painéis abertos continuam abertos: desfazer não muda o que se está vendo
  const paineis = ["card-markers", "analysis-panel"].filter((id) => $(id).open);
  clearTimeout(autosaveTimer);
  restoring = true;
  try {
    await applyProjectData(projeto);
  } finally {
    restoring = false;
  }
  paineis.forEach((id) => { $(id).open = true; });
  markProjectDirty(true, { history: false });       // estado restaurado: salva sozinho de novo
}

export const undo = () => restoreState(historico.index - 1);
export const redo = () => restoreState(historico.index + 1);

// Aceita os dois formatos: o das linhas da tela (band_min/band_max) e o que
// já veio de um projeto salvo (band), para salvar de novo não estragar nada.
function sensorsForProject(sensors) {
  return (sensors || []).map((s) => {
    const low = s.band ? s.band[0] : s.band_min;
    const high = s.band ? s.band[1] : s.band_max;
    const temBanda = ![low, high].some((v) => v === "" || v === null || v === undefined);
    return {
      channel: s.channel,
      name: s.name ?? "",
      nominal_wavelength: s.nominal_wavelength ?? null,
      band: temBanda ? [low, high] : null,
      temp_sensitivity: [undefined, null, ""].includes(s.temp_sensitivity) ? null : s.temp_sensitivity,
      hidden: Boolean(s.hidden),
    };
  });
}

function collectProject() {
  saveCurrentSeriesState();
  saveCurrentSpectrumState();
  const marked = (className) =>
    [...document.querySelectorAll(`.${className}:checked`)].map((c) => c.value);

  return {
    name: $("project-name").value.trim(),
    created: projectCreated,
    file: $("file-select").value,
    sensors: sensorsForProject(collectSensors()),
    processing: collectProcessing(),
    // Um estado independente por arquivo
    series: projectSeriesPaths().map((path) => {
      const state = seriesStateFor(path);
      return {
        file: path,
        include: state.include,
        sensors: sensorsForProject(state.sensors),
        processing: state.processing || {},
      };
    }),
    join_series: $("card-concat").open,
    // No preparo comum, os arquivos não levam preparo próprio
    spectra_files: projectSpectraPaths().map((path) => ({
      file: path,
      settings: spectraCommon.on ? null : spectraState[path].settings,
      exclude: Boolean(spectraState[path].exclude),
    })),
    spectra_common: spectraCommon.on,
    spectra_settings: commonSpectrumSettings(),
    evolution: evolutionOptions(),
    evolution_events: evolutionEventsList(),
    markers: collectMarkers(),
    source: vizSource(),
    viz_sources: { series: marked("viz-series-source"), spectra: marked("viz-spectrum-source") },
    channels: marked("viz-channel"),
    spectra: Object.entries(shared.spectrumCurves)
      .filter(([key]) => document.querySelector(`.viz-ch-row[data-channel="${CSS.escape(key)}"] .viz-channel`)?.checked)
      .map(([, curve]) => curve),
    style: collectStyle(),
  };
}

// Os canais da figura só existem depois que o CSV processado é lido
export function applyVizChannelSelection() {
  const rows = document.querySelectorAll(".viz-ch-row");
  if (!pendingVizChannels || !rows.length) return;
  rows.forEach((row) => {
    row.querySelector(".viz-channel").checked = pendingVizChannels.includes(row.dataset.channel);
  });
  pendingVizChannels = null;
  rememberChannelStyles();
}

async function loadProjectList() {
  const resp = await fetch("/api/projects");
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || t("project.listError"));
  return data.projects;
}

async function openProject(name) {
  if (!name) return;
  const resp = await fetch("/api/projects/" + encodeURIComponent(name));
  const project = await resp.json();
  if (!resp.ok) throw new Error(project.error || t("project.openError"));
  try { localStorage.setItem(LAST_PROJECT_KEY, project.name); } catch { /* sem armazenamento */ }
  cancelPendingTimers();             // timers do projeto anterior não disparam com a tela pela metade
  restoring = true;                  // abrir não é mudança do usuário
  try {
    await applyProjectData(project);
  } finally {
    restoring = false;
  }
  $("card-markers").open = collectMarkers().length > 0;
  markProjectDirty(false);
  setSaveState("");
  resetHistory();                    // o desfazer começa no estado de quando abriu
}

// Põe um projeto na tela (abrir, desfazer, refazer): arquivos, opções de
// cada um, sensores, marcações, estilo e o que estava marcado na figura
async function applyProjectData(project) {
  clearProjectState();               // nada do projeto anterior fica para trás
  $("project-name").value = project.name;
  projectCreated = project.created ?? projectCreated;   // desfazer/refazer não a trazem

  // Estados por arquivo
  (project.series || []).forEach((entry) => {
    const state = seriesStateFor(entry.file);
    state.include = entry.include !== false;
    state.sensors = entry.sensors;
    state.processing = entry.processing;
  });
  applySpectraProject(project);
  $("card-concat").open = Boolean(project.join_series);
  renderSeriesFiles();
  renderSpectraFiles();

  const fileSelect = $("file-select");
  const hasFile = [...fileSelect.options].some((o) => o.value === project.file);
  if (hasFile) fileSelect.value = project.file;

  await loadChannels();
  const state = seriesState[project.file];
  applyProcessing(state?.processing || project.processing);
  applySensors(state?.sensors || project.sensors);

  $("marker-list").innerHTML = "";
  project.markers.forEach((m) => addMarkerRow(m.time, m.label, m.color));
  applyStyle(project.style);

  $("viz-source").value = ["spectra", "evolution"].includes(project.source) ? project.source : "series";
  applySourceMode();
  // Lista vazia = nenhuma preferência: curvas de um CSV marcado depois aparecem
  pendingVizChannels = project.channels?.length ? project.channels : null;

  await loadVizSources();
  const sources = project.viz_sources || {};
  const nomeDoArquivo = (f) => f.split("/").pop();
  document.querySelectorAll(".viz-series-source").forEach((cb) => {
    // CSVs de antes das pastas por projeto valem pelo nome do arquivo
    cb.checked = (sources.series || []).some((f) => nomeDoArquivo(f) === nomeDoArquivo(cb.value));
  });
  document.querySelectorAll(".viz-spectrum-source").forEach((cb) => {
    cb.checked = (sources.spectra || (project.spectra || []).map((s) => s.file)).includes(cb.value);
  });
  await refreshVizCurves();
  applyVizChannelSelection();
  markProjectDirty(false);

  if (!hasFile) {
    if (project.file) {               // projeto só de espectros não tem série: não falta nada
      showError(t("project.fileMissing", { file: project.file }));
    }
    return;
  }
  drawPlotMarkers();
  await processData({ save: false });   // abrir só mostra; quem grava é o Processar
}

// ``silent``: o salvar automático só atualiza o indicador do cabeçalho
export function saveProject({ silent = false } = {}) {
  saving = saving.then(() => saveProjectNow(silent));
  return saving;
}

async function saveProjectNow(silent) {
  clearTimeout(autosaveTimer);
  const name = $("project-name").value.trim();
  if (!name) {
    if (!silent) showError(t("project.nameRequired"));
    return false;
  }
  const seq = changeSeq;
  setSaveState("project.saving");
  try {
    const resp = await fetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectProject()),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || t("project.saveError"));
    projectCreated = data.created || projectCreated;
    try { localStorage.setItem(LAST_PROJECT_KEY, data.name); } catch { /* sem armazenamento */ }
    if (seq === changeSeq) markProjectDirty(false);   // mudou durante o envio: o próximo save leva
    setSaveState("project.savedAt", { at: new Date() });
    if (!silent) {
      showError("");
      setText($("status-text"), "project.savedIn", { name: data.name });
      setText($("viz-status"), "project.saved", { name: data.name });
    }
    return true;
  } catch (err) {
    // O motivo fica à vista: o salvamento não vai dar certo enquanto ele existir
    const motivo = err.message.replace(/^(Projeto inválido|Invalid project):\s*/, "");
    setSaveState("project.notSaved", { reason: motivo, msg: err.message }, true);
    if (!silent) showError(err.message);
    return false;
  }
}

async function deleteProject(name, button) {
  if (button.dataset.confirm !== "1") {          // exclusão em dois cliques
    button.dataset.confirm = "1";
    button.textContent = t("gate.confirmDelete");
    button.classList.add("danger");
    setTimeout(() => {
      delete button.dataset.confirm;
      button.textContent = t("gate.delete");
      button.classList.remove("danger");
    }, 6000);
    return;
  }
  const resp = await fetch("/api/projects/" + encodeURIComponent(name), { method: "DELETE" });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || t("project.deleteError"));
  try {
    if (localStorage.getItem(LAST_PROJECT_KEY) === name) localStorage.removeItem(LAST_PROJECT_KEY);
  } catch { /* sem armazenamento */ }
  // O projeto aberto continua na tela, mas agora sem cópia salva (e o salvar
  // sozinho não o recria: só um "Salvar" explícito)
  if ($("project-name").value.trim() === name) {
    clearTimeout(autosaveTimer);
    markProjectDirty(true, { history: false, autosave: false });
    $("project-dirty").classList.remove("hidden");
    setSaveState("project.deletedState");
  }
  await openProjectGate({ canReturn: Boolean($("project-gate").dataset.canReturn) });
}

function newProject() {
  $("project-name").value = "";
  resetProcessing();     // não herda as etapas do projeto aberto antes
  projectCreated = "";
  markProjectDirty(false);
  setSaveState("");
  try { localStorage.removeItem(LAST_PROJECT_KEY); } catch { /* sem armazenamento */ }
  setText($("status-text"), "project.newAdjust");
}

// ── Alterações não salvas: salvar, descartar ou ficar ───────────────────────
function askLeaveProject() {
  return new Promise((resolve) => {
    const nome = $("project-name").value.trim();
    if (nome) setText($("leave-text"), "leave.unsavedNamed", { name: nome });
    else setText($("leave-text"), "leave.unsavedNew");
    $("leave-name-field").classList.toggle("hidden", Boolean(nome));
    $("leave-error").classList.add("hidden");
    $("leave-name").value = "";
    $("leave-dialog").classList.remove("hidden");

    const fechar = (seguir) => {
      $("leave-dialog").classList.add("hidden");
      $("leave-save").removeEventListener("click", salvar);
      $("leave-discard").removeEventListener("click", descartar);
      $("leave-cancel").removeEventListener("click", cancelar);
      document.removeEventListener("keydown", teclas);
      resolve(seguir);
    };
    async function salvar() {
      if (!nome) {
        const novo = $("leave-name").value.trim();
        if (!novo) { $("leave-name").focus(); return; }
        $("project-name").value = novo;
      }
      await saveProject();
      if (projectDirty) {               // não salvou: mostra o motivo aqui mesmo
        setPlain($("leave-error"), $("error-text").textContent || t("leave.saveFailed"));
        $("leave-error").classList.remove("hidden");
        return;
      }
      fechar(true);
    }
    const descartar = () => fechar(true);
    const cancelar = () => fechar(false);
    const teclas = (e) => { if (e.key === "Escape") cancelar(); };

    $("leave-save").addEventListener("click", salvar);
    $("leave-discard").addEventListener("click", descartar);
    $("leave-cancel").addEventListener("click", cancelar);
    document.addEventListener("keydown", teclas);
    (nome ? $("leave-save") : $("leave-name")).focus();
  });
}

// Com o salvar sozinho, trocar de projeto só salva o que falta; sem ele (ou
// se o save falhar), pergunta
const confirmLeaveProject = async () => {
  if (!projectDirty) return true;
  if (autosaveOn() && await flushAutosave()) return true;
  return askLeaveProject();
};

window.addEventListener("beforeunload", (e) => {
  if (!projectDirty) return;
  if (autosaveOn() && $("project-name").value.trim()) {
    // A página está fechando: envia o projeto mesmo assim (keepalive) e não pergunta
    fetch("/api/projects", {
      method: "POST", keepalive: true,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectProject()),
    }).catch(() => {});
    return;
  }
  e.preventDefault();
  e.returnValue = "";
});

$("btn-project-save").addEventListener("click", () => saveProject());
// O nome entra no projeto ao sair do campo (ou Enter), não a cada letra:
// salvar com outro nome cria uma cópia
$("project-name").addEventListener("input", () => markProjectDirty(true, { history: false, autosave: false }));
$("project-name").addEventListener("change", () => { if (autosaveOn()) saveProject({ silent: true }); });
$("project-name").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.target.blur(); saveProject(); } });
$("save-state").addEventListener("click", () => { if ($("save-state").classList.contains("erro")) saveProject(); });
$("autosave").addEventListener("change", () => {
  try { localStorage.setItem(AUTOSAVE_KEY, autosaveOn() ? "1" : "0"); } catch { /* sem armazenamento */ }
  $("project-dirty").classList.toggle("hidden", !projectDirty || autosaveOn());
  if (autosaveOn() && projectDirty) scheduleAutosave();
  else setSaveState("");
});
$("btn-undo").addEventListener("click", () => undo().catch((err) => showError(err.message)));
$("btn-redo").addEventListener("click", () => redo().catch((err) => showError(err.message)));

// Idioma trocado: o indicador de salvamento e a lista do diálogo de projetos
onLanguageChange(() => {
  drawSaveState();
  if (gateList && !$("project-gate").classList.contains("hidden")) renderProjectList();
});
