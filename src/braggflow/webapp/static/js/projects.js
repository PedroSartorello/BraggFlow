// Projetos: tela inicial, adicionar e tirar arquivos, salvar, abrir,
// excluir e o aviso de alterações não salvas.

import { $, fmtBytes, fmtWhen, showError } from "./core.js";
import { baseName, fileKind, projectSeriesPaths, projectSpectraPaths, seriesOrder, seriesState, seriesStateFor, shared, spectraState, spectraStateFor } from "./state.js";
import { clearSelection, addFilesAndShow, applyProcessing, applySensors, collectProcessing, collectSensors, loadChannels, processData, renderSeriesFiles, saveCurrentSeriesState, selectSeriesFile, uploadFiles } from "./series.js";
import { renderSpectraFiles, resetSpectraAnalyses, saveCurrentSpectrumState, selectSpectrumFile } from "./spectra.js";
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
  remove.textContent = "×";
  remove.title = "Tirar do projeto (não apaga o arquivo)";
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
  $("file-select").innerHTML = "";
  $("marker-list").innerHTML = "";
  $("sensor-list").innerHTML = '<span class="hint">Adicione um arquivo…</span>';
  $("viz-channels").innerHTML = '<span class="hint">Marque uma fonte de dados…</span>';
  $("file-info").textContent = "";
  if (shared.figureOptions) applyStyle(shared.figureOptions.style);
  renderSeriesFiles();
  renderSpectraFiles();
  resetSpectraAnalyses();
  clearSelection({ redraw: false });
  resetAnalysis();
  Plotly.purge($("plot"));
  Plotly.purge($("spectra-plot"));
  $("status-text").textContent = "Adicione arquivos de série temporal.";
  $("spectra-status").textContent = "Adicione arquivos de espectro.";
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
  detail.textContent = `${project.n_series} série(s) · ${project.n_spectra} espectro(s)` +
    ` · ${project.n_markers} marcação(ões) · ${project.updated.replace("T", " ")}` +
    (isLast ? " · último aberto" : "");
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
  excluir.textContent = "Excluir";
  excluir.title = `Excluir o projeto "${project.name}". Arquivos de dados e CSVs processados não são apagados.`;
  excluir.addEventListener("click", () => deleteProject(project.name, excluir).catch((err) => {
    $("gate-error").textContent = err.message;
    $("gate-error").classList.remove("hidden");
  }));

  item.append(row, excluir);
  return item;
}

export async function openProjectGate({ canReturn = false } = {}) {
  const box = $("gate-projects");
  box.innerHTML = '<span class="hint">Carregando…</span>';
  $("btn-gate-back").classList.toggle("hidden", !canReturn);
  $("gate-error").classList.add("hidden");
  $("project-gate").classList.remove("hidden");
  $("project-gate").dataset.canReturn = canReturn ? "1" : "";
  $("gate-name").value = "";         // antes de esperar a lista: não apaga o que for digitado
  let last = null;
  try { last = localStorage.getItem(LAST_PROJECT_KEY); } catch { /* sem armazenamento */ }

  const projects = await loadProjectList().catch(() => []);
  box.innerHTML = "";
  const ordered = [...projects].sort((a, b) => (b.name === last) - (a.name === last));
  ordered.forEach((project) => box.appendChild(projectRow(project, project.name === last)));
  if (!projects.length) {
    box.innerHTML = '<span class="hint">Nenhum projeto salvo ainda. Comece um novo abaixo.</span>';
  }
}

function closeProjectGate() {
  $("project-gate").classList.add("hidden");
}

function startNewProject() {
  const name = $("gate-name").value.trim();
  if (!name) {                       // o nome dá a pasta dos resultados
    $("gate-error").textContent = "Dê um nome ao projeto: os resultados ficam numa pasta com esse nome.";
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
  $("status-text").textContent = name
    ? `Projeto "${name}": adicione os arquivos de série temporal.`
    : "Projeto novo: adicione os arquivos de série temporal.";
}

// ── Adicionar arquivos ao projeto ────────────────────────────────────────────
export function renderFilePicker(kind) {
  const box = kind === "spectrum" ? $("spectra-picker") : $("series-picker");
  const dentro = kind === "spectrum" ? projectSpectraPaths() : projectSeriesPaths();
  const disponiveis = shared.rawFiles
    .filter((f) => (kind === "spectrum" ? f.kind === "spectrum" : f.kind !== "spectrum"))
    .filter((f) => !dentro.includes(f.path))
    .sort((a, b) => (b.modified || "").localeCompare(a.modified || ""));

  box.innerHTML = "";
  if (!disponiveis.length) {
    box.innerHTML = '<span class="hint">Nenhum arquivo disponível fora do projeto.</span>';
    return;
  }
  disponiveis.forEach((f) => {
    const label = document.createElement("label");
    label.className = "check-row";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = kind === "spectrum" ? "pick-spectrum" : "pick-series";
    cb.value = f.path;
    const meta = document.createElement("span");
    meta.className = "file-meta";
    meta.textContent = `${fmtWhen(f.modified)} · ${fmtBytes(f.size || 0)}`;
    label.append(cb, document.createTextNode(baseName(f.path)), meta);
    label.title = f.path;
    box.appendChild(label);
  });
}

async function addPickedFiles(kind) {
  const picked = [...document.querySelectorAll(kind === "spectrum" ? ".pick-spectrum:checked" : ".pick-series:checked")]
    .map((c) => c.value);
  if (!picked.length) { showError("Marque os arquivos que quer adicionar."); return; }
  showError("");
  await addFilesAndShow(picked);
  renderFilePicker(kind);
}

export function renderEmptyFiles(kind) {
  const espectro = kind === "spectrum";
  const box = $(espectro ? "spectra-empty-files" : "series-empty-files");
  const dentro = espectro ? projectSpectraPaths() : projectSeriesPaths();
  const lista = shared.rawFiles
    .filter((f) => (f.kind === "spectrum") === espectro && !dentro.includes(f.path))
    .sort((a, b) => (b.modified || "").localeCompare(a.modified || ""));

  box.innerHTML = "";
  if (!lista.length) return;
  const titulo = document.createElement("div");
  titulo.className = "sub-label";
  titulo.textContent = "Ou use um arquivo já enviado";
  box.appendChild(titulo);
  lista.forEach((f) => {
    const botao = document.createElement("button");
    botao.type = "button";
    botao.className = "empty-file";
    botao.title = f.path;
    [f.path.split("/").pop(), fmtWhen(f.modified), fmtBytes(f.size || 0)].forEach((texto) => {
      const span = document.createElement("span");
      span.textContent = texto;
      botao.appendChild(span);
    });
    botao.addEventListener("click", () => addFilesAndShow([f.path]).catch((err) => showError(err.message)));
    box.appendChild(botao);
  });
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
    uploadFiles(e.dataTransfer.files).catch((err) => showError(err.message));
  });
  zona.querySelector(".dropzone-input").addEventListener("change", (e) =>
    uploadFiles(e.target.files).catch((err) => showError(err.message)).finally(() => { e.target.value = ""; }));
});

export async function addFileToProject(path) {
  if (fileKind(path) === "spectrum") {
    spectraStateFor(path);
    renderSpectraFiles();
    await selectSpectrumFile(path);
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
let restoring = false;           // aplicando um estado (abrir, desfazer): não é mudança do usuário
const historico = { states: [], index: -1 };   // estados para desfazer/refazer

const autosaveOn = () => $("autosave").checked;
try { $("autosave").checked = localStorage.getItem(AUTOSAVE_KEY) !== "0"; } catch { /* sem armazenamento */ }

function setSaveState(texto, erro = false) {
  $("save-state").textContent = texto;
  $("save-state").classList.toggle("erro", erro);
}

const agora = () => new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });

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
  setSaveState("alterações…");
  autosaveTimer = setTimeout(autosaveNow, AUTOSAVE_MS);
}

async function autosaveNow() {
  if (!projectDirty || !autosaveOn()) return;
  if (document.activeElement === $("project-name")) return;   // salva quando sair do campo
  if (!$("project-name").value.trim()) { setSaveState("dê um nome ao projeto para salvar"); return; }
  await saveProject({ silent: true });
}

// Salva o que estiver pendente (trocar de projeto, fechar a página)
async function flushAutosave() {
  clearTimeout(autosaveTimer);
  if (projectDirty && autosaveOn() && $("project-name").value.trim()) await saveProject({ silent: true });
  return !projectDirty;
}

// O estado do projeto, sem o nome (renomear não se desfaz: criaria cópias)
function snapshot() {
  const projeto = collectProject();
  delete projeto.name;
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

function scheduleSnapshot() {
  clearTimeout(snapshotTimer);
  snapshotTimer = setTimeout(pushSnapshot, 450);
}

function pushSnapshot() {
  snapshotTimer = null;
  if (historico.index < 0) return;
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
    spectra_files: projectSpectraPaths().map((path) => ({
      file: path, settings: spectraStateFor(path).settings,
    })),
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
  if (!resp.ok) throw new Error(data.error || "Erro ao listar projetos.");
  return data.projects;
}

async function openProject(name) {
  if (!name) return;
  const resp = await fetch("/api/projects/" + encodeURIComponent(name));
  const project = await resp.json();
  if (!resp.ok) throw new Error(project.error || "Erro ao abrir projeto.");
  try { localStorage.setItem(LAST_PROJECT_KEY, project.name); } catch { /* sem armazenamento */ }
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

  // Estados por arquivo
  (project.series || []).forEach((entry) => {
    const state = seriesStateFor(entry.file);
    state.include = entry.include !== false;
    state.sensors = entry.sensors;
    state.processing = entry.processing;
  });
  (project.spectra_files || []).forEach((entry) => {
    spectraStateFor(entry.file).settings = entry.settings;
  });
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

  $("viz-source").value = project.source === "spectra" ? "spectra" : "series";
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
    showError(`O arquivo "${project.file}" do projeto não está em data/. ` +
              "Envie-o novamente ou escolha outro arquivo.");
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
    if (!silent) showError("Informe um nome para o projeto.");
    return false;
  }
  const seq = changeSeq;
  setSaveState("salvando…");
  try {
    const resp = await fetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectProject()),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Erro ao salvar projeto.");
    try { localStorage.setItem(LAST_PROJECT_KEY, data.name); } catch { /* sem armazenamento */ }
    if (seq === changeSeq) markProjectDirty(false);   // mudou durante o envio: o próximo save leva
    setSaveState(`salvo às ${agora()}`);
    if (!silent) {
      showError("");
      $("status-text").textContent = `Projeto "${data.name}" salvo em data/projects.`;
      $("viz-status").textContent = `Projeto "${data.name}" salvo.`;
    }
    return true;
  } catch (err) {
    setSaveState("erro ao salvar — clique para tentar de novo", true);
    if (!silent) showError(err.message);
    return false;
  }
}

async function deleteProject(name, button) {
  if (button.dataset.confirm !== "1") {          // exclusão em dois cliques
    button.dataset.confirm = "1";
    button.textContent = "Confirmar exclusão";
    button.classList.add("danger");
    setTimeout(() => {
      delete button.dataset.confirm;
      button.textContent = "Excluir";
      button.classList.remove("danger");
    }, 6000);
    return;
  }
  const resp = await fetch("/api/projects/" + encodeURIComponent(name), { method: "DELETE" });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || "Erro ao excluir projeto.");
  try {
    if (localStorage.getItem(LAST_PROJECT_KEY) === name) localStorage.removeItem(LAST_PROJECT_KEY);
  } catch { /* sem armazenamento */ }
  // O projeto aberto continua na tela, mas agora sem cópia salva (e o salvar
  // sozinho não o recria: só um "Salvar" explícito)
  if ($("project-name").value.trim() === name) {
    clearTimeout(autosaveTimer);
    markProjectDirty(true, { history: false, autosave: false });
    $("project-dirty").classList.remove("hidden");
    setSaveState("projeto excluído: Salvar recria");
  }
  await openProjectGate({ canReturn: Boolean($("project-gate").dataset.canReturn) });
}

function newProject() {
  $("project-name").value = "";
  markProjectDirty(false);
  setSaveState("");
  try { localStorage.removeItem(LAST_PROJECT_KEY); } catch { /* sem armazenamento */ }
  $("status-text").textContent = "Projeto novo: ajuste as opções e clique em Salvar projeto.";
}

// ── Alterações não salvas: salvar, descartar ou ficar ───────────────────────
function askLeaveProject() {
  return new Promise((resolve) => {
    const nome = $("project-name").value.trim();
    $("leave-text").textContent = nome
      ? `O projeto "${nome}" tem alterações que ainda não foram salvas.`
      : "Este projeto ainda não foi salvo. Dê um nome para guardá-lo.";
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
        $("leave-error").textContent = $("error-bar").textContent || "Não foi possível salvar.";
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
