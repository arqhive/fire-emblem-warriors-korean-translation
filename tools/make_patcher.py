# -*- coding: utf-8 -*-
"""CIA 패처 꾸리기 → release/patcher (lib·bin) + release/python(임베디드 파이썬)

  python tools/make_payload.py                         # 먼저 release/patcher/payload 를 만든다
  python tools/make_patcher.py [--python <임베디드 파이썬 zip 또는 폴더>]

payload 에는 romfs 단위 xdelta 차분, .code IPS, 배너·아이콘, 확인값(manifest.json)만 담는다.
lib 에는 fewpatch·blz 와 pyctr·pycryptodomex(설치된 것 복사), bin 에는 3dstool·makerom·xdelta3 을 넣는다.
임베디드 파이썬은 python.org 의 embeddable package(3.13) 또는 이전 배포 ZIP 을 넘기면 python/ 폴더만 꺼내 쓴다.
"""
import os
import shutil
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
PATCHER = os.path.join('release', 'patcher')


def main():
    py = sys.argv[sys.argv.index('--python') + 1] if '--python' in sys.argv else None
    if not os.path.exists(os.path.join(PATCHER, 'payload', 'manifest.json')):
        sys.exit('payload 가 없습니다. 먼저 python tools/make_payload.py 를 실행하세요.')
    lib = os.path.join(PATCHER, 'lib')
    os.makedirs(lib, exist_ok=True)
    for f in ('fewpatch.py', 'blz.py'):
        shutil.copyfile(os.path.join('tools', f), os.path.join(lib, f))
    import pyctr
    import Cryptodome
    for m in (pyctr, Cryptodome):
        d = os.path.join(lib, m.__name__)
        if os.path.exists(d):
            shutil.rmtree(d)
        shutil.copytree(os.path.dirname(m.__file__), d,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyi', 'SelfTest'))
    b = os.path.join(PATCHER, 'bin')
    os.makedirs(b, exist_ok=True)
    for f in ('3dstool.exe', 'makerom.exe', 'xdelta3.exe'):
        shutil.copyfile(os.path.join('tools', 'bin', f), os.path.join(b, f))
    if py:
        dst = os.path.join('release', 'python')
        if os.path.exists(dst):
            shutil.rmtree(dst)
        if os.path.isdir(py):
            shutil.copytree(py, dst)
        else:
            with zipfile.ZipFile(py) as z:
                names = [i for i in z.infolist() if not i.is_dir()]
                nested = any('python' in i.filename.replace('\\', '/').split('/')[:-1] for i in names)
                for i in names:
                    parts = i.filename.replace('\\', '/').split('/')
                    if nested:                       # 다른 배포 ZIP 에서 python/ 폴더만 꺼낸다
                        if 'python' not in parts[:-1]:
                            continue
                        parts = parts[parts.index('python') + 1:]
                    out = os.path.join(dst, *parts)
                    os.makedirs(os.path.dirname(out), exist_ok=True)
                    open(out, 'wb').write(z.read(i))
    if not os.path.exists(os.path.join('release', 'python', 'python.exe')):
        print('주의: release/python 이 비어 있습니다. --python 으로 임베디드 파이썬을 넣어야 배포할 수 있습니다.')
    print('패처 준비 완료: lib·bin → %s%s' % (PATCHER, ', 파이썬 → release/python' if py else ''))


if __name__ == '__main__':
    main()
