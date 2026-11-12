"""Frecuencia: rangos físicos y unidades de presentación, sin alterar el SDR."""
from __future__ import annotations
import math

UNIT_SCALES = {'Hz': 1.0, 'kHz': 1_000.0, 'MHz': 1_000_000.0, 'GHz': 1_000_000_000.0}
SPAN_CANDIDATES_HZ = (90.0, 180.0, 500.0, 1000.0, 2000.0, 5000.0, 10000.0, 20000.0, 50000.0, 100000.0)


def available_spans(sample_rate: float):
    """Una vista I/Q no puede mostrar frecuencias fuera de Nyquist."""
    nyquist = float(sample_rate) / 2
    return tuple(v for v in SPAN_CANDIDATES_HZ if v < nyquist)


def unit_for_hz(largest_abs_hz: float, preference: str = 'Auto'):
    if preference != 'Auto':
        if preference not in UNIT_SCALES:
            raise ValueError('Unidad no reconocida: ' + str(preference))
        return preference
    magnitude = abs(float(largest_abs_hz))
    for threshold, name in ((1e9, 'GHz'), (1e6, 'MHz'), (1e3, 'kHz')):
        if magnitude >= threshold:
            return name
    return 'Hz'


def to_unit(hz_values, unit: str):
    return hz_values / UNIT_SCALES[unit]


def span_label(hz: float):
    u = unit_for_hz(hz)
    v = hz / UNIT_SCALES[u]
    return f'±{v:g} {u}'


def tick_label(value: float, increment: float) -> str:
    step = abs(float(increment))
    if not math.isfinite(step) or step == 0:
        decimals = 3
    else:
        decimals = max(0, min(12, math.ceil(-math.log10(step)) + 1))
    result = f'{value:.{decimals}f}'.rstrip('0').rstrip('.') if decimals else f'{value:.0f}'
    return '0' if result in ('-0', '') else result
