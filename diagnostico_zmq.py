"""Inspecciona streams complejos publicados por GNU Radio. No transmite RF."""
import json
import time
from pathlib import Path
import numpy as np
import zmq
from radar_core import estimate_reference_tone


def run(seconds=10):
    cfg=json.loads((Path(__file__).parent/'configuracion_radar.json').read_text())
    ctx=zmq.Context()
    socks=[]
    stats=[{'n':0,'invalid':0,'samples':0,'recent':None,'chunks':[]} for _ in range(2)]
    poller=zmq.Poller()
    try:
        for endpoint in (cfg['zmq_rx'],cfg['zmq_ref']):
            s=ctx.socket(zmq.SUB)
            s.setsockopt(zmq.SUBSCRIBE,b'')
            s.setsockopt(zmq.LINGER,0)
            s.setsockopt(zmq.RCVHWM,20)
            s.connect(endpoint)
            poller.register(s,zmq.POLLIN)
            socks.append(s)
        print('AESS / PRUEBA ZERO MQ - 10 SEGUNDOS')
        print('RX:',cfg['zmq_rx'])
        print('TX:',cfg['zmq_ref'])
        print('Mantener GNU Radio ejecutandose durante la prueba.\n')
        start=time.monotonic()
        while time.monotonic()-start<seconds:
            events=dict(poller.poll(200))
            for k,s in enumerate(socks):
                if s not in events:continue
                msg=s.recv()
                if not msg or len(msg)%8:
                    stats[k]['invalid']+=1
                    continue
                iq=np.frombuffer(msg,dtype='<c8')
                if not np.all(np.isfinite(iq)):
                    stats[k]['invalid']+=1
                    continue
                stats[k]['n']+=1
                stats[k]['samples']+=len(iq)
                stats[k]['recent']=time.monotonic()
                if k==1:
                    stats[k]['chunks'].append(iq.copy())
                    while sum(a.size for a in stats[k]['chunks'])>16384:
                        stats[k]['chunks'].pop(0)
        for i,name in enumerate(('RX','TX')):
            st=stats[i]
            print(f'{name}: {st["n"]} paquetes, {st["samples"]} muestras, {st["invalid"]} paquetes invalidos')
            if st['n']==0:
                print(f'   ERROR: no hay muestras en {name}. Comprueba ZMQ PUB Sink, Bind y que GNU Radio siga abierto.')
            else:
                print(f'   Datos complex64: OK. Promedio de llegada: {st["samples"]/seconds/1000:.1f} kS/s (esperado ~{cfg["sample_rate"]/1000:.1f} kS/s)')
        if stats[1]['chunks']:
            arr=np.concatenate(stats[1]['chunks'])
            f=estimate_reference_tone(arr[-min(len(arr),8192):],cfg['sample_rate'])
            print('Tono TX estimado:',f'{f:.1f} Hz' if f is not None else 'SIN IDENTIFICAR (revisar referencia y formato)')
        return 0 if all(x['n'] for x in stats) else 1
    finally:
        for s in socks:s.close(0)
        ctx.term()


if __name__=='__main__':
    raise SystemExit(run())
