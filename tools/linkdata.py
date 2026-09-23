"""FE무쌍(3DS) LINKDATA 파서 — idx/bin + 재귀 컨테이너"""
import struct, os, hashlib

def index_absence_proof(idx, slot):
    """Distinguish absent tail slots from empty entries; bind proof to the index."""
    if slot < 0 or len(idx) % 8:
        raise ValueError('Invalid slot or incomplete archive index')
    entries = len(idx) // 8
    if slot >= entries:
        return dict(classification='outside_archive_index', slot=slot,
                    index_entries=entries, index_bytes=len(idx),
                    index_sha256=hashlib.sha256(idx).hexdigest())
    return None

class LinkData:
    def __init__(self, idx_path, bin_path):
        with open(idx_path, 'rb') as handle:
            self.idx = handle.read()
        self.f = open(bin_path,'rb')
        self.n = len(self.idx)//8

    def entry(self, i):
        a,off = struct.unpack_from('<II', self.idx, i*8)
        return (a>>24), (a & 0xFFFFFF), off

    def used(self):
        for i in range(self.n):
            flag,sz,off = self.entry(i)
            if sz or flag: yield i,sz,off

    def read(self, i):
        flag,sz,off = self.entry(i)
        self.f.seek(off); return self.f.read(sz)

def is_container(d):
    """count + (offset,size)[count] 형태인지 검사"""
    if len(d) < 12: return None
    cnt, = struct.unpack_from('<I', d, 0)
    if not (1 <= cnt <= 4096): return None
    hdr = 4 + cnt*8
    if hdr > len(d): return None
    first_off, = struct.unpack_from('<I', d, 4)
    if first_off != hdr: return None
    out = []
    prev_end = hdr
    for k in range(cnt):
        o,s = struct.unpack_from('<II', d, 4+k*8)
        if o < hdr or s > len(d) or o+s > len(d): return None
        if o < prev_end - 16: return None
        prev_end = o+s
        out.append((o,s))
    return out

def walk(d, path='', depth=0, maxdepth=8):
    """리프 블롭을 (경로, 바이트) 로 순회"""
    ch = is_container(d) if depth < maxdepth else None
    if ch is None:
        yield path, d
        return
    for k,(o,s) in enumerate(ch):
        yield from walk(d[o:o+s], f'{path}/{k}', depth+1, maxdepth)
