import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {readFile,readdir,rm} from 'node:fs/promises';
import pg from 'pg';
import {finishBrowserTask,nextSearchTask} from '../test-support/browser-fixtures.js';

test('lectura browser: identidad exacta, captura persistida y revisión vacía del formulario público',{skip:!process.env.DATABASE_URL,timeout:120000},async()=>{
 const admin=new pg.Client({connectionString:process.env.DATABASE_URL}),schema='test_reading_'+randomUUID().replaceAll('-','');
 const previous=process.env.DATABASE_URL;let pool;const runId=randomUUID();
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
  await admin.query('UPDATE search_configuration SET recover_previous=false');
  await admin.query('UPDATE workflow_control SET enabled=true');
  await admin.query('UPDATE search_settings SET history_ready=true,max_openings=2,batch_size=2');
  await admin.query("UPDATE search_source_settings SET enabled=(source='browser:google')");
  await admin.query('DELETE FROM search_queries WHERE configuration_id=1');
  await admin.query("INSERT INTO search_queries(id,configuration_id,zone,language,term) VALUES($1,1,'spain','en','Developer')",[randomUUID()]);
  await search.startSearchRun({id:runId});
  let step=await search.searchNext(runId);assert.equal(step.status,'awaiting_browser');assert.equal(step.kind,'discover');
  await finishBrowserTask(search,runId,step,{candidates:[
   {title:'Developer incorrecta',company:'Fixture A',url:'https://8.8.8.8/bad'},
   {title:'Developer válida',company:'Fixture B',url:'https://8.8.8.8/good'}
  ]});
  step=await search.searchNext(runId);assert.equal(step.kind,'precheck');
  await search.runSearchStep(runId,step.step_id,step.kind,'1');
  step=await nextSearchTask(search,runId,{read:task=>task.candidate.url.endsWith('/bad')?{complete:false,page_url:'https://8.8.4.4/wrong',application_url:null}:{}});
  assert.equal(step.kind,'precheck');await search.runSearchStep(runId,step.step_id,step.kind,'2');
  step=await nextSearchTask(search,runId,{read:task=>task.candidate.url.endsWith('/bad')?{complete:false,page_url:'https://8.8.4.4/wrong',application_url:null}:{},application:task=>task.candidate.url.endsWith('/good')?{page_url:'https://1.1.1.1/public-application',identity_evidence:'Developer válida Fixture B'}:{status:'closed'}});
  assert.equal(step.continue,true);assert.equal(step.kind,'extract_company');
  const candidates=(await admin.query('SELECT id,url FROM search_candidates WHERE run_id=$1 ORDER BY url',[runId])).rows;
  const bad=candidates.find(row=>row.url.endsWith('/bad')),good=candidates.find(row=>row.url.endsWith('/good'));
  const documents=(await admin.query('SELECT candidate_id,status,source_payload FROM search_documents WHERE run_id=$1',[runId])).rows;
  assert.equal(documents.find(row=>row.candidate_id===bad.id).status,'incomplete');
  assert.equal(documents.find(row=>row.candidate_id===good.id).status,'complete');
  assert.equal(documents.find(row=>row.candidate_id===good.id).source_payload.capture_method,'browser');
  assert.deepEqual((await admin.query('SELECT format,status FROM search_document_reads WHERE candidate_id=$1',[good.id])).rows,[{format:'browser',status:'complete'}]);
  const checks=(await admin.query('SELECT candidate_id,status,page_url,form_found,required_fields,evidence FROM search_application_checks ORDER BY candidate_id')).rows;
  assert.equal(checks.find(row=>row.candidate_id===good.id).status,'accessible');
  assert.equal(checks.find(row=>row.candidate_id===good.id).form_found,true);
  assert.equal(checks.find(row=>row.candidate_id===good.id).page_url,'https://1.1.1.1/public-application');
  assert.match(checks.find(row=>row.candidate_id===good.id).evidence,/Developer válida Fixture B/);
  assert.deepEqual(checks.find(row=>row.candidate_id===good.id).required_fields,['Correo electrónico','CV']);
  assert.equal(checks.find(row=>row.candidate_id===bad.id).status,'unknown');
 } finally {
  if(pool) await pool.end();
  await admin.query(`DROP SCHEMA IF EXISTS ${schema} CASCADE`);await admin.end();process.env.DATABASE_URL=previous;
  await rm(new URL(`../reports/${runId}/`,import.meta.url),{recursive:true,force:true});
 }
});
