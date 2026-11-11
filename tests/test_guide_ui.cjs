// Contrato dos controles do guia em DOM simulado; nao substitui inspecao no navegador.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const page = fs.readFileSync(path.join(__dirname, '../hardware/guia_montagem_final.html'), 'utf8');
const script = page.match(/<script>([\s\S]*?)<\/script>/)[1];
const slides = JSON.parse(script.match(/const slides=(\[.*?\]);\n/)[1]);
const settle = () => new Promise(setImmediate);

async function ui(connected = true, storage = new Map(), hash = '') {
  const nodes = new Map(), requests = [], items = [...page.matchAll(/data-item="([^"]+)"/g)]
    .map(m => ({dataset:{item:m[1]}, style:{}, classList:{toggle(){}}}));
  const el = id => {
    if (!nodes.has(id)) nodes.set(id, {id, value:'', checked:false, hidden:false, disabled:false,
      style:{}, options:[], textContent:'', appendChild(n){this.options.push(n);if(!this.value)this.value=n.value;},
      replaceChildren(){this.options=[];this.value='';}});
    return nodes.get(id);
  };
  const sandbox = {
    document: {getElementById:el, createElement:()=>({}), querySelector:s=>s.startsWith('meta')
      ? connected ? {content:'test-local-key'} : null : {requestFullscreen(){}},
      querySelectorAll:()=>items, addEventListener(){}},
    location:{protocol:connected?'http:':'file:',hash}, history:{replaceState(){}},
    localStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},
    fetch:async (url, options={}) => {
      requests.push({url, options});
      if (url === '/api/ports') return {ok:true,json:async()=>({ports:[
        {device:'COM7',description:'ESP32'},{device:'COM8',description:'Outra placa'}]})};
      const body = JSON.parse(options.body);
      const passed = body.measurements.supply_3v3 !== null && body.confirmations.wiring && body.confirmations.lcd_visual;
      return {ok:true,json:async()=>({status:passed?'passed':'pending',summary:passed?'Conferencias fornecidas':'Quadro recebido; falta conferencia',
        problems:[],next_action:'Desconecte USB antes de instalar.',details:{port:body.port,
          device_lcd_20x4:['LCD'.padEnd(20), 'linha 2'.padEnd(20), 'linha 3'.padEnd(20),'linha 4'.padEnd(20)]}})};
    }
  };
  vm.runInNewContext(script, sandbox, {timeout:1000});
  await settle();
  return {el,requests,items,jump(component){
    const index = slides.findIndex(s=>s.test_component===component);
    assert.ok(index>=0);el('jump').onchange({target:{value:String(index)}});
  }};
}

test('arquivo local mostra como ativar testes e nao acessa USB automaticamente', async()=>{
  const x=await ui(false);x.jump('esp32');
  assert.equal(x.el('startup').hidden,false);
  assert.equal(x.el('run-test').disabled,true);
  assert.equal(x.requests.length,0);
});

test('navega todos os passos e preserva ECHO desconectado durante ensaio', async()=>{
  const x=await ui(false);
  assert.equal(x.el('jump').options.length,23);
  for(let n=1;n<slides.length;n++)x.el('next').onclick();
  assert.equal(x.el('next').disabled,true);
  assert.equal(x.el('title').textContent,'Confira os três funcionando juntos');
  const index=slides.findIndex(s=>s.title==='Confira o divisor antes do ECHO');
  x.el('jump').onchange({target:{value:String(index)}});
  assert.equal(x.items.find(i=>i.dataset.item==='F9').style.display,'none');
  x.el('all').checked=true;x.el('all').onchange();
  assert.ok(x.items.every(i=>i.style.display===''));
});

test('botao envia porta, medidas e confirmacoes sem modo simulado ou gravação', async()=>{
  const x=await ui();x.jump('lcd');
  x.el('supply').value='3.31';x.el('confirm-wiring').checked=true;x.el('confirm-visual').checked=true;
  await x.el('run-test').onclick();
  const request=x.requests.find(r=>r.url==='/api/test');
  assert.equal(request.options.method,'POST');
  assert.equal(request.options.headers['X-MotionPet-Key'],'test-local-key');
  assert.deepEqual(JSON.parse(request.options.body),{component:'lcd',port:'COM7',
    measurements:{supply_3v3:3.31,echo_v:null,reference_cm:null},confirmations:{wiring:true,lcd_visual:true}});
  assert.equal(x.el('test-result').className,'result passed');
  assert.match(x.el('test-result').textContent,/Porta testada: COM7/);
  assert.equal(x.el('received-frame').hidden,false);
});

test('sem medições permanece pendente e mostra quadro para comparação física', async()=>{
  const x=await ui();x.jump('lcd');await x.el('run-test').onclick();
  assert.equal(x.el('test-result').className,'result pending');
  assert.equal(x.el('received-frame').hidden,false);
});

test('troca de porta, medidas e confirmações invalida aprovação anterior', async()=>{
  const x=await ui();x.jump('lcd');
  async function pass(){x.el('supply').value='3.3';x.el('confirm-wiring').checked=true;
    x.el('confirm-visual').checked=true;await x.el('run-test').onclick();assert.equal(x.el('test-result').hidden,false);}
  await pass();x.el('port').value='COM8';x.el('port').onchange();
  assert.equal(x.el('test-result').hidden,true);assert.equal(x.el('supply').value,'');
  assert.equal(x.el('confirm-visual').checked,false);
  await pass();x.el('supply').value='3.2';x.el('supply').oninput();
  assert.equal(x.el('test-result').hidden,true);
  await pass();x.el('confirm-visual').checked=false;x.el('confirm-visual').onchange();
  assert.equal(x.el('test-result').hidden,true);
});

test('IR pede nova medição e voltar ao LCD exige nova captura', async()=>{
  const x=await ui();x.jump('lcd');x.el('supply').value='3.3';
  x.el('confirm-wiring').checked=true;x.el('confirm-visual').checked=true;
  await x.el('run-test').onclick();x.jump('ir');
  assert.equal(x.el('supply').value,'');assert.equal(x.el('test-result').hidden,true);
  assert.equal(x.el('visual-row').hidden,true);assert.equal(x.el('echo-row').hidden,true);
  x.jump('lcd');assert.equal(x.el('test-result').hidden,true);
  x.jump('hcsr04');assert.equal(x.el('echo-row').hidden,false);
  assert.equal(x.el('reference-row').hidden,false);assert.equal(x.el('supply-row').hidden,true);
});

test('diagnóstico bloqueia captura e navegação até declarar retorno aos fios de 3,3 V', async()=>{
  const x=await ui();x.jump('lcd');
  x.el('diagnostic-open').onclick();
  assert.equal(x.el('diagnostic-panel').hidden,false);
  assert.equal(x.el('normal-diagram').hidden,true);
  assert.equal(x.el('diagnostic-diagram').hidden,false);
  assert.equal(x.el('testbox').hidden,true);
  assert.equal(x.el('run-test').disabled,true);
  assert.equal(x.el('jump').disabled,true);
  x.jump('ir');assert.equal(x.el('title').textContent,'Diagnóstico: iluminação do LCD em 5 V');
  await x.el('refresh-ports').onclick();
  assert.equal(x.el('run-test').disabled,true);
  await x.el('run-test').onclick();
  assert.equal(x.requests.filter(r=>r.url==='/api/test').length,0);
  x.el('diagnostic-close').onclick();assert.equal(x.el('diagnostic-panel').hidden,false);
  x.el('diagnostic-restored').checked=true;x.el('diagnostic-restored').onchange();
  assert.equal(x.el('diagnostic-close').disabled,false);
  x.el('diagnostic-close').onclick();
  assert.equal(x.el('diagnostic-panel').hidden,true);
  assert.equal(x.el('normal-diagram').hidden,false);
  assert.equal(x.el('testbox').hidden,false);
  assert.equal(x.el('title').textContent,'Teste o LCD antes de continuar');
  assert.equal(x.el('supply').value,'');
  assert.equal(x.el('confirm-visual').checked,false);
});

test('recarregar página preserva aviso de diagnóstico pendente de restauração', async()=>{
  const storage=new Map();const first=await ui(true,storage);first.jump('lcd');first.el('diagnostic-open').onclick();
  assert.equal(storage.get('motionpet_lcd_light_only_5v'),'1');
  const reloaded=await ui(true,storage);
  assert.equal(reloaded.el('diagnostic-panel').hidden,false);
  assert.equal(reloaded.el('run-test').disabled,true);
  reloaded.el('diagnostic-restored').checked=true;reloaded.el('diagnostic-restored').onchange();reloaded.el('diagnostic-close').onclick();
  assert.equal(storage.has('motionpet_lcd_light_only_5v'),false);
});

test('link de luz piscando abre direto a ligação temporária e bloqueia o teste I2C', async()=>{
  const x=await ui(true,new Map(),'#lcd-power');
  assert.equal(x.el('title').textContent,'Diagnóstico: iluminação do LCD em 5 V');
  assert.equal(x.el('diagnostic-panel').hidden,false);
  assert.equal(x.el('testbox').hidden,true);
  assert.equal(x.el('run-test').disabled,true);
  await x.el('run-test').onclick();
  assert.equal(x.requests.filter(r=>r.url==='/api/test').length,0);
});
