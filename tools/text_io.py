# -*- coding: utf-8 -*-
"""XL 텍스트 블록 읽기 / 재구성

재구성 전략: blob 전체 크기를 원본과 똑같이 유지한다.
 - 문자열 영역을 앞에서부터 다시 깔고 남는 뒤쪽은 0 으로 채운다
 - 헤더(0x00~hdr_size)와 엔트리 개수는 그대로, 각 엔트리의 offset 만 갱신
 - 따라서 상위 컨테이너·LINKDATA.idx 를 건드릴 필요가 없다 (in-place 패치 가능)
 - 제약은 '개별 문자열 길이' 가 아니라 '문자열 영역 전체 합계' 라 훨씬 느슨하다
"""
import struct

XL_MAGIC = 0x00134C58


def read_xl(blob):
    """(hdr_size, count, [(idx, id, offset, bytes)]) 또는 None"""
    if len(blob) < 0x18 or struct.unpack_from('<I', blob, 0)[0] != XL_MAGIC:
        return None
    count = struct.unpack_from('<H', blob, 8)[0]
    hdr = struct.unpack_from('<I', blob, 0xC)[0]
    if hdr < 0x10 or count == 0 or hdr + count * 8 > len(blob):
        return None
    ents = []
    for k in range(count):
        tid, off = struct.unpack_from('<II', blob, hdr + k * 8)
        p = hdr + off
        if off == 0xFFFFFFFF or p >= len(blob):
            ents.append((k, tid, off, None)); continue
        e = blob.find(b'\x00', p)
        if e < 0:
            e = len(blob)
        ents.append((k, tid, off, blob[p:e]))
    return hdr, count, ents


def rebuild_xl(blob, repl):
    """repl: {엔트리인덱스: 새 bytes}.  같은 크기의 새 blob 반환.
    문자열 영역이 넘치면 OverflowError."""
    got = read_xl(blob)
    if got is None:
        raise ValueError('XL 아님')
    hdr, count, ents = got
    data_start = hdr + count * 8
    # 문자열 영역은 '원본 문자열들이 차지하던 범위' 까지만. 그 뒤에는 다른 데이터가 있다.
    ends = [hdr + off + len(s) + 1 for _, _, off, s in ents if s is not None]
    str_end = max(ends) if ends else data_start
    limit = str_end - data_start

    # 같은 내용은 한 번만 저장(원본도 문자열을 공유한다)
    pool = {}
    order = []
    newoff = {}
    cur = 0
    for k, tid, off, s in ents:
        if off == 0xFFFFFFFF or s is None:
            newoff[k] = off; continue
        v = repl.get(k, s)
        if v in pool:
            newoff[k] = pool[v]; continue
        if cur + len(v) + 1 > limit:
            raise OverflowError(f'문자열 영역 초과: {cur + len(v) + 1} > {limit}')
        pool[v] = data_start - hdr + cur      # offset 은 hdr 기준 상대
        newoff[k] = pool[v]
        order.append(v)
        cur += len(v) + 1

    out = bytearray(blob[:data_start])
    for k, tid, off, s in ents:
        struct.pack_into('<II', out, hdr + k * 8, tid, newoff[k])
    for v in order:
        out += v + b'\x00'
    out += b'\x00' * (len(blob) - len(out))
    assert len(out) == len(blob)
    return bytes(out)


def string_region(blob):
    """(시작오프셋, 끝) — 표 영역 다음의 문자열 영역.
    표가 몇 개든 상관없이 '모든 표가 가리키는 최소 offset' 앞까지가 표 영역이다."""
    got = read_xl(blob)
    if got is None:
        return None
    hdr, count, ents = got
    # 헤더의 count 가 실제 표1 엔트리 수와 다른 blob 이 있다(2/0/4: count=3201 이지만
    # 실제 표는 훨씬 짧고 그 뒤부터 문자열이다). 그래서 표 크기를 믿지 않고
    # '유효한 offset 중 최소' 를 문자열 영역 시작으로 삼는다. offset 0 은 빈 문자열 특수값이라 제외.
    offs = [off for _, _, off, s in ents
            if s is not None and 0 < off and hdr + off < len(blob)]
    if not offs:
        return None
    return hdr + min(offs), len(blob)


def all_strings(blob):
    """문자열 영역의 널 종료 문자열 전부 → [(절대오프셋, bytes)]"""
    r = string_region(blob)
    if r is None:
        return []
    i, end = r
    out = []
    while i < end:
        e = blob.find(b'\x00', i)
        if e < 0:
            e = end
        if e > i:
            out.append((i, blob[i:e]))
        i = e + 1
    return out


def free_space(blob, min_run=12, guard=8):
    """재배치에 쓸 수 있는 빈 공간 [(blob내 오프셋, 길이)].
    조건: 문자열 영역 안 / 어떤 표도 안 가리킴 / 전부 0.
    구간 앞 guard 바이트는 남긴다(그 구간을 가리키는 표가 있어도 빈 문자열로 보이도록)."""
    import numpy as np
    got = read_xl(blob)
    if got is None:
        return []
    hdr, count, ents = got
    t1 = hdr + count * 8
    r = string_region(blob)
    if r is None:
        return []
    st, en = r
    refs = {off for _, _, off, s in ents if s is not None and hdr + off >= t1}
    if st > t1:                                   # 표1 뒤의 표들도 u32 로 훑는다
        area = blob[t1:st]
        u = np.frombuffer(area[:len(area) // 4 * 4], dtype='<u4')
        lo, hi = st - hdr, en - hdr
        refs |= {int(x) for x in u if lo <= x < hi}
    cov = bytearray(en - st)
    for off in refs:
        a = hdr + off
        e = blob.find(b'\x00', a)
        if e < 0:
            e = en
        for x in range(max(a, st), min(e + 1, en)):
            cov[x - st] = 1
    out = []
    i = 0
    n = en - st
    while i < n:
        if cov[i] or blob[st + i]:
            i += 1; continue
        j = i
        while j < n and not cov[j] and blob[st + j] == 0:
            j += 1
        if j - i >= min_run + guard:
            out.append((st + i + guard, j - i - guard))
        i = j
    return out
