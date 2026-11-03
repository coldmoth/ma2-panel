'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const zlib = require('node:zlib');
const pw = require('./browser_smoke/node_modules/playwright');
const [base, output] = process.argv.slice(2);
const data = zlib.gzipSync(Buffer.from('opaque upload fixture, not an actual MA2 show'));

async function check(engine) {
  const browser = await pw[engine].launch({headless: true});
  const context = await browser.newContext({viewport: {width: 1024, height: 768}, acceptDownloads: true});
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  let accept = true;
  page.on('dialog', dialog => accept ? dialog.accept() : dialog.dismiss());
  try {
    await page.goto(base);
    await page.waitForFunction(() => connected());
    await page.locator('[data-sec="shows"]').click();
    const card = page.locator('#show-files-card');
    await card.getByRole('button', {name: 'Скачать шоу', exact: true}).click();
    await card.getByRole('link', {name: 'Скачать файл .show.gz'}).waitFor();
    const event = page.waitForEvent('download');
    await card.getByRole('link').click();
    const downloaded = await event;
    const saved = path.join(output, engine + '-saved.show.gz');
    await downloaded.saveAs(saved);
    assert.ok(zlib.gunzipSync(await fs.readFile(saved)).length > 0);
    await card.getByRole('button', {name: 'Сохранить текущее и скачать', exact: true}).click();
    await page.waitForFunction(() => showFileUI.operation && showFileUI.operation.kind === 'save' && showFileUI.operation.state === 'ready');
    await page.screenshot({path: path.join(output, engine + '-ready.png'), fullPage: true});
    accept = false;
    await card.locator('input[type=file]').setInputFiles({name: 'School.show.gz', mimeType: 'application/octet-stream', buffer: data});
    await card.getByRole('alert').filter({hasText: 'Действие отменено'}).waitFor();
    assert.equal(await page.evaluate(() => showFileUI.operation.state), 'confirm');
    accept = true;
    await card.locator('input[type=file]').setInputFiles({name: 'School.show.gz', mimeType: 'application/octet-stream', buffer: data});
    await page.waitForFunction(() => showFileUI.operation && showFileUI.operation.kind === 'load' && showFileUI.operation.state === 'done');
    await page.reload();
    await page.waitForFunction(() => showFileUI.operation && showFileUI.operation.state === 'done');
    await page.locator('[data-sec="shows"]').click();
    await page.screenshot({path: path.join(output, engine + '-loaded.png'), fullPage: true});
    await page.setViewportSize({width: 390, height: 844});
    await page.screenshot({path: path.join(output, engine + '-phone.png'), fullPage: true});
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'horizontal overflow');
    await context.setOffline(true);
    await card.getByRole('button', {name: 'Проверить результат'}).click();
    await card.getByRole('alert').filter({hasText: 'Результат неизвестен'}).waitFor();
    await context.setOffline(false);
    await card.getByRole('button', {name: 'Проверить результат'}).click();
    await page.waitForFunction(() => !showFileUI.error);
    await page.waitForFunction(() => connected());
    await card.locator('input[type=file]').setInputFiles({name: 'Broken.show.gz', mimeType: 'application/octet-stream', buffer: Buffer.from('bad')});
    await card.getByRole('alert').waitFor();
    await page.screenshot({path: path.join(output, engine + '-invalid.png'), fullPage: true});
    assert.deepEqual(errors, []);
    console.log('PASS ' + engine + ': upload, confirmation/cancel, saved download, save/backup, reload, corrupt file, offline/recovery, phone');
  } catch (error) {
    await page.screenshot({path: path.join(output, engine + '-failure.png'), fullPage: true});
    throw error;
  } finally { await browser.close(); }
}
(async () => { for (const engine of ['chromium', 'webkit']) await check(engine); })()
  .catch(error => {console.error(error); process.exitCode = 1;});
