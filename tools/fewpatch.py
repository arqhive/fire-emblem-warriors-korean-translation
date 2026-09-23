# -*- coding: utf-8 -*-
"""파이어 엠블렘 무쌍 한글 패치 — 일본판 CIA 한 개를 한글판 CIA 로 만든다.

타이틀 ID 로 본편·업데이트·추가 콘텐츠를 가른다.

  본편      000400000f70c100  content 0 : romfs 차분 + .code 훅 + 배너·아이콘, content 1(설명서)는 그대로
  업데이트  0004000e0f70c100  content 0 : romfs 차분 + .code 훅 + 아이콘
  DLC       0004008c0f70c100  content 2·3·4 : romfs 차분, 나머지는 그대로

차분은 romfs 단위라 romfs 를 풀었다 다시 쌀 필요가 없다(xdelta 한 번).
.code 는 BLZ 를 풀고 IPS 를 적용한 뒤 exheader 의 압축 플래그(0x0D bit0)를 끈다.

겪어 본 함정
  * CXI·CFA 는 --not-encrypt 로 다시 싸야 한다. 빠뜨리면 원본 헤더의 '암호화됨' 플래그가 남아
    평문을 다시 복호화하다 데이터가 깨진다.
  * makerom 에 -ignoresign 이 없으면 "Content 0 Is Corrupt", -content 는 <파일>:<인덱스>:<ID> 세 칸.
  * makerom 은 TMD 버전을 0 으로 써 버린다 → 원본 TMD 버전으로 되돌린다.
  * 외부 도구는 한글·일본어 경로를 못 읽는 경우가 있다 → 작업 폴더를 cwd 로 두고 짧은 영문 이름만 넘긴다.
"""
import hashlib
import json
import os
import shutil
import struct
import subprocess

import blz

TITLES = {'000400000f70c100': 'base', '0004000e0f70c100': 'update', '0004008c0f70c100': 'dlc'}
NAMES = {'base': '본편', 'update': '업데이트', 'dlc': '추가 콘텐츠(DLC)'}
SIG = {0x10000: 0x23C, 0x10001: 0x13C, 0x10002: 0x7C, 0x10003: 0x23C, 0x10004: 0x13C, 0x10005: 0x7C}
KEY_HELP = ' boot9.bin 과 seeddb.bin 이 필요합니다. README_한국어.txt 를 확인하세요.'


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------- 키

def key_dirs(extra=()):
    env = os.environ
    return [d for d in list(extra) + [
        os.path.join(env.get('APPDATA', ''), 'Azahar', 'sysdata'),
        os.path.join(env.get('APPDATA', ''), 'Citra', 'sysdata'),
        os.path.join(env.get('APPDATA', ''), 'Lime3DS', 'sysdata'),
        os.path.join(os.path.expanduser('~'), '.3ds'),
        os.path.join(os.path.expanduser('~'), '3ds'),
    ] if d]


def find_key(name, dirs):
    for d in dirs:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return None


def key_error(e):
    name = type(e).__name__
    if 'Seed' in name:
        return 'seed 암호화를 풀 seeddb.bin 이 없거나 이 게임의 seed 가 들어 있지 않습니다.' + KEY_HELP
    if 'Bootrom' in name or 'Keyslot' in name:
        return '암호화를 풀 boot9.bin 을 찾지 못했습니다.' + KEY_HELP
    return '파일을 읽지 못했습니다 (%s: %s).%s' % (name, e, KEY_HELP)


# ---------------------------------------------------------------- 도구

class Tools:
    def __init__(self, bindir, work):
        self.bin = bindir
        self.work = work

    def run(self, name, args, logname):
        exe = os.path.join(self.bin, name + ('.exe' if os.name == 'nt' else ''))
        logp = os.path.join(self.work, logname + '.log')
        with open(logp, 'wb') as f:
            r = subprocess.run([exe] + args, cwd=self.work, stdout=f, stderr=subprocess.STDOUT)
        if r.returncode:
            tail = open(logp, encoding='utf-8', errors='replace').read()[-1500:]
            raise SystemExit('%s 실패:\n%s' % (name, tail))


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 24), b''):
            h.update(b)
    return h.hexdigest()


# ---------------------------------------------------------------- CIA 읽기 (키 없이)

def read_cia(path):
    """CIA 헤더와 TMD 만 읽는다. 둘 다 평문이다.
    → dict(tid, version, records=[(인덱스, ID, 암호화?, 크기, 오프셋)]) — CIA 에 들어 있는 콘텐츠만"""
    al = lambda x: (x + 63) & ~63
    with open(path, 'rb') as f:
        head = f.read(0x2020)
        if len(head) < 0x2020:
            raise SystemExit('CIA 파일이 아닙니다.')
        hsize, _t, _v, clen, tlen, tmdlen, _m = struct.unpack_from('<IHHIIII', head, 0)
        bits = head[0x20:0x2020]
        tmd_off = al(al(al(hsize) + clen) + tlen)
        f.seek(tmd_off)
        tmd = f.read(tmdlen)
        try:
            body = 4 + SIG[struct.unpack_from('>I', tmd, 0)[0]]
        except (KeyError, struct.error):
            raise SystemExit('CIA 파일이 아닙니다 (TMD 를 읽지 못함).')
        tid = '%016x' % struct.unpack_from('>Q', tmd, body + 0x4C)[0]
        version = struct.unpack_from('>H', tmd, body + 0x9C)[0]
        count = struct.unpack_from('>H', tmd, body + 0x9E)[0]
        rec = body + 0x9C4
        off = al(tmd_off + tmdlen)
        out = []
        for i in range(count):
            cid, idx, ctype, size = struct.unpack_from('>IHHQ', tmd, rec + i * 0x30)
            if not bits[idx >> 3] & (0x80 >> (idx & 7)):
                continue                       # TMD 에는 있지만 CIA 에 빠진 콘텐츠
            out.append((idx, cid, bool(ctype & 1), size, off))
            off = al(off + size)
    return dict(tid=tid, version=version, records=out)


def ver_str(v):
    return '%d.%d.%d' % (v >> 10, (v >> 4) & 63, v & 15)


def is_plain(path, recs):
    """콘텐츠가 모두 평문(CIA 암호 없음 + NCCH NoCrypto)인가"""
    with open(path, 'rb') as f:
        for _i, _c, enc, _s, off in recs:
            if enc:
                return False
            f.seek(off)
            n = f.read(0x200)
            if n[0x100:0x104] != b'NCCH' or not n[0x18F] & 0x04:
                return False
    return True


def extract_contents(src, info, W, keys):
    """콘텐츠를 평문 NCCH 로 작업 폴더에 꺼낸다 → c<인덱스>.ncch"""
    recs = info['records']
    if is_plain(src, recs):
        for idx, _cid, _e, size, off in recs:
            log('  복사: 콘텐츠 %d (이미 복호화된 CIA)' % idx)
            with open(src, 'rb') as f, open(W('c%d.ncch' % idx), 'wb') as o:
                f.seek(off)
                left = size
                while left:
                    b = f.read(min(left, 1 << 24))
                    if not b:
                        raise SystemExit('CIA 파일이 잘려 있습니다.')
                    o.write(b)
                    left -= len(b)
        return
    boot9, seeddb = keys
    if not boot9:
        raise SystemExit('암호화된 CIA 입니다.' + KEY_HELP)
    try:
        from pyctr.crypto import load_seeddb
        from pyctr.type.cia import CIAReader
        from pyctr.type.ncch import NCCHSection
        if seeddb:
            load_seeddb(seeddb)
        with CIAReader(src) as rd:
            for idx, _cid, _e, _s, _o in recs:
                log('  복호화: 콘텐츠 %d' % idx)
                with rd.contents[idx].open_raw_section(NCCHSection.FullDecrypted) as f, \
                        open(W('c%d.ncch' % idx), 'wb') as o:
                    shutil.copyfileobj(f, o, 1 << 24)
    except SystemExit:
        raise
    except Exception as e:
        raise SystemExit(key_error(e))


# ---------------------------------------------------------------- ExeFS·코드

def rebuild_exefs(d, patches):
    """ExeFS 블롭에서 patches({이름: 내용})만 바꿔 다시 쓴다. 오프셋·크기·SHA-256 재계산."""
    entries = []
    for i in range(10):
        name, off, size = struct.unpack_from('<8sII', d, i * 16)
        if not size:
            continue
        key = name.rstrip(b'\0').decode()
        entries.append((name, key, patches.get(key, d[0x200 + off:0x200 + off + size])))
    missing = set(patches) - {k for _, k, _ in entries}
    if missing:
        raise SystemExit('ExeFS 에 %s 항목이 없습니다.' % ', '.join(sorted(missing)))
    hdr = bytearray(0x200)
    blob = bytearray()
    for i, (name, _key, body) in enumerate(entries):
        struct.pack_into('<8sII', hdr, i * 16, name, len(blob), len(body))
        hdr[0x200 - (i + 1) * 32:0x200 - i * 32] = hashlib.sha256(body).digest()
        blob += body
        blob += b'\0' * ((-len(blob)) % 0x200)
    return bytes(hdr) + bytes(blob)


def read_exefs(d):
    out = {}
    for i in range(10):
        name, off, size = struct.unpack_from('<8sII', d, i * 16)
        if size:
            out[name.rstrip(b'\0').decode()] = d[0x200 + off:0x200 + off + size]
    return out


def apply_ips(data, ips):
    if ips[:5] != b'PATCH':
        raise SystemExit('IPS 패치 파일이 손상됐습니다.')
    out = bytearray(data)
    i = 5
    while ips[i:i + 3] != b'EOF':
        off = int.from_bytes(ips[i:i + 3], 'big')
        size = int.from_bytes(ips[i + 3:i + 5], 'big')
        i += 5
        if size:
            chunk = ips[i:i + size]
            i += size
        else:                                  # RLE
            rle = int.from_bytes(ips[i:i + 2], 'big')
            chunk = ips[i + 2:i + 3] * rle
            i += 3
        if off + len(chunk) > len(out):
            out.extend(b'\0' * (off + len(chunk) - len(out)))
        out[off:off + len(chunk)] = chunk
    return bytes(out)


def patch_code(code, spec, payload):
    """BLZ 압축된 .code → 훅을 넣은 비압축 .code"""
    try:
        plain = blz.decompress(code)
    except Exception:
        plain = code
    if hashlib.sha256(plain).hexdigest() != spec['source_sha256']:
        raise SystemExit('실행 코드(.code)가 예상과 다릅니다. 다른 버전이거나 이미 패치한 파일입니다.')
    out = apply_ips(plain, open(os.path.join(payload, spec['ips']), 'rb').read())
    if hashlib.sha256(out).hexdigest() != spec['result_sha256']:
        raise SystemExit('코드 패치 결과가 예상과 다릅니다. 패치 파일이 손상됐을 수 있습니다.')
    return out


def apply_romfs(T, W, payload, spec, src_name, dst_name, label):
    log('  %s romfs 확인 중...' % label)
    if os.path.getsize(W(src_name)) != spec['source_size'] or \
            sha256_file(W(src_name)) != spec['source_sha256']:
        raise SystemExit('%s romfs 가 원본과 다릅니다. 다른 버전이거나 이미 패치한 파일입니다.' % label)
    log('  %s romfs 차분 적용 중...' % label)
    shutil.copyfile(os.path.join(payload, spec['patch']), W('patch.xdelta'))
    T.run('xdelta3', ['-d', '-f', '-s', src_name, 'patch.xdelta', dst_name], 'xdelta_' + label)
    os.remove(W('patch.xdelta'))
    os.remove(W(src_name))
    if sha256_file(W(dst_name)) != spec['result_sha256']:
        raise SystemExit('%s romfs 패치 결과가 예상과 다릅니다. 패치 파일이 손상됐을 수 있습니다.' % label)


def fix_tmd_version(cia, version):
    al = lambda x: (x + 63) & ~63
    with open(cia, 'r+b') as f:
        hsize, _t, _v, clen, tlen, _tmdlen, _m = struct.unpack('<IHHIIII', f.read(0x18))
        off = al(al(al(hsize) + clen) + tlen)
        f.seek(off)
        sig = struct.unpack('>I', f.read(4))[0]
        o = off + 4 + SIG[sig] + 0x9C
        f.seek(o)
        if struct.unpack('>H', f.read(2))[0] != version:
            f.seek(o)
            f.write(struct.pack('>H', version))


# ---------------------------------------------------------------- 본체

def identify(src):
    info = read_cia(src)
    return TITLES.get(info['tid']), info


def patch(src, dst, payload, bindir, work, key_extra=(), keep=False):
    """src(.cia) → dst(.cia). 실패해도 작업 폴더는 지운다."""
    try:
        return _patch(src, dst, payload, bindir, work, key_extra)
    finally:
        if not keep:
            shutil.rmtree(work, ignore_errors=True)


def _patch(src, dst, payload, bindir, work, key_extra):
    man = json.load(open(os.path.join(payload, 'manifest.json'), encoding='utf-8'))
    tag, info = identify(src)
    if not tag:
        raise SystemExit('일본판 파이어 엠블렘 무쌍 CIA 가 아닙니다 (타이틀 ID %s).' % info['tid'])
    spec = man['titles'][tag]
    log('%s v%s, 콘텐츠 %s' % (NAMES[tag], ver_str(info['version']),
                             ', '.join(str(r[0]) for r in info['records'])))
    present = {r[0] for r in info['records']}
    need = {int(k) for k in spec['contents']}
    if tag in ('base', 'update') and 0 not in present:
        raise SystemExit('프로그램 콘텐츠(0번)가 없는 CIA 입니다.')
    if tag == 'dlc' and not need & present:
        raise SystemExit('한글화할 추가 콘텐츠(2·3·4번)가 이 CIA 에 없습니다.')

    dirs = key_dirs(key_extra)
    boot9, seeddb = find_key('boot9.bin', dirs), find_key('seeddb.bin', dirs)
    # pyctr 는 키 경로를 환경 변수에서 읽는다
    if boot9:
        os.environ['BOOT9_PATH'] = boot9
    if seeddb:
        os.environ['SEEDDB_PATH'] = seeddb

    if os.path.exists(work):
        shutil.rmtree(work)
    os.makedirs(work)
    free = shutil.disk_usage(work).free
    want = {'base': 9, 'update': 1, 'dlc': 5}[tag] << 30
    if free < want:
        raise SystemExit('작업 폴더의 디스크 공간이 부족합니다 (남은 %.1fGB, 필요 약 %dGB).'
                         % (free / (1 << 30), want >> 30))
    T = Tools(bindir, work)
    W = lambda n: os.path.join(work, n)

    log('1) 콘텐츠 꺼내기')
    extract_contents(src, info, W, (boot9, seeddb))
    built = {}

    if tag in ('base', 'update'):
        with open(W('c0.ncch'), 'rb') as f:
            h = f.read(0x200)
        if h[0x100:0x104] != b'NCCH' or '%016x' % struct.unpack_from('<Q', h, 0x118)[0] not in TITLES:
            raise SystemExit('복호화 결과가 올바르지 않습니다.' + KEY_HELP)
        cx = ['--header', 'hdr.bin', '--exh', 'exh.bin', '--logo', 'logo.bin', '--plain', 'plain.bin',
              '--exefs', 'exefs.bin', '--romfs', 'romfs.bin']
        log('2) 프로그램 펼치기')
        T.run('3dstool', ['-xvtf', 'cxi', 'c0.ncch'] + cx, 'xcxi')
        os.remove(W('c0.ncch'))

        log('3) 실행 코드·HOME 메뉴')
        ex = open(W('exefs.bin'), 'rb').read()
        files = read_exefs(ex)
        patches = {'.code': patch_code(files['.code'], spec['code'], payload)}
        for key, item in spec['exefs'].items():
            body = open(os.path.join(payload, item['file']), 'rb').read()
            if hashlib.sha256(body).hexdigest() != item['sha256']:
                raise SystemExit('패치 파일이 손상됐습니다: ' + item['file'])
            patches[key] = body
        open(W('exefs.bin'), 'wb').write(rebuild_exefs(ex, patches))
        eh = bytearray(open(W('exh.bin'), 'rb').read())
        eh[0x0D] &= ~0x01                       # CompressExefsCode 끔 (.code 를 풀어서 넣었다)
        open(W('exh.bin'), 'wb').write(bytes(eh))
        log('  한글 코드 훅, %s 교체' % ('배너·아이콘' if 'banner' in patches else '아이콘'))

        log('4) 게임 데이터')
        apply_romfs(T, W, payload, spec['contents']['0'], 'romfs.bin', 'romfs_ko.bin', 'c0')
        os.replace(W('romfs_ko.bin'), W('romfs.bin'))

        log('5) 다시 묶기')
        T.run('3dstool', ['-cvtf', 'cxi', 'ko0.ncch'] + cx + ['--not-encrypt'], 'ccxi')
        os.remove(W('romfs.bin'))
        built[0] = 'ko0.ncch'
    else:
        log('2) 추가 콘텐츠 대사')
        for key in sorted(spec['contents'], key=int):
            idx = int(key)
            if idx not in present:
                log('  콘텐츠 %d 없음, 건너뜀' % idx)
                continue
            n = 'c%d' % idx
            T.run('3dstool', ['-xvtf', 'cfa', n + '.ncch', '--header', n + '_h.bin',
                              '--romfs', n + '_r.bin'], 'x' + n)
            os.remove(W(n + '.ncch'))
            apply_romfs(T, W, payload, spec['contents'][key], n + '_r.bin', n + '_rk.bin', n)
            T.run('3dstool', ['-cvtf', 'cfa', 'ko%d.ncch' % idx, '--header', n + '_h.bin',
                              '--romfs', n + '_rk.bin', '--not-encrypt'], 'c' + n)
            os.remove(W(n + '_rk.bin'))
            built[idx] = 'ko%d.ncch' % idx
        log('3) 다시 묶기')

    args = ['-f', 'cia', '-o', 'out.cia', '-ignoresign']
    for idx, cid, _e, _s, _o in info['records']:
        args += ['-content', '%s:%d:%d' % (built.get(idx, 'c%d.ncch' % idx), idx, cid)]
    T.run('makerom', args, 'makerom')
    fix_tmd_version(W('out.cia'), info['version'])
    if os.path.exists(dst):
        os.remove(dst)
    shutil.move(W('out.cia'), dst)
    return tag
