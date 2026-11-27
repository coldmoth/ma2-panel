// Visual acceptance against the real, isolated mock UI. No MA2 actions.
import { chromium, webkit } from 'playwright';
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';

const dir = new URL('../screenshots/scale-fit/', import.meta.url);
await mkdir(dir, { recursive: true });
const results = [], interactions = [], errors = [];
const metrics = page => page.locator('.page-hall .stage-viewport > svg').evaluate(s => {
  const rect = e => { const r = e.getBoundingClientRect(); return { x:r.x, y:r.y, width:r.width, height:r.height }; };
  const g = s.querySelector(':scope > g'), b = g.getBBox(), m = g.getScreenCTM();
  const view = s.viewBox.baseVal;
  const centre = new DOMPoint(view.x + view.width / 2, view.y + view.height / 2)
    .matrixTransform(s.getScreenCTM());
  return { centre: {x:centre.x,y:centre.y}, viewport:[innerWidth,innerHeight], main:rect(s.closest('main')), area:rect(s.parentElement),
    svg:rect(s), geometry:rect(g), floor:rect(s.querySelector('[data-room]')),
    bbox:{x:b.x,y:b.y,width:b.width,height:b.height}, ctm:{a:m.a,d:m.d,e:m.e,f:m.f},
    viewBox:s.getAttribute('viewBox'), transform:g.getAttribute('transform'),
    fill:rect(g).height/rect(s.parentElement).height,
    viewFillsAvailableSpace: Math.abs(
      rect(s.closest('main')).height - rect(s.parentElement).height -
      rect(document.querySelector('.stage-heading')).height -
      rect(document.querySelector('.inspector-strip')).height -
      rect(document.querySelector('.page-hall > .live-scenes-bar')).height -
      rect(document.querySelector('.quick-scenes')).height
    ) <= 10,
    clipped:[...g.querySelectorAll('[data-fixture], [data-room], [data-stage-area]')].some(e => {
      const r=e.getBoundingClientRect(),a=s.getBoundingClientRect();
      return r.left<a.left-.5 || r.right>a.right+.5 || r.top<a.top-.5 || r.bottom>a.bottom+.5;
    }), overflow:document.documentElement.scrollWidth>innerWidth || document.documentElement.scrollHeight>innerHeight };
});

for (const engine of [chromium, webkit]) {
  const browser = await engine.launch();
  const page = await browser.newPage({ viewport:{width:1440,height:900}, deviceScaleFactor:1 });
  page.on('pageerror', e => errors.push(e.message));
  try {
    await page.addInitScript(() => localStorage.setItem("luma.language.v1", "ru"));
    await page.goto(process.env.LUMA_URL || 'http://127.0.0.1:5193/');
    await page.waitForSelector('[data-fixture="9"]');
    await page.evaluate(() => document.fonts.ready);
    // Wide first: catches the old 560px cap that the 1440px-only check missed.
    const positions = () => page.evaluate(async () => {
      const url=performance.getEntriesByType('resource').find(e=>/\/src\/client\.mjs/.test(e.name)).name;
      const {bridge}=await import(url);
      return bridge.state.config.fixtures.map(({id,x,y})=>({id,x,y}));
    });
    const originalPositions=await positions();
    for (const [width,height] of [[1920,1080],[1440,900],[1366,768],[1024,768]]) {
      await page.setViewportSize({width,height});
      for (const view of ['Перспектива','Вид сверху']) {
        await page.getByRole('button',{name:view,exact:true}).click();
        await page.waitForTimeout(100);
        const m=await metrics(page);
        results.push({engine:engine.name(),view,...m});
        if (engine===chromium) await page.screenshot({path:new URL(`${engine.name()}-${width}-${view==='Перспектива'?'perspective':'top'}.png`,dir).pathname});
        assert(!m.clipped && !m.overflow, 'geometry must remain visible without page scrolling');
        // Width-limited layouts must still use almost all available width.
        assert(m.fill>=.85 || m.geometry.width/m.area.width>=.92, `hall stays small: ${JSON.stringify(m)}`);
        if (width>=1366) assert(m.viewFillsAvailableSpace, `wide workspace fill: ${JSON.stringify(m)}`);
        assert(Math.abs(m.ctm.a-m.ctm.d)<.001, 'uniform scaling');
        assert(Math.abs(m.centre.x-(m.area.x+m.area.width/2))<1, 'centered horizontally');
        assert(Math.abs(m.centre.y-(m.area.y+m.area.height/2))<1, 'centered vertically');
      }
    }
    await page.setViewportSize({width:1440,height:900});
    for (const view of ['Перспектива','Вид сверху']) {
      await page.getByRole('button',{name:view,exact:true}).click();
      await page.locator('[data-fixture="9"]').click();
      await page.locator('[data-fixture="12"]').click({modifiers:['Shift']});
      await page.waitForFunction(()=>document.querySelectorAll('[data-fixture][aria-pressed="true"]').length===2);
      await page.getByRole('button',{name:'ID',exact:true}).click();
      assert.equal(await page.locator('[data-fixture] > text').count(),0);
      await page.getByRole('button',{name:'ID',exact:true}).click();
      assert.equal(await page.locator('[data-fixture] > text').count(),20);
      await page.getByRole('button',{name:'Лучи',exact:true}).click();
      assert.equal(await page.locator('[data-beam], [data-bar-glow]').count(),0);
      await page.getByRole('button',{name:'Лучи',exact:true}).click();
      assert(await page.locator('[data-beam], [data-bar-glow]').count()>0);

      // Resize only through the existing UI: no changes to inspector implementation.
      const handle=page.getByRole('separator',{name:'Ширина инспектора'});
      await handle.focus(); await page.keyboard.press('End');
      await page.waitForTimeout(100); const wide=await metrics(page);
      await page.getByRole('button',{name:'Свернуть навигацию',exact:true}).click();
      await page.waitForTimeout(100); const collapsed=await metrics(page);
      assert(collapsed.geometry.height>wide.geometry.height+50, 'hall grows when navigation closes');
      await handle.focus(); await page.keyboard.press('Home');
      await page.waitForTimeout(100); const narrow=await metrics(page);
      assert(narrow.geometry.height>collapsed.geometry.height+20, 'hall grows when inspector narrows');
      const shelf=page.getByRole('button',{name:/Быстрые сцены/});
      await shelf.click(); const open=await metrics(page);
      await shelf.click(); const closed=await metrics(page);
      assert.deepEqual(open.svg, closed.svg, 'scene overlay keeps the plot box');
      assert.equal(open.viewBox, closed.viewBox, 'scene overlay keeps the SVG viewBox');
      assert(!closed.clipped && !closed.overflow);
      await page.getByRole('button',{name:'Развернуть навигацию',exact:true}).click();
      await handle.focus(); await page.keyboard.press('End');
      // Restore the default 360px width without relying on stored implementation details.
      for(let i=0;i<14;i++) await page.keyboard.press('ArrowRight');
      interactions.push({engine:engine.name(),view,wideInspector:wide.geometry,collapsed:collapsed.geometry,narrowInspector:narrow.geometry,sceneOverlayKeepsHeight:true});
    }
    assert.deepEqual(await positions(),originalPositions, 'physical fixture coordinates stay unchanged');
    assert.equal(await page.locator('.page-hall .zoom-controls').count(),0);
  } finally {
    await browser.close();
    await writeFile(new URL('measurements.json',dir), JSON.stringify({results,interactions,errors},null,2));
  }
}
assert.deepEqual(errors,[]);
console.log(`PASS: ${results.length} real browser layouts, ${interactions.length} resize/selection/toggle checks; artifacts in ${dir.pathname}`);
