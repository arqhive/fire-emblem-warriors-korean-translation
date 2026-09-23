# -*- coding: utf-8 -*-
"""LINKDATA 전체에서 '일본어' 번역 대상 문자열 + 파일 절대 오프셋 추출

다국어 처리: 대부분의 슬롯은 최상위 컨테이너가 언어별 분기(11개 등)다.
분기마다 かな(히라가나·가타카나) 포함 비율을 재서 가장 높은 분기만 일본어로 채택한다.
(중국어 GB2312/Big5 는 CP932 로 디코드하면 한자처럼 보이지만 かな 가 없다.)
"""
import sys, os, struct, re, collections
sys.path.insert(0, os.path.dirname(__file__))
from linkdata import LinkData, is_container
from text_io import all_strings, XL_MAGIC
import xl
import ctrl
from charfreq import strip_ctrl, sane

KANA = re.compile(r'[぀-ヿ]')
JP   = re.compile(r'[぀-ヿ一-鿿]')
HANKAKU = re.compile(r'[｡-ﾟ]')
PLACE = re.compile(r'(予備|予約|ダミー|dummy|テスト|未使用|_page\d+|表示名|ラベル_|プロトタイプ|プログラマ)')


def walk_abs(data, base, path='', depth=0, maxdepth=8):
    ch = is_container(data) if depth < maxdepth else None
    if ch is None:
        yield path, base, data; return
    for k, (o, s) in enumerate(ch):
        yield from walk_abs(data[o:o + s], base + o, f'{path}/{k}', depth + 1, maxdepth)


def _strings(blob):
    """(blob 내 오프셋, 원본 bytes, 표시용 텍스트) 목록.

    XL 을 제대로 파싱할 수 있으면 엔트리에서 직접 뽑는다. 예전에는 문자열 영역을
    널 단위로 훑기만 해서, 표를 못 읽은 blob(2/0/3 의 '決定'·'戻る'·'次へ' 등)이
    통째로 빠졌다. 파싱이 안 되는 blob 만 예전 방식으로 훑는다.
    """
    out = []
    g = xl.parse(blob)
    if g is not None:
        hdr, cnt, w, tot, ents = g
        seen = set()
        for k, off, b in ents:
            if not b or len(b) > 800 or off in seen:
                continue
            seen.add(off)
            try:
                t = ctrl.to_text(b)
            except Exception:
                continue
            out.append((hdr + off, b, t))
        return out
    if len(blob) < 0x18 or struct.unpack_from('<I', blob, 0)[0] != XL_MAGIC:
        return out
    for o, b in all_strings(blob):
        if not b or len(b) > 800:
            continue
        try:
            t = ctrl.to_text(b)
        except Exception:
            continue
        out.append((o, b, t))
    return out


def category(slot):
    if slot == 2:               return 'UI·시스템·인명'
    if slot in (5, 6, 7):       return '전투 음성'
    if slot == 2462:            return '전투 시스템'
    if 2760 <= slot < 2800:     return '맵 대사'
    if 3000 <= slot < 3500:     return '스토리·대사'
    if 3500 <= slot < 4000:     return '목표·안내'
    if 4000 <= slot < 5000:     return '이벤트 대사'
    if 5000 <= slot < 6000:     return '지명·기타'
    if slot == 10361:           return '용어·이름'
    return '기타'


def jp_branch(data):
    """최상위 분기 중 일본어 분기 인덱스 집합을 고른다."""
    ch = is_container(data)
    if not ch or len(ch) < 2:
        return None                      # 분기 없음 → 전체 사용
    score = []
    for k, (o, s) in enumerate(ch):
        n = kana = 0
        for p, ab, blob in walk_abs(data[o:o + s], 0, str(k)):
            for _, b, t in _strings(blob):
                n += 1
                if KANA.search(t):
                    kana += 1
            if n > 4000:
                break
        score.append(kana / n if n else 0.0)
    best = max(score)
    if best < 0.05:
        return None                      # 언어 분기가 아님 → 전체 사용
    return {k for k, v in enumerate(score) if v >= best * 0.9}


def extract(idx, binf, tag):
    ld = LinkData(idx, binf)
    locs = collections.defaultdict(list)
    meta = {}
    for i, sz, eoff in ld.used():
        data = ld.read(i)
        keep = jp_branch(data)
        for p, ab, blob in walk_abs(data, eoff, str(i)):
            if keep is not None:
                parts = p.split('/')
                if len(parts) < 2 or int(parts[1]) not in keep:
                    continue
            for o, b, t in _strings(blob):
                if not JP.search(t) or not all(sane(c) for c in t):
                    continue
                if HANKAKU.search(t):           # 중국어·유럽어 오디코드 안전망
                    continue
                locs[b].append((tag, ab + o))
                if b not in meta:
                    meta[b] = dict(slot=i, path=p, cat=category(i), disp=t,
                                   nbytes=len(b), place=bool(PLACE.search(t)))
    return locs, meta
