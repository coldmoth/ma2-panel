/* Personal visibility only. Never changes features, safety or fixture capabilities. */
var panelTools = {};
var panelToolNames = {dim:'Яркость',strobe:'Strobe',focus:'Focus',zoom:'Zoom',color:'Color',pos:'Pan/Tilt'};
function panelReadTools() {
  try { var value=JSON.parse(localStorage.getItem('ma2.interface') || '{}'); panelTools = value && typeof value === 'object' && !Array.isArray(value) ? value : {}; }
  catch (error) { panelTools = {}; }
}
function panelToolVisible(key) { return panelTools[key] !== false; }
panelReadTools();
function panelRefreshTools() {
  panelReadTools();
  if (typeof moveStop === 'function') moveStop();
  if (typeof sliderChannels !== 'undefined') Object.keys(sliderChannels).forEach(cancelSlider);
  if (typeof render === 'function') { sectionKey=null; render(); }
}
window.addEventListener('storage', function(e) { if (e.key === 'ma2.interface' || e.key === null) panelRefreshTools(); });
window.addEventListener('pageshow', panelRefreshTools);
document.addEventListener('DOMContentLoaded', function() {
  var target=document.getElementById('interface-tools'); if (!target) return;
  Object.keys(panelToolNames).forEach(function(key) {
    var label=document.createElement('label'); label.className='opt';
    var input=document.createElement('input'); input.type='checkbox'; input.checked=panelToolVisible(key); input.dataset.tool=key;
    var text=document.createElement('span'); text.className='t'; text.textContent=panelToolNames[key];
    input.addEventListener('change', function() {
      var status=document.getElementById('interface-status');
      panelTools[key]=input.checked;
      try { localStorage.setItem('ma2.interface',JSON.stringify(panelTools)); status.textContent='Видимость сохранена в этом браузере.'; }
      catch(error) { status.textContent='Браузер не разрешил сохранить настройку. Разрешите локальное хранение.'; }
    });
    label.append(input,text); target.append(label);
  });
});
