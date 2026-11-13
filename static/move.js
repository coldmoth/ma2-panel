/* Pan/Tilt pad, Zoom and Focus sliders and panel position presets, shown in the «Позиция и луч» card of Свет. */
// Spring joystick: deflection is speed, not position, so it works without knowing where the head points
// and the desk can turn the same head at the same time. ponytail: скорости подобрать в зале.
var JOY_SPEED = 90;   // °/с при полном отклонении
var JOY_FINE = 0.15;  // доля скорости в режиме «Точно»
var JOY_DEAD = 0.08;  // мёртвая зона у центра
var moveState = {els: null, built: null, drag: null, fine: false, mirror: false, settingsOpen: false, presetsOpen: false, manage: false, mode: 'joystick'};

function moveHeads() {
  var byId = {};
  ((state.config && state.config.fixtures) || []).forEach(function (f) {
    if (canMove(f)) byId[f.id] = f;
  });
  return state.selection.filter(function (id) { return byId[id]; }).map(function (id) { return byId[id]; });
}

function moveValue(id, attr) {
  var shown = state.shown[id];
  return shown && typeof shown[attr] === 'number' ? shown[attr] : null;
}

function moveClip(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }

function moveEl(tag, className, text) {
  var el = document.createElement(tag);
  if (className) el.className = className;
  if (text) el.textContent = text;
  return el;
}

// Stick vector -1…1 from the touch-down point; a touch never jumps the head, the knob shows the offset.
function joyVector(event) {
  var drag = moveState.drag, r = moveState.els.pad.getBoundingClientRect(), reach = Math.min(r.width, r.height) / 2;
  var x = (event.clientX - drag.x) / reach, y = (drag.y - event.clientY) / reach, len = Math.hypot(x, y);
  return len > 1 ? {x: x / len, y: y / len} : {x: x, y: y};
}

function joyRate(v) {  // squared curve: fine near the centre, fast at the edge
  var a = Math.abs(v);
  return a < JOY_DEAD ? 0 : Math.sign(v) * Math.pow((a - JOY_DEAD) / (1 - JOY_DEAD), 2) * JOY_SPEED * (moveState.fine ? JOY_FINE : 1);
}

function joyTick() {
  var drag = moveState.drag;
  if (!drag) return;
  var now = performance.now(), dt = Math.min(0.25, (now - drag.t) / 1000);
  drag.t = now;
  var pan = Math.round(joyRate(drag.vx) * dt * 100) / 100, tilt = Math.round(joyRate(drag.vy) * dt * 100) / 100;
  if (pan || tilt) send({a: 'jog', pan: pan, tilt: tilt, mirror: moveState.mirror});
}

// Separate channels prevent a quick Pan then Tilt change from dropping either target.
function moveAxisCancel(axis) {
  clearTimeout(axis.timer); axis.timer = null; axis.latest = null;
}
function moveAxisSend(axis, action) {
  axis.latest = {action: action, ids: state.selection.join(','), config: state.config};
  function flush() {
    axis.timer = null;
    var latest = axis.latest; axis.latest = null;
    if (!latest || axis.blocked || axis.input.disabled || !connected() || featureReason('move') ||
        moveState.mode !== 'absolute' || latest.ids !== state.selection.join(',') || latest.config !== state.config) return;
    if (send(latest.action)) axis.sent = performance.now();
  }
  if (axis.timer !== null) return;
  var wait = Math.max(0, 100 - (performance.now() - axis.sent));
  if (!wait) flush(); else axis.timer = setTimeout(flush, Math.ceil(wait));
}

function moveStop() {
  if (moveState.els && moveState.els.axes) Object.keys(moveState.els.axes).forEach(function (attr) {
    var axis = moveState.els.axes[attr];
    axis.blocked = true; axis.gesture = null; moveAxisCancel(axis);
  });
  var drag = moveState.drag;
  moveState.drag = null;
  if (drag) {
    clearInterval(drag.timer);
    try { moveState.els.pad.releasePointerCapture(drag.pointer); } catch (error) {}
  }
  if (moveState.frame && typeof cancelAnimationFrame === 'function') cancelAnimationFrame(moveState.frame);
  moveState.frame = null;
  if (typeof cancelSlider === 'function') cancelSlider('jog');
}
document.addEventListener('visibilitychange', function () { if (document.hidden) moveStop(); });

function moveShell(el) {
  if (moveState.els) moveStop();
  el.textContent = '';
  var els = {
    chips: moveEl('div', 'move-chips'),
    hint: moveEl('p', 'muted'),
    note: moveEl('p', 'plan-note', 'Джойстик двигает от текущего положения. Отпустите — движение остановится.'),
    tools: moveEl('div', 'move-steps'), fine: moveEl('button', '', 'Точно'), flips: {},
    range: moveEl('p', 'muted'), steps: [], aim: {},
    padCol: moveEl('div', 'pad-col'),
    pad: moveEl('div', 'pad'),
    dot: moveEl('span', 'pad-dot'),
    msg: moveEl('span', 'pad-msg'),
    readout: moveEl('p', 'pad-readout'),
    sliders: {},
    presets: moveEl('div', 'move-presets'),
    save: moveEl('button', '', 'Запомнить пресет')
  };
  els.pad.dataset.feature = 'move';
  if (typeof watchControl === 'function') watchControl(els.pad);
  els.pad.appendChild(els.dot);
  els.pad.appendChild(els.msg);
  els.pad.setAttribute('aria-label', 'Пад Pan и Tilt');
  els.padCol.appendChild(els.pad);
  els.padCol.appendChild(els.readout);
  els.padCol.appendChild(els.tools);
  els.fine.type = 'button';
  els.fine.addEventListener('click', function () { moveState.fine = !moveState.fine; renderMove(el); });
  els.tools.appendChild(els.fine);
  els.mirror = moveEl('button', '', 'Зеркально');
  els.mirror.type = 'button';
  els.mirror.addEventListener('click', function () { moveState.mirror = !moveState.mirror; renderMove(el); });
  els.tools.appendChild(els.mirror);
  var settings = moveEl('details', 'move-settings');
  settings.open = moveState.settingsOpen;
  var settingsTitle = moveEl('summary', '', 'Настройки движения');
  els.inversions = moveEl('span', 'active-inversions');
  settingsTitle.appendChild(els.inversions); settings.appendChild(settingsTitle);
  settings.addEventListener('toggle', function () { moveState.settingsOpen = settings.open; });
  var flips = moveEl('div', 'move-steps'); settings.appendChild(flips);
  els.flipHint = moveEl('p', 'note'); settings.appendChild(els.flipHint);
  // Hung upside down: the bridge flips the sign of every step for these heads (joystick and arrows).
  [['flip_pan', 'Pan наоборот'], ['flip_tilt', 'Tilt наоборот']].forEach(function (pair) {
    var button = moveEl('button', '', pair[1]);
    button.type = 'button';
    button.dataset.feature = 'move';
    button.addEventListener('click', function () {
      var heads = moveHeads(), on = !heads.every(function (f) { return f[pair[0]] === true; });
      heads.forEach(function (f) { var a = {a: 'fixture_flag', id: f.id}; a[pair[0]] = on; send(a); });
      renderMove(el);
    });
    els.flips[pair[0]] = button;
    flips.appendChild(button);
  });
  [els.chips, els.hint].forEach(function (n) { el.appendChild(n); });
  var modes = moveEl('div', 'move-modes');
  els.modeJoystick = moveEl('button', '', 'Джойстик');
  els.modeAbsolute = moveEl('button', '', 'Положение');
  [[els.modeJoystick, 'joystick'], [els.modeAbsolute, 'absolute']].forEach(function (pair) {
    pair[0].type = 'button';
    pair[0].addEventListener('click', function () { moveStop(); moveState.mode = pair[1]; renderMove(el); });
    modes.appendChild(pair[0]);
  });
  el.appendChild(modes);
  var primary = moveEl('div', 'move-primary'); primary.appendChild(els.padCol); el.appendChild(primary);
  els.primary = primary;
  els.absolute = moveEl('div', 'move-absolute'); els.axes = {};
  ['pan', 'tilt'].forEach(function (attr) {
    var label = moveEl('label', 'move-axis'), name = moveEl('span', '', attr === 'pan' ? 'Pan' : 'Tilt');
    var output = moveEl('output'), input = moveEl('input');
    input.type = 'range'; input.min = 0; input.max = 100; input.step = 0.1; input.dataset.feature = 'move';
    if (typeof watchControl === 'function') watchControl(input);
    input.setAttribute('aria-label', (attr === 'pan' ? 'Pan' : 'Tilt') + ' — абсолютное положение');
    var axis = {input: input, output: output, blocked: false, gesture: null, timer: null, latest: null, sent: -Infinity};
    els.axes[attr] = axis;
    input.addEventListener('pointerdown', function (event) {
      if (input.disabled || event.button !== 0) return;
      axis.blocked = false;
      axis.gesture = {pointer: event.pointerId, ids: state.selection.join(','), config: state.config};
    });
    input.addEventListener('keydown', function () { if (!input.disabled) axis.blocked = false; });
    input.addEventListener('input', function () {
      if (input.disabled || axis.blocked || !connected() || featureReason('move') || moveState.mode !== 'absolute') return;
      if (axis.gesture && (axis.gesture.ids !== state.selection.join(',') || axis.gesture.config !== state.config)) {
        axis.blocked = true; return;
      }
      var spec = state.config.attrs[attr] || {}, percent = moveClip(Number(input.value), 0, 100);
      if (!Number.isFinite(percent) || !(spec.max > spec.min)) return;
      var value = Math.round((spec.min + percent * (spec.max - spec.min) / 100) * 10) / 10;
      value = moveClip(value, spec.min, spec.max);
      var action = {a: 'aim'}; action[attr] = value;
      moveAxisSend(axis, action);
      setFill(input, percent); output.textContent = value + '° · отправляется';
    });
    input.addEventListener('pointerup', function () { axis.gesture = null; });
    ['pointercancel', 'lostpointercapture'].forEach(function (type) {
      input.addEventListener(type, function () { if (axis.gesture) { axis.blocked = true; axis.gesture = null; moveAxisCancel(axis); } });
    });
    label.appendChild(name); label.appendChild(output); label.appendChild(input); els.absolute.appendChild(label);
  });
  els.absolute.appendChild(moveEl('p', 'note', 'Абсолютные градусы. Зеркальность и «наоборот» действуют только на джойстик и шаги.'));
  els.absolute.appendChild(moveEl('p', 'muted', 'Показано последнее отправленное панелью; изменения на пульте здесь не видны.'));
  el.appendChild(els.absolute);
  var steps = moveEl('div', 'step-cross');
  steps.appendChild(moveEl('span', 'step-caption', 'Шаг 1°'));
  ['pan', 'tilt'].forEach(function (attr) {
    [-1, 1].forEach(function (dir) {
      var button = moveEl('button');
      button.type = 'button';
      button.dataset.feature = 'move';
      button.addEventListener('click', function () { send({a: 'nudge', attr: attr, dir: dir, step: 1, mirror: moveState.mirror}, button); });
      button.textContent = attr === 'pan' ? (dir === 1 ? '→' : '←') : (dir === 1 ? '↑' : '↓');
      button.className = 'step-' + attr + '-' + (dir === 1 ? 'plus' : 'minus');
      button.setAttribute('aria-label', (attr === 'pan' ? 'Pan' : 'Tilt') + (dir === 1 ? ' +1°' : ' −1°'));
      els.steps.push({button: button, attr: attr, dir: dir});
      steps.appendChild(button);
    });
  });
  primary.appendChild(steps);
  settings.appendChild(els.note); settings.appendChild(els.range);
  el.appendChild(settings);
  var optics = moveEl('div', 'move-optics'); el.appendChild(optics);
  [['zoom', 'Zoom'], ['focus', 'Фокус']].forEach(function (pair) {
    var label = moveEl('label', 'move-slider');
    var name = moveEl('span', '', pair[1]);
    var input = moveEl('input');
    input.type = 'range';
    input.dataset.feature = pair[0];
    input.min = 0;
    input.max = 100;
    input.addEventListener('input', function () {
      setFill(input, Number(input.value));
      throttleSlider({a: pair[0], v: Number(input.value)});
    });
    label.appendChild(name);
    label.appendChild(input);
    optics.appendChild(label);
    els.sliders[pair[0]] = input;
  });
  var presetDetails = moveEl('details', 'preset-details');
  presetDetails.open = moveState.presetsOpen;
  presetDetails.addEventListener('toggle', function () { moveState.presetsOpen = presetDetails.open; });
  els.presetTitle = moveEl('summary'); presetDetails.appendChild(els.presetTitle);
  els.manage = moveEl('button', 'btn small ghost', 'Управлять пресетами');
  els.manage.type = 'button';
  els.manage.addEventListener('click', function () { moveState.manage = !moveState.manage; movePresets(); });
  presetDetails.appendChild(els.presets); presetDetails.appendChild(els.manage);
  el.appendChild(presetDetails);
  els.save.type = 'button';
  els.save.dataset.feature = 'move';
  els.save.dataset.label = els.save.textContent;
  els.save.addEventListener('click', function () {
    var label = prompt('Название пресета');
    if (label !== null) send({a: 'preset_save', label: label}, els.save);
  });
  presetDetails.appendChild(els.save);
  els.saveHint = moveEl('p', 'note', 'Позиция неизвестна: сохранить пресет пока нельзя.');
  presetDetails.appendChild(els.saveHint);

  els.pad.addEventListener('pointerdown', function (event) {
    if (els.pad.classList.contains('off') || moveState.drag || event.button !== 0) return;
    event.preventDefault();
    try { els.pad.setPointerCapture(event.pointerId); } catch (error) {}  // capture is a nicety: the stick works without it
    moveState.drag = {pointer: event.pointerId, x: event.clientX, y: event.clientY, vx: 0, vy: 0, t: performance.now(),
      timer: setInterval(joyTick, 100)};
  });
  els.pad.addEventListener('pointermove', function (event) {
    var drag = moveState.drag;
    if (!drag || drag.pointer !== event.pointerId) return;
    var v = joyVector(event);
    drag.vx = v.x;
    drag.vy = v.y;
    // Touch fires many moves per frame: draw once per frame.
    if (!moveState.frame) moveState.frame = requestAnimationFrame(function () { moveState.frame = 0; renderMove(el); });
  });
  function end(event) {
    var drag = moveState.drag;
    if (!drag || drag.pointer !== event.pointerId) return;
    joyTick();
    clearInterval(drag.timer);
    moveState.drag = null;  // the knob springs back to the centre; the head stays where it is
    renderMove(el);
  }
  ['pointerup', 'pointercancel', 'lostpointercapture'].forEach(function (type) { els.pad.addEventListener(type, end); });
  moveState.root = el;
  moveState.els = els;
  moveState.built = null;
}

function movePresets() {
  var revision = state.config && state.config.revision;
  var box = moveState.els.presets;
  box.textContent = '';
  (state.config.presets || []).forEach(function (preset) {
    var button = moveEl('button', '', preset.label);
    button.type = 'button';
    button.dataset.label = preset.label;
    button.dataset.preset = '';
    button.dataset.feature = 'move';
    if (moveState.manage) {
      var row = moveEl('div', 'preset-manage-row');
      row.appendChild(moveEl('span', '', preset.label));
      var del = moveEl('button', 'btn small danger', 'Удалить'); del.type = 'button';
      del.setAttribute('aria-label', 'Удалить пресет ' + preset.label);
      del.disabled = !connected();
      del.addEventListener('click', function () {
        if (confirm('Удалить пресет «' + preset.label + '» из панели?')) send({a:'preset_delete',id:preset.id,config_revision:revision}, del);
      });
      row.appendChild(del); box.appendChild(row); return;
    }
    button.addEventListener('click', function () {
      if (!send({a: 'preset_go', id: preset.id}, button)) return;
      // The bridge selects the preset's heads; mirror that, as selectFixtures does.
      var present = (state.config.fixtures || []).filter(function (f) { return !f.missing; }).map(function (f) { return f.id; });
      state.selection = Object.keys(preset.pos).map(Number).filter(function (id) { return present.indexOf(id) >= 0; });
      state.group = null;
      render();
    });
    box.appendChild(button);
  });
  moveState.els.presetTitle.textContent = 'Пресеты · ' + (state.config.presets || []).length;
  moveState.els.manage.setAttribute('aria-pressed', String(moveState.manage));
  if (!box.children.length) box.appendChild(moveEl('p', 'muted', 'Пресетов пока нет'));
}

function renderMove(el) {
  if (!state.config || !el) return;
  if (!moveState.els || moveState.root !== el) moveShell(el);
  var els = moveState.els;
  if (moveState.built !== state.config) {
    moveState.built = state.config;
    movePresets();
  }
  var ready = connected();
  var heads = moveHeads();
  var unknown = heads.some(function (f) { return moveValue(f.id, 'pan') === null || moveValue(f.id, 'tilt') === null; });
  var off = !ready || !heads.length || !!featureReason('move');
  var padOff = off;
  var absolute = moveState.mode === 'absolute';
  els.primary.hidden = absolute; els.absolute.hidden = !absolute;
  els.modeJoystick.setAttribute('aria-pressed', String(!absolute));
  els.modeAbsolute.setAttribute('aria-pressed', String(absolute));
  Object.keys(els.axes).forEach(function (attr) {
    var axis = els.axes[attr], spec = state.config.attrs[attr] || {};
    axis.input.disabled = off || !Number.isFinite(spec.min) || !Number.isFinite(spec.max) || spec.max <= spec.min;
    if (axis.input.disabled || (axis.gesture && (axis.gesture.ids !== state.selection.join(',') || axis.gesture.config !== state.config)) ||
        (axis.latest && (axis.latest.ids !== state.selection.join(',') || axis.latest.config !== state.config))) {
      axis.blocked = true; axis.gesture = null; moveAxisCancel(axis);
    }
    var values = heads.map(function (f) { return moveValue(f.id, attr); });
    var unknownAxis = !values.length || values.some(function (v) { return v === null; });
    var mixed = !unknownAxis && values.some(function (v) { return Math.abs(v - values[0]) > 0.05; });
    var percent = unknownAxis || mixed ? null : values[0];
    if (!axis.gesture && !axis.latest) setFill(axis.input, percent);
    axis.output.textContent = (unknownAxis ? 'неизвестно' : mixed ? 'Разные' :
      Math.round((spec.min + percent * (spec.max - spec.min) / 100) * 10) / 10 + '°') +
      ' · ' + spec.min + '…' + spec.max + '°';
    axis.input.setAttribute('aria-valuetext', axis.output.textContent);
  });
  if (padOff && moveState.drag) {  // link lost or selection gone mid-gesture: drop it so the next touch starts clean
    try { els.pad.releasePointerCapture(moveState.drag.pointer); } catch (error) {}
    clearInterval(moveState.drag.timer);
    moveState.drag = null;
  }
  els.fine.setAttribute('aria-pressed', String(moveState.fine));
  els.fine.disabled = off;
  els.mirror.setAttribute('aria-pressed', String(moveState.mirror));
  els.mirror.disabled = off || heads.length < 2;
  var flipReason = !ready ? (state.halted ? 'Аварийная остановка: возобновите управление.' :
    state.showFileActive || (state.showLoad && state.showLoad.state === 'loading') ? 'Дождитесь завершения операции с шоу.' : 'Нет связи с пультом: дождитесь подтверждённого входа.') :
    !heads.length ? 'Выберите голову; если прибор не распознан, отметьте «Голова» в «Зале» → «Расстановка».' :
    featureReason('move') || (busy('fixture_flag') ? 'Сохраняются настройки приборов; дождитесь ответа моста.' : '');
  els.flipHint.textContent = flipReason; els.flipHint.hidden = !flipReason;
  Object.keys(els.flips).forEach(function (k) {
    els.flips[k].setAttribute('aria-pressed', String(!!heads.length && heads.every(function (f) { return f[k] === true; })));
    var count = heads.filter(function(f) { return f[k] === true; }).length;
    els.flips[k].textContent = (k === 'flip_pan' ? 'Pan наоборот' : 'Tilt наоборот') + (count && count < heads.length ? ' · Разные' : '');
    els.flips[k].disabled = !!flipReason;
    els.flips[k].title = flipReason;
  });
  els.inversions.textContent = ['flip_pan','flip_tilt'].filter(function(k) { return heads.some(function(f) { return f[k]; }); }).map(function(k) { return k === 'flip_pan' ? 'Pan ↔' : 'Tilt ↕'; }).join(' · ');
  els.chips.textContent = '';
  heads.forEach(function (f) { els.chips.appendChild(moveEl('span', 'chip', f.label)); });
  els.hint.textContent = heads.length ? '' : fixtures().some(canMove) ? 'Выберите голову' :
    'Голов в плане нет: MA2 не передаёт, у каких приборов есть Pan/Tilt. Отметьте их в «Зале» → «Расстановка» кнопкой «Голова».';
  els.hint.hidden = !!heads.length;
  els.note.hidden = !unknown;
  els.pad.classList.toggle('off', padOff);
  // Why the pad is off and what to do, on the pad itself.
  els.msg.textContent = !padOff ? '' : !ready ? 'Нет связи с пультом' : !heads.length ? 'Выберите голову' :
    'Движение выключено: ' + featureReason('move');
  els.msg.hidden = !padOff;
  els.pad.classList.toggle('dragging', !!moveState.drag);
  els.save.disabled = padOff || unknown || busy('preset_save');
  els.saveHint.hidden = !unknown;
  Object.keys(els.sliders).forEach(function (attr) {
    var input = els.sliders[attr];
    input.parentNode.hidden = (typeof showTool === 'function' && !showTool(attr)) || !attributeVisible(attr) || typeof split === 'function' && !split(attr).yes.length;
    // Error #14 on this console taught the bridge which fixture types lack the attribute.
    var lacking = (state.noAttr || {})[attr] || [];
    input.disabled = !ready || !heads.length || !!featureReason(attr) || heads.every(function (f) { return lacking.indexOf(f.type) >= 0; });
    if (heads.length && document.activeElement !== input && !(sliderChannels[attr] || {}).latest && !(typeof controlActive === 'function' && controlActive(input))) {
      setFill(input, moveValue(heads[0].id, attr));  // unknown: striped track, hollow thumb
    }
  });
  els.presets.querySelectorAll('[data-preset]').forEach(function (b) { b.disabled = !ready || !!featureReason('move'); });
  var attrs = state.config.attrs, panSpec = attrs.pan || {}, tiltSpec = attrs.tilt || {};
  els.steps.forEach(function (item) { item.button.disabled = off; });
  els.range.textContent = Number.isFinite(panSpec.min) && Number.isFinite(tiltSpec.min) ? 'Диапазон Pan ' + panSpec.min + '…' + panSpec.max + '°, Tilt ' + tiltSpec.min + '…' + tiltSpec.max + '°' +
    (panSpec.range_checked === true && tiltSpec.range_checked === true ? ' — проверен на пульте' : ' — из настроек, не проверен на пульте') : 'Диапазоны Pan/Tilt не настроены. Абсолютное положение недоступно.';
  var pan = null, tilt = null, drag = moveState.drag;
  if (heads.length) {
    pan = moveValue(heads[0].id, 'pan');
    tilt = moveValue(heads[0].id, 'tilt');
  }
  // The knob is the stick, not the position: it follows the finger and springs back to the centre.
  var r = els.pad.getBoundingClientRect(), reach = Math.min(r.width, r.height) / 2;
  els.dot.style.left = 'calc(50% + ' + Math.round(drag ? drag.vx * reach : 0) + 'px)';
  els.dot.style.top = 'calc(50% - ' + Math.round(drag ? drag.vy * reach : 0) + 'px)';
  els.readout.textContent = heads.length ? 'Pan ' + (unknown ? '?' : Math.round(pan)) + ' · Tilt ' + (unknown ? '?' : Math.round(tilt)) : '';
}
