const cp = require('child_process');
const path = require('path');
const { resolveExecutablePath } = require('./executable');

let vscode;
let activeController;

function folderKey(folder) {
  const value = path.resolve(folder.uri.fsPath);
  return process.platform === 'win32' ? value.toLowerCase() : value;
}

function isWindowsScript(executable, platform = process.platform) {
  return platform === 'win32' && /\.(?:cmd|bat)$/i.test(executable);
}

function hasWindowsShellMetaCharacter(value) {
  return /[&|<>^()!%"\r\n]/.test(String(value));
}

function spawnSymbraid(executable, args, cwd, platform = process.platform) {
  const shell = isWindowsScript(executable, platform);
  if (shell && (hasWindowsShellMetaCharacter(executable) || args.some(hasWindowsShellMetaCharacter))) {
    throw new Error('Refusing to pass shell metacharacters to a legacy Windows launcher');
  }
  return cp.spawn(executable, args, {
    cwd,
    windowsHide: true,
    shell,
    stdio: ['pipe', 'pipe', 'pipe'],
  });
}

const STOP_GRACE_TIMEOUT_MS = 5000;
const STOP_FORCE_TIMEOUT_MS = 2000;

function childHasExited(child) {
  return (child.exitCode !== null && child.exitCode !== undefined)
    || (child.signalCode !== null && child.signalCode !== undefined);
}

function waitForChildExit(child, timeoutMs = STOP_GRACE_TIMEOUT_MS) {
  if (childHasExited(child)) return Promise.resolve();
  return new Promise((resolve, reject) => {
    let timer;
    let settled = false;
    const cleanup = () => {
      clearTimeout(timer);
      child.removeListener('exit', onExit);
      child.removeListener('close', onClose);
      child.removeListener('error', onError);
    };
    const finish = (handler, value) => {
      if (settled) return;
      settled = true;
      cleanup();
      handler(value);
    };
    const onExit = (code, signal) => finish(resolve, { code, signal });
    const onClose = (code, signal) => finish(resolve, { code, signal });
    const onError = (error) => {
      if (childHasExited(child) || child.pid == null) finish(resolve, { error });
      else finish(reject, error);
    };
    timer = setTimeout(() => {
      const error = new Error('Timed out waiting for Symbraid watch to exit');
      error.code = 'ETIMEDOUT';
      finish(reject, error);
    }, timeoutMs);
    child.once('exit', onExit);
    child.once('close', onClose);
    child.once('error', onError);
  });
}

async function terminateChild(child, options = {}) {
  const graceTimeoutMs = options.graceTimeoutMs ?? STOP_GRACE_TIMEOUT_MS;
  const forceTimeoutMs = options.forceTimeoutMs ?? STOP_FORCE_TIMEOUT_MS;
  if (childHasExited(child)) {
    await waitForChildExit(child, graceTimeoutMs);
    return { forced: false };
  }
  try {
    if (!child.killed) child.kill();
  } catch (error) {
    if (!childHasExited(child) && child.pid != null) throw error;
  }
  try {
    await waitForChildExit(child, graceTimeoutMs);
    return { forced: false };
  } catch (error) {
    if (error.code !== 'ETIMEDOUT') throw error;
  }
  if (childHasExited(child)) return { forced: false };
  try {
    child.kill('SIGKILL');
  } catch (error) {
    if (!childHasExited(child)) throw error;
  }
  try {
    await waitForChildExit(child, forceTimeoutMs);
  } catch (error) {
    if (!childHasExited(child)) {
      error.message = 'Symbraid watch did not exit after forced termination: ' + error.message;
      throw error;
    }
  }
  return { forced: true };
}

function commandError(stderr, stdout, error, args) {
  return (stderr || stdout || error?.message || 'Symbraid command failed: ' + args.join(' ')).trim();
}

function runCommand(executable, args, cwd, stdin = undefined) {
  return new Promise((resolve, reject) => {
    const child = spawnSymbraid(executable, args, cwd);
    let stdout = '';
    let stderr = '';
    let settled = false;
    child.stdout?.on('data', (chunk) => { stdout += chunk.toString(); });
    child.stderr?.on('data', (chunk) => { stderr += chunk.toString(); });
    child.once('error', (error) => {
      if (!settled) { settled = true; reject(error); }
    });
    child.once('close', (code, signal) => {
      if (settled) return;
      settled = true;
      if (code !== 0) {
        reject(new Error(commandError(stderr, stdout, undefined, args) || 'Exited with ' + (signal || code)));
        return;
      }
      const text = stdout.trim();
      if (!text) { resolve({ status: 'ok' }); return; }
      try { resolve(JSON.parse(text)); }
      catch (_) { resolve({ status: 'ok', output: text }); }
    });
    if (stdin === undefined) child.stdin?.end();
    else child.stdin?.end(stdin);
  });
}

function configuredExecutable(api, folder) {
  const setting = api.workspace.getConfiguration('symbraid', folder.uri).get('executablePath');
  return resolveExecutablePath(setting);
}

function projectAutoWatch(state) {
  return Boolean(
    state?.project?.auto_watch
    ?? state?.project?.effective?.auto_watch
    ?? state?.auto_watch,
  );
}

class Controller {
  constructor(context, api) {
    this.context = context;
    this.api = api;
    this.output = api.window.createOutputChannel('Symbraid');
    this.status = api.window.createStatusBarItem(api.StatusBarAlignment.Left, 20);
    this.status.command = 'symbraid.statusClick';
    this.status.show();
    this.processes = new Map();
    this.states = new Map();
    // ManagePanel owns settings presentation; this host only applies them.
    const { ManagePanel } = require('./managePanel');
    this.managePanel = new ManagePanel(context, (args, cwd, stdin) => this.runCli(args, cwd, stdin), (folder, payload) => this.applyProjectSettings(folder, payload));
  }

  async runCli(args, cwd, stdin = undefined) {
    return runCommand(configuredExecutable(this.api, { uri: this.api.Uri.file(cwd) }), args, cwd, stdin);
  }

  async start() {
    for (const folder of this.api.workspace.workspaceFolders || []) {
      const key = folderKey(folder);
      try {
        const settings = await this.runCli(['settings', 'show', '--project', folder.uri.fsPath], folder.uri.fsPath);
        const autoWatch = projectAutoWatch(settings);
        this.states.set(key, { mode: 'stopped', autoWatch });
        if (autoWatch) await this.startWatch(folder, false);
      } catch (error) {
        this.states.set(key, { mode: 'error', error: error.message });
      }
    }
    await this.updateStatus();
  }

  async setAutoWatch(folder, enabled) {
    await this.runCli(['project', 'autowatch', folder.uri.fsPath, enabled ? 'on' : 'off'], folder.uri.fsPath);
    const key = folderKey(folder);
    const state = this.states.get(key) || {};
    this.states.set(key, { ...state, autoWatch: enabled });
  }

  async startWatch(folder, persist = true) {
    const key = folderKey(folder);
    const current = this.processes.get(key);
    if (current && !childHasExited(current)) return current;
    if (current) this.processes.delete(key);
    if (persist) await this.setAutoWatch(folder, true);

    const executable = configuredExecutable(this.api, folder);
    const child = spawnSymbraid(executable, ['watch', folder.uri.fsPath], folder.uri.fsPath);
    this.processes.set(key, child);
    this.states.set(key, { ...(this.states.get(key) || {}), mode: 'starting', autoWatch: true });
    child.stdout?.on('data', (chunk) => this.output.append(chunk.toString()));
    child.stderr?.on('data', (chunk) => this.output.append(chunk.toString()));
    child.once('spawn', () => {
      const state = this.states.get(key) || {};
      this.states.set(key, { ...state, mode: 'running', error: undefined });
      void this.updateStatus();
    });
    child.once('error', (error) => {
      this.processes.delete(key);
      this.states.set(key, { mode: 'error', autoWatch: true, error: error.message });
      void this.updateStatus();
    });
    child.once('close', (code, signal) => {
      if (this.processes.get(key) !== child) return;
      this.processes.delete(key);
      const state = this.states.get(key) || {};
      this.states.set(key, {
        ...state,
        mode: code === 0 ? 'stopped' : 'error',
        error: code === 0 ? undefined : 'Symbraid watch exited with ' + (signal || code),
      });
      void this.updateStatus();
    });
    await this.updateStatus();
    return child;
  }

  async stopWatch(folder, persist = true) {
    const key = folderKey(folder);
    if (persist) await this.setAutoWatch(folder, false);
    const child = this.processes.get(key);
    if (child) {
      try {
        await terminateChild(child);
      } catch (error) {
        const state = this.states.get(key) || {};
        this.states.set(key, {
          ...state,
          mode: 'error',
          autoWatch: false,
          error: error.message,
        });
        await this.updateStatus();
        throw error;
      }
      if (this.processes.get(key) === child) this.processes.delete(key);
    }
    const state = this.states.get(key) || {};
    this.states.set(key, { ...state, mode: 'stopped', autoWatch: false, error: undefined });
    await this.updateStatus();
  }

  async applyProjectSettings(folder, payload) {
    const key = folderKey(folder);
    const wasRunning = this.processes.has(key);
    if (wasRunning) await this.stopWatch(folder, false);
    try {
      const result = await this.runCli(['settings', 'apply-project', folder.uri.fsPath], folder.uri.fsPath, JSON.stringify(payload));
      if (Object.prototype.hasOwnProperty.call(payload || {}, 'auto_watch')) {
        await this.setAutoWatch(folder, Boolean(payload.auto_watch));
      }
      const shouldRun = Object.prototype.hasOwnProperty.call(payload || {}, 'auto_watch')
        ? Boolean(payload.auto_watch)
        : wasRunning;
      if (shouldRun) await this.startWatch(folder, false);
      else if (!shouldRun) await this.stopWatch(folder, false);
      return result;
    } catch (error) {
      if (wasRunning) {
        try { await this.startWatch(folder, false); } catch (_) { /* preserve original error */ }
      }
      throw error;
    }
  }

  async updateStatus() {
    const folder = this.api.window.activeTextEditor
      ? this.api.workspace.getWorkspaceFolder(this.api.window.activeTextEditor.document.uri)
      : (this.api.workspace.workspaceFolders || [])[0];
    if (!folder) {
      this.status.text = '$(radio-tower) Symbraid: No workspace';
      this.status.tooltip = 'Open a workspace to manage Symbraid';
      return;
    }
    const state = this.states.get(folderKey(folder)) || { mode: 'stopped' };
    if (state.mode === 'error') this.status.text = '$(error) Symbraid: Error';
    else if (state.mode === 'starting') this.status.text = '$(sync~spin) Symbraid: Starting';
    else if (state.mode === 'running') this.status.text = '$(radio-tower) Symbraid: Running';
    else this.status.text = '$(radio-tower) Symbraid: Stopped';
    this.status.tooltip = state.error || 'Click to start or stop Symbraid watch';
  }

  async statusClick() {
    const folder = await this.chooseFolder();
    if (!folder) return;
    if (this.processes.has(folderKey(folder))) await this.stopWatch(folder);
    else await this.startWatch(folder);
  }

  async chooseFolder() {
    const folders = this.api.workspace.workspaceFolders || [];
    if (!folders.length) return undefined;
    const uri = this.api.window.activeTextEditor?.document.uri;
    return (uri && this.api.workspace.getWorkspaceFolder(uri))
      || (folders.length === 1 ? folders[0] : this.api.window.showWorkspaceFolderPick({ placeHolder: 'Select the Symbraid workspace' }));
  }

  async manage(folder = undefined) {
    const selected = folder || await this.chooseFolder();
    if (selected) await this.managePanel.open(selected);
  }

  dispose() {
    for (const child of this.processes.values()) child.kill();
    this.processes.clear();
    this.managePanel.dispose();
    this.status.dispose();
    this.output.dispose();
  }
}

async function activate(context) {
  vscode = require('vscode');
  activeController = new Controller(context, vscode);
  context.subscriptions.push(activeController);
  context.subscriptions.push(vscode.commands.registerCommand('symbraid.manage', () => activeController.manage()));
  context.subscriptions.push(vscode.commands.registerCommand('symbraid.toggle', () => activeController.statusClick()));
  context.subscriptions.push(vscode.commands.registerCommand('symbraid.statusClick', () => activeController.statusClick()));
  context.subscriptions.push(vscode.window.onDidChangeActiveTextEditor(() => activeController.updateStatus()));
  await activeController.start();
}

function deactivate() {
  activeController?.dispose();
  activeController = undefined;
}

module.exports = {
  Controller,
  activate,
  deactivate,
  resolveExecutablePath,
  runCommand,
  spawnSymbraid,
  waitForChildExit,
  terminateChild,
};
