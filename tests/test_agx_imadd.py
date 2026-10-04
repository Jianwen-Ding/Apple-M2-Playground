#!/usr/bin/env python3
"""Offline rejection/invariant tests for the pinned imadd addend patcher.

Runs without GPU access. Rebuilds the pinned index control blob from the
committed hex evidence, checks the patcher's acceptance invariants, and
requires deterministic rejection of malformed, truncated, foreign or
re-patched inputs. Also checks the runner oracle distinguishes the addend
field and rejects malformed readbacks. Execute:

    python3 -B tests/test_agx_imadd.py
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
import patch_agx_imadd  # noqa: E402
import run_agx_imadd  # noqa: E402

EVIDENCE = REPO / 'novel-results/2026-10-04-imadd-addend/patch.json'
MOV_EVIDENCE = REPO / 'novel-results/2026-10-04-first-agx-instruction/patch.json'
APPLEGPU = Path('/save/workspace/AGX_Probe/applegpu')


def load_control():
    record = json.loads(EVIDENCE.read_text())
    blob = bytes.fromhex(record['input_hex'])
    assert hashlib.sha256(blob).hexdigest() == patch_agx_imadd.CONTROL_SHA256
    return blob, record


class PatcherAcceptanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.control, cls.record = load_control()
        cls.result = patch_agx_imadd.build_patch(cls.control, APPLEGPU)

    def test_control_blob_layout(self):
        b = self.control
        self.assertEqual(len(b), 2572)
        self.assertEqual(b[:16], b'MesaVkShaderBin\0')
        self.assertEqual(struct.unpack_from('<II', b, 0x8b4), (336, 0))
        zeroed = bytearray(b)
        zeroed[48:68] = bytes(20)
        self.assertEqual(b[48:68], hashlib.sha1(zeroed).digest())

    def test_patch_invariants(self):
        r = self.result
        patched, stale = r['patched'], r['stale']
        self.assertEqual(hashlib.sha256(patched).hexdigest(), self.record['patched_sha256'])
        self.assertEqual(hashlib.sha256(stale).hexdigest(), self.record['stale_sha256'])
        # Exactly one payload byte changes: 0x957, plus the wrapper SHA1 span.
        diffs = [i for i, (x, y) in enumerate(zip(self.control, patched)) if x != y]
        self.assertEqual(diffs, list(range(48, 68)) + [0x957])
        self.assertEqual((self.control[0x957], patched[0x957]), (0x00, 0x01))
        self.assertEqual(len(patched), len(self.control))
        # Instruction-level single bit: instruction-relative bit 40.
        old = int.from_bytes(self.control[0x952:0x95a], 'little')
        new = int.from_bytes(patched[0x952:0x95a], 'little')
        self.assertEqual(old ^ new, 1 << 40)
        # Patched blob carries a valid refreshed wrapper digest; stale does not.
        self.assertEqual(patched[48:68], patch_agx_imadd.integrity(patched))
        self.assertEqual(stale[48:68], self.control[48:68])
        self.assertNotEqual(stale[48:68], patch_agx_imadd.integrity(stale))

    def test_decode_fields_preserved_except_addend(self):
        before = self.record['before_fields']
        after = self.record['after_fields']
        self.assertEqual({k: v for k, v in after.items() if k != 'C'},
                         {k: v for k, v in before.items() if k != 'C'})
        self.assertEqual((before['C'], after['C']), (0, 1))

    def test_model_pins_match_vendor_tree(self):
        self.assertEqual(hashlib.sha256((APPLEGPU / 'applegpu.py').read_bytes()).hexdigest(),
                         patch_agx_imadd.MODEL_SHA256)
        self.assertEqual(hashlib.sha256((APPLEGPU / 'disassemble.py').read_bytes()).hexdigest(),
                         patch_agx_imadd.DISASM_SHA256)


class PatcherRejectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.control, _ = load_control()

    def assertRejected(self, blob):
        with self.assertRaises(ValueError, msg=f'len={len(blob)}'):
            patch_agx_imadd.build_patch(blob, APPLEGPU)

    def test_empty(self):
        self.assertRejected(b'')

    def test_truncated(self):
        self.assertRejected(self.control[:100])
        self.assertRejected(self.control[:2571])

    def test_extended(self):
        self.assertRejected(self.control + b'\0')

    def test_metadata_byte_flip(self):
        for offset in (0, 0x48, 0x100, 0x419, 0x8b4, 0x8bc, 0x957):
            b = bytearray(self.control)
            b[offset] ^= 0x01
            self.assertRejected(bytes(b))

    def test_random_bytes(self):
        import random
        rng = random.Random(0x952)
        self.assertRejected(bytes(rng.randrange(256) for _ in range(2572)))

    def test_foreign_constant_shader_rejected(self):
        # The proven mov-immediate control blob is a valid sibling shader;
        # the imadd patcher must still refuse it (wrong pinned hash).
        mov = bytes.fromhex(json.loads(MOV_EVIDENCE.read_text())['input_hex'])
        self.assertEqual(len(mov), 2572)
        self.assertRejected(mov)

    def test_no_double_patch(self):
        patched = patch_agx_imadd.build_patch(self.control, APPLEGPU)['patched']
        self.assertRejected(patched)

    def test_stale_blob_rejected_as_input(self):
        stale = patch_agx_imadd.build_patch(self.control, APPLEGPU)['stale']
        self.assertRejected(stale)

    def test_non_bytes_input(self):
        with self.assertRaises(TypeError):
            patch_agx_imadd.build_patch('9e09820659000000', APPLEGPU)

    def test_existing_output_dir_refused(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'exists'
            out.mkdir()
            src = Path(d) / 'index.bin'
            src.write_bytes(self.control)
            argv = ['patch_agx_imadd.py', str(src), '--output', str(out)]
            with mock.patch.object(sys, 'argv', argv):
                with self.assertRaises(FileExistsError):
                    patch_agx_imadd.main()


class OracleTest(unittest.TestCase):
    def buffer(self, count, addend, control=False):
        rounded = (count + 31) // 32 * 32
        words = [0xcdcdcdcd] * (8 + rounded + 8) + [0xa5a50000 + j for j in range(16)]
        if not control:
            for i in range(count):
                words[8 + i] = (((i * 0x9e3779b9) + addend) & 0xffffffff) ^ 0x12345678
        return struct.pack('<' + 'I' * len(words), *words)

    def test_accepts_correct_vectors(self):
        for count in (1, 32, 33, 257):
            for addend in (0, 1):
                self.assertTrue(run_agx_imadd.oracle(self.buffer(count, addend), count, addend)['passed'])
            self.assertTrue(run_agx_imadd.oracle(self.buffer(count, 0, control=True), count, 0, control=True)['passed'])

    def test_distinguishes_addend(self):
        for count in (1, 33, 257):
            self.assertFalse(run_agx_imadd.oracle(self.buffer(count, 0), count, 1)['passed'])
            self.assertFalse(run_agx_imadd.oracle(self.buffer(count, 1), count, 0)['passed'])

    def test_rejects_corrupt_guard_tail_payload(self):
        good = bytearray(self.buffer(33, 1))
        for word in (0, 8 + 40, 8 + 64 + 7, 8 + 64 + 8, 8 + 64 + 8 + 15, 8):
            bad = bytearray(good)
            bad[word * 4] ^= 0x01
            self.assertFalse(run_agx_imadd.oracle(bytes(bad), 33, 1)['passed'], msg=f'word {word}')

    def test_rejects_malformed_lengths(self):
        good = self.buffer(33, 1)
        self.assertFalse(run_agx_imadd.oracle(good[:-1], 33, 1)['passed'])  # not uint32-aligned
        self.assertFalse(run_agx_imadd.oracle(good[:-4], 33, 1)['passed'])  # short one word
        self.assertFalse(run_agx_imadd.oracle(good + b'\0\0\0\0', 33, 1)['passed'])
        self.assertFalse(run_agx_imadd.oracle(b'', 33, 1)['passed'])

    def test_rejects_wrong_count(self):
        self.assertFalse(run_agx_imadd.oracle(self.buffer(33, 1), 32, 1)['passed'])
        self.assertFalse(run_agx_imadd.oracle(self.buffer(32, 1), 33, 1)['passed'])

    def test_control_rejects_dispatched_buffer(self):
        self.assertFalse(run_agx_imadd.oracle(self.buffer(33, 0), 33, 0, control=True)['passed'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
