# -*- coding: utf-8 -*-
"""XL 텍스트 블록 - 파서와 재구성

레이아웃 (전부 리틀엔디언):
  0x00 u32  magic 0x134C58
  0x04 u32  하위 16비트만 총 크기와 일치한다(상위 16비트는 별개 값).
  0x08 u16  엔트리 수
  0x0A u16  엔트리 폭 (4 / 8 / 18 / 64 ... 관측)
  0x0C u32  표 시작 (hdr, 관측상 0x14 또는 0x1C)
  hdr~      엔트리 배열. 표 바로 다음(hdr + cnt*w)부터 문자열 영역이다.

엔트리 안에서 offset 필드가 몇 개이고 어디 있는지는 폭마다 다르다.
  w=4   offset 1개
  w=8   id + offset
  w=18  메타 14바이트 + offset 1개
  w=64  offset 16개 (캐릭터 이름의 표기 변형들)
그래서 위치를 가정하지 않고, 4바이트 정렬된 모든 자리 중
'전 행에서 문자열 영역을 가리키거나 비어 있는' 열을 offset 열로 판정한다.

이렇게 하면 문자열을 가리키는 참조를 빠짐없이 알 수 있으므로 문자열 영역을
통째로 다시 깔 수 있다. 개별 문자열 길이 제한이 사라지고 제약은 총량만 남는다.
표가 가리키지 않는 바이트가 남아 있으면 구조를 잘못 읽은 것으로 보고 손대지 않는다.
"""
import struct
import numpy as np

MAGIC = 0x134C58
NUL = bytes(1)
EMPTY = (0, 0xFFFFFFFF)


def _offset_cols(blob, hdr, cnt, w, tot):
    """엔트리 안에서 offset 이 들어 있는 바이트 위치 목록"""
    lo, hi = cnt * w, tot - hdr
    cand = sorted({p for p in range(0, w - 3, 4)} | {w - 4})
    arr = np.frombuffer(blob[hdr:hdr + cnt * w], dtype=np.uint8).reshape(cnt, w)
    cols = []
    for p in cand:
        u = arr[:, p:p + 4].copy().view('<u4').ravel()
        valid = (u >= lo) & (u < hi)
        empty = (u == 0) | (u == 0xFFFFFFFF)
        if valid.any() and bool((valid | empty).all()):
            cols.append(p)
    return cols


def _end(blob, a, tot, wide):
    """문자열 끝 위치. UTF-16 은 짝수 경계의 널 두 바이트가 끝이다."""
    if not wide:
        e = blob.find(NUL, a, tot)
        return e if e >= 0 else tot
    i = a
    while i + 1 < tot:
        if blob[i] == 0 and blob[i + 1] == 0:
            return i
        i += 2
    return tot


def parse(blob, wide=False):
    """(hdr, cnt, w, tot, [(참조위치, offset, bytes|None)]) 또는 None

    참조위치는 offset 필드의 blob 내 절대 바이트 위치다(재구성 때 이 자리를 고쳐 쓴다).
    wide=True 면 문자열을 UTF-16 로 읽는다(훈장이 든 2/x/7 블록).
    """
    if len(blob) < 0x18 or struct.unpack_from('<I', blob, 0)[0] != MAGIC:
        return None
    if (struct.unpack_from('<I', blob, 4)[0] & 0xFFFF) != (len(blob) & 0xFFFF):
        return None
    tot = len(blob)
    cnt, w = struct.unpack_from('<HH', blob, 8)
    hdr = struct.unpack_from('<I', blob, 12)[0]
    if w < 4 or cnt == 0 or hdr < 0x10 or hdr + cnt * w >= tot:
        return None
    cols = _offset_cols(blob, hdr, cnt, w, tot)
    if not cols:
        return None
    refs = []
    for k in range(cnt):
        row = hdr + k * w
        for p in cols:
            off = struct.unpack_from('<I', blob, row + p)[0]
            if off in EMPTY:
                refs.append((row + p, off, None)); continue
            a = hdr + off
            refs.append((row + p, off, blob[a:_end(blob, a, tot, wide)]))
    return hdr, cnt, w, tot, refs


def _str_base(hdr, cnt, w, refs):
    """재배치 구역의 시작(절대). 표가 가리키는 가장 앞 문자열부터다."""
    offs = [o for _, o, s in refs if s is not None]
    return hdr + (min(offs) if offs else cnt * w)


def capacity(blob, wide=False):
    g = parse(blob, wide)
    if g is None:
        return 0
    hdr, cnt, w, tot, refs = g
    return tot - _str_base(hdr, cnt, w, refs)


def rebuild(blob, repl, wide=False):
    """repl: {참조위치: 새 bytes}. 같은 크기의 blob 을 돌려준다.

    표가 가리키지 않는 바이트가 재배치 구역에 남아 있으면 ValueError,
    문자열이 넘치면 OverflowError.
    wide=True 면 UTF-16 문자열로 다룬다(종료 널 두 바이트, 짝수 정렬).
    """
    g = parse(blob, wide)
    if g is None:
        raise ValueError('XL 아님')
    hdr, cnt, w, tot, refs = g
    base = _str_base(hdr, cnt, w, refs)
    limit = tot - base
    unit = 2 if wide else 1

    segs = sorted({(o, len(s) + unit) for _, o, s in refs if s is not None})
    stray, prev = 0, 0
    for o, l in segs:
        a = o - (base - hdr)
        if a > prev:
            gap = blob[base + prev:base + a]
            stray += len(gap) - gap.count(0)
        prev = max(prev, a + l)
    if prev < limit:
        gap = blob[base + prev:tot]
        stray += len(gap) - gap.count(0)
    if stray:
        raise ValueError('미참조 데이터 %d바이트 — 표 구조를 신뢰할 수 없다' % stray)

    out = bytearray(blob)
    pool, buf = {}, bytearray()
    for pos, off, s in refs:
        if s is None:
            continue                       # 빈 offset 은 그대로 둔다
        v = repl.get(pos, s)
        if v not in pool:
            if v == b'' and buf:
                pool[v] = len(buf) - unit  # 앞 문자열의 종료 널을 재활용
            else:
                pool[v] = len(buf)
                buf += v + NUL * unit
        struct.pack_into('<I', out, pos, base - hdr + pool[v])
    if len(buf) > limit:
        raise OverflowError('문자열 영역 초과: %d > %d' % (len(buf), limit))
    out[base:base + len(buf)] = buf
    out[base + len(buf):tot] = NUL * (limit - len(buf))
    assert len(out) == len(blob)
    return bytes(out)
