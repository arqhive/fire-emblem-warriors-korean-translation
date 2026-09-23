"""Read-only CBMD/LZ11 extraction helpers for the HOME-menu banner.

Layout references: dnasdw/3dstool src/banner.h and src/lz77.cpp,
gdkchan/SPICA Formats/CtrGfx/Texture/GfxTexture*.cs.
CGFX textures here use unflipped Morton ABGR, unlike the G1T assets.
"""
import struct


def lz11_decompress(data):
    if len(data) < 4 or data[0] != 0x11:
        raise ValueError('Expected LZ11 header')
    size = int.from_bytes(data[1:4], 'little')
    pos = 4
    if not size:
        if len(data) < 8:
            raise ValueError('Truncated extended LZ11 header')
        size = int.from_bytes(data[4:8], 'little')
        pos = 8
    if size > 16 * 1024 * 1024:
        raise ValueError('Unexpectedly large banner section')
    out = bytearray()

    def take():
        nonlocal pos
        if pos >= len(data):
            raise ValueError('Truncated LZ11 stream')
        value = data[pos]
        pos += 1
        return value

    while len(out) < size:
        flags = take()
        for bit in range(7, -1, -1):
            if len(out) == size:
                break
            if not flags & (1 << bit):
                out.append(take())
                continue
            first = take()
            mode = first >> 4
            if mode == 0:
                second = take()
                count = ((first & 15) << 4) + (second >> 4) + 17
                high = second & 15
            elif mode == 1:
                second, third = take(), take()
                count = ((first & 15) << 12) + (second << 4) + (third >> 4) + 273
                high = third & 15
            else:
                count, high = mode + 1, first & 15
            distance = (high << 8) + take() + 1
            if distance > len(out) or len(out) + count > size:
                raise ValueError('Invalid LZ11 back-reference')
            for _ in range(count):
                out.append(out[-distance])
    return bytes(out), pos


def unpack_banner(data):
    if len(data) < 0x88 or data[:4] != b'CBMD':
        raise ValueError('Expected CBMD banner')
    offsets = struct.unpack_from('<31I', data, 8)
    audio_offset = struct.unpack_from('<I', data, 0x84)[0]
    if data[audio_offset:audio_offset+4] != b'CWAV':
        raise ValueError('Expected preserved CWAV audio')
    models = {}
    for index, offset in enumerate(offsets):
        if not offset:
            continue
        if not 0x88 <= offset < audio_offset:
            raise ValueError('Invalid CGFX offset')
        model, consumed = lz11_decompress(data[offset:audio_offset])
        if model[:4] != b'CGFX' or struct.unpack_from('<I', model, 12)[0] != len(model):
            raise ValueError('CGFX declared size mismatch')
        models[index] = dict(data=model, compressed_offset=offset,
                             compressed_size=consumed)
    return models, data[audio_offset:]
