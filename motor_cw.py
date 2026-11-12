#!/usr/bin/env python3
"""Motor CW V7, sin servidor: procesamiento de señales, ZeroMQ, seguimiento."""
import argparse
from collections import deque
import json
from pathlib import Path
import signal
import threading
import time

import numpy as np
from radar_core import DEFAULT_FC, DEFAULT_FS, FFT_SIZE, estimate_doppler, estimate_reference_tone
from tracking import RadialTracker



class Engine:
    def __init__(self, opts):
        self.opts = opts
        self.lock = threading.RLock()
        self.running = True
        self.tone = None
        self.reference_time = 0.
        self.reference_packets = 0
        self.reference_invalid = 0
        self.reference_buffer = np.zeros(8192, dtype=np.complex64)
        self.reference_filled = 0
        self.last_reference_analysis = 0.0
        self.threshold = float(opts.umbral)
        self.min_doppler_hz = float(getattr(opts, "min_doppler_hz", 6.0))
        self.smoothing_count = int(getattr(opts, "smoothing_count", 3))
        self.display_hz = 180.0
        self.invert = False
        self.calibrated = False
        self.buffer = np.zeros(FFT_SIZE, dtype=np.complex64)
        self.filled = 0
        self.last_message = 0.
        self.packet_count = 0
        self.invalid_packets = 0
        self.rx_samples_total = 0
        self.rate_iq_sps = 0.
        self.iq_rms = 0.
        self.rx_window_time = time.monotonic()
        self.rx_window_samples = 0
        self.detections = deque(maxlen=3)
        self.smooth_hz = deque(maxlen=10)
        self.sequence = 0
        self.spectrogram_sequence = 0
        self.spectrum = []
        self.freqs = []
        self.history = deque(maxlen=120)
        self.tracker = RadialTracker()
        self.message = 'Esperando RX y referencia TX de GNU Radio'
        self.meas = {'detected': False, 'doppler_hz': 0., 'speed_m_s': 0.,
                     'prominence_db': 0., 'direction': 'SIN MOVIMIENTO', 'timestamp': 0.}
        self.link = 'waiting'
        self.start = time.monotonic()
        self.worker = threading.Thread(target=self._run, name='DopplerEngine', daemon=True)

    def start_worker(self):
        self.worker.start()

    def config(self, data):
        with self.lock:
            if 'tone_hz' in data:
                raise ValueError('El tono se obtiene del flujo TX de GNU Radio')
            if 'tracking_zero' in data:
                if data['tracking_zero'] is not True:
                    raise ValueError('tracking_zero requiere true')
                if not self.calibrated:
                    raise ValueError('Calibra la dirección Doppler antes de iniciar seguimiento real')
                raw = data.get('initial_distance_m')
                r0 = None if raw in ('',None) else float(raw)
                self.tracker.zero(time.monotonic(), r0)
            if 'tracking_clear' in data and data['tracking_clear'] is True:
                self.tracker.invalidate('Reinicio manual')
            if 'display_hz' in data:
                span = float(data['display_hz'])
                if not np.isfinite(span) or not 10 <= span < self.opts.fs / 2.0:
                    raise ValueError('Escala fuera de Nyquist (Fs/2)')
                self.display_hz = span
            if 'min_doppler_hz' in data:
                self.min_doppler_hz = float(np.clip(float(data['min_doppler_hz']), 1., 100.))
                self.detections.clear()
                self.smooth_hz.clear()
            if 'smoothing_count' in data:
                self.smoothing_count = int(np.clip(int(data['smoothing_count']), 1, 10))
                self.smooth_hz.clear()
            if 'threshold_db' in data:
                self.threshold = float(np.clip(float(data['threshold_db']), 3, 65))
            if 'invert' in data:
                new_invert = bool(data['invert'])
                if new_invert != self.invert:
                    self.tracker.invalidate('Cambio de convención Doppler')
                    self.calibrated = False
                self.invert = new_invert
            if 'calibrated' in data:
                new_calibrated = bool(data['calibrated'])
                if new_calibrated != self.calibrated:
                    self.tracker.invalidate('Cambio de calibración')
                self.calibrated = new_calibrated
        return self.state()

    def state(self):
        with self.lock:
            age = time.monotonic()-self.last_message
            link = self.link
            status_msg = self.message
            detected = self.meas['detected']
            ref_age = time.monotonic()-self.reference_time if self.reference_time else None
            if age > 1.2:
                detected, link = False, 'waiting'
                status_msg = 'Sin paquetes RX recientes; verifica GNU Radio y ZMQ'
            elif (ref_age is None or ref_age > 1.5 or self.tone is None):
                detected, link = False, 'waiting'
                status_msg = 'Sin referencia TX reciente; verifica salida ZMQ 5558'
            m = dict(self.meas)
            if not detected:
                m.update(detected=False, speed_m_s=0., doppler_hz=0.,
                         prominence_db=0. if link != 'online' else m['prominence_db'],
                         direction='SIN MOVIMIENTO')
            return {
                'mode': 'real', 'link': link,
                'message': status_msg, 'sequence': self.sequence,
                'elapsed': round(time.monotonic()-self.start, 1),
                'carrier_hz': self.opts.fc, 'sample_rate': self.opts.fs,
                'tone_hz': self.tone, 'tone_origin': 'flujo_TX_GNU_Radio',
                'reference_online': (ref_age is not None and ref_age <= 1.5 and self.tone is not None),
                'reference_packets': self.reference_packets, 'reference_invalid': self.reference_invalid,
                'metadata_origin': getattr(self.opts,'metadata_origin','configuracion de GNU Radio'),
                'threshold_db': self.threshold, 'min_doppler_hz': self.min_doppler_hz,
                'smoothing_count': self.smoothing_count, 'display_hz': self.display_hz,
                'invert': self.invert, 'calibrated': self.calibrated,
                'measurement': m, 'spectrum_hz': self.freqs if link == 'online' else [],
                'spectrum_db': self.spectrum if link == 'online' else [],
                'history': list(self.history),
                'tracking': self.tracker.snapshot(self.calibrated, connected=(link == 'online')),
                'rx_diagnostics': {
                    'packets': self.packet_count,
                    'invalid_packets': self.invalid_packets,
                    'samples_total': self.rx_samples_total,
                    'estimated_rate_sps': round(self.rate_iq_sps, 1),
                    'iq_rms': round(self.iq_rms, 6),
                    'last_packet_age_s': round(age, 2) if self.last_message else None,
                    'zmq_endpoint': self.opts.zmq,
                    'zmq_reference': self.opts.zmq_ref,
                },
            }

    def _append(self, samples):
        n = len(samples)
        if not n:
            return
        # Buffer circular para muestras I/Q de RX.
        with self.lock:
            if n >= FFT_SIZE:
                self.buffer[:] = samples[-FFT_SIZE:]
                self.filled = FFT_SIZE
            else:
                self.buffer[:-n] = self.buffer[n:]
                self.buffer[-n:] = samples
                self.filled = min(FFT_SIZE, self.filled + n)

    def _analyze(self):
        if self.filled < FFT_SIZE:
            return
        if self.tone is None or time.monotonic()-self.reference_time>1.5:
            return
        with self.lock:
            tone, threshold, inv, calibrated = self.tone, self.threshold, self.invert, self.calibrated
            min_hz, smooth_n = self.min_doppler_hz, self.smoothing_count
            display_span = self.display_hz
            chunk = self.buffer.copy()
        result = estimate_doppler(chunk, self.opts.fs, self.opts.fc, tone, threshold,
                                  display_hz=display_span, min_doppler_hz=min_hz)
        self.detections.append(result.detected)
        active = sum(self.detections) >= 2 and result.detected
        if active and result.detected:
            self.smooth_hz.append(result.doppler_hz)
        else:
            self.smooth_hz.clear()
        fd_raw = float(np.median(list(self.smooth_hz)[-smooth_n:])) if self.smooth_hz else 0.
        fd = -fd_raw if inv else fd_raw
        speed = abs(fd) * 299_792_458/(2 * self.opts.fc)
        if not active:
            direction = 'SIN MOVIMIENTO'
        elif not calibrated:
            direction = 'DIRECCIÓN SIN CALIBRAR'
        else:
            direction = 'ACERCÁNDOSE' if fd > 0 else 'ALEJÁNDOSE'
        m = dict(detected=active, doppler_hz=round(fd, 2), speed_m_s=round(speed, 3),
                 prominence_db=round(result.prominence_db, 1), direction=direction,
                 timestamp=round(time.monotonic()-self.start, 2))
        # Transmitir unos 245 valores, suficientes para dibujo y espectrograma.
        with self.lock:
            self.tracker.update(time.monotonic(), fd, self.opts.fc, active, calibrated)
            self.sequence += 1
            self.meas = m
            self.freqs = [round(float(z), 2) for z in result.frequency_axis]
            self.spectrum = [round(float(z), 2) for z in result.spectrum_db]
            self.history.append({'t': m['timestamp'], 'speed': m['speed_m_s'],
                                 'fd': m['doppler_hz'], 'present': m['detected'],
                                 'delta': round(self.tracker.displacement_m, 4) if self.tracker.zeroed else None})

    def _run(self):
        self._real_loop()

    def _real_loop(self):
        """Dos streams: RX eco desde Pluto, TX referencia desde generador GNU Radio."""
        try:
            import zmq
        except ImportError:
            with self.lock:
                self.message = 'Falta pyzmq: python -m pip install pyzmq'
                self.link = 'error'
            return
        ctx=zmq.Context()
        rx=ctx.socket(zmq.SUB)
        ref=ctx.socket(zmq.SUB)
        for sock,addr in ((rx,self.opts.zmq),(ref,self.opts.zmq_ref)):
            sock.setsockopt(zmq.SUBSCRIBE,b'')
            sock.setsockopt(zmq.RCVHWM,5)
            sock.setsockopt(zmq.LINGER,0)
            sock.connect(addr)
        poller=zmq.Poller()
        poller.register(rx,zmq.POLLIN)
        poller.register(ref,zmq.POLLIN)
        last_analysis=time.monotonic()
        try:
            while self.running:
                events=dict(poller.poll(65))
                # Primero la referencia para que el siguiente análisis use el tono actual.
                if ref in events:
                    message=ref.recv()
                    if not message or len(message)%8:
                        with self.lock:self.reference_invalid+=1
                    else:
                        tx=np.frombuffer(message,dtype='<c8')
                        if not np.all(np.isfinite(tx)):
                            with self.lock:self.reference_invalid+=1
                        else:
                            n=len(tx)
                            if n>=len(self.reference_buffer):
                                self.reference_buffer[:]=tx[-len(self.reference_buffer):]
                                self.reference_filled=len(self.reference_buffer)
                            else:
                                self.reference_buffer[:-n]=self.reference_buffer[n:]
                                self.reference_buffer[-n:]=tx
                                self.reference_filled=min(len(self.reference_buffer),self.reference_filled+n)
                            now=time.monotonic()
                            # Un tono de 50 Hz necesita varios periodos para su FFT.
                            # Acumulamos paquetes pequeños y evitamos una FFT por paquete.
                            if self.reference_filled>=4096 and now-self.last_reference_analysis>.20:
                                self.last_reference_analysis=now
                                freq=estimate_reference_tone(self.reference_buffer[-self.reference_filled:],self.opts.fs)
                                if freq is None:
                                    with self.lock:self.reference_invalid+=1
                                else:
                                    with self.lock:
                                        # Cambio del control tono_frec en GNU Radio:
                                        # borrar historial de la referencia previa.
                                        if self.tone is not None and abs(self.tone-freq)>1.0:
                                            self.buffer.fill(0)
                                            self.filled=0
                                            self.detections.clear()
                                            self.smooth_hz.clear()
                                            self.history.clear()
                                            self.meas.update(detected=False,doppler_hz=0.,speed_m_s=0.,direction='SIN MOVIMIENTO')
                                            self.tracker.invalidate('Cambio automático del tono TX')
                                        self.tone=freq
                                        self.reference_packets+=1
                                        self.reference_time=now
                if rx in events:
                    message=rx.recv()
                    if len(message)%8 or not message:
                        with self.lock:
                            self.invalid_packets+=1
                            self.link='error'
                            self.message='Paquete RX incompatible; usa Complex y Pass Tags: No'
                        continue
                    iq=np.frombuffer(message,dtype='<c8')
                    if not np.all(np.isfinite(iq)):
                        with self.lock:self.invalid_packets+=1
                        continue
                    self._append(iq)
                    now_rx=time.monotonic()
                    rms=float(np.sqrt(np.mean(iq.real.astype(np.float64)**2+iq.imag.astype(np.float64)**2)))
                    with self.lock:
                        self.last_message=now_rx
                        self.packet_count+=1
                        self.rx_samples_total+=len(iq)
                        self.rx_window_samples+=len(iq)
                        dt=now_rx-self.rx_window_time
                        if dt>=1.5:
                            self.rate_iq_sps=self.rx_window_samples/dt
                            self.rx_window_samples=0
                            self.rx_window_time=now_rx
                        self.iq_rms=rms
                now=time.monotonic()
                with self.lock:
                    ready=(self.tone is not None and self.reference_time and
                           now-self.reference_time<=1.5 and now-self.last_message<=1.2)
                    self.link='online' if ready else 'waiting'
                    self.message=('Recibiendo RX y referencia TX automáticamente' if ready else
                                  'Esperando referencia TX ZMQ 5558' if now-self.last_message<=1.2 else
                                  'Esperando muestras RX ZMQ 5557')
                if ready and now-last_analysis>=.1:
                    self._analyze()
                    last_analysis=now
        finally:
            rx.close(0)
            ref.close(0)
            ctx.term()

