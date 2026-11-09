#!/usr/bin/env python3
"""Приймання зображень. Один записувач каталогу; Python 3, curl і Pillow."""
import argparse,datetime,hashlib,io,json,os,re,subprocess,tempfile,time,uuid
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit,parse_qsl

class DownloadError(RuntimeError):pass
class HTTPError(DownloadError):
 def __init__(self,code):self.code=code;super().__init__(f'HTTP {code}; файл не прийнято.')
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def safe_url(url):
 try:
  u=urlsplit(url)
  if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or u.fragment or any(ord(c)<32 for c in url):raise ValueError()
  if any(re.search(r'token|secret|password|cookie|authorization|signature|credential|api.?key|^key$|^sig$|^auth$|^code$|^x-amz|^x-goog',k,re.I) for k,_ in parse_qsl(u.query)):raise ValueError()
 except (ValueError,TypeError):raise DownloadError('Потрібен публічний URL без секретних параметрів.') from None
 return url

def parse_pages(spec,total=None):
 if not isinstance(spec,str) or not spec.strip():raise ValueError('Порожній перелік сторінок.')
 if spec.startswith('every:'):
  m=re.fullmatch(r'every:(\d+)(?::(\d+)-(\d+))?',spec)
  if not m or int(m[1])<1:raise ValueError('Крок every має бути додатним.')
  if m[2]:spec=f'{m[2]}-{m[3]}:{m[1]}'
  elif total:spec=f'1-{total}:{m[1]}'
  else:raise ValueError('Для every потрібна кількість сторінок.')
 out=[];seen=set()
 for chunk in spec.split(','):
  m=re.fullmatch(r'\s*(\d+)(?:-(\d+)(?::(\d+))?)?\s*',chunk)
  if not m:raise ValueError('Очікується сторінка або N-M[:крок].')
  a=int(m[1]);b=int(m[2] or a);step=int(m[3] or 1)
  if a<1 or b<a or step<1 or total is not None and b>total or b-a>1000000:raise ValueError('Некоректні межі або крок сторінок.')
  for n in range(a,b+1,step):
   if n not in seen:seen.add(n);out.append(n)
 return out

def fetch(url,retries=2,timeout=30,wait_budget=30):
 """curl не змінюється на інший клієнт після блокування; stdout не містить body."""
 safe_url(url)
 if type(retries) is not int or not 0<=retries<=5 or not 0<timeout<=300:raise ValueError('Некоректний retry/timeout.')
 for attempt in range(retries+1):
  with tempfile.TemporaryDirectory() as td:
   body=Path(td)/'body';headers=Path(td)/'headers'
   r=subprocess.run(['curl','--disable','--globoff','--silent','--show-error','--max-time',str(timeout),'--max-filesize','268435456','--proto','=http,https','--dump-header',str(headers),'--output',str(body),'--write-out','%{http_code}\n%{content_type}\n%{url_effective}','--user-agent','GenealogyKit/3.0 (public archival images)','--url',url],capture_output=True)
   if r.returncode:raise DownloadError(f'curl завершився з кодом {r.returncode}; файл не прийнято.')
   parts=r.stdout.decode('utf-8','replace').splitlines()
   if len(parts)<3:raise DownloadError('Неповні HTTP-метадані.')
   try:code=int(parts[0])
   except ValueError:raise DownloadError('Хибний HTTP-код.') from None
   media=parts[1].split(';')[0].strip().lower();final=safe_url(parts[2]);hs=headers.read_text(errors='replace') if headers.exists() else ''
   if code in (301,302,303,307,308):
    # Не слідуємо невідомому перенаправленню з можливими підписаними URL.
    raise DownloadError('Перенаправлення: перевірте кінцеву публічну адресу перед завантаженням.')
   if code==429 or 500<=code<=599:
    if attempt<retries:
     match=re.findall(r'^Retry-After:\s*(.+)$',hs,re.I|re.M);delay=2**attempt
     if match:
      try:delay=float(match[-1].strip())
      except ValueError:
       try:delay=(parsedate_to_datetime(match[-1].strip())-datetime.datetime.now(datetime.timezone.utc)).total_seconds()
       except (ValueError,TypeError):pass
     if delay>wait_budget:raise DownloadError('Retry-After перевищує бюджет; повторіть пізніше.')
     time.sleep(max(0,delay));continue
   if code!=200:raise HTTPError(code)
   data=body.read_bytes()
   if not data:raise DownloadError('Порожня відповідь.')
   lengths=re.findall(r'^Content-Length:\s*(\d+)\s*$',hs,re.I|re.M)
   if lengths and len(data)!=int(lengths[-1]):raise DownloadError('Обрив Content-Length.')
   return data,final,media
 raise DownloadError('Вичерпано повтори.')

def inspect_image(data,media=None):
 try:from PIL import Image
 except ImportError:raise DownloadError('Для завантажувача потрібен Pillow; ручний старт його не потребує.') from None
 if media and media!='application/octet-stream' and not media.startswith('image/'):raise DownloadError('HTTP-вміст не є зображенням.')
 try:
  with Image.open(io.BytesIO(data)) as im:im.verify()
  with Image.open(io.BytesIO(data)) as im:
   im.load();dims=list(im.size);mime=Image.MIME[im.format]
   if min(dims)<1:raise ValueError()
 except Exception:raise DownloadError('Зображення пошкоджене або не декодується.') from None
 return {'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'dimensions':dims,'media_type':mime}

def append(path,row):
 payload=(json.dumps(row,ensure_ascii=False)+'\n').encode()
 with path.open('ab') as f:f.write(payload);f.flush();os.fsync(f.fileno())

def quarantine(path,out):
 dest=out/'quarantine'/(path.name+'.'+uuid.uuid4().hex);dest.parent.mkdir(exist_ok=True)
 if dest.parent.is_symlink():raise DownloadError('Карантин не може бути symlink.')
 path.rename(dest);return str(dest.relative_to(out))

def read_manifest(path):
 if not path.exists():return []
 if path.is_symlink():raise DownloadError('Маніфест не може бути symlink.')
 raw=path.read_bytes();rows=[];good=b''
 for i,line in enumerate(raw.splitlines(keepends=True)):
  try:
   r=json.loads(line)
   if not isinstance(r,dict):raise ValueError()
  except (ValueError,UnicodeError):
   if not line.endswith(b'\n') and i==len(raw.splitlines(keepends=True))-1:
    copy=quarantine(path,path.parent);path.write_bytes(good)
    append(path,{'status':'incomplete_tail','error':'Неповний хвіст; первісний маніфест збережено.','path':copy,'recorded_at':now()});return rows
   raise DownloadError(f'Пошкоджений рядок маніфесту {i+1}.') from None
  rows.append(r);good+=line if line.endswith(b'\n') else line+b'\n'
 if raw and not raw.endswith(b'\n'):
  with path.open('ab') as f:f.write(b'\n')
 return rows

def download_image(document_key,page,width,url,outdir):
 safe_url(url)
 if not isinstance(document_key,str) or not document_key or not isinstance(page,(str,int)) or isinstance(page,bool) or (isinstance(page,int) and page<1) or width is not None and (type(width) is not int or width<1):raise ValueError('Некоректна ідентичність сторінки/ширина.')
 out=Path(outdir);out.mkdir(parents=True,exist_ok=True)
 if out.is_symlink():raise DownloadError('Каталог не може бути symlink.')
 key=json.dumps([document_key,page,width],ensure_ascii=False);name=hashlib.sha256(key.encode()).hexdigest()+'.img'
 target=out/name;part=out/(name+'.part');manifest=out/'manifest.jsonl';rows=read_manifest(manifest)
 base=dict(document_key=document_key,page=page,width=width,requested_url=url,final_url=None,received_at=None,path=name,sha256=None,bytes=None,media_type=None,dimensions=None,status='failed',error=None)
 if part.exists() or part.is_symlink():append(manifest,dict(base,status='quarantined',path=quarantine(part,out),error='Перерваний файл .part'))
 if target.exists() or target.is_symlink():
  valid=[r for r in rows if all(r.get(k)==base[k] for k in ('document_key','page','width','requested_url','path')) and r.get('status')=='verified']
  try:
   if target.is_symlink() or not valid:raise DownloadError('Кеш без підтвердженої ідентичності.')
   meta=inspect_image(target.read_bytes());prior=valid[-1]
   if any(prior.get(k)!=v for k,v in meta.items()):raise DownloadError('Кеш пошкоджений.')
   return dict(prior,status='skipped')
  except (OSError,DownloadError):append(manifest,dict(base,status='quarantined',path=quarantine(target,out),error='Непідтверджений або конфліктний кеш'))
 try:
  data,final,media=fetch(url)
  with part.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
  meta=inspect_image(part.read_bytes(),media);base.update(meta,final_url=final,received_at=now(),status='verified')
  part.replace(target);append(manifest,base);return base
 except Exception as e:
  if part.exists():base['path']=quarantine(part,out)
  base.update(status='failed',error=str(e) if isinstance(e,DownloadError) else 'Локальна помилка '+type(e).__name__)
  try:append(manifest,base)
  except OSError:pass
  raise DownloadError(base['error']) from None

def convert_legacy(source,dest):
 source=Path(source);dest=Path(dest)
 if dest.exists():raise ValueError('Вихід уже існує.')
 rows=[];skipped=[]
 for n,line in enumerate(source.read_text().splitlines(keepends=True),1):
  parts=line.strip().split(maxsplit=3)
  if not line.endswith('\n') or len(parts)!=4 or not re.fullmatch('[0-9a-fA-F]{64}',parts[1]) or not parts[2].isdigit():skipped.append(n);continue
  try:safe_url(parts[3])
  except DownloadError:skipped.append(n);continue
  rows.append(dict(document_key=None,page=parts[0],width=None,requested_url=parts[3],final_url=None,received_at=None,path=None,sha256=parts[1],bytes=int(parts[2]),media_type=None,dimensions=None,status='legacy_unverified',error='Ідентичність, дата й файл потребують звірки.'))
 dest.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows));report={'converted':len(rows),'skipped_lines':skipped,'source_unchanged':True};dest.with_suffix(dest.suffix+'.report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));return report
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['convert']);p.add_argument('source');p.add_argument('dest');a=p.parse_args()
 try:r=convert_legacy(a.source,a.dest);print(json.dumps(r,ensure_ascii=False));raise SystemExit(bool(r['skipped_lines']))
 except (ValueError,OSError) as e:p.exit(1,str(e)+'\n')
