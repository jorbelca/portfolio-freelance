import test from 'node:test';
import assert from 'node:assert/strict';
import {openaiExtraction} from '../src/models.js';
import {extractPrompt} from '../src/codex.js';
import {validateSettings} from '../src/domain.js';
import {readFileSync} from 'node:fs';
test('API usa modelo explícito, esquema estricto, sin persistencia y errores sin secretos',async()=>{
 const previous=process.env.OPENAI_API_KEY;process.env.OPENAI_API_KEY='test-only';
 try {
  const expected={value:'indefinido',evidence:'contrato indefinido',state:'acreditado'};
  const result=await openaiExtraction('documento','chosen-model',async(url,options)=>{
   assert.equal(url,'https://api.openai.com/v1/responses');
   const body=JSON.parse(options.body);assert.equal(body.model,'chosen-model');assert.equal(body.store,false);assert.equal(body.text.format.strict,true);assert.equal(body.tools,undefined);
   return {ok:true,json:async()=>({status:'completed',output:[{type:'message',content:[{type:'output_text',text:JSON.stringify(expected)}]}]})};
  });assert.deepEqual(result,expected);
  await assert.rejects(openaiExtraction('doc','chosen',async()=>({ok:false,status:401})),/HTTP 401/);
  await assert.rejects(openaiExtraction('doc','chosen',async()=>({ok:true,json:async()=>({status:'incomplete'})})),/no completó/);
 }finally{if(previous===undefined)delete process.env.OPENAI_API_KEY;else process.env.OPENAI_API_KEY=previous;}
});
test('rechaza motor desconocido y API sin modelo; configuración anterior compatible',async()=>{
 const settings=JSON.parse(readFileSync(new URL('../defaults.json',import.meta.url)));
 assert.equal(validateSettings(settings),settings);
 assert.throws(()=>validateSettings({...settings,provider:'otro'}),/Motor/);
 assert.throws(()=>validateSettings({...settings,provider:'openai',model:''}),/Elige/);
 assert.equal(validateSettings({...settings,provider:'openai',model:'chosen'}).provider,'openai');
 await assert.rejects(extractPrompt('p','texto',{provider:'otro'}),/Motor/);
 await assert.rejects(extractPrompt('p','texto',{provider:'openai',model:'chosen',model_timeout_seconds:121}),/Tiempo máximo/);
 await assert.rejects(extractPrompt('p','texto',{provider:'codex',model_timeout_seconds:0}),/Tiempo máximo/);
});

test('API respeta el límite temporal de la ejecución',async()=>{
 const previous=process.env.OPENAI_API_KEY;process.env.OPENAI_API_KEY='test-only';
 try {await assert.rejects(openaiExtraction('doc','chosen',async(url,options)=>{
  await new Promise(resolve=>{options.signal.addEventListener('abort',resolve,{once:true});setTimeout(resolve,50);});
  assert.equal(options.signal.aborted,true);throw new Error('tiempo verificado');
 },5),/tiempo verificado/);}
 finally{if(previous===undefined)delete process.env.OPENAI_API_KEY;else process.env.OPENAI_API_KEY=previous;}
});
