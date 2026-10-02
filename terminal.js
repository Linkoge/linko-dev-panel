'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const project = new URL(location.href).searchParams.get('project');
  $('projectName').textContent = project || 'Unknown project';
  $('back').href = `/?project=${encodeURIComponent(project || '')}`;
  document.title = `${project || 'Project'} Terminal · Dev Panel`;
  const terminal = new Terminal({cursorBlink:true, scrollback:10000, fontSize:14,
    fontFamily:'ui-monospace, "DejaVu Sans Mono", Consolas, monospace',
    theme:{background:'#101114'}, allowProposedApi:false});
  const fit = new FitAddon.FitAddon();
  terminal.loadAddon(fit);
  terminal.open($('terminal'));
  let socket, generation = 0, ready = false, reconnectTimer, attempts = 0, stopped = false;
  let queue = [], queuedBytes = 0, inflight = 0;
  const encoder = new TextEncoder();
  const MAX_PENDING = 16 * 1024 * 1024;
  const state = text => { $('connectionState').textContent = text; };
  const message = text => { $('message').textContent = text; };
  function sendControl(data) {
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(data));
  }
  function fitTerminal() {
    const size = fit.proposeDimensions();
    if (size) terminal.resize(Math.max(2, Math.min(1000, size.cols)), Math.max(2, Math.min(500, size.rows)));
    if (ready) sendControl({type:'resize', cols:terminal.cols, rows:terminal.rows});
  }
  new ResizeObserver(fitTerminal).observe($('terminal'));
  window.visualViewport?.addEventListener('resize', () => {
    document.body.style.height = `${window.visualViewport.height}px`;
    fitTerminal();
  });
  function inputStatus() {
    $('inputState').textContent = queuedBytes ? `Sending ${queuedBytes.toLocaleString()} bytes…` : '';
  }
  function pump() {
    if (!ready || inflight || !queue.length) return;
    const data = queue[0];
    const chunk = data.subarray(0, 8192);
    inflight = chunk.length;
    socket.send(chunk);
  }
  function enqueue(data) {
    if (!ready) { message('Disconnected: input was not sent. Reconnect before typing or pasting.'); return; }
    if (queuedBytes + data.length > MAX_PENDING) {
      message('Paste was not sent: the pending input limit is 16 MiB. Send it in smaller parts.'); return;
    }
    queue.push(data); queuedBytes += data.length;
    inputStatus(); pump();
  }
  terminal.onData(data => enqueue(encoder.encode(data)));
  terminal.onBinary(data => enqueue(Uint8Array.from(data, char => char.charCodeAt(0))));
  terminal.attachCustomKeyEventHandler(event => {
    // Let browser clipboard shortcuts reach xterm's native paste handler.
    if (event.ctrlKey && event.key.toLowerCase() === 'v') return false;
    if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === 'c') return false;
    if (event.ctrlKey && event.key.toLowerCase() === 'c' && terminal.hasSelection()) return false;
    return true;
  });
  async function request(path, options = {}) {
    const response = await fetch(path, {cache:'no-store', ...options});
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || 'Terminal request failed.');
    return data;
  }
  function scheduleReconnect() {
    if (stopped) return;
    const delay = Math.min(1000 * 2 ** Math.min(attempts++, 4), 15000);
    state('Disconnected · reconnecting…');
    reconnectTimer = setTimeout(connect, delay);
  }
  async function connect() {
    clearTimeout(reconnectTimer);
    const mine = ++generation;
    if (socket) { socket.onclose = null; socket.close(); }
    ready = false;
    terminal.options.disableStdin = true;
    if (queuedBytes) message('Connection lost with pending input. Delivery may be partial; it will not be replayed automatically. Check the application before pasting again.');
    queue = []; queuedBytes = inflight = 0; inputStatus();
    state('Connecting…');
    try {
      const projects = await request('/api/projects');
      if (!projects.projects.some(item => item.name === project)) throw new Error('Unknown configured project.');
      const ticket = await request('/api/terminal/connect', {method:'POST',
        headers:{'Content-Type':'application/json', 'X-Linko-CSRF':projects.csrfToken},
        body:JSON.stringify({project})});
      if (mine !== generation || stopped) return;
      fitTerminal();
      const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/terminal/ws?project=${encodeURIComponent(project)}`);
      socket = ws;
      ws.binaryType = 'arraybuffer';
      ws.onopen = () => ws.send(JSON.stringify({type:'connect', ticket:ticket.ticket, cols:terminal.cols, rows:terminal.rows}));
      ws.onmessage = event => {
        if (mine !== generation) return;
        if (event.data instanceof ArrayBuffer) {
          const data = new Uint8Array(event.data);
          terminal.write(data, () => {
            if (mine === generation && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({type:'output-ack', bytes:data.length}));
          });
          return;
        }
        const data = JSON.parse(event.data);
        if (data.type === 'ready') {
          terminal.reset(); ready = true; attempts = 0;
          terminal.options.disableStdin = false;
          state('● Connected'); fitTerminal(); terminal.focus();
        } else if (data.type === 'error') {
          message(data.message);
        } else if (data.type === 'input-ack' && inflight && data.bytes === inflight) {
          const head = queue.shift();
          if (head.length > inflight) queue.unshift(head.subarray(inflight));
          queuedBytes -= inflight; inflight = 0; inputStatus(); pump();
        }
      };
      ws.onclose = event => {
        if (mine !== generation || stopped) return;
        ready = false; terminal.options.disableStdin = true;
        if (queuedBytes) message('Connection lost with pending input. Delivery may be partial; it will not be replayed automatically. Check the application before pasting again.');
        queue = []; queuedBytes = inflight = 0; inputStatus();
        if (event.code === 1000) state('Disconnected · use Reconnect');
        else scheduleReconnect();
      };
      ws.onerror = () => message('Terminal connection interrupted. Your tmux session remains on the server.');
    } catch (error) {
      if (mine !== generation || stopped) return;
      message(error.message); scheduleReconnect();
    }
  }
  $('reconnect').onclick = connect;
  window.addEventListener('online', connect);
  window.addEventListener('pagehide', () => { stopped = true; ++generation; clearTimeout(reconnectTimer); socket?.close(); });
  window.addEventListener('pageshow', event => { if (event.persisted) { stopped = false; connect(); } });
  document.querySelectorAll('[data-key]').forEach(button => {
    button.onmousedown = event => event.preventDefault();
    button.onclick = () => { enqueue(encoder.encode(button.dataset.key)); terminal.focus(); };
  });
  $('selectAll').onclick = () => terminal.selectAll();
  $('copy').onclick = async () => {
    if (!terminal.hasSelection()) { message('Select text first: use Select all or Shift+drag. Scroll history opens tmux copy mode.'); return; }
    try { await navigator.clipboard.writeText(terminal.getSelection()); message('Selection copied.'); }
    catch {
      terminal.focus();
      if (document.execCommand('copy')) message('Selection copied.');
      else message('Use Ctrl+Shift+C or your browser’s Copy selection action.');
    }
  };
  $('paste').onclick = async () => {
    if (!ready) { message('Reconnect before pasting.'); return; }
    try {
      if (!navigator.clipboard?.readText) throw new Error('Clipboard API unavailable');
      terminal.paste(await navigator.clipboard.readText()); terminal.focus();
    } catch {
      $('pasteText').value = ''; $('pasteDialog').showModal(); $('pasteText').focus();
    }
  };
  $('pasteDialog').addEventListener('close', () => {
    if ($('pasteDialog').returnValue === 'send') { terminal.paste($('pasteText').value); terminal.focus(); }
    $('pasteText').value = '';
  });
  connect();
})();
