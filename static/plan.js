/* Hall plan drawn from config.hall, and the Зал section: hall shape, step-by-step placement with highlight, panel groups, beam calibration. */
var planState = {fixtureSettings: false,editing: false, ping: null, tab: 'place', cur: 0, newGroup: '', snap: false};
try { planState.snap = localStorage.getItem('ma2.snap') === '1'; } catch (error) {}
var planView = {key:null,zoom:1,x:0,y:0,mode:'select',auto:true};
var HALL_DEFAULT = {w: 18, d: 14, stage: 'top', stageDepth: 4};

function planKind(f) {
  if (['par', 'bar', 'head', 'fresnel'].indexOf(f.icon) >= 0) return f.icon;  // chosen by the operator in «Расстановка»
  if (f.type === 'bar' || /bar/i.test(f.type || '')) return 'bar';
  if (canMove(f)) return 'head';
  if (/fresnel|profile/i.test(f.type || '')) return 'fresnel';
  return 'par';
}
function placed(f) { return typeof f.x === 'number' && typeof f.y === 'number'; }
function hallOf() { return (state.config && state.config.hall) || null; }
function planKey() {
  if (state.sec !== 'hall' && !(state.sec === 'light' && lightUI && lightUI.tab === 'plan')) return '';
  return [planState.tab, planState.cur, planState.editing, !!planState.ping, planState.snap, !!planState.hallDraft].join(':');
}

/* ---------- edit session ---------- */
function planBeginEdit() {
  planState.hallDraft = null;
  planState.revision = state.config && state.config.revision;
  planState.editing = true;
  planState.tab = hallOf() ? 'place' : 'shape';
  stopPing();
  send({a: 'edit_begin'});
}
function stopPing() {
  if (planState.ping !== null) clearInterval(planState.ping);
  planState.ping = null;
}
// Leaving the editor in any way releases the highlight first; the bridge also does it on disconnect or lease timeout.
function planEndEdit() {
  if (!planState.editing) return;
  stopPing();
  planState.editing = false;
  // Always: a highlight the status has not reported yet is still released; on an idle bridge it does nothing.
  send({a: 'highlight_off'});
  send({a: 'edit_end'});
}
function highlightOn(on) {
  if (on) {
    // edit_begin again: entering Зал may have happened while the link was down and been refused.
    if (!planState.editing) planBeginEdit(); else send({a: 'edit_begin'});
    planState.ping = setInterval(function () { send({a: 'highlight_ping'}); }, 3000);
    var cur = planCurrent();
    if (cur) send({a: 'highlight', id: cur.id});
  } else {
    stopPing();
    send({a: 'highlight_off'});
    send({a: 'edit_end'});
    send({a: 'edit_begin'});
  }
  render();
}

// Schematic Pan from panel history or mock simulation; never a measured beam or a Tilt projection.
function planBeamAngle(f, hc) {
  var sim = state.mock && connected() && state.simulation && state.simulation[f.id];
  var pan = (sim || state.shown[f.id] || {}).pan, home = (f.beam || {}).home;
  var range = ((state.config || {}).attrs || {}).pan || {};
  if (!connected() || f.missing || !canMove(f) || !Number.isFinite(pan) || !Number.isFinite(home) ||
      valueFreshness('sent:' + f.id + ':pan') === 'stale' ||
      valueFreshness('sent:' + f.id + ':pan') === 'unknown' ||
      !Number.isFinite(range.min) || !Number.isFinite(range.max) || range.max <= range.min) return null;
  var depth = Math.min(hc.stageDepth || 3, (hc.stage === 'left' || hc.stage === 'right' ? hc.w : hc.d) * .45);
  var target = {top: [hc.w / 2, depth / 2], bottom: [hc.w / 2, hc.d - depth / 2],
    left: [depth / 2, hc.d / 2], right: [hc.w - depth / 2, hc.d / 2]}[hc.stage];
  if (!target) return null;
  return Math.atan2(target[1] - f.y * hc.d, target[0] - f.x * hc.w) * 180 / Math.PI +
    (pan - home) / 100 * (range.max - range.min) * (f.beam.invert ? -1 : 1);
}

/* ---------- plan widget ---------- */
function hallPlan(root, mode) {
  var hc = hallOf() || HALL_DEFAULT;
  var wrap = h('div', {class: 'hall-wrap' + (mode === 'edit' ? ' edit' : '')});
  var hall = h('div', {class: 'hall', role: 'group', 'aria-label': 'Схема зала'});
  var viewKey = JSON.stringify([state.config && state.config.show,hc.w,hc.d,hc.stage,hc.stageDepth]);
  if (mode === 'control' && planView.key !== viewKey) planView = {key:viewKey,zoom:1,x:0,y:0,mode:'select',auto:true};
  var zoomReadout;
  if (mode === 'control') {
    wrap.classList.add('plan-viewport'); wrap.setAttribute('tabindex','0');
    wrap.dataset.mode=planView.mode;
    zoomReadout=h('output',{'aria-label':'Масштаб плана'},Math.round(planView.zoom*100)+'%');
    var toolbar=h('div',{class:'plan-toolbar',role:'group','aria-label':'Вид плана'},
      h('button',{class:'btn small',type:'button','aria-label':'Уменьшить план',onclick:function(){zoomTo(planView.zoom/1.35);}},'−'),zoomReadout,
      h('button',{class:'btn small',type:'button','aria-label':'Увеличить план',onclick:function(){zoomTo(planView.zoom*1.35);}},'+'),
      h('button',{class:'btn small',type:'button',title:'Вписать план',onclick:function(){fit();}},'Вписать'));
    var modeButtons=[];
    add(toolbar,h('div',{class:'seg'},[['select','Выделение'],['pan','Перемещение']].map(function(pair){
      var b=h('button',{type:'button','aria-label':pair[1],title:pair[1], 'aria-pressed':String(planView.mode===pair[0]),onclick:function(){
        planView.mode=pair[0];wrap.dataset.mode=pair[0];modeButtons.forEach(function(btn){btn.setAttribute('aria-pressed',String(btn===b));});
      }},h('span',{},pair[0]==='select'?'Выбор':'Сдвиг'));modeButtons.push(b);return b;
    })));
    add(root,toolbar);
    wrap.addEventListener('scroll',function(){
      planView.x=wrap.scrollLeft;planView.y=wrap.scrollTop;
      if(planView.x || planView.y)planView.auto=false;
    });
    wrap.addEventListener('wheel',function(e){if(!e.ctrlKey && !e.metaKey)return;e.preventDefault();zoomTo(planView.zoom*Math.exp(-e.deltaY*.008),e.clientX,e.clientY);},{passive:false});
    wrap.addEventListener('keydown',function(e){
      if(e.target!==wrap)return;
      if(e.key==='+' || e.key==='='){e.preventDefault();zoomTo(planView.zoom*1.35);}
      if(e.key==='-'){e.preventDefault();zoomTo(planView.zoom/1.35);}
      if(e.key==='0'){e.preventDefault();fit();}
      var delta={ArrowLeft:[-80,0],ArrowRight:[80,0],ArrowUp:[0,-80],ArrowDown:[0,80]}[e.key];
      if(delta){e.preventDefault();wrap.scrollLeft+=delta[0];wrap.scrollTop+=delta[1];}
    });
  }
  add(wrap, hall);
  add(root, wrap);
  var disclaimer = 'Расчётное направление по Pan панели · не измерение луча; Tilt не проецируется';
  var outputSource = mode === 'control' ? h('summary', {class: 'note'}) : null;
  if (outputSource) add(root, h('details', {class: 'plan-source'}, outputSource,
    h('p', {class: 'note'}, disclaimer + '. Масштаб — кнопками, Ctrl/Command + колесо или двумя пальцами. «Вписать» включает автоподгонку.')));
  else add(root, h('p', {class: 'note'}, disclaimer));
  var restoreView = true;
  function size() {
    if (wrap.isConnected === false) { if (observer) observer.disconnect(); return; }
    var gutter = mode === 'control' ? 64 : 0;
    var W = wrap.clientWidth - gutter, H = wrap.clientHeight - gutter, ratio = hc.w / hc.d;
    if (W <= 0 || H <= 0) return;
    var hw = W, hh = W / ratio;
    if (hh > H) { hh = H; hw = H * ratio; }
    if(mode==='control' && planView.auto) planView.zoom=1;
    // Names need more room than the 52px hit area; use IDs when neighbours are close.
    if (mode === 'edit') {
      var placedFixtures = fixtures().filter(placed), dense = false;
      for (var i = 0; i < placedFixtures.length && !dense; i++) {
        for (var j = i + 1; j < placedFixtures.length; j++) {
          if (Math.abs(placedFixtures[i].x - placedFixtures[j].x) * hw < 84 &&
              Math.abs(placedFixtures[i].y - placedFixtures[j].y) * hh < 64) { dense = true; break; }
        }
      }
      hall.classList.toggle('compact-labels', dense);
    }
    var z=mode==='control'?planView.zoom:1;
    hall.style.width = Math.floor(hw*z) + 'px';
    hall.style.height = Math.floor(hh*z) + 'px';
    if(mode==='control') {
      hall.style.marginLeft=Math.max(0,(W-hw*z)/2)+'px';hall.style.marginTop=Math.max(0,(H-hh*z)/2)+'px';
      zoomReadout.textContent=Math.round(z*100)+'%';
      if(restoreView){wrap.scrollLeft=planView.x;wrap.scrollTop=planView.y;restoreView=false;}
    }
  }
  function fit() {
    planView.auto=true;planView.zoom=1;planView.x=planView.y=0;
    size();wrap.scrollLeft=wrap.scrollTop=0;
  }
  function zoomTo(value,cx,cy) {
    var z=planView.zoom, next=Math.max(1,Math.min(5,value)),r=wrap.getBoundingClientRect(),hr=hall.getBoundingClientRect();
    var px=cx===undefined?r.left+r.width/2:cx,py=cy===undefined?r.top+r.height/2:cy;
    var x=(px-hr.left)/hr.width,y=(py-hr.top)/hr.height;
    planView.auto=false;planView.zoom=next;size();
    var nr=hall.getBoundingClientRect();
    wrap.scrollLeft+=nr.left+x*nr.width-px;wrap.scrollTop+=nr.top+y*nr.height-py;
    planView.x=wrap.scrollLeft;planView.y=wrap.scrollTop;
  }
  if (typeof ResizeObserver === 'function') {
    var observer=new ResizeObserver(size);observer.observe(wrap);
  }
  add(hall, h('div', {class: 'grid' + (mode === 'edit' && planState.snap ? ' snap' : '')}));
  var across = hc.stage === 'top' || hc.stage === 'bottom';
  var depth = Math.min(45, (hc.stageDepth || 3) / (across ? hc.d : hc.w) * 100) + '%';
  var sp = {top: {left: '0', top: '0', width: '100%', height: depth}, bottom: {left: '0', bottom: '0', width: '100%', height: depth},
    left: {left: '0', top: '0', height: '100%', width: depth}, right: {right: '0', top: '0', height: '100%', width: depth}}[hc.stage] || {};
  add(hall, h('div', {class: 'stage', style: sp}, 'СЦЕНА'));
  var beamLayer = h('div', {class: 'plan-beams', 'aria-hidden': 'true'});
  add(hall, beamLayer);
  var dots = {};
  fixtures().forEach(function (f) {
    if (!placed(f)) return;
    var b = h('button', {class: 'fx k-' + planKind(f), type: 'button', 'data-id': f.id, title:f.id+' '+(f.label || f.name || ''), 'aria-label': f.id + ' ' + (f.label || f.name) + (f.missing ? ', нет в шоу' : '') + (f.service ? ', служебный' : ''),
      style: {left: f.x * 100 + '%', top: f.y * 100 + '%'}, onclick: function (ev) {
        // Native keyboard/assistive activation has detail=0. Pointer taps finish below.
        if (ev.detail === 0 && !b.disabled && connected()) tapFixture(f.id, mode);
      }}, h('span', {class: 'g', style: f.rot === 90 && planKind(f) === 'bar' ? {width: '14px', height: '34px'} : {}}), h('span', {class: 'l'}, f.label || f.id), h('span', {class: 'i'}, f.id));
    var beam = canMove(f) ? h('div', {class: 'plan-beam', 'aria-hidden': 'true', style: {left: f.x * 100 + '%', top: f.y * 100 + '%'}}) : null;
    if (beam) add(beamLayer, beam);
    dots[f.id] = {el: b, f: f, beam: beam};
    add(hall, b);
  });
  var hint = null;
  if (mode === 'edit') { hint = h('div', {class: 'place-hint'}); add(hall, hint); }
  updaters.push(function () {
    size();
    var liveMeta = state.valuesMeta.live;
    var freshOutput = liveMeta && liveMeta.source === 'ma2' && liveMeta.freshness === 'fresh';
    var simulated = state.mock && connected() && state.simulation && Object.keys(state.simulation).length > 0;
    if (outputSource) outputSource.textContent = simulated ? 'Симуляция · выход mock MA2' : valueFreshness('live') === 'stale' ? 'Чтение MA2 устарело · свет на плане неизвестен' :
      freshOutput && Object.keys(state.live).length ? 'Выход прочитан с MA2' : 'Текущий выход MA2 неизвестен';
    var hl = state.highlight || {}, active = hl.state === 'active' && planState.ping !== null;
    var zone = hl.zone || hl.available || [];
    var cur = mode === 'edit' ? planCurrent() : null;
    Object.keys(dots).forEach(function (id) {
      var d = dots[id], f = d.f, shown = state.shown[id] || state.shown[f.id];
      if (d.beam) {
        var angle = planBeamAngle(f, hallOf() || HALL_DEFAULT);
        d.beam.hidden = angle === null;
        d.beam.style.transform = 'rotate(' + (angle === null ? 0 : angle) + 'deg)';
        d.beam.className = 'plan-beam' + (state.selection.indexOf(f.id) >= 0 ? ' selected' : '');
      }
      var cls = ['fx', 'k-' + planKind(f)];
      // Groups tab picks a set like Свет does; placement marks the one current fixture.
      var picking = mode === 'control' || planState.tab === 'groups';
      if (picking && state.selection.indexOf(f.id) >= 0) cls.push('sel');
      if (mode === 'edit' && !picking && cur && cur.id === f.id) cls.push('cur');
      if (f.missing) cls.push('missing');
      if (f.service) cls.push('service');
      // Simulation is explicitly separate; real output still requires fresh MA2 evidence.
      var live = simulated ? state.simulation[id] : freshOutput ? state.live[id] : null;
      if (mode === 'control') {
        var outputLabel = live ? 'выход ' + live.dim + (simulated ? '% · Симуляция' : '% · MA2') : 'выход неизвестен';
        d.el.setAttribute('title', f.id + ' · ' + (f.label || f.name || f.id) + ' · ' + outputLabel);
        d.el.setAttribute('aria-label', f.id + ' ' + (f.label || f.name || f.id) + ', ' + outputLabel +
          (f.missing ? ', нет в шоу' : '') + (f.service ? ', служебный' : ''));
      }
      shown = live;
      if (mode === 'control' && shown && shown.dim > 0 &&
          Array.isArray(shown.rgb) && shown.rgb.length === 3 &&
          shown.rgb.every(function (v) { return Number.isFinite(v) && v >= 0 && v <= 100; }) &&
          shown.rgb.some(function (v) { return v > 0; })) {
        cls.push('lit');
        d.el.style.setProperty('--c', 'rgba(' + (shown.rgb || [92, 90, 86]).map(function (v) { return Math.round(v * 2.55); }).join(',') + ',' +
          (typeof shown.dim === 'number' ? Math.max(0, Math.min(1, shown.dim / 100)) : .7) + ')');
      }
      if (active && hl.target === f.id) cls.push('hl-target');
      else if (active && hl.target && zone.indexOf(f.id) >= 0) cls.push('hl-dark');
      d.el.className = cls.join(' ');
      d.el.setAttribute('aria-pressed', String(cls.indexOf('sel') >= 0 || cls.indexOf('cur') >= 0));
      d.el.disabled = !connected() || mode === 'control' && (!!f.missing || !allowedFixture(f.id));
    });
    if (hint) {
      hint.hidden = !cur || placed(cur);
      if (cur) hint.textContent = 'Нажмите на схему, где висит ' + (cur.label || cur.name || cur.id);
    }
  });

  var drag = null, lasso = null;
  if(mode==='control') {
    var pointers={},nav=null;
    function clearPick(){drag=null;if(lasso && lasso.el.parentNode)lasso.el.parentNode.removeChild(lasso.el);lasso=null;}
    wrap.addEventListener('pointerdown',function(e){
      if(e.button>0)return;
      pointers[e.pointerId]={x:e.clientX,y:e.clientY};
      var pts=Object.values(pointers);
      if(pts.length===2 || planView.mode==='pan'){
        clearPick();
        nav=pts.length===2?{pinch:true,d:Math.hypot(pts[1].x-pts[0].x,pts[1].y-pts[0].y),z:planView.zoom}:
          {x:e.clientX,y:e.clientY,left:wrap.scrollLeft,top:wrap.scrollTop};
        try{wrap.setPointerCapture(e.pointerId);}catch(error){}
        e.preventDefault();e.stopPropagation();
      }
    },true);
    wrap.addEventListener('pointermove',function(e){
      if(!pointers[e.pointerId])return;pointers[e.pointerId]={x:e.clientX,y:e.clientY};
      if(!nav)return;
      var pts=Object.values(pointers);
      if(nav.pinch && pts.length===2)zoomTo(nav.z*Math.hypot(pts[1].x-pts[0].x,pts[1].y-pts[0].y)/Math.max(1,nav.d),(pts[0].x+pts[1].x)/2,(pts[0].y+pts[1].y)/2);
      else if(!nav.pinch){wrap.scrollLeft=nav.left+nav.x-e.clientX;wrap.scrollTop=nav.top+nav.y-e.clientY;}
      e.preventDefault();e.stopPropagation();
    },true);
    ['pointerup','pointercancel','lostpointercapture'].forEach(function(type){wrap.addEventListener(type,function(e){
      delete pointers[e.pointerId];
      if(nav){clearPick();e.stopPropagation();if(!Object.keys(pointers).length)nav=null;}
      planView.x=wrap.scrollLeft;planView.y=wrap.scrollTop;
    },true);});
  }
  function pct(ev) {
    var r = hall.getBoundingClientRect();
    // Snap: to the 5 % dots of the grid, so fixtures in one row line up.
    var c = function (v) { v = Math.min(1, Math.max(0, v)); if (mode === 'edit' && planState.snap) v = Math.min(.975, (Math.floor(v / .05) + .5) * .05); return Math.round(v * 1000) / 1000; };
    return {x: c((ev.clientX - r.left) / r.width), y: c((ev.clientY - r.top) / r.height)};
  }
  hall.addEventListener('pointerdown', function (ev) {
    if (!connected() || ev.button > 0) return;
    var btn = ev.target.closest('.fx');
    var p = pct(ev);
    if (btn && btn.disabled) return;
    if (btn) {
      drag = {id: Number(btn.dataset.id), el: btn, start: p, moved: false, pointer: ev.pointerId};
      btn.setPointerCapture(ev.pointerId);
      return;
    }
    if (mode === 'edit') {
      var cur = planCurrent();
      if (cur && !placed(cur) && !cur.missing) { send({a: 'layout_save', pos: [{id: cur.id, x: p.x, y: p.y}]}); planNext(true); }
      return;
    }
    lasso = {start: p, el: h('div', {class: 'lasso'}), pointer: ev.pointerId};
    hall.setPointerCapture(ev.pointerId);
  });
  hall.addEventListener('pointermove', function (ev) {
    var p = pct(ev);
    if (drag && drag.pointer === ev.pointerId) {
      if (mode === 'edit' && (drag.moved || Math.hypot(p.x - drag.start.x, p.y - drag.start.y) > .015)) {
        drag.moved = true;
        drag.el.classList.add('dragging');
        drag.el.style.left = p.x * 100 + '%';
        drag.el.style.top = p.y * 100 + '%';
      }
      return;
    }
    if (lasso && lasso.pointer === ev.pointerId) {
      if (!lasso.el.parentNode && Math.hypot(p.x - lasso.start.x, p.y - lasso.start.y) > .02) add(hall, lasso.el);
      lasso.end = p;
      lasso.el.style.left = Math.min(p.x, lasso.start.x) * 100 + '%';
      lasso.el.style.top = Math.min(p.y, lasso.start.y) * 100 + '%';
      lasso.el.style.width = Math.abs(p.x - lasso.start.x) * 100 + '%';
      lasso.el.style.height = Math.abs(p.y - lasso.start.y) * 100 + '%';
    }
  });
  function finish(ev, commit) {
    if (drag && drag.pointer === ev.pointerId) {
      var d = drag; drag = null;
      if (!commit || !connected()) { sectionKey = null; render(); return; }
      if (d.moved) { var p = pct(ev); send({a: 'layout_save', pos: [{id: d.id, x: p.x, y: p.y}]}); return; }
      tapFixture(d.id, mode);
      return;
    }
    if (lasso && lasso.pointer === ev.pointerId) {
      var l = lasso; lasso = null;
      if (l.el.parentNode) l.el.parentNode.removeChild(l.el);
      if (!commit || !l.end) return;
      var x1 = Math.min(l.start.x, l.end.x), x2 = Math.max(l.start.x, l.end.x), y1 = Math.min(l.start.y, l.end.y), y2 = Math.max(l.start.y, l.end.y);
      var ids = fixtures().filter(function (f) { return placed(f) && !f.missing && allowedFixture(f.id) && f.x >= x1 && f.x <= x2 && f.y >= y1 && f.y <= y2; }).map(function (f) { return f.id; });
      if (ids.length) selectFixtures(state.selection.concat(ids.filter(function (id) { return state.selection.indexOf(id) < 0; })));
    }
  }
  hall.addEventListener('pointerup', function (ev) { finish(ev, true); });
  hall.addEventListener('pointercancel', function (ev) { finish(ev, false); });
  return wrap;
}

function tapFixture(id, mode) {
  var f = fixture(id);
  if (!f || f.missing && mode === 'control') return;
  if (mode === 'control') {
    var ids = state.selection.slice(), i = ids.indexOf(id);
    if (i < 0) ids.push(id); else ids.splice(i, 1);
    selectFixtures(ids);
    return;
  }
  if (planState.tab === 'groups') {
    var sel = state.selection.slice(), j = sel.indexOf(id);
    if (j < 0) sel.push(id); else sel.splice(j, 1);
    selectFixtures(sel);
    return;
  }
  planState.cur = planOrder().indexOf(f);
  planLight();
  render();
}

/* ---------- placement order ---------- */
function planOrder() { return fixtures().filter(function (f) { return !f.missing; }); }
function planCurrent() {
  var order = planOrder();
  if (!order.length) return null;
  planState.cur = Math.max(0, Math.min(order.length - 1, planState.cur));
  return order[planState.cur];
}
function planLight() {
  var cur = planCurrent();
  if (cur && planState.ping !== null && !cur.service) send({a: 'highlight', id: cur.id});
}
// After placing, jump to the next fixture without a place; otherwise just the next one.
function planNext(afterPlace) {
  var order = planOrder();
  if (!order.length) return;
  var start = planState.cur;
  if (afterPlace) {
    for (var k = 1; k <= order.length; k++) {
      var i = (start + k) % order.length;
      if (!placed(order[i]) && i !== start) { planState.cur = i; planLight(); render(); return; }
    }
  }
  planState.cur = (start + 1) % order.length;
  planLight();
  render();
}
function planStep(d) {
  var n = planOrder().length;
  if (!n) return;
  planState.cur = (planState.cur + d + n) % n;
  planLight();
  render();
}

/* ---------- Зал ---------- */
SECTIONS.hall = function (el) {
  var ready = connected();
  var hl = state.highlight || {};
  var zone = hl.available || [];
  var page = h('div', {class: 'hallpage'});
  add(el, page);
  var lit = planState.ping !== null;
  var hlBox = h('input', {type: 'checkbox', checked: lit, disabled: !ready || !safe('allow_highlight') || !hallOf(), onchange: function (e) {
    // The highlight puts the other hall fixtures At 0 and removes itself with Off: both touch the desk's programmer.
    if (e.target.checked && !confirm('Подсветка гасит остальные приборы зала, а при снятии убирает их значения командой Off — вместе с тем, что выставлено на пульте вручную. Включать только при подготовке, не во время шоу. Включить?')) { e.target.checked = false; return; }
    highlightOn(e.target.checked);
  }});
  add(page, h('div', {class: 'hallbar'}, h('b', {class: 'ttl'}, 'Редактор зала'),
    h('div', {class: 'seg'}, [['place', 'Расстановка'], ['groups', 'Группы'], ['shape', 'Форма зала'], ['beam', 'Луч']].map(function (t) {
      return h('button', {type: 'button', 'aria-pressed': String(planState.tab === t[0]), onclick: function () { planState.tab = t[0]; render(); }}, t[1]);
    })),
    h('span', {class: 'spacer'}),
    h('label', {class: 'chk', title: safe('allow_highlight') ? '' : 'Подсветка выключена в настройках (allow_highlight)'}, hlBox, 'Подсвечивать выбранный прибор в зале'),
    h('label', {class: 'chk'}, h('input', {type: 'checkbox', checked: planState.snap, onchange: function (e) {
      planState.snap = e.target.checked;
      try { localStorage.setItem('ma2.snap', planState.snap ? '1' : '0'); } catch (error) {}
      render();
    }}), 'Привязка к сетке'),
    h('button', {class: 'btn small edit', type: 'button', onclick: function () { go('light'); }}, icon('check', 18), 'Готово')));
  if (!hallOf() || planState.tab === 'shape') { add(page, h('div', {class: 'center'}, hallForm())); return; }
  if (planState.tab === 'beam') { add(page, h('div', {class: 'center'}, beamCard())); return; }
  var body = h('div', {class: 'hallbody'});
  var box = h('div', {class: 'planbox'});
  add(body, box);
  add(page, body);
  hallPlan(box, 'edit');
  var side = h('aside', {class: 'side', 'data-scroll': 'side-' + planState.tab});
  add(body, side);
  var service = fixtures().filter(function (f) { return f.service; });
  if (planState.tab === 'groups') { groupSide(side); return; }
  add(side, h('p', {class: 'note'}, (lit ? 'Подсветка запрошена для выбранного прибора и ' + Math.max(0, zone.length - 1) + ' остальных приборов плана. Автоснятие возможно только без новых действий со светом и потери контекста. Если подсветка не снята, смотрите предупреждение сверху. ' :
    'С подсветкой выбранный прибор загорится, а ' + Math.max(0, zone.length - 1) + ' других приборов плана погаснут. ') +
    'Не трогаются: ' + (service.length ? service.map(function (f) { return f.label || f.name; }).join(', ') + ' (служебные), ' : '') + 'приборы вне списка панели, сцены, программер других пользователей.'));
  var order = planOrder(), cur = planCurrent();
  var curRow = null;
  fixtures().forEach(function (f) {
    var row = h('button', {class: 'row-item', type: 'button', 'aria-pressed': String(!!cur && cur.id === f.id), disabled: !!f.missing, onclick: function () { planState.cur = order.indexOf(f); planLight(); render(); }},
      h('span', {class: 'id'}, f.id), h('span', {class: 'grow'}, h('b', {}, f.label || f.name), h('span', {class: 'meta'}, f.missing ? 'нет в патче MA2' : placed(f) ? 'на плане' : 'не на плане')),
      canMove(f) ? h('span', {class: 'tag'}, 'голова') : null, f.service ? h('span', {class: 'tag'}, 'служ.') : null);
    if (cur && cur.id === f.id) curRow = row;
    add(side, row);
  });
  // The current fixture stays in view when it was picked on the plan or by «Следующий».
  if (curRow) setTimeout(function () {
    // scrollIntoView also moves #page on phones, hiding the tools above the plan.
    var rowBounds = curRow.getBoundingClientRect(), listBounds = side.getBoundingClientRect();
    if (rowBounds.top < listBounds.top) side.scrollTop += rowBounds.top - listBounds.top;
    else if (rowBounds.bottom > listBounds.bottom) side.scrollTop += rowBounds.bottom - listBounds.bottom;
  }, 0);
  var done = order.filter(placed).length;
  var sameType = cur && cur.type ? fixtures().filter(function (f) { return f.type === cur.type; }).length : 0;
  var card = h('div', {class: 'now-card'});
  if (cur) add(card, h('div', {class: 'who'}, h('span', {class: 'note'}, placed(cur) ? 'Можно перетащить на другое место' : 'Нажмите на схему там, где он висит'),
      h('b', {}, cur.id + ' · ' + (cur.label || cur.name)), h('span', {class: 'note'}, cur.type || '')),
    h('button', {class: 'btn', type: 'button', onclick: function () { planStep(-1); }}, icon('back', 18), 'Назад'),
    h('details', {class:'fixture-settings', open:planState.fixtureSettings, ontoggle:function(e){planState.fixtureSettings=e.currentTarget.open;}},
      h('summary',{},'Настройки прибора'),h('div',{class:'fixture-settings-body'},
    placed(cur) ? h('button', {class: 'btn', type: 'button', disabled: !ready, onclick: function (e) { send({a: 'layout_save', pos: [{id: cur.id, x: null, y: null}]}, e.currentTarget); }}, 'Убрать с плана') : null,
    placed(cur) ? h('button', {class: 'btn', type: 'button', disabled: !ready, title: 'Бар вдоль стены: повернуть схемный значок на 90°',
      onclick: function (e) { send({a: 'fixture_flag', id: cur.id, rot: cur.rot === 90 ? 0 : 90}, e.currentTarget); }}, icon('refresh', 18), 'Повернуть 90°') : null,
    h('div', {class: 'seg', role: 'group', 'aria-label': 'Значок на схеме'}, [['par', '● Круг'], ['bar', '▬ Прямоугольник'], ['head', '■ Квадрат'], ['fresnel', '◆ Ромб']].map(function (k) {
      return h('button', {type: 'button', 'aria-pressed': String(planKind(cur) === k[0]), disabled: !ready,
        onclick: function (e) { send({a: 'fixture_flag', id: cur.id, icon: k[0]}, e.currentTarget); }}, k[1]);
    })),
    h('button', {class: 'btn', type: 'button', disabled: !ready, onclick: function (e) { send({a: 'fixture_flag', id: cur.id, service: !cur.service}, e.currentTarget); }}, cur.service ? 'Не служебный' : 'Служебный, не гасить'),
    h('button', {class: 'btn', type: 'button', 'aria-pressed': String(cur.moves === true), disabled: !ready, title: 'Прибор с Pan/Tilt: доступен в «Свете» → «Позиция и луч»',
      onclick: function (e) { send({a: 'fixture_flag', id: cur.id, moves: cur.moves !== true}, e.currentTarget); }}, cur.moves === true ? icon('check', 18) : null, 'Голова' + (cur.moves === true && cur.moves_auto ? ' (угадано)' : '')),
    sameType > 1 ? h('button', {class: 'btn', type: 'button', disabled: !ready, title: 'Тип «' + cur.type + '»: ' + sameType + ' шт.',
      onclick: function (e) { send({a: 'fixture_flag', id: cur.id, moves: cur.moves !== true, same_type: true}, e.currentTarget); }}, 'Голова: все ' + sameType + ' такого типа') : null)),
    h('button', {class: 'btn edit', type: 'button', onclick: function () { planStep(1); }}, placed(cur) ? 'Следующий' : 'Пропустить', icon('chevron', 18)));
  add(card, h('div', {class: 'stack', style: {gap: '4px'}}, h('span', {class: 'note'}, 'На плане ' + done + ' из ' + order.length), h('div', {class: 'progress'}, h('i', {style: {width: done / Math.max(1, order.length) * 100 + '%'}}))),
    h('span', {class: 'note'}, 'Убрать с плана не удаляет прибор из патча MA2.'));
  add(page, card);
};

function hallForm() {
  var v = planState.hallDraft || Object.assign({}, hallOf() || HALL_DEFAULT);
  function num(k, label) {
    return h('div', {class: 'field'}, h('label', {for: 'hall-' + k}, label), h('input', {id: 'hall-' + k, type: 'number', min: 2, max: 80, step: 0.5, value: String(v[k]),
      oninput: function (e) { var n = Number(e.target.value); if (n > 0) { v[k] = n; planState.hallDraft = v; } }}));
  }
  var save = h('button', {class: 'btn edit full', type: 'button', disabled: !connected(), onclick: function () {
    if (document.activeElement) document.activeElement.blur();
    send({a: 'hall_save', hall: v}, save);
  }}, icon('check'), hallOf() ? 'Применить' : 'Создать схему и начать расстановку');
  return h('div', {class: 'card'}, h('h2', {}, hallOf() ? 'Форма зала' : 'Сначала нарисуйте зал'),
    h('p', {class: 'note'}, 'Размеры задают пропорции схемы. Пока только прямоугольный зал.'),
    planState.hallDraft && planState.revision !== state.config.revision ? h('div',{class:'note warn',role:'status'},
      'План изменён другим клиентом. Ваш черновик сохранён; запись со старой версией будет отклонена.',
      h('button',{class:'btn',type:'button',onclick:function(){planState.hallDraft=null;planState.revision=state.config.revision;render();}},'Отбросить черновик и принять новый план')) : null,
    h('div', {class: 'hallform'}, num('w', 'Ширина зала, м'), num('d', 'Глубина зала, м'),
      h('div', {class: 'field'}, h('label', {for: 'hall-stage'}, 'Сцена у стены'), h('select', {id: 'hall-stage', onchange: function (e) { v.stage = e.target.value; planState.hallDraft=v; }},
        [['top', 'сверху'], ['bottom', 'снизу'], ['left', 'слева'], ['right', 'справа']].map(function (o) { return h('option', {value: o[0], selected: v.stage === o[0]}, o[1]); }))),
      num('stageDepth', 'Глубина сцены, м'), save));
}
on('ok',function(ok,message){
  if (ok && message.a === 'hall_save' && ['unknown','partial','failed'].indexOf(message.outcome) < 0) {
    planState.hallDraft=null;planState.tab='place';render();
  }
});

function groupSide(side) {
  var ready = connected();
  var n = state.selection.length;
  var name = h('input', {id: 'group-name', maxlength: 30, placeholder: 'Например: Рояль', value: planState.newGroup, oninput: function (e) { planState.newGroup = e.target.value; }});
  var create = h('button', {class: 'btn primary', type: 'button', disabled: !ready || !n, onclick: function () {
    var label = planState.newGroup.trim();
    if (!label) { name.focus(); return; }
    if (document.activeElement) document.activeElement.blur();
    if (send({a: 'group_save', label: label, ids: state.selection.slice()}, create)) planState.newGroup = '';
  }}, icon('group'), 'Создать группу панели');
  add(side, h('h2', {}, 'Своя группа'),
    h('p', {class: 'note'}, n ? 'Выбрано ' + n + ': ' + state.selection.join(', ') : 'Нажимайте приборы на схеме по одному или обведите пальцем.'),
    h('div', {class: 'field'}, h('label', {for: 'group-name'}, 'Название'), name), create,
    h('p', {class: 'note'}, 'Группа панели хранится только в панели. На пульте её нет, пока вы не запишете её отдельно.'));
  ((state.config && state.config.groups) || []).filter(function (g) { return !('n' in g); }).forEach(function (g) {
    add(side, h('div', {class: 'grow-row wrap'}, h('span', {class: 'grow', title: g.label}, h('b', {}, g.label), h('span', {class: 'meta'}, g.fixtures.length + ' приб. · группа панели')),
      h('button', {class: 'btn small', type: 'button', disabled: !ready, onclick: function () { openGroupStore(g); }}, 'В MA2…'),
      h('button', {class: 'btn small ghost', type: 'button', 'aria-label': 'Удалить группу ' + g.label, disabled: !ready, onclick: function (e) {
        if (confirm('Удалить группу панели «' + g.label + '»? На пульте ничего не изменится.')) send({a: 'group_delete', id: g.id}, e.currentTarget);
      }}, icon('x', 18))));
  });
  ((state.config && state.config.ma2groups) || []).forEach(function (g) {
    add(side, h('div', {class: 'grow-row'}, h('span', {class: 'tag ma2'}, 'MA2 ' + g.n), h('span', {class: 'grow', title: g.name}, h('b', {}, g.name), h('span', {class: 'meta'}, 'только чтение'))));
  });
}

function openGroupStore(g) {
  var d = document.getElementById('dlg');
  var num = h('input', {id: 'gstore-n', type: 'number', min: 1, max: 9999, autocomplete: 'off'});
  var conf = h('input', {id: 'gstore-c', autocomplete: 'off'});
  var ok = h('button', {class: 'btn', type: 'button', disabled: !connected() || !safe('allow_group_store'), onclick: function () {
    if (!num.value || conf.value !== num.value) { notice('Номер не подтверждён: ничего не отправлено'); return; }
    if (send({a: 'group_store_ma2', id: g.id, n: Number(num.value), confirm: Number(conf.value)}, ok)) d.close();
  }}, 'Записать в MA2');
  d.textContent = '';
  add(d, h('div', {class: 'dlg'}, h('h2', {}, 'Записать «' + g.label + '» в MA2'),
    h('p', {}, 'Отдельное действие: в шоу на пульте появится Group с этими ' + g.fixtures.length + ' приборами. Группа панели останется как есть.'),
    h('div', {class: 'field'}, h('label', {for: 'gstore-n'}, 'Номер Group на пульте'), num),
    h('div', {class: 'field'}, h('label', {for: 'gstore-c'}, 'Повторите номер'), conf),
    h('p', {class: 'note warn'}, 'Только в пустой номер: мост сначала проверит его чтением, занятый не перезапишет.' + (safe('allow_group_store') ? '' : ' Сейчас запись выключена в настройках (allow_group_store).')),
    h('div', {class: 'row'}, h('button', {class: 'btn ghost', type: 'button', onclick: function () { d.close(); }}, 'Отмена'), ok)));
  d.showModal();
}

function beamCard() {
  var heads = state.selection.map(fixture).filter(function (f) { return f && canMove(f) && !f.missing; });
  var head = heads.length === 1 ? heads[0] : null;
  var ready = connected() && !!head;
  return h('div', {class: 'card'}, h('h2', {}, 'Калибровка луча' + (head ? ': ' + (head.label || head.name) : '')),
    h('p', {class: 'note'}, head ? 'Направьте голову прямо на сцену на «Свете», затем нажмите первую кнопку.' : 'Выберите одну голову (на «Свете» или в списке «Расстановка»).'),
    h('div', {class: 'row'}, h('button', {class: 'btn', type: 'button', disabled: !ready || busy('beam_home'), onclick: function (e) { send({a: 'beam_home', id: head.id}, e.currentTarget); }}, 'Сейчас светит прямо на сцену'),
      h('button', {class: 'btn', type: 'button', disabled: !ready || busy('beam_invert'), onclick: function (e) { send({a: 'beam_invert', id: head.id}, e.currentTarget); }}, 'Луч крутится не туда')));
}
