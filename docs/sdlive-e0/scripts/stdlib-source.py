import http.client, inspect, os, socketserver
print("PYTHON_PID", os.getpid())
for owner,name in [(socketserver.TCPServer,'shutdown_request'),(socketserver.StreamRequestHandler,'finish'),(http.client.HTTPConnection,'getresponse'),(http.client.HTTPResponse,'read')]:
    value=getattr(owner,name)
    source,start=inspect.getsourcelines(value)
    print(inspect.getfile(value), owner.__name__+'.'+name, 'line',start)
    for number,line in enumerate(source,start): print(f'{number}: {line}',end='')
