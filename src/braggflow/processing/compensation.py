from typing import List, Optional, Sequence

import numpy as np


def compensation_ratios(
    n_channels: int,
    temp_channel_idx: int,
    k_coeff: float = 1.0,
    thermal_sensitivities: Optional[Sequence[Optional[float]]] = None,
) -> List[Optional[float]]:
    """
    Ratio k applied to each channel by ``temperature_compensation``.

    With ``thermal_sensitivities`` (K_T of each grating, any consistent unit,
    e.g. pm/°C), a channel with a known K_T gets ``k = K_T,s / K_T,r``; a
    channel without one gets ``k_coeff``. The reference channel gets ``None``
    (it is not compensated).

    Raises
    ------
    ValueError
        If the reference index is out of range, ``k_coeff`` is not > 0, the
        list has the wrong length, a K_T is not > 0, or some sensing channel
        has a K_T but the reference does not (the ratio needs both).
    """
    if not (0 <= temp_channel_idx < n_channels):
        raise ValueError(
            f"temp_channel_idx={temp_channel_idx} is out of range "
            f"for an array with {n_channels} channels."
        )
    if not k_coeff > 0:
        raise ValueError(
            f"k_coeff must be > 0 (got {k_coeff}): it is the ratio of the thermal "
            "sensitivities K_T,s / K_T,r."
        )

    sens = list(thermal_sensitivities) if thermal_sensitivities is not None else [None] * n_channels
    if len(sens) != n_channels:
        raise ValueError(
            f"thermal_sensitivities has {len(sens)} entries for {n_channels} channels."
        )
    sens = [None if v is None or (isinstance(v, float) and np.isnan(v)) else float(v) for v in sens]
    for i, v in enumerate(sens):
        if v is not None and not v > 0:
            raise ValueError(f"Thermal sensitivity of channel {i} must be > 0 (got {v}).")

    k_ref = sens[temp_channel_idx]
    others = [v for i, v in enumerate(sens) if i != temp_channel_idx and v is not None]
    if others and k_ref is None:
        raise ValueError(
            "The sensing gratings have a thermal sensitivity K_T but the reference "
            "does not: k = K_T,s / K_T,r needs both."
        )

    return [
        None if i == temp_channel_idx
        else (v / k_ref if v is not None else float(k_coeff))
        for i, v in enumerate(sens)
    ]


def temperature_compensation(
    signals: np.ndarray,
    temp_channel_idx: int,
    k_coeff: float = 1.0,
    thermal_sensitivities: Optional[Sequence[Optional[float]]] = None,
) -> np.ndarray:
    """
    Removes the thermal shift from the sensing FBGs using a reference FBG.

    Model (reference-grating method): a grating responds to the measurand and
    to temperature, ``Δλ_s = Δλ_measurand + K_T,s·ΔT``, while the reference
    grating, shielded from the measurand, responds to temperature only,
    ``Δλ_r = K_T,r·ΔT``. Eliminating ΔT:

        Δλ_comp[i] = Δλ_s[i]  −  k_i · Δλ_r,      k_i = K_T,s[i] / K_T,r

    The ratio is needed because the thermal sensitivity depends on the
    coating and on what the grating is bonded to; with identical gratings in
    the same packaging, k = 1.

    Both shifts must be **relative to the same baseline**, so apply
    ``to_delta_lambda`` first (the pipeline refuses absolute wavelengths:
    ``λ_s − k·λ_r`` would carry the constant ``λ_s0 − k·λ_r0``).

    Assumptions worth stating with the result: the reference does not respond
    to the measurand, both gratings see the same temperature at the same time
    (similar thermal time constants), and K_T is constant over the range.

    Parameters
    ----------
    signals : np.ndarray, shape (n_samples, n_channels)
        Wavelength shifts Δλ (output of ``to_delta_lambda``).
    temp_channel_idx : int
        Column of the reference grating. In the pipeline it can be given by
        name (``temp_channel_idx='FBG'``).
    k_coeff : float
        k used for channels without a thermal sensitivity. Default 1.0.
    thermal_sensitivities : sequence of float or None, one per channel
        K_T of each grating (e.g. pm/°C, from a temperature calibration).
        When given, ``k_i = K_T,s[i] / K_T,r`` for the channels that have
        one; the others use ``k_coeff``.

    Returns
    -------
    np.ndarray, same shape
        Sensing channels compensated; the reference keeps its Δλ (= K_T,r·ΔT).

    References
    ----------
    Kersey, A. D. et al. (1997). "Fiber grating sensors."
    Journal of Lightwave Technology, 15(8), 1442–1463.
    """
    signals = np.asarray(signals, dtype=float)
    ratios = compensation_ratios(signals.shape[1], temp_channel_idx, k_coeff,
                                 thermal_sensitivities)

    compensated = np.copy(signals)
    reference = signals[:, temp_channel_idx]
    for ch, k in enumerate(ratios):
        if k is not None:
            compensated[:, ch] = signals[:, ch] - k * reference
    return compensated


# O pipeline confere antes de aplicar: só faz sentido sobre deslocamentos
temperature_compensation.input_quantity = "wavelength_shift"
