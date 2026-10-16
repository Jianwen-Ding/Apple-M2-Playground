"""Offline check of several-commands-per-SUBMIT and the clock-ramp evidence (results/2026-10-16-commands-per-submit,
simulator task safe-04 step 4)."""
import gzip, hashlib, json, pathlib, statistics, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
R = ROOT/'results/2026-10-16-commands-per-submit'


def main():
    fails = []

    def check(name, ok):
        print(('ok   ' if ok else 'FAIL ')+name)
        if not ok: fails.append(name)

    for line in (R/'sources.sha256').read_text().splitlines():
        h, f = line.split()
        check(f'{f} matches the recorded hash', hashlib.sha256((ROOT/f).read_bytes()).hexdigest() == h)
    m = json.load(gzip.open(R/'matrix.json.gz', 'rt'))
    ramp = json.load(gzip.open(R/'clock-ramp.json.gz', 'rt'))
    for name, d in (('matrix', m), ('ramp', ramp)):
        check(f'{name}: kernels end with stop and passed the simulator oracle before GPU use',
              all(k['code_hex'].endswith('8800') and k['simulator']['oracle_ok'] for k in d['kernels'].values()))
        check(f'{name}: every configuration completed with the exact oracle, all waits returned',
              all(r['oracle_ok'] and r['returncode'] == 0 and all(q['wait'] == 0 for q in r['reps']) for r in d['runs']))
    runs = {(r['kind'], r['barrier'], r['n']): r for r in m['runs']}
    check('matrix: control / delay x chain / none x N = 1, 2, 4, ..., 64 (28 configurations, 8 repeats)',
          len(runs) == 28 and all(len(r['reps']) == 8 for r in runs.values()))
    cmds = lambda r: [q.get('cmd_ts', [q['fw_ts']]) for q in r['reps']]
    gaps = lambda r: [c[i+1][0]-c[i][1] for cs in cmds(r) for c in [cs] for i in range(len(c)-1)]
    check('64 commands in one SUBMIT accepted and timestamped individually',
          all(len(c) == 64 for k in ('control', 'delay') for b in ('chain', 'none') for c in cmds(runs[(k, b, 64)])))
    allg = [g for r in m['runs'] for g in gaps(r)]+[g for r in ramp['runs'] for g in gaps(r)]
    check('commands of one SUBMIT never overlap, with or without barriers', min(allg) > 0)
    med = lambda k, b: statistics.median(g for n in (8, 16, 32, 64) for g in gaps(runs[(k, b, n)]))
    check('no barrier: median gap between consecutive commands 0.4-2.5 us', all(0.3e3 <= med(k, 'none') <= 2.6e3 for k in ('control', 'delay')))
    check('chained barrier: median gap ~11 us (control) / ~22.5 us (delay kernel)', 10e3 <= med('control', 'chain') <= 12e3 and 21e3 <= med('delay', 'chain') <= 24.5e3)
    ctl = [e-s for n in (8, 16, 32, 64) for c in cmds(runs[('control', 'none', n)]) for s, e in c]
    check('control command itself takes ~5.6 us in every configuration', 5.2e3 <= statistics.median(ctl) <= 5.8e3)
    seq = [(s, e-s) for q in ramp['runs'][0]['reps'] for s, e in q['cmd_ts']]
    t0 = seq[0][0]
    low = [t-t0 for t, du in seq if du > 390e3]
    top = [t-t0 for t, du in seq if du < 131e3]
    check('ramp: 1024 back-to-back delay commands (16 SUBMITs x 64, no barrier)', len(seq) == 1024)
    check('ramp: lowest clock (~403 us per command) for the first 6-8 ms of load, top clock (~129 us) from 14-17 ms on',
          max(low) < 8e6 and 6e6 < max(low) and 14e6 < min(top) < 17e6 and all(du < 131e3 for t, du in seq if t-t0 > 17e6))
    lv = sorted({round(du/1e3) for _, du in seq})
    check('ramp: discrete levels incl. 403, 222, 185, 139, 129 us (clock ratio top/bottom ~3.1)',
          {403, 222, 185, 139, 129} <= set(lv) and 3.05 < statistics.median(du for _, du in seq if du > 390e3)/statistics.median(du for _, du in seq if du < 131e3) < 3.2)
    print(f'{len(fails)} failures')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
