// Estatísticas por intervalo entre marcações (cartão da aba Visualização).

import { $, fmtNum, showError } from "./core.js";
import { collectVizOptions } from "./viz.js";

// ── Estatísticas por intervalo ───────────────────────────────────────────────
let analysisData = null;

export const numeroOuTraco = (v, casas) => (v === null || v === undefined ? "—" : fmtNum(v, casas));

const COLUNAS_INTERVALO = [
  ["curva", (l) => l.curva],
  ["intervalo", (l) => l.label],
  ["início (s)", (l) => numeroOuTraco(l.start, 2)],
  ["fim (s)", (l) => numeroOuTraco(l.end, 2)],
  ["n", (l) => l.n.toLocaleString("pt-BR")],
  ["média", (l) => numeroOuTraco(l.mean, 4)],
  ["σ", (l) => numeroOuTraco(l.std, 4)],
  ["mín", (l) => numeroOuTraco(l.min, 4)],
  ["máx", (l) => numeroOuTraco(l.max, 4)],
  ["pico a pico", (l) => numeroOuTraco(l.peak_to_peak, 4)],
  ["deriva (/s)", (l) => numeroOuTraco(l.slope, 5)],
  ["ruído", (l) => numeroOuTraco(l.noise, 4)],
  ["regime", (l) => numeroOuTraco(l.settle_mean, 4)],
  ["Δ vs ref.", (l) => numeroOuTraco(l.delta, 4)],
  ["referência", (l) => l.reference || "—"],
];

const COLUNAS_DEGRAU = [
  ["curva", (l) => l.curva],
  ["marcação", (l) => l.label],
  ["t (s)", (l) => numeroOuTraco(l.time, 2)],
  ["antes", (l) => numeroOuTraco(l.before, 4)],
  ["depois", (l) => numeroOuTraco(l.after, 4)],
  ["degrau", (l) => numeroOuTraco(l.step, 4)],
  ["dispersão", (l) => numeroOuTraco(l.step_spread, 4)],
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
  const unidade = dados.unit ? ` (${dados.unit})` : "";
  $("analysis-result").innerHTML =
    tabela(`Intervalos${unidade}`, COLUNAS_INTERVALO, intervalos) +
    tabela(`Degrau em cada marcação${unidade}`, COLUNAS_DEGRAU, degraus) +
    (dados.n_markers ? "" :
      '<span class="hint">Sem marcações, o sinal inteiro vira um único intervalo. ' +
      'Adicione marcações no cartão "Marcações e eixos".</span>');
}

async function runAnalysis() {
  const opts = collectVizOptions();
  if (opts.source === "spectra") {
    showError("A análise estatística é das séries no tempo.");
    return;
  }
  if (!opts.series.length) { showError("Marque pelo menos uma curva."); return; }
  showError("");
  $("analysis-result").innerHTML = '<span class="hint">Calculando…</span>';
  try {
    const resp = await fetch("/api/analysis", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...opts,
        analysis: {
          settle_window: $("an-settle").value,
          step_window: $("an-step").value,
          reference: $("an-reference").value,
        },
      }),
    });
    const dados = await resp.json();
    if (!resp.ok) throw new Error(dados.error || "Erro ao calcular as estatísticas.");
    renderAnalysis(dados);
  } catch (err) {
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
  const temCurvas = document.querySelectorAll(".viz-channel:checked").length;
  if ($("analysis-panel").open && !analysisData && temCurvas) runAnalysis();
});
