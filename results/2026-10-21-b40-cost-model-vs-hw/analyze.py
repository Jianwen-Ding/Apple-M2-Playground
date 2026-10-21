import json, statistics as st, sys
lib=None; rows=[]
for l in open(sys.argv[1]):
    d=json.loads(l)
    if 'library' in d: lib=d['library']; continue
    d['lib']=lib; rows.append(d)
ok=[r for r in rows if r['pred_us'] and r['fw_us']>0]
print('launches', len(rows), 'usable', len(ok))
by={}
for r in ok: by.setdefault(r['lib'],[]).append(r)
print(f"{'lib':10} {'n':>5} {'med warm us':>11} {'med pred':>9} {'med ratio':>9} {'p10':>6} {'p90':>6} {'cold/warm':>9}")
res={}
for k,v in by.items():
    rat=sorted(r['fw_us']/r['pred_us'] for r in v)
    cw=st.median(r['first_fw_us']/r['fw_us'] for r in v if r.get('first_fw_us'))
    res[k]=dict(n=len(v), ratio_median=st.median(rat), p10=rat[len(rat)//10], p90=rat[9*len(rat)//10])
    print(f"{k:10} {len(v):5} {st.median(r['fw_us'] for r in v):11.1f} {st.median(r['pred_us'] for r in v):9.1f} {st.median(rat):9.2f} {rat[len(rat)//10]:6.2f} {rat[9*len(rat)//10]:6.2f} {cw:9.2f}")
allr=sorted(r['fw_us']/r['pred_us'] for r in ok)
print('ALL median', round(st.median(allr),3), 'p10', round(allr[len(allr)//10],2), 'p90', round(allr[9*len(allr)//10],2))
for lo,hi in ((0,10),(10,50),(50,1e9)):
    s=[r['fw_us']/r['pred_us'] for r in ok if lo<=r['fw_us']<hi]
    if s: print(f'warm {lo}-{hi} us: n={len(s)} median ratio {st.median(s):.2f}')
print('worst (warm > 20 us):')
for r in sorted([r for r in ok if r['fw_us']>20], key=lambda r: -max(r['fw_us']/r['pred_us'], r['pred_us']/r['fw_us']))[:10]:
    print(' ', r['lib'], r['code'], r.get('--grid'), r.get('--wg'), 'warm', round(r['fw_us'],1), 'pred', round(r['pred_us'],1), 'ratio', round(r['fw_us']/r['pred_us'],2))
json.dump(res, open(sys.argv[1]+'.summary.json','w'))
