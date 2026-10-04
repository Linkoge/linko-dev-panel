// Actual URL argv + real Git, private URL rewrites, headless Chrome + real tmux.
import assert from 'node:assert/strict';
import {spawn, execFileSync} from 'node:child_process';
import {createInterface} from 'node:readline';
import {readFileSync, existsSync} from 'node:fs';
import {chromium} from 'playwright';

const env = {...process.env, DISPLAY:'', WAYLAND_DISPLAY:'', XAUTHORITY:''};
const fixture = spawn(process.env.PANEL_TEST_PYTHON || '.venv/bin/python', ['tests/onboarding_fixture.py'], {stdio:['ignore','pipe','pipe'], env});
let stderr = '';
fixture.stderr.on('data', chunk => stderr += chunk);
let browser;
try {
  const config = await new Promise((resolve, reject) => {
    createInterface({input:fixture.stdout}).once('line', line => resolve(JSON.parse(line)));
    fixture.once('exit', code => reject(new Error(`Fixture exited ${code}: ${stderr}`)));
  });
  const origin = `http://127.0.0.1:${config.port}`;
  browser = await chromium.launch({executablePath:process.env.LINKO_PANEL_CHROME || '/usr/bin/google-chrome', args:['--no-sandbox'],env});
  const context = await browser.newContext({viewport:{width:1100,height:900}});
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  await page.goto(origin);
  await page.waitForFunction(() => document.querySelector('#projectName').textContent === 'Existing');
  await page.waitForFunction(() => document.querySelector('#commits').textContent.includes('fixture file'));
  assert.equal(await page.locator('#project option').count(), 1);
  assert.match(await page.locator('#commits').innerText(), /fixture file/);
  await page.locator('#addProject').click();
  await page.locator('#repositoryUrl').fill('https://host/../escape.git');
  await page.waitForFunction(() => document.querySelector('#cloneStatus').textContent.includes('Use an SSH'));
  assert.equal(await page.locator('#cloneProject').isDisabled(), true);
  await page.locator('#repositoryUrl').fill('git@git.fixture.invalid:team/empty.git');
  await page.waitForFunction(() => !document.querySelector('#cloneProject').disabled);
  assert.equal(await page.locator('#cloneRepository').innerText(), 'team/empty');
  assert.equal(await page.locator('#cloneLocalPath').innerText(), `${config.projects}/empty`);
  await page.locator('#cloneProject').click();
  await page.waitForFunction(() => document.querySelector('#project').value === 'empty' && !document.querySelector('#addProjectDialog').open);
  assert.match(await page.locator('#statusHeading').innerText(), /EMPTY REPOSITORY/);
  assert.match(await page.locator('#commits').innerText(), /No commits/);
  assert.equal(await page.locator('#project option').count(), 2);
  const [terminal] = await Promise.all([context.waitForEvent('page'), page.locator('#openTerminal').click()]);
  await terminal.waitForFunction(() => document.querySelector('#connectionState').textContent === '● Connected');
  const tmux = (...args) => execFileSync('tmux', ['-L',config.socket,...args], {encoding:'utf8',stdio:['ignore','pipe','pipe']}).trim();
  const session = tmux('list-sessions', '-F', '#{session_name}');
  assert.equal(tmux('display-message','-p','-t',session,'#{pane_current_path}'), `${config.projects}/empty`);
  const input = terminal.locator('.xterm-helper-textarea');
  await input.focus();
  await terminal.keyboard.type("printf 'created in browser terminal\\n' > first.txt");
  await terminal.keyboard.press('Enter');
  await terminal.waitForFunction(() => document.querySelector('.xterm-screen').textContent.includes('first.txt'));
  for (let i=0; i<100 && !existsSync(`${config.projects}/empty/first.txt`); i++) await new Promise(r=>setTimeout(r,50));
  assert.equal(readFileSync(`${config.projects}/empty/first.txt`,'utf8'), 'created in browser terminal\n');
  await terminal.close();
  console.log('PASS SSH-form empty clone, automatic selector refresh, empty status/history, real terminal cwd/file creation');

  await page.locator('#addProject').click();
  await page.locator('#repositoryUrl').fill('https://git.fixture.invalid/team/empty.git');
  await page.waitForFunction(() => document.querySelector('#cloneStatus').textContent.includes('already exists'));
  assert.equal(await page.locator('#cloneProject').isDisabled(), true);
  await page.locator('#openExistingProject').click();
  assert.equal(readFileSync(`${config.projects}/empty/first.txt`,'utf8'), 'created in browser terminal\n');
  await page.locator('#addProject').click();
  await page.locator('#repositoryUrl').fill('https://git.fixture.invalid/team/missing.git');
  await page.waitForFunction(() => !document.querySelector('#cloneProject').disabled);
  await page.locator('#cloneProject').click();
  await page.waitForFunction(() => document.querySelector('#cloneStatus').textContent.includes('Repository unavailable'));
  await page.waitForFunction(() => !document.querySelector('#cloneProject').disabled);
  assert.equal(existsSync(`${config.projects}/missing`), false);
  assert.equal(await page.locator('#cloneProject').isEnabled(), true, 'failed operation can be retried');
  await page.locator('#repositoryUrl').fill('https://git.fixture.invalid/team/success.git');
  await page.waitForFunction(() => !document.querySelector('#cloneProject').disabled && document.querySelector('#cloneRepository').textContent === 'team/success');
  await page.locator('#cloneProject').click();
  await page.waitForFunction(() => document.querySelector('#project').value === 'success' && !document.querySelector('#addProjectDialog').open);
  assert.equal(readFileSync(`${config.projects}/success/keep.txt`,'utf8'), 'committed original\n');
  await page.locator('#project').selectOption('Existing');
  await page.waitForFunction(() => document.querySelector('#projectName').textContent === 'Existing');
  await page.waitForFunction(() => document.querySelector('#commits').textContent.includes('fixture file'));
  assert.equal(readFileSync(`${config.projects}/existing/keep.txt`,'utf8'), 'unsaved original\n');
  assert.match(await page.locator('#commits').innerText(), /fixture file/);
  console.log('PASS HTTPS-form nonempty clone, duplicate selection, failed clone cleanup/retry, original project selection/history/files preserved');

  await page.setViewportSize({width:390,height:844});
  await page.locator('#addProject').click();
  assert.equal(await page.locator('#repositoryUrl').isVisible(), true);
  assert.equal(await page.locator('#closeAddProject').isVisible(), true);
  assert.deepEqual(errors, []);
  console.log('PASS mobile dialog and no browser script errors');

  const freshFixture = spawn(process.env.PANEL_TEST_PYTHON || '.venv/bin/python', ['tests/onboarding_fixture.py'], {
    stdio:['ignore','pipe','pipe'], env:{...env, PANEL_TEST_EMPTY_START:'1'}
  });
  let freshErrors = '';
  freshFixture.stderr.on('data', chunk => freshErrors += chunk);
  try {
    const fresh = await new Promise((resolve,reject) => {
      createInterface({input:freshFixture.stdout}).once('line', line => resolve(JSON.parse(line)));
      freshFixture.once('exit', code => reject(new Error(`Fresh fixture exited ${code}: ${freshErrors}`)));
    });
    const freshPage = await context.newPage();
    const freshPageErrors = [];
    freshPage.on('pageerror', error => freshPageErrors.push(String(error)));
    await freshPage.goto(`http://127.0.0.1:${fresh.port}`);
    await freshPage.locator('#emptyProjects').waitFor({state:'visible'});
    assert.equal(await freshPage.locator('#project option').count(), 0);
    await freshPage.locator('#addProject').click();
    await freshPage.locator('#repositoryUrl').fill('https://git.fixture.invalid/team/empty.git');
    await freshPage.waitForFunction(() => !document.querySelector('#cloneProject').disabled);
    await freshPage.locator('#cloneProject').click();
    await freshPage.waitForFunction(() => document.querySelector('#project').value === 'empty' && !document.querySelector('#addProjectDialog').open);
    assert.equal(await freshPage.locator('#emptyProjects').isHidden(), true);
    assert.equal(await freshPage.locator('#openTerminal').isVisible(), true);
    assert.match(await freshPage.locator('#statusHeading').innerText(), /EMPTY REPOSITORY/);
    assert.deepEqual(freshPageErrors, []);
    await freshPage.close();
    console.log('PASS fresh installation with no configured/discovered projects and first-project onboarding');
  } finally {
    freshFixture.kill('SIGTERM');
    await new Promise(resolve => freshFixture.exitCode !== null ? resolve() : freshFixture.once('exit',resolve));
  }
} finally {
  await browser?.close();
  fixture.kill('SIGTERM');
  await new Promise(resolve => fixture.exitCode !== null ? resolve() : fixture.once('exit',resolve));
}
