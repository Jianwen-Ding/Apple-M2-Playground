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
done_alu = ('mov_imm iadd imadd convert bfi bfeil extr shlhi shrhi asr asrh bitop fmadd32 fmadd16 fadd32 fadd16 '
            'fmul32 fmul16 floor ceil trunc rint rcp rsqrt rsqrt_special sin_pt_1 sin_pt_2 log2 exp2 icmpsel fcmpsel icmp_ballot fcmp_ballot '
            'icmp_quad_ballot fcmp_quad_ballot simd_shuffle simd_shuffle_down simd_shuffle_up simd_shuffle_xor simd_shuffle_rotate_up '
            'quad_shuffle quad_shuffle_down quad_shuffle_up quad_shuffle_xor quad_shuffle_rotate_up simd_shuf_op').split()
STATUS = {n: ('mapped', ALU) for n in done_alu}
STATUS.update({n: ('mapped (sub-op space)', SUB) for n in ('funop', 'simd_op', 'dfdx', 'dfdy')})
# intl/bitrev/popcount/ffs/iunop are one encoding space (0x3e, op2 = bits 26-27), not separate instructions
STATUS.update({
    'iunop': ('mapped; applegpu catch-all (op1 != 0) for the same 0x3e space as intl/bitrev/popcount/ffs (aliases)', SUB),
    'intl': ('mapped (= iunop op2 00 with B operand; Morton interleave per applegpu/Mesa)', SUB),
    'bitrev': ('mapped (= iunop op2 01; alias space with intl/popcount/ffs)', SUB),
    'popcount': ('mapped (= iunop op2 10; alias space with intl/bitrev/ffs)', SUB),
    'ffs': ('mapped (= iunop op2 11, highest set bit; alias space with intl/bitrev/popcount)', SUB),
})
for n in ('quad_and quad_or quad_xor quad_iadd quad_fadd quad_fmul quad_prefix_iadd quad_prefix_fadd quad_prefix_fmul quad_min.u quad_max.u '
          'quad_min.s quad_max.s quad_min.f quad_max.f simd_and simd_or simd_xor simd_iadd simd_fadd simd_fmul simd_prefix_iadd simd_prefix_fadd '
          'simd_prefix_fmul simd_prefix_and simd_prefix_or simd_prefix_xor simd_prefix_min.s simd_prefix_min.u simd_prefix_max.s simd_prefix_max.u '
          'simd_min.u simd_max.u simd_min.s simd_max.s simd_min.f simd_max.f').split():
    STATUS[n] = ('mapped (128-entry simd_op model)', SUB)
STATUS.update({
    'get_sr': ('mapped (bit 22 undefined)', MEM), 'TODO.sr_thing': ('mapped earlier: bit-15 get_sr writes nothing', F+'2026-10-10-sr-geometry-core-id/README.md'),
    'wait': ('mapped (bits 9-15 inert; bit 7 = 0xb8 hangs)', ALU),
    'threadgroup_barrier': ('mapped (gap bits 8-15: no observable effect with one SIMD group; scope effects untested)', MEM),
    'if_icmp': ('mapped', MEM), 'if_fcmp': ('mapped', MEM), 'while_icmp': ('mapped', MEM), 'while_fcmp': ('equals while_icmp for lt/gt/eq only (3 of 8 conds; straight-line, 42 cases)', F+'2026-10-11-cf-float/README.md'),
    'else_icmp': ('mapped', MEM), 'else_fcmp': ('equals else_icmp for lt/gt/eq only (3 of 8 conds; straight-line, 42 cases)', F+'2026-10-11-cf-float/README.md'), 'pop_exec': ('mapped', MEM),
    'device_load': ('mapped (bit 31 disables)', MEM), 'device_store': ('mapped (bit 31 drops)', MEM),
    'device_load.TODO': ('u-fields not swept (u4 = cache hint per Mesa)', MEM), 'device_store.TODO': ('u-fields not swept', MEM),
    'threadgroup_load': ('mapped', MEM), 'threadgroup_store': ('mapped', MEM), 'uniform_store': ('mapped (preshader only)', MEM),
    'TODO.unk51': ('ends the SIMD group (= no_var with u=0)', MEM),
    'no_var': ('u=0 form (0x00000051) ends the SIMD group in compute; Mesa emits u=1 (0x80000051), not run', MEM),
    'TODO.after_sampling1': ('hangs in compute', MEM), 'TODO.after_sampling2': ('hangs in compute', MEM), 'TODO.unk0C00': ('hangs; last before wedge', MEM),
    'TODO.unk40C0': ('fails fast in compute', MEM), 'TODO.unk30C0': ('inert', MEM), 'TODO.unkC0000000': ('inert', MEM), 'TODO.unkE800': ('0x68 + bit 7: no observable effect with one SIMD group; scope effects untested', MEM),
    'doorbell': ('inert', MEM), 'simd_matrix_fmadd32': ('reached via shuffle bit 27; operands not mapped', SUB), 'simd_matrix_fmadd16': ('reached via shuffle bit 27; operands not mapped', SUB),
    'stop': ('known', OPC), 'trap': ('known', OPC),
    'jmp_exec_any': ('used by every loop probe (gap bits not swept)', F+'2026-10-10-agx-loop-alu-timing/README.md'),
    'jmp_exec_none': ('used by the granularity probes (gap bits not swept)', OPC),
    'memory_barrier': ('used by the in-shader clock probe (gap bits not swept)', F+'2026-10-11-in-shader-clock/README.md'),
})
ATOM = F+'2026-10-11-atomics/README.md'
ATOMV = F+'2026-10-17-atomic-variants/README.md'
STATUS.update({
    'atomic': ('mapped: Mesa ops 0-10 exact; bit 45: sub = float32 add (ftz, RNE), cmpxchg = u64 min/max (bit 46 = max); ops 11-15 end the SIMD group; u1-u4 single-bit follow-up in atomic-gap-bits finding', ATOMV),
    'threadgroup_atomic': ('Mesa ops 0-10 exact; ops 11-15 stop one issuing group even with empty mask; sub bit 6 suppresses; selected other bits inert; termination memory effects open', F+'2026-10-17-tg-atomic-followup/README.md'),
})
STATUS.update({
    'call': ('uniform direct and register targets measured; nested direct calls work; divergent targets open', F+'2026-10-17-call-ret/README.md'),
    'ret': ('uniform buffer-relative byte target; pop_exec 2 reconverges; divergent and out-of-program behavior open', F+'2026-10-17-call-ret/README.md'),
})
STK = F+'2026-10-11-stack-via-mesa/README.md'
STATUS.update({'stack_store': ('Mesa form runs exactly through Mesa; binary captured (also decodes Mesa stack_adjust)', STK),
               'stack_load': ('Mesa form runs exactly through Mesa; binary captured', STK)})
TODO_REASON = {
    'jmp_if_skipping_doorbell': 'not run: may loop on itself',
    'jmp_incomplete': 'not run: branch semantics unknown, could loop',
}
FRAG = {'iter', 'iterproj', 'TODO.ldcf', 'st_var', 'st_var_final', 'wait_pix', 'signal_pix', 'sample_mask', 'zs_emit', 'TODO.ld/st_tile', 'image_write_block'}
TEX = {'tex_state_store', 'sampler_state_store', 'image_write', 'texture_sample', 'texture_load', 'map', 'TODO.unk75_alt'}
STACK = {'stack_get_ptr', 'TODO.stack_adjust', 'TODO.stack_adjust2', 'async_store', 'async_load', 'TODO.pop_exec2'}


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
           f'[opcode descriptions]({OPC}): 31 no-op (low bits `0b11`, 6 bytes), 0x78 a 4-SIMD-group barrier',
           f'([0x68 vs 0x78]({F}2026-10-11-barrier-0x68-vs-0x78/README.md)), 0x18 a fixed-cost op of unknown target',
           f'([sync opcodes]({F}2026-10-11-sync-and-end-opcodes/README.md)), 16 ends, 7 fault on direct DRM;',
           '0x64/0x74 never run on direct DRM (presumed faulting from the 2026-10-04 Vulkan scan, outputs not retained); 0x6e not run.', '',
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
