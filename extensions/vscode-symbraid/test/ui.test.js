const assert = require('assert');
const fs = require('fs');
const path = require('path');

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

console.log('manage webview tests passed');
