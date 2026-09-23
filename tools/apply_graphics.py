# -*- coding: utf-8 -*-
"""승인된 그래픽 페이로드를 빌드된 LayeredFS 아카이브에 반영한다.

  python tools/apply_graphics.py work/builds/out

텍스트를 재구성하면 자원의 절대 오프셋이 움직이므로, manifest 에 적힌 절대 위치를
그대로 쓰지 않고 LINKDATA.idx 에서 자원을 다시 찾아 그 안의 상대 위치에 쓴다.
같은 자원에 여러 항목이 들어가는 경우(base 6410 은 제작사 로고와 주의 안내,
base 6421 은 타이틀 로고와 하단 저작권)를 위해 자원 단위로 모아서 한 번에 반영한다.

반영 전에는 원본 payload 해시를, 반영 뒤에는 디스크에서 되읽어 대조한다.
"""
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from linkdata import LinkData

REUSE = Path('translation/graphics/reuse_manifest.json')
NATIVE = Path('translation/graphics/native_manifest.json')


def sha(b):
    return hashlib.sha256(b).hexdigest()


def collect():
    """(tag, 슬롯) → [적용할 조각] 으로 모은다."""
    jobs = defaultdict(list)
    reuse = json.loads(REUSE.read_text('utf-8'))
    for e in reuse['entries']:                     # superseded_entries 는 쓰지 않는다
        t = e['target']
        jobs[(t['tag'], str(t['resource_path']))].append(dict(
            id=e['id'], offset=t['payload_offset_in_resource'], length=t['length'],
            before=t['before_payload_sha256'], payload=Path(e['payload_file']),
            payload_sha=e['payload_sha256']))
    native = json.loads(NATIVE.read_text('utf-8'))
    for e in native['entries']:
        if not e.get('patch_inclusion_allowed'):
            print('  건너뜀(포함 허용 아님): %s' % e['id'])
            continue
        for t in e['targets']:
            jobs[(t['tag'], str(t['resource_path']))].append(dict(
                id=e['id'], offset=t['payload_offset_in_resource'], length=t['length'],
                before=t['before_payload_sha256'], payload=Path(e['payload_file']),
                payload_sha=e['payload_sha256']))
    return jobs


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else 'work/builds/out')
    jobs = collect()
    report = {'archive': str(out), 'resources': [], 'applied': 0, 'skipped': []}

    for (tag, slot), items in sorted(jobs.items()):
        folder = out / ('base' if tag == 'base' else 'update_resources') / 'romfs'
        idx, binf = folder / 'LINKDATA.idx', folder / 'LINKDATA.bin'
        if not binf.exists():
            report['skipped'].append(dict(tag=tag, slot=slot, reason='아카이브 없음'))
            continue
        if '/' in slot:
            report['skipped'].append(dict(tag=tag, slot=slot, reason='중첩 경로는 아직 지원하지 않음'))
            continue
        ld = LinkData(str(idx), str(binf))
        if int(slot) >= ld.n:
            report['skipped'].append(dict(tag=tag, slot=slot, reason='인덱스 범위 밖'))
            continue
        # flag 는 존재 여부가 아니다. 본편은 flag=0 이면서도 size/offset 이 유효하다.
        # LinkData.used() 와 같이 크기로 판정한다.
        flag, size, eoff = ld.entry(int(slot))
        if not size:
            report['skipped'].append(dict(tag=tag, slot=slot, reason='빈 슬롯'))
            continue
        data = bytearray(ld.read(int(slot)))
        entry = dict(tag=tag, slot=slot, resource_offset=eoff, resource_size=size,
                     before_sha256=sha(bytes(data)), pieces=[])
        ok = True
        for it in sorted(items, key=lambda x: x['offset']):
            o, n = it['offset'], it['length']
            if o + n > len(data):
                entry['pieces'].append(dict(id=it['id'], status='범위 초과'))
                ok = False
                continue
            cur = bytes(data[o:o + n])
            payload = it['payload'].read_bytes()
            if sha(payload) != it['payload_sha']:
                entry['pieces'].append(dict(id=it['id'], status='페이로드 해시 불일치'))
                ok = False
                continue
            if sha(cur) == sha(payload):
                entry['pieces'].append(dict(id=it['id'], status='이미 반영됨'))
                continue
            if sha(cur) != it['before']:
                entry['pieces'].append(dict(id=it['id'], status='원본 payload 해시가 기록과 다름',
                                            found=sha(cur)[:16], expected=it['before'][:16]))
                ok = False
                continue
            data[o:o + n] = payload
            entry['pieces'].append(dict(id=it['id'], status='반영', offset=o, length=n,
                                        payload_sha256=it['payload_sha']))
            report['applied'] += 1
        if not ok:
            entry['written'] = False
            report['resources'].append(entry)
            print('  ! %s %s — 문제가 있어 쓰지 않았다' % (tag, slot))
            for p in entry['pieces']:
                print('      %-22s %s' % (p['id'], p['status']))
            continue
        with open(binf, 'r+b') as f:
            f.seek(eoff)
            f.write(bytes(data))
            f.flush()
            f.seek(eoff)
            back = f.read(len(data))
        entry['written'] = True
        entry['readback_verified'] = (back == bytes(data))
        entry['after_sha256'] = sha(bytes(data))
        report['resources'].append(entry)
        print('  %s %-6s %d개 조각  되읽기 %s' % (
            tag, slot, sum(1 for p in entry['pieces'] if p['status'] == '반영'),
            '일치' if entry['readback_verified'] else '★ 불일치'))

    Path('reports/graphics_applied.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print('반영 %d조각 / 건너뜀 %d' % (report['applied'], len(report['skipped'])))
    for s in report['skipped']:
        print('   건너뜀 %s %s — %s' % (s['tag'], s['slot'], s['reason']))


if __name__ == '__main__':
    main()
