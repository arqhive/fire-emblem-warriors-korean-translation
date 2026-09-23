"""Encode approved rendered artwork into small staged payloads, never archives."""
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image
from ctrtex import etc1a4_rgba, morton8_abgr32_rgba
from ctrtex_encode import abgr32_encode, etc1a4_encode


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    inventory = json.loads(Path('reports/graphics_inventory.json').read_text(encoding='utf-8'))
    folder = Path('translation/graphics/native')
    report_folder = Path('reports/graphics_review/native_review')
    report_folder.mkdir(exist_ok=True)
    specs = [
        ('notice', 'round3_A', [('base', '6410', 1)], None),
        ('title_logo', 'round4_A', [('base', '6421', 0)], None),
        ('credits_footer', 'round8_credits_footer_korean_B',
         [('base', '26', 5), ('update', '26', 5)], [131, 465, 250, 46]),
        ('title_footer', 'round9_title_footer_korean_reuse_B', [('base', '6421', 2)], None),
    ]
    entries = []
    for name, approval, refs, roi in specs:
        image_path = folder / f'{name}.png'
        pixels = np.array(Image.open(image_path).convert('RGBA'))
        targets, sources = [], []
        for tag, path, index in refs:
            resource = next(r for r in inventory['resources'] if r['tag'] == tag and r['path'] == path)
            texture = resource['textures'][index]
            with Path(f'extract/{tag}/LINKDATA.bin').open('rb') as f:
                f.seek(resource['offset'])
                blob = f.read(resource['size'])
            assert sha(blob) == resource['sha256']
            w, h, fmt = texture['width'], texture['height'], texture['format']
            assert pixels.shape == (h, w, 4) and texture['mip_hint'] == 1
            at = texture['header_offset'] + 20
            assert blob[at-12:at-8] == b'\x0c\0\0\0'
            size = w*h*(4 if fmt == 9 else 1)
            assert texture['span_bytes'] == size + 20
            raw = blob[at:at+size]
            if sources:
                assert raw == sources[0][0], 'Multiple targets must have identical texture payloads'
            sources.append((raw, blob, at, w, h, fmt))
            targets.append(dict(tag=tag, resource_path=path, texture_index=index,
                                resource_sha256=sha(blob), resource_offset=resource['offset'],
                                payload_offset_in_resource=at, length=size,
                                before_payload_sha256=sha(raw),
                                texture_header_hex=blob[at-20:at].hex()))
        raw, blob, at, w, h, fmt = sources[0]
        decoder = morton8_abgr32_rgba if fmt == 9 else etc1a4_rgba
        original_pixels = decoder(raw, w, h)
        Image.fromarray(original_pixels).save(report_folder / f'{name}_before.png')
        if fmt == 9:
            encoded = abgr32_encode(pixels)
            changed_blocks = None
        else:
            encoded, ids = etc1a4_encode(pixels, original=raw, region=roi)
            changed_blocks = len(ids)
            if roi:
                before_blocks = np.frombuffer(raw, np.uint8).reshape(-1, 16)
                after_blocks = np.frombuffer(encoded, np.uint8).reshape(-1, 16)
                keep = np.ones(len(before_blocks), bool)
                keep[ids] = False
                assert np.array_equal(before_blocks[keep], after_blocks[keep])
        decoded = decoder(encoded, w, h)
        if fmt == 9:
            assert np.array_equal(decoded, pixels)
        else:
            check = np.ones((h, w), bool)
            if roi:
                rx, ry, rw, rh = roi
                check[:] = False
                check[ry:ry+rh, rx:rx+rw] = True
            expected_alpha = ((pixels[:, :, 3].astype(np.uint16)*15+127)//255)*17
            assert np.array_equal(decoded[:, :, 3][check], expected_alpha[check])
        assert len(encoded) == len(raw)
        payload_path = folder / f'{name}.payload.bin'
        payload_path.write_bytes(encoded)
        Image.fromarray(decoded).save(report_folder / f'{name}_after.png')
        # Metrics in visible, premultiplied RGB; transparent garbage is irrelevant.
        a = pixels[:, :, 3:4] / 255.0
        b = decoded[:, :, 3:4] / 255.0
        errors = np.abs(pixels[:, :, :3]*a - decoded[:, :, :3]*b)
        visible = (pixels[:, :, 3] > 0) | (decoded[:, :, 3] > 0)
        if roi:
            inside = np.zeros((h, w), bool)
            rx, ry, rw, rh = roi
            inside[ry:ry+rh, rx:rx+rw] = True
            visible &= inside
        for target, (source, full, offset, _, _, _) in zip(targets, sources):
            patched = full[:offset] + encoded + full[offset+len(encoded):]
            assert len(patched) == len(full)
            assert patched[:offset] == full[:offset] and patched[offset+len(encoded):] == full[offset+len(encoded):]
            target['resource_after_sha256'] = sha(patched)
        entries.append(dict(id=name, approval=approval, targets=targets, native_size=[w, h],
                            format=fmt, rendered_image=image_path.as_posix(),
                            payload_file=payload_path.as_posix(), payload_sha256=sha(encoded),
                            source_roi=roi, reencoded_4x4_blocks=changed_blocks,
                            restored_image=(report_folder/f'{name}_after.png').as_posix(),
                            proof=dict(format9_exact_rgba_roundtrip=fmt == 9,
                                       alpha_matches_format_quantization=True,
                                       resource_header_size_and_outside_payload_unchanged=True,
                                       untouched_compressed_blocks_preserved=bool(roi),
                                       multi_target_source_payloads_identical=len(targets)>1,
                                       visible_premultiplied_rgb_mae=float(errors[visible].mean())),
                            native_after_review='pending_user', patch_inclusion_allowed=False,
                            archive_applied=False, installed=False))
        print(name, f'{w}x{h}', 'bytes', len(encoded), 'targets', len(targets), flush=True)
    report = dict(status='native_payloads_prepared_awaiting_after_review', entries=entries,
                  archive_modified=False, build_performed=False, installed=False)
    Path('translation/graphics/native_manifest.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
