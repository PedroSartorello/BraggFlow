import numpy as np


def temperature_compensation(
    signals: np.ndarray,
    temp_channel_idx: int,
    k_coeff: float = 1.0,
) -> np.ndarray:
    """
    Applies cross-sensitivity temperature compensation to FBG sensor signals.

    The compensation follows the standard dual-FBG cross-sensitivity model:

        Δλ_comp[i] = Δλ_sensor[i]  -  k · Δλ_ref

    where:
        - Δλ_sensor[i]  is the wavelength shift of the i-th sensing channel
                        (already converted to Δλ by ``to_delta_lambda``).
        - Δλ_ref        is the wavelength shift of the temperature-reference
                        FBG channel (``temp_channel_idx``), which responds
                        only to temperature (no mechanical / gas stimulus).
        - k             is the cross-sensitivity coefficient, defined as the
                        ratio of thermal sensitivities:

                            k = S_T_sensor / S_T_ref   [dimensionless]

                        With k = 1 (default) both FBGs are assumed to have
                        equal thermal sensitivity — a reasonable first
                        approximation when both gratings are inscribed in the
                        same fibre type and packaged identically.

    The temperature-reference channel is **kept unchanged** in the output so
    that its original Δλ curve remains available for inspection and plotting.

    Parameters
    ----------
    signals : np.ndarray, shape (n_samples, n_channels)
        Signal array **after** ``to_delta_lambda`` has been applied.
        Units: nm (Δλ).
    temp_channel_idx : int
        Column index of the temperature-reference channel.
        In the pipeline this is resolved automatically from a channel name
        (e.g. ``temp_channel_idx='FBG'``) by ``OpticalPipeline.apply_filter``.
    k_coeff : float
        Cross-sensitivity coefficient k = S_T_sensor / S_T_ref.
        Must be > 0. Default is 1.0 (equal thermal sensitivities).
        Typical range for silica FBG pairs: 0.8 – 1.2.

    Returns
    -------
    compensated : np.ndarray, shape (n_samples, n_channels)
        Sensing channels are thermally compensated; the reference channel
        retains its original Δλ values.

    Raises
    ------
    ValueError
        If ``temp_channel_idx`` is out of range, or ``k_coeff`` is not > 0.

    References
    ----------
    Kersey, A. D. et al. (1997). "Fiber grating sensors."
    Journal of Lightwave Technology, 15(8), 1442–1463.
    """
    n_samples, n_channels = signals.shape

    # ── validation ────────────────────────────────────────────────────────────
    if not (0 <= temp_channel_idx < n_channels):
        raise ValueError(
            f"temp_channel_idx={temp_channel_idx} is out of range "
            f"for an array with {n_channels} channels."
        )
    if k_coeff <= 0:
        raise ValueError(
            f"k_coeff must be > 0 (got {k_coeff}). "
            "Typical silica FBG cross-sensitivity ratio: 0.8 – 1.2."
        )

    # ── compensation ──────────────────────────────────────────────────────────
    compensated = np.copy(signals)

    # Δλ of the temperature-reference FBG (responds to T only)
    delta_lambda_ref = signals[:, temp_channel_idx]

    for ch in range(n_channels):
        if ch != temp_channel_idx:
            # Subtract the thermally-induced shift scaled by k
            compensated[:, ch] = signals[:, ch] - k_coeff * delta_lambda_ref
        # Reference channel: left unchanged so its original curve is preserved

    return compensated