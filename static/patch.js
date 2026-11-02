/* ---------- Патч (spec 21): the show's patch, RDM devices, and one confirmed readdress at a time ---------- */
var patchState = {edit: false, cur: null, address: '', patch: true, physical: false, plan: null, result: null, rdm: null, uid: '', footprint: ''};

function patchKey() { return JSON.stringify([patchState.edit, patchState.cur, patchState.plan && patchState.plan.token, patchState.result, patchState.rdm && patchState.rdm.t]); }

on('rdm', function (rdm) { patchState.rdm = rdm; render(); });
on('ok', function (ok, m) {
  if (m.a === 'patch_plan') { patchState.plan = ok ? m.plan : null; if (ok) patchDialog(m.plan); else notice(m.err); }
  if (m.a === 'patch_apply') { patchState.result = m; patchState.plan = null; closeDialog(); render(); }
  if (m.a === 'rdm_list' && !ok) notice(m.err);
  if (m.a === 'rdm_identify' && !ok) notice(m.err);
});

function dmxText(a) { return Math.floor((a - 1) / 512) + 1 + '.' + String((a - 1) % 512 + 1).padStart(3, '0'); }
function closeDialog() { var d = document.getElementById('dlg'); if (d.open) d.close(); }

function rdmCard() {
  var rdm = patchState.rdm;
  var card = h('div', {class: 'card'}, h('b', {}, 'RDM-устройства'),
    h('p', {class: 'note warn'}, 'Панель не включает RDM: на пульте Setup → Console Global Settings → Enable RDM, для вселенной — Setup → Patch → DMX List, ячейка RDM. ' +
      'RDM у вас вызывал мигание френеля: после поиска и записи выключите его там же.'),
    h('div', {class: 'row'},
      h('button', {class: 'btn', type: 'button', disabled: !connected() || !safe('allow_rdm'), onclick: function (e) { send({a: 'rdm_list'}, e.currentTarget); }}, 'Найти (RdmList)'),
      safe('allow_rdm') ? null : h('span', {class: 'note'}, 'RDM выключен в настройках (allow_rdm).')));
  if (!rdm) return card;
  add(card, h('span', {class: 'note'}, 'Прочитано в ' + rdm.t + ': устройств с UID ' + rdm.devices.length + '. Колонки ответа пульта не проверены, ниже строки как есть.'));
  add(card, rdm.devices.map(function (d) {
    var linked = fixtures().filter(function (f) { return f.rdm && f.rdm.uid === d.uid; })[0];
    return h('div', {class: 'grow-row wrap'}, h('div', {class: 'grow'}, h('b', {}, d.uid), h('span', {class: 'meta'}, d.line)),
      h('span', {class: 'note'}, linked ? 'связан с ' + linked.id : 'не связан'),
      h('span', {class: 'row'},
        h('button', {class: 'btn small', type: 'button', disabled: !connected(), onclick: function (e) { send({a: 'rdm_identify', uid: d.uid, on: true}, e.currentTarget); }}, 'Identify'),
        h('button', {class: 'btn small', type: 'button', disabled: !connected(), onclick: function (e) { send({a: 'rdm_identify', uid: d.uid, on: false}, e.currentTarget); }}, 'Выкл.')));
  }));
  if (rdm.lines.length && !rdm.devices.length) add(card, h('pre', {class: 'note'}, rdm.lines.join('\n')));
  return card;
}

function patchTable() {
  var rows = (state.config && state.config.patch) || [];
  var byId = {};
  fixtures().forEach(function (f) { byId[f.id] = f; });
  function range(start, n) { return n ? dmxText(start) + '–' + ((start + n - 2) % 512 + 1) : dmxText(start) + '–?'; }
  return h('div', {class: 'tablewrap', 'data-scroll': 'patch'}, h('table', {},
    h('tr', {}, ['Fixture', 'Имя', 'Тип', 'Патч MA2', 'Каналы MA2', 'Физический (RDM)', 'Пересечения'].map(function (t) { return h('th', {}, t); })),
    rows.map(function (r) {
      var f = byId[r.id] || {};
      return h('tr', {class: patchState.cur === r.id ? 'sel' : null, onclick: patchState.edit ? function () { patchPick(r.id); } : null, style: patchState.edit ? {cursor: 'pointer'} : {}},
        h('td', {class: 'id'}, r.id), h('td', {}, f.label || f.name || ''), h('td', {}, f.type || ''),
        h('td', {}, range(r.start, r.ma2)),
        h('td', {}, r.ma2 ? r.ma2 + (r.ma2_from ? ' · ' + r.ma2_from : '') : 'не прочитано'),
        h('td', {}, r.uid ? r.uid + ' · ' + range(r.phys_start, r.phys) + (r.phys ? '' : ' (размер не прочитан)') : '—'),
        h('td', {class: r.conflicts.length ? 'bad' : null}, r.conflicts.length ? 'с ' + r.conflicts.join(', ') : '—'));
    })));
}

function patchPick(id) {
  var f = fixture(id);
  Object.assign(patchState, {cur: id, address: f.address || '', patch: true, physical: false, result: null, uid: (f.rdm && f.rdm.uid) || '', footprint: (f.rdm && f.rdm.footprint) || ''});
  render();
}

function patchEditor() {
  var f = fixture(patchState.cur);
  if (!f) return h('div', {class: 'card'}, h('p', {class: 'note'}, 'Нажмите строку таблицы, чтобы выбрать прибор.'));
  var devices = (patchState.rdm && patchState.rdm.devices) || [];
  function check(key, label) {
    return h('label', {class: 'opt'}, h('input', {type: 'checkbox', checked: patchState[key], onchange: function (e) { patchState[key] = e.target.checked; }}), h('span', {class: 't'}, label));
  }
  return h('div', {class: 'card'}, h('b', {}, 'Прибор ' + f.id + ' «' + (f.label || f.name) + '», патч ' + f.address),
    h('div', {class: 'stack'},
      h('b', {}, '1. Связь с физическим прибором'),
      h('p', {class: 'note'}, 'Совпадение имени или адреса связь не подтверждает: проверьте Identify, что мигает нужный прибор.'),
      h('div', {class: 'row'},
        h('select', {onchange: function (e) { patchState.uid = e.target.value; }},
          h('option', {value: ''}, '— UID —'), devices.map(function (d) { return h('option', {value: d.uid, selected: d.uid === patchState.uid}, d.uid); })),
        h('label', {class: 'field'}, h('span', {}, 'Каналов у прибора (если знаете)'), h('input', {type: 'number', min: 1, max: 512, value: patchState.footprint, oninput: function (e) { patchState.footprint = e.target.value; }})),
        h('button', {class: 'btn small', type: 'button', disabled: !connected(), onclick: function (e) {
          if (!patchState.uid) { notice('Выберите UID: сначала «Найти (RdmList)»'); return; }
          var msg = {a: 'rdm_link', id: f.id, uid: patchState.uid};
          if (patchState.footprint) msg.footprint = Number(patchState.footprint);
          send(msg, e.currentTarget);
        }}, 'Связать'),
        f.rdm ? h('button', {class: 'btn small', type: 'button', disabled: !connected(), onclick: function (e) { send({a: 'rdm_link', id: f.id, uid: null}, e.currentTarget); }}, 'Отвязать') : null)),
    h('div', {class: 'stack'},
      h('b', {}, '2. Новый стартовый адрес'),
      h('div', {class: 'row'},
        h('input', {type: 'text', inputmode: 'decimal', value: patchState.address, placeholder: '1.290', oninput: function (e) { patchState.address = e.target.value; }}),
        check('patch', 'Патч MA2 (это шоу)'), check('physical', 'Физический адрес по RDM (прибор, все шоу)')),
      h('button', {class: 'btn edit', type: 'button', disabled: !connected(), onclick: function (e) {
        send({a: 'patch_plan', id: f.id, address: patchState.address, patch: patchState.patch, physical: patchState.physical}, e.currentTarget);
      }}, 'Показать план')));
}

function patchDialog(plan) {
  var d = document.getElementById('dlg');
  d.textContent = '';
  var accept = {conflicts: !plan.conflicts.length, physical: !plan.physical};
  var go = h('button', {class: 'btn edit', type: 'button', disabled: true}, 'Записать');
  function refresh() { go.disabled = !connected() || !accept.conflicts || !accept.physical; }
  function tick(key, label) {
    return h('label', {class: 'opt'}, h('input', {type: 'checkbox', onchange: function (e) { accept[key] = e.target.checked; refresh(); }}), h('span', {class: 't'}, label));
  }
  go.onclick = function () {
    send({a: 'patch_apply', id: plan.id, address: plan.new, patch: plan.patch, physical: plan.physical, token: plan.token, accept_conflicts: plan.conflicts.length > 0}, go);
  };
  add(d, h('div', {class: 'dlg'}, h('h2', {}, 'План: прибор ' + plan.id + ' «' + plan.name + '»'),
    h('p', {}, (plan.patch ? 'Патч MA2: ' + plan.old + ' → ' + plan.new : 'Патч MA2 не меняется (' + plan.old + ')') + (plan.ma2_range ? ', каналы ' + plan.ma2_range.join('–') : ', число каналов не прочитано')),
    plan.physical ? h('p', {}, 'Физический адрес ' + plan.uid + ': ' + (plan.old_phys || 'не прочитан') + ' → ' + plan.new +
      (plan.phys_range ? ', каналы ' + plan.phys_range.join('–') : ', число каналов прибора не прочитано')) : null,
    h('p', {class: 'note'}, 'Команды по порядку: ' + plan.lines.join('; ')),
    plan.conflicts.length ? h('p', {class: 'bad'}, 'Пересечение с приборами ' + plan.conflicts.join(', ')) : h('p', {class: 'note'}, 'Пересечений с другими приборами плана нет.'),
    plan.conflicts.length ? tick('conflicts', 'Записать, несмотря на пересечение') : null,
    plan.physical ? h('p', {class: 'note warn'}, 'Физический адрес меняется в самом приборе: это коснётся всех шоу, не только открытого. Две записи не атомарны: если вторая не пройдёт, панель покажет, что изменилось, и обратную команду.') : null,
    plan.physical ? tick('physical', 'Понимаю: меняется сам прибор') : null,
    h('div', {class: 'row'}, h('button', {class: 'btn', type: 'button', onclick: closeDialog}, 'Отмена'), go)));
  refresh();
  d.showModal();
}

function patchResult() {
  var r = patchState.result;
  if (!r) return null;
  return h('div', {class: 'card'}, h('b', {class: r.ok ? null : 'bad'}, r.ok ? 'Записано' : (r.err || 'Не записано')),
    (r.steps || []).map(function (s) { return h('p', {class: s.ok ? 'note' : 'bad'}, (s.ok ? 'да · ' : 'нет · ') + s.line + (s.reply ? ' — ' + s.reply : '')); }),
    r.check ? h('p', {class: 'note'}, 'Перечитано: ' + (r.check.patch ? 'патч ' + r.check.patch : '') + (r.check.rdm ? ' · RDM: ' + r.check.rdm.join(' ') : '') + (r.check.error ? ' · ошибка перечитывания: ' + r.check.error : '')) : null,
    (r.undo || []).length ? h('p', {class: 'note warn'}, 'Вернуть как было: ' + r.undo.join('; ') + ' (постройте план на прежний адрес ' + ((r.plan && r.plan.old) || '') + ').') : null,
    r.note ? h('p', {class: 'note warn'}, r.note) : null);
}

SECTIONS.patch = function (el) {
  add(el, h('div', {class: 'ph'}, h('h1', {}, 'Патч'),
    h('button', {class: 'btn', type: 'button', 'aria-pressed': String(patchState.edit), onclick: function () { patchState.edit = !patchState.edit; if (!patchState.edit) patchState.cur = null; render(); }},
      patchState.edit ? 'Режим правки: вкл.' : 'Режим правки')));
  add(el, h('p', {class: 'note'}, 'Fixture ID — номер прибора в MA2, его панель не меняет. Патч — адрес в этом шоу. Физический адрес — то, что выставлено на самом приборе. ' +
    (safe('allow_patch') ? '' : 'Запись патча выключена в настройках (allow_patch). ')));
  add(el, h('div', {class: 'row'}, h('button', {class: 'btn', type: 'button', disabled: !connected() || !safe('allow_fixture_read'), onclick: function (e) { send({a: 'fixtures_fetch'}, e.currentTarget); }}, 'Перечитать патч из MA2')));
  add(el, patchResult());
  if (patchState.edit) add(el, patchEditor());
  add(el, h('div', {class: 'card'}, patchTable()));
  add(el, rdmCard());
};
