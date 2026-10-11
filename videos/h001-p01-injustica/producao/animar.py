"""Render the complete contemporary pixel-art chapter from layered assets.

Generated atlases remain unchanged. Sprites, set layers, props and original
sound are composited at 12 animation frames/s into a 24 fps Full HD movie.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import difflib
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
from scipy import ndimage, signal

EP = Path(__file__).resolve().parents[1]
ROOT = EP.parents[1]
WORK = ROOT / 'work' / EP.name
W, H, FPS, ART_FPS = 960, 540, 24, 12
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
GOLD, INK, CREAM = '#D9A34B', '#12172D', '#F3E6CC'


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def font(size):
    return ImageFont.truetype(FONT, size)


def sprites_from_grid(path, columns, rows):
    sheet = Image.open(path).convert('RGBA')
    alpha = np.asarray(sheet.getchannel('A'))
    labels, count = ndimage.label(alpha > 65, structure=np.ones((3, 3)))
    groups = {i: [] for i in range(columns * rows)}
    for component, box in enumerate(ndimage.find_objects(labels), 1):
        if box is None or np.count_nonzero(labels[box] == component) < 450:
            continue
        yy, xx = box
        x0, y0, x1, y1 = xx.start, yy.start, xx.stop, yy.stop
        col = min(columns - 1, int((x0 + x1) / 2 / (sheet.width / columns)))
        row = min(rows - 1, int((y0 + y1) / 2 / (sheet.height / rows)))
        groups[row * columns + col].append((x0, y0, x1, y1))
    result = []
    for index, boxes in groups.items():
        if not boxes:
            raise ValueError(f'Missing sprite cell {path.name}:{index}')
        box = (min(b[0] for b in boxes), min(b[1] for b in boxes),
               max(b[2] for b in boxes), max(b[3] for b in boxes))
        result.append(sheet.crop(box))
    return result


class Assets:
    def __init__(self):
        self.sprites = {}
        self.sprites['work'] = sprites_from_grid(EP/'assets/personagens-trabalho.png', 6, 2)
        self.sprites['home'] = sprites_from_grid(EP/'assets/personagens-casa.png', 4, 2)
        self.sprites['lume'] = sprites_from_grid(EP/'assets/lume.png', 4, 2)
        self.backgrounds = {}
        for filename, names in [('cenarios-trabalho.png', ['office','warehouse','street','loading']),
                                ('cenarios-casa.png', ['dining','desk','laundry','purchasing'])]:
            sheet = Image.open(EP/'assets'/filename).convert('RGB')
            for index, name in enumerate(names):
                col, row = index % 2, index // 2
                box = (round(col*sheet.width/2)+2, round(row*sheet.height/2)+2,
                       round((col+1)*sheet.width/2)-2, round((row+1)*sheet.height/2)-2)
                panel = sheet.crop(box).resize((480,270),Image.Resampling.NEAREST)
                self.backgrounds[name] = panel.resize((W,H),Image.Resampling.NEAREST).convert('RGBA')
        self.sized = {}

    def sprite(self, atlas, index, height, flip=False):
        key = atlas,index,round(height),flip
        if key not in self.sized:
            source = self.sprites[atlas][index]
            logical_h = 100 if atlas != 'lume' else 50
            logical_w = max(1, round(source.width * logical_h/source.height))
            source = source.resize((logical_w,logical_h), Image.Resampling.NEAREST)
            size = (max(1,round(source.width*height/source.height)),round(height))
            source = source.resize(size, Image.Resampling.NEAREST)
            if flip: source = ImageOps.mirror(source)
            self.sized[key] = source
        return self.sized[key]


_ASSETS = None
def assets():
    global _ASSETS
    if _ASSETS is None: _ASSETS = Assets()
    return _ASSETS


def actor(name, x=380, feet=500, height=310, pose=0, **kw):
    return dict(name=name,x=x,feet=feet,height=height,pose=pose,**kw)


def scene(bg, actors=(), prop=None, focus=(480,270), zoom=1.0, **kw):
    return dict(bg=bg,actors=list(actors),prop=prop,focus=focus,zoom=zoom,**kw)


def recipe(index):
    D=lambda **kw:actor('daniel',**kw)
    M=lambda **kw:actor('mauro',**({'x':700}|kw))
    V=lambda **kw:actor('vitor',**({'x':790}|kw))
    J=lambda **kw:actor('julia',**({'x':515}|kw))
    L=lambda **kw:actor('lara',**({'x':780}|kw))
    N=lambda **kw:actor('nina',**({'x':610,'height':235}|kw))
    close=lambda bg,a,**kw:scene(bg,[a],focus=(a['x'],a['feet']-a['height']*.68),zoom=1.85,**kw)
    office=lambda **kw:scene('office',[D(x=340),M(x=695)],**kw)
    meeting=lambda **kw:scene('warehouse',[D(x=235),J(x=435,height=270,feet=473),M(x=650),V(x=830,height=290)],**kw)
    family=lambda **kw:scene('dining',[D(x=380,pose=4,height=295,feet=510),N(x=620,pose=0,height=255,feet=443),L(x=825,pose=1,height=325,feet=510)],table=True,**kw)
    detail=lambda kind,bg='office',**kw:scene(bg,prop=kind,detail=True,**kw)
    recipes={
      0:detail('confession',action='slide',lume=True),
      1:detail('confession',action='pen'),
      2:detail('confession',action='amount'),
      3:close('office',D(x=360,pose=1),gesture=True),
      4:scene('office',[M(x=730)],door='close'),
      5:close('office',M(x=690)),
      6:close('office',D(x=380)),
      7:scene('loading',[D(x=240,height=290,feet=485,walk=True,to_x=550)],truck=True,boxes=True),
      8:scene('warehouse',[D(x=340,pose=3)],clock=True),
      9:office(),
      10:scene('office',[D(x=300),M(x=735)],focus=(700,255),zoom=1.25),
      11:close('office',D(x=360,pose=1),gesture=True),
      12:detail('confession',action='withdraw'),
      13:close('office',M(x=700,pose=1)),
      14:meeting(crowd=True),
      15:scene('warehouse',[D(x=330),V(x=700)],prop='small-report',flashback=True),
      16:detail('report',action='withdraw'),
      17:close('warehouse',D(x=350,pose=1)),
      18:close('warehouse',V(x=700)),
      19:close('warehouse',D(x=350,pose=1),gesture=True),
      20:scene('warehouse',[D(x=240),V(x=800)],zoom=1.02),
      21:detail('report',bg='warehouse'),
      22:close('warehouse',M(x=660,pose=1),gesture=True),
      23:scene('warehouse',[D(x=220,to_x=310),M(x=670)],approach=True),
      24:detail('report',bg='warehouse',action='dates'),
      25:scene('warehouse',[V(x=750,pose=1,height=290)],tv=True,focus=(780,220),zoom=1.18),
      26:scene('loading',[D(x=220,height=260,feet=472,walk=True,to_x=555)],truck=True,boxes=True,cctv=True),
      27:close('warehouse',D(x=360,pose=1),gesture=True),
      28:close('warehouse',M(x=690,pose=1)),
      29:scene('warehouse',[D(x=250),J(x=580)],focus=(565,235),zoom=1.45),
      30:close('warehouse',J(x=555),look_down=True),
      31:meeting(quiet=True),
      32:close('warehouse',D(x=350,pose=1),gesture=True),
      33:scene('warehouse',[M(x=695,pose=1),D(x=320)]),
      34:detail('badge',action='remove'),
      35:scene('warehouse',[J(x=420,height=285),V(x=760)],zoom=1.03),
      36:scene('warehouse',[D(x=380,walk=True,to_x=630)],zoom=1.04),
      37:detail('bag',action='meal'),
      38:scene('office',[D(x=370,walk=True,to_x=745),M(x=255)],door='open'),
      39:close('office',M(x=690)),
      40:detail('phone',bg='street',phone='viral',vibrate=True),
      41:detail('phone',bg='street',phone='typing',vibrate=True),
      42:scene('street',[D(x=275,pose=3,height=300,feet=460)]),
      43:close('street',D(x=310,pose=3)),
      44:close('dining',L(x=740),call=True),
      45:close('street',D(x=310,pose=3)),
      46:close('dining',L(x=740)),
      47:close('dining',L(x=740),call=True),
      48:scene('street',[D(x=280,height=285,feet=465,walk=True,to_x=590)],bus=True),
      49:family(),
      50:family(focus=(380,295),zoom=1.58),
      51:family(focus=(620,312),zoom=1.65),
      52:family(focus=(380,300),zoom=1.75),
      53:family(focus=(380,290),zoom=1.7),
      54:detail('bills',bg='dining',action='spread'),
      55:family(focus=(825,285),zoom=1.55),
      56:scene('dining',[D(x=390,pose=4,height=295,feet=510),L(x=820,to_x=775,pose=1,height=325,feet=510)],table=True,approach=True),
      57:family(focus=(825,290),zoom=1.7),
      58:family(),
      59:scene('desk',[D(x=387,pose=4,flip=True,height=240,feet=443)],monitor='cv',computer=True),
      60:detail('phone',bg='desk',phone='denied'),
      61:scene('desk',[D(x=387,pose=4,flip=True,height=240,feet=443)],monitor='files',computer=True),
      62:close('desk',D(x=400,pose=4,flip=True,height=260,feet=465)),
      63:detail('compare',bg='desk',action='highlight'),
      64:scene('desk',[D(x=580,pose=5,feet=505)],monitor='files',vibrate=False),
      65:detail('phone',bg='dining',phone='julia',vibrate=True,lume=True),
      66:detail('phone',bg='dining',phone='julia'),
      67:scene('laundry',[D(x=680,pose=5,to_x=520)],approach=True),
      68:close('laundry',D(x=540,pose=5)),
      69:close('purchasing',J(x=520,pose=1)),
      70:close('laundry',D(x=540,pose=5)),
      71:close('purchasing',J(x=520,pose=1)),
      72:scene('purchasing',[J(x=520,pose=1)],focus=(515,245),zoom=1.6),
      73:detail('phone',bg='laundry',phone='shipment',vibrate=True),
      74:detail('phone',bg='laundry',phone='shipment',action='highlight'),
      75:close('laundry',D(x=540,pose=5)),
      76:scene('loading',truck=True,depart=True,night=True),
      77:scene('laundry',focus=(305,405),zoom=1.75),
      78:detail('badge',bg='office',action='blocked'),
      79:detail('phone',bg='laundry',phone='shipment',action='highlight'),
      80:close('laundry',D(x=540,pose=5)),
      81:scene('purchasing',[J(x=465,pose=1),V(x=865,to_x=725,feet=503,height=305)],door='open',enter=True),
      82:scene('purchasing',[J(x=450,pose=1),V(x=740)],focus=(730,235),zoom=1.4,door='ajar'),
      83:scene('purchasing',[J(x=440,pose=1),V(x=730)],focus=(650,245),zoom=1.5,door='ajar'),
    }
    return recipes[index]


def plan():
    paragraphs=(EP/'narracao.txt').read_text().strip().split('\n\n')
    words=json.loads((WORK/'words.json').read_text())
    normalize=lambda token:re.sub(r'\W','',token).casefold()
    tokens=[];paragraph_tokens=[]
    for paragraph in paragraphs:
        paragraph_tokens.append(len(tokens))
        tokens.extend(n for token in paragraph.split() if (n:=normalize(token)))
    actual=[normalize(w['text']) for w in words]
    if tokens != actual:
        raise ValueError('Speech word boundaries must exactly match spoken tokens; punctuation-only dashes are excluded.')
    narration=json.loads((WORK/'narracao.json').read_text())
    speech_end=narration['duration_seconds']
    starts=[round(max(0,words[offset]['offset']/1e7-.1)*FPS)/FPS for offset in paragraph_tokens]
    starts[0]=0
    starts.append(math.ceil(speech_end*FPS)/FPS)
    shots=[]
    for i,paragraph in enumerate(paragraphs):
        start,end=starts[i],starts[i+1]
        n=max(1,math.ceil((end-start)/12.5))
        for cut in range(n):
            first=round((start+(end-start)*cut/n)*FPS)
            last=round((start+(end-start)*(cut+1)/n)*FPS)
            s=recipe(i)
            if cut:
                if s['actors'] and not s.get('detail'):
                    a=s['actors'][cut%len(s['actors'])]
                    s['focus']=(a['x'],a['feet']-a['height']*.68)
                    s['zoom']=1.65
                elif s.get('prop'):s['zoom']=1.13
            s.update(index=len(shots),paragraph=i,narration=paragraph,
                     start_seconds=first/FPS,duration_seconds=(last-first)/FPS,frames=last-first)
            shots.append(s)
    first=round(starts[-1]*FPS)
    ending=scene('purchasing',closing=True,lume=True)
    ending.update(index=len(shots),paragraph=84,narration='',start_seconds=first/FPS,
                  duration_seconds=3.2,frames=77)
    ending['duration_seconds']=ending['frames']/FPS
    shots.append(ending)
    total=sum(s['frames'] for s in shots)/FPS
    for previous,current in zip(shots,shots[1:]):
        if abs(previous['start_seconds']+previous['duration_seconds']-current['start_seconds'])>.002:
            raise ValueError('Non-contiguous timeline')
    data=dict(duration_seconds=total,speech_duration_seconds=speech_end,art_fps=ART_FPS,
              output_fps=FPS,paragraph_starts=starts,shots=shots)
    save_json(EP/'producao/plano_cenas.json',data)
    metadata=json.loads((EP/'metadata.json').read_text())
    metadata['chapters']=[{'start_seconds':starts[i],'title':title} for i,title in [
        (0,'A confissão que ele recusou'),(14,'Acusado diante de todos'),
        (37,'Do lado de fora'),(49,'A pergunta da filha'),
        (59,'Os primeiros registros'),(65,'A ligação de Júlia')]]
    save_json(EP/'metadata.json',metadata)
    save_json(EP/'storyboard.json',dict(status='defined',assembly_engine='producao/animar.py',
        duration_seconds=total,subtitle_mode='none',animation_fps=ART_FPS,
        shots=[{'kind':'layered_animation','duration_seconds':s['duration_seconds'],
                'pixel_art':True,'animation_recipe':s} for s in shots]))
    print(f'TIMELINE {len(shots)} animated shots, {total:.3f} seconds',flush=True)


def place(canvas, item, x, feet, opacity=1):
    if opacity < 1:
        item=item.copy()
        item.putalpha(item.getchannel('A').point(lambda value:round(value*opacity)))
    canvas.alpha_composite(item,(round(x-item.width/2),round(feet-item.height)))


def background(s,t):
    image=assets().backgrounds[s['bg']].copy()
    if s.get('detail'):
        shade=Image.new('RGBA',(W,H),(10,14,27,150))
        image=Image.alpha_composite(image,shade)
        # The animated prop occupies a close view in front of its actual set.
    if s.get('night'):
        image=Image.alpha_composite(image,Image.new('RGBA',(W,H),(13,27,65,155)))
    draw=ImageDraw.Draw(image)
    if s['bg'] in ('warehouse','loading','office','purchasing') and not s.get('detail'):
        for k in range(5):
            x=215+k*157;y=35+(k%2)*20
            if s['bg']=='office':y=75
            draw.rectangle((x,y,x+11,y+2),fill=(145,205,228,80+round(15*math.sin(t*.9+k))))
    if s['bg'] in ('street','loading') and not s.get('detail'):
        for k in range(6):
            x=150+k*90+round(3*math.sin(t*.65+k));y=34+(k*37)%90
            draw.rectangle((x,y,x+2,y+1),fill=(231,236,204,55))
    if s['bg'] in ('desk','dining','laundry') and not s.get('detail'):
        # Window lights, lamp shimmer and the hanging towel are separate motions.
        for k in range(4):
            x=712+(k*21)%115;y=125+(k*17)%45
            if s['bg']=='desk':x-=65
            draw.rectangle((x,y,x+3,y+3),fill=(245,198,107,90+round(35*math.sin(t*.38+k))))
        if s['bg']=='laundry':
            region=(365,190,438,302)
            strip=image.crop(region)
            image.alpha_composite(strip,(region[0]+round(math.sin(t*.8)),region[1]))
    return image


def draw_actor(canvas,a,s,t):
    A=assets();name=a['name'];pose=a['pose'];u=t/max(.1,s['duration_seconds'])
    x=a['x']
    if a.get('to_x') is not None:
        move=min(1,t/(1.8 if s.get('approach') else max(1,s['duration_seconds'])))
        x+=(a['to_x']-x)*move
    if name=='daniel':
        if a.get('walk'):
            atlas,index='home',int(t*5)%4
        elif pose in (4,5):atlas,index='home',pose
        else:atlas,index='work',[0,1,6,7][pose]
    elif name=='mauro':atlas,index='work',2+(6 if pose else 0)
    elif name=='vitor':atlas,index='work',3+(6 if pose else 0)
    elif name=='julia':atlas,index='work',4+(6 if pose else 0)
    elif name=='lara':atlas,index='work',5+(6 if pose else 0)
    elif name=='nina':atlas,index='home',6+pose
    else:raise ValueError(name)
    item=A.sprite(atlas,index,a['height'],a.get('flip',False))
    if s.get('enter') and name=='vitor' and t<2.8:
        # Animate the legs on a separate plane as he comes through the doorway.
        split=round(item.height*.61);legs=item.crop((0,split,item.width,item.height))
        moving=Image.new('RGBA',item.size)
        moving.alpha_composite(item.crop((0,0,item.width,split)),(0,0))
        for row in range(0,legs.height,3):
            shift=round(math.sin(t*10)*4*row/max(1,legs.height))
            moving.alpha_composite(legs.crop((0,row,legs.width,min(row+3,legs.height))),(shift,split+row))
        item=moving
    bob=round(1.5*math.sin(t*math.pi*10)) if a.get('walk') else round(.75*math.sin(t*1.7+index))
    feet=a['feet']+bob
    d=ImageDraw.Draw(canvas)
    seated=(name=='daniel' and pose==4) or (name=='lara' and pose==1) or (name=='nina' and pose==0)
    if s.get('table') and seated:
        cx=x+item.width*(.1 if name in ('lara','nina') else -.1)
        seat=round(feet-item.height*.43);bottom=490 if name=='nina' else 516
        side=1 if name in ('lara','nina') else -1
        d.rectangle((cx-38,seat,cx+38,seat+11),fill='#64513C',outline='#302B27',width=2)
        for xx in (cx-34,cx+27):d.rectangle((xx,seat+8,xx+7,bottom),fill='#493A2E')
        xx=cx+side*36
        d.rectangle((xx-5,seat-94,xx+5,seat+8),fill='#66533E')
    if not seated:d.ellipse((x-item.width*.30,feet-3,x+item.width*.30,feet+4),fill=(6,12,20,65))
    if s.get('gesture') and t<.55 and name in ('daniel','mauro'):
        previous=A.sprite('work',0 if name=='daniel' else 2,a['height'],a.get('flip',False))
        place(canvas,previous,x,feet,opacity=1-min(1,t/.55))
        place(canvas,item,x,feet,opacity=min(1,t/.55))
    else:place(canvas,item,x,feet)
    if s.get('boxes') and name=='daniel':
        for k in range(2):
            bx=round(x+23+k*45);by=round(feet-a['height']*.53+k*5)
            d.rectangle((bx-35,by-44,bx+30,by+8),fill='#9B6B42',outline='#3C302A',width=2)
            d.line((bx,by-43,bx,by+6),fill='#C99B5E',width=5)
            d.rectangle((bx-29,by-34,bx-13,by-22),fill='#B23F44')
    if s.get('call') and name=='lara':
        d.rectangle((x-item.width*.36,feet-a['height']*.83,x-item.width*.36+12,feet-a['height']*.70),fill='#16212B',outline='#556B78')
    if s.get('look_down') and name=='julia':
        # A small nod is anchored at the neck; the torso remains stationary.
        top=round(item.height*.19)
        head=item.crop((0,0,item.width,top))
        place(canvas,head,x,feet-item.height+top+round(2*min(1,t/1.2)))
    return x,feet


def truck_layer(t,u,depart=False):
    im=Image.new('RGBA',(440,180));d=ImageDraw.Draw(im)
    d.rectangle((18,18,283,136),fill='#CAD2D5',outline='#273642',width=4)
    for x in range(33,282,22):d.line((x,25,x,128),fill='#ADBCC4',width=2)
    d.rectangle((285,55,394,136),fill='#E3E9E9',outline='#273642',width=4)
    d.rectangle((300,63,367,94),fill='#1D3C50',outline='#587486',width=3)
    d.rectangle((284,110,405,136),fill='#D7E0E2')
    d.rectangle((11,132,414,145),fill='#283542')
    for x in (82,328):
        d.ellipse((x-25,128,x+25,178),fill='#17212D',outline='#556572',width=3)
        d.ellipse((x-11,142,x+11,164),fill='#8995A0')
        angle=t*6
        d.line((x-9*math.cos(angle),153-9*math.sin(angle),x+9*math.cos(angle),153+9*math.sin(angle)),fill='#334452',width=3)
    d.rectangle((397,108,407,114),fill='#F5D899')
    return im


def bus_layer(t,color):
    im=Image.new('RGBA',(480,155));d=ImageDraw.Draw(im)
    d.rectangle((9,15,470,121),fill=color,outline='#263B45',width=4)
    d.rectangle((15,102,468,125),fill='#D9E4DF')
    for x in range(25,420,54):d.rectangle((x,28,x+43,78),fill='#283C4A',outline='#97B6BC',width=2)
    d.rectangle((426,28,457,97),fill='#395561',outline='#97B6BC',width=2)
    for x in (92,385):
        d.ellipse((x-24,108,x+24,153),fill='#16212A',outline='#74858B',width=3)
        d.ellipse((x-10,120,x+10,141),fill='#99A7AA')
    return im


def paper(kind,t,u):
    im=Image.new('RGBA',(480,345));d=ImageDraw.Draw(im)
    d.rectangle((4,5,475,339),fill='#D4CAB4')
    d.rectangle((0,0,469,333),fill='#F4EFE0',outline='#9C957D',width=2)
    if kind=='confession':
        d.text((34,29),'DECLARAÇÃO',font=font(26),fill='#273642')
        d.text((34,83),'Daniel',font=font(21),fill='#303E43')
        d.text((34,121),'Desvio de mercadorias',font=font(19),fill='#3C474A')
        if u>.18:d.rectangle((28,161,437,207),fill='#EAD1B0')
        d.text((34,167),'R$ 180.000,00',font=font(30),fill='#8A3D3C')
        for y in (228,245):d.line((35,y,431,y),fill='#BEC0B3',width=2)
        d.line((35,290,432,290),fill='#545B54',width=2)
        d.text((34,301),'Assinatura',font=font(15),fill='#73796F')
    else:
        d.text((28,23),'SAÍDAS DE ESTOQUE',font=font(24),fill='#273642')
        d.text((28,67),'Responsável: Daniel',font=font(21),fill='#465A60')
        for k,(code,day) in enumerate([('R0247','SEG., 08:15'),('R0251','TER., 09:40'),('R0259','QUA., 14:20')]):
            y=118+k*52
            d.rectangle((24,y,444,y+39),fill='#E7E7DA' if k%2==0 else '#F0F0E4')
            d.text((36,y+9),code,font=font(18),fill='#283D44')
            d.text((193,y+9),day,font=font(18),fill='#36474B')
        d.text((29,291),'3 registros · conferência interna',font=font(15),fill='#747D74')
    return im


def phone(kind,t,u):
    im=Image.new('RGBA',(310,455));d=ImageDraw.Draw(im)
    d.rounded_rectangle((0,0,309,454),radius=20,fill='#141D29',outline='#879398',width=3)
    d.rectangle((16,34,294,420),fill='#E5EADD')
    d.rectangle((16,34,294,80),fill='#275C62')
    d.text((33,44),'Júlia' if kind in ('julia','shipment') else 'Mensagens',font=font(21),fill='#F3EADF')
    d.line((115,437,193,437),fill='#AAB4B5',width=3)
    if kind=='shipment':
        d.rectangle((27,99,283,335),fill='#F3F2E5',outline='#899E97',width=2)
        d.text((40,115),'SAÍDA DE MERCADORIAS',font=font(15),fill='#30464B')
        d.text((40,158),'Responsável',font=font(15),fill='#6B7A70')
        d.text((40,186),'Daniel',font=font(26),fill='#23464F')
        if u>.15:d.rectangle((35,229,275,267),fill='#ECD2A1')
        d.text((41,238),'HOJE · 18:48',font=font(22),fill='#7A3C36')
        d.text((41,289),'CARGA LIBERADA',font=font(16),fill='#336E6B')
        d.text((32,366),'Imagem recebida',font=font(16),fill='#6A7D75')
    elif kind=='julia':
        d.rounded_rectangle((29,117,278,245),radius=8,fill='#F6F5E8')
        for value,y in [('Pode atender?',132),('Mas fala de um lugar',165),('onde ninguém escute.',193)]:
            d.text((42,y),value,font=font(18),fill='#293F46')
        d.text((222,226),'18:58',font=font(11),fill='#768B7C')
        d.ellipse((116,310,195,389),fill='#467F71')
        d.arc((135,330,176,366),30,150,fill='#F2ECDD',width=8)
    elif kind=='denied':
        for value,y in [('Vitor',116),('Agora trate disso',172),('pelos meios certos.',203)]:
            d.text((38,y),value,font=font(20),fill='#364E51')
        d.text((40,276),'Ligação não atendida',font=font(17),fill='#9A5250')
        d.text((41,309),'Mauro',font=font(18),fill='#405D61')
    else:
        d.rounded_rectangle((29,100,282,148),radius=7,fill='#F5F4E5')
        d.text((41,113),'O que aconteceu aí?',font=font(18),fill='#30464B')
        if kind=='viral':
            mini=cctv(t).resize((241,137),Image.Resampling.NEAREST)
            im.alpha_composite(mini,(35,167))
            d.rectangle((36,277,275,305),fill='#1E2C3D')
            d.text((52,283),'Vídeo encaminhado',font=font(15),fill='#E1E6DA')
            d.text((42,342),'3 novas mensagens',font=font(17),fill='#43736B')
        else:
            phrase='É mentira.'
            length=round(len(phrase)*min(1,t/1.6)) if t<2.2 else max(0,len(phrase)-round((t-2.2)*10))
            d.rounded_rectangle((65,199,281,258),radius=8,fill='#BFD4BD')
            d.text((80,218),phrase[:length]+'│',font=font(21),fill='#354C44')
            d.rectangle((19,308,291,419),fill='#CAD4CD')
            for row in range(3):
                for col in range(9):d.rectangle((26+col*29,318+row*28,48+col*29,339+row*28),fill='#F0F2E8')
    return im


def cctv(t):
    im=assets().backgrounds['loading'].copy()
    truck=truck_layer(0,0)
    place(im,truck,735,435)
    a=actor('daniel',x=260,to_x=660,walk=True,height=265,feet=470)
    draw_actor(im,a,dict(duration_seconds=6,boxes=True),t%6)
    d=ImageDraw.Draw(im);d.rectangle((20,20,30,30),fill='#B64846')
    d.text((37,15),'REC',font=font(15),fill='#DDE7DE')
    return im


def props(im,s,t):
    u=min(1,t/max(.1,s['duration_seconds']));kind=s.get('prop');d=ImageDraw.Draw(im)
    if kind in ('confession','report'):
        item=paper(kind,t,u);x=480
        if s.get('action')=='slide':x=620-140*min(1,t/1.5)
        if s.get('action')=='withdraw':x=480+155*min(1,t/1.1)
        place(im,item,x,457)
        if s.get('action') in ('slide','withdraw'):
            hx=x+228;hy=354
            d.polygon([(hx,hy),(hx+74,hy-14),(W,hy+3),(W,hy+48),(hx+76,hy+33),(hx,hy+27)],fill='#C79C73')
            if hx+109<W:d.rectangle((hx+109,hy-9,W,hy+47),fill='#E9E1CE')
            for k in range(3):d.line((hx+9,hy+4+k*6,hx+53,hy+1+k*6),fill='#8C654E',width=2)
        if kind=='confession':
            d.polygon([(750,380),(757,374),(810,460),(803,466)],fill='#293C48')
            d.polygon([(802,465),(807,459),(818,479)],fill='#CAB28B')
    elif kind=='phone':
        item=phone(s.get('phone','viral'),t,u)
        x=480+(round(2*math.sin(t*48)) if s.get('vibrate') and t<.9 else 0)
        place(im,item,x,504)
        d.polygon([(359,430),(353,475),(360,H),(443,H),(438,495),(411,468),(404,430)],fill='#B78565')
    elif kind=='badge':
        y=172+round(85*min(1,t/1.2)) if s.get('action')=='remove' else 246
        d.line((396,45,445,y),fill='#3D8C83',width=13)
        d.line((566,45,525,y),fill='#3D8C83',width=13)
        d.rounded_rectangle((371,y,595,y+186),radius=8,fill='#E9E9D7',outline='#31525A',width=4)
        d.rectangle((389,y+24,458,y+93),fill='#6D8390')
        head=assets().sprite('work',0,160).crop((0,0,100,58)).resize((68,68),Image.Resampling.NEAREST)
        im.alpha_composite(head,(391,y+24))
        d.text((475,y+29),'DANIEL',font=font(21),fill='#293F4C')
        d.text((475,y+62),'Estoque',font=font(16),fill='#6B7975')
        for k in range(26):d.line((391+k*7,y+116,391+k*7,y+145),fill='#4D666A',width=1+(k%3==0))
        if s.get('action')=='blocked':
            d.rectangle((354,y+126,611,y+171),fill='#713D43')
            d.text((367,y+139),'ACESSO BLOQUEADO',font=font(18),fill='#F0E4D3')
    elif kind=='compare':
        left=paper('report',t,u).resize((400,302),Image.Resampling.NEAREST)
        right=paper('confession',t,u).resize((390,302),Image.Resampling.NEAREST)
        place(im,left,259,452);place(im,right,695,452)
        d.rectangle((531,179,865,391),fill='#F4EFE0')
        for value,y in [('DEVOLUÇÃO',191),('Recibo R0247',238),('SEX., 17:42',285)]:
            d.text((552,y),value,font=font(24),fill='#30565B')
        if t>.6:
            d.rectangle((208,254,423,289),outline='#B8654C',width=4)
            d.rectangle((546,282,845,322),outline='#B8654C',width=4)
            d.line((424,272,540,300),fill='#D4A252',width=3)
    elif kind=='bills':
        for k,(label,amount) in enumerate([('ALUGUEL','Este mês'),('CONTAS','Próximo mês'),('RENDA','A encontrar')]):
            x=190+k*222+round((1-min(1,t/1.1))*(110-k*33));y=205+(k%2)*26
            d.rectangle((x,y,x+210,y+217),fill='#E7E1CA',outline='#A09C89',width=2)
            d.text((x+20,y+25),label,font=font(20),fill='#344F53')
            d.text((x+20,y+85),amount,font=font(19),fill='#8E6250')
            for row in range(4):d.line((x+20,y+131+row*13,x+187,y+131+row*13),fill='#B4BBAD',width=2)
    elif kind=='bag':
        d.rounded_rectangle((200,211,470,468),radius=20,fill='#202E3B',outline='#586776',width=4)
        d.rectangle((275,170,400,225),outline='#546676',width=11)
        d.rectangle((236,279,434,433),fill='#38434C',outline='#8C9592',width=3)
        d.rounded_rectangle((530,262,776,411),radius=17,fill='#A8C3B6',outline='#527575',width=4)
        d.rectangle((544,285,763,303),fill='#D4E0CB')
        badge=paper('confession',t,u).resize((202,146),Image.Resampling.NEAREST)
        place(im,badge,672,195)
        d.rectangle((562,148,653,207),fill='#E5E6D9',outline='#588C89',width=3)
        d.text((571,167),'DANIEL',font=font(14),fill='#2A5154')


def set_motion(im,s,t):
    u=min(1,t/max(.1,s['duration_seconds']));d=ImageDraw.Draw(im)
    if s.get('door'):
        opening=min(1,t/1.2)
        if s['door']=='ajar':opening=1
        if s['door']=='close':opening=1-opening
        x0,y0,x1,y1=(628,71,777,400) if s['bg']=='purchasing' else (754,89,850,350)
        d.rectangle((x0,y0,x1,y1),fill='#111E2C',outline='#334956',width=3)
        edge=x0+(x1-x0)*(1-opening*.88)
        d.polygon([(x0,y0),(edge,y0+opening*20),(edge,y1-opening*20),(x0,y1)],fill='#675B4A' if s['bg']=='purchasing' else '#30414E',outline='#192C39')
        d.rectangle((edge-14,(y0+y1)/2,edge-8,(y0+y1)/2+8),fill='#BDAC75')
    if s.get('truck'):
        depart=s.get('depart',False)
        item=truck_layer(t if depart else 0,u,depart)
        x=717+(u*670 if depart else 0)
        place(im,item,x,454)
    if s.get('bus'):
        # Two buses pass in the road plane, before Daniel crosses the foreground.
        for k,color in enumerate(('#388184','#9B624B')):
            phase=u*2.1-k*.85
            if -.2<phase<1.35:
                item=bus_layer(t,color).resize((610,197),Image.Resampling.NEAREST)
                place(im,item,-310+phase*1590,404)
    if s.get('tv'):
        footage=cctv(t).resize((187,99),Image.Resampling.NEAREST)
        im.alpha_composite(footage,(752,102))
        d.rectangle((747,97,943,206),outline='#101D29',width=5)
    if s.get('clock'):
        d.ellipse((719,28,789,98),fill='#DEE2D8',outline='#3D5661',width=3)
        d.line((754,62,749,36),fill='#344956',width=3)
        angle=t*.3
        d.line((754,62,754+24*math.sin(angle),62-24*math.cos(angle)),fill='#344956',width=2)
    if s.get('monitor'):
        x,y=185,150
        d.rectangle((x,y,x+176,y+89),fill='#172F3E')
        d.rectangle((x,y,x+176,y+13),fill='#3C6B73')
        d.text((x+7,y+1),'Currículo' if s['monitor']=='cv' else 'Conferências',font=font(10),fill='#F1E5CC')
        if s['monitor']=='cv':
            d.rectangle((x+35,y+20,x+145,y+85),fill='#DCE2D6')
            d.text((x+42,y+25),'Daniel',font=font(11),fill='#315259')
            for k in range(min(5,1+int(t*.55))):d.line((x+44,y+45+k*7,x+130,y+45+k*7),fill='#829A94')
        else:
            for k in range(4):
                xx=x+10+(k%2)*80;yy=y+25+(k//2)*28
                d.rectangle((xx,yy,xx+17,yy+13),fill='#C49454')
                d.text((xx+23,yy+3),['Fotos','Recibos','Datas','Contatos'][k],font=font(9),fill='#DCE5D9')
        mx=x+20+min(135,t*14);my=y+28+12*math.sin(t*.9)
        d.polygon([(mx,my),(mx,my+10),(mx+3,my+6),(mx+8,my+6)],fill='#F3EADB')


def image_frame(s,t):
    im=background(s,t+s['start_seconds'])
    set_motion(im,s,t)
    for a in sorted(s.get('actors',[]),key=lambda a:a['feet']):
        if s.get('enter') and a['name']=='vitor' and t<.55:continue
        draw_actor(im,a,s,t)
    if s.get('table'):
        original=assets().backgrounds['dining']
        mask=Image.new('L',(W,H));d=ImageDraw.Draw(mask)
        d.polygon([(421,279),(866,277),(870,310),(422,314)],fill=255)
        d.polygon([(425,309),(445,309),(445,527),(427,527)],fill=255)
        d.polygon([(846,309),(868,309),(873,528),(851,528)],fill=255)
        im=Image.composite(original,im,mask).convert('RGBA')
        d=ImageDraw.Draw(im)
        # Dinner props belong on the table plane, never floating over faces.
        for x in (485,643,790):
            d.ellipse((x-27,285,x+27,297),fill='#CED7C2',outline='#70827D')
        if s['paragraph']>=49:d.rectangle((635,282,669,292),fill='#15222D')
    props(im,s,t)
    if s.get('cctv'):
        d=ImageDraw.Draw(im);d.rectangle((23,25,32,34),fill='#B8524F')
    if s.get('lume'):
        item=assets().sprite('lume',int(t*9)%8,52)
        fade=min(1,t/.5,max(0,(s['duration_seconds']-t)/.6))
        place(im,item,85+round(9*math.sin(t*1.4)),105+round(6*math.sin(t*2)),opacity=fade)
    z=s.get('zoom',1)+.018*min(1,t/max(.1,s['duration_seconds']))
    if z>1:
        cw,ch=W/z,H/z;cx,cy=s.get('focus',(480,270))
        cx=max(cw/2,min(W-cw/2,cx));cy=max(ch/2,min(H-ch/2,cy))
        im=im.crop((round(cx-cw/2),round(cy-ch/2),round(cx+cw/2),round(cy+ch/2))).resize((W,H),Image.Resampling.NEAREST)
    if s.get('closing'):
        im=Image.alpha_composite(im,Image.new('RGBA',(W,H),(18,23,45,232)))
        d=ImageDraw.Draw(im)
        for value,y,size in [('Fio de Lume',165,35),('PARTE 1 DE 4',224,19),('Continua na parte 2',275,27),('O preço do silêncio',322,23)]:
            f=font(size);b=d.textbbox((0,0),value,font=f)
            d.text(((W-b[2]+b[0])/2,y),value,font=f,fill=CREAM)
        item=assets().sprite('lume',int(t*9)%8,56)
        place(im,item,480+round(4*math.sin(t*2)),143)
    im=im.convert('RGB');d=ImageDraw.Draw(im)
    d.rectangle((9,9,W-10,H-10),outline=GOLD,width=2)
    if s['index']==0 and t<.25:im=Image.blend(Image.new('RGB',(W,H),INK),im,t/.25)
    if s.get('closing') and t>s['duration_seconds']-.55:
        im=Image.blend(im,Image.new('RGB',(W,H),INK),(t-s['duration_seconds']+.55)/.55)
    return im


def render_one(s):
    folder=WORK/'animacao';folder.mkdir(parents=True,exist_ok=True)
    file=folder/f'cena-{s["index"]:03d}.mp4';stamp=file.with_suffix('.sha256')
    signature=hashlib.sha256((json.dumps(s,sort_keys=True)+Path(__file__).read_text()).encode()).hexdigest()
    if file.exists() and file.stat().st_size>1000 and stamp.exists() and stamp.read_text()==signature:
        return str(file)
    partial=file.with_name(file.stem+'.partial.mp4')
    command=['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo',
             '-pixel_format','rgb24','-video_size',f'{W}x{H}','-framerate',str(ART_FPS),
             '-i','pipe:0','-vf','fps=24,scale=1920:1080:flags=neighbor,setsar=1',
             '-frames:v',str(s['frames']),'-an','-c:v','libx264','-preset','veryfast',
             '-crf','23','-threads','2','-pix_fmt','yuv420p','-movflags','+faststart',str(partial)]
    with file.with_suffix('.log').open('w') as log:
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=log,stderr=log)
        try:
            for frame in range(math.ceil(s['frames']/2)):
                process.stdin.write(image_frame(s,frame/ART_FPS).tobytes())
            process.stdin.close()
            if process.wait():raise RuntimeError(f'Failed render: {file.name}')
            actual=int(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0',
                       '-show_entries','stream=nb_frames','-of','default=noprint_wrappers=1:nokey=1',str(partial)],text=True))
            if actual!=s['frames']:raise ValueError(f'Frame count differs: {file.name}, {actual}/{s["frames"]}')
            partial.replace(file)
        except Exception:
            if process.poll() is None:process.kill();process.wait()
            partial.unlink(missing_ok=True)
            raise
    stamp.write_text(signature)
    return str(file)


def original_score(shots,total):
    sr=24000;audio=np.zeros((round(total*sr),2),np.float32)
    chords=[(130.813,155.563,195.998),(103.826,130.813,155.563),
            (87.307,103.826,130.813),(97.999,123.471,146.832)]
    reveal=next(s['start_seconds'] for s in shots if s['paragraph']==73)
    rng=np.random.default_rng(1901)
    for bar in range(math.ceil(total/15)):
        begin=bar*15;length=min(17,total-begin);n=round(length*sr)
        if n<=0:continue
        tt=np.arange(n)/sr;env=np.minimum(1,tt/3)*np.minimum(1,(length-tt)/4)
        strength=.16 if begin>reveal-5 else .42
        chord=chords[(bar//2)%4];offset=round(begin*sr)
        for k,freq in enumerate(chord):
            pad=(np.sin(2*np.pi*freq*tt)+.13*np.sin(2*np.pi*freq*2*tt))*.026*env*strength
            audio[offset:offset+n,0]+=pad*(.7+.1*k)
            audio[offset:offset+n,1]+=pad*(.9-.1*k)
        for k in range(3):
            start=begin+3.2+k*3.7
            if start+3>total:continue
            t=np.arange(sr*3)/sr
            note=(np.sin(2*np.pi*chord[k]*2*t)+.18*np.sin(2*np.pi*chord[k]*4.002*t))
            note*=np.exp(-t*2.7)*np.minimum(1,t/.008)*.014*strength
            pos=round(start*sr);audio[pos:pos+len(note),0]+=note;audio[pos:pos+len(note),1]+=note*.85
    for s in shots:
        pos=round(s['start_seconds']*sr);n=min(round(s['duration_seconds']*sr),len(audio)-pos)
        tt=np.arange(n)/sr;fade=np.minimum(1,tt/.4)*np.minimum(1,(n/sr-tt)/.4)
        if s['bg'] in ('warehouse','loading','street') and not s.get('detail'):
            noise=rng.standard_normal(n)
            ambience=signal.sosfilt(signal.butter(2,[100,1100],btype='band',fs=sr,output='sos'),noise)*.004*fade
            audio[pos:pos+n,0]+=ambience;audio[pos:pos+n,1]+=np.roll(ambience,50)
        if s.get('vibrate'):
            t=np.arange(round(.35*sr))/sr
            buzz=np.sin(2*np.pi*112*t)*np.sin(np.pi*t/.35)**2*.013
            audio[pos:pos+len(buzz)]+=buzz[:,None]
        if s.get('door'):
            t=np.arange(round(.21*sr))/sr
            click=np.sin(2*np.pi*180*t)*np.exp(-t*27)*.018
            at=min(len(audio)-len(click),pos+round(.6*sr));audio[at:at+len(click)]+=click[:,None]
        if s.get('prop') in ('confession','report','bills'):
            t=np.arange(round(.25*sr))/sr
            noise=signal.sosfilt(signal.butter(2,[900,4000],btype='band',fs=sr,output='sos'),rng.standard_normal(len(t)))
            rustle=noise*np.exp(-t*15)*.015
            audio[pos:pos+len(rustle)]+=rustle[:,None]
    end=next(s['start_seconds'] for s in shots if s.get('closing'))
    # A very brief original minor chord arrives only after the last question.
    t=np.arange(round((total-end)*sr))/sr
    hit=sum(np.sin(2*np.pi*f*t) for f in (65.406,77.782,97.999))*.018
    hit*=np.exp(-t*1.6)*np.minimum(1,t/.015)
    at=round(end*sr);audio[at:at+len(hit)]+=hit[:,None]
    fade=np.minimum(1,np.arange(len(audio))/(sr*.6))*np.minimum(1,(len(audio)-np.arange(len(audio)))/(sr*.8))
    audio*=fade[:,None]
    path=WORK/'trilha_original.wav'
    with wave.open(str(path),'wb') as out:
        out.setnchannels(2);out.setsampwidth(2);out.setframerate(sr)
        out.writeframes((np.clip(audio,-.8,.8)*32767).astype('<i2').tobytes())
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(path),
                    '-c:a','libmp3lame','-b:a','96k',str(EP/'assets/trilha_ambientes.mp3')],check=True)


def finish(shots,total):
    concat=WORK/'animacao/concat.txt'
    concat.write_text(''.join(f"file 'cena-{s['index']:03d}.mp4'\n" for s in shots))
    silent=WORK/'animacao/silent.mp4'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-xerror','-y','-f','concat',
                   '-safe','1','-i',str(concat),'-c','copy',str(silent)],check=True)
    expected=sum(s['frames'] for s in shots)
    actual=int(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0',
               '-show_entries','stream=nb_frames','-of','default=noprint_wrappers=1:nokey=1',str(silent)],text=True))
    if actual!=expected:raise ValueError(f'Incomplete movie: {actual}/{expected} frames')
    original_score(shots,total)
    filters=('[1:a]loudnorm=I=-16:TP=-1.5:LRA=9,apad,asplit=2[voice][control];'
             '[2:a]volume=-4dB[bed];[bed][control]sidechaincompress=threshold=0.02:ratio=5:attack=15:release=300[ducked];'
             '[voice][ducked]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.89:level=false[mixed]')
    partial=EP/'video.partial.mp4'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(silent),
                   '-i',str(WORK/'narracao.mp3'),'-i',str(EP/'assets/trilha_ambientes.mp3'),
                   '-filter_complex',filters,'-map','0:v:0','-map','[mixed]','-t',str(total),
                   '-c:v','copy','-c:a','aac','-b:a','128k','-ar','48000','-ac','2','-sn',
                   '-map_metadata','-1','-movflags','+faststart',str(partial)],check=True)
    partial.replace(EP/'video.mp4')
    for name in ('narracao.mp3','narracao.json','legendas.srt'):
        shutil.copyfile(WORK/name,EP/name)
    shutil.copyfile(WORK/'words.json',EP/'producao/palavras.json')
    meta=json.loads((EP/'metadata.json').read_text());meta['status']='produced'
    save_json(EP/'metadata.json',meta)
    print(f'VIDEO READY: {total:.3f}s, {(EP/"video.mp4").stat().st_size} bytes',flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=('plan','render','finish'))
    parser.add_argument('--workers',type=int,default=4);args=parser.parse_args()
    WORK.mkdir(parents=True,exist_ok=True)
    if args.stage=='plan':plan();return
    data=json.loads((EP/'producao/plano_cenas.json').read_text())
    shots,total=data['shots'],data['duration_seconds']
    if args.stage=='render':
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures={pool.submit(render_one,s):s for s in shots}
            for future in as_completed(futures):
                future.result();s=futures[future]
                print(f'ANIMATED {s["index"]+1:02d}/{len(shots)}: {s["duration_seconds"]:.2f}s',flush=True)
    elif args.stage=='finish':finish(shots,total)


if __name__=='__main__':main()




