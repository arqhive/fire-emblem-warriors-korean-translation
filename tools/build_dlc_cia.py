# -*- coding: utf-8 -*-
"""한글 대사를 넣은 DLC CIA 를 만든다.

  python tools/patch_dlc.py work/builds/out work/builds/out_dlc   # 먼저 아카이브 패치
  python tools/build_dlc_cia.py --cia "DLC.cia" --out "한글DLC.cia"

DLC(0004008C0F70C100)는 별도 타이틀이라 LayeredFS 로 덮을 수 없다. 콘텐츠마다 romfs 를
풀어 LINKDATA 를 갈아 끼우고 다시 싼다.

  content 0  메타데이터(CXI) — 그대로
  content 1  c1 LINKDATA — 번역 대상 아님, 그대로
  content 2  c2 — 교체
  content 3  c3 — 교체
  content 4  c4 — 교체
  content 5  c5 — 번역 대상 아님, 그대로

임시 공간이 5GB 가까이 필요하다.
"""
import argparse
import hashlib
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TID = '0004008c0f70c100'
CONTENT_TAG = {2: 'c2', 3: 'c3', 4: 'c4'}

sysdata = Path(os.environ.get('APPDATA', '')) / 'Azahar' / 'sysdata'
for var, name in (('BOOT9_PATH', 'boot9.bin'), ('SEEDDB_PATH', 'seeddb.bin')):
    if var not in os.environ and (sysdata / name).exists():
        os.environ[var] = str(sysdata / name)
if 'SEEDDB_PATH' not in os.environ and (ROOT / 'seeddb.bin').exists():
    os.environ['SEEDDB_PATH'] = str(ROOT / 'seeddb.bin')
from pyctr.type.cia import CIAReader
from pyctr.type.ncch import NCCHSection


def run(cmd, log):
    with open(log, 'wb') as f:
        r = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    if r.returncode:
        print(open(log, encoding='utf-8', errors='replace').read()[-2000:])
        raise SystemExit('실패: %s  (로그 %s)' % (' '.join(map(str, cmd)), log))


def sha(path, chunk=1 << 24):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cia', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--tools', default=str(HERE / 'bin'))
    ap.add_argument('--dlc', default=str(ROOT / 'work' / 'builds' / 'out_dlc'))
    ap.add_argument('--work', default=str(ROOT / 'work' / 'cia' / 'dlc'))
    ap.add_argument('--keep', action='store_true')
    a = ap.parse_args()
    npth = os.path.normpath
    tool = lambda n: npth(os.path.join(a.tools, n + ('.exe' if os.name == 'nt' else '')))
    W = npth(a.work)
    shutil.rmtree(W, ignore_errors=True)
    os.makedirs(W, exist_ok=True)
    P = lambda n: npth(os.path.join(W, n))
    L = lambda n: P(n + '.log')

    for tag in CONTENT_TAG.values():
        for name in ('LINKDATA.bin', 'LINKDATA.idx'):
            if not (Path(a.dlc) / tag / name).exists():
                raise SystemExit('DLC 패치 결과가 없다: %s/%s — tools/patch_dlc.py 를 먼저 돌린다'
                                 % (tag, name))

    with CIAReader(a.cia) as c:
        ver = c.tmd.title_version
        recs = [(r.cindex, r.id) for r in c.tmd.chunk_records]
        print('원본 DLC: 타이틀 버전 %s, 콘텐츠 %d개' % (ver, len(recs)))
        if str(c.contents[0].program_id).lower() != TID:
            raise SystemExit('DLC 타이틀(%s)이 아니다: %s' % (TID, c.contents[0].program_id))
        for idx, _cid in recs:
            dst = P('c%d.ncch' % idx)
            print('콘텐츠 %d 복호화' % idx, flush=True)
            with c.contents[idx].open_raw_section(NCCHSection.FullDecrypted) as f, \
                    open(dst, 'wb') as o:
                shutil.copyfileobj(f, o, 1 << 24)

    built = {}
    for idx, tag in CONTENT_TAG.items():
        print('콘텐츠 %d (%s) romfs 교체' % (idx, tag), flush=True)
        ncch, hdr = P('c%d.ncch' % idx), P('c%d_header.bin' % idx)
        romfs, rdir = P('c%d_romfs.bin' % idx), P('c%d_romfs' % idx)
        run([tool('3dstool'), '-xvtf', 'cfa', ncch, '--header', hdr, '--romfs', romfs],
            L('x_cfa_%d' % idx))
        run([tool('3dstool'), '-xvtf', 'romfs', romfs, '--romfs-dir', rdir],
            L('x_romfs_%d' % idx))
        for name in ('LINKDATA.bin', 'LINKDATA.idx'):
            target = Path(rdir) / name
            if not target.exists():
                raise SystemExit('romfs 안에 %s 가 없다: %s' % (name, rdir))
            shutil.copyfile(Path(a.dlc) / tag / name, target)
        new_romfs = P('c%d_romfs_ko.bin' % idx)
        run([tool('3dstool'), '-cvtf', 'romfs', new_romfs, '--romfs-dir', rdir],
            L('c_romfs_%d' % idx))
        out_ncch = P('c%d_ko.ncch' % idx)
        # --not-encrypt 를 빠뜨리면 원본 헤더의 '암호화됨' 플래그가 남는다.
        # 내용은 평문인데 본체가 복호화를 시도해 데이터가 깨진다(타이틀 화면 크래시의 원인이었다).
        run([tool('3dstool'), '-cvtf', 'cfa', out_ncch, '--header', hdr,
             '--romfs', new_romfs, '--not-encrypt'], L('c_cfa_%d' % idx))
        built[idx] = out_ncch
        shutil.rmtree(rdir, ignore_errors=True)
        os.remove(romfs)
        print('   %s → %s 바이트' % (format(os.path.getsize(ncch), ','),
                                     format(os.path.getsize(out_ncch), ',')))

    print('CIA 묶기 (makerom -ignoresign)', flush=True)
    cmd = [tool('makerom'), '-f', 'cia', '-o', npth(a.out), '-ignoresign']
    for idx, cid in recs:
        src = built.get(idx, P('c%d.ncch' % idx))
        cmd += ['-content', '%s:%d:%d' % (src, idx, int(cid, 16))]
    run(cmd, L('makerom'))

    want = 0
    for part, shift in zip(str(ver).split('.'), (10, 4, 0)):
        want |= int(part) << shift
    with open(a.out, 'r+b') as f:
        al = lambda x: (x + 63) & ~63
        f.seek(0)
        h = f.read(0x20)
        hsize, _t, _v, clen, tlen, tmdlen, _m = struct.unpack_from('<IHHIIII', h, 0)
        off = al(al(al(hsize) + clen) + tlen)
        f.seek(off)
        sig = struct.unpack('>I', f.read(4))[0]
        SIG = {0x10000: 0x23C, 0x10001: 0x13C, 0x10002: 0x7C,
               0x10003: 0x23C, 0x10004: 0x13C, 0x10005: 0x7C}
        vo = off + 4 + SIG[sig] + 0x9C
        f.seek(vo)
        cur = struct.unpack('>H', f.read(2))[0]
        if cur != want:
            f.seek(vo)
            f.write(struct.pack('>H', want))
            print('TMD 버전 %d -> %d' % (cur, want))
    print('완료: %s (%s 바이트)' % (a.out, format(os.path.getsize(a.out), ',')))
    if not a.keep:
        shutil.rmtree(W, ignore_errors=True)


if __name__ == '__main__':
    main()
