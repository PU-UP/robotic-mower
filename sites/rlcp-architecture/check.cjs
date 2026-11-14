const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const { pathToFileURL } = require('node:url');
const buildHtml = require('./build.cjs');
const standalone = fs.readFileSync(path.join(__dirname, 'dist/index.html'), 'utf8').replace(/\r\n/g, '\n');
assert.equal(standalone, buildHtml(), 'Run node build.cjs to update the standalone file');
const { modules, edges, scenarios, topics, processes } = require('./src/model.js');
const deployment = require('./src/layout.js')(modules, edges, processes);
const deploymentNodes = Object.fromEntries(deployment.nodes.map(n => [n.id, n]));
for (const group of deployment.groups) for (const id of group.members) {
  const n = deploymentNodes[id];
  assert(n.x >= group.x && n.x+n.w <= group.x+group.w && n.y >= group.y+60 && n.y+n.h <= group.y+group.h, `Node outside its process: ${id}`);
}
const endpoint = id => processes.find(p=>p.members.includes(id))?.id || id;
for (const e of edges) {
  const from=endpoint(e.from), to=endpoint(e.to);
  if(from===to)continue;
  assert.equal(deployment.overview.filter(r=>r.from===from&&r.to===to||r.from===to&&r.to===from).length,1,`Missing or duplicated overview relation: ${e.id}`);
}
const onBorder = (p,n) => ((p.x === n.x || p.x === n.x+n.w) && p.y >= n.y && p.y <= n.y+n.h) || ((p.y === n.y || p.y === n.y+n.h) && p.x >= n.x && p.x <= n.x+n.w);
for (const r of deployment.overview) {
  const points=[...r.path.matchAll(/[ML](\d+) (\d+)/g)].map(m=>({x:+m[1],y:+m[2]}));
  const from=deployment.groups.find(g=>g.id===r.from)||deploymentNodes[r.from];
  const to=deployment.groups.find(g=>g.id===r.to)||deploymentNodes[r.to];
  assert(onBorder(points[0],from)&&onBorder(points.at(-1),to),`Wrong overview endpoints: ${r.from}/${r.to}`);
  for(let i=1;i<points.length;i++)for(const n of deployment.nodes){
    const a=points[i-1],b=points[i];
    const crosses=a.y===b.y?a.y>n.y&&a.y<n.y+n.h&&Math.max(a.x,b.x)>n.x&&Math.min(a.x,b.x)<n.x+n.w:a.x>n.x&&a.x<n.x+n.w&&Math.max(a.y,b.y)>n.y&&Math.min(a.y,b.y)<n.y+n.h;
    assert(!crosses,`Overview crosses module: ${r.from}/${r.to}/${n.id}`);
  }
}
for (const edge of edges) {
  const points = deployment.routes[edge.id].points;
  assert(onBorder(points[0], deploymentNodes[edge.from]) && onBorder(points.at(-1), deploymentNodes[edge.to]), `Wrong route endpoints: ${edge.id}`);
  for (let i = 1; i < points.length; i++) {
    const a=points[i-1], b=points[i];
    assert(a.x === b.x || a.y === b.y);
    for (const n of deployment.nodes) {
      const crosses = a.y === b.y
        ? a.y > n.y && a.y < n.y+n.h && Math.max(a.x,b.x) > n.x && Math.min(a.x,b.x) < n.x+n.w
        : a.x > n.x && a.x < n.x+n.w && Math.max(a.y,b.y) > n.y && Math.min(a.y,b.y) < n.y+n.h;
      assert(!crosses, `Route crosses module: ${edge.id} / ${n.id}`);
    }
  }
}
for(const m of modules){
  const detail=require('./src/layout.js')(modules,edges,processes,edges.filter(e=>e.from===m.id||e.to===m.id));
  for(const [id,route] of Object.entries(detail.routes)){
    const p=route.points;
    for(const [a,b] of [[p[0],p[1]],[p.at(-1),p.at(-2)]]){
      assert(Math.abs(a.x-b.x)+Math.abs(a.y-b.y)>=36,`Turn too close to port: ${m.id}/${id}`);
    }
  }
}
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
  assert(!edges.some(e => e.from === 'map' && e.to === planner && e.label.includes('costmap')), 'Map Server must not provide runtime costmaps');
}
for (const consumer of ['percep', 'global', 'local']) {
  const relation = edges.find(e => e.from === 'tf' && e.to === consumer);
  assert(relation && topics.main.edges.includes(relation.id), `TF consumer missing from overview: ${consumer}`);
}
for (const id of ['slam-tf','tf-percep','percep-submap','submap-pose','board-anomaly','anomaly-decision']) {
  assert(edges.some(e => e.id === id), `Missing confirmed architecture relation: ${id}`);
}
assert(!edges.some(e => ['global','local'].includes(e.from) && ['global','local'].includes(e.to)), 'Planners must coordinate only through Decision');
assert(!edges.some(e => e.from === 'board' && e.to === 'decision'), 'Hardware faults must enter Anomaly first');
assert(edges.some(e => e.from === 'board' && e.to === 'anomaly'));
for (const id of ['anomaly','map']) assert.equal(modules.find(m => m.id === id).parent, 'decision');
assert.equal(processes.length, 3);
const assigned = processes.flatMap(p => p.members);
assert.equal(new Set(assigned).size, assigned.length, 'Process memberships must not overlap');
assert(assigned.every(id => moduleIds.has(id)));
assert.deepEqual([...assigned].sort(), modules.filter(m => !['business','sensors','camera','board','motor'].includes(m.id)).map(m => m.id).sort());
assert(processes.find(p => p.id === 'planning').members.includes('navmap'));
assert.deepEqual(processes.find(p => p.id === 'decision').members, ['decision','anomaly','map']);
const planningSteps = scenarios.navigate.steps.map(s => s[0]);
for (const id of ['global-state','decision-local']) assert(planningSteps.includes(id), `Missing planning handoff: ${id}`);
assert(planningSteps.indexOf('global-state') < planningSteps.indexOf('decision-local'));
assert.equal(edges.find(e => e.id === 'submap-register').origin, '补充建议', 'Undecided anchor protocol must remain a proposal');
const wheel = edges.find(e => e.id === 'wheel-local');
assert(wheel && wheel.from === 'board' && wheel.to === 'local' && wheel.origin === '用户确认', 'Wheel speed must feed local controller');
assert(!edges.some(e => e.id === 'wheel-nav'), 'Superseded wheel-speed relation remains');
assert(modules.find(m => m.id === 'map').parts.some(([, detail]) => detail.includes('map 坐标均冻结') && detail.includes('SLAM 优化不得修改') && detail.includes('新版本')), 'Saved boundary coordinates must remain frozen and edits produce a new version');
for (const [id, from, to] of [['slam-trajectory','slam','map'],['business-map','business','map'],['map-business','map','business'],['map-constraints','map','navmap']]) {
  assert(edges.some(e => e.id === id && e.from === from && e.to === to));
  assert(topics.assets.edges.includes(id), `Missing map collaboration relation: ${id}`);
}
const steps = scenarios.files.steps.map(s => s[0]);
for (const id of ['map-state','decision-nav','nav-state','decision-global']) assert(steps.includes(id), `Missing map readiness step: ${id}`);
assert(steps.indexOf('map-state') < steps.indexOf('decision-nav'), 'Load the saved asset version after the commit result');
assert(steps.indexOf('nav-state') < steps.indexOf('decision-global'), 'Navigation readiness must precede planning');
console.log(`Model: ${modules.length} modules, ${edges.length} interfaces, ${Object.keys(scenarios).length} flows valid.`);

// Browser QA uses an existing Playwright installation; the site itself has no dependencies.
if (process.argv[2]) (async () => {
  const { chromium } = require(process.argv[2]);
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const tempDir = fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'rlcp-standalone-'));
  const standalonePath = path.join(tempDir, 'index.html');
  fs.writeFileSync(standalonePath, standalone);
  fs.mkdirSync(path.resolve(__dirname, '../../.local-archive'), { recursive: true });
  try {
    for (const variant of ['source', 'standalone']) {
      const url = pathToFileURL(variant === 'source' ? path.join(__dirname, 'src/index.html') : standalonePath).href;
      const page = await browser.newPage({ viewport: { width: 1600, height: 1100 }, reducedMotion: 'reduce' });
      const errors = [];
      const networkRequests = [];
      page.on('pageerror', e => errors.push(e.message));
      page.on('request', request => { if (/^https?:/.test(request.url()) || variant === 'standalone' && request.url() !== url) networkRequests.push(request.url()); });
      await page.goto(url);
      assert.equal(await page.locator('.node').count(), modules.length);
      if (variant === 'standalone') {
        assert.equal(await page.locator('main > section').count(), 1);
        assert.equal(await page.locator('.principles,.contracts,.questions,footer,.intro,.top-link').count(), 0);
        assert.equal(await page.locator('script[src],link[href]').count(), 0);
      } else assert.equal(await page.locator('#question-list .question').count(), require('./src/model.js').questions.length);
      await page.locator('#reset').click();
      await page.screenshot({ path: path.resolve(__dirname, `../../.local-archive/rlcp-architecture-${variant}-desktop.png`), fullPage: true });
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
        await page.locator('.graph').screenshot({ path: path.resolve(__dirname, `../../.local-archive/rlcp-architecture-${variant}-${id}.png`) });
      }
      await page.locator('[data-filter="all"]').click();
      await page.locator('.edge[data-edge="global-state"]').focus();
      await page.keyboard.press('Enter');
      assert.match(await page.locator('#inspector').textContent(), /用户确认/);
      assert.equal(await page.locator(':focus').getAttribute('data-edge'), 'global-state', 'Keyboard focus lost on selection');
      for (const filter of ['data', 'command', 'feedback']) {
        await page.locator(`[data-filter="${filter}"]`).click();
        assert.equal(await page.locator('.edge').count(), edges.filter(e => e.type === filter).length);
      }
      for (const view of ['ipc', 'single', 'logical']) {
        await page.locator(`[data-view="${view}"]`).click();
        assert.equal(await page.locator(`[data-view="${view}"]`).getAttribute('aria-pressed'), 'true');
        if (view === 'ipc') {
          assert.equal(await page.locator('.process-region').count(), 3);
          for (const process of processes) for (const id of process.members) {
            assert.equal(await page.locator(`#nodes [data-module="${id}"] small`).textContent(), process.name);
            assert(await page.locator(`#nodes [data-module="${id}"]`).evaluate((el, className) => el.classList.contains(className), `process-${process.id}`));
          }
          await page.locator('[data-topic="main"]').click();
          await page.locator('.graph').screenshot({path:path.resolve(__dirname, `../../.local-archive/rlcp-architecture-${variant}-ipc.png`)});
          assert.equal(await page.locator('.edge.internal').count(), 0);
          await page.locator('[data-filter="all"]').click();
          assert.equal(await page.locator('.edge.aggregate').count(), deployment.overview.length);
          assert.equal(await page.locator('.edge[data-edge]').count(), 0);
          for (const r of deployment.overview) {
            const link=page.locator(`[data-process-link="${r.from}:${r.to}"]`);
            const forward=edges.some(e=>endpoint(e.from)===r.from&&endpoint(e.to)===r.to);
            const backward=edges.some(e=>endpoint(e.from)===r.to&&endpoint(e.to)===r.from);
            assert.equal(!!await link.locator('.route').getAttribute('marker-end'),forward);
            assert.equal(!!await link.locator('.route').getAttribute('marker-start'),backward);
          }
          for (const m of modules) {
            await page.locator(`#nodes [data-module="${m.id}"]`).click();
            assert.equal(await page.locator('#inspector h2').textContent(), m.name);
            const collisions=await page.evaluate(()=>{
              const labels=[...document.querySelectorAll('#connections .edge.active text')].map(el=>({id:el.parentElement.dataset.edge,box:el.getBoundingClientRect()}));
              const obstacles=[...document.querySelectorAll('#nodes .node,.process-title,.process-caption')].map(el=>({id:el.textContent,box:el.getBoundingClientRect()}));
              const overlap=(a,b)=>a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top;
              return labels.flatMap((a,i)=>[...labels.slice(i+1),...obstacles].filter(b=>overlap(a.box,b.box)).map(b=>a.id+' / '+b.id));
            });
            assert.deepEqual(collisions,[],`Overlapping labels for ${m.id}`);
            if(variant==='standalone')await page.locator('.graph').screenshot({path:path.resolve(__dirname, `../../.local-archive/rlcp-module-${m.id}.png`)});
          }
          await page.locator('#nodes [data-module="navmap"]').click();
          assert.equal(await page.locator('.edge.aggregate').count(),0);
          assert.equal(await page.locator('.edge[data-edge]').count(),edges.filter(e=>e.from==='navmap'||e.to==='navmap').length);
          await page.locator('#ipc-overview').click();
          assert.equal(await page.locator('.edge.aggregate').count(),deployment.overview.length);
          await page.locator('#nodes [data-module="navmap"]').click();
          await page.locator('#inspector [data-edge="nav-global"]').click();
          assert.equal(await page.locator('.edge.active').getAttribute('data-edge'), 'nav-global');
          assert.equal(await page.locator('.edge.active').evaluate(el=>getComputedStyle(el).outlineStyle), 'none', 'Mouse selection adds a misleading SVG outline');
          assert.equal(await page.locator('.edge.active text').evaluate(el=>getComputedStyle(el).opacity), '1');
          assert.match(await page.locator('#inspector .subtitle').textContent(), /进程内接口/);
        }
      }
      for (const flowView of ['logical','ipc']) {
        await page.locator(`[data-view="${flowView}"]`).click();
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
      }
      await page.locator('[data-view="logical"]').click();
      if (variant === 'source') {
        for (const [selector, name] of [
          ['.map-breakdown [data-module="navmap"]', 'Nav Map'],
          ['.principles > [data-module="local"]', 'local controller']
        ]) {
          await page.locator(selector).click();
          assert.equal(await page.locator('#inspector h2').textContent(), name);
          assert(await page.locator('#inspector h2').evaluate(el => {
            const rect = el.getBoundingClientRect();
            return rect.top >= 0 && rect.bottom <= window.innerHeight;
          }), 'Detail shortcut does not bring module details into view');
          assert.equal(await page.locator(':focus').getAttribute('id'), 'inspector');
        }
        await page.locator('[data-filter="all"]').click();
        await page.locator('#interface-rows [data-edge="tf-global"]').click();
        assert.match(await page.locator('#inspector .subtitle').textContent(), /Global planner/);
        assert(await page.locator('#inspector h2').evaluate(el => {
          const rect = el.getBoundingClientRect();
          return rect.top >= 0 && rect.bottom <= window.innerHeight;
        }), 'Interface shortcut does not bring details into view');
      }
      await page.locator('#reset').click();
      await page.setViewportSize({ width: 390, height: 844 });
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'Page overflows mobile viewport');
      await page.locator('#nodes [data-module="motion"]').click();
      assert.equal(await page.locator('#inspector h2').textContent(), 'motion');
      await page.locator('[data-view="ipc"]').click();
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'Deployment view overflows mobile page');
      await page.screenshot({ path: path.resolve(__dirname, `../../.local-archive/rlcp-architecture-${variant}-mobile.png`), fullPage: true });
      assert.deepEqual(errors, []);
      assert.deepEqual(networkRequests, [], 'Offline page unexpectedly uses network resources');
      console.log(`Browser (${variant}): module details, keyboard input, filters, deployment views, all flows, mobile viewport and offline access passed.`);
      await page.close();
    }
  } finally {
    await browser.close();
    fs.unlinkSync(standalonePath);
    fs.rmdirSync(tempDir);
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
