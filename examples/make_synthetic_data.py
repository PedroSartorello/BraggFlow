"""
Generates the SYNTHETIC example data in ``examples/data/`` (no real
measurement is ever versioned in this repository).

    python examples/make_synthetic_data.py

Files written (fixed random seed, so the output is reproducible):

``synthetic_interrogator.asc``
    Interrogator export, 15 min at 10 Hz, tab-separated with decimal comma
    like the real exports. Three channels: two EFBGs that respond to the gas
    (near 1550 and 1545 nm) and one FBG temperature reference (near 1540 nm).
    All three share a slow thermal drift; the signal also carries noise,
    lost peaks (readings of ``0``) and isolated outliers, and the EFBGs step
    up while CO2 flows (first-order response).

``synthetic_gas_events.csv``
    Gas event table (``GAS, SM_INDEX, SEGUNDOS, OBSERVACOES, VAZAO_L_MIN,
    TEMP_FLUKE_C``), read by ``load_gas_table``.

``synthetic_spectrum.txt``
    Short reflection spectrum (dBm) of the three gratings, 1535-1555 nm.

See ``docs/data-formats.md`` for the description of each format.
"""

from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent / "data"
SEED = 2026

FS = 10.0                      # Hz
DURATION = 900.0               # s
NOMINAL = {"CH_1 Sensor_1 [nm]": 1550.0,   # EFBG1
           "CH_2 Sensor_1 [nm]": 1545.0,   # EFBG2
           "CH_3 Sensor_1 [nm]": 1540.0}   # FBG (temperature reference)
GAS_RESPONSE_NM = {"CH_1 Sensor_1 [nm]": 0.040, "CH_2 Sensor_1 [nm]": 0.025,
                   "CH_3 Sensor_1 [nm]": 0.0}
TAU_S = 15.0                   # time constant of the gas response
THERMAL_NM_PER_C = 0.010       # ~10 pm/°C, typical of an FBG at 1550 nm
NOISE_NM = 0.0015

# (gas, start time in s, flow in L/min)
EVENTS = [("AR", 0.0, 0.0), ("N2", 120.0, 0.5), ("CO2", 300.0, 0.5),
          ("N2", 480.0, 0.5), ("CO2", 660.0, 0.5), ("N2", 780.0, 0.5)]


def temperature(t: np.ndarray) -> np.ndarray:
    """Room temperature seen by all gratings (°C): slow drift around 25 °C."""
    return 25.0 + 1.2 * np.sin(2 * np.pi * t / 1500.0) + 0.0008 * t


def gas_fraction(t: np.ndarray) -> np.ndarray:
    """0 without CO2, rising to 1 while CO2 flows (first-order response)."""
    level = np.zeros_like(t)
    for (gas, start, _), nxt in zip(EVENTS, EVENTS[1:] + [(None, np.inf, None)]):
        target = 1.0 if gas == "CO2" else 0.0
        inside = (t >= start) & (t < nxt[1])
        if not inside.any():
            continue
        before = level[np.argmax(inside) - 1] if np.argmax(inside) > 0 else 0.0
        level[inside] = target + (before - target) * np.exp(-(t[inside] - start) / TAU_S)
    return level


def interrogator(rng: np.random.Generator) -> str:
    t = np.arange(0.0, DURATION + 1e-9, 1.0 / FS)
    drift = THERMAL_NM_PER_C * (temperature(t) - temperature(t[:1]))
    gas = gas_fraction(t)

    columns = {}
    for name, nominal in NOMINAL.items():
        y = nominal + drift + GAS_RESPONSE_NM[name] * gas + rng.normal(0.0, NOISE_NM, t.size)
        lost = rng.choice(t.size, size=20, replace=False)          # interrogator lost the peak
        y[lost] = 0.0
        spikes = rng.choice(t.size, size=12, replace=False)        # isolated outliers
        y[spikes] += rng.choice([-1.0, 1.0], size=12) * rng.uniform(0.2, 0.4, 12)
        columns[name] = y

    lines = ["\t".join(["Time [s]", *NOMINAL])]
    for i, ti in enumerate(t):
        row = [f"{ti:.3f}"] + [f"{columns[name][i]:.6f}" for name in NOMINAL]
        lines.append("\t".join(row).replace(".", ","))
    return "\n".join(lines) + "\n"


def gas_table() -> str:
    lines = ["GAS,SM_INDEX,SEGUNDOS,OBSERVACOES,VAZAO_L_MIN,TEMP_FLUKE_C"]
    for gas, start, flow in EVENTS:
        index = int(round(start * FS))
        note = "inicio" if start == 0 else f"troca para {gas}"
        lines.append(f"{gas},{index},{start:.1f},{note},{flow:.1f},"
                     f"{temperature(np.array([start]))[0]:.2f}")
    return "\n".join(lines) + "\n"


def spectrum() -> str:
    wl = np.round(np.arange(1535.0, 1555.0 + 1e-9, 0.01), 2)
    linear = np.full(wl.size, 1e-6)                         # -60 dBm floor (mW)
    for nominal in NOMINAL.values():
        linear += 1e-2 * np.exp(-0.5 * ((wl - nominal) / (0.2 / 2.3548)) ** 2)  # FWHM 0.2 nm
    dbm = 10 * np.log10(linear)
    lines = ["Wavelength [nm];Reflection [dBm]"]
    lines += [f"{w:.2f};{p:.3f}".replace(".", ",") for w, p in zip(wl, dbm)]
    return "\n".join(lines) + "\n"


def main() -> None:
    rng = np.random.default_rng(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "synthetic_interrogator.asc": interrogator(rng),
        "synthetic_gas_events.csv": gas_table(),
        "synthetic_spectrum.txt": spectrum(),
    }
    for name, text in files.items():
        path = OUT / name
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"{path.relative_to(OUT.parent.parent)}  ({path.stat().st_size / 1024:.0f} kB)")


if __name__ == "__main__":
    main()
