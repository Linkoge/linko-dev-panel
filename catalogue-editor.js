(() => {
  const $ = id => document.getElementById(id);
  const view = $('productsView');
  let state=null, revision='', dirty=false, categoryId=null, showHidden=true, imageTarget=null, loadedProject='', editingId=null, savedProducts={}, editLanguage='ka', catalogScroll=0, changes=0, saving=false;
  const el=(tag,cls,text)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=text;return node};
  const slug=value=>value.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,45);
  const unique=(base,used)=>{let value=base,n=2;while(used.includes(value))value=`${base}-${n++}`;return value};
  const imageUrl=path=>`/site/${encodeURIComponent(loadedProject)}/preview/${path.split('/').map(encodeURIComponent).join('/')}`;
  const api=(path,options)=>window.catalogueApi(path,options);
  const mark=()=>{dirty=true; changes++; const node=$('catalogueStatus');if(node){node.textContent='Unsaved changes';node.className='editor-status'}};
  const status=(message,error=false)=>{const node=$('catalogueStatus');if(node){node.textContent=message;node.className=`editor-status${error?' error':''}`}};
  const current=()=>categoryId?state.catalog.categories.find(c=>c.id===categoryId).entries:state.catalog.root;
  const set=(obj,key,value)=>{obj[key]=value;mark()};
  const button=(label,fn,cls='')=>{const b=el('button',cls,label);b.type='button';b.onclick=fn;return b};
  const label=(text,input)=>{const wrap=el('label');wrap.textContent=text;wrap.append(input);return wrap};
  const input=(value,onchange,type='text')=>{const n=el(type==='textarea'?'textarea':'input');if(type!=='textarea')n.type=type;if(type==='number'){n.min='0';n.step='any'}n.value=value??'';n.oninput=()=>onchange(n.value);return n};
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
    actions.append(button('Duplicate',()=>duplicate(p)),button('Edit product page',()=>openProduct(p.id),'editor-wide'));
    if(categoryId)actions.append(button('Remove from category',()=>{refs().splice(index,1);mark();render()},'editor-wide'));
    const details=el('details');details.append(el('summary','','Details & destination'));
    details.append(label('Kind',choice(p.kind,[['product','Product'],['service','Service'],['package','Package']],v=>set(p,'kind',v))));
    field(details,'Image alt text',p.image.alt.ka,v=>set(p.image.alt,'ka',v));
    details.append(label('Destination',choice(p.destination.mode,[['none','No link'],['existing','Existing link'],['generated','Generated detail page']],v=>{p.destination.mode=v;if(v==='generated')p.detailReady=false;mark();render()})));
    if(p.destination.mode==='existing')field(details,'Existing URL',p.destination.url||'',v=>set(p.destination,'url',v));
    if(p.destination.mode==='generated')details.append(label('Publish detail page',choice(String(p.detailReady),[['false','Keep as draft'],['true','Publish generated page']],v=>set(p,'detailReady',v==='true'))));
    field(details,'URL slug',p.slug,v=>set(p,'slug',v));
    card.append(details);return card;
  }
  function localizedField(parent,title,obj,key,type='text') {
    const value=key?obj[key]:obj;
    const control=input(value?.[editLanguage]||'',v=>{
      const target=key?(obj[key] ||= {ka:''}):obj;
      set(target,editLanguage,v);
    },type);
    if(editLanguage!=='ka') control.placeholder=value?.ka||'Falls back to Georgian';
    const wrap=label(title,control);
    if(type==='textarea') {
      const toolbar=el('div','format-toolbar');
      for(const [caption,mode] of [['Bold','bold'],['List','list']]) {
        const b=button(caption,()=>formatText(control,mode));
        b.onmousedown=e=>e.preventDefault();
        toolbar.append(b);
      }
      // Buttons are siblings of the label so they cannot redirect focus.
      parent.append(toolbar);
    }
    parent.append(wrap);
  }
  function formatText(control,mode) {
    let start=control.selectionStart,end=control.selectionEnd;
    const value=control.value;
    if(mode==='bold') {
      control.setRangeText('**'+value.slice(start,end)+'**',start,end,'select');
      control.setSelectionRange(start+2,end+2);
    } else {
      start=value.lastIndexOf('\n',start-1)+1;
      const last=end>start&&value[end-1]==='\n'?end-1:end;
      end=value.indexOf('\n',last);if(end<0)end=value.length;
      const lines=value.slice(start,end).split('\n');
      const remove=lines.every(line=>line.startsWith('- '));
      control.setRangeText(lines.map(line=>remove?line.slice(2):line.startsWith('- ')?line:'- '+line).join('\n'),start,end,'select');
    }
    control.focus();control.dispatchEvent(new Event('input',{bubbles:true}));
  }
  function rowActions(wrap,rows,n) {
    const actions=el('div','editor-actions');
    for(const [caption,delta] of [['↑ Move up',-1],['↓ Move down',1]]) {
      const b=button(caption,()=>{[rows[n],rows[n+delta]]=[rows[n+delta],rows[n]];mark();render()});
      b.disabled=n+delta<0||n+delta>=rows.length;actions.append(b);
    }
    actions.append(button('Remove row',()=>{rows.splice(n,1);mark();render()}));wrap.append(actions);
  }
  function structured(parent,title,obj,key,make,fields) {
    const rows=obj[key]||[],box=el('section','detail-editor-section');box.append(el('h3','',title));
    rows.forEach((row,n)=>{
      const wrap=el('div','structured-row');
      for(const [caption,field,type] of fields) localizedField(wrap,caption,row,field,type);
      rowActions(wrap,rows,n);box.append(wrap);
    });
    box.append(button('Add row',()=>{(obj[key] ||= []).push(make());mark();render()}));parent.append(box);
  }
  function editorURL(id) {
    const url=new URL(location.href);url.searchParams.set('project',loadedProject);url.searchParams.set('view','products');
    if(id)url.searchParams.set('product',id);else url.searchParams.delete('product');
    history.replaceState(null,'',url);
  }
  function openProduct(id) {catalogScroll=window.scrollY;editingId=id;editorURL(id);render();window.scrollTo(0,0);$('detailEditorTitle').focus()}
  function closeProduct() {editingId=null;editorURL(null);render();window.scrollTo(0,catalogScroll)}
  function renderProduct() {
    const p=state.products[editingId];view.replaceChildren();
    const editor=el('div','detail-editor');
    const title=el('h2','',`Edit product page — ${p.title.ka}`);title.id='detailEditorTitle';title.tabIndex=-1;editor.append(title);
    const toolbar=el('div','editor-toolbar detail-editor-toolbar');
    toolbar.append(button('← Back (keep edits)',closeProduct),button(saving?'Saving…':'Save & Generate',save,'primary'));
    toolbar.append(button('Preview saved page',()=>{
      const saved=savedProducts[p.id];
      if(!saved||saved.destination.mode!=='generated'||!saved.detailReady){status('Select Generated detail page and Publish detail page, then save to create a preview.',true);return}
      window.open(imageUrl('product-'+saved.slug+'.html')+'?lang='+editLanguage,'_blank','noopener');
      if(dirty)status('Preview shows the last saved page. Save & Generate to include pending edits.');
    }));
    editor.append(toolbar);
    const note=el('p','editor-status',dirty?'Unsaved changes — Back keeps all pending catalogue edits.':'Saved');note.id='catalogueStatus';note.setAttribute('role','status');editor.append(note);
    editor.append(el('p','editor-help','Save & Generate saves this page and all pending catalogue edits. Blank translations use Georgian. Descriptions: blank lines make paragraphs, **text** makes bold, and - starts a list.'));
    editor.append(label('Editing language',choice(editLanguage,[['ka','ქართული'],['en','English'],['ru','Русский']],v=>{editLanguage=v;render()})));
    localizedField(editor,'Product title',p,'title');
    editor.append(label('Price mode',choice(p.price.mode,[['on-request','On request'],['fixed','Fixed'],['starting-from','Starting from']],v=>{p.price.mode=v;p.price.amount=v==='on-request'?null:p.price.amount??0;mark();render()})));
    if(p.price.mode!=='on-request')field(editor,'Price (GEL)',p.price.amount,v=>set(p.price,'amount',v===''?null:Number(v)),'number');
    localizedField(editor,'Price note (optional)',p,'priceNote');
    localizedField(editor,'Short introduction (optional)',p,'introduction','textarea');
    structured(editor,'Description sections',p,'description',()=>({heading:{ka:''},body:{ka:''}}),[['Section title (optional)','heading'],['Description','body','textarea']]);
    structured(editor,'Specifications',p,'specifications',()=>({label:{ka:''},value:{ka:''}}),[['Label','label'],['Value','value']]);
    structured(editor,"What's included",p,'included',()=>({ka:''}),[['Item',null]]);
    const gallery=el('section','detail-editor-section');gallery.append(el('h3','','Gallery'));
    const main=el('div','structured-row');const image=el('img');image.src=imageUrl(p.image.path);image.alt='';main.append(el('h4','','Main image (also used on the catalogue card)'),image,button('Choose main image',()=>pick(p.image,'path')));localizedField(main,'Main image alt text',p.image,'alt');gallery.append(main);
    if(p.image.secondary){const secondary=el('div','structured-row');const img=el('img');img.src=imageUrl(p.image.secondary);img.alt='';secondary.append(el('h4','','Secondary card image'),img,button('Choose secondary image',()=>pick(p.image,'secondary')));gallery.append(secondary)}
    (p.gallery||[]).forEach((entry,n)=>{
      const row=el('div','structured-row'),thumb=el('img');thumb.src=imageUrl(typeof entry==='string'?entry:entry.path);thumb.alt='';row.append(thumb);
      row.append(button('Choose image',()=>pick(null,null,path=>{if(typeof entry==='string')p.gallery[n]={path,alt:{ka:''}};else entry.path=path})));
      // Upgrade legacy path strings only when the user supplies alt text or a new image.
      if(typeof entry==='string')field(row,'Image alt text','',v=>{const item=typeof p.gallery[n]==='string'?(p.gallery[n]={path:entry,alt:{ka:''}}):p.gallery[n];set(item.alt,editLanguage,v)});
      else localizedField(row,'Image alt text',entry,'alt');
      rowActions(row,p.gallery,n);gallery.append(row);
    });
    gallery.append(button('Add gallery image',()=>pick(null,null,path=>(p.gallery ||= []).push({path,alt:{ka:''}}))));editor.append(gallery);
    const destination=el('section','detail-editor-section');destination.append(el('h3','','Page destination'));
    destination.append(label('Destination',choice(p.destination.mode,[['none','No link'],['existing','Existing link'],['generated','Generated detail page']],v=>{p.destination.mode=v;if(v==='generated')p.detailReady=false;mark();render()})));
    if(p.destination.mode==='existing')field(destination,'Existing URL',p.destination.url||'',v=>set(p.destination,'url',v));
    if(p.destination.mode==='generated')destination.append(label('Publish detail page',choice(String(p.detailReady),[['false','Keep as draft'],['true','Publish generated page']],v=>{set(p,'detailReady',v==='true')})));
    field(destination,'URL slug',p.slug,v=>set(p,'slug',v));editor.append(destination);view.append(editor);
  }
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
  function render(){if(!state)return;if(editingId){renderProduct();return;}view.replaceChildren();const toolbar=el('div','editor-toolbar');
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
  async function load(force=false){if(!window.catalogueProject)return;const project=window.catalogueProject();if(!force&&state&&loadedProject===project)return;try{status('Loading…');const data=await api('/api/catalogue');state={catalog:data.catalog,products:data.products};revision=data.revision;savedProducts=structuredClone(data.products);loadedProject=project;categoryId=null;dirty=false;const requested=new URL(location.href).searchParams.get('product');editingId=state.products[requested]?requested:null;render()}catch(error){view.textContent=error.message}}
  async function save(){
    if(saving)return false;
    saving=true;const version=changes,submitted=structuredClone(state),project=loadedProject;status('Validating and generating…');
    try {
      const data=await api('/api/catalogue/save',{method:'POST',body:{revision,catalog:submitted.catalog,products:submitted.products}});
      if(project!==loadedProject)return true;
      revision=data.revision;savedProducts=submitted.products;dirty=changes!==version;
      status(dirty?'Saved submitted changes. Newer edits are still unsaved.':`Saved. Generated ${data.generated.length} file(s).`);return true;
    } catch(error){status(error.message,true);return false}
    finally{saving=false}
  }
  async function pick(target,key,apply){imageTarget={target,key,apply};$('catalogueImageDialog').showModal();$('catalogueImageSearch').value='';await searchImages()}
  function applyImage(path,width,height){
    if(imageTarget.apply)imageTarget.apply(path);
    else {
      imageTarget.target[imageTarget.key]=path;
      if(imageTarget.key==='path'&&width){imageTarget.target.width=width;imageTarget.target.height=height}
    }
    mark();$('catalogueImageDialog').close();render();
  }
  async function searchImages(){try{const data=await api('/api/catalogue/images?q='+encodeURIComponent($('catalogueImageSearch').value));const box=$('catalogueImageResults');box.replaceChildren();for(const image of data.images){const img=el('img');img.src=image.url;img.alt='';const b=button(image.name,()=>{applyImage(image.path,img.naturalWidth,img.naturalHeight)});b.prepend(img);box.append(b)}}catch(error){$('catalogueImageResults').textContent=error.message}}
  $('catalogueImageSearch').oninput=()=>searchImages();$('catalogueImageClose').onclick=()=>$('catalogueImageDialog').close();
  $('catalogueImageUpload').onchange=async e=>{const file=e.target.files?.[0];if(!file)return;try{if(file.size>8_000_000)throw Error('Image must be 8 MB or smaller.');const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file)});const result=await api('/api/catalogue/upload',{method:'POST',body:{name:file.name,data}});applyImage(result.path,result.width,result.height)}catch(error){$('catalogueImageResults').textContent=error.message}finally{e.target.value=''}};
  window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue=''}});
  window.catalogueEditor={load,dirty:()=>dirty,discard:()=>{state=null;dirty=false;editingId=null}};
  if (!view.classList.contains('hidden')) load();
})();
