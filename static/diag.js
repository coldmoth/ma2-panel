'use strict';
const LINK_TEXT = {down: 'Нет соединения с пультом', tcp: 'Соединение установлено, вход ещё не выполнен',
  login_failed: 'Ошибка входа в пульт (пользователь или пароль)', manual_off: 'Связь с пультом разорвана вручную',
  login_unknown: 'Вход не подтверждён: ответ пульта не распознан (см. Диагностику)', logged_in: 'Вход подтверждён (ListVar вернул пользователя)'};
const RESULT_TEXT = {sent: 'отправлена, пульт ответил без ошибки (это не подтверждает, что свет изменился)',
  error: 'ОШИБКА пульта', unknown: 'результат неизвестен: пульт не ответил вовремя, повторно не отправлена', not_sent: 'не отправлена'};
const el = id => document.getElementById(id);
function replyList(id, items) {
  el(id).replaceChildren();
  items.forEach(item => {
    const title = document.createElement('p');
    title.textContent = (item.t ? item.t + ' · ' : '') + item.cmd + ' · ' +
      (item.status ? (RESULT_TEXT[item.status] || item.status) : item.ok ? 'ответ без ошибки' : 'ошибка');
    const pre = document.createElement('pre'); pre.textContent = item.reply;
    el(id).append(title, pre);
  });
}
async function refresh() {
  try {
    const response = await fetch('/api/diag');
    if (!response.ok) throw new Error('Не удалось получить диагностику');
    const data = await response.json();
    el('connection').textContent = LINK_TEXT[data.ma2] || data.ma2;
    const v = data.login_vars || {};
    el('details').textContent = `Версия панели ${data.version} · режим ${data.mode} · ${data.host} · пользователь в настройках ${data.user}` +
      (v.USER ? ` · MA2 ${v.VERSION || '?'}: вошёл ${v.USER}, права ${v.USERRIGHTS || '?'}, профиль ${v.USERPROFILE || '?'}, шоу ${v.SHOWFILE || '?'}` : '');
    el('last').textContent = data.last ? `${data.last.cmd}\n${RESULT_TEXT[data.last.status] || data.last.status}\n${data.last.text || ''}` : 'Ещё не отправлялась';
    el('login').textContent = data.login_reply || 'Ответ входа ещё не получен';
    el('errors').replaceChildren();
    data.errors.forEach(error => {
      const li = document.createElement('li');
      const msg = document.createElement('p'); msg.textContent = `${error.t} · ${error.level} · ${error.msg}`;
      const hint = document.createElement('p'); hint.className = 'muted'; hint.textContent = error.hint;
      li.append(msg, hint); el('errors').append(li);
    });
    el('export-info').textContent = exportText(data.export);
    replyList('raw', data.raw.slice().reverse());
    el('refresh-error').textContent = '';
  } catch (error) { el('refresh-error').textContent = 'Нет связи с мостом. Повторная проверка через 5 секунд.'; }
}
function exportText(x) {
  if (!x) return 'нет данных';
  const lines = [`Чтение приборов разрешено: ${x.allow_fixture_read}`, `Команда: ${x.export_cmd}`, `Папка экспорта: ${x.export_dir}`,
    `Папки поиска: ${(x.export_search || []).join(' | ') || '—'}`, `Ожидание: ${x.export_wait} с`, `Путь установки MA2 ($PATH): ${x.console_path || 'не прочитан'}`];
  (x.folders || []).forEach(f => lines.push(f.exists ? `Папка ${f.dir}: файлов ${f.count}; новейшие: ${f.newest.slice(0, 5).map(n => n.name + ' ' + n.mtime).join(', ') || 'нет'}` : `Папка ${f.dir}: НЕТ`));
  const t = x.last_attempt;
  lines.push(t ? `Последняя попытка ${t.t}: ожидался ${t.expected_file}; ответ MA2: ${t.reply || '—'}; ` +
    (t.file ? `файл найден ${t.file.path} (${t.file.size} байт)` : 'файл не найден') + (t.parse_error ? `; ошибка разбора: ${t.parse_error}` : '') + (t.error ? `; итог: ${t.error}` : '; итог: успех')
    : 'Попыток получить оборудование ещё не было');
  lines.push(x.active_probe ? `Проверка экспорта ${x.active_probe.t}: ${x.active_probe.results.map(r => r.key + ' → новых файлов ' + r.new_files.length).join(', ')}` : 'Проверка экспорта ещё не запускалась');
  const d = x.dmx_read;
  if (d) {
    lines.push(`DMX-опрос: ${d.enabled ? 'включён' : 'выключен'} · интервал ${d.dmx_seconds} с · вход MA2 ${d.connected ? 'подтверждён' : 'не подтверждён'}${d.mock ? ' · MOCK' : ''}`);
    lines.push(`Приборов с адресами: ${d.patched_fixtures}; действующих типов: ${d.mapped_types}/${d.types}; актуальных приборов: ${d.actual_fixtures}; неизвестных: ${d.unknown_fixtures}`);
    lines.push(`Последнее успешное чтение: ${d.last_success || 'нет'}; этап: ${d.stage}; ${d.summary || d.reason || '—'}`);
    lines.push(`Полный круг: ${d.cycle_seconds == null ? 'ещё не измерен' : d.cycle_seconds.toFixed(2) + ' с'}; TTL ${d.ttl_seconds} с${d.capacity_exceeded ? ' · опрос медленнее TTL, часть выхода неизвестна' : ''}`);
    if (d.span) lines.push(`Чтение DMX ${d.t}: адреса ${d.span[0]}–${d.span[0] + d.span[1] - 1}, получено значений ${d.values}; ответ: ${d.reply || '—'}`);
  } else lines.push('Чтение DMX ещё не выполнялось');
  Object.entries(x.type_reads || {}).forEach(([no, t]) => lines.push(`Тип ${no} ${t.t}: ${t.error ? 'ошибка: ' + t.error : 'каналы ' + JSON.stringify(t.spec || {})}; файл ${t.file || '—'}; ответ: ${t.reply || '—'}`));
  return lines.join('\n');
}
function showExport(data) {
  el('export-results').replaceChildren();
  (data.results || []).forEach(r => {
    const title = document.createElement('p'); title.textContent = `${r.cmd} · ${r.ok ? 'ответ без ошибки' : 'ошибка или отказ'} · новых файлов: ${r.new_files.length}`;
    const pre = document.createElement('pre'); pre.textContent = r.reply + (r.new_files.length ? '\n' + r.new_files.map(f => `${f.path} (${f.size} байт, ${f.mtime})`).join('\n') : '');
    el('export-results').append(title, pre);
  });
}
async function runRead() {
  const response = await fetch('/api/probe', {method: 'POST'});
  const data = await response.json();
  if (!response.ok || !data.ok) throw new Error(data.err || 'Не удалось прочитать списки пульта');
  replyList('probe-results', data.results);
}
async function runLink() {
  const response = await fetch('/api/diag/link_test', {method: 'POST'});
  const data = await response.json();
  if (!response.ok || !data.ok) throw new Error(data.err || 'Не удалось проверить соединение');
  el('link-results').textContent = JSON.stringify({состояние: data.state, цель: data.target, попытки: data.attempts, пробное_соединение: data.bare_connect, netstat: data.netstat, python: data.python_processes}, null, 1);
}
async function runExport() {
  const response = await fetch('/api/diag/export_probe', {method: 'POST'});
  const data = await response.json();
  if (!response.ok || !data.ok) throw new Error(data.err || 'Не удалось проверить экспорт');
  showExport(data);
}
async function guarded(button, steps, done) {
  document.querySelectorAll('#link-test, #probe, #export-probe, #all').forEach(b => { b.disabled = true; });
  const failed = [];
  for (const [name, step] of steps) {
    el('probe-status').textContent = name + '…';
    try { await step(); } catch (error) { failed.push(name + ': ' + error.message); }
  }
  el('probe-status').textContent = failed.length ? 'Не всё удалось — ' + failed.join(' · ') : 'Готово.';
  document.querySelectorAll('#link-test, #probe, #export-probe, #all').forEach(b => { b.disabled = false; });
  refresh(); if (done) done();
}
el('link-test').addEventListener('click', e => guarded(e.currentTarget, [['Проверяю соединение', runLink]]));
el('probe').addEventListener('click', e => guarded(e.currentTarget, [['Читаю списки', runRead]]));
el('export-probe').addEventListener('click', e => guarded(e.currentTarget, [['Проверяю экспорт', runExport]]));
// A failed step never blocks the package: whatever was collected is downloaded anyway.
el('all').addEventListener('click', e => guarded(e.currentTarget, [['Проверяю соединение', runLink], ['Читаю списки', runRead], ['Проверяю экспорт', runExport]], () => { location.href = '/api/diag.zip'; }));
refresh(); setInterval(refresh, 5000);
