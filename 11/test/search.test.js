import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {readFile,readdir,rm} from 'node:fs/promises';
import pg from 'pg';
import {finishBrowserTask,nextSearchTask} from '../test-support/browser-fixtures.js';
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
  const search=await import('../src/search.js');
  const {startSearchRun,searchNext,runSearchStep,getSearchResults,controlSearch,getSearchCandidate,trackSearchCandidate,resolveSearchIdentity,correctSearchCandidate}=search;
  const engine=search;
  const {saveOffer}=await import('../src/store.js');const {offerInput}=await import('../src/domain.js');
  const applied='https://8.8.8.8/prior';
  await saveOffer(null,offerInput({company:'Fixture previa',title:'Developer previo',url:applied,availability:'abierta',review_state:'guardada',application_state:'enviada'}));
  const id=randomUUID();runId=id;
  await assert.rejects(()=>startSearchRun({id}),{status:409});
  await admin.query('UPDATE search_configuration SET recover_previous=false');
  await admin.query('UPDATE workflow_control SET enabled=true WHERE id=1');
  await assert.rejects(()=>startSearchRun({id}),{status:409});
  await admin.query('UPDATE search_settings SET history_ready=true,max_openings=1,batch_size=1,model_retries=1 WHERE id=1');
  await admin.query("UPDATE search_source_settings SET enabled=(source='browser:google')");
  await admin.query('DELETE FROM search_queries WHERE configuration_id=1');
  await admin.query("INSERT INTO search_queries(id,configuration_id,zone,language,term) VALUES($1,1,'spain','en','Developer')",[randomUUID()]);
  assert.equal((await startSearchRun({id})).status,'running');
  assert.equal((await startSearchRun({id})).existing,true);
  let reads=0,extractions=0,decisions=0,fits=0;
  const day=new Date().toISOString().slice(0,10);
  const job={'@type':'JobPosting',title:'Developer junior',hiringOrganization:{name:'Fixture aislada'},datePosted:day,jobLocation:{address:{addressCountry:'ES'}},description:'Desarrollo de software. '.repeat(30)};
  const deps={evaluateFit:async()=>{fits++;return {state:'acreditado',value:'débil',evidence:'Desarrollo de software.'};},extractField:async()=>{extractions++;return {state:'desconocido',value:'desconocido',evidence:''};},evaluateRule:async()=>{decisions++;return {state:'desconocido',value:'desconocido',evidence:''};}};
  let next=await searchNext(id);
  assert.equal(next.status,'awaiting_browser');assert.equal(next.kind,'discover');
  await assert.rejects(()=>runSearchStep(id,next.step_id,next.kind,'1',deps),{status:409});
  const candidates=[{title:'Developer previo',company:'Fixture previa',url:applied},{title:'Developer junior',company:'Fixture aislada',url:'https://8.8.8.8/new'}];
  assert.equal((await finishBrowserTask(engine,id,next,{candidates})).accepted,2);
  assert.equal((await search.submitBrowserDiscovery(id,next.step_id,{page_urls:[next.url || 'https://www.google.com/search?q=Developer'],truncated:false,candidates})).status,'already_completed');
  assert.equal((await admin.query('SELECT count(*)::int AS n FROM search_candidates')).rows[0].n,2);
  let state=(await getSearchResults(id)).state;
  const paused=await controlSearch(id,{action:'pause',revision:state.revision});
  assert.equal((await searchNext(id)).continue,false);
  await controlSearch(id,{action:'resume',revision:paused.revision});
  for(let count=0;count<70;count++) {
   next=await nextSearchTask(engine,id,{read:()=>{reads++;return {};}});if(!next.continue) break;
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
  await admin.query('UPDATE search_configuration SET recover_previous=true,reuse_evidence=true');
  const continuityPriorId=randomUUID();
  await startSearchRun({id:continuityPriorId});
  await admin.query("UPDATE workflow_runs SET status='succeeded',finished_at=now() WHERE id=$1",[continuityPriorId]);
  const {readJobPosting}=await import('../src/sources.js');
  const continuityCandidateId=randomUUID(),continuityStepId=randomUUID();
  const continuityUrl='https://8.8.8.8/continuity';
  const continuityAlias='https://8.8.8.8/continuity?utm_source=old';
  const continuityEvidence='Desarrollo de software.';
  const priorExtraction={state:'acreditado',value:'Desarrollo de software',evidence:continuityEvidence};
  const priorFit={state:'acreditado',value:'favorable',evidence:continuityEvidence};
  const priorDocument=readJobPosting(`<script type="application/ld+json">${JSON.stringify({...job,title:'Developer continuidad',hiringOrganization:{name:'Fixture continuidad'},url:'https://8.8.8.8/continuity'})}</script>`);
  assert.equal(priorDocument.complete,true);
  const appliedCandidateId=randomUUID();
  const addFinalist=(candidateId,externalId,url,company,title,classification)=>admin.query("INSERT INTO search_candidates(id,run_id,source,external_id,url,company,title,hint,process_id,identity_resolution,evaluation,stage) VALUES($1,$2,'arbeitnow',$3,$4,$5,$6,'{}',$1,'distinct',$7,'evaluated')",[candidateId,continuityPriorId,externalId,url,company,title,{classification,computable:classification==='A',fit:'favorable'}]);
  await addFinalist(continuityCandidateId,'continuity',continuityUrl,'Fixture continuidad','Developer continuidad','A');
  await addFinalist(appliedCandidateId,'applied',applied,'Fixture previa','Developer previo','B');
  await admin.query('INSERT INTO search_candidate_links(candidate_id,url) VALUES($1,$2)',[continuityCandidateId,continuityAlias]);
  await admin.query("INSERT INTO search_documents(candidate_id,run_id,url,status,http_status,text,job,checked_at) VALUES($1,$2,$3,'complete',200,$4,$5,now())",[continuityCandidateId,continuityPriorId,continuityUrl,priorDocument.text,priorDocument.job]);
  await admin.query("INSERT INTO search_steps(id,run_id,candidate_id,task_key,kind,priority,status,result) VALUES($1,$2,$3,'continuity:extract:company','extract_company',10,'succeeded',$4)",[continuityStepId,continuityPriorId,continuityCandidateId,priorExtraction]);
  await admin.query("INSERT INTO search_candidate_overrides(candidate_id,field,value,evidence,reason) VALUES($1,'fit',$2,$3,'Corrección previa confirmada')",[continuityCandidateId,priorFit,continuityEvidence]);
  await admin.query('UPDATE search_settings SET max_openings=3 WHERE id=1');
  secondRunId=randomUUID();await startSearchRun({id:secondRunId});
  let failed=await searchNext(secondRunId);
  assert.equal(failed.kind,'recover');
  assert.equal((await runSearchStep(secondRunId,failed.step_id,failed.kind,'2',deps)).status,'succeeded');
  assert.equal((await admin.query('SELECT result FROM search_steps WHERE id=$1',[failed.step_id])).rows[0].result.accepted,2);
  assert.equal((await admin.query('SELECT count(*)::int AS n FROM search_candidates WHERE run_id=$1',[secondRunId])).rows[0].n,2);
  failed=await searchNext(secondRunId);assert.equal(failed.status,'awaiting_browser');assert.equal(failed.kind,'discover');
  const claimed=await search.claimBrowserTask(secondRunId);
  await admin.query("UPDATE search_step_attempts SET status='failed',error='Fallo de navegador aislado',finished_at=now() WHERE step_id=$1 AND status='running'",[claimed.step_id]);
  await admin.query("UPDATE search_steps SET status='failed',error='Fallo de navegador aislado',finished_at=now() WHERE id=$1",[claimed.step_id]);
  await admin.query("UPDATE search_run_state SET control='paused',revision=revision+1 WHERE run_id=$1",[secondRunId]);
  state=(await getSearchResults(secondRunId)).state;
  await assert.rejects(()=>controlSearch(secondRunId,{action:'resume',revision:state.revision}),{status:409});
  await controlSearch(secondRunId,{action:'retry',revision:state.revision,step_id:failed.step_id,reason:'Fuente recuperada; se repite solo descubrimiento'});
  failed=await searchNext(secondRunId);assert.equal(failed.status,'awaiting_browser');
  await finishBrowserTask(engine,secondRunId,failed,{candidates:[]});
  assert.equal((await admin.query('SELECT count(*)::int AS n FROM search_step_attempts WHERE step_id=$1',[failed.step_id])).rows[0].n,2);
  let continuityStep;
  for(let index=0;index<5;index++) {
   continuityStep=await searchNext(secondRunId);
   if(continuityStep.status==='awaiting_browser') break;
   assert.equal(continuityStep.kind,'precheck');
   await runSearchStep(secondRunId,continuityStep.step_id,continuityStep.kind,String(4+index),deps);
  }
  assert.equal(continuityStep.status,'awaiting_browser');assert.equal(continuityStep.kind,'read');
  const readsBeforeContinuity=reads;
  await finishBrowserTask(engine,secondRunId,continuityStep,{read:()=>{reads++;return {};}});
  continuityStep=await nextSearchTask(engine,secondRunId,{read:()=>{reads++;return {};}});
  assert.equal(continuityStep.kind,'extract_company');
  assert.equal(reads,readsBeforeContinuity+1);
  const recovered=(await admin.query('SELECT * FROM search_candidates WHERE run_id=$1 AND prior_candidate_id=$2',[secondRunId,continuityCandidateId])).rows[0];
  assert.ok(recovered);
  const inherited=(await admin.query("SELECT value FROM search_candidate_events WHERE candidate_id=$1 AND kind='continuity'",[recovered.id])).rows[0].value;
  assert.deepEqual(inherited.inherited,['fit']);
  assert.ok((await admin.query('SELECT url FROM search_candidate_links WHERE candidate_id=$1',[recovered.id])).rows.some(row=>row.url===continuityAlias));
  continuityStep=await searchNext(secondRunId);assert.equal(continuityStep.kind,'extract_company');
  await runSearchStep(secondRunId,continuityStep.step_id,continuityStep.kind,'6',deps);
  const reused=(await admin.query('SELECT input,result FROM search_steps WHERE id=$1',[continuityStep.step_id])).rows[0];
  assert.equal(reused.input.reused_from_step,continuityStepId);
  assert.deepEqual(reused.result,priorExtraction);
  let recalculated=false;
  for(let index=0;index<35;index++) {
   const next=await searchNext(secondRunId);assert.equal(next.continue,true);
   const result=await runSearchStep(secondRunId,next.step_id,next.kind,String(20+index),deps);
   assert.equal(result.status,'succeeded',next.kind);
   if(next.kind==='evaluate') {recalculated=true;break;}
  }
  assert.equal(recalculated,true);
  const currentEvaluation=(await admin.query('SELECT evaluation FROM search_candidates WHERE id=$1',[recovered.id])).rows[0].evaluation;
  assert.equal(currentEvaluation.fit,'favorable');
  assert.equal(currentEvaluation.classification,'B');
  continuityStep=await searchNext(secondRunId);assert.equal(continuityStep.kind,'batch');
  await runSearchStep(secondRunId,continuityStep.step_id,continuityStep.kind,'61',deps);
  continuityStep=await searchNext(secondRunId);
  for(let index=0;continuityStep.kind==='precheck' && index<5;index++) {
   await runSearchStep(secondRunId,continuityStep.step_id,continuityStep.kind,String(70+index),deps);
   continuityStep=await searchNext(secondRunId);
  }
  assert.equal(continuityStep.kind,'audit');
  const checkedApplied=(await admin.query('SELECT id FROM search_candidates WHERE run_id=$1 AND prior_candidate_id=$2',[secondRunId,appliedCandidateId])).rows[0].id;
  assert.equal((await admin.query('SELECT stage FROM search_candidates WHERE id=$1',[checkedApplied])).rows[0].stage,'excluded');
  assert.equal((await admin.query('SELECT count(*)::int AS n FROM search_documents WHERE candidate_id=$1',[checkedApplied])).rows[0].n,0);
  // Saltar una extracción o comparación incierta conserva la cadena y el dato desconocido.
  const skipCandidate=randomUUID();
  await admin.query("INSERT INTO search_candidates(id,run_id,source,url,company,title,hint,process_id,stage) VALUES($1,$2,'browser:google','https://8.8.8.8/skip','Fixture pendiente','Developer','{}',$1,'lead')",[skipCandidate,secondRunId]);
  for(const kind of ['extract_company','decide_seniority','assess_fit']) {
   const stepId=randomUUID();
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
