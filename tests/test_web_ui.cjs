const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

class Element {
  constructor(id='') { this.id=id; this.dataset={}; this.style={}; this.children=[]; this.listeners={}; this.value=''; this.hidden=false; this.disabled=false; this.textContent=''; this.classList={toggle(){}}; }
  addEventListener(type,fn){ this.listeners[type]=fn; }
  setAttribute(name,value){ this[name]=value; }
  removeAttribute(name){ delete this[name]; }
  replaceChildren(){ this.children=[]; }
  append(...nodes){ this.children.push(...nodes); }
  add(option){ this.children.push(option); }
}

test('interface usa chave local, mantém controles seguros e apresenta slide inicial', async () => {
  const elements=new Map(), requests=[], timers=[], gainValues=[];
  const get=id=>{if(!elements.has(id))elements.set(id,new Element(id));return elements.get(id)};
  const nav=['pet','launch','music','slides'].map(view=>{const n=new Element();n.dataset.view=view;return n});
  const views=['pet','launch','music','slides'].map(view=>new Element('view-'+view));
  const buttons=['feed','save','slides_next'].map(action=>{const n=new Element();n.dataset.action=action;n.dataset.requires=action==='feed'?'pet':'connected';return n});
  const keyButton=new Element();keyButton.dataset.key='enter';keyButton.dataset.requires='launch';
  const state={connection:{status:'connected',port:'COM3',origin:'ESP32_HW',age_ms:30},mode:'MOTION_PET',pet:{name:'Pip',stage:'CHICK',hunger:25,happiness:80,energy:85,health:95,coins:2,level:1},sensors:{distance_cm:15,valid_ultrasonic:true,ir_detected:false},gesture:null,launch:{phase:'MENU',upgrades:[]},music:{volume:.35,muted:true},slides:{current:1,total:2,items:[{title:'Primeiro',body:'Oi'},{title:'Segundo'}]},events:[]};
  const document={activeElement:null,hidden:false,getElementById:get,querySelector:()=>({content:'chave-local'}),querySelectorAll(selector){return ({'.nav':nav,'.view':views,'[data-action]':buttons,'[data-key]':[keyButton],'[data-requires]':[...buttons,keyButton]})[selector]||[]},createElement:()=>new Element(),addEventListener(){}};
  const fetch=async(path,options)=>{requests.push({path,options});return {ok:true,json:async()=>path==='/api/ports'?{ports:[{device:'COM3',description:'ESP32'}]}:path==='/api/state'?state:{ok:true,state}}};
  const Audio=class { constructor(){this.currentTime=0;this.destination={}} createOscillator(){return {frequency:{setTargetAtTime(){}},connect(){},start(){}}} createGain(){return {gain:{value:0,setTargetAtTime(value){gainValues.push(value)}},connect(){}}} async resume(){} };
  const context={document,window:{AudioContext:Audio},fetch,Option:class{constructor(text,value){this.text=text;this.value=value}},setTimeout:fn=>{timers.push(fn);return timers.length},clearTimeout(){},console};
  vm.runInNewContext(fs.readFileSync('terminal/web/static/app.js','utf8'),context);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(get('slide-title').textContent,'Primeiro');assert.equal(get('slide-count').textContent,'1 / 2');
  assert.equal(get('distance').textContent,'15,0 cm');assert.equal(get('ir').textContent,'Livre');assert.equal(buttons[0].disabled,false);
  assert.equal(get('hunger-value').textContent,'75%');assert.equal(get('hunger-bar').style.width,'75%');
  assert.ok(requests.every(r=>r.options.headers['X-MotionPet-Key']==='chave-local'));
  buttons[0].listeners.click();await new Promise(resolve=>setImmediate(resolve));
  const sent=requests.find(r=>r.path==='/api/action');assert.equal(JSON.parse(sent.options.body).action,'feed');
  nav[2].listeners.click();await new Promise(resolve=>setImmediate(resolve)); state.music={note:'A4',frequency_hz:440,volume:.35,muted:false}; await get('enable-audio').listeners.click(); assert.ok(gainValues.at(-1)>0);
  state.sensors.valid_ultrasonic=false;timers.at(-1)();await new Promise(resolve=>setImmediate(resolve));assert.equal(gainValues.at(-1),0);
  state.sensors.valid_ultrasonic=true;document.hidden=true;timers.at(-1)();await new Promise(resolve=>setImmediate(resolve));assert.equal(gainValues.at(-1),0);
  document.hidden=false;state.connection.age_ms=2001;timers.at(-1)();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(buttons[0].disabled,true);assert.equal(get('connection-label').textContent,'Sem leituras');
});
