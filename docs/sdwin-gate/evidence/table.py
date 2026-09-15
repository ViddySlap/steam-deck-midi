import json,gzip,sys,os,glob,hashlib
d=sys.argv[1]; label=sys.argv[2]
rows=[]
for p in sorted(glob.glob(d+'/*.json')+glob.glob(d+'/*.json.gz')):
    r=json.loads(gzip.open(p).read() if p.endswith('.gz') else open(p,'rb').read())
    name=os.path.basename(p).split('.json')[0]
    for arm,c in r['comparisons'].items():
        t=c['totals']
        # independent recomputation of identity from raw records
        recs={a:[(x['step'],tuple(x['bytes'])) for x in r['arms'][a]['records'] if x['record']=='midi'] for a in ('A',arm)}
        raw_equal = recs['A']==recs[arm] and len(recs['A'])>0
        candhash=hashlib.sha256(repr(recs[arm]).encode()).hexdigest()[:12]
        pac=r['pacing'][arm]
        rows.append(dict(name=name,arm=arm,steps=t['steps'],exercised=t['mappings_exercised'],total=t['mappings'],mA=t['messages_A'],mB=t['messages_B'],identical=c['identical'],raw_equal=raw_equal,unex=c['unexercised_mappings'],diff=c['different_mappings'],passed=r['passed'],error=r.get('error'),candidate=r['arms'][arm]['commit'][:7],A=r['arms']['A']['commit'][:7],pkt=r['packet_stream_sha256'][:12],sent=r.get('sent_packet_stream_sha256','')[:12],candhash=candhash,
          p60=(pac.get('axis-60hz',{}).get('min_ns'),None,None) if 'min_ns' not in pac.get('axis-60hz',{}) else (pac['axis-60hz']['min_ns'],pac['axis-60hz']['median_ns'],pac['axis-60hz']['no_overspeed']),p10=(pac['axis-10hz']['min_ns'],pac['axis-10hz']['median_ns'],pac['axis-10hz']['no_overspeed']),
          gone=all(a['cleanup']['pid_gone'] for a in r['arms'].values()),clock=r.get('timestamp_clock',{}).get('implementation'),wall=r.get('replay_wall_seconds')))
for x in rows: print(label, json.dumps(x))
