# -*- coding: utf-8 -*-
"""boot9.bin·seeddb.bin 위치를 BOOT9_PATH·SEEDDB_PATH 로 잡는다. pyctr 를 import 하기 전에 setup() 을 부른다.

찾는 순서: 이미 잡힌 환경 변수 → 프로젝트 맨 위 → 상위 폴더(G:\\KoreanTranslation, 여러 작품 공용) → Azahar sysdata
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIRS = [ROOT, ROOT.parent, Path(os.environ.get('APPDATA', '')) / 'Azahar' / 'sysdata']


def setup():
    for var, name in (('BOOT9_PATH', 'boot9.bin'), ('SEEDDB_PATH', 'seeddb.bin')):
        if var in os.environ:
            continue
        for d in DIRS:
            if (d / name).is_file():
                os.environ[var] = str(d / name)
                break


if __name__ == '__main__':
    setup()
    for var in ('BOOT9_PATH', 'SEEDDB_PATH'):
        print(var, os.environ.get(var, '(못 찾음)'))
