# -*- coding: utf-8 -*-
"""Legacy comparison extractor. Writes isolated output; does not replace audited caches.

This heuristic extractor excludes some Japanese branches. Use audit_extraction_v2.py
and restore_extraction_locations.py for the reviewed recovery workflow.
"""
import sys, os, pickle, collections, io, json
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_text import extract

allocs = collections.defaultdict(list)
allmeta = {}
for tag, d in (('base', 'extract/base'), ('update', 'extract/update')):
    locs, meta = extract(d + '/LINKDATA.idx', d + '/LINKDATA.bin', tag)
    for k, v in locs.items():
        allocs[k] += v
    for k, v in meta.items():
        allmeta.setdefault(k, v)
    print('%-7s 문자열 %s' % (tag, f'{len(meta):,}'))
output = Path('extract/legacy_reextract')
output.mkdir(parents=True, exist_ok=True)
pickle.dump(dict(allocs), open(output / 'locs.pkl', 'wb'))
pickle.dump(allmeta, open(output / 'meta.pkl', 'wb'))
print('비교용 추출 결과:', output, '(검증된 작업 캐시는 보존됨)')

import tl
ko = tl.load_ko()
have = {bytes.fromhex(h) for h in ko}
print('총 %s건 / %s자' % (f'{len(allmeta):,}',
                          f'{sum(len(m["disp"]) for m in allmeta.values()):,}'))
print('기존 번역 중 원문 목록에 남은 것 %d / %d' % (len(have & set(allmeta)), len(have)))
c = collections.Counter()
for b, m in allmeta.items():
    if not m['place']:
        c[m['cat']] += 0 if b in have else 1
print('분류별 미번역:', dict(c.most_common()))
