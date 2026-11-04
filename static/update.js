(() => {
  const el = id => document.getElementById(id);
  const check = el('update-check'), start = el('update-start'), message = el('update-state');
  const stages = {
    manual: 'Обновление с USB или по локальной сети…',
    downloading: 'Скачивание и проверка обновления…', validated: 'Пакет проверен. Проверка занятости панели…',
    waiting: 'Мост останавливается…', installing: 'Установка обновления…', starting: 'Запуск новой версии…',
    verifying: 'Проверка запуска обоих интерфейсов…', rolling_back: 'Восстановление предыдущей версии…',
    completed: 'Обновление установлено. Панель доступна.', rolled_back: 'Предыдущая версия восстановлена.',
    failed: 'Обновление не выполнено.', idle: 'Обновления устанавливаются только по вашему нажатию.'
  };
  const terminal = phase => ['idle', 'completed', 'rolled_back', 'failed'].includes(phase);
  let busy = false, available = false, posting = false, selectedVersion = null;
  const buttons = () => { check.disabled = busy || posting; start.disabled = busy || posting || !available; };
  async function request(url, post = false, body = undefined) {
    const response = await fetch(url, post ? {method: 'POST', headers: {'X-Update': '1', 'Content-Type': 'application/json'}, body: body === undefined ? undefined : JSON.stringify(body)} : {});
    const data = await response.json();
    if (!response.ok || data.ok === false) throw Error(data.err || 'Ошибка обновления');
    return data;
  }
  function show(data) {
    busy = !terminal(data.phase || 'idle');
    if (data.current) el('update-version').textContent = 'Установлено: ' + data.current;
    message.textContent = (stages[data.phase] || stages.idle) + (data.error ? ' ' + data.error : '');
    if (terminal(data.phase)) available = false;
    buttons();
    if (busy) setTimeout(poll, 1500);
  }
  async function poll() {
    try { show(await request('/api/update/status')); }
    catch (error) {
      message.textContent = busy ? 'Ожидаем соединения после перезапуска…' : error.message;
      buttons();
      // Only read the persisted operation; never repeat installation POST after a lost response.
      if (busy) setTimeout(poll, 1500);
    }
  }
  check.addEventListener('click', async () => {
    if (busy || posting) return;
    posting = true; buttons();
    try {
      const data = await request('/api/update/check', true);
      selectedVersion = data.available?.version || null;
      el('update-notes').textContent = data.available?.notes || '';
      if (!data.available) {
        el('update-version').textContent = 'Установлено: ' + data.current;
        available = false;
        message.textContent = 'Новых стабильных обновлений нет.';
        return;
      }
      el('update-version').textContent = 'Установлено: ' + data.current + ' · Доступно: ' + data.available.version;
      available = data.compatible_installation && data.available.version !== data.current;
      message.textContent = data.compatible_installation
        ? 'Перед установкой панель проверит пакет и отсутствие текущих действий.'
        : 'Сначала установите полный Windows-комплект с поддержкой обновлений.';
    } catch (error) { message.textContent = error.message; available = false; }
    finally { posting = false; buttons(); }
  });
  start.addEventListener('click', async () => {
    if (busy || posting || !available) return;
    posting = true; busy = true; buttons();
    try { show(await request('/api/update/start', true, {version: selectedVersion})); }
    catch (error) {
      message.textContent = 'Ответ не получен. Проверяем сохранённую операцию…';
      setTimeout(poll, 1500);
    } finally { posting = false; buttons(); }
  });
  buttons(); poll();
})();
