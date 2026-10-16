"""Offline check of the submission-latency evidence (results/2026-10-16-submit-latency, simulator task safe-04 step 3)."""
import gzip, hashlib, json, pathlib, statistics, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
R = ROOT/'results/2026-10-16-submit-latency'
SLOW = 250_000  # ns: submit -> firmware start above this is a GPU wake-up


def main():
    fails = []

    def check(name, ok):
        print(('ok   ' if ok else 'FAIL ')+name)
        if not ok: fails.append(name)

    for line in (R/'sources.sha256').read_text().splitlines():
        h, f = line.split()
        check(f'{f} matches the recorded hash', hashlib.sha256((ROOT/f).read_bytes()).hexdigest() == h)
    coarse, fine, fg = (json.loads((R/n).read_text()) for n in ('idle-coarse.json', 'idle-fine.json', 'busy-fg.json'))
    bgk = json.loads((R/'busy-bg-kernel.json').read_text())
    for name, d in (('idle-coarse', coarse), ('idle-fine', fine), ('busy-fg', fg)):
        check(f'{name}: control kernel ends with stop, simulator oracle passed, every gap completed with the oracle',
              d['code_hex'].endswith('8800') and d['simulator']['oracle_ok'] and all(g['oracle_ok'] and g['returncode'] == 0 for g in d['gaps']))
        for g in d['gaps']:
            for q in g['reps']:
                ok = (q['submit_to_start'] == q['fw_ts'][0]-q['drm_time'][0] and q['end_to_wake'] == q['drm_time'][1]-q['fw_ts'][1]
                      and q['wait'] == 0)
                if not ok: check(f'{name}: derived fields recomputed', False)
    check('background kernel ends with stop and passed the simulator oracle', bgk['code_hex'].endswith('8800') and bgk['simulator']['oracle_ok'])
    s2s = lambda g: [q['submit_to_start'] for q in g['reps'][1:]]
    slow = lambda g: sum(x > SLOW for x in s2s(g))
    by = {g['gap_us']: g for g in coarse['gaps']}
    check('idle GPU, gap >= 30 ms: every submission pays a wake-up (submit -> start > 250 us)',
          all(slow(by[k]) == len(s2s(by[k])) for k in (30000, 100000)))
    check('idle GPU, gap >= 1 ms: at least 13 of 15 submissions pay a wake-up', all(slow(by[k]) >= 13 for k in (1000, 3000, 10000)))
    check('wake-up submissions start 0.37-0.75 ms after SUBMIT',
          all(SLOW < x < 750_000 for d in (coarse, fine) for g in d['gaps'] for x in s2s(g) if x > SLOW))
    warm = [x for d in (coarse, fine) for g in d['gaps'] for x in s2s(g) if x <= SLOW]
    check('warm submissions start 40-140 us after SUBMIT (one intermediate 217 us of 115)',
          min(warm) >= 40_000 and sum(x > 140_000 for x in warm) <= 1)
    check('idle GPU, gap <= 0.9 ms: a mix of warm and wake-up submissions (alternating at gap 0)',
          all(0 < slow(g) < len(s2s(g)) for g in coarse['gaps'][:2]+fine['gaps']))
    busy = [tuple(json.loads(l)['fw_ts']) for l in gzip.open(R/'busy-bg.jsonl.gz', 'rt')]
    check('background: 40 processes x 64 submissions completed', len(busy) == 40*64)
    near = lambda t: any(s <= t <= e+50_000 for s, e in busy)
    during = [q['submit_to_start'] for g in fg['gaps'] for q in g['reps'][1:] if near(q['fw_ts'][0])]
    check('GPU kept busy by another process: >= 75 submissions, none slower than 140 us, at gaps 0 / 1 / 3 ms',
          len(during) >= 75 and max(during) <= 140_000)
    fw_idle = statistics.median(q['fw_ts'][1]-q['fw_ts'][0] for g in coarse['gaps'] for q in g['reps'][1:])
    fw_busy = statistics.median(q['fw_ts'][1]-q['fw_ts'][0] for g in fg['gaps'] for q in g['reps'][1:])
    check('control dispatch firmware time: ~6-7 us from idle, ~2.8 us with the GPU warm', 5_500 <= fw_idle <= 7_100 and 2_500 <= fw_busy <= 3_200)
    print(f'{len(fails)} failures')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
