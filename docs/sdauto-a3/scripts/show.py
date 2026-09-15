import json, sys
d = json.load(open(sys.argv[1]))
print('booted', d['booted'], 'tree', [(t['pid'], t['image'].split('\\')[-3:]) for t in d['tree']])
c = d.get('cpu', {}); print({k: v for k, v in c.items() if k not in ('per_second_deltas', 'per_pid')})
for r in c.get('per_pid', []): print('  ', r)
print('console', d['console'])
print(json.dumps(d.get('stops'), indent=1))
for k in ('driver_signals_received', 'popen_returncode', 'final_exit_codes', 'all_gone', 'udp_port_rebind', 'log_tail'):
    print(k, d.get(k))
