"""Малі локальні перевірки умовних контрактів U11–U14."""
import csv,hashlib,json,sys,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];EX=ROOT/'examples/synthetic'
class ConditionalTests(unittest.TestCase):
 def test_U11_index_locators_and_gap(self):
  rows=list(csv.DictReader((EX/'book-index.tsv').read_text().splitlines(),delimiter='\t'))
  for row in rows:
   text=(EX/row['transcript_path']).read_text();self.assertIn(row['locator'],text)
  a=[r for r in rows if r['document_key']=='DEMO:A'];self.assertEqual(len(a),2);self.assertEqual(len({r['entry'] for r in a}),1);self.assertNotIn('2',[r['frame'] for r in a]);self.assertEqual(rows[-1]['review_status'],'machine_ocr_unverified')
 def test_U12_media_and_manifest(self):
  m=json.loads((EX/'exports/cards/manifest.json').read_text());self.assertEqual(m['deployed_status'],'not_deployed');self.assertIn('synthetic',m['privacy_revision'])
  for entry in m['input_files']+m['files']:self.assertEqual(hashlib.sha256((EX/entry['path']).read_bytes()).hexdigest(),entry['sha256'])
  ids={r['id'] for r in json.loads((EX/'data/links.json').read_text())};self.assertTrue(all(x['id'] in ids for x in m['record_refs'] if x['type']=='L'))
 def test_U13_mock_unknown_conflict_repeat_privacy_candidate(self):
  # Mock віддаленої пам’яті — лише репетиція контракту; немає мережі чи експортера.
  remote={};operations={}
  def apply(op,lose_response=False):
   if op['decision_status'] in ('candidate','unresolved') and op['action']=='parent_child':return 'blocked_candidate'
   if op['media_sensitive'] and not op['media_authorized']:return 'blocked_privacy'
   if op['operation_id'] in operations:return 'verified'  # read-back operation_id, не повторний create
   if op['expected_version']!=remote.get(op['external_id'],{}).get('version',0):return 'conflict'
   remote[op['external_id']]={'value':op['value'],'version':op['expected_version']+1};operations[op['operation_id']]=dict(op)
   return 'unknown' if lose_response else 'verified'
  op=dict(operation_id='DEMO-1',external_id='DEMO-P1',expected_version=0,value='погоджений синтетичний текст',decision_status='accepted_working',action='update',media_sensitive=False,media_authorized=False)
  self.assertEqual(apply(op,True),'unknown');self.assertEqual(apply(op),'verified');self.assertEqual(len(remote),1);self.assertEqual(len(operations),1)
  self.assertEqual(apply(dict(op,operation_id='DEMO-2',value='конфлікт')),'conflict')
  self.assertEqual(apply(dict(op,operation_id='DEMO-3',decision_status='candidate',action='parent_child')),'blocked_candidate')
  self.assertEqual(apply(dict(op,operation_id='DEMO-4',media_sensitive=True)),'blocked_privacy')
 def test_U14_container_namespace_delta(self):
  m=json.loads((EX/'incoming/inventory.json').read_text());archive=EX/m['container']['path'];self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),m['container']['sha256'])
  with zipfile.ZipFile(archive) as z:
   self.assertEqual(len(z.namelist()),3)
   for member in m['members']:self.assertEqual(hashlib.sha256(z.read(member['member'])).hexdigest(),member['sha256'])
  self.assertEqual({x['kind'] for x in m['members']},{'original_record','research_report','tree_assertion'})
  mapping=m['namespace_mapping'];self.assertEqual(mapping[0]['old_id'],mapping[1]['old_id']);self.assertNotEqual(mapping[0]['source_namespace'],mapping[1]['source_namespace']);self.assertIsNone(mapping[1]['proposed_local_id'])
  self.assertEqual(m['content_delta'][0]['status'],'pending_review')
  a=json.loads((EX/'incoming/assertion-context.json').read_text());self.assertNotEqual(a['assertion_context']['recorded_at'],a['decision_context']['recorded_at']);self.assertEqual(a['execution'],'unknown')
if __name__=='__main__':unittest.main()
