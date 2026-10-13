"""
Validação de opções vindas da interface.

Um *spec* descreve cada campo como ``(tipo, padrão, limites ou opções, nome)``;
``resolve_section`` aplica o spec a um dicionário parcial (tudo o que vem de um
formulário chega como texto) e devolve valores já convertidos. Tipos
terminados em ``?`` aceitam vazio, que vira ``None`` ("automático").

Usado pelo estilo das figuras (``braggflow.visualization.figure``) e pelo preparo
dos espectros (``braggflow.processing.spectra``).
"""

import math
from typing import Optional

from matplotlib import colors as mcolors

ANY_RANGE = (None, None)


def is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def coerce(kind: str, value, default, extra, label: str):
    """Converte e valida um campo; erros citam o nome exibido do campo."""
    optional = kind.endswith("?")
    base = kind.rstrip("?")

    if base == "bool":
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "on", "yes", "sim"}
        return default if value is None else bool(value)

    if base == "str":
        return "" if value is None else str(value)

    if is_blank(value):
        return None if optional else default

    if base in {"float", "int"}:
        try:
            number = float(str(value).replace(",", ".")) if isinstance(value, str) else float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{label}: número inválido ({value!r}).") from None
        if not math.isfinite(number):
            raise ValueError(f"{label}: número inválido ({value!r}).")
        if base == "int":
            if number != int(number):
                raise ValueError(f"{label}: use um número inteiro ({value!r}).")
            number = int(number)
        low, high = extra or ANY_RANGE
        if (low is not None and number < low) or (high is not None and number > high):
            limits = f"≥ {low:g}" if high is None else f"entre {low:g} e {high:g}"
            raise ValueError(f"{label}: valor deve ser {limits} (recebido {number:g}).")
        return number

    if base == "choice":
        text = str(value).strip()
        if text not in extra:
            raise ValueError(f"{label}: opção inválida ({text!r}).")
        return text

    if base == "color":
        text = str(value).strip()
        if not mcolors.is_color_like(text):
            raise ValueError(f"{label}: cor inválida ({text!r}).")
        return text

    raise AssertionError(f"tipo desconhecido: {kind}")


def resolve_section(spec: dict, user: Optional[dict], prefix: str = "") -> dict:
    """Aplica um spec a um dicionário parcial, completando com os padrões."""
    user = user or {}
    if not isinstance(user, dict):
        raise ValueError(f"Opções inválidas{(' em ' + prefix) if prefix else ''}.")
    return {
        key: coerce(kind, user.get(key), default, extra, f"{prefix}{label}")
        for key, (kind, default, extra, label) in spec.items()
    }
