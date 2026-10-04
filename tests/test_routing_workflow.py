import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import catalogue_backend as backend
from routing_fixture import create


class RoutingWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.project=create(self.root)

    def draft(self, state, key='draft-new-product', kind='product'):
        draft=copy.deepcopy(state['products']['P01'])
        draft.update(id=key,kind=kind,slug='',visible=False,detailReady=False,destination={'mode':'none'},title={'ka':'ახალი','en':'New equipment'})
        state['products'][key]=draft
        state['catalog']['root'].append({'type':'product','id':key})

    def test_save_generate_allocation_edit_reorder_slug_hide_publish(self):
        initial=backend.snapshot(self.project)
        state=copy.deepcopy(initial)
        self.draft(state)
        self.draft(state,'draft-new-service','service')
        result=backend.save(self.project,state)
        self.assertEqual(result['assignedIds'],{'draft-new-product':'P08','draft-new-service':'S03'})
        self.assertTrue((self.root/'data/products/P08.json').exists())
        reopened=backend.snapshot(self.project)
        self.assertEqual(set(reopened['products']),set(initial['products'])|{'P08','S03'})
        reopened['catalog']['root'].reverse()
        p=reopened['products']['P01']
        p['slug']='renamed-standard-kit';p['title']['ka']='ახალი სახელი';p['price']['amount']=123
        p['visible']=False;p['description'].append({'body':{'ka':'ახალი აღწერა'}})
        result=backend.save(self.project,reopened)
        self.assertEqual(result['products']['P01']['id'],'P01')
        self.assertEqual(result['catalog']['root'][0]['id'],'S03')
        self.assertEqual(result['catalog']['aliases']['/products/P01-starlink-standard-4x'],'P01')
        self.assertFalse((self.root/'products/P01-starlink-standard-4x.html').exists())
        self.assertIn('noindex, follow',(self.root/'products/P01-renamed-standard-kit.html').read_text())
        state=backend.snapshot(self.project)
        state['products']['P08'].update(visible=True,detailReady=True,destination={'mode':'generated'})
        backend.save(self.project,state)
        self.assertTrue((self.root/'products/P08-new-equipment.html').exists())
        self.assertEqual(backend.engine(self.root).generate(check=True),[])
        with self.assertRaises(backend.ConflictError):backend.save(self.project,reopened)

    def test_invalid_save_immutable_namespace_identity_and_registry(self):
        for mutate in [lambda s:s['products']['P01'].update(id='P99'),
                       lambda s:s['products']['P01'].update(kind='service'),
                       lambda s:s['products']['P01'].update(slug='ქართული'),
                       lambda s:s['products'].pop('P01')]:
            state=backend.snapshot(self.project)
            before={p.relative_to(self.root).as_posix():p.read_bytes() for p in backend.files(self.root)}
            mutate(state)
            with self.assertRaises(ValueError):backend.save(self.project,state)
            self.assertEqual(before,{p.relative_to(self.root).as_posix():p.read_bytes() for p in backend.files(self.root)})
        state=backend.snapshot(self.project)
        self.draft(state)
        state['products']['draft-new-product']['price']['amount']=-1
        with self.assertRaises(ValueError):backend.save(self.project,state)
        state['products']['draft-new-product']['price']['amount']=1
        self.assertEqual(backend.save(self.project,state)['assignedIds']['draft-new-product'],'P08')

    def test_restore_preserves_ids_aliases_and_retired_numbers(self):
        baseline=self.project.head()
        state=backend.snapshot(self.project)
        state['products']['P01']['slug']='changed-before-restore'
        self.draft(state)
        backend.save(self.project,state)
        self.project.commit('Edit product and create P08')
        self.project.restore_version(baseline)
        restored=backend.snapshot(self.project)
        self.assertEqual(restored['products']['P01']['slug'],'starlink-standard-4x')
        self.assertNotIn('P08',restored['products'])
        self.assertIn('P08',restored['catalog']['identity']['issued'])
        self.assertEqual(restored['catalog']['aliases']['/products/P01-changed-before-restore'],'P01')
        self.draft(restored)
        self.assertEqual(backend.save(self.project,restored)['assignedIds']['draft-new-product'],'P09')
        self.assertEqual(backend.engine(self.root).generate(check=True),[])

    def test_restore_pre_migration_content_keeps_permanent_identity(self):
        modern=self.project.head()
        historical=json.loads((self.root/'data/products/P01.json').read_text())
        historical.update(id='starlink-device',slug='starlink-device')
        historical['title']['ka']='ისტორიული მოწყობილობა'
        for path in (self.root/'data/products').glob('*.json'):path.unlink()
        (self.root/'data/products/starlink-device.json').write_text(json.dumps(historical))
        (self.root/'data/catalog.json').write_text(json.dumps({'version':1,'root':[{'type':'product','id':'starlink-device'}],'categories':[]}))
        self.project.commit('Historical pre-migration content fixture')
        legacy=self.project.head()
        self.project.run('restore','--source='+modern,'--staged','--worktree','--',':/')
        self.project.commit('Return to modern catalogue')
        self.project.restore_version(legacy)
        restored=backend.snapshot(self.project)
        self.assertEqual(set(restored['products']),{'P01'})
        self.assertEqual(restored['products']['P01']['title']['ka'],'ისტორიული მოწყობილობა')
        self.assertEqual(restored['products']['P01']['slug'],'starlink-standard-4x')
        self.assertEqual(restored['catalog']['root'],[{'type':'product','id':'P01'}])
        self.assertIn('P07',restored['catalog']['identity']['issued'])
        self.draft(restored)
        self.assertEqual(backend.save(self.project,restored)['assignedIds']['draft-new-product'],'P08')

    def test_discard_rollback_and_history_recovery_do_not_recycle(self):
        baseline=self.project.head()
        state=backend.snapshot(self.project)
        self.draft(state)
        backend.save(self.project,state)
        # Simulate discarding all unsaved source/output changes in this disposable repository.
        self.project.run('restore','--source='+baseline,'--staged','--worktree','--',':/')
        self.project.run('clean','-fd')
        state=backend.snapshot(self.project)
        self.draft(state)
        self.assertEqual(backend.save(self.project,state)['assignedIds']['draft-new-product'],'P09')
        self.project.commit('Save next identity')
        (self.root/'.catalogue-identities.json').unlink()
        state=backend.snapshot(self.project)
        self.draft(state)
        self.assertEqual(backend.save(self.project,state)['assignedIds']['draft-new-product'],'P10')

    def test_detached_history_cannot_save_or_allocate(self):
        self.project.run('switch','--detach',self.project.head())
        state=backend.snapshot(self.project)
        self.assertTrue(state['readOnly'])
        self.draft(state)
        with self.assertRaisesRegex(ValueError,'read-only'):backend.save(self.project,state)
        self.assertFalse((self.root/'.catalogue-identities.json').exists())

    def test_failed_source_write_preserves_content_and_reserves_issued_number(self):
        state=backend.snapshot(self.project)
        self.draft(state)
        before={p.relative_to(self.root).as_posix():p.read_bytes() for p in backend.files(self.root)}
        original=backend._atomic
        calls=0
        def fail_once(path,data,root):
            nonlocal calls
            calls+=1
            if calls==2:raise OSError('simulated disk failure')
            return original(path,data,root)
        with patch.object(backend,'_atomic',side_effect=fail_once):
            with self.assertRaisesRegex(OSError,'disk failure'):backend.save(self.project,state)
        self.assertEqual(before,{p.relative_to(self.root).as_posix():p.read_bytes() for p in backend.files(self.root)})
        self.assertEqual(backend.engine(self.root).generate(check=True),[])
        self.assertEqual(backend.save(self.project,state)['assignedIds']['draft-new-product'],'P09')

    def test_preview_routes_languages_aliases_unknown_and_historical(self):
        examples={'products':('products.html',None),
                  'en/':('en/index.html',None),
                  'ru/products/P01-starlink-standard-4x':('ru/products/P01-starlink-standard-4x.html',None),
                  'product-starlink-device':('products/P01-starlink-standard-4x.html','/products/P01-starlink-standard-4x'),
                  'products/P01':('products/P01-starlink-standard-4x.html','/products/P01-starlink-standard-4x'),
                  'en/products.html':('en/products.html','/en/products')}
        for relative,expected in examples.items():
            self.assertEqual(backend.preview_route(self.project,relative),expected)
            self.assertEqual(backend.preview_route(self.project,relative,commit=self.project.head()),expected)
        self.assertEqual(backend.preview_route(self.project,'products','lang=en&utm_source=old'),('en/products.html','/en/products?utm_source=old'))
        self.assertEqual(backend.preview_route(self.project,'en/products','lang=ru'),('en/products.html','/en/products'))
        self.assertEqual(backend.preview_route(self.project,'products/P99999-unknown'),('products/P99999-unknown',None))


if __name__=='__main__':unittest.main()
