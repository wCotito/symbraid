const { test, expect } = require('@playwright/test');
const fs = require('fs');
const os = require('os');
const path = require('path');
const Module = require('module');
const { spawnSync } = require('child_process');
const { loadManageState } = require('../manageState');

const extension = path.resolve(__dirname, '..');
const origin = 'https://symbraid.test';
const originalLoad = Module._load;
let ManagePanel;
try {
  Module._load = function (request, ...args) {
    if (request === 'vscode') return { Uri: { joinPath: (_base, name) => ({ name }) } };
    return originalLoad.call(this, request, ...args);
  };
  ({ ManagePanel } = require('../managePanel'));
} finally {
  Module._load = originalLoad;
}
const html = ManagePanel.prototype.html({
  cspSource: origin, asWebviewUri: uri => `${origin}/${uri.name}`,
}, {});

for (const locale of ['en', 'ru']) {
  test(`long global root preview and shorter-root registration (${locale})`, async ({ page }) => {
    const tempRoot = fs.realpathSync(os.tmpdir());
    const temporary = fs.mkdtempSync(path.join(tempRoot, 'symbraid-manage-preview-'));
    const run = (operation, payload) => {
      const result = spawnSync(process.env.SYMBRAID_TEST_PYTHON || 'python', [
        '-S', path.join(__dirname, 'manage_fixture.py'), temporary, operation,
      ], {
        input: payload === undefined ? undefined : JSON.stringify(payload), encoding: 'utf8',
        env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONDONTWRITEBYTECODE: '1' },
      });
      if (result.error) throw result.error;
      if (result.status !== 0) throw new Error(result.stderr);
      return JSON.parse(result.stdout);
    };
    try {
      const fixture = run('init');
      const before = fs.readFileSync(path.join(temporary, 'config.json'), 'utf8');
      const state = await loadManageState(async args => run(args.includes('--project') ? 'state' : 'globals'), fixture.project);
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route(`${origin}/**`, async route => {
        const name = new URL(route.request().url()).pathname;
        if (name === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (name === '/manage.js' || name === '/manage.css') return route.fulfill({
          contentType: name.endsWith('.js') ? 'application/javascript' : 'text/css',
          body: fs.readFileSync(path.join(extension, 'media', name.slice(1)), 'utf8'),
        });
        return route.abort();
      });
      await page.addInitScript(() => {
        window.messages = [];
        window.acquireVsCodeApi = () => ({ postMessage: message => window.messages.push(message) });
      });
      await page.goto(origin);
      await page.evaluate(({ state, locale }) => window.postMessage({ type: 'state', state, locale }, '*'), { state, locale });
      await page.locator('[data-tab="project"]').click();
      const form = page.locator('#projectForm');
      for (const name of ['max_file_bytes', 'chunk_chars', 'chunk_overlap_chars', 'batch_size', 'rg_path']) {
        await expect(form.locator(`[name="${name}"]`)).toHaveValue(String(fixture.defaults[name]));
      }
      await expect(form.locator('[name="embedding_profile"]')).toHaveValue(fixture.defaults.embedding_profile);
      await expect(form.locator('[name="lancedb_root"]')).toHaveValue(fixture.defaults.lancedb_root);
      await expect(page.locator('#planProject')).toHaveText(locale === 'ru' ? 'Зарегистрировать и запустить' : 'Register and start');
      expect(await page.evaluate(() => window.messages)).toEqual([{ command: 'ready' }]);
      expect(fs.readFileSync(path.join(temporary, 'config.json'), 'utf8')).toBe(before);

      await form.locator('[name="lancedb_root"]').fill(fixture.short_root);
      await page.locator('#planProject').click();
      const submitted = await page.evaluate(() => window.messages.find(message => message.command === 'planProject'));
      expect(submitted.payload).toMatchObject({
        backend: 'lancedb', embedding_profile: fixture.defaults.embedding_profile,
        lancedb_root: fixture.short_root, auto_watch: true,
        max_file_bytes: 2097152, chunk_chars: 2400, chunk_overlap_chars: 120, batch_size: 7,
      });
      const plan = run('plan', submitted.payload);
      expect(plan.impact).toBe('register');
      expect(run('state').project.registered).toBe(false);
      expect(fs.readFileSync(path.join(temporary, 'config.json'), 'utf8')).toBe(before);
      await page.evaluate(({ plan, payload }) => window.postMessage({ type: 'plan', plan, payload }, '*'), { plan, payload: submitted.payload });
      await page.locator('#applyPlan').click();
      const confirmed = await page.evaluate(() => window.messages.find(message => message.command === 'applyProject'));
      expect(confirmed.payload).toMatchObject({ ...submitted.payload, plan_hash: plan.plan_hash, impact: 'register' });
      expect(run('apply', confirmed.payload).impact).toBe('register');
      const registered = run('project');
      expect(registered.effective).toMatchObject({
        embedding_profile: fixture.defaults.embedding_profile,
        lancedb_root: fixture.short_root, max_file_bytes: 2097152,
        chunk_chars: 2400, chunk_overlap_chars: 120, batch_size: 7,
      });
      expect(registered.project.auto_watch).toBe(true);
      expect(Object.keys(registered.project.sources)).toHaveLength(1);
      const source = registered.project.sources[registered.project.active_source_id];
      expect(source.embedding_profile).toBe(fixture.defaults.embedding_profile);
      expect(path.dirname(source.location.directory)).toBe(fixture.short_root);
      expect(fs.existsSync(fixture.short_root)).toBe(false);
      expect(fs.existsSync(fixture.defaults.lancedb_root)).toBe(false);
      expect(errors).toEqual([]);
    } finally {
      if (path.dirname(path.resolve(temporary)) !== tempRoot || !path.basename(temporary).startsWith('symbraid-manage-preview-')) {
        throw new Error('Unexpected fixture cleanup target');
      }
      fs.rmSync(temporary, { recursive: true, force: true });
    }
  });
}
