# -*- coding: utf-8 -*-
"""DLC content 0(메타데이터)의 한글판: 콘텐츠 정보 파일과 아이콘 제목.

  python tools/dlc_info.py <ContentInfoArchive_JPN_ja.bin>     # 바꿀 내용만 보여 준다

ContentInfoArchive_JPN_ja.bin: 머리 8바이트(u32 판, u32 개수) 뒤에 200바이트 레코드가 이어진다.
  레코드 = 이름 0x40 + 설명 0x80 (UTF-8, 널로 채움) + u32 콘텐츠 번호 + u32 플래그
  0번 레코드는 DummyTitle/DummyDescription 이다. 3DS 데이터 관리 화면의 추가 콘텐츠 이름이 여기서 나온다.
번역은 translation/dlc_info_ko.json 에 레코드 번호 → 한글 이름으로 둔다(원문 없음).

exefs 아이콘(SMDH)은 그림·설정이 본편과 같다. 본편 한글 아이콘(work/home_menu/base/icon.bin)의
제목 칸(일본어·영어·한국어)을 그대로 옮긴다. 한국판 본체는 한국어 칸을 읽는데 원본은 영어다.
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRANSLATION = ROOT / 'translation' / 'dlc_info_ko.json'
BASE_ICON = ROOT / 'work' / 'home_menu' / 'base' / 'icon.bin'
REC, NAME = 200, 0x40
ICON_SLOTS = (0, 1, 7)          # SMDH 제목 칸: 일본어, 영어, 한국어


def records(b):
    _ver, n = struct.unpack_from('<II', b, 0)
    assert 8 + (n + 1) * REC == len(b), '레코드 수가 맞지 않는다'
    for i in range(n + 1):
        o = 8 + i * REC
        yield i, o, b[o:o + NAME].split(b'\0')[0].decode('utf-8')


def patch_info(b):
    tr = json.loads(TRANSLATION.read_text('utf-8'))
    if hashlib.sha256(b).hexdigest() != tr['source_sha256']:
        raise SystemExit('ContentInfoArchive 원본이 기록과 다르다')
    out = bytearray(b)
    for i, o, _old in records(b):
        new = tr['names'].get(str(i))
        if new is None:
            continue
        raw = new.encode('utf-8')
        if len(raw) >= NAME:
            raise SystemExit('이름이 너무 길다(%d바이트): %s' % (len(raw), new))
        out[o:o + NAME] = raw + b'\0' * (NAME - len(raw))
    return bytes(out)


def patch_icon(dlc_icon):
    base = BASE_ICON.read_bytes()
    assert dlc_icon[:4] == base[:4] == b'SMDH' and len(dlc_icon) == len(base)
    out = bytearray(dlc_icon)
    for k in ICON_SLOTS:
        o = 8 + k * 0x200
        out[o:o + 0x200] = base[o:o + 0x200]
    return bytes(out)


if __name__ == '__main__':
    src = Path(sys.argv[1]).read_bytes()
    new = patch_info(src)
    for (i, _o, a), (_j, _p, b) in zip(records(src), records(new)):
        print('%d  %s%s' % (i, a, '' if a == b else '  →  ' + b))
