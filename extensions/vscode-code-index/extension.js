const vscode = require('vscode');
const cp = require('child_process');
const path = require('path');
const os = require('os');
const { eventKind, headChanged, normalizeFsPath } = require('./core');

const runtime = path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local'), 'CodeIndex');
const python = path.join(runtime, 'runtime', '.venv', 'Scripts', 'python.exe');
const cli = path.join(runtime, 'app', 'scripts', 'code_index_cli.py');

function runCli(args, cwd, stdin = undefined) {
  return new Promise((resolve, reject) => {
    const child = cp.execFile(python, [cli, ...args], { cwd, windowsHide: true, maxBuffer: 8 * 1024 * 1024 }, (error, stdout, stderr) => {
      let value;
      try { value = JSON.parse((stdout || stderr).trim()); } catch (_) { value = { status: 'error', error: (stderr || stdout || error?.message || 'CLI failed').trim() }; }
      if (error || value.status === 'error') reject(new Error(value.error || error.message)); else resolve(value);
    });
    child.stdin.end(stdin === undefined ? undefined : stdin);
  });
}

function folderForActiveEditor() {
  const folders = vscode.workspace.workspaceFolders || [];
  if (!folders.length) return undefined;
  const uri = vscode.window.activeTextEditor?.document.uri;
  return (uri && vscode.workspace.getWorkspaceFolder(uri)) || (folders.length === 1 ? folders[0] : undefined);
}

async function chooseFolder() {
  const active = folderForActiveEditor();
  if (active) return active;
  const folders = vscode.workspace.workspaceFolders || [];
  if (!folders.length) return undefined;
  return vscode.window.showWorkspaceFolderPick({ placeHolder: 'Select the Code Index project' });
}

class Controller {
  constructor(context) {
    this.context = context;
    this.output = vscode.window.createOutputChannel('Code Index');
    this.status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 20);
    this.status.command = 'codeIndex.statusClick';
    this.status.show();
    this.watchers = new Map();
    this.timers = new Map();
    this.pending = new Map();
    this.gitTimers = new Map();
    this.gitHeads = new Map();
    this.states = new Map();
    this.settings = { debounce_ms: 1500, bulk_change_threshold: 100 };
    this.panel = undefined;
  }

  async start() {
    try { this.settings = (await runCli(['defaults', 'show'], process.cwd())).defaults; } catch (_) {}
    const folders = vscode.workspace.workspaceFolders || [];
    for (const folder of folders) {
      try {
        await runCli(['project', 'register', folder.uri.fsPath], folder.uri.fsPath);
        const sources = await runCli(['source', 'list', folder.uri.fsPath], folder.uri.fsPath);
        if (sources.watch_enabled) await this.enable(folder, false);
      } catch (error) { this.states.set(normalizeFsPath(folder.uri.fsPath), { error: error.message }); }
    }
    await this.updateStatus();
  }

  async sourceInfo(folder) {
    return runCli(['source', 'list', folder.uri.fsPath], folder.uri.fsPath);
  }

  async enable(folder, persist = true) {
    const key = normalizeFsPath(folder.uri.fsPath);
    const info = await this.sourceInfo(folder);
    const active = info.sources.find(item => item.id === info.active_source_id);
    if (!active || active.owner !== 'code-index') throw new Error('The active source is external and read-only');
    if (persist) await runCli(['project', 'watch', folder.uri.fsPath, 'on'], folder.uri.fsPath);
    if (!this.watchers.has(key)) {
      const watcher = vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(folder, '**/*'));
      const enqueue = uri => this.enqueue(folder, uri);
      watcher.onDidCreate(enqueue); watcher.onDidChange(enqueue); watcher.onDidDelete(enqueue);
      this.watchers.set(key, watcher);
      this.gitHeads.set(key, await this.gitHead(folder));
      this.gitTimers.set(key, setInterval(() => this.checkGitHead(folder), 5000));
    }
    this.states.set(key, { mode: 'on', backend: active.backend, owner: active.owner });
    await this.reconcile(folder);
  }

  async disable(folder, persist = true) {
    const key = normalizeFsPath(folder.uri.fsPath);
    this.watchers.get(key)?.dispose(); this.watchers.delete(key);
    clearTimeout(this.timers.get(key)); this.timers.delete(key); this.pending.delete(key);
    clearInterval(this.gitTimers.get(key)); this.gitTimers.delete(key); this.gitHeads.delete(key);
    if (persist) await runCli(['project', 'watch', folder.uri.fsPath, 'off'], folder.uri.fsPath);
    const info = await this.sourceInfo(folder);
    const active = info.sources.find(item => item.id === info.active_source_id);
    this.states.set(key, { mode: 'off', backend: active?.backend, owner: active?.owner });
    await this.updateStatus();
  }

  enqueue(folder, uri) {
    const relative = path.relative(folder.uri.fsPath, uri.fsPath);
    const kind = eventKind(relative);
    if (kind === 'ignore') return;
    const key = normalizeFsPath(folder.uri.fsPath);
    const pending = this.pending.get(key) || new Set();
    pending.add(kind === 'reconcile' ? '*' : relative);
    this.pending.set(key, pending);
    clearTimeout(this.timers.get(key));
    this.timers.set(key, setTimeout(() => this.flush(folder), Number(this.settings.debounce_ms || 1500)));
  }

  async flush(folder) {
    const key = normalizeFsPath(folder.uri.fsPath);
    const files = [...(this.pending.get(key) || [])]; this.pending.delete(key);
    if (!files.length) return;
    try {
      if (files.includes('*') || files.length > Number(this.settings.bulk_change_threshold || 100)) await this.reconcile(folder);
      else {
        this.states.set(key, { mode: 'indexing' }); await this.updateStatus();
        await runCli(['refresh', folder.uri.fsPath, ...files], folder.uri.fsPath);
        const info = await this.sourceInfo(folder); const active = info.sources.find(x => x.id === info.active_source_id);
        this.states.set(key, { mode: 'on', backend: active.backend, owner: active.owner });
      }
    } catch (error) { this.states.set(key, { error: error.message }); this.output.appendLine(error.stack || error.message); }
    await this.updateStatus();
  }

  async reconcile(folder) {
    const key = normalizeFsPath(folder.uri.fsPath);
    this.states.set(key, { mode: 'indexing' }); await this.updateStatus();
    try {
      await runCli(['index', folder.uri.fsPath], folder.uri.fsPath);
      const info = await this.sourceInfo(folder); const active = info.sources.find(x => x.id === info.active_source_id);
      this.states.set(key, { mode: 'on', backend: active.backend, owner: active.owner });
    } catch (error) { this.states.set(key, { error: error.message }); throw error; }
    finally { await this.updateStatus(); }
  }

  async gitHead(folder) {
    return new Promise(resolve => cp.execFile('git', ['-C', folder.uri.fsPath, 'rev-parse', 'HEAD'], { windowsHide: true }, (error, stdout) => resolve(error ? '' : stdout.trim())));
  }

  async checkGitHead(folder) {
    const key = normalizeFsPath(folder.uri.fsPath); const previous = this.gitHeads.get(key); const current = await this.gitHead(folder);
    if (headChanged(previous, current)) { this.gitHeads.set(key, current); try { await this.reconcile(folder); } catch (_) {} }
    else if (current) this.gitHeads.set(key, current);
  }

  async updateStatus() {
    const folder = folderForActiveEditor() || (vscode.workspace.workspaceFolders || [])[0];
    if (!folder) { this.status.text = '$(database) Code Index: No workspace'; return; }
    const key = normalizeFsPath(folder.uri.fsPath);
    try {
      const info = await this.sourceInfo(folder); const active = info.sources.find(x => x.id === info.active_source_id);
      if (active.owner === 'kilo') {
        let ready = 'Ready'; try { const s = await runCli(['status', folder.uri.fsPath], folder.uri.fsPath); if (!s.indexed) ready = 'Stale'; } catch (_) { ready = 'Error'; }
        this.status.text = `$(database) Code Index: Kilo · ${ready}`; this.status.tooltip = 'Open source management'; return;
      }
      const state = this.states.get(key) || { mode: info.watch_enabled ? 'on' : 'off', backend: active.backend };
      if (state.error) this.status.text = '$(error) Code Index: Error';
      else if (state.mode === 'indexing') this.status.text = '$(sync~spin) Code Index: Indexing';
      else if (state.mode === 'on') this.status.text = `$(database) Code Index: On · ${active.backend === 'lancedb' ? 'LanceDB' : 'Qdrant'}`;
      else this.status.text = '$(database) Code Index: Off';
      this.status.tooltip = state.error || 'Click to toggle workspace indexing';
    } catch (error) { this.status.text = '$(error) Code Index: Unavailable'; this.status.tooltip = error.message; }
  }

  async statusClick() {
    const folder = await chooseFolder(); if (!folder) return;
    const info = await this.sourceInfo(folder); const active = info.sources.find(x => x.id === info.active_source_id);
    if (active.owner !== 'code-index') return this.manage(folder);
    const key = normalizeFsPath(folder.uri.fsPath);
    if (this.watchers.has(key)) await this.disable(folder); else await this.enable(folder);
  }

  async manage(folder = undefined) {
    folder = folder || await chooseFolder(); if (!folder) return;
    if (!this.panel) {
      this.panel = vscode.window.createWebviewPanel('codeIndexManage', 'Code Index: Manage', vscode.ViewColumn.Active, { enableScripts: true });
      this.panel.onDidDispose(() => { this.panel = undefined; });
      this.panel.webview.onDidReceiveMessage(message => this.handleMessage(message));
    }
    this.panelFolder = folder;
    await this.render(); this.panel.reveal();
  }

  async render() {
    const folder = this.panelFolder;
    const [defaults, profiles, sources] = await Promise.all([
      runCli(['defaults', 'show'], folder.uri.fsPath), runCli(['profile', 'list'], folder.uri.fsPath), this.sourceInfo(folder)
    ]);
    const d = defaults.defaults, o = sources.overrides || {}, p = profiles.profiles[d.embedding_profile] || {}, rows = sources.sources.map(s => `<option value="${esc(s.id)}" ${s.id === sources.active_source_id ? 'selected' : ''}>${esc(s.id)} — ${esc(s.owner)} / ${esc(s.backend)}</option>`).join('');
    this.panel.webview.html = `<!doctype html><html><body><h1>Code Index</h1><p>${esc(folder.uri.fsPath)}</p>
      <label>Backend <select id="backend"><option ${d.backend==='lancedb'?'selected':''}>lancedb</option><option ${d.backend==='qdrant'?'selected':''}>qdrant</option></select></label><br>
      <label>Qdrant URL <input id="qurl" size="50" value="${esc(d.qdrant_url)}"></label><br><label>Qdrant API key <input id="qkey" type="password"></label><br>
      <label>LanceDB root <input id="lroot" size="70" value="${esc(d.lancedb_root)}"></label><br>
      <h2>Project overrides</h2><label>Embedding profile <input id="oproject" value="${esc(o.embedding_profile || '')}" placeholder="inherit"></label><br><label>Debounce ms <input id="odebounce" type="number" value="${Number(o.debounce_ms || d.debounce_ms)}"></label><br><label>Bulk threshold <input id="obulk" type="number" value="${Number(o.bulk_change_threshold || d.bulk_change_threshold)}"></label><br>
      <h2>Embedding profile</h2><label>Provider <select id="provider"><option ${p.provider==='fastembed'?'selected':''}>fastembed</option><option ${p.provider==='openai-compatible'?'selected':''}>openai-compatible</option></select></label><br>
      <label>Model <input id="model" size="60" value="${esc(p.model||'')}"></label><br><label>Dimension <input id="dimension" type="number" value="${Number(p.dimension||0)}"></label><br><label>Base URL <input id="base" size="60" value="${esc(p.base_url||'')}"></label><br><label>API key <input id="ekey" type="password"></label><br>
      <button onclick="send('save')">Save defaults/profile</button><button onclick="send('test')">Test profile</button>
      <h2>Sources</h2><select id="source">${rows}</select><button onclick="send('use')">Use source</button><button onclick="send('detect')">Detect Kilo</button><button onclick="send('index')">Reconcile</button><button onclick="send('migrate')">Migrate backend</button>
      <pre id="result"></pre><script>const vscode=acquireVsCodeApi(); function send(command){vscode.postMessage({command,backend:backend.value,qurl:qurl.value,qkey:qkey.value,lroot:lroot.value,oproject:oproject.value,odebounce:odebounce.value,obulk:obulk.value,provider:provider.value,model:model.value,dimension:dimension.value,base:base.value,ekey:ekey.value,source:source.value});} window.addEventListener('message',e=>result.textContent=JSON.stringify(e.data,null,2));</script></body></html>`;
  }

  async handleMessage(m) {
    const folder = this.panelFolder; if (!folder) return;
    try {
      let result;
      if (m.command === 'save') {
        await runCli(['defaults','set','--backend',m.backend,'--qdrant-url',m.qurl,'--lancedb-root',m.lroot,...(m.qkey?['--qdrant-api-key-stdin']:[])], folder.uri.fsPath, m.qkey || undefined);
        await runCli(['project','override',folder.uri.fsPath,...(m.oproject?['--embedding-profile',m.oproject]:['--clear-embedding-profile']),'--debounce-ms',String(m.odebounce),'--bulk-change-threshold',String(m.obulk)], folder.uri.fsPath);
        result = await runCli(['profile','set','default-code','--provider',m.provider,'--model',m.model,'--dimension',String(m.dimension),'--base-url',m.base,...(m.ekey?['--api-key-stdin']:[])], folder.uri.fsPath, m.ekey || undefined);
      } else if (m.command === 'test') result = await runCli(['profile','test','default-code'], folder.uri.fsPath);
      else if (m.command === 'use') result = await runCli(['source','use',folder.uri.fsPath,m.source], folder.uri.fsPath);
      else if (m.command === 'detect') {
        result = await runCli(['source','detect',folder.uri.fsPath], folder.uri.fsPath);
        if (result.candidates?.length) {
          const picked = await vscode.window.showQuickPick(result.candidates.map((candidate, index) => ({ label: `${candidate.backend}: ${candidate.location.collection || candidate.location.directory}`, description: `${candidate.metadata.embedding_provider || ''} ${candidate.metadata.embedding_model_id || ''}`, candidate, index })), { placeHolder: 'Found Kilo Code indexes — select one to attach' });
          if (picked) {
            const action = await vscode.window.showInformationMessage('Attach this Kilo source? Activation is allowed only after schema/profile/dimension validation.', 'Attach', 'Attach and activate');
            if (action) {
              const candidate = picked.candidate; const sourceId = `kilo-${candidate.backend}-${Date.now()}`;
              const args = candidate.backend === 'qdrant'
                ? ['source','add-kilo-qdrant',folder.uri.fsPath,sourceId,candidate.location.url,candidate.location.collection,'--profile','default-code']
                : ['source','add-kilo-lancedb',folder.uri.fsPath,sourceId,candidate.location.directory,'--profile','default-code'];
              if (action === 'Attach and activate') args.push('--activate');
              result = await runCli(args, folder.uri.fsPath);
            }
          }
        }
      }
      else if (m.command === 'index') result = await runCli(['index',folder.uri.fsPath], folder.uri.fsPath);
      else if (m.command === 'migrate') result = await runCli(['migrate-backend',folder.uri.fsPath,m.backend], folder.uri.fsPath);
      this.panel.webview.postMessage(result); await this.render(); await this.updateStatus();
    } catch (error) { this.panel.webview.postMessage({status:'error',error:error.message}); }
  }

  dispose() { for (const watcher of this.watchers.values()) watcher.dispose(); for (const timer of this.timers.values()) clearTimeout(timer); for (const timer of this.gitTimers.values()) clearInterval(timer); this.status.dispose(); this.output.dispose(); }
}

function esc(value) { return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

async function activate(context) {
  const controller = new Controller(context); context.subscriptions.push(controller);
  context.subscriptions.push(vscode.commands.registerCommand('codeIndex.manage', () => controller.manage()));
  context.subscriptions.push(vscode.commands.registerCommand('codeIndex.toggle', () => controller.statusClick()));
  context.subscriptions.push(vscode.commands.registerCommand('codeIndex.statusClick', () => controller.statusClick()));
  context.subscriptions.push(vscode.commands.registerCommand('codeIndex.index', async () => { const folder = await chooseFolder(); if (folder) await controller.reconcile(folder); }));
  context.subscriptions.push(vscode.window.onDidChangeActiveTextEditor(() => controller.updateStatus()));
  await controller.start();
}

function deactivate() {}
module.exports = { activate, deactivate };
