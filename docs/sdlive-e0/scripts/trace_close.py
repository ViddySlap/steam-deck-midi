"""Scratch-only observation: original client and server, no transport repair."""
import collections
import http.client
import json
import os
from pathlib import Path
import socket
import sys
import threading
import unittest

root = Path(sys.argv[1]).resolve()
os.chdir(root)
sys.path[:0] = [str(root), str(root / 'tests')]
from deck.control_api import _Handler, ControlServer
import test_deck_control_api

records = []
lock = threading.Lock()
def emit(event, **values):
    with lock:
        records.append(dict(index=len(records), thread=threading.current_thread().name,
                            event=event, **values))

class ObservedReader:
    def __init__(self, inner, handler):
        self.inner, self.handler = inner, handler
        self.body_read = 0
    def __getattr__(self, key):
        return getattr(self.inner, key)
    def read(self, size=-1):
        emit('server_read_begin', size=size)
        value = self.inner.read(size)
        self.body_read += len(value)
        emit('server_read_end', bytes=len(value), total=self.body_read)
        return value
    def close(self):
        emit('server_rfile_close', method=getattr(self.handler, 'command', ''),
             declared=getattr(self.handler, 'headers', {}).get('Content-Length'),
             body_read=self.body_read)
        return self.inner.close()

setup = _Handler.setup
def observed_setup(self):
    setup(self)
    self.rfile = ObservedReader(self.rfile, self)
_Handler.setup = observed_setup
respond = _Handler._json
def observed_json(self, code, result):
    emit('server_response', method=self.command, code=code,
         declared=self.headers.get('Content-Length'), body_read=self.rfile.body_read,
         result=result)
    return respond(self, code, result)
_Handler._json = observed_json
shutdown = socket.socket.shutdown
close = socket.socket.close
def observed_shutdown(self, how):
    emit('socket_shutdown', fd=self.fileno(), how=how)
    return shutdown(self, how)
def observed_close(self):
    emit('socket_close', fd=self.fileno())
    return close(self)
socket.socket.shutdown = observed_shutdown
socket.socket.close = observed_close
send = http.client.HTTPConnection.send
read = http.client.HTTPResponse.read
def observed_send(self, data):
    emit('client_send_begin', bytes=len(data), preview=repr(data)[:250])
    result = send(self, data)
    emit('client_send_end', bytes=len(data))
    return result
def observed_read(self, *args):
    emit('client_response_read_begin', declared=self.length)
    result = read(self, *args)
    emit('client_response_read_end', bytes=len(result))
    return result
http.client.HTTPConnection.send = observed_send
http.client.HTTPResponse.read = observed_read
kinds = collections.Counter()
for i in range(30):
    emit('test_start', iteration=i)
    test = test_deck_control_api.DeckControlAPITests('test_malformed_json_and_unsupported_method_are_json')
    result = unittest.TestResult()
    test.run(result)
    for case, tb in result.errors + result.failures:
        kinds[tb.strip().splitlines()[-1]] += 1
        emit('test_error', case=str(case), traceback=tb)
    emit('test_end', iteration=i)
Path(sys.argv[2]).write_text(json.dumps({'events':records,'errors':dict(kinds)}, indent=2), encoding='utf-8')
print('OBSERVED', json.dumps(dict(kinds)))
for key, count in collections.Counter((r['method'],r['declared'],r['body_read'],r['code']) for r in records if r['event']=='server_response').items():
    print('RESPONSE method=%s declared=%s body_read=%s code=%s count=%s' % (*key,count))
