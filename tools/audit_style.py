# -*- coding: utf-8 -*-
"""문체 규칙 위반 후보를 훑는다(docs/STYLE_GUIDE.md, 한국어 문체 메모 기준).

  python tools/audit_style.py

검사 항목
 - 물결표(~)  : 범위는 풀어 쓴다. 다만 원문에 있던 전각 ～ 는 그대로 둔다.
 - 물결표 뒤 문장부호
 - 대사 속 '그녀'
 - 띄어쓰기 없는 긴 한글 뭉치(축약 흔적)
 - 문장 중간의 어색한 공백(전각 공백 제외)
 - 같은 원문에 서로 다른 번역
"""
import io
import json
import pickle
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, 'tools')
import ctrl
import tl

FILES = [('캐시', tl.load_ko, 'dict'),
         ('순차 대사', tl.load_dialogue, 'list'),
         ('DLC 대사', tl.load_dlc, 'records'),
         ('훈장', tl.load_medals, 'records')]
LONG_RUN = re.compile(r'[가-힣]{9,}')


def load():
    meta = pickle.load(open('extract/meta.pkl', 'rb'))
    by_hex = {b.hex(): m for b, m in meta.items()}
    out = []
    for label, loader, shape in FILES:
        data = loader()
        if shape == 'dict':
            for h, t in data.items():
                m = by_hex.get(h, {})
                out.append((label, m.get('disp', ''), t))
        else:
            recs = data if shape == 'list' else data['records']
            for r in recs:
                out.append((label, r.get('source', ''), r['translation']))
    return out


def main():
    rows = load()
    print('검사 대상 %s건' % f'{len(rows):,}')
    hits = defaultdict(list)

    for label, src, t in rows:
        plain = ctrl.PH.sub('', t)
        # 반각 물결표
        if '~' in plain:
            hits['반각 물결표(~)'].append((label, src, t))
        # 물결표 뒤에 바로 문장부호
        if re.search(r'[~～][.!?,]', plain):
            hits['물결표 뒤 문장부호'].append((label, src, t))
        # 대사 속 '그녀'
        if '그녀' in plain and label in ('순차 대사', 'DLC 대사'):
            hits["대사 속 '그녀'"].append((label, src, t))
        # 띄어쓰기 없는 긴 뭉치
        for m in LONG_RUN.finditer(plain):
            if len(m.group()) >= 9:
                hits['띄어쓰기 없는 9자 이상'].append((label, src, t))
                break
        # 줄 끝 공백
        if any(l != l.rstrip() for l in plain.split('\n')):
            hits['줄 끝 공백'].append((label, src, t))

    # 같은 원문에 다른 번역
    same = defaultdict(set)
    for label, src, t in rows:
        if src:
            same[src].add(t)
    conflict = {s: v for s, v in same.items() if len(v) > 1}

    for k in sorted(hits, key=lambda x: -len(hits[x])):
        print('\n== %s : %d건' % (k, len(hits[k])))
        for label, src, t in hits[k][:8]:
            print('   [%s] %s' % (label, t.replace('\n', ' / ')[:66]))
    print('\n== 같은 원문에 서로 다른 번역 : %d종' % len(conflict))
    for s, v in list(conflict.items())[:6]:
        print('   원문 %s' % s.replace('\n', ' / ')[:40])
        for x in list(v)[:3]:
            print('      -> %s' % x.replace('\n', ' / ')[:56])

    json.dump({k: [[a, b, c] for a, b, c in v] for k, v in hits.items()},
              io.open('reports/style_audit.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n기록: reports/style_audit.json')


if __name__ == '__main__':
    main()
