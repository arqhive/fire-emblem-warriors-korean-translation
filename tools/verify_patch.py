# -*- coding: utf-8 -*-
"""완성된 LayeredFS 아카이브를 통째로 다시 읽어 텍스트·그래픽·훈장을 대조한다.

  python tools/verify_patch.py work/builds/out
"""
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from linkdata import LinkData
from extract_text import walk_abs, jp_branch
from kopatch import load_slots, encode_ko
import ctrl
import xl


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else 'work/builds/out')
    import tl
    ko = tl.load_ko()
    # 글리프 배정은 빌드가 남긴 것을 그대로 쓴다. 다시 계산하면 DLC·훈장 음절이 빠져 코드가 어긋난다.
    codes = {c: bytes.fromhex(h) for c, h in
             json.loads((out / 'glyph_assign.json').read_text('utf-8')).items()}
    enc = {}
    for k, t in ko.items():
        try:
            enc[bytes.fromhex(k)] = encode_ko(t, codes)
        except ValueError:
            pass
    want = set(enc.values())

    report = {'archive': str(out)}
    # 1) 텍스트: 아카이브에서 번역 바이트가 몇 종 읽히는지
    for tag in ('base', 'update'):
        folder = out / ('base' if tag == 'base' else 'update_resources') / 'romfs'
        ld = LinkData(str(folder / 'LINKDATA.idx'), str(folder / 'LINKDATA.bin'))
        found, blobs, broken = set(), 0, 0
        for i, size, eoff in ld.used():
            data = ld.read(i)
            keep = jp_branch(data)
            for p, ab, blob in walk_abs(data, eoff, str(i)):
                if keep is not None:
                    pr = p.split('/')
                    if len(pr) < 2 or int(pr[1]) not in keep:
                        continue
                g = xl.parse(blob)
                if g is None:
                    continue
                blobs += 1
                for _, _, s in g[4]:
                    if s in want:
                        found.add(s)
        report.setdefault('text', {})[tag] = dict(xl_blocks=blobs, translated_found=len(found))
        print('%-7s XL 블록 %s개, 번역 문자열 %s종 확인'
              % (tag, f'{blobs:,}', f'{len(found):,}'))

    # 2) 그래픽
    gj = json.loads(Path('reports/graphics_applied.json').read_text('utf-8'))
    gok = ghit = 0
    for res in gj['resources']:
        if not res.get('written'):
            continue
        folder = out / ('base' if res['tag'] == 'base' else 'update_resources') / 'romfs'
        ld = LinkData(str(folder / 'LINKDATA.idx'), str(folder / 'LINKDATA.bin'))
        data = ld.read(int(res['slot']))
        for piece in res['pieces']:
            if piece['status'] != '반영':
                continue
            ghit += 1
            cur = data[piece['offset']:piece['offset'] + piece['length']]
            if sha(cur) == piece['payload_sha256']:
                gok += 1
    report['graphics'] = dict(checked=ghit, matched=gok)
    print('그래픽 조각 %d개 중 %d개 일치' % (ghit, gok))

    # 3) 훈장
    man = json.loads(Path('translation/utf16_medals_ko.json').read_text('utf-8'))
    wanted = defaultdict(dict)
    for r in man['records']:
        for loc in r['locations']:
            wanted[loc['tag']][loc['index']] = r['translation']
    mok = mhit = 0
    for tag, table in wanted.items():
        folder = out / ('base' if tag == 'base' else 'update_resources') / 'romfs'
        ld = LinkData(str(folder / 'LINKDATA.idx'), str(folder / 'LINKDATA.bin'))
        for p, ab, blob in walk_abs(ld.read(2), 0, '2'):
            if p != '2/0/7':
                continue
            g = xl.parse(blob, wide=True)
            for k, (pos, off, s) in enumerate(g[4]):
                if k not in table or s is None:
                    continue
                mhit += 1
                if s.decode('utf-16-le', 'replace') == table[k]:
                    mok += 1
            break
    report['medals'] = dict(checked=mhit, matched=mok)
    print('훈장 %d참조 중 %d개 일치' % (mhit, mok))

    Path('reports/patch_verification.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print('기록: reports/patch_verification.json')


if __name__ == '__main__':
    main()
