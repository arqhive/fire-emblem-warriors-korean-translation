# -*- coding: utf-8 -*-
"""배포 ZIP 만들기.

  python tools/make_payload.py
  python tools/make_patcher.py [--python <임베디드 파이썬>]      # release/patcher·release/python 채우기
  python tools/make_release.py v0.1

release/FEWarriors_KO_<버전>_Patcher.zip
  FEWarriors_KO_<버전>_Patcher/패치하기.bat, patcher/, python/   일본판 CIA 를 한글판으로 만드는 패처
  README_한국어.txt, LICENSE.txt

이 게임은 LayeredFS 로 적용할 수 없어(docs/TECHNICAL.md) LayeredFS ZIP 은 만들지 않는다.
"""
import hashlib
import os
import sys
import zipfile
import zlib


def add_tree(z, src, arc):
    n = 0
    for root, dirs, files in os.walk(src):
        dirs[:] = sorted(d for d in dirs if d != '__pycache__')
        for f in sorted(files):
            p = os.path.join(root, f)
            z.write(p, arc + '/' + os.path.relpath(p, src).replace(os.sep, '/'))
            n += 1
    return n


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    ver = sys.argv[1]
    for need in (os.path.join('release', 'python', 'python.exe'),
                 os.path.join('release', 'patcher', 'payload', 'manifest.json'),
                 os.path.join('release', 'patcher', 'lib', 'fewpatch.py')):
        if not os.path.exists(need):
            sys.exit('패처가 준비되지 않았습니다(%s 없음). 먼저 python tools/make_patcher.py 를 실행하세요.' % need)
    top = 'FEWarriors_KO_%s_Patcher' % ver
    out = os.path.join('release', top + '.zip')
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.write(os.path.join('release', '패치하기.bat'), top + '/패치하기.bat')
        n = add_tree(z, os.path.join('release', 'patcher'), top + '/patcher')
        n += add_tree(z, os.path.join('release', 'python'), top + '/python')
        z.write(os.path.join('release', 'README_한국어.txt'), top + '/README_한국어.txt')
        z.write('LICENSE', top + '/LICENSE.txt')
    data = open(out, 'rb').read()
    print('%s: 파일 %d개, %s 바이트' % (out, n + 3, format(len(data), ',')))
    print('  CRC32 %08X  MD5 %s' % (zlib.crc32(data), hashlib.md5(data).hexdigest()))


if __name__ == '__main__':
    main()
