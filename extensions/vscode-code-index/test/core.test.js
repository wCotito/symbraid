const assert = require('assert');
const path = require('path');
const { eventKind, headChanged, normalizeFsPath } = require('../core');

assert.strictEqual(eventKind('src/auth/session.ts'), 'refresh');
assert.strictEqual(eventKind('docs/design.md'), 'refresh');
assert.strictEqual(eventKind('.gitignore'), 'reconcile');
assert.strictEqual(eventKind('node_modules/pkg/index.js'), 'ignore');
assert.strictEqual(eventKind('dist/app.js'), 'ignore');
assert.strictEqual(eventKind('src/app.min.js'), 'ignore');
assert.strictEqual(eventKind('src/image.png'), 'ignore');
assert.strictEqual(eventKind('src/new.ts'), 'refresh');
assert.strictEqual(eventKind('src/deleted.ts'), 'refresh');
assert.strictEqual(headChanged('abc', 'def'), true);
assert.strictEqual(headChanged('abc', 'abc'), false);
assert.strictEqual(normalizeFsPath('.'), process.platform === 'win32' ? path.resolve('.').toLowerCase() : path.resolve('.'));

console.log('watcher core tests passed');
