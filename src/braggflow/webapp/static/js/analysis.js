// Estatísticas por intervalo entre marcações, abaixo do gráfico da aba Séries
// temporais: do sinal processado que está no gráfico, um canal por linha.

import { $, fmtNum, fmtSig, showError } from "./core.js";
import { currentPlotOptions, plotRelative } from "./series.js";
import { collectMarkers } from "./viz.js";

// ── Estatísticas por intervalo ───────────────────────────────────────────────
let analysisData = null;

export const numeroOuTraco = (v, casas) => (v === null || v === undefined ? "—" : fmtNum(v, casas));

const COLUNAS_INTERVALO = [
  ["curva", (l) => l.curva],
  ["intervalo", (l) => l.label],
  ["início (s)", (l) => numeroOuTraco(l.start, 2)],
  ["fim (s)", (l) => numeroOuTraco(l.end, 2)],
  ["n", (l) => l.n.toLocaleString("pt-BR")],
  ["média", (l) => fmtSig(l.mean)],
  ["σ", (l) => fmtSig(l.std)],
  ["mín", (l) => fmtSig(l.min)],
  ["máx", (l) => fmtSig(l.max)],
  ["pico a pico", (l) => fmtSig(l.peak_to_peak)],
  ["deriva (/s)", (l) => fmtSig(l.slope)],
  ["ruído", (l) => fmtSig(l.noise)],
  ["regime", (l) => fmtSig(l.settle_mean)],
  ["Δ vs ref.", (l) => fmtSig(l.delta)],
  ["referência", (l) => l.reference || "—"],
];

const COLUNAS_DEGRAU = [
  ["curva", (l) => l.curva],
  ["marcação", (l) => l.label],
  ["t (s)", (l) => numeroOuTraco(l.time, 2)],
  ["antes", (l) => fmtSig(l.before)],
  ["depois", (l) => fmtSig(l.after)],
  ["degrau", (l) => fmtSig(l.step)],
  ["dispersão", (l) => fmtSig(l.step_spread)],
];

export function tabela(titulo, colunas, linhas) {
  if (!linhas.length) return "";
  const cabecalho = colunas.map(([nome]) => `<th>${nome}</th>`).join("");
  const corpo = linhas.map((linha) =>
    `<tr>${colunas.map(([, valor]) => `<td>${valor(linha)}</td>`).join("")}</tr>`).join("");
  return `<div class="sub-label">${titulo}</div>` +
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
  const unidade = dados.unit ? ` (${dados.unit}${dados.relative ? ", relativo ao início" : ""})` : "";
  $("analysis-result").innerHTML =
    tabela(`Intervalos${unidade}`, COLUNAS_INTERVALO, intervalos) +
    tabela(`Degrau em cada marcação${unidade}`, COLUNAS_DEGRAU, degraus) +
    (dados.n_markers ? "" :
      '<span class="hint">Sem marcações, o sinal inteiro vira um único intervalo. ' +
      "Marque instantes com a ferramenta Marcar do gráfico.</span>");
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
    $("analysis-result").innerHTML = '<span class="hint">Escolha um arquivo para ver o sinal processado.</span>';
    return;
  }
  const request = ++analysisRequest;
  $("analysis-result").innerHTML = '<span class="hint">Calculando…</span>';
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
    if (!resp.ok) throw new Error(dados.error || "Erro ao calcular as estatísticas.");
    renderAnalysis(dados);
  } catch (err) {
    if (request !== analysisRequest) return;
    showError(err.message);
    $("analysis-result").innerHTML = `<span class="hint">Falha: ${err.message}</span>`;
  }
}

// CSV com ponto e vírgula e vírgula decimal, que é o que o Excel brasileiro abre
function analysisCsv() {
  if (!analysisData) return "";
  const linhasCsv = [];
  const bloco = (titulo, colunas, linhas) => {
    if (!linhas.length) return;
    linhasCsv.push(titulo);
    linhasCsv.push(colunas.map(([nome]) => nome).join(";"));
    linhas.forEach((linha) => {
      linhasCsv.push(colunas.map(([, valor]) => valor(linha).replace(/—/, "")).join(";"));
    });
    linhasCsv.push("");
  };
  const unidade = analysisData.unit ? ` (${analysisData.unit})` : "";
  bloco(`Intervalos${unidade}`, COLUNAS_INTERVALO, achatar(analysisData, "intervals"));
  bloco(`Degrau em cada marcacao${unidade}`, COLUNAS_DEGRAU, achatar(analysisData, "steps"));
  return linhasCsv.join("\n");
}

function downloadAnalysis() {
  const csv = analysisCsv();
  if (!csv) { showError("Calcule as estatísticas antes de baixar."); return; }
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
