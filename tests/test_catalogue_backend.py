import copy
import base64
import io
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
import catalogue_backend as CB
import server

SOURCE=Path(__file__).resolve().parent/'fixtures/linko'

class BackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for folder in ('data/products','templates','assets/product-images'): (self.root/folder).mkdir(parents=True)
        for rel in ('catalogue.py','data/catalog.json','data/products/mounts.json','templates/products.html','assets/product-images/mounts.svg'):
            dest=self.root/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy(SOURCE/rel,dest)
        self.project=SimpleNamespace(name='Fixture',path=self.root)
        allow=patch.object(CB,'enabled',return_value=True);allow.start();self.addCleanup(allow.stop)
        catalog=json.loads((self.root/'data/catalog.json').read_text(encoding='utf-8'));catalog['root']=[{'type':'product','id':'mounts'}]
        (self.root/'data/catalog.json').write_text(json.dumps(catalog),encoding='utf-8')
        CB.engine(self.root).generate()
    def test_conflict_and_invalid_preserve_files(self):
        snap=CB.snapshot(self.project);proposed=copy.deepcopy(snap);proposed['products']['mounts']['title']['ka']='განახლება'
        result=CB.save(self.project,proposed);self.assertNotEqual(result['revision'],snap['revision'])
        with self.assertRaisesRegex(ValueError,'changed since'):CB.save(self.project,proposed)
        current=CB.snapshot(self.project);bad=copy.deepcopy(current);bad['products']['mounts']['price']['mode']='fixed'
        before=(self.root/'data/products/mounts.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'price.amount'):CB.save(self.project,bad)
        self.assertEqual(before,(self.root/'data/products/mounts.json').read_bytes())
    def test_multifile_write_failure_restores_prior_json(self):
        snap=CB.snapshot(self.project);changed=copy.deepcopy(snap);changed['products']['mounts']['title']['ka']='არ უნდა დარჩეს'
        before={str(path.relative_to(self.root)):path.read_bytes() for path in CB.files(self.root)}
        real=CB._atomic;calls=[0]
        def fail_second(path,data,root):
            calls[0]+=1
            if calls[0]==2: raise OSError('simulated disk failure')
            return real(path,data,root)
        with patch.object(CB,'_atomic',side_effect=fail_second):
            with self.assertRaisesRegex(OSError,'simulated disk failure'):CB.save(self.project,changed)
        self.assertEqual(before,{str(path.relative_to(self.root)):path.read_bytes() for path in CB.files(self.root)})
    def test_path_and_upload_restrictions(self):
        snap=CB.snapshot(self.project);bad=copy.deepcopy(snap);bad['products']['mounts']['image']['path']='../../etc/passwd'
        with self.assertRaisesRegex(ValueError,'image.path'):CB.save(self.project,bad)
        with self.assertRaisesRegex(ValueError,'valid supported image'):CB.upload(self.project,{'name':'bad.png','data':'c2NyaXB0'})
        avif=(SOURCE/'assets/main-pics/sample.avif').read_bytes()
        result=CB.upload(self.project,{'name':'phone.avif','data':base64.b64encode(avif).decode()})
        self.assertTrue(result['path'].endswith('.avif'))
        with self.assertRaisesRegex(ValueError,'AVIF'):
            CB.upload(self.project,{'name':'fake.avif','data':base64.b64encode(b'\x00\x00\x00\x18ftypavif' + b'\x00'*16).decode()})
    def test_symlink_images_are_excluded(self):
        external=Path(self.tmp.name).parent/'not-an-image.png'
        try:
            (self.root/'assets/product-images/escape.png').symlink_to(external)
        except OSError as exc:
            if sys.platform!='win32' or getattr(exc,'winerror',None)!=1314: raise
            self.skipTest(f'Windows symlink permission is required: {exc}')
        self.assertFalse(any(item['path'].endswith('escape.png') for item in CB.images(self.project)))
    def test_edit_upload_reorder_category_and_draft_round_trip(self):
        picture=Image.new('RGB',(12,12),'red');stream=io.BytesIO();picture.save(stream,format='PNG')
        upload={'name':'Phone Photo.png','data':base64.b64encode(stream.getvalue()).decode()}
        first=CB.upload(self.project,upload)['path'];second=CB.upload(self.project,upload)['path']
        self.assertNotEqual(first,second)
        snap=CB.snapshot(self.project);model=copy.deepcopy(snap)
        mounts=model['products']['mounts'];mounts['title']['ka']='სამაგრები ახალი';mounts['price']={'mode':'fixed','amount':25,'currency':'GEL'};mounts['image']['path']=first
        draft=copy.deepcopy(mounts);draft.update(id='draft-one',slug='draft-one',visible=False,destination={'mode':'none'})
        model['products']['draft-one']=draft
        category={'id':'mount-group','slug':'mount-group','title':{'ka':'ჯგუფი'},'image':first,'visible':True,'priceMode':'from','entries':[{'type':'product','id':'mounts'},{'type':'product','id':'draft-one'}]}
        model['catalog']['categories']=[category]
        model['catalog']['root']=[{'type':'category','id':'mount-group'},{'type':'product','id':'mounts'}]
        CB.save(self.project,model)
        current=CB.snapshot(self.project)
        self.assertEqual(current['catalog']['root'][0]['id'],'mount-group')
        self.assertEqual(current['products']['mounts']['image']['path'],first)
        html=(self.root/'products.html').read_text(encoding='utf-8')
        self.assertIn('სამაგრები ახალი',html);self.assertIn('25 ₾',html);self.assertNotIn('draft-one.html',html)
        self.assertTrue((self.root/'catalog-mount-group.html').is_file())
        current['products']['mounts']['visible']=False;CB.save(self.project,current)
        self.assertNotIn('სამაგრები ახალი',(self.root/'catalog-mount-group.html').read_text(encoding='utf-8'))
        restored=CB.snapshot(self.project);restored['products']['mounts']['visible']=True;CB.save(self.project,restored)
        self.assertIn('სამაგრები ახალი',(self.root/'catalog-mount-group.html').read_text(encoding='utf-8'))
    def test_private_routes_scope_csrf_and_conflict(self):
        other=SimpleNamespace(name='Other',path=self.root)
        def request(method,path,body=None,origin=None,token=None):
            handler=server.Handler.__new__(server.Handler);handler.path=path
            handler.headers={'Host':'127.0.0.1'};handler.wfile=BytesIO();handler.rfile=BytesIO(json.dumps(body or {}).encode())
            response={};handler.send_response=lambda status:response.update(status=status)
            handler.send_header=lambda *args:None;handler.end_headers=lambda:None
            if method=='POST':
                handler.headers.update({'Content-Type':'application/json','Content-Length':str(len(handler.rfile.getvalue())),'X-Linko-CSRF':token or ''})
                if origin:handler.headers['Origin']=origin
                handler.do_POST()
            else:handler.do_GET()
            return response['status'],json.loads(handler.wfile.getvalue())
        with patch.dict(server.PROJECTS,{'Fixture':self.project,'Other':other},clear=True),patch.object(CB,'enabled',side_effect=lambda p:p.name=='Fixture'):
            status,snap=request('GET','/api/catalogue?project=Fixture');self.assertEqual(status,200)
            self.assertEqual(request('GET','/api/catalogue?project=Other')[0],400)
            body={'project':'Fixture','revision':snap['revision'],'catalog':snap['catalog'],'products':snap['products']}
            self.assertEqual(request('POST','/api/catalogue/save',body,token='wrong')[0],403)
            self.assertEqual(request('POST','/api/catalogue/save',body,origin='http://evil.invalid',token=server.CSRF_TOKEN)[0],403)
            self.assertEqual(request('POST','/api/catalogue/save',body,token=server.CSRF_TOKEN)[0],200)
            (self.root/'data/products/mounts.json').write_text((self.root/'data/products/mounts.json').read_text(encoding='utf-8')+' ',encoding='utf-8')
            self.assertEqual(request('POST','/api/catalogue/save',body,token=server.CSRF_TOKEN)[0],409)
    def test_watcher_skips_output_already_built_by_save(self):
        process=subprocess.Popen([sys.executable,'-c',
            'import sys; from pathlib import Path; from catalogue_backend import engine; engine(Path(sys.argv[1])).watch()',
            str(self.root)],cwd=Path(__file__).resolve().parents[1],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        self.addCleanup(lambda:(process.terminate(),process.wait(timeout=3)) if process.poll() is None else None)
        time.sleep(.3)
        self.assertIsNone(process.poll(),'Catalogue watcher failed to start')
        snap=CB.snapshot(self.project);snap['products']['mounts']['title']['ka']='ახალი სახელი';CB.save(self.project,snap)
        output=self.root/'products.html';built=output.stat().st_mtime_ns
        time.sleep(1)
        self.assertIsNone(process.poll(),'Catalogue watcher exited unexpectedly')
        self.assertEqual(output.stat().st_mtime_ns,built)

if __name__=='__main__':unittest.main()
