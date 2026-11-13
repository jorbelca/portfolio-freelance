import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {readFile,readdir,rm} from 'node:fs/promises';
import pg from 'pg';
test('los lotes cuentan fichas incompletas y evaluadas antes de abrir la siguiente',{skip:!process.env.DATABASE_URL,timeout:180000},async()=>{
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
  const {startSearchRun,searchNext,runSearchStep,getSearchResults}=await import('../src/search.js');
  await admin.query('UPDATE workflow_control SET enabled=true');
  await admin.query('UPDATE search_settings SET history_ready=true,public_alternatives=false');
  await admin.query("UPDATE search_source_settings SET enabled=(source='arbeitnow')");
  for(const {total,batch,mixed} of [{total:6,batch:5,mixed:false},{total:2,batch:2,mixed:true}]) {
   await admin.query('UPDATE search_settings SET max_openings=$1,batch_size=$2',[total,batch]);
   const id=randomUUID();runIds.push(id);await startSearchRun({id});
   const leads=Array.from({length:total},(_,index)=>({source:'arbeitnow',external_id:String(index),company:`Fixture lote ${index}`,title:`Developer ${index}`,url:`https://jobs.example.test/${mixed?'mixed':'incomplete'}/${index}`}));
   let reads=0,seenBatch=false;
   const deps={discoverSource:async()=>({leads}),publicGet:async url=>{
    reads++;
    if(mixed && url.endsWith('/0')) {
     const job={'@type':'JobPosting',title:'Developer 0',hiringOrganization:{name:'Fixture lote 0'},datePosted:'2000-01-01',jobLocation:{address:{addressCountry:'ES'}},description:'Desarrollo de software. '.repeat(20)};
     return {status:200,url,checked_at:new Date().toISOString(),text:`<script type="application/ld+json">${JSON.stringify(job)}</script>`};
    }
    if(url.endsWith('/1')) throw new Error('Fallo de lectura aislado');
    return {status:403,url,checked_at:new Date().toISOString(),text:'Acceso no verificable'};
   },extractField:async()=>{assert.fail('Una ficha incompleta o ya excluida no debe llamar al modelo');}};
   for(let count=0;count<40;count++) {
    const next=await searchNext(id);if(!next.continue) break;
    if(next.kind==='batch') {assert.equal(reads,batch);assert.equal(seenBatch,false);seenBatch=true;}
    assert.equal((await runSearchStep(id,next.step_id,next.kind,'1',deps)).status,'succeeded');
    if(next.kind==='batch') {
     const run=(await admin.query('SELECT status,result FROM workflow_runs WHERE id=$1',[id])).rows[0];
     assert.equal(run.status,'running');assert.equal(run.result.openings,batch);
     const register=JSON.parse(await readFile(new URL(`../reports/${id}/registro.json`,import.meta.url),'utf8'));
     assert.equal(register.report.openings,batch);assert.equal(register.report.final,false);
     assert.equal(register.report.summary.classes.C,mixed?1:0);
    }
   }
   assert.equal(seenBatch,true);assert.equal(reads,total);
   const run=(await admin.query('SELECT status,result FROM workflow_runs WHERE id=$1',[id])).rows[0];
   assert.equal(run.status,'succeeded');assert.equal(run.result.openings,total);
   const results=await getSearchResults(id);assert.equal(results.state.report_files_error,null);assert.equal(results.state.report_files_revision,results.state.report_revision);
   assert.equal((await admin.query("SELECT count(*)::int AS n FROM search_steps WHERE run_id=$1 AND kind='batch'",[id])).rows[0].n,1);
  }
 } finally {
  if(pool) await pool.end();
  await admin.query(`DROP SCHEMA IF EXISTS ${schema} CASCADE`);await admin.end();process.env.DATABASE_URL=previous;
  for(const id of runIds) await rm(new URL(`../reports/${id}/`,import.meta.url),{recursive:true,force:true});
 }
});
