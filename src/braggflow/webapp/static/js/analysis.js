// Estatísticas por intervalo entre marcações, abaixo do gráfico da aba Séries
// temporais: do sinal processado que está no gráfico, um canal por linha.

import { $, fmtNum, fmtSig, hintHtml, setText, showError, toCsv } from "./core.js";
import { onLanguageChange, t } from "./i18n.js";
import { currentPlotOptions, plotRelative } from "./series.js";
import { collectMarkers } from "./viz.js";

// ── Estatísticas por intervalo ───────────────────────────────────────────────
let analysisData = null;

export const numeroOuTraco = (v, casas) => (v === null || v === undefined ? "—" : fmtNum(v, casas));

// [chave do título, valor]; os rótulos dos intervalos vêm do servidor, no idioma do pedido
const COLUNAS_INTERVALO = [
  ["stats.col.curve", (l) => l.curva],
  ["stats.col.interval", (l) => l.label],
  ["stats.col.start", (l) => numeroOuTraco(l.start, 2)],
  ["stats.col.end", (l) => numeroOuTraco(l.end, 2)],
  ["stats.col.n", (l) => fmtNum(l.n, 0)],
  ["stats.col.mean", (l) => fmtSig(l.mean)],
  ["stats.col.std", (l) => fmtSig(l.std)],
  ["stats.col.min", (l) => fmtSig(l.min)],
  ["stats.col.max", (l) => fmtSig(l.max)],
  ["stats.col.peakToPeak", (l) => fmtSig(l.peak_to_peak)],
  ["stats.col.drift", (l) => fmtSig(l.slope)],
  ["stats.col.noise", (l) => fmtSig(l.noise)],
  ["stats.col.settle", (l) => fmtSig(l.settle_mean)],
  ["stats.col.delta", (l) => fmtSig(l.delta)],
  ["stats.col.reference", (l) => l.reference || "—"],
];

const COLUNAS_DEGRAU = [
  ["stats.col.curve", (l) => l.curva],
  ["stats.col.marker", (l) => l.label],
  ["stats.col.time", (l) => numeroOuTraco(l.time, 2)],
  ["stats.col.before", (l) => fmtSig(l.before)],
  ["stats.col.after", (l) => fmtSig(l.after)],
  ["stats.col.step", (l) => fmtSig(l.step)],
  ["stats.col.spread", (l) => fmtSig(l.step_spread)],
];

const escapeHtml = (texto) => String(texto).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

export function tabela(titulo, colunas, linhas) {
  if (!linhas.length) return "";
  const cabecalho = colunas.map(([chave]) => `<th>${t(chave)}</th>`).join("");
  const corpo = linhas.map((linha) =>
    `<tr>${colunas.map(([, valor]) => `<td>${escapeHtml(valor(linha))}</td>`).join("")}</tr>`).join("");
  return `<div class="sub-label">${escapeHtml(titulo)}</div>` +
         `<div class="table-wrap"><table class="data-table">` +
         `<thead><tr>${cabecalho}</tr></thead><tbody>${corpo}</tbody></table></div>`;
}

function achatar(dados, campo) {
  return dados.curves.flatMap((curva) =>
    curva[campo].map((linha) => ({ ...linha, curva: curva.key })));
}

function renderAnalysis(dados) {
  analysisData = dados;
  const intervalos = achatar(dados, "intervals");
  const degraus = achatar(dados, "steps");
  const unidade = dados.unit
    ? ` (${dados.relative ? t("stats.unitRelative", { unit: dados.unit }) : dados.unit})` : "";
  $("analysis-result").innerHTML =
    tabela(`${t("stats.intervalsTitle")}${unidade}`, COLUNAS_INTERVALO, intervalos) +
    tabela(`${t("stats.stepsTitle")}${unidade}`, COLUNAS_DEGRAU, degraus) +
    (dados.n_markers ? "" : hintHtml("stats.noMarkers"));
}

let analysisRequest = 0;
let analysisTimer = null;

// Projeto ou arquivo trocado: nada do anterior fica na tabela
export function resetAnalysis() {
  analysisRequest++;
  clearTimeout(analysisTimer);
  analysisData = null;
  $("analysis-result").innerHTML = "";
}

// Marcações, processamento ou exibição mudaram: recalcula se o cartão está aberto
export function scheduleAnalysis() {
  if (!$("analysis-panel").open) { analysisData = null; return; }
  clearTimeout(analysisTimer);
  analysisTimer = setTimeout(() => runAnalysis(), 400);
}

async function runAnalysis() {
  const options = currentPlotOptions();
  if (!options) {
    $("analysis-result").innerHTML = hintHtml("stats.pickFile");
    return;
  }
  const request = ++analysisRequest;
  $("analysis-result").innerHTML = hintHtml("stats.calculating");
  try {
    const resp = await fetch("/api/series/intervals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        options,
        markers: collectMarkers(),
        relative: plotRelative(),
        analysis: {
          settle_window: $("an-settle").value,
          step_window: $("an-step").value,
          reference: $("an-reference").value,
        },
      }),
    });
    const dados = await resp.json();
    if (request !== analysisRequest) return;
    if (!resp.ok) throw new Error(dados.error || t("stats.error"));
    renderAnalysis(dados);
  } catch (err) {
    if (request !== analysisRequest) return;
    showError(err.message);
    const falha = document.createElement("span");
    falha.className = "hint";
    setText(falha, "common.failed", { msg: err.message });
    $("analysis-result").replaceChildren(falha);
  }
}

// CSV no formato da planilha do idioma (ver toCsv)
function analysisCsv() {
  if (!analysisData) return "";
  const linhasCsv = [];
  const bloco = (titulo, colunas, linhas) => {
    if (!linhas.length) return;
    linhasCsv.push([titulo]);
    linhasCsv.push(colunas.map(([chave]) => t(chave)));
    linhas.forEach((linha) => linhasCsv.push(colunas.map(([, valor]) => valor(linha))));
    linhasCsv.push([""]);
  };
  const unidade = analysisData.unit ? ` (${analysisData.unit})` : "";
  bloco(`${t("stats.intervalsTitle")}${unidade}`, COLUNAS_INTERVALO, achatar(analysisData, "intervals"));
  bloco(`${t("stats.stepsCsvTitle")}${unidade}`, COLUNAS_DEGRAU, achatar(analysisData, "steps"));
  return toCsv(linhasCsv);
}

function downloadAnalysis() {
  const csv = analysisCsv();
  if (!csv) { showError(t("stats.calculateFirst")); return; }
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "estatisticas.csv";
  a.click();
  URL.revokeObjectURL(url);
}

// O "?" vive dentro do <summary>, então não pode abrir e fechar o cartão
$("btn-analysis-help").addEventListener("click", (e) => {
  e.preventDefault();
  e.stopPropagation();
  const aberto = $("analysis-help").classList.toggle("hidden");
  $("btn-analysis-help").classList.toggle("on", !aberto);
  if (!$("analysis-panel").open) $("analysis-panel").open = true;
});

$("btn-analyse").addEventListener("click", () => runAnalysis());
$("btn-analysis-csv").addEventListener("click", downloadAnalysis);
$("analysis-panel").addEventListener("toggle", () => {
  if ($("analysis-panel").open && !analysisData) runAnalysis();
});
["an-settle", "an-step", "an-reference"].forEach((id) =>
  $(id).addEventListener("change", () => { if (analysisData) runAnalysis(); }));

// Idioma trocado: calcula de novo (os rótulos dos intervalos vêm do servidor)
onLanguageChange(() => { if (analysisData) runAnalysis(); });
