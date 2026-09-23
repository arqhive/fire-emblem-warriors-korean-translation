"""Extract the newly identified dialogue format from every base/update/DLC slot."""
import collections
import hashlib
import json
import pickle
from pathlib import Path

from audit_extraction_v2 import walk
from dialogue_records import parse, first_record_candidates
from linkdata import LinkData


def main():
    out = Path('extract/dialogue_v2')
    out.mkdir(parents=True, exist_ok=True)
    meta = pickle.loads(Path('extract/meta.pkl').read_bytes())
    ko = json.loads(Path('translation/ko.json').read_text(encoding='utf-8'))
    archives = [('base', Path('extract/base/LINKDATA.idx')),
                ('update', Path('extract/update/LINKDATA.idx'))]
    archives += [(p.stem.split('_')[0], p) for p in sorted(Path('extract/dlc').glob('*_LINKDATA.idx'))]
    blocks, sources, stats, near_misses = [], {}, {}, []
    for tag, idx in archives:
        ld = LinkData(idx, idx.with_suffix('.bin'))
        count = collections.Counter()
        for slot, size, absolute in ld.used():
            for path, off, blob, depth in walk(ld.read(slot), absolute, str(slot)):
                parsed = parse(blob)
                if parsed is None:
                    candidates = first_record_candidates(blob)
                    if candidates:
                        near_misses.append(dict(tag=tag, slot=slot, path=path, offset=off,
                            size=len(blob), candidates=candidates))
                    continue
                count['blocks'] += 1
                count['records'] += len(parsed['entries'])
                count['header_' + str(parsed['record_width'])] += 1
                block = dict(tag=tag, slot=slot, path=path, offset=off, size=len(blob),
                             sha256=hashlib.sha256(blob).hexdigest(), **parsed)
                blocks.append(block)
                for row in parsed['entries']:
                    key = row['source_hex']
                    if key not in sources:
                        sources[key] = dict(source_hex=key, source=row['source'],
                            legacy_source=bytes.fromhex(key) in meta, translation=ko.get(key),
                            locations=[])
                    sources[key]['locations'].append(dict(tag=tag, path=path, index=row['index'],
                        offset=off + row['offset'], format='dialogue_' + str(parsed['record_width'])))
        ld.f.close()
        stats[tag] = dict(count)
        print(tag, dict(count), flush=True)
    summary = dict(scope='Strict sequential CP932 dialogue records; all seven extracted LINKDATA archives.',
        archives=stats, blocks=len(blocks), unique_sources=len(sources),
        absent_from_legacy=sum(not r['legacy_source'] for r in sources.values()),
        already_translated=sum(r['translation'] is not None for r in sources.values()),
        near_miss_blocks=len(near_misses),
        patch_status='Extracted only; not automatically inserted into XL cache or patched.')
    for name, value in [('blocks.json', blocks), ('sources.json', list(sources.values())),
                        ('summary.json', summary), ('near_misses.json', near_misses)]:
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    print(summary, flush=True)


if __name__ == '__main__':
    main()
