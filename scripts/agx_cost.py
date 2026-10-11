#!/usr/bin/env python3
"""AGX (G14C) cycle cost model and simulator. No GPU access.

    python3 scripts/agx_cost.py code.bin [--groups 1|4] [--trips N] [--annotate]

Pipeline
  decode   : applegpu decodes every instruction; operands give the registers read/written
             (16-bit halves), immediates and wait slots.
  trace    : the dynamic path for one SIMD group, from applegpu's emulator. Instructions it
             cannot execute are skipped (they leave registers unchanged), which is enough to
             follow counted loops and structured control flow driven by iadd / *_cmp.
  simulate : a cycle-level model of one core running G identical SIMD groups:
             * each group issues in order, at most one instruction per cycle, and an
               instruction blocks its group for its *issue interval* (per class);
             * a source is ready `latency` cycles after its producer issued;
             * per core and cycle: at most ISSUE_PER_CORE instructions, at most
               READ_PORTS 32-bit register-operand reads (16-bit = 1/2), and per execution
               unit at most its measured instructions/cycle (token buckets);
             * loads complete after LOAD_LATENCY cycles; `wait s` stalls until slot s drains;
             * a taken backward jump costs BRANCH_TAKEN extra cycles.
Parameters come from results/2026-10-11-instruction-bench (latency, issue interval and
per-core throughput per instruction class) and results/2026-10-11-cost-model/calibration.json
(control-flow, get_sr, wait, load costs measured on hardware).
"""
import argparse, contextlib, gzip, io, json, math, re, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agx_loop

REPO = Path(__file__).resolve().parents[1]
BENCH = REPO/'results/2026-10-11-instruction-bench/bench.json.gz'
CALIB = REPO/'results/2026-10-11-cost-model/calibration.json'

ISSUE_PER_CORE = 4.0
# Cycle units: the model works in units of the benchmark reference (a dependent 8-byte `iadd x, x, 1`
# step = 2 units). Against the GPU's DVFS table (444..1398 MHz, t602x-common.dtsi) every inferred clock is
# low by 1.049, so one unit = 1.049 real cycles. `--real-cycles` applies it.
REAL_CYCLES_PER_UNIT = 1.049
RESULT_CACHE = 8          # per SIMD group: the last 8 written registers are readable at producer latency
RF_WRITEBACK = 17         # a value evicted from the result cache is readable from the register file this
                          # many cycles after its producer issued (fit: D = 9/10/12/16 rotation, cost-model README)
READ_PORTS = 4.0          # 32-bit register-operand reads per core per cycle (fit, see the bench finding)

# descriptor name -> benchmark row used for latency / issue interval / unit throughput
CLASS = {
    'iadd': 'iadd', 'isub': 'isub', 'imadd': 'imadd', 'bitop': 'and', 'and': 'and', 'or': 'and', 'xor': 'xor',
    'andn1': 'and', 'andn2': 'and', 'orn1': 'and', 'orn2': 'and', 'xnor': 'xor', 'nand': 'and', 'nor': 'and', 'not': 'and', 'bitop_mov_a': 'and',
    'bfi': 'bfi', 'bfeil': 'bfeil', 'extr': 'extr', 'shlhi': 'shlhi', 'shrhi': 'shrhi', 'asr': 'asr', 'asrh': 'asrh',
    'bitrev': 'bitrev', 'popcount': 'popcount', 'ffs': 'ffs', 'intl': 'intl', 'icmpsel': 'icmpsel', 'fcmpsel': 'fcmpsel',
    'mov_imm': 'mov_imm', 'fadd32': 'fadd32', 'fmul32': 'fmul32', 'fmadd32': 'fmadd32', 'fadd16': 'fadd16',
    'fmul16': 'fmul16', 'fmadd16': 'fmadd16', 'convert': 'convert_f2i', 'floor': 'floor', 'ceil': 'floor', 'trunc': 'floor',
    'rint': 'rint', 'rcp': 'rcp', 'rsqrt': 'rsqrt', 'rsqrt_special': 'rsqrt_special', 'log2': 'log2', 'exp2': 'exp2',
    'sin_pt_1': 'sin_pt_1', 'sin_pt_2': 'sin_pt_2', 'simd_shuffle': 'simd_shuffle', 'simd_shuffle_down': 'simd_shuffle_down',
    'simd_shuffle_up': 'simd_shuffle_down', 'simd_shuffle_xor': 'simd_shuffle_xor', 'simd_shuffle_rotate_up': 'simd_shuffle_down',
    'quad_shuffle': 'quad_shuffle', 'quad_shuffle_down': 'quad_shuffle', 'quad_shuffle_up': 'quad_shuffle', 'quad_shuffle_xor': 'quad_shuffle',
    'icmp_ballot': 'icmp_ballot', 'fcmp_ballot': 'fcmp_ballot', 'icmp_quad_ballot': 'icmp_ballot', 'fcmp_quad_ballot': 'fcmp_ballot',
}
# benchmark rows that exercise the same execution unit with different operand kinds; a unit's
# throughput cap is the best any of them reached (the slower ones are read-port bound)
UNIT_GROUPS = [['iadd', 'isub', 'iadd_lsl2', 'iadd_imm', 'iadd_cache'], ['imadd', 'imul', 'imadd_cache'],
               ['fadd32', 'fadd32_imm', 'fadd32_cache', 'fadd32_cache2'], ['fmul32', 'fmul32_cache'],
               ['fmadd32', 'fmadd32_imm', 'fmadd32_cache'], ['and', 'xor']]
# execution-unit families: an instruction's issue interval blocks only later instructions of the same
# family in that SIMD group (measured: bfi/imadd/floor/rcp + independent iadds overlap), except SIMD
# reductions/scans, which block the whole group (reduction + 8 iadds is additive)
FAMILY = {}
for k in ('imadd', 'imul', 'imadd_cache', 'imadd_wide'): FAMILY[k] = 'imad'
for k in ('bfi', 'bfeil', 'extr', 'shlhi', 'shrhi', 'asr', 'asrh', 'bitrev', 'popcount', 'ffs', 'intl'): FAMILY[k] = 'bitfield'
for k in ('rcp', 'rsqrt', 'rsqrt_special', 'log2', 'exp2', 'sin_pt_1', 'sin_pt_2', 'floor', 'rint'): FAMILY[k] = 'sfu'
for k in ('convert_f2i', 'convert_i2f'): FAMILY[k] = 'convert'
for k in ('simd_shuffle', 'simd_shuffle_down', 'simd_shuffle_xor', 'icmp_ballot', 'fcmp_ballot'): FAMILY[k] = 'shuffle'
GROUP_BLOCKING = {'simd_iadd', 'simd_prefix_iadd', 'simd_fadd', 'simd_min.u', 'quad_iadd'}
WAW_PARTIAL = 1           # extra cycle: a 32-bit write right after a 16-bit write of the same register (measured +0.86 per pair)
SIMD_REDUCE = re.compile(r'^(simd|quad)_(prefix_)?(iadd|fadd|fmul|and|or|xor|min|max)')
CONTROL = {'if_icmp', 'if_fcmp', 'else_icmp', 'else_fcmp', 'while_icmp', 'while_fcmp', 'pop_exec', 'push_exec',
           'jmp_exec_any', 'jmp_exec_none', 'stop'}
REG = re.compile(r'^r(\d+)(l|h)?(?:_r(\d+))?$')


def halves(op):
    """Register operand -> set of 16-bit half indices (empty for non-registers)."""
    s = str(op)
    m = REG.match(s.split('.')[0])
    if not m: return set()
    a = int(m.group(1)); t = type(op).__name__
    if m.group(2): return {2*a + (m.group(2) == 'h')}
    if m.group(3): return set(range(2*a, 2*int(m.group(3))+2))
    if t == 'Reg64': return set(range(2*a, 2*a+4))
    return {2*a, 2*a+1}


class Params:
    def __init__(self, bench=BENCH, calib=CALIB, load_latency=None):
        b = json.loads(gzip.open(bench).read())['ops']
        self.rows = {k: {'lat': v['latency']['cycles_per_step'], 'ii': v['simd_issue']['cycles_per_step'],
                         'ipc': v['gpu']['lanes_per_cycle_per_core']/32, 'tmpl': v['template']} for k, v in b.items()}
        self.unit_cap = {k: v['ipc'] for k, v in self.rows.items()}
        for grp in UNIT_GROUPS:
            best = max(self.rows[k]['ipc'] for k in grp if k in self.rows)
            for k in grp: self.unit_cap[k] = best
        self.cal = json.loads(Path(calib).read_text()) if Path(calib).exists() else {}
        self.load_latency = load_latency or self.cal.get('device_load_l1_cycles', 50)

    def row(self, name):
        return self.rows.get(name)


def decode(code, P):
    _, g = agx_loop._tools()
    out, pc = [], 0
    while pc < len(code):
        n = g.opcode_to_number(code[pc:pc+16]); d = g.get_instruction_descriptor(n)
        if d is None: raise ValueError(f'undecodable instruction at {pc}')
        size = d.decode_size(n); n &= (1 << 8*size)-1
        ops = d.decode_operands(n)
        name = d.name
        text = ' '.join(str(d.disassemble(n)).split())
        regs = [halves(o) for o in ops]
        imm = sum(1 for o in ops if type(o).__name__ == 'Immediate')
        rec = {'pc': pc, 'size': size, 'name': name, 'text': text, 'dst': set(), 'src': set(), 'reads32': 0.0, 'unit': None}
        if name in ('device_load', 'threadgroup_load', 'stack_load'):
            rec['dst'] = set().union(*[r for r, o in zip(regs, ops) if type(o).__name__ == 'RegisterTuple'])
            rec['src'] = set().union(set(), *[r for r, o in zip(regs, ops) if type(o).__name__ != 'RegisterTuple'])
            rec['kind'] = 'load'; rec['slot'] = int(n >> 30 & 1)
        elif name in ('device_store', 'threadgroup_store', 'stack_store', 'atomic', 'threadgroup_atomic', 'uniform_store'):
            rec['src'] = set().union(set(), *regs); rec['kind'] = 'store'
            if name in ('atomic', 'threadgroup_atomic') and any(regs[:2]): rec['kind'] = 'load'; rec['dst'] = regs[2] if name == 'atomic' else regs[0]; rec['slot'] = 0
        elif name == 'wait':
            rec['kind'] = 'wait'; rec['slot'] = int(str(ops[0])) if ops else 0
        elif name in CONTROL:
            rec['kind'] = 'control'; rec['src'] = set().union(set(), *regs[1:]); rec['dst'] = {0} if name != 'stop' else set()
        elif 'barrier' in name:
            rec['kind'] = 'barrier'
        else:
            rec['kind'] = 'alu'
            rr = [r for r in regs if r]          # register operands only (modes / conditions are strings)
            if rr:
                rec['dst'] = rr[0]; rec['src'] = set().union(set(), *rr[1:])
            # register-port reads: unique 32/64-bit source registers; 16-bit sources do not count
            # (quad_shuffle with a 16-bit index reaches 3.8 instr/cycle/core)
            srcops = [(o, r) for o, r in zip(ops, regs) if r][1:]
            rec['reads32'] = len({h//2 for o, r in srcops if type(o).__name__ in ('Reg32', 'Reg64') for h in r})
            rec['cache'] = any('.cache' in str(o) for o, r in srcops)
            if name.startswith('get_sr'): rec['src'] = set(); rec['reads32'] = 0
            key = CLASS.get(name)
            if key is None and SIMD_REDUCE.match(name):
                key = 'quad_iadd' if name.startswith('quad') else ('simd_prefix_iadd' if 'prefix' in name else 'simd_iadd')
            if name in ('iadd', 'isub', 'imadd') and any(len(r) == 4 for r in regs[:1]):
                key = 'iadd64' if name != 'imadd' else 'imadd_wide'
            # pick the measured operand variant when one exists
            if key and imm and P.row(key+'_imm'): key = key+'_imm'
            elif key and rec['cache'] and P.row(key+'_cache'): key = key+'_cache'
            rec['unit'] = key
            rec['imm'] = imm
        out.append(rec); pc += size
    return out


def trace(code, active=32, max_steps=500_000):
    """Dynamic pc sequence for one SIMD group (applegpu emulator; unsupported ops skipped)."""
    _, g = agx_loop._tools()
    st = g.CoreState(num_registers=128, uniforms=g.Uniforms(), device_memory=agx_loop._Memory(agx_loop.TABLE_VA, [0]*65536))
    for t in range(g.SIMD_WIDTH):
        st.set_reg16(0, t, 0 if t < active else 1); st.set_reg32(1, t, t)
    st.exec = [t < active for t in range(g.SIMD_WIDTH)]
    pcs, pc, skipped = [], 0, set()
    while pc < len(code):
        n = g.opcode_to_number(code[pc:pc+16]); d = g.get_instruction_descriptor(n)
        size = d.decode_size(n); n &= (1 << 8*size)-1
        pcs.append(pc)
        if len(pcs) > max_steps: raise RuntimeError('trace step limit (non-terminating loop?)')
        if d.name == 'stop': break
        if d.name == 'jmp_exec_any':
            off = dict(d.decode_fields(n))['off']; off = off-(1 << 32) if off & (1 << 31) else off
            pc = pc+off if any(st.exec) else pc+size; continue
        if d.name == 'jmp_exec_none':
            off = dict(d.decode_fields(n))['off']; off = off-(1 << 32) if off & (1 << 31) else off
            pc = pc+off if not any(st.exec) else pc+size; continue
        try:
            with contextlib.redirect_stdout(io.StringIO()):   # applegpu prints debug lines for some ops
                d.exec(n, st)
        except Exception:
            skipped.add(d.name)
        pc += size
    return pcs, skipped


def simulate(instrs, pcs, P, groups=1, detail=False):
    """Cycle-level simulation of `groups` identical SIMD groups on one core. Returns cycles
    (and per-pc issue/stall statistics when detail=True)."""
    by_pc = {r['pc']: r for r in instrs}
    cal = P.cal
    branch = cal.get('branch_taken_cycles', 30)
    ctrl_ii = cal.get('control_issue_cycles', 1)
    nxt = [0]*groups                 # index into pcs
    busy = [0]*groups                # group may issue at cycle >= busy
    ready = [defaultdict(int) for _ in range(groups)]   # half register -> ready cycle
    loads = [defaultdict(list) for _ in range(groups)]  # slot -> completion cycles
    fam_busy = [defaultdict(int) for _ in range(groups)]
    last_w = [dict() for _ in range(groups)]            # 32-bit register -> (width in halves, ready cycle)
    rcache = [[] for _ in range(groups)]                # 32-bit register ids, most recent last
    wtime = [dict() for _ in range(groups)]             # 32-bit register -> issue cycle of its last write
    unit_tok = defaultdict(float); port_tok = 0.0
    W = cal.get('rf_writeback_cycles', RF_WRITEBACK); NC = cal.get('result_cache_entries', RESULT_CACHE)
    def src_ready(gi, h):
        r = ready[gi][h]; reg = h//2
        if reg in wtime[gi] and reg not in rcache[gi]:
            r = max(r, wtime[gi][reg]+W)
        return r
    stats = defaultdict(lambda: {'n': 0, 'stall': 0, 'issue_cycle_sum': 0})
    cyc = 0; done = 0; last_issue = [0]*groups; pend_branch = [(None, 0)]*groups
    while done < groups:
        issued = 0
        port_tok = min(port_tok+READ_PORTS, READ_PORTS+4)
        # token buckets hold at most rate + 1 so a unit rated r per cycle can issue r per cycle on average
        for u in list(unit_tok): unit_tok[u] = min(unit_tok[u]+P.unit_cap[u], P.unit_cap[u]+1)
        order = list(range(groups)); order = order[cyc % groups:]+order[:cyc % groups]
        for gi in order:
            if nxt[gi] >= len(pcs) or busy[gi] > cyc or issued >= ISSUE_PER_CORE: continue
            r = by_pc[pcs[nxt[gi]]]
            if any(src_ready(gi, h) > cyc for h in r['src']):
                continue
            fam = FAMILY.get(r.get('unit') or '', r.get('unit'))
            if cal.get('issue_mode', 'group') == 'shared' and r.get('unit') and P.rows[r['unit']]['ii'] >= 1.5:
                fam = 'complex'      # all multi-cycle-issue classes share one pipe per SIMD group
            if fam and fam_busy[gi][fam] > cyc:
                continue
            # partial-width write after write: a 16-bit write and a 32-bit write of one register serialize
            if r['kind'] == 'alu' and r['dst']:
                wid = len(r['dst']); regs_w = {h//2 for h in r['dst']}
                if any(reg in last_w[gi] and last_w[gi][reg][0] < wid and last_w[gi][reg][1]+1+WAW_PARTIAL > cyc for reg in regs_w):
                    continue
            if r['kind'] == 'wait':
                pend = loads[gi][r['slot']]
                if pend and max(pend) > cyc: continue
                loads[gi][r['slot']] = []
            u = r.get('unit')
            if u:
                if u not in unit_tok: unit_tok[u] = P.unit_cap[u]+1
                if unit_tok[u] < 1 or port_tok < min(r['reads32'], READ_PORTS): continue
                unit_tok[u] -= 1; port_tok -= min(r['reads32'], READ_PORTS)
            # issue
            taken = False
            row = P.rows.get(u) if u else None
            if r['kind'] == 'alu':
                lat = row['lat'] if row else cal.get('alu_default_latency', 2)
                ii = row['ii'] if row else 1
                if r['name'].startswith('get_sr'): lat, ii = cal.get('get_sr_latency', 4), cal.get('get_sr_issue', 1)
                for h in r['dst']: ready[gi][h] = cyc+int(round(lat))
            elif r['kind'] == 'load':
                lat = P.load_latency; ii = 1
                for h in r['dst']: ready[gi][h] = cyc+lat
                loads[gi][r['slot']].append(cyc+lat)
            elif r['kind'] == 'control':
                ii = ctrl_ii
                for h in r['dst']: ready[gi][h] = cyc+cal.get('control_latency', 2)
                if r['name'] == 'jmp_exec_any' and nxt[gi]+1 < len(pcs) and pcs[nxt[gi]+1] < r['pc']:
                    ii += branch; taken = True
            else:
                ii = cal.get('store_issue_cycles', 1) if r['kind'] == 'store' else cal.get(r['kind']+'_cycles', 1)
            if r['kind'] in ('alu', 'load'):
                for reg in sorted({h//2 for h in r['dst']}):
                    if reg in rcache[gi]: rcache[gi].remove(reg)
                    rcache[gi].append(reg); wtime[gi][reg] = cyc
                    if len(rcache[gi]) > NC: rcache[gi].pop(0)
            st = stats[r['pc']]; st['n'] += 1
            stall = cyc-last_issue[gi]-1 if nxt[gi] else 0
            bpc, bpen = pend_branch[gi]
            if bpc is not None:                 # taken-branch penalty belongs to the jump, not to this instruction
                moved = min(stall, bpen); stats[bpc]['stall'] += moved; stats[bpc]['branch'] = stats[bpc].get('branch', 0)+moved
                stall -= moved; pend_branch[gi] = (None, 0)
            st['stall'] += stall; st['issue_cycle_sum'] += cyc
            if taken: pend_branch[gi] = (r['pc'], branch)
            last_issue[gi] = cyc
            if r['kind'] == 'alu' and r['dst']:
                for reg in {h//2 for h in r['dst']}: last_w[gi][reg] = (len(r['dst']), cyc)    # issue cycle
            if r.get('unit') in GROUP_BLOCKING or r['kind'] != 'alu' or cal.get('issue_mode', 'group') == 'group':
                busy[gi] = cyc+max(1, int(round(ii)))
            else:
                busy[gi] = cyc+1
                if fam: fam_busy[gi][fam] = cyc+max(1, int(round(ii)))
            nxt[gi] += 1; issued += 1
            if nxt[gi] >= len(pcs): done += 1
        cyc += 1
        if cyc > 50_000_000: raise RuntimeError('simulation limit')
    return (cyc, stats) if detail else cyc


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('code', type=Path)
    ap.add_argument('--groups', type=int, default=1)
    ap.add_argument('--load-latency', type=int)
    ap.add_argument('--annotate', action='store_true')
    a = ap.parse_args()
    P = Params(load_latency=a.load_latency)
    code = a.code.read_bytes()
    ins = decode(code, P); pcs, skipped = trace(code)
    cyc, stats = simulate(ins, pcs, P, a.groups, detail=True)
    print(json.dumps({'instructions': len(ins), 'dynamic': len(pcs), 'groups': a.groups, 'cycles': cyc,
                      'emulator_skipped': sorted(skipped)}))
    if a.annotate:
        for r in ins:
            s = stats.get(r['pc'], {'n': 0, 'stall': 0})
            print(f"{r['pc']:6d}  x{s['n']:<7d} stall {s['stall']:<8d} {r['unit'] or r['kind']:16s} {r['text']}")


if __name__ == '__main__':
    main()
