"""XL 텍스트 포맷(magic 0x00134C58) 파서"""
import struct
XL_MAGIC = 0x00134C58

def parse(b):
    """(id, 문자열bytes) 리스트 반환. 실패시 None"""
    if len(b) < 0x18 or struct.unpack_from('<I', b, 0)[0] != XL_MAGIC:
        return None
    count = struct.unpack_from('<H', b, 8)[0]
    hdr   = struct.unpack_from('<I', b, 0xC)[0]
    if hdr < 0x10 or hdr > len(b): return None
    tbl_end = hdr + count*8
    if count == 0 or tbl_end > len(b): return None
    out = []
    for k in range(count):
        tid, off = struct.unpack_from('<II', b, hdr + k*8)
        p = hdr + off
        if p >= len(b): continue
        e = b.find(b'\x00', p)
        if e < 0: e = len(b)
        out.append((tid, b[p:e]))
    return out
