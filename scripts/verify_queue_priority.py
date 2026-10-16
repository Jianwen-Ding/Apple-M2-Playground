"""Offline check of the queue-priority evidence (results/2026-10-16-queue-priority, simulator task safe-04 step 1)."""
import gzip, hashlib, json, pathlib, statistics, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
R = ROOT/'results/2026-10-16-queue-priority'


def main():
    fails = []

    def check(name, ok):
        print(('ok   ' if ok else 'FAIL ')+name)
        if not ok: fails.append(name)

    for line in (R/'sources.sha256').read_text().splitlines():
        h, f = line.split()
        check(f'{f} matches the recorded hash', hashlib.sha256((ROOT/f).read_bytes()).hexdigest() == h)
    runs = {f.name[:-8]: json.load(gzip.open(f, 'rt')) for f in sorted(R.glob('*.json.gz'))}
    check('three load shapes recorded', sorted(runs) == ['a1048576-d20000-wg128', 'a1048576-d20000-wg32', 'a4194304-d4000-wg32'])
    for name, d in runs.items():
        check(f'{name}: both kernels end with stop and passed the simulator oracle',
              all(k['code_hex'].endswith('8800') and k['simulator']['oracle_ok'] for k in d['kernels'].values()))
        check(f'{name}: B priority 1 (MEDIUM) and 0 (LOW) against A at 0; every readback exact; every wait returned',
              [r['b_prio'] for r in d['runs']] == [1, 0] and all(r['ok'] == {'a': True, 'b': True} for r in d['runs'])
              and all(q['wait'] == 0 for r in d['runs'] for q in r['a']+r['b']))
        for r in d['runs']:
            busy = [tuple(q['fw_ts']) for q in r['a']]
            for q in r['b']:
                if q['a_running'] != any(s <= q['drm_time'][0] <= e for s, e in busy): check(f'{name}: a_running recomputed', False)
    inside = lambda name, bp: [q for r in runs[name]['runs'] if r['b_prio'] == bp for q in r['b'] if q['a_running']]
    for name in runs:
        for bp in (1, 0):
            w = [q['fw_ts'][0]-q['drm_time'][0] for q in inside(name, bp)]
            check(f'{name} prio {bp}: >= 40 B submissions while A runs; B command starts 50-310 us after SUBMIT (median <= 90 us)',
                  len(w) >= 40 and max(w) <= 310e3 and min(w) >= 30e3 and statistics.median(w) <= 90e3)
    fw = lambda name, bp: statistics.median(q['fw_ts'][1]-q['fw_ts'][0] for q in inside(name, bp))
    check('32-lane A workgroups (cores not full): B runs in 6-11 us', all(5e3 <= fw(n, bp) <= 11e3 for n in ('a4194304-d4000-wg32', 'a1048576-d20000-wg32') for bp in (1, 0)))
    check('128-lane A workgroups (all 96 slots full): B takes 0.25-0.32 ms (waits for a free slot)', all(250e3 <= fw('a1048576-d20000-wg128', bp) <= 320e3 for bp in (1, 0)))
    check('MEDIUM vs LOW priority: B timing within 15% (no preemption advantage)',
          abs(fw('a1048576-d20000-wg128', 1)-fw('a1048576-d20000-wg128', 0)) <= 0.15*fw('a1048576-d20000-wg128', 0))
    print(f'{len(fails)} failures')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
