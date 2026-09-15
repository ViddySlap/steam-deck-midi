import json,sys
d=json.load(open(sys.argv[1]))
print({k:d[k] for k in ('passed','measurement_qualified','locked_rule_passed','m_bridge_rule_passed','byte_identical','rederived_m_bridge_mismatches','per_arm_stat_mismatches_vs_instrument','wall_seconds')})
for row in d['rows']:
    s=row['stats']['m_bridge_ms']; t=row['stats']['m_total_ms']; w=row['worst_stats']['m_bridge_ms']
    print(row['repeat'],row['arm'].ljust(8),'MB %.3f %.3f %.3f max %.1f'%(s['p50'],s['p95'],s['p99'],s['max']),'| MT %.3f %.2f %.2f'%(t['p50'],t['p95'],t['p99']),'| worstMB p99 %.3f'%w['p99'],'| load1',row['load1_before'],'drop',row['stream_dropped'],'ev',row['stream_data_events'],'cl',row['client_counts_minmax'],'pub_drop',row['publisher_dropped'],'att',row['attempts'])
for k in ('rules','worst_rules'):
    print(k, json.dumps({m:{x:d[k][m][x] for x in ('noise_floor_ms','open_delta_ms','within')} for m in ('m_bridge_ms','m_total_ms')}))
print('pooled MB', json.dumps(d['pooled']['m_bridge_ms']))
print('worst pooled MB', json.dumps(d['worst_pooled']['m_bridge_ms']))
print('per_repeat', [(r['repeat'], ''.join('Y' if r['within'][s] else 'N' for s in ('p50','p95','p99'))) for r in d['per_repeat_m_bridge']])
