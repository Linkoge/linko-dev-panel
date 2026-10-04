import copy
import json
import tempfile
import unittest
from pathlib import Path
import catalogue_backend as backend
from product_images_fixture import create, SOURCE


@unittest.skipUnless((SOURCE/'product-detail.js').is_file(), 'Current Linko checkout required')
class ProductImagesTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name);self.project=create(self.root)

    def canonical(self, state):
        p=state['products']['mounts']
        p['images']=backend.engine(self.root).product_images(p)
        del p['image'];del p['gallery']
        return p

    def test_legacy_load_render_and_unedited_save_preserve_source(self):
        before=(self.root/'data/products/mounts.json').read_bytes()
        state=backend.snapshot(self.project)
        self.assertIn('image',state['products']['mounts'])
        page=(self.root/'product-mounts.html').read_text()
        self.assertIn('assets/product-images/mounts.svg',page)
        self.assertNotIn('class="detail-thumbs"',page)
        backend.save(self.project,state)
        p=json.loads((self.root/'data/products/mounts.json').read_text())
        self.assertEqual(p,json.loads(before))

    def test_multiple_save_reload_reorder_remove_and_primary(self):
        state=backend.snapshot(self.project);p=self.canonical(state)
        original=copy.deepcopy(p['images'][0]);p['images'] += [
            {'path':'assets/product-images/portrait.png','alt':{'ka':'portrait'},'width':80,'height':240},
            {'path':'assets/product-images/landscape.png','alt':{'ka':'wide'},'width':400,'height':100}]
        backend.save(self.project,state);again=backend.snapshot(self.project)
        self.assertEqual(again['products']['mounts']['images'],p['images'])
        self.assertEqual(again['products']['mounts']['images'][0],original)
        q=again['products']['mounts'];q['images'].insert(0,q['images'].pop(2))
        backend.save(self.project,again);reloaded=backend.snapshot(self.project)
        self.assertEqual(reloaded['products']['mounts']['images'],q['images'])
        cards=(self.root/'products.html').read_text();detail=(self.root/'product-mounts.html').read_text()
        self.assertIn('assets/product-images/landscape.png',cards)
        self.assertNotIn('assets/product-images/portrait.png',cards)
        self.assertIn('data-photo="2"',detail)
        q=reloaded['products']['mounts'];q['images'].pop(1)
        backend.save(self.project,reloaded)
        self.assertTrue((self.root/'assets/product-images/mounts.svg').exists())
        self.assertEqual(backend.engine(self.root).generate(check=True),[])
        self.assertEqual(q['unknownField'],{'preserve':True})

    def test_legacy_secondary_and_gallery_accessor_preserves_order_metadata(self):
        p=backend.snapshot(self.project)['products']['mounts']
        p['image']['secondary']='assets/product-images/portrait.png'
        p['gallery']=['assets/product-images/landscape.png',{'path':'assets/product-images/square.png','alt':{'ka':'square'},'extra':'keep'}]
        ordered=backend.engine(self.root).product_images(p)
        self.assertEqual([i['path'] for i in ordered],[p['image']['path'],p['image']['secondary'],p['gallery'][0],p['gallery'][1]['path']])
        self.assertEqual(ordered[-1]['extra'],'keep')
        self.assertEqual(ordered[0]['alt'],p['image']['alt'])

    def test_missing_secondary_allowed_but_unsafe_or_missing_primary_rejected(self):
        state=backend.snapshot(self.project);p=self.canonical(state)
        p['images'].append({'path':'assets/product-images/unavailable.png','alt':{'ka':''}})
        backend.save(self.project,state)
        for path in ('assets/product-images/../../escape.png','/etc/passwd','assets/product-images/.hidden.png'):
            bad=backend.snapshot(self.project);bad['products']['mounts']['images'][1]['path']=path
            with self.assertRaises(ValueError):backend.save(self.project,bad)
        bad=backend.snapshot(self.project);bad['products']['mounts']['images'].reverse()
        with self.assertRaisesRegex(ValueError,'images\\[0\\].path'):backend.save(self.project,bad)

    def test_invalid_array_never_writes(self):
        for images in ([], 'path', [None], [{'path':'assets/product-images/mounts.svg','alt':{'ka':''},'width':False}]):
            state=backend.snapshot(self.project);p=self.canonical(state);p['images']=images
            before=(self.root/'data/products/mounts.json').read_bytes()
            with self.assertRaises(ValueError):backend.save(self.project,state)
            self.assertEqual((self.root/'data/products/mounts.json').read_bytes(),before)

    def test_no_duplicate_legacy_state_and_shared_reference_removal(self):
        state=backend.snapshot(self.project);p=self.canonical(state)
        other=copy.deepcopy(p);other.update(id='shared',slug='shared');state['products']['shared']=other
        p['images'].append({'path':'assets/product-images/square.png','alt':{'ka':''}})
        backend.save(self.project,state)
        state=backend.snapshot(self.project);state['products']['mounts']['images'].pop(0);backend.save(self.project,state)
        self.assertTrue((self.root/'assets/product-images/mounts.svg').exists())
        self.assertIn('assets/product-images/mounts.svg',(self.root/'product-shared.html').read_text())
        bad=backend.snapshot(self.project);bad['products']['mounts']['image']=other['images'][0]
        with self.assertRaisesRegex(ValueError,'legacy'):backend.save(self.project,bad)
