# -*- coding: utf-8 -*-
"""HOME 메뉴의 배너와 게임 이름만 한글로 바꾼 CIA 를 만든다.

  python tools/build_home_banner.py                  # 먼저 work/home_menu/banner_ko.bin 생성
  python tools/build_cia.py --tag base   --cia "본편.cia"     --out "한글본편.cia"
  python tools/build_cia.py --tag update --cia "업데이트.cia" --out "한글업데이트.cia"

게임 안 텍스트는 LayeredFS 패치로 입히고, 이 CIA 는 ExeFS 의 배너·아이콘만 바꾼다.
romfs 는 원본 그대로 옮긴다.

본편 ExeFS 에는 .code / banner / icon 이 있고, 업데이트에는 .code / icon 만 있다.
그래서 배너는 본편에만 넣을 수 있고, 게임 이름은 업데이트가 설치되어 있으면
업데이트 쪽이 HOME 메뉴에 보인다. 양쪽 다 만들어 두는 편이 안전하다.

준비물
  * 일본판 CIA, 3dstool·makerom(`tools/bin`), boot9.bin·seeddb.bin
    (Azahar 의 %APPDATA%\\Azahar\\sysdata 에 있으면 자동으로 쓴다)
  * 본편은 임시 공간이 8GB 가까이 필요하다.

겪어 본 함정 (에버 오아시스·페더레이션 포스 기록)
  * CXI 를 --not-encrypt 로 만들어야 makerom 이 exheader 를 읽어 meta 영역까지 만든다.
  * makerom 에 -ignoresign 이 없으면 "Content 0 Is Corrupt", -content 는 <파일>:<인덱스>:<ID> 세 칸.
  * makerom 은 TMD 버전을 exheader 의 remaster version 으로 쓴다 → 원본 TMD 버전으로 되돌린다.
  * 외부 도구는 '/' 와 '\\' 가 섞인 경로를 거부하므로 os.path.normpath 로 맞춘다.
"""
import argparse, hashlib, os, shutil, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TID = {'base': '000400000f70c100', 'update': '0004000e0f70c100'}

sysdata = os.path.join(os.environ.get('APPDATA', ''), 'Azahar', 'sysdata')
for var, name in (('BOOT9_PATH', 'boot9.bin'), ('SEEDDB_PATH', 'seeddb.bin')):
    if var not in os.environ and os.path.exists(os.path.join(sysdata, name)):
        os.environ[var] = os.path.join(sysdata, name)
if 'SEEDDB_PATH' not in os.environ and os.path.exists(os.path.join(ROOT, 'seeddb.bin')):
    os.environ['SEEDDB_PATH'] = os.path.join(ROOT, 'seeddb.bin')
from pyctr.type.cia import CIAReader
from pyctr.type.ncch import NCCHSection


def run(cmd, log):
    with open(log, 'wb') as f:
        r = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    if r.returncode:
        print(open(log, encoding='utf-8', errors='replace').read()[-2000:])
        raise SystemExit('실패: %s  (로그 %s)' % (' '.join(cmd), log))


def rebuild_exefs(d, patches):
    """ExeFS 블롭에서 patches({이름: 내용})만 바꿔 다시 쓴다. 오프셋·크기·SHA-256 재계산."""
    entries = []
    for i in range(10):
        name, off, size = struct.unpack_from('<8sII', d, i * 16)
        if not size:
            continue
        key = name.rstrip(b'\0').decode()
        entries.append((name, key, patches.get(key, d[0x200 + off:0x200 + off + size])))
    known = {k for _, k, _ in entries}
    for k in patches:
        if k not in known:
            raise SystemExit('ExeFS 에 %r 항목이 없습니다. 교체 대상이 아닙니다.' % k)
    hdr = bytearray(0x200)
    blob = bytearray()
    for i, (name, key, body) in enumerate(entries):
        struct.pack_into('<8sII', hdr, i * 16, name, len(blob), len(body))
        hdr[0x200 - (i + 1) * 32:0x200 - i * 32] = hashlib.sha256(body).digest()
        blob += body
        blob += b'\0' * ((-len(blob)) % 0x200)
        print('  [%d] %-8s %10s 바이트  %s' % (i, key, format(len(body), ','),
                                              '교체' if key in patches else '원본'))
    return bytes(hdr) + bytes(blob)


def tmd_version_offset(f):
    """CIA 파일에서 TMD 타이틀 버전 필드의 절대 위치."""
    al = lambda x: (x + 63) & ~63
    f.seek(0)
    hdr = f.read(0x20)
    hsize, _t, _v, clen, tlen, tmdlen, _m = struct.unpack_from('<IHHIIII', hdr, 0)
    off = al(al(al(hsize) + clen) + tlen)
    f.seek(off)
    sig = struct.unpack('>I', f.read(4))[0]
    SIG = {0x10000: 0x23C, 0x10001: 0x13C, 0x10002: 0x7C,
           0x10003: 0x23C, 0x10004: 0x13C, 0x10005: 0x7C}
    return off + 4 + SIG[sig] + 0x9C


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tag', required=True, choices=('base', 'update'))
    ap.add_argument('--cia', required=True, help='일본판 CIA')
    ap.add_argument('--out', required=True, help='만들 CIA')
    ap.add_argument('--tools', default=os.path.join(HERE, 'bin'))
    ap.add_argument('--assets', default=os.path.join(ROOT, 'work', 'home_menu'))
    ap.add_argument('--work', default=os.path.join(ROOT, 'work', 'cia'))
    ap.add_argument('--romfs-from', default=None,
                    help='romfs 의 LINKDATA 를 이 폴더 것으로 갈아 끼운다(LayeredFS 대신)')
    ap.add_argument('--no-home', action='store_true',
                    help='배너·아이콘은 건드리지 않는다')
    ap.add_argument('--code', action='store_true',
                    help='한글 코드 매핑 훅을 ExeFS 의 .code 에 넣는다(LayeredFS code.ips 대신)')
    ap.add_argument('--keep', action='store_true', help='작업 폴더를 지우지 않는다')
    a = ap.parse_args()
    np_ = os.path.normpath
    tool = lambda n: np_(os.path.join(a.tools, n + ('.exe' if os.name == 'nt' else '')))
    W = np_(os.path.join(a.work, a.tag))
    shutil.rmtree(W, ignore_errors=True)
    os.makedirs(W, exist_ok=True)
    P = lambda n: np_(os.path.join(W, n))
    L = lambda n: P(n + '.log')

    src = np_(os.path.join(a.assets, a.tag))
    patches = {}
    if not a.no_home:
        patches['icon'] = open(os.path.join(src, 'icon.bin'), 'rb').read()
        if a.tag == 'base':
            patches['banner'] = open(os.path.join(src, 'banner.bin'), 'rb').read()

    # 1) 콘텐츠 복호화 (pyctr, seed 포함)
    with CIAReader(a.cia) as c:
        ver = c.tmd.title_version
        recs = [(r.cindex, r.id) for r in c.tmd.chunk_records]
        print('원본 CIA: 타이틀 버전 %s, 콘텐츠 %s' % (ver, recs))
        got = str(c.contents[0].program_id).lower()
        if got != TID[a.tag]:
            raise SystemExit('%s 타이틀(%s)이 아닙니다: %s' % (a.tag, TID[a.tag], got))
        for idx, _cid in recs:
            dst = P('c%d.ncch' % idx)
            print('콘텐츠 %d 복호화 → %s' % (idx, dst))
            with c.contents[idx].open_raw_section(NCCHSection.FullDecrypted) as f, \
                    open(dst, 'wb') as o:
                shutil.copyfileobj(f, o, 1 << 24)

    # 2) CXI 펼치기 (romfs 는 펼치지 않고 통째로 옮긴다)
    parts = ['--header', P('ncchheader.bin'), '--exh', P('exheader.bin'),
             '--logo', P('logo.bin'), '--plain', P('plain.bin'),
             '--exefs', P('exefs.bin'), '--romfs', P('romfs.bin')]
    print('CXI 펼치기 (3dstool)')
    run([tool('3dstool'), '-xvtf', 'cxi', P('c0.ncch')] + parts, L('xcxi'))

    # 3) 한글 코드 매핑 훅
    # 실기에서 LayeredFS 가 안 먹으므로 code.ips 대신 .code 를 직접 갈아 끼운다.
    # 패치는 '압축 해제된' code 기준이라, exheader 의 CompressExefsCode 플래그를 끈다.
    if a.code:
        sys.path.insert(0, HERE)
        from hangul_font import make_patch
        patched_code, _ips, detail = make_patch(a.tag)
        patches['.code'] = patched_code
        eh = bytearray(open(P('exheader.bin'), 'rb').read())
        before = eh[0x0D]
        eh[0x0D] &= ~0x01
        open(P('exheader.bin'), 'wb').write(bytes(eh))
        print('코드 훅: entry=0x%X cave=0x%X %d바이트 / exheader flags %02X -> %02X'
              % (detail['entry'], detail['cave'], detail['hook_bytes'], before, eh[0x0D]))

    # 3) 배너·아이콘 교체
    if patches:
        print('ExeFS 교체')
        ex = open(P('exefs.bin'), 'rb').read()
        open(P('exefs.bin'), 'wb').write(rebuild_exefs(ex, patches))
    else:
        print('ExeFS 는 원본 유지')

    # 3-1) romfs 안의 LINKDATA 교체
    # 이 게임은 Luma LayeredFS 로 romfs 를 덮으면 타이틀 화면에서 죽는다(원본을 넣어도 같다).
    # 그래서 아카이브 자체를 갈아 끼운다.
    if a.romfs_from:
        rdir = P('romfs_dir')
        print('romfs 펼치기 (오래 걸린다)', flush=True)
        run([tool('3dstool'), '-xvtf', 'romfs', P('romfs.bin'), '--romfs-dir', rdir],
            L('xromfs'))
        for name in ('LINKDATA.bin', 'LINKDATA.idx'):
            target = os.path.join(rdir, name)
            source = os.path.join(a.romfs_from, name)
            if not os.path.exists(target):
                raise SystemExit('romfs 안에 %s 가 없다' % name)
            if not os.path.exists(source):
                raise SystemExit('교체할 %s 가 없다: %s' % (name, source))
            before = os.path.getsize(target)
            shutil.copyfile(source, target)
            print('   %s  %s → %s 바이트'
                  % (name, format(before, ','), format(os.path.getsize(target), ',')))
        print('romfs 다시 싸기 (오래 걸린다)', flush=True)
        run([tool('3dstool'), '-cvtf', 'romfs', P('romfs.bin'), '--romfs-dir', rdir],
            L('cromfs'))
        shutil.rmtree(rdir, ignore_errors=True)

    # 4) CXI 다시 싸기 → CIA 묶기
    print('CXI 재빌드 (--not-encrypt)', flush=True)
    run([tool('3dstool'), '-cvtf', 'cxi', P('ko.cxi')] + parts + ['--not-encrypt'], L('ccxi'))
    print('CIA 묶기 (makerom -ignoresign)')
    cmd = [tool('makerom'), '-f', 'cia', '-o', np_(a.out), '-ignoresign']
    for idx, cid in recs:
        cmd += ['-content', '%s:%d:%d' % (P('ko.cxi') if idx == 0 else P('c%d.ncch' % idx),
                                          idx, int(cid, 16))]
    run(cmd, L('makerom'))

    # 5) TMD 버전을 원본 값으로
    want = 0
    for part, shift in zip(str(ver).split('.'), (10, 4, 0)):
        want |= int(part) << shift
    with open(a.out, 'r+b') as f:
        o = tmd_version_offset(f)
        f.seek(o)
        cur = struct.unpack('>H', f.read(2))[0]
        if cur != want:
            f.seek(o)
            f.write(struct.pack('>H', want))
            print('TMD 버전 %d -> %d' % (cur, want))
    print('완료: %s (%s 바이트)' % (a.out, format(os.path.getsize(a.out), ',')))
    if not a.keep:
        shutil.rmtree(W, ignore_errors=True)


if __name__ == '__main__':
    main()
