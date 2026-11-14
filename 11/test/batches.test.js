import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {readFile,readdir,rm} from 'node:fs/promises';
import pg from 'pg';
import {nextSearchTask} from '../test-support/browser-fixtures.js';

test('los lotes cuentan fichas incompletas y completas antes de abrir la siguiente',{skip:!process.env.DATABASE_URL,timeout:180000},async()=>{
 const admin=new pg.Client({connectionString:process.env.DATABASE_URL}),schema='test_batches_'+randomUUID().replaceAll('-','');
 const previous=process.env.DATABASE_URL;let pool;const runIds=[];
 await admin.connect();
 try {
  await admin.query(`CREATE SCHEMA ${schema}`);await admin.query(`SET search_path TO ${schema}`);
  for(const file of (await readdir(new URL('../sql/',import.meta.url))).filter(file=>/^\d+\.sql$/.test(file)).sort()) {
   await admin.query((await readFile(new URL(`../sql/${file}`,import.meta.url),'utf8')).replace(/^BEGIN;\s*/i,'').replace(/COMMIT;\s*$/i,''));
   if(file==='001.sql') await admin.query('INSERT INTO settings(id,value) VALUES(1,$1)',[JSON.parse(await readFile(new URL('../defaults.json',import.meta.url),'utf8'))]);
  }
  const scoped=new URL(previous);scoped.searchParams.set('options',`-c search_path=${schema}`);process.env.DATABASE_URL=scoped.href;
  ({pool}=await import('../src/db.js'));
  const search=await import('../src/search.js');
  await admin.query('UPDATE workflow_control SET enabled=true');
  await admin.query('UPDATE search_settings SET history_ready=true');
  await admin.query("UPDATE search_source_settings SET enabled=(source='browser:google')");
  await admin.query('DELETE FROM search_queries WHERE configuration_id=1');
  await admin.query("INSERT INTO search_queries(id,configuration_id,zone,language,term) VALUES($1,1,'spain','en','Developer')",[randomUUID()]);
  for(const {total,batch,mixed} of [{total:6,batch:5,mixed:false},{total:2,batch:2,mixed:true}]) {
   await admin.query('UPDATE search_settings SET max_openings=$1,batch_size=$2',[total,batch]);
   const id=randomUUID();runIds.push(id);await search.startSearchRun({id});
   const candidates=Array.from({length:total},(_,index)=>({title:`Developer ${index}`,company:`Fixture lote ${index}`,url:`https://8.8.8.8/${mixed?'mixed':'incomplete'}/${index}`}));
   let reads=0,seenBatch=false;
   for(let count=0;count<100;count++) {
    const next=await nextSearchTask(search,id,{
     candidates,
     read:task=>{
      reads++;
      const index=Number(task.candidate.url.split('/').at(-1));
      return mixed && index===0?{}:{complete:false,application_url:null,visible_text:'Página sin una ficha verificable.'};
     },
     application:()=>({status:'closed',form_found:false,evidence:'La página indica que la vacante está cerrada.'})
    });
    if(!next.continue) break;
    if(next.kind==='batch') {assert.equal(reads,batch);assert.equal(seenBatch,false);seenBatch=true;}
    assert.equal((await search.runSearchStep(id,next.step_id,next.kind,'1',{extractField:async()=>{assert.fail('No se llama al modelo en fichas incompletas ni en la cerrada.');}})).status,'succeeded',next.kind);
    if(next.kind==='batch') {
     const run=(await admin.query('SELECT status,result FROM workflow_runs WHERE id=$1',[id])).rows[0];
     assert.equal(run.status,'running');assert.equal(run.result.openings,batch);
     const register=JSON.parse(await readFile(new URL(`../reports/${id}/registro.json`,import.meta.url),'utf8'));
     assert.equal(register.report.openings,batch);assert.equal(register.report.final,false);
     assert.equal(register.report.summary.classes.C,mixed?1:0);
    }
    if(count===99) assert.fail('Bucle de lotes no acotado');
   }
   assert.equal(seenBatch,true);assert.equal(reads,total);
   const run=(await admin.query('SELECT status,result FROM workflow_runs WHERE id=$1',[id])).rows[0];
   assert.equal(run.status,'succeeded');assert.equal(run.result.openings,total);
   const results=await search.getSearchResults(id);assert.equal(results.state.report_files_error,null);assert.equal(results.state.report_files_revision,results.state.report_revision);
   assert.equal((await admin.query("SELECT count(*)::int AS n FROM search_steps WHERE run_id=$1 AND kind='batch'",[id])).rows[0].n,1);
  }
 } finally {
  if(pool) await pool.end();
  await admin.query(`DROP SCHEMA IF EXISTS ${schema} CASCADE`);await admin.end();process.env.DATABASE_URL=previous;
  for(const id of runIds) await rm(new URL(`../reports/${id}/`,import.meta.url),{recursive:true,force:true});
 }
});
