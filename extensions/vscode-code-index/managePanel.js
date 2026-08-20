const vscode = require('vscode');

class ManagePanel {
  constructor(context, runCli, applyProject) {
    this.context = context; this.runCli = runCli; this.applyProject = applyProject;
    this.panel = undefined; this.folder = undefined;
    this.locale = vscode.env.language.toLowerCase().startsWith('ru') ? 'ru' : 'en';
  }

  async open(folder) {
    this.folder = folder;
    if (!this.panel) {
      const media = vscode.Uri.joinPath(this.context.extensionUri, 'media');
      this.panel = vscode.window.createWebviewPanel('codeIndexManage', vscode.l10n.t('Code Index: Manage'), vscode.ViewColumn.Active, {
        enableScripts: true, retainContextWhenHidden: true, localResourceRoots: [media],
      });
      this.panel.onDidDispose(() => { this.panel = undefined; });
      this.panel.webview.onDidReceiveMessage(message => this.handleMessage(message));
      this.panel.webview.html = this.html(this.panel.webview, media);
    }
    this.panel.reveal(); await this.sendState();
  }

  async sendState(result = undefined) {
    if (!this.panel || !this.folder) return;
    const state = await this.runCli(['settings', 'show', '--project', this.folder.uri.fsPath], this.folder.uri.fsPath);
    this.panel.webview.postMessage({ type: 'state', state, locale: this.locale, result });
  }

  async handleMessage(message) {
    if (!this.panel || !this.folder) return;
    const cwd = this.folder.uri.fsPath;
    try {
      let result;
      if (message.command === 'ready' || message.command === 'refresh') return this.sendState();
      if (message.command === 'choosePath') {
        const picked = await vscode.window.showOpenDialog({
          canSelectFiles: message.kind === 'file', canSelectFolders: message.kind !== 'file', canSelectMany: false,
          defaultUri: vscode.Uri.file(message.value || cwd), openLabel: this.locale === 'ru' ? 'Выбрать' : 'Select',
        });
        if (picked?.[0]) this.panel.webview.postMessage({ type: 'path', target: message.target, value: picked[0].fsPath });
        return;
      }
      if (message.command === 'saveDefaults') {
        result = await this.runCli(['settings', 'apply-defaults'], cwd, JSON.stringify(message.payload));
      } else if (message.command === 'testBackend') {
        result = await this.runCli(['settings', 'test-backend'], cwd, JSON.stringify(message.payload));
      } else if (message.command === 'planProject') {
        result = await this.runCli(['settings', 'plan', cwd], cwd, JSON.stringify(message.payload));
        this.panel.webview.postMessage({ type: 'plan', plan: result, payload: message.payload }); return;
      } else if (message.command === 'applyProject') {
        const warning = this.locale === 'ru'
          ? `Применить изменения (${message.payload.impact || 'configuration-only'})? Предыдущий source будет сохранён.`
          : `Apply changes (${message.payload.impact || 'configuration-only'})? The previous source will be retained.`;
        const apply = this.locale === 'ru' ? 'Применить' : 'Apply';
        if (await vscode.window.showWarningMessage(warning, { modal: true }, apply) !== apply) return;
        result = await this.applyProject(this.folder, message.payload);
      } else if (message.command === 'saveProfile') {
        const p = message.payload;
        const args = ['profile', 'set', p.profile_id, '--display-name', p.display_name, '--scope', p.scope,
          '--provider', p.provider, '--model', p.model, '--dimension', String(p.dimension), '--base-url', p.base_url || ''];
        if (p.scope === 'project') args.push('--project-id', p.project_id);
        if (p.api_key) args.push('--api-key-stdin');
        result = await this.runCli(args, cwd, p.api_key || undefined);
      } else if (message.command === 'testProfile') {
        result = await this.runCli(['profile', 'test-config'], cwd, JSON.stringify(message.payload));
      } else if (message.command === 'deleteProfile') {
        const remove = this.locale === 'ru' ? 'Удалить' : 'Delete';
        if (await vscode.window.showWarningMessage(this.locale === 'ru' ? 'Удалить неиспользуемый профиль?' : 'Delete the unused profile?', { modal: true }, remove) !== remove) return;
        result = await this.runCli(['profile', 'delete', message.profileId], cwd);
      } else if (message.command === 'useSource') {
        result = await this.runCli(['source', 'use', cwd, message.sourceId], cwd);
      } else if (message.command === 'reconcile') {
        result = await this.runCli(['index', cwd], cwd);
      }
      await this.sendState(result);
    } catch (error) {
      this.panel.webview.postMessage({ type: 'result', result: { status: 'error', error: error.message } });
    }
  }

  html(webview, media) {
    const nonce = [...Array(32)].map(() => Math.random().toString(36)[2]).join('');
    const script = webview.asWebviewUri(vscode.Uri.joinPath(media, 'manage.js'));
    const style = webview.asWebviewUri(vscode.Uri.joinPath(media, 'manage.css'));
    return `<!doctype html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
      <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource}; script-src 'nonce-${nonce}';">
      <link rel="stylesheet" href="${style}"><title>Code Index</title></head><body>
      <header><div><h1>Code Index</h1><p id="projectPath"></p></div><button id="refresh" class="secondary" data-i18n="refresh"></button></header>
      <nav role="tablist"><button data-tab="overview" data-i18n="overview"></button><button data-tab="global" data-i18n="global"></button><button data-tab="project" data-i18n="project"></button><button data-tab="profiles" data-i18n="profiles"></button><button data-tab="sources" data-i18n="sources"></button></nav>
      <main>
        <section id="tab-overview" class="tab"><div class="cards"><article><h2 data-i18n="activeSource"></h2><dl id="summary"></dl></article><article><h2 data-i18n="indexStatus"></h2><pre id="statusResult"></pre></article></div></section>
        <section id="tab-global" class="tab hidden"><h2 data-i18n="globalSettings"></h2><p data-i18n="globalHint"></p><form id="globalForm">
          <div class="grid"><label><span data-i18n="backend"></span><select name="backend"><option value="lancedb">LanceDB</option><option value="qdrant">Qdrant</option></select></label>
          <label><span data-i18n="embeddingProfile"></span><select name="embedding_profile" data-profiles></select></label></div>
          <fieldset data-backend="lancedb"><legend>LanceDB</legend><label><span data-i18n="lanceRoot"></span><div class="path"><input name="lancedb_root"><button type="button" data-pick="lancedb_root" data-kind="folder">…</button></div></label></fieldset>
          <fieldset data-backend="qdrant"><legend>Qdrant</legend><div class="grid"><label><span>URL</span><input name="qdrant_url"></label><label><span data-i18n="apiKey"></span><input name="qdrant_api_key" type="password" autocomplete="new-password" placeholder="••••••"></label></div></fieldset>
          <details><summary data-i18n="advanced"></summary><div class="grid advanced-fields"></div></details>
          <div class="actions"><button type="button" data-action="test-global" class="secondary" data-i18n="testConnection"></button><button type="submit" data-i18n="saveGlobal"></button></div></form></section>
        <section id="tab-project" class="tab hidden"><h2 data-i18n="projectSettings"></h2><p data-i18n="projectHint"></p><form id="projectForm">
          <label class="check"><input type="checkbox" name="watch_enabled"><span data-i18n="watcher"></span></label>
          <div class="grid"><label><span data-i18n="backend"></span><select name="backend"><option value="lancedb">LanceDB</option><option value="qdrant">Qdrant</option></select></label>
          <label><span data-i18n="embeddingProfile"></span><select name="embedding_profile" data-profiles></select></label></div>
          <fieldset data-backend="lancedb"><legend>LanceDB</legend><label><span data-i18n="lanceRoot"></span><div class="path"><input name="lancedb_root"><button type="button" data-pick="lancedb_root" data-kind="folder">…</button></div></label></fieldset>
          <fieldset data-backend="qdrant"><legend>Qdrant</legend><div class="grid"><label><span>URL</span><input name="qdrant_url"></label><label><span data-i18n="apiKey"></span><input name="qdrant_api_key" type="password" autocomplete="new-password" placeholder="••••••"></label></div></fieldset>
          <details><summary data-i18n="advanced"></summary><div class="grid advanced-fields"></div></details>
          <div class="actions"><button type="button" id="resetProject" class="secondary" data-i18n="resetProject"></button><button type="submit" data-i18n="planChanges"></button></div></form><article id="planBox" class="hidden"><h3 data-i18n="changePlan"></h3><pre id="planResult"></pre><button id="applyPlan" data-i18n="apply"></button></article></section>
        <section id="tab-profiles" class="tab hidden"><div class="split"><div><h2 data-i18n="profiles"></h2><select id="profileList" size="10"></select><div class="actions"><button id="newProfile" data-i18n="newProfile"></button><button id="copyProfile" class="secondary" data-i18n="copyProfile"></button></div></div>
          <form id="profileForm"><label><span>ID</span><input name="profile_id" required></label><label><span data-i18n="displayName"></span><input name="display_name" required></label><div class="grid"><label><span data-i18n="scope"></span><select name="scope"><option value="global" data-i18n="global"></option><option value="project" data-i18n="project"></option></select></label><label><span data-i18n="provider"></span><select name="provider"><option value="fastembed">FastEmbed</option><option value="openai-compatible">OpenAI-compatible</option></select></label></div>
          <label><span data-i18n="model"></span><input name="model" required></label><label><span data-i18n="dimension"></span><input name="dimension" type="number" min="1" required></label><label><span data-i18n="baseUrl"></span><input name="base_url"></label><label><span data-i18n="apiKey"></span><input name="api_key" type="password" autocomplete="new-password" placeholder="••••••"></label>
          <div class="actions"><button type="button" id="testProfile" class="secondary" data-i18n="testProfile"></button><button type="submit" data-i18n="saveProfile"></button><button type="button" id="deleteProfile" class="danger" data-i18n="deleteProfile"></button></div></form></div></section>
        <section id="tab-sources" class="tab hidden"><h2 data-i18n="sources"></h2><table><thead><tr><th>ID</th><th data-i18n="backend"></th><th data-i18n="embeddingProfile"></th><th></th></tr></thead><tbody id="sourceRows"></tbody></table><div class="actions"><button id="reconcile" data-i18n="reconcile"></button></div></section>
      </main><aside id="toast" aria-live="polite"></aside><script nonce="${nonce}" src="${script}"></script></body></html>`;
  }

  dispose() { this.panel?.dispose(); this.panel = undefined; }
}

module.exports = { ManagePanel };
