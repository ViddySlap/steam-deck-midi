// Real Chromium, real loopback UDP receiver and SSE. No synthetic DOM/events.
// The bridge must be a scratch dry-run process started by check_browser.py.
const fs = require('node:fs');
const path = require('node:path');
const dgram = require('node:dgram');
const assert = require('node:assert/strict');
const [url, executablePath, ...args] = process.argv.slice(2);
const out = args[args.indexOf('--out') + 1];
const {chromium} = require(process.env.PLAYWRIGHT_CORE || '/Users/viddyslap/Documents/project-workspaces/life-os-showday/web-ui-server/node_modules/playwright-core');
const results = [];
const check = (name, actual, expected) => { results.push({name, actual, expected}); assert.deepEqual(actual, expected, name); console.log('PASS', name); };
(async () => {
  assert.equal(new URL(url).hostname, '127.0.0.1');
  assert.notEqual(new URL(url).port, '7723');
  fs.mkdirSync(out, {recursive:true});
  const browser = await chromium.launch({executablePath,headless:true,args:args.includes('--single-process')?['--single-process']:[]});
  const socket = dgram.createSocket('udp4');
  let seq = 0;
  try {
    const context = await browser.newContext({viewport:{width:1440,height:900}});
    const page = await context.newPage();
    const errors=[]; page.on('pageerror',e=>errors.push(e.message));
    const settings=await (await context.request.get(url+'/api/settings')).json();
    const [host,port]=settings.listen.split(':');
    check('loopback sender destination',host,'127.0.0.1'); assert.notEqual(Number(port),45123);
    const send = body => new Promise((resolve,reject)=>socket.send(Buffer.from(JSON.stringify({...body,seq:++seq})),Number(port),host,e=>e?reject(e):resolve()));
    const press = (action,state) => send({kind:'action',action,state});
    const axis = (action,value) => send({kind:'axis',action,value});
    const clients = async wanted => {
      for(let i=0;i<100;i++) {
        const snapshot=await (await context.request.get(url+'/api/live/snapshot')).json();
        if(snapshot.clients===wanted) { check('observed live clients',snapshot.clients,wanted); return; }
        await new Promise(r=>setTimeout(r,30));
      }
      throw new Error('live client count did not reach '+wanted);
    };
    await clients(0);
    await page.goto(url,{waitUntil:'domcontentloaded'});
    await page.waitForFunction(()=>document.getElementById('controllerLiveStatus').textContent==='live');
    await clients(1);
    check('default Controller visible',await page.locator('#controllerView').isVisible(),true);
    check('Follow default off',await page.locator('#controllerFollow').getAttribute('aria-pressed'),'false');
    await page.screenshot({path:path.join(out,'default-controller.png')});
    const lit = async (id,down) => page.waitForFunction(({id,down})=>document.querySelector(`.controller-art [data-control="${id}"]`).classList.contains('control-down')===down,{id,down});
    await press('BTN_A','down'); await lit('btn_a',true);
    check('follow off leaves card closed',await page.locator('#controllerCard').isVisible(),false);
    check('received highlight label',await page.locator('.controller-label[data-control="btn_a"]').evaluate(e=>e.classList.contains('control-down')),true);
    await press('BTN_A_LAYER_2','down');
    await page.waitForFunction(()=>document.querySelector('.controller-label[data-control="btn_a"] .controller-live-tag').textContent==='tap L2');
    await press('BTN_A','up');
    await page.waitForFunction(()=>document.querySelector('.controller-label[data-control="btn_a"] .controller-live-tag').textContent==='L2');
    await lit('btn_a',true);
    await press('BTN_A_LAYER_2','up'); await lit('btn_a',false);
    check('multi-ID hold/release',true,true);
    await page.click('.controller-label[data-control="btn_a"]');
    await page.evaluate(()=>{
      window.liveRows=[];
      window.liveRowObserver=new MutationObserver(records=>{
        for(const {target} of records) if(target.classList.contains('controller-midi-flash')) window.liveRows.push(target.dataset.action);
      });
      window.liveRowObserver.observe(document.getElementById('controllerRows'),{subtree:true,attributes:true,attributeFilter:['class']});
    });
    await press('BTN_A','down');
    await page.waitForFunction(()=>window.liveRows.includes('BTN_A'));
    check('actual MIDI flashes its exact row',await page.evaluate(()=>[...new Set(window.liveRows)]),['BTN_A']);
    await page.waitForFunction(()=>document.querySelectorAll('.controller-midi-flash').length===0);
    await press('BTN_A','up'); await lit('btn_a',false);
    await axis('L_STICK_X_AXIS',32649); await axis('L_STICK_Y_AXIS',-33202);
    await axis('L_TRIGGER_PRESSURE',65535);
    await axis('GYRO_PITCH',32767); await axis('GYRO_YAW',-32767); await axis('GYRO_ROLL',0);
    await page.waitForFunction(()=>document.querySelector('[data-live-dot="left_stick"]').getAttribute('cx')==='310'&&document.querySelector('[data-live-dot="left_stick"]').getAttribute('cy')==='205'&&document.querySelector('[data-live-bar="l2"]').getAttribute('width')==='64');
    check('real stick X/Y and trigger geometry',await page.locator('[data-live-dot="left_stick"]').evaluate(e=>[e.getAttribute('cx'),e.getAttribute('cy')]),['310','205']);
    await page.waitForFunction(()=>document.querySelector('[data-live-axis="GYRO_YAW"]').getAttribute('cx')==='601');
    check('three gyro indicators',await page.locator('[data-live-axis]').evaluateAll(es=>es.map(e=>e.getAttribute('cx'))),['643','601','622']);
    await axis('L_PAD_X_POS',32767);
    await page.waitForFunction(()=>document.querySelector('[data-live-dot="left_pad"]').style.opacity==='1');
    await page.waitForFunction(()=>getComputedStyle(document.querySelector('[data-live-dot="left_pad"]')).opacity==='0');
    check('pad arrives then visibly fades',true,true);
    await page.click('#controllerFollow');
    await press('BTN_B','down');
    await page.waitForFunction(()=>document.getElementById('controllerTitle').textContent==='B');
    check('follow opens physical B card',await page.locator('#controllerTitle').textContent(),'B');
    await page.locator('[data-action="BTN_B"] .controller-edit').click();
    await page.locator('#controller_BTN_B_f_note').fill('86');
    await page.waitForFunction(()=>!document.getElementById('controllerFollowNote').hidden);
    await press('BTN_X','down'); await lit('btn_x',true);
    check('follow preserves unsaved card',await page.locator('#controllerTitle').textContent(),'B');
    check('follow preserves actual typed field',await page.locator('#controller_BTN_B_f_note').inputValue(),'86');
    check('pause note visible',await page.locator('#controllerFollowNote').isVisible(),true);
    await page.screenshot({path:path.join(out,'live-follow-paused.png')});
    await page.click('#viewList'); await clients(0);
    await press('BTN_X','up'); await press('BTN_B','up');
    await page.click('#viewController'); await clients(1);
    await lit('btn_x',false); await lit('btn_b',false);
    check('reopen uses current snapshot',true,true);
    await page.click('.tab[data-tab="engines"]'); await clients(0);
    await page.click('.tab[data-tab="editor"]'); await clients(1);
    await page.reload({waitUntil:'domcontentloaded'});
    await page.waitForFunction(()=>document.getElementById('controllerLiveStatus').textContent==='live');
    check('follow preference remembered after reload',await page.locator('#controllerFollow').getAttribute('aria-pressed'),'true');
    await clients(1);
    check('browser JS errors',errors,[]);
    await page.close(); await clients(0);
  } finally {
    socket.close(); await browser.close();
    fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify(results,null,2)+'\n');
  }
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
