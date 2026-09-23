"""Read-only archive census. Keep rejected strings and exclusion reasons visible.

Scans every indexed resource and language branch, including all five DLC archives.
Writes an independent candidate inventory; never overwrites the legacy cache.
"""
import bisect
import collections
import hashlib
import json
import mmap
import pickle
import re
import struct
from pathlib import Path

import ctrl
import xl
from charfreq import sane
from extract_text import JP, KANA, HANKAKU, PLACE, category, _strings
from linkdata import LinkData, is_container

MAGIC = b'XL\x13\0'
OUT = Path('extract/audit_v2')


def walk(data, absolute, path, depth=0):
    children = is_container(data) if depth < 32 else None
    if children is None:
        yield path, absolute, data, depth
    else:
        for i, (off, size) in enumerate(children):
            yield from walk(data[off:off + size], absolute + off,
                            f'{path}/{i}', depth + 1)


def wide_string(blob, start):
    end = start
    while end + 1 < len(blob) and blob[end:end + 2] != b'\0\0':
        end += 2
    if end + 1 >= len(blob):
        return None
    try:
        text = blob[start:end].decode('utf-16-le')
    except UnicodeDecodeError:
        return None
    return (blob[start:end], text) if all(sane(c) for c in text) else None


def entries(blob):
    parsed = xl.parse(blob)
    if parsed is None:
        return 'unparsed', [(o, b, t, []) for o, b, t in _strings(blob)], None
    hdr, count, width, total, refs = parsed
    pointers = collections.defaultdict(list)
    for pos, off, raw in refs:
        if raw is not None:
            pointers[hdr + off].append(pos)
    offsets = sorted(pointers)
    # Detect wide Japanese text by decoding complete aligned code units.
    sample = [o for o in offsets if blob[o:o + 2] != b'\0\0'][:40]
    wide = [wide_string(blob, o) for o in sample]
    wide_valid = sum(s is not None for s in wide)
    wide_kana = sum(s is not None and KANA.search(s[1]) is not None for s in wide)
    cp_kana = 0
    for o in sample:
        end = blob.find(b'\0', o)
        try:
            cp_kana += KANA.search(ctrl.to_text(blob[o:end])) is not None
        except UnicodeDecodeError:
            pass
    is_wide = bool(sample and wide_valid / len(sample) >= .85
                   and wide_kana >= max(2, len(sample) * .15)
                   and wide_kana > cp_kana)
    result = []
    failures = []
    for o in offsets:
        if is_wide:
            value = wide_string(blob, o)
            if value is None:
                failures.append(dict(offset=o, reason='utf16_decode_or_character_filter'))
                continue
            raw, text = value
        else:
            end = blob.find(b'\0', o)
            if end < 0:
                failures.append(dict(offset=o, reason='missing_terminator'))
                continue
            raw = blob[o:end]
            try:
                text = ctrl.to_text(raw)
            except UnicodeDecodeError:
                failures.append(dict(offset=o, reason='cp932_decode'))
                continue
        result.append((o, raw, text, pointers[o]))
    detail = dict(count=count, width=width, pointer_count=len(refs),
                  failures=failures, utf16_sample_valid=wide_valid,
                  utf16_sample_kana=wide_kana, cp932_sample_kana=cp_kana)
    return ('utf-16-le' if is_wide else 'cp932'), result, detail


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    meta = pickle.loads(Path('extract/meta.pkl').read_bytes())
    legacy_locs = pickle.loads(Path('extract/locs.pkl').read_bytes())
    old_locations = {(tag, off) for locations in legacy_locs.values() for tag, off in locations}
    archives = [('base', Path('extract/base/LINKDATA.idx'), Path('extract/base/LINKDATA.bin')),
                ('update', Path('extract/update/LINKDATA.idx'), Path('extract/update/LINKDATA.bin'))]
    archives += [(p.stem.split('_')[0], p, p.with_suffix('.bin'))
                 for p in sorted(Path('extract/dlc').glob('*_LINKDATA.idx'))]
    report = dict(scope='All indexed resources in base, update and extracted DLC archives; all branches.',
                  legacy_unique=len(meta), archives={}, blocks=[], new_candidates=[],
                  suspicious_placeholders=[], excluded_branches=[], long_strings=[],
                  halfwidth_strings=[], character_filter=[], raw_magic_unvisited=[])
    with (OUT / 'strings.jsonl').open('w', encoding='utf-8') as inventory:
        for tag, idx, binary in archives:
            print(f'Scanning {tag}: {binary.stat().st_size:,} bytes', flush=True)
            ld = LinkData(idx, binary)
            stats = collections.Counter()
            visited = set()
            for slot, size, eoff in ld.used():
                stats['indexed_resources'] += 1
                data = ld.read(slot)
                assert len(data) == size, (tag, slot, 'truncated indexed resource')
                records = []
                branch_scores = collections.defaultdict(lambda: [0, 0])
                children = is_container(data)
                leaves = list(walk(data, eoff, str(slot)))
                stats['leaf_resources'] += len(leaves)
                for path, absolute, blob, depth in leaves:
                    stats['max_depth'] = max(stats['max_depth'], depth)
                    if not blob.startswith(MAGIC):
                        continue
                    visited.add(absolute)
                    stats['xl_blocks'] += 1
                    enc, strings, detail = entries(blob)
                    stats['xl_' + enc] += 1
                    report['blocks'].append(dict(tag=tag, path=path, offset=absolute,
                        size=len(blob), encoding=enc, parsed=detail))
                    # Reproduce the old kana-ratio selection for comparison only.
                    branch = int(path.split('/')[1]) if '/' in path else None
                    if children and len(children) >= 2:
                        old = _strings(blob)
                        branch_scores[branch][0] += len(old)
                        branch_scores[branch][1] += sum(bool(KANA.search(t)) for _, _, t in old)
                    for off, raw, text, pointers in strings:
                        if not text:
                            continue
                        row = dict(tag=tag, slot=slot, path=path, offset=absolute + off,
                            encoding=enc, source_hex=raw.hex(), source=text,
                            category=category(slot), pointer_positions=pointers,
                            legacy_location=(tag, absolute + off) in old_locations,
                            legacy_source=raw in meta if enc == 'cp932' else False,
                            flags=[])
                        if len(raw) > 800:
                            row['flags'].append('legacy_800_byte_limit')
                        if not JP.search(text):
                            row['flags'].append('no_japanese_character')
                        if not all(sane(c) for c in text):
                            row['flags'].append('legacy_character_filter')
                        if HANKAKU.search(text):
                            row['flags'].append('legacy_halfwidth_filter')
                        if PLACE.search(text):
                            row['flags'].append('legacy_placeholder_filter')
                        records.append(row)
                scores = {k: kana / n if n else 0 for k, (n, kana) in branch_scores.items()}
                best = max(scores.values(), default=0)
                keep = {k for k, v in scores.items() if v >= best * .9} if best >= .05 else None
                for row in records:
                    branch = int(row['path'].split('/')[1]) if '/' in row['path'] else None
                    if keep is not None and branch not in keep:
                        row['flags'].append('legacy_branch_filter')
                    stats['decoded_strings'] += 1
                    stats['legacy_locations_found'] += row['legacy_location']
                    inventory.write(json.dumps(row, ensure_ascii=False) + '\n')
                    has_kana = bool(KANA.search(row['source']))
                    plausible = has_kana and 'legacy_character_filter' not in row['flags']
                    short = {k: v for k, v in row.items() if k not in ('pointer_positions',)}
                    if plausible and not row['legacy_source']:
                        report['new_candidates'].append(short)
                    if plausible:
                        for flag, key in [('legacy_branch_filter', 'excluded_branches'),
                                          ('legacy_800_byte_limit', 'long_strings'),
                                          ('legacy_halfwidth_filter', 'halfwidth_strings')]:
                            if flag in row['flags']:
                                report[key].append(short)
                        if 'legacy_placeholder_filter' in row['flags'] and not re.fullmatch(
                                r'(予備|予約|未使用|ダミー|dummy|テスト)([\s_・０-９0-9]*)', row['source']):
                            report['suspicious_placeholders'].append(short)
                    if has_kana and 'legacy_character_filter' in row['flags']:
                        report['character_filter'].append(short)
            ld.f.close()
            # Independent byte-signature pass also finds XL headers that traversal missed.
            with binary.open('rb') as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                off = mm.find(MAGIC)
                while off >= 0:
                    stats['raw_xl_magic'] += 1
                    if off not in visited:
                        report['raw_magic_unvisited'].append(dict(tag=tag, offset=off,
                                                                  header=mm[off:off + 32].hex()))
                    off = mm.find(MAGIC, off + 4)
            report['archives'][tag] = dict(stats)
            print(f'{tag}: {dict(stats)}', flush=True)
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print({k: len(v) for k, v in report.items() if isinstance(v, list)}, flush=True)


if __name__ == '__main__':
    main()
