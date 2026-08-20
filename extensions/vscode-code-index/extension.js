const vscode = require('vscode');
const cp = require('child_process');
const path = require('path');
const os = require('os');
const { eventKind, headChanged, normalizeFsPath } = require('./core');
const { ManagePanel } = require('./managePanel');

const runtime = path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local'), 'CodeIndex');
const python = path.join(runtime, 'runtime', '.venv', 'Scripts', 'python.exe');
const cli = path.join(runtime, 'app', 'scripts', 'code_index_cli.py');

function runCli(args, cwd, stdin = undefined) {
  return new Promise((resolve, reject) => {
    const child = cp.execFile(python, [cli, ...args], { cwd, windowsHide: true, maxBuffer: 8 * 1024 * 1024 }, (error, stdout, stderr) => {
      let value;
      try { value = JSON.parse((stdout || stderr).trim()); }
      catch (_) { value = { status: 'error', error: (stderr || stdout || error?.message || 'CLI failed').trim() }; }
      if (error || value.status === 'error') reject(new Error(value.error || error.message)); else resolve(value);
    });
    child.stdin.end(stdin);
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
    this.status.command = 'codeIndex.statusClick'; this.status.show();
    this.watchers = new Map(); this.timers = new Map(); this.pending = new Map();
    this.gitTimers = new Map(); this.gitHeads = new Map(); this.states = new Map(); this.folderSettings = new Map();
    this.managePanel = new ManagePanel(context, runCli, (folder, payload) => this.applyProjectSettings(folder, payload));
  }

  async start() {
    for (const folder of vscode.workspace.workspaceFolders || []) {
      const key = normalizeFsPath(folder.uri.fsPath);
      try {
        await runCli(['project', 'register', folder.uri.fsPath], folder.uri.fsPath);
        await this.loadSettings(folder);
        const sources = await this.sourceInfo(folder);
        if (sources.watch_enabled) await this.enable(folder, false);
      } catch (error) { this.states.set(key, { error: error.message }); }
    }
    await this.updateStatus();
  }

  async loadSettings(folder) {
    const state = await runCli(['settings', 'show', '--project', folder.uri.fsPath], folder.uri.fsPath);
    this.folderSettings.set(normalizeFsPath(folder.uri.fsPath), state.project.effective);
    return state;
  }

  async sourceInfo(folder) { return runCli(['source', 'list', folder.uri.fsPath], folder.uri.fsPath); }

  async enable(folder, persist = true) {
    const key = normalizeFsPath(folder.uri.fsPath);
    const info = await this.sourceInfo(folder); const active = info.sources.find(item => item.id === info.active_source_id);
    if (!active) throw new Error('No active managed source');
    if (persist) await runCli(['project', 'watch', folder.uri.fsPath, 'on'], folder.uri.fsPath);
    if (!this.watchers.has(key)) {
      const watcher = vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(folder, '**/*'));
      const enqueue = uri => this.enqueue(folder, uri);
      watcher.onDidCreate(enqueue); watcher.onDidChange(enqueue); watcher.onDidDelete(enqueue);
      this.watchers.set(key, watcher); this.gitHeads.set(key, await this.gitHead(folder));
      this.gitTimers.set(key, setInterval(() => this.checkGitHead(folder), 5000));
    }
    this.states.set(key, { mode: 'on', backend: active.backend });
    await this.reconcile(folder);
  }

  async disable(folder, persist = true) {
    const key = normalizeFsPath(folder.uri.fsPath);
    this.watchers.get(key)?.dispose(); this.watchers.delete(key);
    clearTimeout(this.timers.get(key)); this.timers.delete(key); this.pending.delete(key);
    clearInterval(this.gitTimers.get(key)); this.gitTimers.delete(key); this.gitHeads.delete(key);
    if (persist) await runCli(['project', 'watch', folder.uri.fsPath, 'off'], folder.uri.fsPath);
    const info = await this.sourceInfo(folder); const active = info.sources.find(item => item.id === info.active_source_id);
    this.states.set(key, { mode: 'off', backend: active?.backend }); await this.updateStatus();
  }

  enqueue(folder, uri) {
    const relative = path.relative(folder.uri.fsPath, uri.fsPath); const kind = eventKind(relative);
    if (kind === 'ignore') return;
    const key = normalizeFsPath(folder.uri.fsPath); const pending = this.pending.get(key) || new Set();
    pending.add(kind === 'reconcile' ? '*' : relative); this.pending.set(key, pending);
    clearTimeout(this.timers.get(key));
    const settings = this.folderSettings.get(key) || {};
    this.timers.set(key, setTimeout(() => this.flush(folder), Number(settings.debounce_ms || 1500)));
  }

  async flush(folder) {
    const key = normalizeFsPath(folder.uri.fsPath); const files = [...(this.pending.get(key) || [])]; this.pending.delete(key);
    if (!files.length) return;
    try {
      const settings = this.folderSettings.get(key) || {};
      if (files.includes('*') || files.length > Number(settings.bulk_change_threshold || 100)) await this.reconcile(folder);
      else {
        this.states.set(key, { mode: 'indexing' }); await this.updateStatus();
        await runCli(['refresh', folder.uri.fsPath, ...files], folder.uri.fsPath);
        const info = await this.sourceInfo(folder); const active = info.sources.find(x => x.id === info.active_source_id);
        this.states.set(key, { mode: 'on', backend: active.backend });
      }
    } catch (error) { this.states.set(key, { error: error.message }); this.output.appendLine(error.stack || error.message); }
    await this.updateStatus();
  }

  async reconcile(folder) {
    const key = normalizeFsPath(folder.uri.fsPath); this.states.set(key, { mode: 'indexing' }); await this.updateStatus();
    try {
      await runCli(['index', folder.uri.fsPath], folder.uri.fsPath);
      const info = await this.sourceInfo(folder); const active = info.sources.find(x => x.id === info.active_source_id);
      this.states.set(key, { mode: 'on', backend: active.backend });
    } catch (error) { this.states.set(key, { error: error.message }); throw error; }
    finally { await this.updateStatus(); }
  }

  async applyProjectSettings(folder, payload) {
    const key = normalizeFsPath(folder.uri.fsPath); const wasWatching = this.watchers.has(key);
    if (wasWatching) await this.disable(folder, false);
    try {
      const result = await runCli(['settings', 'apply-project', folder.uri.fsPath], folder.uri.fsPath, JSON.stringify(payload));
      const state = await this.loadSettings(folder);
      if (state.project.watch_enabled) await this.enable(folder, false);
      return result;
    } catch (error) {
      if (wasWatching) { try { await this.enable(folder, false); } catch (_) {} }
      throw error;
    }
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
    const key = normalizeFsPath(folder.uri.fsPath);
    if (this.watchers.has(key)) await this.disable(folder); else await this.enable(folder);
  }

  async manage(folder = undefined) { folder = folder || await chooseFolder(); if (folder) await this.managePanel.open(folder); }

  dispose() {
    for (const watcher of this.watchers.values()) watcher.dispose();
    for (const timer of this.timers.values()) clearTimeout(timer);
    for (const timer of this.gitTimers.values()) clearInterval(timer);
    this.managePanel.dispose(); this.status.dispose(); this.output.dispose();
  }
}

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
