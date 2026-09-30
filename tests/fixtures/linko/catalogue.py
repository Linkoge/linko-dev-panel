#!/usr/bin/env python3
"""Validate and generate the static Linko catalogue. Python standard library only."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import html
import json
import math
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit, quote

ROOT = Path(__file__).resolve().parent
MANIFEST = Path('data/catalogue-generated.json')
ID = re.compile(r'^[a-z][a-z0-9-]{1,63}$')
MODES = {'fixed', 'starting-from', 'on-request'}
KINDS = {'product', 'service', 'package'}
AVAILABILITY = {'available', 'unavailable', 'preorder'}
DESTINATIONS = {'none', 'existing', 'generated'}
IMAGE_EXT = {'.avif', '.webp', '.jpg', '.jpeg', '.png', '.svg', '.gif'}

class CatalogueError(ValueError):
    pass

@contextmanager
def build_lock():
    lock=ROOT/'.catalogue.lock'
    if lock.is_symlink(): raise CatalogueError('unsafe catalogue lock file')
    with lock.open('a+b') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX)
        try: yield
        finally: fcntl.flock(stream,fcntl.LOCK_UN)

def fail(file, field, message):
    raise CatalogueError(f'{file}: {field}: {message}')

def read_json(path):
    try:
        target=(ROOT / path).resolve()
        if not target.is_relative_to(ROOT): fail(path,'path','outside project')
        return json.loads(target.read_text(encoding='utf-8'),parse_constant=lambda value: fail(path,'JSON',f'non-finite number {value}'))
    except (OSError, json.JSONDecodeError) as e:
        raise CatalogueError(f'{path}: {e}') from e

def safe_path(path, file, field, *, image=False):
    if not isinstance(path, str) or not path or path.startswith('/') or '\\' in path or '?' in path or '#' in path:
        fail(file, field, 'must be a project-relative path')
    parts = Path(path).parts
    if any(p in ('.', '..') or p.startswith('.') for p in parts):
        fail(file, field, 'unsafe path')
    target = (ROOT / path).resolve()
    if not target.is_relative_to(ROOT) or not target.is_file():
        fail(file, field, 'file missing or outside project')
    if image and (not path.startswith(('assets/main-pics/', 'assets/product-images/')) or target.suffix.lower() not in IMAGE_EXT):
        fail(file, field, 'expected an image under assets/main-pics/ or assets/product-images/')
    return path

def localized(value, file, field, *, optional=False):
    if not isinstance(value, dict) or not isinstance(value.get('ka'), str) or (not optional and not value['ka'].strip()):
        fail(file, field, 'requires Georgian (ka) text')
    if any(k not in {'ka','en','ru'} or not isinstance(v, str) for k,v in value.items()):
        fail(file, field, 'only ka, en, ru strings are supported')
    return value

def optional_localized(value, file, field):
    if value is not None: localized(value,file,field,optional=True)

def gallery_image(value, file, field):
    # Older catalogues stored gallery images as paths. Keep them readable.
    if isinstance(value,str): return safe_path(value,file,field,image=True)
    if not isinstance(value,dict): fail(file,field,'expected an image with path and alt text')
    safe_path(value.get('path'),file,field+'.path',image=True)
    localized(value.get('alt'),file,field+'.alt',optional=True)
    return value['path']

def ref_list(refs, file, field, products, categories, *, category=False):
    if not isinstance(refs, list): fail(file, field, 'must be an array')
    seen=set()
    for n,ref in enumerate(refs):
        at=f'{field}[{n}]'
        if not isinstance(ref,dict) or ref.get('type') not in {'product','category'} or not isinstance(ref.get('id'),str):
            fail(file,at,'expected type and id')
        key=(ref['type'],ref['id'])
        if key in seen: fail(file,at,'duplicate entry')
        seen.add(key)
        if category and ref['type']=='category': fail(file,at,'nested categories are unsupported')
        if ref['id'] not in (products if ref['type']=='product' else categories): fail(file,at,'unknown entry')

def validate(catalog, products):
    file='data/catalog.json'
    if not isinstance(catalog,dict) or catalog.get('version')!=1: fail(file,'version','expected 1')
    if not isinstance(catalog.get('categories'),list): fail(file,'categories','must be an array')
    categories={}; urls={'products.html'}; product_slugs=set()
    for n,c in enumerate(catalog['categories']):
        at=f'categories[{n}]'
        if not isinstance(c,dict): fail(file,at,'must be an object')
        cid=c.get('id'); slug=c.get('slug')
        if not isinstance(cid,str) or not ID.fullmatch(cid) or cid in categories: fail(file,at+'.id','invalid or duplicate ID')
        if not isinstance(slug,str) or not ID.fullmatch(slug): fail(file,at+'.slug','invalid slug')
        localized(c.get('title'),file,at+'.title')
        safe_path(c.get('image'),file,at+'.image',image=True)
        if not isinstance(c.get('visible'),bool): fail(file,at+'.visible','must be boolean')
        if c.get('priceMode','view-options') not in {'view-options','from'}: fail(file,at+'.priceMode','invalid mode')
        url=f'catalog-{slug}.html'
        if url in urls or ((ROOT/url).exists() and url not in old_outputs()): fail(file,at+'.slug','generated URL collision')
        urls.add(url); categories[cid]=c
    for id,p in products.items():
        pf=f'data/products/{id}.json'
        if not isinstance(p,dict): fail(pf,'root','must be an object')
        if p.get('id')!=id or not ID.fullmatch(id): fail(pf,'id','must match safe filename')
        if p.get('kind') not in KINDS: fail(pf,'kind','invalid kind')
        slug=p.get('slug')
        if not isinstance(slug,str) or not ID.fullmatch(slug): fail(pf,'slug','invalid slug')
        if slug in product_slugs: fail(pf,'slug','duplicate product slug')
        product_slugs.add(slug)
        localized(p.get('title'),pf,'title')
        image=p.get('image')
        if not isinstance(image,dict): fail(pf,'image','must be an object')
        safe_path(image.get('path'),pf,'image.path',image=True)
        localized(image.get('alt'),pf,'image.alt',optional=True)
        if image.get('secondary') is not None: safe_path(image['secondary'],pf,'image.secondary',image=True)
        if image.get('presentation','cover') not in {'cover','cutout','illustration'}: fail(pf,'image.presentation','invalid style')
        for dim in ('width','height'):
            if not isinstance(image.get(dim),int) or image[dim]<=0: fail(pf,'image.'+dim,'positive integer required')
        if p.get('badge') is not None and not isinstance(p['badge'],str): fail(pf,'badge','must be text or null')
        price=p.get('price')
        if not isinstance(price,dict) or price.get('mode') not in MODES: fail(pf,'price.mode','invalid mode')
        if price.get('currency')!='GEL': fail(pf,'price.currency','expected GEL')
        amount=price.get('amount')
        if price['mode']=='on-request' and amount is not None: fail(pf,'price.amount','must be null on request')
        if price['mode']!='on-request' and (isinstance(amount,bool) or not isinstance(amount,(int,float)) or not math.isfinite(amount) or amount<0): fail(pf,'price.amount','finite nonnegative number required')
        if not isinstance(p.get('visible'),bool): fail(pf,'visible','must be boolean')
        if p.get('availability') not in AVAILABILITY: fail(pf,'availability','invalid value')
        dest=p.get('destination')
        if not isinstance(dest,dict) or dest.get('mode') not in DESTINATIONS: fail(pf,'destination.mode','invalid mode')
        if dest['mode']=='existing':
            url=dest.get('url')
            if not isinstance(url,str) or any(ord(ch)<32 for ch in url): fail(pf,'destination.url','invalid URL')
            try: valid_web=isinstance(url,str) and url.startswith('https://') and bool(urlsplit(url).hostname) and not any(ch in url for ch in '<>"\'')
            except ValueError: valid_web=False
            valid_local=isinstance(url,str) and url.endswith('.html') and '/' not in url and '\\' not in url and (ROOT/url).resolve().is_relative_to(ROOT) and (ROOT/url).is_file()
            if not isinstance(url,str) or not (re.fullmatch(r'tel:\+[0-9]+',url) or valid_web or valid_local):
                fail(pf,'destination.url','expected a working tel, https, or existing local HTML destination')
        if not isinstance(p.get('detailReady'),bool): fail(pf,'detailReady','must be boolean')
        optional_localized(p.get('introduction'),pf,'introduction')
        for key in ('description','gallery','specifications','included'):
            if not isinstance(p.get(key,[]),list): fail(pf,key,'must be an array')
        for n,section in enumerate(p.get('description',[])):
            if not isinstance(section,dict): fail(pf,f'description[{n}]','must be an object')
            optional_localized(section.get('heading'),pf,f'description[{n}].heading')
            localized(section.get('body'),pf,f'description[{n}].body')
        for n,image in enumerate(p.get('gallery',[])): gallery_image(image,pf,f'gallery[{n}]')
        for n,row in enumerate(p.get('specifications',[])):
            if not isinstance(row,dict): fail(pf,f'specifications[{n}]','must be an object')
            localized(row.get('label'),pf,f'specifications[{n}].label')
            localized(row.get('value'),pf,f'specifications[{n}].value')
        for n,item in enumerate(p.get('included',[])): localized(item,pf,f'included[{n}]')
        if dest['mode']=='generated' and p['detailReady']:
            url=f'product-{slug}.html'
            if url in urls or ((ROOT/url).exists() and url not in old_outputs()): fail(pf,'slug','generated URL collision')
            urls.add(url)
    if set(products)&set(categories): fail(file,'categories','category IDs must differ from product IDs')
    ref_list(catalog.get('root'),file,'root',products,categories)
    for id,c in categories.items(): ref_list(c.get('entries'),file,f'categories[{id}].entries',products,categories,category=True)
    return categories

def old_outputs():
    try:
        value=read_json(MANIFEST)
        return set(value.get('files',[])) if isinstance(value,dict) else set()
    except CatalogueError: return set()

def load():
    catalog=read_json('data/catalog.json')
    products={}
    for path in sorted((ROOT/'data/products').glob('*.json')):
        if not ID.fullmatch(path.stem): fail(path.relative_to(ROOT),'filename','invalid ID')
        products[path.stem]=read_json(path.relative_to(ROOT))
    categories=validate(catalog,products)
    return catalog,products,categories

def e(value): return html.escape(str(value),quote=True)
def ka(value): return value.get('ka','')

def plain_description(text):
    """Render blank-line paragraphs and lines beginning '- ' as simple lists."""
    blocks=[]; paragraph=[]; items=[]
    def flush():
        if paragraph:
            blocks.append('<p>'+e(' '.join(paragraph))+'</p>'); paragraph.clear()
        if items:
            blocks.append('<ul>'+''.join('<li>'+e(item)+'</li>' for item in items)+'</ul>'); items.clear()
    for line in text.splitlines():
        stripped=line.strip()
        if not stripped: flush()
        elif stripped.startswith('- '):
            if paragraph: flush()
            items.append(stripped[2:])
        else:
            if items: flush()
            paragraph.append(stripped)
    flush()
    return ''.join(blocks)

def price_html(price):
    mode=price['mode']
    if mode=='on-request': return '<span class="product-price product-price--request">ფასი მოთხოვნით</span>'
    amount=price['amount']; amount=f'{amount:g}' if isinstance(amount,float) else str(amount)
    prefix='<span class="product-price__prefix">დან</span>' if mode=='starting-from' else ''
    return f'<span class="product-price">{prefix}{e(amount)} ₾</span>'

def card(p, first=False):
    title=ka(p['title']); image=p['image']; dest=p['destination']; price=price_html(p['price'])
    url=dest.get('url') if dest['mode']=='existing' else f"product-{p['slug']}.html" if dest['mode']=='generated' and p['detailReady'] else None
    tag='a' if url else 'div'
    price_label='ფასი მოთხოვნით' if p['price']['mode']=='on-request' else f"{p['price']['amount']} ₾"
    action='დარეკვა' if url and url.startswith('tel:') else 'დეტალები'
    attrs=f' href="{e(url)}" aria-label="{e(title)} — {e(price_label)}, {action}"' if url else ''
    classes='product-media'+(' product-media--pair product-media--cutout' if image.get('secondary') else ' product-media--illustration' if image.get('presentation')=='illustration' else '')
    loading=' fetchpriority="high"' if first else ' loading="lazy"'
    src=f'<img src="{e(image["path"])}" alt="{e(ka(image["alt"]))}" width="{image["width"]}" height="{image["height"]}"{loading} decoding="async">'
    if image.get('secondary'): src+=f'<img src="{e(image["secondary"])}" alt="" width="{image["width"]}" height="{image["height"]}" loading="lazy" decoding="async">'
    badge=f'<span class="product-badge">{e(p["badge"])}</span>' if p.get('badge') else ''
    return f'<{tag} class="product-card"{attrs}><span class="{classes}">{src}{badge}</span><h2 class="product-title">{e(title)}</h2>{price}</{tag}>'

def category_card(c, products):
    prices=[p['price']['amount'] for ref in c['entries'] if ref['type']=='product' for p in [products[ref['id']]] if p['visible'] and p['availability']=='available' and p['price']['mode']!='on-request']
    price=price_html({'mode':'starting-from','amount':min(prices),'currency':'GEL'}) if c.get('priceMode')=='from' and prices else '<span class="product-price product-price--request">ვარიანტების ნახვა</span>'
    title=ka(c['title'])
    return f'<a class="product-card" href="catalog-{e(c["slug"])}.html"><span class="product-media"><img src="{e(c["image"])}" alt="" loading="lazy" decoding="async"></span><h2 class="product-title">{e(title)}</h2>{price}</a>'

def grid(refs,products,categories):
    rows=[]
    for ref in refs:
        item=(products if ref['type']=='product' else categories)[ref['id']]
        if not item['visible']: continue
        rows.append(card(item,not rows) if ref['type']=='product' else category_card(item,products))
    return '<div class="product-grid">\n        '+'\n        '.join(rows)+'\n      </div>'

def detail(p):
    """Plain real-data fallback while the isolated product design is reviewed.

    Deliberately contains no rejected detail layout or demo fixture content.
    Keep existing catalogue destinations and editor-generated content usable.
    """
    images=[p['image']]
    if p['image'].get('secondary'): images.append(p['image']['secondary'])
    images.extend(p.get('gallery', []))
    media=''.join(f'<img src="{e(item if isinstance(item,str) else item["path"])}" alt="{e(ka(item.get("alt",{})) if isinstance(item,dict) else "")}" width="320" loading="lazy">' for item in images)
    sections=[]
    for section in p.get('description',[]):
        heading=ka(section.get('heading',{}))
        sections.append((f'<h2>{e(heading)}</h2>' if heading else '')+plain_description(ka(section['body'])))
    if p.get('specifications'):
        sections.append('<h2>მახასიათებლები</h2><dl>'+''.join(f'<dt>{e(ka(row["label"]))}</dt><dd>{e(ka(row["value"]))}</dd>' for row in p['specifications'])+'</dl>')
    if p.get('included'):
        sections.append('<h2>კომპლექტში შედის</h2><ul>'+''.join(f'<li>{e(ka(item))}</li>' for item in p['included'])+'</ul>')
    message=quote(f'გამარჯობა, მაინტერესებს {ka(p["title"])}. https://linko.ge/product-{p["slug"]}.html')
    return f'<article><p><a href="products.html">← პროდუქცია</a></p>{media}{price_html(p["price"])}<p>{e(ka(p.get("introduction",{})))}</p>{"".join(sections)}<p><a class="phone-action" href="https://wa.me/995511779966?text={e(message)}" target="_blank" rel="noopener noreferrer">WhatsApp</a> <a class="phone-action" href="tel:+995511779966">დარეკვა</a></p></article>'

def render(catalog=None, products=None):
    if catalog is None and products is None:
        catalog,products,categories=load()
    else:
        categories=validate(catalog,products)
    template_path=(ROOT/'templates/products.html').resolve()
    if not template_path.is_relative_to(ROOT): fail('templates/products.html','path','outside project')
    template=template_path.read_text(encoding='utf-8')
    if template.count('{{CATALOG_GRID}}')!=1: fail('templates/products.html','CATALOG_GRID','expected once')
    outputs={'products.html':template.replace('{{CATALOG_GRID}}',grid(catalog['root'],products,categories))}
    for c in categories.values():
        if not c['visible']: continue
        page=template.replace('<title>პროდუქტები და სერვისები | Linko</title>',f'<title>{e(ka(c["title"]))} | Linko</title>')
        page=page.replace('<h1 id="page-title">პროდუქტები და სერვისები</h1>',f'<h1 id="page-title">{e(ka(c["title"]))}</h1>')
        outputs[f'catalog-{c["slug"]}.html']=page.replace('{{CATALOG_GRID}}',grid(c['entries'],products,categories))
    for p in products.values():
        if p['destination']['mode']!='generated' or not p['detailReady']: continue
        title=e(ka(p['title'])); intro=ka(p.get('introduction') or {}).strip()
        description=e((intro or ka(p['title']))+' — Linko. პროდუქტის დეტალები და საკონტაქტო ინფორმაცია.')
        page=template.replace('<title>პროდუქტები და სერვისები | Linko</title>',f'<title>{title} | Linko</title>')
        page=page.replace('Linko-ს Starlink მოწყობილობები, პროფესიონალური მონტაჟი და ქსელური გადაწყვეტილებები საქართველოში.',description)
        page=page.replace('<h1 id="page-title">პროდუქტები და სერვისები</h1>',f'<h1 id="page-title">{title}</h1>')
        outputs[f'product-{p["slug"]}.html']=page.replace('{{CATALOG_GRID}}',detail(p))
    if '<title>პროდუქტები და სერვისები | Linko</title>' in template:
        missing=template.replace('<title>პროდუქტები და სერვისები | Linko</title>','<title>გვერდი ვერ მოიძებნა | Linko</title>')
        missing=missing.replace('Linko-ს Starlink მოწყობილობები, პროფესიონალური მონტაჟი და ქსელური გადაწყვეტილებები საქართველოში.','გვერდი ვერ მოიძებნა. დაბრუნდით Linko-ს პროდუქციის კატალოგში.')
        missing=missing.replace('<h1 id="page-title">პროდუქტები და სერვისები</h1>','<h1 id="page-title">გვერდი ვერ მოიძებნა</h1>')
        outputs['404.html']=missing.replace('{{CATALOG_GRID}}','<div class="catalog-not-found"><p>მითითებული გვერდი არ არსებობს.</p><a class="phone-action" href="products.html">პროდუქციის ნახვა</a></div>')
    outputs[str(MANIFEST)]=json.dumps({'files':sorted(outputs)},ensure_ascii=False,indent=2)+'\n'
    return outputs

def generate(check=False, locked=False):
    if not locked:
        with build_lock(): return generate(check=check,locked=True)
    outputs=render(); old=old_outputs(); owned=set(outputs)
    for name in owned:
        target=ROOT/name
        if target.is_symlink() or not target.resolve().is_relative_to(ROOT):
            raise CatalogueError(f'unsafe generated output {name}')
    for name in old-owned:
        if not (name.startswith('catalog-') or name.startswith('product-')) or '/' in name or not name.endswith('.html'):
            raise CatalogueError(f'{MANIFEST}: unsafe obsolete output {name}')
    changed=[name for name,content in outputs.items() if not (ROOT/name).exists() or (ROOT/name).read_text(encoding='utf-8')!=content]
    obsolete=old-owned
    if check:
        if changed or obsolete: raise CatalogueError('Generated catalogue is stale: '+', '.join(sorted(changed+list(obsolete))))
        return []
    staged={}; backup={}
    try:
        for name in changed:
            target=ROOT/name
            if target.is_symlink() or not target.resolve().is_relative_to(ROOT): raise CatalogueError(f'unsafe generated output {name}')
            fd,tmp=tempfile.mkstemp(prefix='.catalogue-',dir=target.parent)
            with os.fdopen(fd,'w',encoding='utf-8') as stream: stream.write(outputs[name]); stream.flush(); os.fsync(stream.fileno())
            staged[name]=Path(tmp)
        for name in sorted(changed,key=lambda x:x==str(MANIFEST)):
            target=ROOT/name; backup[name]=target.read_bytes() if target.exists() else None
            os.replace(staged.pop(name),target)
        for name in obsolete:
            target=ROOT/name
            if target.is_symlink(): raise CatalogueError(f'unsafe obsolete output {name}')
            backup[name]=target.read_bytes() if target.exists() else None
            target.unlink(missing_ok=True)
    except Exception:
        for name,data in backup.items():
            target=ROOT/name
            if data is None: target.unlink(missing_ok=True)
            else: target.write_bytes(data)
        raise
    finally:
        for tmp in staged.values(): tmp.unlink(missing_ok=True)
    return changed

def source_state():
    paths=[ROOT/'data/catalog.json',ROOT/'templates/products.html',*sorted((ROOT/'data/products').glob('*.json'))]
    return tuple((str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in paths)

def watch():
    previous=source_state(); due=None
    print('Watching catalogue JSON and templates',flush=True)
    while True:
        time.sleep(.25)
        try: now=source_state()
        except OSError as exc: print(f'Catalogue watch: {exc}',file=sys.stderr,flush=True); continue
        if now!=previous: previous=now; due=time.monotonic()+.5
        if due and time.monotonic()>=due:
            due=None
            try:
                try:
                    generate(check=True)
                    print('Catalogue already current',flush=True)
                except CatalogueError as exc:
                    if not str(exc).startswith('Generated catalogue is stale:'): raise
                    print('Generated: '+', '.join(generate()),flush=True)
            except (CatalogueError,OSError) as exc: print(f'Catalogue error: {exc}',file=sys.stderr,flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('command',choices=['generate','check','watch']); args=parser.parse_args()
    try:
        if args.command=='watch': watch()
        else: print('Catalogue '+ ('valid and current' if args.command=='check' else 'generated')+': '+', '.join(generate(check=args.command=='check')))
    except (CatalogueError,OSError) as exc:
        print(f'Catalogue error: {exc}',file=sys.stderr); sys.exit(1)
