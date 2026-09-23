# -*- coding: utf-8 -*-
"""UTF-16 훈장 문구를 빌드된 LayeredFS 아카이브에 반영한다.

  python tools/apply_medals.py work/builds/out

훈장은 슬롯 2 의 `2/<언어>/7` 블록에 UTF-16LE 로 들어 있다. 구조 자체는 보통의 XL 이고
문자열만 UTF-16 이라, 널 한 바이트로 끊어 읽던 예전 파서가 중간에서 잘라 읽었을 뿐이다.
`xl.parse(..., wide=True)` 로 제대로 읽어 문자열 영역을 다시 깐다.
일본어 분기(`2/0/7`)만 바꾸고 다른 언어 블록은 손대지 않는다.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from linkdata import LinkData
from extract_text import walk_abs
import xl

MANIFEST = Path('translation/utf16_medals_ko.json')
TARGET = '2/0/7'


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else 'work/builds/out')
    import tl
    man = tl.load_medals()
    # (tag, 엔트리 인덱스) → 번역문
    want = {}
    for r in man['records']:
        for loc in r['locations']:
            want[(loc['tag'], loc['index'])] = (r['source'], r['translation'])

    report = {'archive': str(out), 'resource': TARGET, 'blocks': [], 'applied': 0}
    for tag in ('base', 'update'):
        folder = out / ('base' if tag == 'base' else 'update_resources') / 'romfs'
        idx, binf = folder / 'LINKDATA.idx', folder / 'LINKDATA.bin'
        if not binf.exists():
            continue
        ld = LinkData(str(idx), str(binf))
        _, size, eoff = ld.entry(2)
        data = ld.read(2)
        hit = None
        for p, ab, blob in walk_abs(data, 0, '2'):
            if p == TARGET:
                hit = (ab, blob)
                break
        if hit is None:
            report['blocks'].append(dict(tag=tag, status='블록을 찾지 못함'))
            continue
        rel, blob = hit
        g = xl.parse(blob, wide=True)
        if g is None:
            report['blocks'].append(dict(tag=tag, status='UTF-16 XL 파싱 실패'))
            continue
        hdr, cnt, w, tot, refs = g

        repl, checked, mismatch = {}, 0, []
        for k, (pos, off, s) in enumerate(refs):
            if s is None or (tag, k) not in want:
                continue
            src, ko = want[(tag, k)]
            try:
                cur = s.decode('utf-16-le')
            except UnicodeDecodeError:
                mismatch.append(dict(index=k, reason='디코딩 실패'))
                continue
            if cur == ko:
                checked += 1           # 이미 반영됨
                continue
            if cur != src:
                mismatch.append(dict(index=k, expected=src[:20], found=cur[:20]))
                continue
            repl[pos] = ko.encode('utf-16-le')
        if mismatch:
            report['blocks'].append(dict(tag=tag, status='원문 불일치로 중단',
                                         mismatch=mismatch[:10]))
            print('  ! %s — 원문이 기록과 달라 쓰지 않았다 (%d건)' % (tag, len(mismatch)))
            continue
        if not repl:
            report['blocks'].append(dict(tag=tag, status='이미 반영됨', already=checked))
            print('  %s 이미 반영됨 (%d건)' % (tag, checked))
            continue

        try:
            nb = xl.rebuild(blob, repl, wide=True)
        except OverflowError as e:
            report['blocks'].append(dict(tag=tag, status='용량 초과', detail=str(e),
                                         capacity=xl.capacity(blob, wide=True)))
            print('  ! %s 용량 초과: %s' % (tag, e))
            continue
        # 되읽기 검증
        back = xl.parse(nb, wide=True)
        ok = all(back[4][k][2] == (repl.get(refs[k][0], refs[k][2]))
                 for k in range(len(refs)) if refs[k][2] is not None)
        with open(binf, 'r+b') as f:
            f.seek(eoff + rel)
            f.write(nb)
            f.flush()
            f.seek(eoff + rel)
            disk = f.read(len(nb))
        report['blocks'].append(dict(
            tag=tag, status='반영', replaced=len(repl), already=checked,
            capacity=xl.capacity(blob, wide=True),
            used=sum(len(v) + 2 for v in {bytes(x) for x in repl.values()}),
            block_offset=eoff + rel, block_size=len(nb),
            before_sha256=sha(bytes(blob)), after_sha256=sha(nb),
            reparse_verified=ok, disk_readback_verified=(disk == nb)))
        report['applied'] += len(repl)
        print('  %-7s %d건 반영 (이미 %d건)  되읽기 %s  재파싱 %s'
              % (tag, len(repl), checked, '일치' if disk == nb else '★ 불일치',
                 '일치' if ok else '★ 불일치'))

    Path('reports/medals_applied.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print('훈장 %d건 반영' % report['applied'])


if __name__ == '__main__':
    main()
