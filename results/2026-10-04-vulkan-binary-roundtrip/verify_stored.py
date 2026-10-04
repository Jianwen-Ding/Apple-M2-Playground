#!/usr/bin/env python3
"""Independent evidence verification: no runner import, driver load, or GPU work."""
import hashlib
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parent
r=json.loads((ROOT/'primary/record.json').read_text())
assert r['passed'] and r['runtime_unchanged_before_after_each_case']
assert len(r['cases'])==15
for case in r['cases']:
    n=case['count']; extent=((n+31)//32)*32
    want=[0xcdcdcdcd]*(extent+16)+[0xa5a50000+j for j in range(16)]
    if case['mode']!='control':
        for j in range(n):
            value=case['expected_constant']
            if case['name'].startswith('index-'): value ^= (j*2654435769) % 4294967296
            want[j+8]=value
    assert case['actual']==want and case['expected']==want and case['passed']
    raw=b''.join(x.to_bytes(4,'little') for x in case['actual'])
    assert hashlib.sha256(raw).hexdigest()==case['readback_sha256']
    assert case['api_events'][-1]['completed']
    assert all(e['result']==0 for e in case['api_events'] if 'api' in e)
    identity=next(e['identity'] for e in case['api_events'] if 'identity' in e)
    assert identity['name']=='Apple M2 Max (G14C B1)' and identity['info']=='Mesa 25.3.6'
    assert identity['uuid']=='2313bd7c3909b8ad0f31883eab5c412e' and identity['binary_version']==0
p=r['instruction_patch']; before=bytes.fromhex(p['input_hex']); after=bytes.fromhex(p['patched_hex'])
assert hashlib.sha256(before).hexdigest()==p['input_sha256']
assert hashlib.sha256(after).hexdigest()==p['patched_sha256']
assert len(before)==len(after)==2572
for b in (before,after):
    zeroed=bytearray(b);zeroed[48:68]=bytes(20)
    assert hashlib.sha1(zeroed).digest()==b[48:68]
    assert struct.unpack_from('<Q',b,40)[0]==len(b)
changes=[i for i,(x,y) in enumerate(zip(before,after)) if x!=y]
assert changes==p['changed_byte_offsets']
assert [i for i in changes if not 48<=i<68]==[0x954]
assert before[0x952:0x958].hex()=='620978563412'
assert after[0x952:0x958].hex()=='620979563412'
assert int.from_bytes(before[0x952:0x958],'little') ^ int.from_bytes(after[0x952:0x958],'little') == 1<<16
assert r['stale_integrity_control']['passed']
assert next(e['result'] for e in r['stale_integrity_control']['api_events'] if e.get('api')=='vkCreateShadersEXT')==1000482000
assert not any(e.get('api')=='vkQueueSubmit' for e in r['stale_integrity_control']['api_events'])
for kind in ('constant','index'):
    encoding=json.loads((ROOT/('primary/'+kind+'-encoding.json')).read_text())
    words=list(encoding['header'])
    for instr in encoding['instructions']:
        words += [((len(instr['operands'])+1)<<16)|instr['opcode'], *instr['operands']]
    raw=struct.pack('<'+'I'*len(words),*words)
    assert hashlib.sha256(raw).hexdigest()==r[kind+'_validation']['sha256']
    assert r[kind+'_validation']['result']==0
source_changes={}
for source in (ROOT/'primary/sources').iterdir():
    canonical=ROOT.parents[1]/('tests' if source.suffix=='.c' else 'scripts')/source.name
    if canonical.read_bytes()!=source.read_bytes():
        # The sole reviewed change suppresses reference-tree bytecode writes.
        guard='    sys.dont_write_bytecode = True  # Reference imports must not write into vendor trees.\n'
        assert source.name=='patch_agx_shader.py'
        assert canonical.read_text().replace(guard,'',1)==source.read_text()
        check=json.loads((ROOT/'integration-review/offline-patcher-check.json').read_text())
        assert check['passed'] and check['patched_and_stale_bytes_match_hardware_suite']
        assert hashlib.sha256(canonical.read_bytes()).hexdigest()==check['current_patcher_sha256']
        source_changes[source.name]='Reference bytecode writes disabled; offline patch bytes unchanged'
print(json.dumps({'passed':True,'successful_readbacks':15,'dispatch_readbacks':14,'patch_instruction_bit':16,
                  'stale_integrity_rejected_before_submit':True,'source_snapshots_match':not source_changes,'reviewed_source_changes':source_changes}))
