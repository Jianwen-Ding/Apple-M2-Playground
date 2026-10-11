#!/usr/bin/env python3
"""Write docs/isa-coverage.md: every applegpu instruction descriptor, its unaccounted bits,
and the hardware status from this repository's findings (hand-maintained STATUS table).
No GPU access."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agx_loop  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
F = '../novel-results/'
ALU, SUB, MEM = F+'2026-10-11-fmadd-lane-offset/README.md', F+'2026-10-11-subop-spaces/README.md', F+'2026-10-11-mem-control-gap-bits/README.md'
OPC = F+'2026-10-11-opcode-descriptions/README.md'
done_alu = ('mov_imm iadd imadd convert bfi bfeil extr shlhi shrhi asr asrh bitop bitrev popcount intl ffs fmadd32 fmadd16 fadd32 fadd16 '
            'fmul32 fmul16 floor ceil trunc rint rcp rsqrt rsqrt_special sin_pt_1 sin_pt_2 log2 exp2 icmpsel fcmpsel icmp_ballot fcmp_ballot '
            'icmp_quad_ballot fcmp_quad_ballot simd_shuffle simd_shuffle_down simd_shuffle_up simd_shuffle_xor simd_shuffle_rotate_up '
            'quad_shuffle quad_shuffle_down quad_shuffle_up quad_shuffle_xor quad_shuffle_rotate_up simd_shuf_op').split()
STATUS = {n: ('mapped', ALU) for n in done_alu}
STATUS.update({n: ('mapped (sub-op space)', SUB) for n in ('funop', 'iunop', 'simd_op', 'dfdx', 'dfdy')})
for n in ('quad_and quad_or quad_xor quad_iadd quad_fadd quad_fmul quad_prefix_iadd quad_prefix_fadd quad_prefix_fmul quad_min.u quad_max.u '
          'quad_min.s quad_max.s quad_min.f quad_max.f simd_and simd_or simd_xor simd_iadd simd_fadd simd_fmul simd_prefix_iadd simd_prefix_fadd '
          'simd_prefix_fmul simd_prefix_and simd_prefix_or simd_prefix_xor simd_prefix_min.s simd_prefix_min.u simd_prefix_max.s simd_prefix_max.u '
          'simd_min.u simd_max.u simd_min.s simd_max.s simd_min.f simd_max.f').split():
    STATUS[n] = ('mapped (128-entry simd_op model)', SUB)
STATUS.update({
    'get_sr': ('mapped (bit 22 undefined)', MEM), 'TODO.sr_thing': ('mapped earlier: bit-15 get_sr writes nothing', F+'2026-10-10-sr-geometry-core-id/README.md'),
    'wait': ('mapped (bit 7 hangs; slots 2/3 hand-encoded)', MEM), 'threadgroup_barrier': ('mapped', MEM),
    'if_icmp': ('mapped', MEM), 'if_fcmp': ('mapped', MEM), 'while_icmp': ('mapped', MEM), 'while_fcmp': ('equals while_icmp (straight-line, 42 cases)', F+'2026-10-11-cf-float/README.md'),
    'else_icmp': ('mapped', MEM), 'else_fcmp': ('equals else_icmp (straight-line, 42 cases)', F+'2026-10-11-cf-float/README.md'), 'pop_exec': ('mapped', MEM),
    'device_load': ('mapped (bit 31 disables)', MEM), 'device_store': ('mapped (bit 31 drops)', MEM),
    'device_load.TODO': ('u-fields not swept (u4 = cache hint per Mesa)', MEM), 'device_store.TODO': ('u-fields not swept', MEM),
    'threadgroup_load': ('mapped', MEM), 'threadgroup_store': ('mapped', MEM), 'uniform_store': ('mapped (preshader only)', MEM),
    'TODO.unk51': ('ends the SIMD group (= no_var)', MEM), 'no_var': ('ends the SIMD group in compute', MEM),
    'TODO.after_sampling1': ('hangs in compute', MEM), 'TODO.after_sampling2': ('hangs in compute', MEM), 'TODO.unk0C00': ('hangs; last before wedge', MEM),
    'TODO.unk40C0': ('fails fast in compute', MEM), 'TODO.unk30C0': ('inert', MEM), 'TODO.unkC0000000': ('inert', MEM), 'TODO.unkE800': ('inert', MEM),
    'doorbell': ('inert', MEM), 'simd_matrix_fmadd32': ('reached via shuffle bit 27; operands not mapped', SUB), 'simd_matrix_fmadd16': ('reached via shuffle bit 27; operands not mapped', SUB),
    'stop': ('known', OPC), 'trap': ('known', OPC),
    'jmp_exec_any': ('used by every loop probe (gap bits not swept)', F+'2026-10-10-agx-loop-alu-timing/README.md'),
    'jmp_exec_none': ('used by the granularity probes (gap bits not swept)', OPC),
    'memory_barrier': ('used by the in-shader clock probe (gap bits not swept)', F+'2026-10-11-in-shader-clock/README.md'),
})
ATOM = F+'2026-10-11-atomics/README.md'
STATUS.update({
    'atomic': ('mapped: Mesa ops 0-10 exact incl. return/contention; ops 11-15 and u-bits not run (hang risk)', ATOM),
    'threadgroup_atomic': ('mapped: Mesa ops 0-10 exact incl. return/contention; ops 11-15 and u-bits not run (hang risk)', ATOM),
})
TODO_REASON = {
    'call': 'not run: a bad target can hang the GPU', 'ret': 'not run: a bad target can hang the GPU',
    'jmp_if_skipping_doorbell': 'not run: may loop on itself',
    'jmp_incomplete': 'not run: branch semantics unknown, could loop',
}
FRAG = {'iter', 'iterproj', 'TODO.ldcf', 'st_var', 'st_var_final', 'wait_pix', 'signal_pix', 'sample_mask', 'zs_emit', 'TODO.ld/st_tile', 'image_write_block'}
TEX = {'tex_state_store', 'sampler_state_store', 'image_write', 'texture_sample', 'texture_load', 'map', 'TODO.unk75_alt'}
STACK = {'stack_store', 'stack_load', 'stack_get_ptr', 'TODO.stack_adjust', 'TODO.stack_adjust2', 'async_store', 'async_load', 'TODO.pop_exec2'}


def main():
    _, g = agx_loop._tools()
    rows, seen = [], set()
    for d in g.instruction_descriptors:
        if d.name in seen: continue
        seen.add(d.name)
        lo, hi = d.sizes
        cov = d.mask | d.fields_mask | ((1 << d.length_bit_pos) if lo != hi else 0)
        gaps = sum(1 for b in range(8*hi) if not cov >> b & 1)
        unk = [nm for _, _, nm in d.fields if nm.startswith('u') and nm[1:].isdigit() or nm == 'unk']
        if d.name in STATUS: st, link = STATUS[d.name]
        elif d.name in TODO_REASON: st, link = 'open: '+TODO_REASON[d.name], None
        elif d.name in FRAG: st, link = 'open: fragment-stage only (needs a render pipeline, not direct-DRM compute)', None
        elif d.name in TEX: st, link = 'open: needs texture/sampler/image state', None
        elif d.name in STACK: st, link = 'open: needs scratch/stack memory (helper program; earlier attempts hung)', None
        else: st, link = 'open: not yet tested', None
        rows.append((d.name, f'{lo}/{hi}', gaps, ', '.join(unk), st, link))
    out = ['# AGX ISA coverage (applegpu descriptors vs. hardware results)', '',
           'Generated by `scripts/isa_coverage.py` (offline). "Gap bits" = bits applegpu leaves unaccounted in the longest form.',
           'Top-level 7-bit opcodes that applegpu cannot decode are all classified in',
           f'[opcode descriptions]({OPC}) (33 no-op, 16 ends, 7 fault, 0x64/0x74/0x6e not run).', '',
           '| Descriptor | Bytes | Gap bits | Unknown fields | Status |', '| --- | --- | --- | --- | --- |']
    for name, sz, gaps, unk, st, link in rows:
        out.append(f'| `{name}` | {sz} | {gaps} | {unk} | {f"[{st}]({link})" if link else st} |')
    n_open = sum(1 for r in rows if r[4].startswith('open'))
    out += ['', f'{len(rows)} descriptors; {len(rows)-n_open} mapped or classified, {n_open} open.']
    (REPO/'docs/isa-coverage.md').write_text('\n'.join(out)+'\n')
    print(f'{len(rows)} descriptors, {n_open} open')
    for r in rows:
        if r[4] == 'open: not yet tested': print('  untested:', r[0])


if __name__ == '__main__':
    main()
