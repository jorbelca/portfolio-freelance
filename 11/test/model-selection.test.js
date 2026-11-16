import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
test('cargar ajustes conserva el modelo guardado al mostrar y guardar el formulario',async()=>{
 const source=await readFile(new URL('../public/app.js',import.meta.url),'utf8');
 const body=source.slice(source.indexOf('function showSettings()'),source.indexOf("$('#settings-form').onsubmit"));
 const fields=new Map();const field=key=>{if(!fields.has(key)) fields.set(key,{value:'',textContent:''});return fields.get(key);};let selected;
 vm.runInNewContext(body+';showSettings();',{settingsFields:['reasoning_effort'],settings:{revision:12,value:{reasoning_effort:'max',provider:'codex',model:'gpt-6-luna'}},modelChoices:{},$:field,document:{body:{dataset:{}}},showModels:()=>{selected=field('#cfg-model').value;}});
 assert.equal(field('#cfg-reasoning_effort').value,'max');assert.equal(selected,'gpt-6-luna');assert.equal(field('#cfg-provider').value,'codex');
});
test('el esfuerzo se guarda aparte y rechaza valores no admitidos',async()=>{
 const {validateSettings}=await import('../src/domain.js');
 const settings=JSON.parse(await readFile(new URL('../defaults.json',import.meta.url),'utf8'));
 assert.equal(validateSettings({...settings,reasoning_effort:'low'}).reasoning_effort,'low');
 assert.throws(()=>validateSettings({...settings,reasoning_effort:'inventado'}),/razonamiento/);
 const {codexJson}=await import('../src/codex.js');
 await assert.rejects(codexJson('texto',{}, {reasoning_effort:'inventado'}),/razonamiento/);
 const {captureTask}=await import('../src/browser-capture.js');let effort;
 await captureTask({kind:'read',url:'https://example.com'},{reasoning_effort:'high',visit:async()=>({page_url:'https://example.com',text:'Página general',html:'',links:[]}),analyze:async(prompt,schema,options)=>{effort=options.reasoning_effort;return {readable:false,application_url:null};}});
 assert.equal(effort,'high');
});
