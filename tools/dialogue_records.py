"""Strict parser for sequential, length-prefixed Japanese dialogue records.

Two observed layouts: (u16 ordinal, u16 length) and
(u16 ordinal, u16 cue, u16 length). The game reads the stored length as
CP932 byte count + newline count + 1 (stored_length()) and uses it to find the
next record. Original Japanese text is all double-byte except newlines, so it
also equals twice the character count plus one; three original records with a
stray half-width space follow that form instead. The byte record ends at NUL.
No mutation or guessing about container sizes is performed here.
"""
import struct

import ctrl
from extract_text import KANA, HANKAKU


def stored_length(raw):
    """게임이 다음 레코드를 찾을 때 쓰는 길이: CP932 바이트 수 + 개행 수 + 1.

    「글자 수×2+1」은 원본 일본어(개행 말고 전부 2바이트)에서만 같은 값이다.
    반각 문자가 섞인 한글에 그 식을 쓰면 반각 하나마다 1씩 커져 둘째 대사부터
    엉뚱한 줄이나 빈칸이 나온다(v0.1). 오프닝 진단 빌드로 확인했다.
    """
    return len(raw) + raw.count(b'\n') + 1


def first_record_candidates(blob):
    """Retain near-misses for manual inspection instead of silently dropping them."""
    result = []
    if len(blob) < 7 or blob[:2] != b'\x01\x00':
        return result
    for width in (4, 6):
        end = blob.find(b'\0', width)
        if end < width or end - width > 4096:
            continue
        raw = blob[width:end]
        try:
            decoded = raw.decode('cp932')
            text = ctrl.to_text(raw)
        except UnicodeDecodeError:
            continue
        length = struct.unpack_from('<H', blob, width - 2)[0]
        if (len(KANA.findall(text)) >= 2 and not HANKAKU.search(text)
                and all(ord(c) >= 32 or c in '\n\t' for c in text)
                and length == 2 * len(decoded) + 1):
            result.append(dict(record_width=width, first_source=text))
    return result


def parse(blob, japanese_only=True):
    if len(blob) < 7 or blob[:2] != b'\x01\x00':
        return None
    candidates = []
    for width in (4, 6):
        rows, pos, ordinal = [], 0, 1
        while pos + width <= len(blob):
            number = struct.unpack_from('<H', blob, pos)[0]
            size = struct.unpack_from('<H', blob, pos + width - 2)[0]
            start = pos + width
            if (number != ordinal and not (number == 0 and rows)) or size < 1 or start >= len(blob):
                break
            nul = blob.find(b'\0', start)
            if nul < 0:
                break
            raw = blob[start:nul]
            end = nul + 1
            # One observed resource ends with a default (index 0) copy of its
            # final line. Keep that reference too; do not discard the whole block.
            if number == 0 and (end != len(blob) or raw.hex() != rows[-1]['source_hex']):
                break
            try:
                decoded = raw.decode('cp932')
                text = ctrl.to_text(raw)
            except UnicodeDecodeError:
                break
            if size not in (2 * len(decoded) + 1, stored_length(raw)):
                break
            if any(ord(c) < 32 and c not in '\n\t' for c in text):
                break
            rows.append(dict(index=number, header_offset=pos, offset=start,
                stored_length=size, length=len(raw) + 1, source_hex=raw.hex(), source=text,
                cue=struct.unpack_from('<H', blob, pos + 2)[0] if width == 6 else None))
            pos, ordinal = end, ordinal + 1
        if pos == len(blob) and rows:
            if not japanese_only or (any(KANA.search(r['source']) for r in rows)
                    and not any(HANKAKU.search(r['source']) for r in rows)):
                candidates.append(dict(record_width=width, entries=rows))
    return candidates[0] if len(candidates) == 1 else None
