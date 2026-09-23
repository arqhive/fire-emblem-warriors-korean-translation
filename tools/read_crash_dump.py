# -*- coding: utf-8 -*-
"""Luma3DS 예외 덤프를 읽는다.

  python tools/read_crash_dump.py F:/luma/dumps/arm11/crash_dump_00000011.dmp

헤더 구조는 Luma3DS 의 exceptions.h 를 따른다.
"""
import struct
import sys
from pathlib import Path

TYPES = {0: 'FIQ', 1: '정의되지 않은 명령(undefined instruction)',
         2: '프리페치 어보트(prefetch abort)', 3: '데이터 어보트(data abort)'}
NAMES = ['r0', 'r1', 'r2', 'r3', 'r4', 'r5', 'r6', 'r7', 'r8', 'r9', 'r10',
         'r11', 'r12', 'sp', 'lr', 'pc', 'cpsr']


def main():
    p = Path(sys.argv[1])
    d = p.read_bytes()
    magic = struct.unpack_from('<II', d, 0)
    if magic != (0xDEADC0DE, 0xDEADCAFE):
        raise SystemExit('Luma 예외 덤프가 아니다: %s' % (magic,))
    (vmaj, vmin, processor, etype, _res,
     nregs, codesize, stacksize, extrasize) = struct.unpack_from('<9I', d, 8)
    print('%s  (%d 바이트)' % (p.name, len(d)))
    print('  버전 %d.%d  프로세서 %d  예외 %s'
          % (vmaj, vmin, processor & 0xFF, TYPES.get(etype, etype)))
    if processor >> 16:
        print('  코어 %d' % (processor >> 16))
    off = 44
    regs = list(struct.unpack_from('<%dI' % (nregs // 4), d, off))
    off += nregs
    print('  레지스터 %d개' % len(regs))
    for i, v in enumerate(regs):
        name = NAMES[i] if i < len(NAMES) else 'x%d' % i
        print('    %-5s %08X' % (name, v), end='\n' if i % 4 == 3 else '')
    print()
    code = d[off:off + codesize]; off += codesize
    stack = d[off:off + stacksize]; off += stacksize
    extra = d[off:off + extrasize]
    if code:
        print('  코드 덤프 %d바이트: %s' % (len(code), code.hex(' ')))
    if extra:
        print('  추가 정보 %d바이트' % len(extra))
        # 보통 프로세스 이름과 타이틀 ID 가 들어 있다
        print('   ', extra[:64].hex(' '))
        txt = bytes(c if 32 <= c < 127 else 46 for c in extra[:64]).decode('ascii')
        print('   ', txt)
    if stack:
        print('  스택 덤프 %d바이트 (앞 64)' % len(stack))
        print('   ', stack[:64].hex(' '))


if __name__ == '__main__':
    main()
