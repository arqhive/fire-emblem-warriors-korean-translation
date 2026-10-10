# -*- coding: utf-8 -*-
"""전자 설명서(본편 content 1 의 Manual.bcma) 그림을 한글판으로 바꾼다.

  python tools/manual_patch.py [출력=work/builds/out/manual/Manual.bcma]

구조: Manual.bcma = darc ─ JPN_ja_texture.arc (LZ10 압축) = darc ─ *.bclim
그림(BCLIM)은 크기가 그대로라 안쪽 darc 에서 제자리 교체 → LZ10 으로 다시 압축 → 겉 darc 맨 끝 항목만 갈아 끼운다.
입력 그림: translation/graphics/manual/<bclim 이름>.png (GPT 결과, 게임 크기). 원본: extract/manual/Manual.bcma
"""
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from survey_graphics import morton_addr

SRC = Path('extract/manual/Manual.bcma')
IMAGES = Path('translation/graphics/manual')


# ---------------------------------------------------------------- LZ10

def lz10_decompress(b):
    assert b[0] == 0x10
    size = int.from_bytes(b[1:4], 'little')
    out, i = bytearray(), 4
    while len(out) < size:
        flags = b[i]; i += 1
        for k in range(8):
            if len(out) >= size:
                break
            if flags & (0x80 >> k):
                x = (b[i] << 8) | b[i + 1]; i += 2
                n, disp = (x >> 12) + 3, (x & 0xFFF) + 1
                for _ in range(n):
                    out.append(out[-disp])
            else:
                out.append(b[i]); i += 1
    return bytes(out)


def lz10_compress(data):
    """탐욕 LZ10(창 4096, 길이 3~18). 3바이트 머리말 위치 목록으로 찾는다."""
    n = len(data)
    out = bytearray([0x10]) + n.to_bytes(3, 'little')
    heads, i = {}, 0
    while i < n:
        flag_pos = len(out); out.append(0); flags = 0
        for k in range(8):
            if i >= n:
                break
            best_len, best_disp = 0, 0
            if i + 3 <= n:
                for j in reversed(heads.get(data[i:i + 3], ())):
                    if i - j > 4096:
                        break
                    m = 3
                    while m < 18 and i + m < n and data[j + m] == data[i + m]:
                        m += 1
                    if m > best_len:
                        best_len, best_disp = m, i - j
                        if m == 18:
                            break
            step = best_len if best_len >= 3 else 1
            if best_len >= 3:
                flags |= 0x80 >> k
                x = ((best_len - 3) << 12) | (best_disp - 1)
                out += bytes([x >> 8, x & 0xFF])
            else:
                out.append(data[i])
            for p in range(i, i + step):
                if p + 3 <= n:
                    lst = heads.setdefault(data[p:p + 3], [])
                    lst.append(p)
                    if len(lst) > 64:
                        del lst[0]
            i += step
        out[flag_pos] = flags
    return bytes(out)


# ---------------------------------------------------------------- darc

def darc_files(d):
    """→ [(이름, 표 번호, 오프셋, 크기)] 파일만"""
    _m, _bom, _hl, _v, _size, tab_off, _tl, _do = struct.unpack_from('<4sHHIIIII', d, 0)
    n = struct.unpack_from('<III', d, tab_off)[2]
    names = tab_off + n * 12
    out = []
    for i in range(1, n):
        no, off, sz = struct.unpack_from('<III', d, tab_off + i * 12)
        raw = d[names + (no & 0xFFFFFF):]
        k = 0
        while raw[k:k + 2] != b'\0\0':
            k += 2
        if not no >> 24:
            out.append((raw[:k].decode('utf-16-le'), i, off, sz))
    return out


# ---------------------------------------------------------------- BCLIM

def clim_info(b):
    i = b.rfind(b'CLIM')
    im = b.find(b'imag', i)
    w, h, fmt = struct.unpack_from('<HHI', b, im + 8)
    pw = 1 << max(3, (w - 1).bit_length())
    ph = 1 << max(3, (h - 1).bit_length())
    return i, w, h, fmt, pw, ph


def clim_encode(b, img):
    """같은 형식·크기로 다시 쓴다. 그림 밖 여백(2의 거듭제곱까지)은 원본 화소를 둔다."""
    data_len, w, h, fmt, pw, ph = clim_info(b)
    addr = morton_addr(pw, ph)
    src = np.asarray(img.convert('RGBA'), dtype=np.uint16)
    if src.shape[:2] != (h, w):
        raise ValueError('그림 크기가 다르다: %s vs %dx%d' % (src.shape, w, h))
    if fmt == 7:                     # RGBA5551
        cur = np.frombuffer(b[:data_len], '<u2').copy()
        full = cur[addr]
        r, g, bl, a = src[..., 0] >> 3, src[..., 1] >> 3, src[..., 2] >> 3, (src[..., 3] >= 128).astype(np.uint16)
        full[:h, :w] = (r << 11) | (g << 6) | (bl << 1) | a
        cur[addr] = full
        data = cur.astype('<u2').tobytes()
    elif fmt == 9:                   # RGBA8 (바이트 순서 ABGR)
        cur = np.frombuffer(b[:data_len], np.uint8).reshape(-1, 4).copy()
        full = cur[addr]
        full[:h, :w] = src[..., ::-1].astype(np.uint8)
        cur[addr] = full
        data = cur.tobytes()
    else:
        raise ValueError('지원하지 않는 BCLIM 형식 %d' % fmt)
    assert len(data) == data_len
    return data + b[data_len:]


# ---------------------------------------------------------------- 본체

def build(out):
    outer = SRC.read_bytes()
    files = {name: (i, off, sz) for name, i, off, sz in darc_files(outer)}
    idx, off, sz = files['JPN_ja_texture.arc']
    _m, _bom, _hl, _v, _size, tab_off, _tl, _do = struct.unpack_from('<4sHHIIIII', outer, 0)
    if off + sz != len(outer):
        raise ValueError('텍스처 묶음이 맨 끝이 아니다')
    inner = bytearray(lz10_decompress(outer[off:off + sz]))
    done = []
    for png in sorted(IMAGES.glob('*.png')):
        name = png.stem + '.bclim'
        hit = [(o, s) for nm, _i, o, s in darc_files(bytes(inner)) if nm == name]
        if not hit:
            raise KeyError(name)
        o, s = hit[0]
        new = clim_encode(bytes(inner[o:o + s]), Image.open(png))
        assert len(new) == s
        inner[o:o + s] = new
        done.append(name)
    packed = lz10_compress(bytes(inner))
    assert lz10_decompress(packed) == bytes(inner)
    res = bytearray(outer[:off]) + packed
    struct.pack_into('<I', res, 12, len(res))                      # 파일 전체 크기
    struct.pack_into('<I', res, tab_off + idx * 12 + 8, len(packed))  # 항목 크기
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(bytes(res))
    # 되읽어 확인
    back = lz10_decompress(bytes(res)[off:off + len(packed)])
    assert back == bytes(inner)
    print('설명서 그림 %d장 교체: %s → %s (%s → %s 바이트)' % (len(done), ', '.join(done), out,
                                                       format(len(outer), ','), format(len(res), ',')))
    return done


def roundtrip_check():
    """원본 BCLIM 을 그대로 풀었다 다시 써도 바이트가 같은지(인코더 검증)."""
    from survey_extra_images import decode_clim
    inner = lz10_decompress(SRC.read_bytes()[67488:])
    for name, _i, o, s in darc_files(inner):
        if name not in ('battle_01.bclim', 'battle_02.bclim', 'amiibo_logo_c.bclim'):
            continue
        b = inner[o:o + s]
        data_len, w, h, fmt, pw, ph = clim_info(b)
        img = Image.fromarray(decode_clim(fmt, b[:data_len], pw, ph)[:h, :w])
        print(name, '왕복 일치' if clim_encode(b, img) == b else '★ 왕복 불일치')


if __name__ == '__main__':
    if '--check' in sys.argv:
        roundtrip_check()
    else:
        build(Path(sys.argv[1] if len(sys.argv) > 1 else 'work/builds/out/manual/Manual.bcma'))
