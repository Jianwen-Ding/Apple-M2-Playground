"""Independent stored instruction/readback checks; no runner imports or GPU calls."""
from pathlib import Path
import hashlib
import json
import struct

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[1]
for root in [ROOT,REPO/'novel-results/2026-10-04-first-agx-instruction']:
    m=json.loads((root/'manifest-sha256.json').read_text())
    assert set(m)=={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.name!='manifest-sha256.json'}
    assert all((root/n).is_file() and hashlib.sha256((root/n).read_bytes()).hexdigest()==h for n,h in m.items())
r=json.loads((ROOT/'primary/record.json').read_text())
assert r['passed'] and len(r['cases'])==15
word_count=0
for c in r['cases']:
    n=c['count'];extent=((n+31)//32)*32
    want=[0xcdcdcdcd]*(extent+16)+list(range(0xa5a50000,0xa5a50010))
    constant=0x12345679 if c['name'].startswith('mov-patched-') else 0x12345678
    if c['mode']!='control':
        for i in range(n):
            want[8+i]=((i*2654435769)%2**32)^constant if c['name'].startswith('index-') else constant
    assert c['actual']==want and c['expected']==want and c['expected_constant']==constant,c['name']
    raw=struct.pack('<'+str(len(want))+'I',*want)
    assert hashlib.sha256(raw).hexdigest()==c['readback_sha256']
    events=[json.loads(line) for line in (ROOT/'primary'/c['name']/'stdout.txt').read_text().splitlines()]
    assert events==c['api_events']
    assert events[-1]['dispatch']==(c['mode']!='control') and events[-1]['count']==n
    command=json.loads((ROOT/'primary'/c['name']/'command.json').read_text())
    assert command['returncode']==0 and not command.get('timed_out',False)
    word_count+=len(want)
p=r['instruction_patch']
before=bytes.fromhex(p['input_hex']);after=bytes.fromhex(p['patched_hex']);stale=bytes.fromhex(p['stale_hex'])
assert len(before)==len(after)==len(stale)==2572
assert hashlib.sha256(before).hexdigest()=='b79bd25941bdea1a0095b219fe0333ac5c18822225de811c9308a38702e9e098'
assert hashlib.sha256(after).hexdigest()=='e1ea5f9ca2822860c244627acd8406faf7a1b87ffe175f88234e67646b7698bb'
for blob in [before,after]:
    zeroed=bytearray(blob);zeroed[48:68]=bytes(20)
    assert hashlib.sha1(zeroed).digest()==blob[48:68]
assert (before[0x954]^after[0x954])==1
assert [i for i in range(len(before)) if before[i]!=after[i] and not 48<=i<68]==[0x954]
assert int.from_bytes(before[0x952:0x958],'little') ^ int.from_bytes(after[0x952:0x958],'little') == 1<<16
assert stale[48:68]==before[48:68] and stale[:48]==after[:48] and stale[68:]==after[68:]
assert p['before_fields']=={'Dt':2,'D':4,'imm32':0x12345678,'kill':0}
assert p['after_fields']=={'Dt':2,'D':4,'imm32':0x12345679,'kill':0}
finding=REPO/'novel-results/2026-10-04-first-agx-instruction'
assert json.loads((finding/'patch.json').read_text())==p
text_before=(finding/'before-main.txt').read_text();text_after=(finding/'after-main.txt').read_text()
assert text_after==text_before.replace('620978563412','620979563412').replace('305419896','305419897')
assert (finding/'before-preamble.txt').read_bytes()==(finding/'after-preamble.txt').read_bytes()
negative=[json.loads(line) for line in (ROOT/'primary/stale-integrity/stdout.txt').read_text().splitlines()]
assert [e['result'] for e in negative if e.get('api')=='vkCreateShadersEXT']==[1000482000]
assert not any(e.get('api')=='vkQueueSubmit' for e in negative)
assert json.loads((ROOT/'primary/stale-integrity/command.json').read_text())['returncode']==1
print(json.dumps({'passed':True,'scope':'Stored evidence only; no GPU rerun',
                  'successful_readbacks':15,'output_words_verified':word_count,
                  'patched_counts':[33,257],'changed_instruction_bits':[16],
                  'destination_and_kill_preserved':True,'preamble_and_non_target_bytes_preserved':True,
                  'stale_sha1_rejected_before_submission':True}))
