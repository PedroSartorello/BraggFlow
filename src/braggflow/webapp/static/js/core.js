// Base da página: $, avisos de erro, formatação de números e o fetch
// que explica respostas em HTML. Não importa nada dos outros módulos.

export const $ = (id) => document.getElementById(id);

// Precisa bater com API_BUILD em braggflow/webapp/app.py
const API_BUILD = "2026-10-27";

// Quando o servidor responde com uma página de erro (HTML), a mensagem diz o
// que fazer em vez do críptico "Unexpected token '<'".
const fetchOriginal = window.fetch;
window.fetch = async (url, options) => {
  const resp = await fetchOriginal(url, options);
  const endereco = typeof url === "string" ? url : url.url;
  resp.json = async () => {
    const texto = await resp.clone().text();
    try {
      return texto ? JSON.parse(texto) : null;
    } catch {
      throw new Error(
        `O servidor respondeu com uma página (HTTP ${resp.status}) em ${endereco}, não com dados. ` +
        (resp.status === 404
          ? "Se você atualizou o BraggFlow, reinicie o servidor: Ctrl+C e braggflow-web."
          : "Veja o erro no terminal onde o servidor está rodando."));
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
    showError(`Esta página é mais nova que o servidor (${build || "versão anterior"} ≠ ${API_BUILD}). ` +
              "Reinicie o servidor: Ctrl+C no terminal e braggflow-web.");
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

// Barra de status como leitura de instrumento: valores em destaque com o
// rótulo ao lado, observações em texto apagado e o estado no fim, num selo.
// `partes`: [valor, rótulo] ou um texto; `estado`: {texto, tipo: ok|warn|info, title?}
export function setReadout(el, partes, estado = null) {
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
}

// Uma observação a mais no fim da barra de status, sem desmontar a leitura
export function appendReadoutNote(el, texto) {
  el.append(Object.assign(document.createElement("span"), { className: "ro-note", textContent: texto }));
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

// Gráfico mostrando um resultado antigo (o último cálculo falhou ou falta corrigir um campo)
export function markStale(id, texto = "") {
  const el = $(id);
  el.classList.toggle("is-stale", Boolean(texto));
  if (texto) el.dataset.stale = texto;
  else delete el.dataset.stale;
}

// ── Campos com valor que o processamento não aceita ──────────────────────────
// A mensagem fica logo abaixo do campo, antes de qualquer pedido ao servidor.
const FIELD_RULES = {
  "savgol-window": (el) => {
    const janela = Number(el.value), ordem = Number($("savgol-poly").value);
    if (!Number.isInteger(janela) || janela < 3 || janela % 2 === 0) return "Use um número ímpar a partir de 3.";
    if (Number.isFinite(ordem) && janela <= ordem) return `A janela precisa ser maior que a ordem (${ordem}).`;
    return "";
  },
  "evo-window": (el) => (el.value.trim() !== "" && !(Number(el.value) > 0)
    ? "Use um valor maior que zero, ou deixe vazio para não limitar." : ""),
};

export function fieldProblem(el) {
  if (el.disabled || el.closest("label")?.classList.contains("hidden")) return "";
  const step = el.closest(".step");
  if (step?.querySelector(".step-switch") && !step.querySelector(".step-switch").checked) return "";
  const v = el.validity;
  if (v.badInput) return "Digite um número.";
  const propria = FIELD_RULES[el.id]?.(el);      // a regra do campo explica melhor que o limite
  if (propria) return propria;
  if (v.rangeUnderflow) return `Use um valor a partir de ${el.min.replace(".", ",")}.`;
  if (v.rangeOverflow) return `Use um valor até ${el.max.replace(".", ",")}.`;
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
  return texto || el.getAttribute("aria-label") || el.placeholder || "campo";
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

export const fmtNum = (v, digits = 3) =>
  Number(v).toLocaleString("pt-BR", { maximumFractionDigits: digits });

// Medidas: 4 casas para níveis absolutos (1.550,0123), 4 algarismos para o
// resto (0,0541; 0,0008834), para que valores pequenos não virem 0
export function fmtSig(v) {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return Math.abs(v) >= 100
    ? v.toLocaleString("pt-BR", { maximumFractionDigits: 4 })
    : v.toLocaleString("pt-BR", { maximumSignificantDigits: 4 });
}

// ── Começo vazio: arquivos já enviados, do mais novo para o mais antigo ─────
export const fmtBytes = (n) => (n >= 1024 ** 2
  ? `${(n / 1024 ** 2).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} MB`
  : `${Math.max(1, Math.round(n / 1024))} kB`);
export const fmtWhen = (iso) => (iso ? iso.replace(/^(\d{4})-(\d{2})-(\d{2})T/, "$3/$2/$1 ") : "");
