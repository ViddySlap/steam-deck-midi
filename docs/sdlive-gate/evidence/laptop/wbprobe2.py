import json, os, shlex, sys, webbrowser
py = sys.executable.replace('\\', '/')
out = []
for cmd in ['C:/Windows/System32/cmd.exe /c rem %s', 'C:/Windows/System32/cmd.exe /c exit 0 %s', py + ' -c pass %s', 'C:/Windows/System32/cmd.exe /d /c rem.%s']:
    b = webbrowser.GenericBrowser(shlex.split(cmd))
    try:
        r = b.open('http://127.0.0.1:61083')
    except Exception as exc:
        r = repr(exc)
    out.append({'cmd': cmd, 'returned': r})
print(json.dumps(out))
