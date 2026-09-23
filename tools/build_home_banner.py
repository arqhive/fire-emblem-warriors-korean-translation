# -*- coding: utf-8 -*-
"""승인된 HOME 배너 시안을 게임 형식(CGFX 텍스처)으로 바꾸고 CBMD 를 다시 묶는다.

승인된 배치는 `placed_proposal_A.svg` 다. 내용은
「korean_banner_A.png 를 256x128 로 놓고 original_variant_9.png 의 알파를 마스크로 씌운다」
이므로 SVG 렌더러 없이 그대로 재현한다. 생성 PNG 를 그냥 넣으면 불투명 사각형 배경이 남는다.

CGFX 텍스처는 G1T 와 달리 Y축을 뒤집지 않는 모턴 ABGR 이다.
텍스처 payload 만 바꾸고 장면·모델·애니메이션·CWAV 오디오는 원본 바이트를 그대로 둔다.
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ctrtex import morton8_abgr32_rgba
from ctrtex_encode import abgr32_encode
from home_menu_assets import lz11_decompress, unpack_banner

REVIEW = Path('reports/graphics_review/home_menu')
BANNER = Path('extract/exefs/base_banner.bin')
OUT = Path('work/home_menu')
W, H = 256, 128


def sha(b):
    return hashlib.sha256(b).hexdigest()


# --------------------------------------------------------------- LZ11 압축
def lz11_compress(data, window=4096, max_len=0xFFFF + 273):
    """3dstool 과 같은 LZ11 스트림을 만든다. 되돌려 풀면 입력과 바이트가 같아야 한다."""
    n = len(data)
    out = bytearray()
    if n < 0x1000000:
        out += bytes([0x11]) + n.to_bytes(3, 'little')
    else:
        out += bytes([0x11, 0, 0, 0]) + n.to_bytes(4, 'little')

    heads = {}          # 3바이트 키 → 최근 위치 목록
    pos = 0
    chunk = bytearray()
    flags = 0
    bit = 7

    def flush():
        nonlocal chunk, flags, bit
        if bit != 7 or chunk:
            out.append(flags)
            out.extend(chunk)
        chunk = bytearray()
        flags = 0
        bit = 7

    while pos < n:
        best_len, best_dist = 0, 0
        if pos + 3 <= n:
            key = data[pos:pos + 3]
            for cand in reversed(heads.get(bytes(key), ())):
                dist = pos - cand
                if dist > window:
                    break
                length = 3
                limit = min(max_len, n - pos)
                while length < limit and data[cand + length] == data[pos + length]:
                    length += 1
                if length > best_len:
                    best_len, best_dist = length, dist
                    if length >= limit:
                        break

        if best_len >= 3:
            flags |= 1 << bit
            d = best_dist - 1
            if best_len <= 16:
                chunk += bytes([((best_len - 1) << 4) | (d >> 8), d & 0xFF])
            elif best_len <= 272:
                v = best_len - 17
                chunk += bytes([v >> 4, ((v & 0xF) << 4) | (d >> 8), d & 0xFF])
            else:
                v = best_len - 273
                chunk += bytes([0x10 | (v >> 12), (v >> 4) & 0xFF,
                                ((v & 0xF) << 4) | (d >> 8), d & 0xFF])
            step = best_len
        else:
            chunk.append(data[pos])
            step = 1

        for k in range(pos, pos + step):
            if k + 3 <= n:
                heads.setdefault(bytes(data[k:k + 3]), []).append(k)
        pos += step
        bit -= 1
        if bit < 0:
            flush()
    flush()
    return bytes(out)


# --------------------------------------------------------------- 배너 이미지
def korean_texture():
    """승인된 배치를 256x128 RGBA 로 재현한다."""
    art = Image.open(REVIEW / 'korean_banner_A.png').convert('RGBA').resize(
        (W, H), Image.LANCZOS)
    mask = Image.open(REVIEW / 'original_variant_9.png').convert('RGBA')
    if mask.size != (W, H):
        raise ValueError('원본 배너 크기가 다르다: %r' % (mask.size,))
    out = np.array(art, dtype=np.uint8)
    out[..., 3] = np.array(mask, dtype=np.uint8)[..., 3]      # 원본 알파를 그대로
    return out


# --------------------------------------------------------------- 재조립
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    raw = BANNER.read_bytes()
    models, audio = unpack_banner(raw)
    audio_offset = struct.unpack_from('<I', raw, 0x84)[0]
    targets = json.loads((REVIEW / 'source_textures.json').read_text('utf-8'))
    by_variant = {t['variant']: t for t in targets}

    rgba = korean_texture()
    Image.fromarray(rgba, 'RGBA').save(OUT / 'korean_banner_native.png')
    payload = abgr32_encode(rgba, flip=False)
    if len(payload) != W * H * 4:
        raise ValueError('payload 크기가 맞지 않는다: %d' % len(payload))
    # 왕복 검증: 인코딩한 것을 다시 풀면 원래 픽셀이어야 한다
    back = morton8_abgr32_rgba(payload, W, H, flip=False)
    if not np.array_equal(np.asarray(back, dtype=np.uint8)[..., :4], rgba):
        raise ValueError('ABGR 왕복이 일치하지 않는다')

    report = {'source': str(BANNER), 'source_sha256': sha(raw),
              'texture_sha256': sha(payload), 'variants': []}

    new_models = {}
    for index, info in sorted(models.items()):
        data = bytearray(info['data'])
        t = by_variant.get(index)
        if t is not None:
            off, size = t['payload_offset'], t['payload_size']
            if size != len(payload):
                raise ValueError('변종 %d payload 크기 불일치' % index)
            before = bytes(data[off:off + size])
            if sha(before) != t['payload_sha256']:
                raise ValueError('변종 %d 원본 payload 해시가 기록과 다르다' % index)
            data[off:off + size] = payload
            report['variants'].append(dict(
                variant=index, replaced=True, payload_offset=off,
                before_sha256=sha(before), after_sha256=sha(payload),
                outside_payload_preserved=(
                    bytes(data[:off]) == info['data'][:off] and
                    bytes(data[off + size:]) == info['data'][off + size:])))
        else:
            report['variants'].append(dict(variant=index, replaced=False))
        # CGFX 는 헤더 0x0C 에 자기 크기를 적어 둔다. payload 만 바꾸므로 그대로여야 한다.
        if struct.unpack_from('<I', data, 12)[0] != len(data):
            raise ValueError('변종 %d CGFX 크기 필드가 깨졌다' % index)
        new_models[index] = bytes(data)

    # CBMD 다시 쓰기. 헤더 0x88 은 원본을 두고 오프셋만 갱신한다.
    head = bytearray(raw[:0x88])
    body = bytearray()
    offsets = [0] * 31
    for index in sorted(new_models):
        comp = lz11_compress(new_models[index])
        restored, _ = lz11_decompress(comp)
        if restored != new_models[index]:
            raise ValueError('변종 %d LZ11 왕복 실패' % index)
        offsets[index] = 0x88 + len(body)
        body += comp
    pad = (-(0x88 + len(body))) % 32              # CWAV 는 32바이트 정렬
    body += bytes(pad)
    new_audio_offset = 0x88 + len(body)
    for i, off in enumerate(offsets):
        struct.pack_into('<I', head, 8 + i * 4, off)
    struct.pack_into('<I', head, 0x84, new_audio_offset)
    out = bytes(head) + bytes(body) + audio

    # 재조립본을 다시 읽어 원본과 대조한다
    check_models, check_audio = unpack_banner(out)
    if check_audio != audio:
        raise ValueError('CWAV 오디오가 보존되지 않았다')
    if set(check_models) != set(new_models):
        raise ValueError('CGFX 구성이 달라졌다')
    for index in new_models:
        if check_models[index]['data'] != new_models[index]:
            raise ValueError('변종 %d 재조립 결과가 다르다' % index)

    (OUT / 'banner_ko.bin').write_bytes(out)
    report.update(output='work/home_menu/banner_ko.bin', output_sha256=sha(out),
                  original_size=len(raw), output_size=len(out),
                  audio_offset_before=audio_offset, audio_offset_after=new_audio_offset,
                  audio_sha256=sha(audio), audio_preserved=True,
                  repack_verified=True)
    (OUT / 'banner_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')

    print('CGFX 변종 %d개, 교체 %d개' % (
        len(new_models), sum(1 for v in report['variants'] if v['replaced'])))
    print('배너 %s → %s 바이트' % (f'{len(raw):,}', f'{len(out):,}'))
    print('CWAV 오프셋 %d → %d (오디오 보존)' % (audio_offset, new_audio_offset))
    print('출력 work/home_menu/banner_ko.bin')


if __name__ == '__main__':
    main()
