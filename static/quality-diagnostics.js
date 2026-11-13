'use strict';
// Passive local snapshots only. Existing active probes keep their separate controls.
(() => {
  const main = document.querySelector('main');
  if (!main) return;
  const section = document.createElement('section'); section.className = 'card diagsec';
  const title = document.createElement('h2'); title.textContent = 'Готовность и данные для тестирования';
  const note = document.createElement('p'); note.className = 'note';
  note.textContent = 'Пассивная проверка: команды на MA2 не отправляются. Неизвестное состояние не считается успешной проверкой. Архив содержит обезличенную структуру, без исходных логов; пропуски указаны явно.';
  const status = document.createElement('ul'); status.id = 'quality-checks'; status.setAttribute('aria-live', 'polite');
  const button = document.createElement('button'); button.type = 'button'; button.className = 'btn';
  button.id = 'testing-preview'; button.textContent = 'Собрать данные для тестирования';
  const preview = document.createElement('pre'); preview.id = 'testing-preview-content';
  const download = document.createElement('a'); download.className = 'btn'; download.id = 'testing-download';
  download.textContent = 'Сохранить проверенный снимок локально'; download.hidden = true;
  section.append(title, note, status, button, preview, download); main.prepend(section);
  const labels = {pass:'ОК',fail:'Ошибка',unknown:'Неизвестно',blocked:'Ограничено'};
  async function readiness() {
    try {
      const response = await fetch('/api/quality/readiness', {cache:'no-store'});
      if (!response.ok) throw Error('Откройте диагностику на ПК моста через localhost.');
      const data = await response.json(); status.replaceChildren();
      data.checks.forEach(check => {
        const row = document.createElement('li');
        row.textContent = labels[check.status] + ': ' + check.reason + (check.status === 'pass' ? '' : ' ' + check.action);
        if (check.status === 'fail') row.className = 'bad'; status.append(row);
      });
      const names = {dim:'Яркость',color:'Цвет',pos:'Pan/Tilt',zoom:'Zoom',focus:'Focus',strobe:'Стробоскоп'};
      let tools = {};
      try { tools = JSON.parse(localStorage.getItem('ma2.interface') || '{}').tools || {}; } catch (error) {}
      Object.keys(names).filter(key => tools[key] === false).forEach(key => {
        const row = document.createElement('li'); row.textContent = names[key] + ': инструмент скрыт вами в этом браузере. Включите его в настройках интерфейса.'; status.append(row);
      });
    } catch (error) { status.textContent = error.message; }
  }
  button.addEventListener('click', async () => {
    button.disabled = true; download.hidden = true;
    try {
      const response = await fetch('/api/testing/preview', {method:'POST'});
      if (!response.ok) throw Error('Сбор доступен на основном ПК через localhost.');
      const data = await response.json();
      preview.textContent = 'Файлы: manifest.json, ' + Object.keys(data.files).join(', ') +
        '\nРазмер: ' + data.bytes + ' байт\nSHA256: ' + data.sha256 + '\nНе хватает:\n' + data.missing.join('\n');
      download.href = '/api/testing/download/' + encodeURIComponent(data.token); download.hidden = false;
    } catch (error) { preview.textContent = error.message; }
    finally { button.disabled = false; }
  });
  readiness(); setInterval(readiness, 5000);
})();
