# -*- coding: utf-8 -*-
"""LINKDATA 밖 그림: 전자 설명서 BCLIM 51장, DLC 아이콘(.icn) 5개, SMDH 아이콘 → work/survey/extra_png/

  python tools/survey_extra_images.py      (survey_untranslated 단계에서 work/survey/extra 에 원본을 꺼내 둔 뒤)
"""
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ctrtex import etc1a4_rgba
from survey_graphics import etc1_rgba, morton_addr

SRC = Path('work/survey/extra')
OUT = Path('work/survey/extra_png')


def unswizzle(pixels, W, H):
    """morton 순서로 저장된 픽셀 배열(N, C) → (H, W, C)"""
    return pixels[morton_addr(W, H)]


def rgb565(raw, W, H):
    v = np.frombuffer(raw[:W * H * 2], dtype='<u2')
    r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
    px = np.stack([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2), np.full_like(r, 31) * 8 + 7], -1)
    return unswizzle(px.astype(np.uint8), W, H)


def decode_clim(fmt, raw, W, H):
    n = W * H
    if fmt == 9:   # RGBA8 (ABGR 바이트)
        px = np.frombuffer(raw[:n * 4], np.uint8).reshape(-1, 4)[:, ::-1]
        return unswizzle(px, W, H)
    if fmt == 6:   # RGB8 (BGR)
        px = np.frombuffer(raw[:n * 3], np.uint8).reshape(-1, 3)[:, ::-1]
        return unswizzle(np.concatenate([px, np.full((n, 1), 255, np.uint8)], 1), W, H)
    if fmt == 5:
        return rgb565(raw, W, H)
    if fmt == 8:   # RGBA4
        v = np.frombuffer(raw[:n * 2], '<u2')
        px = np.stack([(v >> 12) & 15, (v >> 8) & 15, (v >> 4) & 15, v & 15], -1).astype(np.uint8) * 17
        return unswizzle(px, W, H)
    if fmt == 7:   # RGBA5551
        v = np.frombuffer(raw[:n * 2], '<u2')
        px = np.stack([((v >> 11) & 31) * 8, ((v >> 6) & 31) * 8, ((v >> 1) & 31) * 8, (v & 1) * 255], -1).astype(np.uint8)
        return unswizzle(px, W, H)
    if fmt == 3:   # LA8
        v = np.frombuffer(raw[:n * 2], np.uint8).reshape(-1, 2)
        px = np.stack([v[:, 1], v[:, 1], v[:, 1], v[:, 0]], -1)
        return unswizzle(px, W, H)
    if fmt == 2:   # LA4
        v = np.frombuffer(raw[:n], np.uint8)
        px = np.stack([(v >> 4) * 17] * 3 + [(v & 15) * 17], -1).astype(np.uint8)
        return unswizzle(px, W, H)
    if fmt in (0, 1):   # L8 / A8
        v = np.frombuffer(raw[:n], np.uint8)
        px = np.stack([v, v, v, np.full_like(v, 255)] if fmt == 0 else [np.zeros_like(v)] * 3 + [v], -1)
        return unswizzle(px, W, H)
    if fmt in (12, 13):   # L4 / A4
        v = np.frombuffer(raw[:n // 2], np.uint8)
        nib = np.empty(n, np.uint8); nib[0::2] = v & 15; nib[1::2] = v >> 4
        nib *= 17
        px = np.stack([nib] * 3 + [np.full_like(nib, 255)], -1) if fmt == 12 else np.stack([np.zeros_like(nib)] * 3 + [nib], -1)
        return unswizzle(px, W, H)
    if fmt == 10:
        return etc1_rgba(raw, W, H, flip=False)
    if fmt == 11:
        return etc1a4_rgba(raw, W, H, flip=False)
    raise ValueError('BCLIM 형식 %d' % fmt)


def bclim(b):
    """→ (형식, 폭, 높이, RGBA). 꼬리 CLIM 헤더 + imag 블록."""
    i = b.rfind(b'CLIM')
    im = b.find(b'imag', i)
    W, H, fmt = struct.unpack_from('<HHI', b, im + 8)
    # 저장 크기는 2의 거듭제곱으로 올린 값
    pw = 1 << max(3, (W - 1).bit_length()); ph = 1 << max(3, (H - 1).bit_length())
    img = decode_clim(fmt, b[:i], pw, ph)
    return fmt, W, H, img[:H, :W]


def darc_items(d):
    magic, bom, hlen, ver, size, tab_off, tab_len, data_off = struct.unpack_from('<4sHHIIIII', d, 0)
    ent = lambda i: struct.unpack_from('<III', d, tab_off + i * 12)
    n = ent(0)[2]; nb = tab_off + n * 12; out = []
    for i in range(1, n):
        no, off, sz = ent(i)
        raw = d[nb + (no & 0xFFFFFF):]; k = 0
        while raw[k:k + 2] != b'\0\0':
            k += 2
        if not no >> 24:
            out.append((raw[:k].decode('utf-16-le'), d[off:off + sz]))
    return out


def main():
    (OUT / 'manual').mkdir(parents=True, exist_ok=True)
    (OUT / 'dlc_icons').mkdir(parents=True, exist_ok=True)
    rows = []
    for nm, b in darc_items((SRC / 'JPN_ja_texture.arc.bin').read_bytes()):
        try:
            fmt, W, H, img = bclim(b)
            Image.fromarray(img).save(OUT / 'manual' / (nm.rsplit('.', 1)[0] + '.png'))
            rows.append((nm, fmt, W, H))
        except Exception as e:
            print('실패', nm, e)
    print('설명서 그림', len(rows))
    for p in sorted(SRC.glob('*.icn')):
        Image.fromarray(rgb565(p.read_bytes(), 48, 48)).save(OUT / 'dlc_icons' / (p.stem + '.png'))
    print('DLC 아이콘', len(list(SRC.glob('*.icn'))))
    for nm, fmt, W, H in rows:
        print('  ', nm, fmt, W, H)


if __name__ == '__main__':
    main()
