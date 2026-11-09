#!/usr/bin/env python3
"""Оновлює лише позначений блок покажчика; не створює рішень."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
from validate_registry import Validator
START='<!-- BEGIN GENERATED LINKS -->';END='<!-- END GENERATED LINKS -->'
def cell(x):
 if isinstance(x,dict):x=f"{x.get('level','')} — {x.get('reason','')}"
 return str(x).replace('|','\\|').replace('\n',' ')
def render(root):
 root=Path(root);v=Validator(root)
 if v.run():raise ValueError('Спочатку усуньте структурні помилки реєстрів.')
 files=['people.json','links.json','claims.json'];h=hashlib.sha256()
 for name in files:h.update(name.encode());h.update((root/'data'/name).read_bytes())
 lines=[START,'Зріз: '+datetime.date.today().isoformat()+'; SHA-256 P/L/C: `'+h.hexdigest()+'`.', '', '| L | Люди / ролі | Статус | Тотожність | Спорідненість | C → S | Застереження / наступне |','|---|---|---|---|---|---|---|']
 for r,_ in v.rows['L']:
  people=', '.join(v.index['P'][p]['display_name']+' ('+p+')' for p in r['person_ids'])
  refs=', '.join(c+' → '+v.index['C'][c]['source_id'] for c in r['claim_ids'])
  values=[r['id'],people+'; '+str(r['roles']),r['status'],r['identity_confidence'],r['relationship_confidence'],refs,str(r.get('conflicts',[]))+'; '+r.get('revisit_if','')]
  lines.append('| '+' | '.join(cell(x) for x in values)+' |')
 lines.append(END);block='\n'.join(lines)
 path=root/'state/links.md';old=path.read_text() if path.exists() else '# Актуальні робочі зв’язки\n'
 if old.count(START)!=old.count(END) or old.count(START)>1:raise ValueError('Пошкоджені межі генерованого блока.')
 if START in old:
  a=old.index(START);b=old.index(END)+len(END)
  if old.index(END)<a:raise ValueError('Порушений порядок меж.')
  new=old[:a]+block+old[b:]
 else:new=old.rstrip()+'\n\n'+block+'\n'
 path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.md.part');tmp.write_text(new);tmp.replace(path)
 return path
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',nargs='?',default='.');a=p.parse_args()
 try:print(render(a.root))
 except (ValueError,OSError) as e:p.exit(1,str(e)+'\n')
