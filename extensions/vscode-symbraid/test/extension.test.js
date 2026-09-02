const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const childProcess = require('child_process');
const { EventEmitter } = require('events');
const manifest = require('../package.json');
const { legacyExecutablePath, resolveExecutablePath } = require('../executable');
const { Controller, spawnSymbraid, terminateChild } = require('../extension');

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

const legacy = legacyExecutablePath({ LOCALAPPDATA: temp }, process.platform);
assert.strictEqual(resolveExecutablePath('', { env: { LOCALAPPDATA: temp, PATH: '' } }), legacy);

let spawnCalled = false;
const originalSpawn = childProcess.spawn;
childProcess.spawn = () => {
  spawnCalled = true;
  throw new Error('spawn should not be reached for an unsafe legacy launcher argument');
};
try {
  assert.throws(
    () => spawnSymbraid(
      'legacy.code-index.cmd',
      ['watch', path.join(temp, 'workspace & payload')],
      temp,
      'win32',
    ),
    /shell metacharacters/,
  );
  assert.throws(
    () => spawnSymbraid(
      path.join(temp, 'legacy&evil.cmd'),
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
assert.strictEqual(spawnCalled, false, 'unsafe legacy launcher inputs must not reach a shell-backed spawn');

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
assert.ok(!fs.existsSync(path.join(root, 'core.js')), 'legacy local watcher/index core should be removed');

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
