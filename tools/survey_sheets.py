# -*- coding: utf-8 -*-
"""전수 조사한 텍스처를 번호 붙인 모음 시트로 만든다(눈 검수용).

  python tools/survey_sheets.py
결과: work/survey/sheets/{nonmodel,model}_NNN.png, work/survey/sheets/index.json (번호 → 텍스처 id)
16px 이하는 글자가 들어갈 수 없어 빼고 개수만 남긴다.
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw

SRC = Path('work/survey')
OUT = SRC / 'sheets'
CELL, COLS, ROWS = 136, 12, 8


def checker(w, h):
    bg = Image.new('RGBA', (w, h), (110, 110, 120, 255))
    d = ImageDraw.Draw(bg)
    for y in range(0, h, 8):
        for x in range(0, w, 8):
            if (x // 8 + y // 8) % 2:
                d.rectangle([x, y, x + 7, y + 7], fill=(150, 150, 160, 255))
    return bg


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    T = json.load(open(SRC / 'graphics.json', encoding='utf-8'))['textures']
    index, skipped = {}, 0
    for group in ('nonmodel', 'model'):
        rows = [u for u in T if u['model_only'] == (group == 'model')]
        big = []
        for u in rows:
            if max(u['w'], u['h']) <= 16:
                skipped += 1
            else:
                big.append(u)
        big.sort(key=lambda u: (u['refs'][0]['tag'] != 'base', u['refs'][0]['slot'], u['refs'][0]['path'], -u['w'] * u['h']))
        per = COLS * ROWS
        for s in range(0, len(big), per):
            sheet = Image.new('RGB', (COLS * CELL, ROWS * (CELL + 16)), (40, 40, 48))
            d = ImageDraw.Draw(sheet)
            for k, u in enumerate(big[s:s + per]):
                n = '%s%04d' % (group[0], s + k)
                index[n] = u['id']
                im = Image.open(SRC / 'tex' / (u['id'] + '.png')).convert('RGBA')
                im.thumbnail((CELL - 6, CELL - 6), Image.LANCZOS if max(im.size) > CELL else Image.NEAREST)
                if max(im.size) < CELL // 2:
                    f = (CELL - 6) // max(im.size)
                    im = im.resize((im.size[0] * f, im.size[1] * f), Image.NEAREST)
                bg = checker(*im.size)
                bg.alpha_composite(im)
                x, y = (k % COLS) * CELL, (k // ROWS * 0 + k // COLS) * (CELL + 16)
                sheet.paste(bg, (x + 3, y + 3))
                d.text((x + 3, y + CELL + 1), '%s %dx%d %s' % (n, u['w'], u['h'], u['refs'][0]['path'][:14]), fill=(255, 240, 150))
            sheet.save(OUT / ('%s_%03d.png' % (group, s // per)))
        print(group, '시트', (len(big) + per - 1) // per, '장, 텍스처', len(big))
    json.dump(index, open(OUT / 'index.json', 'w', encoding='utf-8'), indent=0)
    print('16px 이하 제외', skipped)


if __name__ == '__main__':
    main()
