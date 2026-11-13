/* Panel core: link to the bridge, shell (rail, top bar, banners) and the Площадка, Сцены, Шоу sections.
   light.js draws Свет, plan.js draws the hall plan and Зал, move.js the Pan/Tilt pad. */
var state = {valuesRevision: -1, master: null, readFreshness: {}, ws: null, ma2: 'down', mock: false, last: null, manual: false, page: null, scenes: {}, config: null, configN: 0,
  shown: {}, live: {}, simulation: {}, dmx: {}, sceneMeta: {}, valuesMeta: {}, tracked: true, selection: [], group: null, halted: false, safety: null, features: {}, highlight: null,
  showLoad: {state: 'idle'}, show: {name: null}, sec: 'scenes', blackoutArm: false, blackoutEpoch: 0,
  fetch: null, ma2read: null, showNames: null, showRaw: [], showLocal: [], showPick: null, saveReply: '', history: []};
// Reconnect restores intent only after fresh fixture identity and bridge-only selection ACK.
var selectionIntent = null;
var selectionSync = null;
var awaitingConfig = true;
function selectionIdentity(cfg, ids) {
  if (!cfg || !ids.length) return null;
  var list = ids.map(function(id) { return (cfg.fixtures || []).filter(function(f) { return f.id === id && !f.missing; })[0]; });
  if (list.some(function(f) { return !f; })) return null;
  return JSON.stringify([cfg.show, cfg.attrs, cfg.dmx_map, list.map(function(f) {
    // Layout/name and movement calibration do not replace the fixture's identity.
    var copy = {}; Object.keys(f).sort().forEach(function(k) { if (['x','y','label','name','rot','icon','flip_pan','flip_tilt','beam'].indexOf(k) < 0) copy[k] = f[k]; }); return copy;
  })]);
}
function rememberSelection() {
  if (state.selection.length) selectionIntent = {ids:state.selection.slice(), group:state.group, show:state.show.name, identity:selectionIdentity(state.config,state.selection)};
  state.selection = []; state.group = null; selectionSync = null;
  awaitingConfig = true;
}
function validateSelectionIntent() {
  if (!selectionIntent || awaitingConfig || !bridgeUp() || !linkReady()) return;
  var intent = selectionIntent; selectionIntent = null;
  if (!intent.show || intent.show !== state.show.name || !intent.identity || intent.identity !== selectionIdentity(state.config,intent.ids) ||
      state.show.name && state.config.show && state.show.name !== state.config.show ||
      intent.ids.some(function(id) { return typeof allowedFixture === 'function' && !allowedFixture(id); })) {
    notice('Выбор снят: шоу или состав приборов изменились. Выберите приборы заново.', 'warning'); return;
  }
  state.selection = intent.ids; state.group = intent.group;
  // This existing action updates the bridge session only; it emits no MA2 lines.
  if (send({a:'select_fixtures',ids:intent.ids.slice()})) selectionSync = requestPrefix + ':' + requestSerial;
  else { selectionIntent = intent; state.selection = []; state.group = null; }
}
var evidenceReceipts = {scenes: {}, values: {}};
var listeners = {};
var pending = {};
var operationFeedback = null;
var configQueue = [];
var configActive = null;
var actionRevision;
var CONFIG_WRITES = ['scene_fade','layout_save','hall_save','fixture_flag','group_save','group_delete','preset_save','preset_delete',
  'beam_home','beam_invert','dmx_map','rdm_link','scene_create','scene_rename','scene_delete','page_save','scenes_import',
  'ma2_import','fixtures_fetch','import_confirm_merge','plan_copy','show_bind','show_open_plan','show_load','patch_apply','undo'];
function captureRevision(fn) {
  var revision = state.config && state.config.revision;
  return function () {
    var before = actionRevision;
    actionRevision = revision;
    try { return fn.apply(this, arguments); } finally { actionRevision = before; }
  };
}
function pumpConfigQueue() {
  if (configActive || !configQueue.length || !bridgeUp()) return;
  var entry = configQueue.shift();
  configActive = entry.action.request_id;
  try {
    state.ws.send(JSON.stringify(entry.action));
    pending[entry.action.request_id].sent = true;
    pending[entry.action.request_id].sentAt = Date.now();
  }
  catch (error) { discardPending(); }
}
var requestSerial = 0;
var requestPrefix = Date.now().toString(36) + Math.random().toString(36).slice(2);
var sliderChannels = {};
var SLIDER_ACTIONS = ['master', 'dim', 'color', 'move', 'jog', 'zoom', 'focus', 'strobe'];
var sceneUI = {query: '', editing: false, masterOpen: false};
var sceneFade = 0;  // persisted by the bridge, shared with the simple panel
var fadeSeconds = 0;  // fade for jumps (quick % buttons, colour swatches, a tap on the wheel); drags never fade
var reconnectTimer = null;
var sectionDisposers = [];
var updaters = [];     // value refreshers of the current section; rebuilt with it
var sectionKey = null;
var latestSelectionRequest = null;
var activeControls = [];
var controlGeneration = 0;
var sectionDeferred = false;
var SECTIONS = {};     // name -> function (el); light.js and plan.js add theirs
var SETUP = ['start', 'hall', 'patch', 'shows'];  // venue preparation; the rest is the live show

function on(type, fn) {
  (listeners[type] || (listeners[type] = [])).push(fn);
  return function () { listeners[type] = listeners[type].filter(function (item) { return item !== fn; }); };
}

/* Tiny DOM builder: h('button', {class: 'btn', onclick: fn}, 'text', child) */
function h(tag, attrs) {
  var el = document.createElement(tag);
  Object.keys(attrs || {}).forEach(function (k) {
    var v = attrs[k];
    if (v === null || v === undefined || v === false) return;
    if (k === 'class') el.className = v;
    else if (k === 'text') el.textContent = v;
    else if (k.slice(0, 2) === 'on') {
      var handler = captureRevision(v);
      el.addEventListener(k.slice(2), function (event) {
        if ((event.type === 'input' || event.type === 'change') && el._controlGeneration !== undefined && el._controlGeneration !== controlGeneration) return;
        return handler.call(el,event);
      });
    }
    else if (k === 'style') Object.keys(v).forEach(function (s) { el.style.setProperty(s, v[s]); });
    else if (k in el && typeof v !== 'string') el[k] = v;
    else el.setAttribute(k, v === true ? '' : v);
  });
  add.apply(null, [el].concat(Array.prototype.slice.call(arguments, 2)));
  if (tag === 'input' && attrs && attrs.type === 'range' || attrs && attrs.role === 'slider') watchControl(el);
  if (tag === 'input' || tag === 'textarea' || tag === 'select') el.addEventListener('blur', catchUpSection);
  return el;
}
function catchUpSection() {
  if (sectionDeferred) setTimeout(function () { render(); }, 0);
}
function watchControl(el) {
  el._controlGeneration = controlGeneration;
  function begin() { el._controlGeneration = controlGeneration; if (activeControls.indexOf(el) < 0) activeControls.push(el); }
  function end() { activeControls = activeControls.filter(function (item) { return item !== el; }); catchUpSection(); }
  el.addEventListener('pointercancel',function(){if (controlActive(el)) cancelTargetControls();});
  ['pointerdown','keydown'].forEach(function (type) { el.addEventListener(type, begin); });
  ['pointerup','pointercancel','lostpointercapture','keyup','blur'].forEach(function (type) { el.addEventListener(type, end); });
}
function controlActive(el) { return activeControls.indexOf(el) >= 0; }
function cancelTargetControls() {
  controlGeneration++;
  Object.keys(sliderChannels).forEach(cancelSlider);
  activeControls = [];
  if (typeof moveStop === 'function') moveStop();
}
function add(el) {
  for (var i = 1; i < arguments.length; i++) {
    var kid = arguments[i];
    if (kid === null || kid === undefined || kid === false) continue;
    if (Array.isArray(kid)) kid.forEach(function (k) { add(el, k); });
    else el.appendChild(typeof kid === 'object' ? kid : document.createTextNode(String(kid)));
  }
}
var ICON = {
  plug: '<path d="M9 2v5M15 2v5M6 7h12v4a6 6 0 0 1-12 0zM12 17v5"/>', download: '<path d="M12 3v12M7 10l5 5 5-5M4 20h16"/>',
  pause: '<path d="M8 5v14M16 5v14"/>', play: '<path d="M7 4l13 8-13 8z"/>', power: '<path d="M12 3v8M6.3 6.3a8 8 0 1 0 11.4 0"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4"/>', check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>', x: '<path d="M6 6l12 12M18 6L6 18"/>',
  alert: '<path d="M12 3l10 18H2zM12 10v5M12 18v.5"/>', file: '<path d="M6 3h8l5 5v13H6zM14 3v5h5"/>', save: '<path d="M5 3h11l3 3v15H5zM8 3v6h8M8 21v-7h8v7"/>',
  refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>', back: '<path d="M15 6l-6 6 6 6"/>', chevron: '<path d="M9 6l6 6-6 6"/>',
  group: '<circle cx="8" cy="9" r="3"/><circle cx="16" cy="9" r="3"/><circle cx="12" cy="16" r="3"/>',
  select: '<path d="m4 3 7 18 2-8 8-2z"/>', hand: '<path d="M8 13V6a2 2 0 0 1 4 0v6M12 10V4a2 2 0 0 1 4 0v8M16 10a2 2 0 0 1 4 0v6a6 6 0 0 1-6 6h-2c-2 0-4-2-5-4l-3-5a2 2 0 0 1 3-2l2 3"/>',
  fit: '<path d="M8 3H3v5M16 3h5v5M21 16v5h-5M3 16v5h5"/>',
  search: '<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',
  light: '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.8.8 1 1.5 1 2.5h6c0-1 .2-1.7 1-2.5A6 6 0 0 0 12 3z"/>'
};
function icon(name, size) {
  var span = document.createElement('span');
  span.style.display = 'inline-flex';
  span.innerHTML = '<svg class="icon" viewBox="0 0 24 24" width="' + (size || 22) + '" height="' + (size || 22) + '" aria-hidden="true">' + (ICON[name] || '') + '</svg>';
  return span;
}

function pageOf(scene) { return parseInt(String(scene.exec).split('.')[0], 10) || 1; }
function bridgeUp() { return !!state.ws && state.ws.readyState === WebSocket.OPEN; }
// Commands go out only after the bridge confirmed the login (ListVar returned the configured user).
function linkReady() { return state.ma2 === 'logged_in'; }
function contextReadable() { return bridgeUp() && linkReady() && !awaitingConfig && !state.halted && !state.showFileActive && !(state.showLoad && state.showLoad.state === 'loading'); }
function connected() { return contextReadable() && !selectionSync && !state.recovering; }
function fixtures() { return (state.config && state.config.fixtures) || []; }
function fixture(id) { return fixtures().filter(function (f) { return f.id === id; })[0] || null; }
// A head: marked by the operator (moves), or Pan/Tilt among the attribute names from MA2. Same rule as commands.can_move.
function canMove(f) {
  var profile = ((state.config || {}).dmx_map || {})[f.type] || {};
  return !f.missing && (f.moves === true || (f.params || []).some(function (p) { return /^(pan|tilt)$/i.test(p); }) ||
    !profile.stale && !profile.unsupported && (profile.has || []).indexOf('pos') >= 0);
}
function hasFixtures() { return fixtures().length > 0; }
function safe(flag) { return !!(state.safety && state.safety[flag]); }

var LINK_TEXT = {down: 'Нет соединения с пультом', tcp: 'Соединение есть, вход ещё не выполнен',
  login_failed: 'Ошибка входа в пульт (пользователь или пароль)', manual_off: 'Связь с пультом разорвана вручную',
  login_unknown: 'Вход не подтверждён: ответ пульта не распознан (Диагностика)', logged_in: 'Вход подтверждён'};
var RESULT_TEXT = {sent: 'отправлена, пульт ответил без ошибки (это не подтверждает, что свет изменился)',
  error: 'ОШИБКА пульта', unknown: 'результат неизвестен: пульт не ответил вовремя, повторно не отправлена', not_sent: 'не отправлена'};
function linkLine() {
  if (!bridgeUp()) return {dot: '', text: 'Нет связи с мостом'};
  if (state.halted && linkReady()) return {dot: 'wait', text: 'Передача остановлена'};
  var short = {logged_in:'Подключено',down:'Нет связи с пультом',tcp:'Подключение…',login_failed:'Ошибка входа',
    login_unknown:'Вход не подтверждён',manual_off:'Связь отключена'};
  if (state.recovering) return {dot:'wait',text:'Восстановление данных MA2'};
  if (state.showFileActive) return {dot:'wait',text:'Передача файла шоу'};
  if (state.showLoad && state.showLoad.state === 'loading') return {dot:'wait',text:'Загрузка шоу'};
  return {dot:state.ma2 === 'logged_in' ? 'on' : state.ma2 === 'down' ? '' : 'wait',text:short[state.ma2] || state.ma2};
}

// Busy is processing, never proof that the desk applied a change.
function send(action, button) {
  var recoveryRead = state.recovering && contextReadable() && ['fixtures_fetch','import_confirm_merge','show_identify'].indexOf(action.a) >= 0;
  if ((!connected() && !recoveryRead) || featureReason(actionFeature(action.a))) return false;
  if (button && button.getAttribute('aria-busy') === 'true') return false;
  // Global Off discards old gestures; other actions retain their ordering with sliders.
  if (action.a === 'blackout') {
    cancelTargetControls();
  } else if (SLIDER_ACTIONS.indexOf(action.a) < 0) flushSliders();
  var revision = actionRevision === undefined ? state.config && state.config.revision : actionRevision;
  if (state.sec === 'hall' && typeof planState !== 'undefined' && planState.editing) revision = planState.revision;
  action = Object.assign({config_revision: revision, blackout_epoch: state.blackoutEpoch}, action, {request_id: requestPrefix + ':' + (++requestSerial)});
  pending[action.request_id] = {a: action.a, request_id: action.request_id, serial: requestSerial,
    label: commandOperationName(action, state.config), sent: false, waitMs: commandWaitMs(action),
    button: button || null, revision: action.config_revision, scene: action.id};
  if (['select_fixtures','select_group','ma2_group_go','clear'].indexOf(action.a) >= 0) latestSelectionRequest = action.request_id;
  operationFeedback = null;
  if (CONFIG_WRITES.indexOf(action.a) >= 0) {
    configQueue.push({action: action});
    pumpConfigQueue();
  } else {
    try {
      state.ws.send(JSON.stringify(action));
      pending[action.request_id].sent = true; pending[action.request_id].sentAt = Date.now();
    } catch (error) {
      delete pending[action.request_id];
      notice('Запрос не отправлен: нет связи с мостом.', 'error', true, commandOperationName(action, state.config));
      renderOperationFeedback();
      return false;
    }
  }
  if (!pending[action.request_id]) return false;
  if (button) { button.setAttribute('aria-busy', 'true'); button.classList.add('waiting'); }
  renderOperationFeedback();
  return true;
}
function sendRaw(action) {  // halt / resume / link: work without a console link
  if (bridgeUp()) {
    action = Object.assign({}, action, {request_id: requestPrefix + ':' + (++requestSerial)});
    pending[action.request_id] = {a: action.a, request_id: action.request_id, serial: requestSerial,
      label: commandOperationName(action, state.config), sent: true, sentAt: Date.now(), waitMs: commandWaitMs(action), button: null};
    operationFeedback = null;
    try { state.ws.send(JSON.stringify(action)); }
    catch (error) {
      delete pending[action.request_id];
      notice('Запрос не отправлен: нет связи с мостом.', 'error', true, commandOperationName(action, state.config));
    }
    renderOperationFeedback();
  }
}
function busy(a) { return Object.keys(pending).some(function (id) { return pending[id].a === a; }); }

function feedback(button, ok, error, operation) {
  if (button) { button.removeAttribute('aria-busy'); button.classList.remove('waiting'); }
  notice(ok ? 'Обработка завершена. Изменение состояния MA2 не подтверждено.' : (error || 'Ошибка команды'), ok ? 'info' : 'error', !ok, operation);
}
function renderOperationFeedback() {
  var el = document.getElementById('operation-status');
  var requests = Object.keys(pending).map(function (id) { return pending[id]; }).filter(function(r) { return ['select_fixtures','select_group','clear'].indexOf(r.a)<0; });
  requests.sort(function (a, b) { return b.serial - a.serial; });
  var current = requests[0], result = current ? commandWaiting(current, state.operations, Date.now()) : operationFeedback;
  var text = result && !result.sticky ? (current ? current.label + ': ' : '') + result.text +
    (requests.length > 1 ? ' · Ожидают: ' + requests.length : '') : '';
  if (el.textContent !== text) el.textContent = text;
  el.className = 'operation-status ' + (result ? result.kind : '');
  el.hidden = !text;
}
function notice(text, kind, sticky, operation, requestId) {
  if (text && ((!kind || kind === 'error') || sticky)) {
    var errors = document.getElementById('errors');
    var row = h('div', {class: 'error-entry ' + (kind || 'error'), title: requestId || ''}, h('span', {}, (operation ? operation + ': ' : '') + text));
    add(row, h('button', {type: 'button', class: 'btn small', 'aria-label': 'Закрыть сообщение: ' + (operation || text), onclick: function () {
      errors.removeChild(row); errors.hidden = !errors.children.length;
    }}, 'Закрыть'));
    add(errors, row); errors.hidden = false;
    return;
  }
  var el = document.getElementById('notice');
  el.textContent = text || '';
  el.className = 'notice ' + (kind || 'error');
  el.hidden = !text;
  clearTimeout(notice.timer);
  if (text && !sticky) notice.timer = setTimeout(function () { el.hidden = true; }, 6000);
}

function actionFeature(action) {
  return {move_start: 'move', nudge: 'move', jog: 'move', aim: 'move', preset_go: 'move', preset_save: 'move',
    scene_go: 'scenes', scene_off: 'scenes', blackout: 'scenes', scene_create: 'store', store_scene: 'store'}[action] || action;
}
function featureReason(feature) {
  var value = (state.features || {})[feature];
  if (value === false) return 'функция «' + feature + '» отключена в настройках (features.' + feature + ')';
  return typeof value === 'string' ? 'функция «' + feature + '» заблокирована: ' + value : '';
}

function go(sec) {
  if (!SECTIONS[sec]) return;
  if (sec !== state.sec) cancelTargetControls();
  if (sec !== 'light' && typeof lightUI !== 'undefined') lightUI.picking = false;
  if (state.sec === 'hall' && sec !== 'hall' && typeof planEndEdit === 'function') planEndEdit();
  if (sec === 'hall' && state.sec !== 'hall' && typeof planBeginEdit === 'function') planBeginEdit();
  state.sec = sec;
  try { localStorage.setItem('ma2.sec', sec); } catch (error) {}
  render();
}

/* ---------- shell ---------- */
function render() {
  // Before the first config the plan is unknown, not empty: keep the section a reload came back to.
  if (state.config && !hasFixtures() && ['light', 'hall', 'scenes'].indexOf(state.sec) >= 0 && !(state.config && (state.config.scenes || []).length && state.sec === 'scenes')) {
    if (state.sec === 'hall' && typeof planEndEdit === 'function') planEndEdit();
    state.sec = 'start';
  }
  var line = linkLine();
  document.querySelectorAll('#rail [data-sec]').forEach(function (b) {
    var sec = b.dataset.sec;
    if (sec === state.sec) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    b.disabled = (sec === 'light' || sec === 'hall' || sec === 'patch') && !hasFixtures() ||
      sec === 'scenes' && !hasFixtures() && !(state.config && (state.config.scenes || []).length);
  });
  document.getElementById('rail-dot').className = 'badge dot ' + line.dot;
  document.getElementById('top-dot').className = 'dot ' + line.dot;
  document.getElementById('top-link').textContent = line.text;
  document.getElementById('top-dot').setAttribute('title', LINK_TEXT[state.ma2] || line.text);
  document.getElementById('top-link').setAttribute('title', LINK_TEXT[state.ma2] || line.text);
  document.getElementById('top-show').textContent = (state.show && state.show.name) || 'неизвестно';
  document.getElementById('mock').hidden = !state.mock;
  // Two modes, told apart by the whole frame: Концерт (Сцены, Свет) on a neutral ground, Подготовка (Площадка, Зал, Шоу) on a cool one.
  var setup = SETUP.indexOf(state.sec) >= 0;
  document.getElementById('col').className = 'col ' + (setup ? 'setup' : 'live');
  document.getElementById('mode').hidden = !setup;
  var pill = document.getElementById('selpill');
  pill.hidden = !state.selection.length || setup;
  document.getElementById('selpill-text').textContent = 'Выбрано: ' + state.selection.length;
  var halt = document.getElementById('halt');
  var haltLabel = state.halted ? 'Возобновить передачу' : 'Стоп передачи';
  if (halt.textContent !== haltLabel) {
    halt.textContent = '';
    add(halt, [icon(state.halted ? 'play' : 'pause'), haltLabel]);
  }
  halt.setAttribute('aria-pressed', String(!!state.halted));
  halt.disabled = !bridgeUp();
  var bo = document.getElementById('blackout');
  var blackoutUnknown = state.blackout && state.blackout.phase === 'unknown';
  var blackoutLabel = blackoutUnknown ? 'Проверьте Grand Master' : state.blackout && state.blackout.phase === 'active' ? 'Восстановить свет' : 'Blackout MA2';
  bo.title = 'Grand Master: временное затемнение. Приборы без React to Master и DMX overrides могут остаться включены.';
  if (bo.textContent !== blackoutLabel) {
    bo.textContent = '';
    add(bo, [icon('power'), blackoutLabel]);
  }
  bo.disabled = blackoutUnknown || !connected() || !!featureReason('scenes') || !state.safety || state.safety.mode !== 'full' || busy('blackout');
  renderBanners();
  renderOperationFeedback();
  renderSection();
  updaters.forEach(function (fn) { fn(); });
}

function renderBanners() {
  var b = document.getElementById('banners');
  b.textContent = '';
  if (typeof rdmSearchBanner === 'function') { var rdmBanner = rdmSearchBanner(); if (rdmBanner) b.appendChild(rdmBanner); }
  var hl = state.highlight || {};
  if (hl.state === 'stuck') b.appendChild(h('div', {class: 'banner bad', role: 'alert'}, icon('alert'),
    'Подсветка не снята' + (hl.reason ? ': ' + hl.reason : '') + '. Кнопка снимает её командой Off: у приборов зала пропадёт и то, что выставлено на пульте вручную. Сначала сохраните шоу или запишите сцену.',
    h('button', {class: 'btn small', type: 'button', disabled: !connected(), onclick: function () { if (confirm('Снять подсветку командой Off без восстановления прежних значений? У приборов зала пропадёт и то, что выставлено на пульте вручную.')) send({a: 'highlight_off', release_token: hl.release_token}); }}, 'Снять подсветку')));
  if (bridgeUp() && !linkReady()) b.appendChild(h('div', {class: 'banner ' + (state.ma2 === 'login_failed' ? 'bad' : 'warn'), role: 'alert'}, icon('alert'),
    (LINK_TEXT[state.ma2] || state.ma2) + '. Управление недоступно' + (state.manual ? '.' : ', мост переподключается сам.')));
  if (bridgeUp() && state.recovering) b.appendChild(h('div', {class:'banner warn', role:'status'}, 'Восстановление данных MA2. ' + (state.recoveryError || 'Управление станет доступно после проверки контекста.')));
  if (state.blackout && state.blackout.phase === 'unknown') b.appendChild(h('div', {class:'banner warn', role:'alert'}, state.blackout.reason || 'Состояние затемнения неизвестно. Проверьте Grand Master на MA2 вручную.'));
  if (!bridgeUp()) b.appendChild(h('div', {class: 'banner bad', role: 'alert'}, icon('alert'), 'Нет связи с мостом. Панель переподключается каждые 2 с.'));
  if (bridgeUp() && state.halted) b.appendChild(h('div', {class: 'banner warn', role: 'alert'}, icon('pause'),
    'Передача остановлена: панель ничего не отправляет на MA2, очередь удалена. Свет на пульте не менялся.',
    h('button', {class: 'btn small', type: 'button', onclick: function () { sendRaw({a: 'resume'}); }}, 'Возобновить')));
  if (bridgeUp() && state.showFileActive) b.appendChild(h('div', {class: 'banner warn', role: 'status'}, icon('refresh'),
    'Идёт передача файла шоу. Управление светом временно недоступно; дождитесь результата операции.'));
  var load = state.showLoad || {};
  var loadText = {loading: 'Загружается шоу «' + load.name + '». Управление светом недоступно до подтверждения от MA2.',
    failed: 'Загрузка шоу «' + load.name + '» не подтверждена' + (load.reason ? ': ' + load.reason : '') + '. План панели не переключён.',
    unknown: 'Результат загрузки «' + load.name + '» неизвестен' + (load.reason ? ': ' + load.reason : '') + '. Проверьте на пульте.'}[load.state];
  if (loadText) b.appendChild(h('div', {class: 'banner warn', role: 'status'}, icon('refresh'), loadText));
  var show = state.show && state.show.name, bound = state.config && state.config.show;
  if (show && bound && show !== bound) b.appendChild(h('div', {class: 'banner warn', role: 'alert'}, icon('alert'),
    'На пульте шоу «' + show + '», а открыт план панели «' + bound + '».',
    h('button', {class: 'btn small', type: 'button', disabled: !connected(), onclick: function (e) { send({a: 'show_open_plan', name: show}, e.currentTarget); }}, 'Открыть план «' + show + '»')));
}

function renderSection() {
  var el = document.getElementById('page');
  activeControls = activeControls.filter(function(control){return el.contains(control);});
  var hl = state.highlight || {};
  var key = JSON.stringify([typeof showFileUI !== 'undefined' ? showFileUI.version : 0, state.sec, state.configN, state.selection, state.ma2, state.halted, state.manual, state.showLoad, state.showFileActive, state.showFileOperation, hl.state, hl.target,
    // Poll timestamps are evidence, not structural UI state. Replacing the page on
    // every read loses open details and pointer targets between down and up.
    [state.show.name,state.show.source], sceneUI.editing, sceneUI.masterOpen, state.safety, state.features, SETUP.indexOf(state.sec) >= 0 ? state.readFreshness : null, state.fetch, state.ma2read, state.showNames, state.showPick, state.saveReply, state.page, sceneFade,
    state.sec === 'start' ? state.last : null, // «Последняя команда» on Площадка; elsewhere a command must not redraw the sliders
    state.sec === 'history' ? state.history : null,
    typeof planKey === 'function' ? planKey() : '', state.sec === 'patch' && typeof patchKey === 'function' ? patchKey() : '', typeof lightKey === 'function' ? lightKey() : '']);
  if (key === sectionKey) return;
  if (!state.config && state.sec !== 'start') {
    el.textContent = '';
    add(el, h('p', {class: 'note loading'}, bridgeUp() ? 'Загружаю план панели…' : 'Жду связи с мостом…'));
    return;
  }
  var focused = document.activeElement;
  var focusKey = focused && el.contains(focused) ? {id:focused.id, label:focused.getAttribute('aria-label'), text:focused.textContent, tag:focused.tagName} : null;
  // Re-render would drop text being typed; values catch up on the next change.
  if (renderSection.sec === state.sec && (activeControls.length || focused && el.contains(focused) && (focused.tagName === 'INPUT' && focused.type !== 'range' && focused.type !== 'checkbox' && focused.id !== 'fixture-search' && focused.id !== 'scene-search' || focused.tagName === 'TEXTAREA'))) { sectionDeferred = true; return; }
  sectionDeferred = false;
  if (typeof moveStop === 'function') moveStop();
  sectionKey = key;
  // A rebuild must not throw lists back to the top: a tap on a fixture low in the list keeps the list where it was.
  var scroll = {page: el.scrollTop};
  el.querySelectorAll('[data-scroll]').forEach(function (n) { scroll[n.getAttribute('data-scroll')] = n.scrollTop; });
  var sameSec = renderSection.sec === state.sec;
  sectionDisposers.forEach(function(fn){fn();}); sectionDisposers=[];
  el.textContent = '';
  updaters = [];
  el.className = 'page' + (state.sec === 'light' || state.sec === 'hall' ? ' fill' : '');
  SECTIONS[state.sec](el);
  if (['light','scenes'].indexOf(state.sec) >= 0 && typeof lightUI !== 'undefined' && lightUI.picking) document.getElementById('fixture-picker').showModal();
  if (state.sec === 'scenes' && sceneUI.masterOpen) document.getElementById('scene-master').showModal();
  if (sameSec) {
    el.scrollTop = scroll.page;
    el.querySelectorAll('[data-scroll]').forEach(function (n) { var v = scroll[n.getAttribute('data-scroll')]; if (v) n.scrollTop = v; });
  }
  if (sameSec && focusKey) {
    var focusTarget = Array.prototype.slice.call(el.querySelectorAll('button,input,select,summary')).filter(function(n) {
      return focusKey.id ? n.id === focusKey.id : focusKey.label ? n.getAttribute('aria-label') === focusKey.label : n.tagName === focusKey.tag && n.textContent === focusKey.text;
    })[0];
    if (focusTarget && !focusTarget.disabled) focusTarget.focus({preventScroll:true});
  }
  renderSection.sec = state.sec;
}

/* ---------- Площадка ---------- */
function readFromMa2() { return !!(state.config && state.config.fixtures_read); }
function fixtureImportComplete(f) {
  var choices = f.choices || {}, used = [];
  return (f.items || []).length > 0 && f.items.every(function (item) {
    if (!Object.prototype.hasOwnProperty.call(choices, item.new_id)) return false;
    var old = choices[item.new_id];
    if (old === null) return true;
    if (used.indexOf(old) >= 0) return false;
    used.push(old);
    return item.candidates.some(function (candidate) { return candidate.old_id === old; });
  });
}
function fixtureImportChoices(f) {
  var choices = f.choices || (f.choices = {});
  return h('div', {class: 'import-choices', style: {display: 'grid', gap: '12px'}},
    h('p', {class: 'note warn', role: 'alert'}, 'Неоднозначная перепривязка. План пока не изменён. Выберите соответствие для каждого нового прибора или оставьте его новым.'),
    f.err ? h('p', {class: 'bad', role: 'alert'}, f.err) : null,
    (f.items || []).map(function (item) {
      function choose(old) { choices[item.new_id] = old; render(); }
      return h('div', {class: 'card'},
        h('p', {}, h('strong', {}, 'Новый прибор #' + item.new_id + ': ' + item.label)),
        h('div', {class: 'row'}, item.candidates.map(function (candidate) {
          var selected = choices[item.new_id] === candidate.old_id;
          var used = Object.keys(choices).some(function (key) { return key !== String(item.new_id) && choices[key] === candidate.old_id; });
          return h('button', {class: 'btn' + (selected ? ' primary' : ''), type: 'button', disabled: used,
            'aria-pressed': selected ? 'true' : 'false', onclick: function () { choose(candidate.old_id); }},
            'Объединить с #' + candidate.old_id + ' (' + candidate.label + ')');
        }), h('button', {class: 'btn' + (Object.prototype.hasOwnProperty.call(choices, item.new_id) && choices[item.new_id] === null ? ' primary' : ''),
          type: 'button', 'aria-pressed': Object.prototype.hasOwnProperty.call(choices, item.new_id) && choices[item.new_id] === null ? 'true' : 'false',
          onclick: function () { choose(null); }}, 'Оставить новый')));
    }),
    h('div', {class: 'row'},
      h('button', {class: 'btn primary', type: 'button', disabled: !contextReadable() || !fixtureImportComplete(f) || busy('import_confirm_merge'), onclick: function (event) {
        if (!fixtureImportComplete(f) || busy('import_confirm_merge')) return;
        state.fetch = {state: 'loading'};
        if (!send({a: 'import_confirm_merge', request_token: f.request_token, choices: choices}, event.currentTarget)) {
          f.err = 'Не удалось отправить выбор: проверьте соединение'; state.fetch = f;
        }
        render();
      }}, 'Применить выбор'),
      h('button', {class: 'btn', type: 'button', onclick: function () { state.fetch = null; notice('Импорт отменён, план не изменён', 'info'); render(); }}, 'Отменить импорт')));
}
SECTIONS.start = function (el) {
  var ready = connected();
  add(el, h('div', {class: 'ph'}, h('h1', {}, hasFixtures() ? 'Площадка' : 'Новая площадка')));
  add(el, setupSteps());
  var line = linkLine();
  var conn = h('section', {class: 'card'}, h('h2', {}, 'Подключение к grandMA2'),
    h('p', {class: line.dot === 'on' ? 'ok' : 'note'}, line.text + (state.show && state.show.name ? '. На пульте шоу «' + state.show.name + '».' : '')));
  if (bridgeUp()) add(conn, h('div', {class: 'row'},
    h('button', {class: 'btn' + (state.manual ? ' primary' : ' small'), type: 'button', onclick: function () {
      if (!state.manual && !confirm('Разорвать соединение панели с пультом? Сеть и сам пульт не затрагиваются.')) return;
      discardPending();
      sendRaw({a: state.manual ? 'link_connect' : 'link_drop'});
    }}, icon('plug'), state.manual ? 'Подключиться' : 'Разорвать связь'),
    state.mock ? h('button', {class: 'btn small', type: 'button', disabled: !ready, onclick: function (e) { send({a: 'mock_drop'}, e.currentTarget); }}, 'Оборвать связь (имитация)') : null));
  add(conn, h('p', {class: 'note'}, safetyText()), h('p', {class: 'note'}, h('a', {href: 'diag.html'}, 'Диагностика'), ' · ', h('a', {href: 'settings.html'}, 'Настройки'), ' · ', h('a', {href: 'log.html'}, 'Журнал действий')));
  add(conn, h('a', {class: 'btn small', href: 'diag.html#report'}, 'Отправить диагностику'));
  var last = state.last;
  if (last) add(conn, h('p', {class: 'note ' + (last.status === 'error' ? 'bad' : '')}, 'Последняя команда ' + last.t + ': ' + last.cmd + ' — ' + (RESULT_TEXT[last.status] || last.status)));

  var canFetch = contextReadable() && safe('allow_fixture_read') && !busy('fixtures_fetch') && !busy('import_confirm_merge');
  var f = state.fetch;
  var eq = h('section', {class: 'card'}, h('h2', {}, 'Оборудование из MA2'),
    h('p', {class: 'note'}, 'Читаю приборы текущего патча: ID, имя, тип и параметры. Это не поиск RDM. Повторное чтение сохраняет расстановку, добавляет новые приборы и помечает пропавшие.'),
    h('div', {class: 'row'}, h('button', {class: 'btn' + (hasFixtures() ? '' : ' primary'), type: 'button', disabled: !canFetch, onclick: function (e) {
      state.fetch = {state: 'loading'}; send({a: 'fixtures_fetch'}, e.currentTarget); render();
    }}, icon(hasFixtures() ? 'refresh' : 'download'), busy('fixtures_fetch') ? 'Читаю патч…' : hasFixtures() ? 'Получить снова' : 'Получить оборудование из MA2')),
    !safe('allow_fixture_read') ? h('p', {class: 'note warn'}, 'Чтение приборов выключено. Включите «Разрешить получение приборов из MA2» в ', h('a', {href: 'settings.html'}, 'Настройках'), '.') : null,
    f && f.state === 'done' ? h('div', {role:'status'}, h('p',{class:'ok'},'Получено из MA2: добавлено ' + f.added + ', пропало ' + f.missing + ', всего ' + f.total),
      h('dl',{class:'sync-summary'},h('dt',{},'Изменено'),h('dd',{},typeof f.changed === 'number' ? f.changed : 'Мост не сообщает отдельное число'),
        h('dt',{},'Без Fixture ID'),h('dd',{},f.no_id && f.no_id.length ? f.no_id.join(', ') : 'Нет в ответе'),
        h('dt',{},'Параметры не прочитаны'),h('dd',{},fixtures().filter(function(item){return !item.missing && !(item.params || []).length;}).map(function(item){return item.id;}).join(', ') || 'Нет'),
        h('dt',{},'Сохранение'),h('dd',{},'План панели обновлён. Расстановка сохранена; пропавшие приборы помечены. Патч MA2 этим не изменён.'))) : null,
    f && f.state === 'error' ? h('p', {class: 'bad', role: 'alert'}, 'Не получено из MA2: ' + f.err) : null,
    f && f.state === 'error' ? h('p', {class: 'note'}, h('a', {href: 'diag.html'}, 'Открыть диагностику')) : null,
    f && f.state === 'ambiguous' ? fixtureImportChoices(f) : null,
    hasFixtures() && readFromMa2() ? h('p', {class: 'note'}, 'Последнее получение: ' + state.config.fixtures_read.t + (state.config.fixtures_read.source === 'ma2' ? ' (из MA2)' : ' (из файла XML)') + '.') : null,
    hasFixtures() && !readFromMa2() ? h('p', {class: 'note warn', role: 'status'}, 'Показан сохранённый план: приборы и расстановка из прошлой работы. Данные из MA2 ещё не получены, параметры не прочитаны.') : null);
  add(el, h('div', {class: 'grid2'}, conn, eq));
  if (!hasFixtures()) return;
  var rows = fixtures().map(function (fx) {
    return h('tr', {class: fx.missing ? 'missing' : ''}, h('td', {class: 'id'}, fx.id), h('td', {}, fx.name || fx.label, fx.service ? ' · служебный' : ''),
      h('td', {}, fx.missing ? 'нет в патче MA2' : fx.type || '—'),
      h('td', {}, (fx.params || []).length ? h('span', {class: 'params'}, fx.params.slice(0, 8).map(function (p) { return h('span', {class: 'param'}, p); })) : h('span', {class: 'note'}, fx.channels ? fx.channels + ' кан.' : 'не прочитаны')),
      h('td', {}, fx.address || '—'),
      h('td', {}, typeof fx.x === 'number' ? 'да' : '—'));
  });
  add(el, h('section', {class: 'card', style: {'margin-bottom': '12px'}}, h('div', {class: 'vrow'}, h('h2', {}, 'Приборы плана' + (state.config.show ? ' «' + state.config.show + '»' : '') + ' · ' + fixtures().length),
    h('button', {class: 'btn small edit', type: 'button', onclick: function () { go('hall'); }}, icon('edit', 18), 'Расставить в зале')),
    fixtures().some(function (fx) { return fx.channels && !(fx.params || []).length; }) ? h('p', {class: 'note'}, 'Имена каналов MA2 не передаёт: видно только их число.') : null,
    h('div', {class: 'tablewrap'}, h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, 'ID'), h('th', {}, 'Имя'), h('th', {}, 'Тип'), h('th', {}, 'Параметры'), h('th', {}, 'Адрес'), h('th', {}, 'На плане'))), h('tbody', {}, rows)))));
  add(el, ma2Card());
};
// Venue preparation at a glance: what is done, what is next. Steps 3 and 4 can be skipped; the panel works without them.
function setupSteps() {
  var cfg = state.config || {};
  var stage = fixtures().filter(function (f) { return !f.missing; });
  var onPlan = stage.filter(function (f) { return typeof f.x === 'number'; }).length;
  var ma2n = (cfg.ma2groups || []).length + (((cfg.ma2presets || {}).colors || []).length) + (cfg.scenes || []).length;
  var steps = [
    ['Связь с пультом', linkReady(), linkReady() ? 'вход подтверждён' : (LINK_TEXT[state.ma2] || 'нет связи').toLowerCase(), null],
    ['Приборы из MA2', !!state.readFreshness.fixtures, state.readFreshness.fixtures ? stage.length + ' приборов · получено сейчас' : hasFixtures() ? 'сохранённые данные' : 'ещё не получены', null],
    ['Группы, пресеты, сцены', !!(state.readFreshness.ma2 || state.readFreshness.scenes), state.readFreshness.ma2 || state.readFreshness.scenes ? 'прочитано сейчас' : ma2n ? 'сохранённые данные' : 'по желанию', null],
    ['Зал и расстановка', !!cfg.hall && onPlan > 0, cfg.hall ? onPlan + ' из ' + stage.length + ' на плане' : 'план не нарисован', hasFixtures() ? function () { go('hall'); } : null]
  ];
  return h('ol', {class: 'steps', 'aria-label': 'Подготовка площадки'}, steps.map(function (s, i) {
    var body = [h('span', {class: 'n', 'aria-hidden': 'true'}, s[1] ? icon('check', 18) : String(i + 1)), h('span', {class: 'st'}, h('b', {}, s[0]), h('span', {class: 'note'}, s[2]))];
    return h('li', {class: s[1] ? 'done' : ''}, s[3] ? h('button', {type: 'button', class: 'step-btn', onclick: s[3]}, body, icon('chevron', 18)) : h('div', {class: 'step-btn'}, body));
  }));
}
function safetyText() {
  var s = state.safety;
  if (!s) return '';
  if (s.mode === 'full') return 'Режим: полный (запись в пульт разрешена).';
  return 'Режим «' + s.mode + '»: приборы ' + (s.fixtures.length ? s.fixtures.join(', ') : 'не разрешены') + '; сцены ' + (s.scenes.length ? s.scenes.join(', ') : 'не разрешены') +
    (s.mode === 'store' ? '; запись только в ' + (s.store.join(', ') || '—') : '; запись в пульт заблокирована') + '.';
}
function ma2Card() {
  var r = state.ma2read;
  var card = h('section', {class: 'card'}, h('h2', {}, 'Группы, пресеты и сцены из MA2'),
    h('p', {class: 'note'}, 'Прочитать, что есть в этом шоу, и отметить, что показать в панели. На пульте ничего не меняется. Группы MA2 хранятся отдельно от групп панели.'));
  add(card, h('div', {class: 'row'}, h('button', {class: 'btn', type: 'button', disabled: !connected() || busy('ma2_read'), onclick: function (e) { send({a: 'ma2_read'}, e.currentTarget); }}, icon('download'), 'Прочитать из MA2'),
    h('button', {class: 'btn ghost', type: 'button', disabled: !connected() || busy('scenes_import'), onclick: function (e) { send({a: 'scenes_import'}, e.currentTarget); }}, 'Обновить только сцены')));
  if (r && !r.ok) add(card, h('p', {class: 'bad', role: 'alert'}, (r.err || 'ответ не распознан') + '. Ничего не изменено.'), r.raw ? h('pre', {class: 'raw'}, r.raw) : null);
  if (!r || !r.ok) return card;
  var pick = {groups: r.groups.map(function (g) { return g.n; }), colors: true, positions: true, scenes: true};
  r.groups.forEach(function (g) {
    add(card, h('label', {class: 'chk'}, h('input', {type: 'checkbox', checked: true, onchange: function (e) {
      pick.groups = e.target.checked ? pick.groups.concat([g.n]) : pick.groups.filter(function (n) { return n !== g.n; });
    }}), h('span', {class: 'tag ma2'}, 'MA2 ' + g.n), 'Группа «' + g.name + '»' + (g.ids ? ' · ' + g.ids.length + ' приб.' : '')));
  });
  add(card, h('label', {class: 'chk'}, h('input', {type: 'checkbox', checked: true, onchange: function (e) { pick.colors = e.target.checked; }}), 'Цветовые пресеты · ' + r.colors.length),
    h('label', {class: 'chk'}, h('input', {type: 'checkbox', checked: true, onchange: function (e) { pick.positions = e.target.checked; }}), 'Пресеты позиции · ' + r.positions.length),
    h('label', {class: 'chk'}, h('input', {type: 'checkbox', checked: true, onchange: function (e) { pick.scenes = e.target.checked; }}), 'Сцены (исполнители страниц)'),
    h('div', {class: 'row'}, h('button', {class: 'btn primary', type: 'button', disabled: !connected(), onclick: function (e) {
      send({a: 'ma2_import', groups: pick.groups, colors: pick.colors, positions: pick.positions, scenes: pick.scenes}, e.currentTarget);
    }}, icon('check'), 'Добавить отмеченное')));
  return card;
}

/* ---------- Сцены ---------- */
function pagesList() {
  var pages = state.config && state.config.pages;
  return Array.isArray(pages) ? pages : Object.keys(pages || {}).map(function (key) { return {n:Number(key),label:pages[key]}; });
}
// Keep the existing preparation sections and their forms reachable from four primary entries.
SECTIONS.prepare = function (el) {
  add(el, h('div', {class:'ph'}, h('h1', {}, 'Подготовка')),
    h('p', {class:'note'}, 'Изменения отдельно от исполнения.'));
  var links = h('div', {class:'preparation-links'});
  [['start','Подключение и синхронизация'],['patch','Приборы и Patch'],['hall','План зала и группы'],['shows','Шоу'],['scenes','Редактировать сцены'],['history','История']].forEach(function (item) {
    add(links, h('button', {class:'btn', type:'button', onclick:function () {
      if (item[0] === 'scenes') sceneUI.editing = true;
      go(item[0]);
    }}, item[1]));
  });
  add(links,h('button',{class:'btn',type:'button',onclick:function(){go('hall');planState.tab='groups';render();}},'Группы'),h('a',{class:'btn',href:'diag.html'},'Диагностика'),h('a',{class:'btn',href:'settings.html'},'Настройки подключения'));
  add(el, links);
};
SECTIONS.help = function (el) {
  add(el, h('div', {class:'ph'}, h('h1', {}, 'Связь и помощь')),
    h('section', {class:'card'}, h('h2', {}, linkLine().text),
      h('p', {class:'note'}, 'После обрыва команды не повторяются. Проверьте состояние света перед новой командой.'),
      h('p', {class:'note'}, 'Отправка команды не подтверждает физическое состояние света.'),
      h('div', {class:'row'}, h('button', {class:'btn', type:'button', onclick:function(){go('start');}}, 'Площадка'),
        h('button', {class:'btn', type:'button', onclick:function(){go('history');}}, 'История'),
        h('a', {class:'btn', href:'diag.html'}, 'Диагностика'), h('a', {class:'btn', href:'settings.html'}, 'Настройки'),
        h('a', {class:'btn', href:'log.html'}, 'Журнал действий'))));
};

function transitionControl() {
  var input = h('input', {type:'number', min:0, max:30, step:0.5, value:String(sceneFade), 'aria-label':'Время перехода, секунды', onchange:function () {
    var value = Number(input.value);
    if (!input.value.trim() || !Number.isFinite(value) || value < 0 || value > 30) { input.value = String(sceneFade); notice('Время перехода: от 0 до 30 секунд.', 'warning'); return; }
    send({a:'scene_fade',fade:value});
  }});
  return h('div', {class:'card fade shared-fade', role:'group', 'aria-label':'Общее время перехода'},
    h('label', {}, 'Переход, с', input), [0,2,5,10].map(function (seconds) {
      var button = h('button', {class:'btn small', type:'button', 'aria-pressed':String(sceneFade === seconds), onclick:function () { send({a:'scene_fade',fade:seconds}); }}, seconds ? seconds + ' с' : 'Сразу');
      updaters.push(function () { button.setAttribute('aria-pressed',String(sceneFade === seconds)); });
      return button;
    }), h('span', {class:'src'}, 'Сцены и быстрые значения. Перетаскивание — сразу.'));
}
SECTIONS.scenes = function (el) {
  var ready = connected();
  var scenes = (state.config && state.config.scenes) || [];
  var addBtn = h('button', {class: 'btn primary', type: 'button', disabled: !ready || !!featureReason('store'),
    title: 'Записать свет, который выставлен сейчас, в новую сцену', onclick: function () { openStore(state.page || 1); }}, 'Сохранить сцену');
  var edit = h('button', {class: 'btn small edit', type: 'button', onclick: function () {
    sceneUI.editing = !sceneUI.editing; render();
  }}, sceneUI.editing ? 'К исполнению' : 'Изменить сцены');
  var head = h('div', {class: 'ph'}, h('h1', {}, sceneUI.editing ? 'Редактирование сцен' : 'Сцены'), edit, addBtn);
  var master = masterControl();
  var compactMaster = h('button', {id:'compact-master', class:'btn compact-master', type:'button', onclick:function () {
    sceneUI.masterOpen = true; render();
  }}, 'Общая яркость');
  function closeMaster() {
    sceneUI.masterOpen = false; render();
    var button = document.getElementById('compact-master'); if (button) button.focus({preventScroll:true});
  }
  var masterDialog = h('dialog', {id:'scene-master', 'aria-label':'Общая яркость', oncancel:function(event){event.preventDefault();closeMaster();}},
    h('div', {class:'dlg'}, sceneUI.masterOpen ? master : null,
      h('button', {class:'btn', type:'button', onclick:closeMaster}, 'К сценам')));
  add(el, head, compactMaster, masterDialog);
  add(el, transitionControl());
  if (!scenes.length) {
    add(el, h('div', {class: 'card'}, h('p', {}, 'Сцен в панели нет. Прочитайте их из MA2 на «Площадке».'), h('div', {}, h('button', {class: 'btn', type: 'button', onclick: function () { go('start'); }}, 'Открыть «Площадку»'))));
    if (hasFixtures()) lightWorkspace(el, true);
    return;
  }
  var search = h('input', {id:'scene-search', type:'search', value:sceneUI.query,
    placeholder:'Найти сцену по имени или номеру', 'aria-label':'Найти сцену по имени или номеру',
    oninput:function () { sceneUI.query = search.value; filterScenes(); }});
  var entries = [];
  var emptySearch = h('p', {class:'note', role:'status'}, 'Не найдено. Попробуйте часть названия или номер.');
  function filterScenes() {
    var query = sceneUI.query.toLocaleLowerCase('ru').trim();
    var count = 0;
    entries.forEach(function (entry) { entry.row.hidden = entry.text.indexOf(query) < 0; if (!entry.row.hidden) count++; });
    emptySearch.hidden = count > 0;
  }
  var workspace = h('div', {class:'concert-workspace'});
  var list = h('section', {class:'concert-list', 'aria-label':'Список сцен'}, search);
  var side = h('section', {class:'concert-side', 'aria-label':'План и параметры света'});
  if (hasFixtures()) lightWorkspace(side, true);
  else add(side, h('div', {class:'card master-card'}, sceneUI.masterOpen ? null : master));
  add(workspace, list, side); add(el, workspace);
  var tiles = h('div', {class:'tiles scene-list', 'data-scroll':'scenes'});
  scenes.forEach(function (scene, index) {
    var current = sceneEvidence(scene.id), run = current.value === true;
    var allowed = sceneAllowed(scene);
    var label = scene.label || 'Без названия';
    var tile = h('button', {class:'tile' + (run ? ' run' : '') + (scene.write_error ? ' write-error' : ''), type:'button', 'data-scene':scene.id,
      'aria-label': (index + 1) + '. ' + label + ', ' + current.label.toLowerCase(),
      disabled: !ready || !allowed || !!featureReason('scenes') || !!scene.write_error, onclick:function() {
        var action = {a:'scene_go',id:scene.id,swap:scenes.filter(function(o){return o.id !== scene.id && sceneAllowed(o) && sceneEvidence(o.id).value !== false;}).map(function(o){return o.id;})};
        if (sceneFade) action.fade = sceneFade;
        send(action,tile);
      }}, h('span',{class:'scene-number'},index + 1), h('span',{class:'scene-name'},label),
      h('span',{class:'scene-state'},scene.write_error ? 'Запись не подтверждена' : current.label));
    var controls = h('div',{class:'tile-controls'},sceneUI.editing ? h('button',{class:'btn small ghost',type:'button',disabled:!ready,
      onclick:function(){openSceneEdit(scene);}},'Изменить') : null);
    var off = h('button',{class:'btn small off',type:'button','data-scene':scene.id,
      'aria-label':'Выключить сцену «' + label + '»',onclick:function(e){send({a:'scene_off',id:scene.id},e.currentTarget);}},'Выключить');
    add(controls,off);
    updaters.push(function () {
      var evidence = sceneEvidence(scene.id);
      tile.classList.toggle('run',evidence.value === true);
      tile.disabled = off.disabled = !connected() || !sceneAllowed(scene) || !!featureReason('scenes');
      tile.disabled = tile.disabled || !!scene.write_error;
      tile.setAttribute('aria-label',(index + 1) + '. ' + label + ', ' + evidence.label.toLowerCase());
      tile.setAttribute('aria-pressed',evidence.value === null ? 'mixed' : String(evidence.value === true));
      var waiting = Object.keys(pending).map(function (id) { return pending[id]; }).filter(function (item) { return item.scene === scene.id && item.a === 'scene_go'; }).slice(-1)[0];
      tile.children[2].textContent = scene.write_error ? 'Запись не подтверждена' : evidence.label + (waiting ? ' · ' + commandWaiting(waiting,state.operations || [],Date.now()).text : '');
      off.hidden = evidence.value === false;
    });
    var row = h('div',{class:'tile-wrap'},tile,controls);
    entries.push({row:row, text:((index + 1) + ' ' + label).toLocaleLowerCase('ru')});
    add(tiles,row);
  });
  add(list,tiles,emptySearch); filterScenes();
};

function masterControl() {
  var out = h('span', {class: 'val'});
  var source = h('span', {class: 'note'});
  var input = h('input', {type: 'range', min: 0, max: 100, value: 100, 'aria-label': 'Общая яркость', oninput: function (e) {
    out.textContent = e.target.value + '%'; out.classList.remove('unknown'); setFill(input, Number(e.target.value));
    throttleSlider({a: 'master', v: Number(e.target.value), fade: 0});
  }});
  updaters.push(function () {
    input.disabled = !connected() || !(state.safety && state.safety.master);
    input.title = state.safety && !state.safety.master ? 'Общая яркость заблокирована (allow_master)' : '';
    if (controlActive(input)) { source.textContent = 'Ввод: ' + input.value + '% · последнее отправленное: ' + (state.master === null ? 'неизвестно' : Math.round(state.master) + '%'); return; }
    out.textContent = state.master === null ? 'неизвестно' : Math.round(state.master) + '%';
    out.classList.toggle('unknown', state.master === null);
    source.textContent = state.master === null ? 'значение неизвестно' : 'отправлено панелью' +
      (valueFreshness('master') === 'stale' ? ' · устарело' : '');
    setFill(input, state.master);
  });
  return h('div', {class: 'master'}, h('div', {class: 'vrow'}, h('b', {}, 'Общая яркость'), out), input, source);
}
function setFill(input, v) {
  input.classList.toggle('unknown', v === null || v === 'mixed');
  if (typeof v === 'number') input.value = v;
  input.style.setProperty('--p', (typeof v === 'number' ? v : 0) + '%');
}
function openSceneEdit(s) {
  var d = document.getElementById('dlg');
  var name = h('input', {id: 'scene-name', maxlength: 30, value: s.label || '', autocomplete: 'off'});
  var rename = h('button', {class: 'btn', type: 'button', onclick: function () {
    var label = name.value.trim();
    if (label) send({a: 'scene_rename', id: s.id, label: label}, rename);
  }}, 'Сохранить имя');
  var rewrite = h('button', {class: 'btn primary', type: 'button', disabled: !!featureReason('store'), onclick: function () {
    var label = name.value.trim() || s.label;
    if (!confirm('Перезаписать сцену «' + (s.label || 'Без названия') + '» текущим светом? Старое содержимое пропадёт.')) return;
    if (send({a: 'scene_create', label: label, page: pageOf(s), exec: String(s.exec), confirm: String(s.exec), replace: true}, rewrite)) { /* close on reply */ }
  }}, icon('save'), 'Перезаписать текущим светом');
  d.textContent = '';
  d._result = h('p',{class:'note',role:'status'});
  add(d, h('div', {class: 'dlg'}, h('h2', {}, s.label || 'Без названия'),
    s.write_error ? h('p',{class:'note warn'},s.write_error) : null,
    h('div', {class: 'field'}, h('label', {for: 'scene-name'}, 'Имя сцены'), name),
    h('p', {class:'note'}, 'Перезапись сохранит текущий выход пульта.'), d._result,
    h('details',{},h('summary',{},'Технические данные'),h('p',{class:'note'},'Адрес на MA2: ' + s.exec)),
    h('div', {class:'scene-delete-actions'}, [false,true].map(function(desk) {
      return h('button',{class:'btn small' + (desk ? ' danger' : ' ghost'),type:'button',disabled:!connected() || (desk && !!featureReason('store')),onclick:function(e) {
        if (confirm((desk ? 'Удалить на пульте ' : 'Убрать из панели ') + '«' + s.label + '» (' + s.exec + ')?' + (desk ? ' Вернуть можно только из бэкапа шоу.' : ' На пульте сцена останется.'))) send({a:'scene_delete',id:s.id,desk:desk},e.currentTarget);
      }}, desk ? 'Удалить на пульте' : 'Убрать из панели');
    })),
    h('div', {class: 'row'}, h('button', {class: 'btn ghost', type: 'button', onclick: function () { d.close(); }}, 'Отмена'), rename, rewrite)));
  d.showModal();
  name.focus();
}
var storeUI = null, storeSerial = 0;
function cancelStore() {
  if (storeUI && storeUI.request) sendRaw({a:'scene_slot_cancel',request:storeUI.request});
  storeUI = null;
}
function openStore() {
  cancelStore();
  var d = document.getElementById('dlg');
  var ui = {request:null,slot:null}; storeUI = ui;
  var name = h('input',{id:'store-name',maxlength:30,placeholder:'Например: Солист у рояля',autocomplete:'off'});
  var progress = h('p',{class:'note',role:'status'},'Сохранится текущий выход выбранных приборов. Сначала выберите их на плане; затем найдите свободное место. Пока ничего не записывается.');
  d._result = progress;
  var address = h('p',{class:'note'});
  var search = h('button',{class:'btn primary',type:'button',disabled:!connected() || !!featureReason('store'),onclick:function() {
    if (!name.value.trim()) { name.focus(); return; }
    if (ui.request) sendRaw({a:'scene_slot_cancel',request:ui.request});
    ui.request = 'slot-' + (++storeSerial); ui.slot = null;
    ui.update({state:'searching',checked:0});
    if (!send({a:'scene_slot_find',request:ui.request},search)) ui.update({state:'error',err:'Запись недоступна'});
  }},'Найти место');
  var write = h('button',{class:'btn primary',type:'button',hidden:true,onclick:function() {
    if (!ui.slot || !name.value.trim()) return;
    send({a:'scene_create',label:name.value.trim(),page:pageOf(ui.slot),exec:ui.slot.exec,confirm:ui.slot.exec,token:ui.slot.token},write);
  }},'Записать');
  ui.update = function(slot) {
    write.hidden = slot.state !== 'ready';
    search.hidden = slot.state === 'searching';
    if (slot.state === 'ready') {
      ui.slot = slot;
      progress.textContent = 'Свободное место найдено. Сохранится текущий выход выбранных приборов. Подтвердите запись.';
      address.textContent = 'Адрес на MA2: ' + slot.exec;
    } else {
      ui.slot = null;
      progress.textContent = slot.state === 'searching' ? 'Ищу свободное место… проверено: ' + (slot.checked || 0) : slot.err || 'Поиск отменён';
    }
  };
  d.textContent = '';
  add(d,h('div',{class:'dlg'},h('h2',{},'Новая сцена'),h('div',{class:'field'},h('label',{for:'store-name'},'Название'),name),progress,h('details',{},h('summary',{},'Технические данные'),address),
    h('div',{class:'row'},h('button',{class:'btn ghost',type:'button',onclick:function(){cancelStore();d.close();}},'Отмена'),search,write)));
  d.showModal(); name.focus();
}
on('scene_slot',function(slot) { if (storeUI && slot.request === storeUI.request) storeUI.update(slot); });
document.getElementById('dlg').addEventListener('close',cancelStore);

/* ---------- История ---------- */
SECTIONS.history = function (el) {
  add(el, h('div', {class: 'ph'}, h('h1', {}, 'История')));
  add(el, h('p', {class: 'note'}, 'Последние 100 изменений с этого моста, новые сверху. «Откатить» возвращает то, что было до изменения. После перезапуска моста история пустая.'));
  if (!state.history.length) { add(el, h('div', {class: 'card'}, h('p', {}, 'Изменений пока нет.'))); return; }
  add(el, h('div', {class: 'card'}, state.history.slice().reverse().map(function (e) {
    return h('div', {class: 'grow-row history-row'}, h('span', {class: 'note'}, e.t), h('span', {class: 'nm'}, e.what),
      e.undo ? h('button', {class: 'btn small', type: 'button', disabled: !linkReady() || e.done, onclick: function (ev) { send({a: 'undo', n: e.n}, ev.currentTarget); }},
        e.done ? 'Откачено' : 'Откатить') : h('span', {class: 'note'}, e.reason || 'не откатывается'));
  })));
};

/* ---------- Шоу ---------- */
SECTIONS.shows = function (el) {
  var ready = connected();
  var name = state.show && state.show.name, bound = state.config && state.config.show;
  var scenes = (state.config && state.config.scenes) || [];
  add(el, h('div', {class: 'ph'}, h('h1', {}, 'Шоу')));
  var cur = h('section', {class: 'card'}, h('h2', {}, 'Сейчас на пульте'),
    h('div', {class: 'grow-row'}, icon('file'), h('span', {class: 'nm'}, name || 'имя не прочитано'), h('span', {class: 'tag'}, 'файл шоу')),
    h('dl', {class: 'kv'}, h('dt', {}, 'План панели'), h('dd', {}, bound ? '«' + bound + '»' : 'не привязан к шоу'),
      h('dt', {}, 'В плане'), h('dd', {}, fixtures().length + ' приб., ' + ((state.config && state.config.groups) || []).length + ' групп панели, ' + scenes.length + ' сцен'),
      h('dt', {}, 'Страница на пульте'), h('dd', {}, state.page || 'неизвестна')),
    h('div', {class: 'row'},
      h('button', {class: 'btn small', type: 'button', disabled: !ready, onclick: function (e) { send({a: 'show_identify'}, e.currentTarget); }}, 'Перечитать имя'),
      name && !bound ? h('button', {class: 'btn small', type: 'button', disabled: !ready, onclick: function (e) { send({a: 'show_bind', name: name, confirm: false}, e.currentTarget); }}, 'Привязать план к «' + name + '»') : null,
      !name ? h('button', {class: 'btn small', type: 'button', disabled: !ready, onclick: function (e) {
        var n = prompt('Имя шоу для этого плана', bound || '');
        if (!n) return;
        var change = !!bound && bound !== n;
        if (change && !confirm('Сменить привязку плана с «' + bound + '» на «' + n + '»?')) return;
        send({a: 'show_bind', name: n, confirm: change}, e.currentTarget);
      }}, 'Привязать план вручную') : null));
  add(cur, h('h3', {}, 'Сохранить шоу на пульте'),
    safe('allow_show_save') ? h('div', {}, h('button', {class: 'btn', type: 'button', disabled: !ready, onclick: function (e) {
      // SaveShow writes over the show open on the desk; the bridge reads its name fresh.
      if (confirm('Сохранить шоу, открытое на пульте' + (name ? ' («' + name + '»)' : '') + ', поверх файла?')) send({a: 'show_save'}, e.currentTarget);
    }}, icon('save'), 'Сохранить шоу на пульте')) : h('p', {class: 'note'}, 'Сохранение выключено в настройках (allow_show_save).'),
    state.saveReply ? h('pre', {class: 'raw'}, state.saveReply + '\nОтправка команды не доказывает сохранение. Проверьте на пульте.') : null);

  var list = h('section', {class: 'card'}, h('h2', {}, 'Файлы шоу на пульте'),
    h('p', {class: 'note'}, 'Загрузка другого шоу меняет всё на MA2. Само ничего не загружается: ни при открытии панели, ни при переподключении.'),
    h('div', {}, h('button', {class: 'btn small', type: 'button', disabled: !ready || busy('shows_list'), onclick: function (e) { send({a: 'shows_list'}, e.currentTarget); }}, icon('refresh', 18), state.showNames ? 'Обновить список' : 'Показать список')));
  if (state.showNames && !state.showNames.length) add(list, h('p', {class: 'bad'}, 'Имена файлов в ответе MA2 не распознаны, загрузка недоступна.'), h('pre', {class: 'raw'}, state.showRaw.join('\n')));
  (state.showNames || []).forEach(function (n) {
    var isCur = n === name;
    add(list, h('button', {class: 'grow-row', type: 'button', 'aria-pressed': String(state.showPick === n), disabled: isCur, onclick: function () { state.showPick = n; render(); }},
      icon('file'), h('span', {class: 'nm'}, n), h('span', {class: 'note'}, isCur ? 'загружено' : '')));
  });
  if (state.showLocal.length) add(list, h('p', {class: 'note'}, 'Файлы на этом ПК: ' + state.showLocal.join(', ') + '. Загрузка — только по имени из ответа MA2.'));
  if (state.showPick && state.showPick !== name && (state.showNames || []).indexOf(state.showPick) >= 0) {
    var pickName = state.showPick;
    var load = h('button', {class: 'btn blackout', type: 'button', disabled: !ready || !safe('allow_show_load') || busy('show_load'), onclick: function () {
      if (!confirm('Загрузить шоу «' + pickName + '»? Несохранённые изменения текущего шоу пропадут.')) return;
      if (send({a: 'show_load', name: pickName, confirm_name: pickName, ack_unsaved: true}, load)) { state.showPick = null; }
    }}, 'Загрузить «' + pickName + '»');
    add(list, h('div', {class: 'card', style: {background: 'var(--s2)'}}, h('h3', {style: {color: 'var(--ink)'}}, 'Загрузка «' + pickName + '» заменит всё на MA2'),
      h('p', {class: 'note warn'}, 'MA2 не сообщает о несохранённых изменениях текущего шоу. Если они нужны, сначала сохраните его.'),
      !safe('allow_show_load') ? h('p', {class: 'note warn'}, 'Загрузка выключена в настройках (allow_show_load).') : null,
      h('div', {}, load)));
  }
  var plans = (state.config && state.config.plans) || [];
  var from = h('select', {}, plans.map(function (n) { return h('option', {value: n}, n); }));
  var copy = h('section', {class: 'card'}, h('h2', {}, 'Перенести из другого шоу'),
    h('p', {class: 'note'}, 'Расстановка, подписи, отметки голов и группы панели переносятся на приборы с теми же номерами. ' +
      (state.selection.length ? 'Только выбранные приборы: ' + state.selection.length + '.' : 'Все приборы (чтобы перенести часть, выберите их на «Свете»).') +
      ' Патч на пульте панель не меняет: прибора, которого нет в этом шоу, не будет.'),
    plans.length ? h('div', {class: 'row'}, from, h('button', {class: 'btn small', type: 'button', disabled: !bridgeUp() || busy('plan_copy'), onclick: function (e) {
      send({a: 'plan_copy', from: from.value, ids: state.selection.slice()}, e.currentTarget);
    }}, 'Перенести')) : h('p', {class: 'note'}, 'Других планов на этом ПК нет.'));
  add(el, h('div', {class: 'shows'}, typeof showFilesCard === 'function' ? showFilesCard() : null, cur, list, copy));
};

/* ---------- link ---------- */
function discardPending() {
  if (selectionSync) { selectionSync=null; selectionIntent=null; state.selection=[]; state.group=null; }
  var unfinished = Object.keys(pending).filter(function (id) { return pending[id].sent; }).length;
  var unsent = Object.keys(pending).length - unfinished;
  Object.keys(pending).forEach(function (id) { var b = pending[id].button; if (b) { b.removeAttribute('aria-busy'); b.classList.remove('waiting'); } });
  if (unfinished) notice('Связь прервана: результат незавершённых запросов неизвестен. Команды не повторены.', 'warning', true);
  if (unsent) notice('Запросы из очереди панели не отправлены: ' + unsent + '. Очередь отменена.', 'warning', true);
  pending = {};
  operationFeedback = null;
  configQueue = []; configActive = null;
  cancelTargetControls();
  renderOperationFeedback();
}

function clearEvidence() {
  state.scenes = {}; state.sceneMeta = {}; state.shown = {}; state.live = {}; state.simulation = {}; state.dmx = {};
  state.valuesMeta = {}; state.master = null;
  evidenceReceipts = {scenes: {}, values: {}};
}
function sceneAllowed(scene) {
  return !state.safety || state.safety.mode === 'full' || (state.safety.scenes || []).indexOf(String(scene.exec)) >= 0;
}
function sceneEvidence(id) {
  var meta = state.sceneMeta[id], value = state.scenes[id];
  if (!meta || meta.source !== 'ma2' || meta.freshness !== 'fresh') value = null;
  if (value !== true && value !== false) value = null;
  return {value: value, label: value === true ? 'Идёт · MA2' : value === false ? 'Остановлена · MA2' :
    meta && meta.freshness === 'stale' ? 'Статус устарел' : 'Статус неизвестен'};
}
function valueFreshness(kind) {
  return (state.valuesMeta[kind] || {}).freshness;
}
function sentSource() {
  return 'последнее отправленное панелью';
}
function sentStale(attr) {
  return state.selection.some(function(id) { return valueFreshness('sent:' + id + ':' + attr) === 'stale'; });
}
function observeEvidence(meta, receipts) {
  Object.keys(meta).forEach(function (id) {
    var value = meta[id], old = receipts[id];
    if (value.freshness !== 'fresh') { delete receipts[id]; return; }
    if (!old || old.stamp !== value.updated_at) receipts[id] = {stamp: value.updated_at, at: Date.now()};
    else if (Date.now() - old.at >= 6000) value.freshness = 'stale';
  });
}
function expireEvidence() {
  renderOperationFeedback();
  var changed = false;
  [[state.sceneMeta, evidenceReceipts.scenes, true], [state.valuesMeta, evidenceReceipts.values, false]].forEach(function (group) {
    Object.keys(group[1]).forEach(function (id) {
      if (Date.now() - group[1][id].at < 6000) return;
      if (group[0][id] && group[0][id].freshness === 'fresh') {
        group[0][id] = Object.assign({}, group[0][id], {freshness: 'stale'});
        if (group[2]) state.scenes[id] = null;
        else if (id === 'live') { state.live = {}; state.simulation = {}; state.dmx = {}; }
        else if (id.indexOf('sent:') === 0) {
          var parts = id.split(':');
          if (state.shown[parts[1]]) delete state.shown[parts[1]][parts[2]];
        }
        changed = true;
      }
    });
  });
  if (changed) render();
}
setInterval(expireEvidence, 500);
function receive(message) {
  if ('values_revision' in message) {
    if (message.values_revision <= state.valuesRevision) return;
    state.valuesRevision = message.values_revision;
  }
  if (message.status) {
    if (typeof message.status.blackout_epoch === 'number' && message.status.blackout_epoch !== state.blackoutEpoch) {
      state.blackoutEpoch = message.status.blackout_epoch;
      cancelTargetControls();
    }
    state.recovering = !!message.status.recovering;
    state.recoveryError = message.status.recovery_error || null;
    state.blackout = message.status.blackout || {phase:'idle'};
    if ('rdm_search' in message.status) state.rdmSearch = message.status.rdm_search;
    state.operations = message.status.operations || [];
    state.showFileActive = !!message.status.show_file_active;
    state.showFileOperation = message.status.show_file || null;
    if (state.showFileActive) cancelTargetControls();
    state.readFreshness = message.status.read_freshness || {};
    state.highlight = message.status.highlight || {state: 'idle', available: []};
    state.showLoad = message.status.show_load || {state: 'idle'};
    if (state.showLoad.state === 'loading') { selectionIntent = null; selectionSync = null; cancelTargetControls(); state.selection = []; state.group = null; clearEvidence(); }
    var nextShow = message.status.show || {name: null, source: 'unknown'};
    if (state.show.name && nextShow.name && state.show.name !== nextShow.name) {
      state.selection = []; state.group = null; selectionIntent = null; selectionSync = null;
      cancelTargetControls();
    }
    state.show = nextShow;
    state.ma2 = message.status.ma2; state.login = message.status.login;
    if (!linkReady()) clearEvidence();
    state.mock = message.status.mock;
    state.halted = !!message.status.halted;
    state.safety = message.status.safety || null;
    state.features = message.status.features || {};
    state.noAttr = message.status.no_attr || {};
    state.manual = !!message.status.manual;
    if ('last' in message.status) state.last = message.status.last;
    if ((!linkReady() || state.halted || state.showLoad.state === 'loading') && storeUI) { cancelStore(); var sd = document.getElementById('dlg'); if (sd.open) sd.close(); }
    if (!linkReady() || state.recovering || state.halted) { if (typeof moveStop === 'function') moveStop(); discardPending(); }
  }
  if (message.last) state.last = message.last;
  if (message.config) {
    var priorIdentity = selectionIdentity(state.config, state.selection);
    if (priorIdentity && priorIdentity !== selectionIdentity(message.config,state.selection)) {
      state.selection = []; state.group = null; selectionSync = null;
      Object.keys(sliderChannels).forEach(cancelSlider); if (typeof moveStop === 'function') moveStop();
      notice('Выбор снят: изменился состав или адреса приборов.', 'warning');
    }
    if (state.config && state.config.show !== message.config.show) {
      if (storeUI) { cancelStore(); var sd = document.getElementById('dlg'); if (sd.open) sd.close(); }
      // Another show's plan: old selection and values never carry over.
      cancelTargetControls();
      if (state.selection.length) notice('Открыт план другого шоу. Выделение прежних приборов снято.', 'info');
      clearEvidence(); state.selection = []; state.group = null; state.fetch = null; state.ma2read = null;
      if (typeof planState !== 'undefined') planState.cur = 0;
      if (typeof planEndEdit === 'function' && state.sec === 'hall') planEndEdit();
    }
    if (JSON.stringify(state.config) !== JSON.stringify(message.config)) { state.config = message.config; state.configN++; }
    awaitingConfig = false;
    sceneFade = fadeSeconds = state.config.scene_fade || 0;
  }
  if ('master' in message) state.master = message.master;
  if (message.shown) state.shown = message.shown;
  if (message.history) state.history = message.history;
  if (message.simulation) state.simulation = message.simulation;
  if (message.live) state.live = message.live;  // what the desk outputs (DMX read-back), every fixture
  if (message.dmx) state.dmx = message.dmx;
  if ('tracked' in message) state.tracked = message.tracked;
  if ('page' in message) state.page = message.page;
  if (message.running) Object.assign(state.scenes, message.running);
  if (message.running_meta) { observeEvidence(message.running_meta, evidenceReceipts.scenes); Object.assign(state.sceneMeta, message.running_meta); }
  if (message.values_meta) { observeEvidence(message.values_meta, evidenceReceipts.values); Object.assign(state.valuesMeta, message.values_meta); }
  if ('ok' in message) {
    var request = pending[message.request_id];
    if (message.request_id && !request) return;  // an old socket/reply cannot finish another action
    if (message.request_id === selectionSync) {
      selectionSync = null;
      if (!message.ok) { state.selection = []; state.group = null; }
    }
    var button = request && request.button;
    delete pending[message.request_id];
    if (configActive === message.request_id) {
      configActive = null;
      if (message.ok && message.config_revision && request) {
        configQueue.forEach(function (entry) {
          if (entry.action.config_revision === request.revision) {
            entry.action.config_revision = message.config_revision;
            pending[entry.action.request_id].revision = message.config_revision;
          }
        });
        if (typeof planState !== 'undefined' && planState.revision === request.revision) planState.revision = message.config_revision;
      } else if (!message.ok) {
        if (configQueue.length) notice('Запросы из очереди панели не отправлены: ' + configQueue.length +
          '. Очередь отменена после отказа предыдущей операции.', 'warning', true);
        configQueue.forEach(function (entry) {
          var b = pending[entry.action.request_id] && pending[entry.action.request_id].button;
          if (b) { b.removeAttribute('aria-busy'); b.classList.remove('waiting'); }
          delete pending[entry.action.request_id];
        });
        configQueue = [];
      }
      pumpConfigQueue();
    }
    var a = message.a;
    if (message.conflict) notice('План изменён другим клиентом. Проверьте новые данные и повторите правку.', 'warning', true);
    if (a === 'fixtures_fetch' && !message.ok && message.ambiguous) {
      if (button) { button.removeAttribute('aria-busy'); button.classList.remove('waiting'); }
      state.fetch = {state: 'ambiguous', items: message.ambiguous, request_token: message.request_token, choices: {}};
      render();
      return;
    }
    var result = commandFeedback(message);
    var resultDialog = document.getElementById('dlg');
    if (button && resultDialog.contains(button) && resultDialog._result) resultDialog._result.textContent = result.text;
    var operation = request ? request.label : commandOperationName({a: a}, state.config);
    if (button) { button.removeAttribute('aria-busy'); button.classList.remove('waiting'); }
    if (result.sticky) notice(result.text, result.kind, true, operation, message.request_id);
    if ((!message.ok || ['select_fixtures','select_group','clear'].indexOf(a)<0) && (!request || !operationFeedback || request.serial >= operationFeedback.serial)) {
      operationFeedback = {text: operation + ': ' + result.text, kind: result.kind, sticky: result.sticky, serial: request ? request.serial : requestSerial};
    }
    if (message.ok && ['unknown','partial','failed'].indexOf(message.outcome) < 0 && !(message.command_evidence || []).some(function (value) { return value !== 'sent'; }) && ['scene_create','scene_rename','scene_delete'].indexOf(a) >= 0) { var dialog = document.getElementById('dlg'); if (dialog.open) dialog.close(); }
    if (a === 'fixtures_fetch') state.fetch = message.ok ? {state: 'done', added: message.added, missing: message.missing, total: message.total, changed:message.changed, no_id:message.no_id || []} : {state: 'error', err: message.err || 'ошибка чтения'};
    if (a === 'import_confirm_merge') {
      state.fetch = message.ok ? {state: 'done', added: message.added, missing: message.missing, total: message.total, changed:message.changed, no_id:message.no_id || []} : {state: 'error', err: message.err || 'ошибка подтверждения'};
    }
    if (a === 'ma2_read') state.ma2read = message;
    if (message.ok && a === 'ma2_import') state.ma2read = null;
    if (message.ok && a === 'ma2_import' && message.members_err) notice(message.members_err + '. Сырой ответ — в Диагностике.', 'warning');
    if (message.ok && a === 'scenes_import') notice((message.switched ? 'Открыт план шоу «' + message.switched + '». ' : '') + 'Добавлено сцен: ' + message.added + ', всего ' + message.total +
      (message.unrecognised > 0 ? '. ' + message.unrecognised + ' строк ответа не распознано — см. Диагностику' : ''), message.unrecognised > 0 ? 'warning' : 'success');
    if (message.ok && a === 'shows_list') { state.showNames = message.names || []; state.showRaw = message.raw_lines || []; state.showLocal = message.local_names || []; }
    if (a === 'show_save') state.saveReply = (message.name ? 'Шоу «' + message.name + '»: ' : '') + (message.reply || message.err || '');
    if (a === 'plan_copy' && message.ok) notice('Перенесено приборов: ' + message.copied + ', групп: ' + message.groups +
      (message.skipped.length ? '. Нет в этом шоу: ' + message.skipped.join(', ') : ''), 'success');
    if ((a === 'fixtures_fetch' || a === 'import_confirm_merge') && message.ok && (message.switched || (message.no_id || []).length)) notice(
      (message.switched ? 'Открыт план шоу «' + message.switched + '», приборы получены в него. ' : '') +
      ((message.no_id || []).length ? 'Без Fixture ID, панель ими не управляет: ' + message.no_id.join(', ') + '. Дайте им Fixture ID в патче MA2.' : ''));
    if (!message.ok && message.request_id === latestSelectionRequest && ['select_group','select_fixtures','ma2_group_go','clear'].indexOf(a) >= 0) { cancelTargetControls(); state.selection = []; state.group = null; }
  }
  validateSelectionIntent();
  render();
  Object.keys(message).forEach(function (type) {
    (listeners[type] || []).slice().forEach(function (fn) { fn(message[type], message); });
  });
}

function connect() {
  clearTimeout(reconnectTimer);
  discardPending();
  if (typeof planEndEdit === 'function' && state.sec === 'hall') planEndEdit();
  if (state.ws) state.ws.close();
  rememberSelection(); clearEvidence(); state.ma2 = 'down';
  var ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws');
  state.ws = ws;
  state.valuesRevision = -1;
  render();
  ws.onopen = function () {
    render();
    if (state.sec === 'hall' && typeof planBeginEdit === 'function') planBeginEdit();
  };
  ws.onmessage = function (event) { if (state.ws === ws) receive(JSON.parse(event.data)); };
  ws.onerror = function () { ws.close(); };
  ws.onclose = function () {
    if (state.ws !== ws) return;
    if (typeof moveStop === 'function') moveStop();
    if (storeUI) { cancelStore(); var sd = document.getElementById('dlg'); if (sd.open) sd.close(); }
    rememberSelection(); state.ma2 = 'down'; clearEvidence(); state.readFreshness = {};
    discardPending();
    render();
    reconnectTimer = setTimeout(connect, 2000);
  };
}

/* ---------- sliders: one latest-value channel each, 10 per second ---------- */
function cancelSlider(key) {
  var channel = sliderChannels[key];
  if (!channel) return;
  clearTimeout(channel.timer);
  channel.timer = null;
  channel.latest = null;
}
function flushSliders() {
  Object.keys(sliderChannels).forEach(function (key) {
    var channel = sliderChannels[key];
    if (!channel.latest) return;
    var latest = channel.latest;
    cancelSlider(key);
    if (send(latest)) channel.sent = performance.now();
  });
}
function throttleSlider(action) {
  if (featureReason(actionFeature(action.a)) || !connected()) return;
  var channel = sliderChannels[action.a] || (sliderChannels[action.a] = {timer: null, latest: null, sent: -Infinity});
  channel.latest = action;
  function flush() {
    channel.timer = null;
    var latest = channel.latest;
    channel.latest = null;
    if (latest && send(latest)) channel.sent = performance.now();
  }
  if (channel.timer !== null) return;
  var wait = Math.max(0, 100 - (performance.now() - channel.sent));
  if (wait === 0) flush(); else channel.timer = setTimeout(flush, Math.ceil(wait));
}

function selectConsoleGroup(group, button) {
  if (!connected() || !(group.ids || []).length) return false;
  if (typeof moveStop === 'function') moveStop();
  Object.keys(sliderChannels).forEach(cancelSlider);
  if (!send({a:'ma2_group_go',n:group.n},button)) return false;
  state.selection=group.ids.slice();state.group='ma2:'+group.n;
  selectionSync=requestPrefix+':'+requestSerial;
  render();return true;
}
function selectFixtures(ids) {
  if (!connected()) return false;
  cancelTargetControls();
  // The bridge rejects an empty select_fixtures list; clear removes the last selection.
  if (!send(ids.length ? {a: 'select_fixtures', ids: ids.slice()} : {a: 'clear'})) return false;
  state.selection = ids.slice();
  state.group = null;
  render();
  return true;
}

/* ---------- wiring ---------- */
document.querySelectorAll('#rail [data-sec]').forEach(function (b) {
  b.addEventListener('click', function () { go(b.dataset.sec); });
});
document.getElementById('notice').addEventListener('click',function(){notice('');});
document.getElementById('selpill-clear').addEventListener('click', function () { selectFixtures([]); });
document.addEventListener('visibilitychange',function(){if(document.hidden){cancelTargetControls();catchUpSection();}});
if (typeof window !== 'undefined') window.addEventListener('blur',function(){cancelTargetControls();catchUpSection();});
// Stop sending: works without a console link. Sliders and the queue are dropped here, the bridge drops its own.
document.getElementById('halt').addEventListener('click', function () {
  discardPending();
  sendRaw({a: state.halted ? 'resume' : 'halt'});
});
// Native suppression is reversible; the bridge owns the shared snapshot.
document.getElementById('blackout').addEventListener('click', function () {
  send({a: 'blackout'}, null);
});

on('a', function (a, message) { if (a === 'show_load' && message.ok) state.showNames = null; });
try { state.sec = localStorage.getItem('ma2.sec') || 'scenes'; } catch (error) { state.sec = 'start'; }
if (!SECTIONS[state.sec] && ['light', 'hall'].indexOf(state.sec) < 0) state.sec = 'start';
document.addEventListener('DOMContentLoaded', function () { if (state.sec === 'hall') state.sec = 'light'; connect(); });
