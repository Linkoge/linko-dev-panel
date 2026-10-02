// Optional smoke check of the installed private service. No project writes,
// commits, pushes or session destruction. Leaves a new shell session persistent.
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {chromium} from 'playwright';
const settings = execFileSync('systemctl', ['--user','show','linko-dev-panel.service','--property=Environment','--value'], {encoding:'utf8'});
const host = settings.match(/LINKO_PANEL_HOST=([^\s"]+)/)?.[1] || '127.0.0.1';
const port = settings.match(/LINKO_PANEL_PORT=([^\s"]+)/)?.[1] || '8765';
const origin = process.env.LINKO_PANEL_LIVE_ORIGIN || `http://${host}:${port}`;
const browser = await chromium.launch({executablePath:process.env.LINKO_PANEL_CHROME || '/usr/bin/google-chrome',args:['--no-sandbox']});
try {
  const page = await browser.newPage({viewport:{width:1400,height:900}});
  const errors=[]; page.on('pageerror', error => errors.push(String(error)));
  await page.goto(origin);
  await page.waitForFunction(() => document.querySelector('#online').textContent.includes('Server online'));
  const projects = await (await page.request.get(origin+'/api/projects')).json();
  const project = projects.projects.find(p => p.name === 'Dev Panel');
  assert.ok(project, 'installed service has the known Dev Panel project');
  await page.selectOption('#project', project.name);
  const status = await (await page.request.get(`${origin}/api/terminal/status?project=${encodeURIComponent(project.name)}`)).json();
  assert.ok(status.available);
  const [terminal] = await Promise.all([page.context().waitForEvent('page'),page.locator('#openTerminal').click()]);
  terminal.on('pageerror', error=>errors.push(String(error)));
  await terminal.waitForFunction(() => document.querySelector('#connectionState').textContent === '● Connected');
  const tmux = (...args) => execFileSync('tmux',['-L','linko-dev-panel',...args],{encoding:'utf8',stdio:['ignore','pipe','pipe']}).trim();
  // Inspect state instead of typing into a possibly already-running application.
  assert.equal(tmux('display-message','-p','-t',status.session,'#{pane_current_path}'), process.cwd());
  const panePid = tmux('display-message','-p','-t',status.session,'#{pane_pid}');
  await terminal.close();
  await new Promise(resolve=>setTimeout(resolve,700));
  assert.equal(tmux('list-clients','-t',status.session,'-F','#{client_pid}'), '');
  tmux('has-session','-t',status.session);
  if (process.argv.includes('--restart')) {
    for (const p of projects.projects.filter(p=>p.capturePages?.length)) {
      const capture = await (await page.request.get(`${origin}/api/screenshots?project=${encodeURIComponent(p.name)}`)).json();
      assert.ok(!capture.job?.running, 'no capture active before restart');
    }
    execFileSync('systemctl',['--user','restart','linko-dev-panel.service'],{stdio:'pipe'});
    await new Promise(resolve=>setTimeout(resolve,700));
    assert.equal(tmux('display-message','-p','-t',status.session,'#{pane_pid}'),panePid);
    console.log('PASS installed service restart: identical persistent tmux pane remains alive.');
  }
  for (const p of projects.projects) {
    for (const route of ['status','history','diff']) {
      const response=await page.request.get(`${origin}/api/${route}?project=${encodeURIComponent(p.name)}`);
      assert.equal(response.status(),200,`${p.name} ${route}`);
    }
    if(p.previewUrl) assert.equal((await page.request.get(origin+p.previewUrl)).status(),200,'website preview');
    if(p.catalogue) assert.equal((await page.request.get(`${origin}/api/catalogue?project=${encodeURIComponent(p.name)}`)).status(),200,'catalogue snapshot');
  }
  assert.deepEqual(errors,[]);
  console.log('PASS installed service: selector/open terminal, correct project cwd, disconnect cleanup, persistent tmux shell, all project status/history/diff, website preview and catalogue snapshot.');
} finally { await browser.close(); }
