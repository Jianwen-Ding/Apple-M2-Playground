#!/usr/bin/env python3
"""CPU-only corruption checks for exact arithmetic and placement properties."""
import copy
import unittest
import probe_integer_core_distribution as C


class CorePlaneChecks(unittest.TestCase):
    def test_missing_readback_stops_through_the_recorded_check_path(self):
        out,table=C.literal(256,1,1024,0)
        for o,t in ((None,table),(out,None),(None,None)):
            with self.subTest(output_present=o is not None,table_present=t is not None),self.assertRaisesRegex(AssertionError,'missing complete native readback'):
                C.check(o,t,256,1,1024,128,20)

    def test_independent_workgroup_histogram(self):
        out,table=C.literal(256,1,1024,0)
        table[256:512]=[0]*128+[0x39]*128
        v=C.check(out,table,256,1,1024,128,20)
        self.assertEqual(v['workgroups_per_core'],{0:1,0x39:1})
        self.assertEqual(v['workgroups_per_cluster'],{0:1,3:1})
        self.assertEqual(v['cores_seen'],2)
        # Fewer active cores are a finding to retain, not a failed oracle.
        table[256:512]=[0]*256
        self.assertEqual(C.check(out,table,256,1,1024,128,20)['cores_seen'],1)

    def test_rejects_corruption(self):
        out,table=C.literal(256,1,1024,0)
        cases=[]
        bad=copy.deepcopy(table);bad[0]+=1;cases.append(('arithmetic',out,bad))
        bad=copy.deepcopy(table);bad[-1]=0;cases.append(('table guard',out,bad))
        bad=copy.deepcopy(out);bad[-1]=0;cases.append(('output guard',bad,table))
        bad=copy.deepcopy(table);bad[256]=0x1f;cases.append(('disabled core',out,bad))
        bad=copy.deepcopy(table);bad[256]=1;cases.append(('split workgroup',out,bad))
        cases.append(('missing plane word',out,table[:-1]))
        for label,o,t in cases:
            with self.subTest(label=label),self.assertRaises(AssertionError):C.check(o,t,256,1,1024,128,20)
        allocation=C.literal(256,1,1024,64)
        self.assertEqual(C.check(*allocation,256,1,1024,128,19),dict(allocation_tag_exact=True))
        allocation[1][256]=63
        with self.assertRaises(AssertionError):C.check(*allocation,256,1,1024,128,19)


if __name__=='__main__':unittest.main()
