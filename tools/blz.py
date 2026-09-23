# -*- coding: utf-8 -*-
"""3DS code.bin BLZ(backward LZ77) 해제"""
import struct

def decompress(data):
    d = bytes(data)
    inc_len = struct.unpack_from('<I', d, len(d) - 4)[0]
    if inc_len == 0:
        return d[:-8]
    hdr_len = d[len(d) - 5]
    if not (8 <= hdr_len <= 0x0B):
        raise ValueError(f'헤더 길이 이상: {hdr_len}')
    enc_len = struct.unpack_from('<I', d, len(d) - 8)[0] & 0x00FFFFFF
    dec_len = len(d) - enc_len          # 비압축 선두 길이
    if dec_len < 0:
        raise ValueError('enc_len 이 파일보다 큼')
    comp = d[dec_len: len(d) - hdr_len][::-1]      # 뒤집어서 정방향 해제
    out = bytearray()
    i = 0
    n = len(comp)
    while i < n:
        flags = comp[i]; i += 1
        for _ in range(8):
            if i >= n:
                break
            if flags & 0x80:
                if i + 1 >= n:
                    break
                j = (comp[i] << 8) | comp[i + 1]; i += 2
                disp = (j & 0x0FFF) + 3
                ln = (j >> 12) + 3
                for _ in range(ln):
                    out.append(out[len(out) - disp])
            else:
                out.append(comp[i]); i += 1
            flags = (flags << 1) & 0xFF
    return d[:dec_len] + bytes(out)[::-1]
