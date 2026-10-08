// Real startup, warning rendering, empty-state controls, and recovery on reload.
import assert from 'node:assert/strict';
import {spawn, execFileSync} from 'node:child_process';
import {createInterface} from 'node:readline';
import {chromium} from 'playwright';

const env = {...process.env, DISPLAY:'', WAYLAND_DISPLAY:'', XAUTHORITY:'', PANEL_TEST_MISSING_PROJECTS:'1'};
let browser;
try {
  browser = await chromium.launch({executablePath:process.env.LINKO_PANEL_CHROME || '/usr/bin/google-chrome', args:['--no-sandbox'], env});
  for (const emptyStart of [false, true]) {
    const fixture = spawn(process.env.PANEL_TEST_PYTHON || '.venv/bin/python', ['tests/onboarding_fixture.py'], {
      stdio:['ignore','pipe','pipe'], env:{...env, PANEL_TEST_EMPTY_START:emptyStart ? '1' : '0'}
    });
    let stderr = '';
    fixture.stderr.on('data', chunk => stderr += chunk);
    let context;
    try {
      const config = await new Promise((resolve, reject) => {
        createInterface({input:fixture.stdout}).once('line', line => resolve(JSON.parse(line)));
        fixture.once('exit', code => reject(new Error(`Fixture exited ${code}: ${stderr}`)));
      });
      context = await browser.newContext({viewport:{width:390,height:844}});
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(String(error)));
      await page.goto(`http://127.0.0.1:${config.port}`);
      await page.waitForFunction(() => document.querySelector('#online').textContent.includes('online'));
      assert.equal(await page.locator('#projectWarnings').isVisible(), true);
      assert.match(await page.locator('#projectErrors').innerText(), /Missing <script>/);
      assert.match(await page.locator('#projectErrors').innerText(), /directory does not exist/);
      assert.equal(await page.locator('#projectErrors script').count(), 0, 'error names render as text');
      assert.equal(await page.locator('#project option').count(), emptyStart ? 0 : 1);
      assert.equal(await page.locator('#project').isDisabled(), emptyStart);
      assert.equal(await page.locator('#emptyProjects').isVisible(), emptyStart);
      if (emptyStart) {
        assert.match(await page.locator('#emptyProjects').innerText(), /No available projects/);
        assert.equal(await page.locator('#openTerminal').isVisible(), false);
        assert.equal(await page.locator('#repositoryView').isVisible(), false);
      } else {
        await page.waitForFunction(() => document.querySelector('#projectName').textContent === 'Existing');
      }
      await page.locator('#addProject').click();
      assert.equal(await page.locator('#repositoryUrl').isVisible(), true);
      await page.locator('#closeAddProject').click();
      assert.match(stderr, /Project unavailable/);

      execFileSync('git', ['init', '-q', '-b', 'main', `${config.projects}/missing`]);
      await page.reload();
      await page.waitForFunction(() => document.querySelector('#projectWarnings').classList.contains('hidden'));
      await page.waitForFunction(() => document.querySelector('#online').textContent.includes('online'));
      assert.equal(await page.locator('#project option').count(), emptyStart ? 1 : 2);
      assert.equal(await page.locator('#project').isEnabled(), true);
      assert.equal(await page.locator('#emptyProjects').isVisible(), false);
      assert.equal(await page.locator('#openTerminal').isVisible(), true);
      assert.deepEqual(errors, []);
      console.log(`PASS ${emptyStart ? 'all' : 'one'} configured project missing: online, visible error, Add Project works, recovery without restart`);
    } finally {
      await context?.close();
      if (fixture.exitCode === null) {
        fixture.kill('SIGTERM');
        await new Promise(resolve => fixture.once('exit', resolve));
      }
    }
  }
} finally {
  await browser?.close();
}
