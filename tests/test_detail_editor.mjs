// State/control checks. No browser rendering or layout is simulated.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
class Element {
  constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.style={};this.dataset={};this.attributes={};this.value='';this.selectionStart=0;this.selectionEnd=0;this.className='';this.text='';this.classList={contains:n=>this.className.split(' ').includes(n),toggle:(n,on)=>{const set=new Set(this.className.split(' '));on?set.add(n):set.delete(n);this.className=[...set].join(' ')}}}
  set textContent(value){this.text=String(value);this.children=[]}
  get textContent(){return this.text+this.children.map(n=>n.textContent).join('')}
  append(...nodes){this.children.push(...nodes)}
  prepend(...nodes){this.children.unshift(...nodes)}
  replaceChildren(...nodes){this.children=nodes;this.text=''}
  setAttribute(key,value){this.attributes[key]=value}
  querySelector(selector){return all(this).find(n=>selector.startsWith('.')?n.classList.contains(selector.slice(1)):n.tagName===selector.toUpperCase())}
  focus(){document.activeElement=this}
  showModal(){this.open=true}
  close(){this.open=false}
  setSelectionRange(start,end){this.selectionStart=start;this.selectionEnd=end}
  setRangeText(text,start,end){this.value=this.value.slice(0,start)+text+this.value.slice(end);this.setSelectionRange(start,start+text.length)}
  dispatchEvent(event){this['on'+event.type]?.(event)}
}
function all(node){return node.children.flatMap(child=>[child,...all(child)])}
const view=new Element();view.id='productsView';view.className='hidden';
const nodes=[view,...['catalogueImageDialog','catalogueImageSearch','catalogueImageClose','catalogueImageUpload','catalogueImageResults'].map(id=>Object.assign(new Element(),{id}))];
const document={getElementById:id=>nodes.flatMap(n=>[n,...all(n)]).find(n=>n.id===id),createElement:tag=>new Element(tag)};
const p={id:'sample',slug:'sample',title:{ka:'Original',en:'Original English'},kind:'product',price:{mode:'fixed',amount:40,currency:'GEL'},badge:null,visible:true,availability:'available',destination:{mode:'generated'},detailReady:true,image:{path:'assets/main.png',alt:{ka:'Main'},width:800,height:600},description:[{body:{ka:'Original body',en:'Existing translation'}}],specifications:[{label:{ka:'Label'},value:{ka:'Value'}}],gallery:['assets/old.png'],included:[{ka:'Included'}],unknown:{preserve:true}};
let saved={catalog:{version:1,categories:[],root:[{type:'product',id:'sample'}]},products:{sample:p}},revision='one',submitted,failSave=false,finishSave;
const events={};
const location={href:'http://panel.test/?project=Linko&view=products'};
const window={scrollY:42,scrollTo(){},addEventListener:(name,fn)=>events[name]=fn,confirm:()=>false,open(){},catalogueProject:()=> 'Linko',catalogueApi:async(path,options)=>{
  if(path==='/api/catalogue')return structuredClone({...saved,revision});
  if(path.startsWith('/api/catalogue/images'))return {images:[{name:'New image',path:'assets/new.png',url:'/new.png'}]};
  if(failSave)throw Error('Simulated validation failure');
  submitted=structuredClone(options.body);
  if(finishSave)await new Promise(resolve=>finishSave=resolve);
  saved={catalog:submitted.catalog,products:submitted.products};revision+='x';return {revision,generated:['product-sample.html']};
}};
vm.runInNewContext(readFileSync(new URL('../catalogue-editor.js',import.meta.url),'utf8'),{document,window,location,history:{replaceState:(_,__,url)=>location.href=String(url)},URL,structuredClone,Event:class{constructor(type){this.type=type}}});
const findButton=text=>all(view).find(n=>n.tagName==='BUTTON'&&n.textContent===text);
const field=text=>{const label=all(view).find(n=>n.tagName==='LABEL'&&n.text===text);assert.ok(label,`Missing field ${text}`);return label.children.find(n=>['INPUT','TEXTAREA','SELECT'].includes(n.tagName))};
const type=(name,value)=>{const n=field(name);n.value=value;n.oninput();return n};
const choose=(name,value)=>{const n=field(name);n.value=value;n.onchange()};
await window.catalogueEditor.load();
type('Title','Pending catalogue title');
findButton('Edit product page').onclick();
assert.equal(field('Product title').value,'Pending catalogue title');
assert.ok(window.catalogueEditor.dirty());
let body=type('Description','Bold\n\nFirst\nSecond');body.setSelectionRange(0,4);
all(view).filter(n=>n.className==='format-toolbar')[1].children[0].onclick();
assert.equal(body.value,'**Bold**\n\nFirst\nSecond');assert.equal(document.activeElement,body);assert.equal(body.selectionStart,2);
body.setSelectionRange(10,body.value.length);
all(view).filter(n=>n.className==='format-toolbar')[1].children[1].onclick();
assert.equal(body.value,'**Bold**\n\n- First\n- Second');assert.equal(document.activeElement,body);
type('Section title (optional)','Section');type('Label','New label');type('Value','New value');type('Image alt text','Legacy alt');type('Price note (optional)','Price note');
choose('Editing language','en');assert.equal(field('Description').value,'Existing translation');type('Description','**English**');
choose('Editing language','ka');assert.equal(field('Description').value,'**Bold**\n\n- First\n- Second');
findButton('← Back (keep edits)').onclick();assert.equal(field('Title').value,'Pending catalogue title');
findButton('Edit product page').onclick();assert.equal(field('Label').value,'New label');
await findButton('Choose image').onclick();
const picker=document.getElementById('catalogueImageResults');picker.children[0].onclick();
assert.equal(field('Image alt text').value,'Legacy alt');
failSave=true;await findButton('Save & Generate').onclick();assert.ok(window.catalogueEditor.dirty());
assert.match(document.getElementById('catalogueStatus').textContent,/Simulated validation/);
failSave=false;await findButton('Save & Generate').onclick();assert.equal(window.catalogueEditor.dirty(),false);
assert.deepEqual(submitted.products.sample.unknown,{preserve:true});
assert.equal(submitted.products.sample.images[0].path,'assets/new.png');
assert.equal(submitted.products.sample.images[0].alt.ka,'Legacy alt');
assert.equal(submitted.products.sample.images[1].path,'assets/old.png');
assert.equal(submitted.products.sample.image,undefined);
assert.equal(submitted.products.sample.gallery,undefined);
assert.equal(submitted.products.sample.description[0].body.en,'**English**');
window.catalogueEditor.discard();await window.catalogueEditor.load();
assert.equal(field('Description').value,'**Bold**\n\n- First\n- Second');
assert.equal(field('Label').value,'New label');assert.equal(field('Value').value,'New value');
assert.equal(field('Product title').value,'Pending catalogue title');
await findButton('+ Add image').onclick();picker.children[0].onclick();
findButton('Make primary').onclick();
await findButton('Save & Generate').onclick();
assert.equal(submitted.products.sample.images[0].path,'assets/old.png');
assert.equal(submitted.products.sample.images.length,3);
window.catalogueEditor.discard();await window.catalogueEditor.load();
assert.match(all(view).find(n=>n.className==='product-image-item').textContent,/1 · Primary/);
findButton('Move right →').onclick();
findButton('Remove image').onclick();
await findButton('Save & Generate').onclick();
assert.equal(submitted.products.sample.images.length,2);
assert.equal(submitted.products.sample.images[0].path,'assets/old.png');
// A successful request must not mark edits made during that request as saved.
finishSave=true;const pending=findButton('Save & Generate').onclick();type('Section title (optional)','Newer unsaved heading');finishSave();await pending;
assert.ok(window.catalogueEditor.dirty());
let prevented=false;events.beforeunload({preventDefault:()=>prevented=true});assert.ok(prevented);
console.log('PASS: shared editor state, Back/reopen, formatting selection/focus, translations, legacy gallery, save/reload, errors and edits during save (DOM-state checks only).');
