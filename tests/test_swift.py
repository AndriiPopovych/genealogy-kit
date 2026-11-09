"""Виконувані проби Swift/PDFKit лише на macOS; компіляція в тимчасовій папці."""
import json,os,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def synthetic_pdf(path):
 objs=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
 stream=b'BT /F1 18 Tf 20 100 Td (SYNTHETIC TEST ONLY) Tj ET';objs.append(b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream')
 out=b'%PDF-1.4\n';offsets=[0]
 for i,obj in enumerate(objs,1):offsets.append(len(out));out+=str(i).encode()+b' 0 obj\n'+obj+b'\nendobj\n'
 xref=len(out);out+=b'xref\n0 6\n0000000000 65535 f \n'+b''.join(f'{n:010d} 00000 n \n'.encode() for n in offsets[1:]);out+=f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode();path.write_bytes(out)
@unittest.skipUnless(sys.platform=='darwin' and shutil.which('swiftc'),'Потрібні macOS і swiftc; інші ОС не перевіряються')
class SwiftTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name);cls.pdf=cls.root/'synthetic.pdf';synthetic_pdf(cls.pdf);cls.logs={}
  for name in ('pdfpage','pdfhalf','pdfbands','pdfsheet','pdftext'):
   r=subprocess.run(['swiftc','-module-cache-path',str(cls.root/'cache'),str(ROOT/'tools'/f'{name}.swift'),'-o',str(cls.root/name)],capture_output=True,text=True);cls.logs[name]=r.stderr
   if r.returncode:raise RuntimeError(name+': '+r.stderr)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def run_tool(self,name,*args):return subprocess.run([str(self.root/name),*map(str,args)],capture_output=True)
 def test_missing_arguments(self):
  for name in self.logs:
   r=self.run_tool(name);self.assertNotEqual(r.returncode,0);self.assertIn('Помилка'.encode(),r.stderr)
 def test_valid_render_and_format(self):
  from PIL import Image
  for name,args,ext,fmt in [('pdfpage',['1'],'png','PNG'),('pdfhalf',['1'],'png','PNG'),('pdfsheet',['1','1','1','300'],'jpg','JPEG'),('pdfbands',['1','1','1','0.5','300'],'jpg','JPEG')]:
   out=self.root/(name+'.'+ext)
   full=[self.pdf,*args,out]
   if name=='pdfhalf':full=[self.pdf,'1',out,'1','full']
   r=self.run_tool(name,*full);self.assertEqual(r.returncode,0,r.stderr)
   with Image.open(out) as im:self.assertEqual(im.format,fmt);im.verify()
  self.assertEqual(self.run_tool('pdfpage',self.pdf,'count').stdout.strip(),b'1')
  self.assertIn(b'SYNTHETIC TEST ONLY',self.run_tool('pdftext',self.pdf).stdout)
 def test_bad_ranges_scale_and_extension(self):
  cases=[('pdfpage',[self.pdf,'0',self.root/'bad.png']),('pdfpage',[self.pdf,'2',self.root/'bad.png']),('pdfpage',[self.pdf,'1',self.root/'bad.png','nan']),('pdfhalf',[self.pdf,'1',self.root/'bad.png','1','unknown']),('pdfsheet',[self.pdf,'1','1','0','300',self.root/'bad.jpg']),('pdfsheet',[self.pdf,'1','1','1','300',self.root/'bad.png']),('pdfbands',[self.pdf,'1','1','0','0.5','300',self.root/'bad.jpg']),('pdfbands',[self.pdf,'1','1','1','2','300',self.root/'bad.jpg'])]
  for name,args in cases:
   with self.subTest(name=name,args=args):self.assertNotEqual(self.run_tool(name,*args).returncode,0)
if __name__=='__main__':unittest.main()
