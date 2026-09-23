"""Read-only G1T resource inventory. No payload copies or archive modifications."""
import collections
import hashlib
import json
import struct
from pathlib import Path

from linkdata import LinkData
from audit_extraction_v2 import walk
import g1t


def main():
    archives = [('base', Path('extract/base/LINKDATA.idx')),
                ('update', Path('extract/update/LINKDATA.idx'))]
    archives += [(p.stem.split('_')[0], p)
                 for p in sorted(Path('extract/dlc').glob('*_LINKDATA.idx'))]
    records, rejected, stats = [], [], {}
    for tag, idx in archives:
        ld = LinkData(idx, idx.with_suffix('.bin'))
        count = collections.Counter()
        try:
            for slot, size, absolute in ld.used():
                count['indexed_resources'] += 1
                for path, offset, blob, depth in walk(ld.read(slot), absolute, str(slot)):
                    start = 0
                    while True:
                        pos = blob.find(b'GT1G', start)
                        if pos < 0:
                            break
                        start = pos + 4
                        if pos + 28 > len(blob):
                            rejected.append(dict(tag=tag, path=path, offset=offset+pos,
                                                 reason='short_header'))
                            continue
                        total, table, n, platform = struct.unpack_from('<IIII', blob, pos+8)
                        if total < 28 or pos+total > len(blob):
                            rejected.append(dict(tag=tag, path=path, offset=offset+pos,
                                                 reason='invalid_total_size'))
                            continue
                        data = blob[pos:pos+total]
                        textures = g1t.parse(data)
                        if not textures or len(textures) != n:
                            rejected.append(dict(tag=tag, path=path, offset=offset+pos,
                                                 reason='unsupported_or_invalid_table'))
                            continue
                        row = dict(tag=tag, path=path, slot=slot, offset=offset+pos,
                                   leaf_offset=pos, size=total, platform=platform,
                                   version=data[4:8].decode('ascii', 'replace'),
                                   sha256=hashlib.sha256(data).hexdigest(), textures=[])
                        for i, (fmt, w, h, mip, p) in enumerate(textures):
                            end = textures[i+1][4] if i+1 < len(textures) else total
                            row['textures'].append(dict(index=i, format=fmt, width=w,
                                height=h, mip_hint=mip, header_offset=p,
                                span_bytes=end-p, header_hex=data[p:p+24].hex()))
                            count[f'format_{fmt}'] += 1
                        records.append(row)
                        count['g1t_resources'] += 1
                        count['textures'] += len(textures)
        finally:
            ld.f.close()
        stats[tag] = dict(count)
        print(tag, dict(count), flush=True)
    result = dict(scope='GT1G signatures in every indexed resource leaf of seven archives',
                  purpose='Source inventory only; text presence and payload formats need review',
                  archives=stats, resources=records, rejected_signatures=rejected,
                  source_modified=False, edited_graphics=0, build_performed=False,
                  review_policy='User review before editing and after before/after comparison')
    Path('reports/graphics_inventory.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Resources:', len(records), 'Rejected signatures:', len(rejected))


if __name__ == '__main__':
    main()
