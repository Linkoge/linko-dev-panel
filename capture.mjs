/** Capture configured local previews using real Chromium scroll positions. */
import fs from 'node:fs';
import path from 'node:path';
import { chromium, devices } from 'playwright';
import { nextScrollPosition } from './scroll_plan.mjs';

const config = JSON.parse(fs.readFileSync(0, 'utf8'));
const presets = {
  mobile: {width: 390, height: 844, deviceScaleFactor: 2, isMobile: true,
    hasTouch: true, userAgent: devices['Pixel 7'].userAgent},
  desktop: {width: 1440, height: 900, deviceScaleFactor: 1, isMobile: false, hasTouch: false},
};
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
function progress(phase, device, current = 0) {
  fs.writeFileSync(path.join(config.outputDir, 'progress.json'), JSON.stringify({phase, device, current}));
}
async function moveTo(page, y) {
  await page.evaluate(target => {
    window.scrollTo({top: target, left: 0, behavior: 'instant'});
  }, y);
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}
async function maxScroll(page) {
  return page.evaluate(() => Math.max(0, Math.ceil(Math.max(
    document.documentElement.scrollHeight, document.body?.scrollHeight || 0
  ) - window.innerHeight)));
}
async function stickyRegions(page) {
  return page.evaluate(() => [...document.querySelectorAll('*')].filter(el => {
    const parent = el.parentElement;
    return parent && getComputedStyle(el).position === 'sticky' &&
      el.getBoundingClientRect().height >= innerHeight * 0.4 &&
      parent.getBoundingClientRect().height >= innerHeight * 2;
  }).slice(0, 20).map(el => {
    const rect = el.parentElement.getBoundingClientRect();
    const top = Math.max(0, Math.round(rect.top + scrollY));
    return {top, end: Math.round(top + rect.height - innerHeight)};
  }).filter(region => region.end > region.top));
}
async function readyImages(page) {
  await page.evaluate(async () => {
    const visible = [...document.images].filter(img => {
      const rect = img.getBoundingClientRect();
      return rect.bottom > 0 && rect.top < innerHeight && rect.right > 0 && rect.left < innerWidth;
    });
    await Promise.race([
      Promise.all(visible.map(async img => {
        if (!img.complete) await new Promise(resolve => {
          img.addEventListener('load', resolve, {once: true});
          img.addEventListener('error', resolve, {once: true});
        });
        if (img.complete && img.naturalWidth) await img.decode().catch(() => {});
      })),
      new Promise(resolve => setTimeout(resolve, 5000))
    ]);
  });
}
async function captureDevice(browser, device) {
  const preset = presets[device];
  const {width, height, ...deviceOptions} = preset;
  const context = await browser.newContext({...deviceOptions, viewport: {width, height},
    screen: {width, height}, colorScheme: 'light', reducedMotion: 'no-preference'});
  try {
    const page = await context.newPage();
    // The source is fixed by projects.json. Prevent navigation to another document.
    page.on('framenavigated', frame => {
      if (frame === page.mainFrame() && !frame.url().startsWith(config.origin + '/')) {
        page.close().catch(() => {});
      }
    });
    await page.goto(config.url, {waitUntil: 'domcontentloaded', timeout: 30000});
    await page.waitForLoadState('load', {timeout: 15000}).catch(() => {});
    await page.evaluate(() => Promise.race([
      document.fonts.ready, new Promise(resolve => setTimeout(resolve, 10000))
    ]));
    // Walk the actual viewport first so native lazy images and scroll-created content load.
    const step = Math.max(1, Math.round(preset.height * (1 - config.overlap / 100)));
    progress('Preparing lazy content', device);
    for (let i = 0, y = 0; i < 100; i++, y += step) {
      const bottom = await maxScroll(page);
      await moveTo(page, Math.min(y, bottom));
      await delay(120);
      if (y >= bottom) break;
    }
    await moveTo(page, 0);
    await delay(config.settleMs);
    const regions = await stickyRegions(page);
    const images = [];
    progress('Capturing', device);
    for (let i = 0, y = 0; i < 100; i++) {
      const bottom = await maxScroll(page);
      const target = Math.min(y, bottom);
      await moveTo(page, target);
      await delay(config.settleMs);
      await readyImages(page);
      const filename = `${device}-raw-${String(i + 1).padStart(3, '0')}.png`;
      await delay(100);
      await page.screenshot({path: path.join(config.outputDir, filename)});
      const state = await page.evaluate(() => ({
        scrollY: Math.round(window.scrollY),
        activeText: [...document.querySelectorAll('.slide-text.active, [aria-current="true"]')]
          .map(el => el.textContent.trim()).join('|').slice(0, 500)
      }));
      images.push({file: filename, ...state});
      progress('Capturing', device, images.length);
      if (target >= bottom) break;
      y = nextScrollPosition(target, bottom, height, config.overlap, regions);
    }
    return {device, images, truncated: images.length === 100 && images.at(-1).scrollY < await maxScroll(page)};
  } finally {
    await context.close();
  }
}

let browser;
try {
  browser = await chromium.launch({executablePath: config.chromeBinary, headless: true,
    args: ['--disable-dev-shm-usage']});
  const groups = [];
  for (const device of config.devices) groups.push(await captureDevice(browser, device));
  process.stdout.write(JSON.stringify({groups}));
} catch (error) {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
} finally {
  await browser?.close();
}
