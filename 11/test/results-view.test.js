import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

test('resultados agrupa todas las páginas por clase y conserva las pistas sin clasificarlas',async()=>{
 const source=await readFile(new URL('../public/app.js',import.meta.url),'utf8');
 class Element {
  children=[];dataset={};textContent='';
  append(...items){this.children.push(...items);}
  prepend(...items){this.children.unshift(...items);}
 }
 const candidates=Array.from({length:26},(_,id)=>({id,title:`Puesto ${id}`,company:'Empresa',url:'https://example.com',source:'web',evaluation:id===25?null:{classification:['A','B','C'][id%3],computable:false}}));
 const offsets=[];
 const context=vm.createContext({document:{createElement:()=>new Element()},api:async path=>{const offset=Number(new URL(path,'https://local/').searchParams.get('offset'));offsets.push(offset);return {state:{},candidates:candidates.slice(offset,offset+25)};}});
 vm.runInContext(source.slice(source.indexOf('async function renderSearchPanel('),source.indexOf('function renderCandidateTools(')),context);
 const panel=new Element();
 await context.renderSearchPanel({id:'run'},panel,true);
 assert.deepEqual(offsets,[0,25]);
 const groups=panel.children.slice(2);
 assert.equal(groups.length,4);
 assert.deepEqual(groups.map(group=>group.children.filter(item=>item.dataset.candidateId!==undefined).length),[9,8,8,1]);
 assert.match(groups[3].children[0].textContent,/Sin clasificar/);
 assert.equal(groups[0].children[1].children[0].textContent,'Puesto 0 — Empresa');
});

test('resultados muestra CAPTCHA y errores aunque la ejecución figure completada',async()=>{
 const source=await readFile(new URL('../public/app.js',import.meta.url),'utf8');
 class Element {children=[];dataset={};textContent='';append(...items){this.children.push(...items);}prepend(...items){this.children.unshift(...items);}}
 const context=vm.createContext({document:{createElement:()=>new Element()},api:async()=>({state:{},candidates:[],diagnostics:[{kind:'discover',status:'succeeded',input:{source:'browser:google',term:'engineer'},result:{status:'captcha',reason:'Google exige reCAPTCHA'}},{kind:'read',status:'unknown',error:'Tiempo de espera agotado'}]})});
 vm.runInContext(source.slice(source.indexOf('async function renderSearchPanel('),source.indexOf('function renderCandidateTools(')),context);
 const panel=new Element();await context.renderSearchPanel({id:'run',status:'succeeded'},panel,true);
 const diagnostic=panel.children[1];
 assert.match(diagnostic.children[1].children[0].textContent,/Google.*CAPTCHA/);
 assert.equal(diagnostic.children[1].children[1].textContent,'Google exige reCAPTCHA');
 assert.equal(diagnostic.children[2].children[1].textContent,'Tiempo de espera agotado');
 assert.equal(diagnostic.children[1].className,'notice');
});
