"""Build isolated base/update patches, verify every written text block, report omissions.

python tools/build_verified.py <output> [--no-dialogue]
Writes base/romfs and update_resources/romfs LINKDATA plus glyph_assign.json and
build_report.json. build_cia.py --romfs-from packs them into CIAs.
"""
import bisect
import collections
import hashlib
import json
import mmap
import pickle
import shutil
import struct
import sys
from pathlib import Path

import numpy as np
import ctrl
import xl
from build_ko2 import PRESET, SRC, FONT_SLOT
from ctrtex import etc1a4_alpha, etc1a4_write
from extract_text import walk_abs, jp_branch
from fonttest import render
from hangul_font import assign, make_patch
from kopatch import encode_ko, lint
from linkdata import LinkData
from patch_dialogue import MANIFEST, load_manifest, patch_archive
import tl


def digest(data):
    return hashlib.sha256(data).hexdigest()


def build(output, with_dialogue=True):
    ko = tl.load_ko()
    dialogue = load_manifest()
    # 글리프 아틀라스는 본편 폰트 한 벌뿐이다. DLC 와 훈장에만 나오는 음절도 여기서 같이
    # 배정해 두지 않으면 그쪽 화면에서 빈칸이 된다. 배정은 아틀라스 한도(1,880자) 안이다.
    extra = []
    for path, key in (('translation/dlc_dialogue_ko.json', 'records'),
                      ('translation/utf16_medals_ko.json', 'records')):
        p = Path(path)
        if p.exists():
            extra += [r['translation'] for r in json.loads(p.read_text('utf-8'))[key]]
    syllables = {c for t in list(ko.values()) + [r['translation'] for r in dialogue] + extra
                 for c in t if '\uac00' <= c <= '\ud7a3'}
    codes, cells = assign(syllables)
    enc = {}
    for key, text in ko.items():
        src = bytes.fromhex(key)
        errors = lint(src, text, codes, check_len=False)
        if errors:
            raise ValueError((text, errors))
        enc[src] = encode_ko(text, codes)
    with Path('extract/locs.pkl').open('rb') as f:
        locs = pickle.load(f)
    output = Path(output)
    output.mkdir(exist_ok=True)
    # Invalidate a previous success report before touching any candidate files.
    (output / 'build_report.json').write_text(
        json.dumps(dict(status='building', game_screen_verified=False)), encoding='utf-8')
    (output / 'dialogue_verification.json').write_text(
        json.dumps(dict(status='pending_rebuild', game_screen_verified=False)), encoding='utf-8')
    report = dict(status='complete', translation_entries=len(ko), hangul_syllables=len(codes),
                  translation_sha256=digest(tl.KO.read_bytes()),
                  extraction_cache_sha256=digest(Path('extract/locs.pkl').read_bytes()),
                  builder_sha256=digest(Path(__file__).read_bytes()),
                  dialogue_manifest_sha256=digest(MANIFEST.read_bytes()) if MANIFEST.exists() else None,
                  dialogue_writer_sha256=digest(Path('tools/patch_dialogue.py').read_bytes()),
                  glyph_strategy='Private-use codes; original Japanese cells preserved',
                  game_screen_verified=False, sources={})
    for tag in ('base', 'update'):
        target = output / ('base' if tag == 'base' else 'update_resources')
        romfs = target / 'romfs'
        romfs.mkdir(parents=True, exist_ok=True)
        dst = romfs / 'LINKDATA.bin'
        shutil.copyfile(SRC[tag][1], dst)
        shutil.copyfile(SRC[tag][0], romfs / 'LINKDATA.idx')
        ld = LinkData(*SRC[tag])
        source_stats = dict(rebuilt_blocks=0, translated_references=0, in_place=0,
                            verified_write_regions=0, omissions=[], rebuild_fallbacks=[])
        applied = collections.Counter()
        applied_locations = set()
        regions = []
        done = []
        occurrences = sorted({(off, len(src)) for src, entries in locs.items()
                              for t, off in entries if t == tag})
        starts = [o for o, _ in occurrences]
        max_length = max((n for _, n in occurrences), default=0)
        # Use the extracted locations to target text-bearing resources. Scanning
        # gigabytes of models/audio/textures for every build is unnecessary.
        catalog = sorted((off, off + size, i) for i, size, off in ld.used())
        catalog_starts = [row[0] for row in catalog]
        target_slots = set()
        expected_locations = {(src.hex(), off) for src in enc
                              for t, off in locs.get(src, []) if t == tag}
        for _, off in expected_locations:
            slot = bisect.bisect_right(catalog_starts, off) - 1
            if slot >= 0 and off < catalog[slot][1]:
                target_slots.add(catalog[slot][2])
        source_stats['target_slots'] = len(target_slots)
        source_stats['expected_cached_locations'] = len(expected_locations)
        print(f'{tag}: rebuilding {len(target_slots)} text resources...', flush=True)
        with dst.open('r+b') as handle, mmap.mmap(handle.fileno(), 0) as buf:
            for i, size, eoff in ld.used():
                if i not in target_slots:
                    continue
                data = ld.read(i)
                for path, absolute, blob in walk_abs(data, eoff, str(i)):
                    parsed = xl.parse(blob)
                    if parsed is None:
                        continue
                    # The audited source/location cache decides eligibility. Repeating
                    # the kana-ratio language guess here dropped valid Japanese maps.
                    repl = {p: enc[s] for p, off, s in parsed[4]
                            if s in enc and (s.hex(), absolute + parsed[0] + off) in expected_locations}
                    if not repl:
                        continue
                    try:
                        new = xl.rebuild(blob, repl)
                    except (ValueError, OverflowError) as error:
                        source_stats['rebuild_fallbacks'].append(dict(path=path, reason=str(error)))
                        continue
                    # Validate original references directly; do not rely on re-detecting
                    # pointer columns in a reconstructed block.
                    hdr = parsed[0]
                    for pos, off, src in parsed[4]:
                        new_off = struct.unpack_from('<I', new, pos)[0]
                        if src is None:
                            assert new_off == off
                            continue
                        want = repl.get(pos, src)
                        start = hdr + new_off
                        assert new[start:start + len(want) + 1] == want + b'\0', (tag, path, pos)
                        if pos in repl:
                            applied[src.hex()] += 1
                            applied_locations.add((src.hex(), absolute + hdr + off))
                    assert len(new) == len(blob)
                    buf[absolute:absolute + len(new)] = new
                    regions.append((absolute, len(new), digest(new)))
                    done.append((absolute, absolute + len(new)))
                    source_stats['rebuilt_blocks'] += 1
                    source_stats['translated_references'] += len(repl)
            done.sort()
            for src, new in enc.items():
                for t, off in locs.get(src, []):
                    if t != tag:
                        continue
                    j = bisect.bisect_right(done, (off, 1 << 62)) - 1
                    if j >= 0 and done[j][0] <= off < done[j][1]:
                        continue
                    reason = None
                    if len(new) > len(src):
                        reason = 'in_place_capacity'
                    else:
                        lo = bisect.bisect_left(starts, off - max_length)
                        hi = bisect.bisect_right(starts, off + len(src))
                        if any((p, n) != (off, len(src)) and p <= off + len(src) and p + n >= off
                               for p, n in occurrences[lo:hi]):
                            reason = 'overlapping_source_strings'
                        elif buf[off:off + len(src) + 1] != src + b'\0':
                            reason = 'source_location_mismatch'
                    if reason:
                        source_stats['omissions'].append(dict(source_hex=src.hex(), offset=off,
                                                              source=ctrl.to_text(src), reason=reason))
                        continue
                    buf[off:off + len(new) + 1] = new + b'\0'
                    regions.append((off, len(new) + 1, digest(new + b'\0')))
                    applied[src.hex()] += 1
                    applied_locations.add((src.hex(), off))
                    source_stats['in_place'] += 1
            buf.flush()
        ld.f.close()
        # Reopen the actual output and check hashes of every written region.
        with dst.open('rb') as handle:
            for off, size, expected in regions:
                handle.seek(off)
                assert digest(handle.read(size)) == expected, (tag, off)
        source_stats['verified_write_regions'] = len(regions)
        source_stats['applied_unique'] = len(applied)
        source_stats['applied_cached_locations'] = len(expected_locations & applied_locations)
        recorded = {(item['source_hex'], item['offset']) for item in source_stats['omissions']}
        for key, off in sorted(expected_locations - applied_locations - recorded):
            source_stats['omissions'].append(dict(source_hex=key, offset=off,
                source=ctrl.to_text(bytes.fromhex(key)), reason='not_found_in_reconstructed_references'))
        source_stats['unapplied_unique'] = sorted({key for key, _ in expected_locations} - set(applied))
        source_stats['applied_counts_by_source'] = dict(applied)
        source_stats['file_size'] = dst.stat().st_size
        report['sources'][tag] = source_stats
        print(f'{tag}: {len(applied)} unique translations applied; '
              f'{len(source_stats["omissions"])} occurrence omissions', flush=True)

    ld = LinkData(*SRC['base'])
    _, _, base = ld.entry(FONT_SLOT)
    blob = ld.read(FONT_SLOT)
    ld.f.close()
    table = struct.unpack_from('<I', blob, 12)[0]
    tex = table + struct.unpack_from('<I', blob, table)[0] + 20
    data = blob[tex:tex + 1024 * 1024]
    original_image = etc1a4_alpha(data, 1024, 1024)
    image = original_image.copy()
    mask = np.zeros_like(image, dtype=bool)
    for char, cell in cells.items():
        y, x = divmod(cell, 64)
        region = np.s_[y * 16:y * 16 + 16, x * 16:x * 16 + 16]
        assert not original_image[region].any(), ('Nonempty atlas slot', cell)
        image[region] = render(char, PRESET)
        mask[region] = True
    encoded = etc1a4_write(data, 1024, 1024, image)
    decoded = etc1a4_alpha(encoded, 1024, 1024)
    assert np.array_equal(decoded, image)
    assert np.array_equal(decoded[~mask], original_image[~mask])
    dst = output / 'base/romfs/LINKDATA.bin'
    with dst.open('r+b') as f:
        f.seek(base + tex)
        f.write(encoded)
    with dst.open('rb') as f:
        f.seek(base + tex)
        assert f.read(len(encoded)) == encoded
    report['original_font_pixels_preserved'] = True
    report['dialogue'] = {}
    for tag in ('base', 'update'):
        target = output / ('base' if tag == 'base' else 'update_resources') / 'romfs'
        # 순차 대사는 자원을 파일 끝으로 옮기고 인덱스를 고친다. 원인을 가릴 때는 끈다.
        if with_dialogue:
            report['dialogue'][tag] = patch_archive(tag, SRC[tag], target, dialogue, codes)
        else:
            report['dialogue'][tag] = dict(skipped=True)
        report['sources'][tag]['file_size'] = (target / 'LINKDATA.bin').stat().st_size
    report['code_patches'] = {}
    for tag in ('base', 'update'):
        _, ips, detail = make_patch(tag)
        target = output / ('base' if tag == 'base' else 'update_resources') / 'exefs'
        target.mkdir(exist_ok=True)
        (target / 'code.ips').write_bytes(ips)
        report['code_patches'][tag] = detail
    (output / 'glyph_assign.json').write_text(
        json.dumps({s: c.hex() for s, c in codes.items()}, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'build_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Build and read-back verification complete: {output}', flush=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    args = [a for a in sys.argv[1:] if a != '--no-dialogue']
    build(args[0] if args else 'work/builds/out',
          with_dialogue='--no-dialogue' not in sys.argv)
