# -*- coding: utf-8 -*-
"""번역 JSON → 패치된 LINKDATA (XL blob 통째 재구성 방식)

기존 build_ko.py 는 문자열을 제자리에 덮어써서 '원문 바이트 이내' 라는 제약이 있었다.
XL 구조를 완전히 해독했으므로(tools/xl.py) 이제 문자열 영역을 통째로 다시 깔고
엔트리 offset 을 갱신한다. 제약은 개별 길이가 아니라 blob 당 문자열 영역 총량이다.
blob 크기 자체는 그대로라 LINKDATA.idx 나 상위 컨테이너는 손대지 않는다.

  python tools/build_ko2.py [출력폴더]   (옛 빌더. 지금은 build_verified.py 가 상수만 가져다 쓴다)
"""
import sys, os, io, json, shutil, struct, pickle, bisect
sys.path.insert(0, os.path.dirname(__file__))
from linkdata import LinkData
from extract_text import walk_abs, jp_branch
from ctrtex import etc1a4_alpha, etc1a4_write
from kopatch import load_slots, assign, encode_ko, lint
from fonttest import render
import xl

FONT_SLOT = 22
PRESET = dict(font='tools/fonts/PretendardVariable.ttf', size=15, weight=900, gamma=0.75, dy=-0.5)
SRC = {'base':   ('extract/base/LINKDATA.idx',   'extract/base/LINKDATA.bin'),
       'update': ('extract/update/LINKDATA.idx', 'extract/update/LINKDATA.bin')}
OUT = {'base':   'luma/titles/000400000F70C100/romfs/LINKDATA.bin',
       'update': 'luma/titles/0004000E0F70C100/romfs/LINKDATA.bin'}


def build(ko, outdir, verbose=True):
    rows = load_slots()
    syls = {c for t in ko.values() for c in t if 0xAC00 <= ord(c) <= 0xD7A3}
    syl2code, syl2cell = assign(syls, rows, keep_chars=frozenset())
    if verbose:
        print('고유 음절 %s → 칸 배정 (가용 %s)' % (f'{len(syls):,}',
              f'{sum(1 for r in rows if r["used"]):,}'))

    enc, bad = {}, []
    for hexk, t in ko.items():
        src = bytes.fromhex(hexk)
        p = lint(src, t, syl2code, check_len=False)
        if p:
            bad.append((t, p)); continue
        enc[src] = encode_ko(t, syl2code)
    if verbose:
        print('번역 %s건 중 정상 %s / 문제 %s' % (f'{len(ko):,}', f'{len(enc):,}', f'{len(bad):,}'))
        for t, p in bad[:8]:
            print('   X %r  %s' % (t[:28], p))

    os.makedirs(outdir, exist_ok=True)
    locs = pickle.load(open('extract/locs.pkl', 'rb'))
    paths, nstr, nblob, over, ninp, skipped = {}, 0, 0, [], 0, []
    for tag, rel in OUT.items():
        dst = os.path.join(outdir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(SRC[tag][1], dst)
        paths[tag] = dst
        ld = LinkData(*SRC[tag])
        buf = bytearray(io.open(dst, 'rb').read())
        done = []                                   # 재구성한 구간 [시작, 끝)
        for i, sz, eoff in ld.used():
            data = ld.read(i)
            keep = jp_branch(data)
            for p, ab, blob in walk_abs(data, eoff, str(i)):
                if keep is not None:
                    parts = p.split('/')
                    if len(parts) < 2 or int(parts[1]) not in keep:
                        continue
                g = xl.parse(blob)
                if g is None:
                    continue
                repl = {k: enc[s] for k, off, s in g[4] if s is not None and s in enc}
                if not repl:
                    continue
                try:
                    nb = xl.rebuild(blob, repl)
                except ValueError:
                    # 미참조 데이터가 있어 재구성이 위험한 blob. 제자리 패치에 맡긴다.
                    continue
                except OverflowError as e:
                    over.append((tag, i, p, str(e), len(repl))); continue
                buf[ab:ab + len(nb)] = nb
                done.append((ab, ab + len(nb)))
                nstr += len(repl); nblob += 1
        # 재구성이 닿지 않은 곳(표가 여러 개인 blob 등)은 제자리 덮어쓰기로 보강.
        # 이쪽은 예전처럼 '원본 바이트 이내' 제약이 그대로 걸린다.
        done.sort()
        for src, e in enc.items():
            for t, off in locs.get(src, []):
                if t != tag:
                    continue
                j = bisect.bisect_right(done, (off, 1 << 62)) - 1
                if j >= 0 and done[j][0] <= off < done[j][1]:
                    continue
                if len(e) > len(src):
                    skipped.append((src, e)); continue
                buf[off:off + len(e) + 1] = e + bytes(1)
                ninp += 1
        io.open(dst, 'wb').write(bytes(buf))
    if verbose:
        print('blob %s개 재구성 / 문자열 %s곳 교체 + 제자리 %s곳' % (
            f'{nblob:,}', f'{nstr:,}', f'{ninp:,}'))
        if skipped:
            u = {s for s, _ in skipped}
            print('   ! 제자리 구간 길이 초과로 원문 유지: %d건' % len(u))
            for s in list(u)[:5]:
                print('      ', s.decode('cp932', 'replace')[:30])
        for o in over:
            print('   ! 용량 초과 %s slot%d %s : %s (%d건 포기)' % (o[0], o[1], o[2], o[3], o[4]))

    ld = LinkData(*SRC['base'])
    flag, sz, eoff = ld.entry(FONT_SLOT)
    blob = ld.read(FONT_SLOT)
    tbl = struct.unpack_from('<I', blob, 0xC)[0]
    q = tbl + struct.unpack_from('<I', blob, tbl)[0]
    data = blob[q + 20:q + 20 + 1024 * 1024]
    img = etc1a4_alpha(data, 1024, 1024)
    for s, cell in syl2cell.items():
        r, k = divmod(cell, 64)
        img[r * 16:r * 16 + 16, k * 16:k * 16 + 16] = render(s, PRESET)
    with open(paths['base'], 'r+b') as f:
        f.seek(eoff + q + 20); f.write(etc1a4_write(data, 1024, 1024, img))
    if verbose:
        print('글리프 %s칸 기록' % f'{len(syl2cell):,}')
    json.dump({s: c.hex() for s, c in syl2code.items()},
              io.open(os.path.join(outdir, 'glyph_assign.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=0)
    return paths, bad, over


if __name__ == '__main__':
    import tl
    out = sys.argv[1] if len(sys.argv) > 1 else 'out'
    build(tl.load_ko(), out)
