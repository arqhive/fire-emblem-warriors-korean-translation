# -*- coding: utf-8 -*-
"""문장 끝 마침표 누락을 찾는다.

  python tools/audit_periods.py            # 요약
  python tools/audit_periods.py --list     # 전체 목록

문체 기준(docs/STYLE_GUIDE.md)
 - 대사·설명문은 완결 문장으로 쓰고 마침표를 찍는다.
 - 메뉴명·버튼명·아이템명·짧은 상태 표시에는 일괄로 찍지 않는다.
그래서 '종결어미로 끝나는데 문장부호가 없는 것'만 후보로 올린다.
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

# 종결어미. 어간 없이 이것만으로 끝나는 짧은 라벨(예: '이동')은 걸러진다.
ENDINGS = (
    '습니다', '입니다', 'ㅂ니다', '됩니다', '립니다', '십니다', '납니다', '옵니다',
    '합니다', '집니다', '칩니다', '갑니다', '깁니다', '봅니다', '줍니다',
    '했다', '한다', '된다', '진다', '난다', '온다', '간다', 'win다',
    '이다', '있다', '없다', '같다', '된다', '준다', '본다', '뜬다', '쓴다',
    '느다', '른다', '든다', '쉽다', '많다', '높다', '길다', '짧다', '좋다',
    '세요', '에요', '예요', '어요', '아요', '워요', '해요', '이죠', '지요',
    '군요', '네요', '까요', '나요', '는가', '을까', 'ㄹ까',
    '겠다', '았다', '었다', '였다', '린다', '킨다', '난다', '싼다',
)
CLOSERS = '.!?…～~」』"\'）)】]〉》'
# 끝에 붙어도 문장부호로 인정하는 전각 기호
FULLWIDTH = '。！？．・'


def tail(text):
    """마지막 줄에서 제어코드와 공백을 걷어낸 꼬리"""
    plain = ctrl.PH.sub('', text)
    lines = [l for l in plain.split('\n') if l.strip()]
    if not lines:
        return ''
    return lines[-1].rstrip()


def needs_period(text):
    t = tail(text)
    if len(t) < 4:
        return False
    if t[-1] in CLOSERS or t[-1] in FULLWIDTH:
        return False
    if re.search(r'%[0-9]*[a-zA-Z]$', t):      # 변수로 끝나면 문장이 아니다
        return False
    return any(t.endswith(e) for e in ENDINGS)


def source_has_period(src):
    s = ctrl.PH.sub('', src)
    lines = [l for l in s.split('\n') if l.strip()]
    if not lines:
        return False
    return lines[-1].rstrip()[-1:] in '。.！？!?…'


def main():
    show = '--list' in sys.argv
    meta = pickle.load(open('extract/meta.pkl', 'rb'))
    by_hex = {b.hex(): m for b, m in meta.items()}
    rows = []

    ko = tl.load_ko()
    for h, t in ko.items():
        if not needs_period(t):
            continue
        m = by_hex.get(h)
        rows.append(dict(kind='캐시', cat=(m or {}).get('cat', '?'),
                         src=(m or {}).get('disp', ''), ko=t))

    for name, recs in (('순차 대사', tl.load_dialogue()),
                       ('DLC 대사', tl.load_dlc()['records'])):
        for r in recs:
            if needs_period(r['translation']):
                rows.append(dict(kind=name, cat=name, src=r.get('source', ''),
                                 ko=r['translation']))

    med = tl.load_medals()
    for r in med['records']:
        if needs_period(r['translation']):
            rows.append(dict(kind='훈장', cat='훈장', src=r['source'], ko=r['translation']))

    print('마침표가 빠진 것으로 보이는 항목: %d건' % len(rows))
    c = Counter(r['cat'] for r in rows)
    for k, v in c.most_common():
        print('  %-16s %d' % (k, v))

    with_src = [r for r in rows if source_has_period(r['src'])]
    print()
    print('그중 원문에도 마침표가 있는 것: %d건 (명백한 누락)' % len(with_src))

    json.dump(rows, io.open('reports/period_audit.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('기록: reports/period_audit.json')

    if show:
        print()
        for r in rows:
            mark = '*' if source_has_period(r['src']) else ' '
            print('%s [%s] %s' % (mark, r['cat'],
                                  r['ko'].replace('\n', ' / ')[:70]))


if __name__ == '__main__':
    main()
