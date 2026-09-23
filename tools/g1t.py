import struct
def parse(b):
    if len(b)<28 or b[:4]!=b'GT1G': return None
    total, tbl, cnt, plat = struct.unpack_from('<IIII', b, 8)
    if total>len(b) or tbl<28 or cnt==0 or cnt>8192 or tbl+4*cnt>total: return None
    offs=struct.unpack_from(f'<{cnt}I', b, tbl)
    out=[]
    for o in offs:
        p=tbl+o
        if o<4*cnt or p+8>total or (out and p<=out[-1][4]): return None
        # Eight-byte texture header: mip/depth, format, packed XY exponents,
        # then five flag bytes. Width/height are nominal header dimensions.
        # Reference: VitaSmith/gust_tools, gust_g1t.c, g1t_tex_header.
        mipsys, fmt, dxdy = b[p], b[p+1], b[p+2]
        out.append((fmt, 1<<(dxdy&0xF), 1<<(dxdy>>4), mipsys>>4, p))
    return out
