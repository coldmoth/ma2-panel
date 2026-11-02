/* Panel core: link to the bridge, shell (rail, top bar, banners) and the Площадка, Сцены, Шоу sections.
   light.js draws Свет, plan.js draws the hall plan and Зал, move.js the Pan/Tilt pad. */
var state = {valuesRevision: -1, master: null, readFreshness: {}, ws: null, ma2: 'down', mock: false, last: null, manual: false, page: null, scenes: {}, config: null, configN: 0,
  shown: {}, live: {}, dmx: {}, tracked: true, selection: [], group: null, halted: false, safety: null, features: {}, highlight: null,
  showLoad: {state: 'idle'}, show: {name: null}, sec: 'start', blackoutArm: false,
  fetch: null, ma2read: null, showNames: null, showRaw: [], showLocal: [], showPick: null, saveReply: '', history: []};
var listeners = {};
var pending = {};
var sliderChannels = {};
var SLIDER_ACTIONS = ['master', 'dim', 'color', 'move', 'jog', 'zoom', 'focus', 'strobe'];
var sceneFade = 0;  // scene crossfade, seconds; the scenes running now always go Off (at once or when it ends)
var fadeSeconds = 0;  // fade for jumps (quick % buttons, colour swatches, a tap on the wheel); drags never fade
var reconnectTimer = null;
var updaters = [];     // value refreshers of the current section; rebuilt with it
var sectionKey = null;
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
    else if (k.slice(0, 2) === 'on') el.addEventListener(k.slice(2), v);
    else if (k === 'style') Object.keys(v).forEach(function (s) { el.style.setProperty(s, v[s]); });
    else if (k in el && typeof v !== 'string') el[k] = v;
    else el.setAttribute(k, v === true ? '' : v);
  });
  add.apply(null, [el].concat(Array.prototype.slice.call(arguments, 2)));
  return el;
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
function connected() { return bridgeUp() && linkReady() && !state.halted && !(state.showLoad && state.showLoad.state === 'loading'); }
function fixtures() { return (state.config && state.config.fixtures) || []; }
function fixture(id) { return fixtures().filter(function (f) { return f.id === id; })[0] || null; }
// A head: marked by the operator (moves), or Pan/Tilt among the attribute names from MA2. Same rule as commands.can_move.
function canMove(f) { return f.moves === true || (f.params || []).some(function (p) { return /pan|tilt/i.test(p); }); }
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
  if (state.showLoad && state.showLoad.state === 'loading') return {dot:'wait',text:'Загрузка шоу'};
  return {dot:state.ma2 === 'logged_in' ? 'on' : state.ma2 === 'down' ? '' : 'wait',text:short[state.ma2] || state.ma2};
}

// Optional button gets "· готово" or the error after the reply.
function send(action, button) {
  if (!connected() || featureReason(actionFeature(action.a))) return false;
  if (button && button.getAttribute('aria-busy') === 'true') return false;
  // Waiting slider values go out before any other action, so the bridge sees them in the user's order.
  if (SLIDER_ACTIONS.indexOf(action.a) < 0) flushSliders();
  try { state.ws.send(JSON.stringify(action)); } catch (error) { return false; }
  if (SLIDER_ACTIONS.indexOf(action.a) < 0) (pending[action.a] || (pending[action.a] = [])).push(button || null);
  if (button) { button.setAttribute('aria-busy', 'true'); button.classList.add('waiting'); }
  return true;
}
function sendRaw(action) {  // halt / resume / link: work without a console link
  if (bridgeUp()) state.ws.send(JSON.stringify(action));
}
function busy(a) { return !!(pending[a] || []).length; }

function feedback(button, ok, error) {
  if (button) { button.removeAttribute('aria-busy'); button.classList.remove('waiting'); }
  notice(ok ? 'Действие выполнено' : (error || 'Ошибка команды'), ok ? 'success' : 'error', !ok);
}
function notice(text, kind, sticky) {
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
  halt.textContent = '';
  add(halt, [icon(state.halted ? 'play' : 'pause'), state.halted ? 'Возобновить передачу' : 'Стоп передачи']);
  halt.setAttribute('aria-pressed', String(!!state.halted));
  halt.disabled = !bridgeUp();
  var bo = document.getElementById('blackout');
  bo.textContent = '';
  add(bo, [icon('power'), state.blackoutArm ? 'Ещё раз — погасить' : 'Погасить свет']);
  bo.disabled = !connected() || !!featureReason('scenes');
  renderBanners();
  renderSection();
  updaters.forEach(function (fn) { fn(); });
}

function renderBanners() {
  var b = document.getElementById('banners');
  b.textContent = '';
  var hl = state.highlight || {};
  if (hl.state === 'stuck') b.appendChild(h('div', {class: 'banner bad', role: 'alert'}, icon('alert'),
    'Подсветка не снята' + (hl.reason ? ': ' + hl.reason : '') + '. Кнопка снимает её командой Off: у приборов зала пропадёт и то, что выставлено на пульте вручную. Сначала сохраните шоу или запишите сцену.',
    h('button', {class: 'btn small', type: 'button', disabled: !connected(), onclick: function () { if (confirm('Снять подсветку командой Off? У приборов зала пропадёт и то, что выставлено на пульте вручную.')) send({a: 'highlight_off'}); }}, 'Снять подсветку')));
  if (bridgeUp() && !linkReady()) b.appendChild(h('div', {class: 'banner ' + (state.ma2 === 'login_failed' ? 'bad' : 'warn'), role: 'alert'}, icon('alert'),
    (LINK_TEXT[state.ma2] || state.ma2) + '. Управление недоступно' + (state.manual ? '.' : ', мост переподключается сам.')));
  if (!bridgeUp()) b.appendChild(h('div', {class: 'banner bad', role: 'alert'}, icon('alert'), 'Нет связи с мостом. Панель переподключается каждые 2 с.'));
  if (bridgeUp() && state.halted) b.appendChild(h('div', {class: 'banner warn', role: 'alert'}, icon('pause'),
    'Передача остановлена: панель ничего не отправляет на MA2, очередь удалена. Свет на пульте не менялся.',
    h('button', {class: 'btn small', type: 'button', onclick: function () { sendRaw({a: 'resume'}); }}, 'Возобновить')));
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
  var hl = state.highlight || {};
  var key = JSON.stringify([state.sec, state.configN, state.selection, state.ma2, state.halted, state.manual, state.showLoad, hl.state, hl.target,
    state.show, state.scenes, state.safety, state.features, state.readFreshness, state.fetch, state.ma2read, state.showNames, state.showPick, state.saveReply, state.page, sceneFade,
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
  if (focused && el.contains(focused) && (focused.tagName === 'INPUT' && focused.type !== 'range' && focused.type !== 'checkbox' || focused.tagName === 'TEXTAREA')) return;
  if (typeof moveStop === 'function') moveStop();
  sectionKey = key;
  // A rebuild must not throw lists back to the top: a tap on a fixture low in the list keeps the list where it was.
  var scroll = {page: el.scrollTop};
  el.querySelectorAll('[data-scroll]').forEach(function (n) { scroll[n.getAttribute('data-scroll')] = n.scrollTop; });
  var sameSec = renderSection.sec === state.sec;
  el.textContent = '';
  updaters = [];
  el.className = 'page' + (state.sec === 'light' || state.sec === 'hall' ? ' fill' : '');
  SECTIONS[state.sec](el);
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
  var last = state.last;
  if (last) add(conn, h('p', {class: 'note ' + (last.status === 'error' ? 'bad' : '')}, 'Последняя команда ' + last.t + ': ' + last.cmd + ' — ' + (RESULT_TEXT[last.status] || last.status)));

  var canFetch = ready && safe('allow_fixture_read') && !busy('fixtures_fetch');
  var f = state.fetch;
  var eq = h('section', {class: 'card'}, h('h2', {}, 'Оборудование из MA2'),
    h('p', {class: 'note'}, 'Читаю приборы текущего патча: ID, имя, тип и параметры. Это не поиск RDM. Повторное чтение сохраняет расстановку, добавляет новые приборы и помечает пропавшие.'),
    h('div', {class: 'row'}, h('button', {class: 'btn' + (hasFixtures() ? '' : ' primary'), type: 'button', disabled: !canFetch, onclick: function (e) {
      state.fetch = {state: 'loading'}; send({a: 'fixtures_fetch'}, e.currentTarget); render();
    }}, icon(hasFixtures() ? 'refresh' : 'download'), busy('fixtures_fetch') ? 'Читаю патч…' : hasFixtures() ? 'Получить снова' : 'Получить оборудование из MA2')),
    !safe('allow_fixture_read') ? h('p', {class: 'note warn'}, 'Чтение приборов выключено. Включите «Разрешить получение приборов из MA2» в ', h('a', {href: 'settings.html'}, 'Настройках'), '.') : null,
    f && f.state === 'done' ? h('p', {class: 'ok'}, 'Получено из MA2: добавлено ' + f.added + ', пропало ' + f.missing + ', всего ' + f.total) : null,
    f && f.state === 'error' ? h('p', {class: 'bad', role: 'alert'}, 'Не получено из MA2: ' + f.err) : null,
    f && f.state === 'error' ? h('p', {class: 'note'}, h('a', {href: 'diag.html'}, 'Открыть диагностику')) : null,
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
  return Array.isArray(pages) ? pages : [];
}
SECTIONS.scenes = function (el) {
  var ready = connected();
  var scenes = (state.config && state.config.scenes) || [];
  var addBtn = h('button', {class: 'btn primary', type: 'button', disabled: !ready || !!featureReason('store'),
    title: 'Записать свет, который выставлен сейчас, в новую сцену', onclick: function () { openStore(state.page || 1); }}, '+ Добавить');
  var head = h('div', {class: 'ph'}, h('h1', {}, 'Сцены'), addBtn);
  var master = masterControl();
  add(head, h('div', {class: 'card master-card'}, master));
  add(el, head);
  add(el, h('div', {class: 'card fade', role: 'group', 'aria-label': 'Плавный переход между сценами',
    title: 'Сцена включается плавно за это время. Время сцены в самом пульте при этом заменяется.'},
    h('span', {class: 'note'}, 'Переход'), [0, 2, 5, 10].map(function (sec) {
      return h('button', {class: 'btn small', type: 'button', 'aria-pressed': String(sec === sceneFade),
        onclick: function () { sceneFade = sec; render(); }}, sec ? sec + ' с' : 'сразу');
    })));
  if (!scenes.length) {
    add(el, h('div', {class: 'card'}, h('p', {}, 'Сцен в панели нет. Прочитайте их из MA2 на «Площадке».'), h('div', {}, h('button', {class: 'btn', type: 'button', onclick: function () { go('start'); }}, 'Открыть «Площадку»'))));
    return;
  }
  var tiles = h('div', {class:'tiles'});
  scenes.forEach(function (scene, index) {
    var run = !!state.scenes[scene.id];
    var allowed = !state.safety || state.safety.mode === 'full' || (state.safety.scenes || []).indexOf(String(scene.exec)) >= 0;
    var label = scene.label || 'Без названия';
    var tile = h('button', {class:'tile' + (run ? ' run' : '') + (scene.write_error ? ' write-error' : ''), type:'button', 'data-scene':scene.id,
      'aria-label': (index + 1) + '. ' + label + (run ? ', идёт' : ''),
      disabled: !ready || !allowed || !!featureReason('scenes') || !!scene.write_error, onclick:function() {
        var action = {a:'scene_go',id:scene.id,swap:scenes.filter(function(o){return o.id !== scene.id && state.scenes[o.id];}).map(function(o){return o.id;})};
        if (sceneFade) action.fade = sceneFade;
        send(action,tile);
      }}, h('span',{class:'scene-number'},index + 1), h('span',{class:'scene-name'},label),
      h('span',{class:'scene-state'},scene.write_error ? 'Запись не подтверждена' : run ? 'Идёт' : 'Запустить'));
    var controls = h('div',{class:'tile-controls'},h('button',{class:'btn small ghost',type:'button',disabled:!ready,
      onclick:function(){openSceneEdit(scene);}},'Изменить'));
    if (run) add(controls,h('button',{class:'btn small off',type:'button','data-scene':scene.id,disabled:!ready,
      'aria-label':'Выключить сцену «' + label + '»',onclick:function(e){send({a:'scene_off',id:scene.id},e.currentTarget);}},'Выключить'));
    add(tiles,h('div',{class:'tile-wrap'},tile,controls));
  });
  add(el,tiles);
};

function masterControl() {
  var activeGesture = false;
  var out = h('span', {class: 'val'});
  var input = h('input', {type: 'range', min: 0, max: 100, value: 100, 'aria-label': 'Общая яркость', oninput: function (e) {
    out.textContent = e.target.value + '%'; out.classList.remove('unknown'); setFill(input, Number(e.target.value));
    throttleSlider({a: 'master', v: Number(e.target.value), fade: 0});
  }});
  ['pointerdown','keydown'].forEach(function(event) { input.addEventListener(event,function(){activeGesture=true;}); });
  ['pointerup','pointercancel','lostpointercapture','keyup','blur'].forEach(function(event) { input.addEventListener(event,function(){activeGesture=false;}); });
  updaters.push(function () {
    input.disabled = !connected() || !(state.safety && state.safety.master);
    input.title = state.safety && !state.safety.master ? 'Общая яркость заблокирована (allow_master)' : '';
    out.textContent = state.master === null ? 'неизвестно' : Math.round(state.master) + '%';
    out.classList.toggle('unknown', state.master === null);
    if (!activeGesture) setFill(input, state.master);
  });
  return h('div', {class: 'master'}, h('div', {class: 'vrow'}, h('b', {}, 'Общая яркость'), out), input);
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
    if (!confirm('Перезаписать сцену ' + s.exec + ' светом, который выставлен сейчас? Старое содержимое пропадёт.')) return;
    if (send({a: 'scene_create', label: label, page: pageOf(s), exec: String(s.exec), confirm: String(s.exec), replace: true}, rewrite)) { /* close on reply */ }
  }}, icon('save'), 'Перезаписать текущим светом');
  d.textContent = '';
  add(d, h('div', {class: 'dlg'}, h('h2', {}, s.label || 'Без названия'),
    s.write_error ? h('p',{class:'note warn'},s.write_error) : null,
    h('div', {class: 'field'}, h('label', {for: 'scene-name'}, 'Имя сцены'), name),
    h('p', {class:'note'}, 'Адрес на MA2: ' + s.exec + '. Перезапись сохранит текущий выход пульта.'),
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
  var progress = h('p',{class:'note',role:'status'},'Панель найдёт свободное место на MA2. Пока ничего не записывается.');
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
      progress.textContent = 'Запишется текущий выход пульта. Место на MA2: ' + slot.exec + '. Подтвердите запись.';
    } else {
      ui.slot = null;
      progress.textContent = slot.state === 'searching' ? 'Ищу свободное место… проверено: ' + (slot.checked || 0) : slot.err || 'Поиск отменён';
    }
  };
  d.textContent = '';
  add(d,h('div',{class:'dlg'},h('h2',{},'Новая сцена'),h('div',{class:'field'},h('label',{for:'store-name'},'Название'),name),progress,
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
    return h('div', {class: 'grow-row'}, h('span', {class: 'note'}, e.t), h('span', {class: 'nm'}, e.what),
      e.undo ? h('button', {class: 'btn small', type: 'button', disabled: !linkReady() || e.done, onclick: function (ev) { send({a: 'undo', n: e.n}, ev.currentTarget); }},
        e.done ? 'Откачено' : 'Откатить') : h('span', {class: 'note'}, 'не откатывается'));
  })));
};

/* ---------- Шоу ---------- */
// The typed name only proves intent: a tablet keyboard capitalises the first letter and adds a space after a suggestion.
function sameName(typed, name) { return typed.trim().replace(/\s+/g, ' ').toLowerCase() === name.toLowerCase(); }
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
    var ack = h('input', {type: 'checkbox'});
    var conf = h('input', {id: 'load-confirm', autocomplete: 'off', autocapitalize: 'off', autocorrect: 'off', spellcheck: 'false'});
    var load = h('button', {class: 'btn blackout', type: 'button', disabled: true, onclick: function () {
      if (send({a: 'show_load', name: pickName, confirm_name: pickName, ack_unsaved: ack.checked}, load)) { state.showPick = null; }
    }}, 'Загрузить «' + pickName + '»');
    var check = function () { load.disabled = !(connected() && safe('allow_show_load') && ack.checked && sameName(conf.value, pickName)); };
    ack.addEventListener('change', check); conf.addEventListener('input', check);
    add(list, h('div', {class: 'card', style: {background: 'var(--s2)'}}, h('h3', {style: {color: 'var(--ink)'}}, 'Загрузка «' + pickName + '» заменит всё на MA2'),
      h('p', {class: 'note warn'}, 'MA2 не сообщает о несохранённых изменениях текущего шоу. Если они нужны, сначала сохраните его.'),
      !safe('allow_show_load') ? h('p', {class: 'note warn'}, 'Загрузка выключена в настройках (allow_show_load).') : null,
      h('label', {class: 'chk'}, ack, 'Несохранённые изменения текущего шоу пропадут'),
      h('div', {class: 'field'}, h('label', {for: 'load-confirm'}, 'Введите имя загружаемого шоу'), conf), h('div', {}, load)));
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
  add(el, h('div', {class: 'shows'}, cur, list, copy));
};

/* ---------- link ---------- */
function discardPending() {
  Object.keys(pending).forEach(function (a) { pending[a].forEach(function (b) { if (b) { b.removeAttribute('aria-busy'); b.classList.remove('waiting'); } }); });
  pending = {};
  Object.keys(sliderChannels).forEach(cancelSlider);
}

function receive(message) {
  if ('values_revision' in message) {
    if (message.values_revision <= state.valuesRevision) return;
    state.valuesRevision = message.values_revision;
  }
  if (message.status) {
    state.readFreshness = message.status.read_freshness || {};
    state.highlight = message.status.highlight || {state: 'idle', available: []};
    state.showLoad = message.status.show_load || {state: 'idle'};
    if (state.showLoad.state === 'loading') { discardPending(); state.selection = []; state.group = null; state.scenes = {}; }
    state.show = message.status.show || {name: null, source: 'unknown'};
    state.ma2 = message.status.ma2; state.login = message.status.login;
    state.mock = message.status.mock;
    state.halted = !!message.status.halted;
    state.safety = message.status.safety || null;
    state.features = message.status.features || {};
    state.noAttr = message.status.no_attr || {};
    state.manual = !!message.status.manual;
    if ('last' in message.status) state.last = message.status.last;
    if ((!linkReady() || state.halted || state.showLoad.state === 'loading') && storeUI) { cancelStore(); var sd = document.getElementById('dlg'); if (sd.open) sd.close(); }
    if (!linkReady() || state.halted) { if (typeof moveStop === 'function') moveStop(); discardPending(); }
  }
  if (message.last) state.last = message.last;
  if (message.config) {
    if (state.config && state.config.show !== message.config.show) {
      if (storeUI) { cancelStore(); var sd = document.getElementById('dlg'); if (sd.open) sd.close(); }
      // Another show's plan: old selection and values never carry over.
      state.master = null; state.selection = []; state.group = null; state.shown = {}; state.fetch = null; state.ma2read = null;
      if (typeof planState !== 'undefined') planState.cur = 0;
      if (typeof planEndEdit === 'function' && state.sec === 'hall') planEndEdit();
    }
    state.config = message.config;
    state.configN++;
  }
  if ('master' in message) state.master = message.master;
  if (message.shown) state.shown = message.shown;
  if (message.history) state.history = message.history;
  if (message.live) state.live = message.live;  // what the desk outputs (DMX read-back), every fixture
  if (message.dmx) state.dmx = message.dmx;
  if ('tracked' in message) state.tracked = message.tracked;
  if ('page' in message) state.page = message.page;
  if (message.running) Object.assign(state.scenes, message.running);
  if ('ok' in message) {
    var queue = pending[message.a];
    var button = queue && queue.shift();
    if (button) feedback(button, message.ok, message.err || 'ошибка');
    var a = message.a;
    if (message.ok && ['scene_create','scene_rename','scene_delete'].indexOf(a) >= 0) { var dialog = document.getElementById('dlg'); if (dialog.open) dialog.close(); }
    if (message.ok && button && (a === 'scene_go' || a === 'scene_off')) state.scenes[button.dataset.scene] = a === 'scene_go';
    if (message.ok && a === 'blackout') state.scenes = {};
    if (a === 'fixtures_fetch') state.fetch = message.ok ? {state: 'done', added: message.added, missing: message.missing, total: message.total} : {state: 'error', err: message.err || 'ошибка чтения'};
    if (a === 'ma2_read') state.ma2read = message;
    if (message.ok && a === 'ma2_import') state.ma2read = null;
    if (message.ok && a === 'ma2_import' && message.members_err) notice(message.members_err + '. Сырой ответ — в Диагностике.', 'warning');
    if (message.ok && a === 'scenes_import') notice((message.switched ? 'Открыт план шоу «' + message.switched + '». ' : '') + 'Добавлено сцен: ' + message.added + ', всего ' + message.total +
      (message.unrecognised > 0 ? '. ' + message.unrecognised + ' строк ответа не распознано — см. Диагностику' : ''), message.unrecognised > 0 ? 'warning' : 'success');
    if (message.ok && a === 'shows_list') { state.showNames = message.names || []; state.showRaw = message.raw_lines || []; state.showLocal = message.local_names || []; }
    if (a === 'show_save') state.saveReply = (message.name ? 'Шоу «' + message.name + '»: ' : '') + (message.reply || message.err || '');
    if (a === 'plan_copy' && message.ok) notice('Перенесено приборов: ' + message.copied + ', групп: ' + message.groups +
      (message.skipped.length ? '. Нет в этом шоу: ' + message.skipped.join(', ') : ''), 'success');
    if (a === 'fixtures_fetch' && message.ok && (message.switched || (message.no_id || []).length)) notice(
      (message.switched ? 'Открыт план шоу «' + message.switched + '», приборы получены в него. ' : '') +
      ((message.no_id || []).length ? 'Без Fixture ID, панель ими не управляет: ' + message.no_id.join(', ') + '. Дайте им Fixture ID в патче MA2.' : ''));
    if (!message.ok && button) notice(message.err || 'Ошибка команды', 'error', true);
    if (!message.ok && (a === 'select_group' || a === 'select_fixtures' || a === 'clear')) { state.selection = []; state.group = null; notice(message.err || 'Ошибка выбора'); }
    else if (!message.ok && !button && SLIDER_ACTIONS.indexOf(a) < 0) notice(message.err || 'Ошибка команды');
    else if (!message.ok && SLIDER_ACTIONS.indexOf(a) >= 0) notice((a === 'master' ? 'Общая яркость' : a) + ': ' + (message.err || 'ошибка'));
  }
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
  state.scenes = {}; state.selection = []; state.group = null; state.ma2 = 'down';
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
    state.ma2 = 'down'; state.master = null; state.readFreshness = {};
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

function selectFixtures(ids) {
  if (!connected()) return false;
  cancelSlider('dim'); cancelSlider('color');
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
// Stop sending: works without a console link. Sliders and the queue are dropped here, the bridge drops its own.
document.getElementById('halt').addEventListener('click', function () {
  discardPending();
  sendRaw({a: state.halted ? 'resume' : 'halt'});
});
// Blackout: second press within 3 s. A single accidental tap does nothing.
document.getElementById('blackout').addEventListener('click', function (event) {
  if (!connected()) return;
  if (!state.blackoutArm) {
    state.blackoutArm = true;
    render();
    setTimeout(function () { state.blackoutArm = false; render(); }, 3000);
    return;
  }
  state.blackoutArm = false;
  send({a: 'blackout'}, null);
  render();
});
on('a', function (a, message) { if (a === 'show_load' && message.ok) state.showNames = null; });
try { state.sec = localStorage.getItem('ma2.sec') || 'start'; } catch (error) { state.sec = 'start'; }
if (!SECTIONS[state.sec] && ['light', 'hall'].indexOf(state.sec) < 0) state.sec = 'start';
document.addEventListener('DOMContentLoaded', function () { if (state.sec === 'hall') state.sec = 'light'; connect(); });
