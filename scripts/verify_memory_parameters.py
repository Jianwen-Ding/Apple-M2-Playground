"""Offline check: TLB reach and the SLC / DRAM latency curve (results/2026-10-16-memory-parameters, safe-03 steps 2-3).
All runs used the long-command clock keeper except tlb-pages / tlb-lines (first keeper; kept for reference)."""
import gzip, hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
R = ROOT/'results/2026-10-16-memory-parameters'


def curve(name):
    d = json.load(gzip.open(R/f'{name}.json.gz', 'rt'))
    out = {}
    for v in d['variants']:
        assert v['buffer_ok'] and v['simulator']['oracle_ok']
        out[v['footprint']//v['stride']] = min(s['fw_ts'][1]-s['fw_ts'][0] for s in v['samples'][1:])/v['hops']
    return d['passed'], out


def main():
    fails = []

    def check(name, ok):
        print(('ok   ' if ok else 'FAIL ')+name)
        if not ok: fails.append(name)

    for line in (R/'sources.sha256').read_text().splitlines():
        h, f = line.split()
        check(f'{f} matches the recorded hash', hashlib.sha256((ROOT/f).read_bytes()).hexdigest() == h)
    C = {}
    for n in ('tlb-pages2', 'tlb-lines2', 'tlb-pages3', 'tlb-lines3'):
        ok, C[n] = curve(n)
        check(f'{n}: every chase exact and agx_run-gated', ok)
    p = {**C['tlb-pages2'], **C['tlb-pages3']}; l = {**C['tlb-lines2'], **C['tlb-lines3']}
    check('one element per 16 KiB page costs the same as packed 64 B lines (within 25 ns) up to 16,384 pages (256 MiB)',
          all(abs(p[k]-l[k]) < 25 for k in C['tlb-pages3'] if k <= 16384) and all(abs(C['tlb-pages2'][k]-C['tlb-lines2'][k]) < 5 for k in C['tlb-pages2'] if k <= 8192))
    check('24,576 pages (384 MiB) adds > 100 ns and 32,768 pages (512 MiB) > 150 ns per hop (TLB reach exceeded)',
          p[24576]-l[24576] > 100 and C['tlb-pages2'][32768]-C['tlb-lines2'][32768] > 150)
    check('packed lines: L1 to 8 KiB (~40 ns), L2 ~93-123 ns to 256 KiB, spilling by 1-2 MiB (> 280 ns)',
          all(39 < l[k] < 42 for k in (16, 32, 64, 128)) and 90 < l[256] < 100 and l[4096] < 125 and l[16384] > 280 and l[32768] > 340)
    slc = {}
    for f in (16, 24, 32, 40, 48, 56, 64, 80, 96):
        d = json.load(gzip.open(R/f'slc-{f}.json.gz', 'rt')); v = d['variants'][0]
        assert v['buffer_ok'] and v['simulator']['oracle_ok'] and v['hops'] >= 2*(f << 20)//64
        slc[f] = sorted(s['fw_ts'][1]-s['fw_ts'][0] for s in v['samples'])[1]/v['hops']
    print({k: round(v, 1) for k, v in slc.items()})
    check('16-96 MiB full-coverage chases: latency rises only gradually (410-490 ns, < 20% over the range), no sharp SLC edge',
          all(400 < v < 490 for v in slc.values()) and slc[96]/slc[16] < 1.2 and max(slc[k+8]-slc[k] for k in (16, 24, 32, 40, 48, 56)) < 25)
    print(f'{len(fails)} failures')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
