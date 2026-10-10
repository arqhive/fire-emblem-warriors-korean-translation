# -*- coding: utf-8 -*-
"""빌드 결과물을 거꾸로 훑어 일본어가 남은 곳을 찾는다(번역 누락 역검사).

  python tools/survey_untranslated.py [빌드 폴더=work/builds/out] [DLC 빌드=work/builds/out_dlc]

번역 목록이 아니라 결과 LINKDATA 자체를 본다. 그래야 추출 단계에서 빠진 문자열도 걸린다.
  * 언어 분기는 원본 아카이브에서 고른다(번역된 쪽은 가나 비율이 낮아 엉뚱한 분기를 고를 수 있다).
  * XL 블록(CP932·UTF-16), 순차 대사 레코드, 그 밖의 자원(원시 바이트에서 일본어 줄)을 모두 본다.
  * 읽은 자원·건너뛴 자원 수를 종류별로 센다.
일본어 판정: 히라가나·가타카나(・ー 제외)·한자·반각 가나. 한글 번역의 ・ 는 걸리지 않는다.

결과: work/survey/untranslated.json 과 화면 요약.
"""
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ctrl
import tl
import xl
from dialogue_records import parse as parse_dialogue
from extract_text import category, jp_branch, walk_abs
from linkdata import LinkData

JP = re.compile(r'[ぁ-ゖァ-ヺ一-鿿ｦ-ﾝ]')
KANA = re.compile(r'[ぁ-ゖァ-ヺｦ-ﾝ]')
SJIS_RUN = re.compile(rb'(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]|[\x20-\x7e\n]){4,}')
BINARY_MAGIC = {b'WiiV', b'GT1G', b'_A2G', b'_M1G', b'XF1G', b'SARC', b'KTSR', b'KTSC'}


def jp_strings_in_raw(blob):
    """원시 바이트에서 가나가 2자 이상 든 CP932 줄"""
    out = []
    for m in SJIS_RUN.finditer(blob):
        try:
            t = m.group(0).decode('cp932')
        except UnicodeDecodeError:
            continue
        if len(KANA.findall(t)) >= 2:
            out.append(t.strip())
    return out


def scan_archive(tag, orig_dir, built_dir, report, stats):
    lo = LinkData(str(Path(orig_dir) / 'LINKDATA.idx'), str(Path(orig_dir) / 'LINKDATA.bin'))
    lb = LinkData(str(Path(built_dir) / 'LINKDATA.idx'), str(Path(built_dir) / 'LINKDATA.bin'))
    for slot, size, _off in lo.used():
        orig = lo.read(slot)
        keep = jp_branch(orig)
        data = lb.read(slot)
        for path, _ab, blob in walk_abs(data, 0, str(slot)):
            parts = path.split('/')
            if keep is not None and (len(parts) < 2 or int(parts[1]) not in keep):
                stats[tag]['다른 언어 분기'] += 1
                continue
            magic = blob[:4]
            g = xl.parse(blob)
            wide = None if g else xl.parse(blob, wide=True)
            if g or wide:
                stats[tag]['XL' if g else 'XL(UTF-16)'] += 1
                for _pos, _off2, s in (g or wide)[4]:
                    if not s:
                        continue
                    try:
                        t = s.decode('utf-16-le') if wide else s.decode('cp932')
                    except UnicodeDecodeError:
                        stats[tag]['XL 디코딩 실패 문자열'] += 1
                        continue
                    if JP.search(t):
                        report.append(dict(tag=tag, slot=slot, path=path, kind='XL(UTF-16)' if wide else 'XL',
                                           source_hex=s.hex(), text=t))
                continue
            d = parse_dialogue(blob, japanese_only=False)
            if d:
                stats[tag]['순차 대사'] += 1
                for e in d['entries']:
                    if JP.search(e['source']):
                        report.append(dict(tag=tag, slot=slot, path=path, kind='순차 대사', index=e['index'],
                                           source_hex=e['source_hex'], text=e['source']))
                continue
            if magic in BINARY_MAGIC:
                stats[tag]['바이너리(%s)' % magic.decode('latin-1')] += 1
                continue
            hits = jp_strings_in_raw(blob)
            stats[tag]['기타 자원'] += 1
            if hits:
                stats[tag]['기타 자원 중 일본어 있음'] += 1
                report.append(dict(tag=tag, slot=slot, path=path, kind='기타 자원', magic=magic.hex(),
                                   size=len(blob), samples=hits[:8], count=len(hits)))


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else 'work/builds/out')
    dlc = Path(sys.argv[2] if len(sys.argv) > 2 else 'work/builds/out_dlc')
    targets = [('base', 'extract/base', out / 'base' / 'romfs'),
               ('update', 'extract/update', out / 'update_resources' / 'romfs')]
    for t in ('c1', 'c2', 'c3', 'c4'):
        src = Path('extract/dlc')
        built = dlc / t if (dlc / t / 'LINKDATA.bin').exists() else None
        # c1 은 패치하지 않으므로 원본을 그대로 본다
        tmp = Path('work/survey/_dlc_' + t)
        tmp.mkdir(parents=True, exist_ok=True)
        for n in ('idx', 'bin'):
            p = tmp / ('LINKDATA.' + n)
            if not p.exists():
                p.hardlink_to((built / ('LINKDATA.' + n)) if built else (src / ('%s_LINKDATA.%s' % (t, n))))
        otmp = Path('work/survey/_orig_' + t)
        otmp.mkdir(parents=True, exist_ok=True)
        for n in ('idx', 'bin'):
            p = otmp / ('LINKDATA.' + n)
            if not p.exists():
                p.hardlink_to(src / ('%s_LINKDATA.%s' % (t, n)))
        targets.append((t, otmp, tmp))
    report, stats = [], collections.defaultdict(collections.Counter)
    for tag, o, b in targets:
        print('훑는 중:', tag, flush=True)
        scan_archive(tag, o, b, report, stats)
    ko = tl.load_ko()
    for r in report:
        if r['kind'] == 'XL':
            r['has_translation'] = r['source_hex'] in ko
            r['category'] = category(r['slot'])
    Path('work/survey').mkdir(parents=True, exist_ok=True)
    json.dump(dict(stats={k: dict(v) for k, v in stats.items()}, items=report),
              open('work/survey/untranslated.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n== 읽은 자원')
    for tag, c in stats.items():
        print('  %-6s %s' % (tag, dict(c)))
    print('\n== 일본어가 남은 곳')
    c = collections.Counter((r['tag'], r['kind'], r.get('has_translation')) for r in report)
    for k, v in sorted(c.items(), key=str):
        print('  %s %d' % (k, v))


if __name__ == '__main__':
    main()
