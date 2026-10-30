const assert = require('node:assert/strict');
const path = require('node:path');
const { modules, edges, scenarios, topics } = require('./dist/model.js');
const moduleIds = new Set(modules.map(m => m.id));
assert.equal(moduleIds.size, modules.length);
assert.equal(new Set(edges.map(e => e.id)).size, edges.length);
for (const e of edges) {
  assert(moduleIds.has(e.from) && moduleIds.has(e.to), `Missing endpoint: ${e.id}`);
  assert(['data', 'command', 'feedback'].includes(e.type));
  assert(e.meaning && e.contract && e.origin, `Missing interface semantics: ${e.id}`);
}
for (const flow of Object.values(scenarios)) {
  for (const [id] of flow.steps) assert(edges.some(e => e.id === id), `Missing flow edge: ${id}`);
}
for (const topic of Object.values(topics)) {
  for (const id of topic.edges) assert(edges.some(e => e.id === id), `Missing topic edge: ${id}`);
}
for (const planner of ['global', 'local']) {
  assert(edges.some(e => e.from === 'navmap' && e.to === planner && e.label.includes('costmap')));
  assert(!edges.some(e => e.from === 'map' && e.to === planner), 'File server must not provide runtime maps');
}
for (const consumer of ['percep', 'global', 'local']) {
  const relation = edges.find(e => e.from === 'tf' && e.to === consumer);
  assert(relation && topics.main.edges.includes(relation.id), `TF consumer missing from overview: ${consumer}`);
}
for (const id of ['slam-tf','tf-percep','percep-submap','submap-pose','board-decision','anomaly-decision']) {
  assert(edges.some(e => e.id === id), `Missing confirmed architecture relation: ${id}`);
}
assert.equal(edges.find(e => e.id === 'submap-register').origin, '补充建议', 'Undecided anchor protocol must remain a proposal');
const wheel = edges.find(e => e.id === 'wheel-local');
assert(wheel && wheel.from === 'board' && wheel.to === 'local' && wheel.origin === '用户确认', 'Wheel speed must feed Local planner');
assert(!edges.some(e => e.id === 'wheel-nav'), 'Superseded wheel-speed relation remains');
assert(modules.find(m => m.id === 'navmap').parts.some(([name, detail]) => name.startsWith('边界轨迹层') && detail.includes('map 坐标均冻结') && detail.includes('SLAM 优化不得修改')), 'Saved boundary coordinates must remain frozen');
console.log(`Model: ${modules.length} modules, ${edges.length} interfaces, ${Object.keys(scenarios).length} flows valid.`);

// Browser QA uses an existing Playwright installation; the site itself has no dependencies.
if (process.argv[2]) (async () => {
  const { chromium } = require(process.argv[2]);
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1600, height: 1100 }, reducedMotion: 'reduce' });
    const errors = [];
    const networkRequests = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', request => { if (/^https?:/.test(request.url())) networkRequests.push(request.url()); });
    await page.goto(`file:///${path.resolve(__dirname, 'dist/index.html').replaceAll('\\', '/')}`);
    assert.equal(await page.locator('.node').count(), modules.length);
    await page.locator('#reset').click();
    await page.screenshot({ path: path.resolve(__dirname, '../../.local-archive/rlcp-architecture-desktop.png'), fullPage: true });
    for (const m of modules) {
      await page.locator(`#nodes [data-module="${m.id}"]`).click();
      assert.equal(await page.locator('#inspector h2').textContent(), m.name);
    }
    await page.locator('[data-filter="all"]').click();
    assert.equal(await page.locator('.edge').count(), edges.length);
    await page.locator('#suggestions').uncheck();
    assert.equal(await page.locator('.edge.suggested').count(), 0);
    await page.locator('#suggestions').check();
    for (const [id, topic] of Object.entries(topics)) {
      await page.locator(`[data-topic="${id}"]`).click();
      assert.equal(await page.locator('.edge').count(), topic.edges.length);
      await page.locator('.graph').screenshot({ path: path.resolve(__dirname, `../../.local-archive/rlcp-architecture-${id}.png`) });
    }
    await page.locator('[data-filter="all"]').click();
    await page.locator('.edge[data-edge="global-local"]').focus();
    await page.keyboard.press('Enter');
    assert.match(await page.locator('#inspector').textContent(), /用户确认/);
    assert.equal(await page.locator(':focus').getAttribute('data-edge'), 'global-local', 'Keyboard focus lost on selection');
    for (const filter of ['data', 'command', 'feedback']) {
      await page.locator(`[data-filter="${filter}"]`).click();
      assert.equal(await page.locator('.edge').count(), edges.filter(e => e.type === filter).length);
    }
    for (const view of ['ipc', 'single', 'logical']) {
      await page.locator(`[data-view="${view}"]`).click();
      assert.equal(await page.locator(`[data-view="${view}"]`).getAttribute('aria-pressed'), 'true');
    }
    for (const [key, flow] of Object.entries(scenarios)) {
      await page.locator('#scenario').selectOption(key);
      for (let i = 0; i < flow.steps.length; i++) {
        await page.locator('#next').click();
        assert.equal(await page.locator('#step-counter').textContent(), `${i + 1}/${flow.steps.length}`);
        assert.equal(await page.locator('.edge.active').getAttribute('data-edge'), flow.steps[i][0]);
      }
      await page.locator('#previous').click();
      assert.equal(await page.locator('#step-counter').textContent(), `${flow.steps.length - 1}/${flow.steps.length}`);
      await page.locator('#exit-walk').click();
    }
    await page.locator('.map-breakdown [data-module="navmap"]').click();
    assert.equal(await page.locator('#inspector h2').textContent(), 'Nav Map');
    assert(await page.locator('#inspector h2').evaluate(el => {
      const rect = el.getBoundingClientRect();
      return rect.top >= 0 && rect.bottom <= window.innerHeight;
    }), 'Detail shortcut does not bring module details into view');
    assert.equal(await page.locator(':focus').getAttribute('id'), 'inspector');
    await page.locator('[data-filter="all"]').click();
    await page.locator('#interface-rows [data-edge="tf-global"]').click();
    assert.match(await page.locator('#inspector .subtitle').textContent(), /Global planner/);
    assert(await page.locator('#inspector h2').evaluate(el => {
      const rect = el.getBoundingClientRect();
      return rect.top >= 0 && rect.bottom <= window.innerHeight;
    }), 'Interface shortcut does not bring details into view');
    await page.locator('#reset').click();
    await page.setViewportSize({ width: 390, height: 844 });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'Page overflows mobile viewport');
    await page.locator('#nodes [data-module="motion"]').click();
    assert.equal(await page.locator('#inspector h2').textContent(), 'Motion');
    await page.screenshot({ path: path.resolve(__dirname, '../../.local-archive/rlcp-architecture-mobile.png'), fullPage: true });
    assert.deepEqual(errors, []);
    assert.deepEqual(networkRequests, [], 'Offline page unexpectedly uses network resources');
    console.log('Browser: module details, detail shortcuts, edge keyboard input, filters, deployment views, all flow steps, mobile viewport and offline access passed.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
