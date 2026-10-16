"""Offline check: compute command boundaries in another process evict the GPU-wide L2
(results/2026-10-16-l2-command-boundary)."""
import gzip, hashlib, json, pathlib, statistics, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
R = ROOT/'results/2026-10-16-l2-command-boundary'


def main():
    fails = []

    def check(name, ok):
        print(('ok   ' if ok else 'FAIL ')+name)
        if not ok: fails.append(name)

    for line in (R/'sources.sha256').read_text().splitlines():
        h, f = line.split()
        check(f'{f} matches the recorded hash', hashlib.sha256((ROOT/f).read_bytes()).hexdigest() == h)
    bg = json.loads((R/'background.json').read_text())
    check('mode c background kernel ends with stop and passed the simulator oracle', bg['c_long_kernel']['code_hex'].endswith('8800') and bg['c_long_kernel']['simulator']['oracle_ok'])
    ns = {}
    for m in ('none', 'a', 'b', 'c', 'newkeeper'):
        d = json.load(gzip.open(R/f'chase-{m}.json.gz', 'rt'))
        v = {x['footprint']: x for x in d['variants']}[65536]
        hops = v['hops']  # trips x steps
        fw = [s['fw_ts'][1]-s['fw_ts'][0] for s in v['samples']]
        check(f'{m}: 64 KiB chase exact and agx_run-gated', v['buffer_ok'] and v['simulator']['oracle_ok'])
        ns[m] = (min(fw)/hops, statistics.median(fw)/hops)
    print({k: (round(a, 1), round(b, 1)) for k, (a, b) in ns.items()})
    check('no background: L2-resident 64 KiB chase ~96 ns per hop', 90 <= ns['none'][1] <= 100)
    check('a (a command boundary every ~0.13 ms): median > 2x the clean value', ns['a'][1] > 2*ns['none'][1])
    check('b (one short command every ~5 ms) and c (6.3 ms commands back to back, 100% busy): within 8% of clean',
          ns['b'][1] < 1.08*ns['none'][1] and ns['c'][1] < 1.08*ns['none'][1])
    check('the long-command clock keeper: within 5% of clean', ns['newkeeper'][1] < 1.05*ns['none'][1])
    print(f'{len(fails)} failures')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
