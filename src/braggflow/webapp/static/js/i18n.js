// Idioma da interface: português do Brasil (o padrão) ou inglês. Os textos
// ficam em strings.js; a página marca os seus com data-i18n (o texto),
// data-i18n-html (texto com <em>, <sub>…) e data-i18n-title, -placeholder,
// -aria-label e -alt (os atributos). Não importa nada dos outros módulos.
//
// O idioma das figuras é outra opção (Rótulos automáticos, na aba Figura):
// a figura vai para o artigo, a interface é de quem a usa.

import STRINGS from "./strings.js";

export const LANGUAGES = ["pt-BR", "en"];
const STORAGE_KEY = "braggflow.language";
const ATTRIBUTES = ["title", "placeholder", "aria-label", "alt"];

function storedLanguage() {
  try {
    const salvo = localStorage.getItem(STORAGE_KEY);
    return LANGUAGES.includes(salvo) ? salvo : null;
  } catch {
    return null;       // sem armazenamento: fica o padrão
  }
}

let current = storedLanguage() || "pt-BR";
const listeners = [];

export const getLanguage = () => current;
const field = () => (current === "en" ? "en" : "pt");

// ── Números: seguem o idioma da interface (1.550,25 ou 1,550.25) ────────────
export const numberLocale = () => (current === "en" ? "en-US" : "pt-BR");

export const fmtNum = (v, digits = 3) =>
  Number(v).toLocaleString(numberLocale(), { maximumFractionDigits: digits });

// Medidas: 4 casas para níveis absolutos (1.550,0123), 4 algarismos para o
// resto (0,0541; 0,0008834), para que valores pequenos não virem 0
export function fmtSig(v) {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return Math.abs(v) >= 100
    ? v.toLocaleString(numberLocale(), { maximumFractionDigits: 4 })
    : v.toLocaleString(numberLocale(), { maximumSignificantDigits: 4 });
}

// Separador decimal do idioma, para números escritos fora do toLocaleString
export const decimalSeparator = () => (current === "en" ? "." : ",");

// ── Textos ───────────────────────────────────────────────────────────────────
// `{nome}` recebe vars.nome; um número sai formatado no idioma, com até 3
// casas, ou N casas em `{nome:N}`. Um texto com duas formas ([um, vários])
// escolhe pela variável `n`.
export function t(key, vars = {}) {
  const entry = STRINGS[key];
  if (!entry) {
    console.warn(`i18n: texto ausente: ${key}`);
    return key;
  }
  let texto = entry[field()] ?? entry.pt;
  if (Array.isArray(texto)) texto = texto[vars.n === 1 ? 0 : 1];
  return texto.replace(/\{(\w+)(?::(\d+))?\}/g, (marca, nome, casas) => {
    if (!(nome in vars)) return marca;
    const valor = vars[nome];
    return typeof valor === "number" ? fmtNum(valor, casas === undefined ? 3 : Number(casas)) : String(valor);
  });
}

// Troca só o texto de um elemento: ícones, campos e teclas dentro dele ficam
// (o texto é o primeiro trecho não vazio, com os espaços em volta preservados)
export function setNodeText(el, texto) {
  if (!el.firstElementChild) { el.textContent = texto; return; }
  const no = [...el.childNodes].find((n) => n.nodeType === Node.TEXT_NODE && n.textContent.trim());
  if (!no) { el.append(texto); return; }
  const [, antes, , depois] = no.textContent.match(/^(\s*)([\s\S]*?)(\s*)$/);
  no.textContent = antes + texto + depois;
}

const varsOf = (el) => (el.dataset.i18nVars ? JSON.parse(el.dataset.i18nVars) : {});

// Põe no idioma atual tudo o que está marcado dentro de `root`
export function applyI18n(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((el) => setNodeText(el, t(el.dataset.i18n, varsOf(el))));
  root.querySelectorAll("[data-i18n-html]").forEach((el) => { el.innerHTML = t(el.dataset.i18nHtml); });
  ATTRIBUTES.forEach((attr) => root.querySelectorAll(`[data-i18n-${attr}]`).forEach((el) => {
    el.setAttribute(attr, t(el.getAttribute(`data-i18n-${attr}`)));
  }));
}

// Quem desenha textos fora do HTML (tabelas, listas, gráficos) se registra
// aqui e desenha de novo quando o idioma muda
export function onLanguageChange(fn) {
  listeners.push(fn);
}

export function setLanguage(lang) {
  if (!LANGUAGES.includes(lang) || lang === current) return;
  current = lang;
  try { localStorage.setItem(STORAGE_KEY, lang); } catch { /* sem armazenamento: vale até recarregar */ }
  syncLanguage();
  listeners.forEach((fn) => {
    try {
      fn(lang);
    } catch (err) {
      console.warn("i18n:", err);       // um módulo que falhou não deixa os outros sem traduzir
    }
  });
}

// Os seletores de idioma: o do cabeçalho e o do diálogo de projetos
const switches = () => document.querySelectorAll(".lang-switch input[type=radio]");

function syncLanguage() {
  document.documentElement.lang = current;
  switches().forEach((el) => { el.checked = el.value === current; });
  applyI18n();
}

switches().forEach((el) =>
  el.addEventListener("change", () => { if (el.checked) setLanguage(el.value); }));

if (current !== "pt-BR") syncLanguage();       // o HTML já vem em português
else document.documentElement.lang = current;
