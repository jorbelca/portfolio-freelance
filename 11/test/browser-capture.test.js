import test from 'node:test';
import assert from 'node:assert/strict';
import {captureTask,observedUrl} from '../src/browser-capture.js';
const page=(page_url,text='Vacante de desarrollo')=>({page_url,text,html:'<p>Vacante</p>',links:[],form_count:1,fields:[]});
const task={kind:'discover',url:'https://www.google.com/search?q=developer',max_pages:2};
test('recorre solo paginación visible y conserva candidatos observados',async()=>{
 const next='https://www.google.com/search?q=developer&start=10',job='https://example.com/jobs/1';let calls=0;
 const result=await captureTask(task,{visit:async url=>({...page(url),links:[{url:next},{url:job}]}),analyze:async()=>({status:'ok',reason:'',next_url:calls++?null:next,candidates:[{title:'Developer',company:'Empresa',url:job,location:'Madrid',publication:null}]})});
 assert.equal(calls,2);assert.deepEqual(result.page_urls,[task.url,next]);assert.equal(result.truncated,false);assert.equal(result.candidates[0].publication,undefined);
});
test('rechaza enlaces inventados y paginación externa',async()=>{
 assert.throws(()=>observedUrl('https://example.com',page(task.url)),/no aparece/);
 await assert.rejects(captureTask(task,{visit:async url=>({...page(url),links:[{url:'https://example.com/search'}]}),analyze:async()=>({status:'ok',reason:'',next_url:'https://example.com/search',candidates:[]})}),/salió del buscador/);
});
test('un desafío detiene la fuente sin gastar cuota',async()=>{
 const result=await captureTask(task,{visit:async url=>({...page(url,'reCAPTCHA'),challenge:'captcha'}),analyze:async()=>assert.fail('No debe llamar al modelo')});
 assert.equal(result.status,'captcha');assert.deepEqual(result.candidates,[]);assert.equal(result.truncated,false);
});
test('un bloqueo no se convierte en ficha aunque el modelo se equivoque',async()=>{
 const result=await captureTask({...task,kind:'read'},{visit:async url=>({...page(url),challenge:'blocked'}),analyze:async()=>({readable:true,application_url:null})});
 assert.equal(result.html,'');assert.equal(result.visible_text,'');
});
test('la inspección exige evidencia literal',async()=>{
 await assert.rejects(captureTask({...task,kind:'browser_apply'},{visit:async url=>page(url),analyze:async()=>({status:'accessible',form_found:true,required_fields:[],evidence:'inventado',identity_evidence:'',reason:''})}),/evidencia/);
});
test('un fallo de cuota no se convierte en búsqueda vacía',async()=>{
 await assert.rejects(captureTask(task,{visit:async url=>page(url),analyze:async()=>{throw new Error('Cuota agotada');}}),/Cuota agotada/);
});
