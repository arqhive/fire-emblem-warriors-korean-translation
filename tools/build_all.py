# -*- coding: utf-8 -*-
"""번역부터 배포 payload 까지 한 번에 다시 만든다.

  python tools/build_all.py

순서
  1. 텍스트·대사·폰트          build_verified.py
  2. 그림 글씨                 apply_graphics.py
  3. UTF-16 훈장               apply_medals.py
  4. 되읽어 대조               verify_patch.py
  5. DLC 대사                  patch_dlc.py
  6. 한글판 CIA 세 개          build_cia.py / build_dlc_cia.py
  7. 배포 차분                 make_payload.py

한글판 CIA 는 바탕화면에 `FEWarriors_KO_{base,update,DLC}.cia` 로 만든다(설치 확인용).
"""
import glob
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = 'work/builds/out'
DLC = 'work/builds/out_dlc'
DESK = Path(os.path.expandvars(r'%USERPROFILE%\Desktop'))


def step(title, cmd):
    t0 = time.time()
    print('\n[%s] %s' % (time.strftime('%H:%M:%S'), title), flush=True)
    r = subprocess.run([sys.executable] + cmd, cwd=ROOT)
    if r.returncode:
        raise SystemExit('실패: %s' % title)
    print('   (%.0f초)' % (time.time() - t0), flush=True)


def orig(pattern):
    hits = glob.glob(str(ROOT / pattern))
    if not hits:
        raise SystemExit('원본 CIA 없음: %s' % pattern)
    return hits[0]


def main():
    import shutil
    shutil.rmtree(ROOT / OUT, ignore_errors=True)
    step('텍스트·대사·폰트', ['tools/build_verified.py', OUT])
    step('그림 글씨', ['tools/apply_graphics.py', OUT])
    step('UTF-16 훈장', ['tools/apply_medals.py', OUT])
    step('되읽어 대조', ['tools/verify_patch.py', OUT])
    step('DLC 대사', ['tools/patch_dlc.py', OUT, DLC])

    tmp = DESK / '_FEWarriors_tmp.cia'
    for tag, pat, final in (('base', '000400000F70C100*.cia', 'FEWarriors_KO_base.cia'),
                            ('update', '0004000E0F70C100*.cia', 'FEWarriors_KO_update.cia')):
        romfs = '%s/%s/romfs' % (OUT, 'base' if tag == 'base' else 'update_resources')
        step('%s CIA — romfs·배너·아이콘' % tag,
             ['tools/build_cia.py', '--tag', tag, '--cia', orig(pat),
              '--out', str(tmp), '--romfs-from', romfs])
        step('%s CIA — 코드 훅' % tag,
             ['tools/build_cia.py', '--tag', tag, '--cia', str(tmp),
              '--out', str(DESK / final), '--code', '--no-home'])
        tmp.unlink()
    step('DLC CIA', ['tools/build_dlc_cia.py', '--cia', orig('0004008C0F70C100*.cia'),
                     '--out', str(DESK / 'FEWarriors_KO_DLC.cia')])
    step('배포 차분', ['tools/make_payload.py'])
    print('\n완료. 바탕화면에 한글판 CIA 세 개, release/patcher/payload 에 배포 차분.')


if __name__ == '__main__':
    main()
