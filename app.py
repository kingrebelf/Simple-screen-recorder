import ctypes, ctypes.wintypes as wt, os, sys, time, threading, subprocess, tempfile, shutil, queue, datetime, json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import numpy as np
import soundcard as sc
import soundfile as sf
from PIL import ImageGrab, Image
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
        self.folder=tk.StringVar(value=str(Path.home()/'Videos')); self.quality=tk.StringVar(value='Balanced'); self.sound=tk.BooleanVar(value=True); self.mic=tk.BooleanVar(value=False); self.show_mouse=tk.BooleanVar(value=True); self.status=tk.StringVar(value='Ready to record')
        self.theme=tk.StringVar(value='System'); self.fps=tk.StringVar(value='30'); self.resolution=tk.StringVar(value='Original'); self.selected_screen=0; self.preview_images=[]; self.cards=[]; self.applied_theme=None
        self.background=('#f5f4f2','#16181e'); self.surface=('#ffffff','#22252d'); self.subtle=('#eeedeb','#2d313b'); self.text=('#272a32','#f7f6f4'); self.muted=('#777b86','#9ca2ae'); self.line=('#deddd9','#3b404b'); self.accent='#d65361'
        self.root.configure(fg_color=self.background)
        frame=ctk.CTkFrame(root,fg_color='transparent'); frame.grid(row=0,column=0,padx=28,pady=(22,20),sticky='nsew'); frame.grid_columnconfigure(0,weight=1)
        header=ctk.CTkFrame(frame,fg_color='transparent'); header.grid(row=0,column=0,sticky='ew'); header.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(header,text='●   SCREEN RECORDER',text_color=self.accent,font=ctk.CTkFont(family='Segoe UI',size=11,weight='bold')).grid(row=0,column=0,sticky='w')
        self.theme_box=ctk.CTkOptionMenu(header,values=['System','Light','Dark'],variable=self.theme,command=lambda _:self.apply_theme(),width=112,height=34,corner_radius=10,fg_color=self.surface,button_color=self.surface,button_hover_color=self.subtle,text_color=self.text,dropdown_fg_color=self.surface,dropdown_text_color=self.text,font=ctk.CTkFont(family='Segoe UI',size=12)); self.theme_box.grid(row=0,column=1,sticky='e')
        ctk.CTkLabel(frame,text='Capture your screen.',font=ctk.CTkFont(family='Segoe UI',size=25,weight='bold'),text_color=self.text).grid(row=1,column=0,sticky='w',pady=(8,0))
        ctk.CTkLabel(frame,text='A little setup, then you’re ready to roll.',text_color=self.muted,font=ctk.CTkFont(family='Segoe UI',size=12)).grid(row=2,column=0,sticky='w',pady=(0,15))
        line=ctk.CTkFrame(frame,fg_color='transparent'); line.grid(row=3,column=0,sticky='ew'); line.grid_columnconfigure(0,weight=1)
        self.label(line,'Choose a screen').grid(row=0,column=0,sticky='w')
        self.refresh_button=ctk.CTkButton(line,text='↻  Refresh',width=85,height=30,corner_radius=9,fg_color='transparent',hover_color=self.subtle,text_color=self.muted,font=ctk.CTkFont(family='Segoe UI',size=12),command=self.refresh_screens); self.refresh_button.grid(row=0,column=1,sticky='e')
        self.preview_frame=ctk.CTkScrollableFrame(frame,width=610,height=160,orientation='horizontal',corner_radius=12,fg_color='transparent',scrollbar_button_color=self.line,scrollbar_button_hover_color=self.muted); self.preview_frame.grid(row=4,column=0,sticky='ew',pady=(4,12))
        self.label(frame,'Audio & cursor').grid(row=5,column=0,sticky='w')
        audio=ctk.CTkFrame(frame,fg_color=self.surface,corner_radius=13); audio.grid(row=6,column=0,sticky='ew',pady=(7,14))
        check_kw=dict(corner_radius=6,checkbox_width=20,checkbox_height=20,border_width=2,fg_color=self.accent,hover_color='#b64351',border_color=self.line,text_color=self.text,font=ctk.CTkFont(family='Segoe UI',size=12))
        self.audio_checks=[ctk.CTkCheckBox(audio,text='Computer sound',variable=self.sound,**check_kw),ctk.CTkCheckBox(audio,text='Microphone',variable=self.mic,**check_kw),ctk.CTkCheckBox(audio,text='Show mouse cursor',variable=self.show_mouse,**check_kw)]
        for i,c in enumerate(self.audio_checks): c.grid(row=0,column=i,sticky='w',padx=(15,5),pady=15)
        self.label(frame,'Video settings').grid(row=7,column=0,sticky='w')
        options=ctk.CTkFrame(frame,fg_color='transparent'); options.grid(row=8,column=0,sticky='ew',pady=(6,13))
        for i in range(3): options.grid_columnconfigure(i,weight=1,uniform='settings')
        for i,title in enumerate(('COMPRESSION','RESOLUTION','FRAME RATE')): ctk.CTkLabel(options,text=title,text_color=self.muted,font=ctk.CTkFont(family='Segoe UI',size=10,weight='bold')).grid(row=0,column=i,sticky='w',padx=(0,10))
        option_kw=dict(height=38,corner_radius=10,fg_color=self.surface,button_color=self.surface,button_hover_color=self.subtle,text_color=self.text,dropdown_fg_color=self.surface,dropdown_text_color=self.text,font=ctk.CTkFont(family='Segoe UI',size=12))
        self.q=ctk.CTkOptionMenu(options,variable=self.quality,values=['Small file','Balanced','High quality'],**option_kw); self.q.grid(row=1,column=0,sticky='ew',padx=(0,10),pady=(4,0))
        self.res_box=ctk.CTkOptionMenu(options,variable=self.resolution,values=['Original','1080p','1440p / 2K','2160p / 4K'],**option_kw); self.res_box.grid(row=1,column=1,sticky='ew',padx=(0,10),pady=(4,0))
        self.fps_box=ctk.CTkOptionMenu(options,variable=self.fps,values=['15','24','30','60'],**option_kw); self.fps_box.grid(row=1,column=2,sticky='ew',pady=(4,0))
        self.label(frame,'Save to').grid(row=9,column=0,sticky='w')
        dest=ctk.CTkFrame(frame,fg_color='transparent'); dest.grid(row=10,column=0,sticky='ew',pady=(7,17)); dest.grid_columnconfigure(0,weight=1)
        self.path=ctk.CTkEntry(dest,textvariable=self.folder,height=38,corner_radius=10,fg_color=self.surface,border_width=0,text_color=self.text,font=ctk.CTkFont(family='Segoe UI',size=12)); self.path.grid(row=0,column=0,sticky='ew')
        self.browse=ctk.CTkButton(dest,text='Browse…',command=self.choose_folder,width=100,height=38,corner_radius=10,fg_color=self.subtle,hover_color=self.line,text_color=self.text,font=ctk.CTkFont(family='Segoe UI',size=12,weight='bold')); self.browse.grid(row=0,column=1,padx=(8,0))
        self.button=ctk.CTkButton(frame,text='●   Start recording',command=self.toggle,height=48,corner_radius=13,fg_color=self.accent,hover_color='#b64351',text_color='#ffffff',font=ctk.CTkFont(family='Segoe UI',size=14,weight='bold')); self.button.grid(row=11,column=0,sticky='ew')
        ctk.CTkLabel(frame,textvariable=self.status,text_color=self.muted,font=ctk.CTkFont(family='Segoe UI',size=11)).grid(row=12,column=0,sticky='w',pady=(8,0))
        self.controls=[self.q,self.res_box,self.fps_box,self.path,self.browse,self.refresh_button]+self.audio_checks
        self.refresh_screens(); self.apply_theme(); self.watch_theme(); root.protocol('WM_DELETE_WINDOW',self.close); self.poll()
    def label(self,parent,text):
        return ctk.CTkLabel(parent,text=text,text_color=self.text,font=ctk.CTkFont(family='Segoe UI',size=13,weight='bold'))
    def system_theme(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
                return 'Light' if winreg.QueryValueEx(key,'AppsUseLightTheme')[0] else 'Dark'
        except OSError: return 'Light'
    def apply_theme(self):
        mode=self.system_theme() if self.theme.get()=='System' else self.theme.get()
        if mode!=self.applied_theme: self.applied_theme=mode; ctk.set_appearance_mode(mode)
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
                image.thumbnail((165,85),Image.Resampling.LANCZOS)
                canvas=Image.new('RGB',(165,85),'#252a33'); canvas.paste(image,((165-image.width)//2,(85-image.height)//2)); photo=ctk.CTkImage(light_image=canvas,dark_image=canvas,size=(165,85))
            except Exception: photo=None
            self.preview_images.append(photo)
            card=ctk.CTkFrame(self.preview_frame,fg_color=self.surface,corner_radius=12,border_width=2,border_color=self.line,cursor='hand2'); card.grid(row=0,column=i,padx=(0,9),pady=(1,2))
            img=ctk.CTkLabel(card,image=photo,text='' if photo else 'Preview unavailable',width=165,height=85,fg_color=self.subtle,corner_radius=7,cursor='hand2'); img.grid(row=0,column=0,padx=7,pady=(7,0))
            desc=f"Screen {i+1}{'  ·  Primary' if s['primary'] else ''}"; label=ctk.CTkLabel(card,text=desc,text_color=self.text,font=ctk.CTkFont(family='Segoe UI',size=11,weight='bold'),anchor='w',cursor='hand2'); label.grid(row=1,column=0,sticky='w',padx=9,pady=(4,0))
            detail=ctk.CTkLabel(card,text=f"{s['w']} × {s['h']}",text_color=self.muted,font=ctk.CTkFont(family='Segoe UI',size=10),anchor='w',cursor='hand2'); detail.grid(row=2,column=0,sticky='w',padx=9,pady=(0,4))
            for widget in (card,img,label,detail): widget.bind('<Button-1>',lambda e,n=i:self.select_screen(n))
            self.cards.append(card)
        self.paint_cards()
    def select_screen(self,index):
        if not self.recording and not self.busy: self.selected_screen=index; self.paint_cards()
    def paint_cards(self):
        for i,card in enumerate(self.cards): card.configure(border_color=self.accent if i==self.selected_screen else self.line)
    def choose_folder(self):
        p=filedialog.askdirectory(initialdir=self.folder.get(),title='Choose where to save recordings')
        if p: self.folder.set(p)
    def set_controls(self, enabled):
        for c in self.controls: c.configure(state='normal' if enabled else 'disabled')
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
        cmd=[FFMPEG,'-hide_banner','-loglevel','error','-y','-f','gdigrab','-draw_mouse','1' if self.show_mouse.get() else '0','-framerate',str(fps),'-offset_x',str(s['x']),'-offset_y',str(s['y']),'-video_size',f"{s['w']}x{s['h']}",'-i','desktop','-an','-vf',vf,'-c:v','libx264','-preset','veryfast','-crf',str(crf),'-pix_fmt','yuv420p','-movflags','+faststart',str(self.video)]
        try:
            self.log=open(self.temp/'ffmpeg.log','w+',encoding='utf-8'); self.proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=self.log,creationflags=CREATE_NO_WINDOW)
            for name,device in devices:
                path=self.temp/f'{name}.wav'; self.audios.append(path)
                thread=threading.Thread(target=self.capture_audio,args=(device,path,name),daemon=True); thread.start(); self.threads.append(thread)
        except Exception as e:
            if self.proc and self.proc.poll() is None: self.proc.kill()
            self.stop_audio.set(); messagebox.showerror(APP,f'Could not start recording:\n{e}'); return
        self.recording=True; self.started=time.monotonic(); self.set_controls(False); self.button.configure(text='■  Stop recording'); self.root.after(500,self.tick)
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
    ctk.set_appearance_mode('Light'); root=ctk.CTk(); App(root); root.mainloop()
