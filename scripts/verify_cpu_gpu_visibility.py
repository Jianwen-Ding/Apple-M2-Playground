"""Offline check of CPU <-> GPU visibility (results/2026-10-16-cpu-gpu-visibility, simulator task safe-03 step 4)."""
import gzip, hashlib, json, pathlib, re, statistics, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
R = ROOT/'results/2026-10-16-cpu-gpu-visibility'


def main():
    fails = []

    def check(name, ok):
        print(('ok   ' if ok else 'FAIL ')+name)
        if not ok: fails.append(name)

    for line in (R/'sources.sha256').read_text().splitlines():
        h, f = line.split()
        check(f'{f} matches the recorded hash', hashlib.sha256((ROOT/f).read_bytes()).hexdigest() == h)
    tb = [float(m) for m in re.findall(r'diff (-?\d+)', (R/'timebase.txt').read_text())]
    br = [float(m) for m in re.findall(r'bracket_ns (\d+)', (R/'timebase.txt').read_text())]
    check('GET_TIME (firmware ns) = CNTVCT * 1e9 / 24e6 within the read bracket', all(abs(t) <= b for t, b in zip(tb, br)) and len(tb) == 8)
    d = json.load(gzip.open(R/'record.json.gz', 'rt')); N = d['n']
    check('simulator gate passed for all six variants', all(g['oracle_ok'] for g in d['simulator'].values()) and len(d['simulator']) == 6)
    by = {}
    for r in d['runs']:
        by.setdefault(r['variant'], []).append(r)
    check('6 variants x 4 trials, every readback exact, final token N', all(len(v) == 4 and all(r['ok'] and r['final_T'] == N for r in v) for v in by.values()))
    for v in ('plain', 'release', 'coherent', 'mesa_qf'):
        rs = by[v]
        check(f'{v}: the CPU sees only the final token, at the end of the command (within 5 us of the firmware end)',
              all(r['tokens_seen'] == [N] and abs(r['echo_seen'][0]*1e9/24e6 - r['fw_ts'][1]) < 5000 for r in rs))
    for v in ('coherent_release', 'coherent_mesa_qf'):
        rs = by[v]
        check(f'{v}: the CPU sees >= 90% of the tokens during the dispatch', all(len(r['tokens_seen']) >= 0.9*N for r in rs))

    def analyse(r):
        base = int(r['fw_ts'][0]*24e6/1e9)
        def full(c):
            f = (base & ~0xffffffff) | c
            if f > base+(1 << 31): f -= 1 << 32
            if f < base-(1 << 31): f += 1 << 32
            return f*1e9/24e6
        E, C = r['R'][0::2], [full(c) for c in r['R'][1::2]]
        first = {}
        for j, e in enumerate(E):
            if 1 <= e <= N and e not in first: first[e] = j
        iters = [first[k+1]-k for k in range(N) if k+1 in first and first[k+1] >= k]
        seen = {t: c*1e9/24e6 for t, c in zip(r['tokens_seen'], r['echo_seen'])}
        lag = [seen[k+1]-C[k] for k in range(N) if k+1 in seen]
        return C, iters, lag
    for r in by['coherent_release']:
        C, iters, lag = analyse(r)
        check(f"coherent_release trial {r['trial']}: clock word monotonic; echo of token k first read at iteration k+1 (median, >= 95%); CPU sees token a median 150-350 ns after C(k)",
              all(C[i] <= C[i+1] for i in range(N-1)) and statistics.median(iters) == 1 and sum(i <= 1 for i in iters) >= 0.95*len(iters)
              and 150 <= statistics.median(lag) <= 350)
    for r in by['coherent_mesa_qf']:
        C, iters, lag = analyse(r)
        check(f"coherent_mesa_qf trial {r['trial']}: echo seen in the same iteration (median 0 iterations)", statistics.median(iters) == 0)
    print(f'{len(fails)} failures')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
