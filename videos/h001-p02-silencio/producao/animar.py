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
        self.sprites['investigation'] = sprites_from_grid(EP/'assets/personagens-investigacao.png', 6, 2)
        self.sprites['seated'] = sprites_from_grid(EP/'assets/personagens-acordo.png', 4, 2)
        self.sprites['lume'] = sprites_from_grid(EP/'assets/lume.png', 4, 2)
        self.backgrounds = {}
        for filename, names in [('cenarios-trabalho.png', ['office','warehouse','street','loading']),
                                ('cenarios-casa.png', ['dining','desk','laundry','purchasing']),
                                ('cenarios-investigacao.png', ['dispatch','depot','cafe','gate'])]:
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
    D=lambda **kw:actor('daniel',**({'x':680,'outfit':'blue'}|kw))
    H=lambda **kw:actor('daniel',**({'x':540,'pose':5}|kw))
    M=lambda **kw:actor('mauro',**({'x':700}|kw))
    V=lambda **kw:actor('vitor',**({'x':730}|kw))
    J=lambda **kw:actor('julia',**({'x':340,'flip':True}|kw))
    B=lambda **kw:actor('beto',**({'x':280}|kw))
    L=lambda **kw:actor('lara',**({'x':825}|kw))
    close=lambda bg,a,**kw:scene(bg,[a],focus=(a['x'],a['feet']-a['height']*.70),zoom=1.82,**kw)
    cafe=lambda **kw:scene('cafe',[J(height=295,feet=496),D(height=310)],**kw)
    carrier=lambda **kw:scene('dispatch',[B(),D()],**kw)
    office=lambda dp=0,mp=0,**kw:scene('office',[D(x=310,height=290,feet=506,seated=True,pose=dp),M(x=700,height=295,feet=506,seated=True,pose=mp)],conference_table=True,**kw)
    family=lambda **kw:scene('dining',[D(x=380,pose=0,seated=True,height=295,feet=510),L(pose=1,height=325,feet=510)],table=True,**kw)
    detail=lambda kind,bg='dispatch',**kw:scene(bg,prop=kind,detail=True,**kw)
    recipes={
      0:scene('purchasing',[J(x=440,pose=1,flip=False),V()],focus=(730,235),zoom=1.4,door='ajar',lume=True),
      1:scene('purchasing',[J(x=440,pose=1,flip=False),V()],focus=(550,245),zoom=1.5,door='ajar',lower_phone=True),
      2:close('purchasing',J(x=440,pose=0,flip=False),door='ajar'),
      3:detail('phone',bg='laundry',phone='shipment'),
      4:detail('phone',bg='laundry',phone='rescue',vibrate=True),
      5:scene('laundry',[H(x=535,pose=4,height=260,feet=480),L(x=790,to_x=725)],approach=True),
      6:close('laundry',L(x=740)),
      7:close('laundry',H(x=515,pose=4,height=260,feet=480)),
      8:scene('laundry',[H(x=535,pose=4,height=260,feet=480),L(x=725)]),
      9:scene('cafe',[D(),J(x=180,to_x=335,height=295,feet=496)],approach=True,arrival=True,lume=True),
      10:close('cafe',J()),
      11:close('cafe',D()),
      12:cafe(focus=(650,250),zoom=1.55),
      13:detail('phone',bg='cafe',phone='order'),
      14:close('cafe',J(pose=1)),
      15:close('cafe',D()),
      16:close('cafe',J()),
      17:detail('order-compare',bg='cafe'),
      18:close('cafe',D()),
      19:close('cafe',J(),look_down=True),
      20:cafe(focus=(640,250),zoom=1.4),
      21:scene('cafe',[D(),J(x=340,to_x=130)],approach=True,arrival=True),
      22:scene('depot',[B(x=400),D(x=830,to_x=665,walk=True)],truck=True,approach=True,lume=True),
      23:close('depot',B()),
      24:detail('receipt',bg='depot',action='place'),
      25:scene('depot',[B(),D(pose=1)],truck=True),
      26:close('depot',B(pose=1)),
      27:scene('dispatch',[B(x=190,to_x=280,pose=1),D()],approach=True,arrival=True),
      28:detail('compare',action='highlight'),
      29:carrier(focus=(300,255),zoom=1.4),
      30:close('dispatch',B(pose=1)),
      31:detail('delivery-proof'),
      32:detail('archive',action='photo'),
      33:detail('phone',phone='shipment'),
      34:close('dispatch',D(pose=1)),
      35:scene('dispatch',[B(),D()],dispatch_monitor=True,focus=(300,225),zoom=1.12),
      36:close('dispatch',B(pose=2)),
      37:detail('route'),
      38:detail('phone',phone='route'),
      39:detail('route-compare'),
      40:close('dispatch',D(pose=1)),
      41:carrier(focus=(650,250),zoom=1.45),
      42:scene('depot',[B()],truck=True,focus=(470,260),zoom=1.12),
      43:close('dispatch',B()),
      44:carrier(),
      45:detail('phone',bg='street',phone='unsent'),
      46:scene('desk',[D(x=387,seated=True,flip=True,height=240,feet=443)],monitor='files',computer=True),
      47:detail('bills',bg='dining',action='spread',lume=True),
      48:family(focus=(820,290),zoom=1.55),
      49:family(focus=(380,290),zoom=1.58),
      50:family(focus=(825,290),zoom=1.6),
      51:detail('phone',bg='dining',phone='mauro',vibrate=True),
      52:detail('phone',bg='dining',phone='mauro'),
      53:detail('record',bg='dining'),
      54:scene('desk',[D(x=387,seated=True,flip=True,height=240,feet=443)],monitor='files',computer=True),
      55:scene('gate',[D(x=725,to_x=365,walk=True)],approach=True,lume=True),
      56:office(door='close'),
      57:detail('agreement',bg='office',action='slide'),
      58:office(dp=1,focus=(310,290),zoom=1.65),
      59:detail('agreement',bg='office',action='highlight'),
      60:office(focus=(310,290),zoom=1.6),
      61:office(mp=0,focus=(700,290),zoom=1.65),
      62:office(focus=(310,290),zoom=1.7),
      63:detail('meeting-documents',bg='office',action='receipt'),
      64:office(dp=2,focus=(340,290),zoom=1.55),
      65:office(mp=3,focus=(700,290),zoom=1.65),
      66:detail('meeting-documents',bg='office',action='route'),
      67:office(dp=1,focus=(310,290),zoom=1.65),
      68:office(dp=3,mp=2,papers_move=True),
      69:office(dp=0,focus=(310,290),zoom=1.7),
      70:office(mp=0,focus=(690,260),zoom=1.6,look_door=True),
      71:office(mp=3,focus=(700,255),zoom=1.88),
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
    ending=scene('office',closing=True,lume=True)
    ending.update(index=len(shots),paragraph=len(paragraphs),narration='',start_seconds=first/FPS,
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
        (0,'A ligação interrompida'),(9,'O que Júlia viu'),
        (22,'Os documentos da viagem'),(33,'A mudança de endereço'),
        (47,'Contas e escolhas'),(56,'A proposta de Mauro')]]
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
    if s['bg'] in ('warehouse','loading','office','purchasing','dispatch','depot','gate') and not s.get('detail'):
        for k in range(5):
            x=215+k*157;y=35+(k%2)*20
            if s['bg']=='office':y=75
            draw.rectangle((x,y,x+11,y+2),fill=(145,205,228,80+round(15*math.sin(t*.9+k))))
    if s['bg'] in ('street','loading','depot','gate','cafe') and not s.get('detail'):
        for k in range(6):
            x=150+k*90+round(3*math.sin(t*.65+k));y=34+(k*37)%90
            draw.rectangle((x,y,x+2,y+1),fill=(231,236,204,55))
    if s['bg']=='laundry' and not s.get('detail'):
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
    settled=bool(a.get('walk') and s.get('approach') and t>=1.8)
    x=a['x']
    if a.get('to_x') is not None:
        move=min(1,t/(1.8 if s.get('approach') else max(1,s['duration_seconds'])))
        x+=(a['to_x']-x)*move
    if name=='daniel' and a.get('outfit')=='blue':
        if a.get('seated'):atlas,index='seated',pose
        elif a.get('walk'):atlas,index='investigation',8 if settled else 8+int(t*5)%4
        else:atlas,index='investigation',4+pose
    elif name=='mauro' and a.get('seated'):atlas,index='seated',4+pose
    elif name=='beto':atlas,index='investigation',pose
    elif name=='daniel':
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
    flip=a.get('flip',False)
    if name=='mauro' and a.get('seated') and pose==0:flip=not flip
    item=A.sprite(atlas,index,a['height'],flip)
    if s.get('lower_phone') and name=='julia':
        lowered=A.sprite('work',4,a['height'],a.get('flip',False))
        change=min(1,t/.8)
        place(canvas,item,x,a['feet'],opacity=1-change)
        place(canvas,lowered,x,a['feet'],opacity=change)
        return x,a['feet']
    if s.get('look_door') and name=='mauro' and t<1.8:
        item=item.copy();split=round(item.height*.21)
        head=item.crop((0,0,item.width,split))
        item.paste((0,0,0,0),(0,0,item.width,split))
        item.alpha_composite(ImageOps.mirror(head),(0,0))
    if ((s.get('enter') and name=='vitor') or (s.get('arrival') and a.get('to_x') is not None)) and t<2.8:
        # Animate the legs on a separate plane as he comes through the doorway.
        split=round(item.height*.61);legs=item.crop((0,split,item.width,item.height))
        moving=Image.new('RGBA',item.size)
        moving.alpha_composite(item.crop((0,0,item.width,split)),(0,0))
        for row in range(0,legs.height,3):
            shift=round(math.sin(t*10)*4*row/max(1,legs.height))
            moving.alpha_composite(legs.crop((0,row,legs.width,min(row+3,legs.height))),(shift,split+row))
        item=moving
    bob=round(1.5*math.sin(t*math.pi*10)) if a.get('walk') and not settled else round(.75*math.sin(t*1.7+index))
    feet=a['feet']+bob
    d=ImageDraw.Draw(canvas)
    seated=a.get('seated',False) or (name=='daniel' and pose==4) or (name=='lara' and pose==1) or (name=='nina' and pose==0)
    if seated:
        cx=x+item.width*(.1 if name in ('lara','nina') else -.1)
        seat=round(feet-item.height*.43)
        bottom=(490 if name=='nina' else 516) if s.get('table') or s.get('conference_table') else round(feet+6)
        side=1 if name in ('lara','nina','mauro') else -1
        d.rectangle((cx-38,seat,cx+38,seat+11),fill='#64513C',outline='#302B27',width=2)
        for xx in (cx-34,cx+27):d.rectangle((xx,seat+8,xx+7,bottom),fill='#493A2E')
        xx=cx+side*36
        d.rectangle((xx-5,seat-94,xx+5,seat+8),fill='#66533E')
    if not seated:d.ellipse((x-item.width*.30,feet-3,x+item.width*.30,feet+4),fill=(6,12,20,65))
    if s.get('gesture') and t<.55 and name in ('daniel','mauro') and not a.get('outfit'):
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
    if kind in ('agreement','receipt','route'):
        title={'agreement':'PROPOSTA DE ACORDO','receipt':'RECIBO DE DEVOLUÇÃO','route':'ORDEM DA TRANSPORTADORA'}[kind]
        d.text((25,24),title,font=font(22),fill='#273642')
        if kind=='agreement':
            d.text((28,78),'Daniel',font=font(21),fill='#345359')
            d.rectangle((25,119,441,173),fill='#EDD8B1')
            d.text((35,130),'R$ 40.000,00',font=font(31),fill='#724532')
            d.text((28,194),'Encerramento do assunto',font=font(20),fill='#41534F')
            d.text((28,230),'Confidencialidade',font=font(21),fill='#884949')
            d.line((30,285,439,285),fill='#646D60',width=2)
            d.text((30,299),'Assinatura',font=font(15),fill='#66776A')
        elif kind=='receipt':
            for value,y,size in [('R0247',76,29),('SEX., 17:42',123,25),('2 CAIXAS · ETIQUETA VERMELHA',175,17),('Destino: fornecedor',212,21),('Devolução recebida',251,22)]:
                d.text((28,y),value,font=font(size),fill='#34575B')
            d.line((29,295,436,295),fill='#738C7A',width=2)
            d.line((315,285,331,281,339,288,353,277,371,287),fill='#406B72',width=2)
            d.text((29,304),'Via da transportadora',font=font(14),fill='#75846F')
        else:
            for value,y,size in [('QUI., 18:48',75,25),('Solicitante: Vitor',122,25),('ALTERAÇÃO DE DESTINO',171,19),('Rua das Palmeiras, 318',213,23),('Portão B',251,23)]:
                d.text((28,y),value,font=font(size),fill='#34575B')
            d.line((28,291,438,291),fill='#81907D',width=2)
            d.text((28,303),'Registro da viagem · original',font=font(14),fill='#75846F')
    elif kind=='confession':
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


def phone(kind,t,u,day='HOJE'):
    im=Image.new('RGBA',(310,455));d=ImageDraw.Draw(im)
    d.rounded_rectangle((0,0,309,454),radius=20,fill='#141D29',outline='#879398',width=3)
    d.rectangle((16,34,294,420),fill='#E5EADD')
    d.rectangle((16,34,294,80),fill='#275C62')
    title='Júlia' if kind in ('julia','shipment','rescue') else 'Vitor' if kind in ('order','route') else 'Mauro' if kind=='mauro' else 'Colegas' if kind=='unsent' else 'Mensagens'
    d.text((33,44),title,font=font(21),fill='#F3EADF')
    d.line((115,437,193,437),fill='#AAB4B5',width=3)
    if kind=='shipment':
        d.rectangle((27,99,283,335),fill='#F3F2E5',outline='#899E97',width=2)
        d.text((40,115),'SAÍDA DE MERCADORIAS',font=font(15),fill='#30464B')
        d.text((40,158),'Responsável',font=font(15),fill='#6B7A70')
        d.text((40,186),'Daniel',font=font(26),fill='#23464F')
        if u>.15:d.rectangle((35,229,275,267),fill='#ECD2A1')
        d.text((41,238),day+' · 18:48',font=font(22),fill='#7A3C36')
        d.text((41,289),'CARGA LIBERADA',font=font(16),fill='#336E6B')
        d.text((32,366),'Imagem recebida',font=font(16),fill='#6A7D75')
    elif kind in ('rescue','order','route','mauro'):
        lines={
            'rescue':['Não liga.','Amanhã, 7h30.','No café perto','do terminal.'],
            'order':['Registra a saída.','Mantém o','responsável.'],
            'route':['Palmeiras, 318.','Portão B.','Deixa lá.','A conferência','fica comigo.'],
            'mauro':['Vamos conversar.','Hoje, no escritório.','Vamos resolver','isso com calma.']
        }[kind]
        d.rounded_rectangle((28,108,282,139+len(lines)*35),radius=8,fill='#F7F5E7')
        for k,value in enumerate(lines):d.text((39,123+k*35),value,font=font(20),fill='#2D454C')
        stamp='QUI. · 18:32' if kind=='order' else 'QUI. · 16:15' if kind=='route' else 'Mensagem recebida'
        d.text((38,157+len(lines)*35),stamp,font=font(14),fill='#668172')
        if kind=='mauro':
            d.rounded_rectangle((90,343,279,384),radius=7,fill='#C2D7C1')
            d.text((106,354),'Eu vou.',font=font(20),fill='#305350')
    elif kind=='unsent':
        d.text((40,115),'Conversa do trabalho',font=font(17),fill='#456569')
        phrase='Eu tenho os recibos.'
        length=round(len(phrase)*min(1,t/1.8)) if t<2.3 else max(0,len(phrase)-round((t-2.3)*10))
        d.rounded_rectangle((27,186,283,248),radius=7,fill='#CADCC6')
        d.text((35,210),phrase[:length]+'│',font=font(18),fill='#344C47')
        d.rectangle((20,285,290,420),fill='#C8D4CB')
        for row in range(3):
            for col in range(9):d.rectangle((26+col*29,297+row*34,48+col*29,323+row*34),fill='#F0F2E8')
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
    if kind in ('agreement','receipt','route'):
        item=paper(kind,t,u);x=480
        if s.get('action') in ('slide','place'):x=615-135*min(1,t/1.4)
        place(im,item,x,457)
        if s.get('action')=='highlight':
            y=328 if kind=='agreement' else 241
            d.rectangle((x-219,y,x+211,y+39),outline='#AE664A',width=3)
        if s.get('action') in ('slide','place'):
            hx=x+220;hy=352
            d.polygon([(hx,hy),(hx+65,hy-9),(W,hy+2),(W,hy+40),(hx+70,hy+31),(hx,hy+22)],fill='#C79C73')
        if kind=='agreement':
            d.line((757,366,812,458),fill='#293B48',width=8)
            d.polygon([(807,454),(816,460),(819,476)],fill='#BFA981')
    elif kind in ('order-compare','route-compare','delivery-proof','archive','meeting-documents'):
        if kind=='order-compare':
            left=phone('order',t,u).resize((257,377),Image.Resampling.NEAREST)
            right=phone('shipment',t,u,'ONTEM').resize((257,377),Image.Resampling.NEAREST)
            place(im,left,286,485);place(im,right,680,485)
            if t>.8:d.line((425,324,540,324),fill=GOLD,width=4)
        elif kind=='route-compare':
            left=phone('shipment',t,u,'ONTEM').resize((257,377),Image.Resampling.NEAREST)
            right=paper('route',t,u).resize((400,285),Image.Resampling.NEAREST)
            place(im,left,250,485);place(im,right,703,451)
            d.rectangle((151,252,355,288),outline='#B96A50',width=3)
            d.rectangle((520,244,882,284),outline='#5A978A',width=3)
        elif kind=='delivery-proof':
            footage=cctv(t).resize((407,229),Image.Resampling.NEAREST)
            im.alpha_composite(footage,(30,181))
            place(im,paper('receipt',t,u).resize((423,304),Image.Resampling.NEAREST),719,456)
            d.rectangle((26,177,441,414),outline='#789A9F',width=3)
        elif kind=='archive':
            place(im,paper('receipt',t,u),441,459)
            camera=phone('rescue',t,u).resize((174,255),Image.Resampling.NEAREST)
            cd=ImageDraw.Draw(camera)
            cd.rectangle((9,19,165,235),fill='#243744')
            cd.text((18,27),'Câmera',font=font(12),fill='#EDEAD8')
            im.alpha_composite(camera,(696,263))
            d.rectangle((708,297,858,473),fill='#203E4A')
            view=paper('receipt',t,u).resize((123,89),Image.Resampling.NEAREST)
            im.alpha_composite(view,(720,332))
            if .7<t<.88:d.rectangle((708,297,858,473),fill='#E1E7D2')
        else:
            place(im,paper('agreement',t,u).resize((390,281),Image.Resampling.NEAREST),288,470)
            sheet=paper('route' if s.get('action')=='route' else 'receipt',t,u).resize((430,309),Image.Resampling.NEAREST)
            x=783-125*min(1,t/1.5)
            place(im,sheet,x,430)
            hx=x+203
            d.polygon([(hx,300),(W,313),(W,358),(hx,334)],fill='#B78565')
            if s.get('action')=='route' and t>.6:
                d.rectangle((493,316,855,357),outline='#AC664B',width=3)
                px=690;py=315
                d.polygon([(px,py),(px+18,py),(px+27,285),(px+42,254),(px+30,248),(px+13,283)],fill='#CFA783')
    elif kind=='record':
        item=phone('mauro',t,u)
        dd=ImageDraw.Draw(item)
        dd.rectangle((17,34,293,81),fill='#275C62')
        dd.text((33,44),'Áudio',font=font(21),fill='#F3EADF')
        dd.rectangle((17,81,293,420),fill='#172A37')
        dd.text((37,111),'Gravador',font=font(26),fill='#E8E4D0')
        for k in range(25):
            x=34+k*10;amplitude=6+abs(math.sin(k*1.8+t*2))*26
            dd.line((x,222-amplitude,x,222+amplitude),fill='#71AAA5',width=3)
        dd.ellipse((127,315,183,371),fill='#A65051')
        dd.rectangle((146,334,164,352),fill='#F0D8C1')
        place(im,item,480,504)
    elif kind in ('confession','report'):
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
        item=phone(s.get('phone','viral'),t,u,'HOJE' if s['paragraph']<9 else 'ONTEM')
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
        right=paper('receipt',t,u).resize((390,302),Image.Resampling.NEAREST)
        place(im,left,259,452);place(im,right,695,452)
        if t>.6:
            d.rectangle((208,254,423,289),outline='#B8654C',width=4)
            d.rectangle((519,256,868,291),outline='#B8654C',width=4)
            d.line((424,272,515,272),fill='#D4A252',width=3)
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
    if s.get('dispatch_monitor'):
        d.rectangle((93,135,275,232),fill='#152C39',outline='#729496',width=2)
        d.rectangle((93,135,275,155),fill='#35696E')
        d.text((104,140),'VIAGENS',font=font(11),fill='#F0E4C8')
        for k in range(4):
            y=168+k*13
            d.line((104,y,257,y),fill='#709D98',width=2)
        mx=122+min(105,t*16)
        d.polygon([(mx,188),(mx,197),(mx+8,194)],fill='#F0E4CD')
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
    if s.get('conference_table'):
        d=ImageDraw.Draw(im)
        d.polygon([(187,336),(805,336),(862,359),(138,359)],fill='#937249',outline='#4A4033')
        d.rectangle((138,359,862,378),fill='#705539',outline='#453C31',width=2)
        for x in (167,826):d.rectangle((x,376,x+18,526),fill='#4A3C2B')
        shift=round(15*min(1,t/1.3)) if s.get('papers_move') else 0
        d.polygon([(404+shift,344),(535+shift,344),(550+shift,356),(393+shift,356)],fill='#EDE9D9',outline='#A4A48A')
        d.line((577,348,618,355),fill='#233844',width=4)
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
        if s['paragraph']>=47:d.rectangle((635,282,669,292),fill='#15222D')
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
        for value,y,size in [('Fio de Lume',165,35),('PARTE 2 DE 4',224,19),('Continua na parte 3',275,27),('O valor que ninguém via',322,23)]:
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
    chords=[(110.0,130.813,164.814),(87.307,110.0,130.813),
            (97.999,123.471,146.832),(82.407,97.999,123.471)]
    reveal=next(s['start_seconds'] for s in shots if s['paragraph']==56)
    rng=np.random.default_rng(1902)
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
        if s['bg'] in ('warehouse','loading','street','depot','cafe','gate') and not s.get('detail'):
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
        if s.get('prop') in ('confession','report','bills','receipt','route','agreement','meeting-documents'):
            t=np.arange(round(.25*sr))/sr
            noise=signal.sosfilt(signal.butter(2,[900,4000],btype='band',fs=sr,output='sos'),rng.standard_normal(len(t)))
            rustle=noise*np.exp(-t*15)*.015
            audio[pos:pos+len(rustle)]+=rustle[:,None]
    end=next(s['start_seconds'] for s in shots if s.get('closing'))
    # A very brief original minor chord arrives only after the last question.
    t=np.arange(round((total-end)*sr))/sr
    hit=sum(np.sin(2*np.pi*f*t) for f in (55.0,65.406,82.407))*.018
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




