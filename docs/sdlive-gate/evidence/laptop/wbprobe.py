import os, sys, json
os.environ['BROWSER'] = 'C:/Windows/System32/cmd.exe /c rem %s'
import webbrowser
webbrowser.register_standard_browsers()
order = list(webbrowser._tryorder)
first = webbrowser.get(order[0])
info = {'tryorder': order, 'first_type': type(first).__name__, 'first_name': getattr(first, 'name', None), 'first_args': getattr(first, 'args', None)}
# Call ONLY the first (BROWSER) entry, never the fallback chain.
try:
    info['first_open_returned'] = first.open('http://127.0.0.1:9/probe')
except Exception as exc:
    info['first_open_error'] = repr(exc)
print(json.dumps(info))
