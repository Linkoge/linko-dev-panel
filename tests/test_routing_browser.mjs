import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {readFileSync} from 'node:fs';
import {chromium} from 'playwright';

const fixture=spawn(process.env.PANEL_TEST_PYTHON||'.venv/bin/python',['tests/routing_fixture.py'],{stdio:['ignore','pipe','pipe']});
let stderr='',browser;
fixture.stderr.on('data',data=>stderr+=data);
try {
  const config=await new Promise((resolve,reject)=>{
    createInterface({input:fixture.stdout}).once('line',line=>resolve(JSON.parse(line)));
    fixture.once('exit',code=>reject(Error(`Fixture exited ${code}: ${stderr}`)));
  });
  const origin=`http://127.0.0.1:${config.port}`,prefix='/site/Routing/preview';
  const read=()=>JSON.parse(readFileSync(config.root+'/data/catalog.json','utf8'));
  const originalOrder=read().root.map(ref=>ref.id);
  browser=await chromium.launch({executablePath:process.env.LINKO_PANEL_CHROME||'/usr/bin/google-chrome',args:['--no-sandbox']});
  for(const mobile of [false,true]) {
    const context=await browser.newContext({viewport:mobile?{width:360,height:800}:{width:1440,height:1000},hasTouch:mobile,isMobile:mobile});
    await context.addInitScript(()=>localStorage.setItem('linko-language','ru'));
    const page=await context.newPage(),errors=[],failed=[];
    page.on('pageerror',error=>errors.push(String(error)));
    page.on('response',response=>{if(response.status()>=400&&response.url().startsWith(origin+prefix))failed.push(response.url());});
    for(const [language,marker] of [['ka',''],['en','/en'],['ru','/ru']]) {
      await page.goto(origin+prefix+marker+'/products');
      assert.equal(await page.locator('html').getAttribute('lang'),language);
      assert.equal(await page.locator('.product-card').count(),9);
      const paths=await page.locator('.product-card').evaluateAll(cards=>cards.map(card=>new URL(card.href).pathname));
      assert.ok(paths.every(path=>path.startsWith(prefix+marker+'/products/')||path.startsWith(prefix+marker+'/services/')));
      const result=await page.goto(origin+prefix+marker+'/products/P01-starlink-standard-4x');
      assert.equal(result.status(),200);
      assert.equal(await page.locator('html').getAttribute('lang'),language);
      assert.equal(await page.locator('.detail-catalogue-id').textContent(),'P01');
      assert.equal(await page.locator('.detail-catalogue-id').evaluate(node=>getComputedStyle(node).fontSize),'12px');
      assert.equal(await page.locator('[rel=canonical]').getAttribute('href'),`https://linko.ge${marker}/products/P01-starlink-standard-4x`);
      assert.equal(await page.locator('link[rel=alternate]').count(),4);
      assert.equal(await page.locator('meta[name=robots]').count(),language==='ka'?0:1);
      await page.locator('[data-main-photo]').evaluate(img=>img.decode());
      assert.equal(await page.locator('[data-main-photo]').evaluate(img=>img.naturalWidth>0),true);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
      await page.screenshot({path:`/tmp/linko-routing-${language}-${mobile?'mobile':'desktop'}.png`,fullPage:true});
      await page.evaluate(()=>window.scrollTo(0,document.body.scrollHeight));
      await page.waitForTimeout(400);
      await page.locator('.page-back-link').click();
      await page.waitForURL(origin+prefix+marker+'/products');
      await page.goto(origin+prefix+marker+'/contact');
      assert.equal(await page.locator('html').getAttribute('lang'),language);
      await page.goto(origin+prefix+marker+'/');
      assert.equal(await page.locator('html').getAttribute('lang'),language);
      await page.locator('.menu-toggle').click();
      const next=language==='ka'?'en':'ka';
      await Promise.all([page.waitForURL(origin+prefix+(next==='ka'?'/':'/en/')),page.locator(`[data-language=${next}]`).click()]);
      assert.equal(await page.locator('html').getAttribute('lang'),next);
    }
    assert.deepEqual(errors,[]);assert.deepEqual(failed,[]);
    await context.close();
    console.log(`PASS ${mobile?'360px touch':'1440px desktop'}: language routes, storage precedence, catalogue/order, detail ID, galleries/assets, SEO, backlink, home/contact switching and overflow.`);
  }
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  const page=await context.newPage();
  await page.goto(origin+'/?project=Routing&view=products');
  await page.getByRole('button',{name:'Add Product',exact:true}).waitFor();
  const save=async()=>{await page.getByRole('button',{name:'Save & Generate',exact:true}).click();await page.locator('#catalogueStatus').filter({hasText:/Saved\. Generated/}).waitFor();};
  await page.getByRole('button',{name:'Add Product',exact:true}).click();
  await page.locator('.editor-item').last().getByRole('button',{name:'Edit product page',exact:true}).click();
  await page.getByLabel('Product title',{exact:true}).fill('New equipment');
  await page.getByLabel('Editing language').selectOption('en');
  await page.getByLabel('Product title',{exact:true}).fill('New standard kit');
  await page.getByLabel('Destination').selectOption('generated');
  await page.getByLabel('Publish detail page').selectOption('true');
  await save();
  assert.ok(page.url().includes('product=P08'));
  assert.match(await page.locator('.detail-editor').innerText(),/Permanent ID: P08/);
  const saved=JSON.parse(readFileSync(config.root+'/data/products/P08.json','utf8'));
  assert.equal(saved.slug,'new-standard-kit');
  const [preview]=await Promise.all([context.waitForEvent('page'),page.getByRole('button',{name:'Preview saved page',exact:true}).click()]);
  await preview.waitForLoadState();
  assert.match(preview.url(),/\/en\/products\/P08-new-standard-kit$/);
  assert.equal(await preview.locator('.detail-catalogue-id').textContent(),'P08');await preview.close();
  await page.getByLabel('URL slug',{exact:true}).fill('edited-kit');
  await page.getByLabel('Product title',{exact:true}).fill('Renamed equipment');
  await save();
  assert.equal(JSON.parse(readFileSync(config.root+'/data/products/P08.json','utf8')).id,'P08');
  await page.getByRole('button',{name:'← Back (keep edits)',exact:true}).click();
  await page.getByRole('button',{name:'Add Service',exact:true}).click();await save();
  assert.equal(JSON.parse(readFileSync(config.root+'/data/products/S03.json','utf8')).kind,'service');
  assert.deepEqual(read().root.slice(0,9).map(ref=>ref.id),originalOrder);
  // Check permanent HTTP aliases and a real 404 through the actual preview server.
  for(const [path,target] of [['product-starlink-device?lang=en','/en/products/P01-starlink-standard-4x'],
                              ['products.html?lang=ru','/ru/products'],['en/index.html','/en/'],
                              ['products/P08-new-standard-kit','/products/P08-edited-kit']]) {
    const response=await page.request.get(origin+prefix+'/'+path,{maxRedirects:0});
    assert.equal(response.status(),301,path);assert.equal(response.headers().location,prefix+target,path);
  }
  for(const path of ['missing','products/P99999-unknown','services/P01-wrong-kind']) {
    const response=await page.request.get(origin+prefix+'/'+path,{maxRedirects:0});assert.equal(response.status(),404,path);
  }
  const noJS=await browser.newContext({javaScriptEnabled:false});
  const staticPage=await noJS.newPage();await staticPage.goto(origin+prefix+'/en/products/P01-starlink-standard-4x');
  assert.equal(await staticPage.locator('html').getAttribute('lang'),'en');
  assert.equal(await staticPage.locator('.detail-actions').getByText('Call',{exact:true}).count(),1);
  assert.equal(await staticPage.locator('.detail-catalogue-id').textContent(),'P01');
  await noJS.close();await context.close();
  console.log('PASS: real editor new product/service allocation, returned permanent ID, generated slug, Save & Generate, saved EN preview, rename/slug identity, historical redirects, actual 404 and no-JavaScript EN rendering.');
} finally {
  await browser?.close();fixture.kill('SIGTERM');
  await new Promise(resolve=>fixture.exitCode!==null?resolve():fixture.once('exit',resolve));
}
