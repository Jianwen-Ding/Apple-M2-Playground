"""Offline check of the queue-concurrency evidence (results/2026-10-16-queue-concurrency, simulator task safe-04 step 2)."""
import gzip, hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
R = ROOT/'results/2026-10-16-queue-concurrency'


def conc(ts):
    ev = sorted([(s, 1) for s, _ in ts]+[(e, -1) for _, e in ts])
    c = b = 0
    for _, d in ev:
        c += d; b = max(b, c)
    return b


def main():
    fails = []

    def check(name, ok):
        print(('ok   ' if ok else 'FAIL ')+name)
        if not ok: fails.append(name)

    for line in (R/'sources.sha256').read_text().splitlines():
        h, f = line.split()
        check(f'{f} matches the recorded hash', hashlib.sha256((ROOT/f).read_bytes()).hexdigest() == h)
    d = json.load(gzip.open(R/'record.json.gz', 'rt'))
    check('kernel ends with stop and passed the simulator oracle', d['kernel']['code_hex'].endswith('8800') and d['kernel']['simulator']['oracle_ok'])
    runs = {r['n']: r for r in d['runs']}
    check('N = 2, 4, 8, 16, 32 queues x 8 repeats, exact readbacks, all waits returned',
          sorted(runs) == [2, 4, 8, 16, 32] and all(r['oracle_ok'] and len(r['reps']) == 8 and all(q['wait'] == 0 for q in r['reps']) for r in runs.values()))
    check('one process: N commands run at once for N <= 4, never more than 4',
          all(conc(q['ts']) == min(n, 4) for n, r in runs.items() for q in r['reps']))
    def handoff(q):
        t = sorted(q['ts'])
        return t[4][0]-min(e for _, e in t[:4])
    check('with N = 8 the 5th command starts 0-20 us after the first running one ends (a slot is handed over)',
          all(0 <= handoff(q) <= 20e3 for q in runs[8]['reps']))
    two = d['two_process']
    reps = {k: [q for q in v if 'multi' in q] for k, v in two['runs'].items()}
    check('two processes x 4 queues, three trials, exact readbacks', two['readbacks_ok'] and len(reps) == 6 and all(len(v) == 8 for v in reps.values()))
    for t in (1, 2, 3):
        ts = [x for k in (f'p1-{t}.out', f'p2-{t}.out') for q in reps[k] for x in q['ts']]
        check(f'trial {t}: the two processes together never exceed 4 running commands', conc(ts) == 4)
    print(f'{len(fails)} failures')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
