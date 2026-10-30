import ctypes, ctypes.wintypes as wt, os, sys, time, threading, subprocess, tempfile, shutil, queue, datetime, json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import numpy as np
import soundcard as sc
import soundfile as sf
from PIL import ImageGrab, ImageTk, Image
import winreg

APP = 'Simple Screen Recorder'
CREATE_NO_WINDOW = 0x08000000
BASE = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
FFMPEG = str(BASE / 'ffmpeg.exe') if (BASE / 'ffmpeg.exe').exists() else (shutil.which('ffmpeg') or str(BASE / 'ffmpeg.exe'))
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception: pass

def screens():
    result = []
    class RECT(ctypes.Structure): _fields_ = [('left',wt.LONG),('top',wt.LONG),('right',wt.LONG),('bottom',wt.LONG)]
    class MONITORINFOEX(ctypes.Structure): _fields_ = [('cbSize',wt.DWORD),('rcMonitor',RECT),('rcWork',RECT),('dwFlags',wt.DWORD),('szDevice',wt.WCHAR*32)]
    callback = ctypes.WINFUNCTYPE(wt.BOOL, wt.HMONITOR, wt.HDC, ctypes.POINTER(RECT), wt.LPARAM)
    def visit(handle, dc, rect, data):
        info = MONITORINFOEX(); info.cbSize = ctypes.sizeof(info)
        if ctypes.windll.user32.GetMonitorInfoW(handle, ctypes.byref(info)):
            r=info.rcMonitor; result.append(dict(x=r.left,y=r.top,w=r.right-r.left,h=r.bottom-r.top,primary=bool(info.dwFlags & 1)))
        return True
    cb=callback(visit); ctypes.windll.user32.EnumDisplayMonitors(None,None,cb,0)
    return result

class App:
    def __init__(self, root):
        self.root=root; root.title(APP); root.resizable(False,False)
        try: root.iconbitmap(str(BASE / 'app.ico'))
        except tk.TclError: pass
        self.proc=None; self.recording=False; self.busy=False; self.events=queue.Queue(); self.stop_audio=threading.Event(); self.threads=[]
        self.folder=tk.StringVar(value=str(Path.home()/'Videos')); self.quality=tk.StringVar(value='Balanced'); self.sound=tk.BooleanVar(value=True); self.mic=tk.BooleanVar(value=False); self.status=tk.StringVar(value='Ready to record')
        self.theme=tk.StringVar(value='System'); self.fps=tk.StringVar(value='30'); self.resolution=tk.StringVar(value='Original'); self.selected_screen=0; self.preview_images=[]; self.cards=[]; self.applied_theme=None
        self.style=ttk.Style(root); self.style.theme_use('clam')
        self.frame=frame=ttk.Frame(root,padding=22); frame.grid(sticky='nsew'); frame.columnconfigure(0,weight=1)
        header=ttk.Frame(frame); header.grid(row=0,column=0,columnspan=2,sticky='ew'); header.columnconfigure(0,weight=1)
        ttk.Label(header,text='●  Simple Screen Recorder',style='Title.TLabel').grid(row=0,column=0,sticky='w')
        self.theme_box=ttk.Combobox(header,state='readonly',textvariable=self.theme,values=['System','Light','Dark'],width=8); self.theme_box.grid(row=0,column=1,sticky='e'); self.theme_box.bind('<<ComboboxSelected>>',lambda e:self.apply_theme())
        ttk.Label(frame,text='Capture your screen in a few clicks.',style='Sub.TLabel').grid(row=1,column=0,columnspan=2,sticky='w',pady=(3,18))
        line=ttk.Frame(frame); line.grid(row=2,column=0,columnspan=2,sticky='ew'); line.columnconfigure(0,weight=1)
        ttk.Label(line,text='CHOOSE A SCREEN',style='Section.TLabel').grid(row=0,column=0,sticky='w'); self.refresh_button=ttk.Button(line,text='↻  Refresh previews',command=self.refresh_screens,style='Quiet.TButton'); self.refresh_button.grid(row=0,column=1,sticky='e')
        self.preview_canvas=tk.Canvas(frame,width=612,height=157,highlightthickness=0,bd=0); self.preview_canvas.grid(row=3,column=0,columnspan=2,sticky='ew',pady=(7,0))
        self.preview_frame=ttk.Frame(self.preview_canvas); self.preview_window=self.preview_canvas.create_window((0,0),window=self.preview_frame,anchor='nw')
        self.preview_frame.bind('<Configure>',lambda e:self.preview_canvas.configure(scrollregion=self.preview_canvas.bbox('all')))
        self.scroll=ttk.Scrollbar(frame,orient='horizontal',command=self.preview_canvas.xview); self.preview_canvas.configure(xscrollcommand=self.scroll.set); self.scroll.grid(row=4,column=0,columnspan=2,sticky='ew',pady=(0,14))
        ttk.Label(frame,text='AUDIO',style='Section.TLabel').grid(row=5,column=0,sticky='w'); audio=ttk.Frame(frame); audio.grid(row=6,column=0,columnspan=2,sticky='w',pady=(7,16))
        self.audio_checks=[ttk.Checkbutton(audio,text='Computer sound',variable=self.sound),ttk.Checkbutton(audio,text='Microphone',variable=self.mic)]
        for i,c in enumerate(self.audio_checks): c.grid(row=0,column=i,sticky='w',padx=(0,24))
        ttk.Label(frame,text='QUALITY',style='Section.TLabel').grid(row=7,column=0,sticky='w'); self.q=ttk.Combobox(frame,state='readonly',textvariable=self.quality,values=['Small file','Balanced','High quality'],width=54); self.q.grid(row=8,column=0,columnspan=2,sticky='ew',pady=(6,3)); ttk.Label(frame,text='Compression: smaller files or higher detail',style='Sub.TLabel').grid(row=9,column=0,columnspan=2,sticky='w',pady=(0,12))
        options=ttk.Frame(frame); options.grid(row=10,column=0,columnspan=2,sticky='ew',pady=(0,15)); options.columnconfigure(0,weight=1); options.columnconfigure(1,weight=1)
        ttk.Label(options,text='RESOLUTION',style='Section.TLabel').grid(row=0,column=0,sticky='w'); ttk.Label(options,text='FRAMES PER SECOND',style='Section.TLabel').grid(row=0,column=1,sticky='w')
        self.res_box=ttk.Combobox(options,state='readonly',textvariable=self.resolution,values=['Original','1080p','1440p / 2K','2160p / 4K'],width=25); self.res_box.grid(row=1,column=0,sticky='ew',padx=(0,10),pady=(6,0)); self.fps_box=ttk.Combobox(options,state='readonly',textvariable=self.fps,values=['15','24','30','60'],width=25); self.fps_box.grid(row=1,column=1,sticky='ew',pady=(6,0))
        ttk.Label(frame,text='SAVE TO',style='Section.TLabel').grid(row=11,column=0,sticky='w'); self.path=ttk.Entry(frame,textvariable=self.folder,width=43); self.path.grid(row=12,column=0,sticky='ew',pady=(6,17)); self.browse=ttk.Button(frame,text='Browse…',command=self.choose_folder); self.browse.grid(row=12,column=1,padx=(8,0),pady=(6,17))
        self.button=ttk.Button(frame,text='●   Start recording',command=self.toggle,style='Accent.TButton'); self.button.grid(row=13,column=0,columnspan=2,sticky='ew',ipady=8)
        ttk.Label(frame,textvariable=self.status,style='Sub.TLabel').grid(row=14,column=0,columnspan=2,sticky='w',pady=(12,0))
        self.controls=[self.q,self.res_box,self.fps_box,self.path,self.browse,self.refresh_button]+self.audio_checks
        self.refresh_screens(); self.apply_theme(); self.watch_theme(); root.protocol('WM_DELETE_WINDOW',self.close); self.poll()
    def system_theme(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
                return 'Light' if winreg.QueryValueEx(key,'AppsUseLightTheme')[0] else 'Dark'
        except OSError: return 'Light'
    def apply_theme(self):
        mode=self.system_theme() if self.theme.get()=='System' else self.theme.get()
        if mode==self.applied_theme: return
        self.applied_theme=mode
        dark=mode=='Dark'; bg='#171b24' if dark else '#f5f7fb'; fg='#f1f3f8' if dark else '#182235'; muted='#a9b3c3' if dark else '#66758a'; field='#293140' if dark else '#ffffff'; border='#445166' if dark else '#d5dce7'
        self.bg,self.fg,self.muted,self.field,self.border=bg,fg,muted,field,border
        self.root.configure(bg=bg); self.preview_canvas.configure(bg=bg)
        self.style.configure('.',background=bg,foreground=fg,font=('Segoe UI',10)); self.style.configure('TFrame',background=bg); self.style.configure('TLabel',background=bg,foreground=fg)
        self.style.configure('Title.TLabel',font=('Segoe UI',17,'bold'),foreground=fg); self.style.configure('Sub.TLabel',foreground=muted,font=('Segoe UI',9)); self.style.configure('Section.TLabel',font=('Segoe UI',9,'bold'),foreground=muted)
        self.style.configure('TCheckbutton',background=bg,foreground=fg); self.style.map('TCheckbutton',background=[('active',bg)],foreground=[('disabled',muted)])
        self.style.configure('TButton',background=field,foreground=fg,bordercolor=border,padding=(10,6)); self.style.map('TButton',background=[('active',border),('disabled',bg)],foreground=[('disabled',muted)])
        self.style.configure('Quiet.TButton',background=bg,foreground=muted,borderwidth=0,padding=(5,2))
        self.style.configure('Accent.TButton',background='#e74757',foreground='#ffffff',borderwidth=0,font=('Segoe UI',11,'bold')); self.style.map('Accent.TButton',background=[('disabled',border),('active','#c93344')],foreground=[('disabled',muted)])
        self.style.configure('TCombobox',fieldbackground=field,background=field,foreground=fg,arrowcolor=fg,bordercolor=border); self.style.map('TCombobox',fieldbackground=[('readonly',field)],foreground=[('readonly',fg),('disabled',muted)],selectbackground=[('readonly',field)],selectforeground=[('readonly',fg)])
        self.style.configure('TEntry',fieldbackground=field,foreground=fg,bordercolor=border,insertcolor=fg); self.style.configure('Horizontal.TScrollbar',background=field,troughcolor=bg,arrowcolor=muted)
        self.paint_cards()
    def watch_theme(self):
        if self.theme.get()=='System': self.apply_theme()
        self.root.after(1500,self.watch_theme)
    def refresh_screens(self):
        old=self.selected_screen; self.displays=screens(); self.selected_screen=min(old,max(0,len(self.displays)-1)); self.preview_images=[]
        for card in self.cards: card.destroy()
        self.cards=[]
        for i,s in enumerate(self.displays):
            try:
                image=ImageGrab.grab(bbox=(s['x'],s['y'],s['x']+s['w'],s['y']+s['h']),all_screens=True)
                image.thumbnail((184,103),Image.Resampling.LANCZOS)
                bg=Image.new('RGB',(184,103),'#202938'); bg.paste(image,((184-image.width)//2,(103-image.height)//2)); photo=ImageTk.PhotoImage(bg)
            except Exception: photo=None
            self.preview_images.append(photo)
            card=tk.Frame(self.preview_frame,bd=0,highlightthickness=3,cursor='hand2'); card.grid(row=0,column=i,padx=(0,8),pady=(2,2))
            img=tk.Label(card,image=photo,width=184 if photo else 24,height=103 if photo else 5,bd=0,bg='#202938',fg='white',text='' if photo else 'Preview unavailable',cursor='hand2'); img.pack()
            label=tk.Label(card,text=f"Screen {i+1}{'  ·  Primary' if s['primary'] else ''}   {s['w']} × {s['h']}",font=('Segoe UI',8,'bold'),anchor='w',padx=5,pady=5,cursor='hand2'); label.pack(fill='x')
            for widget in (card,img,label): widget.bind('<Button-1>',lambda e,n=i:self.select_screen(n))
            self.cards.append(card)
        self.paint_cards()
    def select_screen(self,index):
        if not self.recording and not self.busy: self.selected_screen=index; self.paint_cards()
    def paint_cards(self):
        if not hasattr(self,'field'): return
        for i,card in enumerate(self.cards):
            card.configure(highlightbackground='#e74757' if i==self.selected_screen else self.border, highlightcolor='#e74757' if i==self.selected_screen else self.border)
            card.winfo_children()[1].configure(bg=self.field,fg=self.fg)
    def choose_folder(self):
        p=filedialog.askdirectory(initialdir=self.folder.get(),title='Choose where to save recordings')
        if p: self.folder.set(p)
    def set_controls(self, enabled):
        for c in self.controls: c.configure(state=('readonly' if c in (self.q,self.res_box,self.fps_box) else 'normal') if enabled else 'disabled')
    def toggle(self):
        if self.recording: self.stop(); return
        if self.busy: return
        self.start()
    def start(self):
        if not self.displays: messagebox.showerror(APP,'No screen was found.'); return
        folder=Path(self.folder.get()).expanduser()
        if not folder.is_dir(): messagebox.showerror(APP,'Please choose an existing folder.'); return
        devices=[]
        try:
            if self.sound.get():
                speaker=sc.default_speaker()
                if speaker is None: raise RuntimeError('No default speaker was found. Choose a Windows output device or turn off computer sound.')
                devices.append(('computer',sc.get_microphone(id=str(speaker.id),include_loopback=True)))
            if self.mic.get():
                mic=sc.default_microphone()
                if mic is None: raise RuntimeError('No default microphone was found. Connect one or turn off microphone audio.')
                devices.append(('microphone',mic))
        except Exception as e: messagebox.showerror(APP,f'Could not open an audio device:\n{e}'); return
        self.temp=Path(tempfile.mkdtemp(prefix='simple-screen-recorder-')); self.video=self.temp/'video.mp4'; self.audios=[]; self.stop_audio.clear(); self.threads=[]
        s=self.displays[self.selected_screen]; crf={'Small file':28,'Balanced':23,'High quality':20}[self.quality.get()]; fps=int(self.fps.get())
        dimensions={'1080p':(1920,1080),'1440p / 2K':(2560,1440),'2160p / 4K':(3840,2160)}.get(self.resolution.get())
        vf='pad=ceil(iw/2)*2:ceil(ih/2)*2'
        if dimensions:
            width,height=dimensions if s['w']>=s['h'] else dimensions[::-1]
            vf=f"scale=w='min(iw,{width})':h='min(ih,{height})':force_original_aspect_ratio=decrease:force_divisible_by=2,"+vf
        stamp=datetime.datetime.now().strftime('%Y-%m-%d %H-%M-%S'); self.output=folder/f'Recording {stamp}.mp4'; n=1
        while self.output.exists(): self.output=folder/f'Recording {stamp} ({n}).mp4'; n+=1
        cmd=[FFMPEG,'-hide_banner','-loglevel','error','-y','-f','gdigrab','-framerate',str(fps),'-offset_x',str(s['x']),'-offset_y',str(s['y']),'-video_size',f"{s['w']}x{s['h']}",'-i','desktop','-an','-vf',vf,'-c:v','libx264','-preset','veryfast','-crf',str(crf),'-pix_fmt','yuv420p','-movflags','+faststart',str(self.video)]
        try:
            self.log=open(self.temp/'ffmpeg.log','w+',encoding='utf-8'); self.proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=self.log,creationflags=CREATE_NO_WINDOW)
            for name,device in devices:
                path=self.temp/f'{name}.wav'; self.audios.append(path)
                thread=threading.Thread(target=self.capture_audio,args=(device,path,name),daemon=True); thread.start(); self.threads.append(thread)
        except Exception as e:
            if self.proc and self.proc.poll() is None: self.proc.kill()
            self.stop_audio.set(); messagebox.showerror(APP,f'Could not start recording:\n{e}'); return
        self.recording=True; self.started=time.monotonic(); self.set_controls(False); self.button.config(text='■  Stop recording'); self.root.after(500,self.tick)
    def capture_audio(self,device,path,name):
        try:
            with device.recorder(samplerate=48000,channels=2,blocksize=2048) as recorder, sf.SoundFile(str(path),mode='w',samplerate=48000,channels=2,subtype='PCM_16') as out:
                while not self.stop_audio.is_set(): out.write(recorder.record(numframes=2048))
        except Exception as e: self.events.put(('audio_error',f'{name.capitalize()} audio could not be recorded: {e}'))
    def tick(self):
        if self.recording:
            elapsed=int(time.monotonic()-self.started); self.status.set(f'Recording  •  {elapsed//60:02d}:{elapsed%60:02d}')
            if self.proc.poll() is not None: self.events.put(('process_error','Screen capture stopped unexpectedly.')); self.stop(); return
            self.root.after(500,self.tick)
    def stop(self):
        if not self.recording: return
        self.recording=False; self.busy=True; self.stop_audio.set(); self.button.configure(state='disabled',text='Saving…'); self.status.set('Finishing your recording…')
        threading.Thread(target=self.finish,daemon=True).start()
    def finish(self):
        try:
            try: self.proc.stdin.write(b'q\n'); self.proc.stdin.flush()
            except (BrokenPipeError,OSError): pass
            try: self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired: self.proc.kill(); self.proc.wait()
            for t in self.threads: t.join(timeout=8)
            self.log.flush(); self.log.seek(0); log=self.log.read(); self.log.close()
            if self.proc.returncode != 0 or not self.video.exists() or self.video.stat().st_size<1000: raise RuntimeError('Screen capture failed. '+log[-1400:])
            valid=[p for p in self.audios if p.exists() and p.stat().st_size>1000]
            if valid:
                cmd=[FFMPEG,'-hide_banner','-loglevel','error','-y','-i',str(self.video)]
                for p in valid: cmd+=['-i',str(p)]
                if len(valid)==2: cmd+=['-filter_complex','[1:a][2:a]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95[a]','-map','0:v:0','-map','[a]']
                else: cmd+=['-map','0:v:0','-map','1:a:0']
                cmd+=['-c:v','copy','-c:a','aac','-b:a','128k','-shortest','-movflags','+faststart',str(self.output)]
                p=subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,creationflags=CREATE_NO_WINDOW,text=True)
                if p.returncode: raise RuntimeError('Could not combine audio and video: '+p.stderr[-1400:])
            else: shutil.copy2(self.video,self.output)
            shutil.rmtree(self.temp,ignore_errors=True); self.events.put(('done',str(self.output)))
        except Exception as e: self.events.put(('error',f'{e}\n\nTemporary files were kept at:\n{self.temp}'))
    def poll(self):
        try:
            while True:
                kind,data=self.events.get_nowait()
                if kind in ('audio_error','process_error'):
                    if self.recording: self.stop()
                    messagebox.showwarning(APP,data+'\nRecording is being stopped.')
                elif kind=='done':
                    self.busy=False; self.proc=None; self.set_controls(True); self.button.configure(state='normal',text='●   Start recording'); self.status.set('Saved: '+Path(data).name); messagebox.showinfo(APP,'Recording saved to:\n'+data)
                elif kind=='error':
                    self.busy=False; self.proc=None; self.set_controls(True); self.button.configure(state='normal',text='●   Start recording'); self.status.set('Could not save recording'); messagebox.showerror(APP,data)
        except queue.Empty: pass
        self.root.after(200,self.poll)
    def close(self):
        if self.recording or self.busy: messagebox.showinfo(APP,'Stop the recording and wait for it to finish saving before closing.'); return
        self.root.destroy()

if __name__=='__main__':
    root=tk.Tk(); App(root); root.mainloop()
