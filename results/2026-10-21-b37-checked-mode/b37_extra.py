#!/usr/bin/env python3
"""B37 items 2 and 3 on top of the LLVM fork's llvm/utils/agx-checked/zluda_tests.py (its kernels, zoc builds and
run_checked.launch). Usage: b37_extra.py ZOC LLVM_BUILD AGX_RUN [sim|hw]
  item 3: each bug kernel's checked build launched with the error record already claimed (claimed = 1): the kernel
          must return at once, so every output buffer keeps its initial contents and the record is unchanged.
  item 2: GRID_COPY over 2^22 threads (256 per block), checked and unchecked, 5 runs each; firmware time from the
          agx_run_hw JSON line (AGX_RUN should be a wrapper that appends it to $B37_LOG). On sim, 2^14 threads (gate)."""
import json, os, statistics, sys, tempfile
sys.path.insert(0, '/scratch/llvm-agx/llvm/utils/agx-checked')
import zluda_tests as Z, run_checked as rc
zoc, build, agx_run, mode = sys.argv[1:5]
objcopy, readelf = os.path.join(build, 'bin/llvm-objcopy'), os.path.join(build, 'bin/llvm-readelf')
res = {'mode': mode}
with tempfile.TemporaryDirectory() as tmp:
    rows = {}
    for name in ('off-by-one-store', 'atomic-out-of-bounds', 'shared-out-of-bounds', 'second-block', 'struct-pointer-off-by-one'):
        ptx, args, grid, wg, expect, kw = Z.KERNELS[name]
        obj = Z.compile_ptx(name, ptx, zoc, 'agx-g14c', False, True, tmp)
        a = args()
        r = rc.launch(obj, 'k', a, grid, wg, agx_run, objcopy, readelf, claimed=1, **{k: v for k, v in kw.items() if k in ('tg_bytes', 'dynamic_shared')})
        init = [x[1] for x in a if x[0] == 'buf'] + [y[1] for x in a if x[0] == 'param' for y in x[1] if y[0] == 'buf']
        unchanged = all(bytes(b) == bytes(i) for b, i in zip(r.buffers, init))
        rows[name] = {'claimed_after': r.claimed, 'buffers_unchanged': unchanged, 'record_kind': getattr(r, 'kind', None)}
    res['item3_second_launch_after_error'] = rows
    n = 1 << (22 if mode == 'hw' else 14)
    times = {}
    for checked in (False, True):
        obj = Z.compile_ptx('grid', Z.HEADER + Z.GRID_COPY, zoc, 'agx-g14c', False, checked, tmp)
        t = []
        for _ in range(5 if mode == 'hw' else 1):
            log = os.path.join(tmp, 'log.jsonl'); open(log, 'w').close(); os.environ['B37_LOG'] = log
            r = rc.launch(obj, 'k', [('buf', Z.words(n)), ('buf', bytes(4 * n)), ('i32', n)], (n, 1, 1), (256, 1, 1),
                          agx_run, objcopy, readelf)
            assert not r.claimed, str(r)
            out = Z.u32s(r.buffers[1])
            assert all(out[i] == 2 * i for i in range(n)), 'wrong copy'
            for line in open(log):
                j = json.loads(line)
                if 'fw_ns' in j: t.append(j['fw_ns'] / 1e6)
        times['checked' if checked else 'unchecked'] = t
    res['item2_grid_copy_threads'] = n
    res['item2_firmware_ms'] = {k: [round(x, 4) for x in v] for k, v in times.items()}
    if all(times.values()):
        res['item2_ratio_median'] = statistics.median(times['checked']) / statistics.median(times['unchecked'])
print(json.dumps(res, indent=1))
