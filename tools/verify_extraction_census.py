"""Independent signature/offset checks for the all-archive text census."""
import bisect
import collections
import hashlib
import json
import mmap
import pickle
import struct
from pathlib import Path

from linkdata import LinkData


def main():
    census = json.loads(Path('extract/audit_v2/report.json').read_text(encoding='utf-8'))
    old_locs = pickle.loads(Path('extract/backups/before_extraction_audit_v2/locs.pkl').read_bytes())
    old = {(tag, off): raw for raw, pairs in old_locs.items() for tag, off in pairs}
    found = set()
    for line in Path('extract/audit_v2/strings.jsonl').open(encoding='utf-8'):
        row = json.loads(line)
        key = row['tag'], row['offset']
        if key in old and row['source_hex'] == old[key].hex():
            found.add(key)
    missing = [dict(tag=tag, offset=off, source_hex=old[(tag, off)].hex())
               for tag, off in sorted(set(old) - found)]
    report = dict(legacy_locations=len(old), matched_legacy_locations=len(found),
                  legacy_not_exactly_reproduced=missing, archive_checks={},
                  limitation='Known phrase probes cannot prove absence of unknown formats, compressed text, or image text.')
    probes = ['シオン', 'カムイ', 'アイトリス', 'してください', 'よろしいですか', 'ファイアーエムブレム']
    for tag in census['archives']:
        binary = (Path('extract') / tag / 'LINKDATA.bin' if tag in ('base', 'update')
                  else Path('extract/dlc') / f'{tag}_LINKDATA.bin')
        index = binary.with_suffix('.idx')
        ranges = sorted((b['offset'], b['offset'] + b['size']) for b in census['blocks'] if b['tag'] == tag)
        starts = [a for a, b in ranges]
        outside, hits, rejected_magic = [], collections.Counter(), []
        with binary.open('rb') as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            digest = hashlib.sha256(mm).hexdigest()
            for phrase in probes:
                for enc in ('cp932', 'utf-16-le'):
                    needle = phrase.encode(enc)
                    off = mm.find(needle)
                    while off >= 0:
                        hits[enc] += 1
                        i = bisect.bisect_right(starts, off) - 1
                        if i < 0 or not (ranges[i][0] <= off and off + len(needle) <= ranges[i][1]):
                            outside.append(dict(phrase=phrase, encoding=enc, offset=off))
                        off = mm.find(needle, off + len(needle))
            for candidate in census['raw_magic_unvisited']:
                if candidate['tag'] != tag:
                    continue
                off = candidate['offset']
                count, width, hdr = struct.unpack_from('<HHI', mm, off + 8)
                ld = LinkData(index, binary)
                slots = [(i, size, start) for i, size, start in ld.used() if start <= off < start + size]
                ld.f.close()
                capacity = max((start + size - off for i, size, start in slots), default=0)
                invalid = hdr < 16 or hdr + count * width > capacity
                rejected_magic.append(dict(offset=off, count=count, width=width, header=hdr,
                    indexed_remaining_capacity=capacity, invalid_table_bounds=invalid))
        report['archive_checks'][tag] = dict(file=str(binary), size=binary.stat().st_size,
            sha256=digest, probe_hits=dict(hits), probe_hits_outside_xl=outside,
            unmatched_magic_validation=rejected_magic)
    Path('reports/extraction_census_validation_20260920.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Legacy:', len(found), '/', len(old), 'matched; remaining:', missing)
    print({tag: dict(outside_xl=len(d['probe_hits_outside_xl']),
        invalid_magic=sum(x['invalid_table_bounds'] for x in d['unmatched_magic_validation']))
        for tag, d in report['archive_checks'].items()})


if __name__ == '__main__':
    main()
