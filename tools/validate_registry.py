#!/usr/bin/env python3
"""Лише структурна перевірка. Не змінює файли й не встановлює спорідненості."""
import argparse
import hashlib
import json
import re
from pathlib import Path

FILES = {'P':'people.json','S':'sources.json','C':'claims.json','L':'links.json','SEARCH':'searches.jsonl','CHANGE':'corrections.jsonl'}
REQUIRED = {
 'P':'id display_name living_status', 'S':'id title kind provenance locator',
 'C':'id source_id subject_person_ids text_as_written statement_kind normalized_statement locator reading_confidence',
 'L':'id kind person_ids roles claim_ids status identity_confidence relationship_confidence assessed_by assessed_at',
 'SEARCH':'id date question_id repository query_or_route method coverage gaps result next_step',
 'CHANGE':'id date target_id field old_value new_value reason evidence_refs confidence author applied'}
LEVELS = {'high','medium','low','undetermined'}
STATUSES = {'candidate','accepted_working','supported','unresolved','rejected'}
KINDS = {'family_testimony','original_record','historical_copy','derivative_index','tree_assertion','research_report','catalog','reference_work'}
ALIASES = {'C':{'literal_text':'text_as_written'},'L':{'kinship_confidence':'relationship_confidence','alternative_search_limits':'alternative_search_scope','parentage_type':'relationship_nature'},'SEARCH':{'resource':'repository'},'S':{'review_scope':'reviewed_scope','reviewed_by':'reviewer'}}
OPTIONAL = {
 'P':'name_variants claim_ids link_ids merged_into notes updated_at aliases',
 'S':'creator_or_informant creation_date_as_written received_at accessed_at url archive_locator digital_locator files derived_from_source_ids dependency_note review_status reviewed_scope reviewer reviewer_type reviewed_at transcript_path locator_conflicts locator_variants illegible_parts notes container member source_namespace old_id',
 'C':'event_type event_date place_as_written review_status reviewed_scope reviewer reviewer_type reviewed_at illegible_parts review_ref uncertainties recorded_at derivation assertion_context notes inference',
 'L':'relationship_nature basis support conflicts missing_evidence alternatives alternative_search_scope next_discriminating_check revisit_if notes',
 'SEARCH':'url_or_path source_ids document_key resource_channel access_status coverage_parts repeat_of repeat_reason positive_control notes',
 'CHANGE':'target_type notes'}
REVIEW_FIELDS = {'reviewed_scope','reviewer','reviewer_type','reviewed_at','illegible_parts'}


def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()


class Validator:
 def __init__(self, root, legacy=False, hashes=False):
  self.root=Path(root).resolve(); self.legacy=legacy; self.hashes=hashes
  self.rows={t:[] for t in FILES}; self.index={t:{} for t in FILES}; self.issues=[]; self.bad_format=False
 def issue(self, code, loc, message, compat=False, warning=False):
  self.issues.append({'level':'warning' if warning or compat and self.legacy else 'error','code':code,'location':loc,'message':message})
 def need(self,r,fields,loc):
  for k in fields:
   if k not in r:self.issue('required',loc+'.'+k,'Відсутнє поле.',compat=True)
 def enum(self,v,values,loc):
  if not isinstance(v,str) or v not in values:self.issue('enum',loc,'Невідоме значення.',compat=True)
 def ref(self,v,t,loc,owner=None):
  if isinstance(v,dict):
   if t is not None and v.get('type')!=t:self.issue('reference_type',loc,'Посилання має неправильний простір ID.');return
   t=v.get('type');v=v.get('id')
  if t not in self.index or not isinstance(v,str) or v not in self.index[t]:
   self.issue('reference',loc,'Відсутнє або нетипізоване посилання.');return
  if owner==(t,v):self.issue('self_reference',loc,'Самопосилання.')
 def refs(self,v,t,loc,owner=None):
  if not isinstance(v,list):self.issue('type',loc,'Потрібен масив посилань.');return
  for i,x in enumerate(v):
   if t is not None and not isinstance(x,str):self.issue('reference_shape',f'{loc}[{i}]','У цьому полі потрібен рядковий ID.')
   self.ref(x,t,f'{loc}[{i}]',owner)
 def conf(self,v,loc):
  if isinstance(v,str):
   self.enum(v,LEVELS,loc);self.issue('confidence_reason',loc,'Стара оцінка без окремого пояснення.',compat=True);return
  if not isinstance(v,dict):self.issue('type',loc,'Очікується level/reason.');return
  self.enum(v.get('level'),LEVELS,loc+'.level')
  if not isinstance(v.get('reason'),str) or not v['reason'].strip():self.issue('confidence_reason',loc,'Потрібне пояснення.')
 def load(self):
  marker=self.root/'data/format.json'
  try:
   if marker.exists():
    fmt=json.loads(marker.read_text())
    if not isinstance(fmt,dict) or type(fmt.get('schema_version')) is not int or fmt['schema_version']!=1:raise ValueError('Непідтримувана schema_version')
   else:self.legacy=True;self.issue('legacy','data/format.json','Немає маркера: legacy-діагностика.',warning=True)
  except (OSError,ValueError) as e:self.bad_format=True;self.issue('format','data/format.json',str(e))
  for t,name in FILES.items():
   p=self.root/'data'/name
   try:
    raw=p.read_text(encoding='utf-8-sig')
    data=[json.loads(x) for x in raw.splitlines() if x.strip()] if name.endswith('jsonl') else json.loads(raw)
    if not isinstance(data,list):raise ValueError('Верхній рівень має бути масивом')
   except (OSError,ValueError,RecursionError) as e:self.bad_format=True;self.issue('format',str(p),str(e));continue
   for n,r in enumerate(data,1):
    loc=f'data/{name}:{n}'
    if not isinstance(r,dict):self.issue('type',loc,'Запис має бути об’єктом.');continue
    r=dict(r)  # лише представлення у пам’яті; вихідний файл не змінюється
    for old,new in ALIASES.get(t,{}).items():
     if old in r:
      self.issue('alias',loc+'.'+old,'Сумісне ім’я поля; оригінал незмінний.',warning=True)
      if new in r and r[new]!=r[old]:self.issue('alias_conflict',loc,'Старе й нове поле суперечать.')
      elif new not in r:r[new]=r[old]
    self.rows[t].append((r,loc));ident=r.get('id')
    if not isinstance(ident,str) or not ident.strip():self.issue('id',loc,'Потрібен непорожній ID.');continue
    if ident in self.index[t]:self.issue('duplicate_id',loc,'Повторений ID у просторі '+t)
    else:self.index[t][ident]=r
 def review(self,r,loc):
  if 'review_status' not in r:return
  self.enum(r['review_status'],{'unread','machine_ocr_unverified','partial_review','reviewed'},loc+'.review_status')
  if r['review_status']!='reviewed':return
  meta=r
  if 'review_ref' in r:
   ref=r['review_ref'];self.ref(ref,'S',loc+'.review_ref')
   if not isinstance(ref,dict) or ref.get('type')!='S':self.issue('review_ref',loc,'Потрібен тип S.');return
   meta=self.index['S'].get(ref.get('id'),{})
   if meta.get('review_ref') is not None or self.index['S'].get(r.get('id')) is r:
    self.issue('review_ref_chain',loc,'review_ref дозволений для C лише на S з прямими метаданими.');return
   if not ref.get('scope') or ref.get('scope')!=meta.get('reviewed_scope') or ref.get('scope')!=r.get('reviewed_scope') or meta.get('review_status')!='reviewed':
    self.issue('review_scope',loc,'review_ref не підтверджує точно такий самий обсяг.');return
  self.need(meta,REVIEW_FIELDS,loc)
  if 'reviewer_type' in meta:self.enum(meta['reviewer_type'],{'human','model'},loc+'.reviewer_type')
  for k in REVIEW_FIELDS-{'illegible_parts'}:
   if k in meta and (not isinstance(meta[k],str) or not meta[k].strip()):self.issue('review_metadata',loc+'.'+k,'Порожні метадані.',compat=True)
  if 'illegible_parts' in meta and not isinstance(meta['illegible_parts'],list):self.issue('type',loc,'illegible_parts має бути масивом.')
 def local_file(self,f,loc):
  if not isinstance(f,dict):self.issue('type',loc,'Метадані файла мають бути об’єктом.');return
  self.need(f,{'path','provenance','received_at','sha256','bytes','role'},loc)
  for k in ('provenance','received_at','sha256','bytes','role'):
   if k in f and (f[k] is None or isinstance(f[k],str) and not f[k].strip()):
    self.issue('unknown_file_metadata',loc+'.'+k,'Невідоме старе значення.',compat=True)
  path=f.get('path')
  if not isinstance(path,str) or not path:self.issue('file_path',loc,'Немає шляху.');return
  p=(self.root/path).resolve()
  if self.root!=p and self.root not in p.parents:self.issue('file_path',loc,'Шлях поза коренем.');return
  if not p.is_file():self.issue('file_missing',loc,'Файл відсутній.');return
  if f.get('bytes') is not None and (type(f['bytes']) is not int or f['bytes']<0 or f['bytes']!=p.stat().st_size):self.issue('bytes',loc,'Некоректний розмір.')
  digest=f.get('sha256')
  if digest is not None:
   if not isinstance(digest,str) or not re.fullmatch('[0-9a-fA-F]{64}',digest):self.issue('sha256',loc,'Некоректний SHA-256.')
   elif self.hashes and sha(p)!=digest.lower():self.issue('sha256',loc,'Хеш не збігається.')
 def cycles(self,graph,loc,warning=False):
  done=set();active=set()
  for start in graph:
   stack=[(start,False)]
   while stack:
    node,end=stack.pop()
    if end:active.discard(node);done.add(node)
    elif node in active:self.issue('cycle',loc,'Цикл через '+node,warning=warning)
    elif node not in done:
     active.add(node);stack.append((node,True));stack.extend((v,False) for v in graph.get(node,[]))
 def validate(self):
  merges={};parents={};candidates={};candidate_parents={}
  for t,rows in self.rows.items():
   for r,loc in rows:
    owner=(t,r.get('id'));self.need(r,set(REQUIRED[t].split()),loc)
    nullable={'old_value','new_value'}
    for key in set(REQUIRED[t].split())-nullable:
     if key in r and (r[key] is None or isinstance(r[key],str) and not r[key].strip()):self.issue('empty',loc+'.'+key,'Порожнє обов’язкове поле.',compat=True)
    for key in ('id','source_id','display_name','title','text_as_written','normalized_statement','assessed_by','assessed_at','date','question_id','query_or_route','method','result','next_step','field','reason','author'):
     if key in r and not isinstance(r[key],str):self.issue('type',loc+'.'+key,'Очікується рядок.')
    known=set((REQUIRED[t]+' '+OPTIONAL[t]+' depends_on extensions').split())|set(ALIASES.get(t,{}))
    for k in r.keys()-known:self.issue('unknown_field',loc+'.'+k,'Додаткове поле не перевіряється й не видаляється.',warning=True)
    for k in ('reading_confidence','identity_confidence','relationship_confidence','confidence'):
     if k in r:self.conf(r[k],loc+'.'+k)
    if 'depends_on' in r:self.refs(r['depends_on'],None,loc+'.depends_on',owner)
    for k,target in [('claim_ids','C'),('link_ids','L'),('derived_from_source_ids','S'),('source_ids','S'),('subject_person_ids','P'),('person_ids','P')]:
     if k in r:self.refs(r[k],target,loc+'.'+k,owner)
    if t=='P':
     self.enum(r.get('living_status'),{'living','deceased','unknown'},loc)
     if r.get('merged_into') is not None:
      x=r['merged_into'];self.ref(x,'P',loc+'.merged_into',owner)
      target=x.get('id') if isinstance(x,dict) and x.get('type')=='P' else x
      if isinstance(target,str) and isinstance(r.get('id'),str):merges.setdefault(r['id'],[]).append(target)
     for v in r.get('name_variants',[]) if isinstance(r.get('name_variants',[]),list) else []:
      if isinstance(v,dict) and v.get('source_id'):self.ref(v['source_id'],'S',loc+'.name_variants')
    elif t=='S':
     self.enum(r.get('kind'),KINDS,loc+'.kind');self.review(r,loc)
     if 'locator_variants' in r:
      if not isinstance(r['locator_variants'],list):self.issue('type',loc,'locator_variants має бути масивом.')
      else:
       for v in r['locator_variants']:
        if not isinstance(v,dict):self.issue('type',loc,'Варіант має бути об’єктом.');continue
        self.need(v,{'system','value','provenance','source_ref','relation'},loc+'.locator_variants')
        if v.get('source_ref'):self.ref(v['source_ref'],None,loc+'.locator_variants.source_ref')
     if 'files' in r:
      if not isinstance(r['files'],list):self.issue('type',loc,'files має бути масивом.')
      else:
       for i,f in enumerate(r['files']):self.local_file(f,loc+f'.files[{i}]')
     if r.get('transcript_path') and not (self.root/r['transcript_path']).is_file():self.issue('file_missing',loc,'Транскрипція відсутня.')
    elif t=='C':
     self.ref(r.get('source_id'),'S',loc+'.source_id');self.review(r,loc)
     self.enum(r.get('statement_kind'),{'source_statement','inference'},loc+'.statement_kind')
     if r.get('statement_kind')=='inference' and not r.get('derivation'):self.issue('inference',loc,'Потрібна підстава inference.')
    elif t=='L':
     self.enum(r.get('kind'),{'identity','parent_child','spouses','siblings','family_circle'},loc+'.kind');self.enum(r.get('status'),STATUSES,loc+'.status')
     if 'relationship_nature' in r:self.enum(r['relationship_nature'],{'unspecified','biological','adoptive','step','household','other'},loc+'.relationship_nature')
     roles=r.get('roles');people=r.get('person_ids',[])
     if not isinstance(roles,dict) or not isinstance(people,list):self.issue('roles',loc,'roles — об’єкт, person_ids — масив.');continue
     for role,p in roles.items():
      self.ref(p,'P',loc+'.roles.'+role)
      if p not in people:self.issue('role_member',loc,'Роль не належить person_ids.')
     if len([p for p in people if isinstance(p,str)])!=len(set(p for p in people if isinstance(p,str))):self.issue('self_link',loc,'Повторена особа у зв’язку.')
     if r.get('kind')=='parent_child':
      if set(roles)!={'parent','child'} or len(people)!=2:self.issue('parent_roles',loc,'Окремий L для parent і child; parent2 не допускається.')
      a,b=roles.get('parent'),roles.get('child')
      if isinstance(a,str) and isinstance(b,str):
       if a==b:self.issue('self_parent',loc,'Самобатьківство.')
       if r.get('relationship_nature')=='biological' and r.get('status')!='rejected':
        candidates.setdefault(a,[]).append(b)
        candidate_parents.setdefault(b,set()).add(a)
        if r.get('status') in ('supported','accepted_working'):parents.setdefault(a,[]).append(b)
     if r.get('status') in ('supported','accepted_working'):
      if not r.get('claim_ids'):self.issue('decision_evidence',loc,'Потрібне чинне посилання на підставу C.',compat=True)
      for k in ('basis','revisit_if','assessed_by','assessed_at'):
       if not r.get(k) or isinstance(r[k],str) and not r[k].strip():self.issue('decision_basis',loc+'.'+k,'Потрібне обґрунтування.',compat=True)
      if 'conflicts' not in r:self.issue('decision_basis',loc,'Потрібне conflicts (можна []).',compat=True)
      if not r.get('alternatives') and not r.get('alternative_search_scope'):self.issue('alternatives',loc,'Потрібні альтернативи або межі пошуку.',compat=True)
    elif t=='SEARCH':
     q=r.get('question_id');qp=self.root/'state/questions.md'
     if isinstance(q,str) and (not qp.is_file() or not re.search(r'(?<![\w-])'+re.escape(q)+r'(?![\w-])',qp.read_text())):self.issue('question_reference',loc,'Q не знайдено у state/questions.md.')
     if 'access_status' in r:self.enum(r['access_status'],{'not_checked','catalog_only','images_available','access_blocked','searched_no_match'},loc+'.access_status')
     if r.get('repeat_of'):
      self.ref(r['repeat_of'],'SEARCH',loc+'.repeat_of',owner)
      if not r.get('repeat_reason'):self.issue('repeat_reason',loc,'Немає причини повтору.')
     if 'coverage_parts' in r:
      if not isinstance(r['coverage_parts'],list):self.issue('type',loc,'coverage_parts має бути масивом.')
      else:
       for part in r['coverage_parts']:
        if not isinstance(part,dict):self.issue('type',loc,'Частина має бути об’єктом.');continue
        self.need(part,{'unit','from','to','fields','method'},loc+'.coverage_parts')
        a,b=part.get('from'),part.get('to')
        if type(a) is int and type(b) is int and (a<1 or b<a):self.issue('coverage_range',loc,'Хибний діапазон.')
     if r.get('access_status') in ('access_blocked','not_checked') and r.get('coverage_parts'):self.issue('access_coverage',loc,'Без доступу немає оглянутих кадрів.')
    elif t=='CHANGE':
     target=r.get('target_id');typ=r.get('target_type')
     if isinstance(target,dict):self.ref(target,None,loc+'.target_id')
     else:
      choices=[k for k in self.index if isinstance(target,str) and target in self.index[k]]
      self.ref(target,typ or (choices[0] if len(choices)==1 else None),loc+'.target_id')
     if 'evidence_refs' in r:self.refs(r['evidence_refs'],None,loc+'.evidence_refs')
     if type(r.get('applied')) is not bool:self.issue('type',loc,'applied має бути boolean.')
  for child,options in candidate_parents.items():
   if len(options)>2:self.issue('competing_parents','L:'+child,'Понад два кандидатні біологічні батьки; зіставте альтернативи, без автоматичного злиття.',warning=True)
  self.cycles(merges,'P.merged_into');self.cycles(parents,'L.biological');self.cycles(candidates,'L.candidate_graph',True)
 def run(self):
  try:self.load();self.validate()
  except (TypeError,ValueError,OSError,KeyError,RecursionError) as e:
   self.issue('shape','registry','Непідтримувана вкладена структура: '+type(e).__name__)
  return 2 if self.bad_format else int(any(x['level']=='error' for x in self.issues))

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',nargs='?',default='.');p.add_argument('--legacy',action='store_true');p.add_argument('--hashes',action='store_true');p.add_argument('--json',action='store_true');a=p.parse_args()
 v=Validator(a.root,a.legacy,a.hashes);code=v.run();out={'exit_code':code,'legacy':v.legacy,'errors':sum(x['level']=='error' for x in v.issues),'warnings':sum(x['level']=='warning' for x in v.issues),'issues':v.issues}
 print(json.dumps(out,ensure_ascii=False,indent=2) if a.json else '\n'.join(f"{x['level']} {x['location']}: {x['message']}" for x in v.issues)+f"\nПомилок: {out['errors']}; застережень: {out['warnings']}.")
 return code
if __name__=='__main__':raise SystemExit(main())
