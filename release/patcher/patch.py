# -*- coding: utf-8 -*-
"""파이어 엠블렘 무쌍 한글 패치 적용기 — 일본판 CIA 를 한글판 CIA 로 만든다.

  패치하기.bat 에 .cia 파일을 끌어다 놓는다 (여러 개 가능).
  python patch.py <파일> [<파일> ...]

본편·업데이트·추가 콘텐츠는 타이틀 ID 로 알아서 구분한다.
결과는 원본과 같은 폴더에 `<원래 이름>_KO.cia` 로 생긴다. 원본 파일은 바뀌지 않는다.
암호화된 CIA 면 boot9.bin 과 seeddb.bin 이 필요하다. 패치 폴더(이 파일의 한 단계 위)에 두거나
Azahar·Citra 의 sysdata 폴더, 사용자 폴더의 .3ds 폴더에 있으면 자동으로 찾는다.
"""
import json
import os
import sys
import time
import traceback

for _s in (sys.stdout, sys.stderr):
    try:                                   # 콘솔 코드 페이지가 UTF-8 이 아니면 일본어 파일명에서 죽는다
        _s.reconfigure(errors='replace')
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, 'lib'))
import fewpatch

PAYLOAD = os.path.join(HERE, 'payload')


def ask():
    print('\n일본판 파이어 엠블렘 무쌍 .cia 파일 경로를 입력하세요 (파일을 이 창에 끌어다 놓아도 됩니다).')
    return input('> ').strip().strip('"')


def main():
    man = json.load(open(os.path.join(PAYLOAD, 'manifest.json'), encoding='utf-8'))
    print('파이어 엠블렘 무쌍 한글 패치 %s (CIA 패처)\n' % man['version'])
    files = [a for a in sys.argv[1:] if a.strip()] or [ask()]
    done = []
    for src in files:
        src = src.strip('"')
        print('=' * 60 + '\n' + os.path.basename(src))
        if not os.path.isfile(src):
            print('[오류] 파일을 찾을 수 없습니다: %s' % src)
            continue
        stem, ext = os.path.splitext(src)
        if ext.lower() != '.cia':
            print('[오류] .cia 파일만 넣을 수 있습니다.')
            continue
        if stem.endswith('_KO'):
            print('[오류] 이미 한글 패치로 만든 파일입니다. 일본판 원본을 넣어 주세요.')
            continue
        dst = stem + '_KO.cia'
        t = time.time()
        try:
            tag = fewpatch.patch(src, dst, PAYLOAD, os.path.join(HERE, 'bin'),
                                 os.path.join(TOP, 'work'), key_extra=(TOP, HERE))
        except SystemExit as e:
            print('[오류] %s' % e)
            continue
        except Exception:
            traceback.print_exc()
            print('[오류] 예상하지 못한 문제가 생겼습니다.')
            continue
        print('\n완료 (%d초): %s' % (time.time() - t, dst))
        done.append(tag)
    print('\n%d개 중 %d개 완료.' % (len(files), len(done)))
    if 'base' in done and 'update' not in done:
        print('\n※ 업데이트(v6.9.0)를 설치해 쓰고 있다면 업데이트 CIA 도 한글판으로 만들어 설치하세요.')
        print('  실제로 실행되는 프로그램이 업데이트 쪽이라, 원본 업데이트가 있으면 한글이 나오지 않습니다.')
    return 0 if len(done) == len(files) else 1


if __name__ == '__main__':
    sys.exit(main())
