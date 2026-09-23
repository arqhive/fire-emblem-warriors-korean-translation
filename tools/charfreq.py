# -*- coding: utf-8 -*-
"""스크립트 문자 빈도 — 제어코드 제거 후 XL 파일 단위로 '진짜 텍스트'만 선별"""
import sys, os, struct, collections
sys.path.insert(0, os.path.dirname(__file__))
from linkdata import LinkData, walk
from xltext import parse, XL_MAGIC

def strip_ctrl(b):
    """ESC 제어 시퀀스 제거.  ESC+c  (c in 'APF' 면 인자 1바이트 더)"""
    out = bytearray(); i = 0; n = len(b)
    while i < n:
        c = b[i]
        if c == 0x1b:
            i += 2
            if i - 1 < n and b[i-1] in (0x41, 0x50, 0x46):   # 'A','P','F' 는 인자 1바이트
                i += 1
            continue
        out.append(c); i += 1
    return bytes(out)

EXTRA = {0x00b0, 0x00d7, 0x00f7, 0x00a5, 0x2026, 0x2015, 0x301c, 0x00b1}

def sane(c):
    o = ord(c)
    return ((0x20 <= o < 0x7f) or (0x3000 <= o <= 0x30ff) or (0x4e00 <= o <= 0x9fff)
            or (0xff01 <= o <= 0xff9f) or (0x2010 <= o <= 0x2e7f) or o in (0x0a, 0x09)
            or o in EXTRA)

def scan(idx, binf, file_ratio=0.90, min_ok=1):
    ld = LinkData(idx, binf)
    freq = collections.Counter(); seen = set()
    nfile = ngood = 0
    for i, sz, off in ld.used():
        for p, blob in walk(ld.read(i), str(i)):
            if len(blob) < 0x18 or struct.unpack_from('<I', blob, 0)[0] != XL_MAGIC:
                continue
            r = parse(blob)
            if not r:
                continue
            nfile += 1
            ok = bad = 0; msgs = []
            for tid, s in r:
                if not s or len(s) > 800:
                    continue
                t0 = strip_ctrl(s)
                try:
                    t = t0.decode('cp932')
                except Exception:
                    bad += 1; continue
                if all(sane(c) for c in t):
                    ok += 1; msgs.append((s, t))
                else:
                    bad += 1
            if ok + bad == 0 or ok < (ok + bad) * file_ratio or ok < min_ok:
                continue
            ngood += 1
            for s, t in msgs:
                if s in seen: continue
                seen.add(s); freq.update(t)
    return freq, nfile, ngood, len(seen)
