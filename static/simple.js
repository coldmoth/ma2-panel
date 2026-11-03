'use strict';
(() => {
  let ws, status = {}, config = {scenes: [], pages: []}, running = {}, runningMeta = {}, receipts = {}, pending = [];
  let serial = 0;
  const prefix = Date.now().toString(36) + Math.random().toString(36).slice(2);
  const scenes = document.getElementById('scenes');
  const connection = document.getElementById('connection');
  const error = document.getElementById('error');
  const blackout = document.getElementById('blackout');
  function ready() {
    return ws && ws.readyState === WebSocket.OPEN && status.ma2 === 'logged_in' && !status.halted &&
      (!status.show_load || status.show_load.state !== 'loading');
  }
  function enabled() {
    return ready() && (!status.features || status.features.scenes === undefined || status.features.scenes === true);
  }
  function send(action) {
    if (!enabled() || pending.length) return;
    error.hidden = true;
    action = Object.assign({}, action, {request_id: prefix + ':' + (++serial)});
    pending.push(action);
    ws.send(JSON.stringify(action));
    render();
  }
  function sceneAllowed(scene) {
    return !status.safety || status.safety.mode === 'full' || (status.safety.scenes || []).includes(String(scene.exec));
  }
  function evidence(id) {
    const meta = runningMeta[id];
    let value = running[id];
    if (!meta || meta.source !== 'ma2' || meta.freshness !== 'fresh') value = null;
    if (value !== true && value !== false) value = null;
    return {value, label: value === true ? 'идёт · MA2' : value === false ? 'остановлена · MA2' :
      meta && meta.freshness === 'stale' ? 'статус устарел' : 'статус неизвестен'};
  }
  function render() {
    connection.textContent = !ws || ws.readyState !== WebSocket.OPEN ? 'Нет связи с мостом' :
      status.halted ? 'Передача остановлена' : status.ma2 !== 'logged_in' ? 'Нет связи с пультом' :
      status.show_load && status.show_load.state === 'loading' ? 'Загружается шоу…' : status.mock ? 'Имитация · подключено' : 'Подключено';
    blackout.disabled = !enabled() || !!pending.length;
    scenes.replaceChildren();
    const list = Array.isArray(config.scenes) ? config.scenes : [];
    if (!list.length) {
      const empty = document.createElement('p'); empty.className='muted'; empty.textContent='Сцен пока нет'; scenes.append(empty);
    }
    const section = document.createElement('section');
      const tiles = document.createElement('div'); tiles.className = 'simple-tiles';
      list.forEach((scene,index) => {
        const current = evidence(scene.id);
        const tile = document.createElement('div');
        tile.className = 'simple-scene' + (current.value === true ? ' running' : '');
        const allowed = sceneAllowed(scene);
        const go = document.createElement('button'); go.type = 'button'; go.className = 'go';
        go.disabled = !enabled() || !allowed || !!pending.length || !!scene.write_error;
        go.textContent = (index + 1) + ' · ' + (scene.label || 'Без названия') + (scene.write_error ? ' · Запись не подтверждена' : ' · ' + current.label);
        go.onclick = () => send({a: 'scene_go', id: scene.id, swap: config.scenes.filter(o => o.id !== scene.id && sceneAllowed(o) && evidence(o.id).value !== false).map(o => o.id)});  // replace configured scenes unless a fresh read proves they are stopped
        tile.append(go);
        if (current.value !== false) {
          const off = document.createElement('button'); off.type = 'button'; off.textContent = 'Выключить';
          off.disabled = !enabled() || !allowed || !!pending.length;
          off.setAttribute('aria-label', 'Выключить сцену «' + (scene.label || scene.exec) + '»');
          off.onclick = () => send({a: 'scene_off', id: scene.id}); tile.append(off);
        }
        tiles.append(tile);
      });
      section.append(tiles); scenes.append(section);
  }
  blackout.onclick = () => { if (confirm('Погасить всё?')) send({a: 'blackout'}); };
  function connect() {
    ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws');
    ws.onopen = render;
    ws.onmessage = event => {
      const msg = JSON.parse(event.data);
      if (msg.status) {
        status = msg.status;
        if (status.ma2 !== 'logged_in' || status.show_load && status.show_load.state === 'loading') { running = {}; runningMeta = {}; receipts = {}; }
      }
      if (msg.config) {
        if (config.show !== msg.config.show) { running = {}; runningMeta = {}; receipts = {}; }
        config = msg.config;
      }
      if (msg.running) Object.assign(running, msg.running);
      if (msg.running_meta) {
        Object.keys(msg.running_meta).forEach(id => {
          const meta = msg.running_meta[id], old = receipts[id];
          if (meta.freshness !== 'fresh') delete receipts[id];
          else if (!old || old.stamp !== meta.updated_at) receipts[id] = {stamp: meta.updated_at, at: Date.now()};
          else if (Date.now() - old.at >= 6000) meta.freshness = 'stale';
        });
        Object.assign(runningMeta, msg.running_meta);
      }
      if ('ok' in msg) {
        const index = pending.findIndex(action => action.request_id === msg.request_id);
        if (index < 0) return;
        const action = pending.splice(index, 1)[0];
        if (!msg.ok) { error.classList.remove('sent'); error.textContent = (msg.outcome === 'unknown' ? 'Результат неизвестен. ' : msg.outcome === 'partial' ? 'Выполнена только часть операции. ' : '') + (msg.err || 'Не удалось выполнить'); error.hidden = false; }
        else if (action) { error.classList.add('sent'); error.textContent = 'Команда отправлена'; error.hidden = false; }
      }
      render();
    };
    ws.onclose = () => { if (pending.length) { error.classList.remove('sent'); error.textContent = 'Связь прервана: результат неизвестен. Команда не повторена.'; error.hidden = false; } status = {}; pending = []; running = {}; runningMeta = {}; receipts = {}; render(); setTimeout(connect, 1500); };
    ws.onerror = () => ws.close();
  }
  setInterval(() => {
    let changed = false;
    Object.keys(receipts).forEach(id => {
      if (Date.now() - receipts[id].at < 6000) return;
      if (runningMeta[id] && runningMeta[id].freshness === 'fresh') {
        runningMeta[id] = Object.assign({}, runningMeta[id], {freshness: 'stale'});
        running[id] = null;
        changed = true;
      }
    });
    if (changed) render();
  }, 500);
  connect();
})();
