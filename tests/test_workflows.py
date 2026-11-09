"""Виконувані синтетичні репетиції ручних протоколів, не тести реальних агентів."""
import copy,hashlib,json,os,shutil,subprocess,sys,tempfile,time,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from validate_registry import Validator
from build_release import build,digest

def hashes(root):return {str(p.relative_to(root)):digest(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
class WorkflowTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def test_T2_real_process_interruption(self):
  worker=self.base/'attempt';worker.mkdir();progress=worker/'progress.json';script="import json,pathlib,time; p=pathlib.Path(__import__('sys').argv[1]); p.write_text(json.dumps({'last_frame':3,'gap':[2],'next_frame':4,'reviewed_fields':['імена']})); time.sleep(30)"
  proc=subprocess.Popen([sys.executable,'-c',script,str(progress)])
  try:
   for _ in range(100):
    if progress.exists():break
    time.sleep(.01)
   self.assertTrue(progress.exists());proc.terminate();proc.wait(timeout=3)
   state=json.loads(progress.read_text());self.assertEqual(state['last_frame'],3);self.assertEqual(state['gap'],[2]);self.assertEqual(state['next_frame'],4)
   # Файл не є доказом живого стану; результат termination підтверджує лише цей процес.
   queue={'execution':'unknown','acceptance':'partial','attempt_path':str(worker)};self.assertEqual(queue['execution'],'unknown')
  finally:
   if proc.poll() is None:proc.kill();proc.wait()
 def test_T5_text_partial_and_replay(self):
  worker=self.base/'worker';worker.mkdir();blocked=worker/'readonly';blocked.mkdir();blocked.chmod(0o555)
  try:
   result=subprocess.run([sys.executable,'-c',"from pathlib import Path; import sys; Path(sys.argv[1]).write_text('проба')",str(blocked/'report.md')],capture_output=True,text=True)
   self.assertNotEqual(result.returncode,0);self.assertIn('PermissionError',result.stderr)
  finally:blocked.chmod(0o755)
  (worker/'report.md').write_text('Автор: синтетичний працівник; збережено координатором дослівно.\nJ1-F1: кадри 1–3, поле імен, кадр 2 пропущений.\nJ1-F2: побічна зачіпка.\nJ1-F3: хибне ключове прочитання 81, звірено як 31.\nJ1-F4: негативний прохід.\n')
  source=worker/'source.txt';source.write_text('СИНТЕТИЧНИЙ запис: вік 31, не 81.')
  decisions=[('J1-F1','accepted','SEARCH1'),('J1-F2','deferred','Q2'),('J1-F3','rejected','SEARCH2'),('J1-F4','accepted','SEARCH3')]
  mapping={};registered=[]
  # Репетиція явної карти, не production-інтегратор: рішення передані координатором.
  for run in range(2):
   for local,fate,permanent in decisions:
    if local in mapping:self.assertEqual(mapping[local],(fate,permanent));continue
    mapping[local]=(fate,permanent);registered.append(permanent)
  self.assertEqual(len(mapping),4);self.assertEqual(len(registered),4)
  dest=self.base/'original.txt';shutil.copy2(source,dest);self.assertEqual(digest(source.read_bytes()),digest(dest.read_bytes()));source.write_text('змінений працівником');self.assertNotEqual(source.read_bytes(),dest.read_bytes())
  self.assertEqual(len(set(registered)),len(registered))
 def test_T6_legacy_backup_dryrun_rollback_repeat(self):
  old=self.base/'old';shutil.copytree(ROOT/'examples/synthetic',old);(old/'data/format.json').unlink()
  p=old/'data/people.json';people=json.loads(p.read_text());people[0]['id']='RDL-001';people[0]['aliases']={'old':None,'raw':'помилкове свідчення'};p.write_text(json.dumps(people,ensure_ascii=False))
  for name in ('claims.json','links.json'):
   p=old/'data'/name;p.write_text(p.read_text().replace('P1','RDL-001'))
  p=old/'data/sources.json';s=json.loads(p.read_text());s[0]['kind']='old_testimony';s[0]['unknown_nested']={'raw':['',None]};s[1]['review_status']='reviewed';p.write_text(json.dumps(s,ensure_ascii=False))
  (old/'AGENTS.md').write_text('Локальне правило: працювати тільки з цим вигаданим родоводом.')
  (old/'workers/archive').mkdir(parents=True);shutil.copy2(old/'transcripts/testimony.txt',old/'workers/archive/source.txt')
  s[0]['files'][0]['path']='workers/archive/source.txt';p.write_text(json.dumps(s,ensure_ascii=False))
  change=old/'data/corrections.jsonl';rows=[json.loads(x) for x in change.read_text().splitlines()];rows[0]['applied']=False;change.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
  before=hashes(old);backup=self.base/'backup';shutil.copytree(old,backup);self.assertEqual(before,hashes(backup));v=Validator(old,legacy=True);self.assertEqual(v.run(),0,v.issues);self.assertEqual(before,hashes(old))
  # Відоме структурне доповнення на копії; статуси й історія незмінні.
  work=self.base/'work';shutil.copytree(old,work)
  for _ in range(2):
   people=json.loads((work/'data/people.json').read_text())
   for person in people:person.setdefault('extensions',{})
   (work/'data/people.json').write_text(json.dumps(people,ensure_ascii=False))
  self.assertEqual([x['id'] for x in people],[x['id'] for x in json.loads((old/'data/people.json').read_text())])
  self.assertEqual((work/'data/corrections.jsonl').read_bytes(),change.read_bytes());self.assertEqual((work/'AGENTS.md').read_bytes(),(old/'AGENTS.md').read_bytes());self.assertTrue((work/'workers/archive/source.txt').exists())
  first=hashes(work);people=json.loads((work/'data/people.json').read_text());[x.setdefault('extensions',{}) for x in people];(work/'data/people.json').write_text(json.dumps(people,ensure_ascii=False));self.assertEqual(first,hashes(work))
  shutil.rmtree(work);shutil.copytree(backup,work);self.assertEqual(hashes(work),before);self.assertEqual(hashes(old),before)
 def test_T7_allowlist_canary_symlink_and_hash(self):
  kit=self.base/'kit';(kit/'templates/starter/data').mkdir(parents=True);(kit/'reviews').mkdir();(kit/'reviews/private.txt').write_text('PRIVATE_CANARY_731');(kit/'.hidden').write_text('PRIVATE_CANARY_731')
  (kit/'guide').mkdir();(kit/'guide/public.md').write_text('Загальна інструкція');(kit/'templates/starter/data/people.json').write_text('[]\n')
  m={'version':'test-local','files':[{'path':'guide/public.md','sha256':digest((kit/'guide/public.md').read_bytes()),'type':'guide'},{'path':'templates/starter/data/people.json','destination':'data/people.json','sha256':digest(b'[]\n'),'type':'template'}],'empty_directories':['originals']};(kit/'KIT_FILES.json').write_text(json.dumps(m))
  result=build(kit,self.base/'release');self.assertEqual(result['license'],'unresolved')
  with zipfile.ZipFile(self.base/'release.zip') as z:
   self.assertEqual(sorted(x for x in z.namelist() if not x.endswith('/')),['KIT_FILES.json','data/people.json','guide/public.md']);self.assertNotIn(b'PRIVATE_CANARY_731',b''.join(z.read(n) for n in z.namelist()))
  (kit/'guide/public.md').unlink();(kit/'guide/public.md').symlink_to(kit/'reviews/private.txt')
  with self.assertRaises(ValueError):build(kit,self.base/'badlink')
  (kit/'guide/public.md').unlink();(kit/'guide/public.md').write_text('змінено')
  with self.assertRaises(ValueError):build(kit,self.base/'badhash')
 def test_release_mit_license_and_required_file(self):
  kit=self.base/'kit';kit.mkdir()
  m={'version':'test-local','license':'MIT','files':[]}
  manifest=kit/'KIT_FILES.json';manifest.write_text(json.dumps(m))
  with self.assertRaisesRegex(ValueError,'LICENSE'):build(kit,self.base/'missing-license')
  self.assertFalse((self.base/'missing-license').exists())
  license_bytes=(ROOT/'LICENSE').read_bytes();(kit/'LICENSE').write_bytes(license_bytes)
  m['files']=[{'path':'LICENSE','sha256':digest(license_bytes),'type':'license'}];manifest.write_text(json.dumps(m))
  result=build(kit,self.base/'licensed')
  self.assertEqual(result['license'],'MIT');self.assertFalse(result['published'])
  self.assertEqual(json.loads((self.base/'licensed.inventory.json').read_text())['license'],'MIT')
  with zipfile.ZipFile(self.base/'licensed.zip') as z:self.assertEqual(z.read('LICENSE'),license_bytes)
if __name__=='__main__':unittest.main()
