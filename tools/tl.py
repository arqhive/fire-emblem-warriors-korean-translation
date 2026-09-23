# -*- coding: utf-8 -*-
"""번역 파일 입출력. 저장소의 번역 파일에는 일본어 원문을 넣지 않는다.

  python tools/tl.py find 크롬            # 원문·번역문에서 찾기 (원문은 extract/ 에서 읽는다)
  python tools/tl.py check                # 네 파일의 원문을 모두 복원할 수 있는지 확인

파일별 형식 (translation/)
  ko.json                {원문ID: 번역문}                 캐시 원문. ID = SHA-1(원문 CP932 바이트) 앞 12자리
  dialogue_ko.json       [{tag, path, index, translation, review}]     본편·업데이트 순차 대사
  dlc_dialogue_ko.json   {scope, records: [{tag, path, index, cue, translation, ...}]}  DLC 순차 대사
  utf16_medals_ko.json   {..., records: [{translation, locations: [{tag, index, offset}]}]}  훈장

도구는 load_*() 로 읽는다. 원문(source, source_hex, 캐시 키의 원문 바이트)을 extract/ 의 캐시에서
채워 예전과 같은 모양으로 돌려준다. save_*() 는 원문을 걷어내고 쓴다.
원문을 채우려면 본인 게임에서 뽑은 extract/(meta.pkl, dialogue_v2/blocks.json, base·update LINKDATA)가 있어야 한다.
"""
import hashlib
import io
import json
import os
import pickle
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

KO = ROOT / 'translation' / 'ko.json'
DIALOGUE = ROOT / 'translation' / 'dialogue_ko.json'
DLC = ROOT / 'translation' / 'dlc_dialogue_ko.json'
MEDALS = ROOT / 'translation' / 'utf16_medals_ko.json'
META = ROOT / 'extract' / 'meta.pkl'
BLOCKS = ROOT / 'extract' / 'dialogue_v2' / 'blocks.json'
MEDAL_RESOURCE = '2/0/7'


def text_id(raw):
    return hashlib.sha1(raw).hexdigest()[:12]


def _read(path):
    return json.load(io.open(path, encoding='utf-8'))


def _write(path, data, indent):
    tmp = Path(str(path) + '.tmp')
    with io.open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)
        f.write('\n')
    os.replace(tmp, path)


# ---------------------------------------------------------------- 원문 캐시

_cache = {}


def _meta_by_id():
    if 'meta' not in _cache:
        meta = pickle.load(open(META, 'rb'))
        table = {}
        for raw in meta:
            i = text_id(raw)
            if i in table and table[i] != raw:
                raise ValueError('원문 ID 충돌: %s' % i)
            table[i] = raw
        _cache['meta'] = table
    return _cache['meta']


def _blocks():
    if 'blocks' not in _cache:
        table = {}
        for b in _read(BLOCKS):
            for e in b['entries']:
                table[(b['tag'], b['path'], e['index'])] = e
        _cache['blocks'] = table
    return _cache['blocks']


def _medal_sources(tag):
    key = 'medal_' + tag
    if key not in _cache:
        from linkdata import LinkData
        from extract_text import walk_abs
        import xl
        d = ROOT / 'extract' / tag
        ld = LinkData(str(d / 'LINKDATA.idx'), str(d / 'LINKDATA.bin'))
        blob = next(b for p, _a, b in walk_abs(ld.read(2), 0, '2') if p == MEDAL_RESOURCE)
        refs = xl.parse(blob, wide=True)[4]
        _cache[key] = {k: (s.decode('utf-16-le') if s is not None else None)
                       for k, (_pos, _off, s) in enumerate(refs)}
    return _cache[key]


# ---------------------------------------------------------------- 캐시 원문 (ko.json)

def load_ko():
    """{원문 바이트 16진: 번역문} — 파일 순서를 지킨다(글리프 배정 순서가 여기에 달려 있다)."""
    table = _meta_by_id()
    out = {}
    for i, t in _read(KO).items():
        if i not in table:
            raise KeyError('extract/meta.pkl 에 없는 원문 ID: %s' % i)
        out[table[i].hex()] = t
    return out


def save_ko(ko):
    _write(KO, {text_id(bytes.fromhex(h)): t for h, t in ko.items()}, 0)


# ---------------------------------------------------------------- 순차 대사

def _fill(rows):
    blocks = _blocks()
    for r in rows:
        e = blocks.get((r['tag'], r['path'], r['index']))
        if e is None:
            raise KeyError(('extract/dialogue_v2/blocks.json 에 없는 대사', r['tag'], r['path'], r['index']))
        r['source_hex'] = e['source_hex']
        r['source'] = e['source']
    return rows


def _strip(rows):
    return [{k: v for k, v in r.items() if k not in ('source', 'source_hex')} for r in rows]


def load_dialogue():
    return _fill(_read(DIALOGUE))


def save_dialogue(rows):
    _write(DIALOGUE, _strip(rows), 1)


def load_dlc():
    man = _read(DLC)
    _fill(man['records'])
    return man


def save_dlc(man):
    _write(DLC, dict(man, records=_strip(man['records'])), 1)


# ---------------------------------------------------------------- 훈장 (UTF-16)

def load_medals():
    man = _read(MEDALS)
    for r in man['records']:
        loc = r['locations'][0]
        src = _medal_sources(loc['tag']).get(loc['index'])
        if src is None:
            raise KeyError(('훈장 원문을 찾지 못함', loc))
        r['source'] = src
    return man


def save_medals(man):
    recs = [{k: v for k, v in r.items() if k != 'source'} for r in man['records']]
    _write(MEDALS, dict(man, records=recs), 1)


# ---------------------------------------------------------------- 명령줄

def _all():
    import ctrl
    for h, t in load_ko().items():
        yield 'ko', text_id(bytes.fromhex(h)), ctrl.to_text(bytes.fromhex(h)), t
    for r in load_dialogue():
        yield 'dialogue', '%s %s:%d' % (r['tag'], r['path'], r['index']), r['source'], r['translation']
    for r in load_dlc()['records']:
        yield 'dlc', '%s %s:%d' % (r['tag'], r['path'], r['index']), r['source'], r['translation']
    for r in load_medals()['records']:
        yield 'medals', '%s:%d' % (r['locations'][0]['tag'], r['locations'][0]['index']), r['source'], r['translation']


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'find' and len(sys.argv) > 2:
        word = ' '.join(sys.argv[2:])
        n = 0
        for kind, key, src, ko in _all():
            if word in src or word in ko:
                print('[%s] %s\n  원문 %s\n  번역 %s' % (kind, key, src.replace('\n', ' / '), ko.replace('\n', ' / ')))
                n += 1
        print('%d건' % n)
    elif cmd == 'check':
        import collections
        c = collections.Counter(kind for kind, *_ in _all())
        print('원문 복원 완료:', dict(c))
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
