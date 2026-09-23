# -*- coding: utf-8 -*-
"""한글 글리프 렌더 후보 비교"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def render(ch, spec):
    """spec: dict(font, index, size, weight, ss, bold, dy, dx, gamma)"""
    ss = spec.get('ss', 4)                       # 슈퍼샘플 배수
    sz = spec['size'] * ss
    f = ImageFont.truetype(spec['font'], sz, index=spec.get('index', 0))
    if spec.get('weight'):
        try: f.set_variation_by_axes([spec['weight']])
        except Exception: pass
    big = Image.new('L', (16*ss, 16*ss), 0)
    ImageDraw.Draw(big).text((8*ss + spec.get('dx',0)*ss, 8*ss + spec.get('dy',0)*ss),
                             ch, font=f, fill=255, anchor='mm',
                             stroke_width=spec.get('bold', 0)*ss)
    im = big.resize((16,16), Image.LANCZOS) if ss > 1 else big
    a = np.asarray(im, np.float32)/255.0
    g = spec.get('gamma', 1.0)
    if g != 1.0: a = a ** g
    return np.clip((a*15+0.5).astype(np.int32),0,15).astype(np.uint8)*17

MG  = 'C:/Windows/Fonts/malgun.ttf'
MGB = 'C:/Windows/Fonts/malgunbd.ttf'
GUL = 'C:/Windows/Fonts/gulim.ttc'
NOTO= 'C:/Windows/Fonts/NotoSansKR-VF.ttf'

CANDS = [
 ('굴림 비트맵(현재)', dict(font=GUL, index=0, size=16, ss=1)),
 ('돋움 비트맵',       dict(font=GUL, index=2, size=16, ss=1)),
 ('맑은고딕 14',       dict(font=MG,  size=14)),
 ('맑은고딕 15',       dict(font=MG,  size=15)),
 ('맑은고딕B 14',      dict(font=MGB, size=14)),
 ('맑은고딕B 15',      dict(font=MGB, size=15)),
 ('Noto 500 15',       dict(font=NOTO, size=15, weight=500)),
 ('Noto 600 15',       dict(font=NOTO, size=15, weight=600)),
 ('Noto 700 15',       dict(font=NOTO, size=15, weight=700)),
 ('Noto 700 16',       dict(font=NOTO, size=16, weight=700)),
 ('Noto 600 16 γ0.8',  dict(font=NOTO, size=16, weight=600, gamma=0.8)),
 ('Noto 500 16 γ0.75', dict(font=NOTO, size=16, weight=500, gamma=0.75)),
]
