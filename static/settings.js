'use strict';
const el = id => document.getElementById(id);
const featureNames = {dim: 'Яркость', color: 'Цвет', move: 'Движение', zoom: 'Зум', focus: 'Фокус', strobe: 'Стробоскоп', scenes: 'Сцены', store: 'Запись'};
let original = {};
let savedPort = location.port || '80';
let passwordTouched = false;
function status(text, bad = false) { el('status').textContent = text; el('status').className = bad ? 'bad' : ''; }
function saved(text, bad = false) { el('save-status').textContent = text; el('save-status').className = 'savestatus ' + (bad ? 'bad' : 'ok'); }
function clearErrors() {
  document.querySelectorAll('.sx .err').forEach(e => { e.textContent = ''; });
  document.querySelectorAll('.sx .invalid').forEach(e => e.classList.remove('invalid'));
}
// "Неверные настройки: bind: требуется IPv4-адрес" -> the message goes under the field named in front of the second colon.
const FIELD_OF = {bind: 'bind', port: 'port', 'ma2.port': 'ma2-port', rate_hz: 'rate_hz', poll_seconds: 'poll_seconds', dmx_seconds: 'dmx_seconds', timeout: 'ma2-timeout',
  'ma2.timeout': 'ma2-timeout', 'safety.allowed_fixtures': 'allowed_fixtures', attrs: 'attrs'};
function fieldError(message) {
  const m = /^(?:Неверные настройки:\s*)?([\w.]+):\s*(.*)$/s.exec(message);
  if (!m) return false;
  let id = FIELD_OF[m[1]];
  if (!id && /^ma2\.\w+_regex$/.test(m[1])) id = 'ma2-' + m[1].slice(4);
  if (!id && /^ma2\.\w+$/.test(m[1])) id = 'ma2-' + m[1].slice(4);
  if (!id || !el('err-' + id)) return false;
  el('err-' + id).textContent = m[2]; el(id).classList.add('invalid'); el(id).scrollIntoView({block: 'center', behavior: 'smooth'});
  return true;
}
function warning() { el('full-warning').hidden = el('mode').value !== 'full'; }
function csv(id) { return el(id).value.split(',').map(v => v.trim()).filter(Boolean); }
function fill(data) {
  original = data.settings;
  const ma2 = {...data.defaults.ma2, timeout: 2, prompt_regex: '', login_ok_regex: '', exec_empty_regex: '(?i)no objects? found|nothing found', ...original.ma2};
  const safety = {...data.defaults.safety, ...original.safety};
  Object.keys(ma2).forEach(key => {
    const input = el('ma2-' + key); if (!input) return;
    if (input.type === 'checkbox') input.checked = ma2[key]; else input.value = ma2[key];
  });
  const panel = {bind: '127.0.0.1', port: 8080, rate_hz: 5, poll_seconds: 0, dmx_seconds: 2, ...original};
  ['bind', 'port', 'rate_hz', 'poll_seconds', 'dmx_seconds'].forEach(key => { el(key).value = panel[key]; });
  el('mode').value = safety.mode;
  ['allowed_fixtures', 'allowed_scenes', 'store_execs'].forEach(key => { el(key).value = safety[key].join(', '); });
  ['allow_master', 'allow_page_change', 'allow_fixture_read', 'allow_highlight', 'allow_show_load', 'allow_show_save', 'allow_group_store', 'allow_patch', 'allow_rdm'].forEach(key => { el(key).checked = safety[key]; });
  el('features').replaceChildren();
  Object.entries(featureNames).forEach(([key, name]) => {
    const value = (original.features || {})[key] ?? true;
    const row = document.createElement('div'); row.className = 'feat';
    const label = document.createElement('label'); label.className = 'opt';
    const check = document.createElement('input'); check.type = 'checkbox'; check.id = 'feature-' + key; check.checked = value === true;
    const text = document.createElement('span'); text.className = 't'; text.textContent = name;
    label.append(check, text);
    const reasonLabel = document.createElement('label'); reasonLabel.className = 'fld';
    const caption = document.createElement('span'); caption.className = 'lbl'; caption.textContent = 'Причина блокировки (если функция выключена)';
    const reason = document.createElement('input'); reason.id = 'reason-' + key; reason.value = typeof value === 'string' ? value : '';
    reasonLabel.append(caption, reason); row.append(label, reasonLabel); el('features').append(row);
  });
  el('attrs').value = JSON.stringify(original.attrs || {}, null, 2);
  el('config-attrs').textContent = JSON.stringify(data.config_attrs, null, 2);
  el('path').textContent = data.path;
  el('password-state').textContent = data.password_set ? 'пароль задан' : 'пароль не задан';
  el('settings-form').hidden = false; warning(); status('');
}
async function load() {
  try {
    const response = await fetch('/api/settings');
    if (response.status === 403) { status('Настройки меняются только на самом ПК с мостом: откройте http://localhost:8080/settings.html там', true); return; }
    if (!response.ok) throw new Error('Не удалось загрузить настройки');
    fill(await response.json());
  } catch (error) { status(error.message, true); }
}
el('mode').addEventListener('change', warning);
el('password').addEventListener('input', () => { passwordTouched = true; });
el('settings-form').addEventListener('submit', async event => {
  event.preventDefault(); el('save').disabled = true; el('restart').hidden = true; clearErrors(); saved('Сохраняю…');
  try {
    // Clone every existing key, including nested fields the form does not edit.
    const settings = structuredClone(original);
    settings.ma2 = {...settings.ma2}; settings.safety = {...settings.safety}; settings.features = {...settings.features};
    ['host', 'user', 'shows_dir', 'prompt_regex', 'login_ok_regex', 'exec_empty_regex'].forEach(key => { settings.ma2[key] = el('ma2-' + key).value; });
    ['port', 'timeout'].forEach(key => { settings.ma2[key] = Number(el('ma2-' + key).value); });
    settings.ma2.require_prompt = el('ma2-require_prompt').checked;
    settings.bind = el('bind').value.trim();
    ['port', 'rate_hz', 'poll_seconds', 'dmx_seconds'].forEach(key => { settings[key] = Number(el(key).value); });
    settings.safety.mode = el('mode').value;
    const ids = csv('allowed_fixtures');
    if (ids.some(id => !/^\d+$/.test(id))) { el('err-allowed_fixtures').textContent = 'Номера приборов — целые числа через запятую'; el('allowed_fixtures').classList.add('invalid'); throw new Error('Не сохранено: исправьте поле «Разрешённые приборы»'); }
    settings.safety.allowed_fixtures = ids.map(Number);
    ['allowed_scenes', 'store_execs'].forEach(key => { settings.safety[key] = csv(key); });
    ['allow_master', 'allow_page_change', 'allow_fixture_read', 'allow_highlight', 'allow_show_load', 'allow_show_save', 'allow_group_store', 'allow_patch', 'allow_rdm'].forEach(key => { settings.safety[key] = el(key).checked; });
    Object.keys(featureNames).forEach(key => { settings.features[key] = el('reason-' + key).value.trim() || el('feature-' + key).checked; });
    try { settings.attrs = JSON.parse(el('attrs').value || '{}'); } catch (error) { el('err-attrs').textContent = 'Неверный JSON — ' + error.message; el('attrs').classList.add('invalid'); throw new Error('Не сохранено: исправьте поле attrs'); }
    const body = {settings, clear_password: el('clear-password').checked};
    if (passwordTouched && el('password').value) body.password = el('password').value;
    const response = await fetch('/api/settings', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.err || 'Не удалось сохранить настройки');
    original = settings; savedPort = String(settings.port);
    if (body.clear_password || 'password' in body) el('password-state').textContent = body.clear_password ? 'пароль не задан' : 'пароль задан';
    el('password').value = ''; passwordTouched = false; el('clear-password').checked = false;
    saved('Сохранено в ' + new Date().toLocaleTimeString() + '. Пульт не затронут. Нажмите «Перезапустить мост», чтобы применить.'); el('restart').hidden = false; el('restart').disabled = false;
  } catch (error) { fieldError(error.message); saved(error.message, true); }
  finally { el('save').disabled = false; }
});
el('restart').addEventListener('click', async () => {
  el('restart').disabled = true;
  try {
    const response = await fetch('/api/restart', {method: 'POST', headers: {'X-Stop': '1'}});
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.err || 'Не удалось перезапустить мост');
    saved('Мост перезапускается…');
    el('save').disabled = true;
    const target = new URL(location.href); target.port = savedPort; target.pathname = '/'; target.search = ''; target.hash = '';
    const sameOrigin = target.origin === location.origin;
    // Allow the old process to stop before checking the new one.
    setTimeout(async function poll() {
      try {
        const response = await fetch(target.href, {cache: 'no-store', mode: sameOrigin ? 'same-origin' : 'no-cors', signal: AbortSignal.timeout(4000)});
        if (sameOrigin && !response.ok) throw new Error('Мост ещё запускается');
        saved('Мост перезапущен.'); el('restart').hidden = true;
        if (sameOrigin) { el('save').disabled = false; await load(); saved('Мост перезапущен, настройки загружены заново.'); }
        else { const link = document.createElement('a'); link.href = new URL('settings.html', target).href; link.textContent = 'Открыть настройки на новом порту'; el('save-status').append(' ', link); }
      } catch (error) { setTimeout(poll, 2000); }
    }, 2500);
  } catch (error) { saved(error.message, true); el('restart').disabled = false; }
});
load();

let manualImport = null;
let manualImportBusy = false;
let importChoicesPanel = null;
function importElement(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function importComplete() {
  if (!manualImport) return false;
  const used = [];
  return manualImport.ambiguous.length > 0 && manualImport.ambiguous.every(item => {
    if (!Object.prototype.hasOwnProperty.call(manualImport.choices, item.new_id)) return false;
    const old = manualImport.choices[item.new_id];
    if (old === null) return true;
    if (used.includes(old) || !item.candidates.some(c => c.old_id === old)) return false;
    used.push(old);
    return true;
  });
}
function renderImportChoices() {
  if (!importChoicesPanel) {
    importChoicesPanel = importElement('div');
    el('import-file').parentNode.appendChild(importChoicesPanel);
  }
  importChoicesPanel.textContent = '';
  if (!manualImport) return;
  importChoicesPanel.appendChild(importElement('p', 'Неоднозначная перепривязка. План пока не изменён. Выберите соответствие для каждого прибора или оставьте его новым.', 'warnbox'));
  const choices = manualImport.choices;
  manualImport.ambiguous.forEach(item => {
    const card = importElement('div', undefined, 'importbox');
    card.appendChild(importElement('p', `Новый прибор #${item.new_id}: ${item.label}`));
    const row = importElement('div', undefined, 'opts');
    function button(text, old, disabled) {
      const selected = Object.prototype.hasOwnProperty.call(choices, item.new_id) && choices[item.new_id] === old;
      const node = importElement('button', text, 'btn' + (selected ? ' primary' : ''));
      node.type = 'button'; node.disabled = disabled || manualImportBusy;
      node.setAttribute('aria-pressed', selected ? 'true' : 'false');
      node.addEventListener('click', () => { choices[item.new_id] = old; renderImportChoices(); });
      row.appendChild(node);
    }
    item.candidates.forEach(candidate => button(`Объединить с #${candidate.old_id} (${candidate.label})`, candidate.old_id,
      Object.keys(choices).some(key => key !== String(item.new_id) && choices[key] === candidate.old_id)));
    button('Оставить новый', null, false);
    card.appendChild(row); importChoicesPanel.appendChild(card);
  });
  const apply = importElement('button', 'Применить выбор', 'btn primary');
  apply.type = 'button'; apply.disabled = !importComplete() || manualImportBusy;
  apply.addEventListener('click', async () => {
    if (manualImportBusy || !importComplete()) return;
    const body = {request_token: manualImport.request_token, choices: manualImport.choices};
    manualImportBusy = true;
    renderImportChoices();
    status('Применяю выбранные соответствия…');
    try {
      const response = await fetch('/api/fixtures/import_confirm', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.err || 'Импорт не подтверждён');
      importResult(result);
    } catch (error) { status('Не удалось подтвердить импорт: ' + error.message + '. Проверьте план перед повторным импортом.', true); }
    finally {
      manualImport = null; manualImportBusy = false;
      el('import-file').disabled = false; renderImportChoices();
    }
  });
  importChoicesPanel.appendChild(apply);
  const cancel = importElement('button', 'Отменить импорт', 'btn');
  cancel.type = 'button'; cancel.disabled = manualImportBusy;
  cancel.addEventListener('click', () => {
    manualImport = null; el('import-file').disabled = false;
    renderImportChoices(); status('Импорт отменён, план не изменён');
  });
  importChoicesPanel.appendChild(cancel);
}
function importResult(result) {
  status(`Добавлено ${result.added}, пропало ${result.missing}, всего ${result.total}` +
    ((result.no_id || []).length ? '. Без Fixture ID: ' + result.no_id.join(', ') : ''));
}
el('import-file').addEventListener('click', async () => {
  if (manualImportBusy || manualImport) return;
  const file = el('fixture-file').files[0];
  if (!file) { status('Выберите XML-файл', true); return; }
  manualImportBusy = true;
  el('import-file').disabled = true;
  try {
    const response = await fetch('/api/fixtures/import_file', {method: 'POST', body: await file.text()});
    const result = await response.json();
    if (Array.isArray(result.ambiguous) && result.ambiguous.length && result.request_token) {
      manualImport = {ambiguous: result.ambiguous, request_token: result.request_token, choices: {}};
      status('Импорт ожидает вашего выбора; план пока не изменён');
    } else {
      if (!response.ok || !result.ok) throw new Error(result.err || 'Импорт не удался');
      importResult(result);
    }
  } catch (error) { status(error.message, true); }
  finally {
    manualImportBusy = false;
    el('import-file').disabled = !!manualImport;
    renderImportChoices();
  }
});
