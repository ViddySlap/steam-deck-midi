import json,sys,glob
for f in sorted(glob.glob('/tmp/sdauto-gate/win/L07-f2-*-g*.txt')):
    t=open(f).read()
    js="\n".join(l[5:] for l in t.splitlines() if l.startswith("JSON "))
    try: d=json.loads(js)
    except Exception as e: print(f,'NOJSON',e); continue
    st=[(s['method'],s['tree_exited_within_5s'],s['elapsed'],s.get('exit_codes')) for s in d['stops']]
    lines=[l for l in t.splitlines() if l.startswith(("PID ","PYTHON_PROCESSES","RECORDED","CLONE_HEAD","V049","NEEDS","FAILSAFE"))]
    print(f.split('/')[-1], d['label'], 'ctrlc_enabled',d['console']['enable_ctrl_c'], 'cpu_s',d['cpu']['tree_cpu_seconds'],'wall',d['cpu']['wall_seconds'],'%1core',d['cpu']['tree_pct_of_one_core'],'%all',d['cpu']['tree_pct_of_all_cores'],'stops',st,'final',d['final_exit_codes'],'all_gone',d['all_gone'],'rebind',d['udp_port_rebind'],'tail',d['log_tail'][-2:])
    print('   ',lines)
