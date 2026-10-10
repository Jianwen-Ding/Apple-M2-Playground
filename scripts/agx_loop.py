#!/usr/bin/env python3
"""Counted AGX loop bodies plus an offline emulator check (no GPU access).

Loop shape (Mesa's nested-loop pattern; the control prefix leaves in-bounds
lanes at r0l=0 and out-of-bounds lanes at r0l=1):

    mov_imm r3, 0 ; mov_imm r4, K ; mov_imm r2, P ; mov_imm r5..r7, 0
    push_exec r0l, 1                 ; out-of-bounds lanes -> 2
  top:
    <M chain steps round-robin over r2 (and r5..r7 for 2/4 chains)>
    iadd r3, 1, r3.sx
    while_icmp r0l, ult, r3, r4, 1   ; lanes with r3 >= K -> r0l = 1
    jmp_exec_any top
    pop_exec r0l, 1                  ; finished 1 -> 0, out-of-bounds 2 -> 1
    iadd/fadd32 r2, r2, rN           ; fold extra chains into the stored r2

The counter counts up and the loop continues only while r3 < K, so an
inverted condition reading exits after one iteration instead of hanging.
emulate() runs the bytes with applegpu's per-instruction exec semantics
(jmp_exec_any resolved here) under a step limit and returns lane state.
"""
from pathlib import Path
import sys

import patch_agx_sr as patcher
import run_agx_timestamps as chains

APPLEGPU = chains.APPLEGPU


def _tools():
    sys.path.insert(0, str(APPLEGPU))
    import assemble
    import applegpu
    return assemble, applegpu


def encode(text, want=None):
    """Assemble one line and require decode(bytes) to round-trip (or match want)."""
    assemble, g = _tools()
    b = bytes(assemble.assemble_line(text))
    n = g.opcode_to_number(b); d = g.get_instruction_descriptor(n)
    if d is None or d.decode_size(n) != len(b):
        raise ValueError('inconsistent assembly: '+text)
    shown = ' '.join(str(d.disassemble(n)).split())
    if shown != ' '.join((want or text).split()):
        raise ValueError(f'round-trip mismatch: {text!r} -> {shown!r}')
    return b


CHAIN_REGS = (2, 5, 6, 7)  # r3/r4 hold the loop counter and trip count


def loop_body(trips, steps, kind='iadd8', preload=0x10000000, chains_n=1):
    """Return (bytes, oracle) for `trips` iterations of `steps` chain steps over `chains_n` registers."""
    if not (1 <= trips <= 0x7fffffff and 0 <= steps <= 4096):
        raise ValueError('bounded trips/steps required')
    _, g = _tools()
    gpu, _ = patcher.load_model(APPLEGPU)
    start = preload if kind == 'iadd8' else 0
    if chains_n not in (1, 2, 4) or steps % chains_n:
        raise ValueError('chains must be 1/2/4 and divide steps')
    regs = CHAIN_REGS[:chains_n]
    head = chains.mov_imm(3, 0)+chains.mov_imm(4, trips)+chains.mov_imm(2, start)
    head += b''.join(chains.mov_imm(r, 0) for r in regs[1:])
    head += encode('if_fcmp r0l, eq, 0.0, 0.0, 1', 'push_exec r0l, 1')
    step = [chains.encode_step(kind, r, gpu) for r in regs]
    loop = b''.join(step[k % chains_n] for k in range(steps))
    loop += encode('iadd r3, 1, r3.sx')
    loop += encode('while_icmp r0l, ult, r3, r4, 1')
    jump = encode(f'jmp_exec_any pc-{len(loop)}', f'jmp_exec_any pc-{len(loop)}')
    tail = encode('pop_exec r0l, 1')
    op = 'iadd' if kind == 'iadd8' else 'fadd32'
    tail += b''.join(encode(f'{op} r2, r2, r{r}') for r in regs[1:])
    body = head+loop+jump+tail
    return body, chains.oracle(trips*steps, kind, preload)


def emulate(body, active, max_steps=2_000_000):
    """Run body on one 32-lane SIMD group; lanes < active start at r0l=0, others 1."""
    _, g = _tools()
    st = g.CoreState(num_registers=8)
    for t in range(g.SIMD_WIDTH):
        st.set_reg16(0, t, 0 if t < active else 1)
        st.set_reg32(2, t, 0xdeadbeef)  # stale; the body must overwrite r2
    st.exec = [t < active for t in range(g.SIMD_WIDTH)]
    pc = 0; executed = 0; trace = {}
    while pc < len(body):
        n = g.opcode_to_number(body[pc:]); d = g.get_instruction_descriptor(n)
        size = d.decode_size(n); n &= (1 << (8*size))-1
        trace[d.name] = trace.get(d.name, 0)+1
        if d.name == 'jmp_exec_any':
            off = dict(d.decode_fields(n))['off']
            off = off-(1 << 32) if off & (1 << 31) else off
            pc = pc+off if any(st.exec) else pc+size
        else:
            d.exec(n, st); pc += size
        executed += 1
        if executed > max_steps:
            raise RuntimeError('emulator step limit: loop does not terminate')
    if pc != len(body):
        raise RuntimeError(f'control left the body at pc={pc}')
    return {'r2': [st.get_reg32(2, t) for t in range(g.SIMD_WIDTH)],
            'r0l': [st.get_reg16(0, t) for t in range(g.SIMD_WIDTH)],
            'exec': list(st.exec), 'executed': executed, 'counts': trace}


def check(trips, steps, kind='iadd8', active=17, preload=0x10000000, chains_n=1):
    """Emulate and require: active lanes hold the oracle and are re-enabled; others stay masked."""
    body, want = loop_body(trips, steps, kind, preload, chains_n)
    r = emulate(body, active)
    ok = (all(r['r2'][t] == want for t in range(active)) and
          r['r0l'] == [0]*active+[1]*(32-active) and r['exec'] == [True]*active+[False]*(32-active) and
          r['counts'].get('jmp_exec_any') == trips)
    return ok, body, want, r


if __name__ == '__main__':
    for trips, steps, kind, active, *rest in [(1, 0, 'iadd8', 32), (1, 1, 'iadd8', 17), (3, 2, 'iadd8', 17),
                                       (10, 4, 'fadd4', 5), (100, 1, 'iadd8', 32), (257, 3, 'fadd4', 1),
                                       (7, 8, 'iadd8', 32, 4), (9, 8, 'fadd4', 20, 2), (5, 16, 'fadd6', 3, 4)]:
        chains_n = rest[0] if rest else 1
        ok, body, want, r = check(trips, steps, kind, active, chains_n=chains_n)
        print({'trips': trips, 'steps': steps, 'chains': chains_n, 'kind': kind, 'active': active, 'ok': ok, 'oracle': hex(want),
               'bytes': len(body), 'executed': r['executed'], 'jumps': r['counts'].get('jmp_exec_any')})
