// Execute the shipped editor script with controlled HTTP timing and a small DOM.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(process.argv[2] || 'windows/static/index.html', 'utf8');
const source = html.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/\nloadAll\(\);\s*$/, '');
const elements = new Map();
const timers = [];
function element() {
  return {textContent:'', innerHTML:'', value:'', hidden:true, children:[], listeners:{},
    classList:{toggle(){},add(){},remove(){}},
    addEventListener(name, handler){this.listeners[name]=handler;},
    replaceChildren(){this.children=[];}, appendChild(child){this.children.push(child);},
    querySelectorAll(){return [];},
  };
}
const document = {
  getElementById(id){if(!elements.has(id)) elements.set(id,element());return elements.get(id);},
  createElement:element, querySelectorAll(){return [];}, addEventListener(){},
};
const context = vm.createContext({assert, document, window:{confirm:()=>false},
  setInterval(fn,ms){timers.push({fn,ms});}, setTimeout(){}});
vm.runInContext(source, context);
assert.equal(timers.length, 1);
assert.equal(timers[0].ms, 2000);
vm.runInContext(`
  renderSidebar = renderSettingsGrids = renderPresetDropdown = renderMacroLibrary = () => {};
  let renderedNote;
  renderEditor = () => {renderedNote=state.BTN_A.note;};
  toast = () => {};
  selected = 'BTN_A';
  let version=0, note=36, engine=true, failure=false, blockMappings=null, removedSection=false, blockReload=null;
  let calls=[];
  apiFetch=async(path,opts={})=>{
    calls.push({path,opts});
    if(failure) throw new Error('offline');
    if(path==='/api/state-version') return version;
    if(path.startsWith('/api/mappings')) {
      if(blockMappings) await blockMappings;
      if(removedSection && path.includes('?')) throw Object.assign(new Error('section gone'), {httpStatus:422});
      return {section:'windows',bridge_section:'macbook',sections:['macbook','windows'],legacy:false,
        preset:'Show.json',mappings:{BTN_A:{type:'note',channel:0,note}},engines:{rec:engine}};
    }
    if(path==='/api/engines') return {engines:[{type:'rec',name:'Recorder',active:true}]};
    if(path==='/api/actions') return {actions:['BTN_A']};
    if(path==='/api/reload') {if(blockReload) await blockReload; return {ok:true};}
    return {};
  };
`,context);
(async()=>{
  await vm.runInContext(`(async()=>{
    assert.equal(await loadAll(),true);
    assert.equal(stateVersion,0);
    assert.equal(renderedNote,36);
    version=1; note=50; engine=false;
    await pollStateVersion();
    assert.equal(state.BTN_A.note,50);
    assert.equal(renderedNote,50);
    assert.equal(engineStates.rec,false);
    assert.ok(document.getElementById('enginesList').innerHTML.includes('data-type="rec"'));
    assert.ok(!document.getElementById('enginesList').innerHTML.includes(' checked'));
    assert.equal(selected,'BTN_A');
    assert.equal(selectedSection,'windows');
    assert.equal(calls.findLast(x=>x.path.startsWith('/api/mappings')).path,'/api/mappings?section=windows');
    assert.equal(stateVersion,1);
    const count=calls.filter(x=>x.path.startsWith('/api/mappings')).length;
    await pollStateVersion();
    assert.equal(calls.filter(x=>x.path.startsWith('/api/mappings')).length,count);

    setDirty(true); state.BTN_A.note=99; engineStates.rec=true;
    version=2; note=70;
    await pollStateVersion();
    assert.equal(state.BTN_A.note,99);
    assert.equal(engineStates.rec,true);
    assert.equal(dirty,true);
    assert.equal(stateVersion,1);
    assert.equal(document.getElementById('presetChangeNotice').hidden,false);
    const before=calls.length;
    await document.getElementById('btnReloadPreset').listeners.click();
    assert.equal(calls.length,before);
    assert.equal(state.BTN_A.note,99);
    window.confirm=()=>true;
    await document.getElementById('btnReloadPreset').listeners.click();
    assert.equal(calls.findLast(x=>x.path==='/api/reload').opts.method,'POST');
    assert.equal(state.BTN_A.note,70);
    assert.equal(dirty,false);
    assert.equal(document.getElementById('presetChangeNotice').hidden,true);

    // Editing after a clean poll starts must survive its HTTP responses.
    version=3; note=80;
    let release;
    blockMappings=new Promise(resolve=>{release=resolve;});
    const pending=pollStateVersion();
    for(let i=0;i<8;i++) await Promise.resolve();
    setDirty(true); state.BTN_A.note=101;
    release(); await pending; blockMappings=null;
    assert.equal(state.BTN_A.note,101);
    assert.equal(dirty,true);
    assert.equal(stateVersion,2);
    assert.equal(document.getElementById('presetChangeNotice').hidden,false);

    // Unapplied fields/JSON must also defer refresh without changing Apply.
    setDirty(false);
    document.getElementById('editorContent').listeners.input();
    assert.equal(formDirty,true);
    await pollStateVersion();
    assert.equal(state.BTN_A.note,101);
    assert.equal(stateVersion,2);
    assert.equal(document.getElementById('presetChangeNotice').hidden,false);
    formDirty=false;
    document.getElementById('ms_update_hz').value='45';
    document.getElementById('macroGrid').listeners.input();
    assert.equal(dirty,true);
    assert.equal(macroSettings.update_hz,45);
    await pollStateVersion();
    assert.equal(macroSettings.update_hz,45);
    assert.equal(stateVersion,2);

    // A failed refresh does not acknowledge the unseen version; retry works.
    setDirty(false); failure=true;
    await pollStateVersion();
    assert.equal(stateVersion,2);
    assert.equal(state.BTN_A.note,101);
    failure=false;
    await pollStateVersion();
    assert.equal(state.BTN_A.note,80);
    assert.equal(stateVersion,3);
    assert.equal(document.getElementById('presetChangeNotice').hidden,true);
    removedSection=true; version=4; note=85;
    await pollStateVersion();
    assert.equal(state.BTN_A.note,85);
    assert.equal(calls.findLast(x=>x.path.startsWith('/api/mappings')).path,'/api/mappings');
    removedSection=false;
    // Confirmation covers the current draft, not later edits during POST.
    let finishReload;
    blockReload=new Promise(resolve=>{finishReload=resolve;});
    const reloadRequest=document.getElementById('btnReloadPreset').listeners.click();
    await Promise.resolve();
    setDirty(true); state.BTN_A.note=104;
    finishReload(); await reloadRequest; blockReload=null;
    assert.equal(state.BTN_A.note,104);
    assert.equal(dirty,true);
    assert.equal(document.getElementById('presetChangeNotice').hidden,false);
    await document.getElementById('btnReloadPreset').listeners.click();
    assert.equal(state.BTN_A.note,85);
    assert.equal(dirty,false);
  })()`,context);
  // The registered timer itself must invoke the poll, not an unrelated callback.
  vm.runInContext('version=5; note=90;', context);
  await timers[0].fn();
  assert.equal(vm.runInContext('state.BTN_A.note',context),90);
  console.log('UI reload behavior: PASS (timer, clean editor/engines, dirty notice, explicit reload, in-flight edits, retry)');
})().catch(error=>{console.error(error);process.exitCode=1;});
