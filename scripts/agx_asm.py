#!/usr/bin/env python3
"""Tiny structured assembler for direct-DRM probe bodies. A line is AGX assembly text or a tuple:
  ('IMM', reg, value)        mov_imm reg, value (run_agx_timestamps.mov_imm)
  ('JMP', [lines])           jmp_exec_none over the enclosed block (Mesa's structured if-skip)
  ('LABEL', name)            a position
  ('JANY', name)             jmp_exec_any to a label (forward or backward; 6 bytes)
assemble(lines) -> bytes; count(lines) -> instruction count (labels excluded)."""
import agx_loop
import run_agx_timestamps as chains


def _flat(lines):
    out = []
    for l in lines:
        if isinstance(l, tuple) and l[0] == 'JMP':
            body = agx_loop_bytes(l[1])
            jt = 6+len(body)
            out.append(('RAW', agx_loop.encode(f'jmp_exec_none pc+{jt}', f'jmp_exec_none pc+{jt}')+body))
        else:
            out.append(l)
    return out


def agx_loop_bytes(lines):
    return assemble(lines)


def assemble(lines):
    e, mov = agx_loop.encode, chains.mov_imm
    pos, at, items = {}, 0, []
    for l in _flat(lines):
        if isinstance(l, tuple) and l[0] == 'LABEL':
            pos[l[1]] = at
        elif isinstance(l, tuple) and l[0] == 'JANY':
            items.append(('J', l[1], at)); at += 6
        else:
            b = l[1] if isinstance(l, tuple) and l[0] == 'RAW' else mov(l[1], l[2]) if isinstance(l, tuple) else e(l)
            items.append(('B', b, at)); at += len(b)
    out = []
    for kind, v, where in items:
        if kind == 'B':
            out.append(v)
        else:
            off = pos[v]-where
            t = f'jmp_exec_any pc+{off}' if off >= 0 else f'jmp_exec_any pc-{-off}'
            b = e(t, t)
            assert len(b) == 6
            out.append(b)
    return b''.join(out)


def count(lines):
    n = 0
    for l in lines:
        if isinstance(l, tuple) and l[0] == 'LABEL':
            continue
        n += count(l[1])+1 if isinstance(l, tuple) and l[0] == 'JMP' else 1
    return n
