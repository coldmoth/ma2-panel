'use strict';
(() => {
  let ws, status = {}, config = {scenes: [], pages: []}, running = {}, pending = [];
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
    pending.push(action);
    ws.send(JSON.stringify(action));
    render();
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
        const tile = document.createElement('div');
        tile.className = 'simple-scene' + (running[scene.id] ? ' running' : '');
        const allowed = !status.safety || status.safety.mode === 'full' || (status.safety.scenes || []).includes(String(scene.exec));
        const go = document.createElement('button'); go.type = 'button'; go.className = 'go';
        go.disabled = !enabled() || !allowed || !!pending.length || !!scene.write_error;
        go.textContent = (index + 1) + ' · ' + (scene.label || 'Без названия') + (scene.write_error ? ' · Запись не подтверждена' : running[scene.id] ? ' · идёт' : '');
        go.onclick = () => send({a: 'scene_go', id: scene.id, swap: config.scenes.filter(o => o.id !== scene.id && running[o.id]).map(o => o.id)});  // a scene replaces the running ones (spec 20)
        tile.append(go);
        if (running[scene.id]) {
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
        if (status.show_load && status.show_load.state === 'loading') running = {};
      }
      if (msg.config) config = msg.config;
      if (msg.running) Object.assign(running, msg.running);
      if ('ok' in msg) {
        const action = pending.shift();
        if (!msg.ok) { error.textContent = msg.err || 'Не удалось выполнить'; error.hidden = false; }
        else if (action) {
          if (action.a === 'blackout') running = {};
          else running[action.id] = action.a === 'scene_go';
        }
      }
      render();
    };
    ws.onclose = () => { status = {}; pending = []; running = {}; render(); setTimeout(connect, 1500); };
    ws.onerror = () => ws.close();
  }
  connect();
})();
