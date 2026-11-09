// First-run wizard on the isolated, delivered Windows runtime (mock only).
const assert = require('node:assert/strict');
const path = require('node:path');
const {chromium} = require('./browser_smoke/node_modules/playwright');
(async () => {
  const browser = await chromium.launch({headless: true});
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(process.argv[2] + '/setup.html');
    await page.locator('#setup-form').waitFor({state: 'visible'});
    await page.waitForFunction(() => !document.getElementById('setup-save').disabled);
    assert.equal(await page.locator('#setup-form').isVisible(), true);
    assert.deepEqual(errors, []);
    await page.screenshot({path: path.join(process.argv[3], 'windows-first-run.png'), fullPage: true});
    console.log('Delivered first-run wizard rendered, settings controls ready, no JS errors');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
