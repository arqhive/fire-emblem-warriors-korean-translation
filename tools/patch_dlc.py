# -*- coding: utf-8 -*-
"""DLC 순차 대사를 DLC 아카이브에 반영한다.

  python tools/patch_dlc.py work/builds/out work/builds/out_dlc

DLC 는 별도 타이틀(0004008C0F70C100)의 콘텐츠라 LayeredFS 로 덮을 수 없다.
여기서 만든 LINKDATA 는 DLC CIA 를 다시 만들 때 쓴다(tools/build_dlc_cia.py).

글리프는 본편 폰트 한 벌을 공유하므로, 한글 코드 배정은 본편 빌드가 남긴
glyph_assign.json 을 그대로 읽어 쓴다. 따로 배정하면 서로 어긋난다.
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_dialogue import patch_archive
import ctrl

SRC = Path('extract/dlc')
MANIFEST = Path('translation/dlc_dialogue_ko.json')
TAGS = ('c2', 'c3', 'c4')
FLAGS = {'c2': (3,), 'c3': (4,), 'c4': (5,)}


def load_rows():
    import tl
    man = tl.load_dlc()
    rows, seen = [], set()
    for r in man['records']:
        if r['tag'] not in TAGS:
            raise ValueError(('지원하지 않는 DLC 태그', r['tag']))
        key = (r['tag'], r['path'], r['index'])
        if key in seen:
            raise ValueError(('중복 대상', key))
        seen.add(key)
        if r['source'] != ctrl.to_text(bytes.fromhex(r['source_hex'])):
            raise ValueError(('원문 불일치', key))
        if not r['translation'].strip() or '\0' in r['translation']:
            raise ValueError(('빈 번역 또는 널 포함', key))
        rows.append(r)
    return rows


def main():
    build = Path(sys.argv[1] if len(sys.argv) > 1 else 'work/builds/out')
    out = Path(sys.argv[2] if len(sys.argv) > 2 else 'work/builds/out_dlc')
    codes = {s: bytes.fromhex(h) for s, h in
             json.loads((build / 'glyph_assign.json').read_text('utf-8')).items()}
    rows = load_rows()
    out.mkdir(parents=True, exist_ok=True)
    report = {'glyph_source': str(build / 'glyph_assign.json'),
              'records': len(rows), 'contents': {}}

    missing = sorted({c for r in rows for c in r['translation']
                      if '가' <= c <= '힣' and c not in codes})
    if missing:
        raise SystemExit('본편 빌드에 없는 한글 %d자: %s'
                         % (len(missing), ''.join(missing)[:40]))

    for tag in TAGS:
        target = out / tag
        target.mkdir(parents=True, exist_ok=True)
        src = (str(SRC / ('%s_LINKDATA.idx' % tag)), str(SRC / ('%s_LINKDATA.bin' % tag)))
        shutil.copyfile(src[0], target / 'LINKDATA.idx')
        shutil.copyfile(src[1], target / 'LINKDATA.bin')
        detail = patch_archive(tag, src, target, rows, codes, allowed_flags=FLAGS[tag])
        detail['output_size'] = (target / 'LINKDATA.bin').stat().st_size
        report['contents'][tag] = detail
        print('%-3s 대사 %s건 / 블록 %d개 재구성 / 누락 %d / 되읽기 %s  %s 바이트'
              % (tag, f"{detail['translated_records']:,}", detail['rebuilt_blocks'],
                 detail['omitted_records'],
                 '일치' if detail['disk_readback_verified'] else '★ 불일치',
                 format(detail['output_size'], ',')))

    Path('reports/dlc_patch.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print('기록: reports/dlc_patch.json')


if __name__ == '__main__':
    main()
