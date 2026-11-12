"""Estimación en vivo de rechazo usando PSD de dos flujos IQ complejos.

La relación de PSD no exige coherencia de fase, pero sí señales aproximadamente
estacionarias durante la ventana de medida. No es un analizador de redes.
"""
import threading
import time
import numpy as np

class LiveRejection:
    def __init__(self, raw='tcp://127.0.0.1:5557', filtered='tcp://127.0.0.1:5559', fs=48000):
        self.endpoints=(raw,filtered)
        self.fs=float(fs)
        self.running=True
        self.lock=threading.Lock()
        self.freq=np.array([],dtype=float)
        self.db=np.array([],dtype=float)
        self.status='Esperando señal original (5557) y filtrada (5559)'
        self.last_update=0.
        self.thread=threading.Thread(target=self._run,daemon=True,name='LiveReject')
        self.thread.start()

    def snapshot(self):
        with self.lock:
            return self.freq.copy(),self.db.copy(),self.status,self.last_update

    def stop(self):
        self.running=False

    def _run(self):
        try:
            import zmq
        except ImportError:
            with self.lock:self.status='Falta pyzmq'
            return
        ctx=zmq.Context()
        sockets=[]
        poller=zmq.Poller()
        try:
            for endpoint in self.endpoints:
                s=ctx.socket(zmq.SUB)
                s.setsockopt(zmq.SUBSCRIBE,b'')
                s.setsockopt(zmq.RCVHWM,8)
                s.setsockopt(zmq.LINGER,0)
                s.connect(endpoint)
                poller.register(s,zmq.POLLIN)
                sockets.append(s)
            nfft=65536
            # Acumulación por canal, con ventana temporal similar para ambos.
            buffers=[np.empty(0,dtype=np.complex64),np.empty(0,dtype=np.complex64)]
            psds=[None,None]
            last_seen=[0.,0.]
            win=np.hanning(nfft).astype(np.float32)
            freq=np.fft.fftshift(np.fft.fftfreq(nfft,1/self.fs))
            last_compute=0.
            while self.running:
                events=dict(poller.poll(80))
                now=time.monotonic()
                for idx,s in enumerate(sockets):
                    if s not in events:continue
                    # Drenar mensajes viejos para evitar latencia creciente.
                    latest=None
                    while True:
                        try:latest=s.recv(flags=zmq.NOBLOCK)
                        except zmq.Again:break
                    if latest is None or not latest or len(latest)%8:continue
                    arr=np.frombuffer(latest,dtype='<c8')
                    if not np.isfinite(arr).all():continue
                    buffers[idx]=np.concatenate((buffers[idx],arr))[-2*nfft:]
                    last_seen[idx]=now
                if now-last_compute<0.35:continue
                last_compute=now
                for idx in range(2):
                    if len(buffers[idx])<nfft:continue
                    data=buffers[idx][-nfft:]
                    spec=np.fft.fftshift(np.fft.fft(data*win))
                    power=np.abs(spec)**2
                    psds[idx]=power if psds[idx] is None else .75*psds[idx]+.25*power
                if any(now-t>1.5 for t in last_seen):
                    with self.lock:self.status='Esperando ZMQ 5557 y 5559 (datos recientes)'
                    continue
                if psds[0] is None or psds[1] is None:
                    with self.lock:self.status='Acumulando muestras para FFT de 65 536 puntos'
                    continue
                # En frecuencias sin energía suficiente, la división de PSD no es fiable.
                raw,flt=psds
                floor=max(float(np.max(raw))*1e-7,1e-20)
                valid=raw>floor
                ratio=np.full(len(raw),np.nan)
                ratio[valid]=10*np.log10(np.maximum(flt[valid],1e-30)/np.maximum(raw[valid],1e-30))
                # Mostrar frecuencias positivas; resolución 0.732 Hz a 48 kS/s.
                positive=freq>=0
                with self.lock:
                    self.freq=freq[positive].copy()
                    self.db=np.clip(ratio[positive],-110,30)
                    self.last_update=now
                    self.status='En vivo · PSD filtrada/original · aprox. 3 actualizaciones/s'
        except Exception as exc:
            with self.lock:self.status='Error de medición: '+str(exc)
        finally:
            for s in sockets:s.close(0)
            ctx.term()
