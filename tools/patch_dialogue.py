"""Scoped sequential dialogue patches; preserve record IDs, cues and sibling data.

Relocate complete parent resources through LINKDATA.idx, retaining original data.
The game consumer still requires runtime validation; structural checks alone do
not establish that a relocated resource is accepted by every loader.
"""
import hashlib
import json
import struct
from pathlib import Path

import ctrl
from dialogue_records import parse
from kopatch import encode_ko, lint
from linkdata import LinkData, is_container
import tl

MANIFEST = Path('translation/dialogue_ko.json')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_manifest():
    if not MANIFEST.exists():
        return []
    rows = tl.load_dialogue()
    seen = set()
    for row in rows:
        key = (row['tag'], row['path'], row['index'])
        if key in seen or row['tag'] not in ('base', 'update'):
            raise ValueError(('duplicate or unsupported target', key))
        seen.add(key)
        if row['source'] != ctrl.to_text(bytes.fromhex(row['source_hex'])):
            raise ValueError(('source text mismatch', key))
        if not row['translation'].strip() or '\0' in row['translation']:
            raise ValueError(('empty or embedded NUL', key))
    return rows


def rebuild_records(blob, edits, codes):
    parsed = parse(blob)
    if parsed is None:
        raise ValueError('Original dialogue does not parse unambiguously')
    width = parsed['record_width']
    by_index = {r['index']: r for r in edits}
    if len(by_index) != len(edits):
        raise ValueError('Duplicate dialogue index')
    output, expected, used = bytearray(), [], set()
    for row in parsed['entries']:
        raw = bytes.fromhex(row['source_hex'])
        edit = by_index.get(row['index'])
        if edit:
            if edit['source_hex'] != raw.hex():
                raise ValueError(('Source mismatch', row['index']))
            errors = lint(raw, edit['translation'], codes, check_len=False)
            if errors:
                raise ValueError(errors)
            raw = encode_ko(edit['translation'], codes)
            used.add(row['index'])
        # Final index 0 is the default copy of the preceding record.
        if row['index'] == 0:
            if edit and raw != expected[-1][2]:
                raise ValueError('Default record differs from final dialogue')
            raw = expected[-1][2]
        if b'\0' in raw:
            raise ValueError('Embedded NUL in dialogue')
        stored = 2 * len(raw.decode('cp932')) + 1
        if stored > 65535:
            raise ValueError('Dialogue length exceeds u16')
        header = bytearray(blob[row['header_offset']:row['offset']])
        struct.pack_into('<H', header, width - 2, stored)
        output.extend(header + raw + b'\0')
        expected.append((row['index'], row['cue'], raw))
    if used != set(by_index):
        raise ValueError(('Missing indices', set(by_index) - used))
    rebuilt = parse(output, japanese_only=False)
    if rebuilt is None or rebuilt['record_width'] != width:
        raise ValueError('Rebuilt dialogue failed structural readback')
    actual = [(r['index'], r['cue'], bytes.fromhex(r['source_hex']))
              for r in rebuilt['entries']]
    if actual != expected:
        raise ValueError('Rebuilt record IDs, cues or text differ')
    return bytes(output)


def replace_leaf(blob, path, replacement):
    """Repack known offset/size containers, rejecting overlaps/unknown padding."""
    if not path:
        return replacement
    children = is_container(blob)
    index, *rest = path
    if children is None or not 0 <= index < len(children):
        raise ValueError('Invalid container path')
    cursor = 4 + 8 * len(children)
    pieces = []
    for offset, size in children:
        if offset < cursor or any(blob[cursor:offset]):
            raise ValueError('Overlapping children or nonzero container padding')
        pieces.append(blob[offset:offset + size])
        cursor = offset + size
    if any(blob[cursor:]):
        raise ValueError('Nonzero container trailer')
    pieces[index] = replace_leaf(pieces[index], rest, replacement)
    result = bytearray(4 + 8 * len(children))
    struct.pack_into('<I', result, 0, len(children))
    for i, piece in enumerate(pieces):
        result.extend(b'\0' * (-len(result) % 4))
        struct.pack_into('<II', result, 4 + 8 * i, len(result), len(piece))
        result.extend(piece)
    result.extend(b'\0' * (-len(result) % 4))
    new_children = is_container(result)
    if new_children is None:
        raise ValueError('Rebuilt container invalid')
    for i, (offset, size) in enumerate(new_children):
        if result[offset:offset + size] != pieces[i]:
            raise ValueError('Sibling readback mismatch')
    return bytes(result)


def leaf(blob, path):
    for index in path:
        children = is_container(blob)
        if children is None or not 0 <= index < len(children):
            raise ValueError('Invalid resource path')
        offset, size = children[index]
        blob = blob[offset:offset + size]
    return blob


def patch_archive(tag, source_paths, target, rows, codes, allowed_flags=(0, 1)):
    rows = [r for r in rows if r['tag'] == tag]
    inventory = json.loads(Path('extract/dialogue_v2/blocks.json').read_text(encoding='utf-8'))
    blocks = {(r['tag'], r['path']): r for r in inventory}
    grouped = {}
    for row in rows:
        grouped.setdefault(row['path'], []).append(row)
    original = LinkData(*source_paths)
    destination = LinkData(target / 'LINKDATA.idx', target / 'LINKDATA.bin')
    index = bytearray(destination.idx)
    original_index = bytes(index)
    by_slot, details = {}, []
    try:
        # Validate every target before making any writes.
        for path, edits in grouped.items():
            slot, *route = map(int, path.split('/'))
            # These exact resources are uncompressed containers in both archives.
            # Index flags seen so far: 0 base, 1 update, 3/4/5 for DLC c2/c3/c4.
            # The flag is preserved either way; the check only rejects unexamined ones.
            if original.entry(slot)[0] not in allowed_flags:
                raise ValueError(('Unexamined dialogue index flag', tag, slot))
            block = blocks[(tag, path)]
            source = leaf(original.read(slot), route)
            if sha(source) != block['sha256']:
                raise ValueError(('Inventory hash mismatch', tag, path))
            parent = by_slot.get(slot, destination.read(slot))
            if leaf(parent, route) != source:
                raise ValueError(('Target already changed', tag, path))
            replacement = rebuild_records(source, edits, codes)
            by_slot[slot] = replace_leaf(parent, route, replacement)
            details.append(dict(path=path, translated_records=len(edits),
                original_sha256=sha(source), patched_sha256=sha(replacement),
                old_size=len(source), new_size=len(replacement)))
    finally:
        original.f.close()
        destination.f.close()
    relocations = []
    with (target / 'LINKDATA.bin').open('r+b') as handle:
        handle.seek(0, 2)
        for slot, blob in sorted(by_slot.items()):
            handle.write(b'\0' * (-handle.tell() % 16))
            offset = handle.tell()
            if len(blob) > 0xFFFFFF or offset + len(blob) > 0xFFFFFFFF:
                raise ValueError('LINKDATA index capacity exceeded')
            old, old_offset = struct.unpack_from('<II', index, slot * 8)
            struct.pack_into('<II', index, slot * 8, (old & 0xFF000000) | len(blob), offset)
            handle.write(blob)
            relocations.append(dict(slot=slot, old_offset=old_offset, new_offset=offset,
                old_size=old & 0xFFFFFF, new_size=len(blob), sha256=sha(blob)))
    (target / 'LINKDATA.idx').write_bytes(index)
    check = LinkData(target / 'LINKDATA.idx', target / 'LINKDATA.bin')
    try:
        for slot, blob in by_slot.items():
            if check.read(slot) != blob:
                raise ValueError(('Archive disk readback mismatch', slot))
        for slot in range(check.n):
            if slot not in by_slot and check.idx[slot*8:slot*8+8] != original_index[slot*8:slot*8+8]:
                raise ValueError(('Unrelated index changed', slot))
    finally:
        check.f.close()
    return dict(translated_records=len(rows), rebuilt_blocks=len(details),
        omitted_records=0, disk_readback_verified=True,
        blocks=details, relocations=relocations, runtime_verified=False)
