# -*- coding: utf-8 -*-
"""아틀라스 셀 <-> SJIS 코드 전수 매핑"""
import sys, os, json, io
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def sjis_codes():
    out = []
    for lead in list(range(0x81, 0xA0)) + list(range(0xE0, 0xF0)):
        for trail in range(0x40, 0xFD):
            if trail == 0x7F: continue
            b = bytes([lead, trail])
            try: c = b.decode('cp932')
            except Exception: continue
            out.append((b, c))
    return out

def render_all(chars, fonts, sizes):
    """(variant, N, 16,16) float32"""
    outs = []
    for fp, idx in fonts:
        for sz in sizes:
            f = ImageFont.truetype(fp, sz, index=idx)
            arr = np.zeros((len(chars), 16, 16), np.float32)
            for i, c in enumerate(chars):
                im = Image.new('L', (16, 16), 0)
                ImageDraw.Draw(im).text((8, 8), c, font=f, fill=255, anchor='mm')
                arr[i] = np.asarray(im, np.float32)
            outs.append(arr)
    return outs

def nrm(v):
    v = v.reshape(len(v), -1)
    v = v - v.mean(1, keepdims=True)
    n = np.linalg.norm(v, axis=1, keepdims=True); n[n == 0] = 1
    return v / n

def score_matrix(cells, variants, shifts=(-1, 0, 1)):
    A = nrm(cells.astype(np.float32))
    S = np.full((len(cells), variants[0].shape[0]), -1, np.float32)
    for arr in variants:
        for dy in shifts:
            for dx in shifts:
                g = np.roll(np.roll(arr, dy, axis=1), dx, axis=2)
                S = np.maximum(S, A @ nrm(g).T)
    return S

def align_anchored(S, anchors):
    """단조증가 DP. anchors: {cell_row: code_col} 하드 고정"""
    C, K = S.shape
    idx = np.arange(K)
    NEG = -1e9
    prev = S[0].astype(np.float32).copy()
    if 0 in anchors:
        m = np.full(K, NEG, np.float32); m[anchors[0]] = prev[anchors[0]]; prev = m
    bk = np.zeros((C, K), np.int16)
    for i in range(1, C):
        run = np.maximum.accumulate(prev)
        arg = np.maximum.accumulate(np.where(prev >= run, idx, -1)).astype(np.int16)
        cur = np.full(K, NEG, np.float32)
        cur[1:] = run[:-1] + S[i, 1:]
        bk[i, 1:] = arg[:-1]
        if i in anchors:
            a = anchors[i]; v = cur[a]
            cur[:] = NEG; cur[a] = v
        prev = cur
    path = np.zeros(C, np.int32); path[-1] = int(np.argmax(prev))
    for i in range(C - 1, 0, -1):
        path[i-1] = bk[i, path[i]]
    return path
