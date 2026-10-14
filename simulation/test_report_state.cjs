// Run after python -m simulation. No npm dependencies; checks real replay records.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const template = fs.readFileSync(path.join(__dirname, 'report_template.html'), 'utf8');
const source = template.split('<script>')[1].split('$("view-brain").onclick')[0];
const elements = new Map();
function element() {
  return {children: [], attrs: {}, textContent: '', append(n) { this.children.push(n); },
    replaceChildren() { this.children = []; }, setAttribute(k,v) { this.attrs[k] = v; }};
}
const document = {getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
  createElement: element, createElementNS: element};
document.getElementById('data').textContent = '[]';
const context = vm.createContext({document});
vm.runInContext(source, context);
const api = vm.runInContext('({build:r=>{run=r;return buildSteps(r)}, render:showStateMachines, evidence:decisionEvidence, changes, nextCondition})', context);
const output = path.join(__dirname, 'output');
const results = fs.readdirSync(output).filter(n=>fs.existsSync(path.join(output,n,'result.json')))
  .map(n=>JSON.parse(fs.readFileSync(path.join(output,n,'result.json'),'utf8')));
let frames = 0;
for (const result of results) {
  for (const step of api.build(result)) {
    if (!step.brain) continue;
    api.render(step); frames++;
    assert(step.decisionIndex <= step.eventIndex, 'decision must not come from the future');
    const text = Object.values(api.evidence(step)).join('\n');
    assert(!text.includes('undefined'), result.scenario);
  }
}
const mapping = results.find(r=>r.scenario==='mapping_session');
const steps = api.build(mapping);
const closure = steps.find(s=>s.event.payload?.signal==='REGION_CLOSED' && s.event.brain_before?.public_status.mission_state?.stage==='BUILD_BOUNDARY');
assert.match(api.evidence(closure).change,/BUILD_BOUNDARY → COMMIT_OBJECT/);
api.render(closure);
assert(elements.get('mission-graph').children.some(n=>n.attrs.class==='state-edge changed'));
const ready = steps.find(s=>s.event.action==='status' && s.event.brain_before?.public_status.mission_state?.stage==='BUILD_BOUNDARY' && s.event.brain_before.directive.phase==='PREPARE' && s.brain.directive.phase==='EXECUTE');
api.render(ready);
assert(!elements.get('mission-graph').children.some(n=>n.attrs.class==='state-edge changed'), 'READY must not highlight the control-switch loop');
assert.match(api.evidence(ready).input,/确认 roboframe 就绪/);
const fault = api.build(results.find(r=>r.scenario==='mission_lifecycle'));
const reset = fault.find(s=>s.event.payload?.type==='RESET_ERROR');
assert.match(api.evidence(reset).next,/RESUME/);
assert.equal(reset.brain.public_status.mission_state.lifecycle,'FAILED');
const timeout = api.build(results.find(r=>r.scenario==='pause_and_timeout')).find(s=>s.event.action==='tick');
assert(timeout, 'clock timeout must have its own before/after evidence');
assert.match(api.evidence(timeout).input,/时钟检查/);
const ignored = api.build(results.find(r=>r.scenario==='pause_and_timeout')).find(s=>s.event.action==='status' && s.ignored && s.event.brain_before.directive.revision===s.brain.directive.revision);
assert(ignored);
assert.match(api.evidence(ignored).input,/未更新当前证据/);
assert.equal(api.evidence(ignored).change,'业务状态未转换。');
const cancel = api.build(results.find(r=>r.scenario==='cancel')).find(s=>s.event.payload?.type==='CANCEL');
api.render(cancel);
assert(!elements.get('lifecycle-strip').children.some(n=>n.className==='life active'), 'cancel must not be shown as success or active execution');
const cutting = api.build(results.find(r=>r.scenario==='cover_regions'));
const regionDone = cutting.find(s=>s.event.brain_before?.public_status.mission_state?.target_id==='region-1' && s.brain?.public_status.mission_state?.target_id==='region-2');
assert(regionDone, 'whole region completion must advance to the next region');
api.render(regionDone);
function labels(n) { return [n.textContent, ...n.children.flatMap(labels)]; }
for (const mode of ['IDLE','MAPPING','WORKING','RETURN_TO_CHARGE','CHARGING']) {
  assert(labels(elements.get('mode-graph')).some(t=>t.includes(mode)), `missing actual mode ${mode}`);
}
assert.match(api.evidence(regionDone).next,/MOW_REGION|区域|READY/);
console.log(`${results.length} scenarios / ${frames} replay steps rendered; state labels, whole-region transition, readiness, retry, timeout, stale feedback and cancellation verified.`);
