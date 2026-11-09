#!/usr/bin/env python3
"""Створює чистий локальний пакет за KIT_FILES; не публікує."""
import argparse,hashlib,io,json,os,shutil,stat,zipfile
from pathlib import Path,PurePosixPath

def digest(data):return hashlib.sha256(data).hexdigest()
def safe_relative(text):
 p=PurePosixPath(text)
 if not text or p.is_absolute() or '..' in p.parts or '\\' in text:raise ValueError('Небезпечний відносний шлях.')
 return Path(*p.parts)
def no_symlinks(root,rel):
 p=root
 for part in rel.parts:
  p=p/part
  if p.is_symlink():raise ValueError('Symlink у дозволеному шляху: '+str(rel))
 return p

def inspect_nested(data,depth=0):
 if not zipfile.is_zipfile(io.BytesIO(data)):return
 if depth>3:raise ValueError('Надмірна вкладеність архівів.')
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  if sum(x.file_size for x in z.infolist())>268435456:raise ValueError('Завеликий вкладений архів для локальної перевірки.')
  seen=set()
  for info in z.infolist():
   safe_relative(info.filename)
   if info.filename in seen:raise ValueError('Повтор шляху у вкладеному архіві.')
   seen.add(info.filename)
   if stat.S_ISLNK(info.external_attr>>16):raise ValueError('Symlink у вкладеному архіві.')
   if not info.is_dir():inspect_nested(z.read(info),depth+1)

def build(root,dest):
 root=Path(root).resolve();dest=Path(dest).absolute();archive=dest.with_suffix('.zip');inventory=dest.with_suffix('.inventory.json')
 if any(p.exists() for p in (dest,archive,inventory)):raise ValueError('Призначення вже існує; перезапис заборонено.')
 manifest_path=no_symlinks(root,Path('KIT_FILES.json'));raw=manifest_path.read_bytes();m=json.loads(raw);rows=m['files'];payload={}
 forbidden={'proposals','reviews','backups','workers','originals','transcripts','working','inbox','exports','drafts','.git','.codex','.claude'}
 for row in rows:
  rel=safe_relative(row['path']);target=safe_relative(row.get('destination',row['path']))
  if rel.parts[0] in forbidden or target.parts[0] in forbidden:raise ValueError('Заборонений вміст у allowlist.')
  if rel.parts[0] in ('data','state') or str(rel)=='INTAKE.md':raise ValueError('Робочі приватні шаблони не копіюються; використайте templates/starter.')
  if (target.parts[0] in ('data','state') or str(target)=='INTAKE.md') and rel.parts[:2]!=('templates','starter'):raise ValueError('Стартові файли лише з templates/starter.')
  path=no_symlinks(root,rel)
  if not path.is_file():raise ValueError('Файл відсутній: '+str(rel))
  data=path.read_bytes()
  inspect_nested(data)
  if digest(data)!=row['sha256']:raise ValueError('Хеш allowlist не збігається: '+str(rel))
  name=target.as_posix()
  if name in payload or name=='KIT_FILES.json':raise ValueError('Повтор цілі allowlist.')
  payload[name]=data
 payload['KIT_FILES.json']=raw
 license_id=m.get('license','unresolved')
 if license_id=='MIT' and 'LICENSE' not in payload:raise ValueError('Для MIT потрібен LICENSE у складі пакета.')
 # Повна перевірка до створення виходу; у разі збою часткову папку не називаємо готовим пакетом.
 dest.mkdir(parents=True)
 for name,data in payload.items():
  p=dest/safe_relative(name);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
 for name in m.get('empty_directories',[]):
  p=dest/safe_relative(name);p.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
  for name in sorted(payload):z.writestr(name,payload[name])
  for name in m.get('empty_directories',[]):z.writestr(safe_relative(name).as_posix()+'/',b'')
 checked=[]
 with zipfile.ZipFile(archive) as z:
  names=[x.filename for x in z.infolist() if not x.is_dir()]
  if sorted(names)!=sorted(payload):raise ValueError('Фактичний склад ZIP не відповідає allowlist.')
  for info in z.infolist():
   safe_relative(info.filename)
   if stat.S_ISLNK(info.external_attr>>16):raise ValueError('Symlink у ZIP.')
   if info.is_dir():continue
   data=z.read(info)
   if data!=payload[info.filename]:raise ValueError('Байти ZIP не збігаються.')
   checked.append({'path':info.filename,'bytes':len(data),'sha256':digest(data)})
 result={'version':m['version'],'license':license_id,'published':False,'archive_sha256':digest(archive.read_bytes()),'files':checked}
 inventory.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');return result
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('root');p.add_argument('dest');a=p.parse_args()
 try:r=build(a.root,a.dest);print(json.dumps({'files':len(r['files']),'license':r['license'],'archive_sha256':r['archive_sha256']},ensure_ascii=False))
 except (ValueError,OSError,KeyError,TypeError) as e:p.exit(1,str(e)+'\n')
