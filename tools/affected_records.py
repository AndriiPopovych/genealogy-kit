#!/usr/bin/env python3
"""Черга перегляду залежностей і видань, лише читання."""
import argparse,hashlib,json
from pathlib import Path
from validate_registry import Validator,sha

def affected(root, changed):
 root=Path(root);v=Validator(root)
 if v.run():raise ValueError('Реєстри мають структурні помилки.')
 seeds=set()
 for x in changed:
  if ':' in x:
   typ,ident=x.split(':',1);choices=[(typ,ident)] if ident in v.index.get(typ,{}) else []
  else:choices=[(typ,x) for typ in v.index if x in v.index[typ]]
  if len(choices)!=1:raise ValueError('Відсутній або неоднозначний ID: '+x)
  seeds.update(choices)
 reverse={}
 for typ,rows in v.rows.items():
  for r,_ in rows:
   deps=[(x['type'],x['id']) for x in r.get('depends_on',[])]
   if typ=='C':deps.append(('S',r['source_id']))
   if typ=='L':deps.extend(('C',x) for x in r['claim_ids'])
   for d in deps:reverse.setdefault(d,set()).add((typ,r['id']))
 impacted=set(seeds);todo=list(seeds)
 while todo:
  for x in reverse.get(todo.pop(),set())-impacted:impacted.add(x);todo.append(x)
 editions=[]
 for p in sorted((root/'exports').glob('*/manifest.json')):
  m=json.loads(p.read_text());refs={(x['type'],x['id']) for x in m.get('record_refs',[])}
  stale=[x['path'] for x in m.get('input_files',[]) if not (root/x['path']).is_file() or sha(root/x['path'])!=x['sha256']]
  stale_records=[]
  for ref in m.get('record_refs',[]):
   record=v.index.get(ref['type'],{}).get(ref['id'])
   if ref.get('sha256') and (record is None or hashlib.sha256(json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=ref['sha256']):stale_records.append(ref['type']+':'+ref['id'])
  if refs&impacted or stale or stale_records:editions.append({'path':str(p.relative_to(root)),'proposed_status':'outdated','affected_refs':[f'{t}:{i}' for t,i in sorted(refs&impacted)],'changed_files':stale,'changed_records':stale_records})
 return {'changed':[f'{t}:{i}' for t,i in sorted(seeds)],'needs_review':[f'{t}:{i}' for t,i in sorted(impacted-seeds)],'editions':editions,'writes':False}
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('root');p.add_argument('ids',nargs='+');a=p.parse_args()
 try:print(json.dumps(affected(a.root,a.ids),ensure_ascii=False,indent=2))
 except (ValueError,OSError,KeyError,TypeError) as e:p.exit(1,str(e)+'\n')
