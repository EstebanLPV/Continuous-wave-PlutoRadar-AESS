"""Procesamiento Doppler CW. No mide distancia ni ángulo."""
from dataclasses import dataclass
import numpy as np

C = 299_792_458.0
DEFAULT_FS = 48_000.0
DEFAULT_FC = 2_400_000_000.0
FFT_SIZE = 32768


@dataclass
class Result:
    detected: bool
    doppler_hz: float
    speed_m_s: float
    prominence_db: float
    frequency_axis: np.ndarray
    spectrum_db: np.ndarray


def estimate_doppler(iq, sample_rate=DEFAULT_FS, carrier_hz=DEFAULT_FC,
                     tone_hz=280.0, threshold_db=16., min_doppler_hz=6.,
                     max_doppler_hz=180., display_hz=500., max_display_points=2400):
    """Busca un pico espectral relativo al tono; el signo requiere calibración IQ.

    La magnitud de la rapidez es |fd|*c/(2*fc). La frecuencia no es rango.
    El umbral compara el pico con la mediana del ruido en la banda estudiada.
    """
    x = np.asarray(iq, dtype=np.complex64)
    n = len(x)
    if n < 8192:
        return Result(False, 0., 0., 0., np.empty(0), np.empty(0))
    # La multiplicación evita confundir el tono (p.ej. 280 Hz) con el Doppler.
    idx = np.arange(n, dtype=np.float64)
    bb = x * np.exp(-2j * np.pi * tone_hz * idx / sample_rate)
    bb = bb - np.mean(bb)
    spectrum = np.fft.fftshift(np.fft.fft(bb * np.hanning(n)))
    hz = np.fft.fftshift(np.fft.fftfreq(n, 1 / sample_rate))
    magnitudes = 20 * np.log10(np.abs(spectrum) + 1e-12)
    search = (np.abs(hz) >= min_doppler_hz) & (np.abs(hz) <= max_doppler_hz)
    display_hz = min(float(display_hz), sample_rate / 2.0)
    visible = (hz >= -display_hz) & (hz <= display_hz)
    if not np.any(search):
        return Result(False, 0., 0., 0., hz[visible], np.zeros(np.sum(visible)))
    noise_floor = float(np.median(magnitudes[search]))
    candidates = np.flatnonzero(search)
    peak_index = int(candidates[np.argmax(magnitudes[candidates])])
    prominence = float(magnitudes[peak_index] - noise_floor)
    peak_hz = float(hz[peak_index])
    if 0 < peak_index < n - 1:
        a, b, c = magnitudes[peak_index - 1:peak_index + 2]
        denom = a - 2*b + c
        if np.isfinite(denom) and abs(denom) > 1e-10:
            shift = float(np.clip(.5 * (a-c) / denom, -.5, .5))
            peak_hz += shift * sample_rate/n
    detected = prominence >= threshold_db
    speed = abs(peak_hz) * C / (2 * carrier_hz)
    display = np.clip(magnitudes[visible] - noise_floor, -15, 80)
    display_axis = hz[visible]
    # Amplia el campo visible sin mandar las 32768 muestras a Tk cada 100 ms.
    # Agrupación por máximos: conserva picos estrechos al disminuir resolución.
    if display.size > max_display_points:
        stride = int(np.ceil(display.size / max_display_points))
        padding = (-display.size) % stride
        padded = np.pad(display, (0, padding), constant_values=-15)
        display = np.max(padded.reshape(-1, stride), axis=1)
        # La etiqueta del bin se coloca en el centro de cada grupo FFT.
        display_axis = display_axis[::stride] + (stride-1)*sample_rate/(2*n)
    return Result(detected, peak_hz if detected else 0.,
                  speed if detected else 0., prominence,
                  display_axis.astype(np.float32), display.astype(np.float32))



def estimate_reference_tone(tx_iq, sample_rate=DEFAULT_FS, min_hz=45.0, max_hz=2000.0):
    """Estima la frecuencia de referencia TX, sin introducirla a mano.

    Soporta tanto una exponencial I/Q compleja como una señal coseno real
    transportada en complex64 por GNU Radio.
    """
    x = np.asarray(tx_iq, dtype=np.complex64)
    if x.size < 256 or not np.all(np.isfinite(x)):
        return None
    if np.sqrt(np.mean(np.abs(x) ** 2)) < 1e-6:
        return None
    products = x[1:] * np.conj(x[:-1])
    valid = np.abs(products) > 1e-9
    if np.count_nonzero(valid) >= 128:
        phase = np.angle(products[valid]).astype(np.float64)
        hz = float(np.median(phase) * sample_rate/(2*np.pi))
        if np.isfinite(hz) and min_hz-1.5 <= hz <= max_hz+1.5:
            return float(np.clip(hz, min_hz, max_hz))
    # FFT positiva de una referencia posiblemente real (Cosine).
    # Una ventana demasiado corta puede no separar 50 Hz; exigir
    # varias muestras por ciclo y no publicar valores poco fiables.
    n = len(x)
    if n < sample_rate/min_hz*2:
        return None
    sig = x - np.mean(x)
    window = np.hanning(n)
    sp = np.abs(np.fft.fft(sig * window))
    freq = np.fft.fftfreq(n, 1/sample_rate)
    mask = (freq >= min_hz) & (freq <= max_hz)
    if not np.any(mask):
        return None
    ids = np.flatnonzero(mask)
    k = int(ids[np.argmax(sp[ids])])
    if sp[k] < np.median(sp[mask])*6:
        return None
    peak = float(freq[k])
    if 1 <= k < len(sp)-1:
        la, lb, lc = np.log(np.maximum(sp[k-1:k+2], 1e-20))
        denom = la - 2*lb + lc
        if abs(denom)>1e-12:
            peak += float(np.clip(0.5*(la-lc)/denom,-0.5,0.5)) * sample_rate/n
    return float(peak) if min_hz-1.5 <= peak <= max_hz+1.5 else None
