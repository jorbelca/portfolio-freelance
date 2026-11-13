import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {readFile,readdir,rm} from 'node:fs/promises';
import pg from 'pg';
test('búsqueda persistente: historial antes de abrir, cupo reservado, tareas singulares, pausa/reanudación e informe',{skip:!process.env.DATABASE_URL,timeout:180000},async()=>{
 const admin=new pg.Client({connectionString:process.env.DATABASE_URL}),schema='test_search_'+randomUUID().replaceAll('-','');
 const previous=process.env.DATABASE_URL;let pool,runId,secondRunId;
 await admin.connect();
 try {
  await admin.query(`CREATE SCHEMA ${schema}`);await admin.query(`SET search_path TO ${schema}`);
  for(const file of (await readdir(new URL('../sql/',import.meta.url))).filter(file=>/^\d+\.sql$/.test(file)).sort()) {
   await admin.query((await readFile(new URL(`../sql/${file}`,import.meta.url),'utf8')).replace(/^BEGIN;\s*/i,'').replace(/COMMIT;\s*$/i,''));
   if(file==='001.sql') await admin.query('INSERT INTO settings(id,value) VALUES(1,$1)',[JSON.parse(await readFile(new URL('../defaults.json',import.meta.url),'utf8'))]);
  }
  const scoped=new URL(previous);scoped.searchParams.set('options',`-c search_path=${schema}`);process.env.DATABASE_URL=scoped.href;
  ({pool}=await import('../src/db.js'));
  const {startSearchRun,searchNext,runSearchStep,getSearchResults,controlSearch,getSearchCandidate,trackSearchCandidate,resolveSearchIdentity,correctSearchCandidate}=await import('../src/search.js');
  const {saveOffer}=await import('../src/store.js');const {offerInput}=await import('../src/domain.js');
  const applied='https://jobs.example.test/prior';
  await saveOffer(null,offerInput({company:'Fixture previa',title:'Developer previo',url:applied,availability:'abierta',review_state:'guardada',application_state:'enviada'}));
  const id=randomUUID();runId=id;
  await assert.rejects(()=>startSearchRun({id}),{status:409});
  await admin.query('UPDATE search_configuration SET recover_previous=false');
  await admin.query('UPDATE workflow_control SET enabled=true WHERE id=1');
  await assert.rejects(()=>startSearchRun({id}),{status:409});
  await admin.query('UPDATE search_settings SET history_ready=true,max_openings=1,batch_size=1,model_retries=1 WHERE id=1');
  await admin.query("UPDATE search_source_settings SET enabled=(source='arbeitnow')");
  assert.equal((await startSearchRun({id})).status,'running');
  assert.equal((await startSearchRun({id})).existing,true);
  let reads=0,extractions=0,decisions=0,fits=0;
  const day=new Date().toISOString().slice(0,10);
  const job={'@type':'JobPosting',title:'Developer junior',hiringOrganization:{name:'Fixture aislada'},datePosted:day,jobLocation:{address:{addressCountry:'ES'}},description:'Desarrollo de software. '.repeat(30)};
  const deps={evaluateFit:async()=>{fits++;return {state:'acreditado',value:'débil',evidence:'Desarrollo de software.'};},discoverSource:async source=>({checked_at:new Date().toISOString(),leads:[{source,external_id:'prior',company:'Fixture previa',title:'Developer previo',url:applied},{source,external_id:'new',company:'Fixture aislada',title:'Developer junior',url:'https://jobs.example.test/new'}]}),publicGet:async url=>{reads++;return {status:200,url,checked_at:new Date().toISOString(),text:`<script type="application/ld+json">${JSON.stringify(job)}</script>`};},extractField:async()=>{extractions++;return {state:'desconocido',value:'desconocido',evidence:''};},evaluateRule:async()=>{decisions++;return {state:'desconocido',value:'desconocido',evidence:''};}};
  let next=await searchNext(id);
  await assert.rejects(()=>runSearchStep(id,next.step_id,'read','1',deps));
  const first=await runSearchStep(id,next.step_id,next.kind,'1',deps);assert.equal(first.status,'succeeded');
  assert.equal((await runSearchStep(id,next.step_id,next.kind,'1',deps)).status,'succeeded');
  assert.equal((await admin.query('SELECT count(*)::int AS n FROM search_candidates')).rows[0].n,2);
  let state=(await getSearchResults(id)).state;
  const paused=await controlSearch(id,{action:'pause',revision:state.revision});
  assert.equal((await searchNext(id)).continue,false);
  await controlSearch(id,{action:'resume',revision:paused.revision});
  for(let count=0;count<70;count++) {
   next=await searchNext(id);if(!next.continue) break;
   if(['extract_company','decide_seniority','assess_fit'].includes(next.kind)) {
    const invalid=async()=>{throw Object.assign(new Error('Cita no literal de la prueba aislada'),{retryable:true});};
    const failureDeps={...deps,[next.kind.startsWith('extract_')?'extractField':next.kind==='assess_fit'?'evaluateFit':'evaluateRule']:invalid};
    assert.equal((await runSearchStep(id,next.step_id,next.kind,'1',failureDeps)).status,'pending');
    assert.equal((await getSearchResults(id)).state.control,'active');
    const retried=await searchNext(id);assert.equal(retried.step_id,next.step_id);
    if(next.kind==='decide_seniority') {
     assert.equal((await runSearchStep(id,next.step_id,next.kind,'1',failureDeps)).status,'failed');
     const stopped=(await getSearchResults(id)).state;assert.equal(stopped.control,'paused');
     await controlSearch(id,{action:'retry',revision:stopped.revision,step_id:next.step_id,reason:'Modelo revisado; recuperar solo la decisión fallida'});
     await searchNext(id);
    }
   }
   assert.equal((await runSearchStep(id,next.step_id,next.kind,'1',deps)).status,'succeeded',next.kind);
   if(count===69) assert.fail('Bucle no acotado');
  }
  assert.equal(reads,1);assert.equal(extractions,15);assert.equal(decisions,11);
  const run=(await admin.query('SELECT * FROM workflow_runs WHERE id=$1',[id])).rows[0];
  assert.equal(run.status,'succeeded');assert.equal(fits,1);
  assert.match(await readFile(new URL(`../reports/${id}/informe.md`,import.meta.url),'utf8'),/Objetivo de cupos no cumplido/);assert.equal(run.result.openings,1);assert.equal(run.result.spain,1);assert.equal(run.result.fulfilled,false);
  assert.equal(run.result.deficit_spain,12);assert.equal(run.result.deficit_europe,7);
  assert.equal(run.result.summary.computable,1);assert.equal(run.result.summary.b_computable,1);assert.equal(run.result.summary.fit['débil'],1);
  const rows=(await getSearchResults(id)).candidates;
  assert.equal(rows.find(row=>row.url===applied).stage,'excluded');
  assert.equal(rows.find(row=>row.url.endsWith('/new')).evaluation.classification,'B');
  assert.equal((await admin.query('SELECT count(*)::int AS n FROM search_documents')).rows[0].n,1);
  const candidate=rows.find(row=>row.url.endsWith('/new'));
  await assert.rejects(()=>correctSearchCandidate(candidate.id,{version:1,field:'decision:functions',value:'cumple',evidence:'inventado',reason:'No se admite'}));
  const corrected=await correctSearchCandidate(candidate.id,{version:1,field:'decision:functions',value:'cumple',evidence:'Desarrollo de software.',reason:'Confirmado en la descripción conservada'});
  assert.equal(corrected.version,2);assert.equal(corrected.events.length,1);
  const correctedFit=await correctSearchCandidate(candidate.id,{version:2,field:'fit',value:'favorable',evidence:'Desarrollo de software.',reason:'Encaje revisado por el usuario de la prueba aislada'});
  assert.equal(correctedFit.evaluation.fit,'favorable');assert.equal(correctedFit.evaluation.fit_evidence,'Desarrollo de software.');
  await assert.rejects(()=>correctSearchCandidate(candidate.id,{version:1,field:'country',value:'ES',evidence:'ES',reason:'Versión anterior'}),{status:409});
  const tracked=await trackSearchCandidate(candidate.id);
  const duplicateId=randomUUID();
  await admin.query("INSERT INTO search_candidates(id,run_id,source,url,company,title,hint,stage) VALUES($1,$2,'arbeitnow','https://jobs.example.test/alias','Fixture aislada','Developer junior','{}','blocked')",[duplicateId,id]);
  await admin.query("INSERT INTO search_candidate_links VALUES($1,'https://jobs.example.test/alias')",[duplicateId]);
  await resolveSearchIdentity(duplicateId,{version:1,resolution:'duplicate',duplicate_candidate_id:candidate.id,reason:'Mismo proceso confirmado por el usuario en la prueba aislada'});
  const main=await getSearchCandidate(candidate.id);assert.ok(main.links.includes('https://jobs.example.test/alias'));
  assert.equal((await getSearchCandidate(duplicateId)).evaluation.classification,'C');
  await assert.rejects(()=>resolveSearchIdentity(candidate.id,{version:main.version,resolution:'distinct',reason:'No puede eludir un ID ya registrado'}),{status:409});
  const offer=(await admin.query('SELECT * FROM offer_summary WHERE id=$1',[tracked.id])).rows[0];
  await saveOffer(offer.id,offerInput({...offer,application_state:'enviada',submitted_at:undefined,reason:'Inscripción de prueba en esquema aislado'}),offer.version);
  const after=(await getSearchResults(id)).candidates.find(row=>row.id===candidate.id);
  assert.equal(after.evaluation.classification,'C');assert.equal(after.evaluation.computable,false);
  const refreshed=(await admin.query('SELECT result FROM workflow_runs WHERE id=$1',[id])).rows[0].result;
  assert.equal(refreshed.spain,0);assert.equal(refreshed.deficit_spain,13);assert.equal(refreshed.summary.computable,0);assert.equal(refreshed.summary.b_computable,0);
  assert.match(await readFile(new URL(`../reports/${id}/informe.md`,import.meta.url),'utf8'),/España 13; Europa 7/);
  assert.ok((await admin.query('SELECT count(*)::int AS n FROM search_step_attempts')).rows[0].n>=28);
  // Un fallo no reinicia el lote ni borra intentos; cancelación conserva el avance.
  secondRunId=randomUUID();await startSearchRun({id:secondRunId});
  let failed=await searchNext(secondRunId);
  assert.equal((await runSearchStep(secondRunId,failed.step_id,failed.kind,'2',{discoverSource:async()=>{throw new Error('Fallo transitorio de prueba');}})).status,'failed');
  state=(await getSearchResults(secondRunId)).state;
  await assert.rejects(()=>controlSearch(secondRunId,{action:'resume',revision:state.revision}),{status:409});
  await controlSearch(secondRunId,{action:'retry',revision:state.revision,step_id:failed.step_id,reason:'Fuente recuperada; se repite solo descubrimiento'});
  failed=await searchNext(secondRunId);assert.equal((await runSearchStep(secondRunId,failed.step_id,failed.kind,'3',deps)).status,'succeeded');
  assert.equal((await admin.query('SELECT count(*)::int AS n FROM search_step_attempts WHERE step_id=$1',[failed.step_id])).rows[0].n,2);
  // Saltar una extracción o comparación incierta conserva la cadena y el dato desconocido.
  for(const kind of ['extract_company','decide_seniority','assess_fit']) {
   const stepId=randomUUID();
   const skipCandidate=(await admin.query("SELECT id FROM search_candidates WHERE run_id=$1 AND url LIKE '%/new'",[secondRunId])).rows[0].id;
   await admin.query("INSERT INTO search_steps(id,run_id,candidate_id,kind,task_key,input,status,priority) VALUES($1,$2,$3,$4,$5,'{}','unknown',10)",[stepId,secondRunId,skipCandidate,kind,`skip:${kind}`]);
   state=(await getSearchResults(secondRunId)).state;
   await controlSearch(secondRunId,{action:'skip',revision:state.revision,step_id:stepId,reason:'Respuesta interrumpida; continuar sin inferir el dato'});
   const skipped=(await admin.query('SELECT result FROM search_steps WHERE id=$1',[stepId])).rows[0].result;
   assert.equal(skipped.value,'desconocido');assert.equal(skipped.evidence,'');
   const successor=kind==='extract_company'?'extract_title':kind==='assess_fit'?'evaluate':'decide_experience';
   assert.equal((await admin.query("SELECT count(*)::int AS n FROM search_steps WHERE run_id=$1 AND candidate_id=$2 AND kind=$3 AND status='pending'",[secondRunId,skipCandidate,successor])).rows[0].n,1);
  }
  state=(await getSearchResults(secondRunId)).state;await controlSearch(secondRunId,{action:'cancel',revision:state.revision});
  assert.equal((await admin.query('SELECT result FROM workflow_runs WHERE id=$1',[secondRunId])).rows[0].result.reason,'cancelada');

 } finally {
  if(secondRunId) await rm(new URL(`../reports/${secondRunId}/`,import.meta.url),{recursive:true,force:true});
  if(runId) await rm(new URL(`../reports/${runId}/`,import.meta.url),{recursive:true,force:true});
  process.env.DATABASE_URL=previous;if(pool) await pool.end();
  await admin.query(`DROP SCHEMA IF EXISTS ${schema} CASCADE`);await admin.end();
 }
});
