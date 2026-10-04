"""Exercise the current sibling Linko generator through the actual save backend.

All content and output live in a temporary fixture; real product JSON is never saved.
The historical fixture suite separately verifies support for older Linko checkouts.
"""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import catalogue_backend as backend

SOURCE = Path(__file__).resolve().parents[2] / 'Linko'

@unittest.skipUnless((SOURCE / 'product-detail.js').exists(), 'Current Linko checkout required')
class DetailWorkflowTests(unittest.TestCase):
    def test_save_reopen_generate_and_preserve_catalogue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('catalogue.py', 'sitemap.py', 'templates/products.html', 'assets/product-images/mounts.svg'):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(SOURCE / name, target)
            (root / 'data/products').mkdir(parents=True)
            # Use fixed content: live product translations may be incomplete,
            # which intentionally makes the current generator fall back to ka.
            product = json.loads((Path(__file__).parent / 'fixtures/linko/data/products/mounts.json').read_text())
            product.update(destination={'mode':'generated'}, detailReady=True, visible=True)
            product['image'].update(path='assets/product-images/mounts.svg')
            product['image'].pop('secondary',None)
            product['gallery'] = []
            product['preservedField'] = {'unknown':'keep this'}
            product['title'].update(en='Mounts',ru='Крепления')
            (root/'data/products/mounts.json').write_text(json.dumps(product))
            catalog = {'version':1,'categories':[],'root':[{'type':'product','id':'mounts'}]}
            (root/'data/catalog.json').write_text(json.dumps(catalog))
            project = SimpleNamespace(name='Fixture',path=root,catalogue=True)
            backend.engine(root).generate()
            before = (root/'products.html').read_bytes()
            state = backend.snapshot(project)
            p = state['products']['mounts']
            p['description'] = [{'heading':{'ka':'სათაური','en':'Heading','ru':'Заголовок'}, 'body':{'ka':'პირველი ხაზი\nმეორე ხაზი\n\n**მუქი**\n- ერთი\n- ორი','en':'**Bold**\n\n- One\n- Two','ru':'**Текст**'}}]
            p['priceNote'] = {'ka':'შენიშვნა','en':'Price note','ru':'Примечание'}
            p['specifications'] = [{'label':{'ka':'ფერი','en':'Colour','ru':'Цвет'},'value':{'ka':'შავი','en':'Black','ru':'Чёрный'}}]
            p['gallery'] = ['assets/product-images/mounts.svg',{'path':'assets/product-images/mounts.svg','alt':{'ka':'სურათი','en':'Alt text','ru':'Фото'}}]
            p['included'] = [{'ka':'ნაწილი','en':'Part','ru':'Деталь'}]
            expected = copy.deepcopy(p)
            backend.save(project,state)
            reopened = backend.snapshot(project)
            self.assertEqual(reopened['products']['mounts'],expected)
            self.assertEqual((root/'products.html').read_bytes(),before)
            html = (root/'product-mounts.html').read_text()
            for text in ('product-detail.css','<strong>Bold</strong>','<li>One</li>','Colour','Black','Alt text','Заголовок','<br>','Price note'):
                self.assertIn(text,html)
            self.assertEqual(backend.engine(root).generate(check=True),[])
            # Simultaneous catalogue changes survive the same save transaction.
            reopened['products']['mounts']['title']['ka']='განახლებული'
            reopened['products']['mounts']['price']={'mode':'fixed','amount':123,'currency':'GEL'}
            draft=copy.deepcopy(reopened['products']['mounts']);draft.update(id='draft-one',slug='draft-one',visible=False,destination={'mode':'none'},detailReady=False)
            reopened['products']['draft-one']=draft
            reopened['catalog']['root'].insert(0,{'type':'product','id':'draft-one'})
            backend.save(project,reopened)
            again=backend.snapshot(project)
            self.assertEqual(again['catalog']['root'][0]['id'],'draft-one')
            self.assertEqual(again['products']['mounts']['description'],expected['description'])
            page=(root/'products.html').read_text()
            self.assertIn('განახლებული',page);self.assertIn('123 ₾',page)
            self.assertIn('product-mounts.html',page);self.assertNotIn('product-draft-one.html',page)
