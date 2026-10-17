#!/usr/bin/env python3
"""Host-only timeout/partial-evidence tests. Never opens a GPU device."""
import io
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import probe_control_followup as F


class WatchdogTests(unittest.TestCase):
    def check_hardware_failure(self, stuck):
        good = dict(ok=True, out=[1], table_after=[2])
        bad = dict(ok=False, returncode=None, host_timeout=True)
        if stuck:
            bad['host_process_stuck'] = True
        with tempfile.TemporaryDirectory() as tmp:
            p = dict(code=b'\x88\x00', control=b'\x88\x00', table=[0], expected=([1], [2]),
                     n=1, wg=32, regs=8, gate={}, data_dir=Path(tmp))
            with patch.object(F.P.bench, 'Runner'), patch.object(F.P.gpu_safety, 'require_budget'), \
                 patch.object(F.P, 'snapshot', return_value={'budget_used': 0}), \
                 patch.object(F.time, 'sleep'), \
                 patch.object(F, 'run_one', side_effect=[good, bad, good]) as run:
                r = F.hardware('host-only', p)
            saved = json.load(gzip.open(Path(tmp) / 'host-only.json.gz', 'rt'))
            self.assertEqual(saved, r)
            self.assertEqual(run.call_count, 2 if stuck else 3)
            self.assertEqual('halted' in r, stuck)
            if not stuck:
                self.assertTrue(r['recovery_control_passed'])

    def test_stuck_process_prevents_recovery_submission(self):
        self.check_hardware_failure(stuck=True)

    def test_recovered_failure_is_recorded_without_halting(self):
        self.check_hardware_failure(stuck=False)

    def test_completion(self):
        r = F.run_bounded([sys.executable, '-c', 'print("complete")'], {}, timeout=2)
        self.assertEqual((r['returncode'], r['stdout']), (0, 'complete\n'))
        self.assertNotIn('host_timeout', r)

    def test_real_timeout_retains_output_and_reaps_child(self):
        r = F.run_bounded([sys.executable, '-c', 'import time; print("marker", flush=True); time.sleep(30)'],
                          {}, timeout=0.5, kill_timeout=2)
        self.assertTrue(r['host_timeout'])
        self.assertNotIn('host_process_stuck', r)
        self.assertIn('marker', r['stdout'])
        self.assertIsNotNone(r['returncode'])
        self.assertIn('maps', r['process_at_timeout'])

    def test_stuck_driver_wait_is_bounded_after_kill(self):
        proc = Mock(pid=os.getpid(), stdout=io.BytesIO(), stderr=io.BytesIO())
        proc.communicate.side_effect = [subprocess.TimeoutExpired('probe', 10, output=b'before\n'),
                                       subprocess.TimeoutExpired('probe', 2, output=b'before\npartial')]
        proc.poll.return_value = None
        with patch.object(F.subprocess, 'Popen', return_value=proc):
            r = F.run_bounded(['probe'], {})
        self.assertTrue(r['host_process_stuck'])
        self.assertEqual(r['stdout'], 'before\npartial')
        self.assertEqual([c.kwargs['timeout'] for c in proc.communicate.call_args_list], [10, 2])
        proc.kill.assert_called_once()
        self.assertTrue(proc.stdout.closed and proc.stderr.closed)

    def test_partial_json_and_readback_survive_failure(self):
        def failed(argv, env):
            Path(argv[4]).write_bytes(b'\x01\x00\x00\x00\xff')
            return dict(returncode=-9, stdout='{"rep":', stderr='', host_timeout=True)
        with tempfile.TemporaryDirectory() as tmp:
            runner = SimpleNamespace(out=Path(tmp), exe=Path('/unused'))
            with patch.object(F, 'run_bounded', side_effect=failed), \
                 patch.object(F.P.gpu_safety, 'used', return_value=[]), \
                 patch.object(F.P.gpu_safety, 'record') as record:
                r = F.run_one(runner, b'\x88\x00', dict(table=[0], n=1, wg=32, regs=32), 'variant')
            self.assertFalse(r['ok'])
            self.assertEqual(r['out'], [1])
            self.assertEqual(r['out_partial_tail_hex'], 'ff')
            self.assertEqual(r['incomplete_json_lines'], ['{"rep":'])
            record.assert_called_once()


if __name__ == '__main__':
    unittest.main()
