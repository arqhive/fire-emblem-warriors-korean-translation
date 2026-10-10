# -*- coding: utf-8 -*-
"""G1T 텍스처 전수 조사: 원본 아카이브의 모든 텍스처를 PNG 로 풀고, 빌드에서 바뀐 것을 표시한다.

  python tools/survey_graphics.py

대상: 본편·업데이트 LINKDATA, DLC c1~c4 의 모든 자원 속 GT1G (부모 자원 안 어디에 있든).
같은 그림(0레벨 데이터 해시가 같은 것)은 한 번만 푼다.
결과: work/survey/tex/<id>.png (원본), work/survey/tex_ko/<id>.png (빌드에서 바뀐 것의 현재판),
      work/survey/graphics.json (텍스처별 위치·형식·크기·모델 자원 여부·바뀜 여부)
"""
import collections
import hashlib
import json
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g1t
from ctrtex import _idx, etc1a4_rgba, morton8_abgr32_rgba
from extract_text import walk_abs
from linkdata import LinkData

OUT = Path('work/survey')
BPP = {72: 1.0, 71: 0.5, 9: 4.0, 44: 1.0, 24: 1.0}


def morton_addr(W, H):
    y, x = np.indices((H, W))
    a = (y // 8 * (W // 8) + x // 8) * 64
    for bit in range(3):
        a += ((x >> bit) & 1) << (2 * bit)
        a += ((y >> bit) & 1) << (2 * bit + 1)
    return a


def etc1_rgba(data, W, H, flip=True):
    """ETC1(알파 없음): ETC1A4 디코더에 알파 0xFF 블록을 끼워 재사용한다."""
    n = W * H // 16
    blocks = np.frombuffer(data[:n * 8], dtype='<u8')
    fake = np.empty(n * 2, dtype='<u8')
    fake[0::2] = 0xFFFFFFFFFFFFFFFF
    fake[1::2] = blocks
    return etc1a4_rgba(fake.tobytes(), W, H, flip)


def l8_rgba(data, W, H, flip=True):
    v = np.frombuffer(data[:W * H], dtype=np.uint8)[morton_addr(W, H)]
    out = np.stack([v, v, v, np.full_like(v, 255)], -1)
    return out[::-1] if flip else out


def decode(fmt, data, W, H):
    if fmt == 72:
        return etc1a4_rgba(data, W, H)
    if fmt == 71:
        return etc1_rgba(data, W, H)
    if fmt == 9:
        return morton8_abgr32_rgba(data, W, H)
    if fmt in (44, 24):
        return l8_rgba(data, W, H)
    raise ValueError(fmt)


def textures_in(blob):
    """blob 안의 모든 GT1G → [(G1T 시작, [(번호, 형식, 폭, 높이, 0레벨 데이터)])]"""
    out, start = [], 0
    while True:
        pos = blob.find(b'GT1G', start)
        if pos < 0:
            return out
        start = pos + 4
        if pos + 28 > len(blob):
            continue
        total = struct.unpack_from('<I', blob, pos + 8)[0]
        if total < 28 or pos + total > len(blob):
            continue
        data = blob[pos:pos + total]
        ts = g1t.parse(data)
        if not ts:
            continue
        rows = []
        for i, (fmt, w, h, mip, p) in enumerate(ts):
            flags = int.from_bytes(data[p + 4:p + 8], 'little')
            ext = int.from_bytes(data[p + 8:p + 12], 'little') if flags & 0x10000000 else 0
            q = p + 8 + ext
            size = int(w * h * BPP.get(fmt, 0))
            rows.append((i, fmt, w, h, data[q:q + size]))
        out.append((pos, rows))


def main():
    (OUT / 'tex').mkdir(parents=True, exist_ok=True)
    (OUT / 'tex_ko').mkdir(parents=True, exist_ok=True)
    targets = [('base', 'extract/base', 'work/builds/out/base/romfs'),
               ('update', 'extract/update', 'work/builds/out/update_resources/romfs')]
    for t in ('c1', 'c2', 'c3', 'c4'):
        targets.append((t, 'work/survey/_orig_' + t, 'work/survey/_dlc_' + t))
    uniq, refs = {}, collections.defaultdict(list)
    stats = collections.Counter()
    for tag, odir, bdir in targets:
        lo = LinkData(odir + '/LINKDATA.idx', odir + '/LINKDATA.bin')
        lb = LinkData(bdir + '/LINKDATA.idx', bdir + '/LINKDATA.bin')
        print('훑는 중:', tag, flush=True)
        for slot, size, _off in lo.used():
            od = lo.read(slot)
            if b'GT1G' not in od:
                continue
            bd = lb.read(slot)
            has_model = b'_M1G' in od
            O = {p: b for p, a, b in walk_abs(od, 0, str(slot))}
            B = {p: b for p, a, b in walk_abs(bd, 0, str(slot))}
            for path, blob in O.items():
                bt = {pos: rows for pos, rows in textures_in(B.get(path, b''))}
                for pos, rows in textures_in(blob):
                    stats['G1T'] += 1
                    for i, fmt, w, h, payload in rows:
                        stats['텍스처'] += 1
                        if fmt not in BPP or len(payload) < w * h * BPP[fmt] or w < 8 or h < 8:
                            stats['건너뜀(형식·크기)'] += 1
                            continue
                        key = hashlib.sha1(payload).hexdigest()[:16]
                        now = next((r[4] for r in bt.get(pos, []) if r[0] == i), None)
                        changed = now is not None and now != payload
                        refs[key].append(dict(tag=tag, path=path, slot=slot, g1t=pos, index=i, model=has_model,
                                              changed=changed))
                        if key not in uniq:
                            uniq[key] = dict(id=key, fmt=fmt, w=w, h=h)
                            try:
                                Image.fromarray(decode(fmt, payload, w, h)).save(OUT / 'tex' / (key + '.png'))
                            except Exception as e:
                                uniq[key]['error'] = str(e)
                                stats['디코딩 실패'] += 1
                        if changed:
                            kk = key + '_' + hashlib.sha1(now).hexdigest()[:8]
                            if not (OUT / 'tex_ko' / (kk + '.png')).exists():
                                Image.fromarray(decode(fmt, now, w, h)).save(OUT / 'tex_ko' / (kk + '.png'))
                            refs[key][-1]['now'] = kk
    for k, u in uniq.items():
        u['refs'] = refs[k]
        u['model_only'] = all(r['model'] for r in refs[k])
        u['changed'] = any(r['changed'] for r in refs[k])
    json.dump(dict(stats=dict(stats), textures=list(uniq.values())),
              open(OUT / 'graphics.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(dict(stats))
    c = collections.Counter((u['model_only'], u['changed']) for u in uniq.values())
    print('고유 텍스처', len(uniq), '(모델 자원만, 바뀜) 분포', dict(c))


if __name__ == '__main__':
    main()
