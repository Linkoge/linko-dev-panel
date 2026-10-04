"""Disposable migrated catalogue and real panel server for routing/editor browser tests."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import catalogue_backend as backend
from repository import Project

SOURCE = Path(__file__).resolve().parents[2]/'Linko'

def create(root, git=True):
    for relative in ('catalogue.py','sitemap.py','build.py','templates/products.html','templates/home.html','templates/contact.html',
                     'functions/_middleware.js','data/catalog.json','data/page-translations.json','.gitignore',
                     'site-language.js','products.js','product-detail.js','products.css','product-detail.css','style.css',
                     'contact.css','contact.js','scrolly.css','scrolly.js','footer-ocean.js','satellite-mesh-animation.js','1process-animations.js',
                     'assets/logo-white.svg','assets/product-images/mounts.svg','assets/vendor/three/r128/three.min.js',
                     'fonts/akolkhetih.woff2','fonts/eka.woff2','fonts/zaza.woff2','assets/main-pics/litebeam/background.jpg'):
        target=root/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy(SOURCE/relative,target)
    (root/'data/products').mkdir(parents=True,exist_ok=True)
    for source in (SOURCE/'data/products').glob('*.json'):
        shutil.copy(source,root/'data/products'/source.name)
    project=Project('Routing',root,None,'index.html',(),True)
    model=backend.engine(root)
    for source in (root/'data/products').glob('*.json'):
        product=json.loads(source.read_text())
        for image in model.product_images(product):
            relative=image['path'];target=root/relative
            if (SOURCE/relative).is_file() and not target.exists():
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copy(SOURCE/relative,target)
    # Homepage imagery and SVG animation dependencies referenced by active sources.
    for relative in ('assets/main-pics/hero-mobile.avif','assets/main-pics/hero-dekstop.avif','assets/main-pics/hero-original.avif',
                     'assets/main-pics/starlink-home.avif','assets/main-pics/litebeam/beam.svg','assets/paper/clip.avif','assets/paper/photo.avif'):
        target=root/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy(SOURCE/relative,target)
    model.generate()
    if git:
        subprocess.run(['git','init','-b','main',str(root)],check=True,capture_output=True)
        project.run('config','user.name','Test');project.run('config','user.email','test@example.invalid')
        project.commit('Migrated catalogue fixture')
    return project

if __name__=='__main__':
    import server
    with tempfile.TemporaryDirectory(prefix='linko-routing-') as directory:
        root=Path(directory);project=create(root)
        config=root.parent/(root.name+'-config.json')
        config.write_text(json.dumps({'projects':{'Routing':{'path':str(root),'remote':None,'preview':'index.html','catalogue':True}}}))
        server.initialize_projects(config);server.HOST='127.0.0.1'
        http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        def stop(*_): raise KeyboardInterrupt
        signal.signal(signal.SIGTERM,stop)
        print(json.dumps({'port':http.server_port,'root':str(root)}),flush=True)
        try: http.serve_forever()
        except KeyboardInterrupt: pass
        finally: server.CLONES.shutdown();http.server_close();config.unlink(missing_ok=True)
