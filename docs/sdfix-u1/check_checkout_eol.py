"""Prove the geometry check's pin survives a CRLF-default checkout."""
from pathlib import Path
import hashlib,json,shutil,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[2]
WORK=Path(tempfile.mkdtemp(prefix='eol-',dir='/tmp/sdfix-u1'))
origin=WORK/'origin';origin.mkdir();(origin/'tests').mkdir()
source=ROOT/'tests/ui_controller_geometry.cjs';digest=hashlib.sha256(source.read_bytes()).hexdigest()
shutil.copyfile(source,origin/'tests/ui_controller_geometry.cjs')
attrs=(ROOT/'tests/.gitattributes').read_bytes();target=origin/'tests/.gitattributes';target.write_bytes(attrs)
message=WORK/'commit.txt';message.write_text('Owned disposable line-ending control\n')
commands=[]
def git(*args):
    cmd=['git','-c','core.hooksPath=/dev/null','-c','user.name=EOL control','-c','user.email=eol@example.invalid',*map(str,args)]
    subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE);commands.append(cmd)
git('init','-q',origin)
rows=[]
for name,contents in [('pristine',attrs),('removed-rule',b''),('restored',attrs)]:
    target.write_bytes(contents);git('-C',origin,'add','tests');git('-C',origin,'commit','-q','-F',message)
    checkout=WORK/name
    git('-c','core.autocrlf=true','clone','--quiet',origin,checkout)
    payload=(checkout/'tests/ui_controller_geometry.cjs').read_bytes()
    row={'case':name,'sha256':hashlib.sha256(payload).hexdigest(),'equals_pinned_bytes':hashlib.sha256(payload).hexdigest()==digest,'crlf_count':payload.count(b'\r\n')}
    rows.append(row);assert row['equals_pinned_bytes']==(name!='removed-rule'),row
    print('PASS',name,row)
(ROOT/'docs/sdfix-u1/evidence/eol-proof.json').write_text(json.dumps({'work':str(WORK),'pinned_sha256':digest,'rows':rows,'commands':commands},indent=2)+'\n')
