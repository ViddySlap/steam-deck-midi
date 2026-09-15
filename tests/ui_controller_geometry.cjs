// Real browser only. Boots no bridge and writes no preset data.
// node tests/ui_controller_geometry.cjs URL CHROMIUM [--single-process] [--out DIR] [--mutation m1|m2|m3]
const fs = require('node:fs');
const path = require('node:path');
const args = process.argv.slice(2);
const [url, executablePath] = args;
const option = flag => args.includes(flag) ? args[args.indexOf(flag) + 1] : null;
const out = option('--out'), mutation = option('--mutation');
if (!url || !executablePath || (mutation && !['m1','m2','m3'].includes(mutation))) {
  console.error('Usage: node ui_controller_geometry.cjs URL CHROMIUM [--single-process] [--out DIR] [--mutation m1|m2|m3]');
  process.exit(2);
}
const {chromium} = require(process.env.PLAYWRIGHT_CORE || '/Users/viddyslap/Documents/project-workspaces/life-os-showday/web-ui-server/node_modules/playwright-core');
const results = [], samples = [];
const check = (name, pass, detail = '') => {
  results.push({name, pass: Boolean(pass), detail});
  console.log(`${pass ? 'PASS' : 'FAIL'} ${name} ${JSON.stringify(detail)}`);
};
const rect = r => ({x:r.x, y:r.y, right:r.x+r.width, bottom:r.y+r.height});
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
function lineHitsRect(a,b,r) {
  const c=corners(r);
  return inside(a,r)||inside(b,r)||c.some((p,i)=>intersect(a,b,p,c[(i+1)%4]));
}
function polygonHitsRect(poly,r) {
  if (segments([...poly,poly[0]]).some(([a,b])=>lineHitsRect(a,b,r))) return true;
  // Rectangle wholly inside a triangle is still an intersection.
  return corners(r).some(p=>{const signs=poly.map((a,i)=>cross(a,poly[(i+1)%poly.length],p));return signs.every(s=>s>=0)||signs.every(s=>s<=0);});
}
function assertGeometry(tag,g) {
  samples.push({tag,...g});
  const ids=g.expected.map(c=>c.id).sort(), names=a=>a.map(x=>x.id).sort();
  for(const [name,items] of [['labels',g.labels],['leaders',g.leaders],['shapes',g.shapes],['arrowheads',g.heads]])
    check(`${tag}.23-${name}`, items.length===23 && JSON.stringify(names(items))===JSON.stringify(ids),names(items));
  const overlaps=[];
  for(let i=0;i<g.labels.length;i++)for(let j=i+1;j<g.labels.length;j++)if(overlap(g.labels[i].box,g.labels[j].box))overlaps.push([g.labels[i].id,g.labels[j].id]);
  check(`${tag}.label-overlaps`,overlaps.length===0,overlaps);
  const lines=g.leaders.flatMap(l=>segments(l.points).map(([a,b])=>({id:l.id,a,b}))), crossings=[];
  for(let i=0;i<lines.length;i++)for(let j=i+1;j<lines.length;j++)if(intersect(lines[i].a,lines[i].b,lines[j].a,lines[j].b,true))crossings.push([lines[i].id,lines[j].id]);
  check(`${tag}.leader-intersections`,crossings.length===0,crossings);
  for(const leader of g.leaders) {
    const shape=g.shapes.find(s=>s.id===leader.id), end=leader.points.at(-1);
    const r=shape?.box;
    const distance=r&&end ? Math.min(...segments([...corners(r),corners(r)[0]]).map(([a,b])=>{
      const t=Math.max(0,Math.min(1,((end.x-a.x)*(b.x-a.x)+(end.y-a.y)*(b.y-a.y))/((b.x-a.x)**2+(b.y-a.y)**2)));
      return Math.hypot(end.x-a.x-t*(b.x-a.x),end.y-a.y-t*(b.y-a.y));
    })) : Infinity;
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
}
async function measure(page, expected) {
  return page.evaluate(expected=>{
    const box=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom};};
    const points=e=>{
      const matrix=e.getScreenCTM(), transform=(x,y)=>{const p=new DOMPoint(x,y).matrixTransform(matrix);return {x:p.x,y:p.y};};
      if(e.tagName.toLowerCase()==='line')return [transform(e.x1.baseVal.value,e.y1.baseVal.value),transform(e.x2.baseVal.value,e.y2.baseVal.value)];
      return Array.from({length:e.points.numberOfItems},(_,i)=>{const p=e.points.getItem(i);return transform(p.x,p.y);});
    };
    const pane=box(document.getElementById('tab-editor')), status=box(document.querySelector('.statusbar')), header=box(document.querySelector('header'));
    pane.y=Math.max(pane.y,header.bottom,0);pane.bottom=Math.min(pane.bottom,status.y,innerHeight);pane.x=Math.max(pane.x,0);pane.right=Math.min(pane.right,innerWidth);
    return {expected,pane,
      labels:[...document.querySelectorAll('.controller-label')].map(e=>{const b=box(e),hit=document.elementFromPoint((b.x+b.right)/2,(b.y+b.bottom)/2);return {id:e.dataset.control,box:b,topmost:!!hit&&e.contains(hit),coveredBy:hit?.id||hit?.getAttribute('class')||hit?.tagName,scrollWidth:e.scrollWidth,clientWidth:e.clientWidth,nameHeight:e.querySelector('span').getBoundingClientRect().height};}),
      shapes:[...document.querySelectorAll('.controller-art [data-control]')].map(e=>({id:e.dataset.control,box:box(e)})),
      glyphs:[...document.querySelectorAll('.controller-art text')].map(e=>({text:e.textContent,box:box(e)})),
      leaders:[...document.querySelectorAll('.controller-arrow')].map(e=>({id:e.dataset.controlArrow,points:points(e),stroke:parseFloat(getComputedStyle(e).strokeWidth)*e.getScreenCTM().a})),
      heads:[...document.querySelectorAll('.controller-arrow-head')].map(e=>({id:e.dataset.controlHead,points:points(e)})),
      card:document.getElementById('controllerCard').hidden?null:box(document.getElementById('controllerCard')),
      scroll:[document.documentElement,document.body,document.getElementById('tab-editor'),document.querySelector('.controller-picture-scroll')].map(e=>({id:e.id||e.className||e.tagName,width:e.scrollWidth,height:e.scrollHeight,clientWidth:e.clientWidth,clientHeight:e.clientHeight,top:e.scrollTop,left:e.scrollLeft}))};
  },expected);
}
(async()=>{
  if(out)fs.mkdirSync(out,{recursive:true});
  const browser=await chromium.launch({executablePath,headless:true,args:args.includes('--single-process')?['--single-process']:[]});
  try {
    const context=await browser.newContext();
    const page=await context.newPage();
    page.on('pageerror',e=>check('page-error',false,e.message));
    const response=await context.request.get(new URL('/api/controller-map',url).href);
    if(!response.ok())throw new Error(`controller map HTTP ${response.status()}`);
    const expected=(await response.json()).controls;
    const settle=()=>page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    const open=async id=>{await page.click(`.controller-label[data-control="${id}"]`);await settle();};
    for(const [width,height] of mutation?[[1440,900]]:[[1024,768],[1366,768],[1440,900],[1920,1080]]) {
      await page.setViewportSize({width,height});
      await page.goto(url,{waitUntil:'networkidle'});
      await page.click('.tab[data-tab="editor"]');await page.click('#viewController');
      await page.waitForSelector('.controller-label');await settle();
      const base=`${width}x${height}`;
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
      assertGeometry(`${base}.closed`,await measure(page,expected));
      if(out)await page.screenshot({path:path.join(out,`${base}-closed.png`)});
      if(mutation)break;
      await open('btn_a');
      assertGeometry(`${base}.open-btn_a`,await measure(page,expected));
      if(out)await page.screenshot({path:path.join(out,`${base}-open-btn_a.png`)});
      const nearest=await page.evaluate(()=>{
        const c=document.getElementById('controllerCard').getBoundingClientRect();
        return [...document.querySelectorAll('.controller-label')].map(e=>{const b=e.getBoundingClientRect();return {id:e.dataset.control,textWidth:e.querySelector('span').getBoundingClientRect().width,d:Math.hypot(Math.max(c.left-b.right,b.left-c.right,0),Math.max(c.top-b.bottom,b.top-c.bottom,0))};}).sort((a,b)=>a.d-b.d||b.textWidth-a.textWidth||a.id.localeCompare(b.id))[0].id;
      });
      await open(nearest);assertGeometry(`${base}.open-nearest-${nearest}`,await measure(page,expected));
      for(const c of expected) {
        await open(c.id);
        const shown=await page.evaluate(()=>({title:document.getElementById('controllerTitle').textContent,hidden:document.getElementById('controllerCard').hidden,rows:[...document.querySelectorAll('.controller-row')].map(e=>e.dataset.action)}));
        check(`${base}.drill.${c.id}`,!shown.hidden&&shown.title===c.label&&JSON.stringify(shown.rows)===JSON.stringify(['tap','long_press','layer_2','analog'].flatMap(k=>c.groups[k]||[])),shown);
      }
      await page.click('#controllerClose');await settle();
    }
  } finally {await browser.close();if(out)fs.writeFileSync(path.join(out,'geometry.json'),JSON.stringify({results,samples},null,2)+'\n');}
  console.log(`SUMMARY ${results.filter(r=>r.pass).length}/${results.length} PASS`);
  if(!results.length||results.some(r=>!r.pass))process.exitCode=1;
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
