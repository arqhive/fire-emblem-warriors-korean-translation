# -*- coding: utf-8 -*-
"""DLC content 0(메타데이터)의 콘텐츠 정보 파일 한글판.

  python tools/dlc_info.py <ContentInfoArchive_JPN_ja.bin>     # 바꿀 내용만 보여 준다

ContentInfoArchive_JPN_ja.bin: 머리 8바이트(u32 판, u32 개수) 뒤에 200바이트 레코드가 이어진다.
  레코드 = 이름 0x40 + 설명 0x80 (UTF-8, 널로 채움) + u32 콘텐츠 번호 + u32 플래그
  0번 레코드는 DummyTitle/DummyDescription 이다. 3DS 데이터 관리 화면의 추가 콘텐츠 이름이 여기서 나온다.
번역은 translation/dlc_info_ko.json 에 레코드 번호 → 한글 이름으로 둔다(원문 없음).

같은 content 0 의 exefs 아이콘(SMDH) 제목도 일본어지만 지금은 바꾸지 않는다.
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRANSLATION = ROOT / 'translation' / 'dlc_info_ko.json'
REC, NAME = 200, 0x40


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


if __name__ == '__main__':
    src = Path(sys.argv[1]).read_bytes()
    new = patch_info(src)
    for (i, _o, a), (_j, _p, b) in zip(records(src), records(new)):
        print('%d  %s%s' % (i, a, '' if a == b else '  →  ' + b))
