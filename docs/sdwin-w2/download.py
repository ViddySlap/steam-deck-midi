import hashlib,json,subprocess
from pathlib import Path
root=Path('/Users/viddyslap/Documents/project-workspaces/steam-deck-midi')
manifest=Path('/tmp/sdwin-w2/windows-MANIFEST.sha256')
data=json.loads(manifest.read_text(encoding='utf-8-sig'))
dest=root/'.showready/fixtures/windows-installed'
assert not dest.exists()
dest.mkdir(parents=True)
for entry in data['entries']:
    path=dest/entry['relative']; path.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run([str(root/'scripts/showready/win_rail.sh'),'get',entry['destination'],str(path)],check=True)
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest==entry['sha256_copy']==entry['sha256_before']==entry['sha256_after'],path
    path.chmod(0o444)
(dest/'MANIFEST.sha256').write_bytes(manifest.read_bytes()); (dest/'MANIFEST.sha256').chmod(0o444)
for name in ('capture.json','before.json'):
    subprocess.run([str(root/'scripts/showready/win_rail.sh'),'get','C:\\Users\\Ben\\AppData\\Local\\Temp\\sdwin\\w2\\'+name,'/tmp/sdwin-w2/'+name],check=True)
print(f'Windows downloads verified: {len(data["entries"])}; MANIFEST bytes preserved')
