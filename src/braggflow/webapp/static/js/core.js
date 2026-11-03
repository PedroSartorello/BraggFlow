// Base da página: $, avisos de erro, formatação de números e o fetch
// que explica respostas em HTML. Dos outros módulos, só importa i18n.js.

import { decimalSeparator, fmtNum, fmtSig, getLanguage, numberLocale, onLanguageChange, t } from "./i18n.js";

export { fmtNum, fmtSig };

export const $ = (id) => document.getElementById(id);

// Precisa bater com API_BUILD em braggflow/webapp/app.py
const API_BUILD = "2026-11-03";

// Todo pedido leva o idioma da interface (Accept-Language): as mensagens do
// servidor voltam nele. E quando o servidor responde com uma página de erro
// (HTML), a mensagem diz o que fazer em vez do críptico "Unexpected token '<'".
const fetchOriginal = window.fetch;
window.fetch = async (url, options = {}) => {
  const headers = new Headers(options.headers || (url instanceof Request ? url.headers : undefined));
  if (!headers.has("Accept-Language")) headers.set("Accept-Language", getLanguage());
  const resp = await fetchOriginal(url, { ...options, headers });
  const endereco = typeof url === "string" ? url : url.url;
  resp.json = async () => {
    const texto = await resp.clone().text();
    try {
      return texto ? JSON.parse(texto) : null;
    } catch {
      throw new Error(`${t("error.htmlResponse", { status: String(resp.status), url: endereco })} ` +
                      t(resp.status === 404 ? "error.restartServer" : "error.seeTerminal"));
    }
  };
  return resp;
};

export async function checkServerBuild() {
  let build = null;
  try {
    build = (await (await fetch("/api/version")).json())?.api_build;
  } catch { /* servidor antigo: nem essa rota existe */ }
  if (build !== API_BUILD) {
    showError(t("error.oldServer", { build: build || t("error.previousVersion"), expected: API_BUILD }));
  }
}

// ── UI helpers ───────────────────────────────────────────────────────────────
// Ícone do conjunto da página (o <svg> com os <symbol> no começo do <body>)
export function icon(nome) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("class", "icon");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(ns, "use");
  use.setAttribute("href", `#i-${nome}`);
  svg.appendChild(use);
  return svg;
}

// ── Textos que acompanham o idioma ──────────────────────────────────────────
// Um elemento escrito por aqui é traduzido de novo quando o idioma muda:
// setText guarda a chave (data-i18n), setReadout guarda como montar a leitura.
// Texto que não se traduz (nome de arquivo, mensagem já pronta) vai por setPlain.
const readouts = new Set();

function forget(el) {
  delete el.dataset.i18n;
  delete el.dataset.i18nVars;
  delete el.dataset.i18nHtml;
  el._readout = null;
  readouts.delete(el);
}

export function setText(el, key, vars) {
  forget(el);
  el.dataset.i18n = key;
  if (vars) el.dataset.i18nVars = JSON.stringify(vars);
  el.textContent = t(key, vars);
}

export function setHtml(el, key) {
  forget(el);
  el.dataset.i18nHtml = key;
  el.innerHTML = t(key);
}

export function setPlain(el, texto) {
  forget(el);
  el.textContent = texto;
}

// Um <span class="hint"> que acompanha o idioma, para o innerHTML de listas vazias
export const hintHtml = (key) => `<span class="hint" data-i18n="${key}">${t(key)}</span>`;

// Barra de status como leitura de instrumento: valores em destaque com o
// rótulo ao lado, observações em texto apagado e o estado no fim, num selo.
// `build()` devolve {partes, estado}: `partes` são [valor, rótulo] ou um
// texto; `estado` é {texto, tipo: ok|warn|info, title?}. Ela é chamada de novo
// quando o idioma muda.
export function setReadout(el, build) {
  forget(el);
  el._readout = { build, notes: [] };
  readouts.add(el);
  drawReadout(el);
}

function noteSpan(key, vars) {
  const span = document.createElement("span");
  span.className = "ro-note";
  setText(span, key, vars);
  return span;
}

function drawReadout(el) {
  const { partes, estado } = el._readout.build();
  el.classList.remove("status-error");
  el.replaceChildren();
  partes.filter((parte) => parte !== null && parte !== "").forEach((parte, i) => {
    if (i) el.append(Object.assign(document.createElement("span"), { className: "visually-hidden", textContent: " · " }));
    const item = document.createElement("span");
    if (typeof parte === "string") {
      item.className = "ro-note";
      item.textContent = parte;
    } else {
      item.className = "ro";
      item.append(Object.assign(document.createElement("b"), { textContent: parte[0] }));
      if (parte[1]) item.append(` ${parte[1]}`);
    }
    el.append(item);
  });
  if (estado) {
    const selo = document.createElement("span");
    selo.className = `ro-state ro-${estado.tipo}`;
    if (estado.title) selo.title = estado.title;
    if (estado.tipo === "ok") selo.append(icon("check"));
    selo.append(estado.texto);
    el.append(" ", selo);
  }
  el._readout.notes.forEach(([key, vars]) => el.append(noteSpan(key, vars)));
}

// Uma observação a mais no fim da barra de status, sem desmontar a leitura
export function appendReadoutNote(el, key, vars) {
  el._readout?.notes.push([key, vars]);
  el.append(noteSpan(key, vars));
}

// Aviso de erro: fixo no topo da área de trabalho, anunciado ao leitor de tela
export function showError(msg) {
  $("error-text").textContent = msg;
  $("error-bar").classList.toggle("visible", Boolean(msg));
}
$("error-close").addEventListener("click", () => showError(""));
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && $("error-bar").classList.contains("visible")) showError("");
});

// Gráfico mostrando um resultado antigo (o último cálculo falhou ou falta
// corrigir um campo): `key` é o texto do selo; sem ela, o selo sai
export function markStale(id, key = "") {
  const el = $(id);
  el.classList.toggle("is-stale", Boolean(key));
  if (key) {
    el.dataset.staleKey = key;
    el.dataset.stale = t(key);
  } else {
    delete el.dataset.staleKey;
    delete el.dataset.stale;
  }
}

// ── Campos com valor que o processamento não aceita ──────────────────────────
// A mensagem fica logo abaixo do campo, antes de qualquer pedido ao servidor.
const FIELD_RULES = {
  "savgol-window": (el) => {
    const janela = Number(el.value), ordem = Number($("savgol-poly").value);
    if (!Number.isInteger(janela) || janela < 3 || janela % 2 === 0) return t("field.oddWindow");
    if (Number.isFinite(ordem) && janela <= ordem) return t("field.windowOverOrder", { order: String(ordem) });
    return "";
  },
  "evo-window": (el) => (el.value.trim() !== "" && !(Number(el.value) > 0)
    ? t("field.positiveOrEmpty") : ""),
};

export function fieldProblem(el) {
  if (el.disabled || el.closest("label")?.classList.contains("hidden")) return "";
  const step = el.closest(".step");
  if (step?.querySelector(".step-switch") && !step.querySelector(".step-switch").checked) return "";
  const v = el.validity;
  if (v.badInput) return t("field.number");
  const propria = FIELD_RULES[el.id]?.(el);      // a regra do campo explica melhor que o limite
  if (propria) return propria;
  if (v.rangeUnderflow) return t("field.min", { min: el.min.replace(".", decimalSeparator()) });
  if (v.rangeOverflow) return t("field.max", { max: el.max.replace(".", decimalSeparator()) });
  return "";
}

let fieldErrorCount = 0;
export function markField(el, msg) {
  const host = el.closest("label") || el.parentElement;
  let note = [...host.children].find((c) => c.classList.contains("field-error") && c.dataset.for === (el.id || el.className));
  if (!msg) {
    el.removeAttribute("aria-invalid");
    if (note) { el.removeAttribute("aria-describedby"); note.remove(); }
    return;
  }
  if (!note) {
    note = document.createElement("span");
    note.className = "field-error";
    note.id = `field-error-${++fieldErrorCount}`;
    note.dataset.for = el.id || el.className;
    host.appendChild(note);
  }
  note.textContent = msg;
  el.setAttribute("aria-invalid", "true");
  el.setAttribute("aria-describedby", note.id);
}

// Confere os campos numéricos de uma área; devolve o primeiro inválido (ou null)
export function checkFields(root) {
  let primeiro = null;
  root.querySelectorAll("input[type=number]").forEach((el) => {
    const problema = fieldProblem(el);
    markField(el, problema);
    if (problema && !primeiro) primeiro = el;
  });
  const step = primeiro?.closest(".step");
  if (step) toggleStep(step, true);           // o campo com problema fica à vista
  return primeiro;
}

// Nome do campo para a mensagem de status ("Janela (ímpar)", "K_T de CH_1"…)
export function fieldName(el) {
  const label = el.closest("label");
  const texto = label ? [...label.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join(" ").trim() : "";
  return texto || el.getAttribute("aria-label") || el.placeholder || t("field.fallbackName");
}

// "Corrija o campo destacado: …" numa linha de status; o nome do campo
// acompanha o idioma
export function showFixField(el, campo) {
  setText(el, "common.fixField", { field: fieldName(campo) });
  el._campo = campo;
  el.classList.add("status-error");
}

// Corrigiu o valor: a mensagem sai na hora
document.addEventListener("input", (e) => {
  if (e.target.matches?.('input[type=number][aria-invalid="true"]')) markField(e.target, fieldProblem(e.target));
  if (e.target.id === "savgol-poly" && $("savgol-window").getAttribute("aria-invalid")) {
    markField($("savgol-window"), fieldProblem($("savgol-window")));
  }
});

export function setBusy(busy) {
  $("btn-process").disabled = busy;
  $("spinner").style.display = busy ? "block" : "none";
}

// Etapas: o interruptor liga a etapa; o nome abre e fecha os parâmetros
function syncStepStates() {
  document.querySelectorAll(".step").forEach((step) => {
    const sw = step.querySelector(".step-switch");
    step.classList.toggle("on", !sw || sw.checked);
  });
}

export function toggleStep(step, open) {
  const body = step.querySelector(".step-body");
  const show = open ?? body.classList.contains("hidden");
  body.classList.toggle("hidden", !show);
  step.classList.toggle("open", show);
  step.querySelector(".step-name")?.setAttribute("aria-expanded", String(show));
}

document.querySelectorAll(".step-name").forEach((button) => {
  button.addEventListener("click", () => toggleStep(button.closest(".step")));
});

// Interruptores das etapas e dos cartões: o nome da etapa é o rótulo deles
document.querySelectorAll(".step").forEach((step, i) => {
  const sw = step.querySelector(".step-switch");
  const nome = step.querySelector(".step-name");
  if (!sw || !nome) return;
  nome.id ||= `step-name-${i}`;
  sw.setAttribute("aria-labelledby", nome.id);
  nome.setAttribute("aria-expanded", "false");
});
document.querySelectorAll(".card-header").forEach((head, i) => {
  const sw = head.querySelector("input[type=checkbox]");
  const titulo = head.querySelector("span");
  if (!sw || !titulo) return;
  titulo.id ||= `card-title-${i}`;
  sw.setAttribute("aria-labelledby", titulo.id);
});

export function syncCardStyles() {
  document.querySelectorAll(".card").forEach((card) => {
    const cb = card.querySelector('.card-header input[type=checkbox]');
    if (cb) card.classList.toggle("enabled", cb.checked);
  });
  syncStepStates();
}

// Separadores dos números nos gráficos do Plotly (decimal, milhar), no idioma da interface
export const plotSeparators = () => (getLanguage() === "en" ? ".," : ",.");

// CSV para planilha, no idioma da interface: ponto e vírgula e vírgula
// decimal (o que o Excel em português abre) ou vírgula e ponto decimal. As
// células vêm como aparecem na tela; "—" (sem valor) fica vazio.
export function toCsv(linhas) {
  const ingles = getLanguage() === "en";
  const sep = ingles ? "," : ";";
  const celula = (valor) => {
    let texto = String(valor ?? "").replace(/—/, "");
    if (ingles && /^-?\d{1,3}(,\d{3})+(\.\d+)?$/.test(texto)) texto = texto.replace(/,/g, "");   // sem o milhar
    return /["\n]/.test(texto) || texto.includes(sep) ? `"${texto.replace(/"/g, '""')}"` : texto;
  };
  return linhas.map((linha) => linha.map(celula).join(sep)).join("\n");
}

// ── Começo vazio: arquivos já enviados, do mais novo para o mais antigo ─────
export const fmtBytes = (n) => (n >= 1024 ** 2
  ? `${(n / 1024 ** 2).toLocaleString(numberLocale(), { maximumFractionDigits: 1 })} MB`
  : `${Math.max(1, Math.round(n / 1024))} kB`);
// Data de um arquivo: 03/11/2026 em português, 2026-11-03 em inglês (sem ambiguidade)
export const fmtWhen = (iso) => (iso
  ? iso.replace(/^(\d{4})-(\d{2})-(\d{2})T/, getLanguage() === "en" ? "$1-$2-$3 " : "$3/$2/$1 ") : "");

// Idioma trocado: leituras, selos de desatualizado e erros dos campos
onLanguageChange(() => {
  readouts.forEach((el) => drawReadout(el));
  document.querySelectorAll("[data-stale-key]").forEach((el) => { el.dataset.stale = t(el.dataset.staleKey); });
  document.querySelectorAll('input[aria-invalid="true"]').forEach((el) => markField(el, fieldProblem(el)));
  document.querySelectorAll('[data-i18n="common.fixField"]').forEach((el) => {
    if (el._campo) setText(el, "common.fixField", { field: fieldName(el._campo) });
  });
});
