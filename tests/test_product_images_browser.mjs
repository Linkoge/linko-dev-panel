import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {readFileSync,existsSync} from 'node:fs';
import {chromium} from 'playwright';
const fixture=spawn(process.env.PANEL_TEST_PYTHON||'.venv/bin/python',['tests/product_images_fixture.py'],{stdio:['ignore','pipe','pipe']});
let stderr='',browser;
fixture.stderr.on('data',chunk=>stderr+=chunk);
try {
  const config=await new Promise((resolve,reject)=>{
    createInterface({input:fixture.stdout}).once('line',line=>resolve(JSON.parse(line)));
    fixture.once('exit',code=>reject(Error(`Fixture exited ${code}: ${stderr}`)));
  });
  const origin=`http://127.0.0.1:${config.port}`;
  browser=await chromium.launch({executablePath:process.env.LINKO_PANEL_CHROME||'/usr/bin/google-chrome',args:['--no-sandbox']});
  for(const mobile of [false,true]) {
    const context=await browser.newContext({viewport:mobile?{width:360,height:800}:{width:1440,height:1000},hasTouch:mobile,isMobile:mobile});
    const page=await context.newPage();const errors=[];
    page.on('pageerror',error=>errors.push(String(error)));
    await page.goto(`${origin}/?project=Images&view=products&product=mounts`);
    await page.getByRole('heading',{name:'Product images',exact:true}).waitFor();
    const rows=page.locator('.product-image-item');
    const read=()=>JSON.parse(readFileSync(`${config.root}/data/products/mounts.json`,'utf8'));
    const save=async()=>{await page.getByRole('button',{name:'Save & Generate',exact:true}).click();await page.locator('#catalogueStatus').filter({hasText:/Saved\. Generated/}).waitFor();};
    const reload=async()=>{await page.reload();await page.getByRole('heading',{name:'Product images',exact:true}).waitFor();};
    const add=async name=>{await page.getByRole('button',{name:'+ Add image',exact:true}).click();await page.locator('#catalogueImageResults button').filter({hasText:name}).click();};
    // The second viewport starts from the one-image product left by the first.
    assert.equal(await rows.count(),1);
    assert.match(await rows.first().innerText(),/1 · Primary \/ cover/);
    assert.equal(await rows.first().getByRole('button',{name:'Remove image',exact:true}).isDisabled(),true);
    await save();assert.ok(read().image||read().images?.length===1);
    const detail=await context.newPage();detail.on('pageerror',error=>errors.push(String(error)));
    await detail.goto(`${origin}/site/Images/preview/product-mounts.html`);
    assert.equal(await detail.locator('.detail-thumbs').count(),0);
    await add('portrait.png');await add('landscape.png');
    await page.getByRole('button',{name:'+ Add image',exact:true}).click();
    await page.locator('#catalogueImageUpload').setInputFiles({name:'Uploaded square.png',mimeType:'image/png',buffer:readFileSync(`${config.root}/assets/product-images/square.png`)});
    await page.locator('#catalogueImageDialog').waitFor({state:'hidden'});
    assert.equal(await rows.count(),4);
    await save();const ordered=read().images.map(i=>i.path);
    assert.equal(ordered.length,4);assert.equal(read().image,undefined);assert.equal(read().gallery,undefined);
    await reload();assert.equal(await rows.count(),4);
    assert.deepEqual(await rows.locator('img').evaluateAll(images=>images.map(img=>decodeURI(new URL(img.src).pathname.split('/preview/')[1]))),ordered);
    if(!mobile) {
      await rows.nth(2).dragTo(rows.first());await save();
      assert.equal(read().images[0].path,ordered[2]);
    } else {
      await rows.nth(2).getByRole('button',{name:'← Move left',exact:true}).tap();
      await rows.nth(1).getByRole('button',{name:'Make primary',exact:true}).tap();
      await save();assert.equal(read().images[0].path,ordered[2]);
    }
    await reload();assert.equal(await rows.count(),4);
    const reordered=read().images.map(i=>i.path);
    await detail.reload();
    assert.equal(await detail.locator('.detail-thumb').count(),4);
    const main=detail.locator('[data-main-photo]'),stage=detail.locator('.detail-stage');
    assert.match(await main.getAttribute('src'),/landscape/);
    const before=await stage.boundingBox();
    await detail.locator('.detail-thumb').nth(2).click();
    assert.equal(await main.getAttribute('src'),reordered[2]);
    assert.equal(await detail.locator('.detail-thumb').nth(2).getAttribute('aria-pressed'),'true');
    await main.evaluate(img=>img.decode());
    const after=await stage.boundingBox();assert.ok(Math.abs(before.height-after.height)<1);
    assert.equal(await main.evaluate(img=>getComputedStyle(img).objectFit),'contain');
    const card=await context.newPage();await card.goto(`${origin}/site/Images/preview/products.html`);
    assert.equal(await card.locator('.product-media img').first().getAttribute('src'),reordered[0]);
    assert.equal(await card.locator('.product-media img').count(),1);
    await card.close();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    assert.equal(await detail.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.screenshot({path:`/tmp/phase3-editor-${mobile?'mobile':'desktop'}.png`,fullPage:true});
    await detail.screenshot({path:`/tmp/phase3-gallery-${mobile?'mobile':'desktop'}.png`,fullPage:true});
    const [preview]=await Promise.all([context.waitForEvent('page'),page.getByRole('button',{name:'Preview saved page',exact:true}).click()]);
    await preview.waitForLoadState();assert.equal(await preview.locator('.detail-thumb').count(),4);await preview.close();
    // A secondary asset returning 404 is disabled; valid images remain selectable.
    await detail.route(`**/${reordered[1].split('/').at(-1)}`,route=>route.fulfill({status:404,body:'missing'}));
    await detail.reload();await detail.locator('.detail-thumb').nth(1).waitFor();
    await detail.waitForFunction(()=>document.querySelectorAll('.detail-thumb')[1].disabled);
    await detail.locator('.detail-thumb').nth(3).click();assert.equal(await main.getAttribute('src'),reordered[3]);
    // All missing images leave a stable placeholder without JavaScript errors.
    await detail.route('**/assets/product-images/*',route=>route.fulfill({status:404,body:'missing'}));
    await detail.reload();await detail.locator('.detail-stage[data-unavailable="true"]').waitFor();
    assert.equal(await detail.locator('.detail-open').isDisabled(),true);
    assert.ok((await stage.boundingBox()).height>100);
    // Remove secondary references and keep uploaded/shared underlying files.
    while(await rows.count()>1)await rows.nth(1).getByRole('button',{name:'Remove image',exact:true}).click();
    await save();await reload();assert.equal(await rows.count(),1);
    for(const path of ordered)assert.equal(existsSync(`${config.root}/${path}`),true);
    await detail.unrouteAll();await detail.reload();assert.equal(await detail.locator('.detail-thumbs').count(),0);
    // Reset the cover through the preserved picker for the next viewport.
    await rows.first().getByRole('button',{name:'Choose image',exact:true}).click();
    await page.locator('#catalogueImageResults button').filter({hasText:'mounts.svg'}).click();await save();
    assert.deepEqual(errors,[]);
    console.log(`PASS ${mobile?'360px touch mobile':'1440px desktop'}: legacy/single image, add/pick/upload, save/reload, order/cover, ${mobile?'touch controls':'native drag/drop'}, remove/assets, catalogue, saved preview, gallery selection/fit/stability, broken/all-missing images, no horizontal overflow or JS errors`);
    await context.close();
  }
  const page=await browser.newPage();
  await page.goto(`${origin}/?project=Images&view=products`);
  await page.getByRole('button',{name:'Add Product',exact:true}).click();
  await page.locator('.editor-item').last().getByRole('button',{name:'Edit product page',exact:true}).click();
  assert.equal(await page.locator('.product-image-item').count(),1);
  await page.getByRole('button',{name:'Save & Generate',exact:true}).click();
  await page.locator('#catalogueStatus').filter({hasText:/Saved\. Generated/}).waitFor();
  const draft=JSON.parse(readFileSync(`${config.root}/data/products/draft-product.json`,'utf8'));
  assert.equal(draft.images.length,1);assert.equal(draft.image,undefined);
  await page.reload();await page.locator('.product-image-item').waitFor();
  assert.equal(await page.locator('.product-image-item').count(),1);
  console.log('PASS create/save/reload a new canonical one-image product');
} finally {
  await browser?.close();fixture.kill('SIGTERM');
}
