# -*- coding: utf-8 -*-
"""게임 텍스트의 ESC 제어코드 처리

코드 형태
  \\x1b + 문자            2바이트 (R, T, Z, C ...)
  \\x1b + A/P/F + 인자    3바이트

의미 (관측)
  \\x1bT <본문> \\x1bZ \\x1bT <읽기> \\x1bZ   후리가나(루비). 한국어에는 필요 없다
  \\x1bP<n>                                 버튼 아이콘. 지우면 화면에서 아이콘이 사라진다
  \\x1bA<n> ... \\x1bR / \\x1bF<n>           색·글꼴 강조

번역문에서도 살려야 하므로 루비를 뺀 나머지는 {A6} {PY} {R} 같은 플레이스홀더로
보이게 하고, 다시 바이트로 옮길 때 그대로 되돌린다.
원문에 중괄호가 쓰인 문자열은 없어서(확인함) 충돌하지 않는다.
"""
import re

ARG = {0x41, 0x50, 0x46}          # A, P, F 는 인자 1바이트를 더 갖는다
RUBY_OPEN, RUBY_CLOSE = 0x54, 0x5A
PH = re.compile(r'\{([A-Za-z])([0-9A-Za-z])?\}')
RUBY_PAIR = re.compile(rb'\x1bT(.*?)\x1bZ\x1bT(.*?)\x1bZ', re.S)


def strip_ruby(b):
    """후리가나 표기를 본문만 남기고 걷어낸다."""
    if 0x1b not in b:
        return b
    b = RUBY_PAIR.sub(lambda m: m.group(1), b)
    return b.replace(b'\x1bT', b'').replace(b'\x1bZ', b'')


def tokens(b):
    """[(위치, 코드바이트)] — 루비를 걷어낸 뒤 기준"""
    out, i = [], 0
    while i < len(b):
        if b[i] == 0x1b:
            if i + 1 >= len(b):
                raise UnicodeDecodeError('cp932', b, i, len(b), 'truncated ESC control')
            n = 3 if b[i + 1] in ARG else 2
            if i + n > len(b):
                raise UnicodeDecodeError('cp932', b, i, len(b), 'truncated ESC argument')
            out.append((i, b[i:i + n])); i += n
        else:
            i += 1
    return out


def to_text(b):
    """원문 바이트 → 표시·번역용 텍스트 (제어코드는 {..} 로)"""
    if 0x1b not in b:                 # 대부분은 제어코드가 없다 — 바로 빠져나간다
        return b.decode('cp932')
    b = strip_ruby(b)
    out, i = [], 0
    while i < len(b):
        if b[i] == 0x1b:
            if i + 1 >= len(b):
                raise UnicodeDecodeError('cp932', b, i, len(b), 'truncated ESC control')
            n = 3 if b[i + 1] in ARG else 2
            if i + n > len(b):
                raise UnicodeDecodeError('cp932', b, i, len(b), 'truncated ESC argument')
            out.append('{%s}' % b[i + 1:i + n].decode('latin-1'))
            i += n
            continue
        j = i
        while j < len(b) and b[j] != 0x1b:
            j += 1
        out.append(b[i:j].decode('cp932'))
        i = j
    return ''.join(out)


def codes(text):
    """텍스트 안의 제어코드 플레이스홀더 목록(순서 유지)"""
    return [m.group(0) for m in PH.finditer(text)]
