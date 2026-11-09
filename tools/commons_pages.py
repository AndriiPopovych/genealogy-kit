#!/usr/bin/env python3
"""Рендери сторінок Commons: назва.pdf сторінки папка [ширина]."""
import argparse,hashlib,json,time
from urllib.parse import quote,urlencode
from download_common import DownloadError,fetch,parse_pages,download_image
API='https://commons.wikimedia.org/w/api.php'
def pagecount(name):
 data,_,_=fetch(API+'?'+urlencode({'action':'query','titles':'File:'+name,'prop':'imageinfo','iiprop':'size','format':'json'}))
 try:
  pages=json.loads(data)['query']['pages'];n=next(iter(pages.values()))['imageinfo'][0]['pagecount']
  if type(n) is not int or n<1:raise ValueError()
  return n
 except (KeyError,ValueError,TypeError,StopIteration):raise DownloadError('Не визначено кількість сторінок документа.') from None

def thumb_url(name,page,width):
 fn=name.replace(' ','_');md5=hashlib.md5(fn.encode()).hexdigest();enc=quote(fn,safe='')
 return f'https://upload.wikimedia.org/wikipedia/commons/thumb/{md5[0]}/{md5[:2]}/{enc}/page{page}-{width}px-{enc}.jpg'
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('name');p.add_argument('pages');p.add_argument('outdir');p.add_argument('width',nargs='?',type=int,default=1920,choices=[500,960,1280,1920,3840]);p.add_argument('--pause',type=float,default=1.0);a=p.parse_args()
 try:
  if not 0<=a.pause<=60:raise ValueError('Пауза має бути від 0 до 60 секунд.')
  if not a.name.lower().endswith('.pdf') or '/' in a.name:raise ValueError('Очікується назва PDF, не шлях.')
  parse_pages(a.pages,1000000) # синтаксис до мережевого запиту
  pages=parse_pages(a.pages,pagecount(a.name));counts=dict(requested=len(pages),verified=0,skipped=0,failed=0);gaps=[]
  for n in pages:
   try:r=download_image('commons:'+a.name.replace(' ','_'),n,a.width,thumb_url(a.name,n,a.width),a.outdir);counts[r['status']]+=1
   except (DownloadError,OSError) as e:counts['failed']+=1;gaps.append({'page':n,'error':str(e)})
   time.sleep(a.pause)
  print(json.dumps(dict(counts,gaps=gaps),ensure_ascii=False));return int(bool(gaps))
 except (ValueError,DownloadError,OSError) as e:p.exit(1,str(e)+'\n')
if __name__=='__main__':raise SystemExit(main())
