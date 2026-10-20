#!/usr/bin/env python3
"""CPU-only checks for aligned cluster blocks and partial final blocks."""
import unittest
from verify_integer_geometry_cost import packets


class PacketAnalysis(unittest.TestCase):
    def fixture(self):
        # Ten workgroups: two whole four-group packets, then a two-group tail.
        wg=32;n=10*wg
        tags=[v for core in ([0]*4+[16]*4+[32]*2) for v in [core]*wg]
        return [123]*n+tags+[0xcdcdcdcd]*16,n,wg

    def test_aligned_blocks_include_the_partial_tail(self):
        table,n,wg=self.fixture();r=packets(table,n,1,wg)
        self.assertEqual(r['workgroups'],10)
        self.assertEqual(r['largest_unmixed_tested_width'],4)
        self.assertEqual(r['mixed_aligned_blocks']['4'],0)
        self.assertEqual(r['mixed_aligned_blocks']['8'],1)

    def test_mixed_packet_is_reported_instead_of_forcing_a_hypothesis(self):
        table,n,wg=self.fixture();table[n+wg:n+2*wg]=[16]*wg
        r=packets(table,n,1,wg)
        self.assertEqual(r['largest_unmixed_tested_width'],1)
        self.assertEqual(r['mixed_aligned_blocks']['4'],1)
        self.assertGreater(r['hypothesis_mixed_blocks'],0)


if __name__=='__main__':unittest.main()
