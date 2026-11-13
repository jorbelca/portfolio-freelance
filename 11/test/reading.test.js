import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {readFile,readdir,rm} from 'node:fs/promises';
import pg from 'pg';
test('lectura alternativa: tarea singular, misma ficha, límite reservado y cruce de historial antes de cada petición',{skip:!process.env.DATABASE_URL,timeout:120000},async()=>{
 const admin=new pg.Client({connectionString:process.env.DATABASE_URL}),schema='test_reading_'+randomUUID().replaceAll('-','');
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
  const {startSearchRun,searchNext,runSearchStep,getSearchCandidate}=await import('../src/search.js');
  const {saveOffer}=await import('../src/store.js');const {offerInput}=await import('../src/domain.js');
  await admin.query('UPDATE search_configuration SET recover_previous=false');
  await admin.query('UPDATE workflow_control SET enabled=true');
  await admin.query('UPDATE search_settings SET history_ready=true,max_openings=1,batch_size=1,public_alternatives=true');
  await admin.query("UPDATE search_source_settings SET enabled=(source='smartrecruiters:Scalian:es')");
  const url='https://jobs.smartrecruiters.com/Scalian/123',day=new Date().toISOString().slice(0,10);
  const job={'@type':'JobPosting',title:'Developer junior',hiringOrganization:{name:'Fixture lectura'},datePosted:day,jobLocation:{address:{addressCountry:'ES'}},description:'Desarrollo de software. '.repeat(30),url};
  const calls=[];
  const deps={discoverSource:async source=>({leads:[{source,external_id:'123',company:'Fixture lectura',title:job.title,url}]}),publicGet:async target=>{calls.push(target);return {status:target.includes('api.smartrecruiters.com')?403:200,url:target,checked_at:new Date().toISOString(),text:`<script type="application/ld+json">${JSON.stringify(job)}</script>`};}};
  const start=async()=>{const id=randomUUID();runIds.push(id);await startSearchRun({id});return id;};
  const execute=async id=>{const next=await searchNext(id);assert.equal(next.continue,true);await runSearchStep(id,next.step_id,next.kind,'1',deps);return next;};
  const id=await start();await execute(id);await execute(id);await execute(id);
  assert.equal(calls.length,1);
  let candidate=(await admin.query('SELECT id FROM search_candidates WHERE run_id=$1',[id])).rows[0];
  let detail=await getSearchCandidate(candidate.id);assert.equal(detail.reads[0].http_status,403);assert.equal(detail.document.status,'incomplete');
  const alternate=await execute(id);assert.equal(alternate.kind,'read');assert.equal(calls.length,2);assert.ok(calls[1].startsWith('https://jobs.smartrecruiters.com/'));
  detail=await getSearchCandidate(candidate.id);assert.equal(detail.document.status,'complete');assert.deepEqual(detail.reads.map(row=>row.status),['incomplete','complete']);
  assert.equal((await admin.query('SELECT count(*)::int AS n FROM search_documents WHERE run_id=$1',[id])).rows[0].n,1);
  assert.ok((await searchNext(id)).kind.startsWith('extract_'));
  assert.equal((await runSearchStep(id,alternate.step_id,'read','1',deps)).status,'succeeded');assert.equal(calls.length,2);
  await admin.query("UPDATE workflow_runs SET status='failed' WHERE id=$1",[id]);
  // Una nueva candidatura entre las dos rutas debe bloquear la segunda petición.
  const second=await start();await execute(second);await execute(second);await execute(second);assert.equal(calls.length,3);
  await saveOffer(null,offerInput({company:'Fixture lectura',title:job.title,url,availability:'abierta',review_state:'guardada',application_state:'enviada'}));
  await execute(second);assert.equal(calls.length,3);
  candidate=(await admin.query('SELECT * FROM search_candidates WHERE run_id=$1',[second])).rows[0];assert.equal(candidate.stage,'excluded');assert.equal(candidate.evaluation.classification,'C');
  assert.equal((await admin.query('SELECT count(*)::int AS n FROM search_document_reads WHERE candidate_id=$1',[candidate.id])).rows[0].n,1);
 } finally {
  if(pool) await pool.end();
  await admin.query(`DROP SCHEMA IF EXISTS ${schema} CASCADE`);await admin.end();process.env.DATABASE_URL=previous;
  for(const id of runIds) await rm(new URL(`../reports/${id}/`,import.meta.url),{recursive:true,force:true});
 }
});
