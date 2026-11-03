/* Свет: pick groups or fixtures on the left, every control of the selection on the right at once. */
var lightUI = {tab: 'groups', controlTab: 'light', moveBox: null};
try { lightUI.tab = localStorage.getItem('ma2.pick') || 'groups'; } catch (error) {}
var COLORS = [
  ['Белый', [100, 100, 100]], ['Тёплый', [100, 82, 60]], ['Красный', [100, 0, 0]], ['Оранжевый', [100, 50, 0]],
  ['Жёлтый', [100, 100, 0]], ['Зелёный', [0, 100, 0]], ['Голубой', [0, 100, 100]], ['Синий', [0, 0, 100]],
  ['Пурпурный', [100, 0, 100]], ['Розовый', [100, 35, 65]]
];
// Parameter names come from the MA2 export (attribute names); empty means "not read", not "unsupported".
var PARAM_RE = {dim: /dim|intens/i, color: /col|rgb|red|green|blue|cyan|magenta|yellow|cto|white/i, pos: /pan|tilt/i,
  zoom: /zoom/i, focus: /focus/i, strobe: /strob|shutter/i};
var PARAM_NAME = {dim: 'яркость', color: 'цвет', pos: 'Pan/Tilt', zoom: 'Zoom', focus: 'Focus', strobe: 'стробоскоп'};

// Colour mixing as the bridge sees it: the fixture's own `color`, else attrs.color.mode, else rgb. `none` gets no colour lines.
function colorMode(f) { return f.color || ((state.config && state.config.attrs || {}).color || {}).mode || 'rgb'; }
function supports(f, p) {
  if (p === 'pos') return canMove(f);
  if (p === 'color' && colorMode(f) === 'none') return false;
  if (f.params && f.params.length) return f.params.some(function (name) { return PARAM_RE[p].test(name); });
  return true;
}
function selected() { return state.selection.map(fixture).filter(function (f) { return f && !f.missing; }); }
function attributeVisible(attr) {
  var scope = selected();
  if (!scope.length) scope = (state.config.fixtures || []).filter(function (f) { return !f.missing; });
  var maps = state.config.dmx_map || {};
  return !scope.length || !scope.every(function (f) {
    var spec = maps[f.type];
    return spec && Array.isArray(spec.has) && spec.has.indexOf(attr) < 0;
  });
}
function split(p) {
  var sel = selected();
  return {yes: sel.filter(function (f) { return supports(f, p); }), no: sel.filter(function (f) { return !supports(f, p); })};
}
// What the panel knows: a number it sent, 'mixed', or null (never sent, or lost after a scene).
function known(p) {
  var sel = split(p).yes;
  if (!sel.length || valueFreshness('shown') === 'unknown' || state.tracked === false && (p === 'dim' || p === 'color')) return null;
  var vals = sel.map(function (f) {
    var s = state.shown[f.id] || state.shown[String(f.id)];
    if (!s) return null;
    return p === 'color' ? (s.rgb ? s.rgb.join(',') : null) : typeof s[p] === 'number' ? s[p] : null;
  });
  if (vals.some(function (v) { return v === null; })) return vals.every(function (v) { return v === null; }) ? null : 'mixed';
  return vals.every(function (v) { return v === vals[0]; }) ? vals[0] : 'mixed';
}
function knownText(v, unit) {
  if (v === null) return state.tracked === false ? 'неизвестно после сцены' : 'неизвестно';
  if (v === 'mixed') return 'разные';
  return Math.round(v) + (unit || '');
}
function lightKey() {
  if (state.sec !== 'light') return '';
  return lightUI.controlTab + ':' + lightUI.tab + ':' + state.group + ':' + fadeSeconds + ':' + (state.config ? (state.config.ma2groups || []).length + ',' + (state.config.groups || []).length : '');
}
function unsupportedNote(p) {
  var s = split(p);
  if (!s.yes.length) return h('p', {class: 'note warn'}, 'Выбранные приборы не поддерживают ' + PARAM_NAME[p] + '. Команда не отправится.');
  if (s.no.length) return h('p', {class: 'note'}, 'Подействует на ' + s.yes.length + ' из ' + (s.yes.length + s.no.length) + ': у остальных нет параметра.');
  return null;
}
function fxName(f) { return f.label || f.name || String(f.id); }
function allowedFixture(id) { return !state.safety || state.safety.mode === 'full' || state.safety.fixtures.indexOf(id) >= 0; }
function pickRow(on, disabled, onclick, kids, title) {
  return h('button', {class: 'row-item', type: 'button', 'aria-pressed': String(on), disabled: disabled, title: title || '', onclick: onclick},
    h('span', {class: 'check'}, on ? icon('check', 18) : ''), kids);
}

SECTIONS.light = function (el) {
  var cfg = state.config;
  var wrap = h('div', {class: 'light' + (lightUI.tab === 'plan' ? ' wide' : '')});
  add(el, wrap);
  var tabs = h('div', {class: 'seg'}, [['groups', 'Группы'], ['fixtures', 'Приборы'], ['plan', 'План']].map(function (t) {
    return h('button', {type: 'button', 'aria-pressed': String(lightUI.tab === t[0]), onclick: function () {
      lightUI.tab = t[0];
      try { localStorage.setItem('ma2.pick', t[0]); } catch (error) {}
      render();
    }}, t[1]);
  }));
  var bd = h('div', {class: 'bd' + (lightUI.tab === 'plan' ? ' plan-mini' : ''), 'data-scroll': 'pick-' + lightUI.tab});
  var ready = connected();
  if (lightUI.tab === 'groups') {
    var panelGroups = (cfg.groups || []).filter(function (g) { return !('n' in g); });
    var ma2 = cfg.ma2groups || [];
    var make = h('button', {class: 'btn small', type: 'button', disabled: !ready || !state.selection.length, onclick: function () {
      var label = (prompt('Название группы из ' + state.selection.length + ' выбранных приборов') || '').trim();
      if (label) send({a: 'group_save', label: label, ids: state.selection.slice()}, make);
    }}, icon('group', 18), state.selection.length ? 'Группа из выбранных (' + state.selection.length + ')' : 'Выберите приборы, чтобы создать группу');
    add(bd, make);
    // Deleting forgets the group in the panel only; the desk's Group stays.
    function del(text, action) {
      return h('button', {class: 'btn small ghost', type: 'button', 'aria-label': 'Удалить ' + text, disabled: !ready, onclick: function (e) {
        if (confirm('Удалить из панели ' + text + '? На пульте ничего не изменится.')) send(action, e.currentTarget);
      }}, icon('x', 18));
    }
    if (!panelGroups.length && !ma2.length) add(bd, h('div', {class: 'empty-pick'}, h('b', {}, 'Групп пока нет'),
      h('span', {class: 'note'}, 'Выберите приборы и нажмите «Группа из выбранных». Группы MA2 читаются на «Площадке».'),
      h('button', {class: 'btn small', type: 'button', onclick: function () { lightUI.tab = 'fixtures'; render(); }}, 'Выбрать приборы')));
    panelGroups.forEach(function (g) {
      var on = state.group === g.id;
      var allowed = g.fixtures.every(allowedFixture);
      add(bd, h('div', {class: 'pick-del'}, pickRow(on, !ready || !allowed, function () {
        cancelSlider('dim'); cancelSlider('color');
        if (send({a: 'select_group', id: g.id})) { state.selection = g.fixtures.slice(); state.group = g.id; render(); }
      }, h('span', {class: 'grow'}, h('b', {}, g.label), h('span', {class: 'meta'}, g.fixtures.length + ' приб. · группа панели')), allowed ? '' : 'В группе есть приборы вне allowed_fixtures'),
        del('группу «' + g.label + '»', {a: 'group_delete', id: g.id})));
    });
    ma2.forEach(function (g) {
      var on = state.group === 'ma2:' + g.n, ids = g.ids || [];
      add(bd, h('div', {class: 'pick-del'}, pickRow(on, !ready || !ids.length, function () {
        cancelSlider('dim'); cancelSlider('color');
        if (send({a: 'ma2_group_go', n: g.n}, null)) { state.selection = ids.slice(); state.group = 'ma2:' + g.n; render(); }
      }, [h('span', {class: 'grow'}, h('b', {}, g.name), h('span', {class: 'meta'}, 'Group ' + g.n + (g.ids ? ' · ' + ids.length + ' приб.' : ' · состав не прочитан, импортируйте снова'))),
        h('span', {class: 'tag ma2'}, 'MA2')], ids.length ? '' : 'Состав не прочитан: на «Площадке» нажмите «Прочитать из MA2» и импортируйте группу снова'),
        del('группу MA2 ' + g.n + ' «' + g.name + '»', {a: 'group_delete', n: g.n})));
    });
  } else if (lightUI.tab === 'fixtures') {
    // Grouped by fixture type: a whole row of one type is one tap.
    var types = [], byType = Object.create(null);
    fixtures().filter(function (f) { return !f.missing; }).forEach(function (f) {
      var t = f.type || 'Без типа';
      if (!byType[t]) { byType[t] = []; types.push(t); }
      byType[t].push(f);
    });
    types.forEach(function (t) {
      var list = byType[t], ids = list.filter(function (f) { return allowedFixture(f.id); }).map(function (f) { return f.id; });
      var all = ids.length && ids.every(function (id) { return state.selection.indexOf(id) >= 0; });
      add(bd, h('div', {class: 'type-head'}, h('span', {class: 'grow', title: t}, t), h('button', {class: 'btn small ghost', type: 'button', disabled: !ready || !ids.length,
        onclick: function () {
          var sel = state.selection.filter(function (id) { return ids.indexOf(id) < 0; });
          selectFixtures(all ? sel : sel.concat(ids));
        }}, all ? 'Снять ' + ids.length : 'Все ' + ids.length)));
      list.forEach(function (f) {
        var on = state.selection.indexOf(f.id) >= 0;
        add(bd, pickRow(on, !ready || !allowedFixture(f.id), function () {
          var sel = state.selection.slice(), i = sel.indexOf(f.id);
          if (i < 0) sel.push(f.id); else sel.splice(i, 1);
          selectFixtures(sel);
        }, [h('span', {class: 'id'}, f.id), h('span', {class: 'grow'}, h('b', {}, fxName(f))),
          canMove(f) ? h('span', {class: 'tag'}, 'голова') : null, f.service ? h('span', {class: 'tag'}, 'служ.') : null]));
      });
    });
  } else {
    if (!fixtures().some(function (f) { return typeof f.x === 'number'; })) add(bd, h('div', {class: 'empty-pick'}, h('b', {}, 'План ещё не нарисован'),
      h('span', {class: 'note'}, 'Нарисуйте зал и расставьте приборы — потом их можно выбирать прямо на схеме.'),
      h('button', {class: 'btn small edit', type: 'button', onclick: function () { go('hall'); }}, icon('edit', 18), 'Открыть «Зал»')));
    else hallPlan(bd, 'control');
  }
  add(wrap, h('section', {class: 'pick', 'aria-label': 'Что управляем'}, h('div', {class: 'hd'}, tabs), bd,
    lightUI.tab === 'plan' ? h('p', {class: 'note pick-tip'}, 'Нажмите прибор или обведите несколько пальцем.') : null,
    h('div', {class: 'ft'}, h('button', {class: 'btn small', type: 'button', disabled: !ready, onclick: function () {
      selectFixtures(fixtures().filter(function (f) { return !f.missing && !f.service && allowedFixture(f.id); }).map(function (f) { return f.id; }));
    }}, 'Все сценические'), h('button', {class: 'btn small ghost', type: 'button', disabled: !ready || !state.selection.length, onclick: function () { selectFixtures([]); }}, 'Снять выбор'))));

  var box = h('section', {class: 'ctl', 'aria-label': 'Управление выбранным', 'data-scroll': 'ctl'});
  var ctl = h('div', {class: 'ctl-grid'});
  add(wrap, box);
  add(box, ctl);
  var sel = selected();
  if (!sel.length) {
    add(ctl, h('div', {class: 'empty-sec span'}, icon('light', 40), h('b', {}, 'Ничего не выбрано'),
      h('span', {class: 'note'}, 'Выберите группу, приборы или нажмите их на плане слева. Здесь сразу появятся яркость, цвет, позиция и стробоскоп.')));
    return;
  }
  var names = sel.slice(0, 6).map(fxName).join(', ') + (sel.length > 6 ? ' и ещё ' + (sel.length - 6) : '');
  add(ctl, h('div', {class: 'selbar span'},
    h('div', {class: 'who'}, h('b', {}, sel.length + ' ' + plural(sel.length, 'прибор', 'прибора', 'приборов')), h('span', {class: 'note', title: names}, names)),
    h('div', {class: 'fade', role: 'group', 'aria-label': 'Плавный переход для кнопок яркости и образцов цвета',
      title: 'Кнопки 0–100 %, образцы цвета и касание круга меняют свет плавно за это время. Перетаскивание ползунка или круга всегда сразу: свет идёт за пальцем.'},
      h('span', {class: 'note'}, 'Плавно'), [0, 1, 3, 5].map(function (sec) {
      return h('button', {class: 'btn small', type: 'button', 'aria-pressed': String(sec === fadeSeconds),
        onclick: function () { fadeSeconds = sec; render(); }}, sec ? sec + ' с' : 'сразу');
    })),
    h('button', {class: 'btn small', type: 'button', disabled: !ready || !!featureReason('store'), onclick: function () {
      var pages = ((cfg.scenes || []).map(pageOf));
      openStore(pages.length ? Math.max.apply(null, pages) : 1);
    }}, icon('save', 18), 'В сцену…')));
  // Updated in place: a rebuild here would cut a wheel or slider gesture short.
  var lost = h('p', {class: 'note warn span'}, 'После запуска сцены панель не знает текущих значений: показывает «неизвестно».');
  updaters.push(function () { lost.hidden = state.tracked !== false; });
  add(ctl, lost);
  add(ctl, h('div', {class: 'control-tabs span seg'}, ['light', 'movement'].map(function(tab) {
    return h('button', {type:'button', 'aria-pressed':String(lightUI.controlTab === tab), onclick:function() {
      moveStop(); lightUI.controlTab = tab; render();
    }}, tab === 'light' ? 'Свет' : 'Движение');
  })));
  if (lightUI.controlTab === 'movement') { add(ctl, moveCard()); return; }
  add(ctl, sliderCard('dim', 'Яркость', '%', true));
  if (attributeVisible('strobe')) add(ctl, sliderCard('strobe', 'Стробоскоп', '%'));
  add(ctl, colorCard());
};
function plural(n, one, few, many) {
  var m10 = n % 10, m100 = n % 100;
  return m10 === 1 && m100 !== 11 ? one : m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? few : many;
}

function sliderCard(p, title, unit, quick) {
  var s = split(p);
  var ready = connected() && s.yes.length && !featureReason(p);
  var out = h('span', {class: 'val'}), src = h('span', {class: 'src'});
  var input = h('input', {type: 'range', min: 0, max: 100, value: 0, 'aria-label': title, disabled: !ready, oninput: function (e) {
    var v = Number(e.target.value);
    out.textContent = (p === 'strobe' && !v) ? 'выкл' : v + unit; out.classList.remove('unknown'); setFill(input, v);
    throttleSlider({a: p, v: v});  // a drag is live: the light follows the finger, no fade
  }});
  updaters.push(function () {
    if ((sliderChannels[p] || {}).latest || document.activeElement === input) return;
    var v = known(p);
    setFill(input, v);
    out.textContent = p === 'strobe' && v === 0 ? 'выкл' : knownText(v, unit);
    out.classList.toggle('unknown', v === null || v === 'mixed');
    src.textContent = v === null ? 'MA2 не сообщает текущее значение' : v === 'mixed' ? 'у выбранных разные значения' : sentSource();
  });
  var card = h('div', {class: 'card c-' + p + (s.yes.length ? '' : ' dis')}, h('div', {class: 'vrow'}, h('h2', {}, title), out), input, src);
  if (quick) add(card, h('div', {class: 'quick', title: fadeSeconds ? 'Плавно за ' + fadeSeconds + ' с' : ''}, [0, 25, 50, 75, 100].map(function (v) {
    return h('button', {type: 'button', disabled: !ready, onclick: function () { send({a: 'dim', v: v, fade: fadeSeconds}); }}, v + '%');
  })));
  if (quick && fadeSeconds) add(card, h('p', {class: 'src'}, 'Кнопки — плавно за ' + fadeSeconds + ' с. Ползунок — сразу.'));
  if (featureReason(p)) add(card, h('p', {class: 'note warn'}, featureReason(p)));
  add(card, unsupportedNote(p));
  return card;
}

/* ---------- colour: wheel (hue by angle, saturation by radius) + saturation and lightness sliders ---------- */
function hsv2rgb(hue, s, v) {  // 0-360, 0-1, 0-1 -> [r, g, b] 0-100, as the bridge takes them
  var f = function (n) { var k = (n + hue / 60) % 6; return v - v * s * Math.max(0, Math.min(k, 4 - k, 1)); };
  return [f(5), f(3), f(1)].map(function (x) { return Math.round(x * 100); });
}
function rgb2hsv(c) {
  var r = c[0] / 100, g = c[1] / 100, b = c[2] / 100, max = Math.max(r, g, b), d = max - Math.min(r, g, b), hue = 0;
  if (d) hue = max === r ? (g - b) / d % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return {h: (hue * 60 + 360) % 360, s: max ? d / max : 0, v: max};
}
function cssRgb(c) { return 'rgb(' + c.map(function (v) { return Math.round(v * 2.55); }).join(',') + ')'; }

function colorCard() {
  var s = split('color');
  var sel = selected();
  var reason = featureReason('color');
  var presets = (state.config.ma2presets || {}).colors || [];
  var presetRow = function (enabled) {
    return presets.length ? [h('h3', {}, 'Пресеты цвета MA2'), h('div', {class: 'row'}, presets.map(function (pr) {
      return h('button', {class: 'btn small', type: 'button', disabled: !enabled, onclick: function (e) { send({a: 'ma2_preset_go', type: 'color', n: pr.n}, e.currentTarget); }}, pr.name);
    }))] : null;
  };
  if (!s.yes.length) {
    // No RGB/CMY mixing on any selected fixture: no wheel, only what the console itself can apply.
    return h('div', {class: 'card c-color'}, h('h2', {}, 'Цвет'),
      h('p', {class: 'note warn'}, sel.length === 1 ? 'У этого прибора нет смешения цвета (RGB или CMY): круг к нему не применить.' : 'У выбранных приборов нет смешения цвета (RGB или CMY): круг к ним не применить.'),
      presets.length ? h('p', {class: 'note'}, 'Пресеты цвета MA2 пульт применит к тем приборам, для которых они записаны.') : h('p', {class: 'note'}, 'Цвет этих приборов из панели не управляется.'),
      presetRow(connected()));
  }
  var ready = connected() && !reason;
  var cp = {h: 0, s: 1, v: 1, set: false, drag: null};  // what the card shows; set=false: nothing honest to show
  var mark = h('span', {class: 'mark'}), shade = h('span', {class: 'shade'});
  var wheel = h('div', {class: 'wheel', role: 'slider', tabindex: ready ? '0' : '-1', 'aria-label': 'Оттенок (по кругу) и насыщенность (от центра)', 'aria-valuemin': '0', 'aria-valuemax': '359'}, shade, mark);
  var chip = h('span', {class: 'swatch-now'}), now = h('b', {}), nowSrc = h('span', {class: 'src'});
  var satIn = h('input', {type: 'range', min: 0, max: 100, 'aria-label': 'Насыщенность', oninput: function (e) { cp.s = Number(e.target.value) / 100; pick(); }});
  var valIn = h('input', {type: 'range', min: 0, max: 100, 'aria-label': 'Светлота цвета', oninput: function (e) { cp.v = Number(e.target.value) / 100; pick(); }});
  var satOut = h('span', {class: 'num'}), valOut = h('span', {class: 'num'});
  // jump: a swatch or the first touch on the wheel, sent with the chosen fade; a drag goes out at once.
  function pick(jump) {
    cp.set = true;
    var rgb = hsv2rgb(cp.h, cp.s, cp.v);
    var action = {a: 'color', r: rgb[0], g: rgb[1], b: rgb[2]};
    if (jump && fadeSeconds) action.fade = fadeSeconds;
    if (jump) { cancelSlider('color'); send(action); } else throttleSlider(action);
    draw();
  }
  function fromPointer(ev, jump) {
    var r = wheel.getBoundingClientRect(), R = r.width / 2;
    var dx = ev.clientX - r.left - R, dy = ev.clientY - r.top - R;
    var sat = Math.min(1, Math.sqrt(dx * dx + dy * dy) / R);
    if (sat > .04) cp.h = (Math.atan2(dx, -dy) * 180 / Math.PI + 360) % 360;
    cp.s = sat < .06 ? 0 : sat;  // the centre snaps to pure white
    if (!cp.set) cp.v = 1;
    pick(jump);
  }
  wheel.addEventListener('pointerdown', function (ev) {
    if (!ready || ev.button > 0) return;
    ev.preventDefault();
    cp.drag = ev.pointerId;
    cp.from = [ev.clientX, ev.clientY];  // a finger jitters: a tap must not turn into a drag and cut its fade
    try { wheel.setPointerCapture(ev.pointerId); } catch (error) {}
    fromPointer(ev, true);
  });
  wheel.addEventListener('pointermove', function (ev) {
    if (cp.drag !== ev.pointerId) return;
    if (cp.from && Math.abs(ev.clientX - cp.from[0]) + Math.abs(ev.clientY - cp.from[1]) < 8) return;
    cp.from = null;
    fromPointer(ev);
  });
  ['pointerup', 'pointercancel', 'lostpointercapture'].forEach(function (type) {
    wheel.addEventListener(type, function (ev) { if (cp.drag === ev.pointerId) { cp.drag = null; draw(); } });
  });
  wheel.addEventListener('keydown', function (ev) {
    var step = ev.shiftKey ? 15 : 5;
    var move = {ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, .05], ArrowDown: [0, -.05]}[ev.key];
    if (!move || !ready) return;
    ev.preventDefault();
    if (!cp.set) { cp.s = 1; cp.v = 1; }
    cp.h = (cp.h + move[0] + 360) % 360;
    cp.s = Math.min(1, Math.max(0, cp.s + move[1]));
    pick();
  });
  var swatches = COLORS.map(function (c) {
    return h('button', {class: 'sw', type: 'button', 'aria-label': c[0], title: c[0], 'data-rgb': c[1].join(','), style: {'--c': cssRgb(c[1])}, disabled: !ready,
      onclick: function () { var v = rgb2hsv(c[1]); cp.h = v.s ? v.h : cp.h; cp.s = v.s; cp.v = v.v; pick(true); }});
  });
  function draw() {
    var v = known('color');
    var rgb = hsv2rgb(cp.h, cp.s, cp.v), rad = cp.h * Math.PI / 180;
    mark.hidden = !cp.set;
    mark.style.setProperty('left', 50 + cp.s * 50 * Math.sin(rad) + '%');
    mark.style.setProperty('top', 50 - cp.s * 50 * Math.cos(rad) + '%');
    mark.style.setProperty('--c', cssRgb(rgb));
    shade.style.setProperty('opacity', cp.set ? String(1 - cp.v) : '0');
    wheel.setAttribute('aria-valuenow', String(Math.round(cp.h)));
    wheel.setAttribute('aria-valuetext', cp.set ? 'оттенок ' + Math.round(cp.h) + '°, насыщенность ' + Math.round(cp.s * 100) + '%' : 'цвет неизвестен');
    [[satIn, satOut, cp.s], [valIn, valOut, cp.v]].forEach(function (x) {
      x[0].disabled = !ready || !cp.set;
      if (document.activeElement !== x[0]) setFill(x[0], cp.set ? Math.round(x[2] * 100) : null); else x[0].style.setProperty('--p', Math.round(x[2] * 100) + '%');
      x[1].textContent = cp.set ? Math.round(x[2] * 100) + '%' : '—';
    });
    chip.classList.toggle('unknown', !cp.set);
    chip.style.setProperty('--c', cp.set ? cssRgb(rgb) : 'transparent');
    var busyNow = cp.drag !== null || !!(sliderChannels.color || {}).latest;
    now.textContent = busyNow ? 'Отправляется…' : v === null ? (state.tracked === false ? 'Неизвестен после сцены' : 'Текущий цвет неизвестен') :
      v === 'mixed' ? 'У выбранных разные цвета' : 'R ' + rgb[0] + ' · G ' + rgb[1] + ' · B ' + rgb[2];
    nowSrc.textContent = busyNow ? '' : v === null ? 'MA2 не сообщает цвет. Выберите оттенок на круге или образец.' : v === 'mixed' ? 'Новый выбор задаст один цвет всем.' : sentSource();
    swatches.forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.rgb === v)); });
  }
  updaters.push(function () {
    // While the operator drags or a value waits to go out, the card shows the operator's pick, not the echo.
    if (cp.drag === null && !(sliderChannels.color || {}).latest && document.activeElement !== satIn && document.activeElement !== valIn) {
      var v = known('color');
      if (typeof v === 'string' && v !== 'mixed') {
        var hv = rgb2hsv(v.split(',').map(Number));
        if (hv.s) cp.h = hv.h;
        cp.s = hv.s; cp.v = hv.v; cp.set = true;
      } else cp.set = false;
    }
    draw();
  });
  var modes = {}, guessed = false;
  s.yes.forEach(function (f) { modes[colorMode(f).toUpperCase()] = 1; if (!f.color) guessed = true; });
  return h('div', {class: 'card c-color' + (ready ? '' : ' dis')}, h('div', {class: 'vrow'}, h('h2', {}, 'Цвет'),
      h('span', {class: 'src', title: guessed ? 'MA2 не сообщает, как прибор смешивает цвет: тип взят из настроек панели (attrs.color)' : ''},
        'смешение ' + Object.keys(modes).join(' и ') + (guessed ? ' · по настройкам' : ''))),
    h('div', {class: 'picker'}, wheel, h('div', {class: 'picker-side'},
      h('div', {class: 'now'}, chip, h('div', {class: 'stack0'}, now, nowSrc)),
      h('label', {class: 'mini'}, h('span', {class: 'vrow'}, h('span', {}, 'Насыщенность'), satOut), satIn),
      h('label', {class: 'mini'}, h('span', {class: 'vrow'}, h('span', {}, 'Светлота цвета'), valOut), valIn),
      h('div', {class: 'swatches', role: 'group', 'aria-label': 'Быстрые цвета'}, swatches),
      h('p', {class: 'src'}, 'Круг меняет только цвет. Яркость прибора — отдельный регулятор «Яркость».' +
        (fadeSeconds ? ' Образцы и касание круга — плавно за ' + fadeSeconds + ' с, перетаскивание — сразу.' : '')))),
    presetRow(ready), reason ? h('p', {class: 'note warn'}, reason) : null, unsupportedNote('color'));
}

function moveCard() {
  var s = split('pos');
  var presets = (state.config.ma2presets || {}).positions || [];
  var presetRow = presets.length ? [h('h3', {}, 'Пресеты позиции MA2'), h('div', {class: 'row'}, presets.map(function (pr) {
    return h('button', {class: 'btn small', type: 'button', disabled: !connected() || !s.yes.length, onclick: function (e) { send({a: 'ma2_preset_go', type: 'position', n: pr.n}, e.currentTarget); }}, pr.name);
  }))] : null;
  if (!s.yes.length) {
    // No head in the selection: one short line instead of a dead pad.
    var anyHead = fixtures().some(canMove);
    return h('div', {class: 'card c-pos slim'}, h('div', {class: 'vrow'}, h('h2', {}, 'Позиция и луч'), h('span', {class: 'src'}, 'Pan/Tilt, Zoom, Фокус')),
      h('p', {class: 'note'}, anyHead ? 'В выборе нет голов (приборов с Pan/Tilt).' : 'Голов в плане нет: MA2 не сообщает, у каких приборов есть Pan/Tilt. Отметьте их в «Зале» кнопкой «Голова».'),
      anyHead ? null : h('div', {}, h('button', {class: 'btn small edit', type: 'button', onclick: function () { go('hall'); }}, icon('edit', 18), 'Отметить головы')));
  }
  // move.js keeps its own pad and listeners; reuse the same element so a gesture survives a rebuild.
  if (!lightUI.moveBox) lightUI.moveBox = h('div', {class: 'stack movebox'});
  var card = h('div', {class: 'card c-pos'}, h('h2', {}, 'Позиция и луч'), lightUI.moveBox, presetRow, unsupportedNote('pos'));
  updaters.push(function () { if (typeof renderMove === 'function') renderMove(lightUI.moveBox); });
  return card;
}
