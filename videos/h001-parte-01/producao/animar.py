"""Original layered pixel animation and score for Fio de Lume episode 001.

This renders a video from generated production assets; it does not regenerate
or alter the source illustrations. Speech is the approved Thalita recording.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import subprocess
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from scipy import ndimage, signal

EP = Path(__file__).resolve().parents[1]
REPO = EP.parents[1]
WORK = REPO / 'work' / EP.name
W, H, FPS, ART_FPS = 1280, 720, 24, 12
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'


def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sprite_boxes(path, grouped=False):
    """Find complete transparent sprites, including irregular sheet spacing."""
    im = Image.open(path).convert('RGBA')
    alpha = np.array(im.getchannel('A'))
    labels, _ = ndimage.label(alpha > 55, structure=np.ones((3, 3)))
    sizes = np.bincount(labels.ravel())
    boxes = []
    for label in np.flatnonzero(sizes[1:] > 1800) + 1:
        yy, xx = np.where(labels == label)
        boxes.append((int(xx.min()), int(yy.min()), int(xx.max())+1, int(yy.max())+1, int(len(xx))))
    if grouped:
        groups = {}
        for x0, y0, x1, y1, area in boxes:
            row = int((y0+y1)/2 >= im.height/2)
            col = min(3, int(((x0+x1)/2) / (im.width/4)))
            groups.setdefault(row*4+col, []).append((x0,y0,x1,y1))
        boxes = []
        for index in range(8):
            group = groups.get(index, [])
            if not group:
                raise ValueError(f'Asset cell missing: {path.name}, {index}')
            boxes.append((min(b[0] for b in group), min(b[1] for b in group), max(b[2] for b in group), max(b[3] for b in group), 0))
    else:
        boxes = sorted(boxes, key=lambda b: b[4], reverse=True)[:8]
        top = sorted([b for b in boxes if (b[1]+b[3])/2 < im.height/2], key=lambda b:b[0])
        bottom = sorted([b for b in boxes if (b[1]+b[3])/2 >= im.height/2], key=lambda b:b[0])
        if len(top) != 4 or len(bottom) != 4:
            raise ValueError(f'Expected four sprites per row: {path.name}')
        boxes = top + bottom
    return [tuple(max(0, v-3) if j<2 else min(im.size[j-2], v+3) for j,v in enumerate(b[:4])) for b in boxes]


class Assets:
    def __init__(self):
        self.bg = {}
        self.sprites = {}
        names = ['s01_lia','s02_joana','s03_elisa_crianca','s04_objetos','s05_lume','s06_investigacao']
        for name in names:
            file = EP/'assets'/f'{name}.png'
            im = Image.open(file).convert('RGBA')
            boxes = sprite_boxes(file, grouped=name in ('s04_objetos','s05_lume','s06_investigacao'))
            self.sprites[name] = [im.crop(box) for box in boxes]
        self.sized = {}

    def background(self, name, detail=False, flashback=False):
        key = name, detail, flashback
        if key not in self.bg:
            im = Image.open(EP/'assets'/f'{name}.png').convert('RGB')
            if detail:
                # A wooden surface from the scene, used behind the animated prop.
                im = im.crop((610, 700, 1450, 1070)).resize((W,H),Image.Resampling.LANCZOS)
                im = im.filter(ImageFilter.GaussianBlur(3))
                im = ImageEnhance.Brightness(im).enhance(.68)
            else:
                im = im.resize((W,H),Image.Resampling.LANCZOS)
            if flashback:
                im = ImageEnhance.Color(im).enhance(.83)
            self.bg[key] = im
        return self.bg[key].copy()

    def item(self, atlas, index, scale=None, width=None, flip=False):
        key = atlas,index,round(scale or 0,3),width,flip
        if key not in self.sized:
            im = self.sprites[atlas][index]
            factor = width/im.width if width else scale
            size = (max(1,round(im.width*factor)), max(1,round(im.height*factor)))
            im = im.resize(size,Image.Resampling.NEAREST)
            if flip: im = ImageOps.mirror(im)
            self.sized[key] = im
        return self.sized[key]


_ASSETS = None
def assets():
    global _ASSETS
    if _ASSETS is None: _ASSETS = Assets()
    return _ASSETS


def actor(name, pose=0, x=480, feet=650, height=400, flip=False, walk=False, to_x=None):
    return dict(name=name,pose=pose,x=x,feet=feet,height=height,flip=flip,walk=walk,to_x=to_x)


def recipe(bg, actors=None, prop=None, focus=None, zoom=1.02, **extra):
    return dict(bg=bg,actors=actors or [],prop=prop,focus=focus or [640,360],zoom=zoom,**extra)


def plan():
    """Cut the first serial chapter at its actual word-boundary timings."""
    word_file = WORK/'words.json'
    if not word_file.exists(): word_file = EP/'producao/palavras.json'
    words = json.loads(word_file.read_text())
    text = (EP/'narracao.txt').read_text().strip()
    paragraphs = text.split('\n\n')
    if len(words) != len(text.split()): raise ValueError('Word timing must match the narration.')
    narration_file = WORK/'narracao.json'
    if not narration_file.exists(): narration_file = EP/'narracao.json'
    narration = json.loads(narration_file.read_text())
    total = math.ceil((narration['duration_seconds']+3.2)*FPS)/FPS
    starts, offset = [0.], 0
    for paragraph in paragraphs[:-1]:
        offset += len(paragraph.split())
        starts.append(max(0,words[offset]['offset']/1e7-.12))
    starts.append(total)
    L = lambda pose=0,**kw: actor('lia',pose,**kw)
    J = lambda pose=0,**kw: actor('joana',pose,**({'x':950,'flip':True}|kw))
    E = lambda pose=0,**kw: actor('elisa',pose,**({'x':740}|kw))
    C = lambda pose=0,**kw: actor('child',pose,height=195,**kw)
    home='a01_casa_interior'; quay='a02_cais'; ext='a03_casa_exterior'; room='a04_sala_joana'; old='a05_quarto_1986'; porch='a06_varanda'
    detail=lambda kind,**kw: recipe(room,prop=kind,detail=True,**kw)
    scenes=[
      [detail('envelope',lume=True,zoom=1.08),recipe(home,[L(1,x=470)],focus=[475,365],zoom=1.7),detail('envelope',zoom=1.18)],
      [detail('case_closed'),recipe(old,[E(2,x=850),C(1,x=355,feet=595)],flashback=True,zoom=1.08),detail('ticket')],
      [detail('drawer'),recipe(home,[L(1,x=465)],focus=[470,355],zoom=1.8),detail('envelope')],
      [recipe(home,zoom=1.02),detail('contract'),detail('keys')],
      [detail('unfold_letter',zoom=1.06),detail('letter',date=True),recipe(home,[L(1,x=500)],focus=[510,360],zoom=1.85)],
      [recipe(quay,boat=True,zoom=1.02),recipe(quay,focus=[365,450],zoom=1.34),recipe(home,[L(2,x=550)],focus=[570,410],zoom=1.76)],
      [recipe(old,[E(2,x=850)],flashback=True,focus=[900,440],zoom=1.17),detail('case_open'),recipe(old,[C(1,x=330,feet=600)],flashback=True,zoom=1.14)],
      [recipe(home,[L(2,x=555)],focus=[560,390],zoom=1.92),recipe(home,focus=[220,305],zoom=1.26),recipe(home,[L(0,x=520)],zoom=1.12)],
      [detail('phone',vibrate=True),recipe(home,[L(0,x=520)],focus=[535,365],zoom=1.72),recipe(home,[L(2,x=540)],focus=[550,400],zoom=1.9)],
      [recipe(home,[L(3,x=730,feet=685)],focus=[840,440],zoom=1.12),detail('case_closed',zoom=1.14),detail('opening_case')],
      [detail('case_open'),detail('ticket',ticket_time=True),detail('letter_ticket')],
      [detail('phone',vibrate=True),detail('keys'),recipe(ext,[L(4,x=230,to_x=620,walk=True,height=330,feet=686)],zoom=1.04)],
      [recipe(ext,[L(4,x=620,to_x=900,walk=True,height=330,feet=686)],zoom=1.02),recipe(quay,[L(4,x=760,to_x=1000,walk=True,height=310,feet=635)],zoom=1.03),recipe(quay,focus=[1080,330],zoom=1.58)],
      [recipe(quay,[L(0,x=1040,height=330,feet=637)],zoom=1.03),recipe(quay,focus=[1090,300],zoom=1.73),detail('star_plaque')],
      [recipe(quay,[J(0,x=1050,height=330,feet=635,flip=True)],focus=[1050,380],zoom=1.22),recipe(room,[L(0,x=340),J(0,flip=True)],zoom=1.04),detail('envelope')],
      [recipe(room,[J(2,flip=True)],focus=[950,395],zoom=1.8),detail('unfold_letter'),recipe(room,[L(1,x=390)],focus=[410,365],zoom=1.83)],
      [recipe(room,[L(0,x=335),J(0,flip=True)],zoom=1.02),recipe(room,[L(1,x=400)],focus=[410,355],zoom=1.8),recipe(room,[J(0,flip=True)],focus=[940,350],zoom=1.94)],
      [recipe(room,[L(2,x=340),J(1,flip=True)],zoom=1.06),detail('ledger_closed'),detail('opening_ledger')],
      [recipe(room,[J(1,flip=True)],focus=[950,407],zoom=1.86),recipe(quay,boat=True,zoom=1.03),detail('ledger',turn_pages=True)],
      [detail('ledger',turn_pages=True),detail('ledger',ledger_entry=True,zoom=1.11),recipe(room,[L(2,x=400)],focus=[430,380],zoom=1.94)],
      [detail('ledger_closed',untie=True),detail('tickets',slide=True),detail('tickets',zoom=1.09)],
      [detail('tickets',ticket_name=True,zoom=1.16),recipe(room,[L(1,x=440)],focus=[460,355],zoom=2.08),detail('tickets',ticket_name=True)],
      [recipe(room,[L(2,x=335),J(1,flip=True)],zoom=1.06),recipe(quay,boat=True,boat_depart=True,zoom=1.03),recipe(room,[L(1,x=420)],focus=[430,365],zoom=1.88)],
      [recipe(room,[J(2,flip=True)],focus=[945,385],zoom=1.83),recipe(old,flashback=True,focus=[340,370],zoom=1.42),detail('tickets',ticket_name=True,closing=True,lume=True,zoom=1.06)]
    ]
    if len(scenes)!=len(paragraphs): raise ValueError('Paragraph count changed; revise the scene direction.')
    shots=[]
    for i, group in enumerate(scenes):
        first=round(starts[i]*FPS); last=round(starts[i+1]*FPS)
        edges=np.linspace(first,last,len(group)+1).round().astype(int)
        for j, spec in enumerate(group):
            spec.update(index=len(shots),paragraph=i+1,start_seconds=int(edges[j])/FPS,frames=int(edges[j+1]-edges[j]),duration_seconds=int(edges[j+1]-edges[j])/FPS)
            shots.append(spec)
    save_json(EP/'producao/plano_cenas.json',dict(duration_seconds=total,art_fps=ART_FPS,output_fps=FPS,shots=shots,paragraph_starts=starts))
    metadata=json.loads((EP/'metadata.json').read_text())
    metadata['chapters']=[{'start_seconds':round(starts[i],2),'title':name} for i,name in [(0,'Uma carta fora do tempo'),(3,'A casa e a despedida'),(6,'Uma lembrança incompleta'),(9,'A mala vazia'),(12,'O caminho até o cais'),(16,'A pergunta a Joana'),(19,'O caderno de viagens'),(21,'O nome no bilhete')]]
    save_json(EP/'metadata.json',metadata)
    save_json(EP/'storyboard.json',dict(status='defined',assembly_engine='producao/animar.py',duration_seconds=total,subtitle_mode='none',soundtrack='assets/trilha_ambientes.mp3',soundtrack_gain_db=-6,shots=[{'asset':f'assets/{s["bg"]}.png','kind':'image','duration_seconds':s['duration_seconds'],'pixel_art':True,'animation_recipe':s} for s in shots]))
    print(f'TIMELINE {len(shots)} shots, {total:.3f} seconds',flush=True)
    return shots,total


def place(canvas,item,cx,feet,angle=0,opacity=1):
    if angle: item=item.rotate(angle,Image.Resampling.BICUBIC,expand=True)
    if opacity<1:
        item=item.copy();item.putalpha(item.getchannel('A').point(lambda a:round(a*opacity)))
    canvas.paste(item,(round(cx-item.width/2),round(feet-item.height)),item)


def atmosphere(im,s,t):
    """Moving water is restricted to water, rain to the open window."""
    bg=s['bg']
    region={'a02_cais':(0,338,690,720),'a03_casa_exterior':(975,266,1280,422),'a04_sala_joana':(0,212,188,450),'a05_quarto_1986':(859,186,1270,366),'a01_casa_interior':(826,135,1270,357),'a06_varanda':(900,185,1280,427)}.get(bg)
    if region and not s.get('detail'):
        x0,y0,x1,y1=region
        for y in range(y0,y1,8):
            d=round(2*math.sin(t*1.5+y*.065))
            strip=im.crop((x0,y,x1,min(y+4,y1)))
            if d:strip=Image.fromarray(np.roll(np.asarray(strip),d,axis=1))
            im.paste(strip,(x0,y))
    layer=Image.new('RGBA',(W,H));draw=ImageDraw.Draw(layer)
    if bg in ('a01_casa_interior','a05_quarto_1986') and not s.get('detail'):
        for n in range(32):
            x=828+(n*67)%428;y=35+int((n*47+t*145)%308)
            draw.line((x,y,x-2,y+12),fill=(182,210,235,40),width=1)
    # A few dust motes, quietly lit, never a dense particle overlay.
    if bg in ('a04_sala_joana','a06_varanda') and not s.get('detail'):
        for n in range(9):
            x=830+(n*31)%375+int(math.sin(t*.25+n)*7)
            y=85+int((n*39-t*3)%330)
            draw.rectangle((x,y,x+1,y+1),fill=(246,215,152,48))
    return Image.alpha_composite(im.convert('RGBA'),layer)


def image_frame(s,t):
    A=assets();u=min(1,t/max(.1,s['duration_seconds']))
    im=A.background(s['bg'],s.get('detail',False),s.get('flashback',False))
    im=atmosphere(im,s,t+s['start_seconds'])
    actor_names={'lia':('s01_lia',0),'joana':('s02_joana',0),'elisa':('s03_elisa_crianca',0),'child':('s03_elisa_crianca',6)}
    for a in s['actors']:
        name,ref=actor_names[a['name']]
        index=a['pose']+(4 if a['name']=='child' else 0)
        if a['walk']:index=4+int(t*6)%4
        scale=a['height']/A.sprites[name][ref].height
        item=A.item(name,index,scale=scale,flip=a['flip'])
        x=a['x']+(a['to_x']-a['x'])*u if a['walk'] and a['to_x'] is not None else a['x']
        bob=(1.8*math.sin(t*math.pi*12) if a['walk'] else .8*math.sin(t*1.8))
        shadow=Image.new('RGBA',(W,H));d=ImageDraw.Draw(shadow)
        d.ellipse((x-item.width*.32,a['feet']-6,x+item.width*.32,a['feet']+5),fill=(10,7,16,75))
        im=Image.alpha_composite(im,shadow.filter(ImageFilter.GaussianBlur(4)))
        place(im,item,x,a['feet']+bob)
    if s.get('delivery'):
        envelope=A.item('s04_objetos',0,width=160)
        place(im,envelope,280+190*min(1,t/2),485-6*min(1,t/2),angle=-4)
    if s.get('boat'):
        ferry=A.item('s04_objetos',6,width=320)
        x=530-375*u if s.get('boat_depart') else 255+110*u
        place(im,ferry,x,493+2*math.sin(t*1.5),angle=.25*math.sin(t*.8))
    kind=s.get('prop')
    if kind:
        old={'envelope':0,'letter':1,'case_closed':2,'case_open':3,'opening_case':3,'ledger':4,'opening_ledger':4,'tickets':5}
        new={'phone':0,'contract':1,'keys':2,'drawer':3,'ticket':4,'star_plaque':5,'ledger_closed':6,'unfold_letter':7}
        width=650 if kind.startswith('case') or kind=='opening_case' else (540 if 'ledger' in kind else 510)
        if kind in ('phone','keys'):width=340
        y=580+1.4*math.sin(t*.6)
        if kind in ('letter_contract','letter_ticket'):
            left=A.item('s04_objetos',1,width=310)
            right=A.item('s06_investigacao',1 if kind=='letter_contract' else 4,width=350)
            place(im,left,475,570,angle=-3)
            place(im,right,810,540,angle=2)
        else:
            atlas='s04_objetos' if kind in old else 's06_investigacao'
            index=old[kind] if kind in old else new[kind]
            item=A.item('s04_objetos',1,width=width) if kind=='unfold_letter' else A.item(atlas,index,width=width)
            cx=640
            angle=.15*math.sin(t*.6)
            if s.get('vibrate') and t<1.2:cx+=2*math.sin(t*35)
            if s.get('slide'):cx=640+200*(1-min(1,t/1.6))
            if kind in ('opening_case','opening_ledger','unfold_letter'):
                closed=A.item('s04_objetos' if kind!='opening_ledger' else 's06_investigacao',2 if kind=='opening_case' else (6 if kind=='opening_ledger' else 0),width=width)
                opening=min(1,t/1.2)
                if opening<1:place(im,closed,cx,y,opacity=1-opening)
                # Folding plane opens progressively rather than holding one still pose.
                reveal=item.resize((max(1,round(item.width*(.4+.6*opening))),item.height),Image.Resampling.NEAREST)
                place(im,reveal,cx,y,opacity=opening)
            else:
                place(im,item,cx,y,angle=angle)
            if s.get('turn_pages'):
                phase=(t%3)/3
                if phase<.42:
                    page=Image.new('RGBA',(240,310),(237,216,180,205))
                    page=page.resize((max(1,round(240*abs(math.cos(phase/.42*math.pi)))),310),Image.Resampling.NEAREST)
                    place(im,page,637,535,opacity=.44*math.sin(phase/.42*math.pi))
        d=ImageDraw.Draw(im)
        if s.get('date'):
            d.text((500,510),'MARÇO DE 1986',font=ImageFont.truetype(FONT,23),fill=(101,63,35,255))
        if s.get('ticket_time'):
            d.text((445,454),'5h · PRIMEIRA BARCA',font=ImageFont.truetype(FONT,22),fill=(101,63,35,255))
        if s.get('ledger_entry'):
            d.rounded_rectangle((414,367,655,432),radius=3,fill=(229,206,165,255))
            d.text((426,378),'Elisa',font=ImageFont.truetype(FONT,23),fill=(101,63,35,255))
            d.text((426,405),'2 passagens',font=ImageFont.truetype(FONT,20),fill=(101,63,35,255))
        if s.get('ticket_name'):
            # Writing belongs to a story prop; never a transcript of the voice.
            d.text((674,478),'Lia',font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf',21),fill=(101,63,35,255))
            d.text((674,502),'Ferreira',font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf',16),fill=(101,63,35,255))
    if s.get('lume'):
        item=A.item('s05_lume',int(t*10)%8,width=75)
        x=90+25*math.sin(t*.6);y=137+8*math.sin(t*1.7)
        opacity=min(1,t/.7,max(0,(s['duration_seconds']-t)/.7))
        place(im,item,x,y,opacity=opacity)
    # Independent foreground and subject layers create actual scene movement.
    im=im.convert('RGB')
    z=s['zoom']+(0.028*u if s['index']%2==0 else .028*(1-u))
    cw,ch=W/z,H/z;cx,cy=s['focus']
    cx=max(cw/2,min(W-cw/2,cx));cy=max(ch/2,min(H-ch/2,cy))
    im=im.crop((round(cx-cw/2),round(cy-ch/2),round(cx+cw/2),round(cy+ch/2))).resize((W,H),Image.Resampling.LANCZOS)
    draw=ImageDraw.Draw(im)
    draw.rectangle((12,12,W-13,H-13),outline=(217,163,75),width=2)
    if s.get('closing') and t>s['duration_seconds']-3.1:
        # Only the serial signature appears once the narrated scene has concluded.
        overlay=Image.new('RGBA',(W,H),(18,23,45,220))
        im=Image.alpha_composite(im.convert('RGBA'),overlay).convert('RGB')
        d=ImageDraw.Draw(im)
        for value,y,size in [('Fio de Lume',225,46),('PARTE 1 DE 4',310,26),('Continua na parte 2',365,32),('A madrugada esquecida',414,25)]:
            font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf',size)
            box=d.textbbox((0,0),value,font=font)
            d.text(((W-(box[2]-box[0]))/2,y),value,font=font,fill=(243,230,204))
        d.rectangle((12,12,W-13,H-13),outline=(217,163,75),width=2)
    if s['index']==0 and t<.45:im=Image.blend(Image.new('RGB',(W,H)),im,min(1,t/.45))
    if s.get('closing') and t>s['duration_seconds']-1:
        im=Image.blend(im,Image.new('RGB',(W,H)),min(1,(t-(s['duration_seconds']-1))))
    return im


def render_one(s):
    folder=WORK/'animacao';folder.mkdir(parents=True,exist_ok=True)
    file=folder/f'cena-{s["index"]:03d}.mp4';stamp=file.with_suffix('.sha256')
    signature=hashlib.sha256((json.dumps(s,sort_keys=True)+Path(__file__).read_text()).encode()).hexdigest()
    if file.exists() and file.stat().st_size>1000 and stamp.exists() and stamp.read_text()==signature:return file
    partial=file.with_name(file.stem+'.partial.mp4')
    command=['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pixel_format','rgb24','-video_size',f'{W}x{H}','-framerate',str(ART_FPS),'-i','pipe:0','-vf','fps=24,scale=1920:1080:flags=lanczos,setsar=1','-frames:v',str(s['frames']),'-an','-c:v','libx264','-preset','veryfast','-crf','23','-threads','2','-pix_fmt','yuv420p','-movflags','+faststart',str(partial)]
    with file.with_suffix('.log').open('w') as log:
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=log,stderr=log)
        try:
            for f in range(math.ceil(s['frames']/2)):
                process.stdin.write(image_frame(s,f/ART_FPS).tobytes())
            process.stdin.close()
            if process.wait():raise RuntimeError(f'Render failed: {file.name}')
            actual=int(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=nb_frames','-of','default=noprint_wrappers=1:nokey=1',str(partial)],text=True))
            if actual!=s['frames']:raise ValueError(f'Clip frame count differs: {file.name}')
            partial.replace(file)
        except Exception:
            if process.poll() is None:process.kill()
            partial.unlink(missing_ok=True);raise
    stamp.write_text(signature)
    print(f'ANIMATED {s["index"]+1:02d}: {s["duration_seconds"]:.2f}s',flush=True)
    return file


def make_score(shots,total):
    """Original restrained pad/plucked motif, river/rain and timed prop sounds."""
    sr=24000;audio=np.zeros((round(total*sr),2),np.float32)
    # Evolving harmony: suspense in minor; a warm consonant resolution.
    chords=[(130.813,155.563,195.998),(103.826,130.813,155.563),(87.307,103.826,130.813),(97.999,123.471,146.832)]
    reveal=next(s['start_seconds'] for s in shots if s.get('ticket_name'))
    for bar in range(math.ceil(total/12)):
        begin=bar*12;length=min(14,total-begin)
        if length<=0:continue
        n=round(length*sr);t=np.arange(n)/sr
        chord=(130.813,164.814,195.998) if begin>reveal else chords[(bar//2)%4]
        env=np.minimum(1,t/2.6)*np.minimum(1,(length-t)/3.8)
        section=.48 if begin<reveal else .58
        if reveal-8<begin<reveal+12:section=.13
        if begin>total-28:section=.24
        for k,freq in enumerate(chord):
            pad=(np.sin(2*np.pi*freq*t)+.2*np.sin(2*np.pi*freq*2*t)+.06*np.sin(2*np.pi*freq*3*t))*.04*env*section
            offset=round(begin*sr);end=offset+n
            audio[offset:end,0]+=pad*(.7+.1*k);audio[offset:end,1]+=pad*(.95-.1*k)
        for k in range(4):
            start=begin+2+k*2.4
            if start+3>total:continue
            tt=np.arange(sr*3)/sr;freq=chord[k%3]*2
            bell=(np.sin(2*np.pi*freq*tt)+.22*np.sin(2*np.pi*freq*2.003*tt))*np.exp(-tt*2.2)*np.minimum(1,tt/.006)*.025*section
            pos=round(start*sr);audio[pos:pos+len(bell),0]+=bell;audio[pos:pos+len(bell),1]+=bell*.85
    rng=np.random.default_rng(611)
    for s in shots:
        start=round(s['start_seconds']*sr);n=round(s['duration_seconds']*sr);n=min(n,len(audio)-start)
        t=np.arange(n)/sr;fade=np.minimum(1,t/.35)*np.minimum(1,(n/sr-t)/.4)
        if s['bg'] in ('a02_cais','a03_casa_exterior','a06_varanda') and not s.get('detail'):
            noise=rng.standard_normal(n).astype(np.float32)
            water=signal.sosfilt(signal.butter(2,[130,1500],btype='band',fs=sr,output='sos'),noise)*.015*fade*(.75+.25*np.sin(t*.8))
            audio[start:start+n,0]+=water;audio[start:start+n,1]+=np.roll(water,40)
        if s['bg']=='a05_quarto_1986' and not s.get('detail'):
            noise=rng.standard_normal(n).astype(np.float32)
            rain=signal.sosfilt(signal.butter(2,[700,4000],btype='band',fs=sr,output='sos'),noise)*.012*fade
            audio[start:start+n]+=rain[:,None]
        if s.get('prop') in ('opening_case','opening_ledger','unfold_letter','tickets'):
            length=int(sr*.28);tt=np.arange(length)/sr
            rustle=signal.sosfilt(signal.butter(2,[500,5000],btype='band',fs=sr,output='sos'),rng.standard_normal(length))*np.exp(-tt*13)*.035
            pos=min(len(audio)-length,start+sr//2);audio[pos:pos+length]+=rustle[:,None]
        if s.get('prop')=='opening_case':
            for delay in [.16,.38]:
                tt=np.arange(int(sr*.15))/sr
                latch=(np.sin(2*np.pi*1550*tt)+.4*np.sin(2*np.pi*2130*tt))*np.exp(-tt*40)*.032
                pos=start+round(sr*delay);audio[pos:pos+len(latch)]+=latch[:,None]
        if s.get('vibrate'):
            tt=np.arange(int(sr*.38))/sr
            buzz=np.sin(2*np.pi*115*tt)*np.sin(np.pi*tt/.38)**2*.028
            pos=start+int(sr*.16);audio[pos:pos+len(buzz)]+=buzz[:,None]
        if any(a.get('walk') for a in s.get('actors',[])):
            for delay in np.arange(.2,s['duration_seconds']-.15,.48):
                tt=np.arange(int(sr*.12))/sr
                step=np.sin(2*np.pi*82*tt)*np.exp(-tt*30)*.025
                pos=start+round(sr*delay);audio[pos:pos+len(step),0]+=step;audio[pos:pos+len(step),1]+=step*.78
    fade=np.minimum(1,np.arange(len(audio))/(sr*1.5))*np.minimum(1,(len(audio)-np.arange(len(audio)))/(sr*2))
    audio*=fade[:,None]
    pcm=np.clip(audio,-.9,.9)
    file=WORK/'trilha_original.wav'
    with wave.open(str(file),'wb') as out:
        out.setnchannels(2);out.setsampwidth(2);out.setframerate(sr);out.writeframes((pcm*32767).astype('<i2').tobytes())
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(file),'-c:a','libmp3lame','-b:a','96k',str(EP/'assets/trilha_ambientes.mp3')],check=True)
    print('Original score and ambience ready.',flush=True)


def finish(shots,total):
    concat=WORK/'animacao/concat.txt'
    concat.write_text(''.join(f"file 'cena-{s['index']:03d}.mp4'\n" for s in shots))
    silent=WORK/'animacao/silent.mp4'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-xerror','-y','-f','concat','-safe','1','-i',str(concat),'-c','copy',str(silent)],check=True)
    expected=sum(s['frames'] for s in shots)
    actual=int(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=nb_frames','-of','default=noprint_wrappers=1:nokey=1',str(silent)],text=True))
    if actual!=expected:
        raise ValueError(f'Incomplete visual timeline: {actual} frames, expected {expected}.')
    make_score(shots,total)
    filters='[1:a]loudnorm=I=-16:TP=-1.5:LRA=9,apad,asplit=2[voice][control];[2:a]volume=-6dB[bed];[bed][control]sidechaincompress=threshold=0.025:ratio=5:attack=15:release=300[ducked];[voice][ducked]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.89:level=false[mixed]'
    voice_file=WORK/'narracao.mp3'
    if not voice_file.exists(): voice_file=EP/'narracao.mp3'
    with (WORK/'mixagem.log').open('w') as log:
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(silent),'-i',str(voice_file),'-i',str(EP/'assets/trilha_ambientes.mp3'),'-filter_complex',filters,'-map','0:v:0','-map','[mixed]','-t',str(total),'-c:v','copy','-c:a','aac','-b:a','128k','-ar','48000','-ac','2','-sn','-map_metadata','-1','-movflags','+faststart',str(EP/'video.mp4')],check=True,stdout=log,stderr=log)
    import shutil
    for name in ('narracao.mp3','narracao.json','legendas.srt'):
        if (WORK/name).exists():shutil.copyfile(WORK/name,EP/name)
    if (WORK/'words.json').exists():shutil.copyfile(WORK/'words.json',EP/'producao/palavras.json')
    meta=json.loads((EP/'metadata.json').read_text());meta['status']='produced';save_json(EP/'metadata.json',meta)
    print(f'VIDEO READY: {total:.3f}s, {(EP/"video.mp4").stat().st_size} bytes',flush=True)


def preview(shots):
    folder=WORK/'previas';folder.mkdir(parents=True,exist_ok=True)
    for s in shots:
        image_frame(s,s['duration_seconds']*.47).save(folder/f'{s["index"]:03d}.jpg',quality=91)
    for page in range(math.ceil(len(shots)/8)):
        sheet=Image.new('RGB',(1600,900),'#12172D')
        d=ImageDraw.Draw(sheet);font=ImageFont.truetype(FONT,15)
        for j,s in enumerate(shots[page*8:page*8+8]):
            image=Image.open(folder/f'{s["index"]:03d}.jpg').resize((400,225))
            x=(j%4)*400;y=(j//4)*450+90
            sheet.paste(image,(x,y));d.text((x+12,y+232),f"{s['index']+1:02d} · {s['start_seconds']:.1f}s · bloco {s['paragraph']}",font=font,fill='#F3E6CC')
        sheet.save(folder/f'pagina-{page+1:02d}.jpg',quality=92)
    print(f'PREVIEWS {len(shots)} shots',flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['plan','preview','render','finish']);p.add_argument('--workers',type=int,default=3)
    args=p.parse_args();WORK.mkdir(parents=True,exist_ok=True)
    if args.stage=='plan':plan();return
    data=json.loads((EP/'producao/plano_cenas.json').read_text());shots,total=data['shots'],data['duration_seconds']
    if args.stage=='preview':preview(shots)
    elif args.stage=='render':
        with ProcessPoolExecutor(max_workers=args.workers) as pool:list(pool.map(render_one,shots))
    elif args.stage=='finish':finish(shots,total)

if __name__=='__main__':main()
