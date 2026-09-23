# -*- coding: utf-8 -*-
"""번역 JSON → LINKDATA in-place 패치 + 글리프 배정

핵심 규칙
 - 문자열은 반드시 '원본 바이트 길이 + 1(널)' 안에 들어가야 한다
 - 제어코드(ESC 시퀀스)와 포맷 지정자(%s, %1s0 …)는 보존해야 한다
 - 한글 음절 → 아틀라스 칸(= SJIS 코드)은 atlas_map_true.json 기준으로 배정
"""
import sys, os, re, json, io, struct, pickle, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ctrl
sys.path.insert(0, os.path.dirname(__file__))

FMT = re.compile(rb'%[0-9]*[a-zA-Z]')
ESC = re.compile(rb'\x1b.')

def ctrl_signature(b):
    """보존해야 할 제어·포맷 토큰 집합"""
    out = []
    i = 0
    while i < len(b):
        if b[i] == 0x1b:
            n = 3 if i + 1 < len(b) and b[i+1] in (0x41, 0x50, 0x46) else 2
            out.append(b[i:i+n]); i += n; continue
        m = FMT.match(b, i)
        if m:
            out.append(m.group()); i = m.end(); continue
        i += 1
    return collections.Counter(out)


def load_slots(path='extract/font/atlas_map_true.json'):
    """글리프를 바꿔 쓸 수 있는 칸 목록 (셀, SJIS코드, 원래문자)"""
    rows = json.load(io.open(path, encoding='utf-8'))
    return rows


def pick_slots(rows, need, keep_chars):
    """need개의 칸을 고른다. keep_chars(원문에 남겨야 할 문자)는 건드리지 않는다."""
    def cat(ch):
        o = ord(ch)
        if 0x4e00 <= o <= 0x9fff: return 'kanji'
        if 0x3040 <= o <= 0x30ff: return 'kana'
        return 'sym'
    ok = [r for r in rows if r['used'] and r['ch'] not in keep_chars]
    # 원문에 덜 쓰이는 칸부터 내어준다(미번역 구간 훼손 최소화). 한자 → かな → 기호 순.
    rank = {'kanji': 0, 'kana': 1, 'sym': 2}
    cand = sorted(ok, key=lambda r: (rank[cat(r['ch'])], r.get('freq', 0)))
    if len(cand) < need:
        raise RuntimeError(f'칸 부족: 필요 {need} / 가용 {len(cand)}')
    return cand[:need]


def assign(syllables, rows, keep_chars=frozenset()):
    """음절 → SJIS 코드 배정표"""
    syl = sorted(set(syllables))
    slots = pick_slots(rows, len(syl), keep_chars)
    return {s: bytes.fromhex(r['code']) for s, r in zip(syl, slots)}, \
           {s: r['cell'] for s, r in zip(syl, slots)}


def encode_ko(text, syl2code):
    """한국어 문자열 → 게임 바이트열. 제어코드/ASCII 는 그대로."""
    out = bytearray(); i = 0
    while i < len(text):
        c = text[i]
        if c == '{':                      # {A6} {PY} {R} → ESC 시퀀스로 되돌린다
            m = ctrl.PH.match(text, i)
            if m:
                out.append(0x1b)
                out.append(ord(m.group(1)))
                if m.group(2):
                    out.append(ord(m.group(2)))
                i = m.end(); continue
        if c == '\x1b':
            out.append(0x1b)
            if i + 1 < len(text):
                out.append(ord(text[i+1]))
                if text[i+1] in 'APF' and i + 2 < len(text):
                    out.append(ord(text[i+2])); i += 1
                i += 1
            i += 1; continue
        o = ord(c)
        if o < 0x80:
            out.append(o); i += 1; continue
        if c in syl2code:
            out += syl2code[c]; i += 1; continue
        try:
            out += c.encode('cp932')      # 원문에 있던 문자(기호 등)는 그대로
        except Exception:
            raise ValueError(f'인코딩 불가 문자: {c!r} in {text!r}')
        i += 1
    return bytes(out)


def lint(src_bytes, ko_text, syl2code, check_len=True):
    """번역 검사 → 문제 목록"""
    probs = []
    try:
        enc = encode_ko(ko_text, syl2code)
    except ValueError as e:
        return [str(e)]
    if check_len and len(enc) > len(src_bytes):
        probs.append(f'길이 초과 {len(enc)} > {len(src_bytes)}')
    a, b = ctrl_signature(src_bytes), ctrl_signature(enc)
    for tok in set(a) | set(b):
        if tok.startswith(b'%') and a[tok] != b[tok]:
            probs.append(f'포맷 불일치 {tok!r}: 원본 {a[tok]} → 번역 {b[tok]}')
    # 제어코드는 순서까지 그대로여야 한다. 후리가나(루비)만 빼고 비교한다.
    want = [t for _, t in ctrl.tokens(ctrl.strip_ruby(src_bytes))]
    got = [t for _, t in ctrl.tokens(enc)]
    if want != got:
        probs.append('제어코드 불일치: 원본 %s → 번역 %s'
                     % ([t.hex() for t in want], [t.hex() for t in got]))
    return probs
