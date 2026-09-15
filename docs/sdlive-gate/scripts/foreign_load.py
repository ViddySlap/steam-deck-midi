"""sdlive gate 3b load gate: load1, foreign_lines (harness engine tests / run-all.sh), pgrep.

foreign_lines counts `ps -A -o pid,command` rows whose COMMAND's first token basename is
zsh, bash, sh or node AND whose first script argument (first non-option token; a -c
command string is skipped as an option value) is under
/Users/viddyslap/Documents/project-workspaces/local-LLM-h14/engine/tests/ or is run-all.sh,
excluding any line containing `codex exec`. Prints JSON; exit 0 only if foreign_lines == 0
and pgrep -f "while True: pass" is readable and empty (exit 1, no output).
"""
import json, os, shlex, subprocess, sys
TESTS = '/Users/viddyslap/Documents/project-workspaces/local-LLM-h14/engine/tests/'
ps = subprocess.run(['ps', '-A', '-o', 'pid=,command='], capture_output=True, text=True)
matched = []
for line in ps.stdout.splitlines():
    pid, _, command = line.strip().partition(' ')
    if 'codex exec' in command:
        continue
    tokens = command.split()
    if not tokens or os.path.basename(tokens[0]) not in ('zsh', 'bash', 'sh', 'node'):
        continue
    rest, script = tokens[1:], None
    i = 0
    while i < len(rest):
        t = rest[i]
        if t == '-c':
            i += 2
            continue
        if t.startswith('-'):
            i += 1
            continue
        script = t
        break
    if script and (script.startswith(TESTS) or os.path.basename(script) == 'run-all.sh'):
        matched.append(line.strip()[:220])
pg = subprocess.run(['pgrep', '-f', 'while True: pass'], capture_output=True, text=True)
load1 = float(subprocess.run(['sysctl', '-n', 'vm.loadavg'], capture_output=True, text=True).stdout.split()[1])
out = {'load1': load1, 'foreign_lines': len(matched), 'matched': matched, 'ps_exit': ps.returncode,
       'pgrep_exit': pg.returncode, 'pgrep_stdout': pg.stdout, 'pgrep_stderr': pg.stderr,
       'pgrep_status': 'empty' if pg.returncode == 1 and not pg.stdout.strip() and not pg.stderr.strip() else 'present-or-unreadable'}
print(json.dumps(out))
sys.exit(0 if ps.returncode == 0 and not matched and out['pgrep_status'] == 'empty' else 1)
