"""Private, project-scoped catalogue operations for the Dev Panel."""
from __future__ import annotations
import base64
import hashlib
import importlib.util
import io
import json
import os
import re
import tempfile
import threading
from pathlib import Path
from PIL import Image, UnidentifiedImageError

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
    config=json.loads((Path(__file__).resolve().parent/'projects.json').read_text())['projects'].get(project.name,{})
    return config.get('catalogue') is True and Path(config.get('path','')).resolve()==project.path and (project.path/'catalogue.py').is_file()

def require(project):
    if not enabled(project): raise ValueError('Catalogue is unavailable for this project.')
    return project.path

def engine(root):
    spec=importlib.util.spec_from_file_location('linko_catalogue',root/'catalogue.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

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
        digest.update(str(path.relative_to(root)).encode());digest.update(b'\0');digest.update(path.read_bytes());digest.update(b'\0')
    return digest.hexdigest()

def snapshot(project):
    root=require(project)
    with _LOCK:
        model=engine(root)
        catalog,products,_=model.load()
        return {'catalog':catalog,'products':products,'revision':revision(root),
                'previewUrl':f'/site/Linko/preview/products.html'}

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
            result.append({'path':relative,'name':path.name,'url':'/site/Linko/preview/'+relative})
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
        if body.get('revision')!=revision(root): raise ConflictError('Catalogue changed since this editor loaded. Reload and review your changes.')
        catalog=body.get('catalog');products=body.get('products')
        if not isinstance(products,dict) or len(products)>500: raise ValueError('products must be an object of at most 500 entries.')
        for id in products:
            if not isinstance(id,str) or not _ID.fullmatch(id): raise ValueError('Invalid product ID.')
        prior={p.stem for p in files(root)[1:]}
        if not prior.issubset(products): raise ValueError('Permanent deletion is unavailable; hide a product instead.')
        model.render(catalog,products)  # Validate every proposed field before any write.
        if body.get('revision')!=revision(root): raise ConflictError('Catalogue changed during validation. Reload and review your changes.')
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
        return {'revision':revision(root),'generated':changed}

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
    with _LOCK:
        for n in range(10000):
            filename=f'{stem}{"-"+str(n) if n else ""}{_UPLOAD_FORMATS[fmt]}'
            target=folder/filename
            try:
                with target.open('xb') as out: out.write(payload)
                return {'path':target.relative_to(root).as_posix(),'url':'/site/Linko/preview/'+target.relative_to(root).as_posix(),
                        'width':width,'height':height}
            except FileExistsError: continue
    raise ValueError('Unable to choose a unique image filename.')
