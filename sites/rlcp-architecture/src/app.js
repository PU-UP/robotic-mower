const {modules,edges,questions,scenarios,topics,processes}=architecture;
const $=id=>document.getElementById(id);
const names=Object.fromEntries(modules.map(m=>[m.id,m.name]));
const ipcLayout=createIpcLayout(modules,edges,processes,[]);
const processOf=id=>processes.find(p=>p.members.includes(id));
const isInternal=e=>!!processOf(e.from)&&processOf(e.from)===processOf(e.to);
const colors={data:'#286fa4',command:'#b36a24',feedback:'#258473',aggregate:'#627989'};
const typeNames={data:'数据',command:'指令',feedback:'反馈'};
const state={view:'logical',filter:'main',topic:'main',suggestions:true,selected:null,edge:null,scenario:'navigate',step:-1};
const notes={logical:'Decision 节点表示调度核心；Anomaly、Map Server 是决策模块的子模块，分开绘制以展开接口。连线表示逻辑交互。',ipc:'总览只显示进程之间及外部的交互；点击子模块查看具体接口，点击“返回进程总览”收起。Global / local controller 仍经 Decision 协调。',single:'后期候选：算法模块可装配进同一进程。虚框仅表示候选装配范围，Business_core 是否合并待定；逻辑职责和统一调度关系保持不变。'};
function visibleEdges(){
  if(state.step>=0){const ids=new Set(scenarios[state.scenario].steps.map(s=>s[0]));return edges.filter(e=>ids.has(e.id));}
  const topicEdges=new Set(topics[state.topic].edges);
  return edges.filter(e=>(state.view!=='ipc'||(state.edge?e.id===state.edge:!state.selected||e.from===state.selected||e.to===state.selected))&&(state.suggestions||e.origin!=='补充建议')&&(state.filter==='all'||state.filter==='main'&&(topicEdges.has(e.id)||state.selected&&(e.from===state.selected||e.to===state.selected))||e.type===state.filter));
}
function edgeButton(e){return `<button data-edge="${e.id}">${e.label}<small>${names[e.from]} → ${names[e.to]}</small></button>`;}
function renderInspector(){
  const e=edges.find(e=>e.id===state.edge);
  if(e){$('inspector').innerHTML=`<span class="small-tag ${e.origin==='补充建议'?'proposal':''}">${e.origin}</span><h2>${e.label}</h2><p class="subtitle">${names[e.from]} → ${names[e.to]}${state.view==='ipc'?'<br>'+(!processOf(e.from)||!processOf(e.to)?'外部接口':isInternal(e)?'进程内接口':'IPC · '+processOf(e.from).name+' → '+processOf(e.to).name):''}</p><p class="summary">${e.meaning}</p><div class="detail-label">接口需要约定</div><p class="ownership">${e.contract}</p><div class="boundary"><strong>传输与逻辑分开</strong>${state.view==='logical'?'本接口描述交互含义，不指定消息格式与传输机制。':state.view==='ipc'?'跨进程使用 IPC；同进程可为库调用。当前按感知定位、决策、规控三个容器装配。':'同进程可通过组件接口传递，仍需约定数据生命周期、取消、顺序与有效性。'}</div><div class="detail-label">两端职责</div><div class="port-list"><button data-module="${e.from}">${names[e.from]} · 发送方 →</button><button data-module="${e.to}">${names[e.to]} · 接收方 →</button></div>`;return;}
  const m=modules.find(m=>m.id===state.selected);
  if(!m){$('inspector').innerHTML=state.view==='ipc'?'<h2>三个进程，一条协作链</h2><p class="summary">感知定位提供观测与位姿，决策协调任务，规控生成地图并规划执行。容器表示部署归属，总览连线汇总进程间的接口。</p><div class="boundary"><strong>先看跨进程，再看内部职责</strong>点击子模块展开具体接口，再用“返回进程总览”收起。汇总线的箭头依据当前筛选范围，悬停可查看包含的接口。TF 是 SLAM 公共接口。</div><div class="detail-label">关键交互</div><div class="port-list">'+['global-state','decision-local','board-anomaly','percep-submap'].map(id=>edgeButton(edges.find(e=>e.id===id))).join('')+'</div><p class="ownership">Recovery / motion 暂归规控；Business_core 为外部业务模块。</p>':'<h2>查看模块与交互</h2><p class="summary">点击模块查看职责，点击连线查看数据与指令。切换“当前三进程”查看部署分组；下方可逐步演示协作流程。</p>';return;}
  const incoming=edges.filter(e=>e.to===m.id),outgoing=edges.filter(e=>e.from===m.id);
  $('inspector').innerHTML=`<span class="small-tag ${m.tag.includes('待')?'proposal':''}">${m.tag}</span><h2>${m.name}</h2><p class="subtitle">${m.cn}<br>${m.role}<br>${processOf(m.id)?.name||'算法进程外部'}${m.parent?' · 隶属决策模块':''}</p><p class="summary">${m.summary}</p><div class="detail-label">状态与数据归属</div><p class="ownership">${m.owns}</p><div class="detail-label">内部职责 · 确认范围与建议见各项标注</div><ul class="parts">${m.parts.map(([n,d])=>`<li><strong>${n}</strong><p>${d}</p></li>`).join('')}</ul><div class="boundary"><strong>边界与待确认项</strong>${m.boundary}</div><div class="detail-label">输入接口 · 含补充建议</div><div class="port-list">${incoming.map(edgeButton).join('')||'<p class="ownership">外部输入未进一步展开。</p>'}</div><div class="detail-label">输出接口 · 含补充建议</div><div class="port-list">${outgoing.map(edgeButton).join('')||'<p class="ownership">外部输出未进一步展开。</p>'}</div>`;
}
// Measure the actual SVG text; labels reserve space independently of route selection.
function placeInterfaceLabels(layout){
  const occupied=[...layout.nodes.map(n=>({x:n.x-8,y:n.y-8,w:n.w+16,h:n.h+16})),...layout.headers];
  const overlap=(a,b)=>a.x<b.x+b.w&&a.x+a.w>b.x&&a.y<b.y+b.h&&a.y+a.h>b.y;
  const lineBoxes=Object.values(layout.routes).flatMap(r=>r.points.slice(1).map((p,i)=>({x:Math.min(p.x,r.points[i].x)-2,y:Math.min(p.y,r.points[i].y)-2,w:Math.abs(p.x-r.points[i].x)+4,h:Math.abs(p.y-r.points[i].y)+4})));
  for(const group of $('connections').querySelectorAll('[data-edge]')){
    const text=group.querySelector('text'), route=layout.routes[group.dataset.edge];
    const box=text.getBBox(),w=box.width+14,h=box.height+10;
    const candidates=[];
    for(let i=1;i<route.points.length;i++){
      const a=route.points[i-1],b=route.points[i],horizontal=a.y===b.y;
      for(const t of [.5,.25,.75])for(const offset of [18,36,54,72,90,120])for(const sign of [-1,1]){
        const cx=a.x+(b.x-a.x)*t+(horizontal?0:sign*(w/2+offset));
        const cy=a.y+(b.y-a.y)*t+(horizontal?sign*offset:0);
        const rect={x:cx-w/2,y:cy-h/2,w,h};
        if(rect.x<6||rect.x+w>1474||rect.y<6||rect.y+h>layout.height-6||occupied.some(r=>overlap(rect,r)))continue;
        candidates.push({...rect,cx,cy,score:offset+(horizontal?0:18)+Math.abs(t-.5)*30+lineBoxes.filter(r=>overlap(rect,r)).length*200});
      }
    }
    candidates.sort((a,b)=>a.score-b.score);
    const best=candidates[0];
    if(!best)throw new Error('No room for interface label: '+group.dataset.edge);
    text.setAttribute('x',best.cx);
    text.setAttribute('y',best.cy+box.height/2-3);
    occupied.push(best);
  }
}
function render(){
  $('view-note').textContent=notes[state.view];
  document.querySelector('.ipc-control').hidden=state.view!=='ipc';
  const overview=state.view==='ipc'&&!state.selected&&!state.edge&&state.step<0;
  $('ipc-overview').disabled=overview;
  $('legend-note').textContent=state.view==='ipc'?(overview?'汇总线连接进程边界 · 悬停查看接口 · 点击子模块展开':'显示所选模块 / 接口 · 返回进程总览可收起'):'箭头指向接收方 · TF 为公共接口';
  const height=state.view==='ipc'?ipcLayout.height:960;
  $('connections').setAttribute('viewBox',`0 0 1480 ${height}`);
  $('graph').style.setProperty('--graph-height',height);
  document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.view===state.view));
  document.querySelectorAll('[data-filter]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.filter===state.filter));
  document.querySelectorAll('[data-topic]').forEach(b=>b.setAttribute('aria-pressed',state.filter==='main'&&b.dataset.topic===state.topic));
  $('topic-note').textContent=state.filter==='main'?topics[state.topic].note:'当前按全图接口类型筛选；点击专题按钮返回相应关系视图。';
  $('suggestions').checked=state.suggestions;
  const shown=visibleEdges();
  const detailLayout=state.view==='ipc'&&!overview?createIpcLayout(modules,edges,processes,shown):ipcLayout;
  const focus=state.edge?new Set(edges.filter(e=>e.id===state.edge).flatMap(e=>[e.from,e.to])):state.selected?new Set([state.selected,...shown.filter(e=>e.from===state.selected||e.to===state.selected).flatMap(e=>[e.from,e.to])]):null;
  let svg=`<defs>${Object.entries(colors).map(([k,v])=>`<marker id="arrow-${k}" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="${state.view==='ipc'?10:6}" markerHeight="${state.view==='ipc'?10:6}" ${state.view==='ipc'?'markerUnits="userSpaceOnUse"':''} orient="auto-start-reverse"><path d="M0 0 L8 4 L0 8 Z" fill="${v}"/></marker>`).join('')}</defs>`;
  if(state.view==='single')svg+='<path class="deployment-outline" d="M23 155 H315 V285 H645 V20 H1190 V910 H23 V760 H255 V635 H23 Z"/><text class="deployment-label" x="660" y="897">候选算法进程 · client / server 仍为逻辑角色</text>';
  $('graph').dataset.deployment=state.view;
  if(state.view!=='ipc')svg+='<text class="layer-label" x="330" y="25">BUSINESS</text><text class="layer-label" x="660" y="25">ASYNC CLIENT</text><text class="layer-label" x="1280" y="25">HARDWARE EVENTS</text>';
  if(state.view==='ipc')svg+=ipcLayout.groups.map(g=>`<g class="process-region process-${g.id}" data-process="${g.id}" aria-label="${g.name}"><rect x="${g.x}" y="${g.y}" width="${g.w}" height="${g.h}" rx="16"/><text class="process-title" x="${g.x+24}" y="${g.y+32}">${g.name}</text><text class="process-caption" x="${g.x+24}" y="${g.y+53}">${g.id==='perception'?'定位 · 观测 · 公共 TF':g.id==='decision'?'调度核心 · 异常检测 · 地图资产':'导航地图 · 规划 · 运动执行'}</text></g>`).join('');
  if(overview) {
    const endpoint=id=>processOf(id)?.id||id;
    svg+=ipcLayout.overview.map(r=>{
      const forward=shown.filter(e=>endpoint(e.from)===r.from&&endpoint(e.to)===r.to);
      const backward=shown.filter(e=>endpoint(e.from)===r.to&&endpoint(e.to)===r.from);
      const members=[...forward,...backward];
      if(!members.length)return '';
      const type=members.every(e=>e.type===members[0].type)?members[0].type:'aggregate';
      const summary=r.reverseLabel?[forward.length?r.label:'',backward.length?r.reverseLabel:''].filter(Boolean).join(' · '):r.label;
      const label=state.filter==='main'||state.filter==='all'?summary:typeNames[state.filter];
      return `<g class="edge aggregate ${members.every(e=>e.origin==='补充建议')?'suggested':''}" style="--edge-color:${colors[type]}" data-process-link="${r.from}:${r.to}" tabindex="0" aria-label="${summary}，${members.length} 条接口"><title>${members.map(e=>names[e.from]+' → '+names[e.to]+'：'+e.label).join('；')}</title><path class="route" d="${r.path}" ${backward.length?'marker-start="url(#arrow-'+type+')"':''} ${forward.length?'marker-end="url(#arrow-'+type+')"':''}/><path class="hit" d="${r.path}"/><text x="${r.lx}" y="${r.ly}">${label}</text></g>`;
    }).join('');
  }
  else svg+=shown.map(e=>{const geometry=state.view==='ipc'?detailLayout.routes[e.id]:e;const active=state.edge===e.id||!state.edge&&state.selected&&(e.from===state.selected||e.to===state.selected);const dim=!!(state.edge||state.selected)&&!active;return `<g class="edge ${state.view==='ipc'?(isInternal(e)?'internal':'cross-process'):''} ${e.origin==='补充建议'?'suggested':''} ${active?'active':''} ${dim?'dim':''}" style="--edge-color:${colors[e.type]}" data-edge="${e.id}" role="button" tabindex="0" aria-label="${names[e.from]} 到 ${names[e.to]}：${e.label}，${e.origin}"><title>${e.label} · ${e.origin}</title><path class="route" d="${geometry.path}" marker-end="url(#arrow-${e.type})"/><path class="hit" d="${geometry.path}"/><text x="${geometry.lx}" y="${geometry.ly}">${e.label}</text></g>`;}).join('');
  $('connections').innerHTML=svg;
  if(state.view==='ipc'&&!overview)placeInterfaceLabels(detailLayout);
  $('nodes').innerHTML=(state.view==='ipc'?ipcLayout.nodes:modules).map(m=>`<button data-module="${m.id}" class="node ${m.kind} process-${processOf(m.id)?.id||'external'} ${m.id==='tf'?'public-interface':''} ${state.selected===m.id&&!state.edge?'selected':''} ${focus&&!focus.has(m.id)?'dim':''}" style="--x:${m.x};--y:${m.y}" aria-pressed="${state.selected===m.id&&!state.edge}" aria-label="${m.name} ${m.cn}：查看职责"><strong>${m.id==='anomaly'?'Anomaly':m.name}</strong><span>${m.cn}</span><small title="${m.role}">${state.view==='ipc'?(processOf(m.id)?.name||'外部输入 / 执行对象'):m.role}</small></button>`).join('');
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
  const fromDetailsLink=!!b.closest('table,.principles');
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
$('ipc-overview').addEventListener('click',()=>{leaveWalk();state.edge=null;state.selected=null;render();$('ipc-overview').focus({preventScroll:true});});
$('suggestions').addEventListener('change',event=>{leaveWalk();state.suggestions=event.target.checked;state.edge=null;render();});
$('scenario').addEventListener('change',event=>{state.scenario=event.target.value;leaveWalk();state.edge=null;state.selected=null;render();});
function stepBy(delta){const flow=scenarios[state.scenario];state.step=(state.step+delta+flow.steps.length)%flow.steps.length;state.edge=flow.steps[state.step][0];state.selected=null;state.suggestions=true;render();}
$('next').addEventListener('click',()=>stepBy(1));$('previous').addEventListener('click',()=>stepBy(-1));
$('exit-walk').addEventListener('click',()=>{leaveWalk();state.edge=null;state.selected=null;render();});
$('reset').addEventListener('click',()=>{Object.assign(state,{view:'logical',filter:'main',topic:'main',suggestions:true,selected:null,edge:null,scenario:'navigate',step:-1});$('scenario').value='navigate';render();});
$('print')?.addEventListener('click',()=>window.print());
if($('question-list')) $('question-list').innerHTML=questions.map(([s,t,d])=>`<article class="question"><span class="status">${s}</span><h3>${t}</h3><p>${d}</p></article>`).join('');
$('scenario').innerHTML=Object.entries(scenarios).map(([id,s])=>`<option value="${id}">${s.name}</option>`).join('');
render();
