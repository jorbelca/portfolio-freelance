import test from 'node:test';
import assert from 'node:assert/strict';
import {checkOffersBatch} from '../src/store.js';

test('consulta todo el lote una vez, normaliza y conserva orden y duplicados',async()=>{
  const urls=['https://es.linkedin.com/jobs/view/dev-123?utm_source=test','https://example.test/job?id=2#top','https://es.linkedin.com/jobs/view/dev-123?utm_source=test'];
  let calls=0;
  const result=await checkOffersBatch({urls},{query:async(sql,params)=>{
    calls++;
    assert.match(sql,/JOIN applications/);
    assert.deepEqual(params,[['https://es.linkedin.com/jobs/view/dev-123','https://example.test/job?id=2','https://es.linkedin.com/jobs/view/dev-123'],['linkedin:123',null,'linkedin:123']]);
    return {rows:[{applied:true},{applied:false},{applied:true}]};
  }});
  assert.equal(calls,1);
  assert.deepEqual(result,{results:urls.map((url,index)=>({url,applied:index!==1}))});
});

test('rechaza entradas inválidas antes de consultar y propaga fallos sin devolver false',async()=>{
  const client={query:()=>{throw new Error('No debe consultarse');}};
  for(const raw of [null,[],{}, {urls:[]},{urls:Array(101).fill('https://example.test')},{urls:['']},{urls:[null]},{urls:['javascript:alert(1)']},{urls:['https://user:secret@example.test']},{urls:['https://example.test'],company:'x'}]) {
    await assert.rejects(checkOffersBatch(raw,client));
  }
  await assert.rejects(checkOffersBatch({urls:['https://example.test/job']},{query:async()=>{throw new Error('DB unavailable');}}),/DB unavailable/);
});
