"""Offline check of the cache-line evidence (results/2026-10-16-cache-line, simulator task safe-03 step 1)."""
import gzip, hashlib, json, pathlib, statistics, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
R = ROOT/'results/2026-10-16-cache-line'


def main():
    fails = []

    def check(name, ok):
        print(('ok   ' if ok else 'FAIL ')+name)
        if not ok: fails.append(name)

    for line in (R/'sources.sha256').read_text().splitlines():
        h, f = line.split()
        check(f'{f} matches the recorded hash', hashlib.sha256((ROOT/f).read_bytes()).hexdigest() == h)
    d = json.load(gzip.open(R/'neighbour.json.gz', 'rt'))
    H = d['hops']
    runs = {(r['elements'], r['offset']): r for r in d['runs']}
    check('42 runs (3 element counts x 14 offsets), every readback exact, every kernel + table passed agx_run first',
          len(runs) == 42 and all(r['oracle_ok'] and r['simulator']['oracle_ok'] for r in runs.values()))
    med = lambda n, d_: statistics.median(runs[(n, d_)]['fw_ns'])/H
    for n, step in ((64, 10), (1024, 120), (65536, 100)):
        below = [med(n, x) for x in (4, 16, 32, 48, 60)]
        above = [med(n, x) for x in (64, 96, 124, 128, 192)]
        check(f'{n} elements: every offset >= 64 B costs > {step} ns more per hop than every offset < 64 B',
              min(above)-max(below) > step)
        a128 = [med(n, x) for x in (128, 192)]; a64 = [med(n, x) for x in (64, 96, 124)]
        check(f'{n} elements: no second step at 128 B (offsets 128-192 within 12% of 64-124)',
              abs(statistics.mean(a128)-statistics.mean(a64)) < 0.12*statistics.mean(a64))
    print(f'{len(fails)} failures')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
