"""Offline check: 0x18 waits for nothing new (results/2026-10-16-fixed18-waits, simulator task safe-08 step 3).

The keeper run (GPU clock held at its top state by a background 64-lane delay stream) gives stable references; the
two runs without the keeper show why it is needed (references jump between clock states)."""
import collections, gzip, hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
R = ROOT/'results/2026-10-16-fixed18-waits'


def extra(d):
    T, res, out = d['trips'], d['results'], collections.defaultdict(list)
    for i, r in enumerate(res):
        if r['name'].endswith('-ref'): continue
        _, mem, cand = r['name'].split('-')
        ref = min(min(res[j]['fw_ns']) for j in (i-1, i+1) if 0 <= j < len(res) and res[j]['name'] == f'memwait-{mem}-ref')
        out[(mem, cand)].append((min(r['fw_ns'])-ref)/T)
    return out


def main():
    fails = []

    def check(name, ok):
        print(('ok   ' if ok else 'FAIL ')+name)
        if not ok: fails.append(name)

    for line in (R/'sources.sha256').read_text().splitlines():
        h, f = line.split()
        check(f'{f} matches the recorded hash', hashlib.sha256((ROOT/f).read_bytes()).hexdigest() == h)
    k = json.loads((R/'keeper-kernel.json').read_text())
    check('keeper kernel ends with stop and passed the simulator oracle', k['code_hex'].endswith('8800') and k['simulator']['oracle_ok'])
    d = json.load(gzip.open(R/'keeper-run.json.gz', 'rt'))
    check('keeper run: 40 jobs complete, no fault, every job stored the suffix in all 32 lanes',
          d['complete'] and len(d['results']) == 40 and not any(r['fault'] for r in d['results']) and all(r['suffix_lanes'] == 32 for r in d['results']))
    refs = collections.defaultdict(list)
    for r in d['results']:
        if r['name'].endswith('-ref'): refs[r['name']].append(min(r['fw_ns'])/d['trips'])
    check('keeper run: each reference stable within 1 ns per trip across its 6 placements', all(max(v)-min(v) < 1.0 for v in refs.values()))
    e = extra(d)
    check('0x18 adds 4.2-5.2 ns per use after an atomic with return, f533, f59d and store + f533 (both trials)',
          all(4.2 <= x <= 5.2 for m in ('atomic_ret', 'f533', 'f59d', 'store_f533') for x in e[(m, '18')]))
    check('wait 0 after an atomic with return costs ~67 ns (it waits for the returned value); 0x18 does not',
          all(60 <= x <= 75 for x in e[('atomic_ret', 'wait')]) and all(x < 6 for x in e[('atomic_ret', '18')]))
    check('wait 0 after f533 / f59d / store+f533 costs < 4 ns (nothing to wait for)', all(x < 4 for m in ('f533', 'f59d', 'store_f533') for x in e[(m, 'wait')]))
    noisy = [json.load(gzip.open(f, 'rt')) for f in sorted(R.glob('no-keeper-run*.json.gz'))]
    spread = []
    for n in noisy:
        rr = collections.defaultdict(list)
        for r in n['results']:
            if r['name'].endswith('-ref'): rr[r['name']].append(min(r['fw_ns'])/n['trips'])
        spread += [max(v)-min(v) for v in rr.values()]
    check('without the keeper the reference minimum jumps between clock states (> 30 ns per trip for some reference)',
          len(noisy) == 2 and max(spread) > 30)
    print(f'{len(fails)} failures')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
