const assert = require('assert');
const fs = require('fs');
const path = require('path');
const { loadManageState } = require('../manageState');
const Module = require('module');

let confirmRegistration;
const originalLoad = Module._load;
let ManagePanel;
try {
  Module._load = function (request, ...args) {
    if (request === 'vscode') return { window: { showWarningMessage: (...values) => confirmRegistration(...values) } };
    return originalLoad.call(this, request, ...args);
  };
  ({ ManagePanel } = require('../managePanel'));
} finally {
  Module._load = originalLoad;
}

const root = path.resolve(__dirname, '..');
const host = fs.readFileSync(path.join(root, 'managePanel.js'), 'utf8');
const client = fs.readFileSync(path.join(root, 'media', 'manage.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'media', 'manage.css'), 'utf8');
const extension = fs.readFileSync(path.join(root, 'extension.js'), 'utf8');

assert.ok(host.includes('Content-Security-Policy'));
assert.ok(host.includes("script-src 'nonce-${nonce}'"));
assert.ok(!host.includes('onclick='));
assert.ok(client.includes("ru:"));
assert.ok(client.includes("en:"));
assert.ok(client.includes("clear_overrides"));
assert.ok(client.includes("JSON.stringify(project.index_status || {}, null, 2)"));
assert.ok(!client.includes('project.service_status'));
assert.ok(css.includes('var(--vscode-editor-background)'));
for (const source of [host, client, extension]) {
  assert.ok(!source.toLowerCase().includes(['ki', 'lo'].join('')));
}

(async () => {
  const cwd = path.join(root, 'fixture');
  const defaults = { backend: 'qdrant', qdrant_url: 'http://localhost:18133', embedding_profile: 'remote' };
  const profiles = { remote: { scope: 'global', provider: 'openai-compatible', model: 'custom', dimension: 8 } };
  const newProjectCalls = [];
  const newProject = await loadManageState(async (args, commandCwd) => {
    assert.strictEqual(commandCwd, cwd);
    newProjectCalls.push(args);
    assert.deepStrictEqual(args, ['settings', 'show', '--project', cwd]);
    return {
      status: 'ok', defaults, profiles,
      project: {
        path: cwd, registered: false, effective: defaults,
        active_source: null, sources: [],
        index_status: { status: 'not_registered', indexed: false },
      },
    };
  }, cwd);
  assert.strictEqual(newProject.status, 'ok', 'Manage must preview an unregistered workspace');
  assert.deepStrictEqual(newProject.defaults, defaults);
  assert.deepStrictEqual(newProject.profiles, profiles);
  assert.strictEqual(newProject.project.registered, false);
  assert.strictEqual(newProject.project.effective.embedding_profile, 'remote');
  assert.deepStrictEqual(newProjectCalls, [
    ['settings', 'show', '--project', cwd],
  ]);

  const calls = [];
  const recovered = await loadManageState(async (args) => {
    calls.push(args);
    if (args[0] === 'settings') return { status: 'ok', project: { path: cwd } };
    return { status: 'ok', indexed: true };
  }, cwd);
  assert.deepStrictEqual(recovered.project.index_status, { status: 'ok', indexed: true });
  assert.strictEqual(calls.length, 2);

  const fallbackFailure = await loadManageState(async (args) => {
    if (args[0] === 'settings') return { status: 'ok', project: { path: cwd, index_status: {} } };
    throw new Error('status failed');
  }, cwd);
  assert.deepStrictEqual(fallbackFailure.project.index_status, { status: 'error', error: 'status failed' });

  const settingsFailure = await loadManageState(async () => { throw new Error('settings failed'); }, cwd);
  assert.strictEqual(settingsFailure.status, 'error');
  assert.deepStrictEqual(settingsFailure.project.index_status, { status: 'error', error: 'settings failed' });

  const registrationFailure = await loadManageState(async (args) => {
    if (args.includes('--project')) throw new Error('project settings failed');
    assert.deepStrictEqual(args, ['settings', 'show']);
    return { status: 'ok', defaults, profiles: { ...profiles, private: { scope: 'project', project_id: 'other' } } };
  }, cwd);
  assert.strictEqual(registrationFailure.status, 'error');
  assert.deepStrictEqual(registrationFailure.defaults, defaults, 'global settings must remain visible on a project failure');
  assert.deepStrictEqual(registrationFailure.profiles, profiles, 'fallback must only expose global profiles');
  assert.deepStrictEqual(registrationFailure.project.index_status, { status: 'error', error: 'project settings failed' });

  const panel = Object.create(ManagePanel.prototype);
  panel.locale = 'ru';
  panel.folder = { uri: { fsPath: cwd } };
  panel.panel = { webview: { postMessage() {} } };
  let registrations = 0;
  panel.applyProject = async (folder, values) => {
    assert.strictEqual(folder, panel.folder);
    assert.strictEqual(values.embedding_profile, defaults.embedding_profile);
    registrations += 1;
    return { status: 'ok' };
  };
  panel.sendState = async () => {};
  const confirmation = { command: 'applyProject', payload: { ...defaults, auto_watch: true, impact: 'register', plan_hash: 'reviewed' } };
  confirmRegistration = async (warning, options) => {
    assert.ok(warning.includes('Зарегистрировать проект'));
    assert.strictEqual(options.modal, true);
    return undefined;
  };
  await panel.handleMessage(confirmation);
  assert.strictEqual(registrations, 0, 'cancelling confirmation must leave the project unregistered');
  confirmRegistration = async (_warning, _options, apply) => apply;
  await panel.handleMessage(confirmation);
  assert.strictEqual(registrations, 1, 'global settings can be registered with explicit confirmation');

  console.log('manage webview tests passed');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
