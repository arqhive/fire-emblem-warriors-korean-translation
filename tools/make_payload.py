# -*- coding: utf-8 -*-
"""배포용 패치 데이터(payload)를 만든다.

  python tools/make_payload.py [버전]      # 기본 VERSION

원본 CIA 와 한글 CIA 에서 콘텐츠별 romfs 를 뽑아 xdelta 차분을 만든다.
romfs 단위로 뜨면 movie·sound·voice 2.2GB 가 그대로 재사용돼 차분이 작고,
사용자 쪽에서 romfs 를 풀었다 다시 쌀 필요가 없다.

.code 는 차분 대신 IPS 를 그대로 쓴다. 원본은 BLZ 로 압축돼 있으므로
사용자 쪽에서 풀고(IPS 적용) exheader 의 압축 플래그를 끈다. 110바이트면 된다.

게임 데이터는 들어가지 않는다. 차분은 원본이 있어야만 의미가 있다.
"""
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
AZ = Path(os.environ.get('APPDATA', '')) / 'Azahar' / 'sysdata'
os.environ.setdefault('BOOT9_PATH', str(AZ / 'boot9.bin'))
os.environ.setdefault('SEEDDB_PATH', str(ROOT / 'seeddb.bin'))
sys.path.insert(0, str(HERE))
from pyctr.type.cia import CIAReader
from pyctr.type.ncch import NCCHSection
from hangul_font import make_patch

DESK = Path(os.path.expandvars(r'%USERPROFILE%\Desktop'))
XDELTA = HERE / 'bin' / 'xdelta3.exe'
VERSION = 'v0.2'
OUT = ROOT / 'release' / 'patcher' / 'payload'
TMP = ROOT / 'work' / 'payload_tmp'

JOBS = [
    ('base', '000400000F70C100*.cia', DESK / 'FEWarriors_KO_base.cia', [0]),
    ('update', '0004000E0F70C100*.cia', DESK / 'FEWarriors_KO_update.cia', [0]),
    ('dlc', '0004008C0F70C100*.cia', DESK / 'FEWarriors_KO_DLC.cia', [2, 3, 4]),
]


def sha(p, chunk=1 << 24):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def dump_romfs(cia, index, dst):
    if dst.exists():
        return dst
    with CIAReader(str(cia)) as c:
        with c.contents[index].open_raw_section(NCCHSection.RomFS) as f, open(dst, 'wb') as o:
            shutil.copyfileobj(f, o, 1 << 24)
    return dst


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    version = sys.argv[1] if len(sys.argv) > 1 else VERSION
    manifest = {'version': version, 'titles': {}}

    for tag, pattern, built, indexes in JOBS:
        orig = glob.glob(pattern)
        if not orig or not built.exists():
            print('%s 건너뜀 (원본 또는 한글 CIA 없음)' % tag)
            continue
        entry = {'contents': {}}
        for idx in indexes:
            a = dump_romfs(orig[0], idx, TMP / ('%s_c%d_orig.bin' % (tag, idx)))
            b = dump_romfs(built, idx, TMP / ('%s_c%d_ko.bin' % (tag, idx)))
            name = '%s_c%d_romfs.xdelta' % (tag, idx)
            print('%s content %d 차분 생성...' % (tag, idx), flush=True)
            subprocess.run([str(XDELTA), '-e', '-9', '-f', '-S', 'none',
                            '-B', '2147483648', '-s', str(a), str(b), str(OUT / name)],
                           check=True)
            entry['contents'][str(idx)] = dict(
                patch=name, patch_size=(OUT / name).stat().st_size,
                source_sha256=sha(a), result_sha256=sha(b),
                source_size=a.stat().st_size, result_size=b.stat().st_size)
            print('   %s  %s 바이트' % (name, format((OUT / name).stat().st_size, ',')))
            a.unlink(); b.unlink()

        if tag in ('base', 'update'):
            _, ips, detail = make_patch(tag)
            (OUT / ('%s_code.ips' % tag)).write_bytes(ips)
            entry['code'] = dict(ips='%s_code.ips' % tag, size=len(ips),
                                 source_sha256=detail['source_sha256'],
                                 result_sha256=detail['patched_sha256'],
                                 entry=detail['entry'], cave=detail['cave'],
                                 note='BLZ 를 풀고 적용한 뒤 exheader 의 압축 플래그를 끈다')
            src = ROOT / 'work' / 'home_menu' / tag
            files = ['icon.bin'] + (['banner.bin'] if tag == 'base' else [])
            entry['exefs'] = {}
            for fn in files:
                shutil.copyfile(src / fn, OUT / ('%s_%s' % (tag, fn)))
                entry['exefs'][fn.split('.')[0]] = dict(
                    file='%s_%s' % (tag, fn), sha256=sha(OUT / ('%s_%s' % (tag, fn))))
        manifest['titles'][tag] = entry

    (OUT / 'manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')
    total = sum(p.stat().st_size for p in OUT.iterdir() if p.is_file())
    print()
    for p in sorted(OUT.iterdir()):
        print('  %12s  %s' % (format(p.stat().st_size, ','), p.name))
    print('payload 합계 %s 바이트' % format(total, ','))


if __name__ == '__main__':
    main()
