"""Повністю синтетичні перевірки контракту; жодних родинних даних."""
import copy,hashlib,json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from validate_registry import Validator
from render_links import render
from affected_records import affected
import shutil
class RegistryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'fixture';shutil.copytree(ROOT/'examples/synthetic',self.root)
 def tearDown(self):self.tmp.cleanup()
 def data(self,file):return json.loads((self.root/'data'/file).read_text())
 def save(self,file,value):(self.root/'data'/file).write_text(json.dumps(value,ensure_ascii=False))
 def check(self,code=1,legacy=False,hashes=False):
  v=Validator(self.root,legacy,hashes);self.assertEqual(v.run(),code,v.issues);return {x['code'] for x in v.issues}
 def test_valid_read_only(self):
  before={str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()};self.check(0,hashes=True)
  self.assertEqual(before,{str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
 def test_duplicate(self):
  a=self.data('people.json');a.append(a[0]);self.save('people.json',a);self.assertIn('duplicate_id',self.check())
 def test_missing_refs(self):
  a=self.data('claims.json');a[0]['source_id']='MISSING';self.save('claims.json',a);self.assertIn('reference',self.check(legacy=True))
 def test_reviewed_scope(self):
  a=self.data('sources.json');a[1].update(review_status='reviewed',reviewed_scope='акт 1',reviewer='модель',reviewer_type='model',reviewed_at='2026-11-09',illegible_parts=[]);self.save('sources.json',a)
  c=self.data('claims.json');c[1].update(review_status='reviewed',reviewed_scope='вся книга',review_ref={'type':'S','id':'S2','scope':'вся книга'});self.save('claims.json',c);self.assertIn('review_scope',self.check())
  c[1].update(reviewed_scope='акт 1',review_ref={'type':'S','id':'S2','scope':'акт 1'});self.save('claims.json',c);self.check(0)
 def test_review_metadata_legacy(self):
  a=self.data('sources.json');a[1]['review_status']='reviewed';self.save('sources.json',a);self.check(1);self.check(0,legacy=True)
 def test_parent_and_merge_cycles(self):
  a=self.data('links.json');a[0]['relationship_nature']='biological';b=copy.deepcopy(a[0]);b.update(id='L9',roles={'parent':'P1','child':'P2'});a.append(b);self.save('links.json',a);self.assertIn('cycle',self.check())
 def test_candidate_cycle_warning(self):
  a=self.data('links.json');a[0].update(relationship_nature='biological',status='candidate');b=copy.deepcopy(a[0]);b.update(id='L9',roles={'parent':'P1','child':'P2'});a.append(b);self.save('links.json',a);self.assertIn('cycle',self.check(0))
 def test_merge_cycle(self):
  a=self.data('people.json');a[0]['merged_into']='P2';a[1]['merged_into']='P1';self.save('people.json',a);self.assertIn('cycle',self.check())
 def test_roles_and_conditionals(self):
  a=self.data('links.json');a[0]['roles']['parent2']='P4';del a[0]['revisit_if'];self.save('links.json',a);codes=self.check();self.assertIn('parent_roles',codes);self.assertIn('decision_basis',codes)
 def test_no_two_source_requirement(self):
  a=self.data('links.json');a[0]['claim_ids']=['C1'];self.save('links.json',a);self.check(0)
 def test_unknown_fields_enums(self):
  a=self.data('sources.json');a[0]['private_extension']={'unknown':[None,'']};a[0]['kind']='old_kind';self.save('sources.json',a);self.check(1);self.check(0,legacy=True)
 def test_missing_marker_is_legacy(self):
  (self.root/'data/format.json').unlink();self.assertIn('legacy',self.check(0))
 def test_invalid_format(self):
  (self.root/'data/corrections.jsonl').write_text('{broken\n');self.check(2,legacy=True)
 def test_unknown_schema(self):
  self.save('format.json',{'schema_version':99});self.check(2)
 def test_bad_shapes(self):
  for field,value in [('roles',[]),('person_ids',{}),('depends_on',[{'type':[],'id':{}}])]:
   with self.subTest(field=field):
    a=self.data('links.json');a[0][field]=value;self.save('links.json',a);self.check(1)
 def test_hash_optional(self):
  p=self.root/'transcripts/record-a.txt';raw=p.read_bytes();p.write_bytes(raw.replace(b'1901',b'1902'));self.check(0);self.assertIn('sha256',self.check(1,hashes=True))
 def test_missing_file(self):
  (self.root/'transcripts/record-a.txt').unlink();self.assertIn('file_missing',self.check())
 def test_repeat_reason(self):
  p=self.root/'data/searches.jsonl';rows=[json.loads(x) for x in p.read_text().splitlines()];del rows[-1]['repeat_reason'];p.write_text('\n'.join(json.dumps(x) for x in rows)+'\n');self.assertIn('repeat_reason',self.check())
 def test_render_preserves_prose(self):
  p=self.root/'state/links.md';p.write_text('ДО\n');render(self.root);p.write_text(p.read_text()+'ПІСЛЯ\n');render(self.root);render(self.root);s=p.read_text();self.assertTrue(s.startswith('ДО\n'));self.assertTrue(s.endswith('ПІСЛЯ\n'));self.assertEqual(s.count('BEGIN GENERATED'),1)
 def test_dependency_selective_and_no_writes(self):
  for name,refs in [('dependent',[{'type':'L','id':'L1'}]),('independent',[{'type':'L','id':'L2'}])]:
   p=self.root/'exports'/name/'manifest.json';p.parent.mkdir(parents=True);p.write_text(json.dumps({'record_refs':refs,'input_files':[]}))
  before=(self.root/'data/links.json').read_bytes();a=affected(self.root,['C3']);self.assertEqual(a['needs_review'],['L:L1']);self.assertEqual({x['path'] for x in a['editions']},{'exports/cards/manifest.json','exports/dependent/manifest.json','exports/research-update/manifest.json','exports/family-report/manifest.json'});self.assertEqual(before,(self.root/'data/links.json').read_bytes())
 def test_cli_exit_codes(self):
  r=subprocess.run([sys.executable,str(ROOT/'tools/validate_registry.py'),str(self.root),'--json'],capture_output=True,text=True);self.assertEqual(r.returncode,0);self.assertEqual(json.loads(r.stdout)['errors'],0)
 def test_typed_namespace_and_ambiguous_change(self):
  p=self.data('people.json');p.append({'id':'S1','display_name':'Інша вигадана особа','living_status':'unknown'});self.save('people.json',p)
  path=self.root/'data/corrections.jsonl';rows=[json.loads(x) for x in path.read_text().splitlines()];rows[0]['target_id']='S1';path.write_text(''.join(json.dumps(x)+'\n' for x in rows));self.check(1)
  rows[0]['target_type']='S';path.write_text(''.join(json.dumps(x)+'\n' for x in rows));self.check(0)
  links=self.data('links.json');links[0]['claim_ids']=[{'type':'S','id':'S1'}];self.save('links.json',links);self.assertIn('reference_type',self.check(1))
 def test_review_ref_cannot_confirm_itself(self):
  a=self.data('sources.json');a[1].update(review_status='reviewed',reviewed_scope='акт',review_ref={'type':'S','id':'S2','scope':'акт'});self.save('sources.json',a);self.assertIn('review_ref_chain',self.check(1))
 def test_no_evidence_and_blank_basis(self):
  a=self.data('links.json');a[0].update(claim_ids=[],basis='   ');self.save('links.json',a);codes=self.check();self.assertIn('decision_evidence',codes);self.assertIn('decision_basis',codes)
 def test_external_file_symlink(self):
  outside=Path(self.tmp.name)/'outside.txt';outside.write_text('СИНТЕТИЧНИЙ зовнішній файл');link=self.root/'external.txt';link.symlink_to(outside)
  a=self.data('sources.json');a[0]['files'][0]['path']='external.txt';self.save('sources.json',a);self.assertIn('file_path',self.check(hashes=True))
 def test_alias_conflict(self):
  a=self.data('links.json');a[0]['kinship_confidence']={'level':'low','reason':'Суперечливий alias'};self.save('links.json',a);self.assertIn('alias_conflict',self.check(legacy=True))
 def test_edition_record_hash_detects_staleness(self):
  a=self.data('links.json');a[0]['basis']='Уточнена синтетична підстава';self.save('links.json',a)
  result=affected(self.root,['C5']);cards=next(x for x in result['editions'] if x['path']=='exports/cards/manifest.json');self.assertIn('L:L1',cards['changed_records'])
 def test_canonical_id_fields_reject_objects(self):
  a=self.data('links.json');a[0]['claim_ids']=[{'type':'C','id':'C1'}];self.save('links.json',a);self.assertIn('reference_shape',self.check())
  a=self.data('claims.json');a[0]['source_id']={'type':'S','id':'S1'};self.save('claims.json',a);self.assertIn('type',self.check())
 def test_reversed_render_markers_preserve_file(self):
  p=self.root/'state/links.md';text='<!-- END GENERATED LINKS --><!-- BEGIN GENERATED LINKS -->';p.write_text(text)
  with self.assertRaises(ValueError):render(self.root)
  self.assertEqual(p.read_text(),text)
if __name__=='__main__':unittest.main()
