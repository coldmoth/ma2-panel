/* Recovery reads status by ID; it never resends a command. */
var showFileUI = {operation: null, error: '', working: false, version: 0, timer: null};
var SHOW_FILE_KEY = 'ma2-show-file-operation';
function showFilesPaint() { showFileUI.version++; render(); }
function showFilesRemember(id) { try { sessionStorage.setItem(SHOW_FILE_KEY, id); } catch (_) {} }
async function showFilesRequest(path, body, raw) {
  var options = body === undefined ? {cache: 'no-store'} : {
    method: 'POST', headers: {'X-Show-Files': '1'}, body: raw ? body : JSON.stringify(body)};
  if (body !== undefined && !raw) options.headers['Content-Type'] = 'application/json';
  var response = await fetch('/api/show-files' + path, options);
  var result = await response.json();
  if (!response.ok || !result.ok) throw new Error(result.err || 'Ошибка обмена файлом шоу');
  return result;
}
function showFilesPoll() {
  clearTimeout(showFileUI.timer);
  var op = showFileUI.operation;
  if (op && ['queued', 'backup', 'saving', 'checking', 'loading'].indexOf(op.state) >= 0) {
    showFileUI.timer = setTimeout(showFilesRefresh, 750);
  }
}
async function showFilesRefresh() {
  var op = showFileUI.operation;
  if (!op) return;
  try {
    var result = await showFilesRequest('/' + encodeURIComponent(op.id));
    if (!showFileUI.operation || showFileUI.operation.id !== op.id) return;
    showFileUI.operation = result; showFileUI.error = '';
    showFileUI.working = ['queued', 'backup', 'saving', 'checking', 'loading'].indexOf(result.state) >= 0;
    showFilesPoll();
  } catch (error) {
    showFileUI.error = 'Результат неизвестен: ' + error.message + '. Команды не повторены. Проверьте связь и результат на MA2.';
    showFileUI.working = false;
  }
  showFilesPaint();
}
async function showFilesConfirm(offer) {
  var text;
  if (offer.kind === 'load') text = 'Загрузить файл «' + offer.original + '» в MA2 как «' + offer.name + '»?\n' +
    'Несохранённые изменения текущего шоу пропадут. Существующие файлы не перезаписываются.\n' +
    'Проверена целостность gzip; формат и совместимость версии проверяет MA2.';
  else if (offer.kind === 'save') text = 'Сохранить текущее шоу «' + offer.name + '» поверх его файла и подготовить скачивание?\n' +
    'Прежний файл будет отдельно скопирован в backups. Не переключайте шоу и не сохраняйте его на MA2 или из другой программы до окончания операции.';
  else text = 'Скачать сохранённую версию «' + offer.name + '»?\nНесохранённые изменения MA2 не входят в этот файл. Запись на пульте не выполняется.';
  if (!confirm(text)) { showFileUI.error = 'Действие отменено. Команда MA2 не отправлена.'; return; }
  showFilesRemember(offer.id);
  try {
    showFileUI.operation = await showFilesRequest('/' + offer.id + '/confirm', {
      confirm_name: offer.name, ack_unsaved: offer.kind === 'load', ack_overwrite: offer.kind === 'save'});
    showFileUI.working = true; showFilesPoll();
  } catch (error) {
    showFileUI.error = 'Результат неизвестен: ' + error.message + '. Нажмите «Проверить результат»; команды не повторяются.';
  }
}
async function showFilesPrepare(kind) {
  if (showFileUI.working) return;
  showFileUI.working = true; showFileUI.error = ''; showFilesPaint();
  try {
    var offer = await showFilesRequest('/prepare', {kind: kind});
    showFileUI.operation = offer;
    await showFilesConfirm(offer);
  } catch (error) { showFileUI.error = error.message; }
  showFileUI.working = !!(showFileUI.operation && ['queued', 'backup', 'saving', 'checking', 'loading'].indexOf(showFileUI.operation.state) >= 0);
  showFilesPaint();
}
async function showFilesUpload(file) {
  if (!file || showFileUI.working) return;
  if (!/\.show\.gz$/i.test(file.name) || !file.size || file.size > 512 * 1024 * 1024) {
    showFileUI.error = 'Выберите непустой .show.gz до 512 МиБ'; showFilesPaint(); return;
  }
  showFileUI.working = true; showFileUI.error = ''; showFileUI.operation = null;
  showFilesPaint();
  try {
    var offer = await showFilesRequest('/upload?name=' + encodeURIComponent(file.name), file, true);
    showFileUI.operation = offer;
    await showFilesConfirm(offer);
  } catch (error) { showFileUI.error = 'Передача файла не подтверждена: ' + error.message + '. Загрузка MA2 автоматически не запускается.'; }
  showFileUI.working = !!(showFileUI.operation && ['queued', 'backup', 'saving', 'checking', 'loading'].indexOf(showFileUI.operation.state) >= 0);
  showFilesPaint();
}
function showFilesCard() {
  var op = showFileUI.operation, disabled = showFileUI.working || !connected();
  var stages = {confirm: 'Действие ещё не подтверждено', queued: 'Операция принята', backup: 'Резервная копия',
    saving: 'Сохранение MA2', checking: 'Проверка файла', loading: 'Загрузка MA2', ready: 'Файл готов к скачиванию',
    done: 'Загрузка подтверждена MA2', failed: 'Операция не выполнена', unknown: 'Результат неизвестен'};
  return h('section', {class: 'card', id: 'show-files-card'}, h('h2', {}, 'Файлы шоу на вашем устройстве'),
    h('p', {class: 'note'}, 'Настоящие файлы MA2 (.show.gz). Для локальной onPC; каталог shows задаётся в настройках на основном ПК.'),
    h('div', {class: 'row'},
      h('label', {class: 'btn', 'aria-disabled': disabled || !safe('allow_show_load') ? 'true' : 'false'}, 'Загрузить файл шоу', h('input', {type: 'file', accept: '.show.gz',
        'aria-label': 'Загрузить файл шоу', disabled: disabled || !safe('allow_show_load'),
        style: {display: 'none'}, onchange: function (e) { showFilesUpload(e.target.files[0]); }})),
      h('button', {class: 'btn', type: 'button', disabled: disabled, onclick: function () { showFilesPrepare('download'); }}, 'Скачать шоу'),
      h('button', {class: 'btn', type: 'button', disabled: disabled || !safe('allow_show_save'), onclick: function () { showFilesPrepare('save'); }}, 'Сохранить текущее и скачать')),
    h('p', {class: 'note'}, '«Скачать шоу» берёт сохранённую версию. Для последних изменений выберите сохранение с подтверждением перезаписи.'),
    showFileUI.working && !op ? h('p', {role: 'status'}, 'Передаю и проверяю файл…') : null,
    op ? h('div', {class: 'note', role: 'status', 'aria-live': 'polite', style: {'overflow-wrap': 'anywhere'}},
      h('p', {}, (stages[op.state] || op.state) + ': «' + op.name + '»'),
      op.size ? h('p', {}, (op.size / 1024 / 1024).toFixed(2) + ' МиБ' + (op.mtime ? ' · файл от ' + new Date(op.mtime * 1000).toLocaleString() : '')) : null,
      op.reason ? h('p', {class: op.state === 'failed' || op.state === 'unknown' ? 'warn' : 'note'}, op.reason) : null,
      op.state === 'ready' ? h('a', {class: 'btn primary', href: '/api/show-files/' + op.id + '/download', download: op.name + '.show.gz'}, 'Скачать файл .show.gz') : null,
      h('button', {class: 'btn small', type: 'button', onclick: showFilesRefresh}, 'Проверить результат')) : null,
    showFileUI.error ? h('p', {class: 'warn', role: 'alert'}, showFileUI.error) : null);
}
try {
  var showFileSavedId = sessionStorage.getItem(SHOW_FILE_KEY);
  if (showFileSavedId) { showFileUI.operation = {id: showFileSavedId, state: 'unknown', name: 'последняя операция'}; showFilesRefresh(); }
} catch (_) {}
