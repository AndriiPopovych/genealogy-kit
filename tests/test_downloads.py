"""HTTP лише на loopback; усі зображення генеруються тестом."""
import io,json,sys,tempfile,threading,time,unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import download_common as d
import agad_pages as agad

class DownloadTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  b=io.BytesIO();Image.new('RGB',(32,24),'blue').save(b,format='PNG');cls.png=b.getvalue();cls.hits={}
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def do_GET(self):
    path=self.path;cls.hits[path]=cls.hits.get(path,0)+1
    status=200;body=cls.png;ctype='image/png'
    if path=='/html':body=b'<html>login</html>';ctype='text/html'
    if path=='/corrupt':body=cls.png[:32]
    if path in ('/404','/429','/500','/206','/302'):status=int(path[1:])
    if path=='/long-retry':status=429
    if path=='/retry':status=429 if cls.hits[path]==1 else 200
    if path=='/timeout':time.sleep(.3)
    self.send_response(status);self.send_header('Content-Type',ctype)
    if path=='/long-retry':self.send_header('Retry-After','200')
    if status==429 and path!='/long-retry':self.send_header('Retry-After','0')
    if status==302:self.send_header('Location','/ok')
    self.send_header('Content-Length',str(len(body)+(10 if path=='/interrupted' else 0)));self.end_headers()
    try:self.wfile.write(body)
    except BrokenPipeError:pass
  cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start();cls.base=f'http://127.0.0.1:{cls.server.server_port}'
 @classmethod
 def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join()
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.out=Path(self.temp.name)
 def tearDown(self):self.temp.cleanup()
 def test_ranges(self):
  self.assertEqual(d.parse_pages('1,1,3-5',5),[1,3,4,5]);self.assertEqual(d.parse_pages('every:2:1-5',5),[1,3,5])
  for text in ('','5-3','0','1-9','every:0','1-5:0','1,'):
   with self.subTest(text=text),self.assertRaises(ValueError):d.parse_pages(text,5)
 def test_http_errors(self):
  for path in ('/html','/corrupt','/404','/429','/500','/206','/302','/interrupted'):
   with self.subTest(path=path),self.assertRaises(d.DownloadError):
    with patch.object(d.time,'sleep'):d.download_image('doc',1,100,self.base+path,self.out)
  self.assertFalse(list(self.out.glob('*.img')))
 def test_timeout(self):
  with self.assertRaises(d.DownloadError):d.fetch(self.base+'/timeout',timeout=.05)
 def test_retry(self):
  with patch.object(d.time,'sleep') as sleep:data,_,_=d.fetch(self.base+'/retry')
  self.assertEqual(data,self.png);self.assertEqual(sleep.call_count,1)
 def test_cache_identity_corruption(self):
  a=d.download_image('doc',1,100,self.base+'/ok',self.out);b=d.download_image('doc',1,100,self.base+'/ok',self.out);self.assertEqual(b['status'],'skipped')
  c=d.download_image('other',1,100,self.base+'/ok',self.out);e=d.download_image('doc',1,200,self.base+'/ok',self.out);self.assertEqual(len({a['path'],c['path'],e['path']}),3)
  target=self.out/a['path'];target.write_bytes(b'x'*a['bytes']);self.assertEqual(d.download_image('doc',1,100,self.base+'/ok',self.out)['status'],'verified');self.assertTrue(list((self.out/'quarantine').iterdir()))
 def test_rename_manifest_interruption(self):
  original=d.append
  def fail(path,row):
   if row['status']=='verified':raise OSError('синтетичний обрив')
   return original(path,row)
  with patch.object(d,'append',fail),self.assertRaises(d.DownloadError):d.download_image('doc',1,100,self.base+'/ok',self.out)
  r=d.download_image('doc',1,100,self.base+'/ok',self.out);self.assertEqual(r['status'],'verified');self.assertTrue(list((self.out/'quarantine').iterdir()))
 def test_partial_and_manifest_tail(self):
  r=d.download_image('doc',1,100,self.base+'/ok',self.out);(self.out/(r['path']+'.part')).write_bytes(b'partial')
  with (self.out/'manifest.jsonl').open('ab') as f:f.write(b'{"broken":')
  self.assertEqual(d.download_image('doc',1,100,self.base+'/ok',self.out)['status'],'skipped')
  rows=[json.loads(x) for x in (self.out/'manifest.jsonl').read_text().splitlines()];self.assertTrue(any(x['status']=='incomplete_tail' for x in rows))
 def test_legacy_conversion(self):
  p=self.out/'MANIFEST.txt';raw='1 '+'a'*64+' 10 '+self.base+'/ok\n'+'broken';p.write_text(raw);r=d.convert_legacy(p,self.out/'converted.jsonl');self.assertEqual(r['converted'],1);self.assertEqual(r['skipped_lines'],[2]);self.assertEqual(p.read_text(),raw);self.assertIsNone(json.loads((self.out/'converted.jsonl').read_text())['received_at'])
 def test_agad_boundaries(self):
  page=b'<a href="pages/a.htm">a</a>'
  with patch.object(agad,'fetch',side_effect=[(page,'','text/html'),d.HTTPError(404)]):self.assertEqual(agad.list_pages('https://example.invalid/'),['a'])
  for responses in ([d.HTTPError(404)],[(page,'','text/html'),d.HTTPError(500)],[(page,'','text/html'),(page,'','text/html')]):
   with patch.object(agad,'fetch',side_effect=responses),self.assertRaises(d.DownloadError):agad.list_pages('https://example.invalid/')
  with patch.object(agad,'fetch',return_value=(page,'','text/html')),self.assertRaises(d.DownloadError):agad.list_pages('https://example.invalid/',1)
 def test_secret_url(self):
  for url in ('https://a.invalid/?token=secret','https://u:p@a.invalid/x','file:///tmp/a'):
   with self.assertRaises(d.DownloadError):d.safe_url(url)
 def test_curl_config_disabled(self):
  (self.out/'.curlrc').write_text('location\n')
  with patch.dict('os.environ',{'CURL_HOME':str(self.out)}),self.assertRaises(d.DownloadError):d.fetch(self.base+'/302')
 def test_long_retry_after_stops(self):
  with patch.object(d.time,'sleep') as sleep,self.assertRaises(d.DownloadError):d.fetch(self.base+'/long-retry')
  sleep.assert_not_called()
 def test_manifest_middle_corruption(self):
  (self.out/'manifest.jsonl').write_text('{bad}\n{}\n')
  with self.assertRaises(d.DownloadError):d.download_image('doc',1,100,self.base+'/ok',self.out)
 def test_manifest_no_newline(self):
  row={'status':'failed','error':'Синтетична помилка'};(self.out/'manifest.jsonl').write_text(json.dumps(row))
  d.download_image('doc',1,100,self.base+'/ok',self.out)
  self.assertEqual(len([json.loads(x) for x in (self.out/'manifest.jsonl').read_text().splitlines()]),2)
if __name__=='__main__':unittest.main()
