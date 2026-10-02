// Live Chrome + real PTY/tmux checks against a disposable Git project.
import assert from 'node:assert/strict';
import {spawn, execFileSync} from 'node:child_process';
import {createInterface} from 'node:readline';
import {readFileSync, readdirSync} from 'node:fs';
import {chromium} from 'playwright';

const headlessEnv = {...process.env, DISPLAY:'', WAYLAND_DISPLAY:'', XAUTHORITY:''};
const fixture = spawn(process.env.PANEL_TEST_PYTHON || '.venv/bin/python', ['tests/terminal_fixture.py'], {stdio:['ignore','pipe','pipe'],env:headlessEnv});
let serverErrors = '';
fixture.stderr.on('data', data => { serverErrors += data; });
const config = await new Promise((resolve, reject) => {
  const lines = createInterface({input:fixture.stdout});
  lines.once('line', line => resolve(JSON.parse(line)));
  fixture.once('exit', code => reject(new Error(`Fixture exited ${code}: ${serverErrors}`)));
});
const origin = `http://127.0.0.1:${config.port}`;
const url = `${origin}/terminal?project=${encodeURIComponent(config.project)}`;
const tmux = (...args) => execFileSync('tmux', ['-L', config.socket, ...args], {encoding:'utf8',stdio:['ignore','pipe','pipe']}).trim();
const screen = () => tmux('capture-pane', '-p', '-S', '-10000', '-t', config.session);
const initialFds = readdirSync(`/proc/${fixture.pid}/fd`).length;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(check, label, timeout=20000) {
  const start = Date.now();
  while (Date.now()-start < timeout) { if (await check()) return; await sleep(100); }
  throw new Error(`Timed out: ${label}`);
}
let browser;
try {
  browser = await chromium.launch({executablePath:process.env.LINKO_PANEL_CHROME || '/usr/bin/google-chrome', args:['--no-sandbox'],env:headlessEnv});
  const context = await browser.newContext({viewport:{width:1400,height:900}});
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  await page.goto(origin);
  const rejected = await page.evaluate(async url => {
    return await new Promise(resolve => {
      const ws = new WebSocket(url);
      ws.onopen = () => ws.send(JSON.stringify({type:'connect',ticket:'invalid',cols:80,rows:24}));
      ws.onclose = event => resolve(event.code);
    });
  }, `${origin.replace('http:', 'ws:')}/api/terminal/ws?project=${encodeURIComponent(config.project)}`);
  assert.equal(rejected, 1008, 'invalid ticket rejected');
  assert.throws(() => tmux('has-session', '-t', config.session), 'no session before valid ticket');
  await page.waitForFunction(() => document.querySelector('#openTerminal').href.includes('/terminal?project='));
  const [terminalPage] = await Promise.all([context.waitForEvent('page'), page.locator('#openTerminal').click()]);
  const terminal = terminalPage;
  async function connected(p=terminal) {
    try { await p.waitForFunction(() => document.querySelector('#connectionState').textContent === '● Connected', null, {timeout:10000}); }
    catch(error) { console.error(await p.locator('body').innerText()); throw error; }
  }
  await connected();
  const text = p => p.locator('.xterm-helper-textarea');
  async function command(value) { await text(terminal).focus(); await terminal.keyboard.type(value); await terminal.keyboard.press('Enter'); }
  await command('pwd');
  await until(() => screen().includes(config.path), 'project directory');
  assert.equal(tmux('display-message', '-p', '-t', config.session, '#{pane_current_path}'), config.path);
  await command("printf '\\033[31mANSI_RED\\033[0m\\n'");
  await until(() => terminal.locator('.xterm-screen').textContent().then(t => t.includes('ANSI_RED')), 'ANSI output');
  await until(() => terminal.locator('.xterm-screen span').evaluateAll(nodes => nodes.some(n => {
    const rgb = getComputedStyle(n).color.match(/\d+/g)?.map(Number);
    return rgb && rgb[0] > 100 && rgb[1] < 80 && rgb[2] < 80;
  })), 'ANSI red color rendering');
  await command('seq 1 300');
  await until(() => screen().includes('300'), 'scroll output');
  await terminal.locator('#terminal').hover();
  await terminal.mouse.wheel(0, -1500);
  await until(() => tmux('display-message', '-p', '-t', config.session, '#{pane_in_mode}') === '1', 'wheel enters tmux scrollback');
  await terminal.keyboard.press('Escape');
  await until(() => tmux('display-message', '-p', '-t', config.session, '#{pane_in_mode}') === '0', 'leave scrollback');
  await command('sleep 100');
  await until(() => tmux('display-message','-p','-t',config.session,'#{pane_current_command}') === 'sleep', 'foreground sleep started');
  await terminal.keyboard.press('Control+c');
  await command("printf 'CONTROL_%s\\n' OK");
  await until(() => screen().includes('CONTROL_OK'), 'Ctrl+C');
  await terminal.setViewportSize({width:970,height:640});
  await sleep(500);
  await command('stty size > terminal-size.txt');
  await until(() => {
    try { return readFileSync(`${config.path}/terminal-size.txt`,'utf8').trim() === tmux('display-message', '-p', '-t', config.session, '#{pane_height} #{pane_width}'); }
    catch { return false; }
  }, 'PTY resize');
  console.log('PASS basic: project cwd, shell, ANSI colors, scrolling, Ctrl+C, resize');

  // Read raw bytes in a real terminal application; bracketed paste is explicitly
  // enabled, just as an editor/agent would do. Receiver writes only test files.
  const receiver = `import sys,tty,os; tty.setraw(0); os.write(1,b'\\x1b[?2004hPASTE_READY\\r\\n'); data=bytearray(); end=b'\\x1b[201~'; start=b'\\x1b[200~';\nwhile not data.endswith(end): data.extend(os.read(0,4096))\nopen(sys.argv[1],'wb').write(bytes(data).removeprefix(start).removesuffix(end)); os.write(1,b'\\x1b[?2004lPASTE_DONE\\r\\n')`;
  const cases = ['word', 'One paragraph with ordinary text and "quotes", apostrophes \' and $dollars.',
    Array.from({length:12000}, (_, i) => `Line ${i}: დიდი ტექსტი ქართული 😀 "quotes" \\ code\n`).join(''),
    'function example() {\n  const value = "quote";\n  return `Unicode: ქართული 日本語 😀`;\n}\n',
    'Unicode café é 日本語 😀\nქართული ტექსტი\nsecond line\n\nlast line'];
  await context.grantPermissions(['clipboard-read','clipboard-write'], {origin});
  for (const [index, value] of cases.entries()) {
    const program = Buffer.from(receiver.replace('PASTE_READY', `PASTE_READY_${index}`)).toString('base64');
    await command(`python3 -c 'import base64; exec(base64.b64decode("${program}"))' paste-${index}.txt`);
    await until(() => screen().includes(`PASTE_READY_${index}`), 'paste receiver ready');
    await sleep(250);
    // Real browser clipboard -> native Ctrl+V -> xterm paste event -> PTY.
    await terminal.evaluate(value => navigator.clipboard.writeText(value), value);
    await text(terminal).focus();
    await terminal.keyboard.press('Control+v');
    await until(() => { try { return readFileSync(`${config.path}/paste-${index}.txt`).length > 0; } catch { return false; } }, `paste ${index}`, 60000);
    // xterm follows terminal paste semantics: LF/CRLF become CR on the wire.
    assert.equal(readFileSync(`${config.path}/paste-${index}.txt`, 'utf8'), value.replace(/\r?\n/g,'\r'));
    await command('stty sane; clear');
  }
  await command('echo COPY_OK_ქართული');
  await until(() => terminal.locator('.xterm-screen').textContent().then(t => t.includes('COPY_OK_ქართული')), 'copy text');
  await terminal.locator('#selectAll').click(); await terminal.locator('#copy').click();
  assert.match(await terminal.evaluate(() => navigator.clipboard.readText()), /COPY_OK_ქართული/);
  await terminal.evaluate(() => {
    window.testClipboard = navigator.clipboard;
    Object.defineProperty(navigator, 'clipboard', {configurable:true,value:undefined});
  });
  await terminal.locator('#selectAll').click(); await terminal.locator('#copy').click();
  assert.match(await terminal.evaluate(() => window.testClipboard.readText()), /COPY_OK_ქართული/, 'plain HTTP copy fallback');
  await terminal.evaluate(() => { Object.defineProperty(navigator,'clipboard',{configurable:true,value:window.testClipboard}); delete window.testClipboard; });
  console.log(`PASS clipboard: native browser Ctrl+V for word, paragraph, ${Buffer.byteLength(cases[2])} bytes multiline, code, quotes, Unicode, Georgian, newlines; exact UTF-8 comparison; browser copy; no X11 clipboard`);
  await text(terminal).evaluate(el => {
    el.focus(); const clipboardData = new DataTransfer();
    clipboardData.setData('text/plain', 'x'.repeat(16 * 1024 * 1024 + 1));
    el.dispatchEvent(new ClipboardEvent('paste', {clipboardData,bubbles:true,cancelable:true}));
  });
  await terminal.waitForFunction(() => document.querySelector('#message').textContent.includes('Paste was not sent'));

  // An interactive alternate-screen Python curses application survives reload.
  const tui = `import curses\ndef main(s):\n s.addstr(0,0,'TUI_PERSIST'); s.refresh()\n while s.getch()!=ord('q'):\n  s.erase(); s.addstr(0,0,'TUI_PERSIST'); s.refresh()\ncurses.wrapper(main)`;
  await command(`python3 -c 'import base64; exec(base64.b64decode("${Buffer.from(tui).toString('base64')}"))'`);
  await until(() => screen().includes('TUI_PERSIST'), 'interactive curses application');
  const panePid = tmux('display-message', '-p', '-t', config.session, '#{pane_pid}');
  await terminal.reload(); await connected();
  await until(() => terminal.locator('.xterm-screen').textContent().then(t => t.includes('TUI_PERSIST')), 'TUI after refresh');
  assert.equal(tmux('display-message', '-p', '-t', config.session, '#{pane_pid}'), panePid);
  await page.request.post(`${origin}/test/disconnect`);
  await terminal.waitForFunction(() => document.querySelector('#connectionState').textContent.includes('reconnecting'));
  await connected();
  await until(() => terminal.locator('.xterm-screen').textContent().then(t => t.includes('TUI_PERSIST')), 'TUI after abrupt TCP disconnect/automatic reconnect');
  await context.setOffline(true); await sleep(500); await context.setOffline(false);
  await terminal.locator('#reconnect').click(); await connected();
  await until(() => screen().includes('TUI_PERSIST'), 'TUI after network interruption');
  assert.equal(tmux('display-message', '-p', '-t', config.session, '#{pane_current_command}'), 'python3');
  const second = await context.newPage(); await second.goto(url); await connected(second);
  assert.equal(tmux('list-sessions', '-F', '#{session_name}').split('\n').length, 1);
  await second.close();
  for (let i=0; i<8; i++) { await terminal.reload(); await connected(); }
  await until(() => tmux('list-clients', '-F', '#{client_pid}').split('\n').filter(Boolean).length === 1, 'one client after repeated refresh');
  await terminal.close();
  await until(() => tmux('list-clients', '-F', '#{client_pid}') === '', 'no clients after close');
  assert.ok(tmux('has-session', '-t', config.session) === '');
  const reopened = await context.newPage(); await reopened.goto(url); await connected(reopened);
  await until(() => reopened.locator('.xterm-screen').textContent().then(t => t.includes('TUI_PERSIST')), 'reopen same TUI');
  await text(reopened).focus(); await reopened.keyboard.press('q');
  await text(reopened).focus(); await reopened.keyboard.press('Control+b'); await reopened.keyboard.press('d');
  await reopened.waitForFunction(() => document.querySelector('#connectionState').textContent.includes('use Reconnect'));
  await until(() => tmux('list-clients', '-F', '#{client_pid}') === '', 'normal detach cleans clients');
  await reopened.locator('#reconnect').click(); await connected(reopened);
  console.log('PASS persistence: live curses TUI survives refresh, offline/reconnect, page close/reopen, eight refreshes, two browsers; one persistent session and no leftover tmux clients');

  const mobile = await browser.newContext({viewport:{width:393,height:851}, isMobile:true, hasTouch:true});
  const phone = await mobile.newPage(); await phone.goto(url); await connected(phone);
  await phone.evaluate(() => Object.defineProperty(navigator, 'clipboard', {value:undefined}));
  await phone.locator('#paste').click();
  await phone.locator('#pasteDialog').waitFor({state:'visible'});
  await phone.locator('#pasteText').fill('echo MOBILE_ქართული');
  await phone.locator('#sendPaste').click();
  await text(phone).focus(); await phone.keyboard.press('Enter');
  await until(() => screen().includes('MOBILE_ქართული'), 'mobile paste fallback');
  assert.ok(await phone.locator('#terminal').evaluate(el => el.clientHeight > 400), 'mobile terminal workspace');
  await mobile.close();
  await reopened.close();
  await until(() => tmux('list-clients', '-F', '#{client_pid}') === '', 'all terminal clients cleaned up');
  await until(() => readFileSync(`/proc/${fixture.pid}/task/${fixture.pid}/children`, 'utf8').trim() === '', 'no remaining PTY children or zombies');
  await until(() => readdirSync(`/proc/${fixture.pid}/fd`).length <= initialFds + 2, 'no descriptor leak');
  console.log('PASS mobile emulation: paste dialog fallback, Unicode input, usable workspace');
  console.log('PASS resources: no attached clients, PTY children/zombies or descriptor growth after disconnect');
  const projects = await (await page.request.get(`${origin}/api/projects`)).json();
  for (const route of ['status','history','diff','screenshots']) {
    const response = await page.request.get(`${origin}/api/${route}?project=${encodeURIComponent(config.project)}`);
    assert.equal(response.status(),200,route);
  }
  assert.equal((await page.request.get(`${origin}/site/${encodeURIComponent(config.project)}/preview/index.html`)).status(),200);
  assert.equal((await page.request.post(`${origin}/api/terminal/connect`, {data:{project:config.project},headers:{Origin:'http://evil.invalid','X-Linko-CSRF':projects.csrfToken}})).status(),403);
  assert.deepEqual(errors, []);
  console.log('PASS HTTP regression: projects, status, history, diff, screenshots, website preview, cross-origin denial');
} finally {
  await browser?.close();
  fixture.kill('SIGTERM');
  await new Promise(resolve => fixture.once('exit', resolve));
  if (serverErrors.includes('Traceback')) console.error(serverErrors);
}
