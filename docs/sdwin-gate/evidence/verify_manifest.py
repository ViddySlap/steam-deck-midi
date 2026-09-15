import json,hashlib,sys,os
bad=0;n=0
for root in sys.argv[1:]:
    m=json.load(open(os.path.join(root,'MANIFEST.sha256'),encoding='utf-8-sig'))
    for e in m['entries']:
        p=os.path.join(root,e['relative']); b=open(p,'rb').read(); h=hashlib.sha256(b).hexdigest(); n+=1
        ok = h==e['sha256_copy']==e['sha256_before']==e['sha256_after'] and len(b)==e['bytes']
        print(('OK  ' if ok else 'BAD '), h[:12], len(b), root.split('/')[-1], e['relative'])
        bad+= not ok
print('entries',n,'bad',bad); sys.exit(1 if bad or n==0 else 0)
