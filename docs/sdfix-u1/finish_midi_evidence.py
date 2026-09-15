"""Read raw A/B captures, recompare bytes, verify candidate identities and PID absence."""
import gzip,hashlib,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SCRATCH=Path('/tmp/sdfix-u1')
EXPECTED='a5e310456971a92af0b30b50d7cf396bccc29060'
results={}
for name in ('mac-edm','mac-edm-final'):
    path=SCRATCH/(name+'.json.gz')
    if not path.exists():path=SCRATCH/(name+'.json')
    payload=path.read_bytes();r=json.loads(gzip.decompress(payload) if path.suffix=='.gz' else payload)
    assert r['passed'] is True,(name,r.get('error'))
    assert set(r['arms'])=={'A','B1','B2'}
    raw_equal={};gone={}
    midi=lambda arm:[(row['step'],row['bytes']) for row in r['arms'][arm]['records'] if row['record']=='midi']
    baseline=midi('A');assert baseline,'empty capture'
    for arm in ('B1','B2'):
        candidate=midi(arm);assert candidate==baseline,(name,arm,'raw MIDI differs')
        raw_equal[arm]={'identical':True,'messages_A':len(baseline),'messages_B':len(candidate),'totals':r['comparisons'][arm]['totals']}
        assert not r['comparisons'][arm]['different_mappings']
        assert not r['comparisons'][arm]['unexercised_mappings']
        if name=='mac-edm-final':assert r['arms'][arm]['commit']==EXPECTED
    for arm,data in r['arms'].items():
        assert data['cleanup']['pid_gone'] is True
        try:os.kill(data['pid'],0)
        except ProcessLookupError:gone[arm]={'pid':data['pid'],'gone':True,'proof':'os.kill(pid, 0) raised ProcessLookupError'}
        else:raise AssertionError((name,arm,data['pid'],'still present'))
    summary={key:value for key,value in r.items() if key not in ('script','arms','comparisons')}
    summary.update(raw_result=str(path),raw_sha256=hashlib.sha256(payload).hexdigest(),raw_comparison=raw_equal,
                   arms={name:{key:value for key,value in data.items() if key!='records'} for name,data in r['arms'].items()},
                   comparisons={name:{key:value for key,value in data.items() if key!='steps'} for name,data in r['comparisons'].items()},
                   independent_pid_absence=gone)
    results[name]=summary
output=ROOT/'docs/sdfix-u1/evidence/midi-verdict.json'
output.write_text(json.dumps(results,indent=2,sort_keys=True)+'\n')
print(json.dumps({name:{'candidate':r['arms']['B1']['commit'],'passed':r['passed'],'raw_comparison':r['raw_comparison'],'pid_absence':r['independent_pid_absence'],'raw_sha256':r['raw_sha256']} for name,r in results.items()},indent=2))
