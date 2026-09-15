"""Compare real HTTP status/JSON replies of the original Deck API tests."""
import http.client
import json
import os
from pathlib import Path
import sys
import unittest

root, output = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
os.chdir(root)
sys.path[:0] = [str(root), str(root / 'tests')]
from deck.control_api import SenderController
from test_deck_control_api import DeckControlAPITests

# Hold only the volatile age field fixed, identically in both contract arms.
status = SenderController.status
def fixed_status(self):
    value = status(self)
    if value['heartbeat_age'] is not None:
        value['heartbeat_age'] = 0.0
    return value
SenderController.status = fixed_status
current = None
records = []
putrequest = http.client.HTTPConnection.putrequest
getresponse = http.client.HTTPConnection.getresponse
read = http.client.HTTPResponse.read

def observe_request(self, method, url, *args, **kwargs):
    self.contract_request = [method, url]
    return putrequest(self, method, url, *args, **kwargs)
def observe_response(self, *args, **kwargs):
    response = getresponse(self, *args, **kwargs)
    response.contract_request = self.contract_request
    return response
def normalize(value):
    if isinstance(value, str):
        return value.replace(str(current.root), '<fixture>')
    if isinstance(value, list):
        return [normalize(v) for v in value]
    if isinstance(value, dict):
        return {k: normalize(v) for k,v in value.items()}
    return value
def observe_read(self, *args, **kwargs):
    body = read(self, *args, **kwargs)
    if body and hasattr(self, 'contract_request'):
        records.append(dict(test=current._testMethodName, request=self.contract_request,
                            status=self.status, content_type=self.getheader('Content-Type'),
                            body=normalize(json.loads(body))))
    return body
http.client.HTTPConnection.putrequest = observe_request
http.client.HTTPConnection.getresponse = observe_response
http.client.HTTPResponse.read = observe_read
names_path = Path(sys.argv[3])
if not names_path.exists():
    names_path.write_text(json.dumps(unittest.defaultTestLoader.getTestCaseNames(DeckControlAPITests)))
result = unittest.TestResult()
for name in json.loads(names_path.read_text()):
    current = DeckControlAPITests(name)
    current.run(result)
for test,tb in result.errors + result.failures:
    print(test, tb)
output.write_text(json.dumps(records, sort_keys=True, indent=2)+'\n')
print('CONTRACT tests=%d responses=%d errors=%d failures=%d' % (result.testsRun,len(records),len(result.errors),len(result.failures)))
if not result.wasSuccessful() or not records:
    raise SystemExit(1)
if len(sys.argv) > 4:
    before = json.loads(Path(sys.argv[4]).read_text())
    if before != records:
        for i,(a,b) in enumerate(zip(before,records)):
            if a != b:
                print('DIFF',i,a,b)
        raise SystemExit('CONTRACT DIFFERENT')
    print('CONTRACT IDENTICAL: all captured HTTP statuses, JSON bodies and content types')
