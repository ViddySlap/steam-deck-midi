// Run only against a scratch bridge: URL CHROMIUM SCRATCH_TREE OUT_DIR.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_CORE||'/Users/viddyslap/Documents/project-workspaces/life-os-showday/web-ui-server/node_modules/playwright-core');
const [url,executablePath,tree,out]=process.argv.slice(2);
assert.ok(fs.realpathSync(tree).startsWith('/private/tmp/sdfix-'),'scratch fixture tree required');
const preset=path.join(tree,'config/presets/EDM Show.json'),before=fs.readFileSync(preset),rows=[];
const check=(name,pass,detail)=>{rows.push({name,pass:Boolean(pass),detail});console.log(`${pass?'PASS':'FAIL'} ${name} ${JSON.stringify(detail)}`);assert.ok(pass,name);};
(async()=>{
  fs.mkdirSync(out,{recursive:true});
  const browser=await chromium.launch({executablePath,headless:true,args:['--single-process']});
  try {
    const page=await browser.newPage({viewport:{width:1440,height:900}});
    await page.goto(url,{waitUntil:'networkidle'});
    await page.click('.controller-label[data-control="start"]');
    await page.click('.controller-row[data-action="START"] .controller-edit');
    await page.fill('#controller_START_f_cc','79');
    await page.click('#controller_START_editor .controller-apply');
    await page.click('#btnSave');await page.waitForSelector('#conflictOverlay.open');
    const details=await page.textContent('#conflictDetails');
    check('modal-names-actions',details.includes('START')&&details.includes('SELECT'),details);
    await page.click('#btnConflictCancel');
    const marked=await page.evaluate(()=>{
      const row=document.querySelector('.controller-row[data-action="START"]'),m=row.querySelector('.controller-conflict-message');
      const r=m?.getBoundingClientRect(),hit=r&&document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
      const luminance=color=>{
        const rgb=color.match(/[\d.]+/g).slice(0,3).map(Number).map(n=>{n/=255;return n<=.04045?n/12.92:((n+.055)/1.055)**2.4;});
        return .2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2];
      };
      const fg=m?luminance(getComputedStyle(m).color):0,bg=luminance(getComputedStyle(row).backgroundColor);
      return {marked:row.classList.contains('controller-conflict'),message:m?.textContent,topmost:!!hit&&m.contains(hit),modalClosed:!document.getElementById('conflictOverlay').classList.contains('open'),contrast:(Math.max(fg,bg)+.05)/(Math.min(fg,bg)+.05)};
    });
    check('cancel-marks-visible',marked.marked&&marked.message==='MIDI CC conflict'&&marked.topmost&&marked.modalClosed,marked);
    check('message-contrast',marked.contrast>=4.5,marked.contrast);
    check('cancel-preset-identical',before.equals(fs.readFileSync(preset)),null);
    await page.screenshot({path:path.join(out,'conflict-after-cancel.png')});
    await page.click('.controller-label[data-control="select"]');
    check('other-control-still-marked',await page.locator('.controller-row[data-action="SELECT"]').evaluate(e=>e.classList.contains('controller-conflict')),null);
    await page.click('.controller-label[data-control="start"]');
    await page.click('#btnSave');await page.waitForSelector('#conflictOverlay.open');
    await page.click('#btnConflictForce');
    await page.waitForFunction(()=>!document.querySelector('.controller-conflict-message')&&document.getElementById('btnSave').disabled);
    check('successful-save-clears-mark',await page.locator('.controller-row[data-action="START"]').evaluate(e=>!e.classList.contains('controller-conflict')),null);
    const expected=JSON.parse(before);expected.sections.windows.mappings.START.cc=79;
    check('save-only-intended-edit',require('node:util').isDeepStrictEqual(JSON.parse(fs.readFileSync(preset)),expected),null);
  } finally {await browser.close();fs.writeFileSync(path.join(out,'conflict-browser.json'),JSON.stringify(rows,null,2)+'\n');}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
