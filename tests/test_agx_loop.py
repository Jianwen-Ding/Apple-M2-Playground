#!/usr/bin/env python3
"""Regression for counted AGX loops (scripts/agx_loop.py).

Offline (always): the emulator accepts the loop shapes, catches a corrupted
self-branch with its step limit, bounds an inverted condition to one trip,
and large trip counts differ from emulated copies only in the K immediate.

Hardware (--hardware): three small loops through the direct DRM path with
whole-buffer oracles (<1 ms of shader time in total).

    python3 -B tests/test_agx_loop.py [--hardware]
"""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'scripts'))
import agx_loop  # noqa: E402


class EmulatorGate(unittest.TestCase):
    def test_shapes(self):
        for trips, steps, kind, active, chains in [(1, 0, 'iadd8', 32, 1), (3, 2, 'iadd8', 17, 1),
                                                   (9, 8, 'fadd4', 20, 2), (7, 8, 'iadd8', 32, 4)]:
            ok, _, _, r = agx_loop.check(trips, steps, kind, active, chains_n=chains)
            self.assertTrue(ok, (trips, steps, kind, chains))
            self.assertEqual(r['counts']['jmp_exec_any'], trips)

    def test_self_branch_caught(self):
        body, _ = agx_loop.loop_body(3, 2)
        j = body.index(agx_loop.encode('pop_exec r0l, 1'))-6
        bad = body[:j]+agx_loop.encode('jmp_exec_any pc+0')+body[j+6:]
        with self.assertRaises(RuntimeError):
            agx_loop.emulate(bad, 17, max_steps=50000)

    def test_inverted_condition_bounded(self):
        body, want = agx_loop.loop_body(3, 2)
        bad = body.replace(agx_loop.encode('while_icmp r0l, ult, r3, r4, 1'), agx_loop.encode('while_icmp r0l, ugt, r3, r4, 1'))
        r = agx_loop.emulate(bad, 17)
        self.assertEqual(r['counts']['jmp_exec_any'], 1)
        self.assertNotEqual(r['r2'][0], want)

    def test_only_trip_immediate_differs(self):
        a, _ = agx_loop.loop_body(5, 8, chains_n=4)
        b, _ = agx_loop.loop_body(5_000_000, 8, chains_n=4)
        self.assertEqual(len(a), len(b))
        self.assertTrue(all(8 <= i < 12 for i, (x, y) in enumerate(zip(a, b)) if x != y))

    def test_rejects_unbounded(self):
        with self.assertRaises(ValueError):
            agx_loop.loop_body(0, 1)
        with self.assertRaises(ValueError):
            agx_loop.loop_body(4, 6, chains_n=4)


def hardware():
    out = Path(tempfile.mkdtemp(prefix='agx-loop-test-', dir='/scratch/apple-m2-playground/drm-compute'))
    failures = []
    for i, args in enumerate([['--loop-kind', 'iadd8', '--steps', '2', '--lengths', '1,3', '--count', '33'],
                              ['--loop-kind', 'fadd4', '--chains', '2', '--steps', '8', '--lengths', '100', '--count', '257'],
                              ['--loop-kind', 'iadd8', '--chains', '4', '--steps', '16', '--lengths', '50', '--count', '65']]):
        r = subprocess.run([sys.executable, '-B', str(REPO/'scripts/run_drm_compute.py'), '--kind', 'loop', '--repeats', '2',
                            '--timeout', '20', '--output', str(out/f'case{i}')]+args, capture_output=True, text=True, timeout=120)
        print(r.stdout.strip().splitlines()[-1])
        if r.returncode: failures.append(args)
    return failures


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--hardware', action='store_true')
    a, rest = p.parse_known_args()
    result = unittest.main(argv=[sys.argv[0]]+rest, exit=False).result
    bad = not result.wasSuccessful()
    if a.hardware and not bad:
        f = hardware(); bad = bool(f)
        print({'hardware_passed': not f, 'failures': f})
    sys.exit(1 if bad else 0)
