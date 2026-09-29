(() => {
  const $ = id => document.getElementById(id);
  const view = $('productsView');
  let state=null, revision='', dirty=false, categoryId=null, showHidden=true, imageTarget=null, loadedProject='';
  const el=(tag,cls,text)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=text;return node};
  const slug=value=>value.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,45);
  const unique=(base,used)=>{let value=base,n=2;while(used.includes(value))value=`${base}-${n++}`;return value};
  const imageUrl=path=>`/site/${encodeURIComponent(loadedProject)}/preview/${path.split('/').map(encodeURIComponent).join('/')}`;
  const api=(path,options)=>window.catalogueApi(path,options);
  const mark=()=>{dirty=true; const node=$('catalogueStatus');if(node){node.textContent='Unsaved changes';node.className='editor-status'}};
  const status=(message,error=false)=>{const node=$('catalogueStatus');if(node){node.textContent=message;node.className=`editor-status${error?' error':''}`}};
  const current=()=>categoryId?state.catalog.categories.find(c=>c.id===categoryId).entries:state.catalog.root;
  const set=(obj,key,value)=>{obj[key]=value;mark()};
  const button=(label,fn,cls='')=>{const b=el('button',cls,label);b.type='button';b.onclick=fn;return b};
  const label=(text,input)=>{const wrap=el('label');wrap.textContent=text;wrap.append(input);return wrap};
  const input=(value,onchange,type='text')=>{const n=el('input');n.type=type;if(type==='number'){n.min='0';n.step='any'}n.value=value??'';n.oninput=()=>onchange(n.value);return n};
  const choice=(value,items,onchange)=>{const n=el('select');for(const [v,t] of items){const o=el('option','',t);o.value=v;n.append(o)}n.value=value;n.onchange=()=>onchange(n.value);return n};
  const refs=()=>current();
  function move(index,delta){const rows=refs(),to=index+delta;if(to<0||to>=rows.length)return;[rows[index],rows[to]]=[rows[to],rows[index]];mark();render()}
  function previewPrice(p){const mode=p.price.mode;if(mode==='on-request')return 'ფასი მოთხოვნით';return `${mode==='starting-from'?'დან ':''}${p.price.amount??0} ₾`}
  function field(parent,title,value,change,type){parent.append(label(title,input(value,change,type||'text')))}
  function rowControls(card,ref,index){const actions=el('div','editor-actions');actions.append(button('↑ Move up',()=>move(index,-1)),button('↓ Move down',()=>move(index,1)));card.append(actions);return actions}
  function productCard(ref,index){
    const p=state.products[ref.id],card=el('div','editor-item'+(p.visible?'':' is-hidden'));card.draggable=true;
    card.ondragstart=e=>{e.dataTransfer.setData('text/plain',String(index));e.dataTransfer.effectAllowed='move'};
    card.ondragover=e=>e.preventDefault();card.ondrop=e=>{e.preventDefault();const from=Number(e.dataTransfer.getData('text/plain'));if(Number.isInteger(from)&&from!==index)move(from,index-from)};
    const picture=button('',()=>pick(p.image,'path'),'editor-image');picture.title='Choose or upload image';const img=el('img',p.image.presentation==='cutout'?'cutout':'');img.src=imageUrl(p.image.path);img.alt=p.image.alt.ka||'';picture.append(img);card.append(picture);
    const titlePreview=el('div','editor-title',p.title.ka);card.append(titlePreview);
    const pricePreview=el('div','editor-price'+(p.price.mode==='on-request'?' request':''),previewPrice(p));card.append(pricePreview);
    field(card,'Title',p.title.ka,v=>{p.title.ka=v;titlePreview.textContent=v;mark()});
    card.append(label('Price mode',choice(p.price.mode,[['on-request','On request'],['fixed','Fixed'],['starting-from','Starting from']],v=>{p.price.mode=v;p.price.amount=v==='on-request'?null:p.price.amount??0;pricePreview.textContent=previewPrice(p);pricePreview.classList.toggle('request',v==='on-request');mark();render()})));
    if(p.price.mode!=='on-request')field(card,'Price (GEL)',p.price.amount,v=>{p.price.amount=v===''?null:Number(v);pricePreview.textContent=previewPrice(p);mark()},'number');
    field(card,'Badge',p.badge||'',v=>set(p,'badge',v||null));
    card.append(label('Availability',choice(p.availability,[['available','Available'],['unavailable','Unavailable'],['preorder','Preorder']],v=>set(p,'availability',v))));
    card.append(label('Visibility',choice(String(p.visible),[['true','Visible'],['false','Hidden']],v=>{set(p,'visible',v==='true');card.classList.toggle('is-hidden',!p.visible)})));
    const actions=rowControls(card,ref,index);
    actions.append(button('Duplicate',()=>duplicate(p)));
    if(categoryId)actions.append(button('Remove from category',()=>{refs().splice(index,1);mark();render()},'editor-wide'));
    const details=el('details');details.append(el('summary','','Details & destination'));
    details.append(label('Kind',choice(p.kind,[['product','Product'],['service','Service'],['package','Package']],v=>set(p,'kind',v))));
    field(details,'Image alt text',p.image.alt.ka,v=>set(p.image.alt,'ka',v));
    details.append(label('Destination',choice(p.destination.mode,[['none','No link'],['existing','Existing link'],['generated','Generated detail page']],v=>{p.destination.mode=v;if(v==='generated')p.detailReady=false;mark();render()})));
    if(p.destination.mode==='existing')field(details,'Existing URL',p.destination.url||'',v=>set(p.destination,'url',v));
    if(p.destination.mode==='generated')details.append(label('Publish detail page',choice(String(p.detailReady),[['false','Keep as draft'],['true','Publish generated page']],v=>set(p,'detailReady',v==='true'))));
    field(details,'URL slug',p.slug,v=>set(p,'slug',v));
    structured(details,'Description sections',p.description,()=>({heading:{ka:''},body:{ka:''}}),[['Heading','heading'],['Body','body']]);
    structured(details,'Specifications',p.specifications,()=>({label:{ka:''},value:{ka:''}}),[['Label','label'],['Value','value']]);
    const gallery=el('div');gallery.append(el('strong','','Gallery'));
    p.gallery.forEach((path,n)=>{const row=el('div','structured-row');const thumb=el('img');thumb.src=imageUrl(path);thumb.alt='';row.append(thumb,button('Choose image',()=>pick(p.gallery,n)),button('Remove',()=>{p.gallery.splice(n,1);mark();render()}));gallery.append(row)});
    gallery.append(button('Add gallery image',()=>pick(p.gallery,p.gallery.length)));details.append(gallery);
    card.append(details);return card;
  }
  function structured(parent,title,rows,make,fields){const box=el('div');box.append(el('strong','',title));rows.forEach((row,n)=>{const wrap=el('div','structured-row');for(const [caption,key] of fields)field(wrap,caption,row[key].ka,v=>set(row[key],'ka',v));wrap.append(button('Remove row',()=>{rows.splice(n,1);mark();render()}));box.append(wrap)});box.append(button('Add row',()=>{rows.push(make());mark();render()}));parent.append(box)}
  function categoryCard(ref,index){const c=state.catalog.categories.find(item=>item.id===ref.id),card=el('div','editor-item'+(c.visible?'':' is-hidden'));
    const picture=button('',()=>pick(c,'image'),'editor-image');const img=el('img');img.src=imageUrl(c.image);picture.append(img);card.append(picture,el('div','editor-title',c.title.ka));
    card.append(button('Open category',()=>{categoryId=c.id;render()}));
    field(card,'Title',c.title.ka,v=>{c.title.ka=v;mark();card.querySelector('.editor-title').textContent=v});
    field(card,'URL slug',c.slug,v=>set(c,'slug',v));
    card.append(label('Price label',choice(c.priceMode||'view-options',[['view-options','View options'],['from','From eligible products']],v=>set(c,'priceMode',v))));
    card.append(label('Visibility',choice(String(c.visible),[['true','Visible'],['false','Hidden']],v=>{set(c,'visible',v==='true');card.classList.toggle('is-hidden',!c.visible)})));
    rowControls(card,ref,index);return card;
  }
  function duplicate(p){const id=unique(p.id+'-copy',Object.keys(state.products)),copy=structuredClone(p);copy.id=id;copy.slug=unique(p.slug+'-copy',Object.values(state.products).map(x=>x.slug));copy.visible=false;copy.destination={mode:'none'};copy.detailReady=false;state.products[id]=copy;refs().push({type:'product',id});mark();render()}
  function addProduct(){const id=unique('draft-product',Object.keys(state.products));const p={id,kind:'product',slug:id,title:{ka:'ახალი პროდუქტი'},image:{path:'assets/product-images/mounts.svg',alt:{ka:''},presentation:'cover',width:240,height:240},badge:null,price:{mode:'on-request',amount:null,currency:'GEL'},visible:false,availability:'available',destination:{mode:'none'},detailReady:false,description:[],gallery:[],specifications:[]};state.products[id]=p;refs().push({type:'product',id});mark();render()}
  function addCategory(){const id=unique('new-category',state.catalog.categories.map(c=>c.id));state.catalog.categories.push({id,slug:id,title:{ka:'ახალი კატეგორია'},image:'assets/product-images/mounts.svg',visible:false,priceMode:'view-options',entries:[]});state.catalog.root.push({type:'category',id});mark();render()}
  function addExisting(){const used=new Set(refs().filter(r=>r.type==='product').map(r=>r.id));const choices=Object.values(state.products).filter(p=>!used.has(p.id));if(!choices.length){status('Every product is already in this category.');return}const select=choice(choices[0].id,choices.map(p=>[p.id,p.title.ka]),()=>{});const dialog=$('modal');$('modalTitle').textContent='Add existing product';$('modalContent').replaceChildren(select);$('modalConfirm').textContent='ADD PRODUCT';$('modalConfirm').className='primary';dialog.oncancel=null;$('modalConfirm').onclick=()=>{refs().push({type:'product',id:select.value});dialog.close();mark();render()};$('modalCancel').onclick=()=>dialog.close();dialog.showModal()}
  function render(){if(!state)return;view.replaceChildren();const toolbar=el('div','editor-toolbar');
    if(categoryId)toolbar.append(button('← Root catalogue',()=>{categoryId=null;render()}));
    toolbar.append(button('Add Product',addProduct));if(!categoryId)toolbar.append(button('Add Category',addCategory));else toolbar.append(button('Add Existing Product',addExisting));
    toolbar.append(button(showHidden?'Show visible only':'Include hidden',()=>{showHidden=!showHidden;render()}));
    toolbar.append(button('Save & Generate',save,'primary'));
    toolbar.append(button('Reload JSON',()=>{if(dirty&&!window.confirm('Discard unsaved product changes and reload?'))return;load(true)}));
    const category=categoryId?state.catalog.categories.find(c=>c.id===categoryId):null;
    const preview=el('a','button',category&&!category.visible?'Preview Root HTML':'Preview HTML');preview.href=`/site/${encodeURIComponent(loadedProject)}/preview/${category&&category.visible?`catalog-${category.slug}.html`:'products.html'}`;preview.target='_blank';preview.rel='noopener';toolbar.append(preview);
    view.append(toolbar);const crumb=el('p','editor-breadcrumb',categoryId?`Products & Services / ${state.catalog.categories.find(c=>c.id===categoryId).title.ka}`:'Products & Services');view.append(crumb);
    const note=el('p','editor-status',dirty?'Unsaved changes':'Saved');note.id='catalogueStatus';view.append(note);
    const grid=el('div','editor-grid');for(const [index,ref] of refs().entries()){const item=ref.type==='product'?state.products[ref.id]:state.catalog.categories.find(c=>c.id===ref.id);if(!showHidden&&!item.visible)continue;grid.append(ref.type==='product'?productCard(ref,index):categoryCard(ref,index))}view.append(grid);
  }
  async function load(force=false){if(!window.catalogueProject)return;const project=window.catalogueProject();if(!force&&state&&loadedProject===project)return;try{status('Loading…');const data=await api('/api/catalogue');state={catalog:data.catalog,products:data.products};revision=data.revision;loadedProject=project;categoryId=null;dirty=false;render()}catch(error){view.textContent=error.message}}
  async function save(){status('Validating and generating…');try{const data=await api('/api/catalogue/save',{method:'POST',body:{revision,catalog:state.catalog,products:state.products}});revision=data.revision;dirty=false;status(`Saved. Generated ${data.generated.length} file(s). Preview locally, then use Repository to commit and push explicitly.`)}catch(error){status(error.message,true)}}
  async function pick(target,key){imageTarget={target,key};$('catalogueImageDialog').showModal();$('catalogueImageSearch').value='';await searchImages()}
  async function searchImages(){try{const data=await api('/api/catalogue/images?q='+encodeURIComponent($('catalogueImageSearch').value));const box=$('catalogueImageResults');box.replaceChildren();for(const image of data.images){const img=el('img');img.src=image.url;img.alt='';const b=button(image.name,()=>{imageTarget.target[imageTarget.key]=image.path;if(imageTarget.key==='path'&&img.naturalWidth){imageTarget.target.width=img.naturalWidth;imageTarget.target.height=img.naturalHeight}mark();$('catalogueImageDialog').close();render()});b.prepend(img);box.append(b)}}catch(error){$('catalogueImageResults').textContent=error.message}}
  $('catalogueImageSearch').oninput=()=>searchImages();$('catalogueImageClose').onclick=()=>$('catalogueImageDialog').close();
  $('catalogueImageUpload').onchange=async e=>{const file=e.target.files?.[0];if(!file)return;try{if(file.size>8_000_000)throw Error('Image must be 8 MB or smaller.');const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file)});const result=await api('/api/catalogue/upload',{method:'POST',body:{name:file.name,data}});imageTarget.target[imageTarget.key]=result.path;if(imageTarget.key==='path'){imageTarget.target.width=result.width;imageTarget.target.height=result.height}mark();$('catalogueImageDialog').close();render()}catch(error){$('catalogueImageResults').textContent=error.message}finally{e.target.value=''}};
  window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue=''}});
  window.catalogueEditor={load,dirty:()=>dirty,discard:()=>{state=null;dirty=false}};
  if (!view.classList.contains('hidden')) load();
})();
