"""Promote explicitly reviewed Japanese pointer references into the working cache."""
import collections
import hashlib
import json
import pickle
import shutil
import struct
from pathlib import Path

from build_ko2 import SRC
from extract_text import category, walk_abs
from linkdata import LinkData
import xl


def main():
    rows = json.loads(Path('reports/extraction_missing_locations_20260920.json').read_text(encoding='utf-8'))
    meta_path, loc_path = Path('extract/meta.pkl'), Path('extract/locs.pkl')
    meta, locs = pickle.loads(meta_path.read_bytes()), pickle.loads(loc_path.read_bytes())
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (meta_path, loc_path)}
    blocks = {}
    by_tag = {}
    try:
        for tag in ('base', 'update'):
            by_tag[tag] = LinkData(*SRC[tag])
        additions = []
        new_sources = []
        for row in rows:
            tag, slot = row['tag'], row['slot']
            assert tag in by_tag and '/0/' in row['path'] and row['encoding'] == 'cp932'
            key = (tag, slot)
            if key not in blocks:
                ld = by_tag[tag]
                _, _, start = ld.entry(slot)
                blocks[key] = {p: (ab, blob) for p, ab, blob in walk_abs(ld.read(slot), start, str(slot))}
            absolute, blob = blocks[key][row['path']]
            parsed = xl.parse(blob)
            assert parsed is not None and row['pointer_positions']
            raw = bytes.fromhex(row['source_hex'])
            matching = [(pos, off, s) for pos, off, s in parsed[4]
                        if absolute + parsed[0] + off == row['offset'] and s == raw]
            assert matching, (tag, row['path'], row['offset'], 'not an exact string reference')
            location = (tag, row['offset'])
            current = locs.setdefault(raw, [])
            if location not in current:
                current.append(location)
                additions.append(row)
            if raw not in meta:
                meta[raw] = dict(slot=slot, path=row['path'], cat=category(slot),
                    disp=row['source'], nbytes=len(raw), place=False,
                    recovered_by='all-branch pointer-reference audit')
                new_sources.append(row['source'])
    finally:
        for ld in by_tag.values():
            ld.f.close()
    backup = Path('extract/backups/before_extraction_audit_v2')
    backup.mkdir(parents=True, exist_ok=True)
    for path in (meta_path, loc_path):
        dest = backup / path.name
        if not dest.exists():
            shutil.copyfile(path, dest)
    # All byte/reference validation completes before either working cache is written.
    meta_path.write_bytes(pickle.dumps(meta))
    loc_path.write_bytes(pickle.dumps(locs))
    if additions:
        report = dict(before_sha256=before,
            added_locations=len(additions), added_by_archive=dict(collections.Counter(r['tag'] for r in additions)),
            source_variants=len({r['source_hex'] for r in additions}), new_unique_sources=new_sources,
            validation='Every recovered offset verified against original XL pointer and source bytes.',
            additions=additions)
        Path('reports/extraction_restoration_20260920.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Restored {len(additions)} locations, {len(new_sources)} unique strings; originals verified.')


if __name__ == '__main__':
    main()
