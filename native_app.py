#!/usr/bin/env python3
"""PlutoRadar AESS: interfaz Nativa Tk, sin navegador ni servidor web.
V10 reusa el motor Doppler y la integración ZMQ de V7.
"""
from __future__ import annotations
import argparse
import csv
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import zipfile
import ctypes

import numpy as np
from PIL import Image, ImageTk
from radar_core import DEFAULT_FS, DEFAULT_FC
from motor_cw import Engine
from display_utils import available_spans, span_label, unit_for_hz, UNIT_SCALES, tick_label
from live_rejection import LiveRejection

FROZEN = getattr(sys, "frozen", False)
ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
SETTINGS_DIR = Path(os.environ['LOCALAPPDATA']) / 'PlutoRadar-AESS' if FROZEN and os.environ.get('LOCALAPPDATA') else ROOT
SETTINGS_FILE = SETTINGS_DIR / 'ajustes_usuario.json'
ASSETS = Path(getattr(sys, "_MEIPASS", ROOT))
NAVY = '#112E4A'
DEEP = '#0B2137'
BLUE = '#1467A8'
CYAN = '#08A8DB'
TEXT = '#183751'
MUTED = '#5D7387'
BORDER = '#D5E0EA'
BG = '#EFF3F7'
WHITE = '#FFFFFF'
GREEN = '#187B60'
AMBER = '#B27726'


def find_nunito_zip():
    """No instala la tipografía y no la incluye en el proyecto.
    Busca el ZIP original proporcionado por el usuario en ubicaciones habituales.
    """
    candidates = [ROOT / 'Nunito-Full-Version.zip',
                  Path.home() / 'Downloads' / 'Nunito-Full-Version.zip',
                  Path.home() / 'Desktop' / 'Nunito-Full-Version.zip',
                  Path.home() / 'Descargas' / 'Nunito-Full-Version.zip',
                  Path.home() / 'Documents' / 'Nunito-Full-Version.zip']
    return next((f for f in candidates if f.exists()), None)


TEMP_FONT_PATHS = []

def load_nunito(root):
    """Windows: registra Nunito PRIVADAMENTE solo en esta app desde el ZIP del usuario.
    No requiere instalar la fuente ni modifica el registro de Windows.
    """
    if sys.platform != 'win32':
        return 'Nunito' if 'Nunito' in root.tk.call('font','families') else 'DejaVu Sans'
    z = find_nunito_zip()
    if z is None:
        return 'Segoe UI'
    try:
        with zipfile.ZipFile(z) as archive:
            names = archive.namelist()
            for wanted in ('Nunito-Regular.ttf','Nunito-Bold.ttf','Nunito-SemiBold.ttf'):
                matches = [n for n in names if '/Desktop Fonts/Nunito/static/' in n.replace('\\','/') and n.endswith('/'+wanted)]
                if not matches:
                    continue
                data = archive.read(matches[0])
                folder = Path(tempfile.mkdtemp(prefix='aess_nunito_'))
                fpath = folder / wanted
                fpath.write_bytes(data)
                loaded = ctypes.windll.gdi32.AddFontResourceExW(str(fpath),0x10,None)
                if loaded:
                    TEMP_FONT_PATHS.append(fpath)
        root.update_idletasks()
        # Algunas compilaciones de Tk no actualizan inmediatamente la lista font families.
        return 'Nunito' if TEMP_FONT_PATHS else 'Segoe UI'
    except Exception as exc:
        print('No se pudo activar Nunito desde ZIP:', exc)
        return 'Segoe UI'


def label(parent, value, size=11, color=TEXT, weight='normal', **kw):
    return tk.Label(parent,text=value,fg=color,bg=parent.cget('bg'),font=(APP_FONT,size,weight),**kw)


def button(parent, title, cb, blue=False, width=None):
    return tk.Button(parent,text=title,command=cb,cursor='hand2',
                     bg=BLUE if blue else WHITE,fg=WHITE if blue else BLUE,
                     activebackground='#0E528B' if blue else '#E8F1F8',
                     activeforeground=WHITE if blue else BLUE,
                     relief='flat',highlightthickness=1,highlightbackground=BLUE if blue else BORDER,
                     bd=0,padx=13,pady=9,width=width,font=(APP_FONT,10,'bold'))


def panel(parent, title, col=0, row=0, weight=1, pady=(0,10)):
    wrapper=tk.Frame(parent,bg=WHITE,highlightbackground=BORDER,highlightthickness=1)
    wrapper.grid(row=row,column=col,sticky='nsew',padx=(0,10) if col==0 else (0,0),pady=pady)
    bar=tk.Frame(wrapper,bg=WHITE,height=44)
    bar.pack(side='top',fill='x')
    bar.pack_propagate(False)
    label(bar,title,12,weight='bold').pack(side='left',padx=17)
    tk.Frame(wrapper,bg=BORDER,height=1).pack(fill='x')
    return wrapper,bar


class AESSDesktop(tk.Tk):
    def __init__(self,opts):
        super().__init__()
        global APP_FONT
        APP_FONT=load_nunito(self)
        self.title('AESS | PlutoRadar Doppler CW')
        self.configure(bg=BG)
        self.geometry('1460x900')
        self.minsize(1130,700)
        self.engine=Engine(opts)
        self.engine.config({k:v for k,v in getattr(opts,"saved_settings",{}).items() if k in ("invert","calibrated")})
        self.engine.start_worker()
        self.last_seq=-1
        self.rows=[]
        self.max_rows=125
        self.freq_display=180.0
        self.unit_choice=tk.StringVar(value='Auto')
        self.spans=available_spans(opts.fs)
        self.span_choice=tk.StringVar(value=span_label(self.freq_display))
        self.notch_range=tk.StringVar(value='400–600 Hz')
        self.main_graph=tk.StringVar(value="Doppler")
        self.graph_spans={"Doppler":180.0,"Rechazo de banda":1000.0}
        self.min_hz_var=tk.DoubleVar(value=float(getattr(opts,"min_doppler_hz",6)))
        self.smooth_var=tk.IntVar(value=int(getattr(opts,"smoothing_count",3)))
        self.scene_offset=0.0
        self.scene_last=time.monotonic()
        self.live_rejection=LiveRejection(fs=opts.fs)
        self.spectrum_hold=None
        self.active_tab=None
        self.trace_values={'speed':[],'fd':[]}
        self._image=None
        self._image_logo=None
        self._make_ui(opts)
        self.protocol('WM_DELETE_WINDOW',self.shutdown)
        self.bind('<F11>',self.toggle_fullscreen)
        self.bind('<Escape>',lambda e:self.attributes('-fullscreen',False))
        self.after(130,self.refresh)

    def toggle_fullscreen(self,e=None):
        self.attributes('-fullscreen',not self.attributes('-fullscreen'))

    def _make_ui(self,opts):
        hdr=tk.Frame(self,bg=WHITE,height=72)
        hdr.pack(side='top',fill='x')
        hdr.pack_propagate(False)
        try:
            img=Image.open(ASSETS/'logo_aess.png').convert('RGBA')
            img.thumbnail((116,55),Image.Resampling.LANCZOS)
            self._image_logo=ImageTk.PhotoImage(img)
            tk.Label(hdr,image=self._image_logo,bg=WHITE).pack(side='left',padx=(24,20))
        except Exception:
            label(hdr,'AESS',21,color=BLUE,weight='bold').pack(side='left',padx=26)
        tk.Frame(hdr,bg=BORDER,width=1,height=38).pack(side='left',pady=16)
        htitle=tk.Frame(hdr,bg=WHITE)
        htitle.pack(side='left',padx=18)
        label(htitle,'RADAR DOPPLER CW',20,weight='bold').pack(anchor='w')
        self.runmode=tk.Label(hdr,text='SIN CONEXIÓN',bg='#FFF2D9',fg=AMBER,
                              font=(APP_FONT,10,'bold'),padx=15,pady=8)
        self.runmode.pack(side='right',padx=26)
        middle=tk.Frame(self,bg=BG)
        middle.pack(fill='both',expand=True)
        rail=tk.Frame(middle,bg=DEEP,width=174)
        rail.pack(side='left',fill='y')
        rail.pack_propagate(False)
        tk.Frame(rail,bg=DEEP,height=25).pack()
        self.navs={}
        for name in ['Monitor','Análisis','Adquisición','Ajustes']:
            b=tk.Button(rail,text=name,anchor='w',font=(APP_FONT,12,'bold'),
                         bg=DEEP,fg='#CBD9E5',activebackground=NAVY,activeforeground=WHITE,
                         bd=0,relief='flat',padx=22,pady=16,cursor='hand2',
                         command=lambda n=name:self.show(n))
            b.pack(fill='x')
            self.navs[name]=b
        tk.Frame(rail,bg=DEEP).pack(fill='both',expand=True)
        self.content=tk.Frame(middle,bg=BG)
        self.content.pack(fill='both',expand=True,padx=18,pady=(15,14))
        self.pages={}
        for k in self.navs:
            self.pages[k]=tk.Frame(self.content,bg=BG)
        self.build_monitor()
        self.build_analysis()
        self.build_acquisition(opts)
        self.build_settings(opts)
        self.show('Monitor')  # Panel principal con gráficos y seguimiento

    def show(self,name):
        for n,p in self.pages.items():
            p.pack_forget()
            self.navs[n].configure(bg=BLUE if n==name else DEEP,fg=WHITE if n==name else '#CBD9E5')
        self.pages[name].pack(fill='both',expand=True)
        self.active_tab=name
        self.after(25,self.draw_current)

    def build_monitor(self):
        page=self.pages['Monitor']
        page.columnconfigure(0,weight=7)
        page.columnconfigure(1,weight=3,minsize=330)
        page.rowconfigure(0,weight=1)
        page.rowconfigure(1,weight=1)
        a,head=panel(page,'Visualización de señal',0,0)
        ttk.Combobox(head,textvariable=self.main_graph,values=('Doppler','Rechazo de banda'),state='readonly',width=17).pack(side='left',padx=10)
        self.main_graph.trace_add('write',self.change_graph)
        self.spec=tk.Canvas(a,bg='#F9FBFD',highlightthickness=0)
        self.spec.pack(fill='both',expand=True,padx=10,pady=7)
        scale_controls=tk.Frame(head,bg=WHITE)
        scale_controls.pack(side='right',padx=(4,12),pady=6)
        label(scale_controls,'Escala',9,color=MUTED).pack(side='left',padx=(0,5))
        cb=ttk.Combobox(scale_controls,textvariable=self.span_choice,values=[span_label(x) for x in self.spans],
                        state='readonly',width=12,font=(APP_FONT,10))
        cb.pack(side='left',padx=(0,9))
        cb.bind('<<ComboboxSelected>>',self.change_span)
        label(scale_controls,'Unidades',9,color=MUTED).pack(side='left',padx=(0,5))
        cb2=ttk.Combobox(scale_controls,textvariable=self.unit_choice,
                         values=('Auto','Hz','kHz','MHz','GHz'),state='readonly',width=7,font=(APP_FONT,10))
        cb2.pack(side='left')
        cb2.bind('<<ComboboxSelected>>',self.change_display_unit)
        b,_=panel(page,'Lecturas',1,0)
        box=tk.Frame(b,bg=WHITE)
        box.pack(fill='both',expand=True,padx=18,pady=15)
        label(box,'RAPIDEZ RADIAL',10,color=MUTED,weight='bold').pack(anchor='w')
        self.speed_text=label(box,'0.00 m/s',33,color=BLUE,weight='bold')
        self.speed_text.pack(anchor='w',pady=(0,10))
        self.readings={}
        for k,caption in [('fd','Frecuencia Doppler'),('direction','Movimiento'),('snr','Pico / ruido'),('threshold','Umbral')]:
            r=tk.Frame(box,bg=WHITE)
            r.pack(fill='x',pady=6)
            label(r,caption,10,color=MUTED).pack(side='left')
            val=label(r,'—',11,weight='bold')
            val.pack(side='right')
            self.readings[k]=val
        c,_=panel(page,'Espectrograma Doppler',0,1,pady=(0,0))
        self.water=tk.Canvas(c,bg='#0A2645',highlightthickness=0)
        self.water.pack(fill='both',expand=True,padx=10,pady=8)
        d,_=panel(page,'Movimiento 2.5D (posición ilustrativa)',1,1,pady=(0,0))
        trk=tk.Frame(d,bg=WHITE)
        trk.pack(fill='both',expand=True,padx=17,pady=13)
        self.scene_label=label(trk,'SIN DETECCIÓN',12,color=MUTED,weight='bold')
        self.scene_label.pack(anchor='w',pady=(0,8))
        self.track_canvas=tk.Canvas(trk,bg='#102337',height=170,highlightthickness=0)
        self.track_canvas.pack(fill='both',expand=True)
        self.track_status=label(trk,'Posición relativa ilustrativa, sin distancia absoluta',9,color=MUTED)
        self.track_status.pack(anchor='w',pady=7)

    def build_analysis(self):
        page=self.pages['Análisis']
        page.columnconfigure(0,weight=1)
        page.rowconfigure(0,weight=1)
        page.rowconfigure(1,weight=1)
        page.rowconfigure(2,weight=1)
        a,h=panel(page,'Rapidez radial frente al tiempo',0,0)
        button(h,'EXPORTAR CSV',self.export_csv,blue=True).pack(side='right',padx=12)
        self.ch_speed=tk.Canvas(a,bg='#FAFCFE',highlightthickness=0)
        self.ch_speed.pack(fill='both',expand=True,padx=12,pady=8)
        b,_=panel(page,'Frecuencia Doppler frente al tiempo',0,1,pady=(0,0))
        self.ch_fd=tk.Canvas(b,bg='#FAFCFE',highlightthickness=0)
        self.ch_fd.pack(fill='both',expand=True,padx=12,pady=8)
        c,header=panel(page,'Filtro de rechazo de banda · medición en vivo',0,2,pady=(0,0))
        view=tk.Frame(header,bg=WHITE)
        view.pack(side='right',padx=12)
        label(view,'Vista',9,color=MUTED).pack(side='left',padx=(0,6))
        sel=ttk.Combobox(view,textvariable=self.notch_range,values=('400–600 Hz','0–2 kHz', '0–20 kHz'),
                         state='readonly',width=12,font=(APP_FONT,10))
        sel.pack(side='left')
        sel.bind('<<ComboboxSelected>>',lambda e:self.draw_current())
        self.ch_reject=tk.Canvas(c,bg='#FAFCFE',highlightthickness=0)
        self.ch_reject.pack(fill='both',expand=True,padx=12,pady=(5,0))
        self.reject_status=label(c,'Esperando señal sin filtrar (5557) y filtrada (5559)…',
              9,color=MUTED)
        self.reject_status.pack(anchor='w',padx=18,pady=(0,6))

    def build_acquisition(self,opts):
        page=self.pages['Adquisición']
        page.columnconfigure(0,weight=1)
        page.columnconfigure(1,weight=1)
        page.rowconfigure(0,weight=1)
        a,_=panel(page,'Conexión GNU Radio / ZeroMQ',0,0)
        self.acq_labels={}
        f=tk.Frame(a,bg=WHITE)
        f.pack(fill='both',expand=True,padx=22,pady=15)
        for key,title in [('connection','Estado'),('rx','RX / 5557'),('tx','TX / 5558'),
                          ('tone','Tono TX'),('rate','Muestreo esperado'),
                          ('received','Muestreo recibido'),('carrier','Portadora RF'),
                          ('packets','Paquetes RX'),('reference_packets','Paquetes TX'),
                          ('rms','RMS de I/Q'),('age','Último RX'),('message','Diagnóstico')]:
            rr=tk.Frame(f,bg=WHITE)
            rr.pack(fill='x',pady=8)
            label(rr,title,10,color=MUTED).pack(side='left',anchor='w')
            val=label(rr,'—',11,weight='bold',wraplength=300,justify='right')
            val.pack(side='right',anchor='e')
            self.acq_labels[key]=val
        b,_=panel(page,'Verificaciones',1,0)
        f2=tk.Frame(b,bg=WHITE)
        f2.pack(fill='both',expand=True,padx=20,pady=18)
        for txt in ['GNU Radio ejecutándose',
                    'ZMQ RX: complex64 · 48 kS/s · 5557',
                    'ZMQ TX: complex64 · 48 kS/s · 5558',
                    'Ambos ZMQ en modo Bind',
                    'Portadora TX/RX: 2.4 GHz']:
            label(f2,'•  '+txt,11,color=TEXT).pack(anchor='w',pady=11)
        label(f2,'Los contadores y el estado se actualizan automáticamente.',10,color=MUTED,
              wraplength=380,justify='left').pack(anchor='w',pady=(22,0))

    def build_settings(self,opts):
        page=self.pages['Ajustes']
        a,_=panel(page,'Parámetros de detección',0,0)
        a.pack(fill='x') if False else None
        self.thr=tk.DoubleVar(value=float(opts.umbral))
        self.inv=tk.BooleanVar(value=bool(self.engine.invert))
        self.cal=tk.BooleanVar(value=bool(self.engine.calibrated))
        f=tk.Frame(a,bg=WHITE)
        f.pack(fill='x',padx=24,pady=24)
        label(f,'Umbral sobre ruido (dB)',12,weight='bold').pack(anchor='w')
        tk.Scale(f,from_=3,to=65,resolution=1,variable=self.thr,orient='horizontal',length=420,
                 command=self.change_threshold,bg=WHITE,fg=TEXT,highlightthickness=0,
                 troughcolor='#DBE7F0').pack(anchor='w',pady=(5,25))
        tk.Checkbutton(f,text='Invertir signo Doppler',variable=self.inv,command=self.change_invert,
                       bg=WHITE,activebackground=WHITE,selectcolor='#E5F0F7',font=(APP_FONT,12)).pack(anchor='w',pady=6)
        tk.Checkbutton(f,text='Dirección calibrada con movimiento de prueba',variable=self.cal,
                       command=self.change_cal,bg=WHITE,activebackground=WHITE,
                       selectcolor='#E5F0F7',font=(APP_FONT,12)).pack(anchor='w',pady=6)
        label(f,'Umbral mínimo Doppler (Hz)',12,weight='bold').pack(anchor='w',pady=(20,0))
        tk.Scale(f,from_=1,to=30,resolution=1,variable=self.min_hz_var,orient='horizontal',length=420,
                 command=self.change_min_hz,bg=WHITE,fg=TEXT,highlightthickness=0,
                 troughcolor='#DBE7F0').pack(anchor='w',pady=(3,10))
        label(f,'Ignora movimientos radiales por debajo del valor elegido; no mide intensidad.',
              10,color=MUTED).pack(anchor='w')
        label(f,'Suavizado de frecuencia Doppler (mediciones)',12,weight='bold').pack(anchor='w',pady=(20,0))
        tk.Scale(f,from_=1,to=10,resolution=1,variable=self.smooth_var,orient='horizontal',length=420,
                 command=self.change_smooth,bg=WHITE,fg=TEXT,highlightthickness=0,
                 troughcolor='#DBE7F0').pack(anchor='w',pady=(3,10))
        label(f,'El umbral en dB exige un pico suficientemente alto sobre el ruido.',
              10,color=MUTED).pack(anchor='w',pady=(10,0))
        label(f,'Para calibrar: mueve la placa hacia el radar, observa el signo en Monitor,\n'
              'activa Invertir signo si hace falta y confirma la dirección calibrada.',
              10,color=MUTED,justify='left').pack(anchor='w',pady=(14,0))
        button(f,'GUARDAR AJUSTES',self.save_settings,blue=True).pack(anchor='w',pady=(18,0))

    def set_config(self,data):
        try:self.engine.config(data)
        except Exception as e:messagebox.showerror('Configuración',str(e))

    def zero_tracking(self):
        try:
            raw=self.r0.get().strip()
            distance=float(raw) if raw else None
            self.set_config({'tracking_zero':True,'initial_distance_m':distance})
        except ValueError:
            messagebox.showerror('Distancia inicial','Introduzca un número positivo o deje el campo vacío.')

    def clear_tracking(self):self.set_config({'tracking_clear':True})
    def change_min_hz(self,x):self.set_config({'min_doppler_hz':float(x)})
    def change_smooth(self,x):self.set_config({'smoothing_count':int(float(x))})
    def save_settings(self):
        data={'threshold_db':float(self.thr.get()),'min_doppler_hz':float(self.min_hz_var.get()),
              'smoothing_count':int(self.smooth_var.get()),'invert':bool(self.inv.get()),
              'calibrated':bool(self.cal.get())}
        try:
            SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
            SETTINGS_FILE.write_text(json.dumps(data,indent=2),encoding='utf-8')
            messagebox.showinfo('Ajustes','Configuración guardada para el próximo inicio.')
        except OSError as exc:messagebox.showerror('Ajustes',str(exc))
    def change_threshold(self,x):self.set_config({'threshold_db':float(x)})
    def change_invert(self):self.set_config({'invert':self.inv.get()})
    def change_cal(self):self.set_config({'calibrated':self.cal.get()})
    def change_graph(self,*args):
        selected=self.main_graph.get()
        chosen=self.graph_spans.get(selected,180.0)
        self.freq_display=chosen
        self.span_choice.set(span_label(chosen))
        if selected=='Doppler':
            self.set_config({'display_hz':chosen})
        self.draw_current()

    def change_span(self,event=None):
        label_to_span={span_label(v):v for v in self.spans}
        chosen=label_to_span.get(self.span_choice.get())
        if chosen is None or chosen == self.freq_display:return
        try:
            if self.main_graph.get()=='Doppler':self.engine.config({'display_hz':chosen})
        except ValueError as exc:
            messagebox.showerror('Escala del espectro',str(exc))
            self.span_choice.set(span_label(self.freq_display))
            return
        self.freq_display=chosen
        self.graph_spans[self.main_graph.get()]=chosen
        self.rows=[]
        self.spectrum_hold=None
        self.draw_current()

    def change_display_unit(self,event=None):
        self.draw_current()

    def frequency_unit(self,range_hz):
        return unit_for_hz(range_hz,self.unit_choice.get())

    def frequency_reading(self,hz):
        unit=self.frequency_unit(self.freq_display)
        value=hz/UNIT_SCALES[unit]
        return f'{value:+.5g} {unit}'

    def export_csv(self):
        history=self.engine.state()['history']
        if not history:
            messagebox.showinfo('CSV','Aún no hay mediciones.')
            return
        p=filedialog.asksaveasfilename(defaultextension='.csv',filetypes=[('CSV','*.csv')],initialfile='doppler_aess.csv')
        if not p:return
        try:
            with open(p,'w',newline='',encoding='utf-8-sig') as f:
                w=csv.writer(f);w.writerow(['tiempo_s','rapidez_radial_m_s','doppler_hz','detectado','desplazamiento_m'])
                for h in history:w.writerow([h.get('t'),h.get('speed'),h.get('fd'),h.get('present'),h.get('delta')])
        except Exception as e:messagebox.showerror('CSV',str(e))

    def refresh(self):
        try:
            state=self.engine.state()
            self._state=state
            m=state['measurement']
            self.speed_text.config(text=f"{m['speed_m_s']:.2f} m/s" if state['link']=='online' else '— m/s')
            self.readings['fd'].config(text=self.frequency_reading(m['doppler_hz']) if state['link']=='online' else '—')
            self.readings['direction'].config(text=m['direction'] if state['link']=='online' else 'Sin conexión')
            self.readings['snr'].config(text=f"{m['prominence_db']:.1f} dB" if state['link']=='online' else '— dB')
            self.readings['threshold'].config(text=f"{state['threshold_db']:.0f} dB / {state['min_doppler_hz']:.0f} Hz")
            self.scene_label.config(text=m['direction'] if state['link']=='online' else 'SIN CONEXIÓN')
            self.track_status.config(text='Animación relativa; no representa distancia ni ángulo')
            diag=state['rx_diagnostics']
            connected = state['link']=='online'
            rx_age = diag['last_packet_age_s']
            rx_ok = rx_age is not None and rx_age <= 1.2
            tx_ok = state['reference_online']
            self.runmode.config(text='RX + TX CONECTADOS' if connected else 'SIN CONEXIÓN',
                                bg='#E0F0E9' if connected else '#FFF2D9',
                                fg=GREEN if connected else AMBER)
            acq={
              'connection':'RX + TX' if connected else 'ESPERANDO SEÑALES',
              'rx':'Recibiendo' if rx_ok else 'Sin muestras recientes',
              'tx':'Recibiendo' if tx_ok else 'Sin referencia',
              'tone':f"{state['tone_hz']:.2f} Hz" if tx_ok else '—',
              'rate':f"{state['sample_rate']/1000:.2f} kS/s",
              'received':f"{diag['estimated_rate_sps']/1000:.2f} kS/s" if rx_ok else '—',
              'carrier':f"{state['carrier_hz']/1e9:.4f} GHz",
              'packets':f"{diag['packets']}  (inválidos: {diag['invalid_packets']})",
              'reference_packets':f"{state['reference_packets']}  (inválidos: {state['reference_invalid']})",
              'rms':f"{diag['iq_rms']:.5f}" if rx_ok else '—',
              'age':f"{rx_age:.2f} s" if rx_age is not None else '—',
              'message':state['message']}
            for key,value in acq.items(): self.acq_labels[key].config(text=value)
            if state['sequence']!=self.last_seq and state['spectrum_hz']:
                self.last_seq=state['sequence']
                x=np.asarray(state['spectrum_hz'],dtype=np.float64)
                y=np.asarray(state['spectrum_db'],dtype=np.float64)
                coords=np.linspace(-self.freq_display,self.freq_display,240)
                self.rows.append(np.interp(coords,x,y,left=-15.,right=-15.))
                self.rows=self.rows[-self.max_rows:]
            self.draw_current()
        except Exception as e:
            print('ERROR durante refresco:', repr(e))
        if self.winfo_exists():self.after(180,self.refresh)

    def draw_current(self):
        if not hasattr(self,'_state'):return
        state=self._state
        if self.active_tab=='Monitor':
            unit=self.frequency_unit(self.freq_display)
            divisor=UNIT_SCALES[unit]
            freqs=np.asarray(state['spectrum_hz'],dtype=float)/divisor
            span=self.freq_display/divisor
            if self.main_graph.get()=='Rechazo de banda':
                rx,db,status,_=self.live_rejection.snapshot()
                visible=(rx>=0)&(rx<=self.freq_display)
                self.draw_line(self.spec,rx[visible]/divisor,db[visible],
                               f'Frecuencia ({unit})','Atenuación estimada (dB)',
                               (0,span),(-110,30),shaded_bands=[(495/divisor,505/divisor)])
            else:
                self.draw_line(self.spec,freqs,state['spectrum_db'],f'Frecuencia Doppler ({unit})',
                               'dB sobre ruido',(-span,span),(-15,80))
            self.draw_waterfall(self.water)
            self.draw_scene(self.track_canvas,state)
        elif self.active_tab=='Análisis':
            h=state['history']
            tt=[p['t'] for p in h]
            self.draw_line(self.ch_speed,tt,[p['speed'] for p in h],
                           'Tiempo (s)','m/s',None,None)
            unit=self.frequency_unit(self.freq_display)
            divisor=UNIT_SCALES[unit]
            self.draw_line(self.ch_fd,tt,[p['fd']/divisor for p in h],
                           'Tiempo (s)',unit,None,None)
            ranges={'400–600 Hz':(400.,600.),'0–2 kHz':(0.,2000.),'0–20 kHz':(0.,20000.)}
            lo,hi=ranges.get(self.notch_range.get(),(400.,600.))
            notch_unit=self.frequency_unit(hi)
            div=UNIT_SCALES[notch_unit]
            freqs,attenuation,status,updated=self.live_rejection.snapshot()
            self.reject_status.config(text=status)
            present=(freqs>=lo)&(freqs<=hi)
            self.draw_line(self.ch_reject,freqs[present]/div,attenuation[present],
                           f'Frecuencia ({notch_unit})','Atenuación estimada (dB)',
                           (lo/div,hi/div),(-110,30),shaded_bands=[(495./div,505./div)])

    def draw_line(self,canvas,xx,yy,xlabel,ylabel,xlim=None,ylim=None,shaded_bands=None):
        w=canvas.winfo_width();h=canvas.winfo_height()
        if w<80 or h<80:return
        canvas.delete('all')
        left=56;right=w-18;top=18;bottom=h-38
        canvas.create_rectangle(left,top,right,bottom,fill='#F9FBFD',outline=BORDER)
        xa=np.asarray(xx,dtype=float);ya=np.asarray(yy,dtype=float)
        if xlim is None:
            if xa.size: xmin=float(xa.min());xmax=float(xa.max())
            else:xmin,xmax=0,10
            if xmax-xmin<1e-5:xmax=xmin+1
        else:xmin,xmax=xlim
        if ylim is None:
            if ya.size:
                finite=ya[np.isfinite(ya)]
                if finite.size:
                    ymin=min(0.,float(np.min(finite)))
                    ymax=max(0.,float(np.max(finite)))
                else:
                    ymin,ymax=0.,0.
                if ymax==ymin:
                    # En MHz/GHz, una escala fija de 0.5 unidades borraría la curva Doppler.
                    pad=1.0/UNIT_SCALES.get(ylabel,10.0)
                else:
                    pad=(ymax-ymin)*0.15
                ymin-=pad;ymax+=pad
            else:ymin,ymax=0,1
        else:ymin,ymax=ylim
        for band_lo,band_hi in (shaded_bands or ()):
            band_l=max(left,min(right,left+(band_lo-xmin)/(xmax-xmin)*(right-left)))
            band_r=max(left,min(right,left+(band_hi-xmin)/(xmax-xmin)*(right-left)))
            if band_r>band_l:
                canvas.create_rectangle(band_l,top,band_r,bottom,fill='#F9E4E4',outline='')
        for j in range(5):
            x=left+(right-left)*j/4
            y=bottom-(bottom-top)*j/4
            canvas.create_line(x,top,x,bottom,fill='#E6EDF3',dash=(3,3))
            canvas.create_line(left,y,right,y,fill='#E6EDF3',dash=(3,3))
            canvas.create_text(x,bottom+13,text=tick_label(xmin+(xmax-xmin)*j/4,(xmax-xmin)/4),fill=MUTED,font=(APP_FONT,9))
            canvas.create_text(left-8,y,text=tick_label(ymin+(ymax-ymin)*j/4,(ymax-ymin)/4),fill=MUTED,font=(APP_FONT,9),anchor='e')
        canvas.create_text((left+right)/2,h-11,text=xlabel,fill=MUTED,font=(APP_FONT,9))
        canvas.create_text(7,8,text=ylabel,fill=MUTED,anchor='nw',font=(APP_FONT,9))
        if xa.size>1:
            inband=(xa>=xmin)&(xa<=xmax)&np.isfinite(ya)
            vals=np.flatnonzero(inband)
            if len(vals)>1:
                if len(vals)>max(700,w): vals=vals[::int(np.ceil(len(vals)/max(700,w)))]
                xcoords=left+(xa[vals]-xmin)/(xmax-xmin)*(right-left)
                ycoords=bottom-(ya[vals]-ymin)/(ymax-ymin)*(bottom-top)
                ycoords=np.clip(ycoords,top,bottom)
                points=list(np.column_stack((xcoords,ycoords)).ravel())
                canvas.create_line(*points,fill=BLUE,width=1.8,smooth=False)

    def draw_waterfall(self,canvas):
        w=canvas.winfo_width();h=canvas.winfo_height()
        if w<100 or h<80:return
        canvas.delete('all')
        left=55;right=w-18;top=16;bottom=h-38
        if self.rows:
            mat=np.asarray(self.rows,dtype=np.float32)
            out=np.full((self.max_rows,mat.shape[1]),-15.,dtype=np.float32)
            out[-len(mat):]=mat
            p=np.clip((out+12.)/65.,0,1)
            # Lab palette: blue/white, high-contrast peaks, no rainbow
            stops=np.array([[6,31,58],[12,69,115],[23,125,179],[84,188,221],[230,245,254],[255,202,106]],dtype=np.float32)
            ramp=p*(len(stops)-1)
            inds=np.minimum(ramp.astype(int),len(stops)-2)
            frac=(ramp-inds)[...,None]
            rgb=np.clip(stops[inds]*(1-frac)+stops[inds+1]*frac,0,255).astype(np.uint8)
            pic=Image.fromarray(rgb,mode='RGB').resize((max(1,right-left),max(1,bottom-top)),Image.Resampling.BILINEAR)
            self._image=ImageTk.PhotoImage(pic)
            canvas.create_image(left,top,anchor='nw',image=self._image)
        else:
            canvas.create_rectangle(left,top,right,bottom,fill=DEEP,outline=DEEP)
        canvas.create_rectangle(left,top,right,bottom,outline='#6F93AF')
        unit=self.frequency_unit(self.freq_display)
        divisor=UNIT_SCALES[unit]
        for j in range(5):
            x=left+(right-left)*j/4
            canvas.create_line(x,top,x,bottom,fill='#8EB7D1',dash=(2,6))
            val=(-self.freq_display+2*self.freq_display*j/4)/divisor
            canvas.create_text(x,bottom+14,text=tick_label(val,self.freq_display/(2*divisor)),fill=MUTED,font=(APP_FONT,9))
        canvas.create_text((left+right)/2,h-10,text=f'Frecuencia Doppler ({unit})',fill=MUTED,font=(APP_FONT,9))
        canvas.create_text(6,8,text='Tiempo ↓',fill=MUTED,font=(APP_FONT,9),anchor='nw')

    def draw_scene(self,canvas,state):
        w=canvas.winfo_width();h=canvas.winfo_height()
        if w<100 or h<70:return
        canvas.delete('all')
        canvas.create_rectangle(0,0,w,h,fill='#102337',outline='')
        horizon=h*.28
        canvas.create_polygon(0,horizon,w,horizon,w,h,0,h,fill='#19364D',outline='')
        cx=w/2
        for i in range(-3,4):
            canvas.create_line(cx+i*18,horizon,cx+i*w/5,h,fill='#30556C')
        for t in (.4,.57,.76,.95):
            y=horizon+(h-horizon)*t*t
            canvas.create_line(0,y,w,y,fill='#30556C')
        canvas.create_oval(cx-24,h-23,cx+24,h-8,outline='#36C6F0',width=2)
        canvas.create_text(cx,h-4,text='RADAR',fill='#A5D2E5',font=(APP_FONT,8))
        m=state['measurement']
        now=time.monotonic();dt=min(now-self.scene_last,.3);self.scene_last=now
        if state['link']=='online' and m['detected'] and state['calibrated']:
            sign=1 if m['direction']=='ACERCÁNDOSE' else -1
            self.scene_offset=float(np.clip(self.scene_offset+sign*m['speed_m_s']*dt*.20,-.8,.8))
        # La posición visual no es un rango: sólo representa movimiento radial acumulado.
        scale=1+.55*self.scene_offset
        oy=h*.49+h*.14*self.scene_offset
        size=23*scale
        x=cx;y=oy
        canvas.create_oval(x-size*.9,y+size*.65,x+size*.9,y+size,fill='#0C1A27',outline='')
        canvas.create_polygon(x,y-size,x+size,y-size*.5,x,y, x-size,y-size*.5,
                              fill='#8AD6F5',outline='#D0F2FF')
        canvas.create_polygon(x-size,y-size*.5,x,y,x,y+size,x-size,y+size*.48,
                              fill='#368FBE',outline='#B0E5FA')
        canvas.create_polygon(x,y,x+size,y-size*.5,x+size,y+size*.48,x,y+size,
                              fill='#1E638E',outline='#B0E5FA')
        canvas.create_text(12,12,anchor='nw',text='VISTA 2.5D · ILUSTRATIVA',
                           fill='#B9D9EB',font=(APP_FONT,9,'bold'))
        if not state['calibrated']:
            canvas.create_text(w-12,12,anchor='ne',text='DIRECCIÓN SIN CALIBRAR',fill='#F4C77A',font=(APP_FONT,9))

    def shutdown(self):
        self.engine.running=False
        self.live_rejection.stop()
        if sys.platform == 'win32':
            for fpath in TEMP_FONT_PATHS:
                try:
                    ctypes.windll.gdi32.RemoveFontResourceExW(str(fpath),0x10,None)
                    fpath.unlink(missing_ok=True)
                    fpath.parent.rmdir()
                except Exception:
                    pass
        self.destroy()


def options():
    parser=argparse.ArgumentParser(description='PlutoRadar AESS V10 | Solo Pluto real')
    parser.add_argument('--config',default=str(ROOT/'configuracion_radar.json'))
    parser.add_argument('--comprobar-inicio', type=Path, help=argparse.SUPPRESS)
    opts=parser.parse_args()
    try:
        conf=json.loads(Path(opts.config).read_text(encoding='utf-8'))
        opts.fs=float(conf['sample_rate'])
        opts.fc=float(conf['carrier_hz'])
        opts.zmq=conf['zmq_rx']
        opts.zmq_ref=conf['zmq_ref']
        opts.metadata_origin='configuración de GNU Radio'
    except (OSError,ValueError,KeyError,TypeError) as exc:
        parser.error('No se pudo leer configuracion_radar.json: '+str(exc))
    opts.tono=0.0
    opts.umbral=16.0
    opts.min_doppler_hz=6.0
    opts.smoothing_count=3
    try:
        settings_path = SETTINGS_FILE if SETTINGS_FILE.is_file() else ROOT/'ajustes_usuario.json'
        saved=json.loads(settings_path.read_text(encoding='utf-8'))
        opts.umbral=float(saved.get('threshold_db',opts.umbral))
        opts.min_doppler_hz=float(saved.get('min_doppler_hz',opts.min_doppler_hz))
        opts.smoothing_count=int(saved.get('smoothing_count',opts.smoothing_count))
        opts.saved_settings=saved
    except (OSError,ValueError,TypeError,AttributeError):opts.saved_settings={}
    return opts

def main():
    opts = options()
    app = AESSDesktop(opts)
    if opts.comprobar_inicio:
        app.after(500, app.quit)
    app.mainloop()
    if opts.comprobar_inicio:
        try:
            if app._image_logo is None or not app.winfo_viewable():
                raise RuntimeError('No se pudo mostrar la ventana con el logotipo')
            if not app.engine.worker.is_alive() or not app.live_rejection.thread.is_alive():
                raise RuntimeError('No se pudieron iniciar los receptores ZeroMQ')
            opts.comprobar_inicio.write_text('OK', encoding='ascii')
        finally:
            app.shutdown()


if __name__ == '__main__':
    main()
