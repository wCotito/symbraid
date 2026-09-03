const vscode = acquireVsCodeApi();

const strings = {
  en: {
    reload: 'Reload', overview: 'Overview', global: 'Global', project: 'Project', profiles: 'Models', sources: 'Sources',
    activeSource: 'Active source', serviceStatus: 'Service status', globalSettings: 'Global defaults',
    globalHint: 'Backend, storage and model defaults are used when a managed source is created.', backend: 'Backend',
    embeddingProfile: 'Embedding profile', lanceRoot: 'LanceDB root', apiKey: 'API key', advanced: 'Advanced settings',
    testConnection: 'Test connection', saveGlobal: 'Save global defaults', projectSettings: 'Project settings',
    projectHint: 'Local values apply only to this workspace. Changes are applied through the Symbraid CLI.',
    autoWatch: 'Start Symbraid watch automatically', planChanges: 'Plan changes', changePlan: 'Change plan', apply: 'Apply',
    displayName: 'Display name', scope: 'Scope', provider: 'Provider', model: 'Model', dimension: 'Dimension',
    baseUrl: 'Base URL', testProfile: 'Test profile', saveProfile: 'Save profile', deleteProfile: 'Delete profile',
    newProfile: 'New', copyProfile: 'Project copy', use: 'Use', active: 'Active', local: 'local', inherited: 'global',
    resetProject: 'Reset to global', max_file_bytes: 'Max file bytes', chunk_chars: 'Chunk characters',
    chunk_overlap_chars: 'Chunk overlap', batch_size: 'Batch size', rg_path: 'rg executable',
  },
  ru: {
    reload: 'Обновить', overview: 'Обзор', global: 'Глобальные', project: 'Проект', profiles: 'Модели', sources: 'Источники',
    activeSource: 'Активный source', serviceStatus: 'Состояние сервиса', globalSettings: 'Глобальные настройки',
    globalHint: 'Backend, хранилище и модель используются при создании managed source.', backend: 'Backend',
    embeddingProfile: 'Профиль embedding', lanceRoot: 'Корень LanceDB', apiKey: 'API-ключ', advanced: 'Расширенные настройки',
    testConnection: 'Проверить подключение', saveGlobal: 'Сохранить глобальные', projectSettings: 'Настройки проекта',
    projectHint: 'Локальные значения относятся только к этому workspace. Изменения применяются через Symbraid CLI.',
    autoWatch: 'Автоматически запускать Symbraid watch', planChanges: 'Сформировать план', changePlan: 'План изменений',
    apply: 'Применить', displayName: 'Название', scope: 'Область', provider: 'Провайдер', model: 'Модель', dimension: 'Размерность',
    baseUrl: 'Базовый URL', testProfile: 'Проверить профиль', saveProfile: 'Сохранить профиль', deleteProfile: 'Удалить профиль',
    newProfile: 'Новый', copyProfile: 'Копия для проекта', use: 'Использовать', active: 'Активен', local: 'локально', inherited: 'глобально',
    resetProject: 'Сбросить к глобальным', max_file_bytes: 'Максимальный размер файла', chunk_chars: 'Размер chunk в символах',
    chunk_overlap_chars: 'Перекрытие chunks', batch_size: 'Размер batch', rg_path: 'Исполняемый файл rg',
  },
};

const advanced = ['max_file_bytes', 'chunk_chars', 'chunk_overlap_chars', 'batch_size', 'rg_path'];
const numeric = new Set(['max_file_bytes', 'chunk_chars', 'chunk_overlap_chars', 'batch_size', 'dimension']);
let locale = 'en';
let t = strings.en;
let state;
let pendingPlan;

function localize() {
  document.querySelectorAll('[data-i18n]').forEach((element) => {
    const value = t[element.dataset.i18n];
    if (value) element.textContent = value;
  });
}

function input(form, name) { return form.elements.namedItem(name); }

function fill(form, values = {}) {
  [...form.elements].forEach((element) => {
    if (!element.name || values[element.name] === undefined) return;
    if (element.type === 'checkbox') element.checked = Boolean(values[element.name]);
    else if (element.type !== 'password') element.value = values[element.name] ?? '';
  });
  updateBackend(form);
}

function payload(form) {
  const value = {};
  [...form.elements].forEach((element) => {
    if (!element.name) return;
    if (element.type === 'checkbox') value[element.name] = element.checked;
    else if (element.type === 'password' && !element.value) return;
    else value[element.name] = numeric.has(element.name) ? Number(element.value) : element.value;
  });
  return value;
}

function updateBackend(form) {
  const backend = input(form, 'backend')?.value;
  form.querySelectorAll('[data-backend]').forEach((element) => { element.hidden = element.dataset.backend !== backend; });
}

function addAdvancedFields() {
  document.querySelectorAll('.advanced-fields').forEach((box) => advanced.forEach((name) => {
    const label = document.createElement('label');
    const span = document.createElement('span');
    const field = document.createElement('input');
    span.textContent = t[name];
    field.name = name;
    field.type = numeric.has(name) ? 'number' : 'text';
    label.append(span, field);
    if (name === 'rg_path') {
      const wrap = document.createElement('div');
      const pick = document.createElement('button');
      wrap.className = 'path';
      pick.type = 'button';
      pick.textContent = '…';
      pick.dataset.pick = name;
      pick.dataset.kind = 'file';
      label.replaceChildren(span, wrap);
      wrap.append(field, pick);
    }
    box.append(label);
  }));
}

function setProfiles() {
  const profiles = state.profiles || {};
  document.querySelectorAll('[data-profiles]').forEach((select) => {
    const current = select.value;
    const globalOnly = select.closest('form')?.id === 'globalForm';
    select.replaceChildren();
    Object.entries(profiles).filter(([, profile]) => !globalOnly || profile.scope !== 'project').forEach(([id, profile]) => {
      const option = document.createElement('option');
      option.value = id;
      option.textContent = profile.display_name || id;
      select.append(option);
    });
    if ([...select.options].some((option) => option.value === current)) select.value = current;
  });
}

function markOrigins() {
  const project = state.project || {};
  const overrides = project.overrides || {};
  const form = document.getElementById('projectForm');
  [...form.elements].forEach((element) => {
    if (!element.name) return;
    const label = element.closest('label');
    if (!label || label.querySelector('.origin')) return;
    const badge = document.createElement('small');
    badge.className = 'origin';
    badge.textContent = Object.hasOwn(overrides, element.name) ? t.local : t.inherited;
    (label.querySelector('span') || label).append(badge);
  });
}

function render() {
  const project = state.project || {};
  const effective = project.effective || {};
  document.getElementById('projectPath').textContent = project.path || '';
  setProfiles();
  fill(document.getElementById('globalForm'), state.defaults || {});
  fill(document.getElementById('projectForm'), { ...effective, auto_watch: project.auto_watch });
  markOrigins();
  const source = project.active_source || {};
  const location = source.location || {};
  const summary = document.getElementById('summary');
  summary.replaceChildren();
  [['ID', source.id || '—'], [t.backend, source.backend || '—'], [t.embeddingProfile, source.embedding_profile || '—'],
    ['Location', location.directory || `${location.url || ''}${location.collection ? ` / ${location.collection}` : ''}`]].forEach(([key, value]) => {
    const dt = document.createElement('dt');
    const dd = document.createElement('dd');
    dt.textContent = key;
    dd.textContent = value;
    summary.append(dt, dd);
  });
  document.getElementById('statusResult').textContent = JSON.stringify(project.index_status || {}, null, 2);
  const profiles = state.profiles || {};
  const list = document.getElementById('profileList');
  list.replaceChildren();
  Object.entries(profiles).forEach(([id, profile]) => {
    const option = document.createElement('option');
    option.value = id;
    option.textContent = `${profile.display_name || id} · ${profile.provider || ''}`;
    list.append(option);
  });
  if (list.options.length) { list.selectedIndex = 0; loadProfile(list.value); }
  const rows = document.getElementById('sourceRows');
  rows.replaceChildren();
  (project.sources || []).forEach((sourceItem) => {
    const row = document.createElement('tr');
    [sourceItem.id, sourceItem.backend, sourceItem.embedding_profile].forEach((value) => {
      const cell = document.createElement('td');
      cell.textContent = value || '—';
      row.append(cell);
    });
    const action = document.createElement('td');
    const button = document.createElement('button');
    const active = sourceItem.id === project.active_source_id;
    button.textContent = active ? t.active : t.use;
    button.disabled = active;
    button.addEventListener('click', () => send('useSource', { sourceId: sourceItem.id }));
    action.append(button);
    row.append(action);
    rows.append(row);
  });
}

function loadProfile(id, copy = false) {
  const profile = (state.profiles || {})[id] || {};
  const projectId = state.project?.project_id || 'project';
  fill(document.getElementById('profileForm'), {
    ...profile,
    profile_id: copy ? `${id}-${projectId.slice(0, 8)}` : id,
    display_name: copy ? `${profile.display_name || id} (${t.project})` : profile.display_name || id,
    scope: copy ? 'project' : profile.scope || 'global',
    api_key: '',
  });
}

function toast(result) {
  const element = document.getElementById('toast');
  element.className = result?.status === 'error' ? 'error' : 'ok';
  element.textContent = result?.error || JSON.stringify(result);
  clearTimeout(element._timer);
  element._timer = setTimeout(() => { element.className = ''; element.style.display = 'none'; }, 5000);
  element.style.display = 'block';
}

function send(command, extra = {}) { vscode.postMessage({ command, ...extra }); }

document.querySelectorAll('nav button').forEach((button) => button.addEventListener('click', () => {
  document.querySelectorAll('nav button').forEach((item) => item.classList.toggle('active', item === button));
  document.querySelectorAll('.tab').forEach((tab) => tab.classList.toggle('hidden', tab.id !== `tab-${button.dataset.tab}`));
}));
document.querySelector('nav button').classList.add('active');
document.querySelectorAll('select[name="backend"]').forEach((element) => element.addEventListener('change', () => updateBackend(element.form)));
document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-pick]');
  if (button) send('choosePath', { target: button.dataset.pick, kind: button.dataset.kind, value: input(button.form, button.dataset.pick).value });
});
document.getElementById('reload').addEventListener('click', () => send('reload'));
document.getElementById('globalForm').addEventListener('submit', (event) => { event.preventDefault(); send('saveDefaults', { payload: payload(event.target) }); });
document.querySelector('[data-action="test-global"]').addEventListener('click', (event) => send('testBackend', { payload: payload(event.target.form) }));
document.getElementById('projectForm').addEventListener('submit', (event) => { event.preventDefault(); send('planProject', { payload: payload(event.target) }); });
document.getElementById('resetProject').addEventListener('click', () => {
  const form = document.getElementById('projectForm');
  const autoWatch = Boolean(state.project?.auto_watch);
  fill(form, { ...(state.defaults || {}), auto_watch: autoWatch });
  send('planProject', { payload: { clear_overrides: ['backend', 'embedding_profile', 'qdrant_url', 'qdrant_secret_ref', 'lancedb_root', ...advanced], auto_watch: autoWatch } });
});
document.getElementById('applyPlan').addEventListener('click', () => { if (pendingPlan) send('applyProject', { payload: pendingPlan }); });
document.getElementById('profileList').addEventListener('change', (event) => loadProfile(event.target.value));
document.getElementById('newProfile').addEventListener('click', () => { const form = document.getElementById('profileForm'); form.reset(); fill(form, { scope: 'global', provider: 'fastembed', dimension: 768 }); });
document.getElementById('copyProfile').addEventListener('click', () => loadProfile(document.getElementById('profileList').value, true));
document.getElementById('profileForm').addEventListener('submit', (event) => { event.preventDefault(); send('saveProfile', { payload: { ...payload(event.target), project_id: state.project?.project_id } }); });
document.getElementById('testProfile').addEventListener('click', (event) => send('testProfile', { payload: payload(event.target.form) }));
document.getElementById('deleteProfile').addEventListener('click', () => send('deleteProfile', { profileId: input(document.getElementById('profileForm'), 'profile_id').value }));
window.addEventListener('message', (event) => {
  const message = event.data;
  if (message.type === 'state') {
    state = message.state;
    locale = message.locale || 'en';
    t = strings[locale] || strings.en;
    if (!document.querySelector('.advanced-fields').children.length) { localize(); addAdvancedFields(); } else localize();
    render();
    if (message.result) toast(message.result);
  } else if (message.type === 'plan') {
    pendingPlan = { ...message.payload, plan_hash: message.plan.plan_hash, impact: message.plan.impact };
    document.getElementById('planResult').textContent = JSON.stringify(message.plan, null, 2);
    document.getElementById('planBox').classList.remove('hidden');
  } else if (message.type === 'path') {
    document.querySelectorAll(`[name="${message.target}"]`).forEach((element) => { element.value = message.value; });
  } else if (message.type === 'result') toast(message.result);
});

send('ready');
