"""Private, project-scoped catalogue operations for the Dev Panel."""
from __future__ import annotations
import base64
import hashlib
import io
import json
import os
import re
import tempfile
import threading
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from catalogue_compat import load_engine
from repository import preview_url
from urllib.parse import parse_qs, urlencode

_LOCK = threading.RLock()
_ID = re.compile(r'^[a-z][a-z0-9-]{1,63}$')
_IMAGE_EXT = {'.avif','.webp','.jpg','.jpeg','.png','.svg','.gif'}
_UPLOAD_FORMATS = {'JPEG':'.jpg','PNG':'.png','WEBP':'.webp','AVIF':'.avif','GIF':'.gif'}

class ConflictError(ValueError):
    """The editor loaded an older revision."""

def _avif_dimensions(payload):
    """Check the AVIF container and its image dimensions when Pillow lacks AVIF."""
    offset=0; boxes={}; end=len(payload)
    while offset+8<=end:
        size=int.from_bytes(payload[offset:offset+4],'big'); kind=payload[offset+4:offset+8]
        header=8
        if size==1 and offset+16<=end:
            size=int.from_bytes(payload[offset+8:offset+16],'big');header=16
        elif size==0: size=end-offset
        if size<header or offset+size>end: raise ValueError('Invalid AVIF container.')
        boxes.setdefault(kind,(offset,offset+size))
        offset+=size
    if offset!=end or payload[4:8]!=b'ftyp' or b'ftyp' not in boxes or b'meta' not in boxes or b'mdat' not in boxes:
        raise ValueError('Invalid AVIF container.')
    fstart,fend=boxes[b'ftyp'];brands=[payload[i:i+4] for i in range(fstart+8,fend,4)]
    if not any(brand in (b'avif',b'avis') for brand in brands): raise ValueError('File is not an AVIF image.')
    mstart,mend=boxes[b'meta'];index=payload.find(b'ispe',mstart,mend)
    if index<4 or index+16>mend or int.from_bytes(payload[index-4:index],'big')<20: raise ValueError('AVIF dimensions are missing.')
    width=int.from_bytes(payload[index+8:index+12],'big');height=int.from_bytes(payload[index+12:index+16],'big')
    if width<1 or height<1 or width*height>40_000_000: raise ValueError('Image dimensions are unsupported.')
    return width,height

def _image_format(payload):
    if len(payload)>12 and payload[4:8]==b'ftyp':
        width,height=_avif_dimensions(payload)
        return 'AVIF',width,height
    try:
        with Image.open(io.BytesIO(payload)) as img:
            fmt=img.format
            if fmt not in _UPLOAD_FORMATS: raise ValueError('Unsupported image format. Use JPEG, PNG, WebP, AVIF or GIF.')
            if img.width<1 or img.height<1 or img.width*img.height>40_000_000: raise ValueError('Image dimensions are unsupported.')
            img.verify()
            return fmt,img.width,img.height
    except (UnidentifiedImageError,OSError) as exc: raise ValueError('File is not a valid supported image.') from exc

def enabled(project):
    return getattr(project,'catalogue',False) is True and (project.path/'catalogue.py').is_file()

def require(project):
    if not enabled(project): raise ValueError('Catalogue is unavailable for this project.')
    return project.path

def engine(root):
    return load_engine(root)

def files(root):
    product_dir=root/'data/products'
    if product_dir.is_symlink() or not product_dir.resolve().is_relative_to(root): raise ValueError('Unsafe products directory.')
    paths=[root/'data/catalog.json',*sorted(product_dir.glob('*.json'))]
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(root): raise ValueError('Unsafe catalogue file.')
    return paths

def revision(root):
    digest=hashlib.sha256()
    for path in files(root):
        digest.update(path.relative_to(root).as_posix().encode('utf-8'));digest.update(b'\0');digest.update(path.read_bytes());digest.update(b'\0')
    return digest.hexdigest()

def snapshot(project):
    root=require(project)
    with _LOCK:
        model=engine(root)
        catalog,products,_=model.load()
        result = {'catalog':catalog,'products':products,'revision':revision(root),
                  'previewUrl':preview_url(project.name,'products.html')}
        if catalog.get('version') == 2:
            result['routes'] = model.route_metadata(catalog, products)
            result['readOnly'] = hasattr(project, 'branch') and project.branch() is None
        return result

def images(project, term=''):
    root=require(project)
    term=str(term).casefold()[:80]
    result=[]
    for folder in ('assets/main-pics','assets/product-images'):
        base=root/folder
        if base.is_symlink() or not base.resolve().is_relative_to(root): continue
        for path in sorted(base.rglob('*')):
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root) or path.suffix.lower() not in _IMAGE_EXT: continue
            if 'old' in path.parts: continue
            relative=path.relative_to(root).as_posix()
            if term not in relative.casefold(): continue
            try: url=preview_url(project.name,relative)
            except ValueError: continue
            result.append({'path':relative,'name':path.name,'url':url})
    return result[:500]

def _atomic(path, data, root):
    if path.is_symlink() or not path.parent.resolve().is_relative_to(root):
        raise ValueError('Unsafe catalogue path.')
    fd,temp=tempfile.mkstemp(prefix='.catalogue-save-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as out: out.write(data);out.flush();os.fsync(out.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp): os.unlink(temp)

def save(project,body):
    root=require(project)
    model=engine(root)
    with _LOCK, model.build_lock():
        if (root/'.git').exists() and hasattr(project, 'branch') and project.branch() is None:
            raise ValueError('Historical catalogue views are read-only. Return to the current branch to edit.')
        if body.get('revision')!=revision(root): raise ConflictError('Catalogue changed since this editor loaded. Reload and review your changes.')
        catalog=body.get('catalog');products=body.get('products')
        if not isinstance(products,dict) or len(products)>500: raise ValueError('products must be an object of at most 500 entries.')
        assignments, identity = {}, None
        previous_catalog, previous_products, _ = model.load()
        if previous_catalog.get('version') == 2:
            catalog, products, assignments, identity = model.prepare_save(catalog,products,previous_catalog,previous_products)
        else:
            for id in products:
                if not isinstance(id,str) or not _ID.fullmatch(id): raise ValueError('Invalid product ID.')
        prior={p.stem for p in files(root)[1:]}
        if not prior.issubset(products): raise ValueError('Permanent deletion is unavailable; hide a product instead.')
        model.render(catalog,products)  # Validate every proposed field before any write.
        if body.get('revision')!=revision(root): raise ConflictError('Catalogue changed during validation. Reload and review your changes.')
        # Persist issuance before source writes; failed writes may leave gaps but never recycle IDs.
        if identity is not None: model.remember_identity(identity)
        prepared={root/'data/catalog.json':(json.dumps(catalog,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()}
        for id,p in products.items(): prepared[root/'data/products'/f'{id}.json']=(json.dumps(p,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
        before={path:path.read_bytes() if path.exists() else None for path in prepared}
        try:
            for path,data in prepared.items(): _atomic(path,data,root)
            changed=model.generate(locked=True)
        except Exception:
            for path,data in before.items():
                if data is None: path.unlink(missing_ok=True)
                else: _atomic(path,data,root)
            raise
        result = {'revision':revision(root),'generated':changed}
        if catalog.get('version') == 2:
            result.update(catalog=catalog,products=products,assignedIds=assignments,routes=model.route_metadata(catalog,products))
        return result

def upload(project,body):
    root=require(project)
    name=body.get('name');encoded=body.get('data')
    if not isinstance(name,str) or len(name)>200 or not isinstance(encoded,str): raise ValueError('Upload needs a filename and image data.')
    try: payload=base64.b64decode(encoded,validate=True)
    except Exception as exc: raise ValueError('Invalid image encoding.') from exc
    if not payload or len(payload)>8_000_000: raise ValueError('Image must be 8 MB or smaller.')
    fmt,width,height=_image_format(payload)
    folder=root/'assets/product-images'
    if folder.is_symlink() or not folder.resolve().is_relative_to(root): raise ValueError('Unsafe image directory.')
    stem=re.sub(r'[^a-z0-9-]+','-',Path(name).stem.lower()).strip('-')[:48] or 'image'
    if stem in {'con','prn','aux','nul'} or re.fullmatch(r'(com|lpt)[1-9]',stem): stem='image-'+stem
    with _LOCK:
        folder.mkdir(parents=True,exist_ok=True)
        for n in range(10000):
            filename=f'{stem}{"-"+str(n) if n else ""}{_UPLOAD_FORMATS[fmt]}'
            target=folder/filename
            try:
                with target.open('xb') as out: out.write(payload)
                return {'path':target.relative_to(root).as_posix(),'url':preview_url(project.name,target.relative_to(root)),
                        'width':width,'height':height}
            except FileExistsError: continue
    raise ValueError('Unable to choose a unique image filename.')

def preview_route(project, relative, query='', commit=None):
    """Return (repository file, canonical preview path), using that version's route map."""
    try:
        if commit:
            routes = json.loads(project.blob(commit,'data/site-routes.json'))
        else:
            path = project.path/'data/site-routes.json'
            if path.is_symlink(): raise ValueError('Unsafe preview route map.')
            routes = json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return relative, None  # Older checkouts retain their existing file previews.
    path = '/'+relative
    prefix = re.match(r'^/(en|ru)(?=/|$)', path)
    language = prefix[1] if prefix else 'ka'
    if prefix: path = path[len(prefix[0]):] or '/'
    if path.endswith('/index.html'): path = path[:-10]
    elif path.endswith('.html'): path = path[:-5]
    if path != '/': path = path.rstrip('/')
    path = routes.get('pageAliases',{}).get(path,path)
    if path in routes['aliases']:
        path = routes['items'].get(routes['aliases'][path])
        if not path: return relative, None
    item = re.fullmatch(r'/(products|services)/([PS][0-9]+)(?:-[a-z0-9-]+)?',path)
    if item:
        current = routes['items'].get(item[2])
        if not current or not current.startswith('/'+item[1]+'/'): return relative, None
        path = current
    params = parse_qs(query,keep_blank_values=True)
    if path in routes['localized']:
        requested = params.get('lang',[''])[0]
        if not prefix and requested in ('ka','en','ru'): language = requested
        path = ('' if language == 'ka' else '/'+language)+path
    elif prefix:
        return relative, None
    filename = routes['routes'].get(path)
    if not filename: return relative, None
    params.pop('lang',None)
    canonical = path+('?' + urlencode(params,doseq=True) if params else '')
    requested_path = '/'+relative+('?' + query if query else '')
    return filename, canonical if canonical != requested_path else None

def restore_version(project, commit):
    """Restore item content while retaining the current permanent-identity routing contract."""
    root = require(project)
    model = engine(root)
    with _LOCK, model.build_lock():
        current_catalog, current_products, _ = model.load()
        if current_catalog.get('version') != 2: return None
        state = model.identity_history(current_catalog)
        try:
            catalog = json.loads(project.blob(commit,'data/catalog.json'))
        except FileNotFoundError:
            raise ValueError('This version predates the catalogue. Restore a catalogue-era version instead.')
        paths = project.run('ls-tree','-r','--name-only',commit,'--','data/products').splitlines()
        products, mapping = {}, {}
        for path in paths:
            if not path.endswith('.json'): continue
            product = json.loads(project.blob(commit,path))
            old = product['id']
            id = old if model.PERMANENT_ID.fullmatch(old) else state['aliases'].get('/product-'+old)
            if not id: raise ValueError(f'No permanent identity recorded for historical item {old}.')
            mapping[old] = id
            product['id'] = id
            if not model.PERMANENT_ID.fullmatch(old):
                product['slug'] = current_products.get(id,{}).get('slug') or product['slug']
            products[id] = product
        for refs in [catalog['root'], *(c['entries'] for c in catalog['categories'])]:
            for ref in refs:
                if ref['type']=='product': ref['id'] = mapping[ref['id']]
        state['issued'] = sorted(set(state['issued']) | set(catalog.get('identity',{}).get('issued',[])) | set(products))
        for alias, id in catalog.get('aliases',{}).items():
            if alias in state['aliases'] and state['aliases'][alias] != id: raise ValueError('Historical alias identity conflict.')
            state['aliases'][alias] = id
        for id, product in current_products.items():
            state['aliases'][model.product_path(product)] = id
        catalog.update(version=2, identity={'issued':state['issued']}, aliases=state['aliases'])
        # Retain the implementation that enforces identity even when restoring pre-migration history.
        infrastructure = ('catalogue.py','sitemap.py','build.py','site-language.js','scrolly.js','products.js',
                          'product-detail.js','product-detail.css','templates/home.html','templates/contact.html',
                          'templates/products.html','functions/_middleware.js','.gitignore')
        keep = {path:(root/path).read_bytes() for path in infrastructure if (root/path).is_file()}
        model.remember_identity(state)
        head = project.head()
        try:
            project.run('restore',f'--source={commit}','--staged','--worktree','--',':/')
            for path, content in keep.items():
                (root/path).parent.mkdir(parents=True,exist_ok=True)
                _atomic(root/path,content,root)
            # Validate against the restored assets before accepting the historical content.
            model.validate(catalog, products)
            for path in (root/'data/products').glob('*.json'):
                if path.stem not in products: path.unlink()
            _atomic(root/'data/catalog.json',(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n').encode(),root)
            for id, product in products.items():
                _atomic(root/'data/products'/f'{id}.json',(json.dumps(product,ensure_ascii=False,indent=2)+'\n').encode(),root)
            model.generate(locked=True)
            return project.commit(f'Restore version {commit[:12]} (preserve catalogue identities)')
        except Exception:
            project.run('restore',f'--source={head}','--staged','--worktree','--',':/')
            # Remove only generated/catalogue files introduced during the failed restore.
            tracked = set(project.run('ls-tree','-r','--name-only',head).splitlines())
            candidates = [root/'data/catalog.json', *(root/'data/products').glob('*.json')]
            for path in candidates:
                if path.relative_to(root).as_posix() not in tracked: path.unlink(missing_ok=True)
            raise
