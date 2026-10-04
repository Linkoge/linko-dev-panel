"""Disposable current-Linko catalogue for backend and live browser checks."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import catalogue_backend as backend
from PIL import Image

SOURCE = Path(os.environ.get('PANEL_IMAGE_SOURCE', Path(__file__).resolve().parents[2] / 'Linko'))


def create(root):
    for name in ('catalogue.py', 'sitemap.py', 'templates/products.html', 'product-detail.js',
                 'product-detail.css', 'products.css', 'products.js', 'site-language.js', 'style.css',
                 'assets/product-images/mounts.svg'):
        target = root/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(SOURCE/name, target)
    (root/'data/products').mkdir(parents=True)
    source = SOURCE/'data/products/P05.json'
    if not source.exists(): source = SOURCE/'data/products/mounts.json'
    p = json.loads(source.read_text())
    p.update(id='mounts', slug='mounts')  # Stable legacy fixture also exercises old-schema compatibility.
    p.update(destination={'mode':'generated'}, detailReady=True, visible=True, gallery=[])
    p['image']['path'] = 'assets/product-images/mounts.svg'
    p['image'].pop('secondary', None)
    p['unknownField'] = {'preserve':True}
    (root/'data/products/mounts.json').write_text(json.dumps(p))
    (root/'data/catalog.json').write_text(json.dumps({'version':1, 'root':[{'type':'product','id':'mounts'}], 'categories':[]}))
    for name, size in [('portrait.png',(80,240)), ('landscape.png',(400,100)), ('square.png',(160,160))]:
        Image.new('RGB', size, '#739abb').save(root/'assets/product-images'/name)
    project = SimpleNamespace(name='Images',path=root,catalogue=True)
    backend.engine(root).generate()
    return project


if __name__ == '__main__':
    import server
    with tempfile.TemporaryDirectory(prefix='panel-images-') as directory:
        root = Path(directory)
        project = create(root)
        subprocess.run(['git','init','-b','main',str(root)],check=True,capture_output=True)
        subprocess.run(['git','add','.'],cwd=root,check=True,capture_output=True)
        subprocess.run(['git','-c','user.name=Test','-c','user.email=test@example.invalid','commit','-m','Image fixture'],cwd=root,check=True,capture_output=True)
        config = root/'projects.json'
        config.write_text(json.dumps({'projects':{'Images':{'path':str(root),'remote':None,'preview':'products.html','catalogue':True}}}))
        server.initialize_projects(config)
        server.HOST='127.0.0.1'
        http = server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        def stop(*_): raise KeyboardInterrupt
        signal.signal(signal.SIGTERM,stop)
        print(json.dumps({'port':http.server_port,'root':str(root)}),flush=True)
        try: http.serve_forever()
        except KeyboardInterrupt: pass
        finally:
            server.CLONES.shutdown()
            http.server_close()
