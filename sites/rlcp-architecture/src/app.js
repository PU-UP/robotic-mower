const {modules,edges,questions,scenarios,topics,processes}=architecture;
const $=id=>document.getElementById(id);
const names=Object.fromEntries(modules.map(m=>[m.id,m.name]));
const processOf=id=>processes.find(p=>p.members.includes(id));
const colors={data:'#286fa4',command:'#b36a24',feedback:'#258473'};
const typeNames={data:'数据',command:'指令',feedback:'反馈'};
const state={view:'logical',filter:'main',topic:'main',suggestions:true,selected:null,edge:null,scenario:'navigate',step:-1};
const notes={logical:'Decision 节点表示调度核心；Anomaly、Map Server 是决策模块的子模块，分开绘制以展开接口。连线表示逻辑交互。',ipc:'当前按感知定位、决策、规控三个进程划分，节点边框与上方分组同色。Nav Map 放规控；跨进程走 IPC。Global / Local 虽同进程，交互仍经 Decision。',single:'后期候选：算法模块可装配进同一进程。虚框仅表示候选装配范围，Business_core 是否合并待定；逻辑职责和统一调度关系保持不变。'};
function visibleEdges(){
  if(state.step>=0){const ids=new Set(scenarios[state.scenario].steps.map(s=>s[0]));return edges.filter(e=>ids.has(e.id));}
  const topicEdges=new Set(topics[state.topic].edges);
  return edges.filter(e=>(state.suggestions||e.origin!=='补充建议')&&(state.filter==='all'||state.filter==='main'&&(topicEdges.has(e.id)||state.selected&&(e.from===state.selected||e.to===state.selected))||e.type===state.filter));
}
function edgeButton(e){return `<button data-edge="${e.id}">${e.label}<small>${names[e.from]} → ${names[e.to]}</small></button>`;}
function renderInspector(){
  const e=edges.find(e=>e.id===state.edge);
  if(e){$('inspector').innerHTML=`<p class="eyebrow">INTERFACE / ${typeNames[e.type]}流</p><span class="small-tag ${e.origin==='补充建议'?'proposal':''}">${e.origin}</span><h2>${e.label}</h2><p class="subtitle">${names[e.from]} → ${names[e.to]}</p><p class="summary">${e.meaning}</p><div class="detail-label">接口需要约定</div><p class="ownership">${e.contract}</p><div class="boundary"><strong>传输与逻辑分开</strong>${state.view==='logical'?'本接口描述交互含义，不指定消息格式与传输机制。':state.view==='ipc'?'跨进程使用 IPC；同进程可为库调用。当前按感知定位、决策、规控三个进程装配，见上方分组。':'同进程可通过组件接口传递，仍需约定数据生命周期、取消、顺序与有效性。'}</div><div class="detail-label">两端职责</div><div class="port-list"><button data-module="${e.from}">${names[e.from]} · 发送方 →</button><button data-module="${e.to}">${names[e.to]} · 接收方 →</button></div>`;return;}
  const m=modules.find(m=>m.id===state.selected);
  if(!m){$('inspector').innerHTML='<p class="eyebrow">架构图 · 交互说明</p><h2>查看模块与交互</h2><p class="summary">点击模块查看职责，点击连线查看数据与指令。上方切换专题与部署视图，下方可逐步演示协作流程。</p>';return;}
  const incoming=edges.filter(e=>e.to===m.id),outgoing=edges.filter(e=>e.from===m.id);
  $('inspector').innerHTML=`<p class="eyebrow">${m.id==='tf'?'PUBLIC INTERFACE / SLAM 公共输出':'MODULE / 逻辑能力'}</p><span class="small-tag ${m.tag.includes('待')?'proposal':''}">${m.tag}</span><h2>${m.name}</h2><p class="subtitle">${m.cn}<br>${m.role}<br>${processOf(m.id)?.name||'算法进程外部'}${m.parent?' · 隶属决策模块':''}</p><p class="summary">${m.summary}</p><div class="detail-label">状态与数据归属</div><p class="ownership">${m.owns}</p><div class="detail-label">内部职责 · 确认范围与建议见各项标注</div><ul class="parts">${m.parts.map(([n,d])=>`<li><strong>${n}</strong><p>${d}</p></li>`).join('')}</ul><div class="boundary"><strong>边界与待确认项</strong>${m.boundary}</div><div class="detail-label">输入接口 · 含补充建议</div><div class="port-list">${incoming.map(edgeButton).join('')||'<p class="ownership">外部输入未进一步展开。</p>'}</div><div class="detail-label">输出接口 · 含补充建议</div><div class="port-list">${outgoing.map(edgeButton).join('')||'<p class="ownership">外部输出未进一步展开。</p>'}</div>`;
}
function render(){
  $('view-note').textContent=notes[state.view];
  document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.view===state.view));
  document.querySelectorAll('[data-filter]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.filter===state.filter));
  document.querySelectorAll('[data-topic]').forEach(b=>b.setAttribute('aria-pressed',state.filter==='main'&&b.dataset.topic===state.topic));
  $('topic-note').textContent=state.filter==='main'?topics[state.topic].note:'当前按全图接口类型筛选；点击专题按钮返回相应关系视图。';
  $('suggestions').checked=state.suggestions;
  const shown=visibleEdges();
  const focus=state.edge?new Set(edges.filter(e=>e.id===state.edge).flatMap(e=>[e.from,e.to])):state.selected?new Set([state.selected,...shown.filter(e=>e.from===state.selected||e.to===state.selected).flatMap(e=>[e.from,e.to])]):null;
  let svg=`<defs>${Object.entries(colors).map(([k,v])=>`<marker id="arrow-${k}" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0 L8 4 L0 8 Z" fill="${v}"/></marker>`).join('')}</defs>`;
  if(state.view==='single')svg+='<path class="deployment-outline" d="M23 155 H315 V285 H645 V20 H1190 V910 H23 V760 H255 V635 H23 Z"/><text class="deployment-label" x="660" y="897">候选算法进程 · client / server 仍为逻辑角色</text>';
  $('graph').dataset.deployment=state.view;
  svg+='<text class="layer-label" x="330" y="25">BUSINESS</text><text class="layer-label" x="660" y="25">ASYNC CLIENT</text><text class="layer-label" x="1280" y="25">HARDWARE EVENTS</text>';
  svg+=shown.map(e=>{const active=state.edge===e.id||!state.edge&&state.selected&&(e.from===state.selected||e.to===state.selected);const dim=!!(state.edge||state.selected)&&!active;return `<g class="edge ${e.origin==='补充建议'?'suggested':''} ${active?'active':''} ${dim?'dim':''}" style="--edge-color:${colors[e.type]}" data-edge="${e.id}" role="button" tabindex="0" aria-label="${names[e.from]} 到 ${names[e.to]}：${e.label}，${e.origin}"><title>${e.label} · ${e.origin}</title><path class="route" d="${e.path}" marker-end="url(#arrow-${e.type})"/><path class="hit" d="${e.path}"/><text x="${e.lx}" y="${e.ly}">${e.label}</text></g>`;}).join('');
  $('connections').innerHTML=svg;
  $('nodes').innerHTML=modules.map(m=>`<button data-module="${m.id}" class="node ${m.kind} process-${processOf(m.id)?.id||'external'} ${m.id==='tf'?'public-interface':''} ${state.selected===m.id&&!state.edge?'selected':''} ${focus&&!focus.has(m.id)?'dim':''}" style="--x:${m.x};--y:${m.y}" aria-pressed="${state.selected===m.id&&!state.edge}" aria-label="${m.name} ${m.cn}：查看职责"><strong>${m.id==='anomaly'?'Anomaly':m.name}</strong><span>${m.cn}</span><small title="${m.role}">${state.view==='ipc'?(processOf(m.id)?.name||'外部输入 / 执行对象'):m.role}</small></button>`).join('');
  if($('interface-rows')) $('interface-rows').innerHTML=shown.map(e=>`<tr><td>${names[e.from]} <span style="color:#8ba3b3">→</span> ${names[e.to]}</td><td>${e.label}</td><td><i class="type-dot" style="background:${colors[e.type]}"></i>${typeNames[e.type]}</td><td>${e.origin}</td><td><button class="quiet" data-edge="${e.id}" aria-label="查看 ${e.label} 接口">↗</button></td></tr>`).join('');
  if($('table-caption')) $('table-caption').textContent=state.step>=0?'当前显示所选流程涉及的接口。演示是建议顺序，并非已经验证的产品行为。':`当前显示 ${shown.length} 条接口，与上方连线筛选同步。点击右侧箭头查看详细语义。`;
  const flow=scenarios[state.scenario],step=flow.steps[state.step];
  $('step-counter').textContent=step?`${state.step+1}/${flow.steps.length}`:'—';
  $('step-title').textContent=step?step[1]:'用一条真实协作链路检查职责';
  $('step-text').textContent=step?step[2]:'按步骤高亮接口。演示的是建议交互顺序，不是机器人实时状态。';
  $('previous').disabled=state.step<=0;$('next').textContent=state.step<0?'开始演示 →':state.step===flow.steps.length-1?'重新演示 ↺':'下一步 →';$('exit-walk').hidden=state.step<0;
  renderInspector();
}
function leaveWalk(){state.step=-1;}
function selectEdge(id){
  const e=edges.find(e=>e.id===id);if(!e)return;
  leaveWalk();state.edge=id;state.selected=null;state.filter='all';if(e.origin==='补充建议')state.suggestions=true;render();
}
document.addEventListener('click',event=>{
  const b=event.target.closest('[data-module],[data-edge],[data-filter],[data-view],[data-topic]');if(!b)return;
  const fromDetailsLink=!!b.closest('table,.map-breakdown');
  const moduleId=b.dataset.module,edgeId=b.dataset.edge;
  if(b.dataset.module){leaveWalk();state.selected=b.dataset.module;state.edge=null;render();}
  else if(b.dataset.edge){selectEdge(b.dataset.edge);}
  else if(b.dataset.filter){leaveWalk();state.filter=b.dataset.filter;state.edge=null;state.selected=null;render();}
  else if(b.dataset.view){state.view=b.dataset.view;render();}
  else if(b.dataset.topic){leaveWalk();state.topic=b.dataset.topic;state.filter='main';state.selected=null;state.edge=null;render();}
  if(fromDetailsLink){$('inspector').scrollTop=0;$('inspector').scrollIntoView({block:'start',behavior:'instant'});$('inspector').focus({preventScroll:true});}
  else if(moduleId)document.querySelector(`#nodes [data-module="${moduleId}"]`)?.focus({preventScroll:true});
  else if(edgeId)document.querySelector(`#connections [data-edge="${edgeId}"]`)?.focus({preventScroll:true});
});
$('connections').addEventListener('keydown',event=>{if(['Enter',' '].includes(event.key)&&event.target.dataset.edge){event.preventDefault();const id=event.target.dataset.edge;selectEdge(id);document.querySelector(`#connections [data-edge="${id}"]`)?.focus({preventScroll:true});}});
$('suggestions').addEventListener('change',event=>{leaveWalk();state.suggestions=event.target.checked;state.edge=null;render();});
$('scenario').addEventListener('change',event=>{state.scenario=event.target.value;leaveWalk();state.edge=null;state.selected=null;render();});
function stepBy(delta){const flow=scenarios[state.scenario];state.step=(state.step+delta+flow.steps.length)%flow.steps.length;state.edge=flow.steps[state.step][0];state.selected=null;state.suggestions=true;render();}
$('next').addEventListener('click',()=>stepBy(1));$('previous').addEventListener('click',()=>stepBy(-1));
$('exit-walk').addEventListener('click',()=>{leaveWalk();state.edge=null;state.selected=null;render();});
$('reset').addEventListener('click',()=>{Object.assign(state,{view:'logical',filter:'main',topic:'main',suggestions:true,selected:null,edge:null,scenario:'navigate',step:-1});$('scenario').value='navigate';render();});
$('print')?.addEventListener('click',()=>window.print());
if($('question-list')) $('question-list').innerHTML=questions.map(([s,t,d])=>`<article class="question"><span class="status">${s}</span><h3>${t}</h3><p>${d}</p></article>`).join('');
$('process-groups').innerHTML=processes.map(p=>`<article class="process-card process-${p.id}"><strong>${p.name}</strong><p>${p.members.filter(id=>id!=='tf').map(id=>names[id]).join(' · ')}</p><small>${p.note}</small></article>`).join('');
$('scenario').innerHTML=Object.entries(scenarios).map(([id,s])=>`<option value="${id}">${s.name}</option>`).join('');
render();
