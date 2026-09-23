"""Preserve Japanese glyphs and map CP932 private-use codes to blank atlas cells.

The two verified executables accept lead bytes E0..FC in the text decoder.
A small ARM lookup hook maps F040..F9FC to cells 1926..3805. Existing Japanese
lookup tables are untouched. This still requires an in-game display check.
"""
import hashlib
import struct
from pathlib import Path

from keystone import Ks, KS_ARCH_ARM, KS_MODE_ARM

FIRST_CELL = 1926
MAX_SYLLABLES = 1880
PROFILES = {
    'base': dict(entry=0x489CC, cave=0x444CF0, cave_end=0x445000, table=0x448584,
                 prefix='30002de91f4a80e2', displaced='push {r4, r5}'),
    'update': dict(entry=0x4CC28, cave=0x47CF98, cave_end=0x47D000, table=0x4805A4,
                   prefix='00c0a0e11f0a80e2', displaced='mov ip, r0'),
}


def assign(syllables):
    syllables = sorted(set(syllables))
    if len(syllables) > MAX_SYLLABLES:
        raise ValueError(f'Hangul atlas limit: {len(syllables)} > {MAX_SYLLABLES}')
    codes, cells = {}, {}
    for i, char in enumerate(syllables):
        row, col = divmod(i, 188)
        trail = 0x40 + col + (col >= 63)
        codes[char] = bytes((0xF0 + row, trail))
        cells[char] = FIRST_CELL + i
    return codes, cells


def make_patch(tag):
    profile = PROFILES[tag]
    path = Path(f'extract/exefs/{tag}_code_dec.bin')
    original = path.read_bytes()
    entry, cave = profile['entry'], profile['cave']
    # Fingerprint the prologue and all of the mapping, not just a guessed address.
    if original[entry:entry + 8] != bytes.fromhex(profile['prefix']):
        raise ValueError(f'Unexpected {tag} lookup prologue')
    import json
    rows = json.loads(Path('extract/font/atlas_map_true.json').read_text(encoding='utf-8'))
    table = struct.pack('<' + 'H' * len(rows), *(int(r['code'], 16) for r in rows))
    if original[profile['table']:profile['table'] + len(table)] != table:
        raise ValueError(f'Unexpected {tag} Japanese glyph table')
    asm = f'''
        push {{r4}}
        lsr ip, r1, #8
        sub ip, ip, #0xf0
        cmp ip, #9
        bhi original_lookup
        and r3, r1, #0xff
        sub r3, r3, #0x40
        cmp r3, #188
        bhi original_lookup
        cmp r3, #0x3f
        beq original_lookup
        mov r4, #188
        mul r0, ip, r4
        subhi r3, r3, #1
        add r0, r0, r3
        add r0, r0, #0x780
        add r0, r0, #6
        pop {{r4}}
        bx lr
    original_lookup:
        pop {{r4}}
        {profile['displaced']}
        b {0x100000 + entry + 4}
    '''
    assembler = Ks(KS_ARCH_ARM, KS_MODE_ARM)
    body = bytes(assembler.asm(asm, addr=0x100000 + cave)[0])
    if cave + len(body) > profile['cave_end']:
        raise ValueError('Lookup hook exceeds executable padding')
    if any(original[cave:profile['cave_end']]):
        raise ValueError('Executable padding is not empty')
    branch = bytes(assembler.asm(f'b {0x100000 + cave}', addr=0x100000 + entry)[0])
    patches = [(entry, branch), (cave, body)]
    patched = bytearray(original)
    ips = bytearray(b'PATCH')
    for offset, data in patches:
        patched[offset:offset + len(data)] = data
        ips += offset.to_bytes(3, 'big') + len(data).to_bytes(2, 'big') + data
    ips += b'EOF'
    return bytes(patched), bytes(ips), dict(
        source_sha256=hashlib.sha256(original).hexdigest(),
        patched_sha256=hashlib.sha256(patched).hexdigest(),
        entry=entry, cave=cave, hook_bytes=len(body), first_cell=FIRST_CELL,
        max_syllables=MAX_SYLLABLES)


if __name__ == '__main__':
    for tag in PROFILES:
        _, _, report = make_patch(tag)
        print(tag, report)
