/* Browser display preferences. Never sent to the bridge as feature permissions. */
var interfaceTools = {dim:'Яркость', color:'Цвет', pos:'Pan/Tilt', zoom:'Zoom', focus:'Focus', strobe:'Стробоскоп'};
function readDisplayPrefs() {
  try {
    var value = JSON.parse(localStorage.getItem('ma2.interface') || '{}');
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
    if (!value.tools || typeof value.tools !== 'object' || Array.isArray(value.tools)) {
      value.tools = {};
      Object.keys(interfaceTools).forEach(function(key) { if (value[key] === false) value.tools[key] = false; });
    }
    return value;
  } catch (error) { return {}; }
}
var displayPrefs = readDisplayPrefs();
function toolVisible(key) { return displayPrefs.tools ? displayPrefs.tools[key] !== false : displayPrefs[key] !== false; }
function panelToolVisible(key) { return toolVisible(key); }
function saveDisplayPrefs() {
  try { localStorage.setItem('ma2.interface', JSON.stringify(displayPrefs)); } catch (error) {}
}
function interfaceControls(root) {
  var inputs = [];
  Object.keys(interfaceTools).forEach(function(key) {
    var label = document.createElement('label'); label.className = 'opt';
    var input = document.createElement('input'); input.type = 'checkbox'; input.checked = toolVisible(key); input.dataset.tool = key;
    input.addEventListener('change', function() {
      displayPrefs.tools = Object.assign({}, displayPrefs.tools || {});
      displayPrefs.tools[key] = input.checked; saveDisplayPrefs();
    });
    label.append(input, document.createTextNode(interfaceTools[key])); root.appendChild(label); inputs.push(input);
  });
  var reset = document.createElement('button'); reset.type = 'button'; reset.className = 'btn'; reset.textContent = 'Показать все инструменты';
  reset.addEventListener('click', function() { displayPrefs.tools = {}; saveDisplayPrefs(); inputs.forEach(function(input){input.checked = true;}); });
  root.appendChild(reset);
}
function refreshDisplayPrefs() {
  displayPrefs = readDisplayPrefs();
  if (typeof cancelTargetControls === 'function') cancelTargetControls();
  if (typeof lightUI !== 'undefined') lightUI.moveBox = null;
  if (typeof sectionKey !== 'undefined') sectionKey = null;
  if (typeof render === 'function') render();
}
if (typeof window !== 'undefined') {
  window.addEventListener('storage', function(event) {
    if (event.key === 'ma2.interface' || event.key === null) refreshDisplayPrefs();
  });
  window.addEventListener('pageshow', refreshDisplayPrefs);
}
var interfaceRoot = document.getElementById('interface-tools');
if (interfaceRoot) interfaceControls(interfaceRoot);
