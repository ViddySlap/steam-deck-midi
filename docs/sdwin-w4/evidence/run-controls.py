from pathlib import Path
import json,subprocess
base=['scripts/showready/win_rail.sh','run','w4','/tmp/sdwin-w4/run.ps1']
rows=[]
for label,control,expected in [('determinism-1',None,0),('determinism-2',None,0),('sensitivity','sensitivity',1),('coverage','coverage',1),('dead-seam','dead-seam',1)]:
    cmd=base+['-Label',label,'-Preset',r'mac\presets\default.json','-Candidate','v0.4.9','-Speed','50']
    if control:cmd+=['-Control',control]
    with open('/tmp/sdwin-w4/'+label+'.txt','w') as log:
        code=subprocess.call(cmd,stdout=log,stderr=subprocess.STDOUT)
    rows.append({'label':label,'command':cmd,'exit':code,'expected':expected})
    Path('/tmp/sdwin-w4/control-commands.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(label,code,flush=True)
    if code!=expected:raise SystemExit(code or 2)
    prove=['scripts/showready/win_rail.sh','run','w4','/tmp/sdwin-w4/prove-gone.ps1','-Label',label]
    with open('/tmp/sdwin-w4/'+label+'-gone.txt','w') as log:subprocess.run(prove,stdout=log,stderr=subprocess.STDOUT,check=True)
