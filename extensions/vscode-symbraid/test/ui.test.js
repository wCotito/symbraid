const assert = require('assert');
const fs = require('fs');
const path = require('path');
const { loadManageState } = require('../manageState');

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

  console.log('manage webview tests passed');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
