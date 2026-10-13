"""
Estatísticas de séries no tempo, usando as marcações como fronteiras.

Duas leituras do mesmo sinal:

* **Por intervalo** — o trecho entre duas marcações consecutivas (um patamar
  de gás, de pressão, de vazão): média, dispersão, extremos, deriva e ruído,
  mais a diferença de amplitude em relação a outro intervalo.
* **Por marcação** — o degrau na transição: média depois menos média antes,
  medidas em janelas iguais dos dois lados.

Tudo opera sobre o tempo em segundos e sobre os valores como aparecem na
figura (Δλ em pm, por exemplo), para que tabela e gráfico contem a mesma
história.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np

REFERENCES = ("previous", "first", "none")


@dataclass
class Interval:
    label: str
    start: float
    end: float


def intervals_from_markers(markers: Sequence[dict], t_min: float, t_max: float,
                           include_before: bool = True) -> List[Interval]:
    """
    Converte as marcações em intervalos ``[início, fim)``.

    Cada marcação abre um intervalo que vai até a marcação seguinte (ou até o
    fim dos dados). Com ``include_before``, o trecho antes da primeira
    marcação também vira um intervalo, chamado "antes da 1ª marcação".
    """
    pontos = sorted(
        (m for m in markers if t_min <= m["time"] <= t_max),
        key=lambda m: m["time"],
    )
    if not pontos:
        return [Interval("todo o sinal", t_min, t_max)]

    intervalos = []
    if include_before and pontos[0]["time"] > t_min:
        intervalos.append(Interval("antes da 1ª marcação", t_min, pontos[0]["time"]))
    for i, marcacao in enumerate(pontos):
        fim = pontos[i + 1]["time"] if i + 1 < len(pontos) else t_max
        rotulo = (marcacao.get("label") or "").strip() or f"marcação {i + 1}"
        intervalos.append(Interval(rotulo, marcacao["time"], fim))
    return intervalos


def _window_mean(time: np.ndarray, values: np.ndarray, start: float, end: float) -> Dict[str, Optional[float]]:
    mask = (time >= start) & (time < end) & np.isfinite(values)
    if not mask.any():
        return {"mean": None, "std": None, "n": 0}
    trecho = values[mask]
    return {
        "mean": float(np.mean(trecho)),
        "std": float(np.std(trecho, ddof=1)) if len(trecho) > 1 else 0.0,
        "n": int(len(trecho)),
    }


def interval_statistics(time: np.ndarray, values: np.ndarray, interval: Interval,
                        settle_window: Optional[float] = None) -> dict:
    """
    Estatísticas de um intervalo.

    ``settle_window`` (em segundos) mede a média de regime nos últimos
    segundos do intervalo — é o que os ensaios de patamar costumam reportar,
    por ignorar o transitório logo depois da troca.

    A deriva vem de uma reta ajustada ao trecho; ``noise`` é o desvio dos
    resíduos dessa reta, isto é, o que sobra depois de tirar a tendência.
    """
    mask = (time >= interval.start) & (time < interval.end)
    t, y = time[mask], values[mask]
    validos = np.isfinite(y)
    t, y = t[validos], y[validos]

    linha = {
        "label": interval.label,
        "start": float(interval.start),
        "end": float(interval.end),
        "duration": float(interval.end - interval.start),
        "n": int(len(y)),
        "mean": None, "std": None, "median": None, "min": None, "max": None,
        "peak_to_peak": None, "slope": None, "slope_error": None, "noise": None,
        "settle_mean": None, "settle_std": None, "settle_n": 0,
    }
    if not len(y):
        return linha

    linha.update({
        "mean": float(np.mean(y)),
        "std": float(np.std(y, ddof=1)) if len(y) > 1 else 0.0,
        "median": float(np.median(y)),
        "min": float(np.min(y)),
        "max": float(np.max(y)),
        "peak_to_peak": float(np.ptp(y)),
    })

    if len(y) > 2 and np.ptp(t) > 0:
        coeficientes, covariancia = np.polyfit(t - t[0], y, 1, cov=True)
        linha["slope"] = float(coeficientes[0])            # por segundo
        linha["slope_error"] = float(np.sqrt(covariancia[0, 0]))
        residuos = y - np.polyval(coeficientes, t - t[0])
        linha["noise"] = float(np.std(residuos, ddof=2))

    if settle_window:
        regime = _window_mean(t, y, max(interval.start, interval.end - settle_window), interval.end)
        linha.update({"settle_mean": regime["mean"], "settle_std": regime["std"],
                      "settle_n": regime["n"]})
    return linha


def _amplitude(linha: dict) -> Optional[float]:
    """Amplitude do intervalo: a média de regime quando existir, senão a média."""
    return linha["settle_mean"] if linha["settle_mean"] is not None else linha["mean"]


def add_differences(linhas: List[dict], reference: str = "previous") -> List[dict]:
    """
    Diferença de amplitude entre intervalos.

    ``previous`` compara cada intervalo com o anterior (o degrau de um patamar
    para o outro) e ``first`` compara todos com o primeiro (a variação
    acumulada desde a linha de base).
    """
    if reference not in REFERENCES:
        raise ValueError(f"Referência inválida: {reference}. Use {', '.join(REFERENCES)}.")

    for i, linha in enumerate(linhas):
        linha["delta"] = None
        linha["delta_spread"] = None
        linha["reference"] = None
        if reference == "none" or i == 0:
            continue

        base = linhas[i - 1] if reference == "previous" else linhas[0]
        atual, anterior = _amplitude(linha), _amplitude(base)
        if atual is None or anterior is None:
            continue
        linha["delta"] = atual - anterior
        linha["reference"] = base["label"]

        espalhamentos = [linha.get("settle_std") if linha["settle_mean"] is not None else linha["std"],
                         base.get("settle_std") if base["settle_mean"] is not None else base["std"]]
        if all(v is not None for v in espalhamentos):
            linha["delta_spread"] = float(np.hypot(*espalhamentos))
    return linhas


def marker_steps(time: np.ndarray, values: np.ndarray, markers: Sequence[dict],
                 window: float) -> List[dict]:
    """
    Degrau em cada marcação: média de ``window`` segundos depois menos a média
    dos mesmos ``window`` segundos antes. É a resposta direta à pergunta
    "quanto o sinal mudou nesta marcação".
    """
    if window <= 0:
        raise ValueError("A janela do degrau deve ser maior que zero.")

    degraus = []
    for i, marcacao in enumerate(sorted(markers, key=lambda m: m["time"])):
        instante = marcacao["time"]
        antes = _window_mean(time, values, instante - window, instante)
        depois = _window_mean(time, values, instante, instante + window)
        degrau = (None if antes["mean"] is None or depois["mean"] is None
                  else depois["mean"] - antes["mean"])
        espalhamento = (None if antes["std"] is None or depois["std"] is None
                        else float(np.hypot(antes["std"], depois["std"])))
        degraus.append({
            "label": (marcacao.get("label") or "").strip() or f"marcação {i + 1}",
            "time": float(instante),
            "before": antes["mean"], "before_std": antes["std"], "before_n": antes["n"],
            "after": depois["mean"], "after_std": depois["std"], "after_n": depois["n"],
            "step": degrau, "step_spread": espalhamento,
        })
    return degraus


def analyse_curve(time: np.ndarray, values: np.ndarray, markers: Sequence[dict],
                  settle_window: Optional[float] = None,
                  reference: str = "previous",
                  step_window: float = 10.0,
                  include_before: bool = True) -> dict:
    """Intervalos e degraus de uma curva, prontos para a tabela."""
    time = np.asarray(time, dtype=float)
    values = np.asarray(values, dtype=float)
    finitos = np.isfinite(time)
    if not finitos.any():
        raise ValueError("A curva não tem amostras com tempo válido.")
    t_min, t_max = float(np.min(time[finitos])), float(np.max(time[finitos]))

    intervalos = [interval_statistics(time, values, intervalo, settle_window)
                  for intervalo in intervals_from_markers(markers, t_min, t_max, include_before)]
    return {
        "intervals": add_differences(intervalos, reference),
        "steps": marker_steps(time, values, markers, step_window) if markers else [],
    }
