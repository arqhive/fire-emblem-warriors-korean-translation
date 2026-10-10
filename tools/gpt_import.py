# -*- coding: utf-8 -*-
"""GPT 가 다시 그린 그림을 게임 텍스처로 인코딩하고 비교 시트를 만든다(빌드에는 아직 넣지 않는다).

  python tools/gpt_import.py            결과 폴더에 있는 것 전부
  python tools/gpt_import.py 01 05      번호를 골라서

입력: work/GPT/결과/게임크기/<저장할 이름> (없으면 work/GPT/결과/<저장할 이름> 을 게임 크기로 줄인다)
출력: work/GPT/반영/<번호>.payload.bin      게임 텍스처 그대로의 바이트(ETC1·ETC1A4·RGBA8)
      work/GPT/반영/gpt_manifest.json       native_manifest 와 같은 모양의 항목(넣을 위치·원본 해시)
      work/GPT/비교/비교_NN-NN.png          원본 | 현재 | GPT(인코딩했다 푼 모양), 3장씩
결과에 없는 번호는 건드리지 않는다(지금 판 유지).
전자 설명서 그림(17~19)은 설명서 묶음을 다시 만드는 단계가 없어 비교 시트만 만든다.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ctrtex import _idx
from ctrtex_encode import _colour_blocks, abgr32_encode, etc1a4_encode
from extract_text import walk_abs
from linkdata import LinkData
from survey_graphics import decode, textures_in

G = Path('work/GPT')
S = Path('work/survey')
FMT = {'ETC1': 71, 'ETC1A4': 72, 'RGBA8': 9}
SRC = {'base': 'extract/base', 'update': 'extract/update'}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def etc1_encode(rgba):
    """ETC1(투명 없음): ETC1A4 의 색 블록만. 블록 순서·Y 뒤집기는 etc1a4_encode 와 같다."""
    src = np.asarray(rgba, dtype=np.uint8)
    h, w, _ = src.shape
    y, x = _idx(w, h)
    blocks = src[::-1][y, x].reshape(-1, 16, 4).copy()
    blocks[:, :, 3] = 255
    return _colour_blocks(blocks).astype('<u8').tobytes()


def encode(fmt, rgba, original=None, region=None):
    if fmt == 71:
        return etc1_encode(rgba)
    if fmt == 72:
        return etc1a4_encode(rgba, original, region)[0]
    if fmt == 9:
        return abgr32_encode(rgba)
    raise ValueError(fmt)


def locate(tag, path, g1t_pos, index, fmt, w, h):
    """원본 아카이브에서 텍스처 payload 의 자원 안 위치와 원본 바이트"""
    ld = LinkData(SRC[tag] + '/LINKDATA.idx', SRC[tag] + '/LINKDATA.bin')
    slot = int(path.split('/')[0])
    res = ld.read(slot)
    leafs = {p: (ab, b) for p, ab, b in walk_abs(res, 0, str(slot))}
    leaf_off, blob = leafs[path]
    total = int.from_bytes(blob[g1t_pos + 8:g1t_pos + 12], 'little')
    data = blob[g1t_pos:g1t_pos + total]
    import g1t
    for i, (f, tw, th, mip, p) in enumerate(g1t.parse(data)):
        if i != index:
            continue
        flags = int.from_bytes(data[p + 4:p + 8], 'little')
        ext = int.from_bytes(data[p + 8:p + 12], 'little') if flags & 0x10000000 else 0
        q = p + 8 + ext
        size = w * h * {71: 1, 72: 2, 9: 8}[fmt] // 2
        off = leaf_off + g1t_pos + q
        return dict(tag=tag, resource_path=str(slot), leaf_path=path, texture_index=index,
                    resource_sha256=sha(res), payload_offset_in_resource=off, length=size,
                    before_payload_sha256=sha(res[off:off + size]),
                    texture_header_hex=data[p:p + 20].hex()), res[off:off + size]
    raise KeyError((tag, path, index))


def gpt_image(m):
    small = G / '결과' / '게임크기' / m['save_as']
    if small.exists():
        im = Image.open(small).convert('RGBA')
    else:
        im = Image.open(G / '결과' / m['save_as']).convert('RGBA')
    w, h = m['game_size']
    if im.size != (w, h):
        im = im.resize((w, h), Image.LANCZOS)
    return im


def main():
    items = json.load(open(G / 'items.json', encoding='utf-8'))
    pick = set(sys.argv[1:])
    graphics = {u['id']: u for u in json.load(open(S / 'graphics.json', encoding='utf-8'))['textures']}
    (G / '반영').mkdir(parents=True, exist_ok=True)
    (G / '비교').mkdir(parents=True, exist_ok=True)
    manifest, rows = [], []
    for m in items:
        if pick and m['no'] not in pick:
            continue
        if not ((G / '결과' / m['save_as']).exists() or (G / '결과' / '게임크기' / m['save_as']).exists()):
            continue
        new = gpt_image(m)
        orig = Image.open(G / m['original']).convert('RGBA')
        cur = Image.open(G / m['reference']).convert('RGBA')
        if m['key'].startswith('manual/') or m['key'] == 'home':
            rows.append((m, orig, cur, new, '설명서 반영 단계 없음(미리보기만)'))
            continue
        u = graphics[m['texture_id']]
        fmt, (tw, th) = u['fmt'], (u['w'], u['h'])
        targets, payload, original = [], None, None
        for r in u['refs']:
            if r['tag'] not in SRC:
                continue
            t, before = locate(r['tag'], r['path'], r['g1t'], r['index'], fmt, tw, th)
            targets.append(t)
            original = original or before
        if 'crop' in m:
            # 큰 텍스처의 일부만: 지금 판 전체 그림에 GPT 조각을 붙이고 그 블록만 다시 인코딩
            x0, y0, x1, y1 = m['crop']
            full = decode(fmt, original, tw, th)
            now = next((r.get('now') for r in u['refs'] if r.get('now')), None)
            if now:
                full = np.array(Image.open(S / 'tex_ko' / (now + '.png')).convert('RGBA'))
            canvas = Image.fromarray(full)
            canvas.paste(new, (x0, y0))
            payload = encode(fmt, np.array(canvas), original, (x0, y0, x1 - x0, y1 - y0))
            shown = Image.fromarray(decode(fmt, payload, tw, th)).crop((x0, y0, x1, y1))
        else:
            payload = encode(fmt, np.array(new))
            shown = Image.fromarray(decode(fmt, payload, tw, th))
        (G / '반영' / ('%s.payload.bin' % m['no'])).write_bytes(payload)
        manifest.append(dict(id='gpt_%s_%s' % (m['no'], m['name']), source=str(G / '결과' / m['save_as']),
                             payload_file=str(G / '반영' / ('%s.payload.bin' % m['no'])), payload_sha256=sha(payload),
                             format=fmt, native_size=[tw, th], targets=targets,
                             patch_inclusion_allowed=False, approval='사용자 확인 대기'))
        rows.append((m, orig, cur, shown, '%s %dx%d · 위치 %d곳' % ({71: 'ETC1', 72: 'ETC1A4', 9: 'RGBA8'}[fmt], tw, th, len(targets))))
    json.dump(dict(status='비교 시트 확인 대기', entries=manifest),
              open(G / '반영' / 'gpt_manifest.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    sheets(rows)
    print('인코딩 %d장, 비교 시트 %d장 → %s' % (len(manifest), (len(rows) + 2) // 3, G / '비교'))


def sheets(rows):
    try:
        font = ImageFont.truetype('C:/Windows/Fonts/malgun.ttf', 18)
        small = ImageFont.truetype('C:/Windows/Fonts/malgun.ttf', 14)
    except OSError:
        font = small = ImageFont.load_default()
    for s in range(0, len(rows), 3):
        part = rows[s:s + 3]
        cells = []
        for m, o, c, n, note in part:
            scale = max(1, min(3, 760 // max(o.size[0], 1)))
            cells.append([im.resize((im.size[0] * scale, im.size[1] * scale), Image.NEAREST if scale > 1 else Image.LANCZOS)
                          for im in (o, c, n)])
        cw = max(im.size[0] for row in cells for im in row) + 16
        heights = [max(im.size[1] for im in row) + 56 for row in cells]
        sheet = Image.new('RGB', (cw * 3, sum(heights) + 34), (34, 34, 40))
        d = ImageDraw.Draw(sheet)
        for k, t in enumerate(('원본', '현재', 'GPT (인코딩 후)')):
            d.text((k * cw + 8, 6), t, font=font, fill=(255, 235, 140))
        y = 34
        for (m, *_rest, note), row, hh in zip(part, cells, heights):
            d.text((8, y + 2), '%s %s · %s' % (m['no'], m['name'].replace('_', ' '), note), font=small, fill=(220, 220, 230))
            for k, im in enumerate(row):
                bg = Image.new('RGBA', im.size, (80, 80, 88, 255))
                bg.alpha_composite(im.convert('RGBA'))
                sheet.paste(bg, (k * cw + 8, y + 24))
            y += hh
        a, b = part[0][0]['no'], part[-1][0]['no']
        sheet.save(G / '비교' / ('비교_%s-%s.png' % (a, b)))


if __name__ == '__main__':
    main()
