// Base da página: $, avisos de erro, formatação de números e o fetch
// que explica respostas em HTML. Não importa nada dos outros módulos.

export const $ = (id) => document.getElementById(id);

// Precisa bater com API_BUILD em braggflow/webapp/app.py
const API_BUILD = "2026-10-14";

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
export function showError(msg) {
  const bar = $("error-bar");
  bar.textContent = msg;
  bar.style.display = msg ? "block" : "none";
}

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
}

document.querySelectorAll(".step-name").forEach((button) => {
  button.addEventListener("click", () => toggleStep(button.closest(".step")));
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

// ── Começo vazio: arquivos já enviados, do mais novo para o mais antigo ─────
export const fmtBytes = (n) => (n >= 1024 ** 2
  ? `${(n / 1024 ** 2).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} MB`
  : `${Math.max(1, Math.round(n / 1024))} kB`);
export const fmtWhen = (iso) => (iso ? iso.replace(/^(\d{4})-(\d{2})-(\d{2})T/, "$3/$2/$1 ") : "");
