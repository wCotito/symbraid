const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const childProcess = require('child_process');
const { EventEmitter } = require('events');
const manifest = require('../package.json');
const { resolveExecutablePath } = require('../executable');
const {
  Controller,
  appendDiagnosticTail,
  commandError,
  spawnSymbraid,
  terminateChild,
  watcherDetails,
} = require('../extension');

assert.strictEqual(manifest.name, 'symbraid');
assert.strictEqual(manifest.publisher, 'symbraid');
assert.strictEqual(manifest.version, '0.3.0');
assert.ok(manifest.contributes.configuration.properties['symbraid.executablePath']);

const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'symbraid-extension-'));
const configured = path.join(temp, 'custom-symbraid');
assert.strictEqual(resolveExecutablePath('  ' + configured + '  ', { env: { PATH: '' } }), configured);

const pathName = process.platform === 'win32' ? 'symbraid.cmd' : 'symbraid';
const pathExecutable = path.join(temp, pathName);
fs.writeFileSync(pathExecutable, '');
const pathEnv = {
  PATH: temp,
  PATHEXT: '.COM;.EXE;.BAT;.CMD',
};
assert.strictEqual(resolveExecutablePath('', { env: pathEnv }), pathExecutable);

assert.strictEqual(resolveExecutablePath('', { env: { PATH: '' } }), 'symbraid');
assert.strictEqual(
  commandError('{"status":"error","error":"watch lease busy"}', '', undefined, ['watch']),
  'watch lease busy',
);
assert.deepStrictEqual(
  watcherDetails({ project: { watcher: { running: true, owner: { pid: 42 } } } }),
  { running: true, owner: { pid: 42 } },
);
assert.strictEqual(watcherDetails({ watcher: { running: false, owner: null } }), undefined);
assert.strictEqual(appendDiagnosticTail('1234', '5678', 5), '45678');

let spawnCalled = false;
const originalSpawn = childProcess.spawn;
childProcess.spawn = () => {
  spawnCalled = true;
  throw new Error('spawn should not be reached for an unsafe script launcher argument');
};
try {
  assert.throws(
    () => spawnSymbraid(
      'symbraid.cmd',
      ['watch', path.join(temp, 'workspace & payload')],
      temp,
      'win32',
    ),
    /shell metacharacters/,
  );
  assert.throws(
    () => spawnSymbraid(
      path.join(temp, 'symbraid&evil.cmd'),
      ['watch', temp],
      temp,
      'win32',
    ),
    /shell metacharacters/,
    'unsafe configured launcher paths must be rejected before shell spawn',
  );
} finally {
  childProcess.spawn = originalSpawn;
}
assert.strictEqual(spawnCalled, false, 'unsafe script launcher inputs must not reach a shell-backed spawn');

const root = path.resolve(__dirname, '..');
const host = fs.readFileSync(path.join(root, 'extension.js'), 'utf8');
const panel = fs.readFileSync(path.join(root, 'managePanel.js'), 'utf8');
const client = fs.readFileSync(path.join(root, 'media', 'manage.js'), 'utf8');
for (const source of [host, panel, client]) {
  assert.ok(!source.includes('createFileSystemWatcher'), 'the extension must not create a filesystem watcher');
  assert.ok(!source.includes('watch_enabled'), 'the extension must use auto_watch');
}
assert.ok(!host.includes('gitHead'));
assert.ok(!host.includes("['index'"));
assert.ok(!host.includes("['refresh'"));
assert.ok(host.includes("['watch', folder.uri.fsPath]"));
assert.ok(host.includes("['project', 'autowatch'"));
assert.ok(!fs.existsSync(path.join(root, 'core.js')), 'the extension must not contain watcher/index core');

function delayedChild(exitDelayMs) {
  const child = new EventEmitter();
  child.pid = 1234;
  child.exitCode = null;
  child.signalCode = null;
  child.killed = false;
  child.signals = [];
  child.kill = (signal = 'SIGTERM') => {
    child.killed = true;
    child.signals.push(signal);
    setTimeout(() => {
      child.exitCode = signal === 'SIGKILL' ? null : 0;
      child.signalCode = signal === 'SIGKILL' ? 'SIGKILL' : null;
      child.emit('exit', child.exitCode, child.signalCode);
      child.emit('close', child.exitCode, child.signalCode);
    }, exitDelayMs);
    return true;
  };
  return child;
}

function stubbornChild(forceDelayMs) {
  const child = new EventEmitter();
  child.pid = 1234;
  child.exitCode = null;
  child.signalCode = null;
  child.killed = false;
  child.signals = [];
  child.kill = (signal = 'SIGTERM') => {
    child.killed = true;
    child.signals.push(signal);
    if (signal === 'SIGKILL') {
      setTimeout(() => {
        child.signalCode = 'SIGKILL';
        child.emit('exit', null, child.signalCode);
        child.emit('close', null, child.signalCode);
      }, forceDelayMs);
    }
    return true;
  };
  return child;
}

(async () => {
  const alreadyExited = new EventEmitter();
  alreadyExited.pid = 1234;
  alreadyExited.exitCode = 0;
  alreadyExited.signalCode = null;
  alreadyExited.killed = false;
  alreadyExited.kill = () => { throw new Error('already-exited child must not be killed'); };
  const exitedResult = await terminateChild(alreadyExited, { graceTimeoutMs: 25, forceTimeoutMs: 25 });
  assert.strictEqual(exitedResult.forced, false);

  const child = delayedChild(15);
  const started = Date.now();
  const result = await terminateChild(child, { graceTimeoutMs: 100, forceTimeoutMs: 100 });
  assert.strictEqual(result.forced, false);
  assert.deepStrictEqual(child.signals, ['SIGTERM']);
  assert.ok(Date.now() - started >= 10, 'termination must await the child exit event');

  const stubborn = stubbornChild(10);
  const forcedResult = await terminateChild(stubborn, { graceTimeoutMs: 10, forceTimeoutMs: 100 });
  assert.strictEqual(forcedResult.forced, true);
  assert.deepStrictEqual(stubborn.signals, ['SIGTERM', 'SIGKILL']);

  const folder = { uri: { fsPath: temp } };
  const key = process.platform === 'win32' ? path.resolve(temp).toLowerCase() : path.resolve(temp);
  const externalController = Object.create(Controller.prototype);
  externalController.processes = new Map();
  externalController.states = new Map();
  externalController.runCli = async () => ({
    status: 'ok',
    watcher: { running: true, owner: { pid: 42 } },
  });
  externalController.updateStatus = async () => {};
  const adopted = await externalController.startWatch(folder, false);
  assert.strictEqual(adopted, undefined);
  assert.strictEqual(externalController.processes.size, 0);
  assert.strictEqual(externalController.states.get(key).mode, 'running');
  assert.strictEqual(externalController.states.get(key).external, true);

  const staleController = Object.create(Controller.prototype);
  staleController.api = { workspace: { workspaceFolders: [folder] } };
  staleController.processes = new Map();
  staleController.states = new Map([[
    key,
    { mode: 'running', autoWatch: true, external: true, owner: { pid: 42 } },
  ]]);
  staleController.runCli = async () => ({ status: 'ok', watcher: { running: false, owner: null } });
  staleController.updateStatus = async () => {};
  let restarted = false;
  staleController.startWatch = async (_folder, persist) => {
    restarted = persist === false;
  };
  await staleController.refreshExternalWatchers();
  assert.strictEqual(restarted, true, 'auto-watch must restart after an external watcher exits');
  assert.strictEqual(staleController.states.get(key).external, false);

  const disabledController = Object.create(Controller.prototype);
  disabledController.api = { workspace: { workspaceFolders: [folder] } };
  disabledController.processes = new Map();
  disabledController.states = new Map([[
    key,
    { mode: 'running', autoWatch: true, external: true, owner: { pid: 42 } },
  ]]);
  disabledController.externalProbeActive = false;
  let resolveDisabledProbe;
  disabledController.runCli = async () => new Promise((resolve) => { resolveDisabledProbe = resolve; });
  disabledController.updateStatus = async () => {};
  let restartedAfterDisable = false;
  disabledController.startWatch = async () => { restartedAfterDisable = true; };
  const disabledProbe = disabledController.refreshExternalWatchers();
  await Promise.resolve();
  disabledController.states.set(key, {
    ...disabledController.states.get(key),
    autoWatch: false,
  });
  resolveDisabledProbe({ status: 'ok', watcher: { running: false, owner: null } });
  await disabledProbe;
  assert.strictEqual(restartedAfterDisable, false, 'an explicit disable must win over an in-flight probe');
  assert.strictEqual(disabledController.states.get(key).autoWatch, false);

  const startupController = Object.create(Controller.prototype);
  startupController.api = { workspace: { workspaceFolders: [folder] } };
  startupController.states = new Map();
  startupController.runCli = async () => { throw new Error('settings failed'); };
  startupController.updateStatus = async () => {};
  const startupErrors = [];
  startupController.showWatchError = async (message) => { startupErrors.push(message); };
  await startupController.start();
  assert.deepStrictEqual(startupErrors, ['settings failed']);

  const preferenceController = Object.create(Controller.prototype);
  preferenceController.processes = new Map();
  preferenceController.states = new Map();
  preferenceController.setAutoWatch = async () => { throw new Error('preference failed'); };
  preferenceController.updateStatus = async () => {};
  const preferenceErrors = [];
  preferenceController.showWatchError = async (message) => { preferenceErrors.push(message); };
  await assert.rejects(() => preferenceController.startWatch(folder, true), /preference failed/);
  assert.deepStrictEqual(preferenceErrors, ['preference failed']);

  const singleFlightController = Object.create(Controller.prototype);
  singleFlightController.starting = new Map();
  singleFlightController.disposed = false;
  let releaseStart;
  const startGate = new Promise((resolve) => { releaseStart = resolve; });
  let startCalls = 0;
  singleFlightController._startWatch = async () => {
    startCalls += 1;
    await startGate;
    return 'started';
  };
  const firstStart = singleFlightController.startWatch(folder, false);
  const secondStart = singleFlightController.startWatch(folder, false);
  assert.strictEqual(startCalls, 1, 'concurrent starts must share one operation');
  releaseStart();
  assert.deepStrictEqual(await Promise.all([firstStart, secondStart]), ['started', 'started']);

  const disposingController = Object.create(Controller.prototype);
  disposingController.api = { workspace: { workspaceFolders: [folder] } };
  disposingController.processes = new Map();
  disposingController.starting = new Map();
  disposingController.states = new Map([[
    key,
    { mode: 'running', autoWatch: true, external: true, owner: { pid: 42 } },
  ]]);
  disposingController.externalProbeActive = false;
  disposingController.externalProbeTimer = undefined;
  disposingController.managePanel = { dispose() {} };
  disposingController.status = { dispose() {} };
  disposingController.output = { dispose() {} };
  let resolveProbe;
  disposingController.runCli = async () => new Promise((resolve) => { resolveProbe = resolve; });
  disposingController.updateStatus = async () => {};
  let restartedAfterDispose = false;
  disposingController.startWatch = async () => { restartedAfterDispose = true; };
  const pendingProbe = disposingController.refreshExternalWatchers();
  await Promise.resolve();
  disposingController.dispose();
  resolveProbe({ status: 'ok', watcher: { running: false, owner: null } });
  await pendingProbe;
  assert.strictEqual(restartedAfterDispose, false, 'dispose must prevent a late watcher restart');

  const controller = Object.create(Controller.prototype);
  controller.processes = new Map();
  controller.states = new Map([[key, { mode: 'running', autoWatch: true }]]);
  const controllerChild = delayedChild(15);
  controller.processes.set(key, controllerChild);
  controller.updateStatus = async () => {};
  const stopStarted = Date.now();
  await controller.stopWatch(folder, false);
  assert.ok(Date.now() - stopStarted >= 10, 'stopWatch must await child exit before returning');
  assert.strictEqual(controller.processes.has(key), false);
  assert.strictEqual(controller.states.get(key).mode, 'stopped');

  console.log('Symbraid extension tests passed');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
