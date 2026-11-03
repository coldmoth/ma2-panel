'use strict';
(() => {
  const el = id => document.getElementById(id);
  let loaded = false, online = false, saving = false, polling = false;
  let signature = '', instance = null, restarting = false, initialLan = false;
  const local = ['localhost', '127.0.0.1', '[::1]', '::1'].includes(location.hostname);
  const enable = () => { el('setup-save').disabled = !loaded || !online || saving || restarting; };
  async function request(url, options = {}) {
    const response = await fetch(url, {cache: 'no-store', signal: AbortSignal.timeout(5000), ...options});
    if (response.status === 403) throw Error('Мастер доступен только на основном ПК. Откройте его через http://localhost:' + (location.port || '8080') + '/setup.html');
    const data = await response.json();
    if (!response.ok || data.ok === false) throw Error(data.err || 'Не удалось выполнить запрос.');
    return data;
  }
  async function load() {
    const data = await request('/api/settings');
    const m = data.settings.ma2 || {};
    el('setup-host').value = m.host || '127.0.0.1';
    el('setup-port').value = m.port || 30000;
    el('setup-user').value = m.user || 'Remote';
    initialLan = !['127.0.0.1', 'localhost', '::1'].includes(data.settings.bind || '127.0.0.1');
    el('setup-lan').checked = initialLan;
    el('setup-password-state').textContent = data.password_set ? 'Пароль уже сохранён. Пустое поле оставит его прежним.' : 'Сохранённого пароля нет. Если в MA2 пароль пустой, оставьте поле пустым.';
    el('setup-form').hidden = false;
    loaded = true;
  }
  function addresses(data) {
    const key = JSON.stringify(data.urls);
    if (signature === key) return;
    signature = key;
    el('setup-addresses').replaceChildren();
    for (const url of data.urls) {
      const card = document.createElement('div'); card.className = 'setup-address';
      const link = document.createElement('a'); link.href = url; link.textContent = url;
      const image = document.createElement('img'); image.alt = 'QR-код: ' + url;
      image.src = '/api/setup/qr?address=' + encodeURIComponent(new URL(url).hostname);
      image.addEventListener('error', () => { image.hidden = true; signature = ''; });
      card.append(link, image); el('setup-addresses').append(card);
    }
  }
  async function refresh() {
    if (polling || !local) return;
    polling = true;
    try {
      if (!loaded) await load();
      const data = await request('/api/setup');
      online = true;
      if (restarting && data.instance === instance) {
        el('setup-live').textContent = 'Мост перезапускается…';
        return;
      }
      if (restarting) {
        restarting = false; el('setup-restart').hidden = true;
        el('setup-saved').textContent = 'Мост перезапущен. Ниже показано новое подключение.';
      }
      instance = data.instance;
      el('setup-status').textContent = data.mock ? 'Имитация MA2 — настоящего подключения к пульту нет.' : 'Мост работает. Подготовьте MA2 и проверьте подключение ниже.';
      const m = data.ma2;
      const state = m.halted ? 'Передача остановлена' : m.ready ? 'Вход подтверждён' : m.state === 'login_failed' ? 'Ошибка входа: проверьте пользователя и пароль' : 'Вход не подтверждён: проверьте Telnet, адрес и учётную запись';
      el('setup-live').textContent = (data.mock ? 'Имитация. ' : '') + state + ' · ' + m.host + ':' + m.port + ' · пользователь ' + m.user + (m.profile ? ' · профиль ' + m.profile : '');
      el('setup-network').textContent = !data.lan_enabled ? 'Мост пока доступен только на этом компьютере. Включите доступ по локальной сети и перезапустите мост.' : data.urls.length ? 'Выберите адрес сети роутера света:' : 'Подходящий сетевой адрес пока не найден. Подключите ПК к роутеру света.';
      addresses(data);
    } catch (error) {
      online = false; signature = '';
      el('setup-addresses').replaceChildren();
      el('setup-status').textContent = error.message;
      el('setup-live').textContent = 'Мост недоступен. Прежнее состояние подключения не подтверждено.';
      el('setup-network').textContent = 'Адреса недоступны до восстановления связи с мостом.';
    } finally { polling = false; enable(); }
  }
  el('setup-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (saving || !online || restarting || !el('setup-form').reportValidity()) return;
    saving = true; enable();
    try {
      // Read fresh settings so an unrelated edit in another local page is preserved.
      const data = await request('/api/settings');
      const settings = structuredClone(data.settings);
      settings.ma2 = {...settings.ma2, host: el('setup-host').value.trim(),
        port: Number(el('setup-port').value), user: el('setup-user').value.trim()};
      // An existing explicit interface is preserved unless this checkbox is changed.
      if (el('setup-lan').checked !== initialLan) {
        settings.bind = el('setup-lan').checked ? '0.0.0.0' : '127.0.0.1';
      }
      const body = {settings};
      if (el('setup-password').value) body.password = el('setup-password').value;
      await request('/api/settings', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
      initialLan = el('setup-lan').checked;
      el('setup-password').value = '';
      if ('password' in body) el('setup-password-state').textContent = 'Новый пароль сохранён.';
      el('setup-saved').textContent = 'Настройки сохранены. Для применения перезапустите мост; действующее подключение пока прежнее.';
      el('setup-restart').hidden = false; el('setup-restart').disabled = false;
    } catch (error) { el('setup-saved').textContent = error.message; }
    finally { saving = false; enable(); }
  });
  el('setup-restart').addEventListener('click', async () => {
    if (saving || restarting) return;
    el('setup-restart').disabled = true;
    try {
      await request('/api/restart', {method: 'POST', headers: {'X-Stop': '1'}});
      restarting = true; signature = ''; el('setup-addresses').replaceChildren();
      el('setup-saved').textContent = 'Мост перезапускается. Оставьте окно программы открытым.';
      el('setup-live').textContent = 'Ожидаю новое подключение…';
      enable();
    } catch (error) { el('setup-saved').textContent = error.message; el('setup-restart').disabled = false; }
  });
  if (local) { refresh(); setInterval(refresh, 5000); }
  else { el('setup-status').textContent = 'Откройте мастер на основном ПК через http://localhost:' + (location.port || '8080') + '/setup.html'; }
})();
