#!/usr/bin/env python3
"""sdpick K1: classify a laptop inventory per MASTER 04:13. Read-only; prints tables.
RECORDED LANE PID: pid (or an ancestor) appears in EG's owned-tree/python-pids records on the laptop or in the
committed L22 A/B pid list, AND (when the record carries a start time) the live CreationDate matches it to the
second, or (pid-only record) the live process was created inside EG's laptop window 2026-09-15T00:00-04:10 local.
LANE-STARTED BY PATH, UNRECORDED: exe, or command line with at most one leading quote stripped, starts
case-insensitively with the exact clone root + '\\' or sdwin root + '\\'.
NOT LANE: everything else; ALWAYS session != 0, orphan-checkout prefix, 'C:\\Program Files\\' prefix."""
import json, re, sys, datetime
inv = json.load(open(sys.argv[1], encoding='utf-8-sig'))
CLONE = 'c:\\users\\ben\\documents\\project-workspaces\\steam-deck-midi-rc\\'
WORK = 'c:\\users\\ben\\appdata\\local\\temp\\sdwin\\'
ORPHAN = 'c:\\users\\ben\\documents\\project-workspaces\\steam-deck-midi\\'
PF = 'c:\\program files\\'
recorded = {}  # pid -> set of start strings ('' = pid-only)
for path, lines in (inv.get('records') or {}).items():
    if isinstance(lines, str): lines = [lines]
    for ln in lines or []:
        m = re.match(r'^(\d+) (\d+) \S+ parent=(\d+) start=(\S+ \S+)', ln)
        if m:
            recorded.setdefault(int(m.group(1)), set()).add('')
            st = datetime.datetime.strptime(m.group(4), '%m/%d/%Y %H:%M:%S').strftime('%Y-%m-%dT%H:%M:%S')
            recorded.setdefault(int(m.group(2)), set()).add(st)
        elif re.match(r'^\d+$', ln.strip()):
            recorded.setdefault(int(ln.strip()), set()).add('')
for pid in [295132,302692,284024,291004,291632,293848,286780,303836,302944,302144,301128,293912,302588,272892,301264,288164,303516,301700]:
    recorded.setdefault(pid, set()).add('')  # docs/sdlive-gate/evidence/laptop/L22-ab.txt
byid = {p['pid']: p for p in inv['all']}
def rec_match(p):
    st = set(recorded.get(p['pid'], ()))
    if not st: return False
    c = (p.get('created') or '')[:19]
    if c in st: return True
    if '' in st and '2026-09-15T00:00:00' <= c <= '2026-09-15T04:10:00': return True
    return False
def chain(p):
    out, seen, cur = [], set(), p
    while cur and cur['pid'] not in seen and cur['pid'] != 0:
        seen.add(cur['pid']); out.append(cur)
        par = byid.get(cur['ppid'])
        # a parent created after its child is a reused pid, not the real parent
        if par and (par.get('created') or '') > (cur.get('created') or ''): break
        cur = par
    return out
def lower(s): return (s or '').lower()
rows = []
for p in inv['processes']:
    exe, cmd = lower(p['exe']), lower(p['cmd']).lstrip()
    cmd1 = cmd[1:] if cmd.startswith('"') else cmd
    tests = [exe, cmd1]
    if p['session'] != 0 or any(t.startswith(ORPHAN) or t.startswith(PF) for t in tests if t):
        cls = 'NOT LANE'
    elif any(rec_match(x) for x in chain(p)):
        cls = 'RECORDED LANE PID'
    elif any(t.startswith(CLONE) or t.startswith(WORK) for t in tests if t):
        cls = 'LANE-STARTED BY PATH, UNRECORDED'
    else:
        cls = 'NOT LANE'
    if p['pid'] == inv.get('self_pid'): cls += ' (this inventory itself)'
    rows.append((p, cls))
print(f"INVENTORY {inv['label']} taken {inv['taken']} self_pid {inv.get('self_pid')} record_files {len(inv.get('records') or {})} recorded_pids {len(recorded)}")
print('| pid | name | session | ppid | created | class | exe | command line (first 160) |')
print('| --- | --- | --- | --- | --- | --- | --- | --- |')
for p, cls in rows:
    c = (p['cmd'] or '').replace('|', '/')[:160]
    print(f"| {p['pid']} | {p['name']} | {p['session']} | {p['ppid']} | {p['created']} | {cls} | {p['exe']} | {c} |")
br = [p for p, _ in rows if p['name'] in ('chrome.exe', 'msedge.exe', 'firefox.exe')]
print(f"BROWSERS {len(br)} SESSION1 {sum(1 for p in br if p['session']==1)} SESSION0 {sum(1 for p in br if p['session']==0)}")
for k in ('RECORDED LANE PID', 'LANE-STARTED BY PATH, UNRECORDED'):
    print(f"COUNT {k}: {sum(1 for _, c in rows if c.startswith(k) and 'itself' not in c)}")
