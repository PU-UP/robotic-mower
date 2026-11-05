// Deployment geometry is separate from the unchanged logical architecture.
function createIpcLayout(modules, edges, processes, routeEdges = edges) {
  const positions = {
    business:[650,16], decision:[280,250], map:[650,250], anomaly:[1020,250],
    slam:[70,540], tf:[330,540], percep:[190,710],
    navmap:[690,540], global:[960,540], local:[1230,540],
    recovery:[825,710], motion:[1095,710],
    sensors:[70,868], camera:[310,868], board:[825,868], motor:[1230,868]
  };
  const bounds = {perception:[40,430,490,380],decision:[180,150,1120,210],planning:[660,430,780,380]};
  const groups = processes.map(p => {const [x,y,w,h]=bounds[p.id];return {...p,x,y,w,h};});
  const overview = [
    {from:'business',to:'decision',path:'M740 100 L740 150',lx:870,ly:130,label:'任务 · 地图属性',reverseLabel:'状态'},
    {from:'perception',to:'decision',path:'M285 430 L285 360',lx:285,ly:400,label:'定位 · 轨迹 · 异常',reverseLabel:'调度'},
    {from:'decision',to:'planning',path:'M1100 360 L1100 430',lx:1100,ly:400,label:'任务调度 · 地图资产',reverseLabel:'执行反馈'},
    {from:'perception',to:'planning',path:'M530 620 L660 620',lx:595,ly:602,label:'TF · BEV · Submap'},
    {from:'sensors',to:'perception',path:'M160 868 L160 810',lx:160,ly:840,label:'定位传感器'},
    {from:'camera',to:'perception',path:'M400 868 L400 810',lx:400,ly:840,label:'视觉输入'},
    {from:'board',to:'decision',path:'M915 952 L915 976 L1460 976 L1460 300 L1300 300',lx:1360,ly:840,label:'硬件异常'},
    {from:'board',to:'planning',path:'M915 868 L915 810',lx:915,ly:840,label:'轮速'},
    {from:'planning',to:'motor',path:'M1320 810 L1320 868',lx:1160,ly:840,label:'运动指令',reverseLabel:'执行反馈'}
  ];
  const nodes = modules.map(m => {
    if (!positions[m.id]) throw new Error(`Missing deployment position: ${m.id}`);
    return {...m, x:positions[m.id][0], y:positions[m.id][1], w:180, h:84};
  });
  const byId = Object.fromEntries(nodes.map(m=>[m.id,m]));
  const headers=groups.map(g=>({x:g.x+16,y:g.y+8,w:280,h:52}));
  const boxes = [...nodes.map(n=>({...n,x:n.x-36,y:n.y-36,w:n.w+72,h:n.h+72})), ...headers];
  // Each visible interface gets its own port, with a straight 36px approach to the arrow.
  const endpoints=[];
  for(const edge of routeEdges)for(const end of ['from','to']) {
    const n=byId[edge[end]], other=byId[edge[end==='from'?'to':'from']];
    const dx=other.x-n.x,dy=other.y-n.y;
    let side=Math.abs(dy)>100?(dy>0?'bottom':'top'):(dx>0?'right':'left');
    const header=headers.find(h=>n.x+n.w/2>h.x&&n.x+n.w/2<h.x+h.w&&h.y>other.y+other.h&&h.y+h.h<n.y);
    if(side==='top'&&header)side=dx>0?'right':'left';
    endpoints.push({edge:edge.id,end,node:n,other,side,order:side==='top'||side==='bottom'?other.x:other.y});
  }
  // Spread dense fan-outs across adjacent sides instead of squeezing arrowheads together.
  for(const n of nodes)for(const side of ['left','right']){
    const list=endpoints.filter(p=>p.node===n&&p.side===side);
    while(list.length>4){
      const p=list.pop();
      p.side=p.other.y<n.y?'top':'bottom';
      p.order=p.other.x;
    }
  }
  for(const n of nodes)for(const side of ['left','right','top','bottom']) {
    const list=endpoints.filter(p=>p.node===n&&p.side===side).sort((a,b)=>a.order-b.order||a.edge.localeCompare(b.edge));
    list.forEach((p,i)=>{
      const horizontal=side==='top'||side==='bottom';
      const offset=(i-(list.length-1)/2)*Math.min(22,((horizontal?n.w:n.h)-24)/Math.max(1,list.length-1));
      p.border={x:horizontal?n.x+n.w/2+offset:side==='left'?n.x:n.x+n.w,y:horizontal?(side==='top'?n.y:n.y+n.h):n.y+n.h/2+offset};
      p.anchor={x:p.border.x+(side==='left'?-36:side==='right'?36:0),y:p.border.y+(side==='top'?-36:side==='bottom'?36:0)};
    });
  }
  const allAnchors=endpoints.map(p=>p.anchor);
  const xs = [...new Set([12,1468,...allAnchors.map(p=>p.x),...boxes.flatMap(n=>[n.x-24,n.x,n.x+n.w,n.x+n.w+24])])].filter(x=>x>=8&&x<=1472).sort((a,b)=>a-b);
  const ys = [...new Set([8,982,...allAnchors.map(p=>p.y),...boxes.flatMap(n=>[n.y-24,n.y,n.y+n.h,n.y+n.h+24])])].filter(y=>y>=8&&y<=982).sort((a,b)=>a-b);
  const points = ys.flatMap(y=>xs.map(x=>({x,y})));
  const inside = p => boxes.some(b=>p.x>b.x&&p.x<b.x+b.w&&p.y>b.y&&p.y<b.y+b.h);
  const crosses = (a,b) => boxes.some(r=>a.y===b.y
    ? a.y>r.y&&a.y<r.y+r.h&&Math.max(a.x,b.x)>r.x&&Math.min(a.x,b.x)<r.x+r.w
    : a.x>r.x&&a.x<r.x+r.w&&Math.max(a.y,b.y)>r.y&&Math.min(a.y,b.y)<r.y+r.h);
  const neighbors = points.map((p,i)=>inside(p)?[]:[i%xs.length?i-1:-1,i%xs.length<xs.length-1?i+1:-1,i-xs.length,i+xs.length]
    .filter(j=>j>=0&&j<points.length&&!inside(points[j])&&!crosses(p,points[j])));
  const index = (x,y)=>ys.indexOf(y)*xs.length+xs.indexOf(x);
  const distance = (a,b)=>Math.abs(a.x-b.x)+Math.abs(a.y-b.y);
  const usage = new Map();
  const routes = {};
  const lanes=[];
  const normal={left:{x:-1,y:0},right:{x:1,y:0},top:{x:0,y:-1},bottom:{x:0,y:1}};
  for (const edge of routeEdges) {
    const start=endpoints.find(p=>p.edge===edge.id&&p.end==='from');
    const end=endpoints.find(p=>p.edge===edge.id&&p.end==='to');
    const targets = new Set([index(end.anchor.x,end.anchor.y)]);
    const estimate = i=>Math.min(...[...targets].map(t=>distance(points[i],points[t])));
    const open = [index(start.anchor.x,start.anchor.y)].map(i=>({i,dir:2,cost:0,score:estimate(i),previous:null}));
    const costs = new Map(open.map(s=>[`${s.i}:2`,0]));
    let finish;
    while(open.length) {
      open.sort((a,b)=>b.score-a.score);
      const current=open.pop();
      if(current.cost!==costs.get(`${current.i}:${current.dir}`)) continue;
      if(targets.has(current.i)){finish=current;break;}
      for(const next of neighbors[current.i]) {
        const a=points[current.i], b=points[next];
        const dot=n=>(b.x-a.x)*n.x+(b.y-a.y)*n.y;
        if(!current.previous&&dot(normal[start.side])<0||targets.has(next)&&dot(normal[end.side])>0)continue;
        const dir=b.y===a.y?0:1;
        const nearby=lanes.some(l=>l.dir===dir&&Math.abs((dir===0?a.y:a.x)-l.axis)<18&&Math.max(dir===0?a.x:a.y,dir===0?b.x:b.y)>l.min&&Math.min(dir===0?a.x:a.y,dir===0?b.x:b.y)<l.max);
        const segment=[current.i,next].sort((a,b)=>a-b).join(':');
        const cost=current.cost+distance(points[current.i],points[next])+(current.dir!==2&&current.dir!==dir?48:0)+(usage.get(segment)||0)*80+(nearby?distance(a,b)*3+30:0);
        const key=`${next}:${dir}`;
        if(cost>=(costs.get(key)??Infinity))continue;
        costs.set(key,cost);
        open.push({i:next,dir,cost,score:cost+estimate(next),previous:current});
      }
    }
    if(!finish)throw new Error(`Cannot route deployment interface: ${edge.id}`);
    const chain=[];
    for(let cursor=finish;cursor;cursor=cursor.previous)chain.unshift(cursor.i);
    for(let i=1;i<chain.length;i++) {
      const key=[chain[i-1],chain[i]].sort((a,b)=>a-b).join(':');
      usage.set(key,(usage.get(key)||0)+1);
    }
    const line=[start.border,...chain.map(i=>points[i]),end.border]
      .filter((p,i,all)=>!i||i===all.length-1||!((all[i-1].x===p.x&&p.x===all[i+1].x)||(all[i-1].y===p.y&&p.y===all[i+1].y)));
    for(let i=1;i<line.length;i++){
      const a=line[i-1],b=line[i],dir=a.y===b.y?0:1;
      lanes.push({dir,axis:dir===0?a.y:a.x,min:Math.min(dir===0?a.x:a.y,dir===0?b.x:b.y),max:Math.max(dir===0?a.x:a.y,dir===0?b.x:b.y)});
    }
    const segments=line.slice(1).map((p,i)=>({a:line[i],b:p,length:distance(line[i],p)})).sort((a,b)=>b.length-a.length);
    const longest=segments[0];
    routes[edge.id]={path:line.map((p,i)=>`${i?'L':'M'}${p.x} ${p.y}`).join(' '), lx:(longest.a.x+longest.b.x)/2, ly:(longest.a.y+longest.b.y)/2-10, points:line};
  }
  return {nodes:nodes.sort((a,b)=>a.y-b.y||a.x-b.x),groups,routes,overview,headers,height:990};
}
if(typeof module!=='undefined')module.exports=createIpcLayout;

