"""Offline check of the device-atomic contention evidence (results/2026-10-16-atomic-contention, safe-02 step 1)."""
import gzip, hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
R = ROOT/'results/2026-10-16-atomic-contention'


def main():
    fails = []

    def check(name, ok):
        print(('ok   ' if ok else 'FAIL ')+name)
        if not ok: fails.append(name)

    for line in (R/'sources.sha256').read_text().splitlines():
        h, f = line.split()
        check(f'{f} matches the recorded hash', hashlib.sha256((ROOT/f).read_bytes()).hexdigest() == h)
    d = json.load(gzip.open(R/'record.json.gz', 'rt'))
    runs = {(r['mode'], r['spacing'], r['lanes'], r['addresses']): r for r in d['runs']}
    check('40 configurations, every table exactly (lanes per word) x R, simulator-gated',
          len(runs) == 40 and all(r['oracle_ok'] for r in runs.values()))
    t = lambda k: min(runs[k]['fw_ns'])
    per = lambda k: t(k)/runs[k]['atomics']
    one = [per(('all', sp, L, 1)) for sp in (16, 1) for L in (1024, 32768, 65536)] + [per(('lane0', sp, L, 1)) for sp in (16, 1) for L in (32768, 65536)]
    check('one word: 0.84-0.96 ns per lane-operation for 1,024-65,536 lanes, both modes (lanes of a SIMD group are not combined)',
          all(0.84 <= x <= 0.96 for x in one))
    check('one address per 64 B line, 32,768-65,536 lanes: 18-26 operations per ns GPU-wide',
          all(18 <= runs[k]['atomics']/t(k) <= 26 for k in [('all', 16, 32768, 32), ('all', 16, 32768, 1024), ('all', 16, 32768, 32768), ('all', 16, 65536, 65536)]))
    check('distinct words packed 16 per line: > 100 operations per ns (>= 4x the one-per-line rate)',
          all(runs[k]['atomics']/t(k) > 100 for k in [('all', 1, 32768, 1024), ('all', 1, 32768, 32768), ('all', 1, 65536, 65536)]))
    print(f'{len(fails)} failures')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
