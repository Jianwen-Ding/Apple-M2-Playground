#!/usr/bin/env python3
"""CPU-only checks of repetition validation and exclusive timing ownership."""
import fcntl
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import probe_integer_chain_train as B


class TrainChecks(unittest.TestCase):
    def test_lock_prevents_a_second_submission(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'gpu.lock'
            with patch.object(B,'GPU_LOCK',path),patch.object(B,'_hardware',return_value='ok') as submit:
                with path.open('a') as lock:
                    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    with self.assertRaisesRegex(RuntimeError,'no submission'):B.hardware({},0)
                    submit.assert_not_called()
                self.assertEqual(B.hardware({},0),'ok');submit.assert_called_once()

    def test_every_repetition_and_completion_is_required(self):
        for defect in ('none','missing','index','wait','timestamp','completion','partial'):
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as folder:
                samples=[dict(rep=i,wait=0,errno=0,fw_ts=[100+10*i,105+10*i]) for i in range(4)]
                completion=dict(completed=True,count=32,words=64,repeats=4)
                if defect=='missing':samples.pop()
                if defect=='index':samples[2]['rep']=1
                if defect=='wait':samples[2]['errno']=1
                if defect=='timestamp':samples[2]['fw_ts']=[125,125]
                if defect=='completion':completion['repeats']=3
                runner=SimpleNamespace(out=Path(folder),exe=Path('/unused'))
                p=dict(code=b'\x88\x00',table=[0]*16,n=32,wg=32,regs=64)
                def fake_run(argv,env):
                    directory=runner.out/'train'
                    (directory/'out.bin').write_bytes(bytes(4)+(b'x' if defect=='partial' else b''))
                    (directory/'table-out.bin').write_bytes(bytes(4))
                    return dict(returncode=0,stdout='\n'.join(json.dumps(x) for x in samples+[completion]),stderr='')
                with patch.object(B.H,'run_bounded',side_effect=fake_run),patch.object(B.P.gpu_safety,'used',return_value=[]),patch.object(B.P.gpu_safety,'record') as fault:
                    result=B.train(runner,p,4)
                    self.assertEqual(result['ok'],defect=='none')
                    self.assertEqual(fault.call_count,defect!='none')


if __name__=='__main__':unittest.main()
