"""Estimación matemática del filtro FIR de rechazo fijado en radar (1).grc.

No confundir con una medición de atenuación: ZMQ 5557 lee la salida del LPF
anterior al filtro band_reject_filter_0 de GNU Radio.
"""
from __future__ import annotations
import numpy as np


def band_reject_response(sample_rate=48000.0, low_hz=495.0, high_hz=505.0,
                         transition_hz=5.0, points=131073):
    """Respuesta FIR Hamming de rechazo de banda, aproximada al diseño firdes.

    Ventana Hamming y número de taps aproximado como 4 Fs / ancho de transición.
    Retorna frecuencias positivas y ganancia en dB (normalizada a DC).
    """
    fs = float(sample_rate)
    lo, hi, transition = float(low_hz), float(high_hz), float(transition_hz)
    if not (0 < lo < hi < fs / 2 and transition > 0):
        raise ValueError('Parámetros de rechazo inválidos')
    taps_count = int(np.ceil(4 * fs / transition)) | 1
    # Evitar diseños absurdamente enormes: en ese caso el modelo debe ser revisado.
    if taps_count > 300_001:
        raise ValueError('Transición demasiado estrecha para este modelo')
    k = np.arange(taps_count, dtype=np.float64) - taps_count // 2
    taps = (2*lo/fs)*np.sinc(2*lo/fs*k) - (2*hi/fs)*np.sinc(2*hi/fs*k)
    taps[taps_count//2] += 1.0
    taps *= np.hamming(taps_count)
    taps /= np.sum(taps)
    n_fft = 1 << max((int(points) - 1).bit_length(), (taps_count - 1).bit_length())
    fft = np.fft.rfft(taps, n=n_fft)
    hz = np.fft.rfftfreq(n_fft, 1/fs)
    db = 20 * np.log10(np.maximum(np.abs(fft), 1e-10))
    return hz, np.clip(db, -110, 5)
