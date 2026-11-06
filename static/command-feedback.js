/* Request processing and independent MA2 readback are deliberately separate. */
function commandOperationName(action, config) {
  var names = {scene_go: 'Запуск сцены', scene_off: 'Выключение сцены', blackout: 'Погасить свет',
    master: 'Общая яркость', dim: 'Яркость', color: 'Цвет', move: 'Положение', jog: 'Шаг движения',
    aim: 'Положение', nudge: 'Шаг параметра', zoom: 'Зум', focus: 'Фокус', strobe: 'Стробоскоп',
    select_fixtures: 'Выбор приборов', select_group: 'Выбор группы', clear: 'Снять выбор',
    fixture_flag: 'Настройки прибора', layout_save: 'Расстановка', hall_save: 'Размеры зала',
    group_save: 'Сохранение группы', group_delete: 'Удаление группы', preset_save: 'Сохранение позиции',
    preset_go: 'Позиция', preset_delete: 'Удаление позиции', fixtures_fetch: 'Чтение приборов',
    shows_list: 'Список шоу', show_load: 'Загрузка шоу', show_save: 'Сохранение шоу',
    scene_create: 'Запись сцены', scene_rename: 'Имя сцены', scene_delete: 'Удаление сцены',
    ma2_read: 'Чтение MA2', ma2_import: 'Импорт MA2', scenes_import: 'Импорт сцен',
    halt: 'Стоп передачи', resume: 'Возобновление передачи', link_drop: 'Отключение связи', link_connect: 'Подключение'};
  var label = names[action.a] || 'Операция';
  var scene = action.a === 'scene_go' || action.a === 'scene_off'
    ? ((config || {}).scenes || []).filter(function (s) { return s.id === action.id; })[0] : null;
  return label + (scene ? ' «' + (scene.label || scene.id) + '»' : '');
}

function commandFeedback(message) {
  var evidence = Array.isArray(message.command_evidence) ? message.command_evidence : [];
  var text, kind = 'info', sticky = false;
  if (message.outcome === 'unknown' || evidence.indexOf('unknown') >= 0) {
    text = 'Результат неизвестен. Автоматического повтора нет.'; kind = 'warning'; sticky = true;
  } else if (message.outcome === 'partial' || evidence.indexOf('sent') >= 0 &&
      (evidence.indexOf('error') >= 0 || evidence.indexOf('not_sent') >= 0)) {
    text = 'Завершена только часть обработки. Итог MA2 не подтверждён. Автоматического повтора нет.'; kind = 'warning'; sticky = true;
  } else if (evidence.length && evidence.every(function (s) { return s === 'not_sent'; })) {
    text = 'Команда не отправлена.'; kind = 'error'; sticky = true;
  } else if (evidence.indexOf('error') >= 0) {
    text = 'Ошибка в ответе MA2.'; kind = 'error'; sticky = true;
  } else if (!evidence.length && message.outcome === 'failed' &&
      ['master', 'dim', 'color', 'move', 'jog', 'zoom', 'focus', 'strobe'].indexOf(message.a) >= 0 &&
      message.err === 'заменено более новым значением до отправки') {
    // An explicit bridge cancellation is normal for latest-value sliders, not an error.
    return {text: 'Прежнее значение не отправлено: заменено более новым.', kind: 'info', sticky: false};
  } else if (!message.ok || message.outcome === 'failed') {
    text = 'Запрос отклонён.'; kind = 'error'; sticky = true;
  } else if (evidence.length && evidence.every(function (s) { return s === 'sent'; })) {
    text = 'Команда отправлена; MA2 ответила без ошибки. Изменение состояния не подтверждено.';
  } else {
    text = 'Обработка завершена. Изменение состояния MA2 не подтверждено.';
  }
  return {text: text + (message.err ? ' ' + message.err : ''), kind: kind, sticky: sticky};
}

function commandWaiting(request, operations, now) {
  if (!request.sent) return {text: 'В очереди панели · запрос ещё не отправлен', kind: 'waiting'};
  if (now - request.sentAt >= request.waitMs) {
    return {text: 'Ответ задерживается · результат неизвестен. Автоматического повтора нет.', kind: 'warning'};
  }
  var registered = (operations || []).filter(function (op) { return op.request_id === request.request_id; })[0];
  return {text: registered ? 'Запрос зарегистрирован · ' +
    ({queued: 'в очереди моста', fade: 'переход моста', transition: 'переход моста'}[registered.stage] || 'мост обрабатывает') :
    'Отправлено из браузера · ждём ответ моста', kind: 'waiting'};
}

function commandWaitMs(action) {
  // Only a warning about response time, never a cancellation or a retry deadline.
  return Math.max(action.a === 'show_load' ? 150000 : 30000, (Number(action.fade) || 0) * 1000 + 30000);
}
