'use strict';
(() => {
  const button = document.getElementById('upload-send');
  const refresh = document.getElementById('upload-refresh');
  const status = document.getElementById('upload-status');
  const description = document.getElementById('upload-description');
  let latest = null, busy = false, loading = false, generation = 0, id = null, awaitingReceipt = false;
  try {
    id = localStorage.getItem('ma2.diag-report-id');
    if (id?.startsWith('pending:')) { id = id.slice(8); awaitingReceipt = true; }
  } catch (_) { /* checked before queueing */ }

  function rejectedBeforeSave(data) {
    return !data.report_id && ['collection', 'size', 'invalid', 'busy'].includes(data.error);
  }
  function cannotSend(data) {
    return !data || (data.automatic && data.state !== 'sent') || (!data.ok && !data.report_id && !rejectedBeforeSave(data));
  }
  function render(data, receipt = false) {
    if (receipt && rejectedBeforeSave(data)) {
      awaitingReceipt = false;
      try { localStorage.setItem('ma2.diag-report-id', id); } catch (_) { /* no remote send occurred */ }
    }
    // A poll may still describe the PREVIOUS report while our queue request is unresolved.
    if (awaitingReceipt && !receipt && data.ok && data.report_id !== id) {
      data = {ok: true, configured: data.configured, state: 'unconfirmed', report_id: id};
    }
    latest = data;
    if (data.report_id && data.state !== 'unconfirmed') {
      id = data.report_id;
      awaitingReceipt = false;
      try { localStorage.setItem('ma2.diag-report-id', id); } catch (_) { /* fail closed before queueing */ }
    }
    const waiting = data.report_id && data.state !== 'sent';
    description.disabled = busy || !!waiting;
    button.disabled = busy || cannotSend(data);
    button.textContent = waiting && data.automatic ? 'Отчёт сохранён' :
      data.state === 'pending' ? 'Проверить отправку' :
      data.state === 'sent' ? 'Отправить новый отчёт' : 'Отправить диагностику';
    if (!data.ok && !data.report_id) status.textContent = data.err || 'Не удалось прочитать состояние отправки.';
    else if (data.state === 'unconfirmed') status.textContent = 'Сохранение отчёта не подтверждено. Повторите отправку: будет использован тот же отчёт.';
    else if (data.state === 'sent') status.textContent = `Отчёт #${data.number} отправлен в закрытый coldmoth/ma2-panel-diagnostics.`;
    else if (data.state === 'accepted') status.textContent = 'Отчёт принят сервером. Сервер доставит его в закрытый GitHub; номер появится после подтверждения.';
    else if (!data.configured) status.textContent = (waiting ? 'Отчёт сохранён на ПК. ' : '') + (data.err || 'Прежний доступ к GitHub не настроен. Обратитесь к владельцу для проверки старой отправки.');
    else if (data.state === 'pending') status.textContent = 'Результат отправки неизвестен. ' + (data.automatic ? 'Мост автоматически проверяет доставку' : 'Проверьте отправку') + ': поиск того же отчёта без повторного создания.';
    else if (data.state === 'rejected' || waiting && data.error && data.error !== 'network') status.textContent = 'Отчёт сохранён на ПК. ' + (data.err || 'GitHub отклонил отправку. Проверьте доступ.') + (data.automatic ? ' Мост повторит попытку автоматически.' : ' Повтор использует тот же снимок.');
    else if (waiting && data.automatic) status.textContent = 'Отчёт сохранён на ПК. Ожидает интернета: мост отправит его автоматически, браузер можно закрыть.';
    else if (data.state === 'prepared') status.textContent = 'Отчёт сохранён на мосту. Кнопка включит автоматическую отправку того же снимка данных.';
    else if (data.err) status.textContent = data.err;
    else status.textContent = 'Отчёт будет сохранён на ПК и отправлен при наличии интернета.';
  }
  async function load() {
    if (busy || loading) return;
    loading = true;
    const started = generation;
    refresh.disabled = true;
    try {
      const response = await fetch('/api/diag/upload');
      const data = await response.json();
      if (started !== generation) return;
      if (!response.ok || (!data.ok && !data.report_id)) throw new Error(data.err || 'Страница отправки доступна только с самого ПК моста.');
      render(data);
    } catch (error) {
      if (started !== generation) return;
      button.disabled = true;
      status.textContent = error.message || 'Нет связи с мостом. Обновите состояние.';
    } finally { loading = false; refresh.disabled = false; }
  }
  async function sendReport() {
    if (busy || button.disabled) return;
    if (latest?.automatic && latest.state !== 'sent') return load();
    generation++;
    busy = true;
    button.disabled = true;
    description.disabled = true;
    refresh.disabled = true;
    button.setAttribute('aria-busy', 'true');
    status.textContent = 'Сохраняю отчёт на ПК…';
    try {
      if (!id || latest?.state === 'sent' && !awaitingReceipt) id = crypto.randomUUID();
      // Save before HTTP: a lost response must not change identity on retry/reload.
      try { localStorage.setItem('ma2.diag-report-id', 'pending:' + id); }
      catch (_) { throw new Error('Не удалось сохранить номер попытки в браузере. Разрешите локальное хранилище и повторите.'); }
      awaitingReceipt = true;
      latest = {...latest, state: 'unconfirmed', report_id: id, automatic: false};
      const response = await fetch('/api/diag/queue', {
        method: 'POST', headers: {'Content-Type': 'application/json', 'X-Diag-Upload': '1'},
        body: JSON.stringify({report_id: id, description: description.value})
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.err || 'Мост отклонил сохранение отчёта.');
      render(data, true);
    } catch (error) {
      // Do not claim local persistence when the HTTP response was lost.
      status.textContent = 'Отправка не подтверждена: ' + (error.message || 'нет ответа по сети') + ' Обновите состояние или повторите: будет использован тот же отчёт.';
    } finally {
      busy = false;
      button.disabled = cannotSend(latest);
      description.disabled = !!latest?.report_id && latest.state !== 'sent';
      refresh.disabled = false;
      button.setAttribute('aria-busy', 'false');
    }
  }
  button.addEventListener('click', sendReport);
  refresh.addEventListener('click', load);
  setInterval(load, 5000);
  load();
})();
