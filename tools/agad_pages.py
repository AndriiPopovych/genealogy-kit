#!/usr/bin/env python3
"""Кадри книги AGAD: фонд сигнатура папка. Live-доступ перевіряється окремо."""
import argparse,hashlib,json,time,re
from urllib.parse import quote
from download_common import DownloadError,HTTPError,fetch,download_image

def list_pages(base,max_indexes=100):
 names=[];seen=set();hashes=set()
 for n in range(1,max_indexes+1):
  try:data,_,_=fetch(base+('indeks.htm' if n==1 else f'indeks_{n}.htm'))
  except HTTPError as e:
   if e.code==404 and n>1:return names
   raise
  digest=hashlib.sha256(data).hexdigest()
  if digest in hashes:raise DownloadError('Повтор сторінки індексу; перелік не підтверджений.')
  hashes.add(digest)
  entries=re.findall(r'href=[\"\']pages/([^\"\']+)\.htm[\"\']',data.decode('cp1250'),re.I)
  if not entries:raise DownloadError('Індекс без розпізнаних посилань; це не підтвердження порожньої книги.')
  for x in entries:
   if not re.fullmatch(r'[\w .-]+',x) or '..' in x:raise DownloadError('Некоректний шлях кадру.')
   if x not in seen:names.append(x);seen.add(x)
 raise DownloadError('Досягнуто скінченну межу індексів; повноту не встановлено.')

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('fond');p.add_argument('sygn');p.add_argument('outdir');p.add_argument('--max-indexes',type=int,default=100);p.add_argument('--pause',type=float,default=1.0);a=p.parse_args()
 try:
  if not 0<=a.pause<=60:raise ValueError('Пауза має бути від 0 до 60 секунд.')
  if not re.fullmatch(r'\d+',a.fond) or not re.fullmatch(r'[\w.-]+',a.sygn) or not 1<=a.max_indexes<=1000:raise ValueError('Некоректні фонд, сигнатура або межа індексів.')
  base=f'http://agadd.home.net.pl/metrykalia/{a.fond}/sygn.%20{quote(a.sygn)}/';names=list_pages(base,a.max_indexes)
  count=dict(requested=len(names),verified=0,skipped=0,failed=0);gaps=[]
  for n in names:
   try:r=download_image(f'agad:{a.fond}:{a.sygn}',n,None,base+'images/'+quote(n)+'.jpg',a.outdir);count[r['status']]+=1
   except (DownloadError,OSError) as e:count['failed']+=1;gaps.append({'page':n,'error':str(e)})
   time.sleep(a.pause)
  print(json.dumps(dict(count,gaps=gaps),ensure_ascii=False));return int(bool(gaps))
 except (ValueError,DownloadError,OSError) as e:p.exit(1,str(e)+'\n')
if __name__=='__main__':raise SystemExit(main())
