// Real browser only. Boots no bridge and writes no preset data.
// Live-view aware: never waits on networkidle (the Controller view holds an open
// EventSource, so the network never goes idle). It waits for the 23 labels AND the
// live indicator reading live, then drives real UDP axes so the stick dots, trigger
// bars and gyro dots are DRAWN, and measures with those overlays present as obstacles.
// node tests/ui_controller_geometry.cjs URL CHROMIUM [--single-process] [--out DIR]
//                                       [--mutation m1|m2|m3] [--only-viewport WxH] [--closed-only]
const fs = require('node:fs');
const path = require('node:path');
const dgram = require('node:dgram');
const args = process.argv.slice(2);
const [url, executablePath] = args;
const option = flag => args.includes(flag) ? args[args.indexOf(flag) + 1] : null;
const out = option('--out'), mutation = option('--mutation'), onlyViewport = option('--only-viewport');
const closedOnly = args.includes('--closed-only');
if (!url || !executablePath || (mutation && !['m1','m2','m3'].includes(mutation))) {
  console.error('Usage: node ui_controller_geometry.cjs URL CHROMIUM [--single-process] [--out DIR] [--mutation m1|m2|m3] [--only-viewport WxH] [--closed-only]');
  process.exit(2);
}
const target = new URL(url);
if (target.hostname !== '127.0.0.1' || ['7723','45123'].includes(target.port)) { console.error('unsafe url'); process.exit(2); }
const {chromium} = require(process.env.PLAYWRIGHT_CORE || '/Users/viddyslap/Documents/project-workspaces/life-os-showday/web-ui-server/node_modules/playwright-core');
const results = [], samples = [];
const check = (name, pass, detail = '') => {
  results.push({name, pass: Boolean(pass), detail});
  console.log(`${pass ? 'PASS' : 'FAIL'} ${name} ${JSON.stringify(detail)}`);
};
const inside = (p,r) => p.x >= r.x && p.x <= r.right && p.y >= r.y && p.y <= r.bottom;
const overlap = (a,b) => a.x < b.right && b.x < a.right && a.y < b.bottom && b.y < a.bottom;
const cross = (a,b,c) => (b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);
const equal = (a,b) => Math.hypot(a.x-b.x,a.y-b.y) < 0.01;
function intersect(a,b,c,d, excludeShared = false) {
  const eps=1e-5, shared=[a,b].some(p=>[c,d].some(q=>equal(p,q)));
  const collinear=Math.abs(cross(a,b,c))<eps && Math.abs(cross(a,b,d))<eps;
  if (collinear) {
    const axis=Math.abs(b.x-a.x)>Math.abs(b.y-a.y)?'x':'y';
    const length=Math.min(Math.max(a[axis],b[axis]),Math.max(c[axis],d[axis]))-Math.max(Math.min(a[axis],b[axis]),Math.min(c[axis],d[axis]));
    return length > eps || (length >= -eps && !(excludeShared && shared));
  }
  if (excludeShared && shared) return false;
  return cross(a,b,c)*cross(a,b,d)<=eps && cross(c,d,a)*cross(c,d,b)<=eps;
}
const segments = points => points.slice(1).map((p,i)=>[points[i],p]);
const corners = r => [{x:r.x,y:r.y},{x:r.right,y:r.y},{x:r.right,y:r.bottom},{x:r.x,y:r.bottom}];
const edges = r => segments([...corners(r),corners(r)[0]]);
function lineHitsRect(a,b,r) {
  const c=corners(r);
  return inside(a,r)||inside(b,r)||c.some((p,i)=>intersect(a,b,p,c[(i+1)%4]));
}
function polygonHitsRect(poly,r) {
  if (segments([...poly,poly[0]]).some(([a,b])=>lineHitsRect(a,b,r))) return true;
  // Rectangle wholly inside a triangle is still an intersection.
  return corners(r).some(p=>{const signs=poly.map((a,i)=>cross(a,poly[(i+1)%poly.length],p));return signs.every(s=>s>=0)||signs.every(s=>s<=0);});
}
// Point-to-segment and segment-to-segment distance, for criterion c.
function pointSegment(p,a,b) {
  const l=(b.x-a.x)**2+(b.y-a.y)**2;
  const t=l?Math.max(0,Math.min(1,((p.x-a.x)*(b.x-a.x)+(p.y-a.y)*(b.y-a.y))/l)):0;
  return Math.hypot(p.x-a.x-t*(b.x-a.x),p.y-a.y-t*(b.y-a.y));
}
function segmentDistance(a,b,c,d) {
  if (intersect(a,b,c,d)) return 0;
  return Math.min(pointSegment(a,c,d),pointSegment(b,c,d),pointSegment(c,a,b),pointSegment(d,a,b));
}
// Every drawn piece of one leader: its polyline segments plus its arrowhead edges.
function leaderPieces(g,leader) {
  const head=g.heads.find(h=>h.id===leader.id);
  const pieces=segments(leader.points).map(([a,b])=>({a,b,part:'segment'}));
  if (head) for (const [a,b] of segments([...head.points,head.points[0]])) pieces.push({a,b,part:'head'});
  return pieces;
}
function assertGeometry(tag,g) {
  samples.push({tag,...g});
  const ids=g.expected.map(c=>c.id).sort(), names=a=>a.map(x=>x.id).sort();
  for(const [name,items] of [['labels',g.labels],['leaders',g.leaders],['shapes',g.shapes],['arrowheads',g.heads]])
    check(`${tag}.23-${name}`, items.length===23 && JSON.stringify(names(items))===JSON.stringify(ids),names(items));
  // The stream must be connected and the overlays actually drawn, or the run measured
  // an empty picture and every obstacle assertion below would pass vacuously.
  check(`${tag}.stream-live-with-overlays-drawn`,
    g.live==='live' && Number(g.bars.r2)>40 && Number(g.bars.l2)>60 && g.dots.left_stick[0]!=='280' && g.dots.right_stick[0]!=='900',
    {live:g.live,dots:g.dots,bars:g.bars});
  const overlaps=[];
  for(let i=0;i<g.labels.length;i++)for(let j=i+1;j<g.labels.length;j++)if(overlap(g.labels[i].box,g.labels[j].box))overlaps.push([g.labels[i].id,g.labels[j].id]);
  check(`${tag}.label-overlaps`,overlaps.length===0,overlaps);
  const lines=g.leaders.flatMap(l=>segments(l.points).map(([a,b])=>({id:l.id,a,b}))), crossings=[];
  for(let i=0;i<lines.length;i++)for(let j=i+1;j<lines.length;j++)if(intersect(lines[i].a,lines[i].b,lines[j].a,lines[j].b,true))crossings.push([lines[i].id,lines[j].id]);
  check(`${tag}.leader-intersections`,crossings.length===0,crossings);
  for(const leader of g.leaders) {
    const shape=g.shapes.find(s=>s.id===leader.id), end=leader.points.at(-1);
    const r=shape?.box;
    const distance=r&&end ? Math.min(...edges(r).map(([a,b])=>pointSegment(end,a,b))) : Infinity;
    const others=end?g.shapes.filter(s=>s.id!==leader.id&&inside(end,s.box)).map(s=>s.id):[];
    check(`${tag}.own-edge.${leader.id}`,Number.isFinite(distance)&&distance<=3&&others.length===0,{distance,insideOther:others,end});
    const head=g.heads.find(h=>h.id===leader.id), glyphHits=[];
    for(const glyph of g.glyphs) {
      const b=glyph.box, stroke=leader.stroke/2;
      const expanded={x:b.x-stroke,y:b.y-stroke,right:b.right+stroke,bottom:b.bottom+stroke};
      if(segments(leader.points).some(([a,b])=>lineHitsRect(a,b,expanded)) || (head&&polygonHitsRect(head.points,b)))glyphHits.push(glyph.text);
    }
    check(`${tag}.glyph-clear.${leader.id}`,glyphHits.length===0,glyphHits);
    check(`${tag}.leader-visible.${leader.id}`,leader.points.length>=2&&leader.points.every(p=>Number.isFinite(p.x)&&Number.isFinite(p.y))&&segments(leader.points).some(([a,b])=>!equal(a,b))&&head?.points.length===3,{points:leader.points});
  }
  const outside=g.labels.concat(g.shapes).filter(l=>!inside({x:l.box.x,y:l.box.y},g.pane)||!inside({x:l.box.right,y:l.box.bottom},g.pane)).map(l=>l.id);
  check(`${tag}.inside-visible-pane`,outside.length===0,outside);
  const covered=g.labels.filter(l=>!l.topmost).map(l=>({id:l.id,by:l.coveredBy}));
  check(`${tag}.labels-topmost`,covered.length===0,covered);
  const clipped=g.labels.filter(l=>l.scrollWidth>l.clientWidth||l.nameHeight>l.box.bottom-l.box.y).map(l=>l.id);
  check(`${tag}.labels-unwrapped`,clipped.length===0,clipped);
  check(`${tag}.no-page-or-pane-scroll`,g.scroll.every(s=>s.width<=s.clientWidth+1&&s.height<=s.clientHeight+1&&s.top===0&&s.left===0),g.scroll);
  if(g.card)check(`${tag}.card-inside-pane`,inside({x:g.card.x,y:g.card.y},g.pane)&&inside({x:g.card.right,y:g.card.bottom},g.pane),g.card);

  // b. NO LEADER THROUGH ANOTHER CONTROL. A leader segment, bend or arrowhead must not
  // intersect or touch (distance 0) the geometry box of any OTHER control's data-control
  // shape, trigger track or live bar. A leader ending on its OWN shape edge is the design.
  const obstacles=[
    ...g.shapes.map(s=>({owner:s.id,what:'shape',box:s.box})),
    ...g.overlays.filter(o=>o.what==='track'||o.what==='bar').map(o=>({owner:o.owner,what:o.what,box:o.box}))];
  const through=[];
  for(const leader of g.leaders) for(const piece of leaderPieces(g,leader)) for(const o of obstacles) {
    if(o.owner===leader.id) continue;
    if(lineHitsRect(piece.a,piece.b,o.box)) through.push({leader:leader.id,part:piece.part,hits:`${o.owner}.${o.what}`});
  }
  const throughUnique=[...new Map(through.map(t=>[`${t.leader}|${t.hits}|${t.part}`,t])).values()];
  check(`${tag}.b.no-leader-through-other-control`,throughUnique.length===0,throughUnique);

  // b2. NO LIVE OVERLAY OVER THE OPEN CARD OR ANY LABEL.
  const overlayHits=[];
  for(const o of g.overlays) {
    for(const label of g.labels) if(overlap(o.box,label.box)) overlayHits.push({overlay:`${o.owner}.${o.what}`,label:label.id});
    if(g.card && overlap(o.box,g.card)) overlayHits.push({overlay:`${o.owner}.${o.what}`,card:true});
  }
  check(`${tag}.b2.no-live-overlay-over-card-or-label`,overlayHits.length===0,overlayHits);

  // c. CLEARANCE >= 6 px between any two DIFFERENT leaders' segments, bends and arrowheads.
  let min={distance:Infinity,pair:null};
  const pieces=g.leaders.flatMap(l=>leaderPieces(g,l).map(p=>({...p,id:l.id})));
  for(let i=0;i<pieces.length;i++)for(let j=i+1;j<pieces.length;j++) {
    if(pieces[i].id===pieces[j].id) continue;
    const d=segmentDistance(pieces[i].a,pieces[i].b,pieces[j].a,pieces[j].b);
    if(d<min.distance) min={distance:d,pair:[`${pieces[i].id}.${pieces[i].part}`,`${pieces[j].id}.${pieces[j].part}`]};
  }
  check(`${tag}.c.leader-clearance-6px`,min.distance>=6.0,min);

  // d. 1024x768 DRAWER: title, tabs and the first two action rows fully visible inside the
  // card with the card's own scrollTop at 0.
  if(g.drawer) {
    const clipped=g.drawer.parts.filter(p=>!(p.box.x>=g.drawer.view.x-0.5 && p.box.right<=g.drawer.view.right+0.5 && p.box.y>=g.drawer.view.y-0.5 && p.box.bottom<=g.drawer.view.bottom+0.5))
      .map(p=>({part:p.name,overflowBottomPx:Number((p.box.bottom-g.drawer.view.bottom).toFixed(1)),overflowRightPx:Number((p.box.right-g.drawer.view.right).toFixed(1)),box:p.box}));
    check(`${tag}.d.drawer-rows-visible`,clipped.length===0&&g.drawer.scrollTop===0,{clipped,scrollTop:g.drawer.scrollTop,view:g.drawer.view,rows:g.drawer.parts.length});
  }
}
async function measure(page, expected, wantDrawer) {
  return page.evaluate(([expected,wantDrawer])=>{
    const box=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom};};
    const shown=e=>{const cs=getComputedStyle(e),r=e.getBoundingClientRect();return cs.display!=='none'&&cs.visibility!=='hidden'&&Number(cs.opacity)>0&&r.width>0&&r.height>0;};
    const points=e=>{
      const matrix=e.getScreenCTM(), transform=(x,y)=>{const p=new DOMPoint(x,y).matrixTransform(matrix);return {x:p.x,y:p.y};};
      if(e.tagName.toLowerCase()==='line')return [transform(e.x1.baseVal.value,e.y1.baseVal.value),transform(e.x2.baseVal.value,e.y2.baseVal.value)];
      return Array.from({length:e.points.numberOfItems},(_,i)=>{const p=e.points.getItem(i);return transform(p.x,p.y);});
    };
    const pane=box(document.getElementById('tab-editor')), status=box(document.querySelector('.statusbar')), header=box(document.querySelector('header'));
    pane.y=Math.max(pane.y,header.bottom,0);pane.bottom=Math.min(pane.bottom,status.y,innerHeight);pane.x=Math.max(pane.x,0);pane.right=Math.min(pane.right,innerWidth);
    // One .controller-live-overlay group per control, appended in map order, so the group
    // index is the join back to the control id. The overlay carries no data-control itself.
    const groups=[...document.querySelectorAll('.controller-live-overlay')];
    const overlays=[];
    groups.forEach((group,index)=>{
      const owner=expected[index]?.id ?? `group-${index}`;
      for(const e of group.querySelectorAll('circle, rect, line')) {
        if(!shown(e))continue;
        const cls=e.getAttribute('class')||'';
        const what=e.hasAttribute('data-live-dot')?'dot':e.hasAttribute('data-live-bar')?'bar':e.hasAttribute('data-live-axis')?'gyro':cls.includes('controller-live-track')?'track':cls||e.tagName;
        overlays.push({owner,what,box:box(e)});
      }
    });
    const cardEl=document.getElementById('controllerCard');
    let drawer=null;
    if(wantDrawer && !cardEl.hidden) {
      const view=box(cardEl);
      const rows=[...cardEl.querySelectorAll('.controller-row')].slice(0,2);
      const parts=[{name:'title',box:box(document.getElementById('controllerTitle'))},
                   {name:'tabs',box:box(cardEl.querySelector('.controller-tabs'))},
                   ...rows.map((e,i)=>({name:`row${i}:${e.dataset.action}`,box:box(e)}))];
      drawer={view,parts,scrollTop:cardEl.scrollTop};
    }
    return {expected,pane,overlays,drawer,
      labels:[...document.querySelectorAll('.controller-label')].map(e=>{const b=box(e),hit=document.elementFromPoint((b.x+b.right)/2,(b.y+b.bottom)/2);return {id:e.dataset.control,box:b,topmost:!!hit&&e.contains(hit),coveredBy:hit?.id||hit?.getAttribute('class')||hit?.tagName,scrollWidth:e.scrollWidth,clientWidth:e.clientWidth,nameHeight:e.querySelector('span').getBoundingClientRect().height};}),
      shapes:[...document.querySelectorAll('.controller-art [data-control]')].map(e=>({id:e.dataset.control,box:box(e)})),
      // Live overlay text (the gyro axis captions) is an overlay, not scene art: it is
      // judged by b2, not by the sdfix glyph-clear criterion.
      glyphs:[...document.querySelectorAll('.controller-art text')].filter(e=>!e.closest('.controller-live-overlay')).map(e=>({text:e.textContent,box:box(e)})),
      leaders:[...document.querySelectorAll('.controller-arrow')].map(e=>({id:e.dataset.controlArrow,points:points(e),stroke:parseFloat(getComputedStyle(e).strokeWidth)*e.getScreenCTM().a})),
      heads:[...document.querySelectorAll('.controller-arrow-head')].map(e=>({id:e.dataset.controlHead,points:points(e)})),
      card:cardEl.hidden?null:box(cardEl),
      live:document.getElementById('controllerLiveStatus').textContent,
      dots:Object.fromEntries([...document.querySelectorAll('[data-live-dot]')].map(e=>[e.dataset.liveDot,[e.getAttribute('cx'),e.getAttribute('cy')]])),
      bars:Object.fromEntries([...document.querySelectorAll('[data-live-bar]')].map(e=>[e.dataset.liveBar,e.getAttribute('width')])),
      scroll:[document.documentElement,document.body,document.getElementById('tab-editor'),document.querySelector('.controller-picture-scroll')].map(e=>({id:e.id||e.className||e.tagName,width:e.scrollWidth,height:e.scrollHeight,clientWidth:e.clientWidth,clientHeight:e.clientHeight,top:e.scrollTop,left:e.scrollLeft}))};
  },[expected,wantDrawer]);
}
(async()=>{
  if(out)fs.mkdirSync(out,{recursive:true});
  const settings=await (await fetch(new URL('/api/settings',url).href)).json();
  const [listenHost,listenPort]=String(settings.listen).split(':');
  if(listenHost!=='127.0.0.1'||Number(listenPort)===45123)throw new Error('unsafe listen '+settings.listen);
  const socket=dgram.createSocket('udp4');
  let seq=0;
  const send=o=>new Promise((resolve,reject)=>{
    const body={...o,seq:++seq};
    socket.send(Buffer.from(JSON.stringify(Object.fromEntries(Object.keys(body).sort().map(k=>[k,body[k]])))),Number(listenPort),listenHost,e=>e?reject(e):resolve());
  });
  const heartbeat=setInterval(()=>send({kind:'heartbeat'}).catch(()=>{}),100);
  const browser=await chromium.launch({executablePath,headless:true,args:args.includes('--single-process')?['--single-process']:[]});
  try {
    const context=await browser.newContext();
    const page=await context.newPage();
    page.on('pageerror',e=>check('page-error',false,e.message));
    const response=await context.request.get(new URL('/api/controller-map',url).href);
    if(!response.ok())throw new Error(`controller map HTTP ${response.status()}`);
    const expected=(await response.json()).controls;
    const settle=()=>page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    // Push the sticks off centre and both trigger bars non-zero, so every live overlay is
    // drawn as a real obstacle rather than a zero-width rect at rest.
    const drive=async()=>{
      await send({kind:'axis',action:'L_STICK_X_AXIS',value:23085}); await send({kind:'axis',action:'L_STICK_Y_AXIS',value:22863});
      await send({kind:'axis',action:'R_STICK_X_AXIS',value:32487}); await send({kind:'axis',action:'R_STICK_Y_AXIS',value:-32432});
      await send({kind:'axis',action:'L_TRIGGER_PRESSURE',value:65535}); await send({kind:'axis',action:'R_TRIGGER_PRESSURE',value:45875});
      await send({kind:'axis',action:'GYRO_PITCH',value:32767}); await send({kind:'axis',action:'GYRO_YAW',value:-32767});
      await page.waitForFunction(()=>Number(document.querySelector('[data-live-bar="r2"]').getAttribute('width'))>40,null,{timeout:5000});
      await settle();
    };
    const open=async id=>{
      await page.click(`.controller-label[data-control="${id}"]`);
      await page.waitForFunction(()=>!document.getElementById('controllerCard').hidden);
      await settle();
    };
    const all=[[1024,768],[1366,768],[1440,900],[1920,1080]];
    const viewports=mutation?[[1440,900]]:onlyViewport?all.filter(([w,h])=>`${w}x${h}`===onlyViewport):all;
    if(!viewports.length)throw new Error('no viewport matched '+onlyViewport);
    for(const [width,height] of viewports) {
      await page.setViewportSize({width,height});
      // NEVER networkidle: the Controller view holds an open EventSource and the network
      // never goes idle, so networkidle either times out or lands after an arbitrary wait.
      await page.goto(url,{waitUntil:'domcontentloaded'});
      await page.click('.tab[data-tab="editor"]');await page.click('#viewController');
      await page.waitForFunction(()=>document.querySelectorAll('.controller-label').length===23
        && document.getElementById('controllerLiveStatus').textContent==='live',null,{timeout:15000});
      await settle();
      await drive();
      const base=`${width}x${height}`;
      const drawerViewport=width===1024&&height===768;
      if(mutation)await page.evaluate(mode=>{
        const labels=[...document.querySelectorAll('.controller-label')];
        if(mode==='m1') {
          for(const selector of ['.controller-arrow','.controller-arrow-head']) {
            const attr=selector==='.controller-arrow'?'data-control-arrow':'data-control-head';
            const a=document.querySelector(`${selector}[${attr}="btn_a"]`),b=document.querySelector(`${selector}[${attr}="btn_b"]`),saved=a.getAttribute('points');
            a.setAttribute('points',b.getAttribute('points'));b.setAttribute('points',saved);
          }
        } else if(mode==='m2') {labels[1].style.left=labels[0].style.left;labels[1].style.top=labels[0].style.top;}
        else {const p=document.getElementById('controllerPicture').getBoundingClientRect(),s=document.querySelector('.statusbar').getBoundingClientRect();labels[0].style.top=`${s.top+s.height/2-p.top}px`;}
      },mutation);
      assertGeometry(`${base}.closed`,await measure(page,expected,false));
      if(out)await page.screenshot({path:path.join(out,`${base}-closed.png`)});
      if(mutation||closedOnly)break;
      // Every one of the 23 cards, at every viewport: P2 may move any control, so a crowded
      // card anywhere has to fail, not only the two controls an older loop happened to open.
      for(const c of expected) {
        await open(c.id);
        await drive();
        const shown=await page.evaluate(()=>({title:document.getElementById('controllerTitle').textContent,hidden:document.getElementById('controllerCard').hidden,rows:[...document.querySelectorAll('.controller-row')].map(e=>e.dataset.action)}));
        check(`${base}.drill.${c.id}`,!shown.hidden&&shown.title===c.label&&JSON.stringify(shown.rows)===JSON.stringify(['tap','long_press','layer_2','analog'].flatMap(k=>c.groups[k]||[])),shown);
        assertGeometry(`${base}.open-${c.id}`,await measure(page,expected,drawerViewport));
        if(out&&['btn_a','left_stick','r2'].includes(c.id))await page.screenshot({path:path.join(out,`${base}-open-${c.id}.png`)});
      }
      await page.click('#controllerClose');await settle();
    }
  } finally {
    clearInterval(heartbeat);socket.close();await browser.close();
    if(out)fs.writeFileSync(path.join(out,'geometry.json'),JSON.stringify({results,samples},null,2)+'\n');
  }
  console.log(`SUMMARY ${results.filter(r=>r.pass).length}/${results.length} PASS`);
  if(!results.length||results.some(r=>!r.pass))process.exitCode=1;
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
