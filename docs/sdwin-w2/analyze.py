import argparse,collections,json
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('--fixtures',type=Path,required=True)
parser.add_argument('--out',type=Path,required=True)
args=parser.parse_args()
root=args.fixtures
rows=[]
for host in ('windows-installed','mac'):
    for path in sorted((root/host/'presets').glob('*')):
        if path.name.startswith('.active'): continue
        data=json.loads(path.read_text(encoding='utf-8-sig'))
        sections=data.get('sections')
        for section,part in (sections.items() if sections else [('flat',data)]):
            mappings={**data.get('shared',{}).get('mappings',{}),**part['mappings']}
            rows.append(dict(host=host,file=path.name,shape='sectioned' if sections else 'flat',sections=sorted(sections) if sections else [],section=section,keys=len(mappings),types=dict(sorted(collections.Counter(m['type'] for m in mappings.values()).items()))))
comparisons=[]
for name in ('EDM Show','PTZ'):
    win=json.loads((root/'windows-installed/presets'/f'{name}.json').read_text(encoding='utf-8-sig'))
    mac=json.loads((root/'mac/presets'/f'{name}.json').read_text(encoding='utf-8-sig'))
    bak=json.loads((root/'mac/presets'/f'{name}.json.v049.bak').read_text(encoding='utf-8-sig'))
    for target,doc in [('mac-backup',bak),('mac-windows-section',mac['sections']['windows'])]:
        wm,dm=win['mappings'],doc['mappings']
        differences={key:dict(windows=wm.get(key),mac=dm.get(key)) for key in sorted(wm.keys()|dm.keys()) if wm.get(key)!=dm.get(key)}
        comparisons.append(dict(preset=name,target=target,sorted_json_equal=json.dumps(win,sort_keys=True)==json.dumps(doc,sort_keys=True),differing_mapping_keys=list(differences),mapping_differences=differences,non_mapping_differences=[k for k in sorted(win.keys()|doc.keys()) if k!='mappings' and win.get(k)!=doc.get(k)]))
result=dict(rows=rows,comparisons=comparisons)
args.out.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
