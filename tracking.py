"""Seguimiento radial derivado de Doppler; NO mide distancia absoluta.

Reglas: necesita referencia cero y convención I/Q calibrada; pausa ante
pérdida de detección, no integra saltos temporales ni crea rangos ficticios.
"""
from dataclasses import dataclass
from typing import Optional
import math


@dataclass
class RadialTracker:
    displacement_m: float = 0.0  # delta R: negativo = se acerca
    initial_distance_m: Optional[float] = None
    zeroed: bool = False
    last_time: Optional[float] = None
    active_seconds: float = 0.0
    samples: int = 0
    pause_reason: str = 'Sin referencia de posición'
    last_movement: str = 'SIN MOVIMIENTO'

    def zero(self, when, initial_distance_m=None):
        """El usuario coloca el blanco en su referencia conocida y pulsa CERO."""
        if initial_distance_m is not None:
            if not math.isfinite(initial_distance_m) or not 0 < initial_distance_m <= 1000:
                raise ValueError('La distancia inicial debe ser mayor que 0 y menor o igual a 1000 m')
        self.displacement_m = 0.0
        self.initial_distance_m = initial_distance_m
        self.zeroed = True
        self.last_time = float(when)
        self.active_seconds = 0.0
        self.samples = 0
        self.pause_reason = 'Esperando medición válida'
        self.last_movement = 'SIN MOVIMIENTO'

    def invalidate(self, reason='Referencia reiniciada'):
        self.displacement_m = 0.0
        self.initial_distance_m = None
        self.zeroed = False
        self.last_time = None
        self.active_seconds = 0.0
        self.samples = 0
        self.pause_reason = reason

    def update(self, when, fd_hz, carrier_hz, detected, calibrated):
        now = float(when)
        if not self.zeroed:
            self.pause_reason = 'Pulsar CERO para comenzar'
            return
        if not calibrated:
            self.last_time = now
            self.pause_reason = 'Calibrar el signo I/Q'
            return
        if not detected or not math.isfinite(fd_hz) or fd_hz == 0.0:
            self.last_time = now
            self.last_movement = 'SIN MOVIMIENTO'
            self.pause_reason = 'Sin Doppler detectable; acumulación pausada'
            return
        if self.last_time is None:
            self.last_time = now
            self.pause_reason = 'Esperando siguiente medida'
            return
        dt = now - self.last_time
        self.last_time = now
        if dt <= 0 or dt > 0.35:
            self.pause_reason = 'Intervalo de medición discontinuo; pausa'
            return
        # En nuestra convención tras calibrar: fd > 0 implica acercamiento.
        vr_towards = fd_hz * 299_792_458.0 / (2.0 * carrier_hz)
        self.displacement_m -= vr_towards * dt
        self.active_seconds += dt
        self.samples += 1
        self.last_movement = 'ACERCÁNDOSE' if fd_hz > 0 else 'ALEJÁNDOSE'
        self.pause_reason = ''

    def snapshot(self, calibrated, connected=True):
        valid = self.zeroed and calibrated
        distance = self.initial_distance_m + self.displacement_m if self.initial_distance_m is not None and valid else None
        if distance is not None and distance < 0:
            distance = None # No presentar distancias físicas negativas por deriva
        reason = self.pause_reason if connected else 'Sin datos recientes; acumulación pausada'
        return {'zeroed': self.zeroed,
                'calibrated': bool(calibrated),
                'valid': bool(valid),
                'displacement_m': round(self.displacement_m, 4) if valid else None,
                'initial_distance_m': self.initial_distance_m,
                'distance_estimate_m': round(distance, 4) if distance is not None else None,
                'active_seconds': round(self.active_seconds, 2),
                'integrated_samples': self.samples,
                'paused': bool(reason),
                'reason': reason,
                'note': 'Estimación por integración Doppler; error acumulativo. No es distancia medida por CW.'}
